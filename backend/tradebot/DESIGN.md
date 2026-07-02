# TradeBot — automated D10 sleeve on IBKR

**Status:** design agreed 2026-07-01; parameters being finalized from data (see §6).
**Owner:** Bruno. **Boundary:** Claude writes/tests the code; orders are only ever placed by the
deployed bot on the gateway PC, under the kill-switch. No Claude session places trades directly.

## 1. What it trades (decided)

- **Sleeve:** decile-10 picks only, **60-bar / +20% barrier** regime (`p20_60`) — the audited best
  variant (holdout: EV +8.5%/trade, ~8.5 turns/yr, +99% gross / +93% net CAGR in the evidence
  window; honest through-cycle estimate 15–45% net).
- **Account:** separate IBKR account, **real money from day one at tiny size** (Bruno's call),
  ~$15–50k → 15–25 slots of ~$1–2k. Ramp rule: first 2 weeks at half slot-count while fill
  mechanics are audited.
- **Exit:** GTC limit at entry×1.20 (the barrier), OCA-paired with a stop (level from §6), plus a
  time exit at bar 60 (terminal). No discretionary exits.

## 2. Architecture

```
nightly scan (GCS) ──> signals.py ──> execution.py (ib_insync, gateway PC) ──> ledger.py (GCS)
 latest_global.json     D10 p20_60        entry ladder + OCA brackets            bot/state.json
 calibration summary    health gate,      terminal time-exits                    trades.jsonl
 (HEALTHY required)     dedup, caps                                              slippage metrics
                              │
                        risk.py gates every order:
                        kill-switch file · max slots · slot size · sector cap (~40%)
                        daily-loss halt · drawdown halt · no margin · cash buffer
                              │
                        supervisor (nightly `claude -p`, like opus_strategist):
                        audits fills vs model, realized-vs-model divergence,
                        corporate-action anomalies (the DD/MQ class) → report to GCS;
                        may create HALT file; never places or modifies orders
```

- Runs on the **gateway PC** beside the existing IB Gateway. The bot account likely needs a
  **second IB Gateway instance** (own port, e.g. 4003) if it's a separate username — verify at
  deploy; if it's a linked account under the same login, pin orders to the bot account ID.
- Windows Task Scheduler entries (same pattern as the portfolio mirror / SpeculairWeekly):
  `--stage` **12:00 CET** (the nightly scan completes 04:05–04:30 UTC ≈ 06:30 CET with the prior
  US session's closes — verified from GCS archive timestamps; noon gives >5h margin),
  `--morning` 15:25 CET (09:25 ET, the scan's "next trading day open"), `--eod` 22:15 CET,
  supervisor 23:00 CET.

## 3. Entry ladder (the close-vs-next-morning gap)

The tracked strategy enters at the scan-day close; a live bot can't. Tiers:

1. **Overnight session** (IBKR overnight venue / Blue Ocean ATS, 20:00–03:50 ET, exchange
   `OVERNIGHT`): limit ≤ close×1.005 for names available there. Fills ≈ the tracked entry.
   Thin liquidity, large-cap skew — many D10 names won't be tradable; that's fine, it's tier 1.
2. **09:30 ET marketable limit capped at close×(1+chase_cap)** via IBKR Adaptive algo. The
   "price-pressure timing" is the algo's job — mechanical, not an LLM watching ticks.
3. **Gap beyond the chase cap → skip and log.** The model's `p` was priced off the close; a +5%
   gap is a different, unmeasured trade. Skipped-entry log feeds the supervisor report.

Chase-cap value and whether tier 1 is worth the complexity: set by the entry-gap study (§6).

## 4. Signal selection (`signals.py`)

- Source: nightly `scans/latest_global.json`; regime fields `hit_prob_60d` → decile via the served
  `calibration_tracking/v2/config.json` thresholds (`p20_60`) — decile 10 only.
- **Gates, in order:** calibration health for `p20_60` must be HEALTHY (the summary.json
  kill-switch metric); symbol not already held and no working entry order; sector cap ~40%
  (D10 runs ~63% healthcare+spec-tech — the cap forces some diversification); min dollar-volume
  filter (value from §6); slots available.
- **Ranking when signals exceed slots:** highest `vol_adj_edge_60d`, tiebreak higher `p`.
- Corporate-action guard: if the scan price differs from the IBKR quote by >10%, do not trade;
  flag to supervisor (the DD/MQ artifact class).

## 5. What the supervisor does NOT do

No discretionary entries, exits, or sizing. The measured edge is the *discipline*; an LLM
improvising trades would be a different, unvalidated strategy. Its powers: read everything,
write reports, and halt (create the kill-switch file). A pre-market news veto (skip a name with
a binary event before entry) is a possible later addition — off by default.

## 6. Data-derived parameters (workflow `tradebot-stop-and-entry-optimization`)

| Parameter | Source | Value (final, 2026-07-01) |
|---|---|---|
| Stop-loss policy | Holdout EV bounds over 6,815 D10 windows | **NO conventional stop.** Every fixed stop −8%..−60% and every adaptive k×pred_dd has pessimistic EV below the +8.32%/trade no-stop baseline (46% of eventual touchers breach −15% pre-touch; −15% stop EV = +1.07%). Ship a single **−65% disaster stop** (EV cost ≤0.22pp; truncates −70/−90% blowups). Revisit tighter stops only with daily-path FMP replay evidence. |
| Chase cap % | 176 live records, FMP opens vs scan closes | **+2%.** Mean gap +0.18%, 40% gap down; the 2% cap skips 6.8% of entries and executed fills average −0.02% vs scan close (free). Touch-rate impact of open-based entry ≈ 0pp. |
| Overnight tier | Same study | **OFF.** Uncapped gap cost ~18bp/trade; overnight spreads on these names exceed it. Morning marketable limit only — simpler bot. |
| Max slots / slot size | Signal-pace check vs capital | **20 slots**, each sized at current_equity/20 at entry (floor $1k, cap $2k). Candidates from the **standing nightly D10 book** (~58 names), not only newly staged tracker records (new-name flow is lumpy: ~0.2/day in droughts). Time-to-full-book ~1-5 sessions. |
| Sector cap | D10 concentration (63% healthcare+tech) | **4 slots/sector** (20%). |
| Min dollar-volume | Liquidity spot-check | **$5M/day** (scan-day price×volume; D9/D10 p10 ≈ $19M so this excludes little while protecting the 40bps slippage assumption). |
| Expected performance | Honest range, net | **50–85%/yr in a holdout-like rally tape; 10–40%/yr through-cycle.** Do not budget off the 90%+ gross figure. |

Note from verification: `expected_dd_60d` is NOT reliably present in live-staged records —
the bot must not depend on it (it doesn't; the disaster stop is fixed-fraction).

Key prior finding shaping the stop analysis: these are 25–30% predicted-drawdown names and many
eventual touchers first draw down 10–15% — a naive tight stop stops out winners and can turn the
EV negative. The stop must clear a pessimistic bound (assume every toucher whose drawdown
breached the stop was stopped *before* touching) to be adopted; otherwise ship a disaster-only
stop.

## 7. Honesty metrics (built in from day one)

- **Entry slippage:** realized fill vs scan close, per trade and cumulative.
- **Realized-vs-model:** bot P&L vs the calibration tracker's paper outcome for the same picks.
- **Skipped-entry cost:** what the gap-skipped trades would have done (measured, so the chase cap
  can be re-tuned from evidence).
- First live TERMINAL resolutions (~mid-July) are the go/no-go gate for scaling past tiny size:
  live E[loss|no-touch] must not be materially worse than the holdout's −20.8%.

## 8. Build order — status 2026-07-02

1. ✅ §6 workflow → final parameters (table above).
2. ✅ `config.py`, `signals.py`, `risk.py`, `ledger.py` + 25 unit tests (fake-GCS pattern).
3. ✅ `execution.py` (three phases, dry-run default, order specs as testable dicts) +
   `gateway_smoke.py`. Real-data smoke passed: stage correctly gate-blocked on the
   unfunded account; state + audit log live at GCS `tradebot/`.
4. ✅ `SUPERVISOR.md` + `run_supervisor.ps1` + `run_tradebot.ps1` (schtasks commands in
   the file headers — Bruno runs them once, elevated, on the gateway PC).
5. ⬜ GO-LIVE CHECKLIST (in order):
   a. Bruno funds U26508407.
   b. Pull repo on the gateway PC; verify `cfg.ib_port` matches the gateway's API socket
      port; `python -m tradebot.gateway_smoke` must PASS.
   c. Register the 4 scheduled tasks (headers of the two .ps1 files).
   d. Run 2-3 days in dry-run (no LIVE.flag): staging + morning + eod cycle against real
      data, supervisor reports arriving nightly at GCS `tradebot/reports/`.
   e. Set `ramp_until` (config) to ~2 weeks out; create `LIVE.flag` in this directory.
   f. Scale past the ramp only after the first live TERMINAL cohort (~mid-July) confirms
      E[loss|no-touch] is not materially worse than the holdout's −20.8%.
