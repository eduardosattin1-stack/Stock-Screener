"""Weekly hand-off to the Gemini independent-confirmation routine (Antigravity).

After the weekly debate + value lens publish, write one folder per SEATED pick (regime apex +
value apex, de-duplicated) to  C:\\Users\\Bruno\\Documents\\Speculair\\<year>\\Week <ISO week>\\<SYM>\\
with the exact production debate + skeptic prompts for that symbol, STRICT-blind inputs (no prior
committee answer, none of our scan's fair values / margins of safety / peer verdicts), a manifest
with live listing facts (price, trading vs reporting currency, live FX, share count), and Claude's
record isolated in step2_skeptic/ for the skeptic-on-Claude pass. Gemini writes its results into
<SYM>/gemini/; a later pickup step validates them.

usage:  python backend/gemini_confirm/export_week.py [--date YYYY-MM-DD] [--root PATH]
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


def seats():
    out = {}
    for book, f in (("apex", "apex_basket_opus_regime.json"), ("value", "apex_basket_value.json")):
        for p in json.load(open(D / f, encoding="utf-8")).get("apex_basket", []):
            out.setdefault(p["symbol"], []).append(book)
    return out


def capture(sym, online, tmp):
    out = tmp / f"cap_{sym}.json"
    args = ["node", str(HERE / "capture_prompts.mjs"), str(D / "_weekly_debate.js"), sym, str(out)]
    if online:
        args.append("--online")
    subprocess.run(args, check=True, capture_output=True, cwd=REPO)
    cap = {c["label"]: c["prompt"] for c in json.loads(out.read_text(encoding="utf-8"))}
    return cap.get(f"debate:{sym}") or cap[f"debate:{sym}(web)"], cap[f"skeptic:{sym}"]


def strip_inputs(inp):
    """STRICT blind: drop the prior committee answer and every OUR-scan valuation output."""
    removed = {"prior_record": inp.get("prior_record"), "washout": inp.get("washout")}
    inp["prior_record"], inp["washout"] = None, None
    kept = []
    for line in str(inp.get("metrics_str") or "").split("\n"):
        if line.startswith("Valuation:"):
            line = re.sub(r"\s*\|\s*(Fair Value|Margin of Safety) [^|]*", "", line)
        elif line.startswith(("Valuation models (stock page)", "Per-method margin-of-safety")):
            continue
        kept.append(line)
    inp["metrics_str"] = "\n".join(kept)
    return removed


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
    px_major = (q["price"] / 100.0) if (q.get("price") and trade_ccy == "GBp") else q.get("price")
    shares = (q.get("marketCap") / px_major) if q.get("marketCap") and px_major else None
    return {
        "company": q.get("name") or prof.get("companyName"),
        "exchange": q.get("exchange") or prof.get("exchange"),
        "price": q.get("price"), "price_timestamp": q.get("timestamp"),
        "trading_currency": trade_ccy,
        "reporting_currency": rep_ccy,
        "fx_reporting_to_trading": fx,
        "fx_note": note,
        "shares_outstanding_approx": round(shares) if shares else None,
        "shares_note": "market cap / price at export - VERIFY against the latest filing; corporate actions "
                       "(bonus issues, splits, buybacks) change it",
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


def export(run_day, root):
    iso_year, iso_week, _ = run_day.isocalendar()
    week_dir = root / str(iso_year) / f"Week {iso_week}"
    week_dir.mkdir(parents=True, exist_ok=True)
    tmp = week_dir / "_tmp"
    tmp.mkdir(exist_ok=True)
    picks = seats()
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

        manifest = {"symbol": sym, "books": books, "run_week": f"{iso_year}-W{iso_week:02d}",
                    "exported_at": datetime.now().isoformat(timespec="seconds"),
                    "debate_variant": "online (no transcript bundled)" if online else "transcript bundled",
                    "listing": listing_facts(sym),
                    "expected_outputs": [f"gemini/{x}" for x in GEMINI_OUTPUTS]}
        (pdir / "pick.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False), encoding="utf-8")
        index.append({"symbol": sym, "books": books, "folder": sym, "variant": manifest["debate_variant"]})
        print(f"{sym:10} {'+'.join(books):11} {manifest['debate_variant']:30} "
              f"{manifest['listing'].get('trading_currency')}/{manifest['listing'].get('reporting_currency')} "
              f"fx={manifest['listing'].get('fx_reporting_to_trading')}")
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.copy2(HERE / "GEMINI_MASTER_PROMPT.md", week_dir / "MASTER_PROMPT.md")
    (week_dir / "picks.json").write_text(json.dumps({"week": f"{iso_year}-W{iso_week:02d}", "picks": index},
                                                    indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"exported {len(index)} pick(s) -> {week_dir}")
    return week_dir


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="run date (default: the last debate prep date)")
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    a = ap.parse_args()
    if a.date:
        day = date.fromisoformat(a.date)
    else:
        day = date.fromisoformat(json.load(open(D / "_last_debate_run.json", encoding="utf-8"))["prep_at"][:10])
    export(day, Path(a.root))
    sys.exit(0)
