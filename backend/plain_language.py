#!/usr/bin/env python3
# ── Plain-language display layer ──────────────────────────────────────────────
# agent_voice.AGENT_VOICE tells the agents to write plain prose; this module is the
# deterministic BACKSTOP for the tokens that leak through anyway, plus the machine
# lines the prompts REQUIRE the agents to emit verbatim (the trailing
# "CREDIBILITY_SCORE: 3 | TRAJECTORY: PIVOTING | ..." dossier tag line, the bare
# catalyst_status enum).
#
# DESIGN — raw stays raw, only the DISPLAY copy is translated:
#   backend/_opus_debate/results_regime/<SYM>.json  and  dossiers/<SYM>.md  are the
#   machine contract. publish_to_frontend.py regex-parses CREDIBILITY_SCORE / TRAJECTORY
#   out of the raw dossier and ~10 modules do catalyst_status.startswith("PENDING_HARD").
#   Nothing here touches those. The translation is applied only to the copies publish
#   builds for the UI (the per-methodology overlay + the new dated history entry), and
#   enum FIELDS are never rewritten in place — a plain sibling (catalyst_status_plain)
#   is added alongside so the machine field keeps parsing.
#
# SCOPE (Bruno, 2026-08-11): forward-only. This runs inside the weekly publish, so it
# shapes what each run WRITES. Prose already stored in prior history entries is left
# exactly as it was — no back-fill, no retro rewrite (that is _voice_retro.py's job and
# it is not part of the weekly routine).
import re

# Prose fields — the human-readable sentences. Everything not listed here is structured
# (enums, verdicts, convictions, scores, prices, dates) and is never rewritten.
# Mirrors _voice_retro.PROSE_FIELDS, plus the fields that lane/memo records carry.
PROSE_FIELDS = {
    "bull_thesis", "bear_thesis", "sop_bull", "sop_bear", "sop_breakdown", "risk_reward",
    "catalyst_summary", "dated_milestone", "forcing_function", "consensus_delta",
    "valley_of_death", "positioning_washout", "moderator_conclusion", "interrogator_dossier",
    "skeptic_kill_fact", "skeptic_corrections", "peer_comps_note", "role_in_scaleout",
    "catalyst_binding_reason", "binding_reason", "whats_changed_since_prior", "dossier_note",
    "thesis", "rationale", "memo", "director_memo", "regime", "risk_stance", "delta_justification",
    # regime-CRO four-question fields (2026-10-06)
    "thesis_evidence", "macro_fit_note", "entry_event",
}

# Machine token -> plain phrase, in TWO forms, because one string cannot be both.
#
#   TOKEN_GLOSSARY (INLINE) must survive dropping into a live sentence, in either of the
#   two shapes the agents actually write: "status stays <X>" and "a <X> catalyst". So the
#   inline form is an ADJECTIVE PHRASE, never a clause. Substituting a clause is what
#   produced "the catalysts have already already happened" in the 2026-08-11 dry run.
#
#   LABEL_GLOSSARY (STANDALONE) is the caption shown where the bare enum used to render —
#   a noun phrase, free to be a full statement ("the date is fixed").
#
# Keep every replacement a NEUTRAL description of the token — never add a claim the source
# did not make (the agent_voice caveat: a fixed date is not a fixed payout).
TOKEN_GLOSSARY = {
    # grown from the residual-token report (2026-08-31 run)
    "FLOOR_ANCHORED_TO_52W_LOW": "anchored to the 52-week low",
    "THIN_FLOOR": "thinly supported on the downside",
    # catalyst_status
    "PENDING_HARD": "firmly dated",
    "PENDING_SOFT": "real but undated",
    "SOFT_EXTENDED": "soft and undated",
    "SLIPPED": "pushed back",
    "FIRED": "fired",
    "BROKEN": "broken",
    "UNVERIFIABLE": "unverifiable",
    # skeptic verdicts
    "CONFIRMED_WITH_CORRECTIONS": "verified, with corrections",
    "CONFIRMED": "verified",
    "REFUTED": "refuted",
    # numeric / eligibility gate stamps
    "PEAK_ARTIFACT": "a peak-cycle artifact",
    "G4_BEAR_ABOVE_SPOT": "a downside case above today's price",
    "EXCLUDE_ELIGIBILITY": "excluded from seating",
    "NUMERIC_GATE": "the arithmetic check",
    # duration / payback labels
    "PAYBACK_2_3Y": "a two-to-three-year payback",
    "CASH_NOW": "cash-generative today",
    # house labels
    "CONSENSUS_DELTA": "where we disagree with the market",
    "VALLEY_OF_DEATH": "the risky window just ahead",
    "POSITIONING_WASHOUT": "forced-selling pressure",
    "FORCING_FUNCTION": "the catalyst that forces the re-rating",
    "EXPECTATIONS_ARBITRAGE": "where we disagree with the market",
    # regime-CRO four-question enums (2026-10-06). NOW / NONE / INTACT / MECHANICAL / FACTOR are
    # deliberately absent: single plain words that would mangle ordinary capitals.
    "AT_LEVEL": "at a named price",
    "ON_EVENT": "on a named event",
    "WAIT_FOR_PROOF": "wait for proof",
    "LEVEL_REACHED": "entry level reached",
    "FELL_10PCT": "a 10% fall",
}

# Standalone caption form — used for the *_plain sibling fields, where the text stands
# alone rather than sitting inside a sentence. Falls back to the inline form.
LABEL_GLOSSARY = {
    "PENDING_HARD": "the date is fixed",
    "PENDING_SOFT": "real, but no date yet",
    "SOFT_EXTENDED": "a soft catalyst, no fixed date",
    "SLIPPED": "the timeline has been pushed back",
    "FIRED": "already happened",
    "BROKEN": "the thesis has broken",
    "ARB": "a deal-close arbitrage",
    "UNVERIFIABLE": "could not be verified",
    "CONFIRMED_WITH_CORRECTIONS": "verified, with corrections",
    "CONFIRMED": "verified",
    "REFUTED": "did not hold up",
    "PEAK_ARTIFACT": "the fair value leans on peak-cycle earnings",
    "G4_BEAR_ABOVE_SPOT": "the downside case sits above today's price",
}

# Field names that leak into prose as bare code identifiers. Curated on purpose — an
# unknown snake_case token is REPORTED by residual_tokens(), never guessed at.
# Bare noun phrases, no articles — these land inside slash-lists as often as in sentences
# ("no sop_fair_value/bear_px move"), and a leading "the" reads wrong in that position.
FIELD_GLOSSARY = {
    "sop_fair_value": "fair value", "base_fv_px": "base-case value",
    "bear_px": "downside price", "bull_px": "upside price",
    "thesis_break_px": "thesis-break price", "catalyst_status": "catalyst status",
    "value_conviction": "value-only conviction", "size_units": "position size",
    "days_to_earnings": "days to earnings", "risk_reward": "risk-reward",
    "duration_bucket": "payback speed", "phase_fit": "cycle fit",
    "inflation_resilience": "inflation resilience", "quadrant_basis": "the growth-and-inflation read",
    # grown from the residual-token report (the `plain-language` check prints what is
    # still leaking; add the unambiguous ones here rather than guessing at run time)
    "peer_override": "the peer-group override", "anchor_multiple": "the anchor multiple",
    "acquirers_multiple": "the acquirer's multiple", "as_of": "as of", "in_line": "in line",
    "live_price": "the live price", "cheap_vs_peers": "cheap versus peers",
    "rich_vs_peers": "rich versus peers", "p_fcf": "price to free cash flow",
    "rr_ratio": "the risk-reward ratio", "last_full_debate": "the last full debate",
    "dated_fact": "a dated fact", "sector_regulatory": "sector regulatory",
    "catalyst_status_note": "the catalyst-status note", "numeric_gate": "the arithmetic check",
    "whats_changed_since_prior": "what changed since the last look",
    "expected_return_pct": "the expected return",
    "value_conviction_blocker": "the value-conviction blocker",
    # residual-token report, 2026-08-31 run
    "floor_distance_pct": "the distance to the floor",
    "price_currency": "the price currency",
    "prior_record": "the prior record",
    "price_seen": "the price observed",
    "skeptic_corrections_applied": "the corrections the skeptic applied",
    "bear_return_pct": "the downside return",
    "escalate_full_debate": "escalate to a full debate",
    "kill_scope": "the scope of the kill",
    # house field names that double as section labels
    "positioning_washout": "forced-selling pressure", "valley_of_death": "the risky window ahead",
    "forcing_function": "the catalyst that forces the re-rating",
    "consensus_delta": "where we disagree with the market",
    "moderator_conclusion": "the risk officer's conclusion", "peer_comps_note": "the peer-comparison note",
    "bull_thesis": "the bull case", "bear_thesis": "the bear case",
    "sop_bull": "the sum-of-the-parts upside", "sop_bear": "the sum-of-the-parts downside",
    # regime-CRO four-question fields (2026-10-06)
    "thesis_state": "thesis state", "thesis_evidence": "thesis evidence", "thesis_test": "thesis test",
    "entry_mode": "entry mode", "entry_level_px": "entry level", "entry_event": "entry event",
    "washout_type": "wash-out type", "washout_resolution": "wash-out resolution",
    "macro_fit": "macro fit", "macro_fit_note": "macro-fit note", "peer_position": "peer position",
    "no_peers": "no peers", "wait_kind": "wait type", "verdict_agent_orig": "original debate letter",
    "grade_rederived": "re-derived grade", "entry_floor_pct": "entry floor",
    # code-stamped grade fields (grade-derive, 2026-10-06) - delta agents read them off the anchor
    "verdict_structural": "structural letter", "verdict_source": "letter source",
    "grade_flags": "grade flags", "grade_basis": "grade inputs", "grade_schema": "grade schema",
    "entry_mode_agent_orig": "original entry mode", "entry_level_px_agent_orig": "original entry level",
    "entry_level_px_derived": "derived entry level", "conviction_agent_orig": "original conviction",
}

# Dossier tag-line vocabularies. Only the dimensions PRESENT on the line are rendered —
# never invent a moat / trend / threat the source did not state (agent_voice rule 3).
_TRAJECTORY = {"STRENGTHENING": "improving", "STABLE": "steady",
               "DETERIORATING": "weakening", "PIVOTING": "turning"}
_MOAT = {"WIDE": "a wide, durable moat", "NARROW": "a narrow but real moat",
         "ERODING": "a moat that is being eroded", "NONE": "no real moat"}
_MOAT_TREND = {"WIDENING": "widening", "STABLE": "steady", "ERODING": "eroding"}

# "CREDIBILITY_SCORE: 3 | TRAJECTORY: PIVOTING | MOAT: NONE | MOAT_TREND: STABLE | SECULAR_THREAT: manageable"
_TAG_LINE = re.compile(r"^[ \t]*(?:\*\*)?CREDIBILITY_SCORE(?:\*\*)?[ \t]*:.*$", re.MULTILINE)
_TOKEN_RE = re.compile(r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b")
# bare snake_case identifiers ("no sop_fair_value/bear_px move") — reported, never guessed
_SNAKE_RE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")


def _tag_line_to_prose(line: str) -> str:
    """Render the machine tag line as a sentence, translating ONLY what is on it."""
    parts = []
    m = re.search(r"CREDIBILITY_SCORE[^:]*:\s*(\d+)", line)
    if m:
        parts.append(f"Management credibility {m.group(1)} of 5")
    m = re.search(r"TRAJECTORY[^:]*:\s*([A-Za-z]+)", line)
    if m:
        parts.append(f"trajectory {_TRAJECTORY.get(m.group(1).upper(), m.group(1).lower())}")
    m = re.search(r"\bMOAT\s*:\s*([A-Za-z]+)", line)
    if m:
        parts.append(_MOAT.get(m.group(1).upper(), m.group(1).lower()))
    m = re.search(r"MOAT_TREND[^:]*:\s*([A-Za-z]+)", line)
    if m:
        parts.append(f"moat trend {_MOAT_TREND.get(m.group(1).upper(), m.group(1).lower())}")
    m = re.search(r"SECULAR_THREAT[^:]*:\s*([A-Za-z]+)", line)
    if m:
        parts.append(f"structural threat {m.group(1).lower()}")
    if not parts:
        return line
    return " · ".join(parts) + "."


def plainify_text(s):
    """Translate machine tokens inside one prose string. Non-strings pass through.
    Longest token first so CONFIRMED_WITH_CORRECTIONS never gets eaten by CONFIRMED."""
    if not isinstance(s, str) or not s:
        return s
    out = _TAG_LINE.sub(lambda m: _tag_line_to_prose(m.group(0)), s)
    for tok in sorted(TOKEN_GLOSSARY, key=len, reverse=True):
        out = re.sub(rf"\b{re.escape(tok)}\b", TOKEN_GLOSSARY[tok], out)
    for tok in sorted(FIELD_GLOSSARY, key=len, reverse=True):
        # case-insensitive so a sentence-initial "Catalyst_status ..." is caught too;
        # the replacement inherits the original's capitalisation.
        def _sub(m, _p=FIELD_GLOSSARY[tok]):
            return _p[0].upper() + _p[1:] if m.group(0)[0].isupper() else _p
        out = re.sub(rf"\b{re.escape(tok)}\b", _sub, out, flags=re.IGNORECASE)
    # "the catalysts have already fired" — drop the duplicate the substitution can create
    # when the agent already wrote the adverb ("have already FIRED").
    out = re.sub(r"\balready already\b", "already", out)
    return out


def status_plain(value):
    """Standalone caption for a catalyst_status / skeptic-verdict field. Keeps any trailing
    detail the engine appended after the enum ('PENDING_HARD - Aug 31 lock-up')."""
    if not isinstance(value, str) or not value.strip():
        return ""
    v = value.strip()
    known = set(LABEL_GLOSSARY) | set(TOKEN_GLOSSARY)
    for tok in sorted(known, key=len, reverse=True):
        if v.upper().startswith(tok):
            rest = v[len(tok):].lstrip(" -—:·|")
            plain = LABEL_GLOSSARY.get(tok) or TOKEN_GLOSSARY[tok]
            return f"{plain} — {plainify_text(rest)}" if rest else plain
    return plainify_text(v)


# Payback-speed labels (debt_cycle.duration_bucket). 'unknown' is deliberately NOT
# "no free cash flow" — the whole point of the story/unknown split is that unknown means
# the scan had no cash-flow data, and collapsing the two once pinned an entire book to
# the floor (see CLAUDE.md, the DISCIPLINE-cap incident).
_BUCKETS = {
    "cash_now": "pays cash today",
    "payback_2_3y": "pays back in two to three years",
    "story": "a longer-dated story",
    "unknown": "payback speed unknown (no cash-flow data)",
}


def bucket_plain(value):
    """Plain caption for a duration_bucket value; empty string when unset."""
    if not isinstance(value, str) or not value.strip():
        return ""
    return _BUCKETS.get(value.strip().lower(), value)


# Four-question CRO grade captions (2026-10-06). Standalone captions for the *_plain siblings the
# publisher adds next to the bare thesis_state / entry_mode enums (house voice: agent_voice.AGENT_VOICE).
_THESIS = {"INTACT": "the thesis holds", "IMPAIRED": "the thesis is in doubt",
           "BROKEN": "the thesis has broken"}
_SELLER = {"MECHANICAL": "forced selling by holders who must sell regardless of value",
           "FACTOR": "a sector-wide or style-wide sell-off"}


def thesis_plain(state, test=None):
    """Plain caption for a thesis_state; an IMPAIRED one names its test when the record carries it.
    Empty string when unset or unknown (a legacy record says nothing rather than guessing)."""
    s = str(state or "").strip().upper()
    if s not in _THESIS:
        return ""
    if s == "IMPAIRED" and isinstance(test, dict) and str(test.get("metric") or "").strip():
        due = str(test.get("resolves_on") or "").strip()
        return (f"the thesis is in doubt until the test on {plainify_text(str(test['metric']).strip())} "
                f"settles it" + (f" ({plainify_text(due)})" if due else ""))
    return _THESIS[s]


def entry_plain(rec):
    """Plain caption for a record's entry: "buy at today's price" / "buy near <level>[, which <seller>
    could deliver]" / "buy once <event> confirms" / "no entry - pass for now". Empty when unset."""
    if not isinstance(rec, dict):
        return ""
    mode = str(rec.get("entry_mode") or "").strip().upper()
    if mode == "NOW":
        return "buy at today's price"
    if mode == "AT_LEVEL":
        lvl = rec.get("entry_level_px")
        ccy = str(rec.get("price_currency") or "").strip()
        if isinstance(lvl, (int, float)) and not isinstance(lvl, bool) and lvl > 0:
            s = f"buy near {lvl:,.2f}".rstrip("0").rstrip(".") + (f" {ccy}" if ccy else "")
        else:
            s = "buy at a better price"
        who = _SELLER.get(str(rec.get("washout_type") or "").strip().upper())
        return s + (f", which {who} could deliver" if who else "")
    if mode == "ON_EVENT":
        ev = str(rec.get("entry_event") or "").strip()
        return f"buy once {plainify_text(ev)} confirms" if ev else "buy once the named event confirms"
    if mode == "NONE":
        return "no entry - pass for now"
    return ""


def plainify_display(rec, extra_status_fields=("catalyst_status", "skeptic_verdict")):
    """Return a SHALLOW COPY of a record with its prose fields translated and a plain
    sibling added for each enum status field. The enum fields themselves are untouched —
    downstream code (briefing route, catalyst gates, _basket13_inject) exact-matches them."""
    if not isinstance(rec, dict):
        return rec
    out = dict(rec)
    for k, v in rec.items():
        if k in PROSE_FIELDS and isinstance(v, str):
            out[k] = plainify_text(v)
    for k in extra_status_fields:
        v = rec.get(k)
        if isinstance(v, str) and v.strip():
            out[f"{k}_plain"] = status_plain(v)
    return out


def residual_tokens(rec):
    """Code-speak still sitting in the prose of a record AFTER translation — the tokens
    the glossaries do not know about yet (ALL_CAPS_UNDERSCORE enums and bare snake_case
    field names). The weekly `plain-language` check reports these so the glossary grows
    instead of silently shipping code-speak."""
    found = {}
    if not isinstance(rec, dict):
        return found
    for k, v in rec.items():
        if k not in PROSE_FIELDS or not isinstance(v, str):
            continue
        clean = plainify_text(v)
        for t in _TOKEN_RE.findall(clean) + _SNAKE_RE.findall(clean):
            found.setdefault(t, []).append(k)
    return found
