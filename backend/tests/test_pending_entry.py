#!/usr/bin/env python3
"""Tests for the PENDING ENTRY paper tracker (live_debate_engine._update_apex_tracking, 2026-10-06).

Run: python backend/tests/test_pending_entry.py
No network, no GCS, no repo writes: every dependency (_load_apex_tracking, _current_prices_asof,
_first_close_after, FRONTEND_DIR, _GATE_LEDGER, the clock) is monkeypatched to a temp dir. The
old-writer interleave loads main's _update_apex_tracking via `git show origin/main:...` (read-only)
and execs it with the same stubs; those cases SKIP when git / origin/main is unavailable, or when
main already carries the pending-entry writer.
"""
import copy
import json
import logging
import subprocess
import sys
import tempfile
from datetime import datetime as _RealDT, timezone
from pathlib import Path

HERE = Path(__file__).resolve()
BACKEND = HERE.parents[1]
REPO = HERE.parents[2]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "_opus_debate"))

import live_debate_engine as E  # noqa: E402

FAILURES = []
SKIPS = []


def check(name, cond, detail=""):
    status = "ok" if cond else "FAIL"
    print(f"  [{status}] {name}" + (f" - {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


def skip(name, why):
    print(f"  [skip] {name} - {why}")
    SKIPS.append(name)


# ── harness ──────────────────────────────────────────────────────────────────────────────────────
CLOCK = {"d": "2026-10-05"}


class FakeDT(_RealDT):
    @classmethod
    def now(cls, tz=None):
        return _RealDT.strptime(CLOCK["d"] + " 18:00", "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.msgs = []

    def emit(self, record):
        self.msgs.append(record.getMessage())


TMP = Path(tempfile.mkdtemp(prefix="pending_entry_"))
(TMP / "frontend" / "public").mkdir(parents=True, exist_ok=True)
LEDGER = TMP / "_entry_gate_ledger.jsonl"


class World:
    def __init__(self):
        self.states, self.px, self.asof, self.eod, self.eod_calls = {}, {}, {}, {}, []

    def load(self, gcs_path, local_name):
        return copy.deepcopy(self.states.get(local_name, {}))

    def prices_asof(self, syms):
        return ({s: self.px[s] for s in syms if s in self.px},
                {s: self.asof.get(s, "") for s in syms if s in self.px})

    def prices(self, syms):
        return self.prices_asof(syms)[0]

    def first_close_after(self, sym, after, level=None):
        # mirrors the real helper: a close strictly after `after`, strictly before today, <= level
        self.eod_calls.append((sym, after, level))
        rows = self.eod.get(sym)
        if rows == "ERR":
            return "ERR"
        for d, c in sorted(rows or []):
            if after < d < CLOCK["d"] and (level is None or c <= level):
                return (d, c)
        return None


W = World()
_SAVED = {k: getattr(E, k) for k in ("_load_apex_tracking", "_current_prices_asof", "_first_close_after",
                                    "FRONTEND_DIR", "_GATE_LEDGER", "datetime", "requests", "get_key")}
CAP = _Capture()


def _patch():
    E._load_apex_tracking = W.load
    E._current_prices_asof = W.prices_asof
    E._first_close_after = W.first_close_after
    E.FRONTEND_DIR = TMP / "frontend"
    E._GATE_LEDGER = LEDGER
    E.datetime = FakeDT
    E.log.addHandler(CAP)


def _restore():
    for k, v in _SAVED.items():
        setattr(E, k, v)
    E.log.removeHandler(CAP)


# main's (pre-pending) writer, exec'd with the same stubs
OLD = None
OLD_NOTE = ""
try:
    _src = None
    for ref in ("origin/main", "main"):
        r = subprocess.run(["git", "-C", str(REPO), "show", f"{ref}:backend/live_debate_engine.py"],
                           capture_output=True, timeout=60)
        if r.returncode == 0 and r.stdout:
            _src = r.stdout.decode("utf-8")
            OLD_NOTE = ref
            break
    if _src:
        _fn = _src[_src.index("def _update_apex_tracking("):_src.index("def _write_output(")]
        if "entry_rules" in _fn[:_fn.index("-> dict:")]:          # main already ships this writer
            OLD_NOTE = f"{OLD_NOTE} already carries the pending-entry writer"
        else:
            _ns = {"datetime": FakeDT, "timezone": timezone, "json": json, "sys": sys,
                   "log": logging.getLogger("old_writer"), "FRONTEND_DIR": TMP / "frontend",
                   "BASE_DIR": TMP, "APEX_TRACKING_PATH": "x",
                   "_load_apex_tracking": lambda g, l: W.load(g, l), "_current_prices": lambda s: W.prices(s)}
            exec(_fn, _ns)
            OLD = _ns["_update_apex_tracking"]
    else:
        OLD_NOTE = "git show failed"
except Exception as _e:  # pragma: no cover
    OLD_NOTE = f"{type(_e).__name__}: {_e}"


def run(writer, picks, mode="gated", name="t.json", weights=None, clear_cache=True):
    if clear_cache:
        E._FILL_CACHE.clear()
    if writer == "new":
        s = E._update_apex_tracking(picks, push_gcs=False, local_name=name, weights=weights, entry_rules=mode)
    else:
        s = OLD(picks, push_gcs=False, local_name=name, weights=weights)
    W.states[name] = json.loads((TMP / "frontend" / "public" / name).read_text(encoding="utf-8"))
    return s


def st(name="t.json"):
    return W.states[name]


def ledger_rows():
    if not LEDGER.exists():
        return []
    return [json.loads(x) for x in LEDGER.read_text(encoding="utf-8").splitlines() if x.strip()]


BASE = {"inception_date": "2026-06-01", "nav": 100.0, "last_date": "2026-10-03",
        "last_prices": {"A": 10.0},
        "positions": {"A": {"entry_price": 9.0, "entry_date": "2026-09-01", "conviction": 70}},
        "history": [{"date": "2026-10-03", "nav": 100.0, "ret": 0.0, "n": 1}], "closed": []}


def reset(state=None, name="t.json"):
    W.states = {name: copy.deepcopy(BASE if state is None else state)}
    W.px, W.asof, W.eod, W.eod_calls = {}, {}, {}, []
    CAP.msgs.clear()
    for f in (TMP / "frontend" / "public").glob("*.json"):
        f.unlink()
    if LEDGER.exists():
        LEDGER.unlink()


_patch()
try:
    # ── 1. _entry_gate: source order + Bruno's exit rule ────────────────────────────────────────
    print("\n=== _entry_gate source order ===")
    T = "2026-10-05"
    g = E._entry_gate({"entry_gate": {"letter": "B", "mode": "ON_EVENT", "level": None, "event": "Q3 print"},
                       "entry_mode": "NOW"}, "gated", T)
    check("post layer entry_gate wins over the record's flat entry_mode",
          g["kind"] == "event" and g["event"] == "Q3 print" and g["source"] == "entry_gate", g)
    g = E._entry_gate({"entry_gate": {"letter": "B", "mode": "AT_LEVEL", "level": 62.5}, "entry_mode": "NOW",
                       "cro_verdict": "B", "entry_posture": "wait_for_weakness", "cro_add_px": 62.5}, "gated", T)
    check("a floor/trim re-derived A (record says NOW) rests on the derived level, never next close",
          g["kind"] == "price" and g["level_px"] == 62.5, g)
    g = E._entry_gate({"cro_verdict": "B", "entry_posture": "wait_for_weakness", "cro_add_px": 50,
                       "entry_mode": "NOW", "entry_gate": None}, "gated", T)
    check("KEEP'd pending seat (no entry_gate) mirrors the reconciled posture",
          g["kind"] == "price" and g["level_px"] == 50.0 and g["source"] == "entry_posture", g)
    g = E._entry_gate({"entry_mode": "AT_LEVEL", "entry_level_px": 40, "washout_type": "MECHANICAL"}, "gated", T)
    check("typed record fields alone (no posture, no grade)",
          g["kind"] == "price" and g["level_px"] == 40.0 and g["washout_type"] == "MECHANICAL"
          and g["source"] == "entry_mode", g)
    g = E._entry_gate({"entry": {"mode": "ON_EVENT", "event": "FDA date"}}, "gated", T)
    check("nested typed shape {entry:{mode,event}} is read", g["kind"] == "event" and g["event"] == "FDA date", g)
    g = E._entry_gate({"symbol": "X"}, "gated", T)
    check("nothing known -> next_close (fail-open, never blocked)", g["kind"] == "next_close" and g["since"] == T, g)
    g = E._entry_gate({"entry_posture": "some_new_tag"}, "gated", T)
    check("unknown posture with no grade -> next_close", g["kind"] == "next_close", g)
    g = E._entry_gate({"cro_verdict": "C", "entry_posture": ""}, "gated", T)
    check("grade C with no dated override -> blocked", g["kind"] == "blocked", g)
    g = E._entry_gate({"cro_verdict": "C", "entry_posture": "scale_in"}, "gated", T)
    check("grade C + enter-now posture (a dated override survived reconcile) -> next_close", g["kind"] == "next_close", g)
    g = E._entry_gate({"cro_verdict": "B", "entry_posture": ""}, "gated", T)
    check("grade B naming no level or event -> blocked", g["kind"] == "blocked", g)
    g = E._entry_gate({"entry_posture": "wait_for_weakness"}, "gated", T)
    check("wait_for_weakness with no add level -> blocked", g["kind"] == "blocked", g)
    g = E._entry_gate({"entry_posture": "wait_for_weakness", "cro_add_px": 78, "thesis_break_px": 80}, "gated", T)
    check("add level at/below thesis_break_px -> blocked", g["kind"] == "blocked" and "exit" in g["reason"], g)
    g = E._entry_gate({"entry_posture": "wait_for_weakness", "cro_add_px": 78, "downside_floor": 78}, "gated", T)
    check("add level at the debate's downside floor -> blocked", g["kind"] == "blocked", g)
    g = E._entry_gate({"entry_posture": "on_confirmation: Q3 print", "cro_add_px": 78}, "defer", T)
    check("defer -> next_close whatever the posture", g["kind"] == "next_close" and g["source"] == "defer", g)
    g = E._entry_gate({"entry_posture": "on_confirmation: late-October Q3 report"}, "gated", T)
    check("on_confirmation detail is the event", g["kind"] == "event" and g["event"] == "late-October Q3 report", g)
    check("_gate_sig ignores event rewording",
          E._gate_sig({"kind": "event", "event": "a"}) == E._gate_sig({"kind": "event", "event": "b"}))

    # ── 2. _first_close_after (FMP EOD parsing) with a fake requests ───────────────────────────
    print("\n=== _first_close_after ===")
    E._first_close_after = _SAVED["_first_close_after"]
    CLOCK["d"] = "2026-10-12"
    CALLS = []

    class _Resp:
        def __init__(self, ok, data):
            self.ok, self._d = ok, data

        def json(self):
            return self._d

    class _Req:
        mode = "ok"
        rows = []

        def get(self, url, params=None, timeout=None):
            CALLS.append((url, dict(params or {})))
            if self.mode == "raise":
                raise RuntimeError("network down")
            if self.mode == "http":
                return _Resp(False, None)
            if self.mode == "dict":
                return _Resp(True, {"historical": self.rows})
            return _Resp(True, self.rows)

    FREQ = _Req()
    E.requests = FREQ
    E.get_key = lambda name: "TEST_PLACEHOLDER"
    FREQ.rows = [{"date": "2026-10-12", "close": 1.0}, {"date": "2026-10-09", "close": 99.0},
                 {"date": "2026-10-07", "close": 91.0}, {"date": "2026-10-06", "close": 95.0},
                 {"date": "2026-10-05", "close": 94.0}]
    r = E._first_close_after("P", "2026-10-05")
    check("next close strictly after the decision (newest-first rows)", r == ("2026-10-06", 95.0), r)
    check("request window starts the day after the decision",
          CALLS and CALLS[-1][1].get("from") == "2026-10-06" and CALLS[-1][1].get("symbol") == "P", CALLS[-1:])
    r = E._first_close_after("P", "2026-10-05", 92.0)
    check("price gate: first close at/below the level", r == ("2026-10-07", 91.0), r)
    r = E._first_close_after("P", "2026-10-05", 50.0)
    check("today's (possibly in-session) row is never a fill", r is None, r)
    FREQ.mode = "dict"
    check("{historical:[...]} shape accepted", E._first_close_after("P", "2026-10-05") == ("2026-10-06", 95.0))
    FREQ.mode = "http"
    check("HTTP error -> ERR", E._first_close_after("P", "2026-10-05") == "ERR")
    FREQ.mode = "raise"
    check("exception -> ERR", E._first_close_after("P", "2026-10-05") == "ERR")
    FREQ.mode = "ok"
    n0 = len(CALLS)
    check("decision yesterday -> None with no network call",
          E._first_close_after("P", "2026-10-11") is None and len(CALLS) == n0)
    E.get_key = lambda name: ""
    check("no key -> ERR", E._first_close_after("P", "2026-10-05") == "ERR")
    E.requests, E.get_key = _SAVED["requests"], _SAVED["get_key"]
    E._first_close_after = W.first_close_after

    # ── 3. _resolve_fill fallbacks when the EOD lookup fails ───────────────────────────────────
    print("\n=== _resolve_fill fallbacks ===")
    E._FILL_CACHE.clear()
    E._first_close_after = lambda s, a, l=None: "ERR"
    pos = {"pending_since": "2026-10-05", "gate": {"kind": "next_close", "since": "2026-10-05"}}
    r = E._resolve_fill("P", pos, {"P": 99.0}, {"P": "2026-10-10"}, {"P": 99.0}, "2026-10-10")
    check("ERR -> an older writer's mark dated after the decision (prior_mark)", r == ("2026-10-10", 99.0, "prior_mark"), r)
    E._FILL_CACHE.clear()
    r = E._resolve_fill("P", pos, {"P": 97.0}, {"P": "2026-10-12"}, {}, "2026-10-05")
    check("ERR -> this run's mark dated after the decision (mark)", r == ("2026-10-12", 97.0, "mark"), r)
    E._FILL_CACHE.clear()
    r = E._resolve_fill("P", pos, {"P": 97.0}, {"P": ""}, {}, "2026-10-05")
    check("ERR + undated mark -> no fill", r is None, r)
    E._FILL_CACHE.clear()
    r = E._resolve_fill("P", pos, {"P": 97.0}, {"P": "2026-10-03"}, {}, "2026-10-03")
    check("ERR + a mark dated BEFORE the decision -> no fill", r is None, r)
    E._FILL_CACHE.clear()
    pp = {"pending_since": "2026-10-05", "gate": {"kind": "price", "level_px": 90.0, "since": "2026-10-05"}}
    r = E._resolve_fill("P", pp, {"P": 97.0}, {"P": "2026-10-12"}, {}, "2026-10-05")
    check("ERR + mark above the price gate -> no fill", r is None, r)
    E._FILL_CACHE.clear()
    pe = {"pending_since": "2026-10-05", "gate": {"kind": "event", "event": "x", "since": "2026-10-05"}}
    check("event gate never fills", E._resolve_fill("P", pe, {"P": 1.0}, {"P": "2026-10-12"}, {"P": 1.0}, "2026-10-10") is None)
    E._first_close_after = W.first_close_after

    # ── 4. S1: ungated new seat, deploy-gap world (new -> OLD Saturday -> new) ──────────────────
    print("\n=== S1 next-close fill + pending outside NAV/n_open ===")
    reset()
    picks = [{"symbol": "A", "conviction": 70, "entry_posture": "scale_in"},
             {"symbol": "P", "conviction": 74, "entry_posture": "scale_in", "entry_price": 0,
              "entry_date": "2026-10-05", "live_price": 94.05}]
    CLOCK["d"] = "2026-10-05"
    W.px, W.asof = {"A": 10.0, "P": 94.0}, {"A": "2026-10-03", "P": "2026-10-03"}
    W.eod = {"P": [("2026-10-05", 94.0), ("2026-10-06", 95.0), ("2026-10-09", 99.0), ("2026-10-12", 100.0)]}
    s = run("new", picks)
    P = st()["positions"]["P"]
    check("new seat opens PENDING (no entry price, dated decision, decision px = live)",
          P.get("entry_pending") is True and P.get("entry_price") is None and P.get("pending_since") == "2026-10-05"
          and P.get("decision_px") == 94.05 and P["gate"]["kind"] == "next_close", P)
    check("pending seat is NOT in last_prices (outside the NAV)", "P" not in st()["last_prices"], st()["last_prices"])
    check("summary: n_open counts only bought seats, n_pending the rest",
          s["n_open"] == 1 and s["n_pending"] == 1 and s["pending"][0]["symbol"] == "P", s)
    check("history n = open seats only", st()["history"][-1]["n"] == 1, st()["history"][-1])
    check("no top-level state key added (main's writer rebuilds the dict)",
          set(st()) == {"inception_date", "nav", "last_date", "last_prices", "positions", "history", "closed"}, list(st()))
    check("ledger: opened", [r["event"] for r in ledger_rows()] == ["opened"], ledger_rows())
    if OLD:
        CLOCK["d"] = "2026-10-10"
        W.px, W.asof = {"A": 11.0, "P": 99.0}, {"A": "2026-10-10", "P": "2026-10-10"}
        run("old", picks)
        check("main's Saturday writer marks the unfilled seat into last_prices (known gap)",
              st()["last_prices"].get("P") == 99.0 and st()["nav"] == 110.0, st()["last_prices"])
        CLOCK["d"] = "2026-10-12"
        s = run("new", picks)
        P = st()["positions"]["P"]
        exp = round(100 * 1.10 * (1 + (0 + 99 / 95 - 1) / 2), 4)
        check("fill = first close STRICTLY after pending_since (10-06 at 95, not the 10-05 close)",
              P.get("entry_price") == 95.0 and P.get("entry_date") == "2026-10-06"
              and P.get("entry_price_source") == "next_close_eod" and "entry_pending" not in P, P)
        check("NAV chains from the fill: 100*1.10*(1+(0+99/95-1)/2)", st()["nav"] == exp, (st()["nav"], exp))
        check("stepped on a mark dated after the fill -> nav_from cleared", "nav_from" not in P, P)
        check("filled_from_pending audit trail",
              (P.get("filled_from_pending") or {}).get("waited_days") == 1
              and P["filled_from_pending"].get("decision_px") == 94.05, P.get("filled_from_pending"))
        check("summary after fill: 2 open, 0 pending", s["n_open"] == 2 and s["n_pending"] == 0, s)
    else:
        skip("S1 old-writer interleave", OLD_NOTE)

    # ── 5. S7: fill found on a stale-scan run holds the fill as base ────────────────────────────
    print("\n=== S7 stale-scan fill holds its base ===")
    reset()
    picks = [{"symbol": "A", "conviction": 70, "entry_posture": "scale_in"},
             {"symbol": "P", "conviction": 74, "entry_posture": "scale_in", "entry_price": 0}]
    CLOCK["d"] = "2026-10-05"
    W.px, W.asof = {"A": 10.0, "P": 94.0}, {"A": "2026-10-03", "P": "2026-10-03"}
    W.eod = {"P": [("2026-10-06", 95.0)]}
    run("new", picks)
    CLOCK["d"] = "2026-10-07"
    s = run("new", picks)
    P = st()["positions"]["P"]
    check("filled at 10-06 on a run whose scan is dated 10-03 -> base held at the fill",
          P.get("entry_price") == 95.0 and P.get("nav_from") == "2026-10-06" and st()["last_prices"].get("P") == 95.0
          and st()["nav"] == 100.0, (P, st()["last_prices"], st()["nav"]))
    if OLD:
        CLOCK["d"] = "2026-10-10"
        W.px, W.asof = {"A": 11.0, "P": 104.5}, {"A": "2026-10-10", "P": "2026-10-10"}
        run("old", picks)
        check("main's writer then chains P from the fill (100*(1+(0.1+104.5/95-1)/2))",
              st()["nav"] == round(100 * (1 + (0.1 + 104.5 / 95 - 1) / 2), 4), st()["nav"])
        CLOCK["d"] = "2026-10-12"
        run("new", picks)
        check("next new run clears nav_from once a dated mark stepped it", "nav_from" not in st()["positions"]["P"])
    else:
        CLOCK["d"] = "2026-10-10"
        W.px, W.asof = {"A": 11.0, "P": 104.5}, {"A": "2026-10-10", "P": "2026-10-10"}
        run("new", picks, mode="legacy")
        check("new writer chains P from the fill", st()["nav"] == round(100 * (1 + (0.1 + 104.5 / 95 - 1) / 2), 4), st()["nav"])

    # ── 6. S2: event gate + two consecutive old marks (leak is detected, then stripped) ────────
    print("\n=== S2 event gate never price-fills; old-writer leak stripped ===")
    reset()
    picks = [{"symbol": "A", "conviction": 70, "entry_posture": "scale_in"},
             {"symbol": "P", "conviction": 74, "entry_posture": "on_confirmation: late-October Q3 report",
              "entry_price": 0, "entry_date": "2026-10-05"}]
    CLOCK["d"] = "2026-10-05"
    W.px, W.asof = {"A": 10.0, "P": 94.0}, {"A": "2026-10-03", "P": "2026-10-03"}
    W.eod = {"P": [("2026-10-06", 80.0), ("2026-10-07", 70.0)]}
    run("new", picks)
    if OLD:
        CLOCK["d"] = "2026-10-10"
        W.asof = {"A": "2026-10-10", "P": "2026-10-10"}
        run("old", picks)
        CLOCK["d"] = "2026-10-17"
        W.px, W.asof = {"A": 10.0, "P": 103.4}, {"A": "2026-10-17", "P": "2026-10-17"}
        run("old", picks)
        check("two back-to-back old marks leak P's +10% at half weight (known, irreversible)", st()["nav"] == 105.0, st()["nav"])
        CLOCK["d"] = "2026-10-19"
        s = run("new", picks)
        check("new run strips the unfilled seat from last_prices", "P" not in st()["last_prices"], st()["last_prices"])
        check("... and WARNs that older-writer steps chained it",
              any("unfilled but chained by 1 older-writer" in m for m in CAP.msgs), CAP.msgs)
        check("event gate stays pending, n_open excludes it", st()["positions"]["P"].get("entry_pending") is True
              and s["n_open"] == 1 and s["n_pending"] == 1, s)
    else:
        CLOCK["d"] = "2026-10-19"
        W.px, W.asof = {"A": 10.0, "P": 60.0}, {"A": "2026-10-17", "P": "2026-10-17"}
        run("new", picks, mode="legacy")
        check("event gate stays pending under a legacy mark", st()["positions"]["P"].get("entry_pending") is True)
    check("event gate never consults the EOD closes (no price fill)", not [c for c in W.eod_calls if c[0] == "P"],
          W.eod_calls)

    # ── 7. S3: price gate fills at the first close <= level (also under the legacy Saturday mark) ─
    print("\n=== S3 price gate ===")
    reset()
    picks = [{"symbol": "A", "conviction": 70, "entry_posture": "scale_in"},
             {"symbol": "P", "conviction": 74, "entry_posture": "wait_for_weakness", "cro_add_px": 90,
              "thesis_break_px": 80, "entry_price": 0}]
    CLOCK["d"] = "2026-10-05"
    W.px, W.asof = {"A": 10.0, "P": 94.0}, {"A": "2026-10-03", "P": "2026-10-03"}
    W.eod = {"P": [("2026-10-06", 95.0), ("2026-10-07", 91.0), ("2026-10-08", 89.5), ("2026-10-09", 92.0)]}
    run("new", picks)
    check("price gate opened at the add level", st()["positions"]["P"]["gate"].get("level_px") == 90.0,
          st()["positions"]["P"]["gate"])
    CLOCK["d"] = "2026-10-10"
    W.px, W.asof = {"A": 10.0, "P": 92.0}, {"A": "2026-10-10", "P": "2026-10-10"}
    run("new", picks, mode="legacy")
    P = st()["positions"]["P"]
    check("fills at the FIRST close <= 90 (89.5 on 10-08; 91 on 10-07 is above)",
          P.get("entry_price") == 89.5 and P.get("entry_date") == "2026-10-08"
          and P.get("entry_price_source") == "level_close_eod", P)
    check("NAV steps P from its fill at half weight", st()["nav"] == round(100 * (1 + (0 + 92 / 89.5 - 1) / 2), 4),
          st()["nav"])

    # ── 8. S4: blocked gate, then ungated -> re-dated -> next close after the re-date ──────────
    print("\n=== S4 blocked gate, ungate re-dates ===")
    reset()
    picks = [{"symbol": "A", "conviction": 70},
             {"symbol": "P", "conviction": 74, "entry_posture": "wait_for_weakness", "cro_add_px": 78,
              "thesis_break_px": 80, "entry_price": 0}]
    CLOCK["d"] = "2026-10-05"
    W.px, W.asof = {"A": 10.0, "P": 94.0}, {"A": "2026-10-03", "P": "2026-10-03"}
    W.eod = {"P": [("2026-10-06", 70.0), ("2026-10-13", 96.0), ("2026-10-14", 97.0)]}
    run("new", picks)
    check("add level at/below the exit opens BLOCKED (+WARN)", st()["positions"]["P"]["gate"]["kind"] == "blocked"
          and any("BLOCKED gate" in m for m in CAP.msgs), st()["positions"]["P"]["gate"])
    CLOCK["d"] = "2026-10-10"
    run("new", picks)
    check("blocked gate never price-fills (a 70 close sat below the level)",
          st()["positions"]["P"].get("entry_pending") is True and not [c for c in W.eod_calls if c[0] == "P"],
          W.eod_calls)
    CLOCK["d"] = "2026-10-12"
    picks[1] = {**picks[1], "entry_posture": "scale_in"}
    run("new", picks)
    P = st()["positions"]["P"]
    check("ungated by this decision -> pending_since re-dated to the run",
          P.get("pending_since") == "2026-10-12" and P["gate"]["kind"] == "next_close"
          and len(P.get("gate_history") or []) == 1 and P.get("entry_pending") is True, P)
    check("ledger: regated", "regated" in [r["event"] for r in ledger_rows()], ledger_rows())
    CLOCK["d"] = "2026-10-14"
    W.px, W.asof = {"A": 10.0, "P": 97.0}, {"A": "2026-10-14", "P": "2026-10-14"}
    run("new", picks)
    P = st()["positions"]["P"]
    check("fills at the first close after the RE-DATE (10-13 at 96, not 10-06)",
          P.get("entry_price") == 96.0 and P.get("entry_date") == "2026-10-13", P)

    # ── 9. S5: cancel + phantom closed-leg filter ──────────────────────────────────────────────
    print("\n=== S5 cancel leaves no closed leg; phantom legs dropped ===")
    reset()
    picks = [{"symbol": "A", "conviction": 70}, {"symbol": "P", "conviction": 74, "entry_posture": "on_confirmation: x",
                                                 "entry_price": 0}]
    CLOCK["d"] = "2026-10-05"
    W.px, W.asof = {"A": 10.0, "P": 94.0}, {"A": "2026-10-03", "P": "2026-10-03"}
    run("new", picks)
    CLOCK["d"] = "2026-10-06"
    s = run("new", picks[:1])
    check("dropped before it filled: no position, no closed leg, win rate untouched",
          "P" not in st()["positions"] and st()["closed"] == [] and s["win_rate"] is None and s["n_closed"] == 0, s)
    check("ledger: cancelled", "cancelled" in [r["event"] for r in ledger_rows()], ledger_rows())
    if OLD:
        reset()
        CLOCK["d"] = "2026-10-05"
        W.px, W.asof = {"A": 10.0, "P": 94.0}, {"A": "2026-10-03", "P": "2026-10-03"}
        run("new", picks)
        CLOCK["d"] = "2026-10-10"
        run("old", picks)
        CLOCK["d"] = "2026-10-11"
        run("old", picks[:1])
        check("main's writer books a phantom leg (entry_date null) when it drops the unfilled seat",
              any(c.get("symbol") == "P" and c.get("entry_date") is None for c in st()["closed"]), st()["closed"])
        CLOCK["d"] = "2026-10-12"
        s = run("new", picks[:1])
        check("new run drops the phantom leg (+WARN), win rate back to none",
              st()["closed"] == [] and s["win_rate"] is None and any("phantom" in m for m in CAP.msgs), st()["closed"])
    else:
        skip("S5 phantom leg from main's writer", OLD_NOTE)
    # a real leg with an entry_date is never touched by the phantom filter
    reset({**copy.deepcopy(BASE), "closed": [{"symbol": "Z", "entry_date": "2026-08-01", "exit_date": "2026-09-01",
                                               "entry_price": 1.0, "exit_price": 2.0, "return_pct": 100.0,
                                               "conviction": 1},
                                              {"symbol": "Y", "entry_date": "", "exit_date": "2026-09-02",
                                               "entry_price": 1.0, "exit_price": 1.0, "return_pct": 0.0,
                                               "conviction": 1}]})
    CLOCK["d"] = "2026-10-05"
    W.px, W.asof = {"A": 10.0}, {"A": "2026-10-03"}
    run("new", [{"symbol": "A", "conviction": 70}])
    check("legs with a real or empty-string entry_date survive", [c["symbol"] for c in st()["closed"]] == ["Z", "Y"],
          st()["closed"])

    # ── 10. S8: gated inception ────────────────────────────────────────────────────────────────
    print("\n=== S8 gated inception ===")
    reset({})
    CLOCK["d"] = "2026-10-05"
    W.px, W.asof = {"A": 10.0, "P": 94.0}, {"A": "2026-10-03", "P": "2026-10-03"}
    s = run("new", [{"symbol": "A", "entry_posture": "scale_in"}, {"symbol": "P", "entry_posture": "on_confirmation: x"}])
    check("gated inception: everything pending, NAV 100, no last prices",
          s["nav"] == 100.0 and s["n_open"] == 0 and s["n_pending"] == 2 and st()["last_prices"] == {}, s)

    # a hand-migrated pending seat with no decision date rests from the run that first sees it
    mig = copy.deepcopy(BASE)
    mig["positions"]["M"] = {"entry_price": None, "entry_date": None, "conviction": 5, "entry_pending": True}
    reset(mig)
    CLOCK["d"] = "2026-10-05"
    W.px, W.asof = {"A": 10.0, "M": 50.0}, {"A": "2026-10-03", "M": "2026-10-03"}
    W.eod = {"M": [("2026-10-02", 40.0), ("2026-10-06", 51.0)]}
    run("new", [{"symbol": "A"}, {"symbol": "M"}], mode="legacy")
    check("undated pending seat is dated to this run (never a pre-decision close)",
          st()["positions"]["M"].get("pending_since") == "2026-10-05" and st()["positions"]["M"].get("entry_pending"),
          st()["positions"]["M"])
    CLOCK["d"] = "2026-10-07"
    run("new", [{"symbol": "A"}, {"symbol": "M"}], mode="legacy")
    check("... and fills at the next close after it", st()["positions"]["M"].get("entry_price") == 51.0,
          st()["positions"]["M"])

    # ── 11. 9980.HK replay (decision 2026-10-05, on_confirmation late-October Q3 report) ──────
    print("\n=== 9980.HK replay stays pending ===")
    reset()
    HK = {"symbol": "9980.HK", "conviction": 74, "decision": "ADD", "cro_verdict": "B", "cro_says_wait": True,
          "entry_posture": "on_confirmation: late-October 2026 Q3 report (confirms the margin step-up)",
          "cro_add_px": None, "cro_add_event": "late-October 2026 Q3 report", "live_price": 94.05,
          "entry_price": 0, "entry_date": "2026-10-05",
          "entry_gate": {"letter": "B", "mode": "ON_EVENT", "level": None,
                         "event": "late-October 2026 Q3 report", "decided": "2026-10-05"}}
    picks = [{"symbol": "A", "conviction": 70, "decision": "KEEP"}, HK]
    CLOCK["d"] = "2026-10-05"
    W.px, W.asof = {"A": 10.0, "9980.HK": 94.0}, {"A": "2026-10-03", "9980.HK": "2026-10-03"}
    W.eod = {"9980.HK": [("2026-10-06", 93.0), ("2026-10-07", 92.0), ("2026-10-08", 91.0), ("2026-10-09", 95.0)]}
    run("new", picks)
    g0 = st()["positions"]["9980.HK"]["gate"]
    check("opened PENDING on the event (not booked at the stale 94.0 scan price)",
          st()["positions"]["9980.HK"].get("entry_pending") is True and g0["kind"] == "event"
          and g0["event"] == "late-October 2026 Q3 report", st()["positions"]["9980.HK"])
    CLOCK["d"] = "2026-10-10"                      # the Saturday mark, new code, legacy rules
    W.px, W.asof = {"A": 10.5, "9980.HK": 96.0}, {"A": "2026-10-10", "9980.HK": "2026-10-10"}
    run("new", [{"symbol": "A", "conviction": 70}, {**HK, "entry_gate": None}], mode="legacy")
    check("Saturday mark: still pending, not in the NAV", st()["positions"]["9980.HK"].get("entry_pending") is True
          and "9980.HK" not in st()["last_prices"] and st()["nav"] == 105.0, (st()["last_prices"], st()["nav"]))
    CLOCK["d"] = "2026-10-12"                      # next publish: KEEP -> no entry_gate, posture mirror
    run("new", [{"symbol": "A", "conviction": 70, "decision": "KEEP"},
                {**HK, "decision": "KEEP", "entry_gate": None}])
    P = st()["positions"]["9980.HK"]
    check("KEEP re-gate reads the same event -> not re-dated, no gate_history",
          P.get("pending_since") == "2026-10-05" and not P.get("gate_history") and P.get("entry_pending") is True, P)
    CLOCK["d"] = "2026-10-19"
    W.px, W.asof = {"A": 10.5, "9980.HK": 84.0}, {"A": "2026-10-17", "9980.HK": "2026-10-17"}
    run("new", [{"symbol": "A", "conviction": 70, "decision": "KEEP"}, {**HK, "decision": "KEEP", "entry_gate": None}])
    P = st()["positions"]["9980.HK"]
    check("a 10% fall stamps washout_hit (informational) and does NOT fill",
          (P.get("washout_hit") or {}).get("kind") == "drawdown_10pct" and P.get("entry_pending") is True, P)
    check("9980.HK never consulted the EOD closes", not [c for c in W.eod_calls if c[0] == "9980.HK"], W.eod_calls)

    # ── 12. EW + weighted fill identically; only the EW call logs ─────────────────────────────
    print("\n=== EW + weighted share one fill ===")
    reset(name="ew.json")
    W.states["w.json"] = copy.deepcopy(BASE)
    picks = [{"symbol": "A", "conviction": 70}, {"symbol": "P", "conviction": 74, "entry_posture": "scale_in"}]
    CLOCK["d"] = "2026-10-05"
    W.px, W.asof = {"A": 10.0, "P": 94.0}, {"A": "2026-10-03", "P": "2026-10-03"}
    W.eod = {"P": [("2026-10-06", 95.0)]}
    run("new", picks, name="ew.json")
    run("new", picks, name="w.json", weights={"A": 0.5, "P": 0.5}, clear_cache=False)
    CLOCK["d"] = "2026-10-07"
    E._FILL_CACHE.clear()
    W.eod_calls = []
    run("new", picks, name="ew.json", clear_cache=False)
    run("new", picks, name="w.json", weights={"A": 0.5, "P": 0.5}, clear_cache=False)
    pe, pw = st("ew.json")["positions"]["P"], st("w.json")["positions"]["P"]
    check("both files fill P identically", (pe.get("entry_price"), pe.get("entry_date"))
          == (pw.get("entry_price"), pw.get("entry_date")) == (95.0, "2026-10-06"), (pe, pw))
    check("one EOD lookup per process (shared _FILL_CACHE)", len([c for c in W.eod_calls if c[0] == "P"]) == 1, W.eod_calls)
    check("gate ledger written by the EW call only", {r["book"] for r in ledger_rows()} == {"ew.json"}, ledger_rows())

    # ── 13. defer / invalid entry_rules ────────────────────────────────────────────────────────
    print("\n=== defer + invalid entry_rules ===")
    reset()
    CLOCK["d"] = "2026-10-05"
    W.px, W.asof = {"A": 10.0, "P": 94.0}, {"A": "2026-10-03", "P": "2026-10-03"}
    run("new", [{"symbol": "A"}, {"symbol": "P", "entry_posture": "on_confirmation: x"}], mode="defer")
    check("defer: event posture ignored, next close", st()["positions"]["P"]["gate"]["kind"] == "next_close")
    reset()
    W.px, W.asof = {"A": 10.0, "P": 94.0}, {"A": "2026-10-03", "P": "2026-10-03"}
    run("new", [{"symbol": "A"}, {"symbol": "P", "entry_posture": "on_confirmation: x"}], mode="bogus")
    check("unknown entry_rules -> legacy (booked at this run's mark)",
          st()["positions"]["P"].get("entry_price") == 94.0 and not st()["positions"]["P"].get("entry_pending"))

    # ── 14. legacy mode == main's function (state bit-identical) ───────────────────────────────
    print("\n=== legacy mode identical to main's writer ===")
    if OLD:
        steps = [("2026-10-05", {"A": 10.5, "P": 94.0}, [{"symbol": "A", "conviction": 70}, {"symbol": "P", "conviction": 74,
                                                                                         "entry_posture": "on_confirmation: x"}]),
                 ("2026-10-10", {"A": 11.0, "P": 90.0, "Q": 5.0}, [{"symbol": "A", "conviction": 71}, {"symbol": "Q", "conviction": 3}]),
                 ("2026-10-10", {"A": 11.2, "Q": 5.5}, [{"symbol": "A", "conviction": 71}, {"symbol": "Q", "conviction": 3}]),
                 ("2026-10-12", {"A": 12.0, "Q": 4.0, "R": 7.0}, [{"symbol": "A"}, {"symbol": "R", "conviction": 2},
                                                                  {"symbol": "R", "conviction": 2}, {"symbol": "Q", "entry_price": 4.5,
                                                                                                     "entry_date": "2026-10-01"}])]
        for weights in (None, {"A": 0.7, "P": 0.1, "Q": 0.2, "R": 0.3}):
            for start in (BASE, {}):
                reset(start, name="n.json")
                W.states["o.json"] = copy.deepcopy(start)
                same = True
                for i, (d, px, pk) in enumerate(steps):
                    CLOCK["d"] = d
                    W.px, W.asof = dict(px), {k: d for k in px}
                    sn = run("new", copy.deepcopy(pk), mode="legacy", name="n.json", weights=weights)
                    so = run("old", copy.deepcopy(pk), name="o.json", weights=weights)
                    if st("n.json") != st("o.json"):
                        same = False
                        print("    state diff at step", i, json.dumps(st("n.json"))[:300], "|", json.dumps(st("o.json"))[:300])
                    for k in ("nav", "n_open", "n_closed", "win_rate", "since_inception_pct", "inception_date", "history"):
                        if sn.get(k) != so.get(k):
                            same = False
                            print("    summary diff", k, sn.get(k), so.get(k))
                    if sn.get("n_pending") != 0 or sn.get("pending") != []:
                        same = False
                    if ledger_rows():
                        same = False
                        print("    legacy run wrote gate-ledger rows", ledger_rows())
                tag = f"{'weighted' if weights else 'EW'}, {'chained' if start else 'inception'}"
                check(f"legacy == main ({OLD_NOTE}) over 4 runs incl. rotation, duplicate pick, same-day rerun [{tag}]", same)
    else:
        skip("legacy == main", OLD_NOTE)

    # ── 16. CRO review findings 1-4 (policy P8, 2026-10-06) ─────────────────────────────────────
    # The reviewer reproductions (scratch simA / sim_regate / simB / simC / simE), made permanent.
    BASE2 = {"inception_date": "2026-06-01", "nav": 100.0, "last_date": "2026-10-10",
             "last_prices": {"A": 10.0},
             "positions": {"A": {"entry_price": 9.0, "entry_date": "2026-09-01", "conviction": 70}},
             "history": [{"date": "2026-10-10", "nav": 100.0, "ret": 0.0, "n": 1}], "closed": []}
    A0 = {"symbol": "A", "conviction": 70, "decision": "KEEP", "entry_posture": "scale_in"}
    P0 = {"symbol": "P", "conviction": 74, "decision": "ADD", "entry_posture": "scale_in", "cro_verdict": "A",
          "live_price": 100.0, "entry_price": 0, "entry_date": "2026-10-12"}

    def _main_mark_emulated(picks, name="t.json"):
        """main's EW Saturday writer, reduced to what it does to these states (no rotation): EW step over
        the names already in last_prices, then every pick's mark into last_prices (a pending seat
        included), one history point. Used only when main's real writer cannot be loaded."""
        s0 = copy.deepcopy(W.states[name])
        today, lp, px = CLOCK["d"], s0["last_prices"], W.px
        prior = [k for k in lp if k in px and lp[k] > 0]
        nav, ret = s0["nav"], 0.0
        if prior and s0["last_date"] != today:
            ret = sum(px[k] / lp[k] - 1 for k in prior) / len(prior)
            nav *= 1 + ret
        sy = [p["symbol"] for p in picks]
        s0["last_prices"] = {k: px.get(k) or lp.get(k) or 0.0 for k in sy}
        pt = {"date": today, "nav": round(nav, 4), "ret": round(ret, 6), "n": len(sy)}
        s0["history"] = (s0["history"][:-1] if s0["history"][-1]["date"] == today else s0["history"]) + [pt]
        s0["nav"], s0["last_date"] = round(nav, 4), today
        W.states[name] = s0

    def old_mark(picks):
        """The Saturday Cloud Run mark by main's (pre-pending) writer: the real one when loadable."""
        pk = [{**p, "entry_price": None, "entry_date": None} for p in picks]
        if OLD:
            run("old", pk)
        else:
            _main_mark_emulated(pk)

    MAIN_TAG = "main's writer" if OLD else "main's writer, emulated"

    print("\n=== P8 / findings 1+4: the fill on the STORED gate is booked before a later decision ===")
    OUTCOMES = {
        "keep": [A0, {**P0, "decision": "KEEP"}],
        "drop": [A0],
        "regate_event": [A0, {**P0, "decision": "KEEP", "cro_verdict": "B",
                              "entry_posture": "on_confirmation: Q3 print", "cro_add_event": "Q3 print"}],
        "regate_price": [A0, {**P0, "decision": "KEEP", "cro_verdict": "B", "entry_posture": "wait_for_weakness",
                              "cro_add_px": 80.0}],
    }
    for with_mark in (False, True):
        for case, picks in OUTCOMES.items():
            reset(BASE2)
            CLOCK["d"] = "2026-10-12"
            W.px, W.asof = {"A": 10.0, "P": 100.0}, {"A": "2026-10-10", "P": "2026-10-10"}
            W.eod = {"P": [("2026-10-13", 100.0), ("2026-10-14", 95.0), ("2026-10-15", 90.0), ("2026-10-16", 86.0)]}
            run("new", [A0, P0])
            W.px, W.asof = {"A": 10.0, "P": 85.0}, {"A": "2026-10-17", "P": "2026-10-17"}
            if with_mark:
                CLOCK["d"] = "2026-10-17"
                old_mark([A0, P0])
            CLOCK["d"] = "2026-10-19"
            s = run("new", copy.deepcopy(picks))
            P = st()["positions"].get("P")
            tag = f"[{case}" + (f", Saturday mark by {MAIN_TAG}]" if with_mark else ", no mark in between]")
            check(f"the 10-13 fill is booked whatever the 10-19 decision says: NAV 100*(1+(0+85/100-1)/2)=92.5 {tag}",
                  st()["nav"] == 92.5, st()["nav"])
            if case == "drop":
                legs = [c for c in st()["closed"] if c.get("symbol") == "P"]
                check(f"dropping a seat whose gate was already met logs a REAL closed leg (100 -> 85, -15%) {tag}",
                      P is None and len(legs) == 1 and legs[0]["entry_price"] == 100.0
                      and legs[0]["exit_price"] == 85.0 and legs[0]["return_pct"] == -15.0
                      and legs[0]["entry_date"] == "2026-10-13"
                      and (legs[0].get("filled_from_pending") or {}).get("fill_date") == "2026-10-13"
                      and s["n_closed"] == 1 and s["win_rate"] == 0.0 and "P" not in st()["last_prices"]
                      and "cancelled" not in [r["event"] for r in ledger_rows()], (P, st()["closed"]))
            else:
                check(f"a seat that already filled is HELD (keep != buy) and never re-gated {tag}",
                      bool(P) and not P.get("entry_pending") and P.get("entry_price") == 100.0
                      and P.get("entry_date") == "2026-10-13" and not P.get("gate_history")
                      and "regated" not in [r["event"] for r in ledger_rows()]
                      and s["n_open"] == 2 and s["n_pending"] == 0, P)

    # sim_regate (A): next-close fill, a +15% rally, then the A-seat check re-grades the KEEP to a price wait
    reset(BASE2)
    CLOCK["d"] = "2026-10-12"
    W.px, W.asof = {"A": 10.0, "P": 99.0}, {"A": "2026-10-10", "P": "2026-10-10"}
    W.eod = {"P": [("2026-10-13", 100.0), ("2026-10-14", 104.0), ("2026-10-15", 109.0), ("2026-10-16", 115.0)]}
    run("new", [A0, {**P0, "live_price": 99.0,
                     "entry_gate": {"letter": "A", "mode": "NOW", "level": None, "event": "", "decided": "2026-10-12"}}])
    CLOCK["d"] = "2026-10-19"
    W.px, W.asof = {"A": 10.0, "P": 115.0}, {"A": "2026-10-17", "P": "2026-10-17"}
    run("new", [A0, {**P0, "decision": "KEEP", "live_price": 115.0, "cro_verdict": "B", "cro_verdict_record": "A",
                     "entry_posture": "wait_for_weakness", "cro_add_px": 100.0, "entry_gate": None}])
    P = st()["positions"]["P"]
    check("re-grade to a price wait AFTER the next-close fill keeps the fill (100 on 10-13) and the +15% in the NAV",
          P.get("entry_price") == 100.0 and P.get("entry_date") == "2026-10-13" and not P.get("entry_pending")
          and st()["nav"] == 107.5, (P, st()["nav"]))

    # sim_regate (B) / simB: a price order met mid-week, then the wash-out debate answers buy-now
    reset(BASE2)
    CLOCK["d"] = "2026-10-12"
    W.px, W.asof = {"A": 10.0, "P": 99.0}, {"A": "2026-10-10", "P": "2026-10-10"}
    W.eod = {"P": [("2026-10-13", 99.0), ("2026-10-14", 96.0), ("2026-10-15", 94.0), ("2026-10-16", 101.0),
                   ("2026-10-19", 96.0), ("2026-10-20", 99.0)]}
    run("new", [A0, {**P0, "live_price": 99.0, "cro_verdict": "B", "entry_posture": "wait_for_weakness",
                     "cro_add_px": 95.0, "thesis_break_px": 70.0,
                     "entry_gate": {"letter": "B", "mode": "AT_LEVEL", "level": 95.0, "event": "",
                                    "decided": "2026-10-12"}}])
    CLOCK["d"] = "2026-10-19"
    W.px, W.asof = {"A": 10.0, "P": 103.0}, {"A": "2026-10-17", "P": "2026-10-17"}
    run("new", [A0, {**P0, "decision": "KEEP", "live_price": 103.0, "entry_gate": None}])
    P = st()["positions"]["P"]
    check("a price order met at the 10-15 close (94 <= 95) fills there, not at the close after the re-debate",
          P.get("entry_price") == 94.0 and P.get("entry_date") == "2026-10-15"
          and P.get("entry_price_source") == "level_close_eod" and not P.get("entry_pending")
          and (P.get("filled_from_pending") or {}).get("pending_since") == "2026-10-12"
          and st()["nav"] == round(100 * (1 + (103 / 94 - 1) / 2), 4), (P, st()["nav"]))

    # an order whose gate is NOT met yet is still cancelled on a drop: no trade, no closed leg
    reset(BASE2)
    CLOCK["d"] = "2026-10-12"
    W.px, W.asof = {"A": 10.0, "P": 100.0}, {"A": "2026-10-10", "P": "2026-10-10"}
    W.eod = {"P": [("2026-10-13", 100.0)]}
    run("new", [A0, P0])
    CLOCK["d"] = "2026-10-13"                      # the 10-13 close is today's row: not a fill yet
    s = run("new", [A0])
    check("drop before any close printed after the decision -> cancelled, no leg",
          "P" not in st()["positions"] and st()["closed"] == [] and s["n_closed"] == 0
          and "cancelled" in [r["event"] for r in ledger_rows()], (st()["positions"], st()["closed"]))

    print("\n=== P8 / finding 2: two older-writer marks already chained a filled seat ===")
    reset(BASE2)
    CLOCK["d"] = "2026-10-12"
    W.px, W.asof = {"A": 10.0, "P": 100.0}, {"A": "2026-10-10", "P": "2026-10-10"}
    W.eod = {"P": [("2026-10-13", 100.0), ("2026-10-16", 110.0), ("2026-10-23", 121.0)]}
    run("new", [A0, P0])
    CLOCK["d"] = "2026-10-17"
    W.px, W.asof = {"A": 10.0, "P": 110.0}, {"A": "2026-10-17", "P": "2026-10-17"}
    old_mark([A0, P0])
    CLOCK["d"] = "2026-10-24"
    W.px, W.asof = {"A": 10.0, "P": 121.0}, {"A": "2026-10-24", "P": "2026-10-24"}
    old_mark([A0, P0])
    check(f"precondition: {MAIN_TAG} chained P 110 -> 121 at half weight (NAV 105)", st()["nav"] == 105.0, st()["nav"])
    CLOCK["d"] = "2026-10-26"
    run("new", [A0, {**P0, "decision": "KEEP"}])
    P = st()["positions"]["P"]
    check("keeps the chained base: NAV 105, last price 121 (the old code stepped 100 -> 121 again: 116.025)",
          st()["nav"] == 105.0 and st()["last_prices"].get("P") == 121.0, (st()["nav"], st()["last_prices"]))
    check("... still stamps the fill (100 on 10-13) with the chained base in the audit trail; stepped -> no nav_from",
          P.get("entry_price") == 100.0 and P.get("entry_date") == "2026-10-13" and not P.get("entry_pending")
          and "nav_from" not in P
          and ((P.get("filled_from_pending") or {}).get("nav_base") or {}).get("px") == 121.0, P)
    check("... and WARNs that older-writer steps already chained it",
          any("already chained" in m and "P" in m for m in CAP.msgs), CAP.msgs)
    CLOCK["d"] = "2026-10-31"
    W.px, W.asof = {"A": 10.0, "P": 133.1}, {"A": "2026-10-31", "P": "2026-10-31"}
    run("new", [A0, {**P0, "decision": "KEEP"}], mode="legacy")
    check("the next mark steps from the chained base (121 -> 133.1): NAV 110.25", st()["nav"] == 110.25, st()["nav"])

    # the same chain, but this run's quote is OLDER than the chained mark and the Director drops the seat:
    # the base is the chained mark (nav_from = its date), so neither the step nor the exit uses the older quote
    reset(BASE2)
    CLOCK["d"] = "2026-10-12"
    W.px, W.asof = {"A": 10.0, "P": 100.0}, {"A": "2026-10-10", "P": "2026-10-10"}
    W.eod = {"P": [("2026-10-13", 100.0), ("2026-10-16", 110.0), ("2026-10-23", 121.0)]}
    run("new", [A0, P0])
    for _d, _p in (("2026-10-17", 110.0), ("2026-10-24", 121.0)):
        CLOCK["d"] = _d
        W.px, W.asof = {"A": 10.0, "P": _p}, {"A": _d, "P": _d}
        old_mark([A0, P0])
    CLOCK["d"] = "2026-10-26"
    W.px, W.asof = {"A": 10.0, "P": 108.0}, {"A": "2026-10-16", "P": "2026-10-16"}
    run("new", [A0])
    legs = [c for c in st()["closed"] if c.get("symbol") == "P"]
    check("chained base + a quote older than it + drop: exits at the chained base 121 (+21%), NAV stays 105",
          len(legs) == 1 and legs[0]["exit_price"] == 121.0 and legs[0]["entry_price"] == 100.0
          and st()["nav"] == 105.0, (legs, st()["nav"]))

    # guard: the chain ended BEFORE the fill -> stepping from the fill cannot double count, so the fill is the base
    reset(BASE2)
    PG = {**P0, "cro_verdict": "B", "entry_posture": "wait_for_weakness", "cro_add_px": 90.0, "thesis_break_px": 70.0}
    CLOCK["d"] = "2026-10-12"
    W.px, W.asof = {"A": 10.0, "P": 100.0}, {"A": "2026-10-10", "P": "2026-10-10"}
    W.eod = {"P": [("2026-10-13", 97.0), ("2026-10-16", 95.0), ("2026-10-23", 92.0), ("2026-10-27", 89.0)]}
    run("new", [A0, PG])
    CLOCK["d"] = "2026-10-17"
    W.px, W.asof = {"A": 10.0, "P": 95.0}, {"A": "2026-10-17", "P": "2026-10-17"}
    old_mark([A0, PG])
    CLOCK["d"] = "2026-10-24"
    W.px, W.asof = {"A": 10.0, "P": 92.0}, {"A": "2026-10-24", "P": "2026-10-24"}
    old_mark([A0, PG])
    nav_chain = st()["nav"]
    CLOCK["d"] = "2026-10-28"
    run("new", [A0, {**PG, "decision": "KEEP"}])
    P = st()["positions"]["P"]
    check("fill dated after the last older-writer mark -> base = the fill (89), held until a mark dated after it",
          P.get("entry_price") == 89.0 and P.get("entry_date") == "2026-10-27" and P.get("nav_from") == "2026-10-27"
          and st()["last_prices"].get("P") == 89.0 and st()["nav"] == nav_chain, (P, st()["last_prices"]))
    check("... WARNs that older-writer steps chained it before its fill",
          any("before its fill" in m and "P" in m for m in CAP.msgs), CAP.msgs)

    print("\n=== P8 / finding 3: a rotation exit never uses a mark older than the fill ===")
    P120 = {**P0, "live_price": 120.0}
    reset(BASE2)
    CLOCK["d"] = "2026-10-12"
    W.px, W.asof = {"A": 10.0, "P": 120.0}, {"A": "2026-10-10", "P": "2026-10-10"}     # the scan stays at 10-10
    W.eod = {"P": [("2026-10-13", 100.0), ("2026-10-14", 101.0), ("2026-10-15", 102.0)]}
    run("new", [A0, P120])
    CLOCK["d"] = "2026-10-14"
    run("new", [A0, {**P120, "decision": "KEEP"}])
    P = st()["positions"]["P"]
    check("precondition: filled 100 on 10-13, base held (nav_from), NAV untouched",
          P.get("entry_price") == 100.0 and P.get("nav_from") == "2026-10-13"
          and st()["last_prices"].get("P") == 100.0 and st()["nav"] == 100.0, P)
    CLOCK["d"] = "2026-10-16"
    s = run("new", [A0])
    legs = [c for c in st()["closed"] if c.get("symbol") == "P"]
    check("dropped before a mark dated after its fill: exits at the fill (0%), not the stale 10-10 quote (+20%)",
          len(legs) == 1 and legs[0]["exit_price"] == 100.0 and legs[0]["return_pct"] == 0.0
          and st()["nav"] == 100.0, (legs, st()["nav"]))

    # the same, with the fill found in the very run that drops the seat (findings 1 + 3 together)
    for scan_day, scan_px, exp_x, exp_nav in (("2026-10-10", 120.0, 100.0, 100.0), ("2026-10-15", 102.0, 102.0, 101.0)):
        reset(BASE2)
        CLOCK["d"] = "2026-10-12"
        W.px, W.asof = {"A": 10.0, "P": 120.0}, {"A": "2026-10-10", "P": "2026-10-10"}
        W.eod = {"P": [("2026-10-13", 100.0), ("2026-10-14", 101.0), ("2026-10-15", 102.0)]}
        run("new", [A0, P120])
        CLOCK["d"] = "2026-10-16"
        W.px, W.asof = {"A": 10.0, "P": scan_px}, {"A": scan_day, "P": scan_day}
        s = run("new", [A0])
        legs = [c for c in st()["closed"] if c.get("symbol") == "P"]
        check(f"fill + drop in one run, scan dated {scan_day}: closed leg exits at {exp_x}, NAV {exp_nav} (they agree)",
              len(legs) == 1 and legs[0]["entry_price"] == 100.0 and legs[0]["exit_price"] == exp_x
              and st()["nav"] == exp_nav and "P" not in st()["positions"], (legs, st()["nav"]))
finally:
    _restore()

# ── 15. consumers: director ledger split + memo wording (no engine stubs needed) ─────────────────
print("\n=== consumers: director ledger + memo ===")
try:
    import _post_common as PC  # noqa: E402
    apx = {"memo": "Body."}
    pk = [{"symbol": "P", "decision": "KEEP", "entry_posture": "on_confirmation: Q3 print", "cro_add_event": "Q3 print"}]
    PC.reconcile_entry_posture(apx, pk, lambda s: {"verdict": "B", "conclusion": "Wait for the Q3 print.",
                                                   "pending_since": "2026-10-05"}, "memo", today="2026-10-12")
    check("memo says a pending seat is pending, never held",
          "P: pending since 2026-10-05 - not bought yet, waits on its gate" in apx["memo"]
          and "held since" not in apx["memo"].split("ENTRY DISCIPLINE", 1)[1].split("P:", 1)[1], apx["memo"][-400:])
except Exception as e:  # pragma: no cover
    check("memo pending wording", False, f"{type(e).__name__}: {e}")

try:
    import weekly_opus_refresh as WR  # noqa: E402  (import side effects: chdir backend/_opus_debate, mkdir exist_ok)
    _root, _ldh = WR.ROOT, WR._load_decision_history
    try:
        WR.ROOT = TMP
        WR._load_decision_history = lambda: {}
        (TMP / "prior.json").write_text(json.dumps({"apex_basket": [
            {"symbol": "A", "director_conviction": 70, "director_rationale": "held anchor"},
            {"symbol": "P", "director_conviction": 74, "director_rationale": "waits on the Q3 print"}]}), encoding="utf-8")
        (TMP / "track.json").write_text(json.dumps({"positions": {
            "A": {"entry_price": 9.0, "entry_date": "2026-09-01"},
            "P": {"entry_price": None, "entry_date": None, "entry_pending": True, "pending_since": "2026-10-05",
                  "gate": {"kind": "event", "event": "Q3 print"},
                  "washout_hit": {"date": "2026-10-19", "px": 84.0}}}, "closed": []}), encoding="utf-8")
        path, n_held, _n = WR.write_director_ledger("regime", TMP / "prior.json", TMP / "track.json")
        txt = Path(path).read_text(encoding="utf-8") if path else ""
        check("director ledger: HELD NOW lists bought seats only", "HELD NOW (1)" in txt and n_held == 1, txt[:400])
        check("director ledger: PENDING ENTRY section with gate + wash-out",
              "PENDING ENTRY (1)" in txt and "P: PENDING since 2026-10-05 (event: Q3 print); WASH-OUT 2026-10-19 at 84.0" in txt,
              txt)
        check("director ledger: a pending seat is never 'HELD since'", "P: HELD since" not in txt, txt)
        # finding 1 (P8): a drop is free only while the gate is unmet - a met gate is a buy and the drop a closed leg
        check("director ledger: dropping a pending seat is free ONLY while its gate is unmet",
              "costs nothing only if its gate has not been met" in txt and "logs a closed leg" in txt
              and "costs nothing and logs no closed leg" not in txt, txt[:900])
        for _lab, _txt in (("value Director prompt", WR.VALUE_DIRECTOR_PROMPT),
                           ("regime Director STEP 5", WR._WORKFLOW_TEMPLATE)):
            check(f"{_lab}: dropping a pending seat is free ONLY while its gate is unmet",
                  "costs nothing only if its gate has not been met" in _txt
                  and "costs nothing and logs no closed leg" not in _txt)
    finally:
        WR.ROOT, WR._load_decision_history = _root, _ldh
except Exception as e:  # pragma: no cover
    check("director ledger split", False, f"{type(e).__name__}: {e}")

# ── 17. consumers: the legacy weekly paper runner (CRO review finding 7, policy P11) ─────────────
# A pending seat publishes entry_price null. When FMP returns no quote (non-US listings are the likely
# case) the runner computed price = None and `None <= 0` raised TypeError, so that week's
# strategies/speculair history was never written. A pending seat is also not bought there any more.
print("\n=== consumers: legacy paper runner ===")
try:
    import paper_strategy_runner_speculair as PR  # noqa: E402  (import: logging config only)
    _qb, _q1 = PR.fmp_quote_batch, PR.fmp_quote
    try:
        PR.fmp_quote_batch = lambda syms: {}            # FMP returned nothing for these names
        PR.fmp_quote = lambda s: None
        pub = {"apex_basket": [
            {"symbol": "H", "entry_price": 50.0, "entry_date": "2026-09-01", "entry_pending": False},
            {"symbol": "P", "entry_price": None, "entry_date": None, "entry_pending": True},
            {"symbol": "Q", "entry_price": None, "entry_date": None}]}   # a null price without the flag
        picks = PR.build_basket_from_speculair(pub)
        check("paper runner: a pending seat is skipped (not bought at today's quote)",
              [p["symbol"] for p in picks] == ["H", "Q"], picks)
        try:
            keep, removed, added = PR.rotate_basket("2026-10-12", [], picks)
            check("paper runner: rotate with no quote + a null entry price skips the name (no TypeError)",
                  [p["symbol"] for p in keep] == ["H"] and added == [{"symbol": "H", "entry_price": 50.0}],
                  (keep, added))
        except TypeError as e:
            check("paper runner: rotate with no quote + a null entry price skips the name (no TypeError)", False, e)
        try:
            pos, _spy = PR.open_first_basket("2026-10-12", picks)
            check("paper runner: first basket with no quote + a null entry price skips the name (no TypeError)",
                  [p["symbol"] for p in pos] == ["H"], pos)
        except TypeError as e:
            check("paper runner: first basket with no quote + a null entry price skips the name (no TypeError)",
                  False, e)
    finally:
        PR.fmp_quote_batch, PR.fmp_quote = _qb, _q1
except Exception as e:  # pragma: no cover
    check("legacy paper runner", False, f"{type(e).__name__}: {e}")

try:
    import shutil
    shutil.rmtree(TMP, ignore_errors=True)
except Exception:  # pragma: no cover
    pass

print()
if SKIPS:
    print(f"SKIPPED: {len(SKIPS)} - {SKIPS}")
if FAILURES:
    print(f"FAILED: {len(FAILURES)} - {FAILURES}")
    sys.exit(1)
print("ALL PASS")
