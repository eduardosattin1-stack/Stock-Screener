#!/usr/bin/env python3
"""
test_calibration_tracker.py — pure-math unit tests for calibration_tracker.py
==============================================================================
No network: the GCS layer is swapped for a dict-backed FakeGCS and the
ThetaData fetcher for a FakeBarFeed (calibration_tracker._gcs_impl /
calibration_tracker._fetch_impl are injectable by design).

Run:  python backend/test_calibration_tracker.py
"""

import json
import math
import os
import sys
import unittest
from datetime import datetime, timedelta

BACKEND = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND)

import calibration_tracker as ct  # noqa: E402

P = ct.CAL_PREFIX

# Calendar facts used throughout: 2026-06-05 = Friday, 06-06 = Saturday,
# 06-08 = Monday, 06-09 = Tuesday, 06-10 = Wednesday.
FRI = "2026-06-05"
SAT = "2026-06-06"
MON = "2026-06-08"
TUE = "2026-06-09"
WED = "2026-06-10"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeGCS:
    """Dict-backed stand-in for the GCS layer (stores text, like the bucket)."""

    def __init__(self):
        self.store = {}

    def read(self, path, default=None):
        if path not in self.store:
            return default
        try:
            return json.loads(self.store[path])
        except Exception:
            return default

    def read_text(self, path, default=""):
        return self.store.get(path, default)

    def write(self, path, data, content_type="application/json"):
        self.store[path] = data if isinstance(data, str) else json.dumps(data, default=str)
        return True

    def append_jsonl(self, path, rows):
        if not rows:
            return True
        existing = self.store.get(path, "")
        if existing and not existing.endswith("\n"):
            existing += "\n"
        self.store[path] = existing + "".join(json.dumps(r, default=str) + "\n" for r in rows)
        return True

    def list(self, prefix):
        return sorted(k for k in self.store if k.startswith(prefix))

    def impl(self):
        return {"read": self.read, "read_text": self.read_text, "write": self.write,
                "append_jsonl": self.append_jsonl, "list": self.list}

    def jsonl(self, path):
        return [json.loads(l) for l in self.store.get(path, "").splitlines() if l.strip()]


class FakeBarFeed:
    """fetch(symbol, start_iso, end_iso) -> bars within range."""

    def __init__(self):
        self.bars = {}

    def add(self, symbol, *bars):
        self.bars.setdefault(symbol, []).extend(bars)
        self.bars[symbol].sort(key=lambda b: b["date"])

    def fetch(self, symbol, start, end):
        return [b for b in self.bars.get(symbol, []) if start <= b["date"] <= end]


def bar(d, h, l, c, o=None):
    return {"date": d, "open": o if o is not None else c, "high": float(h),
            "low": float(l), "close": float(c)}


def stock(sym, p10=0.0, p20=0.0, sector="Tech"):
    return {"symbol": sym, "hit_prob_10pct_30d": p10, "hit_prob_60d": p20,
            "sector": sector, "price": 100.0}


def weekdays(start_iso, n):
    d = datetime.strptime(start_iso, "%Y-%m-%d").date()
    out = []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def make_config():
    ramp30 = [0.5 * (k + 1) / 30 for k in range(30)]   # F_pooled(30) = 0.5
    ramp60 = [0.6 * (k + 1) / 60 for k in range(60)]   # F_pooled(60) = 0.6
    edges = [round(0.1 * i, 4) for i in range(1, 10)]  # deciles at 0.1 steps
    return {
        "created_at": "2026-06-01T00:00:00+00:00",
        "model_version": "v4.0",
        "trained_through": "2025-06-01",
        "decile_threshold_source": "v4 OOS holdout (test fixture)",
        "decile_thresholds": {"p10_30": edges, "p20_60": edges},
        "baselines": {"p10_30": [0.05 * i for i in range(1, 11)],
                      "p20_60": [0.05 * i for i in range(1, 11)]},
        "touch_cdf": {"p10_30": {"pooled": ramp30, "by_decile": {}},
                      "p20_60": {"pooled": ramp60, "by_decile": {}}},
        "kill_switch": {"z_degraded": -3, "z_drifting": -2, "min_n_eff": 30},
        "universe_filter": "thetadata_us_coverage",
    }


class TrackerTestCase(unittest.TestCase):
    def setUp(self):
        self.fake = FakeGCS()
        self.feed = FakeBarFeed()
        self._old_gcs = ct._gcs_impl
        self._old_fetch = ct._fetch_impl
        ct._gcs_impl = self.fake.impl()
        ct._fetch_impl = self.feed.fetch
        self.fake.write(f"{P}/config.json", make_config())

    def tearDown(self):
        ct._gcs_impl = self._old_gcs
        ct._fetch_impl = self._old_fetch

    def pending(self):
        doc = self.fake.read(f"{P}/pending_entries.json", {"pending": []})
        return doc.get("pending", [])

    def open_records(self, regime):
        return self.fake.read(f"{P}/{regime}/open_state.json", {"records": []}).get("records", [])

    def summary(self):
        return self.fake.read(f"{P}/summary.json")


# ---------------------------------------------------------------------------
# Staging
# ---------------------------------------------------------------------------

class TestStaging(TrackerTestCase):
    def test_config_missing_noop(self):
        del self.fake.store[f"{P}/config.json"]
        out = ct.update_from_scan([stock("AAA", p10=0.3)], scan_date=FRI)
        self.assertEqual(out, {})
        self.assertNotIn(f"{P}/summary.json", self.fake.store)
        self.assertNotIn(f"{P}/pending_entries.json", self.fake.store)

    def test_weekday_gate(self):
        out = ct.update_from_scan([stock("AAA", p10=0.3, p20=0.4)], scan_date=SAT)
        self.assertEqual(out["p10_30"]["staged"], 0)
        self.assertEqual(out["p20_60"]["staged"], 0)
        self.assertEqual(self.pending(), [])

    def test_staging_dedup_and_dot_skip(self):
        stocks = [stock("AAA", p10=0.35, p20=0.45),
                  stock("BBB.DE", p10=0.50, p20=0.50),   # dot symbol -> skipped
                  stock("CCC", p10=0.25, p20=0.0)]        # p10-only
        out1 = ct.update_from_scan(stocks, scan_date=FRI)
        self.assertEqual(out1["p10_30"]["staged"], 2)     # AAA + CCC
        self.assertEqual(out1["p20_60"]["staged"], 1)     # AAA only
        syms = {(p["regime"], p["symbol"]) for p in self.pending()}
        self.assertEqual(syms, {("p10_30", "AAA"), ("p10_30", "CCC"), ("p20_60", "AAA")})
        self.assertNotIn(("p10_30", "BBB.DE"), syms)
        # deciles from config edges, p rounded: 0.35 -> decile 4
        aaa = next(p for p in self.pending() if p["regime"] == "p10_30" and p["symbol"] == "AAA")
        self.assertEqual(aaa["decile"], 4)
        self.assertEqual(aaa["p"], 0.35)
        self.assertIsNone(aaa.get("entry_price"))         # NO price at staging

        # second night, same stocks, still no bars -> dedup: nothing staged
        out2 = ct.update_from_scan(stocks, scan_date=MON)
        self.assertEqual(out2["p10_30"]["staged"], 0)
        self.assertEqual(out2["p20_60"]["staged"], 0)
        self.assertEqual(len(self.pending()), 3)

    def test_open_symbol_not_restaged(self):
        self.feed.add("AAA", bar(FRI, 103, 98, 100))
        ct.update_from_scan([stock("AAA", p10=0.35)], scan_date=FRI)   # night N: staged ONLY (C8)
        self.assertEqual(self.open_records("p10_30"), [])              # no same-night activation
        self.assertEqual(self.pending()[0]["attempts"], 0)             # staging night burns no attempt
        out = ct.update_from_scan([stock("AAA", p10=0.35)], scan_date=MON)  # night N+1: activated
        self.assertEqual(out["p10_30"]["activated"], 1)
        self.assertEqual(out["p10_30"]["staged"], 0)                   # PENDING -> no restage
        self.assertEqual(len(self.open_records("p10_30")), 1)
        out = ct.update_from_scan([stock("AAA", p10=0.35)], scan_date=TUE)
        self.assertEqual(out["p10_30"]["staged"], 0)                   # OPEN -> no restage
        self.assertEqual(len(self.open_records("p10_30")), 1)


# ---------------------------------------------------------------------------
# Activation
# ---------------------------------------------------------------------------

class TestActivation(TrackerTestCase):
    def test_activation_sets_entry_close_and_excludes_entry_bar(self):
        ct.update_from_scan([stock("AAA", p10=0.35, p20=0.45)], scan_date=FRI)
        # entry bar high 111 is ABOVE the +10% barrier (110) — must NOT touch
        self.feed.add("AAA", bar(FRI, 111.0, 95.0, 100.0, o=99.0))
        out = ct.update_from_scan([], scan_date=MON)
        self.assertEqual(out["p10_30"]["activated"], 1)
        self.assertEqual(out["p20_60"]["activated"], 1)
        recs = self.open_records("p10_30")
        self.assertEqual(len(recs), 1)
        r = recs[0]
        self.assertEqual(r["status"], "OPEN")
        self.assertEqual(r["entry_price"], 100.0)          # the EOD close, not the scan quote
        self.assertEqual(r["barrier_price"], 110.0)
        self.assertEqual(r["entry_bar_date"], FRI)
        self.assertEqual(r["last_bar_date"], FRI)
        self.assertEqual(r["bars_elapsed"], 0)             # entry bar excluded
        self.assertEqual(r["max_high_pct"], 0.0)           # entry-bar excursion ignored
        self.assertEqual(r["max_drawdown_pct"], 0.0)
        self.assertIsNone(r["touch_bar"])                  # 111 > 110 on entry bar: no touch
        r60 = self.open_records("p20_60")[0]
        self.assertEqual(r60["barrier_price"], 120.0)
        # entry rows landed in the monthly entries file
        entries = self.fake.jsonl(f"{P}/p10_30/entries/2026-06.jsonl")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["record_id"], f"p10_30:AAA:{FRI}")
        # pending consumed
        self.assertEqual(self.pending(), [])

    def test_dropped_after_three_attempts(self):
        ct.update_from_scan([stock("AAA", p10=0.35)], scan_date=FRI)   # staging night: NO attempt (C8)
        self.assertEqual(self.pending()[0]["attempts"], 0)
        ct.update_from_scan([], scan_date=MON)                          # attempt 1 (no bar)
        self.assertEqual(self.pending()[0]["attempts"], 1)
        ct.update_from_scan([], scan_date=TUE)                          # attempt 2
        self.assertEqual(self.pending()[0]["attempts"], 2)
        out = ct.update_from_scan([], scan_date=WED)                    # attempt 3 -> DROPPED
        self.assertEqual(out["p10_30"]["dropped"], 1)
        self.assertEqual(self.pending(), [])
        dropped = self.fake.jsonl(f"{P}/p10_30/resolved/2026-06.jsonl")
        self.assertEqual(len(dropped), 1)
        self.assertEqual(dropped[0]["status"], "DROPPED")
        self.assertEqual(dropped[0]["resolution"], "DROPPED_NO_BAR")
        # DROPPED is excluded from all stats but counted in cycle.n_dropped
        s = self.summary()
        cyc = s["horizons"]["30d"]["cycle"]
        self.assertEqual(cyc["n_dropped"], 1)
        self.assertEqual(cyc["n_total"], 0)
        self.assertEqual(sum(d["n_total"] for d in s["horizons"]["30d"]["deciles"]), 0)
        self.assertEqual(s["records"], [])


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

class TestResolution(TrackerTestCase):
    def _activate_aaa(self):
        ct.update_from_scan([stock("AAA", p10=0.35, p20=0.45)], scan_date=FRI)
        self.feed.add("AAA", bar(FRI, 103.0, 98.0, 100.0))
        ct.update_from_scan([], scan_date=MON)

    def test_touch_fills_at_barrier_and_counts_bars_not_days(self):
        self._activate_aaa()
        # two trading bars after the Friday entry: Mon (no touch), Tue (touch)
        self.feed.add("AAA", bar(MON, 105.0, 98.0, 104.0), bar(TUE, 112.0, 103.0, 108.0))
        out = ct.update_from_scan([], scan_date=TUE)
        self.assertEqual(out["p10_30"]["touched"], 1)
        self.assertEqual(out["p10_30"]["open"], 0)
        self.assertEqual(self.open_records("p10_30"), [])
        rows = [r for r in self.fake.jsonl(f"{P}/p10_30/resolved/2026-06.jsonl")
                if r["status"] == "RESOLVED"]
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["resolution"], "TOUCH")
        self.assertEqual(r["fill_price"], 110.0)            # fill AT the barrier exactly
        self.assertEqual(r["final_return_pct"], 10.0)       # == barrier_pct, never max-high
        self.assertEqual(r["touch_bar"], 2)
        self.assertEqual(r["bars_elapsed"], 2)              # 2 TRADING bars (4 calendar days)
        self.assertEqual(r["resolved_date"], TUE)
        # the 60d record is still open, marked to market per bar
        r60 = self.open_records("p20_60")[0]
        self.assertEqual(r60["status"], "OPEN")
        self.assertEqual(r60["bars_elapsed"], 2)
        self.assertAlmostEqual(r60["max_high_pct"], 12.0, places=9)
        self.assertAlmostEqual(r60["max_drawdown_pct"], -2.0, places=9)

    def test_terminal_at_bar_K_fills_at_close(self):
        self._activate_aaa()
        dates = weekdays(MON, 31)                           # 31 bars; window K=30
        for i, d in enumerate(dates):
            close = 102.0 if i == 29 else 100.0             # bar 30 closes at 102
            self.feed.add("AAA", bar(d, 103.0, 97.0, close))
        out = ct.update_from_scan([], scan_date=dates[-1])
        self.assertEqual(out["p10_30"]["terminal"], 1)
        rows = [r for r in self.fake.jsonl(f"{P}/p10_30/resolved/2026-07.jsonl")
                if r["resolution"] == "TERMINAL"]
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["bars_elapsed"], 30)             # resolved AT bar K, bar 31 ignored
        self.assertEqual(r["resolved_date"], dates[29])
        self.assertEqual(r["fill_price"], 102.0)            # bar-K close
        self.assertAlmostEqual(r["final_return_pct"], 2.0, places=9)
        self.assertIsNone(r["touch_bar"])
        # 60-bar regime keeps running through bar 31
        r60 = self.open_records("p20_60")[0]
        self.assertEqual(r60["bars_elapsed"], 31)
        self.assertAlmostEqual(r60["max_high_pct"], 3.0, places=9)
        self.assertAlmostEqual(r60["max_drawdown_pct"], -3.0, places=9)

    def test_duplicate_resolved_rows_counted_once(self):
        # Crash-between-append-and-state-write (or dual-job overlap) can
        # double-append a resolved row — stats must dedup by record_id.
        self._activate_aaa()
        self.feed.add("AAA", bar(MON, 105.0, 98.0, 104.0), bar(TUE, 112.0, 103.0, 108.0))
        ct.update_from_scan([], scan_date=TUE)
        path = f"{P}/p10_30/resolved/2026-06.jsonl"
        resolved = [r for r in self.fake.jsonl(path) if r["status"] == "RESOLVED"]
        self.assertEqual(len(resolved), 1)
        self.fake.append_jsonl(path, resolved)                  # duplicate the TOUCH row
        self.assertEqual(len(self.fake.jsonl(path)), 2)
        ct.update_from_scan([], scan_date=WED)                  # stats recomputed off the file
        s = self.summary()
        h30 = s["horizons"]["30d"]
        self.assertEqual(h30["cycle"]["n_total"], 1)            # one record, not two
        self.assertEqual(h30["cycle"]["n_touched"], 1)
        self.assertEqual(h30["cycle"]["n_matured"], 1)
        self.assertEqual(h30["headline"]["observed_touches_to_date"], 1)   # O deduped
        d4 = h30["deciles"][3]                                  # AAA p=0.35 -> decile 4
        self.assertEqual(d4["n_total"], 1)
        self.assertEqual(d4["n_touched"], 1)
        self.assertEqual(sum(d["n_total"] for d in h30["deciles"]), 1)


# ---------------------------------------------------------------------------
# Censoring math (C6), Wilson CI, health
# ---------------------------------------------------------------------------

class TestMath(unittest.TestCase):
    def test_q_and_curve_stats_hand_computed(self):
        # F by_decile["5"] = [0.25, 0.4, 0.5]; pooled = [0.2, 0.4, 0.5]; K = 3
        config = {"touch_cdf": {"p10_30": {"pooled": [0.2, 0.4, 0.5],
                                           "by_decile": {"5": [0.25, 0.4, 0.5]}}}}
        records = [
            # decile 5 -> by_decile CDF: q = 0.4 * 0.25/0.5 = 0.2
            {"p": 0.4, "decile": 5, "bars_elapsed": 1, "status": "OPEN", "resolution": None},
            # decile 3 -> pooled fallback, matured TOUCH: q = 0.5 * 0.5/0.5 = 0.5
            {"p": 0.5, "decile": 3, "bars_elapsed": 3, "status": "RESOLVED", "resolution": "TOUCH"},
            # bars_elapsed == 0 -> q = 0
            {"p": 0.2, "decile": 5, "bars_elapsed": 0, "status": "OPEN", "resolution": None},
        ]
        st = ct._curve_stats(records, config, "p10_30", 3)
        self.assertAlmostEqual(st["expected"], 0.7, places=10)                 # E = 0.2 + 0.5
        self.assertEqual(st["observed"], 1)                                    # one TOUCH
        self.assertAlmostEqual(st["variance"], 0.2 * 0.8 + 0.5 * 0.5, places=10)  # V = 0.41
        self.assertAlmostEqual(st["n_effective"], 0.5 + 1.0, places=10)        # 0.25/0.5 + 1
        self.assertAlmostEqual(st["z"], (1 - 0.7) / math.sqrt(0.41), places=10)
        self.assertAlmostEqual(st["ci_low"], 0.7 - 1.96 * math.sqrt(0.41), places=10)
        self.assertAlmostEqual(st["ci_high"], 0.7 + 1.96 * math.sqrt(0.41), places=10)

    def test_q_for_record_edges(self):
        F = [0.2, 0.4, 0.5]
        self.assertEqual(ct._q_for_record({"p": 0.4, "bars_elapsed": 0}, F, 3), (0.0, 0.0))
        q, frac = ct._q_for_record({"p": 0.4, "bars_elapsed": 5}, F, 3)        # capped at K
        self.assertAlmostEqual(q, 0.4)
        self.assertAlmostEqual(frac, 1.0)
        self.assertEqual(ct._q_for_record({"p": 0.4, "bars_elapsed": 2}, [], 3), (0.0, 0.0))
        self.assertEqual(ct._q_for_record({"p": 0.4, "bars_elapsed": 2}, [0.1, 0.2], 3), (0.0, 0.0))

    def test_zero_variance_z_is_null(self):
        st = ct._curve_stats([], {"touch_cdf": {"p10_30": {"pooled": [1.0], "by_decile": {}}}},
                             "p10_30", 1)
        self.assertIsNone(st["z"])
        self.assertEqual(st["expected"], 0.0)

    def test_wilson_ci(self):
        lo, hi = ct._wilson_ci(0.5, 10)
        self.assertAlmostEqual(lo, 0.2366, places=4)
        self.assertAlmostEqual(hi, 0.7634, places=4)
        # closed form check at p_hat=0.5, n=10, z=1.96
        z = 1.96
        denom = 1 + z * z / 10
        half = z * math.sqrt(0.5 * 0.5 / 10 + z * z / 400) / denom
        self.assertAlmostEqual(lo, 0.5 - half, places=10)   # center == 0.5 by symmetry
        self.assertAlmostEqual(hi, 0.5 + half, places=10)
        self.assertEqual(ct._wilson_ci(0.0, 0), (0.0, 1.0))
        lo1, hi1 = ct._wilson_ci(1.0, 5)
        self.assertGreater(lo1, 0.5)
        self.assertEqual(hi1, 1.0)

    def test_health_transitions(self):
        config = {"kill_switch": {"z_degraded": -3, "z_drifting": -2, "min_n_eff": 30}}

        def point(z, n_eff, observed=10, ci_low=0.0):
            return {"z": z, "n_effective": n_eff, "observed": observed,
                    "ci_low": ci_low, "ci_high": 99.0, "expected": 10.0, "variance": 1.0}

        hb = ct._health_block(point(-5.0, 10.0), config, TUE, 0)
        self.assertEqual(hb["status"], "UNDER_SAMPLED")     # n_eff gate trumps z
        self.assertFalse(hb["kill_switch_active"])

        hb = ct._health_block(point(-3.5, 50.0), config, TUE, 0)
        self.assertEqual(hb["status"], "DEGRADED")
        self.assertTrue(hb["kill_switch_active"])           # kill switch at z < -3

        hb = ct._health_block(point(-2.5, 50.0), config, TUE, 0)
        self.assertEqual(hb["status"], "DRIFTING")
        self.assertFalse(hb["kill_switch_active"])

        hb = ct._health_block(point(-1.0, 50.0), config, TUE, 0)
        self.assertEqual(hb["status"], "HEALTHY")

        hb = ct._health_block(point(None, 50.0), config, TUE, 0)
        self.assertEqual(hb["status"], "HEALTHY")           # z null + sampled -> healthy
        self.assertIsNone(hb["z_score"])

        # consecutive_below_band: increments when O < ci_low, else resets
        hb = ct._health_block(point(-1.0, 50.0, observed=1, ci_low=2.0), config, TUE, 2)
        self.assertEqual(hb["consecutive_below_band"], 3)
        hb = ct._health_block(point(-1.0, 50.0, observed=5, ci_low=2.0), config, TUE, 3)
        self.assertEqual(hb["consecutive_below_band"], 0)

    def test_decile_from_edges(self):
        edges = [round(0.1 * i, 4) for i in range(1, 10)]
        self.assertEqual(ct._decile_from_edges(0.05, edges), 1)
        self.assertEqual(ct._decile_from_edges(0.35, edges), 4)
        self.assertEqual(ct._decile_from_edges(0.95, edges), 10)
        self.assertEqual(ct._decile_from_edges(0.10, edges), 2)   # bisect_right: edge -> upper


# ---------------------------------------------------------------------------
# summary.json shape (C5 — exact key sets)
# ---------------------------------------------------------------------------

class TestSummaryShape(TrackerTestCase):
    def _run_touch_scenario(self):
        ct.update_from_scan([stock("AAA", p10=0.35, p20=0.45)], scan_date=FRI)
        self.feed.add("AAA", bar(FRI, 103.0, 98.0, 100.0))
        ct.update_from_scan([], scan_date=MON)
        self.feed.add("AAA", bar(MON, 105.0, 98.0, 104.0), bar(TUE, 112.0, 103.0, 108.0))
        ct.update_from_scan([], scan_date=TUE)

    def test_summary_shape_exact(self):
        self._run_touch_scenario()
        s = self.summary()
        self.assertIsNotNone(s)
        self.assertEqual(set(s.keys()),
                         {"schema_version", "as_of", "model", "horizons", "records"})
        self.assertEqual(s["schema_version"], "calibration-v2")
        self.assertEqual(s["as_of"], TUE)
        self.assertEqual(set(s["model"].keys()),
                         {"version", "trained_through", "decile_threshold_source"})
        self.assertEqual(set(s["horizons"].keys()), {"30d", "60d"})

        for label, bars_n, barrier in (("30d", 30, 10), ("60d", 60, 20)):
            h = s["horizons"][label]
            self.assertEqual(set(h.keys()),
                             {"horizon_bars", "barrier_pct", "cycle", "headline",
                              "health", "deciles", "curve"})
            self.assertEqual(h["horizon_bars"], bars_n)
            self.assertEqual(h["barrier_pct"], barrier)
            self.assertEqual(set(h["cycle"].keys()),
                             {"tracking_since", "n_scan_dates", "latest_scan_date",
                              "n_total", "n_matured", "n_open", "n_touched",
                              "n_pending", "n_dropped"})
            self.assertEqual(set(h["headline"].keys()),
                             {"expected_touches_to_date", "observed_touches_to_date",
                              "ci_low", "ci_high", "z"})
            self.assertEqual(set(h["health"].keys()),
                             {"status", "kill_switch_active", "z_score", "n_effective",
                              "consecutive_below_band", "rule", "computed_date"})
            self.assertEqual(len(h["deciles"]), 10)
            self.assertEqual([d["decile"] for d in h["deciles"]], list(range(1, 11)))
            for d in h["deciles"]:
                self.assertEqual(set(d.keys()),
                                 {"decile", "n_total", "n_matured", "n_open", "n_touched",
                                  "matured_observed_rate", "predicted_mean_p",
                                  "expected_touches_to_date", "observed_touches_to_date",
                                  "ci_low", "ci_high"})
            self.assertEqual(set(h["curve"].keys()), {"pooled", "by_decile"})
            self.assertEqual(set(h["curve"]["by_decile"].keys()),
                             {str(i) for i in range(1, 11)})
            for pt in h["curve"]["pooled"]:
                self.assertEqual(set(pt.keys()),
                                 {"scan_date", "expected", "observed", "ci_low", "ci_high"})
            for arr in h["curve"]["by_decile"].values():
                for pt in arr:
                    self.assertEqual(set(pt.keys()),
                                     {"scan_date", "expected", "observed", "ci_low", "ci_high"})

        for rec in s["records"]:
            self.assertEqual(set(rec.keys()),
                             {"symbol", "entry_date", "entry_price", "sector", "p10", "p20",
                              "decile_30d", "decile_60d", "bars_elapsed_30d", "bars_elapsed_60d",
                              "iv_entry", "ivr_entry",
                              "max_high_pct", "max_dd_pct", "state_30d", "state_60d",
                              "touch_bar_30d", "touch_bar_60d"})

    def test_summary_contents_after_touch(self):
        self._run_touch_scenario()
        s = self.summary()
        h30 = s["horizons"]["30d"]
        self.assertEqual(h30["cycle"]["n_total"], 1)
        self.assertEqual(h30["cycle"]["n_touched"], 1)
        self.assertEqual(h30["cycle"]["n_matured"], 1)
        self.assertEqual(h30["cycle"]["n_open"], 0)
        self.assertEqual(h30["cycle"]["tracking_since"], FRI)
        self.assertEqual(h30["cycle"]["latest_scan_date"], TUE)
        self.assertEqual(h30["cycle"]["n_scan_dates"], 3)        # 06-05, 06-08, 06-09
        self.assertEqual(h30["headline"]["observed_touches_to_date"], 1)
        # AAA p=0.35, decile 4, TOUCH at bar 2, K=30, pooled ramp F(k)=0.5k/30:
        # q = 0.35 * F(2)/F(30) = 0.35 * (2/30) = 0.0233
        self.assertAlmostEqual(h30["headline"]["expected_touches_to_date"],
                               0.35 * 2 / 30, places=4)
        self.assertEqual(len(h30["curve"]["pooled"]), 3)         # one point per scan night
        self.assertEqual(h30["curve"]["pooled"][-1]["scan_date"], TUE)
        self.assertEqual(h30["health"]["status"], "UNDER_SAMPLED")

        # one joined row per pick (hard project rule)
        self.assertEqual(len(s["records"]), 1)
        rec = s["records"][0]
        self.assertEqual(rec["symbol"], "AAA")
        self.assertEqual(rec["entry_date"], FRI)
        self.assertEqual(rec["entry_price"], 100.0)
        self.assertEqual(rec["sector"], "Tech")
        self.assertEqual(rec["p10"], 0.35)
        self.assertEqual(rec["p20"], 0.45)
        self.assertEqual(rec["decile_30d"], 4)
        self.assertEqual(rec["decile_60d"], 5)
        self.assertEqual(rec["state_30d"], "TOUCHED")
        self.assertEqual(rec["state_60d"], "OPEN")
        self.assertEqual(rec["touch_bar_30d"], 2)
        self.assertIsNone(rec["touch_bar_60d"])
        self.assertEqual(rec["bars_elapsed_30d"], 2)
        self.assertEqual(rec["bars_elapsed_60d"], 2)
        self.assertAlmostEqual(rec["max_high_pct"], 12.0, places=4)
        self.assertAlmostEqual(rec["max_dd_pct"], -2.0, places=4)

    def test_single_regime_pick_has_null_other_fields(self):
        ct.update_from_scan([stock("CCC", p10=0.25, p20=0.0)], scan_date=FRI)
        self.feed.add("CCC", bar(FRI, 101.0, 99.0, 100.0))
        ct.update_from_scan([], scan_date=MON)
        s = self.summary()
        self.assertEqual(len(s["records"]), 1)
        rec = s["records"][0]
        self.assertEqual(rec["p10"], 0.25)
        self.assertIsNone(rec["p20"])
        self.assertIsNone(rec["decile_60d"])
        self.assertIsNone(rec["state_60d"])
        self.assertEqual(rec["state_30d"], "OPEN")

    def test_rerun_same_night_upserts_curve_point(self):
        ct.update_from_scan([stock("AAA", p10=0.35)], scan_date=FRI)
        ct.update_from_scan([stock("AAA", p10=0.35)], scan_date=FRI)   # re-run, same as_of
        s = self.summary()
        self.assertEqual(len(s["horizons"]["30d"]["curve"]["pooled"]), 1)
        curve_lines = self.fake.jsonl(f"{P}/p10_30/daily_curve.jsonl")
        self.assertEqual(len(curve_lines), 1)
        self.assertEqual(curve_lines[0]["scan_date"], FRI)

    def test_read_summary(self):
        self._run_touch_scenario()
        s = ct.read_summary()
        self.assertEqual(s["schema_version"], "calibration-v2")


if __name__ == "__main__":
    unittest.main(verbosity=2)
