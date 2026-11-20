"""Weekly hand-off to the Gemini independent-confirmation routine (Antigravity).

After the weekly debate + value lens publish, write one folder per pick to
C:\\Users\\Bruno\\Documents\\Speculair\\<year>\\Week <ISO week>\\<SYM>\\ with the exact production debate +
skeptic prompts for that symbol, STRICT-blind inputs (no earlier answer about the name, none of our
scan's fair values / margins of safety / peer verdicts), a manifest with live listing facts (price,
trading vs reporting currency, live FX, share count), and Claude's record isolated in step2_skeptic/
for the skeptic-on-Claude pass. Gemini writes its results into <SYM>/gemini/; pickup_week.py
validates them and logs every disagreement.

Scope (2026-11-19, Bruno: "focus not only on the 10 seats but in every pick debated"):
  debated (default) - every name this week's committee actually debated (full debates + the light
                      weekly updates of held seats; carried records and ledger re-checks excluded),
                      plus every seat. Nothing in the week folder says which names we hold: that map
                      is kept in backend/_opus_debate/gemini_export_index.json for the pickup.
  seats             - the old routine: the seated picks only.

usage:  python backend/gemini_confirm/export_week.py [--date YYYY-MM-DD] [--root PATH] [--scope debated|seats]
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[2]
D = REPO / "backend" / "_opus_debate"
HERE = Path(__file__).resolve().parent
DEFAULT_ROOT = Path(r"C:\Users\Bruno\Documents\Speculair")
FMP = "https://financialmodelingprep.com/stable"
GEMINI_OUTPUTS = ("dossier.md", "record.json", "skeptic_on_claude.json", "skeptic_on_gemini.json", "run.json")


def fmp_key():
    for line in (REPO / "frontend" / ".env.local").read_text(encoding="utf-8").splitlines():
        if line.startswith("FMP_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def fmp(path, **params):
    try:
        r = requests.get(f"{FMP}/{path}", params={**params, "apikey": fmp_key()}, timeout=25).json()
        return r if isinstance(r, list) else []
    except Exception:
        return []


EXPORT_INDEX = D / "gemini_export_index.json"   # {week: {symbol: [books]}} - kept OUT of the week folder


def seats():
    out = {}
    for book, f in (("apex", "apex_basket_opus_regime.json"), ("value", "apex_basket_value.json")):
        for p in json.load(open(D / f, encoding="utf-8")).get("apex_basket", []):
            out.setdefault(p["symbol"], []).append(book)
    return out


def debated_this_run(res_dir=None):
    """Names whose record this run is a real debate: a full underwrite or a held seat's weekly update.
    Carried records (restamped, not re-argued) and forensic-ledger re-checks are left out."""
    res_dir = Path(res_dir) if res_dir else D / "results_regime"
    out = set()
    for f in sorted(res_dir.glob("*.json")):
        try:
            r = json.load(open(f, encoding="utf-8"))
        except Exception:
            continue
        if r.get("carried") or str(r.get("source") or "") == "ledger_recheck":
            continue
        out.add(f.stem)
    return out


def picks_for(scope, res_dir=None):
    """{symbol: books} for the export. Seats always ride along; books stay [] for non-seats."""
    held = seats()
    if scope == "seats":
        return held
    names = debated_this_run(res_dir) | set(held)
    return {s: held.get(s, []) for s in sorted(names)}


def capture(sym, online, tmp):
    out = tmp / f"cap_{sym}.json"
    args = ["node", str(HERE / "capture_prompts.mjs"), str(D / "_weekly_debate.js"), sym, str(out)]
    if online:
        args.append("--online")
    subprocess.run(args, check=True, capture_output=True, cwd=REPO)
    cap = {c["label"]: c["prompt"] for c in json.loads(out.read_text(encoding="utf-8"))}
    return cap.get(f"debate:{sym}") or cap[f"debate:{sym}(web)"], cap[f"skeptic:{sym}"]


# Bundle fields that carry an earlier answer about this name. Every one is nulled before export:
# prior_record = our last committee answer; washout = the entry level we set; second_opinion = the
# last Gemini comparison, which quotes OUR base value (our_base_fv_px) - it was added to the bundles
# on 2026-11-12 and leaked into the Week 47 export until 2026-11-19; dossier = our forensic dossier.
BLIND_NULL_FIELDS = ("prior_record", "washout", "second_opinion", "dossier")
# Text that must never appear in a blind attachment (checked by leak_scan after every export).
LEAK_MARKERS = ("our_base_fv_px", "their_base_fv_px", "Margin of Safety", "answer_source")


def strip_inputs(inp):
    """STRICT blind: drop every earlier answer about this name and every OUR-scan valuation output."""
    removed = {k: inp.get(k) for k in BLIND_NULL_FIELDS}
    for k in BLIND_NULL_FIELDS:
        if k in inp:
            inp[k] = None
    kept = []
    for line in str(inp.get("metrics_str") or "").split("\n"):
        if line.startswith("Valuation:"):
            line = re.sub(r"\s*\|\s*(Fair Value|Margin of Safety) [^|]*", "", line)
        elif line.startswith(("Valuation models (stock page)", "Per-method margin-of-safety")):
            continue
        kept.append(line)
    inp["metrics_str"] = "\n".join(kept)
    return removed


def leak_scan(att_dir):
    """Problems found in one pick's blind attachments ([] = clean). Structural on the input bundles
    (a non-null earlier-answer field), textual on every JSON attachment (LEAK_MARKERS)."""
    problems = []
    for f in sorted(Path(att_dir).glob("*.json")):
        text = f.read_text(encoding="utf-8")
        if f.name.startswith("inputs__"):
            d = json.loads(text)
            problems += [f"{f.name}: {k} is not empty" for k in BLIND_NULL_FIELDS if d.get(k)]
        problems += [f"{f.name}: contains '{m}'" for m in LEAK_MARKERS if m in text]
    return problems


def strip_peers(pg):
    rc = str(pg.get("relative_comps") or "")
    rc = re.sub(r"Valuation:.*?(?=Growth:|Margins:|Trend:|$)", "", rc, flags=re.S)
    rc = re.sub(r"\b(?:[A-Za-z-]+\s){0,3}MoS\s*\([^)]*\)\s*(?:and\s+)?", "", rc)
    rc = re.sub(r",\s*versus[^.]*?\b(?:rich|cheap)\w*[^.]*", "", rc)
    rc = re.sub(r"\b(DCF|OE|Graham|EPV|IV15|Buffett) (MoS )?[+-]?\d+%,?\s*", "", rc)
    # any sentence that carries a valuation-model read or a cheap/rich judgement goes (the wording of
    # these Radar notes is free-form; the raw multiples and growth figures are in the inputs bundle)
    rc = ". ".join(s.rstrip(". ") for s in re.split(r"(?<=[a-z0-9%)])\.\s+", rc)
                   if not re.search(r"\bMoS\b|margin[- ]of[- ]safety|\bDCF\b|\bGraham\b|\bEPV\b|owner earnings|"
                                    r"\bIV15\b|\bBuffett\b|fair value|\b(cheap|cheapest|discount|mispric|"
                                    r"undervalu|overvalu|rich)\w*", s, re.I))
    pg["relative_comps"] = (rc + ".") if rc and not rc.endswith(".") else rc
    pg.pop("verdict", None)
    return pg


def listing_facts(sym):
    """Live facts the agent must reconcile against (it must still verify and state its own)."""
    q = (fmp("quote", symbol=sym) or [{}])[0]
    prof = (fmp("profile", symbol=sym) or [{}])[0]
    inc = (fmp("income-statement", symbol=sym, period="quarter", limit=1) or [{}])[0]
    trade_ccy = prof.get("currency")
    rep_ccy = inc.get("reportedCurrency")
    fx, note = None, "unknown - verify"
    if trade_ccy and rep_ccy:
        t, r = trade_ccy.upper(), rep_ccy.upper()
        if t != r:
            fx = (fmp("quote", symbol=f"{r}{t}") or [{}])[0].get("price")
            if trade_ccy == "GBp":                     # pence: 100 per pound on top of any FX
                fx = fx * 100 if fx else None
        elif trade_ccy == "GBp" and rep_ccy == "GBP":
            fx = 100.0
        note = (f"1 {rep_ccy} = {fx} {trade_ccy} (live FMP quote at export"
                + ("; GBp = pence, 100 per pound" if trade_ccy == "GBp" else "") + ")") if fx else \
            "trading and reporting currency are the same"
    # Two share counts, both labelled: FMP's "outstanding" figure can be a vendor error (9980.HK read
    # 895.5M against 727.1M in its own filing, 2026-10), and the filed quarterly diluted average lags
    # buybacks. A >10% gap is flagged so the agent settles it from the filing, never by guessing.
    fl = (fmp("shares-float", symbol=sym) or [{}])[0]
    s_vendor = fl.get("outstandingShares")
    s_filed = inc.get("weightedAverageShsOutDil")
    gap = (s_vendor / s_filed - 1) if s_vendor and s_filed else None
    return {
        "company": q.get("name") or prof.get("companyName"),
        "exchange": q.get("exchange") or prof.get("exchange"),
        "price": q.get("price"), "price_timestamp": q.get("timestamp"),
        "trading_currency": trade_ccy,
        "reporting_currency": rep_ccy,
        "fx_reporting_to_trading": fx,
        "fx_note": note,
        "shares_filed_diluted_avg": s_filed,
        "shares_filed_period": inc.get("date"),
        "shares_vendor_outstanding": s_vendor,
        "shares_note": ("CONFLICT: the two counts differ by {:+.0f}% - settle it from the latest filing and say which "
                        "you used".format(gap * 100) if gap is not None and abs(gap) > 0.10 else
                        "the counts agree within 10%") + "; VERIFY against the latest filing - bonus issues, splits "
                        "and buybacks change it",
        "next_earnings_hint": (fmp("earnings", symbol=sym, limit=2) or [{}])[0].get("date"),
    }


def adapter(mapping, writes):
    lines = ["=== ANTIGRAVITY ADAPTER (added for the Gemini confirmation run - not part of the production prompt) ===",
             "- Paths below are relative to THIS pick's folder. Read files from disk; the production paths map as:"]
    lines += [f"    {a}  ->  {b}" for a, b in mapping]
    lines += [f"- {writes}",
              "- 'FMP MCP tools' / ToolSearch / WebSearch / WebFetch / Quartr = your own web search and browsing.",
              "- 'Claude Opus 5' = you. Ignore 'Reply exactly: DONE'.",
              "=== ORIGINAL PRODUCTION PROMPT (verbatim) ===", ""]
    return "\n".join(lines)


def export(run_day, root, scope="debated"):
    iso_year, iso_week, _ = run_day.isocalendar()
    week_dir = root / str(iso_year) / f"Week {iso_week}"
    week_dir.mkdir(parents=True, exist_ok=True)
    tmp = week_dir / "_tmp"
    tmp.mkdir(exist_ok=True)
    picks = picks_for(scope)
    blind_books = scope != "seats"          # universe export: never tell the second model what we hold
    week_label = f"{iso_year}-W{iso_week:02d}"
    try:
        idx = json.load(open(EXPORT_INDEX, encoding="utf-8"))
    except Exception:
        idx = {}
    idx[week_label] = {"scope": scope, "exported_at": datetime.now().isoformat(timespec="seconds"),
                       "books": {s: b for s, b in picks.items() if b}}
    EXPORT_INDEX.write_text(json.dumps(idx, indent=1, ensure_ascii=False), encoding="utf-8")
    index = []
    for sym, books in sorted(picks.items()):
        pdir = week_dir / sym
        if pdir.exists():
            for sub in ("step1_debate", "step2_skeptic"):
                shutil.rmtree(pdir / sub, ignore_errors=True)
        (pdir / "step1_debate" / "attachments").mkdir(parents=True, exist_ok=True)
        (pdir / "step2_skeptic").mkdir(parents=True, exist_ok=True)
        (pdir / "gemini").mkdir(exist_ok=True)
        att = pdir / "step1_debate" / "attachments"
        tx = D / "transcripts" / f"{sym}.txt"
        online = not tx.exists()
        debate_p, skeptic_p = capture(sym, online, tmp)

        inp = json.load(open(D / "inputs" / f"{sym}.json", encoding="utf-8"))
        strip_inputs(inp)
        (att / f"inputs__{sym}.json").write_text(json.dumps(inp, indent=1, ensure_ascii=False), encoding="utf-8")
        mapping = [(f"backend/_opus_debate/inputs/{sym}.json", f"step1_debate/attachments/inputs__{sym}.json")]
        pf = D / "peer_groups" / f"{sym}.json"
        if pf.exists():
            pg = strip_peers(json.load(open(pf, encoding="utf-8")))
            (att / f"peer_groups__{sym}.json").write_text(json.dumps(pg, indent=1, ensure_ascii=False), encoding="utf-8")
            mapping.append((f"backend/_opus_debate/peer_groups/{sym}.json", f"step1_debate/attachments/peer_groups__{sym}.json"))
        copies = [(tx, f"transcripts__{sym}.txt", f"backend/_opus_debate/transcripts/{sym}.txt")] if not online else []
        copies += [(D / n, n, f"backend/_opus_debate/{n}") for n in
                   ("interrogator_system.txt", "architect_system.txt", "moderator_system.txt",
                    "cro_regime_rubric.txt", "macro_regime.json", "secular_themes.json")]
        copies.append((REPO / "CATALYST_WATCH_REGIME.md", "CATALYST_WATCH_REGIME.md", "CATALYST_WATCH_REGIME.md (repo root)"))
        for src, name, prod in copies:
            if src.exists():
                shutil.copy2(src, att / name)
                mapping.append((prod, f"step1_debate/attachments/{name}"))
        leaks = leak_scan(att)
        if leaks:
            shutil.rmtree(pdir / "step1_debate", ignore_errors=True)
            raise SystemExit(f"LEAK in the blind export for {sym} - step1 removed, export stopped: {leaks}")
        (pdir / "step1_debate" / "PROMPT.md").write_text(
            adapter(mapping, "Instead of the Write tool: save the dossier to gemini/dossier.md and the record to "
                             "gemini/record.json (valid JSON, exact step-7 schema).") + debate_p, encoding="utf-8")

        shutil.copy2(D / "results_regime" / f"{sym}.json", pdir / "step2_skeptic" / "claude_record.json")
        (pdir / "step2_skeptic" / "PROMPT.md").write_text(
            adapter([(f"backend/_opus_debate/results_regime/{sym}.json",
                      "step2_skeptic/claude_record.json (pass A) or gemini/record.json (pass B)"),
                     (f"backend/_opus_debate/dossiers/{sym}.md", "none in pass A; gemini/dossier.md in pass B")],
                    "Instead of the Write tool: save pass A to gemini/skeptic_on_claude.json and pass B to "
                    "gemini/skeptic_on_gemini.json (valid JSON, exact schema in step 4 below). Skip the SELF-GATE "
                    "(always run the full check).") + skeptic_p, encoding="utf-8")

        manifest = {"symbol": sym, "run_week": week_label, "scope": scope,
                    "exported_at": datetime.now().isoformat(timespec="seconds"),
                    "debate_variant": "online (no transcript bundled)" if online else "transcript bundled",
                    "listing": listing_facts(sym),
                    "expected_outputs": [f"gemini/{x}" for x in GEMINI_OUTPUTS]}
        if not blind_books:
            manifest["books"] = books
        (pdir / "pick.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
        row = {"symbol": sym, "folder": sym, "variant": manifest["debate_variant"]}
        if not blind_books:
            row["books"] = books
        index.append(row)
        print(f"{sym:10} {'+'.join(books) or '-':11} {manifest['debate_variant']:30} "
              f"{manifest['listing'].get('trading_currency')}/{manifest['listing'].get('reporting_currency')} "
              f"fx={manifest['listing'].get('fx_reporting_to_trading')}")
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.copy2(HERE / "GEMINI_MASTER_PROMPT.md", week_dir / "MASTER_PROMPT.md")
    # a folder left over from an earlier export of this week that is no longer in scope would be
    # processed by Gemini and then ignored by the pickup - remove it unless Gemini already wrote into it
    for stale in sorted(p for p in week_dir.iterdir() if p.is_dir() and p.name not in picks and not p.name.startswith("_")):
        if (stale / "pick.json").exists() and not any((stale / "gemini").glob("*")):
            shutil.rmtree(stale, ignore_errors=True)
            print(f"removed out-of-scope folder {stale.name}")
    (week_dir / "picks.json").write_text(json.dumps({"week": week_label, "scope": scope, "picks": index},
                                                    indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"exported {len(index)} pick(s) [{scope}] -> {week_dir}")
    return week_dir


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="run date (default: the last debate prep date)")
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--scope", choices=("debated", "seats"), default="debated")
    a = ap.parse_args()
    if a.date:
        day = date.fromisoformat(a.date)
    else:
        day = date.fromisoformat(json.load(open(D / "_last_debate_run.json", encoding="utf-8"))["prep_at"][:10])
    export(day, Path(a.root), scope=a.scope)
    sys.exit(0)
