"""Signal selection for the D10 sleeve — pure logic over injected data.

Selection contract (DESIGN.md §4, plus the optimization workflow's correction):
candidates come from the CURRENT nightly scan's standing D10 book, not only
newly staged tracker records — the tracker dedups by symbol, and new-name flow
is lumpy (58 at launch, then ~0.2/day), so restricting to new stagings would
starve the book during droughts.
"""
import bisect
import logging

from .config import BotConfig, HORIZON_LABEL

log = logging.getLogger("tradebot.signals")


def decile_of(p: float, edges: list) -> int:
    """Decile from the SERVED thresholds (same rule as calibration_tracker)."""
    return min(10, bisect.bisect_right(edges, p) + 1)


def health_status(summary: dict, cfg: BotConfig) -> str:
    """Calibration health for the sleeve's regime; UNKNOWN when unreadable."""
    try:
        label = HORIZON_LABEL[cfg.regime]
        return (summary["horizons"][label]["health"]["status"] or "UNKNOWN").upper()
    except (KeyError, TypeError):
        return "UNKNOWN"


def eligibility(stock: dict, cfg: BotConfig) -> str:
    """'' when tradeable, else the reject reason (first failure wins)."""
    sym = stock.get("symbol") or ""
    if not sym:
        return "no-symbol"
    if "." in sym and not cfg.allow_dotted_symbols:
        return "dotted-symbol"  # foreign listing; the tracked strategy skips these
    if cfg.require_currency and (stock.get("currency") or "USD") != cfg.require_currency:
        return "currency"
    p = stock.get(cfg.prob_field)
    price = stock.get("price")
    if not p or p <= 0:
        return "no-probability"
    if not price or price <= 0:
        return "no-price"
    vol = stock.get("volume") or 0
    if price * vol < cfg.min_dollar_volume:
        return "dollar-volume"
    return ""


def select_candidates(stocks: list, edges: list, cfg: BotConfig,
                      held_symbols: set, pending_symbols: set,
                      sector_counts: dict, slots_free: int) -> list:
    """Ranked entry candidates for tonight, at most `slots_free`.

    Ranking: vol_adj_edge_60d desc when present (sparse in the scan), then
    predicted p desc. Sector cap counts held + pending + selected-this-round.
    """
    if slots_free <= 0 or not edges:
        return []
    blocked = {s.upper() for s in held_symbols} | {s.upper() for s in pending_symbols}
    pool = []
    for s in stocks:
        if eligibility(s, cfg):
            continue
        p = float(s.get(cfg.prob_field))
        if decile_of(p, edges) != cfg.decile:
            continue
        if (s.get("symbol") or "").upper() in blocked:
            continue
        pool.append({
            "symbol": s["symbol"].upper(),
            "p": p,
            "price": float(s["price"]),
            "sector": s.get("sector") or "?",
            "edge": s.get("vol_adj_edge_60d"),
            "expected_dd_60d": s.get("expected_dd_60d"),
        })
    pool.sort(key=lambda c: (-(c["edge"] if c["edge"] is not None else float("-inf")), -c["p"]))
    # nulls-last for edge: python sorts -inf last under this key only if we split
    with_edge = [c for c in pool if c["edge"] is not None]
    without = [c for c in pool if c["edge"] is None]
    with_edge.sort(key=lambda c: (-c["edge"], -c["p"]))
    without.sort(key=lambda c: -c["p"])
    ranked = with_edge + without

    picked, counts = [], dict(sector_counts)
    for c in ranked:
        if len(picked) >= slots_free:
            break
        if counts.get(c["sector"], 0) >= cfg.sector_cap_slots:
            continue
        counts[c["sector"]] = counts.get(c["sector"], 0) + 1
        picked.append(c)
    log.info(f"signals: D10 pool={len(ranked)} picked={len(picked)} "
             f"(slots_free={slots_free}, sector-capped={len(ranked) - len(picked)})")
    return picked
