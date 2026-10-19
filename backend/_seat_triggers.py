"""Held-seat re-debate triggers (2026-10-19).

A held seat gets a light weekly update (delta) unless something real changed, in which case it
gets a FULL re-debate. Three gaps found on 2026-10-19 are closed here. All logic is pure (no
network, no disk); weekly_opus_refresh supplies the fetchers.

1. PRICE - measured from the last FULL debate, not the last weekly update. Delta agents restate
   valuation.live_price every week, so `_debate_price` only ever saw the week-over-week move:
   INTU sat +19% above its 2026-09-29 full debate while the trigger read +5.6%. The full-debate
   price is stamped by lane-stamp (`full_debate_px`); a seat that predates the stamp falls back to
   the historical close on its last_full_debate date.
2. RESULTS RELEASE - a seat re-debates when the company has reported since its last full debate,
   from the FMP reported-earnings dates. The transcript trigger only fires when FMP carries the
   call, so 9980.HK / 267260.KS could never be re-underwritten on their own results.
3. MACRO CHANGE - when the growth x inflation quadrant or the debt-cycle phase differs from the
   read at the seat's last full debate AND the seat is exposed to that change. This only refreshes
   the thesis analysis; it never gates a seat, moves a weight or touches conviction (FORK 2/B -
   macro stays advisory). Fail-open: an UNKNOWN read on either side never triggers (a data gap
   must never churn the book). Capped per run, oldest full debate first.
"""
import re

QUADRANTS = ("GOLDILOCKS", "REFLATION", "STAGFLATION", "RISK_OFF")
PHASES = ("EXPANSION", "DISCIPLINE", "FORCING", "MONETIZATION")
MACRO_U_CAP = 8           # macro-change full re-debates per run; the rest stay on delta and retry next run
STAMP_KEYS = ("full_debate_px", "full_debate_px_date", "full_debate_px_source", "macro_at_full_debate")


def _num(x):
    return x if isinstance(x, (int, float)) and not isinstance(x, bool) and x > 0 else None


def _restated_since_full(pr):
    """True when valuation.live_price may no longer be the full debate's price."""
    return pr.get("update_mode") == "delta" or bool(pr.get("deltas"))


# ── 1. price reference ───────────────────────────────────────────────────────
def full_debate_price(pr, sym=None, is_seat=False, hist_close=None, fallback=None):
    """(price, source) the last FULL underwrite priced against.
    stamped full_debate_px > (seat whose valuation a delta restated) historical close on
    last_full_debate > fallback(pr) (the legacy debate price). Non-seats never hit the network."""
    px = _num(pr.get("full_debate_px"))
    if px:
        return px, "stamped at the full debate"
    lfd = str(pr.get("last_full_debate") or "")[:10]
    if is_seat and sym and lfd and hist_close and _restated_since_full(pr):
        try:
            px = _num(hist_close(sym, lfd))
        except Exception:
            px = None
        if px:
            return px, f"closing price on {lfd}"
    return (fallback(pr) if fallback else None), "last debate record"


# ── 2. results release ───────────────────────────────────────────────────────
def last_report_date(rows, today):
    """Newest earnings date on or before `today` that actually reported (EPS or revenue printed)."""
    past = []
    for r in rows or []:
        d = str((r or {}).get("date") or "")[:10]
        if d and d <= today and (r.get("epsActual") is not None or r.get("revenueActual") is not None):
            past.append(d)
    return max(past) if past else None


def release_trigger(pr, report_date):
    """Reason string when the company reported after the seat's last full debate, else None."""
    ref = str(pr.get("last_full_debate") or pr.get("debated_at") or "")[:10]
    if report_date and ref and report_date > ref:
        return f"results released {report_date} after the last full debate {ref}"
    return None


# ── 3. macro change ──────────────────────────────────────────────────────────
def macro_now(m):
    """{quadrant, phase} from a macro_regime.json dict; None where the read is not live."""
    m = m or {}
    q = m.get("quadrant")
    ok = (m.get("quadrant_inputs") or {}).get("ok", True) is not False
    dc = m.get("debt_cycle") if isinstance(m.get("debt_cycle"), dict) else {}
    ph = dc.get("debt_cycle_phase") or m.get("debt_cycle_phase")
    return {"quadrant": q if (q in QUADRANTS and ok) else None,
            "phase": ph if ph in PHASES else None}


def quadrant_from_note(note):
    """Quadrant a macro_fit_note names: the enum token first, else the plain word. 'risk-off' in
    prose is NOT read as the RISK_OFF quadrant (it is a generic phrase)."""
    s = str(note or "")
    m = re.search(r"\b(GOLDILOCKS|REFLATION|STAGFLATION|RISK_OFF)\b", s)
    if m:
        return m.group(1)
    m = re.search(r"\b(goldilocks|reflation|stagflation)", s, re.I)
    return m.group(1).upper() if m else None


def phase_on(day, ledger_rows):
    """Debt-cycle phase published on or before `day` (YYYY-MM-DD) per _cycle_ledger.jsonl rows."""
    best = None
    for r in ledger_rows or []:
        d = str(r.get("date") or "")[:10]
        if r.get("book", "cycle") == "cycle" and d and d <= day and r.get("debt_cycle_phase") in PHASES:
            if best is None or d >= best[0]:
                best = (d, r["debt_cycle_phase"])
    return best[1] if best else None


def macro_at_full_debate(pr, ledger_rows=None):
    """{quadrant, phase} the seat's last full debate saw. Stamped by lane-stamp from 2026-10-19;
    older seats: phase from the dated cycle ledger, quadrant from the macro note ONLY when the
    record is still the full debate itself (a delta may have rewritten the note since)."""
    st = pr.get("macro_at_full_debate")
    if isinstance(st, dict):
        return {"quadrant": st.get("quadrant") if st.get("quadrant") in QUADRANTS else None,
                "phase": st.get("phase") if st.get("phase") in PHASES else None}
    lfd = str(pr.get("last_full_debate") or "")[:10]
    phase = phase_on(lfd, ledger_rows) if lfd else None
    quad = None if _restated_since_full(pr) else quadrant_from_note(pr.get("macro_fit_note"))
    return {"quadrant": quad, "phase": phase}


def macro_exposure(pr, before, now, ir_label=None, dur_bucket=None):
    """Reason string when the macro read moved since the full debate AND the seat is exposed."""
    qc = bool(before.get("quadrant") and now.get("quadrant") and before["quadrant"] != now["quadrant"])
    pc = bool(before.get("phase") and now.get("phase") and before["phase"] != now["phase"])
    if not (qc or pc):
        return None
    why = []
    mf = str(pr.get("macro_fit") or "").upper()
    if mf in ("TAILWIND", "HEADWIND"):
        why.append(f"its debate called macro a {mf.lower()}")
    if qc and now["quadrant"] in ("REFLATION", "STAGFLATION") and ir_label == "exposed":
        why.append("its margins fell hard in the 2021-22 inflation")
    if pc and now["phase"] in ("DISCIPLINE", "FORCING") and dur_bucket == "story":
        why.append("its payoff depends on cash flow that does not exist yet")
    if not why:
        return None
    change = []
    if qc:
        change.append(f"quadrant {before['quadrant']} -> {now['quadrant']}")
    if pc:
        change.append(f"phase {before['phase']} -> {now['phase']}")
    return f"macro changed since the last full debate ({', '.join(change)}) and the seat is exposed: {'; '.join(why)}"


def promote_macro_seats(cands, now, ledger_rows=None, ir_labels=None, dur_buckets=None, cap=MACRO_U_CAP):
    """cands: [(sym, prior_record)] for seats headed to a delta. Returns ({sym: reason} promoted to
    a full re-debate, [deferred syms]) - oldest last full debate first, at most `cap` per run."""
    ir_labels, dur_buckets = ir_labels or {}, dur_buckets or {}
    if not (now.get("quadrant") or now.get("phase")):
        return {}, []
    hits = []
    for sym, pr in cands:
        if not isinstance(pr, dict):
            continue
        before = macro_at_full_debate(pr, ledger_rows)
        reason = macro_exposure(pr, before, now, ir_labels.get(sym), dur_buckets.get(sym))
        if reason:
            hits.append((str(pr.get("last_full_debate") or "")[:10], sym, reason))
    hits.sort()
    return {s: r for _, s, r in hits[:cap]}, [s for _, s, _ in hits[cap:]]


# ── lane-stamp helpers ───────────────────────────────────────────────────────
def stamp_full_debate(rec, run_date, macro):
    """On a record FULLY debated this run: the price it underwrote against + the macro read it saw."""
    changed = False
    px = _num((rec.get("valuation") or {}).get("live_price")) or _num(rec.get("live_price"))
    if px and (rec.get("full_debate_px") != px or rec.get("full_debate_px_date") != run_date):
        rec["full_debate_px"], rec["full_debate_px_date"] = px, run_date
        rec["full_debate_px_source"] = "full debate"
        changed = True
    m = {"quadrant": (macro or {}).get("quadrant"), "phase": (macro or {}).get("phase"), "asof": run_date}
    if rec.get("macro_at_full_debate") != m:
        rec["macro_at_full_debate"] = m
        changed = True
    return changed


def carry_full_stamps(rec, anchor):
    """On a DELTA record: keep the anchor's full-debate stamps (a delta never re-underwrites)."""
    changed = False
    for k in STAMP_KEYS:
        if rec.get(k) in (None, "", {}) and (anchor or {}).get(k) not in (None, "", {}):
            rec[k] = anchor[k]
            changed = True
    return changed
