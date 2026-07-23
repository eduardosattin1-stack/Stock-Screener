"""Unit tests for the bot's pure logic (no IBKR, no GCS — fake impl)."""
import os
import sys
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradebot.config import BotConfig
from tradebot import signals, risk, ledger
from tradebot.gcs_io import make_fake

EDGES = [0.10, 0.20, 0.28, 0.35, 0.42, 0.48, 0.53, 0.58, 0.63]  # D10 = p > 0.63
CFG = BotConfig()


def stock(sym, p=0.66, price=20.0, sector="Healthcare", volume=1_000_000, **kw):
    s = {"symbol": sym, "hit_prob_60d": p, "price": price, "sector": sector,
         "volume": volume, "currency": "USD"}
    s.update(kw)
    return s


HEALTHY = {"horizons": {"60d": {"health": {"status": "HEALTHY"},
                                "cycle": {"n_matured": 30, "n_touched": 22}}}}  # 8 terminals -> validated
DEGRADED = {"horizons": {"60d": {"health": {"status": "DEGRADED"},
                                 "cycle": {"n_matured": 30, "n_touched": 22}}}}
CENSORED = {"horizons": {"60d": {"health": {"status": "HEALTHY"},
                                 "cycle": {"n_matured": 255, "n_touched": 255}}}}  # touch-only: gate has no teeth


class TestSignals(unittest.TestCase):
    def test_decile_of_edges(self):
        self.assertEqual(signals.decile_of(0.05, EDGES), 1)
        self.assertEqual(signals.decile_of(0.6299, EDGES), 9)
        self.assertEqual(signals.decile_of(0.63, EDGES), 10)  # p == edge -> higher decile (served rule)
        self.assertEqual(signals.decile_of(0.99, EDGES), 10)

    def test_eligibility_filters(self):
        self.assertEqual(signals.eligibility(stock("ABC"), CFG), "")
        self.assertEqual(signals.eligibility(stock("PRX.AS"), CFG), "dotted-symbol")
        self.assertEqual(signals.eligibility(stock("ABC", currency="EUR"), CFG), "currency")
        self.assertEqual(signals.eligibility(stock("ABC", p=0.0), CFG), "no-probability")
        # $5M dollar-volume floor: 20.0 * 100_000 = $2M -> reject
        self.assertEqual(signals.eligibility(stock("ABC", volume=100_000), CFG), "dollar-volume")

    def test_selection_decile_dedup_and_ranking(self):
        stocks = [
            stock("HELD", p=0.70),
            stock("PEND", p=0.70),
            stock("LOWP", p=0.50),                      # D7 — excluded
            stock("NOEDGE", p=0.64),
            stock("EDGY", p=0.64, vol_adj_edge_60d=0.12),
            stock("BIGP", p=0.72),
        ]
        picked = signals.select_candidates(stocks, EDGES, CFG, {"HELD"}, {"PEND"}, {}, 10)
        syms = [c["symbol"] for c in picked]
        self.assertEqual(syms, ["EDGY", "BIGP", "NOEDGE"])  # edge first, then p desc

    def test_sector_cap(self):
        stocks = [stock(f"H{i}", p=0.70 - i * 0.001) for i in range(6)] + \
                 [stock("TECH1", p=0.65, sector="Technology")]
        picked = signals.select_candidates(stocks, EDGES, CFG, set(), set(), {"Healthcare": 2}, 10)
        hc = [c for c in picked if c["sector"] == "Healthcare"]
        self.assertEqual(len(hc), CFG.sector_cap_slots - 2)  # 2 already held/pending
        self.assertIn("TECH1", [c["symbol"] for c in picked])

    def test_slots_free_limit(self):
        stocks = [stock(f"S{i}", p=0.70, sector=f"Sec{i}") for i in range(8)]
        self.assertEqual(len(signals.select_candidates(stocks, EDGES, CFG, set(), set(), {}, 3)), 3)
        self.assertEqual(signals.select_candidates(stocks, EDGES, CFG, set(), set(), {}, 0), [])

    def test_health_status(self):
        self.assertEqual(signals.health_status(HEALTHY, CFG), "HEALTHY")
        self.assertEqual(signals.health_status(DEGRADED, CFG), "DEGRADED")
        self.assertEqual(signals.health_status({}, CFG), "UNKNOWN")


class TestRisk(unittest.TestCase):
    def setUp(self):
        self.gcs = make_fake({})

    def gates(self, summary=HEALTHY, equity=25_000, day_start=25_000, n_open=0,
              n_pending=0, cfg=CFG):
        return risk.entry_gates(cfg, self.gcs, {}, summary, equity, day_start,
                                n_open, n_pending, today="2026-07-02")

    def test_all_pass_baseline(self):
        self.assertTrue(risk.all_pass(self.gates()))

    def test_kill_switch_blocks(self):
        self.gcs["write"]("tradebot/HALT", "halted by supervisor")
        gates = self.gates()
        self.assertFalse(risk.all_pass(gates))
        self.assertFalse(dict((g[0], g[1]) for g in gates)["kill-switch"])

    def test_health_gate_blocks(self):
        self.assertFalse(risk.all_pass(self.gates(summary=DEGRADED)))

    def test_censored_healthy_does_NOT_block_rehearsal_entries(self):
        """Corrected 2026-07-23: HEALTHY certified on touch-only (fully
        censored) data is a LIVE-readiness concern, not a rehearsal-integrity
        one — entry_gates() (shared by dry-run staging) must NOT block on it.
        The original fix (blocking entries) repeated the exact category error
        HALT #5 made: stopping a costless test over a real-money concern."""
        gates = self.gates(summary=CENSORED)
        self.assertTrue(risk.all_pass(gates))
        d = dict((g[0], g[1]) for g in gates)
        self.assertTrue(d["calibration-health"])          # nominal health says HEALTHY
        self.assertNotIn("calibration-validated", d)      # no longer a per-entry gate at all

    def test_calibration_validated_standalone_for_live_startup_only(self):
        """The real check still exists — just relocated to gate LIVE startup
        (run_bot.py), not the shared entry path. Verified here as a pure
        function; the LIVE-refusal wiring itself is smoke-tested via --watch."""
        ok, detail = risk.calibration_validated(CENSORED, CFG)
        self.assertFalse(ok)
        self.assertIn("0 terminal outcomes", detail)
        ok2, detail2 = risk.calibration_validated(HEALTHY, CFG)
        self.assertTrue(ok2)
        self.assertIn("terminal outcome", detail2)
        ok3, detail3 = risk.calibration_validated({"horizons": {"60d": {"health": {"status": "HEALTHY"}}}}, CFG)
        self.assertFalse(ok3)  # missing cycle block -> not validated, fails safe

    def test_slots_gate(self):
        self.assertFalse(risk.all_pass(self.gates(n_open=18, n_pending=2)))
        self.assertTrue(risk.all_pass(self.gates(n_open=18, n_pending=1)))

    def test_daily_loss_halt(self):
        self.assertFalse(risk.all_pass(self.gates(equity=24_000, day_start=25_000)))  # -4%
        self.assertTrue(risk.all_pass(self.gates(equity=24_400, day_start=25_000)))   # -2.4%

    def test_slot_sizing(self):
        self.assertEqual(risk.slot_size_usd(25_000, CFG), 1_250.0)
        self.assertEqual(risk.slot_size_usd(50_000, CFG), 2_000.0)   # capped
        self.assertEqual(risk.slot_size_usd(15_000, CFG), 0.0)       # below $1k floor
        # ramp halves the BOOK, not the slot size
        cfg = BotConfig(ramp_until="2026-07-15")
        self.assertEqual(risk.max_open_slots(cfg, "2026-07-10"), cfg.ramp_slots)
        self.assertEqual(risk.max_open_slots(cfg, "2026-07-16"), cfg.max_slots)
        self.assertEqual(risk.slot_size_usd(25_000, cfg, "2026-07-10"), 1_250.0)

    def test_corp_action_guard(self):
        self.assertTrue(risk.corp_action_guard(20.0, 20.5, CFG))
        self.assertFalse(risk.corp_action_guard(46.84, 138.47, CFG))  # the DD case
        self.assertFalse(risk.corp_action_guard(20.0, 0.0, CFG))


class TestLedger(unittest.TestCase):
    def setUp(self):
        self.store = {}
        self.gcs = make_fake(self.store)

    def test_state_roundtrip(self):
        state = ledger.read_state(self.gcs, CFG)
        self.assertEqual(state["positions"], [])
        ledger.write_state(self.gcs, CFG, state)
        self.assertEqual(ledger.read_state(self.gcs, CFG)["positions"], [])

    def test_fill_flow_and_slippage(self):
        state = ledger.read_state(self.gcs, CFG)
        cand = {"symbol": "ABSI", "sector": "Healthcare", "p": 0.68, "price": 10.00}
        ledger.stage_pending(state, cand, qty=125, limit_price=10.20, scan_date="2026-07-01")
        self.assertEqual(len(state["pending_entries"]), 1)
        pos = ledger.record_fill(state, CFG, "ABSI", fill_price=10.05, qty=125,
                                 fill_date="2026-07-02")
        self.assertEqual(state["pending_entries"], [])
        self.assertEqual(pos["target_price"], round(10.05 * 1.20, 4))
        self.assertEqual(pos["stop_price"], round(10.05 * 0.35, 4))
        self.assertEqual(pos["entry_slippage_pct"], 0.5)
        closed = ledger.close_position(state, "ABSI", 12.06, "2026-07-20", "TARGET")
        self.assertEqual(closed["realized_pct"], 20.0)
        self.assertEqual(ledger.open_positions(state), [])

    def test_sector_counts_includes_pending(self):
        state = ledger.read_state(self.gcs, CFG)
        ledger.stage_pending(state, {"symbol": "A", "sector": "Tech", "p": .7, "price": 5},
                             10, 5.1, "2026-07-01")
        cand = {"symbol": "B", "sector": "Tech", "p": .7, "price": 5}
        ledger.stage_pending(state, cand, 10, 5.1, "2026-07-01")
        ledger.record_fill(state, CFG, "B", 5.0, 10, "2026-07-02")
        self.assertEqual(ledger.sector_counts(state), {"Tech": 2})

    def test_equity_history_and_day_start(self):
        state = ledger.read_state(self.gcs, CFG)
        ledger.equity_snapshot(state, 25_000, 5_000, "2026-07-01")
        ledger.equity_snapshot(state, 25_500, 4_000, "2026-07-02")
        self.assertEqual(ledger.day_start_equity(state, "2026-07-02"), 25_000)
        self.assertEqual(ledger.day_start_equity(state, "2026-07-01"), 0.0)
        ledger.equity_snapshot(state, 26_000, 4_100, "2026-07-02")  # same-day upsert
        self.assertEqual(len(state["equity_history"]), 2)

    def test_trade_log_appends(self):
        ledger.log_event(self.gcs, CFG, "ENTRY_SKIPPED", symbol="XYZ", reason="gap>cap")
        ledger.log_event(self.gcs, CFG, "FILL", symbol="ABC", price=10.0)
        rows = self.store[CFG.trades_path].strip().splitlines()
        self.assertEqual(len(rows), 2)


class TestExecution(unittest.TestCase):
    def setUp(self):
        # hermetic: never attempt a real gateway connection from unit tests
        from tradebot import execution as ex
        self._orig_connect = ex._try_connect
        ex._try_connect = lambda cfg: None

    def tearDown(self):
        from tradebot import execution as ex
        ex._try_connect = self._orig_connect

    def test_qty_sizing(self):
        from tradebot import execution as ex
        self.assertEqual(ex.qty_for(1_250, 10.20), 122)
        self.assertEqual(ex.qty_for(1_250, 1_300.0), 0)   # too expensive for the slot
        self.assertEqual(ex.qty_for(0, 10.0), 0)

    def test_entry_and_exit_specs(self):
        from tradebot import execution as ex
        cand = {"symbol": "ABSI", "price": 10.00, "sector": "Healthcare", "p": 0.68}
        entry = ex.build_entry(CFG, cand, 122)
        self.assertEqual(entry["limit"], 10.20)            # close * 1.02 chase cap
        self.assertEqual(entry["tif"], "DAY")
        self.assertEqual(entry["account"], CFG.ib_account)
        target, stop = ex.build_exit_pair(CFG, "ABSI", 122, 10.05, "20260702")
        self.assertEqual(target["limit"], 12.06)           # fill * 1.20
        self.assertEqual(stop["stop"], 3.52)               # fill * 0.35 disaster stop
        self.assertEqual(target["ocaGroup"], stop["ocaGroup"])
        self.assertEqual(target["tif"], "GTC")
        term = ex.build_terminal_exit(CFG, "ABSI", 122)
        self.assertEqual((term["type"], term["tif"]), ("MKT", "OPG"))

    def test_terminal_due_and_exit_detection(self):
        from tradebot import execution as ex
        pos = {"status": "OPEN", "bar_count": 59}
        self.assertFalse(ex.due_terminal(pos, CFG))
        pos["bar_count"] = 60
        self.assertTrue(ex.due_terminal(pos, CFG))
        opens = [{"symbol": "A"}, {"symbol": "B"}]
        self.assertEqual(ex.detect_exits(opens, {"A": 100}), [{"symbol": "B"}])

    def test_classify_exit(self):
        from tradebot import execution as ex
        pos = {"target_price": 12.06, "stop_price": 3.52}
        self.assertEqual(ex.classify_exit(pos, 12.06), "TARGET")
        self.assertEqual(ex.classify_exit(pos, 3.50), "DISASTER_STOP")
        self.assertEqual(ex.classify_exit(pos, 9.10), "TERMINAL")

    def test_stage_pipeline_dry(self):
        """End-to-end --stage against fake GCS: gates -> selection -> staged pending."""
        from tradebot import execution as ex
        store = {}
        gcs = make_fake(store)
        gcs["write"](CFG.cal_summary_path, HEALTHY)
        gcs["write"](CFG.cal_config_path, {"decile_thresholds": {"p20_60": EDGES}})
        gcs["write"](CFG.scan_path, {"scan_date": "2026-07-02", "stocks": [
            stock("AAA", p=0.70), stock("BBB", p=0.66, sector="Technology"),
            stock("LOW", p=0.30),
        ]})
        # seed equity so slot sizing works
        state = ledger.read_state(gcs, CFG)
        ledger.equity_snapshot(state, 25_000, 25_000, "2026-07-01")
        ledger.write_state(gcs, CFG, state)

        out = ex.run_stage(CFG, gcs)
        self.assertEqual(out, {"staged": 2, "blocked": False})
        state = ledger.read_state(gcs, CFG)
        syms = {p["symbol"] for p in state["pending_entries"]}
        self.assertEqual(syms, {"AAA", "BBB"})
        self.assertEqual(state["pending_entries"][0]["limit_price"],
                         round(20.0 * 1.02, 2))
        # idempotent per session: a second run today short-circuits
        out2 = ex.run_stage(CFG, gcs)
        self.assertEqual(out2.get("skipped"), "stage done today")

    def test_stage_paper_equity_when_unfunded_dry_run(self):
        """No equity snapshot + dry-run -> sizes off paper_equity_usd and stages."""
        from tradebot import execution as ex
        store = {}
        gcs = make_fake(store)
        gcs["write"](CFG.cal_summary_path, HEALTHY)
        gcs["write"](CFG.cal_config_path, {"decile_thresholds": {"p20_60": EDGES}})
        gcs["write"](CFG.scan_path, {"scan_date": "2026-07-02",
                                     "stocks": [stock("AAA", p=0.70)]})
        out = ex.run_stage(CFG, gcs)  # no equity_snapshot seeded at all
        self.assertEqual(out, {"staged": 1, "blocked": False})
        pend = ledger.read_state(gcs, CFG)["pending_entries"][0]
        # slot = 25k/20 = $1,250 at limit 20.40 -> 61 shares
        self.assertEqual(pend["qty"], 61)
        self.assertIn('"paper_equity": true', store[CFG.trades_path])
        # LIVE mode with no equity must still block (fresh state — idempotency
        # would otherwise short-circuit the second run)
        import dataclasses
        live_cfg = dataclasses.replace(CFG, dry_run=False)
        store2 = {}
        gcs2 = make_fake(store2)
        gcs2["write"](CFG.cal_summary_path, HEALTHY)
        gcs2["write"](CFG.cal_config_path, {"decile_thresholds": {"p20_60": EDGES}})
        gcs2["write"](CFG.scan_path, {"stocks": [stock("AAA", p=0.70)]})
        out2 = ex.run_stage(live_cfg, gcs2)
        self.assertTrue(out2.get("blocked"))

    def test_stage_blocked_by_halt(self):
        from tradebot import execution as ex
        store = {}
        gcs = make_fake(store)
        gcs["write"](CFG.cal_summary_path, HEALTHY)
        gcs["write"](CFG.cal_config_path, {"decile_thresholds": {"p20_60": EDGES}})
        gcs["write"](CFG.scan_path, {"stocks": [stock("AAA", p=0.70)]})
        gcs["write"](CFG.halt_path, "halt")
        state = ledger.read_state(gcs, CFG)
        ledger.equity_snapshot(state, 25_000, 25_000, "2026-07-01")
        ledger.write_state(gcs, CFG, state)
        out = ex.run_stage(CFG, gcs)
        self.assertTrue(out["blocked"])
        self.assertEqual(ledger.read_state(gcs, CFG)["pending_entries"], [])

    def test_morning_dry_run_fills_and_brackets(self):
        from tradebot import execution as ex
        store = {}
        gcs = make_fake(store)
        gcs["write"](CFG.cal_summary_path, HEALTHY)
        state = ledger.read_state(gcs, CFG)
        ledger.equity_snapshot(state, 25_000, 25_000, "2026-07-01")
        ledger.stage_pending(state, {"symbol": "AAA", "sector": "Healthcare",
                                     "p": 0.7, "price": 20.0}, 62, 20.40, "2026-07-01")
        ledger.write_state(gcs, CFG, state)
        out = ex.run_morning(CFG, gcs)
        self.assertEqual(out["filled"], 1)
        state = ledger.read_state(gcs, CFG)
        self.assertEqual(len(ledger.open_positions(state)), 1)
        pos = ledger.open_positions(state)[0]
        self.assertEqual(pos["target_price"], 24.0)
        self.assertEqual(pos["stop_price"], 7.0)
        # trade log carries the dry-run order specs (entry pair)
        self.assertIn("ORDER_DRY", store[CFG.trades_path])


class TestIdempotencyHelpers(unittest.TestCase):
    def test_phase_done_roundtrip(self):
        state = dict(ledger.EMPTY_STATE, completed={})
        self.assertFalse(ledger.phase_done(state, "stage", "2026-07-06"))
        ledger.mark_phase_done(state, "stage", "2026-07-06")
        self.assertTrue(ledger.phase_done(state, "stage", "2026-07-06"))
        self.assertFalse(ledger.phase_done(state, "stage", "2026-07-07"))  # next session
        self.assertFalse(ledger.phase_done(state, "morning", "2026-07-06"))

    def test_in_window(self):
        from tradebot import execution as ex
        w = ((15, 25), (17, 30))
        self.assertTrue(ex._in_window(datetime(2026, 7, 6, 15, 30), w))
        self.assertTrue(ex._in_window(datetime(2026, 7, 6, 15, 25), w))
        self.assertTrue(ex._in_window(datetime(2026, 7, 6, 17, 30, 30), w))
        self.assertFalse(ex._in_window(datetime(2026, 7, 6, 15, 24), w))
        self.assertFalse(ex._in_window(datetime(2026, 7, 6, 17, 31), w))


class TestWatch(unittest.TestCase):
    MON_MORNING = datetime(2026, 7, 6, 15, 30)   # Monday, inside the morning window
    MON_EOD = datetime(2026, 7, 6, 22, 30)        # Monday, inside the eod window
    SAT = datetime(2026, 7, 4, 15, 30)            # Saturday

    def setUp(self):
        from tradebot import execution as ex
        self._c, self._p = ex._try_connect, ex._tcp_probe
        ex._try_connect = lambda cfg: None          # never a real IB in tests
        ex._tcp_probe = lambda *a, **k: True         # gateway "listening" by default
        self.store = {}
        self.gcs = make_fake(self.store)
        self.gcs["write"](CFG.cal_summary_path, HEALTHY)
        self.gcs["write"](CFG.cal_config_path, {"decile_thresholds": {"p20_60": EDGES}})
        self.gcs["write"](CFG.scan_path, {"scan_date": "2026-07-06", "stocks": [
            stock("AAA", p=0.70), stock("BBB", p=0.66, sector="Technology")]})

    def tearDown(self):
        from tradebot import execution as ex
        ex._try_connect, ex._tcp_probe = self._c, self._p

    def test_weekend_short_circuits(self):
        from tradebot import execution as ex
        self.assertEqual(ex.run_watch(CFG, self.gcs, now=self.SAT), {"skipped": "weekend"})

    def test_halt_blocks_entries_but_eod_continues(self):
        """Refined halt scope: entries stop, book management never does."""
        from tradebot import execution as ex
        self.gcs["write"](CFG.halt_path, "halted")
        # morning window: nothing runs, notice logged once
        out = ex.run_watch(CFG, self.gcs, now=self.MON_MORNING)
        self.assertEqual((out["halted"], out["ran"]), (True, []))
        self.assertIn("WATCH_HALTED", self.store[CFG.trades_path])
        self.assertNotIn("STAGED", self.store[CFG.trades_path])
        # eod window with an open position: EOD still runs and ages the book
        state = ledger.read_state(self.gcs, CFG)
        ledger.stage_pending(state, {"symbol": "AAA", "sector": "Tech", "p": .7, "price": 20},
                             10, 20.4, "2026-07-06")
        ledger.record_fill(state, CFG, "AAA", 20.0, 10, "2026-07-06")
        ledger.write_state(self.gcs, CFG, state)
        out2 = ex.run_watch(CFG, self.gcs, now=self.MON_EOD)
        self.assertIn("eod", out2["ran"])
        pos = ledger.open_positions(ledger.read_state(self.gcs, CFG))[0]
        self.assertEqual(pos["bar_count"], 1)

    def test_market_open_from_hours(self):
        from tradebot import execution as ex
        hrs = "20260720:0930-20260720:1600;20260721:CLOSED"
        self.assertTrue(ex.market_open_from_hours(hrs, "20260720"))
        self.assertFalse(ex.market_open_from_hours(hrs, "20260721"))
        self.assertTrue(ex.market_open_from_hours(hrs, "20260722"))  # absent -> fail open
        self.assertTrue(ex.market_open_from_hours("", "20260720"))

    def test_dry_cycle_stages_enters_then_idempotent(self):
        from tradebot import execution as ex
        out = ex.run_watch(CFG, self.gcs, now=self.MON_MORNING)
        self.assertEqual(set(out["ran"]), {"stage", "morning"})
        state = ledger.read_state(self.gcs, CFG)
        self.assertEqual(len(ledger.open_positions(state)), 2)
        self.assertEqual(state["completed"]["stage"], "2026-07-06")
        self.assertEqual(state["completed"]["morning"], "2026-07-06")
        # a second cycle the same session does nothing
        out2 = ex.run_watch(CFG, self.gcs, now=self.MON_MORNING)
        self.assertEqual(out2["ran"], [])
        self.assertEqual(len(ledger.open_positions(ledger.read_state(self.gcs, CFG))), 2)

    def test_live_gateway_down_defers_morning_but_stages(self):
        from tradebot import execution as ex
        import dataclasses
        live = dataclasses.replace(CFG, dry_run=False)
        state = ledger.read_state(self.gcs, CFG)      # fund it so live stage can size
        ledger.equity_snapshot(state, 25_000, 25_000, "2026-07-03")
        ledger.write_state(self.gcs, CFG, state)
        ex._tcp_probe = lambda *a, **k: False        # not listening
        out = ex.run_watch(live, self.gcs, now=self.MON_MORNING)
        self.assertEqual(out["ran"], ["stage"])       # stage needs no gateway
        state = ledger.read_state(self.gcs, CFG)
        self.assertEqual(state["completed"].get("stage"), "2026-07-06")
        self.assertIsNone(state["completed"].get("morning"))   # deferred, not done
        self.assertEqual(len(state["pending_entries"]), 2)      # held for retry
        self.assertIn("WATCH", self.store[CFG.trades_path])     # logged the down-gateway window
        # socket now open but full login still fails (test) -> morning still defers, no dupes
        ex._tcp_probe = lambda *a, **k: True
        out2 = ex.run_watch(live, self.gcs, now=self.MON_MORNING)
        self.assertEqual(out2["ran"], [])
        self.assertIsNone(ledger.read_state(self.gcs, CFG)["completed"].get("morning"))

    def test_eod_advances_bars_exactly_once(self):
        from tradebot import execution as ex
        state = ledger.read_state(self.gcs, CFG)
        ledger.stage_pending(state, {"symbol": "AAA", "sector": "Tech", "p": .7, "price": 20},
                             10, 20.4, "2026-07-06")
        ledger.record_fill(state, CFG, "AAA", 20.0, 10, "2026-07-06")
        ledger.write_state(self.gcs, CFG, state)
        ex.run_watch(CFG, self.gcs, now=self.MON_EOD)
        b1 = ledger.open_positions(ledger.read_state(self.gcs, CFG))[0]["bar_count"]
        ex.run_watch(CFG, self.gcs, now=self.MON_EOD)   # same session — must not double-count
        b2 = ledger.open_positions(ledger.read_state(self.gcs, CFG))[0]["bar_count"]
        self.assertEqual((b1, b2), (1, 1))

    def test_stale_pending_expired_at_stage(self):
        from tradebot import execution as ex
        state = ledger.read_state(self.gcs, CFG)
        ledger.stage_pending(state, {"symbol": "OLD", "sector": "Tech", "p": .7, "price": 9},
                             5, 9.2, "2026-06-01")   # a prior session's un-entered pending
        ledger.write_state(self.gcs, CFG, state)
        ex.run_stage(CFG, self.gcs, today="2026-07-06")
        syms = {p["symbol"] for p in ledger.read_state(self.gcs, CFG)["pending_entries"]}
        self.assertNotIn("OLD", syms)
        self.assertIn("ENTRY_EXPIRED", self.store[CFG.trades_path])


if __name__ == "__main__":
    unittest.main(verbosity=2)
