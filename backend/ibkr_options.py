"""
ibkr_options.py — on-demand options enrichment via Interactive Brokers.

Replaces the (ThetaData-backed) massive_options.enrich_stock for the per-stock
Options Intelligence card. Runs co-located with an IB Gateway / TWS session on an
always-on host (NOT in the nightly Cloud Run scan — IBKR's 60-historical-requests
/ 10-min pacing makes universe-wide bulk infeasible; this is one symbol on demand).

Returns the SAME dict shape massive_options.enrich_stock returned, so the frontend
card + StockData fields work unchanged:
    iv_current (fraction, e.g. 0.30) · iv_rank (0-100) · iv_samples (int)
    spread {strategy, spot, expiration, dte, long_strike, short_strike,
            long_mid, short_mid, net_debit, max_gain_per_contract,
            max_loss_per_contract, break_even_price, break_even_move_pct,
            risk_reward, description}
(pc_ratio / term_structure / iv_30d-60d-90d / implied_earnings_move come in a
later pass — this first version covers what the card needs to render + the
IV-rank the ML/IV-edge use.)

Requires: pip install ib_async   (maintained fork of ib_insync; `import ib_insync`
also works if that's what's installed). Market-data subscriptions must be active
on the IBKR account for live greeks/quotes (OPRA for US; Eurex/Euronext for EU).

CLI:  python ibkr_options.py AAPL
      python ibkr_options.py TEP --exchange SBF --currency EUR    # Euronext Paris
"""
from __future__ import annotations
import os, sys, math, json, argparse, logging
from datetime import datetime
from typing import Optional

log = logging.getLogger("ibkr_options")

try:
    from ib_async import IB, Stock, Option, util  # maintained fork
except Exception:
    from ib_insync import IB, Stock, Option, util  # legacy name

IB_HOST = os.environ.get("IB_GATEWAY_HOST", "127.0.0.1")
IB_PORT = int(os.environ.get("IB_GATEWAY_PORT", "4001"))   # 4001 IB Gateway live · 7497 TWS paper
IB_CLIENT_ID = int(os.environ.get("IB_CLIENT_ID", "17"))
TARGET_DTE = 30        # aim for the expiration nearest this many days out
OTM_PCT = 0.10         # short leg ~10% OTM (bull call spread)
IV_LOOKBACK = "1 Y"    # ATM-IV history window for the IV-rank


def _connect() -> IB:
    ib = IB()
    ib.connect(IB_HOST, IB_PORT, clientId=IB_CLIENT_ID, timeout=15, readonly=True)  # readonly: never place orders on the live account
    # Bound EVERY blocking request (qualifyContracts / reqContractDetails /
    # reqSecDefOptParams / reqHistoricalData). Without this a single unresolvable
    # contract (e.g. a bad EU mapping) or a connectivity blip hangs the whole run
    # indefinitely (raises asyncio.TimeoutError instead, which callers skip).
    ib.RequestTimeout = 25
    return ib


def _round_to(value: float, increments: list[float]) -> float:
    """Nearest available strike from the chain's strike list."""
    return min(increments, key=lambda s: abs(s - value)) if increments else value


def _iv_rank(ib: IB, stock) -> Optional[dict]:
    """Underlying ATM-IV history -> current IV + IV-rank. This is what the IBKR app
    shows as 'IV Rank' and what reqHistoricalData(OPTION_IMPLIED_VOLATILITY) returns."""
    bars = ib.reqHistoricalData(
        stock, endDateTime="", durationStr=IV_LOOKBACK,
        barSizeSetting="1 day", whatToShow="OPTION_IMPLIED_VOLATILITY",
        useRTH=True, formatDate=1,
    )
    ivs = [b.close for b in bars if b.close and b.close > 0]
    if len(ivs) < 2:
        return None
    cur = ivs[-1]
    lo, hi = min(ivs), max(ivs)
    rank = ((cur - lo) / (hi - lo) * 100.0) if hi > lo else 50.0
    return {"iv_current": round(cur, 4), "iv_rank": round(rank, 1), "iv_samples": len(ivs)}


def _spot(ib: IB, stock) -> Optional[float]:
    bars = ib.reqHistoricalData(stock, endDateTime="", durationStr="2 D",
                                barSizeSetting="1 day", whatToShow="TRADES",
                                useRTH=True, formatDate=1)
    return bars[-1].close if bars else None


def _mid(ib: IB, contract) -> Optional[float]:
    """Snapshot mid for an option contract (needs the relevant market-data sub)."""
    t = ib.reqMktData(contract, "", True, False)
    ib.sleep(2.0)
    bid, ask, last = t.bid, t.ask, t.last
    ib.cancelMktData(contract)
    if bid and ask and bid > 0 and ask > 0:
        return (bid + ask) / 2.0
    return last if last and last > 0 else None


def enrich(symbol: str, exchange: str = "SMART", currency: str = "USD",
           spot: Optional[float] = None, ib: "IB | None" = None) -> dict:
    """On-demand options enrichment for one symbol. Returns the card's contract shape.
    `spot` may be supplied (e.g. from FMP/the scan) so we don't need the underlying's
    market-data subscription — useful for EU names where only the OPTION feed is subscribed.
    Pass an existing `ib` (already connected) to reuse one socket across many symbols
    (the batch job does this); otherwise a connection is opened and closed per call."""
    out: dict = {"iv_current": None, "iv_rank": None, "iv_samples": 0, "spread": None}
    own = ib is None
    if own:
        ib = _connect()
    try:
        stock = Stock(symbol, exchange, currency)
        if not ib.qualifyContracts(stock):
            log.warning("could not qualify %s on %s/%s", symbol, exchange, currency)
            return out
        ib.reqMarketDataType(2)  # frozen: live when market open, last snapshot when closed (card doesn't need ticks)

        ivr = _iv_rank(ib, stock)
        if ivr:
            out.update(ivr)
        log.info("%s IV: current=%s rank=%s samples=%s", symbol,
                 out["iv_current"], out["iv_rank"], out["iv_samples"])

        spot = spot or _spot(ib, stock)
        if not spot or spot <= 0:
            log.warning("%s: no spot price (supply --spot / FMP price for names without an underlying data sub)", symbol)
            return out

        # ---- bull-call spread (best-effort; NEVER fabricated) ----
        try:
            params = ib.reqSecDefOptParams(stock.symbol, "", stock.secType, stock.conId)
            chain = next((c for c in params if c.exchange in ("SMART", exchange)), params[0] if params else None)
            today = datetime.now().date()
            def _dte(e):  # e = YYYYMMDD
                return (datetime.strptime(e, "%Y%m%d").date() - today).days
            exps = sorted([e for e in (chain.expirations if chain else []) if _dte(e) >= 7],
                          key=lambda e: abs(_dte(e) - TARGET_DTE))
            if exps:
                expiration = exps[0]
                ex = chain.exchange or exchange
                # Valid, already-qualified strikes FOR THIS EXPIRATION. The global
                # chain.strikes mixes expirations/trading-classes and yields strikes
                # that don't exist for a given expiry (the AAPL 327.5 "No security
                # definition" error). reqContractDetails(strike=0) wildcards strikes
                # and returns fully-qualified contracts (with conId) we can quote.
                details = ib.reqContractDetails(Option(symbol, expiration, 0, "C", exchange=ex, currency=currency))
                by_strike = {cd.contract.strike: cd.contract for cd in details}
                strikes = sorted(by_strike)
                if strikes:
                    long_strike = _round_to(spot, strikes)
                    short_strike = _round_to(spot * (1 + OTM_PCT), strikes)
                    if short_strike > long_strike:
                        long_mid = _mid(ib, by_strike[long_strike])
                        short_mid = _mid(ib, by_strike[short_strike])
                        width = short_strike - long_strike
                        if long_mid and short_mid:
                            net_debit = round(long_mid - short_mid, 2)
                            if 0 < net_debit < width:
                                max_gain = round((width - net_debit) * 100)
                                max_loss = round(net_debit * 100)
                                be = long_strike + net_debit
                                out["spread"] = {
                                    "strategy": "Bull Call Spread (IBKR live)", "spot": round(spot, 2),
                                    "expiration": f"{expiration[:4]}-{expiration[4:6]}-{expiration[6:]}",
                                    "dte": _dte(expiration),
                                    "long_strike": long_strike, "short_strike": short_strike,
                                    "long_mid": round(long_mid, 2), "short_mid": round(short_mid, 2),
                                    "net_debit": net_debit,
                                    "max_gain_per_contract": max_gain, "max_loss_per_contract": max_loss,
                                    "break_even_price": round(be, 2),
                                    "break_even_move_pct": round((be - spot) / spot * 100, 2),
                                    "risk_reward": round(max_gain / max_loss, 2) if max_loss else 0,
                                    "description": "Live IBKR chain. Verify with broker before trading.",
                                }
                        else:
                            log.warning("%s: no live quotes for %s/%s strikes (market-data sub? after hours?)",
                                        symbol, long_strike, short_strike)
        except Exception as e:
            log.warning("%s spread build failed: %s", symbol, e)
        return out
    finally:
        if own:
            ib.disconnect()


def _req(ib, contract):
    return ib.reqMktData(contract, "", True, False)  # snapshot


def chain_snapshot(ib, symbol: str, exchange: str = "SMART", currency: str = "USD",
                   spot: Optional[float] = None, n_strikes: int = 4) -> dict:
    """Rich per-name options snapshot for STRATEGY design (Opus): two expirations
    (~35 DTE and ~70 DTE), a strike band around spot for BOTH calls and puts, each
    with bid/ask + greeks (iv/delta/theta/vega). Market-data only (no historical
    pacing). From this Opus can build any structure — debit/credit spread, calendar
    (across the two expiries), diagonal, cash-secured put, covered call, risk
    reversal — with real prices + greeks. iv_rank is added by the caller (GCS hist)."""
    out: dict = {"spot": None, "expirations": []}
    stock = Stock(symbol, exchange, currency)
    if not ib.qualifyContracts(stock):
        return out
    ib.reqMarketDataType(2)  # frozen
    spot = spot or _spot(ib, stock)
    if not spot or spot <= 0:
        return out
    out["spot"] = round(spot, 2)
    try:
        params = ib.reqSecDefOptParams(stock.symbol, "", stock.secType, stock.conId)
        chain = next((c for c in params if c.exchange in ("SMART", exchange)), params[0] if params else None)
        if not chain or not chain.expirations:
            return out
        today = datetime.now().date()
        def _dte(e): return (datetime.strptime(e, "%Y%m%d").date() - today).days
        valid = sorted([e for e in chain.expirations if _dte(e) >= 7], key=_dte)
        ex = chain.exchange or exchange
        targets = []
        for tgt in (35, 70):
            if valid:
                pick = min(valid, key=lambda e: abs(_dte(e) - tgt))
                if pick not in targets:
                    targets.append(pick)
        for expiration in targets:
            det = ib.reqContractDetails(Option(symbol, expiration, 0, "C", exchange=ex, currency=currency))
            strikes = sorted({d.contract.strike for d in det})
            if not strikes:
                continue
            atm = _round_to(spot, strikes)
            ai = strikes.index(atm)
            band = strikes[max(0, ai - n_strikes): ai + n_strikes + 1]
            reqd = []
            for k in band:
                for right in ("C", "P"):
                    reqd.append((k, right, Option(symbol, expiration, k, right, exchange=ex, currency=currency)))
            ib.qualifyContracts(*[c for _, _, c in reqd])
            tickers = {(k, r): _req(ib, c) for k, r, c in reqd if c.conId}
            ib.sleep(3.0)
            legs = []
            for (k, r), t in tickers.items():
                mg = t.modelGreeks
                legs.append({
                    "strike": k, "right": r,
                    "bid": round(t.bid, 2) if t.bid and t.bid > 0 else None,
                    "ask": round(t.ask, 2) if t.ask and t.ask > 0 else None,
                    "iv": round(mg.impliedVol, 4) if mg and mg.impliedVol else None,
                    "delta": round(mg.delta, 3) if mg and mg.delta is not None else None,
                    "theta": round(mg.theta, 4) if mg and mg.theta is not None else None,
                    "vega": round(mg.vega, 4) if mg and mg.vega is not None else None,
                })
            for _, _, c in reqd:
                try:
                    ib.cancelMktData(c)
                except Exception:
                    pass
            out["expirations"].append({
                "expiration": f"{expiration[:4]}-{expiration[4:6]}-{expiration[6:]}",
                "dte": _dte(expiration), "atm_strike": atm, "legs": legs,
            })
    except Exception as e:
        log.warning("%s chain_snapshot failed: %s", symbol, e)
    return out


def quote_legs(ib, symbol: str, exchange: str, currency: str, expiration: str,
               legs: list) -> dict:
    """Re-quote a SPECIFIC set of option legs (for nightly paper-tracker marking).
    expiration: 'YYYY-MM-DD'. legs: [{strike, right}, ...]. Returns
    {(strike,right): {bid, ask}}. Uses frozen data so it works after hours."""
    exp = expiration.replace("-", "")
    pairs = []
    for lg in legs:
        c = Option(symbol, exp, float(lg["strike"]), lg["right"], exchange=exchange, currency=currency)
        pairs.append((lg, c))
    out: dict = {}
    try:
        ib.reqMarketDataType(2)  # frozen
        ib.qualifyContracts(*[c for _, c in pairs])
        tickers = [(lg, c, ib.reqMktData(c, "", True, False)) for lg, c in pairs if c.conId]
        ib.sleep(3.0)
        for lg, c, t in tickers:
            out[(round(float(lg["strike"]), 4), lg["right"])] = {
                "bid": round(t.bid, 2) if t.bid and t.bid > 0 else None,
                "ask": round(t.ask, 2) if t.ask and t.ask > 0 else None,
            }
        for _, c in pairs:
            try:
                ib.cancelMktData(c)
            except Exception:
                pass
    except Exception as e:
        log.warning("%s quote_legs failed: %s", symbol, e)
    return out


def spot_price(ib, symbol: str, exchange: str = "SMART", currency: str = "USD") -> Optional[float]:
    """Underlying last close (for expiry intrinsic settlement)."""
    try:
        stock = Stock(symbol, exchange, currency)
        if not ib.qualifyContracts(stock):
            return None
        return _spot(ib, stock)
    except Exception:
        return None


def enrich_fast(ib, symbol: str, exchange: str = "SMART", currency: str = "USD",
                spot: Optional[float] = None) -> dict:
    """Fast path for the nightly full-universe batch: ATM IV (from the ATM option's
    modelGreeks — validated to populate frozen/after-hours, US+EU) + the bull-call
    spread, all from MARKET DATA. No reqHistoricalData → not under the 60-req/10-min
    historical pacing cap, so it scales to the whole universe. iv_rank is computed by
    the caller from the GCS IV history. Reuses an existing connection (`ib`)."""
    out: dict = {"iv_current": None, "spread": None}
    stock = Stock(symbol, exchange, currency)
    if not ib.qualifyContracts(stock):
        return out
    ib.reqMarketDataType(2)  # frozen
    if not spot or spot <= 0:
        spot = _spot(ib, stock)
    if not spot or spot <= 0:
        return out
    try:
        params = ib.reqSecDefOptParams(stock.symbol, "", stock.secType, stock.conId)
        chain = next((c for c in params if c.exchange in ("SMART", exchange)), params[0] if params else None)
        if not chain or not chain.expirations:
            return out
        today = datetime.now().date()
        def _dte(e): return (datetime.strptime(e, "%Y%m%d").date() - today).days
        exps = sorted([e for e in chain.expirations if _dte(e) >= 7], key=lambda e: abs(_dte(e) - TARGET_DTE))
        if not exps:
            return out
        expiration = exps[0]; ex = chain.exchange or exchange
        det = ib.reqContractDetails(Option(symbol, expiration, 0, "C", exchange=ex, currency=currency))
        by_strike = {d.contract.strike: d.contract for d in det}
        strikes = sorted(by_strike)
        if not strikes:
            return out
        long_strike = _round_to(spot, strikes)
        short_strike = _round_to(spot * (1 + OTM_PCT), strikes)
        # request ATM (+OTM) together, read once
        ta = _req(ib, by_strike[long_strike])
        tb = _req(ib, by_strike[short_strike]) if short_strike > long_strike else None
        ib.sleep(3.0)
        iv = getattr(ta.modelGreeks, "impliedVol", None) if ta.modelGreeks else None
        if not (iv and iv > 0):
            # No live/frozen options data for this venue (e.g. unsubscribed Euronext/MONEP for EU names —
            # we have US options + Eurex but not Euronext derivatives). IBKR offers FREE 15-min-DELAYED
            # data, which is fine for an IV-rank/spread display card. Retry the ATM (+OTM) under delayed.
            try:
                ib.cancelMktData(by_strike[long_strike])
                if tb: ib.cancelMktData(by_strike[short_strike])
            except Exception:
                pass
            ib.reqMarketDataType(3)            # delayed (free)
            ta = _req(ib, by_strike[long_strike])
            tb = _req(ib, by_strike[short_strike]) if short_strike > long_strike else None
            ib.sleep(4.0)                       # delayed ticks arrive a touch slower than frozen
            ib.reqMarketDataType(2)            # restore frozen for the next name
            iv = getattr(ta.modelGreeks, "impliedVol", None) if ta.modelGreeks else None
            if iv and iv > 0:
                out["delayed"] = True          # so the card/consumer can label it 15-min delayed
        out["iv_current"] = round(iv, 4) if iv and iv > 0 else None
        def _mid_of(t):
            if t and t.bid and t.ask and t.bid > 0 and t.ask > 0:
                return (t.bid + t.ask) / 2.0
            return t.last if t and t.last and t.last > 0 else None
        long_mid, short_mid = _mid_of(ta), _mid_of(tb)
        ib.cancelMktData(by_strike[long_strike])
        if tb: ib.cancelMktData(by_strike[short_strike])
        if short_strike > long_strike and long_mid and short_mid:
            net_debit = round(long_mid - short_mid, 2)
            width = short_strike - long_strike
            if 0 < net_debit < width:
                max_gain = round((width - net_debit) * 100)
                max_loss = round(net_debit * 100)
                be = long_strike + net_debit
                out["spread"] = {
                    "strategy": "Bull Call Spread (IBKR live)", "spot": round(spot, 2),
                    "expiration": f"{expiration[:4]}-{expiration[4:6]}-{expiration[6:]}", "dte": _dte(expiration),
                    "long_strike": long_strike, "short_strike": short_strike,
                    "long_mid": round(long_mid, 2), "short_mid": round(short_mid, 2), "net_debit": net_debit,
                    "max_gain_per_contract": max_gain, "max_loss_per_contract": max_loss,
                    "break_even_price": round(be, 2),
                    "break_even_move_pct": round((be - spot) / spot * 100, 2),
                    "risk_reward": round(max_gain / max_loss, 2) if max_loss else 0,
                    "description": "Live IBKR chain. Verify with broker before trading.",
                }
    except Exception as e:
        log.warning("%s enrich_fast failed: %s", symbol, e)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")  # mute ib_async account-sync spam
    log.setLevel(logging.INFO)
    ap = argparse.ArgumentParser()
    ap.add_argument("symbol")
    ap.add_argument("--exchange", default="SMART")
    ap.add_argument("--currency", default="USD")
    ap.add_argument("--spot", type=float, default=None, help="override spot (e.g. FMP price) to skip the underlying data sub")
    a = ap.parse_args()
    print(json.dumps(enrich(a.symbol, a.exchange, a.currency, a.spot), indent=2, default=str))
