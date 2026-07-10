#!/usr/bin/env python3
"""Shared post-processing primitives for BOTH the value apex (_value_post.py) and the regime/apex
book (_regime_post.py): the skeptic kill-tier, the weight builder (with the moat-erosion + combined
caps), and the deterministic secular-theme concentration cap. Factored out so the two books run ONE
implementation — a skeptic that demotes and a cap loop that sizes, identical across surfaces.

Design notes carried over from _value_post.py:
  - consume_skeptic is fork (b): a REFUTED apex member is physically DEMOTED to the front of
    runner_ups ("a skeptic that cannot demote is decoration"). Staleness guard ignores shards older
    than the apex file (a stale verdict must never demote a fresh basket).
  - build_weights enforces Director `combined_caps` + any `extra_caps` (correlation breaches, secular
    themes) by scaling the named cluster's units down to max_units; per_name_cap applies the half-size
    teeth (cro_only / stale_anchor / moat_erosion).
"""
import json
from pathlib import Path


def consume_skeptic(apx, apex_file: Path, skep_dir: Path, conviction_field: str = "value_conviction_cap"):
    """Merge skep_dir/<SYM>.json shards -> sidecar <skep_dir>_results.json and apply the verdicts.
    REFUTED demotes the apex member to the front of runner_ups; CONFIRMED_WITH_CORRECTIONS stamps the
    correction + conviction cap. Idempotent: re-running re-applies the same verdicts to the same members."""
    skep_dir = Path(skep_dir)
    apex_file = Path(apex_file)
    if not skep_dir.is_dir():
        return apx
    apex_mtime = apex_file.stat().st_mtime if apex_file.exists() else 0
    # Freshness window (2026-07-10, two-tier restructure): the skeptic phase now runs BEFORE the
    # Director inside the same weekly workflow, so a same-run shard is legitimately a few minutes-to-
    # hours OLDER than the apex file. The old strict `< apex_mtime - 1` guard would discard every
    # pre-Director shard as stale. A 24h window cleanly separates same-run shards (minutes/hours old)
    # from genuinely stale prior-week shards (~7 days old on the weekly cadence).
    SKEPTIC_FRESH_WINDOW_S = 24 * 3600
    merged, stale, stale_verdicts = {}, [], {}
    for f in sorted(skep_dir.glob("*.json")):
        try:
            d = json.load(open(f, encoding="utf-8"))
            if f.stat().st_mtime < apex_mtime - SKEPTIC_FRESH_WINDOW_S:
                stale.append(f.stem)
                if d.get("symbol"):                      # remember stale verdicts — a stale REFUTED
                    stale_verdicts[d["symbol"]] = d       # on a still-held name must not vanish (HRMY)
                continue
            if d.get("symbol"):
                merged[d["symbol"]] = d
        except Exception as e:
            print(f"WARN skeptic: shard {f.name} unreadable ({e})")
    if stale:
        print(f"skeptic: ignored {len(stale)} stale shard(s) older than the apex: {sorted(stale)}")
    if merged:
        (skep_dir.parent / (skep_dir.name + "_results.json")).write_text(
            json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    # COVERAGE — fail LOUD, not open (the 06-30 apex + EEFT/HRMY value book shipped with zero fresh
    # shards and this function returned silently). Every apex member without a FRESH shard is stamped
    # skeptic_verdict=MISSING (+ skeptic_missing=True -> half-sized by moat_per_name_cap); a STALE
    # REFUTED on a still-held member is stamped skeptic_stale_refuted (half-size + re-run flag), never
    # silently ignored. Publish stays possible (partial runs are the ops norm) — visible and priced.
    missing, stale_ref = [], []
    for p in apx.get("apex_basket", []):
        sym = p.get("symbol")
        if not sym or sym in merged:
            continue
        sv = stale_verdicts.get(sym)
        if sv and (sv.get("verdict") or "").upper() == "REFUTED":
            p["skeptic_verdict"] = "MISSING"
            p["skeptic_stale_refuted"] = True
            p["skeptic_kill_fact"] = f"STALE shard: {str(sv.get('kill_fact', ''))[:160]}"
            stale_ref.append(sym)
        else:
            p["skeptic_verdict"] = "MISSING"
            p["skeptic_missing"] = True
            missing.append(sym)
    if missing:
        print(f"WARN skeptic-coverage: {len(missing)} apex member(s) have NO fresh skeptic shard -> "
              f"stamped MISSING + half-sized: {missing} (fix: run the skeptic workflow)")
    if stale_ref:
        print(f"WARN skeptic-coverage: STALE REFUTED shard(s) on still-held member(s) -> half-sized, "
              f"re-run the skeptic: {stale_ref}")
    if not merged:
        return apx
    keep, demoted = [], []
    for p in apx.get("apex_basket", []):
        v = merged.get(p.get("symbol"))
        if not v:
            keep.append(p)
            continue
        p["skeptic_verdict"] = v.get("verdict", "")
        if v.get("kill_fact"):
            p["skeptic_kill_fact"] = v["kill_fact"]
        if v.get("corrections"):
            p["skeptic_corrections"] = v["corrections"]
        # Unified skeptic (X1): CATEGORICAL severity replaces the numeric cap. A "material"
        # correction (a load-bearing number/date/anchor moved) takes a bounded sizing haircut in
        # moat_per_name_cap — a haircut, never a hard ceiling (the proven numeric-cap bug class).
        if v.get("correction_severity"):
            p["correction_severity"] = v["correction_severity"]
        if v.get("kill_scope"):
            p["skeptic_kill_scope"] = v["kill_scope"]
        if v.get("carried_from_book"):
            p["skeptic_carried_from"] = v["carried_from_book"]
        if isinstance(v.get(conviction_field), (int, float)):   # legacy shards only (pre-X1)
            p[conviction_field] = v[conviction_field]
        if (v.get("verdict") or "").upper() == "REFUTED":
            p["skeptic_refuted"] = True
            demoted.append(p)
            print(f"WARN skeptic: {p['symbol']} REFUTED -> DEMOTED to runner_ups | kill_fact: {str(v.get('kill_fact', ''))[:160]}")
        else:
            keep.append(p)
    if demoted:
        dsyms = {d.get("symbol") for d in demoted}
        apx["apex_basket"] = keep
        apx["runner_ups"] = demoted + [r for r in (apx.get("runner_ups") or [])
                                       if (r.get("symbol") if isinstance(r, dict) else r) not in dsyms]
    for r in apx.get("runner_ups", []):
        if isinstance(r, dict) and r.get("symbol") in merged and "skeptic_verdict" not in r:
            r["skeptic_verdict"] = merged[r["symbol"]].get("verdict", "")
    n_conf = sum(1 for v in merged.values() if (v.get("verdict") or "").upper().startswith("CONFIRMED"))
    print(f"skeptic: {len(merged)} verdicts | confirmed={n_conf} refuted={len(demoted)} (demoted: {[d['symbol'] for d in demoted]})")
    return apx


def build_weights(apx, picks, extra_caps=None, memo_units=None, per_name_cap=None):
    """Normalize size_units -> weight_pct, honoring per-name half-caps + combined/extra caps.
    per_name_cap(p, u) -> u' applies the teeth (cro_only / stale_anchor / moat_erosion). extra_caps and
    apx['combined_caps'] share the schema {names:[...], max_units: float, axis: str}."""
    memo_units = memo_units or {}
    units = {}
    for p in picks:
        u = p.get("size_units")
        if not isinstance(u, (int, float)) or not (0.1 <= u <= 1.5):
            u = memo_units.get(p["symbol"], 1.0)
        if per_name_cap is not None:
            u = per_name_cap(p, u)
        units[p["symbol"]] = u
    for cap in list(apx.get("combined_caps") or []) + list(extra_caps or []):
        names = [s for s in (cap.get("names") or []) if s in units]
        mx = cap.get("max_units")
        tot = sum(units[s] for s in names)
        if names and isinstance(mx, (int, float)) and tot > mx:
            scale = mx / tot
            for s in names:
                units[s] = round(units[s] * scale, 3)
    W = sum(units.values()) or 1.0
    weights = {s: round(u / W, 4) for s, u in units.items()}
    for p in picks:
        p["size_units_effective"] = units[p["symbol"]]
        p["weight_pct"] = round(weights[p["symbol"]] * 100, 2)
    return weights


def secular_theme_caps(picks, max_units=1.5):
    """Deterministic safety-net for the "don't put all eggs in one secular tail" rule. For each
    secular_theme carrying >=2 NON-DURABLE names, emit a combined_caps entry scaling that cluster to
    max_units. A WIDE moat that is NOT eroding is EXEMPT (durable half-relief taken to its limit: the
    anchor that merely carries the narrative is not the tail risk and is not cut). Returns extra_caps
    consumable by build_weights. The Director may ALSO emit its own combined_caps; both are honored."""
    by_theme = {}
    for p in picks:
        if p.get("lane") == "equity_special_sit":
            continue   # lane contract: event-driven seats resolve on their own catalyst, not a secular tail
        th = (p.get("secular_theme") or "").strip().lower()
        if not th or th in ("none", "n/a"):
            continue
        by_theme.setdefault(th, []).append(p)
    caps = []
    for th, members in sorted(by_theme.items()):
        non_durable = [m["symbol"] for m in members
                       if not (str(m.get("moat", "")).upper() == "WIDE" and m.get("moat_erosion") != "CAP")]
        if len(non_durable) >= 2:
            caps.append({"names": non_durable, "max_units": max_units, "axis": f"secular-theme:{th}"})
            print(f"secular-theme cap: {th} carries {len(non_durable)} non-durable legs {non_durable} -> combined units <= {max_units}")
    return caps


def moat_per_name_cap(p, u, extra_flags=()):
    """Half-size teeth: cro_only / stale_anchor (existing) + moat_erosion=='CAP' + skeptic-coverage
    (MISSING / stale-REFUTED). extra_flags lets a caller add book-specific boolean keys to the OR."""
    # Skeptic-coverage teeth apply to EVERY seat, lanes included — an un-vetted seat is half-sized.
    if p.get("skeptic_missing") or p.get("skeptic_stale_refuted"):
        return min(u, 0.5)
    # Unified-skeptic MATERIAL correction (a load-bearing number/date/anchor moved): a BOUNDED
    # 3/4 haircut — consequences without the numeric-cap-as-ceiling bug class (X1/VB-P5).
    if p.get("correction_severity") == "material":
        u = min(u, 0.75)
    # LANE CONTRACT: an equity special-sit seat is EVENT-driven — the Director's STEP-3b exempted it
    # from the compounder moat/erosion teeth, and the publish layer already floor-sizes it harder
    # (1.5% risk-to-floor). Applying the moat half-cap here would contradict that contract.
    if p.get("lane") == "equity_special_sit":
        return u
    if p.get("cro_only") or p.get("stale_anchor") or p.get("moat_erosion") == "CAP" \
            or any(p.get(k) for k in extra_flags):
        return min(u, 0.5)
    return u
