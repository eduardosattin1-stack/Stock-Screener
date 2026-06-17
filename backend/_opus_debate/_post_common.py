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
    merged, stale = {}, []
    for f in sorted(skep_dir.glob("*.json")):
        try:
            if f.stat().st_mtime < apex_mtime - 1:
                stale.append(f.stem)
                continue
            d = json.load(open(f, encoding="utf-8"))
            if d.get("symbol"):
                merged[d["symbol"]] = d
        except Exception as e:
            print(f"WARN skeptic: shard {f.name} unreadable ({e})")
    if stale:
        print(f"skeptic: ignored {len(stale)} stale shard(s) older than the apex: {sorted(stale)}")
    if not merged:
        return apx
    (skep_dir.parent / (skep_dir.name + "_results.json")).write_text(
        json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
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
        if isinstance(v.get(conviction_field), (int, float)):
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
    """Half-size teeth: cro_only / stale_anchor (existing) + moat_erosion=='CAP' (new, additive).
    extra_flags lets a caller add book-specific boolean keys to the OR."""
    if p.get("cro_only") or p.get("stale_anchor") or p.get("moat_erosion") == "CAP" \
            or any(p.get(k) for k in extra_flags):
        return min(u, 0.5)
    return u
