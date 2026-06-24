"""
ibkr_symbol_map.py — map IBKR contracts to the app's FMP-style tickers.

Pure, dependency-free (no ib_async / requests) so it can be unit-tested and
imported by the sync engine without a gateway. The app stores tickers the way
FMP / the screener do: US names are bare (CMCSA), European/other listings carry
a suffix (AIR.PA, DHER.DE, 9999.HK). IBKR instead reports a local exchange
symbol + an exchange/currency, so we translate.

Three layers, applied in order:
  1. CONID_OVERRIDE  — explicit {ib_conid: "APP.TICKER"} for names whose IBKR
     local symbol doesn't resemble the FMP ticker at all (O4J0, ADB, 9999…).
     Keyed by the stable contract id so it never drifts. This is the escape
     hatch Bruno fills in for the handful that don't auto-resolve.
  2. UNDERLYING_OVERRIDE — {ib_underlying_symbol: "APP.UNDERLYING"} for EUROPEAN
     OPTION underlyings, where currency alone (EUR) can't pick the right suffix.
  3. EXCHANGE_TO_SUFFIX — (primary_exchange|exchange, currency) -> suffix, the
     inverse of ibkr_options_batch.SUFFIX (KEEP IN SYNC), plus the venues the
     live account actually uses (SEHK→.HK, FWB→.DE).

Anything that still doesn't resolve falls back to the bare IBKR symbol and is
flagged `unmapped` (the row still shows up — we never silently drop a holding).
"""
from __future__ import annotations
from typing import Optional

# Inverse of ibkr_options_batch.SUFFIX (keep the two in sync), keyed by
# (exchange, currency). EUR maps to many venues, so the exchange must
# disambiguate — currency alone is not enough.
EXCHANGE_TO_SUFFIX = {
    ("SBF", "EUR"): ".PA",        # Euronext Paris
    ("AEB", "EUR"): ".AS",        # Euronext Amsterdam
    ("ENEXT.BE", "EUR"): ".BR",   # Euronext Brussels
    ("BVME", "EUR"): ".MI",       # Borsa Italiana
    ("IBIS", "EUR"): ".DE",       # Xetra
    ("IBIS2", "EUR"): ".DE",      # Xetra (secondary book)
    ("FWB", "EUR"): ".DE",        # Frankfurt floor → treat as .DE
    ("LSE", "GBP"): ".L",         # London
    ("EBS", "CHF"): ".SW",        # SIX Swiss
    ("BM", "EUR"): ".MC",         # Bolsa de Madrid
    ("BVL", "EUR"): ".LS",        # Euronext Lisbon
    ("VSE", "EUR"): ".VI",        # Vienna
    ("HEX", "EUR"): ".HE",        # Helsinki
    ("SFB", "SEK"): ".ST",        # Stockholm
    ("CPH", "DKK"): ".CO",        # Copenhagen
    ("OSE", "NOK"): ".OL",        # Oslo
    ("SEHK", "HKD"): ".HK",       # Hong Kong
}

# Currency-only fallback for stocks when the exchange is unknown/SMART but the
# currency unambiguously implies one venue. Deliberately tiny — only currencies
# with a single supported listing suffix.
CURRENCY_TO_SUFFIX = {
    "GBP": ".L",
    "CHF": ".SW",
    "SEK": ".ST",
    "DKK": ".CO",
    "NOK": ".OL",
    "HKD": ".HK",
}

# Explicit per-contract overrides for names whose IBKR local symbol doesn't
# match the FMP/app ticker. Keyed by IBKR conid (stable across sessions).
# Bruno: verify these against the screener's ticker before the first live write.
CONID_OVERRIDE = {
    425145098: "9999.HK",   # 9999 @SEHK → NetEase (HK line)
    13013250:  "ADBE",      # ADB @FWB   → Adobe Inc (Frankfurt line of the US name; ISIN US00724F1012)
    590822017: "EWSP.PA",   # O4J0 @SBF  → iShares S&P 500 Equal-Weight UCITS ETF (Euronext Paris; localSymbol EWSP)
}

# European OPTION underlyings: IBKR underlying symbol -> app underlying ticker.
# (US option underlyings already equal the app ticker, so no entry is needed.)
UNDERLYING_OVERRIDE = {
    "DHER": "DHER.DE",   # Delivery Hero (Xetra)
    "PRX": "PRX.AS",     # Prosus (Amsterdam)
}


def _suffix_for(exchange: Optional[str], primary: Optional[str], currency: Optional[str]) -> Optional[str]:
    """Resolve a ticker suffix from (exchange/primary, currency). primary wins."""
    for ex in (primary, exchange):
        if ex:
            suf = EXCHANGE_TO_SUFFIX.get((ex, currency))
            if suf:
                return suf
    return CURRENCY_TO_SUFFIX.get(currency or "")


def map_stock(ib_symbol: str, exchange: Optional[str], primary: Optional[str],
              currency: Optional[str], conid: Optional[int]) -> tuple[str, bool]:
    """Return (app_ticker, unmapped). unmapped=True means we fell back to the
    bare IBKR symbol because no rule matched (row still surfaces for review)."""
    if conid is not None and conid in CONID_OVERRIDE:
        return CONID_OVERRIDE[conid], False
    if (currency or "USD").upper() == "USD":
        return ib_symbol, False
    suf = _suffix_for(exchange, primary, currency)
    if suf:
        return ib_symbol + suf, False
    return ib_symbol, True   # unresolved non-USD listing — show under raw symbol


def map_option_underlying(ib_underlying: str, exchange: Optional[str],
                          primary: Optional[str], currency: Optional[str],
                          conid: Optional[int]) -> tuple[str, bool]:
    """Map an option's UNDERLYING to the app ticker (so legs group under the
    name). US underlyings are bare; EU underlyings come from UNDERLYING_OVERRIDE
    (currency can't disambiguate EUR venues), then the exchange/currency suffix."""
    if conid is not None and conid in CONID_OVERRIDE:
        return CONID_OVERRIDE[conid], False
    if (currency or "USD").upper() == "USD":
        return ib_underlying, False
    if ib_underlying in UNDERLYING_OVERRIDE:
        return UNDERLYING_OVERRIDE[ib_underlying], False
    suf = _suffix_for(exchange, primary, currency)
    if suf:
        return ib_underlying + suf, False
    return ib_underlying, True
