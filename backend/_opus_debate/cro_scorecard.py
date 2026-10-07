#!/usr/bin/env python3
"""Quarterly CRO scorecard: do the regime-lane CRO's fields rank forward returns?

The regime-lane CRO (the moderator step of the weekly Opus debate) answers four questions -
THESIS (INTACT|IMPAIRED|BROKEN), VALUATION (typed valuation block), ENTRY (NOW|AT_LEVEL|ON_EVENT|NONE)
and FIT - and code derives the letter: A = INTACT+NOW; B = INTACT+AT_LEVEL (wait_kind price),
IMPAIRED+ON_EVENT (wait_kind proof) or INTACT+ON_EVENT (wait_kind event); C = BROKEN or entry NONE.
This script scores those fields against what the stock did next. It never edits a pipeline file;
the only file it writes in the repo is its own archive (_cro_write_archive.jsonl, see below).

PRE-REGISTERED METHOD (2026-10-06 study, approved by Bruno - change it only with a dated reason):
  * Panel: frontend/public/speculair_debate_history/*.json, DISTINCT CRO writes only - entries with
    carried=True are dropped, and so is an identical re-publish (same bull/bear/moderator text as the
    symbol's previous entry). Regime lane only: Basket-13 catalyst entries (source opus_catalyst*,
    lane equity_special_sit/special_sit) and the scale-out overlay (source opus_scaleout*) are out.
  * Entry = the first close STRICTLY AFTER the write date (decisions publish after the close).
  * Forward windows 20/40/60 trading days. A write whose window is not complete yet is CENSORED and
    left out of that horizon's means (counted in the tables, never silently mixed in).
  * Excess return = the name's return minus the equal-weight mean of every write on the same date;
    dates with fewer than 5 writes are dropped from the excess tests.
  * 95% CIs: bootstrap resampling write DATES (4000 draws), plus a per-symbol robustness row that
    keeps only each symbol's first write.
  * Scored: letter A/B/C; thesis_state; entry_mode; wait_kind; conviction and value_conviction
    (within-date Spearman, averaged over dates); implied upside from the TYPED valuation.base_fv_px
    only (never parsed out of prose); wash-out outcomes for B writes (fell >=10% or touched the named
    entry level within 60 trading days: the next 20/40-day path and the next CRO decision); and the
    _washout_ledger.jsonl when it exists.
  * Prices: FMP /stable/historical-price-eod/light. A series with a >40% one-day move inside the
    scored window is treated as a data error (pence/pound flips, unadjusted spin-offs) and the whole
    symbol is dropped - and listed in the report, because a genuine crash would be dropped too.

History entries published from 2026-10-06 on carry the typed fields themselves (publish_to_frontend
_hist_entry passthrough: valuation, thesis_state, entry_mode, entry_level_px, wait_kind, washout_type,
peer_position, macro_fit, verdict_agent_orig, grade_rederived, entry_floor_pct, washout_resolution,
thesis_break_px, ...). Older entries are filled, when possible, from the results_regime snapshots
(current + _archive_prev, matched on the date the values were produced - debated_at, else valuation.as_of,
else last_full_debate - never onto an earlier write) and from the apex baskets' cro_add_px. Because
the history keeps only the last 12 entries per symbol and results_regime is overwritten weekly, every
run also folds the panel into an append-only archive (default backend/_opus_debate/_cro_write_archive.jsonl)
so writes and their typed values survive truncation. publish_to_frontend.py runs `--collect-only` at
the end of every publish (best-effort); run it by hand if that line printed a WARN.

CLI:
  python backend/_opus_debate/cro_scorecard.py [--since YYYY-MM-DD] [--out PATH.md]
      [--cache-dir DIR] [--archive PATH.jsonl] [--asof YYYY-MM-DD] [--offline] [--refresh]
      [--collect-only] [--no-archive]
Defaults: --archive backend/_opus_debate/_cro_write_archive.jsonl; --cache-dir %LOCALAPPDATA%/cro_scorecard
(the system temp dir when LOCALAPPDATA is unset), so a scheduled run needs no flags.
Writes a plain-language markdown report (+ a per-record CSV next to it) and prints ONE summary line.
The FMP key is read silently from frontend/.env.local (or $FMP_API_KEY) and is never printed.
"""
from __future__ import annotations

import argparse
import bisect
import csv
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent                      # backend/_opus_debate
REPO = HERE.parents[1]
HIST_DIR = REPO / "frontend" / "public" / "speculair_debate_history"
SNAPSHOT_DIRS = (HERE / "results_regime", HERE / "_archive_prev" / "results_regime")
APEX_FILES = (HERE / "apex_basket_opus_regime.json", HERE / "apex_basket_value.json",
              HERE / "_archive_prev" / "apex_basket_opus_regime.json",
              HERE / "_archive_prev" / "apex_basket_value.json")
WASHOUT_LEDGER = HERE / "_washout_ledger.jsonl"   # written by weekly_opus_refresh.lane_stamp (2026-10-06)
ARCHIVE_DEFAULT = HERE / "_cro_write_archive.jsonl"  # tracked in the repo, like _cohort_ledger.jsonl
ENV_FILE = REPO / "frontend" / ".env.local"
FMP_URL = "https://financialmodelingprep.com/stable/historical-price-eod/light"
BENCH = "SPY"

# ---- pre-registered constants (2026-10-06) ------------------------------------------------------
HORIZONS = (20, 40, 60)
PRIMARY_H = 40                 # the bottom line reads this horizon; 20/60 are shown alongside
MIN_WRITES_PER_DATE = 5        # same-date cohorts smaller than this are dropped from excess tests
BOOT_ITERS = 4000
MIN_GROUP_N = 20               # a group needs this many complete-window writes to be judged...
MIN_GROUP_DATES = 5            # ...spread over at least this many write dates
MIN_RANK_DATES = 5             # rank fields: dates with a usable within-date Spearman
MIN_RANK_OBS = 40
SPEARMAN_MIN_PER_DATE = 8
MAX_ENTRY_GAP_DAYS = 7         # first close after the write must land within this many calendar days
JUMP_LIMIT = 0.40              # >40% one-day move = data error -> drop the symbol
WASH_DROP = 0.10
WASH_WINDOW = 60
POST_WINDOWS = (20, 40)
UPSIDE_SANE = (0.2, 5.0)       # base_fv_px / CRO live price outside this = unit error, not a view

THESIS_STATES = ("INTACT", "IMPAIRED", "BROKEN")
ENTRY_MODES = ("NOW", "AT_LEVEL", "ON_EVENT", "NONE")
WAIT_KINDS = ("price", "proof", "event")
WASHOUT_TYPES = ("MECHANICAL", "FACTOR", "NONE")
# washout_resolution.outcome as _post_common.derive_grade stamps it (2026-10-06), in plain words
WASHOUT_OUTCOME_PLAIN = {"BUY": "buy now", "WAIT_FOR_PROOF": "wait for proof",
                         "WAIT_FOR_EVENT": "wait for the event",
                         "WAIT_FOR_PRICE": "wait for a better price (a second price-wait - should not happen)",
                         "PASS": "pass for now", "PASS_BELOW_FLOOR": "pass for now - still below the entry bar"}
CATALYST_LANES = {"equity_special_sit", "special_sit", "catalyst", "b13", "basket13", "basket_13"}

# Expected direction, written down before looking: (better, worse).
EXPECTED_PAIRS = {
    "verdict": [("A", "B"), ("B", "C"), ("A", "C")],
    "thesis_state": [("INTACT", "IMPAIRED"), ("IMPAIRED", "BROKEN"), ("INTACT", "BROKEN")],
    "entry_mode": [("NOW", "AT_LEVEL"), ("NOW", "ON_EVENT"), ("NOW", "NONE"),
                   ("AT_LEVEL", "NONE"), ("ON_EVENT", "NONE")],
    "wait_kind": [("price", "proof"), ("price", "event"), ("proof", "event")],   # descriptive only: no expected sign
}
# The CRO's own letter before code derived it (verdict_agent_orig): same pre-registered order as the
# letter. Scored only on four-question writes, beside the derived letter on the SAME writes.
EXPECTED_PAIRS["verdict_agent_orig"] = EXPECTED_PAIRS["verdict"]
FIELD_LEVELS = {"verdict": ("A", "B", "C"), "verdict_agent_orig": ("A", "B", "C"), "thesis_state": THESIS_STATES,
                "entry_mode": ENTRY_MODES, "wait_kind": WAIT_KINDS}
DESCRIPTIVE = {"wait_kind"}

ARCHIVE_FIELDS = ("symbol", "date", "timestamp", "source", "lane_tag", "engine", "verdict", "conviction",
                  "value_conviction", "thesis_state", "entry_mode", "wait_kind", "entry_level_px",
                  "cro_add_px", "exit_level_px", "washout_type", "peer_position", "macro_fit",
                  "valuation", "typed_src", "level_src", "h", "archived_on",
                  # four-question grade stamps (2026-10-06 publisher passthrough / results_regime)
                  "verdict_agent_orig", "verdict_structural", "grade_schema", "grade_rederived",
                  "entry_floor_pct", "washout_outcome", "grade_flags")
GRADE_FIELDS = ("verdict_agent_orig", "verdict_structural", "grade_schema", "grade_rederived",
                "entry_floor_pct", "washout_outcome", "grade_flags")


def _default_cache_dir() -> Path:
    """%LOCALAPPDATA%/cro_scorecard - survives Windows Storage Sense, unlike the temp dir - else the temp dir."""
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) if base else Path(tempfile.gettempdir())) / "cro_scorecard"


# =============================================================================== small helpers
def _d(s):
    return date.fromisoformat(str(s)[:10])


def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) if v == v and v > 0 else None
    s = str(v).strip()
    m = re.fullmatch(r"[^\d\-]{0,4}([0-9][0-9,]*(?:\.[0-9]+)?)\s*[A-Za-z]{0,3}", s)
    if not m:
        return None
    try:
        x = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    return x if x > 0 else None


def _int(v):
    try:
        return int(v) if v is not None and str(v).strip() != "" else None
    except (TypeError, ValueError):
        return None


def _letter(v):
    s = str(v or "").strip().upper()[:1]
    return s if s in ("A", "B", "C") else None


def _pick(d, *paths):
    for p in paths:
        cur = d
        for k in (p if isinstance(p, tuple) else (p,)):
            cur = cur.get(k) if isinstance(cur, dict) else None
            if cur is None:
                break
        if cur not in (None, ""):
            return cur
    return None


def _enum(v, allowed=None):
    if v is None:
        return None
    if isinstance(v, dict):
        v = v.get("state") or v.get("mode") or v.get("value") or v.get("label") or v.get("fit")
        if v is None:
            return None
    s = re.sub(r"[\s\-]+", "_", str(v).strip().upper()).split(":")[0].strip("_")
    if not s:
        return None
    if allowed is not None:
        return s if s in allowed else "OTHER"
    return s if len(s) <= 24 and re.fullmatch(r"[A-Z0-9_]+", s) else None


def _text_hash(e):
    return hashlib.md5((str(e.get("bull_thesis")) + "|" + str(e.get("bear_thesis")) + "|" +
                        str(e.get("moderator_conclusion"))).encode("utf-8", "replace")).hexdigest()


def lane_of(e):
    src = str(e.get("source") or "").lower()
    lane = str(e.get("lane") or "").lower()
    if src.startswith("opus_catalyst") or lane in CATALYST_LANES or "catalyst" in lane:
        return "catalyst"
    if src.startswith("opus_scaleout"):
        return "scaleout"
    if src.startswith(("opus_regime", "opus_adhoc")):
        return "regime"
    return "other"


def slim_val(v):
    if not isinstance(v, dict):
        return None
    fv = _num(v.get("base_fv_px"))
    if not fv:
        return None
    out = {"base_fv_px": fv}
    for k in ("base_fv_px_orig", "live_price", "bear_px", "bull_px", "downside_floor_px"):
        x = _num(v.get(k))
        if x:
            out[k] = x
    for k in ("price_currency", "quote_listing", "as_of"):
        if v.get(k):
            out[k] = str(v.get(k))
    return out


def _atomic_write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _rederived(v):
    """grade_rederived as derive_grade stamps it ({"from": "A", "to": "B", ...}) -> "A->B"; True -> "yes"."""
    if isinstance(v, dict):
        a, b = _letter(v.get("from")), _letter(v.get("to"))
        return f"{a or '?'}->{b or '?'}"
    return "yes" if v is True else None


def _floor_pct(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 < v < 100 else None


def _washout_outcome(e):
    """The code-stamped wash-out outcome only (stamped_by grade-derive writes `outcome`); an agent-written
    washout_resolution without a bundle trigger carries no outcome and is ignored, as derive_grade does."""
    wr = e.get("washout_resolution")
    return _enum(wr.get("outcome")) if isinstance(wr, dict) and wr.get("outcome") else None


# =============================================================================== panel
def build_row(sym, e, h):
    val = slim_val(e.get("valuation"))
    wk = _pick(e, "wait_kind", ("entry", "wait_kind"), ("cro", "wait_kind"))
    wk = str(wk).strip().lower() if wk else None
    flags = e.get("grade_flags")
    return {
        "symbol": sym,
        "date": str(e.get("date"))[:10],
        "timestamp": e.get("timestamp"),
        "source": e.get("source"),
        "lane_tag": e.get("lane"),
        "engine": e.get("engine"),
        "verdict": _letter(e.get("verdict")),
        "conviction": _int(e.get("conviction")),
        "value_conviction": _int(e.get("value_conviction")),
        "thesis_state": _enum(_pick(e, "thesis_state", ("thesis", "state"), ("cro", "thesis_state")), THESIS_STATES),
        "entry_mode": _enum(_pick(e, "entry_mode", ("entry", "mode"), ("entry", "entry_mode"), ("cro", "entry_mode")), ENTRY_MODES),
        "wait_kind": wk if wk in WAIT_KINDS else None,
        "entry_level_px": _num(_pick(e, "entry_level_px", ("entry", "entry_level_px"), ("entry", "level_px"))),
        "cro_add_px": _num(e.get("cro_add_px")),
        "exit_level_px": _num(_pick(e, "exit_level_px", "thesis_break_px", ("entry", "exit_level_px"))),
        "washout_type": _enum(_pick(e, "washout_type", ("entry", "washout_type")), WASHOUT_TYPES),
        "peer_position": _enum(_pick(e, "peer_position", ("fit", "peer_position"))),
        "macro_fit": _enum(_pick(e, "macro_fit", ("fit", "macro_fit"))),
        "valuation": val,
        "typed_src": "history" if val else None,
        "level_src": "history" if (_pick(e, "entry_level_px", ("entry", "entry_level_px")) or e.get("cro_add_px")) else None,
        "h": h,
        # four-question grade stamps (2026-10-06): the CRO's own letter, the price-free letter, the
        # schema tag, the floor/trim re-derive, the quadrant floor, the wash-out outcome, coercion flags
        "verdict_agent_orig": _letter(e.get("verdict_agent_orig")),
        "verdict_structural": _letter(e.get("verdict_structural")),
        "grade_schema": str(e.get("grade_schema"))[:16] if e.get("grade_schema") else None,
        "grade_rederived": _rederived(e.get("grade_rederived")),
        "entry_floor_pct": _floor_pct(e.get("entry_floor_pct")),
        "washout_outcome": _washout_outcome(e),
        "grade_flags": [str(x)[:40] for x in flags if x] if isinstance(flags, list) and flags else None,
    }


def load_distinct_writes(hist_dir: Path):
    """Returns (distinct regime writes, funnel counts, timeline). The timeline keeps EVERY
    regime-lane entry per symbol as (date, 'write'|'carry', verdict) so a wash-out can be followed
    to whatever the pipeline did next - including carrying the old grade forward unexamined."""
    funnel = Counter()
    rows = []
    timeline = defaultdict(list)
    for f in sorted(hist_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            funnel["unreadable_files"] += 1
            continue
        if not isinstance(data, list):
            funnel["unreadable_files"] += 1
            continue
        sym = f.stem
        ents = sorted((e for e in data if isinstance(e, dict)),
                      key=lambda e: (str(e.get("date", ""))[:10], str(e.get("timestamp") or "")))
        prev = None
        for e in ents:
            funnel["history_entries"] += 1
            h = _text_hash(e)
            dup = h == prev
            prev = h
            lane = lane_of(e)
            if lane != "regime":
                funnel[f"excluded_{lane}_lane"] += 1
                continue
            d = str(e.get("date"))[:10]
            if e.get("carried") is True:
                funnel["dropped_carried"] += 1
                timeline[sym].append((d, "carry", _letter(e.get("verdict"))))
                continue
            if dup:
                funnel["dropped_identical_republish"] += 1
                timeline[sym].append((d, "carry", _letter(e.get("verdict"))))
                continue
            rows.append(build_row(sym, e, h))
            timeline[sym].append((d, "write", _letter(e.get("verdict"))))
    funnel["distinct_regime_writes_in_history"] = len(rows)
    return rows, funnel, timeline


def merge_archive(rows, archive: Path | None, today: str):
    """Union of the live history panel with the append-only archive (history keeps only 12
    entries per symbol). Live rows win; archived typed values fill gaps; then consecutive
    identical-text rows across the union are dropped again."""
    arch = {}
    if archive and archive.exists():
        for line in archive.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue
            if isinstance(r, dict) and r.get("symbol") and r.get("date"):
                arch[(r["symbol"], r["date"])] = r
    cur = {(r["symbol"], r["date"]): r for r in rows}
    restored = 0
    for k, a in arch.items():
        if k in cur:
            r = cur[k]
            for fld, v in a.items():
                if r.get(fld) in (None, "") and v not in (None, ""):
                    r[fld] = v
        else:
            r = {fld: a.get(fld) for fld in ARCHIVE_FIELDS}
            r["from_archive"] = True
            cur[k] = r
            restored += 1
    by = defaultdict(list)
    for r in cur.values():
        by[r["symbol"]].append(r)
    out, redup = [], 0
    for sym, lst in by.items():
        lst.sort(key=lambda r: (r["date"], str(r.get("timestamp") or "")))
        prev = None
        for r in lst:
            if r.get("h") and r["h"] == prev:
                redup += 1
                continue
            prev = r.get("h")
            r.setdefault("archived_on", today)
            out.append(r)
    return out, restored, redup


def save_archive(rows, archive: Path):
    lines = []
    for r in sorted(rows, key=lambda r: (r["symbol"], r["date"])):   # null fields omitted: readers .get() them
        lines.append(json.dumps({k: r.get(k) for k in ARCHIVE_FIELDS if r.get(k) is not None},
                                ensure_ascii=False, default=str))
    _atomic_write(archive, "\n".join(lines) + "\n")


def _after_write(as_of, wdate, slack=3):
    """True when a value dated `as_of` is more than `slack` days newer than the write dated `wdate` -
    filling it onto that write would be look-ahead. An unparseable date is never called look-ahead."""
    a = str(as_of or "")[:10]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", a) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(wdate or "")[:10]):
        return False
    return (_d(a) - _d(wdate)).days > slack


def scrub_lookahead(rows):
    """Self-heal for the archive (2026-10-06 review, finding 5). Before attach_snapshots matched on the
    date the typed values were produced, a delta or refresh snapshot was matched on the last_full_debate
    it copies from its anchor, so an older write got a valuation dated weeks later - and merge_archive
    refilled it from the archive on every run. Drop a snapshot-sourced valuation (and a snapshot-sourced
    level beside it) whose as_of is more than 3 days after the write it sits on. Values the history entry
    carried itself are never touched. Returns how many rows were cleaned."""
    n = 0
    for r in rows:
        v = r.get("valuation")
        if not (str(r.get("typed_src") or "").startswith("snapshot:") and isinstance(v, dict)
                and _after_write(v.get("as_of"), r.get("date"))):
            continue
        r.pop("valuation", None)
        r.pop("typed_src", None)
        if str(r.get("level_src") or "").startswith("snapshot:"):
            for fld in ("entry_level_px", "cro_add_px", "level_src"):
                r.pop(fld, None)
        n += 1
    return n


def attach_snapshots(rows, snap_dirs=SNAPSHOT_DIRS):
    """Fill typed fields the history entry lacks from results_regime snapshots, matched to the
    symbol's distinct write dated 0-3 days on/after the date the snapshot's typed values were PRODUCED:
    debated_at, else valuation.as_of, else (only when both are missing) last_full_debate.
    A delta or refresh record copies last_full_debate from its anchor while its valuation and
    four-question fields are dated today, so matching on last_full_debate put later values on an older
    write (look-ahead; 2026-10-06 review, finding 5). A write dated before the production date is never
    filled, a valuation dated more than 3 days after the write is never filled, and a delta / refresh
    snapshot whose own history entry already carries the typed fields is skipped."""
    by = defaultdict(list)
    for r in rows:
        by[r["symbol"]].append(r)
    n_val = n_other = 0
    for sd in snap_dirs:
        if not sd.exists():
            continue
        tag = f"snapshot:{sd.relative_to(HERE).as_posix()}"
        for f in sd.glob("*.json"):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(d, dict):
                continue
            sym = d.get("symbol") or f.stem
            v = d.get("valuation") if isinstance(d.get("valuation"), dict) else {}
            made = str(d.get("debated_at") or v.get("as_of") or d.get("last_full_debate") or "")[:10]
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", made):
                continue
            cand = [r for r in by.get(sym, []) if 0 <= (_d(r["date"]) - _d(made)).days <= 3]
            if not cand:
                continue
            r = min(cand, key=lambda r: (_d(r["date"]) - _d(made)).days)
            if str(d.get("update_mode") or "").strip().lower() in ("delta", "refresh") and r.get("typed_src") == "history":
                continue                         # its own history entry carries the typed fields
            sv = slim_val(v)
            if sv and not r.get("valuation") and not _after_write(sv.get("as_of"), r["date"]):
                r["valuation"], r["typed_src"] = sv, tag
                n_val += 1
            fill = build_row(sym, d, r.get("h"))
            for fld in ("thesis_state", "entry_mode", "wait_kind", "entry_level_px", "cro_add_px",
                        "exit_level_px", "washout_type", "peer_position", "macro_fit") + GRADE_FIELDS:
                if r.get(fld) in (None, "") and fill.get(fld) not in (None, ""):
                    r[fld] = fill[fld]
                    n_other += 1
                    if fld in ("entry_level_px", "cro_add_px") and not r.get("level_src"):
                        r["level_src"] = tag
    return n_val, n_other


def attach_apex_levels(rows, files=APEX_FILES):
    """Legacy source of an entry level: the Director's cro_add_px on current/previous apex seats."""
    by = defaultdict(list)
    for r in rows:
        by[r["symbol"]].append(r)
    n = 0
    for f in files:
        if not f.exists():
            continue
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        ts = d.get("post_anchor_ts")
        try:
            bdate = datetime.fromtimestamp(float(ts), tz=timezone.utc).date().isoformat()
        except (TypeError, ValueError):
            bdate = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc).date().isoformat()
        for seat in d.get("apex_basket") or []:
            if not isinstance(seat, dict):
                continue
            lvl = _num(seat.get("cro_add_px"))
            if not lvl:
                continue
            cand = [r for r in by.get(seat.get("symbol"), []) if 0 <= (_d(bdate) - _d(r["date"])).days <= 10]
            if not cand:
                continue
            r = max(cand, key=lambda r: r["date"])
            if not (r.get("entry_level_px") or r.get("cro_add_px")):
                r["cro_add_px"], r["level_src"] = lvl, f"apex:{f.relative_to(HERE).as_posix()}"
                n += 1
    return n


# =============================================================================== prices
def _fmp_key():
    try:
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            m = re.match(r"\s*FMP_API_KEY\s*=\s*['\"]?([^'\"\s]+)", line)
            if m:
                return m.group(1)
    except OSError:
        pass
    return os.environ.get("FMP_API_KEY")


class Prices:
    """FMP light EOD closes, cached per symbol under <cache>/px/. A cached series is reused when it
    was fetched for the same as-of date and covers the needed start (or always, with --offline)."""

    def __init__(self, cache_dir: Path, start: str, asof: str, offline=False, refresh=False):
        self.dir = cache_dir / "px"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.start, self.asof, self.offline, self.refresh = start, asof, offline, refresh
        self.key = None if offline else _fmp_key()
        self.stats = Counter()
        self.series = {}

    def _path(self, sym):
        return self.dir / (re.sub(r"[^A-Za-z0-9_.\-]", "_", sym) + ".json")

    def _filter(self, rows):
        out = {}
        for d, c in rows:
            if d <= self.asof and c and c > 0:
                out[d] = float(c)
        return sorted(out.items())

    def _get(self, sym):
        fp = self._path(sym)
        if fp.exists():
            try:
                c = json.loads(fp.read_text(encoding="utf-8"))
                fresh = c.get("asof") == self.asof and str(c.get("from", "9999")) <= self.start
                if self.offline or (fresh and not self.refresh):
                    self.stats["cache"] += 1
                    return sym, self._filter(c.get("rows") or [])
            except Exception:
                pass
        if self.offline or not self.key:
            self.stats["missing_offline" if self.offline else "no_key"] += 1
            return sym, []
        q = urllib.parse.urlencode({"symbol": sym, "from": self.start, "to": self.asof, "apikey": self.key})
        data, err = None, None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(f"{FMP_URL}?{q}", timeout=40) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as ex:      # never str(ex) a URL: it carries the key
                err = f"HTTP{ex.code}"
                if ex.code in (429, 500, 502, 503, 504):
                    time.sleep(1.5 * (attempt + 1))
                    continue
                break
            except Exception as ex:
                err = type(ex).__name__
                time.sleep(1.0 * (attempt + 1))
        if not isinstance(data, list):
            self.stats[f"fail_{err or 'shape'}"] += 1
            return sym, []
        rows = []
        for x in data:
            if isinstance(x, dict) and x.get("date"):
                c = x.get("price", x.get("close"))
                try:
                    rows.append([str(x["date"])[:10], float(c)])
                except (TypeError, ValueError):
                    continue
        _atomic_write(fp, json.dumps({"symbol": sym, "from": self.start, "asof": self.asof,
                                      "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                      "rows": rows}))
        self.stats["fetched"] += 1
        return sym, self._filter(rows)

    def load(self, symbols):
        with ThreadPoolExecutor(max_workers=8) as ex:
            for sym, ser in ex.map(self._get, sorted(set(symbols))):
                self.series[sym] = ser
        return self.series


def first_bad_jump(ser, from_date):
    for i in range(1, len(ser)):
        if ser[i][0] < from_date:
            continue
        a, b = ser[i - 1][1], ser[i][1]
        if a > 0 and abs(b / a - 1) > JUMP_LIMIT:
            return {"from": ser[i - 1][0], "px_from": a, "to": ser[i][0], "px_to": b, "move": b / a - 1}
    return None


def price_features(r, ser, dates):
    i0 = bisect.bisect_right(dates, r["date"])           # first close STRICTLY after the write date
    if i0 >= len(ser):
        return "no_entry_close_yet"
    if (_d(ser[i0][0]) - _d(r["date"])).days > MAX_ENTRY_GAP_DAYS:
        return "entry_gap"
    p0, last = ser[i0][1], len(ser) - 1
    f = {"entry_date": ser[i0][0], "p0": p0, "i0": i0, "n_av": last - i0,
         "r_latest": ser[last][1] / p0 - 1, "latest_date": ser[last][0]}
    for h in HORIZONS:
        if i0 + h <= last:
            f[f"r{h}"], f[f"cens{h}"] = ser[i0 + h][1] / p0 - 1, False
        else:
            f[f"r{h}"], f[f"cens{h}"] = None, True
    return f


def demean(rows):
    thin = Counter()
    for h in HORIZONS:
        by = defaultdict(list)
        for r in rows:
            r[f"x{h}"] = None
            if r.get(f"r{h}") is not None:
                by[r["date"]].append(r)
        for d, lst in by.items():
            if len(lst) < MIN_WRITES_PER_DATE:
                thin[h] += len(lst)
                continue
            m = sum(r[f"r{h}"] for r in lst) / len(lst)
            for r in lst:
                r[f"x{h}"] = r[f"r{h}"] - m
    return thin


def implied_upside(r, key="base_fv_px"):
    """Typed only: base_fv_px over the CRO's own live_price in the same block (same currency/units)."""
    v = r.get("valuation") or {}
    fv = _num(v.get(key)) or (_num(v.get("base_fv_px")) if key == "base_fv_px_orig" else None)
    lp = _num(v.get("live_price"))
    if fv and lp and UPSIDE_SANE[0] < fv / lp < UPSIDE_SANE[1]:
        return fv / lp - 1
    return None


def derive_letter(ts, em):
    """The approved mapping on the EFFECTIVE fields (derive_grade rewrites entry_mode when it coerces
    or re-derives, so a correctly derived record always maps; None = a combination code never emits)."""
    if ts == "BROKEN" or em == "NONE":
        return "C"
    if ts == "INTACT" and em == "NOW":
        return "A"
    if (ts == "INTACT" and em in ("AT_LEVEL", "ON_EVENT")) or (ts == "IMPAIRED" and em == "ON_EVENT"):
        return "B"
    return None


def exit_px(r):
    """The exit level derive_grade guards against: the highest of thesis_break_px (exit_level_px here),
    valuation.bear_px and valuation.downside_floor_px - all in the CRO's own price units."""
    v = r.get("valuation") or {}
    lv = [x for x in (_num(r.get("exit_level_px")), _num(v.get("bear_px")), _num(v.get("downside_floor_px"))) if x]
    return max(lv) if lv else None


# =============================================================================== statistics
def _rng(seed, *tags):
    """One generator per (field, horizon): results do not depend on the order the scores are computed in."""
    return np.random.default_rng([int(seed), zlib.crc32("|".join(tags).encode("utf-8"))])


def rankdata(a):
    a = np.asarray(a, dtype=float)
    sorter = np.argsort(a, kind="mergesort")
    inv = np.empty(len(a), dtype=np.intp)
    inv[sorter] = np.arange(len(a))
    s = a[sorter]
    obs = np.r_[True, s[1:] != s[:-1]]
    dense = obs.cumsum()[inv]
    count = np.r_[np.nonzero(obs)[0], len(obs)]
    return 0.5 * (count[dense] + count[dense - 1] + 1)


def spearman(x, y):
    if len(x) < 4:
        return None
    rx, ry = rankdata(x), rankdata(y)
    rx, ry = rx - rx.mean(), ry - ry.mean()
    den = np.sqrt((rx * rx).sum() * (ry * ry).sum())
    return float((rx * ry).sum() / den) if den > 0 else None


def _ci(arr, need):
    arr = np.asarray(arr, dtype=float)
    ok = arr[np.isfinite(arr)]
    if len(ok) < need:
        return None
    lo, hi = np.percentile(ok, [2.5, 97.5])
    return float(lo), float(hi)


def score_categorical(rows, field, key, seed, levels=None):
    rng = _rng(seed, field, key)
    levels = list(levels or FIELD_LEVELS[field])
    gi = {lv: i for i, lv in enumerate(levels)}
    sub = [r for r in rows if r.get(field) in gi and r.get(key) is not None]
    groups = {}
    h = int(key[1:])
    for lv in levels:
        vals = [r[key] for r in sub if r[field] == lv]
        cens = sum(1 for r in rows if r.get(field) == lv and r.get(f"cens{h}") is True)
        groups[lv] = {"n": len(vals), "n_dates": len({r["date"] for r in sub if r[field] == lv}),
                      "n_symbols": len({r["symbol"] for r in sub if r[field] == lv}),
                      "mean": float(np.mean(vals)) if vals else None,
                      "median": float(np.median(vals)) if vals else None,
                      "hit": (sum(1 for v in vals if v > 0) / len(vals)) if vals else None,
                      "ci": None, "censored": cens}
    pairs = {}
    if sub:
        dates = sorted({r["date"] for r in sub})
        di = {d: i for i, d in enumerate(dates)}
        S = np.zeros((len(dates), len(levels)))
        N = np.zeros((len(dates), len(levels)))
        for r in sub:
            S[di[r["date"]], gi[r[field]]] += r[key]
            N[di[r["date"]], gi[r[field]]] += 1
        W = rng.multinomial(len(dates), np.full(len(dates), 1.0 / len(dates)), size=BOOT_ITERS)
        with np.errstate(invalid="ignore", divide="ignore"):
            M = (W @ S) / (W @ N)
        need = int(0.95 * BOOT_ITERS)
        for lv in levels:
            if groups[lv]["n"]:
                groups[lv]["ci"] = _ci(M[:, gi[lv]], need)
        for a, b in EXPECTED_PAIRS.get(field, []):
            if a in gi and b in gi and groups[a]["n"] and groups[b]["n"]:
                pairs[(a, b)] = {"diff": groups[a]["mean"] - groups[b]["mean"],
                                 "ci": _ci(M[:, gi[a]] - M[:, gi[b]], need)}
    return {"field": field, "key": key, "groups": groups, "pairs": pairs, "n": len(sub),
            "n_present": sum(1 for r in rows if r.get(field) in gi)}


def first_write_rows(rows):
    first = {}
    for r in sorted(rows, key=lambda r: (r["date"], str(r.get("timestamp") or ""))):
        first.setdefault(r["symbol"], r)
    return list(first.values())


def score_rank(rows, feat, h, seed):
    """Within-date Spearman of feat vs the h-day return (identical to vs excess: demeaning is a
    within-date shift), averaged over dates; CI = bootstrap over dates. Robustness: pooled Spearman
    of feat vs date-demeaned excess on each symbol's first write, CI by date-cluster bootstrap."""
    rng = _rng(seed, feat, str(h))
    rk, xk = f"r{h}", f"x{h}"
    by = defaultdict(list)
    for r in rows:
        if r.get(feat) is not None and r.get(xk) is not None:
            by[r["date"]].append(r)
    rhos = []
    for d, lst in sorted(by.items()):
        if len(lst) >= SPEARMAN_MIN_PER_DATE:
            rho = spearman([float(r[feat]) for r in lst], [r[rk] for r in lst])
            if rho is not None and rho == rho:
                rhos.append((d, rho, len(lst)))
    out = {"feat": feat, "h": h, "n_dates": len(rhos), "n_obs": sum(x[2] for x in rhos),
           "n_any": sum(len(v) for v in by.values()), "mean_rho": None, "ci": None, "pos_dates": 0,
           "first_write": None, "per_date": rhos}
    if rhos:
        vals = np.array([x[1] for x in rhos])
        out["mean_rho"] = float(vals.mean())
        out["pos_dates"] = int((vals > 0).sum())
        if len(vals) >= 3:
            bs = vals[rng.integers(0, len(vals), size=(BOOT_ITERS, len(vals)))].mean(axis=1)
            out["ci"] = (float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5)))
    fw = [r for r in first_write_rows([r for r in rows if r.get(feat) is not None]) if r.get(xk) is not None]
    if len(fw) >= 20:
        x = np.array([float(r[feat]) for r in fw])
        y = np.array([r[xk] for r in fw])
        rho = spearman(x, y)
        dates = sorted({r["date"] for r in fw})
        idx = defaultdict(list)
        for i, r in enumerate(fw):
            idx[r["date"]].append(i)
        idx = [np.array(idx[d]) for d in dates]
        bs = []
        if len(dates) >= MIN_RANK_DATES:
            for _ in range(BOOT_ITERS):
                pick = np.concatenate([idx[j] for j in rng.integers(0, len(dates), size=len(dates))])
                s = spearman(x[pick], y[pick])
                if s is not None:
                    bs.append(s)
        out["first_write"] = {"rho": rho, "n": len(fw), "n_dates": len(dates),
                              "ci": _ci(bs, int(0.9 * BOOT_ITERS)) if (bs and len(dates) >= MIN_RANK_DATES) else None}
    out["n_present"] = sum(1 for r in rows if r.get(feat) is not None)
    return out


def bucket_table(rows, feat, key):
    b = defaultdict(list)
    for r in rows:
        if r.get(feat) is not None and r.get(key) is not None:
            b[r[feat]].append(r[key])
    return {k: (len(v), float(np.mean(v))) for k, v in sorted(b.items())}


# =============================================================================== wash-outs
def level_in_fmp_units(r, ser, dates):
    lvl = r.get("entry_level_px") or r.get("cro_add_px")
    if not lvl:
        return None
    lp = _num((r.get("valuation") or {}).get("live_price"))
    j = bisect.bisect_right(dates, r["date"]) - 1           # FMP close on/before the write date
    ref = ser[j][1] if j >= 0 else r["p0"]
    if lp:
        k = ref / lp
        for scale in (1.0, 100.0, 0.01):
            if 0.7 * scale < k < 1.3 * scale:
                lv = lvl * scale
                return lv if 0.3 * r["p0"] < lv <= 1.3 * r["p0"] else None
    for scale in (1.0, 100.0, 0.01):
        lv = lvl * scale
        if 0.3 * r["p0"] < lv <= 1.05 * r["p0"]:
            return lv
    return None


def _ret_between(ser_map_dates, ser, d_from, d_to):
    i = bisect.bisect_right(ser_map_dates, d_from) - 1
    j = bisect.bisect_right(ser_map_dates, d_to) - 1
    if i < 0 or j < 0 or j <= i:
        return None
    return ser[j][1] / ser[i][1] - 1


def washout_eval(r, ser, dates, spy, spy_dates):
    i0, last, p0 = r["i0"], len(ser) - 1, r["p0"]
    end = min(i0 + WASH_WINDOW, last)
    out = {"full_window": i0 + WASH_WINDOW <= last, "days_seen": end - i0, "triggered": False}
    lvl = level_in_fmp_units(r, ser, dates)
    out["has_level"] = lvl is not None
    t10 = next((i for i in range(i0 + 1, end + 1) if ser[i][1] <= (1 - WASH_DROP) * p0), None)
    tl = next((i for i in range(i0, end + 1) if ser[i][1] <= lvl), None) if lvl else None
    cands = [t for t in (t10, tl) if t is not None]
    if not cands:
        return out
    t = min(cands)
    kind = "both" if (t10 == t and tl == t) else ("level" if tl == t else "drop10")
    pt = ser[t][1]
    out.update({"triggered": True, "t": t, "trigger_date": ser[t][0], "days_to_trigger": t - i0,
                "kind": kind, "trigger_px": pt})
    for h in POST_WINDOWS:
        if t + h <= last:
            out[f"post{h}"] = ser[t + h][1] / pt - 1
            sr = _ret_between(spy_dates, spy, ser[t][0], ser[t + h][0]) if spy else None
            out[f"rel{h}"] = (out[f"post{h}"] - sr) if sr is not None else None
            fp = "neither"
            for _, c in ser[t + 1:t + h + 1]:
                if c >= 1.10 * pt:
                    fp = "up10_first"
                    break
                if c <= 0.90 * pt:
                    fp = "down10_first"
                    break
            out[f"fp{h}"] = fp
        else:
            out[f"post{h}"] = out[f"rel{h}"] = out[f"fp{h}"] = None
    return out


def classify_next(n):
    if n is None:
        return "no re-debate yet"
    ts, v = n.get("thesis_state"), n.get("verdict")
    if ts == "BROKEN" or v == "C":
        return "pass (C / broken)"
    if v == "A":
        return "buy (A)"
    if v == "B":
        wk = n.get("wait_kind")
        if wk == "proof" or (ts == "IMPAIRED" and n.get("entry_mode") == "ON_EVENT"):
            return "wait for proof (B)"
        if wk == "event" or (ts == "INTACT" and n.get("entry_mode") == "ON_EVENT"):
            return "wait for the event (B)"
        if wk == "price" or n.get("entry_mode") == "AT_LEVEL":
            return "second price-wait (B) - rule breach"
        return "wait, kind unknown (B, pre-schema)"
    return "unknown"


def read_washout_ledger(path: Path):
    if not path.exists():
        return None
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if isinstance(r, dict):
            out.append(r)
    return out


# =============================================================================== formatting
def pct(x, nd=2):
    return "-" if x is None else f"{x * 100:+.{nd}f}%"


def pts(x, nd=2):
    return "-" if x is None else f"{x * 100:+.{nd}f} pts"


def ci_s(c, scale=100.0, nd=1, unit=""):
    if not c:
        return "-"
    return f"[{c[0] * scale:+.{nd}f}, {c[1] * scale:+.{nd}f}]{unit}"


def rho_s(x):
    return "-" if x is None else f"{x:+.3f}"


def res_plain(res):
    """A wash-out resolution token in plain words (LEGACY_<letter> = an older-format record)."""
    res = str(res or "").upper()
    if res.startswith("LEGACY_"):
        return f"older-format record (letter {res[7:8] or '?'})"
    return WASHOUT_OUTCOME_PLAIN.get(res, res.lower().replace("_", " ") or "unknown")


TRIGGER_PLAIN = {"FELL_10PCT": "fell 10%", "LEVEL_REACHED": "entry level reached"}


def md_table(headers, body):
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in body]
    return out


def _ok_group(g):
    return g["n"] >= MIN_GROUP_N and g["n_dates"] >= MIN_GROUP_DATES


def _borderline(ci):
    """A 95% range whose nearer end sits within 5% of its width from zero: the verdict could flip
    on bootstrap noise or one more debate date - say so instead of pretending it is settled."""
    if not ci:
        return False
    lo, hi = ci
    return min(abs(lo), abs(hi)) < 0.05 * (hi - lo)


def pair_reading(res, a, b, v):
    small = [f"{x} n={res['groups'][x]['n']}/{res['groups'][x]['n_dates']}d" for x in (a, b)
             if not _ok_group(res["groups"][x])]
    if small:
        return "too few to judge (" + ", ".join(small) + ")"
    if not v["ci"]:
        return "too few dates for a range"
    return "separated" if v["ci"][0] > 0 else ("REVERSED" if v["ci"][1] < 0 else "not separated")


def robust_line(res):
    parts = [f"{lv} n={g['n']} {pct(g['mean'])} {ci_s(g['ci'], unit='%')}" + ("" if _ok_group(g) else " (too few)")
             for lv, g in res["groups"].items() if g["n"]]
    pairs = [f"{a}-{b} {pts(v['diff'], 1)} {ci_s(v['ci'], unit=' pts')} {pair_reading(res, a, b, v)}"
             for (a, b), v in res["pairs"].items()]
    return ("; ".join(parts) or "n=0") + (" | " + "; ".join(pairs) if pairs else "")


def cat_verdict(res):
    field = res["field"]
    groups = res["groups"]
    total = sum(g["n"] for g in groups.values())
    if res.get("n_present", 0) == 0:
        return "NOT EMITTED", "no scored write carries this field yet (n=0)"
    if total == 0:
        return "TOO FEW", (f"{res['n_present']} writes carry it, none with a complete "
                           f"{res['key'][1:]}-day window yet")
    small = [f"{lv} n={g['n']}/{g['n_dates']}d" for lv, g in groups.items() if g["n"] and not _ok_group(g)]
    testable = [(p, v) for p, v in res["pairs"].items()
                if _ok_group(groups[p[0]]) and _ok_group(groups[p[1]]) and v["ci"]]
    notes = []
    for (a, b), v in testable:
        lo, hi = v["ci"]
        tag = "separated" if lo > 0 else ("REVERSED" if hi < 0 else "not separated")
        if _borderline(v["ci"]):
            tag += " (borderline: range ends at ~0)"
        notes.append(f"{a} vs {b} {pts(v['diff'], 1)} {ci_s(v['ci'])} {tag}")
    if small:
        notes.append("too few to judge: " + ", ".join(small))
    if not testable:
        return "TOO FEW", "; ".join(notes) or "no group reaches the minimum sample"
    sep = [p for p, v in testable if v["ci"][0] > 0]
    rev = [p for p, v in testable if v["ci"][1] < 0]
    if field in DESCRIPTIVE:
        return ("DIFFERS" if sep or rev else "NO DIFFERENCE"), "; ".join(notes)
    if rev:
        return "INVERTED", "; ".join(notes)
    if sep:
        return "RANKS", "; ".join(notes)
    return "NO EVIDENCE", "; ".join(notes)


def rank_verdict(res):
    if res.get("n_present", 0) == 0:
        return "NOT EMITTED", "no scored write carries this field yet (n=0)"
    if res["n_dates"] < MIN_RANK_DATES or res["n_obs"] < MIN_RANK_OBS or not res["ci"]:
        return "TOO FEW", (f"{res['n_present']} writes carry it, {res['n_any']} with a complete {res['h']}-day "
                           f"window, {res['n_dates']} dates with >= {SPEARMAN_MIN_PER_DATE} such writes "
                           f"(need >= {MIN_RANK_DATES} dates and >= {MIN_RANK_OBS} writes)")
    lo, hi = res["ci"]
    tag = "RANKS" if lo > 0 else ("INVERTED" if hi < 0 else "NO EVIDENCE")
    return tag, (f"mean within-date rho {rho_s(res['mean_rho'])} {ci_s(res['ci'], 1, 3)} over "
                 f"{res['n_dates']} dates / {res['n_obs']} writes (positive on {res['pos_dates']})"
                 + (" - BORDERLINE: the range ends at ~0, one more date can flip this verdict"
                    if _borderline(res["ci"]) else ""))


# =============================================================================== main
def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--since", help="score only writes dated on/after YYYY-MM-DD")
    ap.add_argument("--out", help="markdown report path (default <cache-dir>/cro_scorecard_<asof>.md)")
    ap.add_argument("--cache-dir", help="price cache + default report dir (default: %%LOCALAPPDATA%%/cro_scorecard, "
                                        "else <system temp>/cro_scorecard)")
    ap.add_argument("--archive", help="append-only write archive (default backend/_opus_debate/_cro_write_archive.jsonl)")
    ap.add_argument("--no-archive", action="store_true", help="neither read nor update the archive")
    ap.add_argument("--asof", help="last close to use, YYYY-MM-DD (default: yesterday - drops today's partial bar)")
    ap.add_argument("--offline", action="store_true", help="use cached prices only, no network")
    ap.add_argument("--refresh", action="store_true", help="re-fetch every price series")
    ap.add_argument("--collect-only", action="store_true", help="only fold history + typed snapshots into the archive")
    ap.add_argument("--seed", type=int, default=20261006)
    a = ap.parse_args(argv)

    today = date.today().isoformat()
    asof = a.asof or (date.today() - timedelta(days=1)).isoformat()
    cache_dir = Path(a.cache_dir) if a.cache_dir else _default_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    archive = None if a.no_archive else (Path(a.archive) if a.archive else ARCHIVE_DEFAULT)

    # ---- panel
    rows, funnel, timeline = load_distinct_writes(HIST_DIR)
    if archive:
        rows, restored, redup = merge_archive(rows, archive, today)
        funnel["restored_from_archive"] = restored
        funnel["dropped_identical_republish_across_archive"] = redup
        seen = {(s, d) for s, lst in timeline.items() for d, _, _ in lst}
        for r in rows:                                   # archive-only writes join the timeline too
            if (r["symbol"], r["date"]) not in seen:
                timeline[r["symbol"]].append((r["date"], "write", r.get("verdict")))
    for lst in timeline.values():
        lst.sort()
    n_scrub = scrub_lookahead(rows)                      # archive self-heal (finding 5); 0 once clean
    if n_scrub:
        funnel["lookahead_valuations_dropped"] = n_scrub
    n_typed_snap, n_other_snap = attach_snapshots(rows)
    n_apex_lvl = attach_apex_levels(rows)
    if archive:
        save_archive(rows, archive)
    if a.collect_only:
        typed = sum(1 for r in rows if r.get("valuation"))
        four_q = sum(1 for r in rows if r.get("thesis_state") and r.get("entry_mode"))
        print(f"CRO scorecard collect-only {today}: archive {archive} holds {len(rows)} distinct regime writes "
              f"({typed} with a typed valuation, {four_q} with the four-question fields; +{n_typed_snap} typed "
              f"matched this run, {funnel.get('restored_from_archive', 0)} restored past the 12-entry history cap"
              + (f"; {n_scrub} look-ahead valuations dropped" if n_scrub else "") + ")")
        return 0

    panel = [r for r in rows if r["date"] <= asof and (not a.since or r["date"] >= a.since)]
    funnel["outside_since_or_after_asof"] = len(rows) - len(panel)
    if not panel:
        print("CRO scorecard: no regime-lane writes in range - nothing to score")
        return 1

    # ---- prices
    start = (_d(min(r["date"] for r in panel)) - timedelta(days=10)).isoformat()
    ledger = read_washout_ledger(WASHOUT_LEDGER)
    led_syms = {str(x.get("symbol")) for x in (ledger or []) if x.get("symbol")}
    px = Prices(cache_dir, start, asof, a.offline, a.refresh)
    series = px.load({r["symbol"] for r in panel} | {BENCH} | led_syms)
    spy = series.get(BENCH) or []
    spy_dates = [d for d, _ in spy]
    last_close = max((s[-1][0] for s in series.values() if s), default=None)

    bad = {}
    first_date = defaultdict(lambda: "9999")
    for r in panel:
        first_date[r["symbol"]] = min(first_date[r["symbol"]], r["date"])
    for sym, ser in series.items():
        if sym == BENCH or not ser or sym not in first_date:
            continue
        j = first_bad_jump(ser, first_date[sym])
        if j:
            bad[sym] = j
    dates_of = {s: [d for d, _ in ser] for s, ser in series.items()}

    priced, drop = [], Counter()
    for r in panel:
        ser = series.get(r["symbol"]) or []
        if r["symbol"] in bad:
            drop["bad_series_symbol_dropped"] += 1
            continue
        if not ser:
            drop["no_price_series"] += 1
            continue
        f = price_features(r, ser, dates_of[r["symbol"]])
        if isinstance(f, str):
            drop[f] += 1
            continue
        r.update(f)
        if r.get("wait_kind") is None and r.get("verdict") == "B":
            r["wait_kind"] = ("price" if r.get("entry_mode") == "AT_LEVEL" else
                              "proof" if (r.get("thesis_state") == "IMPAIRED" and r.get("entry_mode") == "ON_EVENT")
                              else "event" if (r.get("thesis_state") == "INTACT" and r.get("entry_mode") == "ON_EVENT")
                              else None)
        r["implied_upside"] = implied_upside(r)
        r["implied_upside_cro"] = implied_upside(r, "base_fv_px_orig")
        priced.append(r)
    thin = demean(priced)
    fw_ids = {id(r) for r in first_write_rows(priced)}
    for r in priced:
        r["first_write"] = id(r) in fw_ids

    # ---- scoring
    cats = {}
    for field in ("verdict", "thesis_state", "entry_mode", "wait_kind"):
        cats[field] = {}
        for h in HORIZONS:
            cats[field][h] = score_categorical(priced, field, f"x{h}", a.seed)
            cats[field][(h, "fw")] = score_categorical([r for r in priced if r["first_write"]], field, f"x{h}", a.seed)
    eng5 = [r for r in priced if str(r.get("engine") or "").startswith("opus-5")]
    cats["verdict"][(PRIMARY_H, "opus5")] = score_categorical(eng5, "verdict", f"x{PRIMARY_H}", a.seed)
    # four-question writes only (2026-10-06 schema): the code-derived letter beside the CRO's own letter
    # on the SAME writes - does the floor/trim re-derive and the coercion add or destroy ranking?
    g4 = [r for r in priced if r.get("grade_schema") or (r.get("verdict_agent_orig") and r.get("thesis_state")
                                                         and r.get("entry_mode"))]
    if g4:
        cats["verdict"][(PRIMARY_H, "g4")] = score_categorical(g4, "verdict", f"x{PRIMARY_H}", a.seed)
        cats["verdict_agent_orig"] = {PRIMARY_H: score_categorical(g4, "verdict_agent_orig", f"x{PRIMARY_H}", a.seed)}
    # stability: split the debate dates that have a complete primary window into an early and a late half
    pdates = sorted({r["date"] for r in priced if r.get(f"x{PRIMARY_H}") is not None})
    split_date = pdates[len(pdates) // 2] if len(pdates) >= 2 * MIN_GROUP_DATES else None
    if split_date:
        for tag, keep in (("early", lambda d: d < split_date), ("late", lambda d: d >= split_date)):
            cats["verdict"][(PRIMARY_H, tag)] = score_categorical([r for r in priced if keep(r["date"])],
                                                                  "verdict", f"x{PRIMARY_H}", a.seed)
    extra_cats = {}
    for field in ("peer_position", "macro_fit", "washout_type"):
        lv = [k for k, n in Counter(r.get(field) for r in priced if r.get(field)).most_common(8)]
        if lv:
            extra_cats[field] = score_categorical(priced, field, f"x{PRIMARY_H}", a.seed, levels=lv)
    ranks = {}
    for feat in ("conviction", "value_conviction", "implied_upside", "implied_upside_cro"):
        ranks[feat] = {h: score_rank(priced, feat, h, a.seed) for h in HORIZONS}

    # ---- wash-outs (B writes) + next CRO decision
    row_at = {(r["symbol"], r["date"]): r for r in rows}   # next decision may be a write we could not price
    wash = []
    for r in priced:
        if r.get("verdict") != "B":
            continue
        ser = series[r["symbol"]]
        w = washout_eval(r, ser, dates_of[r["symbol"]], spy, spy_dates)
        w["row"] = r
        wash.append(w)
    # One EPISODE per (symbol, trigger date): weekly B re-writes of the same name that trip on the same
    # close share one post-trigger path, so path and next-step stats are counted once per episode.
    episodes = {}
    for w in sorted((w for w in wash if w["triggered"]), key=lambda w: w["row"]["date"]):
        k = (w["row"]["symbol"], w["trigger_date"])
        if k in episodes:
            episodes[k]["n_writes"] += 1
            continue
        w["n_writes"] = 1
        sym = k[0]
        nxt = next(((d, kind, v) for d, kind, v in timeline.get(sym, [])
                    if d > w["row"]["date"] and d >= w["trigger_date"]), None)
        if nxt is None:
            w["next_class"], w["next_desc"] = "not re-covered yet", "-"
        elif nxt[1] == "carry":
            w["next_class"] = f"carried forward unchanged ({nxt[2] or '?'}), no re-debate"
            w["next_desc"] = f"{nxt[0]} carry {nxt[2] or '?'}"
        else:
            w["next_class"] = classify_next(row_at.get((sym, nxt[0])) or {"verdict": nxt[2]})
            w["next_desc"] = f"{nxt[0]} {nxt[2] or '?'}"
        if nxt is not None:                      # SPY-relative path after the next step, uniform for all kinds
            ds, ser = dates_of[sym], series[sym]
            i0 = bisect.bisect_right(ds, nxt[0])
            for h in POST_WINDOWS:
                if i0 + h < len(ser):
                    rr = ser[i0 + h][1] / ser[i0][1] - 1
                    sr = _ret_between(spy_dates, spy, ser[i0][0], ser[i0 + h][0]) if spy else None
                    w[f"next_rel{h}"] = rr - sr if sr is not None else None
        episodes[k] = w
    ep = list(episodes.values())

    # ---- wash-out ledger. Field names as weekly_opus_refresh.lane_stamp writes them (2026-10-06): symbol,
    # date / resolved_date (the wash-out debate's run date), trigger_kind FELL_10PCT|LEVEL_REACHED,
    # resolution (derive_grade's outcome BUY|WAIT_FOR_PROOF|WAIT_FOR_EVENT|WAIT_FOR_PRICE|PASS|
    # PASS_BELOW_FLOOR, or LEGACY_<letter> for an older-format record), coerced, prior_letter, new_letter,
    # new_thesis_state. Older/foreign spellings stay accepted. Every row is listed; unpriced ones carry no return.
    ledger_rows = []
    for x in ledger or []:
        sym = str(x.get("symbol") or "")
        d0 = str(_pick(x, "resolved_date", "resolution_date", "debate_date", "trigger_date",
                       "washout_date", "triggered_on", "date") or "")[:10]
        if not sym or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d0):
            continue
        res = str(_pick(x, "resolution", "outcome", "resolved_as", "decision", "next_decision") or "unknown").strip()
        trig = _enum(_pick(x, "trigger_kind", "trigger", "kind"))
        rec = {"symbol": sym, "date": d0, "resolution": res.upper()[:40], "trigger": trig,
               "coerced": x.get("coerced") is True, "prior_letter": _letter(x.get("prior_letter")),
               "new_letter": _letter(x.get("new_letter")), "new_thesis": _enum(x.get("new_thesis_state"), THESIS_STATES),
               "priced": False, "why_unpriced": None}
        ser = series.get(sym) or []
        if sym in bad:
            rec["why_unpriced"] = "bad price series"
        elif not ser:
            rec["why_unpriced"] = "no price series"
        else:
            ds = dates_of[sym]
            i0 = bisect.bisect_right(ds, d0)
            if i0 >= len(ser):
                rec["why_unpriced"] = "no close after the debate yet"
            else:
                rec["priced"] = True
                for h in POST_WINDOWS:
                    if i0 + h < len(ser):
                        rr = ser[i0 + h][1] / ser[i0][1] - 1
                        sr = _ret_between(spy_dates, spy, ser[i0][0], ser[i0 + h][0]) if spy else None
                        rec[f"r{h}"], rec[f"rel{h}"] = rr, (rr - sr if sr is not None else None)
        ledger_rows.append(rec)

    # ---- integrity checks on the new schema
    schema_rows = [r for r in priced if r.get("thesis_state") and r.get("entry_mode")]
    mism = [r for r in schema_rows if derive_letter(r["thesis_state"], r["entry_mode"]) not in (None, r.get("verdict"))]
    unmapped = [r for r in schema_rows if derive_letter(r["thesis_state"], r["entry_mode"]) is None]
    broken_b = [r for r in priced if r.get("thesis_state") == "BROKEN" and r.get("verdict") == "B"]
    # an add level at/below the exit (thesis break / bear / downside floor), on price-waits only
    lvl_below_exit = [r for r in priced if (r.get("entry_level_px") and r.get("entry_mode") in (None, "AT_LEVEL")
                                            and exit_px(r) and r["entry_level_px"] <= exit_px(r))]
    # 2026-10-06 grade stamps: how often code changed the CRO's letter, and A writes below the entry floor
    overridden = Counter(f"{r['verdict_agent_orig']}->{r.get('verdict')}" for r in schema_rows
                         if r.get("verdict_agent_orig") and r.get("verdict") and r["verdict_agent_orig"] != r["verdict"])
    rederived_ct = Counter(r["grade_rederived"] for r in priced if r.get("grade_rederived"))
    a_below_floor = [r for r in priced if r.get("verdict") == "A" and r.get("entry_floor_pct")
                     and r.get("implied_upside") is not None and r["implied_upside"] * 100 < r["entry_floor_pct"]]
    flag_ct = Counter(f for r in schema_rows for f in (r.get("grade_flags") or []))
    hist_wo = Counter(r["washout_outcome"] for r in rows if r.get("washout_outcome"))

    # ---- pace (for "when will the new fields be scoreable")
    recent = [r for r in rows if r["date"] >= (_d(asof) - timedelta(days=56)).isoformat()]
    pace = len(recent) / 8.0
    typed_n = sum(1 for r in priced if r.get("valuation"))

    # ================================================================== report
    out_md = Path(a.out) if a.out else cache_dir / f"cro_scorecard_{asof}.md"
    L = []
    P = PRIMARY_H
    L.append(f"# CRO scorecard - regime lane - as of {last_close or asof}")
    L.append("")
    L.append(f"Generated {today}. Prices are FMP daily closes up to {last_close or '-'} (today's partial bar is "
             f"never used). Writes scored: {len(priced)} distinct CRO writes on {len({r['symbol'] for r in priced})} "
             f"names across {len({r['date'] for r in priced})} debate dates"
             + (f", dated on/after {a.since}" if a.since else "") + ".")
    L.append("")
    L.append("**How to read this.** Every number compares a name with the other names the CRO wrote up on the "
             "*same day*: \"excess\" is the stock's return minus the average return of that day's writes, so a "
             "market-wide rally or sell-off cancels out. Returns start at the first close *after* the write "
             f"(decisions publish after the close) and run {', '.join(str(h) for h in HORIZONS)} trading days. "
             "The 95% ranges come from re-drawing whole debate dates 4,000 times, so they are honest about how "
             "few independent dates we really have. A field \"ranks\" only when its 95% range excludes zero in "
             f"the direction we wrote down in advance. The bottom line reads the {P}-day window.")
    L.append("")

    # ---- bottom line
    L.append("## Bottom line")
    L.append("")
    bl = []
    summary_bits = []
    v_tag, v_note = cat_verdict(cats["verdict"][P])
    bl.append(("Letter (A/B/C)", v_tag, v_note))
    summary_bits.append(f"letter {v_tag}")
    for field, label in (("thesis_state", "Thesis state"), ("entry_mode", "Entry mode"), ("wait_kind", "Wait kind (price / proof / event)")):
        t, n = cat_verdict(cats[field][P])
        bl.append((label, t, n))
        summary_bits.append(f"{field} {t}")
    for feat, label in (("conviction", "Conviction"), ("value_conviction", "Value conviction"),
                        ("implied_upside", "Implied upside (typed base_fv_px)")):
        t, n = rank_verdict(ranks[feat][P])
        bl.append((label, t, n))
        r40 = ranks[feat][P]
        summary_bits.append(f"{feat} {t}" + (f" rho {r40['mean_rho']:+.2f}" if r40["mean_rho"] is not None else "")
                            + (" (borderline)" if t in ("RANKS", "INVERTED", "NO EVIDENCE") and _borderline(r40["ci"]) else ""))
    L += md_table(["Field", f"Verdict ({P}d)", "Evidence (95% range)"], [(a_, f"**{b_}**", c_) for a_, b_, c_ in bl])
    L.append("")
    # plain sentences
    vg = cats["verdict"][P]["groups"]
    vp = cats["verdict"][P]["pairs"]
    if ("B", "C") in vp and vp[("B", "C")]["ci"]:
        d_, c_ = vp[("B", "C")]["diff"], vp[("B", "C")]["ci"]
        verb = ("a real gap at this sample size" if c_[0] > 0 else
                "and the gap runs the WRONG way" if c_[1] < 0 else "but the 95% range still includes zero")
        L.append(f"- **B vs C.** Over {P} trading days, B-graded names beat C-graded names written the same day by "
                 f"{d_ * 100:+.1f} points (95% range {c_[0] * 100:+.1f} to {c_[1] * 100:+.1f}) - {verb}. "
                 f"(B n={vg['B']['n']}, C n={vg['C']['n']}.)")
    if split_date:
        e_, l_ = (cats["verdict"][(P, t)]["pairs"].get(("B", "C")) for t in ("early", "late"))
        if e_ and l_:
            same = (e_["diff"] > 0) == (l_["diff"] > 0)
            L.append(f"- **Is the B-vs-C gap stable?** Debate dates before {split_date}: {pts(e_['diff'], 1)} "
                     f"{ci_s(e_['ci'], unit=' pts')}; from {split_date} on: {pts(l_['diff'], 1)} "
                     f"{ci_s(l_['ci'], unit=' pts')}. "
                     + ("Same sign in both halves." if same else
                        "**The sign flips between halves** - the pooled result leans on the early dates; "
                        "treat it as unproven until the late half confirms it."))
    if vg["A"]["n"] < MIN_GROUP_N or vg["A"]["n_dates"] < MIN_GROUP_DATES:
        L.append(f"- **A is not judgeable yet.** Only {vg['A']['n']} A writes have a complete {P}-day window "
                 f"(on {vg['A']['n_dates']} dates); we need at least {MIN_GROUP_N} on {MIN_GROUP_DATES}+ dates. "
                 "Any statement about whether A beats B is noise at this size.")
    new_fields_missing = [f for f in ("thesis_state", "entry_mode", "wait_kind") if cats[f][P]["n_present"] == 0]
    if new_fields_missing:
        L.append(f"- **New four-question fields are not in the data yet** ({', '.join(new_fields_missing)}: n=0). "
                 f"They become scoreable once each compared group has {MIN_GROUP_N}+ writes with a complete "
                 f"{P}-day window on {MIN_GROUP_DATES}+ dates. At the current pace (~{pace:.0f} distinct regime writes "
                 f"a week) the first {P}-day windows complete about {P // 5 + 1} weeks after the first run that emits "
                 "them, and a rare state such as BROKEN or IMPAIRED+ON_EVENT will take longer. From 2026-10-06 the "
                 "publisher copies these fields (and the valuation block) into each dated debate-history entry, and "
                 "the collect step at the end of every publish keeps them in the archive past the 12-entry cap.")
    for feat, label in (("conviction", "Conviction"), ("value_conviction", "Value conviction"),
                        ("implied_upside", "Typed implied upside")):
        rr = ranks[feat][P]
        t, _ = rank_verdict(rr)
        if t in ("RANKS", "INVERTED", "NO EVIDENCE"):
            halves = ""
            if split_date:
                er = [x[1] for x in rr["per_date"] if x[0] < split_date]
                lr = [x[1] for x in rr["per_date"] if x[0] >= split_date]
                if er and lr:
                    halves = (f" Early dates average rho {np.mean(er):+.2f} ({len(er)} dates), late dates "
                              f"{np.mean(lr):+.2f} ({len(lr)} dates)"
                              + (" - the sign flips, so treat it as unproven." if (np.mean(er) > 0) != (np.mean(lr) > 0)
                                 else "."))
            L.append(f"- **{label}.** Within a debate date, higher {feat.replace('_', ' ')} went with "
                     f"{'higher' if rr['mean_rho'] > 0 else 'lower'} {P}-day returns on average (rho "
                     f"{rr['mean_rho']:+.2f}, 95% range {rr['ci'][0]:+.2f} to {rr['ci'][1]:+.2f}, "
                     f"{rr['n_dates']} dates) - " + {"RANKS": "it ranks.", "INVERTED": "it ranks BACKWARDS.",
                                                     "NO EVIDENCE": "not distinguishable from no relation."}[t]
                     + (" **Borderline:** one end of the range sits at about zero, so this verdict can flip "
                        "with the next few debate dates." if _borderline(rr["ci"]) else "")
                     + halves)
        elif t == "TOO FEW":
            extra = ""
            if feat == "implied_upside":
                extra = (f" Only {typed_n} of {len(priced)} scored writes carry a typed valuation block at all - "
                         "debate-history entries store it only from 2026-10-06 on; older writes have it only where a "
                         "results_regime snapshot was on disk (or archived) when a run saw them.")
            L.append(f"- **{label}.** Too few to judge at {P} days: {rr['n_present']} writes carry it, "
                     f"{rr['n_any']} with a complete window, {rr['n_dates']} usable dates." + extra)
        else:
            L.append(f"- **{label}.** Not in the data yet (n=0).")
    trig = [w for w in wash if w["triggered"]]
    full = [w for w in wash if w["full_window"]]
    full_trig = [w for w in full if w["triggered"]]
    if wash:
        p20 = [w["post20"] for w in ep if w.get("post20") is not None]
        L.append(f"- **Wash-outs.** {len(full_trig)} of {len(full)} B writes with a full {WASH_WINDOW}-day window "
                 f"({(len(full_trig) / len(full) * 100) if full else 0:.0f}%) fell 10% or touched the named entry level "
                 f"({len(ep)} distinct episodes over all windows). "
                 + (f"Buying at the trigger close returned {np.mean(p20) * 100:+.1f}% on average over the next 20 days "
                    f"(median {np.median(p20) * 100:+.1f}%, n={len(p20)} episodes); +10% came before another -10% in "
                    f"{sum(1 for w in ep if w.get('fp20') == 'up10_first')} of them and the reverse in "
                    f"{sum(1 for w in ep if w.get('fp20') == 'down10_first')}. "
                    if p20 else "")
                 + "See section 8 for what the pipeline did next.")
    L.append("- **Caveats that bind every line above:** overlapping weekly writes on the same names, several "
             "fields x three horizons tested at once (expect about one false 'separated' in twenty), and only "
             f"{len({r['date'] for r in priced if r.get('x' + str(P)) is not None})} independent debate dates "
             f"with a complete {P}-day window.")
    L.append("")

    # ---- funnel
    L.append("## Data funnel")
    L.append("")
    fun_rows = [(k.replace("_", " "), v) for k, v in funnel.items()]
    for src, n in Counter(r.get("typed_src") or "none" for r in rows).most_common():
        fun_rows.append((f"writes by typed-valuation source: {src}", n))
    fun_rows += [("typed valuations newly matched from results_regime this run", n_typed_snap),
                 ("entry levels newly taken from apex-basket cro_add_px this run", n_apex_lvl)]
    fun_rows += [(f"not priced: {k.replace('_', ' ')}", v) for k, v in drop.items()]
    fun_rows += [("priced and scored", len(priced))]
    fun_rows += [(f"excluded from {h}d excess: date cohort < {MIN_WRITES_PER_DATE} writes", thin.get(h, 0)) for h in HORIZONS]
    fun_rows += [(f"price series: {k}", v) for k, v in sorted(px.stats.items())]
    L += md_table(["Step", "Count"], fun_rows)
    L.append("")

    # ---- categorical sections
    def cat_section(field, title, intro):
        L.append(f"## {title}")
        L.append("")
        L.append(intro)
        L.append("")
        if cats[field][P]["n_present"] == 0:
            L.append(f"_n = 0: no scored write carries `{field}` yet. Nothing to judge._")
            L.append("")
            return
        for h in HORIZONS:
            res = cats[field][h]
            body = []
            for lv, g in res["groups"].items():
                if not g["n"] and not g["censored"]:
                    continue
                body.append((lv, g["n"], g["n_dates"], g["n_symbols"], pct(g["mean"]), ci_s(g["ci"], unit="%"),
                             pct(g["median"]), "-" if g["hit"] is None else f"{g['hit'] * 100:.0f}%", g["censored"],
                             "yes" if _ok_group(g) else f"no (< {MIN_GROUP_N} writes or < {MIN_GROUP_DATES} dates)"))
            L.append(f"**{h} trading days** (excess vs same-date writes)")
            L.append("")
            L.extend(md_table(["Group", "n", "dates", "names", "mean excess", "95% range", "median", "beat cohort",
                               "censored (window not complete)", "judgeable"], body))
            if res["pairs"]:
                L.append("")
                L.extend(md_table(["Comparison", "gap", "95% range", "reading"],
                                  [(f"{a_} minus {b_}", pts(v["diff"]), ci_s(v["ci"], unit=" pts"),
                                    pair_reading(res, a_, b_, v)) for (a_, b_), v in res["pairs"].items()]))
            L.append("")
        L.append(f"Robustness - each symbol's FIRST write only ({P}d): " + robust_line(cats[field][(P, "fw")]))
        L.append("")

    cat_section("verdict", "1. The letter (A / B / C)",
                "Expected order, written down in advance: A beats B beats C. A = thesis intact and buy now; "
                "B = wait (for a better price, for proof or for the event); C = pass for now.")
    L.append(f"Robustness - later era only (history entries stamped engine opus-5, i.e. published after the "
             f"engine label changed) ({P}d): " + robust_line(cats["verdict"][(P, "opus5")]))
    L.append("")
    if (P, "g4") in cats["verdict"]:
        L.append(f"Four-question writes only ({P}d) - the letter code derived: " + robust_line(cats["verdict"][(P, "g4")]))
        L.append("")
        L.append("Same writes - the CRO's own letter before code derived it: " + robust_line(cats["verdict_agent_orig"][P])
                 + ". If the derived letter separates better than the CRO's own, the entry-floor re-derive and the "
                 "coercions are adding signal; if worse, they are costing it.")
        L.append("")
    if split_date:
        L.append(f"Stability - debate dates before {split_date} ({P}d): " + robust_line(cats["verdict"][(P, "early")]))
        L.append("")
        L.append(f"Stability - debate dates from {split_date} on ({P}d): " + robust_line(cats["verdict"][(P, "late")]))
        L.append("")
    upl = defaultdict(list)
    for r in priced:
        if r.get("implied_upside") is not None and r.get("verdict"):
            upl[r["verdict"]].append(r["implied_upside"])
    if upl:
        L.append("Does the letter just restate the upside? Median typed implied upside at the write: " + "; ".join(
            f"{g} {np.median(v) * 100:+.1f}% (n={len(v)})" for g, v in sorted(upl.items())) + ".")
        L.append("")
    cat_section("thesis_state", "2. Thesis state (INTACT / IMPAIRED / BROKEN)",
                "Expected order: INTACT beats IMPAIRED beats BROKEN.")
    cat_section("entry_mode", "3. Entry mode (NOW / AT_LEVEL / ON_EVENT / NONE)",
                "Expected: NOW beats everything else and every waiting mode beats NONE, measured from the write date. "
                "A correct AT_LEVEL call can still trail NOW here (the CRO expected a dip first) - the wash-out "
                "section is where a price-wait earns its keep.")
    cat_section("wait_kind", "4. Wait kind on B writes (price / proof / event)",
                "Descriptive only - no direction was pre-registered. Shows whether waiting for a better price, "
                "waiting for proof and waiting for the event behave differently.")
    if extra_cats:
        L.append("### Exploratory: other enum fields (no pre-registered direction)")
        L.append("")
        for field, res in extra_cats.items():
            L.append(f"`{field}` ({P}d): " + "; ".join(
                f"{lv} n={g['n']} {pct(g['mean'])} {ci_s(g['ci'], unit='%')}" for lv, g in res["groups"].items()))
        L.append("")

    # ---- rank sections
    def rank_section(feat, title, intro):
        L.append(f"## {title}")
        L.append("")
        L.append(intro)
        L.append("")
        body = []
        for h in HORIZONS:
            rr = ranks[feat][h]
            t, _ = rank_verdict(rr)
            fwr = rr["first_write"]
            body.append((f"{h}d", rr["n_any"], rr["n_dates"], rho_s(rr["mean_rho"]), ci_s(rr["ci"], 1, 3),
                         f"{rr['pos_dates']}/{rr['n_dates']}",
                         (f"{rho_s(fwr['rho'])} {ci_s(fwr['ci'], 1, 3)} n={fwr['n']}" if fwr else "-"), f"**{t}**"))
        L.extend(md_table(["Window", "writes", "dates used", "mean within-date rho", "95% range", "dates rho>0",
                           "first-write-per-name rho (95%)", "verdict"], body))
        L.append("")

    rank_section("conviction", "5. Conviction (1-5)",
                 f"Within each debate date (>= {SPEARMAN_MIN_PER_DATE} writes), do higher-conviction names do better? "
                 "Rank correlation per date, then averaged; the range re-draws dates.")
    bt = bucket_table(priced, "conviction", f"x{P}")
    if bt:
        L.append(f"Mean {P}-day excess by conviction: " + "; ".join(f"{k}: {pct(m)} (n={n})" for k, (n, m) in bt.items()))
        L.append("")
    rank_section("value_conviction", "6. Value conviction (1-5)",
                 "Same test for the value-book conviction the CRO writes alongside.")
    bt = bucket_table(priced, "value_conviction", f"x{P}")
    if bt:
        L.append(f"Mean {P}-day excess by value conviction: " + "; ".join(f"{k}: {pct(m)} (n={n})" for k, (n, m) in bt.items()))
        L.append("")
    nt = Counter(r.get("typed_src") or "none" for r in priced)
    rank_section("implied_upside", "7. Implied upside from the typed fair value",
                 "Upside = valuation.base_fv_px / the CRO's own valuation.live_price - 1 (same block, same units). "
                 "Never parsed from prose: writes without a typed block are simply absent. Typed-block source counts: "
                 + ", ".join(f"{k} {v}" for k, v in nt.most_common()) + ".")
    xs = sorted((r["implied_upside"], r[f"x{P}"]) for r in priced
                if r.get("implied_upside") is not None and r.get(f"x{P}") is not None)
    if len(xs) >= 50:
        q = len(xs) // 5
        parts = [xs[i * q:(i + 1) * q] if i < 4 else xs[4 * q:] for i in range(5)]
        L.append(f"Quintiles of implied upside -> mean {P}-day excess: " + " | ".join(
            f"Q{i + 1} [{p_[0][0] * 100:+.0f}..{p_[-1][0] * 100:+.0f}%] n={len(p_)} {np.mean([b for _, b in p_]) * 100:+.2f}%"
            for i, p_ in enumerate(parts)))
        L.append("")
    else:
        L.append(f"_Only {len(xs)} typed writes have a complete {P}-day window - quintiles need 50._")
        L.append("")
    rank_section("implied_upside_cro", "7b. Implied upside, CRO's original fair value (before skeptic corrections)",
                 "Uses valuation.base_fv_px_orig when the skeptic corrected the number, else base_fv_px. If this ranks "
                 "better than section 7, the corrections are destroying signal; if worse, they are adding it.")

    # ---- wash-outs
    L.append("## 8. Wash-outs on B writes")
    L.append("")
    L.append(f"A B write \"washes out\" when, within {WASH_WINDOW} trading days of entry, the close falls "
             f"{WASH_DROP * 100:.0f}% below the entry close or touches the named entry level "
             "(entry_level_px, else the Director's cro_add_px). Under the new rule the next debate must then resolve: "
             "thesis intact -> buy, impaired -> wait for proof, broken -> pass - never a second price-wait.")
    L.append("")
    if not wash:
        L.append("_No priced B writes._")
        L.append("")
    else:
        kinds = Counter(w.get("kind") for w in ep)
        L += md_table(["", "count"], [
            ("B writes priced", len(wash)),
            (f"... with a full {WASH_WINDOW}-day window", len(full)),
            ("... with a usable entry level (entry_level_px / cro_add_px)", sum(1 for w in wash if w["has_level"])),
            ("B writes triggered (any window seen so far)", len(trig)),
            ("B writes triggered, full-window writes only (rate)",
             f"{len(full_trig)} ({(len(full_trig) / len(full) * 100) if full else 0:.0f}%)"),
            ("distinct episodes (one per name + trigger date)", len(ep)),
            ("episode trigger: -10% / level / both", f"{kinds.get('drop10', 0)} / {kinds.get('level', 0)} / {kinds.get('both', 0)}"),
            ("median trading days to trigger", (f"{np.median([w['days_to_trigger'] for w in ep]):.0f}" if ep else "-")),
            ("distinct names", len({w['row']['symbol'] for w in ep})),
        ])
        L.append("")
        body = []
        for h in POST_WINDOWS:
            pv = [w[f"post{h}"] for w in ep if w.get(f"post{h}") is not None]
            rv = [w[f"rel{h}"] for w in ep if w.get(f"rel{h}") is not None]
            fp = Counter(w[f"fp{h}"] for w in ep if w.get(f"fp{h}"))
            nn = sum(fp.values())
            body.append((f"next {h}d", len(pv), pct(float(np.mean(pv))) if pv else "-",
                         pct(float(np.median(pv))) if pv else "-", pct(float(np.mean(rv))) if rv else "-",
                         f"{fp['up10_first']} ({fp['up10_first'] / nn * 100:.0f}%)" if nn else "-",
                         f"{fp['down10_first']} ({fp['down10_first'] / nn * 100:.0f}%)" if nn else "-",
                         fp["neither"] if nn else "-",
                         sum(1 for w in ep if w.get(f"post{h}") is None)))
        L.append("Path after the trigger close, per episode (as if bought at the trigger close):")
        L.append("")
        L += md_table(["Window", "n", "mean", "median", "mean minus SPY", "+10% came first", "-10% came first",
                       "neither", "censored"], body)
        L.append("")
        nc = defaultdict(list)
        for w in ep:
            nc[w["next_class"]].append(w)
        body = []
        for k, lst in sorted(nc.items(), key=lambda kv: -len(kv[1])):
            r20 = [w["next_rel20"] for w in lst if w.get("next_rel20") is not None]
            r40 = [w["next_rel40"] for w in lst if w.get("next_rel40") is not None]
            body.append((k, len(lst), f"{len(r20)}: {pct(float(np.mean(r20)))}" if r20 else "-",
                         f"{len(r40)}: {pct(float(np.mean(r40)))}" if r40 else "-"))
        L.append("What the pipeline did at the first regime-lane entry on/after the trigger (a fresh CRO write, or "
                 "the old grade carried forward without a re-debate), and how the name did over the next 20/40 "
                 "trading days from that entry, minus SPY:")
        L.append("")
        L += md_table(["Next step", "episodes", "next 20d minus SPY (n: mean)", "next 40d minus SPY (n: mean)"], body)
        L.append("")
        breach = len(nc.get("second price-wait (B) - rule breach", []))
        unknown = len(nc.get("wait, kind unknown (B, pre-schema)", []))
        carried = sum(len(v) for k, v in nc.items() if k.startswith("carried forward"))
        L.append(f"Rule check: {breach} second price-waits under the new schema; {carried} episodes where the grade "
                 "was carried forward with no re-debate (the new rule forces a re-debate)"
                 + (f"; {unknown} pre-schema B->B re-grades whose wait kind cannot be told apart." if unknown else "."))
        L.append("")
        L.append("Per-record: every wash-out episode")
        L.append("")
        body = []
        for w in sorted(ep, key=lambda w: (w["trigger_date"], w["row"]["symbol"])):
            r = w["row"]
            body.append((r["symbol"], r["date"], w["n_writes"], f"{r['p0']:.4g}", w["kind"], w["trigger_date"],
                         w["days_to_trigger"], pct(w.get("post20"), 1), pct(w.get("post40"), 1),
                         w.get("next_desc", "-"), w["next_class"]))
        L += md_table(["Symbol", "first B write", "B writes", "entry close", "trigger", "trigger date", "days",
                       "next 20d", "next 40d", "next step", "classified"], body)
        L.append("")

    L.append("## 9. Wash-out ledger")
    L.append("")
    if ledger is None:
        L.append(f"_`{WASHOUT_LEDGER.relative_to(REPO).as_posix()}` does not exist yet - it is created once the "
                 "wash-out resolution rule ships. Nothing to score._")
    else:
        n_pr = sum(1 for x in ledger_rows if x["priced"])
        L.append(f"{len(ledger)} ledger rows - one per wash-out debate, appended by the weekly Gates lane-stamp - "
                 f"{n_pr} priced (return from the first close after the wash-out debate, else the trigger date). "
                 "Each row is a wait the rule forced to resolve: thesis intact -> buy now, impaired -> wait for "
                 "proof, broken -> pass for now; never a second wait for a better price."
                 + (f" {len(ledger) - len(ledger_rows)} row(s) without a symbol or a date were skipped."
                    if len(ledger_rows) < len(ledger) else ""))
        L.append("")
        g = defaultdict(list)
        for x in ledger_rows:
            g[x["resolution"]].append(x)
        body = []
        for k, lst in sorted(g.items()):
            r20 = [x["r20"] for x in lst if x.get("r20") is not None]
            l20 = [x["rel20"] for x in lst if x.get("rel20") is not None]
            r40 = [x["r40"] for x in lst if x.get("r40") is not None]
            trig = Counter(x.get("trigger") for x in lst)
            body.append((k, res_plain(k), len(lst), f"{trig.get('FELL_10PCT', 0)} / {trig.get('LEVEL_REACHED', 0)}",
                         sum(1 for x in lst if x["coerced"]),
                         f"{len(r20)}: {pct(float(np.mean(r20)))}" if r20 else "-",
                         pct(float(np.mean(l20))) if l20 else "-", f"{len(r40)}: {pct(float(np.mean(r40)))}" if r40 else "-"))
        L += md_table(["Resolution", "in plain words", "rows", "trigger: fell 10% / level reached",
                       "changed by code", "next 20d (n: mean)", "20d minus SPY", "next 40d (n: mean)"], body)
        L.append("")
        if hist_wo:
            L.append(f"Cross-check: {sum(hist_wo.values())} debate-history writes carry a code-stamped wash-out outcome ("
                     + ", ".join(f"{res_plain(k)} {v}" for k, v in sorted(hist_wo.items()))
                     + f") against {len(ledger)} ledger rows; a gap means a ledger append or a publish was missed.")
            L.append("")
        if ledger_rows:
            L.append("Per-record: every ledger row")
            L.append("")
            L += md_table(["Symbol", "wash-out debate", "trigger", "letter before -> after", "thesis", "resolution",
                           "changed by code", "next 20d", "20d minus SPY", "next 40d", "note"],
                          [(x["symbol"], x["date"], TRIGGER_PLAIN.get(x.get("trigger") or "", x.get("trigger") or "-"),
                            f"{x.get('prior_letter') or '?'} -> {x.get('new_letter') or '?'}",
                            (x.get("new_thesis") or "-").lower(), res_plain(x["resolution"]),
                            "yes" if x["coerced"] else "no", pct(x.get("r20"), 1), pct(x.get("rel20"), 1),
                            pct(x.get("r40"), 1), x.get("why_unpriced") or "")
                           for x in sorted(ledger_rows, key=lambda x: (x["date"], x["symbol"]))])
    L.append("")

    # ---- integrity
    L.append("## 10. Schema integrity (new fields)")
    L.append("")
    if not schema_rows:
        L.append("_No write carries both thesis_state and entry_mode yet - the code-derived letter cannot be checked._")
    else:
        L.append(f"{len(schema_rows)} writes carry both fields. Letter differs from the code-derived letter on "
                 f"{len(mism)}; {len(unmapped)} use a combination the letter rules do not map "
                 f"(e.g. IMPAIRED+NOW); {len(broken_b)} BROKEN theses graded B (never allowed); "
                 f"{len(lvl_below_exit)} price-wait levels at/below the exit level (thesis break, bear case or "
                 "downside floor). The first three should be 0 - the published letter is derived by code from the "
                 "effective fields, so a non-zero count means grade-derive did not run on that write. The last "
                 "should be 0 too unless the write had no typed fair value to replace the level with (code then "
                 "keeps the level and only flags it).")
        for r in list({id(x): x for x in mism + broken_b}.values())[:15]:      # a write can be in both lists
            L.append(f"- {r['symbol']} {r['date']}: {r.get('thesis_state')} + {r.get('entry_mode')} graded {r.get('verdict')}")
        for r in lvl_below_exit[:15]:
            L.append(f"- {r['symbol']} {r['date']}: add level {r['entry_level_px']:.4g} at/below exit {exit_px(r):.4g}")
        L.append("")
        n_orig = sum(1 for r in schema_rows if r.get("verdict_agent_orig"))
        L.append(f"Code changed the CRO's own letter on {sum(overridden.values())} of {n_orig} writes that record it"
                 + (" (" + ", ".join(f"{k} {v}" for k, v in sorted(overridden.items())) + ")" if overridden else "")
                 + f"; {sum(rederived_ct.values())} were re-derived because the price was below the entry bar or at "
                 "the trim line"
                 + (" (" + ", ".join(f"{k} {v}" for k, v in sorted(rederived_ct.items())) + ")" if rederived_ct else "")
                 + f". {len(a_below_floor)} A writes show a typed upside at the write below their entry floor (code "
                 "re-derives on the live price at grading time, so a small gap can be legitimate; a large one is "
                 "a missed re-derive).")
        for r in a_below_floor[:15]:
            L.append(f"- {r['symbol']} {r['date']}: A with upside {r['implied_upside'] * 100:+.1f}% vs floor "
                     f"{r['entry_floor_pct']:.0f}%")
        if flag_ct:
            L.append("Grade flags (results_regime snapshots only - the history entry does not carry them): "
                     + ", ".join(f"{k} {v}" for k, v in flag_ct.most_common(12)) + ".")
    L.append("")

    # ---- dropped series
    L.append("## 11. Symbols dropped for a suspected bad price series")
    L.append("")
    if bad:
        L.append(f"A one-day close move above {JUMP_LIMIT * 100:.0f}% inside the scored window is treated as a "
                 "data error (pence/pound flips, unadjusted spin-offs) and the whole symbol is dropped. A genuine "
                 "crash would be dropped too - check this list before trusting a tail.")
        L.append("")
        L += md_table(["Symbol", "writes lost", "from", "close", "to", "close", "move"],
                      [(s, sum(1 for r in panel if r["symbol"] == s), j["from"], f"{j['px_from']:.4g}", j["to"],
                        f"{j['px_to']:.4g}", pct(j["move"], 0)) for s, j in sorted(bad.items())])
    else:
        L.append("_None._")
    L.append("")

    # ---- caveats
    L.append("## Caveats")
    L.append("")
    L += [
        "- The debate history keeps only the last 12 entries per symbol; names debated every week lose their "
        "oldest writes. The archive restores them only from the first run that saw them - the `--collect-only` "
        "step at the end of every publish keeps it whole; a week whose collect printed a WARN must be collected "
        "by hand before the next publish.",
        "- Typed fair values exist only where the history entry carries a valuation block (entries published "
        "from 2026-10-06 on) or a results_regime snapshot (overwritten weekly) was archived in time; older writes "
        "have no typed upside and are absent "
        "from section 7, not estimated.",
        "- Weekly re-debates of the same name overlap in time; the date bootstrap and the first-write-per-name "
        "row are the guard, not a cure.",
        "- Censored windows are excluded from the means, so the most recent writes count only at 20 days.",
        "- Entry levels are converted to the FMP price units by comparing the CRO's live price with the FMP close "
        "on the write date (catches pence vs pounds); a level that still lands outside 30-130% of the entry close "
        "is ignored.",
        "- Basket-13 catalyst writes and the scale-out overlay are excluded by source/lane; their grades mean "
        "something else.",
    ]
    L.append("")

    _atomic_write(out_md, "\n".join(L) + "\n")

    # ---- per-record CSV
    out_csv = out_md.with_suffix(".csv")
    cols = ["symbol", "date", "source", "engine", "verdict", "conviction", "value_conviction", "thesis_state",
            "entry_mode", "wait_kind", "implied_upside", "implied_upside_cro", "typed_src", "entry_date", "p0"]
    cols += [f"r{h}" for h in HORIZONS] + [f"x{h}" for h in HORIZONS] + [f"cens{h}" for h in HORIZONS]
    cols += ["r_latest", "latest_date", "first_write", "from_archive"]
    cols += ["verdict_agent_orig", "grade_schema", "grade_rederived", "entry_floor_pct", "entry_level_px",
             "washout_outcome"]                                   # 2026-10-06 grade stamps (appended, order kept)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        wr = csv.writer(fh)
        wr.writerow(cols)
        for r in sorted(priced, key=lambda r: (r["date"], r["symbol"])):
            wr.writerow([("" if r.get(c) is None else (f"{r[c]:.6f}" if isinstance(r.get(c), float) else r.get(c)))
                         for c in cols])

    vres = cats["verdict"][P]
    bc = vres["pairs"].get(("B", "C"))
    bc_ok = bc and bc["ci"] and _ok_group(vres["groups"]["B"]) and _ok_group(vres["groups"]["C"])
    bc_s = (f" (B-C {bc['diff'] * 100:+.1f}pts {ci_s(bc['ci'], unit='')})" if bc_ok else "")
    if split_date and bc_ok:
        e_, l_ = (cats["verdict"][(P, t)]["pairs"].get(("B", "C")) for t in ("early", "late"))
        if e_ and l_ and (e_["diff"] > 0) != (l_["diff"] > 0):
            bc_s += f" [UNSTABLE: early {e_['diff'] * 100:+.1f} / late {l_['diff'] * 100:+.1f}pts]"
    print(f"CRO scorecard asof {last_close or asof}: {len(priced)} regime writes/{len({r['symbol'] for r in priced})} names; "
          f"{P}d: {summary_bits[0]}{bc_s}; " + "; ".join(summary_bits[1:])
          + f"; wash-outs {len(full_trig)}/{len(full)} full-window B"
          + (f"; wash-out ledger {len(ledger)} rows" if ledger is not None else "")
          + f"; dropped {len(bad)} bad series -> {out_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
