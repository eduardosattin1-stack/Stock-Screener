"""
opus_ev.py — fill-aware, probability-grounded EV for an Opus option strategy.

Replaces the conviction*mid heuristic. For each strategy it:
  1. matches the strategy legs to the REAL chain legs (bid/ask/delta) from the
     gather's strategy_input.json,
  2. prices entry at a REALISTIC fill (cross the spread: buy@ask, sell@bid),
  3. recomputes max_gain / max_loss / breakeven from that fill (this also kills
     the long-call max_gain=999 placeholder artifact),
  4. assigns P(profit) from the v4 model's move-probability curve for the bullish
     debit/long structures (the same interpolation the MassiveOptionsCard uses),
     or the market-implied delta for credit structures, and
  5. returns EV per contract + the pieces, so the /performance column and the card
     can rank on a number that survives the bid/ask and isn't a conviction guess.

This is still an EX-ANTE estimate. The Opus PAPER TRACKER (realized, marked from
live chains) is the actual validator — see opus_paper_tracker.py.
"""
from __future__ import annotations
from typing import Optional


def _p_up(move_pct: float, p20: float) -> float:
    """Model P(reach +move_pct) anchored on p20 = P(+20%). Mirrors MassiveOptionsCard:
    +5%->p20*3.41(cap .80), +10%->*2.29(.65), +15%->*1.49(.50), +20%->p20."""
    pts = [(5.0, min(p20 * 3.41, 0.80)), (10.0, min(p20 * 2.29, 0.65)),
           (15.0, min(p20 * 1.49, 0.50)), (20.0, p20)]
    if move_pct <= 0:
        return 0.85
    if move_pct <= pts[0][0]:
        return min(pts[0][1] + (pts[0][0] - move_pct) * 0.02, 0.90)
    if move_pct >= pts[-1][0]:
        return max(pts[-1][1] - (move_pct - pts[-1][0]) * 0.01, 0.01)
    for i in range(len(pts) - 1):
        if pts[i][0] <= move_pct <= pts[i + 1][0]:
            f = (move_pct - pts[i][0]) / (pts[i + 1][0] - pts[i][0])
            return pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f
    return p20


def _chain_legs(pick: dict, expiration: str) -> dict:
    """Map (strike, right) -> {bid, ask, delta} for the strategy's expiration."""
    out = {}
    for exp in (pick.get("chain") or {}).get("expirations") or []:
        if exp.get("expiration") == expiration:
            for lg in exp.get("legs") or []:
                out[(round(float(lg["strike"]), 4), lg.get("right"))] = lg
    return out


def _fill(leg_q: dict, side: str) -> Optional[float]:
    """Realistic fill: BUY pays the ask, SELL receives the bid."""
    px = leg_q.get("ask") if side == "BUY" else leg_q.get("bid")
    return float(px) if px and px > 0 else None


def compute_ev(strategy: dict, pick: dict) -> Optional[dict]:
    """Return {ev, pop, net_fill, max_gain_fill, max_loss_fill, breakeven_fill,
    method} per contract, or None if it can't be priced from the real chain."""
    if not strategy or strategy.get("structure") == "skip":
        return None
    legs = strategy.get("legs") or []
    if not legs:
        return None
    spot = ((pick.get("chain") or {}).get("spot")) or pick.get("price")
    p20 = pick.get("hit_prob_60d") or 0.0
    if not spot or spot <= 0:
        return None
    cl = _chain_legs(pick, strategy.get("expiration", ""))

    # resolve each leg's realistic fill price + delta
    resolved = []
    for lg in legs:
        k = round(float(lg.get("strike", 0)), 4)
        right = lg.get("right")
        side = (lg.get("action") or "").upper()
        q = cl.get((k, right))
        if not q:
            return None  # leg not in the chain band -> can't price honestly
        px = _fill(q, side)
        if px is None:
            return None  # no two-sided market -> untradeable, no EV
        resolved.append({"strike": k, "right": right, "side": side,
                         "qty": float(lg.get("qty", 1) or 1), "px": px,
                         "delta": q.get("delta")})

    # net cash to OPEN (per share): pay ask for buys, receive bid for sells.
    net_debit = sum((r["px"] if r["side"] == "BUY" else -r["px"]) * r["qty"] for r in resolved)

    calls = [r for r in resolved if r["right"] == "C"]
    puts = [r for r in resolved if r["right"] == "P"]
    longs = [r for r in resolved if r["side"] == "BUY"]
    shorts = [r for r in resolved if r["side"] == "SELL"]

    # ---- single long call (debit, unbounded upside -> value to the stated target)
    if len(resolved) == 1 and resolved[0]["right"] == "C" and resolved[0]["side"] == "BUY":
        debit = net_debit
        strike = resolved[0]["strike"]
        be = strike + debit
        tgt_move = strategy.get("target_move_pct") or 20.0
        tgt_price = spot * (1 + tgt_move / 100.0)
        gain_at_tgt = max(0.0, tgt_price - strike) - debit
        p_tgt = _p_up(tgt_move, p20)
        p_be = _p_up((be - spot) / spot * 100.0, p20)
        ev = (p_tgt * gain_at_tgt - (1 - p_be) * debit) * 100
        return {"ev": round(ev, 1), "pop": round(p_be, 3), "net_fill": round(-debit, 2),
                "max_gain_fill": round(gain_at_tgt, 2), "max_loss_fill": round(debit, 2),
                "breakeven_fill": round(be, 2), "method": "long-call (model, to target)"}

    # ---- bull call (debit) spread: buy lower call, sell higher call
    if len(calls) == 2 and len(longs) == 1 and len(shorts) == 1 and net_debit > 0:
        k_long = longs[0]["strike"]; k_short = shorts[0]["strike"]
        if k_short > k_long:
            width = k_short - k_long
            debit = net_debit
            max_gain = width - debit
            max_loss = debit
            be = k_long + debit
            p_short = _p_up((k_short - spot) / spot * 100.0, p20)
            p_be = _p_up((be - spot) / spot * 100.0, p20)
            ev = (p_short * max_gain - (1 - p_be) * max_loss) * 100
            return {"ev": round(ev, 1), "pop": round(p_be, 3), "net_fill": round(-debit, 2),
                    "max_gain_fill": round(max_gain, 2), "max_loss_fill": round(max_loss, 2),
                    "breakeven_fill": round(be, 2), "method": "debit-spread (model)"}

    # ---- bull put (credit) spread: sell higher put, buy lower put
    if len(puts) == 2 and len(longs) == 1 and len(shorts) == 1 and net_debit < 0:
        k_short = shorts[0]["strike"]; k_long = longs[0]["strike"]
        if k_short > k_long:
            width = k_short - k_long
            credit = -net_debit
            max_gain = credit
            max_loss = width - credit
            be = k_short - credit
            # market-implied P(keep credit) = P(stay above short put) ~ 1 - |short put delta|.
            sd = shorts[0].get("delta")
            p_keep = (1 - abs(float(sd))) if sd is not None else 0.5
            p_keep = max(0.05, min(0.95, p_keep))
            ev = (p_keep * max_gain - (1 - p_keep) * max_loss) * 100
            return {"ev": round(ev, 1), "pop": round(p_keep, 3), "net_fill": round(credit, 2),
                    "max_gain_fill": round(max_gain, 2), "max_loss_fill": round(max_loss, 2),
                    "breakeven_fill": round(be, 2), "method": "credit-spread (delta)"}

    return None  # structure we don't price here -> leave EV unset (no fake number)
