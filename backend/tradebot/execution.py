"""IBKR execution for the D10 sleeve — three scheduled invocations, not a daemon.

  --stage    22:35 CET (after the nightly scan): gates -> stage pending entries.
             Pure data work, no orders, market closed.
  --morning  09:25 ET: place DAY marketable limits for staged entries, wait a
             fill window (marketable limits fill in seconds or not at all),
             attach OCA exit pairs off the ACTUAL fill price, cancel the rest.
  --eod      after the close: reconcile fills/exits vs the ledger, advance bar
             counts (trading days only), fire terminal MOO sells at bar 60,
             snapshot equity.

Same IBKR login as the portfolio mirror (one shared gateway); every order is
pinned to cfg.ib_account with the bot's own client id. cfg.dry_run logs order
specs instead of placing them — flip via TRADEBOT_LIVE=1 only.

Order specs are plain dicts so all construction logic is unit-testable without
ib_insync; only _place/_connect touch the API.
"""
import logging
import math
import socket
from datetime import date, datetime

from .config import BotConfig
from . import ledger, risk, signals

log = logging.getLogger("tradebot.execution")


# ────────────────────────── pure construction logic ──────────────────────────

def qty_for(slot_usd: float, limit_price: float) -> int:
    """Shares sized off the LIMIT (worst fill) so cost never exceeds the slot."""
    if slot_usd <= 0 or limit_price <= 0:
        return 0
    return int(math.floor(slot_usd / limit_price))


def build_entry(cfg: BotConfig, cand: dict, qty: int) -> dict:
    limit = round(cand["price"] * (1.0 + cfg.chase_cap), 2)
    return {"symbol": cand["symbol"], "action": "BUY", "type": "LMT", "qty": qty,
            "limit": limit, "tif": "DAY", "account": cfg.ib_account}


def build_exit_pair(cfg: BotConfig, symbol: str, qty: int, fill_price: float,
                    tag: str) -> list:
    """Target limit + disaster stop as an OCA pair (one cancels the other).
    Terminal (bar 60) exits are separate MOO orders from --eod."""
    oca = f"x_{symbol}_{tag}"
    target = {"symbol": symbol, "action": "SELL", "type": "LMT", "qty": qty,
              "limit": round(fill_price * cfg.barrier_mult, 2), "tif": "GTC",
              "ocaGroup": oca, "account": cfg.ib_account}
    stop = {"symbol": symbol, "action": "SELL", "type": "STP", "qty": qty,
            "stop": round(fill_price * (1.0 - cfg.disaster_stop_frac), 2), "tif": "GTC",
            "ocaGroup": oca, "account": cfg.ib_account}
    return [target, stop]


def build_terminal_exit(cfg: BotConfig, symbol: str, qty: int) -> dict:
    """Market-on-open sell for the next session (placed after the close)."""
    return {"symbol": symbol, "action": "SELL", "type": "MKT", "qty": qty,
            "tif": "OPG", "account": cfg.ib_account}


def due_terminal(pos: dict, cfg: BotConfig) -> bool:
    return pos.get("status") == "OPEN" and int(pos.get("bar_count") or 0) >= cfg.window_bars


def detect_exits(ledger_open: list, ib_positions: dict) -> list:
    """Ledger-open symbols absent from IBKR positions -> an exit order filled
    (target/stop/terminal) since the last reconcile. Returns those positions."""
    return [p for p in ledger_open if p["symbol"] not in ib_positions]


def classify_exit(pos: dict, exec_price: float) -> str:
    """Nearest exit reason from the fill price (executions carry no order tag
    after restarts): target, disaster stop, else terminal/manual."""
    if exec_price >= pos["target_price"] * 0.995:
        return "TARGET"
    if exec_price <= pos["stop_price"] * 1.05:
        return "DISASTER_STOP"
    return "TERMINAL"


# ────────────────────────── scheduling / idempotency helpers ──────────────────────

def _tcp_probe(host: str, port: int, timeout: float = 3.0) -> bool:
    """Cheap check that SOMETHING is listening on the gateway socket. Does NOT
    confirm IBKR login (the full connect in each live phase does that) — it just
    avoids an IB handshake + clientId churn to decide whether a gateway-dependent
    phase is even worth attempting this --watch cycle."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def market_open_from_hours(trading_hours: str, ymd: str) -> bool:
    """Parse an IB contractDetails.tradingHours string for date ymd (YYYYMMDD).
    Format: '20260720:0930-20260720:1600;20260721:CLOSED;...'. Returns False on
    an explicit CLOSED segment; True when an open segment exists; True (fail-
    open, so a parse quirk can't deadlock the bot — the unfilled-order path
    still protects it) when the date is absent/unparseable."""
    if not trading_hours:
        return True
    for seg in trading_hours.split(";"):
        seg = seg.strip()
        if seg.startswith(ymd):
            return not seg.endswith("CLOSED")
    return True


def trading_date() -> str:
    """US-session date the bot keys idempotency off. The gateway PC runs on CET;
    across the --watch active hours (12:00–23:45 CET) the CET and ET calendar
    dates coincide, so date.today() is the session date."""
    return date.today().isoformat()


def _in_window(now: datetime, window) -> bool:
    (sh, sm), (eh, em) = window
    start = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
    end = now.replace(hour=eh, minute=em, second=59, microsecond=0)
    return start <= now <= end


# ────────────────────────── IB plumbing (thin, untested) ──────────────────────────

def _ensure_event_loop():
    """ib_insync's dependency eventkit calls get_event_loop() AT IMPORT TIME,
    which raises on Python >=3.12 (no default loop in the main thread). The
    loop must therefore exist BEFORE `import ib_insync` (observed 2026-07-02)."""
    import asyncio
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())


def _connect(cfg: BotConfig):
    _ensure_event_loop()  # must precede the import — see docstring
    from ib_insync import IB
    ib = IB()
    ib.connect(cfg.ib_host, cfg.ib_port, clientId=cfg.ib_client_id, timeout=20)
    accounts = ib.managedAccounts()
    if cfg.ib_account not in accounts:
        ib.disconnect()
        raise RuntimeError(f"bot account {cfg.ib_account} not in managed accounts {accounts}")
    return ib


def _try_connect(cfg: BotConfig):
    """Connect even in dry-run (read-only: quotes, equity, positions) so the
    dry-run exercises the full data path — order placement is separately gated
    by cfg.dry_run in _place. Absent/unreachable gateway degrades gracefully."""
    try:
        return _connect(cfg)
    except Exception as e:
        log.warning(f"IB gateway unavailable ({e}); continuing without it")
        return None


def _contract(ib, symbol: str):
    from ib_insync import Stock
    c = Stock(symbol, "SMART", "USD")
    ib.qualifyContracts(c)
    return c


def _to_order(spec: dict):
    from ib_insync import LimitOrder, MarketOrder, StopOrder, Order
    if spec["type"] == "LMT":
        o = LimitOrder(spec["action"], spec["qty"], spec["limit"])
    elif spec["type"] == "STP":
        o = StopOrder(spec["action"], spec["qty"], spec["stop"])
    else:
        o = MarketOrder(spec["action"], spec["qty"])
    o.tif = spec["tif"]
    o.account = spec["account"]
    if spec.get("ocaGroup"):
        o.ocaGroup, o.ocaType = spec["ocaGroup"], 1
    return o


def _place(ib, cfg: BotConfig, gcs, spec: dict, why: str):
    ledger.log_event(gcs, cfg, "ORDER_DRY" if cfg.dry_run else "ORDER", why=why, **spec)
    if cfg.dry_run:
        log.info(f"DRY-RUN {why}: {spec}")
        return None
    return ib.placeOrder(_contract(ib, spec["symbol"]), _to_order(spec))


def _equity_and_cash(ib, cfg: BotConfig) -> tuple:
    vals = {v.tag: float(v.value) for v in ib.accountSummary(cfg.ib_account)
            if v.tag in ("NetLiquidation", "TotalCashValue")}
    return vals.get("NetLiquidation", 0.0), vals.get("TotalCashValue", 0.0)


def _live_positions(ib, cfg: BotConfig) -> dict:
    return {p.contract.symbol: p.position for p in ib.positions(cfg.ib_account)
            if p.position != 0}


def _entry_market_open_today(ib) -> bool:
    """PRE-open holiday guard for the entry path (supervisor blocker F2): the
    EOD guard can't be used at 09:25 ET (today's daily bar doesn't exist yet),
    so read SPY's trading calendar from contractDetails instead."""
    from ib_insync import Stock
    try:
        cds = ib.reqContractDetails(Stock("SPY", "SMART", "USD"))
        hours = cds[0].tradingHours if cds else ""
        return market_open_from_hours(hours, date.today().strftime("%Y%m%d"))
    except Exception as e:
        log.warning(f"holiday check failed ({e}); failing open")
        return True


def _market_was_open_today(ib) -> bool:
    """One SPY daily bar — guards bar_count against holidays."""
    from ib_insync import Stock
    bars = ib.reqHistoricalData(Stock("SPY", "SMART", "USD"), "", "2 D", "1 day",
                                "TRADES", useRTH=True)
    return bool(bars) and bars[-1].date.isoformat() == date.today().isoformat()


# ────────────────────────── the three entrypoints ──────────────────────────

def run_stage(cfg: BotConfig, gcs, today: str = None) -> dict:
    """Data-only (no IB): expire yesterday's un-entered pendings, then stage
    today's D10 candidates. Gates on last-known equity. Idempotent per session."""
    today = today or trading_date()
    state = ledger.read_state(gcs, cfg)
    if ledger.phase_done(state, "stage", today):
        return {"skipped": "stage done today"}

    # expire pendings that missed their entry window (a prior session's stage that
    # never got entered) so they can't leak into today's morning at stale prices
    stale = [p for p in state["pending_entries"] if str(p.get("scan_date", today)) < today]
    for p in stale:
        ledger.log_event(gcs, cfg, "ENTRY_EXPIRED", symbol=p["symbol"],
                         reason=f"missed entry window (staged {p.get('scan_date')})")
    if stale:
        state["pending_entries"] = [p for p in state["pending_entries"]
                                    if str(p.get("scan_date", today)) >= today]

    scan = gcs["read"](cfg.scan_path, {})
    summary = gcs["read"](cfg.cal_summary_path, {})
    edges = ((gcs["read"](cfg.cal_config_path, {}) or {}).get("decile_thresholds") or {}).get(cfg.regime)
    equity = ledger.day_start_equity(state, "9999") or 0.0  # latest snapshot
    paper = False
    if cfg.dry_run and equity <= 0:
        equity, paper = cfg.paper_equity_usd, True  # unfunded rehearsal sizing

    held = {p["symbol"] for p in ledger.open_positions(state)}
    pending = {p["symbol"] for p in state["pending_entries"]}
    n_open, n_pend = len(held), len(pending)
    gates = risk.entry_gates(cfg, gcs, state, summary, equity, 0.0, n_open, n_pend, today)
    if not risk.all_pass(gates):
        ledger.log_event(gcs, cfg, "STAGE_BLOCKED",
                         gates=[f"{n}:{d}" for n, ok, d in gates if not ok])
        ledger.mark_phase_done(state, "stage", today)
        ledger.write_state(gcs, cfg, state)
        return {"staged": 0, "blocked": True}

    slots_free = risk.max_open_slots(cfg, today) - n_open - n_pend
    scan_date = (scan.get("scan_date") or today)[:10]
    picks = signals.select_candidates(scan.get("stocks", []), edges or [], cfg,
                                      held, pending, ledger.sector_counts(state), slots_free)
    slot = risk.slot_size_usd(equity, cfg, today)
    staged = 0
    for cand in picks:
        limit = round(cand["price"] * (1.0 + cfg.chase_cap), 2)
        q = qty_for(slot, limit)
        if q < 1:
            ledger.log_event(gcs, cfg, "ENTRY_SKIPPED", symbol=cand["symbol"],
                             reason="qty<1 at slot size")
            continue
        ledger.stage_pending(state, cand, q, limit, scan_date)
        staged += 1
    ledger.log_event(gcs, cfg, "STAGED", n=staged, slot_usd=slot, scan_date=scan_date,
                     paper_equity=paper)
    ledger.mark_phase_done(state, "stage", today)
    ledger.write_state(gcs, cfg, state)
    return {"staged": staged, "blocked": False}


def run_morning(cfg: BotConfig, gcs, fill_wait_s: int = 900, today: str = None) -> dict:
    """At the open — entries + fill-window + OCA exits off actual fills.
    Idempotent per session; in LIVE, defers (does NOT mark done) if the gateway
    is down so the next --watch cycle retries once you're logged in."""
    today = today or trading_date()
    state = ledger.read_state(gcs, cfg)
    if ledger.phase_done(state, "morning", today):
        return {"skipped": "morning done today"}
    if not state["pending_entries"]:
        ledger.mark_phase_done(state, "morning", today)  # nothing to enter — done
        ledger.write_state(gcs, cfg, state)
        return {"placed": 0, "filled": 0}
    ib = _try_connect(cfg)
    if ib is None and not cfg.dry_run:
        ledger.log_event(gcs, cfg, "MORNING_DEFERRED", reason="gateway unreachable / login pending")
        return {"skipped": "gateway unreachable"}  # NOT marked done -> --watch retries
    if ib and not _entry_market_open_today(ib):
        # US market holiday (F2): never fire DAY limits into a closed market.
        # Mark done — there is no session today to catch up to; the pendings
        # expire at the next stage rather than filling at stale prices.
        ib.disconnect()
        ledger.log_event(gcs, cfg, "MORNING_SKIPPED", reason="market holiday")
        state = ledger.read_state(gcs, cfg)
        ledger.mark_phase_done(state, "morning", today)
        ledger.write_state(gcs, cfg, state)
        return {"skipped": "market holiday"}
    try:
        equity, _cash = _equity_and_cash(ib, cfg) if ib else (0.0, 0.0)
        if not equity:  # dry-run: latest snapshot, else unfunded-rehearsal paper equity
            equity = ledger.day_start_equity(state, "9999")
            if cfg.dry_run and equity <= 0:
                equity = cfg.paper_equity_usd
        summary = gcs["read"](cfg.cal_summary_path, {})
        n_open = len(ledger.open_positions(state))
        gates = risk.entry_gates(cfg, gcs, state, summary, equity,
                                 ledger.day_start_equity(state, today),
                                 n_open, 0, today, check_sizing=False)
        if not risk.all_pass(gates):
            ledger.log_event(gcs, cfg, "MORNING_BLOCKED",
                             gates=[f"{n}:{d}" for n, ok, d in gates if not ok])
            state["pending_entries"] = []
            ledger.mark_phase_done(state, "morning", today)
            ledger.write_state(gcs, cfg, state)
            return {"placed": 0, "filled": 0, "blocked": True}

        placed, trades = [], {}
        for pend in list(state["pending_entries"]):
            sym = pend["symbol"]
            if ib:  # corp-action guard needs a live quote
                tick = ib.reqTickers(_contract(ib, sym))
                quote = (tick[0].marketPrice() or 0.0) if tick else 0.0
                if not risk.corp_action_guard(pend["scan_close"], quote, cfg):
                    ledger.log_event(gcs, cfg, "ENTRY_SKIPPED", symbol=sym,
                                     reason=f"corp-action guard: scan {pend['scan_close']} vs quote {quote}")
                    state["pending_entries"] = [p for p in state["pending_entries"]
                                                if p["symbol"] != sym]
                    continue
            spec = {"symbol": sym, "action": "BUY", "type": "LMT", "qty": pend["qty"],
                    "limit": pend["limit_price"], "tif": "DAY", "account": cfg.ib_account}
            t = _place(ib, cfg, gcs, spec, "entry")
            if t is not None:
                trades[sym] = t
            placed.append(sym)

        filled = 0
        if ib and trades:
            ib.sleep(5)
            deadline = fill_wait_s
            while deadline > 0 and any(not t.isDone() for t in trades.values()):
                ib.sleep(10)
                deadline -= 10
            for sym, t in trades.items():
                if t.orderStatus.status == "Filled":
                    fp = t.orderStatus.avgFillPrice
                    pos = ledger.record_fill(state, cfg, sym, fp, int(t.orderStatus.filled), today)
                    for spec in build_exit_pair(cfg, sym, pos["qty"], fp, today.replace("-", "")):
                        _place(ib, cfg, gcs, spec, "exit-pair")
                    ledger.log_event(gcs, cfg, "FILL", symbol=sym, price=fp,
                                     slippage_pct=pos["entry_slippage_pct"])
                    filled += 1
                else:  # unfilled/partial past the window -> cancel, gap-skip
                    ib.cancelOrder(t.order)
                    ledger.log_event(gcs, cfg, "ENTRY_SKIPPED", symbol=sym,
                                     reason=f"unfilled in window (gap>cap), status={t.orderStatus.status}")
                    state["pending_entries"] = [p for p in state["pending_entries"]
                                                if p["symbol"] != sym]
        elif cfg.dry_run:
            # dry-run: simulate fills at scan close for pipeline testing
            for pend in list(state["pending_entries"]):
                pos = ledger.record_fill(state, cfg, pend["symbol"], pend["scan_close"],
                                         pend["qty"], today)
                for spec in build_exit_pair(cfg, pend["symbol"], pos["qty"],
                                            pos["fill_price"], today.replace("-", "")):
                    _place(ib, cfg, gcs, spec, "exit-pair")
                filled += 1
        ledger.mark_phase_done(state, "morning", today)
        ledger.write_state(gcs, cfg, state)
        return {"placed": len(placed), "filled": filled}
    finally:
        if ib:
            ib.disconnect()


def run_eod(cfg: BotConfig, gcs, today: str = None) -> dict:
    """After the close — reconcile (live only), advance bars, terminals, snapshot.

    Dry-run WITH a reachable gateway is the full rehearsal: real equity
    snapshots (so staging un-blocks once the account is funded), real trading-day
    detection, simulated positions aging normally — only orders are simulated.
    Reconciliation against IBKR positions is live-only (simulated positions
    don't exist at the broker and would all read as false exits)."""
    today = today or trading_date()
    state = ledger.read_state(gcs, cfg)
    if ledger.phase_done(state, "eod", today):
        return {"skipped": "eod done today"}  # bars advance at most once per session
    ib = _try_connect(cfg)
    if ib is None and not cfg.dry_run:
        ledger.log_event(gcs, cfg, "EOD_DEFERRED", reason="gateway unreachable / login pending")
        return {"skipped": "gateway unreachable"}  # NOT marked done -> --watch retries
    try:
        exits = terminals = 0
        if ib and not cfg.dry_run:
            live = _live_positions(ib, cfg)
            fills_today = {f.contract.symbol: f.execution.price for f in ib.fills()
                           if f.execution.side == "SLD"}
            tracked = [p for p in state["positions"]
                       if p.get("status") in ("OPEN", "TERMINAL_PENDING")]
            for pos in detect_exits(tracked, live):
                px = fills_today.get(pos["symbol"])
                reason = ("TERMINAL" if pos["status"] == "TERMINAL_PENDING"
                          else classify_exit(pos, px)) if px else "UNKNOWN"
                if px is None:
                    px = pos["target_price"]  # placeholder; supervisor flags UNKNOWN
                pos["status"] = "OPEN"  # so close_position finds it
                ledger.close_position(state, pos["symbol"], px, today, reason)
                ledger.log_event(gcs, cfg, "EXIT", symbol=pos["symbol"], price=px,
                                 reason=reason, realized_pct=pos.get("realized_pct"))
                exits += 1
        # advance bars once per session: live/dry-run-with-gateway use the real
        # SPY-bar holiday check; dry-run WITHOUT a gateway falls back to a plain
        # weekday check so the paper rehearsal still ages without a login
        market_open = (_market_was_open_today(ib) if ib
                       else (cfg.dry_run and date.fromisoformat(today).weekday() < 5))
        if market_open:
            for pos in ledger.open_positions(state):
                pos["bar_count"] = int(pos.get("bar_count") or 0) + 1
        for pos in [p for p in ledger.open_positions(state) if due_terminal(p, cfg)]:
            if ib and not cfg.dry_run:
                # cancel the OCA pair first, then MOO sell for the next open
                for t in ib.openTrades():
                    if (t.contract.symbol == pos["symbol"]
                            and t.order.account == cfg.ib_account
                            and t.order.action == "SELL"):
                        ib.cancelOrder(t.order)
                _place(ib, cfg, gcs, build_terminal_exit(cfg, pos["symbol"], pos["qty"]),
                       "terminal-bar60")
                pos["status"] = "TERMINAL_PENDING"
                terminals += 1
            elif ib:  # dry-run: simulate the terminal close at the market quote
                tick = ib.reqTickers(_contract(ib, pos["symbol"]))
                px = (tick[0].marketPrice() or 0.0) if tick else 0.0
                if px > 0:
                    ledger.close_position(state, pos["symbol"], px, today, "TERMINAL")
                    ledger.log_event(gcs, cfg, "EXIT_SIM", symbol=pos["symbol"],
                                     price=px, reason="TERMINAL")
                    terminals += 1
        if ib:
            equity, cash = _equity_and_cash(ib, cfg)
            if equity > 0:
                ledger.equity_snapshot(state, equity, cash, today)
        ledger.log_event(gcs, cfg, "EOD", open=len(ledger.open_positions(state)),
                         exits=exits, terminals=terminals, dry_run=cfg.dry_run)
        ledger.mark_phase_done(state, "eod", today)
        ledger.write_state(gcs, cfg, state)
        return {"exits": exits, "terminals": terminals,
                "open": len(ledger.open_positions(state))}
    finally:
        if ib:
            ib.disconnect()


def run_watch(cfg: BotConfig, gcs, now: datetime = None) -> dict:
    """Self-healing scheduler — fired every ~15 min by Task Scheduler. Runs any
    phase whose window is open and that hasn't completed for today's session,
    reaching the gateway only when it's actually up. This is the whole answer to
    "run when I log in / catch up if I wasn't logged in": a phase missed because
    the gateway was down runs on the first cycle after login, and per-session
    idempotency means nothing double-fires. Weekends and the kill switch short-
    circuit the entire cycle."""
    now = now or datetime.now()
    if now.weekday() >= 5:
        return {"skipped": "weekend"}
    td = now.date().isoformat()
    # A HALT stops NEW entries (stage/morning) but never the management of the
    # existing book — EOD reconciliation, bar aging, terminal exits and equity
    # snapshots keep running (refined 2026-07-20 after supervisor HALT #5: the
    # original all-phase halt would have frozen the open book's clocks too).
    halted = risk.is_halted(cfg, gcs)
    gateway_up = _tcp_probe(cfg.ib_host, cfg.ib_port, cfg.probe_timeout_s)
    ran = []
    if not halted:
        if _in_window(now, cfg.stage_window):
            if not run_stage(cfg, gcs, today=td).get("skipped"):
                ran.append("stage")
        if _in_window(now, cfg.morning_window) and (cfg.dry_run or gateway_up):
            if not run_morning(cfg, gcs, today=td).get("skipped"):
                ran.append("morning")
    elif _in_window(now, cfg.stage_window) or _in_window(now, cfg.morning_window):
        # log once per session (piggyback the stage idempotency marker)
        state = ledger.read_state(gcs, cfg)
        if not ledger.phase_done(state, "halt_notice", td):
            ledger.log_event(gcs, cfg, "WATCH_HALTED", note="entries blocked; eod continues")
            ledger.mark_phase_done(state, "halt_notice", td)
            ledger.write_state(gcs, cfg, state)
    if _in_window(now, cfg.eod_window) and (cfg.dry_run or gateway_up):
        if not run_eod(cfg, gcs, today=td).get("skipped"):
            ran.append("eod")
    # keep the trade log quiet: only record a WATCH row when something ran, or
    # when live + a trading window is open but the gateway is down (the case worth
    # seeing — "we wanted to act but you weren't logged in")
    window_wants_gateway = (_in_window(now, cfg.morning_window) or _in_window(now, cfg.eod_window))
    if ran or (not cfg.dry_run and not gateway_up and window_wants_gateway):
        ledger.log_event(gcs, cfg, "WATCH", gateway_up=gateway_up, ran=ran or None,
                         halted=halted or None)
    return {"gateway_up": gateway_up, "ran": ran, "halted": halted}
