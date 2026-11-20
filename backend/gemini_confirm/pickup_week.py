"""Pick up the Gemini independent-confirmation run for one week and publish a per-seat verdict.

Reads <week>/<SYM>/gemini/* written by the Antigravity routine (see GEMINI_MASTER_PROMPT.md),
validates each file, checks the run stayed BLIND (its own record saved before it opened ours),
grades Gemini's record with OUR deterministic rules (derive_grade + numeric gate), compares it
with Claude's record, and classifies each seat:

  confirmed     - a blind second model lands within 15% of our base value, grades it a buy or a
                  wait (not a pass), sees upside, and its skeptic did not knock our record down
  repriced      - same direction, but the value moved: base gap 15-30%, or its skeptic found a
                  number in our record that did not hold up (a correction, not a kill)
  disagreement  - base gap over 30%, Gemini says pass / no upside, or its skeptic killed our
                  thesis, moat or catalyst
  unverified    - Gemini's files are missing/invalid or the run was not blind: no badge

Writes backend/_opus_debate/gemini_confirmations.json, frontend/public/speculair_gemini_confirm.json
(fallback copy), <week>/CONFIRMATION_RESULTS.json, and pushes scans/speculair_gemini_confirm.json.
Advisory only: it never touches a seat, weight, grade or conviction.

usage:  python backend/gemini_confirm/pickup_week.py [--week-dir PATH] [--no-push]
"""
import argparse
import copy
import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

logging.disable(logging.CRITICAL)
REPO = Path(__file__).resolve().parents[2]
D = REPO / "backend" / "_opus_debate"
sys.path.insert(0, str(D)); sys.path.insert(0, str(REPO / "backend"))
from _post_common import derive_grade      # noqa: E402
from _numeric_gate import check_record    # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _disagree as DIS                   # noqa: E402  what each disagreement is about + the ledger (2026-11-19)

LEDGER = D / "_disagreements.jsonl"
EXPORT_INDEX = D / "gemini_export_index.json"

ROOT = Path(r"C:\Users\Bruno\Documents\Speculair")
BUCKET = "screener-signals-carbonbridge"
CONFIRM_GAP, REPRICE_GAP = 0.15, 0.30
REVISION_GAP = 0.10
HARD_KILL_SCOPES = {"thesis", "moat", "catalyst"}
REQ = ["symbol", "live_price", "price_currency", "valuation", "bull_thesis", "bear_thesis", "sop_fair_value",
       "catalyst_status", "verdict", "conviction", "thesis_state", "thesis_evidence", "entry_mode",
       "moat", "secular_threat", "moderator_conclusion"]
ENUM = {"catalyst_status": {"FIRED", "ARB", "PENDING_HARD", "SOFT_EXTENDED", "UNVERIFIABLE"},
        "thesis_state": {"INTACT", "IMPAIRED", "BROKEN"}, "entry_mode": {"NOW", "AT_LEVEL", "ON_EVENT", "NONE"}}


def _num(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def latest_week_dir(root=ROOT):
    weeks = [p for p in root.glob("*/Week *") if (p / "picks.json").exists()]
    return max(weeks, key=lambda p: (p.parent.name, int(p.name.split()[-1]))) if weeks else None


def classify(g_base, c_base, price, g_letter, skA):
    """(status, reasons[]) from the comparable numbers - pure, unit-testable."""
    why = []
    gap = (g_base / c_base - 1) if g_base and c_base else None
    v = str((skA or {}).get("verdict") or "").upper()
    scope = str((skA or {}).get("kill_scope") or "").lower()
    rev = _num((skA or {}).get("revised_fv_px"))
    if g_letter == "C":
        why.append("the second model would pass on it")
    if g_base and price and g_base <= price:
        why.append("the second model sees no upside from today's price")
    if v == "REFUTED" and scope in HARD_KILL_SCOPES:
        why.append(f"its skeptic found our {scope} did not hold up")
    if gap is not None and abs(gap) > REPRICE_GAP:
        why.append(f"its value is {gap * 100:+.0f}% from ours")
    if why:
        return "disagreement", why
    if gap is not None and abs(gap) > CONFIRM_GAP:
        why.append(f"its value is {gap * 100:+.0f}% from ours")
    if v == "REFUTED":
        why.append("its skeptic corrected a number in our record"
                   + (f" (revised value {rev:g}, {(rev / c_base - 1) * 100:+.0f}%)" if rev and c_base else ""))
    elif rev and c_base and abs(rev / c_base - 1) > REVISION_GAP:
        why.append(f"its skeptic revised our value to {rev:g} ({(rev / c_base - 1) * 100:+.0f}%)")
    if why:
        return "repriced", why
    return "confirmed", [f"its value is {gap * 100:+.0f}% from ours" if gap is not None else "values agree"]


def pickup(week_dir, push=True):
    picks = json.load(open(week_dir / "picks.json", encoding="utf-8"))
    quad = json.load(open(D / "macro_regime.json", encoding="utf-8")).get("quadrant")
    out = {"week": picks["week"], "generated_at": datetime.now().isoformat(timespec="seconds"),
           "model": "gemini-4-argon", "method": "blind second debate + two-way skeptic, graded with our rules",
           "scope": picks.get("scope") or "seats", "picks": {}}
    # which names we hold: the universe export keeps this map OUT of the week folder (blindness)
    try:
        held = (json.load(open(EXPORT_INDEX, encoding="utf-8")).get(picks["week"]) or {}).get("books") or {}
    except Exception:
        held = {}
    ledger_rows = []
    for p in picks["picks"]:
        s = p["symbol"]
        g = week_dir / s / "gemini"
        e = {"symbol": s, "books": p.get("books") or held.get(s) or [], "issues": []}
        if not g.exists() or not any(g.glob("*")):
            e.update(status="not_run", reasons=["Gemini did not reach this name this week"])
            out["picks"][s] = e
            print(f"{s:10} not_run")
            continue

        def load(n):
            try:
                t = (g / n).read_text(encoding="utf-8")
                return json.loads(t) if n.endswith(".json") else t
            except Exception as ex:
                e["issues"].append(f"{n} unreadable ({type(ex).__name__})")
                return None

        # universe weeks (2026-11-19): the skeptic passes are optional per name - a blind record alone is
        # still a comparison (value and grade); only the record and the dossier are required
        opt = lambda n: load(n) if (g / n).exists() else None     # noqa: E731
        rec, skA, skB, run = load("record.json"), opt("skeptic_on_claude.json"), opt("skeptic_on_gemini.json"), load("run.json")
        load("dossier.md")
        claude = json.load(open(D / "results_regime" / f"{s}.json", encoding="utf-8"))
        cv = claude.get("valuation") or {}
        # blindness: Gemini's own record must be saved before it opened our record (skeptic pass A);
        # with no pass A it never opened our record, so the record is blind by construction
        try:
            blind = (not (g / "skeptic_on_claude.json").exists()
                     or os.path.getmtime(g / "record.json") < os.path.getmtime(g / "skeptic_on_claude.json"))
        except OSError:
            blind = False
        if not blind:
            e["issues"].append("not blind: its record was saved after it had read ours")
        if rec:
            miss = [k for k in REQ if k not in rec]
            if miss:
                e["issues"].append("missing fields: " + ", ".join(miss))
            for k, ok in ENUM.items():
                if rec.get(k) not in ok:
                    e["issues"].append(f"{k} not a valid value ({rec.get(k)!r})")
        if not skA:
            e["issues"].append("no skeptic pass on our record this week (value and grade compared only)")
        if (run or {}).get("status") not in ("complete", "partial"):
            e["issues"].append(f"run status {(run or {}).get('status')!r}")
        gv = (rec or {}).get("valuation") or {}
        gg = copy.deepcopy(rec or {})
        try:
            derive_grade(gg, quadrant=quad, live_px=gv.get("live_price"))
        except Exception:
            pass
        try:
            gate = check_record(copy.deepcopy(rec or {})).get("gate")
        except Exception:
            gate = None
        ccy_ok = str(gv.get("price_currency") or "").upper() == str(cv.get("price_currency") or claude.get("price_currency") or "").upper()
        if rec and not ccy_ok:
            e["issues"].append(f"currency {gv.get('price_currency')} vs ours {cv.get('price_currency') or claude.get('price_currency')}")
        e["gemini"] = {k: _num(gv.get(k)) for k in ("bear_px", "base_fv_px", "bull_px", "live_price")}
        e["gemini"].update(currency=gv.get("price_currency"), grade=gg.get("verdict"), thesis_state=(rec or {}).get("thesis_state"),
                           entry_mode=(rec or {}).get("entry_mode"), conviction=(rec or {}).get("conviction"), numeric_gate=gate)
        e["claude"] = {k: _num(cv.get(k)) for k in ("bear_px", "base_fv_px", "bull_px", "live_price")}
        e["claude"].update(currency=cv.get("price_currency") or claude.get("price_currency"), grade=claude.get("verdict"),
                           thesis_state=claude.get("thesis_state"), entry_mode=claude.get("entry_mode"))
        e["skeptic_on_ours"] = {k: (skA or {}).get(k) for k in ("verdict", "kill_scope", "revised_fv_px", "correction_severity")}
        e["skeptic_on_ours"]["finding"] = str((skA or {}).get("kill_fact") or (skA or {}).get("corrections") or "")[:600]
        e["skeptic_on_ours"]["corrections_typed"] = [
            {k: (c or {}).get(k) for k in ("field", "from", "to")} | {"basis": str((c or {}).get("basis") or "")[:400]}
            for c in ((skA or {}).get("corrections_typed") or []) if isinstance(c, dict)][:8]
        e["skeptic_on_ours"]["fact_disputes"] = DIS.fact_disputes(skA)
        e["skeptic_on_its_own"] = {k: (skB or {}).get(k) for k in ("verdict", "kill_scope", "revised_fv_px")}
        e["blind"] = blind
        valid = bool(rec) and blind and ccy_ok and not any(i.startswith(("missing", "currency")) for i in e["issues"])
        if not valid:
            e["status"], e["reasons"] = "unverified", list(e["issues"])
        else:
            price = e["gemini"]["live_price"] or e["claude"]["live_price"]
            e["status"], e["reasons"] = classify(e["gemini"]["base_fv_px"], e["claude"]["base_fv_px"], price,
                                                 e["gemini"]["grade"], skA)
            dis = DIS.classify(claude, rec, skA, gemini_grade=e["gemini"]["grade"])
            e["disagreement_kind"], e["gap_pct"], e["disagreement"] = dis["kind"], dis["gap_pct"], dis
            ledger_rows.append({
                "week": picks["week"], "picked_up_at": out["generated_at"], "symbol": s, "held_in": e["books"],
                "status": e["status"], "kind": dis["kind"], "direction": dis["direction"], "gap_pct": dis["gap_pct"],
                "grades": dis["grades"], "disputes": dis["disputes"], "newer_facts": dis["newer_facts"],
                "claude": {"base_fv_px": e["claude"]["base_fv_px"], "live_price": e["claude"]["live_price"],
                           "as_of": dis["claude_as_of"], "grade": e["claude"]["grade"]},
                "gemini": {"base_fv_px": e["gemini"]["base_fv_px"], "live_price": e["gemini"]["live_price"],
                           "grade": e["gemini"]["grade"], "currency": e["gemini"]["currency"]},
                "skeptic": {k: e["skeptic_on_ours"].get(k) for k in ("verdict", "kill_scope", "revised_fv_px",
                                                                     "correction_severity")},
                "price_at_pickup": e["gemini"]["live_price"] or e["claude"]["live_price"],
                "resolution": None})
        gb, cb, ccy = e["gemini"]["base_fv_px"], e["claude"]["base_fv_px"], e["gemini"]["currency"] or ""
        lead = {"confirmed": "Second opinion agrees", "repriced": "Second opinion agrees on direction, not on the number",
                "disagreement": "Second opinion disagrees", "unverified": "Second opinion not usable this week"}[e["status"]]
        e["summary"] = (f"{lead}. A different AI model (Gemini), working blind from the filings, valued it at "
                        f"{ccy} {gb:g} against our {cb:g}" if gb and cb else lead) + \
                       (". " + "; ".join(e["reasons"]) + "." if e["reasons"] else ".") + \
                       (f" Its skeptic on our record: {e['skeptic_on_ours']['finding'][:240]}" if e["skeptic_on_ours"].get("verdict") == "REFUTED" else "")
        out["picks"][s] = e
        print(f"{s:10} {e['status']:12} G {gb} vs C {cb} | {'; '.join(e['reasons'])[:150]}")
    for path in (D / "gemini_confirmations.json", REPO / "frontend" / "public" / "speculair_gemini_confirm.json",
                 week_dir / "CONFIRMATION_RESULTS.json"):
        path.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    counts, kinds = {}, {}
    for e in out["picks"].values():
        counts[e["status"]] = counts.get(e["status"], 0) + 1
        if e.get("disagreement_kind"):
            kinds[e["disagreement_kind"]] = kinds.get(e["disagreement_kind"], 0) + 1
    print(f"gemini-pickup {out['week']}: {counts}")
    # DISAGREEMENT LEDGER: resolve open rows from our latest records, then log this week's comparisons
    try:
        records = {}
        for f in (D / "results_regime").glob("*.json"):
            try:
                records[f.stem] = json.load(open(f, encoding="utf-8"))
            except Exception:
                continue
        rows, resolved = DIS.update_ledger(LEDGER, out["week"], ledger_rows, records)
        open_n = sum(1 for r in rows if r.get("resolution") is None)
        print(f"disagreements {out['week']}: " + (" | ".join(f"{k} {v}" for k, v in
              sorted(kinds.items(), key=lambda kv: DIS.KIND_ORDER.index(kv[0]) if kv[0] in DIS.KIND_ORDER else 9))
              or "none compared") + f" | ledger {len(rows)} row(s), {resolved} resolved now, {open_n} open -> {LEDGER.name}")
    except Exception as ex:
        print(f"WARN disagreements: ledger not updated ({type(ex).__name__}: {ex})")
    if push:
        local = REPO / "frontend" / "public" / "speculair_gemini_confirm.json"
        r = subprocess.run(f'gcloud storage cp "{local}" "gs://{BUCKET}/scans/speculair_gemini_confirm.json"',
                           shell=True, capture_output=True, text=True)
        print("  GCS push scans/speculair_gemini_confirm.json:", "OK" if r.returncode == 0 else f"FAILED {r.stderr[-200:]}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--week-dir")
    ap.add_argument("--no-push", action="store_true")
    a = ap.parse_args()
    wd = Path(a.week_dir) if a.week_dir else latest_week_dir()
    if not wd or not (wd / "GEMINI_DONE.json").exists():
        print(f"gemini-pickup: no finished Gemini week found ({wd}) - nothing to do")
        sys.exit(0)
    pickup(wd, push=not a.no_push)
