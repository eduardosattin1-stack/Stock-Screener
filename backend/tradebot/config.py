"""TradeBot configuration — the D10-only 60-bar/+20% sleeve on IBKR.

Every non-obvious value was derived from data, not gut (DESIGN.md §6; workflow
`tradebot-stop-and-entry-optimization`, 2026-07-01):
- NO conventional stop-loss: across 6,815 completed holdout D10 windows, every
  fixed stop from -8% to -60% (and every adaptive k*pred_dd variant) has a
  pessimistic EV below the +8.32%/trade no-stop baseline — 46% of eventual +20%
  touchers breach -15% drawdown before touching. Only a -65% disaster stop
  qualifies (EV cost <=0.22pp); it exists to truncate -70/-90% blowups.
- Entry: next-morning marketable limit at scan_close*1.02. The 2% chase cap
  skips 6.8% of entries and the executed cohort fills at -0.02% vs the scan
  close (gap-downs pay for gap-ups). Overnight-session entry rejected: uncapped
  gap cost is only ~18bp and overnight spreads on these names exceed that.
- Sizing: equity/20 per NEW entry (open positions never resized), floor $1k.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class BotConfig:
    # ── sleeve (the measured strategy; do not tweak without re-running the audit) ──
    regime: str = "p20_60"
    prob_field: str = "hit_prob_60d"
    decile: int = 10
    barrier_mult: float = 1.20          # GTC profit-target limit at fill * 1.20
    window_bars: int = 60               # terminal market exit at trading bar 60
    disaster_stop_frac: float = 0.65    # GTC stop-market at fill * (1 - 0.65)

    # ── entry ladder ──
    chase_cap: float = 0.02             # limit = scan_close * (1 + cap), day order; unfilled -> skip
    use_overnight_entry: bool = False

    # ── sizing ──
    max_slots: int = 20
    slot_floor_usd: float = 1_000.0
    slot_cap_usd: float = 2_000.0
    paper_equity_usd: float = 25_000.0  # DRY-RUN ONLY: sizing basis while the account
                                        # is unfunded, so the rehearsal shows real
                                        # would-be orders; ignored once real equity
                                        # snapshots exist, and never used in live mode
    ramp_slots: int = 10                # half book until ramp_until
    ramp_until: str = ""                # ISO date "YYYY-MM-DD"; "" disables the ramp

    # ── risk gates ──
    sector_cap_slots: int = 4           # max positions per sector (20% of 20)
    min_dollar_volume: float = 5_000_000.0   # scan-day price*volume floor
    daily_loss_halt_frac: float = 0.03  # no new entries if equity is down >3% intraday
    require_health: str = "HEALTHY"     # calibration health gate for the sleeve's regime
    corp_action_max_dev: float = 0.10   # |ibkr_quote/scan_price - 1| beyond this -> skip + flag

    # ── universe hygiene (match the tracked strategy: US-listed, USD) ──
    require_currency: str = "USD"
    allow_dotted_symbols: bool = False  # tracker skips '.' symbols (foreign listings)

    # ── plumbing (GCS is the ledger + kill-switch bus; bot is the single writer) ──
    gcs_bucket: str = "screener-signals-carbonbridge"
    state_path: str = "tradebot/state.json"
    trades_path: str = "tradebot/trades.jsonl"
    halt_path: str = "tradebot/HALT"          # supervisor/manual kill switch (GCS blob)
    local_halt_file: str = "TRADEBOT_HALT"    # kill switch on the gateway PC (same dir as bot)
    scan_path: str = "scans/latest_global.json"
    cal_config_path: str = "calibration_tracking/v2/config.json"
    cal_summary_path: str = "calibration_tracking/v2/summary.json"

    # ── resilience / self-healing catch-up (the --watch phase, fired every ~15
    #    min by Task Scheduler) ─────────────────────────────────────────────────
    # Each phase runs when its window (LOCAL CET HH:MM on the gateway PC) is open
    # AND — for the live gateway-dependent phases — when IBKR is actually
    # reachable + logged in. So if you weren't logged in at the scheduled time,
    # the first --watch cycle after you log in runs the missed phase; every phase
    # is idempotent per US-session date (ledger `completed`), so re-firing never
    # double-executes. CET-anchored: for the ~2 weeks/yr the US springs forward
    # before the EU, the US open is 14:30 CET and morning entries land ~1h late
    # (bounded, captured in entry_slippage_pct).
    stage_window: tuple = ((12, 0), (21, 30))
    eod_window: tuple = ((22, 5), (23, 55))
    # morning_window END is the one STRATEGY knob: how late will the bot still
    # place the day's entries if you logged in late? The fill-timing study
    # (2026-07-01) showed later entry is adverse-selected — by the close eventual
    # winners have already run +2.6% and 59% get cap-skipped, so a very-late fill
    # tends to buy the laggards. Default caps catch-up at ~2h past the open
    # (17:30 CET). Widen toward the close to prioritize "always get exposure";
    # narrow it toward "skip the day if I missed the open".
    morning_window: tuple = ((15, 25), (17, 30))
    probe_timeout_s: float = 3.0   # TCP reachability probe to the gateway socket

    # ── IBKR: same login as the portfolio mirror, one shared gateway instance.
    # The bot uses its own client id and pins every order to the linked bot
    # account. Verify ib_port against the gateway's configured socket port
    # (IB Gateway default: 4001 live / 4002 paper) on the gateway PC. ──
    ib_host: str = "127.0.0.1"
    ib_port: int = 4001
    ib_client_id: int = 7
    ib_account: str = "U26508407"       # the bot's linked account — orders MUST carry this
    dry_run: bool = True                # print orders instead of placing until flipped


# horizon label used by calibration summary.json for each regime
HORIZON_LABEL = {"p10_30": "30d", "p20_60": "60d"}
