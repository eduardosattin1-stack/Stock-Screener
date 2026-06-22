#!/usr/bin/env python3
"""
Retroactive house-voice pass over stored Speculair debate / catalyst write-ups.

The AGENT_VOICE prompt change only affects FUTURE runs; the prose already saved in
frontend/public/speculair_debate_history/<SYM>.json (mirrored to GCS, which the
stock page reads first) was produced by the old prompts and still reads in code-
speak. This rewrites the PROSE fields of an entry in place — facts and numbers
unchanged — while leaving every structured field (verdict, catalyst_status,
conviction, scores, prices, enums) exactly as-is.

apply(sym, newprose): merge {field: rewritten_text} into the latest entry of
<SYM>.json (and entry["catalyst"]["binding_reason"] via the key
"catalyst_binding_reason"). Returns the path written. The Workflow batch and this
FIG pilot both call apply() — one writer, many rewrites.
"""
import json
from pathlib import Path

_PUBLIC = Path(__file__).resolve().parent.parent / "frontend" / "public"
RAW = _PUBLIC / "speculair_debate_history"          # pristine — the pipeline/Director reads this
VOICED = _PUBLIC / "speculair_debate_voiced"        # house-voice display copy — the UI reads this
STAGING = Path(__file__).resolve().parent / "_voice_staging"  # per-symbol rewritten-prose dropbox (batch)

# Fields that hold human-readable prose (safe to rewrite). Everything else is the
# machine contract and must never be touched.
PROSE_FIELDS = {
    "bull_thesis", "bear_thesis", "sop_bull", "sop_bear", "sop_breakdown", "risk_reward",
    "catalyst_summary", "dated_milestone", "forcing_function", "consensus_delta",
    "valley_of_death", "positioning_washout", "moderator_conclusion", "interrogator_dossier",
    "skeptic_kill_fact", "skeptic_corrections", "peer_comps_note", "role_in_scaleout",
    "catalyst_binding_reason",
}
# Deliberately NOT rewritten (machine contract / ambiguous): catalyst_status (enum in some
# files, sentence in others), verdict, conviction, scores, prices, dates, moat/trajectory enums.


def apply(sym: str, newprose: dict) -> Path:
    # Read the pristine raw debate, copy it, swap in the house-voice prose, and write
    # the full display copy to the SEPARATE voiced path. Structured fields (verdict,
    # catalyst_status, conviction, scores, prices, date) are carried over verbatim so
    # the UI can render the voiced copy standalone; the date lets the UI fall back to
    # raw once a future re-debate supersedes this overlay.
    data = json.loads((RAW / f"{sym}.json").read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError(f"{sym}: unexpected shape")
    entry = data[0]
    for k, v in newprose.items():
        if k not in PROSE_FIELDS or not isinstance(v, str) or not v.strip():
            continue  # allowlist only; never touch structured fields, skip junk
        if k == "catalyst_binding_reason":
            cat = entry.get("catalyst")
            if isinstance(cat, dict):
                cat["binding_reason"] = v
        else:
            if k in entry:  # only rewrite fields the raw actually has
                entry[k] = v
    entry["voiced"] = True  # marker so the UI/agents can tell a display copy from a raw one
    VOICED.mkdir(parents=True, exist_ok=True)
    out = VOICED / f"{sym}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def apply_all() -> tuple[list, list]:
    """Apply every backend/_voice_staging/<SYM>.json (a {prose_field: text} map written by
    the batch agents) onto the matching raw debate, producing the voiced display copies.
    Returns (ok, failed)."""
    ok, failed = [], []
    for sp in sorted(STAGING.glob("*.json")):
        sym = sp.stem
        try:
            prose = json.loads(sp.read_text(encoding="utf-8"))
            if not isinstance(prose, dict):
                raise ValueError("staging not a dict")
            apply(sym, prose)
            ok.append(sym)
        except Exception as e:  # noqa: BLE001
            failed.append((sym, f"{type(e).__name__}: {e}"))
    return ok, failed


FIG = {
    "bull_thesis": "Figma is a supply-overhang story, not a broken business. It went public around $33 in late July 2025, spiked to ~$142 intraday on IPO froth, then fell ~81% to ~$19 as four waves of insider lock-up shares (the period insiders are barred from selling) hit the market. The business is excellent and re-accelerating: $1.16B in trailing revenue growing ~41% (Q1-2026 was +46% to $333M), trading at about 7x EV/sales (enterprise value divided by revenue) versus a software-peer average near 19x. The catalyst is the forced seller running out: of the locked insider block (54.1% of Class A, over $6B at a low cost basis), 65% has already been released across Q3-2025 to Q1-2026. The final ~35% (~77.7M shares) frees up after Q2-2026 earnings or Aug 31, 2026, whichever comes first. Once that last seller is gone, the stock can re-rate toward fundamentals — roughly $32, still below the ~$36.88 average analyst target. Downside is tight: ~$19 sits only ~9% above the ~$17.50 floor.",
    "bear_thesis": "The make-or-break event is a supply release, not a deal that pays out. Around Aug 31, 2026 the final ~77.7M low-cost shares (>$6B) become sellable by venture investors whose cost is a fraction of today's price. Forced selling usually comes before any re-rating, so the catalyst is bearish the moment it lands and can pin or push the stock down for weeks. There is no contractual payout, no contingent payment, no breakup value, no merger terms — the $32 target is purely a hoped-for re-rating the market is free to ignore. The accounting looks ugly (a $1.40B loss, -$3.38 EPS), which keeps mainstream buyers away during the exact window supply hits. AI design tools are a real long-term threat to a design franchise. A messy insider sale or any growth wobble at the Q2-2026 report could break the ~$17.50 floor and revisit the $16.60 52-week low.",
    "sop_bull": "Once the overhang clears, ~$32. A 40-46% grower with the forced seller gone should not trade at ~7x EV/sales against peers near 19x. Even a conservative ~11-12x forward sales on ~$1.3-1.4B of forward revenue, after the dual-class discount, supports ~$32 — still under the ~$36.88 average analyst target and well inside the $25-$63 range.",
    "sop_bear": "Wash-out floor ~$17.50 (52-week low $16.60). Even at a punished ~6x EV/sales to reflect a disorderly insider dump and slowing growth, a $1.16B-revenue 40% grower holds a base in the high-$16s to high-$17s. It is a valuation floor, not net cash — real, but a growth miss plus a messy unlock could pierce it.",
    "sop_breakdown": "Win case (overhang cleared, ~11-12x forward sales): ~$32. Loss case (disorderly unlock, punished to ~6x): ~$17.50. Weighting ~45% to the re-rating and ~55% to a slow-clear or floor outcome — the catalyst adds supply and absorption can't be confirmed beforehand — gives a base case around $24. Anchored on $1.16B trailing revenue, +41-46% growth, ~7x EV/sales vs peers ~19x; average analyst target $36.88 (range $25.25-$63).",
    "risk_reward": "About +67% to the $32 target versus about -8.5% to the $17.50 floor from ~$19.12 today — roughly 3-to-1. Attractive on paper, but it hinges on an event that is bearish on arrival, so the real payoff depends on buying after the August 2026 flush, not before it.",
    "catalyst_summary": "A forced-seller, post-IPO supply story. An extended lock-up (an SEC filing dated Aug 30, 2025) covers 54.1% of Class A shares (>$6B at a low cost basis) releasing in four waves; three (65%) already cleared between Q3-2025 and Q1-2026. The final ~35% (~77.7M shares) frees up after Q2-2026 earnings or Aug 31, 2026, whichever first. It is dated and binding, but it releases shares (bearish on arrival) and the upside is a hoped-for re-rating rather than a contractual payout — so it is a soft, dated catalyst for the watchlist, not a clean arbitrage. Price ~$19.12 (Jun 22, 2026); 52-week low $16.60.",
    "forcing_function": "The catalyst is the Aug 31, 2026 / Q2-2026 final lock-up expiry — the last ~77.7M-share, >$6B insider block becomes freely sellable. Once that final seller is exhausted, the overhang that has capped the stock since the IPO is gone, clearing the way to re-rate toward fundamentals.",
    "consensus_delta": "Where we disagree with the market: the street sees an expensive money-loser still bleeding from the IPO collapse — fixed on the $1.40B loss and the IPO crash, with a Hold rating (~$36.88 average target). What it under-weights is that the overhang is self-extinguishing: 65% of the locked insider block already cleared, and the final wave frees up in August 2026 — after which the seller that has capped the stock since the IPO is gone. The market prices FIG at ~7x EV/sales while a 40-46% grower with a cleared overhang is worth far closer to the ~19x peer level. The mispricing is technical (IPO supply), not fundamental.",
    "valley_of_death": "The risky window is the next 3-9 months: the August 2026 unlock releases ~77.7M shares (>$6B) of low-cost venture stock into the market. That is the trade's main hazard — forced selling will likely pin or pressure the stock into and through the event, and a soft Q2-2026 growth print in the same window could pierce the $17.50 floor toward the $16.60 low. There is no debt-maturity risk (it is cash-rich and equity-funded), so the danger is purely the supply flush, not solvency.",
    "positioning_washout": "The mechanical seller is the insider/venture block whose cost is a fraction of $19 — they sell into any liquidity regardless of price, and that forced selling is exactly the wash-out that creates the entry. IPO-chasing retail and momentum holders have already been flushed out (down 81% from the high). The remaining forced selling is the August 2026 wave; once it clears, the marginal seller disappears and the shareholder base resets to fundamentals-driven holders.",
    "moderator_conclusion": "Bottom line: FIG is a genuine forced-seller exhaustion setup on an excellent, re-accelerating business (+46% YoY in Q1-2026, ~7x EV/sales vs peers 19x) trapped under IPO supply mechanics. The asymmetry is real (~3-to-1; ~+67% to a $32 re-rating vs ~-8.5% to a $17.50 floor only ~9% below today, with the 52-week low at $16.60 largely realized). But the decisive point: the make-or-break catalyst is a supply release on Aug 31, 2026 / Q2-2026 earnings — bearish on arrival, with >$6B of insider stock hitting the market before the re-rating it enables. You do not front-run $6B of forced selling. So this is one to watch for capitulation, not an aggressive buy: wait for the August wave to flush, confirm the stock has stopped falling, then enter. Conviction 4 of 5 — the thesis is real, dated, and the downside is tight; the only thing keeping it from a 5 is the unconfirmable absorption of that last unlock and the manageable (not absent) AI-displacement question. On valuation alone, ignoring the catalyst, a 40% grower at 7x sales versus a 19x peer set is genuine value with a real floor.",
    "skeptic_kill_fact": "Skeptic check — verified, with corrections. The make-or-break event is a supply release with no contractual payout — bearish on arrival, not a value-resolving close. The SEC filing (Aug 30, 2025) checks out word-for-word (the 17.5% / 20% / 27.5% waves are done; the final ~77.7M shares / ~35% free up on the earlier of Q2-2026 earnings or Aug 31, 2026), so the date is real — but the $32 target is pure re-rating hope with no event-locked floor. The decisive problem with the 'absorb, then re-rate' idea: the three earlier waves already cleared and produced no re-rating — FIG fell ~40% this year and sits near its $16.60 low right through the absorption. The final, largest, lowest-cost wave can pin or pierce the floor for weeks. One to watch for capitulation, never to front-run.",
    "interrogator_dossier": "# Figma (FIG) — deep dive on the setup\n\n**Frame:** This is not a quality or compounding call. FIG is a forced-seller, post-IPO supply-overhang situation. The thesis is the gap between today's price (~$19.12, Jun 22, 2026) and an overhang-cleared target (~$32), gated on the final insider lock-up clearing, with a floor at the post-wash-out base (~$16.60 52-week low / ~$17.50). The business is excellent (40%+ growth, a design-software franchise); the price is wrecked by IPO mechanics, not a broken business.\n\n## 1. The event — real, dated, binding?\nReal and dated, but it releases supply rather than clearing it at a fixed trigger. Figma went public in late July 2025 (~$33, spiked to ~$142 intraday, then fell ~81% from the high; down ~40% this year). On Aug 30, 2025 it agreed an extended lock-up on 54.1% of Class A (the venture/insider low-cost block, >$6B) with a phased release: 17.5% (~38.9M) after Q3-2025 earnings (done); 20% (~44.4M) after 2025 year-end (done); 27.5% (~61.1M) after Q1-2026 (done); the final ~35% (~77.7M) after Q2-2026 earnings or Aug 31, 2026, whichever first. That last unlock is the make-or-break event — a hard, dated, binding corporate event (an SEC filing). Critically, it adds supply; it is bearish on arrival. The bull case is that the last wave clears, the seller is exhausted, and the stock reprices to fundamentals — a capitulation setup, not a deal-close arbitrage.\n\n## 2. The downside floor\nA technical, wash-out floor, not an asset floor. 52-week low $16.60; floor ~$17.50. Real support: $1.16B trailing revenue growing ~41% (Q1-2026 +46%, $333M), ~7x EV/sales vs software peers ~19x. On any reasonable forward-sales multiple, ~$17-18 is a defensible base for a 40% grower; it only breaks if the whole insider block dumps at once and growth breaks too.\n\n## 3. Red flags\nThe catalyst points the wrong way for an aggressive buy — the dated event releases >$6B of low-cost stock, and forced selling comes before the re-rating. There is no deal, fixed payout, contingent payment, or breakup gap — the $32 target is a re-rating (street average $36.88, range $25.25-$63), not an event-locked value. A large loss (-$1.40B, -$3.38 EPS) keeps mainstream buyers away during the supply window. Dual-class founder control makes public holders price-takers to the insiders' selling pace.\n\n## 4. Green flags\nMost of the overhang is already behind it (65% cleared Q3-2025 to Q1-2026; August 2026 is the last wave). The franchise is intact and re-accelerating (+46% YoY in Q1-2026). ~7x EV/sales vs peers ~19x is a genuine post-wash-out discount on top-tier-growth software. Today's ~$19.12 is only ~9% above the $17.50 floor — downside is tight and largely realized.\n\n## 5. Catalyst type\nDated (Aug 31, 2026 / Q2-2026) and binding, but a supply release that must be absorbed before any re-rating, with upside being a re-rating rather than a contractual payout. A soft, dated catalyst for the watchlist, not a clean arbitrage. The right posture is to wait for the flush (the August unlock), then enter once the stock has clearly stopped falling.\n\n## 6. Summary for the director\nTrajectory: turning (post-IPO repricing, franchise intact). The key thing to weigh: this is a forced-seller exhaustion trade whose make-or-break event adds supply on a fixed date — you are paid to wait for the August 2026 unlock to flush, not to front-run it. The floor is real (~$17.50) and downside is bounded (~9%), but the catalyst is bearish on arrival, so the asymmetry is a watchlist, not an aggressive buy. Moat: narrow but real (network effects plus switching costs); the AI design-tool threat is manageable, not terminal, since Figma is shipping its own AI features.\n\nManagement credibility 3 of 5 · trajectory turning · moat narrow but real · moat trend stable · AI-displacement threat manageable.",
    "catalyst_binding_reason": "A forced-seller, post-IPO supply story. An extended lock-up (an SEC filing dated Aug 30, 2025) covers 54.1% of Class A shares (>$6B at a low cost basis) releasing in four waves; three (65%) already cleared between Q3-2025 and Q1-2026. The final ~35% (~77.7M shares) frees up after Q2-2026 earnings or Aug 31, 2026, whichever first. It is dated and binding, but it releases shares (bearish on arrival) and the upside is a hoped-for re-rating rather than a contractual payout — so it is a soft, dated catalyst for the watchlist, not a clean arbitrage. Price ~$19.12 (Jun 22, 2026); 52-week low $16.60.",
}

if __name__ == "__main__":
    import sys
    if "--apply-staging" in sys.argv:
        ok, failed = apply_all()
        print(f"applied {len(ok)} voiced files; {len(failed)} failed")
        for s, e in failed[:25]:
            print("  FAIL", s, e)
    else:
        out = apply("FIG", FIG)
        print("wrote", out)
