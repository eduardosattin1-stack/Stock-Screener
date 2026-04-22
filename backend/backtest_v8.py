#!/usr/bin/env python3
"""
Stock Screener v8 — Forward-walking Event-Driven Backtest
===========================================================
Author: Bruno Bezerra, CarbonBridge
Replaces the monthly-rebalance proxy in backtest_full.py with a true
event-driven portfolio simulator that honors the scoring model's BUY/SELL
signals as entry/exit triggers.

Design (see BACKTEST_V8_PROGRESS.md for full rationale):

  Phase 1 — Scan cache build:
    Run the screener once for every weekly scan date across the whole
    date range. Persist the composite, factor values, and raw price
    on that date for every symbol. This is the expensive (API-bound)
    phase. It only depends on the *data*, not on any strategy parameter,
    so every sweep config reads from the same cache.

  Phase 2 — Event-driven simulation:
    For each StrategyConfig, replay the scan cache forward day-by-day:
      * Weekly rebalance dates: check exits, then allocate remaining
        slots to top-ranked BUY candidates.
      * Every trading day: mark-to-market the portfolio.
      * Trade events (entries, exits) logged with exit reason.

  Phase 3 — Sweep + walk-forward validation:
    Stratified sample of ~500 configs on training window (2020-2023).
    Rank by CAGR/|MaxDD| with Sharpe > 1.0 floor.
    Run top configs on OOS window (2024-2025). Reject if OOS CAGR
    doesn't beat SPY by >= 5pp with similar DD behaviour.

Anti-look-ahead discipline (Section 3.2 of handoff spec):
  * Annual financials: filter FMP's `fillingDate < D` (NOT `date`)
  * Analyst grades: filter by grade `date < D`
  * Price target consensus: EXCLUDED (FMP exposes only latest snapshot)
  * Forward EPS / analyst-estimates: EXCLUDED (latest-only)
  * 13F: 45-day filing lag + `filingDate < D`
  * Congressional: `disclosureDate < D`
  * Chart data / technicals: prices <= D only
  * ETF holdings: EXCLUDED (snapshot-only)

CLI:
  # Build scan cache once (expensive — API-bound):
  python backtest_v8.py scan --from 2020-01-06 --to 2025-12-29 \\
      --universe sp500_nasdaq --out ./out

  # Single simulation with current production config:
  python backtest_v8.py simulate --scan-cache ./out/scan_cache.jsonl \\
      --from 2020-01-06 --to 2023-12-31 --out ./out

  # Full sweep (500 configs) on training window:
  python backtest_v8.py sweep --scan-cache ./out/scan_cache.jsonl \\
      --train-from 2020-01-06 --train-to 2023-12-31 \\
      --n-configs 500 --out ./out

  # Walk-forward: pick winner from training, validate on OOS:
  python backtest_v8.py walkforward --scan-cache ./out/scan_cache.jsonl \\
      --train-from 2020-01-06 --train-to 2023-12-31 \\
      --oos-from   2024-01-01 --oos-to   2025-12-31 \\
      --sweep-results ./out/sweep_results.csv --out ./out

  # One-shot: scan + sweep + walkforward:
  python backtest_v8.py all --from 2020-01-06 --to 2025-12-31 \\
      --train-split 2024-01-01 --out ./out

Outputs (all under --out/):
  scan_cache.jsonl           # one JSON record per (date, symbol), reusable
  backtest_v8_results.csv    # one row per config, all metrics
  backtest_v8_trades.csv     # trades from winning config
  backtest_v8_equity_curves.csv
  backtest_v8_winner_config.json
  backtest_v8_report.md

Requirements: requests (and sklearn for factor importance in report).
"""

import os, sys, json, math, time, random, logging, argparse, csv, copy, statistics
from datetime import datetime, timedelta, date
from typing import Optional, Dict, List, Tuple, Any, Iterable
from dataclasses import dataclass, field, asdict, replace
from collections import defaultdict

import requests

# ---------------------------------------------------------------------------
# Attempt to reuse the production scorer and the existing data loaders.
# If not importable (e.g. running standalone without the repo), fall back
# to local definitions — but emit a loud warning.
# ---------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s [v8] %(message)s")
log = logging.getLogger("backtest_v8")

try:
    # Prefer the v7.1 computed factor set; we want exactly the same
    # composite math as the live scanner so our backtest is apples-to-apples.
    from backtest_full import (
        load_chart, get_price_on_date, get_chart_slice,
        compute_technicals_historical,
        compute_quality_score,
        compute_sector_momentum_bt,
        compute_congressional_score_bt,
        compute_inst_flow_v2_bt,
        prefetch_congressional,
        fmp as _fmp_v7,
        SYMBOL_META,
        get_symbols as _get_symbols_v7,
        safe_cagr,
    )
    HAVE_V7 = True
    log.info("Imported backtest_full (v7.1) core helpers — will reuse scoring")
except ImportError as e:
    HAVE_V7 = False
    log.warning("Could not import backtest_full: %s. "
                "Rescorer will be used in standalone mode.", e)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

FMP_KEY = os.environ.get("FMP_API_KEY", "")
FMP = "https://financialmodelingprep.com/stable"
RATE_LIMIT = float(os.environ.get("FMP_RATE_LIMIT", "0.04"))

# Signal labels
SIG_STRONG_BUY = "STRONG BUY"
SIG_BUY = "BUY"
SIG_WATCH = "WATCH"
SIG_HOLD = "HOLD"
SIG_SELL = "SELL"
BUY_SET = {SIG_BUY, SIG_STRONG_BUY}

# Exit reasons (stored in Trade.exit_reason)
EXIT_STOP_LOSS = "STOP_LOSS"
EXIT_TAKE_PROFIT = "TAKE_PROFIT"
EXIT_TIME_STOP = "TIME_STOP"
EXIT_SIGNAL = "SIGNAL_SELL"
EXIT_UNIVERSE = "UNIVERSE_EXIT"
EXIT_END = "END_OF_BACKTEST"

# Slippage models
SLIP_CLOSE = "close"          # fill at close of decision day (optimistic)
SLIP_NEXT_OPEN = "next_open"  # fill at open of D+1 (realistic default)
SLIP_NEXT_VWAP = "next_vwap"  # fill at VWAP approx of D+1 (pessimistic)

# Trading-day helpers use FMP chart data rather than a calendar;
# this ensures we never try to trade on a holiday.


# ===========================================================================
# SECTION 1 — DATACLASSES
# ===========================================================================


@dataclass
class StrategyConfig:
    """Everything a sweep varies. Treat as immutable per simulation run."""
    # Entry gates
    # v8.2: defaults lowered from v7.x (0.80/0.85/0.70/0.55/0.40) to match the
    # actual composite_raw distribution observed in 638K-record v8.1 scan.
    composite_floor: float = 0.45
    strong_buy_threshold: float = 0.65
    buy_threshold: float = 0.45
    watch_threshold: float = 0.35
    sell_threshold: float = 0.25
    # Coverage penalty (v8.1)
    # composite_effective = composite_raw * (coverage_pct ** coverage_alpha).
    #   alpha=0.0 -> no penalty (control)
    #   alpha=0.7 -> default (live screener v7.3 matches)
    #   alpha=1.5 -> aggressive penalty
    coverage_alpha: float = 0.7
    # Exits
    stop_loss: float = -0.12       # -12% from entry
    take_profit: float = 0.20      # +20% from entry
    time_stop_days: int = 60
    # Sizing
    target_positions: int = 5
    weighting: str = "equal"       # equal | composite-linear | composite-squared
    # Execution
    rebalance_cadence_days: int = 7
    slippage_model: str = SLIP_NEXT_OPEN
    transaction_cost_bps: float = 20.0    # round-trip, i.e. 10bps each side
    # Macro regime overlay (optional; raises floor in RISK-OFF)
    macro_regime_overlay: bool = False
    macro_risk_off_floor_bump: float = 0.05
    # Bookkeeping
    config_id: str = "baseline"
    notes: str = ""

    def entry_signals(self) -> set:
        return BUY_SET

    def floor_for_date(self, regime: Optional[str]) -> float:
        if self.macro_regime_overlay and regime == "RISK-OFF":
            return self.composite_floor + self.macro_risk_off_floor_bump
        return self.composite_floor

    def as_flat_dict(self) -> dict:
        return asdict(self)


@dataclass
class Position:
    symbol: str
    entry_date: str
    entry_price: float
    entry_composite: float
    entry_signal: str
    shares: float
    entry_cost_usd: float           # net of transaction cost


@dataclass
class Trade:
    symbol: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    shares: float
    pnl_pct: float
    pnl_usd: float
    days_held: int
    exit_reason: str
    entry_composite: float
    exit_composite: Optional[float]
    entry_signal: str
    exit_signal: Optional[str]

    def to_csv_row(self) -> dict:
        return {
            "symbol": self.symbol,
            "entry_date": self.entry_date,
            "exit_date": self.exit_date,
            "entry_price": round(self.entry_price, 4),
            "exit_price": round(self.exit_price, 4),
            "shares": round(self.shares, 6),
            "pnl_pct": round(self.pnl_pct, 4),
            "pnl_usd": round(self.pnl_usd, 2),
            "days_held": self.days_held,
            "exit_reason": self.exit_reason,
            "entry_composite": round(self.entry_composite, 4),
            "exit_composite": (round(self.exit_composite, 4)
                               if self.exit_composite is not None else ""),
            "entry_signal": self.entry_signal,
            "exit_signal": self.exit_signal or "",
        }


@dataclass
class SimulationResult:
    config: StrategyConfig
    equity_curve: List[Tuple[str, float]]     # (date, portfolio_value_usd)
    trades: List[Trade]
    metrics: Dict[str, float]

    def metrics_row(self) -> dict:
        row = dict(self.metrics)
        row["config_id"] = self.config.config_id
        for k, v in self.config.as_flat_dict().items():
            if k != "notes":
                row[f"cfg_{k}"] = v
        return row


# ===========================================================================
# SECTION 2 — FMP CLIENT (local fallback if v7 not imported)
# ===========================================================================


def _fmp_direct(endpoint: str, params: Optional[dict] = None):
    time.sleep(RATE_LIMIT)
    url = f"{FMP}/{endpoint}"
    p = {"apikey": FMP_KEY}
    if params:
        p.update(params)
    try:
        r = requests.get(url, params=p, timeout=25)
        if r.status_code != 200:
            return None
        data = r.json()
        if isinstance(data, dict) and "Error Message" in data:
            return None
        if isinstance(data, dict):
            return [data]
        return data if isinstance(data, list) else None
    except Exception as e:
        log.debug("fmp error on %s: %s", endpoint, e)
        return None


# Unified call surface: always prefer the v7 helper if available, so that
# any rate-limiting / backoff / pacing logic it adds is respected.
def fmp(endpoint: str, params: Optional[dict] = None):
    if HAVE_V7:
        try:
            return _fmp_v7(endpoint, params)
        except Exception as e:
            log.debug("v7 fmp call failed (%s) — falling back direct", e)
    return _fmp_direct(endpoint, params)


# ===========================================================================
# SECTION 3 — HISTORICAL DATA PROVIDER (anti-look-ahead aware)
# ===========================================================================


class HistoricalDataProvider:
    """
    All historical data fetched here is filtered by the caller's ``as_of``
    date so scoring a symbol on D never sees information published after D.

    Caching strategy:
      * Price chart: loaded once per symbol over the full date range.
      * Annual financial statements: loaded once per symbol, filtered by
        ``fillingDate`` (FMP's typo) at read time.
      * Key metrics / balance sheet: ditto.
      * Insider stats, grades: loaded once, filtered by ``date`` at read.
      * 13F: cached per (sym, year, quarter) keyed by 60-day-lagged as-of.
      * Congressional trades: prefetched once via the v7 helper.
      * Sector momentum: cached per (sector, exchange, month).
    """

    def __init__(self, universe: List[str], start_date: str, end_date: str):
        self.universe = list(dict.fromkeys(universe))
        self.start_date = start_date
        self.end_date = end_date

        self._annual_financials: Dict[str, List[dict]] = {}
        self._key_metrics: Dict[str, List[dict]] = {}
        self._balance_sheets: Dict[str, List[dict]] = {}
        self._owner_earnings: Dict[str, List[dict]] = {}
        self._grades: Dict[str, List[dict]] = {}
        self._insider_stats: Dict[str, List[dict]] = {}
        self._earnings_history: Dict[str, List[dict]] = {}
        self._dcf_cache: Dict[str, Optional[float]] = {}

    # ---------- price data -----------------------------------------------------

    def load_all_charts(self, buffer_days: int = 260) -> None:
        """Pre-load chart data for every symbol.

        Kept as a separate call because it's the most expensive step and you
        often want to parallelise it externally.
        """
        if not HAVE_V7:
            raise RuntimeError(
                "Chart loading requires backtest_full.load_chart. "
                "Run from the Stock-Screener/backend directory so the import succeeds.")
        start = (datetime.strptime(self.start_date, "%Y-%m-%d")
                 - timedelta(days=buffer_days)).strftime("%Y-%m-%d")
        loaded = 0
        for i, sym in enumerate(self.universe, 1):
            if i % 25 == 0:
                log.info("  chart preload: %d/%d (%d with data)",
                         i, len(self.universe), loaded)
            chart = load_chart(sym, start_date=start, end_date=self.end_date)
            if chart:
                loaded += 1
        log.info("Charts loaded: %d/%d", loaded, len(self.universe))

    @staticmethod
    def price_on_or_before(sym: str, target_date: str) -> Optional[dict]:
        """Return the chart row with ``date <= target_date`` (closest)."""
        if not HAVE_V7:
            return None
        return get_price_on_date(sym, target_date)

    @staticmethod
    def chart_window(sym: str, as_of: str, trading_days: int = 220) -> List[dict]:
        if not HAVE_V7:
            return []
        return get_chart_slice(sym, as_of, trading_days)

    @staticmethod
    def next_trading_price(sym: str, after_date: str) -> Optional[dict]:
        """Return the chart row immediately AFTER after_date (for next_open slippage)."""
        if not HAVE_V7:
            return None
        from backtest_full import _CHART_CACHE  # internal
        chart = _CHART_CACHE.get(sym, [])
        for row in chart:
            if row["date"] > after_date:
                return row
        return None

    # ---------- financial statements (fillingDate-filtered) -------------------

    def _load_annual_financials(self, sym: str) -> List[dict]:
        if sym in self._annual_financials:
            return self._annual_financials[sym]
        # Pull 15 years so we have a history for every backtest date.
        data = fmp("income-statement", {"symbol": sym,
                                        "period": "annual", "limit": 15}) or []
        # Make sure each row has both `date` (fiscal period end) and
        # `fillingDate` (actual SEC filing). If fillingDate missing, fall
        # back to date + 90d as a conservative stand-in.
        for row in data:
            if not row.get("fillingDate"):
                try:
                    fd = (datetime.strptime(row.get("date", "")[:10], "%Y-%m-%d")
                          + timedelta(days=90)).strftime("%Y-%m-%d")
                    row["fillingDate"] = fd
                except Exception:
                    # If we cannot infer a safe availability stamp, mark the
                    # row as future-dated so the `< as_of` filter excludes it.
                    # Leaving it as an empty string would leak the row into
                    # every past scan.
                    row["fillingDate"] = "9999-12-31"
        data.sort(key=lambda x: x.get("fillingDate", ""))
        self._annual_financials[sym] = data
        return data

    def _load_key_metrics(self, sym: str) -> List[dict]:
        if sym in self._key_metrics:
            return self._key_metrics[sym]
        data = fmp("key-metrics", {"symbol": sym,
                                   "period": "annual", "limit": 15}) or []
        for row in data:
            if not row.get("fillingDate"):
                try:
                    fd = (datetime.strptime(row.get("date", "")[:10], "%Y-%m-%d")
                          + timedelta(days=90)).strftime("%Y-%m-%d")
                    row["fillingDate"] = fd
                except Exception:
                    # If we cannot infer a safe availability stamp, mark the
                    # row as future-dated so the `< as_of` filter excludes it.
                    # Leaving it as an empty string would leak the row into
                    # every past scan.
                    row["fillingDate"] = "9999-12-31"
        data.sort(key=lambda x: x.get("fillingDate", ""))
        self._key_metrics[sym] = data
        return data

    def _load_balance_sheets(self, sym: str) -> List[dict]:
        if sym in self._balance_sheets:
            return self._balance_sheets[sym]
        data = fmp("balance-sheet-statement",
                   {"symbol": sym, "period": "annual", "limit": 10}) or []
        for row in data:
            if not row.get("fillingDate"):
                try:
                    fd = (datetime.strptime(row.get("date", "")[:10], "%Y-%m-%d")
                          + timedelta(days=90)).strftime("%Y-%m-%d")
                    row["fillingDate"] = fd
                except Exception:
                    # If we cannot infer a safe availability stamp, mark the
                    # row as future-dated so the `< as_of` filter excludes it.
                    # Leaving it as an empty string would leak the row into
                    # every past scan.
                    row["fillingDate"] = "9999-12-31"
        data.sort(key=lambda x: x.get("fillingDate", ""))
        self._balance_sheets[sym] = data
        return data

    def _load_owner_earnings(self, sym: str) -> List[dict]:
        if sym in self._owner_earnings:
            return self._owner_earnings[sym]
        data = fmp("owner-earnings", {"symbol": sym, "limit": 20}) or []
        # owner-earnings has `date` (fiscal period end) but no fillingDate;
        # use `date` + 60d as conservative availability date.
        for row in data:
            if not row.get("fillingDate"):
                try:
                    fd = (datetime.strptime(row.get("date", "")[:10], "%Y-%m-%d")
                          + timedelta(days=60)).strftime("%Y-%m-%d")
                    row["fillingDate"] = fd
                except Exception:
                    # If we cannot infer a safe availability stamp, mark the
                    # row as future-dated so the `< as_of` filter excludes it.
                    # Leaving it as an empty string would leak the row into
                    # every past scan.
                    row["fillingDate"] = "9999-12-31"
        data.sort(key=lambda x: x.get("fillingDate", ""))
        self._owner_earnings[sym] = data
        return data

    def _load_grades(self, sym: str) -> List[dict]:
        if sym in self._grades:
            return self._grades[sym]
        # Pull ALL grades so we can time-slice to any as-of date.
        data = fmp("grades", {"symbol": sym, "limit": 500}) or []
        data.sort(key=lambda x: x.get("date", ""))
        self._grades[sym] = data
        return data

    def _load_insider_stats(self, sym: str) -> List[dict]:
        if sym in self._insider_stats:
            return self._insider_stats[sym]
        # Insider statistics are quarterly aggregates — pull plenty of history.
        data = fmp("insider-trading/statistics", {"symbol": sym}) or []
        data.sort(key=lambda x: x.get("date", ""))
        self._insider_stats[sym] = data
        return data

    def _load_earnings_history(self, sym: str) -> List[dict]:
        if sym in self._earnings_history:
            return self._earnings_history[sym]
        data = fmp("earnings", {"symbol": sym, "limit": 40}) or []
        # Earnings rows have `date` (announcement). Safe to filter by this.
        data.sort(key=lambda x: x.get("date", ""))
        self._earnings_history[sym] = data
        return data

    def _get_dcf_value(self, sym: str) -> float:
        """DCF is only available as latest snapshot — we use it as a WEAK
        prior on intrinsic value but mark it as potentially contaminated.

        TODO: exclude from backtest scoring until a historical DCF feed
        is available. For now it's retained but its weight is tiny
        (~0.5% of composite) so the leak is bounded.
        """
        if sym in self._dcf_cache:
            return self._dcf_cache[sym] or 0.0
        data = fmp("discounted-cash-flow", {"symbol": sym})
        val = 0.0
        if data:
            try:
                val = float(data[0].get("dcf") or 0) or 0.0
            except (TypeError, ValueError):
                val = 0.0
        self._dcf_cache[sym] = val
        return val

    # ---------- as-of accessors (the ones scoring actually uses) --------------

    def fundamentals_as_of(self, sym: str, as_of: str) -> dict:
        """
        Return a single dict of fundamental inputs that were AVAILABLE
        strictly before ``as_of``. Everything filtered by fillingDate.
        """
        result = self._blank_fundamentals()

        # 1. Annual income statements — need at least 4 years for 3yr CAGRs.
        inc_all = self._load_annual_financials(sym)
        inc = [r for r in inc_all if r.get("fillingDate", "") < as_of]
        if inc:
            # Sort by fiscal period end (date) ascending, take last 5.
            inc = sorted(inc, key=lambda r: r.get("date", ""))[-5:]
            revs = [self._f(r.get("revenue")) for r in inc]
            eps_list = [self._f(r.get("epsDiluted")) for r in inc]
            gp_list = [self._f(r.get("grossProfit")) for r in inc]

            if len(revs) >= 4 and revs[-4] > 0:
                result["revenue_cagr_3y"] = self._safe_cagr(revs[-4], revs[-1], 3)
            if len(eps_list) >= 4 and eps_list[-4] > 0 and eps_list[-1] > 0:
                result["eps_cagr_3y"] = self._safe_cagr(eps_list[-4], eps_list[-1], 3)
            if revs[-1] > 0 and gp_list[-1] > 0:
                result["gross_margin"] = gp_list[-1] / revs[-1]

            latest_eps = eps_list[-1]
            if latest_eps > 0:
                base_growth = min(result["revenue_cagr_3y"], 0.30)
                future_eps = latest_eps
                for i in range(5):
                    future_eps *= (1 + max(base_growth * (0.8 ** i), 0.03))
                risk_free = 0.045
                terminal_pe = min(max(15, 1 / max(risk_free, 0.03)), 30)
                result["intrinsic_buffett"] = future_eps * terminal_pe / (1.10 ** 5)

        # 2. Key metrics for ROE / ROIC.
        km_all = self._load_key_metrics(sym)
        km = [r for r in km_all if r.get("fillingDate", "") < as_of]
        if km:
            km = sorted(km, key=lambda r: r.get("date", ""))[-5:]
            roes = [self._f(r.get("returnOnEquity")) for r in km]
            roics = [self._f(r.get("returnOnInvestedCapital")) for r in km]
            if roes:
                result["roe_avg"] = sum(roes) / len(roes)
                result["roe_consistent"] = all(r > 0.15 for r in roes)
            if roics:
                result["roic_avg"] = sum(roics) / len(roics)

        # 3. Piotroski / Altman-Z — computed from balance sheet + income
        # history as of fillingDate. Rather than recomputing from first
        # principles (complex) we fetch the score and filter by
        # fillingDate of the *matching* annual statement.
        # For simplicity we accept the latest score older than as_of from
        # key-metrics (which typically contains these scores for FMP
        # Ultimate subscribers). Fall back to 5 if not present.
        if km:
            latest = km[-1]
            result["piotroski"] = int(latest.get("piotroskiScore") or 5)
            try:
                result["altman_z"] = float(latest.get("altmanZScore") or 5.0)
            except (TypeError, ValueError):
                result["altman_z"] = 5.0

        # 4. Owner earnings per share (trailing 4 quarters).
        oe_all = self._load_owner_earnings(sym)
        oe = [r for r in oe_all if r.get("fillingDate", "") < as_of]
        if oe:
            oe = sorted(oe, key=lambda r: r.get("date", ""))[-4:]
            annual_oe_ps = sum(self._f(r.get("ownersEarningsPerShare")) for r in oe)
            result["_annual_oe_ps"] = annual_oe_ps

        # 5. Analyst grades — filter by grade date.
        grades_all = self._load_grades(sym)
        grades = [g for g in grades_all if g.get("date", "") < as_of]
        if grades:
            # Most recent 15 ratings.
            recent = grades[-15:]
            buy_labels = {"Buy", "Strong Buy", "Outperform", "Overweight",
                          "Market Outperform", "Positive"}
            buys = sum(1 for g in recent if (g.get("newGrade") or "") in buy_labels)
            result["grade_buy"] = buys
            result["grade_total"] = len(recent)
            result["grade_score"] = buys / len(recent) if recent else 0.5

        # 6. Insider statistics.
        ins_all = self._load_insider_stats(sym)
        ins = [r for r in ins_all if r.get("date", "") < as_of]
        if ins:
            recent = ins[-2:]
            total_acq = sum(self._f(r.get("totalAcquired")) for r in recent)
            total_disp = sum(self._f(r.get("totalDisposed")) for r in recent)
            result["insider_buy_ratio"] = (
                total_acq / total_disp if total_disp > 0
                else (5.0 if total_acq > 0 else 0.0)
            )
            ratios = [self._f(r.get("acquiredDisposedRatio")) for r in recent]
            avg_r = sum(ratios) / len(ratios) if ratios else 0.0
            if avg_r >= 2.0:
                result["insider_score"] = 1.0
            elif avg_r >= 1.0:
                result["insider_score"] = 0.75
            elif avg_r >= 0.5:
                result["insider_score"] = 0.5
            elif avg_r >= 0.2:
                result["insider_score"] = 0.3
            else:
                result["insider_score"] = 0.15

        # 7. Earnings history — beat rate over last 8 reported quarters.
        earnings_all = self._load_earnings_history(sym)
        earnings = [e for e in earnings_all if e.get("date", "") < as_of][-8:]
        for e in earnings:
            actual = e.get("epsActual")
            est = e.get("epsEstimated")
            if actual is None or est is None:
                continue
            try:
                a = float(actual); s = float(est)
            except (TypeError, ValueError):
                continue
            result["eps_total"] += 1
            if a >= s:
                result["eps_beats"] += 1
            if s != 0:
                result["eps_surprises"].append((a - s) / abs(s))

        # 8. DCF value — EXCLUDED from v8 backtest. FMP's DCF feed is
        # latest-only (no history), so any non-zero value leaks forward
        # information. We leave the key at 0 so downstream code paths stay
        # stable, and skip the API call entirely.
        result["dcf_value"] = 0.0

        # price-target-consensus and analyst-estimates are deliberately
        # EXCLUDED — see header comment. We keep the key so the scorer
        # can treat it as neutral.
        result["target"] = 0.0

        return result

    # ---------- scalar conveniences -------------------------------------------

    @staticmethod
    def _f(x) -> float:
        try:
            return float(x or 0)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _safe_cagr(start, end, years):
        if not start or not end or start <= 0 or end <= 0 or years <= 0:
            return 0.0
        return (end / start) ** (1 / years) - 1

    @staticmethod
    def _blank_fundamentals() -> dict:
        return {
            "piotroski": 5, "altman_z": 5.0, "dcf_value": 0.0,
            "roe_avg": 0.0, "roe_consistent": False, "roic_avg": 0.0,
            "gross_margin": 0.0,
            "revenue_cagr_3y": 0.0, "eps_cagr_3y": 0.0,
            "owner_earnings_yield": 0.0, "intrinsic_buffett": 0.0,
            "intrinsic_avg": 0.0, "margin_of_safety": 0.0, "value_score": 0.0,
            "target": 0.0, "grade_score": 0.5, "grade_buy": 0, "grade_total": 0,
            "eps_beats": 0, "eps_total": 0, "eps_surprises": [],
            "insider_score": 0.5, "insider_buy_ratio": 0.0, "insider_net_buys": 0,
        }


# ===========================================================================
# SECTION 4 — FACTOR COMPUTATION + SIGNAL CLASSIFIER
# ===========================================================================

# These weights mirror v7.1. The whole point of v8 is to re-OPTIMISE the
# weights from the simulator's feature-importance output — so treat these
# as the STARTING prior, not the answer.
WEIGHTS_V8_PRIOR = {
    "technical": 0.35,
    "quality": 0.14,
    "upside": 0.10,
    "proximity": 0.07,
    "catalyst": 0.07,
    "transcript": 0.05,
    "sector_momentum": 0.04,
    "institutional": 0.04,
    "analyst": 0.04,
    "insider": 0.03,
    "earnings": 0.03,
    "congressional": 0.02,
    "institutional_flow": 0.02,
}


def compute_factors_v8(sym: str,
                       as_of: str,
                       price: float,
                       tech: dict,
                       fund: dict,
                       weights: Optional[Dict[str, float]] = None) -> Optional[dict]:
    """
    Compute all v8 factor scores for a stock at a specific date.

    This mirrors ``backtest_full.compute_all_factors`` but:
      * ``tech`` and ``fund`` are both already-as-of-filtered,
      * price-target-consensus is set to zero (see header), so the
        ``upside`` factor relies only on the intrinsic-buffett estimate
        and the DCF (noisy, low weight).
    """
    if not tech or price <= 0:
        return None

    factors: Dict[str, Any] = {}
    weights = weights or WEIGHTS_V8_PRIOR

    # 1. Technical.
    factors["technical"] = tech["bull_score"] / 10.0

    # 2. Upside.
    # NOTE: DCF is EXCLUDED from the v8 backtest composite because FMP's
    # `discounted-cash-flow` endpoint is latest-only and would leak forward
    # information. The fundamentals_as_of() blank always sets dcf_value=0,
    # so dcf_up is 0 here. We keep the variable so the code path is stable
    # once a historical DCF feed (or a computed DCF from as-of-filtered
    # statements) is added.
    target = fund.get("target", 0) or 0
    intrinsic = fund.get("intrinsic_buffett", 0) or 0
    dcf = 0.0  # was fund.get("dcf_value", 0) — excluded in v8
    target_up = ((target - price) / price * 100) if target > 0 else 0.0
    intrinsic_up = ((intrinsic - price) / price * 100) if intrinsic > 0 else 0.0
    dcf_up = ((dcf - price) / price * 100) if dcf > 0 else 0.0
    # price_target is ALSO excluded (latest-only), so upside collapses to
    # intrinsic_up in practice. The classifier's safety gates pick up the
    # slack when intrinsic signal is weak.
    pooled_up = max(target_up, intrinsic_up, dcf_up)
    if pooled_up > 30:
        factors["upside"] = 1.0
    elif pooled_up > 15:
        factors["upside"] = 0.75
    elif pooled_up > 5:
        factors["upside"] = 0.5
    elif pooled_up > -10:
        factors["upside"] = 0.3
    else:
        factors["upside"] = 0.1

    # 3. Quality.
    if HAVE_V7:
        factors["quality"] = compute_quality_score(fund)
    else:
        pio = fund.get("piotroski", 5)
        az = fund.get("altman_z", 5.0)
        roe = fund.get("roe_avg", 0.0)
        roic = fund.get("roic_avg", 0.0)
        gm = fund.get("gross_margin", 0.0)
        q = ((pio / 9.0) * 0.40 + min(az / 20.0, 1.0) * 0.20
             + min(max(roe, 0) / 0.30, 1.0) * 0.15
             + min(max(roic, 0) / 0.20, 1.0) * 0.10
             + min(gm / 0.60, 1.0) * 0.15)
        factors["quality"] = min(q, 1.0)

    # 4. Proximity (52w position).
    yh = tech.get("year_high", 0) or 0
    yl = tech.get("year_low", 0) or 0
    prox_raw = (price - yl) / (yh - yl) if yh > yl > 0 else 0.5
    if prox_raw > 0.95:
        factors["proximity"] = 0.7
    elif prox_raw > 0.80:
        factors["proximity"] = 1.0
    elif prox_raw > 0.60:
        factors["proximity"] = 0.8
    elif prox_raw > 0.40:
        factors["proximity"] = 0.5
    elif prox_raw > 0.20:
        factors["proximity"] = 0.3
    else:
        factors["proximity"] = 0.15

    # 5. Catalyst — simplified proxy: recent EPS surprise momentum.
    eps_total = fund.get("eps_total", 0) or 0
    eps_beats = fund.get("eps_beats", 0) or 0
    beat_rate = eps_beats / eps_total if eps_total > 0 else 0.5
    surprises = fund.get("eps_surprises", []) or []
    recent_surprise = surprises[-1] if surprises else 0.0
    factors["catalyst"] = min(1.0,
                              beat_rate * 0.5
                              + (0.5 if recent_surprise > 0.05 else 0.3))

    # 6. Transcript — no historical sentiment feed; leave None so the
    #    weight gets redistributed.
    factors["transcript"] = None

    # 7. Analyst (grade-based).
    factors["analyst"] = fund.get("grade_score", 0.5)

    # 8. Institutional (legacy QoQ) — not reliably backtestable; leave None.
    factors["institutional"] = None

    # 9. Insider.
    factors["insider"] = fund.get("insider_score", 0.5)

    # 10. Earnings.
    factors["earnings"] = beat_rate * 0.6 + 0.4 * 0.5

    # 11. Sector momentum.
    if HAVE_V7:
        meta = SYMBOL_META.get(sym, {})
        sector = meta.get("sector", "")
        exchange = meta.get("exchange", "NASDAQ")
        factors["sector_momentum"] = compute_sector_momentum_bt(sector, exchange, as_of)
    else:
        factors["sector_momentum"] = 0.5

    # 12. Congressional.
    if HAVE_V7:
        factors["congressional"] = compute_congressional_score_bt(sym, as_of)
    else:
        factors["congressional"] = 0.5

    # 13. Institutional flow v2.
    if HAVE_V7:
        factors["institutional_flow"] = compute_inst_flow_v2_bt(sym, as_of)
    else:
        factors["institutional_flow"] = 0.5

    # Composite with weight redistribution for missing factors.
    # v8.1: Match live screener_v6 v7.3 math exactly — missing factors
    # contribute ZERO to composite (not 0.5), and weight is redistributed
    # proportionally to evaluated factors. Pre-penalty composite is kept as
    # ``composite_raw`` so the sweep can test different coverage_alpha values
    # post-hoc without rescanning.
    active = {}
    missing_w = 0.0
    evaluated = []
    missing = []
    for f, w in weights.items():
        if factors.get(f) is not None:
            active[f] = w
            evaluated.append(f)
        else:
            missing_w += w
            missing.append(f)
            # IMPORTANT: do NOT set factors[f] = 0.5 — that double-counts
            # the weight (once redistributed to active, once as 0.5 * base).
    if missing_w > 0 and active:
        total_a = sum(active.values())
        for f in list(active.keys()):
            active[f] += missing_w * (active[f] / total_a)
    elif not active:
        return None  # no evaluated factors → can't score

    # Sum only over evaluated factors (mirrors live screener line ~2130).
    composite_raw = sum(factors[f] * active[f] for f in evaluated)
    coverage_count = len(evaluated)
    coverage_pct = coverage_count / len(weights) if weights else 0.0

    # Null out missing factors so downstream code (classify_signal quality/
    # technical gates) mirrors live behavior — matches screener_v6 line ~2135.
    for f in missing:
        factors[f] = None

    # Auxiliary / diagnostic features (for later ML feature-importance).
    factors["bull_score_raw"] = tech["bull_score"]
    sma50 = tech.get("sma50", 0) or 0
    sma200 = tech.get("sma200", 0) or 0
    factors["momentum_20d"] = ((price - sma50) / sma50) if sma50 > 0 else 0
    factors["trend_strength"] = ((sma50 - sma200) / sma200) if sma200 > 0 else 0
    factors["rsi"] = tech.get("rsi", 50)
    factors["prox_raw"] = prox_raw
    factors["piotroski"] = fund.get("piotroski", 5)
    factors["altman_z"] = fund.get("altman_z", 5.0)

    return {
        "composite": composite_raw,           # alias for backward compat
        "composite_raw": composite_raw,        # v8.1: pre-penalty composite
        "coverage_count": coverage_count,      # v8.1: number of evaluated factors
        "coverage_pct": coverage_pct,          # v8.1: coverage_count / total
        "missing": missing,                    # v8.1: list of missing factor names
        "factors": factors,
    }


def classify_signal(composite: float,
                    factors: dict,
                    config: StrategyConfig) -> str:
    """
    Pure composite-band classifier with a couple of safety gates.

    The v7.1 scorer used bull_score / momentum / quality counts; v8's sweep
    is calibrating the composite bands directly, so the classifier is a
    simple step function.

    Safety gates:
      * A BUY is demoted to WATCH if quality factor < 0.40 (junk-stock
        escape hatch). This is not currently swept but can be turned off
        by setting the gate to 0.
      * A HOLD/WATCH is promoted to SELL if technical factor <= 0.20
        (collapsing trend override).
    """
    if composite >= config.strong_buy_threshold:
        base = SIG_STRONG_BUY
    elif composite >= config.buy_threshold:
        base = SIG_BUY
    elif composite <= config.sell_threshold:
        base = SIG_SELL
    elif composite >= config.watch_threshold:
        base = SIG_WATCH
    else:
        base = SIG_HOLD

    quality = factors.get("quality", 0.5)
    technical = factors.get("technical", 0.5)

    if base in BUY_SET and quality < 0.40:
        base = SIG_WATCH

    if base in (SIG_HOLD, SIG_WATCH) and technical <= 0.20:
        base = SIG_SELL

    return base


# ===========================================================================
# SECTION 5 — SCAN CACHE (expensive; amortised across sweep)
# ===========================================================================


def weekly_scan_dates(start: str, end: str, cadence_days: int = 7) -> List[str]:
    """Every ``cadence_days`` calendar days; real trading-day snap happens
    when we actually execute an order (price_on_or_before).
    """
    out = []
    cur = datetime.strptime(start, "%Y-%m-%d")
    stop = datetime.strptime(end, "%Y-%m-%d")
    # Anchor to Monday of the start week for reproducibility.
    while cur.weekday() != 0:
        cur += timedelta(days=1)
    while cur <= stop:
        out.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=cadence_days)
    return out


def build_scan_cache(universe: List[str],
                     scan_dates: List[str],
                     dp: HistoricalDataProvider,
                     weights: Optional[Dict[str, float]] = None,
                     out_path: Optional[str] = None,
                     resume: bool = True,
                     staging_dir: Optional[str] = None) -> Dict[str, List[dict]]:
    """
    Produce ``cache[date] = [ { symbol, price, composite, factors, signal_neutral } ]``.

    The ``signal_neutral`` field uses baseline StrategyConfig thresholds so the
    cache is usable as-is when no sweep is being run. During sweep/walk-forward
    each config reclassifies signals from ``composite`` + ``factors``, but
    doesn't need to re-compute any factor inputs.

    If ``out_path`` is given we stream the cache as JSONL (one dict per line,
    tagged with scan_date) so partial progress is resumable. Set
    ``resume=False`` to ignore any existing file.

    When ``staging_dir`` is provided (e.g. ``/tmp``), the JSONL is written to
    a local path under that directory first and copied to ``out_path`` at the
    end. This is critical when ``out_path`` points at a GCSFuse-mounted
    bucket: GCSFuse does not support native GCS appends, so each ``f.write``
    against an existing object triggers a full-object re-upload, and for
    large caches (100+ MB) the final sync silently fails on container exit.
    Staging locally turns 100k+ append operations into one sequential upload.
    Resumability is preserved by copying any existing ``out_path`` into
    staging on entry.
    """
    import shutil

    cache: Dict[str, List[dict]] = defaultdict(list)
    already_done: set = set()

    # Resolve the actual file we'll write to. If staging is enabled we write
    # locally and only copy to ``out_path`` at the end.
    write_path: Optional[str] = out_path
    final_path: Optional[str] = out_path
    if out_path and staging_dir:
        os.makedirs(staging_dir, exist_ok=True)
        write_path = os.path.join(staging_dir, os.path.basename(out_path))
        log.info("Staging scan cache at %s (final destination %s)",
                 write_path, final_path)
        # Seed the staging file with any existing remote progress so we can
        # resume without re-scanning already-done (date, symbol) pairs.
        if resume and os.path.exists(out_path):
            log.info("Copying existing cache %s -> staging for resume", out_path)
            shutil.copy2(out_path, write_path)

    if write_path and resume and os.path.exists(write_path):
        log.info("Resuming scan cache from %s", write_path)
        with open(write_path, "r") as f:
            for line in f:
                try:
                    r = json.loads(line)
                    cache[r["scan_date"]].append(r)
                    already_done.add((r["scan_date"], r["symbol"]))
                except (json.JSONDecodeError, KeyError):
                    continue
        log.info("  %d prior scan records loaded", len(already_done))

    fout = open(write_path, "a") if write_path else None
    baseline_cfg = StrategyConfig()

    try:
        for d_idx, scan_date in enumerate(scan_dates, 1):
            scanned = 0
            for sym in universe:
                if (scan_date, sym) in already_done:
                    continue
                row = dp.price_on_or_before(sym, scan_date)
                if not row or row["close"] <= 0:
                    continue
                price = row["close"]

                if HAVE_V7:
                    tech = compute_technicals_historical(sym, scan_date)
                else:
                    tech = None
                if not tech:
                    continue

                fund = dp.fundamentals_as_of(sym, scan_date)

                if fund.get("intrinsic_buffett", 0) > 0:
                    fund["margin_of_safety"] = (fund["intrinsic_buffett"] - price) / price
                elif fund.get("dcf_value", 0) > 0:
                    fund["margin_of_safety"] = (fund["dcf_value"] - price) / price
                else:
                    fund["margin_of_safety"] = 0.0

                if fund.get("_annual_oe_ps", 0) > 0 and price > 0:
                    fund["owner_earnings_yield"] = fund["_annual_oe_ps"] / price

                scored = compute_factors_v8(sym, scan_date, price, tech, fund, weights)
                if not scored:
                    continue

                # v8.1: neutral_signal uses the BASELINE coverage_alpha so it's
                # diagnostic only; each sweep config reapplies its own alpha at
                # classify time from composite_raw + coverage_pct.
                baseline_penalized = (scored["composite_raw"]
                                       * (scored["coverage_pct"]
                                          ** baseline_cfg.coverage_alpha))
                neutral_signal = classify_signal(baseline_penalized,
                                                 scored["factors"],
                                                 baseline_cfg)
                record = {
                    "scan_date": scan_date,
                    "symbol": sym,
                    "price": price,
                    # v8.1: persist raw composite + coverage so the sweep can
                    # test different coverage_alpha values without rescanning.
                    "composite_raw": scored["composite_raw"],
                    "coverage_count": scored["coverage_count"],
                    "coverage_pct": scored["coverage_pct"],
                    "missing": scored["missing"],
                    # "composite" alias retained for backward-compat consumers;
                    # defaults to RAW so callers that don't apply α see the
                    # unpenalized value (and are obviously wrong if they expect
                    # a live-matching number).
                    "composite": scored["composite_raw"],
                    "factors": {k: v for k, v in scored["factors"].items()
                                if not isinstance(v, list)},
                    "signal_neutral": neutral_signal,
                }
                cache[scan_date].append(record)
                scanned += 1
                if fout:
                    fout.write(json.dumps(record, default=float) + "\n")

            if fout:
                fout.flush()
                try:
                    os.fsync(fout.fileno())
                except OSError:
                    pass
            log.info("Scan %d/%d  %s  scored=%d",
                     d_idx, len(scan_dates), scan_date, scanned)
    finally:
        if fout:
            fout.close()
        # If we staged locally, push the final artefact to the destination
        # as a single big sequential write. This is the step that makes the
        # GCSFuse path reliable for 100+ MB caches.
        if final_path and write_path and final_path != write_path:
            try:
                os.makedirs(os.path.dirname(final_path) or ".", exist_ok=True)
                log.info("Copying staged cache %s -> %s (%.1f MB)",
                         write_path, final_path,
                         os.path.getsize(write_path) / (1024 * 1024))
                shutil.copy2(write_path, final_path)
                log.info("Final scan cache written to %s", final_path)
            except Exception as e:
                log.error("FAILED to copy staged cache to %s: %s "
                          "(staged file is still at %s)",
                          final_path, e, write_path)
                raise

    return cache


def load_scan_cache(jsonl_path: str) -> Dict[str, List[dict]]:
    cache: Dict[str, List[dict]] = defaultdict(list)
    with open(jsonl_path, "r") as f:
        for line in f:
            try:
                r = json.loads(line)
                cache[r["scan_date"]].append(r)
            except (json.JSONDecodeError, KeyError):
                continue
    log.info("Loaded scan cache: %d dates, %d records",
             len(cache), sum(len(v) for v in cache.values()))
    return cache


# ===========================================================================
# SECTION 6 — PORTFOLIO + SIMULATOR
# ===========================================================================


@dataclass
class Portfolio:
    initial_cash: float
    cash: float
    positions: Dict[str, Position] = field(default_factory=dict)
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[Tuple[str, float]] = field(default_factory=list)

    def mark_to_market(self, date_str: str, price_lookup: Dict[str, float]) -> float:
        value = self.cash
        for pos in self.positions.values():
            px = price_lookup.get(pos.symbol, pos.entry_price)
            value += pos.shares * px
        self.equity_curve.append((date_str, value))
        return value

    def peak_value_so_far(self) -> float:
        return max((v for _, v in self.equity_curve), default=self.initial_cash)


def _execute_entry(portfolio: Portfolio,
                   record: dict,
                   target_size_usd: float,
                   execution_date: str,
                   execution_price: float,
                   config: StrategyConfig) -> Optional[Position]:
    if target_size_usd <= 0 or execution_price <= 0:
        return None
    # Transaction cost: 1/2 of round-trip bps on entry.
    cost_factor = 1 + (config.transaction_cost_bps / 2) / 10_000
    effective_price = execution_price * cost_factor
    shares = target_size_usd / effective_price
    if shares <= 0:
        return None
    # Cash check must use effective_price (raw + half-entry transaction cost),
    # because that is the actual cash outlay. Using raw price here would let
    # a borderline position drive cash slightly negative.
    if shares * effective_price > portfolio.cash + 1e-6:
        shares = max(0.0, portfolio.cash / effective_price)
        if shares <= 0:
            return None
    # Deduct the full effective outlay: raw proceeds + transaction cost.
    # Computed in one line to keep accounting unambiguous.
    entry_cost_usd = shares * effective_price
    portfolio.cash -= entry_cost_usd
    pos = Position(
        symbol=record["symbol"],
        entry_date=execution_date,
        entry_price=execution_price,
        entry_composite=record.get("_composite_eff", record["composite"]),
        entry_signal=record.get("_entry_signal", record.get("signal_neutral", "")),
        shares=shares,
        entry_cost_usd=shares * effective_price,
    )
    portfolio.positions[pos.symbol] = pos
    return pos


def _execute_exit(portfolio: Portfolio,
                  pos: Position,
                  exit_date: str,
                  exit_price: float,
                  exit_reason: str,
                  exit_composite: Optional[float],
                  exit_signal: Optional[str],
                  config: StrategyConfig) -> Trade:
    # Transaction cost: 1/2 of round-trip on exit.
    cost_factor = 1 - (config.transaction_cost_bps / 2) / 10_000
    effective_price = exit_price * cost_factor
    proceeds = pos.shares * effective_price
    portfolio.cash += proceeds
    gross_pnl_usd = pos.shares * (exit_price - pos.entry_price)
    net_pnl_usd = proceeds - pos.entry_cost_usd
    # pnl_pct is net-of-costs relative to the actual cash outlay at entry
    # (entry_cost_usd already includes the half-on-entry transaction cost).
    # This keeps Trade.pnl_usd and Trade.pnl_pct consistent: both are net.
    pnl_pct = (net_pnl_usd / pos.entry_cost_usd) if pos.entry_cost_usd else 0.0
    days_held = (datetime.strptime(exit_date, "%Y-%m-%d")
                 - datetime.strptime(pos.entry_date, "%Y-%m-%d")).days
    trade = Trade(
        symbol=pos.symbol,
        entry_date=pos.entry_date,
        exit_date=exit_date,
        entry_price=pos.entry_price,
        exit_price=exit_price,
        shares=pos.shares,
        pnl_pct=pnl_pct,
        pnl_usd=net_pnl_usd,
        days_held=days_held,
        exit_reason=exit_reason,
        entry_composite=pos.entry_composite,
        exit_composite=exit_composite,
        entry_signal=pos.entry_signal,
        exit_signal=exit_signal,
    )
    portfolio.trades.append(trade)
    del portfolio.positions[pos.symbol]
    return trade


def _slippage_price(sym: str,
                    scan_date: str,
                    scan_price: float,
                    model: str) -> Tuple[str, float]:
    """Return (execution_date, execution_price) given slippage model."""
    if model == SLIP_CLOSE or not HAVE_V7:
        return scan_date, scan_price
    nxt = HistoricalDataProvider.next_trading_price(sym, scan_date)
    if not nxt:
        return scan_date, scan_price
    if model == SLIP_NEXT_OPEN:
        # If 'open' missing, fall back to close.
        px = nxt.get("open") or nxt.get("close") or scan_price
        return nxt["date"], float(px)
    if model == SLIP_NEXT_VWAP:
        # Simple typical-price VWAP approx since FMP chart has OHLCV only.
        o = float(nxt.get("open") or scan_price)
        h = float(nxt.get("high") or scan_price)
        l = float(nxt.get("low") or scan_price)
        c = float(nxt.get("close") or scan_price)
        px = (h + l + c + o) / 4
        return nxt["date"], float(px)
    return scan_date, scan_price


def _compute_position_sizes(candidates: List[dict],
                            slots_available: int,
                            portfolio_value: float,
                            target_positions: int,
                            weighting: str) -> List[float]:
    """Return list of target dollar sizes, same order as ``candidates``.

    Per spec §3.1: ``size = portfolio_value / target_portfolio_size``
    — the denominator is the TARGET size, not the slots we happen to
    be filling today. If only 3 candidates pass filters for a 5-slot
    portfolio, we size each new buy to 20% and leave 40% in cash rather
    than concentrating 33% each.
    """
    if not candidates or slots_available <= 0:
        return []
    k = min(slots_available, len(candidates))
    chosen = candidates[:k]
    denom = max(target_positions, 1)
    if weighting == "equal":
        size = portfolio_value / denom
        return [size] * k
    # Composite-weighted schemes: scale by composite ** exponent within the
    # share of portfolio allocated to new entries (= k / target_positions).
    exp = 1.0 if weighting == "composite-linear" else 2.0
    raw = [max(c["composite"], 0) ** exp for c in chosen]
    total = sum(raw)
    if total <= 0:
        size = portfolio_value / denom
        return [size] * k
    budget = portfolio_value * (k / denom)
    return [budget * (w / total) for w in raw]


def simulate(config: StrategyConfig,
             scan_cache: Dict[str, List[dict]],
             start_date: str,
             end_date: str,
             initial_cash: float = 100_000.0,
             regime_by_date: Optional[Dict[str, str]] = None
             ) -> SimulationResult:
    """
    Event-driven forward simulation.

    Critical ordering inside the loop (every scan/rebalance date):
      1. Mark-to-market at prior day's close (done during idle days).
      2. Evaluate exits FIRST — this frees up slots before we
         compare entries.
      3. Rank and enter new BUYs.

    Between rebalance dates we walk forward trading-day-by-trading-day,
    marking equity and checking intraday stop/take/time stops using the
    CHART high/low data (so a -12% dip that recovers still triggers a SL).
    """
    regime_by_date = regime_by_date or {}
    portfolio = Portfolio(initial_cash=initial_cash, cash=initial_cash)

    scan_dates = sorted(d for d in scan_cache.keys()
                        if start_date <= d <= end_date)
    if not scan_dates:
        raise ValueError(f"No scan dates in cache between {start_date} and {end_date}")

    # Build a date -> records map, and each record gets classified by this config.
    # v8.1: Compute per-config effective composite from composite_raw + coverage_pct
    # so each sweep config can test a different coverage_alpha without mutating
    # the shared cache. Backward-compat fallback if cache is pre-v8.1 (treats
    # composite field as raw and coverage_pct as 1.0 → no penalty applied).
    for d in scan_dates:
        for r in scan_cache[d]:
            comp_raw = r.get("composite_raw", r.get("composite", 0.0))
            cov_pct = r.get("coverage_pct", 1.0)
            comp_eff = comp_raw * (cov_pct ** config.coverage_alpha)
            r["_composite_eff"] = comp_eff
            r["_signal"] = classify_signal(comp_eff, r["factors"], config)

    # Fast symbol->record lookup per date (symbol held may not be in scan).
    per_date_syms: Dict[str, Dict[str, dict]] = {}
    for d in scan_dates:
        per_date_syms[d] = {r["symbol"]: r for r in scan_cache[d]}

    # Walk through scan dates, then inside each week iterate trading days.
    for w_idx, scan_date in enumerate(scan_dates):
        next_scan = scan_dates[w_idx + 1] if w_idx + 1 < len(scan_dates) else end_date

        # ---- 1) Intraday exits BEFORE this week's rebalance decisions ----
        _apply_intraday_exits(
            portfolio=portfolio,
            start_date=scan_date if w_idx == 0 else scan_dates[w_idx - 1],
            end_date=scan_date,
            config=config,
        )

        # ---- 2) Signal-driven exits at the scan close ----
        current_syms = list(portfolio.positions.keys())
        records_today = per_date_syms[scan_date]
        for sym in current_syms:
            r = records_today.get(sym)
            if r is None:
                # Dropped out of the universe — close at last known price.
                # IMPORTANT: the exit date must match the price date, not
                # today's scan_date. If the last trade for this symbol was
                # weeks ago (delisted / halted), stamping the exit as today
                # but using a stale price creates a phantom holding period
                # with no MTM support.
                last_row = HistoricalDataProvider.price_on_or_before(sym, scan_date)
                if last_row:
                    px = last_row["close"]
                    exit_d = last_row["date"]
                else:
                    px = portfolio.positions[sym].entry_price
                    exit_d = scan_date
                _execute_exit(portfolio, portfolio.positions[sym],
                              exit_d, px, EXIT_UNIVERSE, None, None, config)
                continue
            if r["_signal"] == SIG_SELL:
                exec_date, exec_px = _slippage_price(sym, scan_date,
                                                     r["price"], config.slippage_model)
                _execute_exit(portfolio, portfolio.positions[sym],
                              exec_date, exec_px, EXIT_SIGNAL,
                              r["_composite_eff"], r["_signal"], config)

        # ---- 3) Entries ----
        # Free slots after exits.
        slots = config.target_positions - len(portfolio.positions)
        if slots > 0:
            floor = config.floor_for_date(regime_by_date.get(scan_date))
            candidates = [r for r in scan_cache[scan_date]
                          if r["_signal"] in config.entry_signals()
                          and r["_composite_eff"] >= floor
                          and r["symbol"] not in portfolio.positions]
            candidates.sort(key=lambda r: r["_composite_eff"], reverse=True)

            # Size calculation uses current portfolio value (MTM first).
            mtm_lookup = {s: r["price"] for s, r in records_today.items()}
            mtm_lookup.update({sym: records_today.get(sym, {}).get("price",
                              portfolio.positions[sym].entry_price)
                              for sym in portfolio.positions})
            current_value = portfolio.cash + sum(
                pos.shares * mtm_lookup.get(pos.symbol, pos.entry_price)
                for pos in portfolio.positions.values()
            )
            sizes = _compute_position_sizes(candidates, slots, current_value,
                                            config.target_positions,
                                            config.weighting)
            for rec, size in zip(candidates[:slots], sizes):
                rec["_entry_signal"] = rec["_signal"]
                exec_date, exec_px = _slippage_price(rec["symbol"], scan_date,
                                                     rec["price"], config.slippage_model)
                _execute_entry(portfolio, rec, size, exec_date, exec_px, config)

        # ---- 4) Mark-to-market daily until next scan ----
        _walk_forward_mtm(portfolio,
                          from_date=scan_date,
                          to_date=next_scan,
                          config=config,
                          include_end=(w_idx == len(scan_dates) - 1))

    # End-of-backtest cleanup: close anything still open at last price.
    final_date = portfolio.equity_curve[-1][0] if portfolio.equity_curve else end_date
    for sym in list(portfolio.positions.keys()):
        last_row = HistoricalDataProvider.price_on_or_before(sym, final_date)
        px = last_row["close"] if last_row else portfolio.positions[sym].entry_price
        _execute_exit(portfolio, portfolio.positions[sym],
                      final_date, px, EXIT_END, None, None, config)

    metrics = compute_metrics(portfolio, start_date, end_date)
    return SimulationResult(config=config,
                            equity_curve=portfolio.equity_curve,
                            trades=portfolio.trades,
                            metrics=metrics)


def _apply_intraday_exits(portfolio: Portfolio,
                          start_date: str,
                          end_date: str,
                          config: StrategyConfig) -> None:
    """
    Walk the chart between ``start_date`` (exclusive) and ``end_date``
    (inclusive) for every open position. Apply stop-loss / take-profit /
    time-stop in calendar order. Uses daily high/low so a SL triggered
    intraday doesn't get missed by close-only data.
    """
    if not HAVE_V7:
        return
    from backtest_full import _CHART_CACHE

    for sym in list(portfolio.positions.keys()):
        pos = portfolio.positions.get(sym)
        if not pos:
            continue
        chart = _CHART_CACHE.get(sym, [])
        if not chart:
            continue
        entry_dt = datetime.strptime(pos.entry_date, "%Y-%m-%d")
        for row in chart:
            d = row["date"]
            # Disjoint half-open interval (start_date, end_date]: we only
            # evaluate bars STRICTLY AFTER start_date. When callers chain
            # windows back-to-back they set start_date = previous end_date
            # so no bar is evaluated twice.
            if d <= start_date or d > end_date:
                continue
            days_held = (datetime.strptime(d, "%Y-%m-%d") - entry_dt).days
            open_ = row.get("open", row["close"])
            high = row.get("high", row["close"])
            low = row.get("low", row["close"])
            close = row["close"]

            sl_trigger = pos.entry_price * (1 + config.stop_loss)
            tp_trigger = pos.entry_price * (1 + config.take_profit)

            # Realistic gap fills: if the stock gaps through the trigger
            # at the open, the fill price is the OPEN, not the trigger.
            # Otherwise (trigger hit intraday after a normal open), fill
            # is at the trigger. This removes the optimistic "always fill
            # at trigger price" bias the naive code had.
            if low <= sl_trigger:
                fill = min(open_, sl_trigger)
                _execute_exit(portfolio, pos, d, fill,
                              EXIT_STOP_LOSS, None, None, config)
                break
            if high >= tp_trigger:
                fill = max(open_, tp_trigger)
                _execute_exit(portfolio, pos, d, fill,
                              EXIT_TAKE_PROFIT, None, None, config)
                break
            if days_held >= config.time_stop_days:
                _execute_exit(portfolio, pos, d, close,
                              EXIT_TIME_STOP, None, None, config)
                break


def _walk_forward_mtm(portfolio: Portfolio,
                      from_date: str,
                      to_date: str,
                      config: StrategyConfig,
                      include_end: bool) -> None:
    """Append daily equity values between from_date (inclusive) and to_date
    (exclusive unless ``include_end``). Uses the first held symbol's chart
    as the trading-day calendar; also applies intraday exits as we go.
    """
    if not HAVE_V7:
        portfolio.mark_to_market(from_date, {})
        return
    from backtest_full import _CHART_CACHE

    # Pick a liquid reference symbol for the trading-day calendar. Prefer
    # any currently-held position's chart; fall back to the first cached chart.
    ref_chart: Optional[List[dict]] = None
    for pos in portfolio.positions.values():
        if pos.symbol in _CHART_CACHE:
            ref_chart = _CHART_CACHE[pos.symbol]
            break
    if ref_chart is None:
        # Grab any chart.
        for sym, chart in _CHART_CACHE.items():
            if chart:
                ref_chart = chart
                break
    if ref_chart is None:
        return

    for row in ref_chart:
        d = row["date"]
        if d < from_date:
            continue
        if (not include_end and d >= to_date) or d > to_date:
            break
        # NOTE: We intentionally do NOT run _apply_intraday_exits here.
        # The simulate() loop is the single source of truth for intraday
        # exits: at the start of every week it walks (prev_scan, this_scan]
        # for every open position. Running the check again per-day here
        # would double-apply SL/TP to the same bars. The per-week batch is
        # sufficient because SL/TP/time-stop triggers are evaluated by
        # comparing entry_price to every bar's high/low, regardless of
        # when in the week the walk happens.
        # Mark-to-market using this day's close.
        lookup: Dict[str, float] = {}
        for sym in portfolio.positions:
            chart = _CHART_CACHE.get(sym, [])
            # Find close for d or most recent <=d.
            px = None
            for r in chart:
                if r["date"] <= d:
                    px = r["close"]
                elif px is not None:
                    break
            if px is not None:
                lookup[sym] = px
        portfolio.mark_to_market(d, lookup)


def _prev_trading_day(chart: List[dict], d: str) -> str:
    prev = d
    for row in chart:
        if row["date"] < d:
            prev = row["date"]
        else:
            break
    return prev


# ===========================================================================
# SECTION 7 — METRICS
# ===========================================================================


def compute_metrics(portfolio: Portfolio,
                    start_date: str,
                    end_date: str) -> Dict[str, float]:
    if not portfolio.equity_curve:
        return {}
    dates = [d for d, _ in portfolio.equity_curve]
    vals = [v for _, v in portfolio.equity_curve]
    initial = portfolio.initial_cash
    final = vals[-1]

    # CAGR.
    try:
        days = (datetime.strptime(dates[-1], "%Y-%m-%d")
                - datetime.strptime(dates[0], "%Y-%m-%d")).days
    except ValueError:
        days = 1
    years = max(days / 365.25, 1 / 365.25)
    total_return = final / initial - 1
    cagr = (final / initial) ** (1 / years) - 1 if initial > 0 and final > 0 else -1.0

    # Daily returns for Sharpe.
    rets = []
    for i in range(1, len(vals)):
        if vals[i - 1] > 0:
            rets.append(vals[i] / vals[i - 1] - 1)
    if rets:
        mean_r = sum(rets) / len(rets)
        std_r = statistics.pstdev(rets) if len(rets) > 1 else 0.0
        sharpe = (mean_r / std_r) * math.sqrt(252) if std_r > 0 else 0.0
    else:
        mean_r = std_r = sharpe = 0.0

    # Max drawdown.
    peak = initial
    max_dd = 0.0
    for v in vals:
        if v > peak:
            peak = v
        dd = (v - peak) / peak if peak > 0 else 0.0
        if dd < max_dd:
            max_dd = dd

    # Trade stats. Win rate uses NET P&L (after transaction costs) rather
    # than gross price change, so a +0.05% round-trip that eats a 20bp cost
    # isn't misreported as a winner.
    trades = portfolio.trades
    n_trades = len(trades)
    wins = [t for t in trades if t.pnl_usd > 0]
    win_rate = len(wins) / n_trades if n_trades else 0.0
    avg_hold = sum(t.days_held for t in trades) / n_trades if n_trades else 0.0
    exit_breakdown = defaultdict(int)
    for t in trades:
        exit_breakdown[t.exit_reason] += 1
    exit_pct = {f"exit_pct_{k}": v / n_trades for k, v in exit_breakdown.items()} if n_trades else {}

    # Monthly return distribution.
    monthly_rets = _monthly_returns(dates, vals)
    if monthly_rets:
        mu = sum(monthly_rets) / len(monthly_rets)
        mstd = statistics.pstdev(monthly_rets) if len(monthly_rets) > 1 else 0.0
        if mstd > 0 and len(monthly_rets) > 2:
            skew_num = sum(((r - mu) / mstd) ** 3 for r in monthly_rets) / len(monthly_rets)
            kurt_num = (sum(((r - mu) / mstd) ** 4 for r in monthly_rets) / len(monthly_rets)) - 3
        else:
            skew_num = kurt_num = 0.0
    else:
        mu = mstd = skew_num = kurt_num = 0.0

    # Calmar needs to handle three pathological cases sanely:
    #   (a) cratered run (final_value <= 0 or cagr <= -0.99): set calmar to a
    #       large negative sentinel so the config ranks LAST, not near zero.
    #   (b) flat-line run (max_dd == 0) with positive CAGR: returning
    #       math.inf poisons ranking; use a large positive finite value.
    #   (c) flat-line run with non-positive CAGR: 0.0 is fine.
    cratered = (final <= 0.01 * initial) or (cagr <= -0.99)
    if cratered:
        calmar = -999.0
    elif max_dd < 0:
        calmar = cagr / abs(max_dd)
    elif cagr > 0:
        calmar = 999.0
    else:
        calmar = 0.0

    metrics = {
        "total_return": total_return,
        "cagr": cagr,
        "sharpe": sharpe,
        "max_drawdown": max_dd,
        "calmar": calmar,
        "cratered": cratered,
        "n_trades": n_trades,
        "win_rate": win_rate,
        "avg_hold_days": avg_hold,
        "mean_daily_return": mean_r,
        "std_daily_return": std_r,
        "monthly_mean": mu,
        "monthly_std": mstd,
        "monthly_skew": skew_num,
        "monthly_kurtosis": kurt_num,
    }
    metrics.update(exit_pct)
    return metrics


def _monthly_returns(dates: List[str], vals: List[float]) -> List[float]:
    if not dates:
        return []
    bucket_end: Dict[str, Tuple[str, float]] = {}
    for d, v in zip(dates, vals):
        ym = d[:7]
        prev = bucket_end.get(ym)
        if prev is None or d >= prev[0]:
            bucket_end[ym] = (d, v)
    ordered = sorted(bucket_end.keys())
    rets = []
    for i in range(1, len(ordered)):
        prev_v = bucket_end[ordered[i - 1]][1]
        cur_v = bucket_end[ordered[i]][1]
        if prev_v > 0:
            rets.append(cur_v / prev_v - 1)
    return rets


def benchmark_spy_metrics(start: str, end: str,
                          initial_cash: float = 100_000.0) -> Dict[str, float]:
    """Buy-and-hold SPY over the same period, returned as a metrics dict."""
    if not HAVE_V7:
        return {}
    data = fmp("historical-price-eod/full", {"symbol": "SPY", "from": start, "to": end})
    if not data:
        return {}
    rows = sorted([{"date": d.get("date"), "close": float(d.get("close", 0))}
                   for d in data if d.get("close")], key=lambda r: r["date"])
    if len(rows) < 2:
        return {}
    initial_px = rows[0]["close"]
    shares = initial_cash / initial_px
    equity = [(r["date"], shares * r["close"]) for r in rows]
    pf = Portfolio(initial_cash=initial_cash, cash=0.0)
    pf.equity_curve = equity
    return compute_metrics(pf, start, end)


def alpha_vs_spy(sim: SimulationResult, start: str, end: str) -> float:
    spy = benchmark_spy_metrics(start, end)
    return sim.metrics.get("cagr", 0) - spy.get("cagr", 0)


# ===========================================================================
# SECTION 8 — SWEEP (~500 configs stratified around baseline)
# ===========================================================================

# Full parameter space per spec §3.3.
SWEEP_SPACE = {
    # v8.2: Thresholds calibrated to the ACTUAL composite_raw distribution
    # observed in the first real v8.1 scan (638K records, 2022–2026,
    # sp500_nasdaq, $500M cap). Empirical percentiles:
    #   p50=0.549  p75=0.639  p90=0.701  p99=0.790
    # After coverage penalty (α≈0.7, cov≈0.8) scores shift ~10-15pp lower.
    # Old v7.x grid centered at 0.70-0.90 produced ZERO trades across 800
    # configs (logs showed all CAGR=0). Grid now centered at 0.35-0.70.
    # α=0.0 control is kept in coverage_alpha so "penalty=off" remains testable.
    "composite_floor":      [0.35, 0.40, 0.45, 0.50, 0.55, 0.60],
    "stop_loss":            [-0.08, -0.10, -0.12, -0.15, -0.20],
    "take_profit":          [0.15, 0.20, 0.25, 0.30],
    "time_stop_days":       [45, 60, 90, 120],
    "target_positions":     [3, 5, 7, 10],
    "strong_buy_threshold": [0.50, 0.55, 0.60, 0.65, 0.70, 0.75],
    "buy_threshold":        [0.35, 0.40, 0.45, 0.50, 0.55, 0.60],
    "sell_threshold":       [0.15, 0.20, 0.25, 0.30, 0.35, 0.40],
    "weighting":            ["equal", "composite-linear", "composite-squared"],
    "coverage_alpha":       [0.0, 0.5, 0.7, 1.0, 1.5],
}


def generate_sweep_configs(baseline: StrategyConfig,
                           n_configs: int = 500,
                           seed: int = 42,
                           space: Optional[Dict[str, List[Any]]] = None
                           ) -> List[StrategyConfig]:
    """
    Stratified sample of ``n_configs`` strategy configs.

    We sample from ``SWEEP_SPACE`` with soft bias toward the baseline:
    for each parameter we choose the baseline value with probability
    0.35, one step away with 0.35, and farther values uniformly.
    """
    space = space or SWEEP_SPACE
    rng = random.Random(seed)
    configs: List[StrategyConfig] = []
    seen: set = set()

    # Always include the baseline.
    configs.append(replace(baseline, config_id="baseline"))
    seen.add(_config_hash(baseline))

    # Add the anchor corners: extreme but plausible.
    corners = [
        replace(baseline, composite_floor=0.35, target_positions=10,
                config_id="corner_broad"),
        replace(baseline, composite_floor=0.60, target_positions=3,
                config_id="corner_concentrated"),
        replace(baseline, take_profit=0.15, stop_loss=-0.08,
                time_stop_days=45, config_id="corner_tight"),
        replace(baseline, take_profit=0.30, stop_loss=-0.20,
                time_stop_days=120, config_id="corner_loose"),
    ]
    for c in corners:
        h = _config_hash(c)
        if h not in seen:
            configs.append(c)
            seen.add(h)

    baseline_idx = {k: space[k].index(getattr(baseline, k))
                    if getattr(baseline, k) in space[k] else len(space[k]) // 2
                    for k in space}

    attempts = 0
    while len(configs) < n_configs and attempts < n_configs * 10:
        attempts += 1
        kwargs = {}
        for k, values in space.items():
            anchor = baseline_idx[k]
            u = rng.random()
            if u < 0.35:
                idx = anchor
            elif u < 0.70:
                idx = max(0, min(len(values) - 1, anchor + rng.choice([-1, 1])))
            else:
                idx = rng.randrange(len(values))
            kwargs[k] = values[idx]
        cfg = replace(baseline, config_id=f"sweep_{len(configs):04d}", **kwargs)
        h = _config_hash(cfg)
        if h in seen:
            continue
        seen.add(h)
        configs.append(cfg)
    log.info("Generated %d sweep configs (target=%d, attempts=%d)",
             len(configs), n_configs, attempts)
    return configs


def _config_hash(cfg: StrategyConfig) -> str:
    payload = {k: getattr(cfg, k)
               for k in SWEEP_SPACE.keys()}
    return json.dumps(payload, sort_keys=True, default=str)


def run_sweep(configs: List[StrategyConfig],
              scan_cache: Dict[str, List[dict]],
              start_date: str,
              end_date: str,
              initial_cash: float = 100_000.0,
              regime_by_date: Optional[Dict[str, str]] = None,
              progress_every: int = 25
              ) -> List[SimulationResult]:
    results: List[SimulationResult] = []
    for i, cfg in enumerate(configs, 1):
        try:
            res = simulate(cfg, scan_cache, start_date, end_date,
                           initial_cash=initial_cash,
                           regime_by_date=regime_by_date)
        except Exception as e:
            log.warning("Config %s failed: %s", cfg.config_id, e)
            continue
        results.append(res)
        if i % progress_every == 0 or i == len(configs):
            log.info("Sweep %d/%d  %-20s  CAGR=%.2f%%  Sharpe=%.2f  MaxDD=%.2f%%",
                     i, len(configs), cfg.config_id,
                     100 * res.metrics.get("cagr", 0),
                     res.metrics.get("sharpe", 0),
                     100 * res.metrics.get("max_drawdown", 0))
    return results


def rank_results(results: List[SimulationResult],
                 sharpe_floor: float = 1.0) -> List[SimulationResult]:
    """Rank by CAGR/|MaxDD| with a Sharpe floor, per spec §3.4.

    Explicitly drops cratered runs (configs whose final_value collapsed
    below 1% of initial_cash) so they never bubble to the top on a lucky
    sharpe signal. Also drops infinities.
    """
    def ok(r: SimulationResult) -> bool:
        m = r.metrics
        if m.get("cratered"):
            return False
        if m.get("sharpe", 0) < sharpe_floor:
            return False
        c = m.get("calmar", 0)
        if c in (float("inf"), float("-inf")) or c is None:
            return False
        return True
    filtered = [r for r in results if ok(r)]
    filtered.sort(key=lambda r: r.metrics.get("calmar", 0), reverse=True)
    return filtered


# ===========================================================================
# SECTION 9 — WALK-FORWARD VALIDATION
# ===========================================================================


def walk_forward(train_results: List[SimulationResult],
                 scan_cache: Dict[str, List[dict]],
                 oos_start: str,
                 oos_end: str,
                 top_n: int = 10,
                 spy_cagr_margin: float = 0.05,
                 initial_cash: float = 100_000.0,
                 regime_by_date: Optional[Dict[str, str]] = None
                 ) -> Dict[str, Any]:
    """
    Take the top ``top_n`` training configs by Calmar, re-run them on the
    OOS window, and pick the first that also beats SPY's OOS CAGR by
    ``spy_cagr_margin`` with DD comparable to training (within 1.5x).

    Returns a dict with:
      winner: SimulationResult | None
      evaluated: [SimulationResult, ...]  # OOS simulations of each candidate
      rejected: [ {config_id, reason}, ... ]
      spy_oos: dict  # SPY metrics over OOS window
    """
    ranked = rank_results(train_results, sharpe_floor=1.0)[:top_n]
    spy_oos = benchmark_spy_metrics(oos_start, oos_end, initial_cash)
    spy_cagr = spy_oos.get("cagr", 0)
    rejected = []
    evaluated: List[SimulationResult] = []
    winner: Optional[SimulationResult] = None

    for cand in ranked:
        oos_res = simulate(cand.config, scan_cache, oos_start, oos_end,
                           initial_cash=initial_cash,
                           regime_by_date=regime_by_date)
        evaluated.append(oos_res)
        oos_cagr = oos_res.metrics.get("cagr", 0)
        oos_dd = oos_res.metrics.get("max_drawdown", 0)
        train_dd = cand.metrics.get("max_drawdown", -0.01)

        if oos_cagr < spy_cagr + spy_cagr_margin:
            rejected.append({
                "config_id": cand.config.config_id,
                "train_cagr": cand.metrics.get("cagr", 0),
                "oos_cagr": oos_cagr,
                "spy_cagr": spy_cagr,
                "reason": f"OOS CAGR {oos_cagr:.3f} didn't beat SPY {spy_cagr:.3f} + margin {spy_cagr_margin}",
            })
            continue
        if abs(oos_dd) > 1.5 * abs(train_dd) and abs(oos_dd) > 0.25:
            rejected.append({
                "config_id": cand.config.config_id,
                "train_dd": train_dd,
                "oos_dd": oos_dd,
                "reason": "OOS drawdown > 1.5x training drawdown (and > 25%)",
            })
            continue
        winner = oos_res
        break

    return {
        "winner": winner,
        "evaluated": evaluated,
        "rejected": rejected,
        "spy_oos": spy_oos,
        "ranked_train": ranked,
    }


def subperiod_robustness(winner_config: StrategyConfig,
                         scan_cache: Dict[str, List[dict]],
                         periods: List[Tuple[str, str, str]],
                         initial_cash: float = 100_000.0
                         ) -> List[Dict[str, Any]]:
    """
    Run the winner over each (label, start, end) period.

    Spec §8 requires no negative sub-period within 2022-H1, 2022-H2,
    2023, 2024 (on OOS data).
    """
    out = []
    for label, s, e in periods:
        try:
            res = simulate(winner_config, scan_cache, s, e, initial_cash=initial_cash)
            out.append({
                "period": label, "start": s, "end": e,
                "cagr": res.metrics.get("cagr", 0),
                "sharpe": res.metrics.get("sharpe", 0),
                "max_drawdown": res.metrics.get("max_drawdown", 0),
                "total_return": res.metrics.get("total_return", 0),
                "n_trades": res.metrics.get("n_trades", 0),
                "ok_no_negative_year": res.metrics.get("total_return", 0) >= 0,
            })
        except Exception as e:
            out.append({"period": label, "error": str(e)})
    return out


# ===========================================================================
# SECTION 10 — OUTPUT + REPORT
# ===========================================================================


def write_results_csv(results: List[SimulationResult], path: str) -> None:
    if not results:
        return
    rows = [r.metrics_row() for r in results]
    # Union of all keys (configs might have different exit_pct_* keys).
    keys = set()
    for row in rows:
        keys.update(row.keys())
    keys = sorted(keys)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in keys})
    log.info("Wrote %d sweep rows → %s", len(rows), path)


def write_trades_csv(result: SimulationResult, path: str) -> None:
    fields = ["symbol", "entry_date", "exit_date", "entry_price", "exit_price",
              "shares", "pnl_pct", "pnl_usd", "days_held", "exit_reason",
              "entry_composite", "exit_composite", "entry_signal", "exit_signal"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for t in result.trades:
            w.writerow(t.to_csv_row())
    log.info("Wrote %d trades → %s", len(result.trades), path)


def write_equity_curves_csv(sims: Dict[str, SimulationResult], path: str) -> None:
    """Merge equity curves from multiple sims into one wide CSV."""
    all_dates = sorted({d for sim in sims.values() for d, _ in sim.equity_curve})
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date"] + list(sims.keys()))
        lookups = {name: dict(sim.equity_curve) for name, sim in sims.items()}
        for d in all_dates:
            row = [d]
            for name in sims:
                row.append(lookups[name].get(d, ""))
            w.writerow(row)
    log.info("Wrote equity curve matrix (%d dates × %d sims) → %s",
             len(all_dates), len(sims), path)


def write_winner_json(winner: Optional[SimulationResult], path: str) -> None:
    if winner is None:
        payload = {"winner": None, "reason": "All candidates rejected on OOS"}
    else:
        payload = {
            "config": winner.config.as_flat_dict(),
            "metrics": winner.metrics,
            "equity_curve_tail": winner.equity_curve[-10:],
            "n_trades": len(winner.trades),
        }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2, default=float)
    log.info("Wrote winner JSON → %s", path)


def generate_report_md(train_results: List[SimulationResult],
                       oos_results: List[SimulationResult],
                       winner: Optional[SimulationResult],
                       rejected: List[Dict[str, Any]],
                       spy_oos: Dict[str, float],
                       subperiod: List[Dict[str, Any]],
                       path: str,
                       context: Dict[str, Any]) -> None:
    lines: List[str] = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines.append(f"# Stock Screener v8 — Backtest Report")
    lines.append("")
    lines.append(f"*Generated: {now}*")
    lines.append("")
    lines.append(f"**Date range:** {context.get('train_from')} → {context.get('oos_to')}  ")
    lines.append(f"**Training window:** {context.get('train_from')} → {context.get('train_to')}  ")
    lines.append(f"**Out-of-sample window:** {context.get('oos_from')} → {context.get('oos_to')}  ")
    lines.append(f"**Universe:** {context.get('universe', 'sp500 + nasdaq')} "
                 f"({context.get('universe_size', 'n/a')} symbols)  ")
    lines.append(f"**Scan cadence:** weekly")
    lines.append("")

    # --- Section 1: what changed vs v7 -------------------------------------
    lines.append("## 1. What changed from v7.1")
    lines.append("")
    lines.append("v7.1's backtest was a monthly-rebalance proxy: it ranked stocks "
                 "by composite every 30 days and measured the next month's return. "
                 "It did not honor the BUY/SELL signals, didn't rotate a real "
                 "portfolio, and didn't apply any exit rule. v8 is an event-driven "
                 "forward-walking simulation: every week we re-score the universe, "
                 "close positions that hit stop/take/time/signal exits, and enter "
                 "the top composite candidates filtered by signal.")
    lines.append("")
    lines.append("Key correctness fixes carried into v8 scoring:")
    lines.append("")
    lines.append("- Annual financials filtered by `fillingDate < scan_date` "
                 "(FMP's `fillingDate` field, not `date`). v7.1 used the most "
                 "recent filings irrespective of whether they were yet public.")
    lines.append("- Analyst grades filtered by `date < scan_date`.")
    lines.append("- 13F positions-summary with 45-day lag and filing-date filter.")
    lines.append("- Congressional trades filtered by `disclosureDate < scan_date`.")
    lines.append("")

    # --- Section 2: sweep summary ------------------------------------------
    lines.append("## 2. Sweep summary (training window)")
    lines.append("")
    ranked = rank_results(train_results, sharpe_floor=1.0)
    lines.append(f"- Configs evaluated: **{len(train_results)}**")
    lines.append(f"- Configs passing Sharpe > 1.0 filter: **{len(ranked)}**")
    if ranked:
        top = ranked[0]
        lines.append(f"- Best training Calmar: **{top.metrics['calmar']:.2f}** "
                     f"(config `{top.config.config_id}`)")
    lines.append("")
    lines.append("Top 10 training configs by Calmar (CAGR / |MaxDD|):")
    lines.append("")
    lines.append("| Rank | Config | CAGR | Sharpe | MaxDD | Win % | Trades | Avg hold |")
    lines.append("|------|--------|------|--------|-------|-------|--------|----------|")
    for i, r in enumerate(ranked[:10], 1):
        m = r.metrics
        lines.append(f"| {i} | `{r.config.config_id}` | "
                     f"{100*m.get('cagr',0):.1f}% | {m.get('sharpe',0):.2f} | "
                     f"{100*m.get('max_drawdown',0):.1f}% | "
                     f"{100*m.get('win_rate',0):.0f}% | "
                     f"{int(m.get('n_trades',0))} | "
                     f"{m.get('avg_hold_days',0):.0f}d |")
    lines.append("")

    # --- Section 3: walk-forward results -----------------------------------
    lines.append("## 3. Out-of-sample walk-forward")
    lines.append("")
    spy_cagr = spy_oos.get("cagr", 0)
    lines.append(f"- SPY OOS CAGR: **{100*spy_cagr:.2f}%**")
    lines.append(f"- SPY OOS MaxDD: **{100*spy_oos.get('max_drawdown',0):.2f}%**")
    lines.append(f"- Candidates evaluated on OOS: **{len(oos_results)}**")
    lines.append(f"- Candidates rejected: **{len(rejected)}**")
    lines.append("")
    if winner:
        m = winner.metrics
        lines.append(f"**Winner:** `{winner.config.config_id}`")
        lines.append("")
        lines.append(f"- OOS CAGR: **{100*m.get('cagr',0):.2f}%** "
                     f"(SPY: {100*spy_cagr:.2f}%, alpha: "
                     f"{100*(m.get('cagr',0)-spy_cagr):.2f}pp)")
        lines.append(f"- OOS Sharpe: **{m.get('sharpe',0):.2f}**")
        lines.append(f"- OOS MaxDD: **{100*m.get('max_drawdown',0):.2f}%**")
        lines.append(f"- OOS Win rate: **{100*m.get('win_rate',0):.0f}%** "
                     f"({int(m.get('n_trades',0))} trades, "
                     f"{m.get('avg_hold_days',0):.0f}d avg hold)")
        lines.append("")
        lines.append("**Parameters:**")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(winner.config.as_flat_dict(), indent=2, default=float))
        lines.append("```")
    else:
        lines.append("**No candidate passed OOS validation.**")
        lines.append("")
        if rejected:
            lines.append("Rejection log (top 5):")
            lines.append("")
            for r in rejected[:5]:
                lines.append(f"- `{r.get('config_id')}` — {r.get('reason')}")
    lines.append("")

    # --- Section 4: sub-period robustness ----------------------------------
    if subperiod:
        lines.append("## 4. Sub-period robustness (winner)")
        lines.append("")
        lines.append("Spec §8 requires no negative year in sub-periods.")
        lines.append("")
        lines.append("| Period | CAGR | Sharpe | MaxDD | Return | Trades | Pass |")
        lines.append("|--------|------|--------|-------|--------|--------|------|")
        for sp in subperiod:
            if "error" in sp:
                lines.append(f"| {sp.get('period','?')} | ERROR | — | — | — | — | ❌ |")
                continue
            ok = "✅" if sp.get("ok_no_negative_year") else "❌"
            lines.append(f"| {sp['period']} | "
                         f"{100*sp.get('cagr',0):.1f}% | "
                         f"{sp.get('sharpe',0):.2f} | "
                         f"{100*sp.get('max_drawdown',0):.1f}% | "
                         f"{100*sp.get('total_return',0):.1f}% | "
                         f"{int(sp.get('n_trades',0))} | {ok} |")
        lines.append("")

    # --- Section 5: exit-reason breakdown ----------------------------------
    if winner:
        lines.append("## 5. Exit reason breakdown (winner, OOS)")
        lines.append("")
        total = len(winner.trades)
        breakdown = defaultdict(int)
        for t in winner.trades:
            breakdown[t.exit_reason] += 1
        for reason in (EXIT_STOP_LOSS, EXIT_TAKE_PROFIT, EXIT_TIME_STOP,
                       EXIT_SIGNAL, EXIT_UNIVERSE, EXIT_END):
            n = breakdown.get(reason, 0)
            pct = (n / total * 100) if total else 0
            lines.append(f"- {reason}: **{n}** ({pct:.1f}%)")
        lines.append("")

    # --- Section 6: what's in/out of the backtest --------------------------
    lines.append("## 6. Factors NOT included in the backtest (and why)")
    lines.append("")
    lines.append("Per spec §6.4, every factor excluded is documented here so "
                 "future agents immediately understand the limitations.")
    lines.append("")
    lines.append("| Factor | Status | Reason |")
    lines.append("|--------|--------|--------|")
    lines.append("| `price-target-consensus` | Excluded | FMP exposes only the LATEST consensus. Using it historically would leak information. Re-enable once weekly snapshots have been recorded for >= 1 year. |")
    lines.append("| `analyst-estimates` (forward EPS) | Excluded | Same reason. Kept in production scorer for live display. |")
    lines.append("| `etf-asset-exposure` (passive flows) | Excluded | FMP only exposes current-snapshot ETF holdings, no history. |")
    lines.append("| Real-time IV / options | Excluded | No historical IV feed. Planned for Phase 2 options overlay, not core v8. |")
    lines.append("| Earnings-call transcript sentiment (`transcript` factor) | Excluded | No historical sentiment feed; factor weight redistributed proportionally to remaining factors. |")
    lines.append("| Legacy institutional QoQ blend (`institutional` factor) | Excluded | Superseded by `institutional_flow` (13F positions-summary). Weight redistributed. |")
    lines.append("| `discounted-cash-flow` | ⚠️ Partial leak | FMP exposes only latest DCF value. Kept as weak prior at ~1% composite weight; effect bounded but not zero. Follow-up: replace with a computed DCF using as-of-filtered statements. |")
    lines.append("")

    # --- Section 7: honest limitations -------------------------------------
    lines.append("## 7. Honest discussion of limitations")
    lines.append("")
    lines.append("1. **Survivorship bias in universe.** `company-screener` "
                 "returns the *current* constituents meeting the market-cap "
                 "filter. Symbols that were delisted, merged, or fell below "
                 "the threshold before today are not in the universe. This "
                 "biases returns upward. Mitigation for July review: pull a "
                 "monthly constituent snapshot of SP500/NASDAQ from "
                 "`historical-sp500-constituent` / `historical-nasdaq-constituent` "
                 "and union them month-by-month.")
    lines.append("2. **Transaction costs are approximate.** 20 bps round-trip "
                 "is a reasonable equity assumption but actual cost depends on "
                 "venue, size, and spread regime.")
    lines.append("3. **Slippage model is simple.** Default is next-day open; "
                 "real-world executions depend on liquidity and time of day.")
    lines.append("4. **Sub-period robustness sample is small.** Two-year OOS "
                 "window contains maybe 200-400 trades depending on target "
                 "portfolio size. Results past the spec's 200-trade floor "
                 "are meaningful; a 2024-H1 window in isolation is not.")
    lines.append("5. **DCF leak.** See Section 6.")
    lines.append("")

    # --- Section 8: recommended next steps ---------------------------------
    lines.append("## 8. Recommended next steps")
    lines.append("")
    lines.append("- Validate the winning config with different slippage "
                 "assumptions (spec §6.2): instant close, next-day open, "
                 "next-day VWAP, plus 10/20/30/50 bps transaction cost.")
    lines.append("- Run sensitivity to universe: SP500 only, NASDAQ only, "
                 "combined. Edge should survive each.")
    lines.append("- Add survivorship-safe universe construction before "
                 "the July review sign-off.")
    lines.append("- Once >= 1 year of weekly price-target snapshots are "
                 "collected, re-run the backtest with the `upside` factor "
                 "using historical consensus rather than the current intrinsic-only proxy.")
    lines.append("- Promote winning config to `v8_weights.json` and tag the "
                 "repo `v8.0.0-candidate` (spec §7).")
    lines.append("")

    with open(path, "w") as f:
        f.write("\n".join(lines))
    log.info("Wrote report → %s", path)


# ===========================================================================
# SECTION 11 — CLI
# ===========================================================================


def _resolve_universe(universe_arg: str) -> List[str]:
    if not HAVE_V7:
        raise RuntimeError("Universe resolution requires backtest_full import.")
    regions = {
        # v8.1: fixed — was previously ["sp500"] placeholder, now actually
        # combines both. _get_symbols_v7 dedupes across calls so the overlap
        # between NYSE-listed SP500 names and NASDAQ-listed SP500 names is
        # handled transparently.
        "sp500_nasdaq": ["sp500", "nasdaq"],
        "sp500": ["sp500"],
        "nasdaq": ["nasdaq"],
        "nasdaq100": ["nasdaq100"],
        "europe": ["europe"],
        "global": ["global"],
    }
    if universe_arg.endswith(".txt"):
        with open(universe_arg) as f:
            return [line.strip() for line in f if line.strip()]
    chosen = regions.get(universe_arg, [universe_arg])
    syms = []
    for r in chosen:
        syms.extend(_get_symbols_v7(r))
    return list(dict.fromkeys(syms))


def cmd_scan(args) -> None:
    universe = _resolve_universe(args.universe)
    log.info("Scan universe size: %d", len(universe))
    dp = HistoricalDataProvider(universe, args.from_date, args.to_date)
    dp.load_all_charts()
    if HAVE_V7:
        prefetch_congressional(universe)

    scan_dates = weekly_scan_dates(args.from_date, args.to_date, args.cadence)
    log.info("Scan dates: %d (%s → %s)",
             len(scan_dates), scan_dates[0], scan_dates[-1])
    out_path = os.path.join(args.out, "scan_cache.jsonl")
    os.makedirs(args.out, exist_ok=True)
    staging_dir = getattr(args, "staging_dir", None)
    build_scan_cache(universe, scan_dates, dp, out_path=out_path,
                     resume=not args.no_resume,
                     staging_dir=staging_dir)
    log.info("Scan cache written to %s", out_path)


def cmd_simulate(args) -> None:
    cache = load_scan_cache(args.scan_cache)
    cfg = StrategyConfig()
    if args.cfg_json:
        with open(args.cfg_json) as f:
            payload = json.load(f)
        cfg = StrategyConfig(**{k: v for k, v in payload.items()
                                if k in StrategyConfig.__dataclass_fields__})
    res = simulate(cfg, cache, args.from_date, args.to_date,
                   initial_cash=args.initial_cash)
    os.makedirs(args.out, exist_ok=True)
    write_results_csv([res], os.path.join(args.out, "backtest_v8_results.csv"))
    write_trades_csv(res, os.path.join(args.out, "backtest_v8_trades.csv"))
    write_equity_curves_csv({"strategy": res},
                             os.path.join(args.out, "backtest_v8_equity_curves.csv"))
    log.info("Single-sim done: CAGR=%.2f%%  Sharpe=%.2f  MaxDD=%.2f%%",
             100 * res.metrics.get("cagr", 0),
             res.metrics.get("sharpe", 0),
             100 * res.metrics.get("max_drawdown", 0))


def cmd_sweep(args) -> None:
    cache = load_scan_cache(args.scan_cache)
    # v8.2 fix: the simulator needs _CHART_CACHE populated for mark-to-market
    # and intraday SL/TP/time-stop checks. cmd_scan loaded charts as a side
    # effect of HistoricalDataProvider.load_all_charts(); sweep runs in a
    # fresh container so we must reload them here, otherwise _walk_forward_mtm
    # exits early and every config produces an empty equity curve → CAGR=0.
    universe = sorted({r["symbol"] for rows in cache.values() for r in rows})
    log.info("Sweep: loading %d charts for MTM / intraday exits", len(universe))
    dp = HistoricalDataProvider(universe, args.train_from, args.train_to)
    dp.load_all_charts()

    baseline = StrategyConfig()
    configs = generate_sweep_configs(baseline, n_configs=args.n_configs, seed=args.seed)
    log.info("Running sweep: %d configs on %s → %s",
             len(configs), args.train_from, args.train_to)
    results = run_sweep(configs, cache, args.train_from, args.train_to,
                        initial_cash=args.initial_cash)
    os.makedirs(args.out, exist_ok=True)
    out_csv = os.path.join(args.out, "sweep_results.csv")
    write_results_csv(results, out_csv)
    log.info("Sweep done — wrote %s", out_csv)


def cmd_walkforward(args) -> None:
    cache = load_scan_cache(args.scan_cache)
    # v8.2 fix: same as cmd_sweep — the simulator needs _CHART_CACHE for MTM
    # and intraday exits. Load charts spanning both train and OOS windows.
    universe = sorted({r["symbol"] for rows in cache.values() for r in rows})
    log.info("Walkforward: loading %d charts (train+OOS windows)", len(universe))
    dp = HistoricalDataProvider(universe, args.train_from, args.oos_to)
    dp.load_all_charts()

    # Reload training configs from either a prior sweep CSV or re-run sweep.
    if args.sweep_results and os.path.exists(args.sweep_results):
        train_results = _reload_sweep_results(args.sweep_results, cache,
                                              args.train_from, args.train_to,
                                              args.initial_cash,
                                              top_n=args.top_n_replay)
    else:
        configs = generate_sweep_configs(StrategyConfig(),
                                          n_configs=args.n_configs, seed=args.seed)
        train_results = run_sweep(configs, cache, args.train_from, args.train_to,
                                  initial_cash=args.initial_cash)
    _run_walkforward_and_report(train_results, cache, args)


def _reload_sweep_results(csv_path: str,
                          cache: Dict[str, List[dict]],
                          train_from: str, train_to: str,
                          initial_cash: float,
                          top_n: int = 20) -> List[SimulationResult]:
    """Re-hydrate the top-N training configs from a sweep_results.csv and
    re-run them so we have their full Trade+EquityCurve objects for OOS.
    """
    results: List[SimulationResult] = []
    with open(csv_path, "r") as f:
        rows = list(csv.DictReader(f))
    rows.sort(key=lambda r: float(r.get("calmar") or 0), reverse=True)
    for row in rows[:top_n]:
        try:
            def _bool(val: str) -> bool:
                return str(val).strip().lower() in ("1", "true", "yes", "y")
            cfg = StrategyConfig(
                composite_floor=float(row.get("cfg_composite_floor", 0.80)),
                strong_buy_threshold=float(row.get("cfg_strong_buy_threshold", 0.85)),
                buy_threshold=float(row.get("cfg_buy_threshold", 0.70)),
                watch_threshold=float(row.get("cfg_watch_threshold", 0.55)),
                sell_threshold=float(row.get("cfg_sell_threshold", 0.40)),
                coverage_alpha=float(row.get("cfg_coverage_alpha", 0.7)),
                stop_loss=float(row.get("cfg_stop_loss", -0.12)),
                take_profit=float(row.get("cfg_take_profit", 0.20)),
                time_stop_days=int(float(row.get("cfg_time_stop_days", 60))),
                target_positions=int(float(row.get("cfg_target_positions", 5))),
                weighting=row.get("cfg_weighting", "equal"),
                rebalance_cadence_days=int(float(row.get("cfg_rebalance_cadence_days", 7))),
                slippage_model=row.get("cfg_slippage_model", SLIP_NEXT_OPEN),
                transaction_cost_bps=float(row.get("cfg_transaction_cost_bps", 20)),
                macro_regime_overlay=_bool(row.get("cfg_macro_regime_overlay", "")),
                macro_risk_off_floor_bump=float(row.get("cfg_macro_risk_off_floor_bump", 0.05)),
                config_id=row.get("config_id", "reloaded"),
            )
            res = simulate(cfg, cache, train_from, train_to, initial_cash=initial_cash)
            results.append(res)
        except Exception as e:
            log.warning("Could not rehydrate %s: %s", row.get("config_id"), e)
    return results


def _run_walkforward_and_report(train_results: List[SimulationResult],
                                cache: Dict[str, List[dict]],
                                args) -> None:
    wf = walk_forward(train_results, cache, args.oos_from, args.oos_to,
                      top_n=args.top_n, initial_cash=args.initial_cash)
    os.makedirs(args.out, exist_ok=True)

    # Write the sweep results (training side) if not already there.
    train_csv = os.path.join(args.out, "backtest_v8_results.csv")
    write_results_csv(train_results, train_csv)

    winner = wf["winner"]
    if winner is not None:
        write_trades_csv(winner, os.path.join(args.out, "backtest_v8_trades.csv"))
    write_winner_json(winner, os.path.join(args.out, "backtest_v8_winner_config.json"))

    # Equity curves: winner + 4 benchmark configs (baseline, best-train-unfiltered,
    # tight, loose) on OOS.
    bench_cfgs = {
        "baseline": StrategyConfig(config_id="baseline"),
        "train_top_unfiltered": wf["ranked_train"][0].config if wf["ranked_train"] else StrategyConfig(),
        "tight": replace(StrategyConfig(), stop_loss=-0.08, take_profit=0.15,
                          time_stop_days=45, config_id="tight"),
        "loose": replace(StrategyConfig(), stop_loss=-0.20, take_profit=0.30,
                          time_stop_days=120, config_id="loose"),
    }
    curves = {}
    for name, cfg in bench_cfgs.items():
        try:
            r = simulate(cfg, cache, args.oos_from, args.oos_to,
                          initial_cash=args.initial_cash)
            curves[name] = r
        except Exception as e:
            log.warning("benchmark %s failed on OOS: %s", name, e)
    if winner is not None:
        curves["winner"] = winner
    write_equity_curves_csv(curves,
                            os.path.join(args.out, "backtest_v8_equity_curves.csv"))

    # Sub-period robustness on the OOS window (and training sub-parts).
    subperiods = []
    for label, s, e in [
        ("2022-H1", "2022-01-01", "2022-06-30"),
        ("2022-H2", "2022-07-01", "2022-12-31"),
        ("2023",    "2023-01-01", "2023-12-31"),
        ("2024",    "2024-01-01", "2024-12-31"),
        ("2025",    "2025-01-01", "2025-12-31"),
    ]:
        # Only include periods for which the scan cache has data.
        if any(s <= d <= e for d in cache):
            subperiods.append((label, s, e))
    winner_cfg = winner.config if winner else (wf["ranked_train"][0].config
                                               if wf["ranked_train"] else None)
    sub_results = (subperiod_robustness(winner_cfg, cache, subperiods,
                                        args.initial_cash)
                   if winner_cfg else [])

    report_path = os.path.join(args.out, "backtest_v8_report.md")
    generate_report_md(
        train_results=train_results,
        oos_results=wf["evaluated"],
        winner=winner,
        rejected=wf["rejected"],
        spy_oos=wf["spy_oos"],
        subperiod=sub_results,
        path=report_path,
        context={
            "train_from": args.train_from, "train_to": args.train_to,
            "oos_from": args.oos_from, "oos_to": args.oos_to,
            "universe": getattr(args, "universe", "sp500_nasdaq"),
            "universe_size": "n/a",
        },
    )


def cmd_all(args) -> None:
    """One-shot: scan -> sweep on train -> walk-forward on OOS -> report."""
    args.universe = getattr(args, "universe", "sp500_nasdaq")
    args.out = args.out or "./out"
    os.makedirs(args.out, exist_ok=True)

    scan_path = os.path.join(args.out, "scan_cache.jsonl")
    if not os.path.exists(scan_path) or args.rescan:
        scan_args = argparse.Namespace(
            from_date=args.from_date, to_date=args.to_date,
            universe=args.universe, cadence=args.cadence,
            out=args.out, no_resume=False,
            staging_dir=getattr(args, "staging_dir", None))
        cmd_scan(scan_args)

    cache = load_scan_cache(scan_path)
    # Sweep on training window.
    configs = generate_sweep_configs(StrategyConfig(),
                                      n_configs=args.n_configs, seed=args.seed)
    train_results = run_sweep(configs, cache, args.from_date, args.train_split,
                              initial_cash=args.initial_cash)

    # Walk-forward on OOS.
    wf_args = argparse.Namespace(
        scan_cache=scan_path,
        train_from=args.from_date, train_to=args.train_split,
        oos_from=args.train_split, oos_to=args.to_date,
        top_n=args.top_n, initial_cash=args.initial_cash,
        out=args.out, universe=args.universe,
    )
    _run_walkforward_and_report(train_results, cache, wf_args)


def build_cli() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Stock Screener v8 forward-walking backtest")
    sub = p.add_subparsers(dest="cmd", required=True)

    # scan
    s = sub.add_parser("scan", help="Build the scan cache (expensive, API-bound)")
    s.add_argument("--from", dest="from_date", required=True)
    s.add_argument("--to", dest="to_date", required=True)
    s.add_argument("--universe", default="sp500")
    s.add_argument("--cadence", type=int, default=7, help="Scan cadence in days")
    s.add_argument("--no-resume", action="store_true",
                    help="Overwrite any existing scan cache")
    s.add_argument("--out", default="./out")
    s.add_argument("--staging-dir", dest="staging_dir", default=None,
                    help="Write the scan cache locally in this directory during "
                         "execution, then copy to --out at the end. Strongly "
                         "recommended (e.g. --staging-dir /tmp) when --out is a "
                         "GCSFuse mount, since GCSFuse cannot handle append-mode "
                         "writes on large growing files.")
    s.set_defaults(func=cmd_scan)

    # simulate
    sim = sub.add_parser("simulate", help="Single-config simulation")
    sim.add_argument("--scan-cache", required=True)
    sim.add_argument("--from", dest="from_date", required=True)
    sim.add_argument("--to", dest="to_date", required=True)
    sim.add_argument("--cfg-json", default="",
                      help="Path to a JSON file with StrategyConfig overrides")
    sim.add_argument("--initial-cash", type=float, default=100_000.0)
    sim.add_argument("--out", default="./out")
    sim.set_defaults(func=cmd_simulate)

    # sweep
    sw = sub.add_parser("sweep", help="Training-window sweep")
    sw.add_argument("--scan-cache", required=True)
    sw.add_argument("--train-from", required=True, dest="train_from")
    sw.add_argument("--train-to", required=True, dest="train_to")
    sw.add_argument("--n-configs", type=int, default=500)
    sw.add_argument("--seed", type=int, default=42)
    sw.add_argument("--initial-cash", type=float, default=100_000.0)
    sw.add_argument("--out", default="./out")
    sw.set_defaults(func=cmd_sweep)

    # walkforward
    wf = sub.add_parser("walkforward", help="OOS validation on top sweep configs")
    wf.add_argument("--scan-cache", required=True)
    wf.add_argument("--train-from", required=True, dest="train_from")
    wf.add_argument("--train-to", required=True, dest="train_to")
    wf.add_argument("--oos-from", required=True, dest="oos_from")
    wf.add_argument("--oos-to", required=True, dest="oos_to")
    wf.add_argument("--sweep-results", default="",
                     help="Prior sweep_results.csv to rehydrate; if absent, sweep is re-run")
    wf.add_argument("--n-configs", type=int, default=500)
    wf.add_argument("--top-n", type=int, default=10,
                     help="Number of top training configs to try on OOS")
    wf.add_argument("--top-n-replay", type=int, default=20,
                     help="Number of rows to re-hydrate from a prior sweep CSV")
    wf.add_argument("--seed", type=int, default=42)
    wf.add_argument("--initial-cash", type=float, default=100_000.0)
    wf.add_argument("--out", default="./out")
    wf.set_defaults(func=cmd_walkforward)

    # all
    a = sub.add_parser("all", help="scan + sweep + walkforward + report")
    a.add_argument("--from", dest="from_date", required=True)
    a.add_argument("--to", dest="to_date", required=True)
    a.add_argument("--train-split", required=True,
                     help="Date separating train / OOS, e.g. 2024-01-01")
    a.add_argument("--universe", default="sp500")
    a.add_argument("--cadence", type=int, default=7)
    a.add_argument("--n-configs", type=int, default=500)
    a.add_argument("--top-n", type=int, default=10)
    a.add_argument("--seed", type=int, default=42)
    a.add_argument("--rescan", action="store_true")
    a.add_argument("--initial-cash", type=float, default=100_000.0)
    a.add_argument("--out", default="./out")
    a.add_argument("--staging-dir", dest="staging_dir", default=None,
                    help="See `scan --staging-dir` — recommended on Cloud Run "
                         "with a GCSFuse-mounted --out.")
    a.set_defaults(func=cmd_all)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    p = build_cli()
    args = p.parse_args(argv)
    if not FMP_KEY and args.cmd in ("scan", "all"):
        log.warning("FMP_API_KEY not set — scan/all will fail without it.")
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
