"""What a disagreement between the two committees is ABOUT, and the ledger that keeps score.

Built 2026-11-19 (Bruno: "Disagreements backed by dated evidence are where the value is" - and they
must cover every debated pick, not only the ~10 seats). Pure functions plus one small file, so the
pickup can call them and the tests can pin them.

Kinds, strongest first (one per name):
  kill       its skeptic refuted our thesis, moat or catalyst
  fact       it disputes an INPUT we used (share count, segment profit, net debt, exchange rate...)
             with a dated source - checkable against the filing, the most actionable kind
  new_fact   it cites a primary source dated AFTER our record, and the two values or grades differ
  judgement  same facts, different growth / multiple / grade - only time settles it
  agree      none of the above

The ledger (backend/_opus_debate/_disagreements.jsonl) has one row per name per Gemini week. A row is
RESOLVED when our next full debate of that name writes `second_opinion_check` (step 1d): how many of
the claims were adopted, rejected or left unverified, and how our base value moved. Forward returns
are scored later from `price_at_pickup` (step 4, not built yet).
"""
import json
import re
from pathlib import Path

CONFIRM_GAP = 0.15
HARD_KILL_SCOPES = {"thesis", "moat", "catalyst"}
OUTPUT_FIELDS = {"bear_px", "base_fv_px", "bull_px", "downside_floor_px", "sop_fair_value", "risk_reward",
                 "verdict", "conviction", "catalyst_status_note"}
DATE_RE = re.compile(r"(20\d\d-[01]\d-[0-3]\d)")
KIND_ORDER = ("kill", "fact", "new_fact", "judgement", "agree")


def _num(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def _first_date(*texts):
    for t in texts:
        m = DATE_RE.search(str(t or ""))
        if m:
            return m.group(1)
    return None


def claude_as_of(rec):
    """The date our record speaks for: its valuation as_of, else its last full debate."""
    v = (rec or {}).get("valuation") or {}
    return str(v.get("as_of") or (rec or {}).get("last_full_debate") or (rec or {}).get("debated_at") or "")[:10] or None


def dated_sources(gemini_rec, skA=None):
    """[(date, what)] from Gemini's own source list and its skeptic's evidence lines."""
    out = []
    meta = (gemini_rec or {}).get("gemini_meta") or (gemini_rec or {}).get("independent_meta") or {}
    for s in meta.get("sources") or []:
        if isinstance(s, dict):
            what = s.get("what") or s.get("title") or s.get("url") or ""
            d = str(s.get("date") or "")[:10] or _first_date(what)
        else:
            what, d = str(s), _first_date(s)
        if d:
            out.append((d, str(what)[:200]))
    for ev in (skA or {}).get("evidence") or []:
        d = _first_date(ev)
        if d:
            out.append((d, str(ev)[:200]))
    return sorted(set(out))


def fact_disputes(skA):
    """Input-level disputes from the skeptic on our record. Prefers the typed `fact_disputes` block the
    master prompt asks for since 2026-11-19; falls back to typed corrections on input fields."""
    sk = skA or {}
    out = []
    for f in sk.get("fact_disputes") or []:
        if isinstance(f, dict) and (f.get("fact") or f.get("field")):
            out.append({"fact": str(f.get("fact") or f.get("field"))[:160], "ours": f.get("ours"),
                        "theirs": f.get("theirs"), "source": str(f.get("source") or "")[:200],
                        "source_date": str(f.get("source_date") or "")[:10] or _first_date(f.get("source"))})
    for c in sk.get("corrections_typed") or []:
        if isinstance(c, dict) and c.get("field") and c.get("field") not in OUTPUT_FIELDS:
            out.append({"fact": str(c["field"])[:160], "ours": c.get("from"), "theirs": c.get("to"),
                        "source": str(c.get("basis") or "")[:200], "source_date": _first_date(c.get("basis"))})
    return out


def classify(claude_rec, gemini_rec, skA, gemini_grade=None):
    """{kind, direction, gap_pct, grade_split, disputes, newer_facts, why} - pure."""
    cv = (claude_rec or {}).get("valuation") or {}
    gv = (gemini_rec or {}).get("valuation") or {}
    cb, gb = _num(cv.get("base_fv_px")), _num(gv.get("base_fv_px"))
    gap = (gb / cb - 1) if cb and gb else None
    c_grade = str((claude_rec or {}).get("verdict") or "").upper()[:1] or None
    g_grade = str(gemini_grade or (gemini_rec or {}).get("verdict") or "").upper()[:1] or None
    grade_split = bool(c_grade and g_grade and c_grade != g_grade)
    sk = skA or {}
    verdict = str(sk.get("verdict") or "").upper()
    scope = str(sk.get("kill_scope") or "").lower()
    severity = str(sk.get("correction_severity") or "").lower()
    disputes = fact_disputes(sk)
    asof = claude_as_of(claude_rec)
    newer = [{"date": d, "what": w} for d, w in dated_sources(gemini_rec, sk) if asof and d > asof][:6]
    differs = (gap is not None and abs(gap) > CONFIRM_GAP) or grade_split
    why = []
    if verdict == "REFUTED" and scope in HARD_KILL_SCOPES:
        kind = "kill"
        why.append(f"its skeptic refuted our {scope}")
    elif disputes or (verdict in ("REFUTED", "CONFIRMED_WITH_CORRECTIONS") and scope == "numbers" and severity == "material"):
        kind = "fact"
        why.append(f"{len(disputes)} disputed input(s)" if disputes else "a material correction to our numbers")
    elif newer and differs:
        kind = "new_fact"
        why.append(f"it cites {len(newer)} source(s) dated after our record ({asof})")
    elif differs:
        kind = "judgement"
        why.append("same facts, different value or grade")
    else:
        kind = "agree"
    if gap is not None:
        why.append(f"its value is {gap * 100:+.0f}% from ours")
    if grade_split:
        why.append(f"grades {c_grade} (ours) vs {g_grade} (theirs)")
    direction = None
    if gap is not None and abs(gap) > CONFIRM_GAP:
        direction = "more_bullish" if gap > 0 else "more_bearish"
    elif grade_split and c_grade and g_grade:
        direction = "more_bullish" if g_grade < c_grade else "more_bearish"     # A < B < C
    return {"kind": kind, "direction": direction, "gap_pct": round(gap * 100, 1) if gap is not None else None,
            "grade_split": grade_split, "grades": {"ours": c_grade, "theirs": g_grade},
            "disputes": disputes[:8], "newer_facts": newer, "claude_as_of": asof, "why": why}


# ---------------------------------------------------------------- ledger
def load_ledger(path):
    p = Path(path)
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def save_ledger(path, rows):
    Path(path).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def resolution_from_record(row, rec):
    """The resolution of one open row from our latest record of that name, or None if our committee
    has not fully re-debated it since the row was opened (or the debate predates the typed check)."""
    if not isinstance(rec, dict):
        return None
    opened = str(row.get("picked_up_at") or "")[:10]
    lfd = str(rec.get("last_full_debate") or "")[:10]
    checks = rec.get("second_opinion_check")
    if not lfd or not opened or lfd < opened or not isinstance(checks, list):
        return None
    counts = {"ADOPTED": 0, "REJECTED": 0, "UNVERIFIED": 0}
    for c in checks:
        o = str((c or {}).get("outcome") or "").upper()
        if o in counts:
            counts[o] += 1
    after = _num(((rec.get("valuation") or {}).get("base_fv_px")))
    before = _num((row.get("claude") or {}).get("base_fv_px"))
    return {"date": lfd, "claims": len(checks), "adopted": counts["ADOPTED"], "rejected": counts["REJECTED"],
            "unverified": counts["UNVERIFIED"], "base_before": before, "base_after": after,
            "base_move_pct": round((after / before - 1) * 100, 1) if after and before else None,
            "checks": [{k: (c or {}).get(k) for k in ("field", "outcome", "verified_value", "source_date")}
                       for c in checks][:8]}


def update_ledger(path, week, new_rows, records):
    """Resolve open rows from `records` ({symbol: our latest record}), replace any rows already logged
    for `week` (a re-run of the pickup is idempotent), append `new_rows`. Returns (rows, resolved_n)."""
    rows = [r for r in load_ledger(path) if r.get("week") != week]
    resolved = 0
    for r in rows:
        if r.get("resolution") is None:
            res = resolution_from_record(r, records.get(r.get("symbol")))
            if res:
                r["resolution"] = res
                resolved += 1
    rows.extend(new_rows)
    save_ledger(path, rows)
    return rows, resolved


def priority(entry):
    """Sort key for spending a capped re-debate slot on a non-seat disagreement: strongest evidence
    first, then the biggest gap. Lower sorts first."""
    kind = str((entry or {}).get("disagreement_kind") or "agree")
    rank = KIND_ORDER.index(kind) if kind in KIND_ORDER else len(KIND_ORDER)
    g = (entry or {}).get("gap_pct")
    return (rank, -abs(g) if isinstance(g, (int, float)) else 0)
