#!/usr/bin/env python3
"""_catalyst_post.py — post-skeptic enforcement for the CATALYST lane.

WHY THIS EXISTS (2026-08-04). Every other lane — apex/value (_regime_post), mining,
fdt, disruptor — routes its skeptic shards through _post_common.consume_skeptic, where a
REFUTED verdict is a MEMBERSHIP EVENT (demote to runner_ups) and, since f9e4be1a, a
kill_scope="numbers" kill with a typed revised_fv_px is a REPRICING that re-grades the
seat on the skeptic's own number.

The catalyst lane had NONE of that. Its only treatment of a skeptic verdict was
`publish_catalyst.py:80` — `entry["skeptic_verdict"] = sk.get("verdict", "")` — i.e. the
verdict was copied onto the payload as a DISPLAY BADGE and nothing branched on it. The
CRO's conviction was published verbatim. Live consequence (EYPT, runs of 2026-07-28 and
2026-08-04): the skeptic returned REFUTED with kill_scope="numbers" twice, re-anchoring
the event-win target on the only live comparable, and both times the published record
carried the refuted target and the conviction ROSE (4 -> 5) while every underlying number
got worse.

WHAT THIS DOES NOT DO. It does not re-run the debate, does not overwrite the CRO's prose,
and does not itself change conviction. It computes the arithmetic both anchors imply and
stamps it, so a reader (and the B13 Director) sees the refuted anchor and the corrected
anchor side by side instead of only the one the CRO happened to carry forward.

Membership note: the catalyst lane has no apex_basket, so consume_skeptic cannot be ported
verbatim — there is nothing to demote INTO. What ports is the repricing arithmetic and the
write-back. Seat-level enforcement stays where it belongs: _basket13_inject's cap validator.

Usage:  python _catalyst_post.py            # stamp every record that has a fresh shard
        python _catalyst_post.py --dry-run  # print the table, write nothing
"""
import json, os, argparse, datetime as _dt

HERE = os.path.dirname(os.path.abspath(__file__))
RES  = os.path.join(HERE, "_catalyst_results")
SKEP = os.path.join(HERE, "_catalyst_skeptic")
MACRO = os.path.join(HERE, "macro_regime.json")

# Mirrors _post_common._ENTRY_FLOOR_PCT — the STEP-3a entry-discount floor, quadrant-scaled.
# Keep the two in sync; fail-open to the LOOSEST bar when the quadrant is unknown (a data
# outage must never tighten the book — the standing macro invariant).
_ENTRY_FLOOR_PCT = {"GOLDILOCKS": 20.0, "REFLATION": 20.0, "STAGFLATION": 25.0, "RISK_OFF": 30.0}


def _load(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def implied_prob(live, win, floor):
    """Market-implied P(win) for a two-state payoff: (live - floor) / (win - floor).

    This is the single most useful number the catalyst lane was not printing. Seeing it at
    BOTH anchors kills an inherited target without any domain argument: if the record's own
    target implies 24% and the skeptic's re-derived target implies 45%, the 'enormous edge'
    was manufactured by the numerator, not discovered in the biology.
    """
    live, win, floor = _num(live), _num(win), _num(floor)
    if live is None or win is None or floor is None or win <= floor:
        return None
    return round(max(0.0, min(1.0, (live - floor) / (win - floor))), 4)


def quadrant():
    m = _load(MACRO) or {}
    return str(m.get("quadrant") or m.get("regime_quadrant") or "").upper()


def enforce(rec, shard, floor_pct):
    """Return the enforcement block for one name, or None when there is nothing to say.

    Fail-safe: a numbers-REFUTED WITHOUT a typed revised_fv_px is treated as a HARD kill
    (skeptic_enforced="REFUTED_HARD"), exactly as _post_common does — never fail-open into
    'the skeptic said something, carry on'.
    """
    if not shard:
        return None
    verdict = str(shard.get("verdict") or "").upper()
    scope   = str(shard.get("kill_scope") or "").lower()
    live    = _num(rec.get("live_price"))
    tgt     = _num(rec.get("target_px"))
    flr     = _num(rec.get("downside_floor"))

    out = {
        "skeptic_verdict": verdict,
        "kill_scope": scope,
        "at": _dt.date.today().isoformat(),
        "record_target_px": tgt,
        "record_floor_px": flr,
        "implied_prob_at_record": implied_prob(live, tgt, flr),
    }

    if verdict != "REFUTED":
        out["skeptic_enforced"] = verdict or "NONE"
        return out

    rev_fv  = _num(shard.get("revised_fv_px"))
    rev_flr = _num(shard.get("revised_floor_px"))
    if scope != "numbers" or rev_fv is None:
        # thesis / catalyst / moat kill, or a numbers kill that never typed its number
        out["skeptic_enforced"] = "REFUTED_HARD"
        out["enforcement_note"] = (
            "REFUTED on %s — no typed revised_fv_px, so the record anchor is NOT repriced and the "
            "line is a hard kill (fail-safe)." % (scope or "unstated scope"))
        return out

    eff_flr = rev_flr if rev_flr is not None else flr
    out.update({
        "skeptic_revised_fv_px": rev_fv,
        "skeptic_revised_floor_px": rev_flr,
        "implied_prob_at_skeptic": implied_prob(live, rev_fv, eff_flr),
    })
    if live is not None and rev_fv > 0:
        rev_er = (rev_fv / live - 1.0) * 100.0
        out["skeptic_revised_er_pct"] = round(rev_er, 1)
        out["entry_floor_pct"] = floor_pct
        out["skeptic_enforced"] = "REPRICED" if rev_er >= floor_pct else "REFUTED_ON_NUMBERS"
        out["enforcement_note"] = (
            "REFUTED/numbers -> target repriced %.2f -> %.2f (ER %+.1f%% vs the %.0f%% floor); "
            "%s." % (tgt if tgt is not None else float("nan"), rev_fv, rev_er, floor_pct,
                     "clears — line survives at a material haircut" if rev_er >= floor_pct
                     else "under the floor — line is dead on its own re-derived number"))
    else:
        out["skeptic_enforced"] = "REFUTED_HARD"
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    try: __import__("sys").stdout.reconfigure(encoding="utf-8")
    except Exception: pass

    q = quadrant()
    floor_pct = _ENTRY_FLOOR_PCT.get(q, 20.0)
    if q not in _ENTRY_FLOOR_PCT:
        print(f"WARN catalyst-post: unknown macro quadrant {q!r} -> fail-open to the loosest "
              f"{floor_pct:.0f}% entry floor (a data outage must never tighten the book)")

    stamped, hard, repriced, dead = 0, [], [], []
    rows = []
    for f in sorted(os.listdir(RES)):
        if not f.endswith(".json"):
            continue
        sym = f[:-5]
        rec = _load(os.path.join(RES, f))
        if not rec:
            continue
        blk = enforce(rec, _load(os.path.join(SKEP, f)), floor_pct)
        if not blk:
            continue
        rows.append((sym, rec, blk))
        st = blk.get("skeptic_enforced")
        if st == "REFUTED_HARD":       hard.append(sym)
        elif st == "REPRICED":         repriced.append(sym)
        elif st == "REFUTED_ON_NUMBERS": dead.append(sym)
        if not args.dry_run:
            rec["skeptic_enforcement"] = blk
            with open(os.path.join(RES, f), "w", encoding="utf-8") as fh:
                json.dump(rec, fh, ensure_ascii=False, indent=1)
            stamped += 1

    print(f"{'SYM':7}{'CONV':5}{'ENFORCED':20}{'P@record':10}{'P@skeptic':11}{'note'}")
    for sym, rec, b in sorted(rows, key=lambda r: -(r[1].get("conviction") or 0)):
        pr = b.get("implied_prob_at_record"); ps = b.get("implied_prob_at_skeptic")
        print(f"{sym:7}{str(rec.get('conviction') or ''):5}{str(b.get('skeptic_enforced') or ''):20}"
              f"{(f'{pr:.0%}' if pr is not None else '-'):10}{(f'{ps:.0%}' if ps is not None else '-'):11}"
              f"{str(b.get('enforcement_note') or '')[:90]}")
    print(f"\n{'DRY-RUN, nothing written' if args.dry_run else f'stamped {stamped} record(s)'} "
          f"| quadrant {q or 'UNKNOWN'} floor {floor_pct:.0f}%")
    if repriced: print(f"  REPRICED (survives, material haircut): {repriced}")
    if dead:     print(f"  REFUTED_ON_NUMBERS (dead on its own re-derived number): {dead}")
    if hard:     print(f"  REFUTED_HARD (thesis/catalyst/moat, or numbers with no typed FV): {hard}")


if __name__ == "__main__":
    main()
