#!/usr/bin/env python3
"""Apply Track D.1 edits to monitor_v7.py.

Monitor currently recomputes composite locally with only 10 of the 13
factors the screener uses. The 3 missing high-weight factors
(institutional_flow, sector_momentum, transcript) plus 2 low-weight ones
(institutional, congressional) sum to 22 pct of weight. The compute function
redistributes the missing weight across the remaining factors, so monitor's
composite is a literally different weighted average than the scan's.
Result: portfolio page shows a different number than the screener and
stock pages for the same stock, same day.

This patch:
 1. Adds a helper _load_scan_composites() that reads all three
    latest_<region>.json snapshots from GCS and returns
    {symbol: {composite, signal, price, _region}}.
 2. Calls that helper once at the top of run_monitor() and builds a
    scan_lookup dict.
 3. Before each per-position compute_composite_v7() call, checks
    scan_lookup. If the symbol is in any scan snapshot, uses the scan's
    composite + signal directly. Otherwise falls back to the local
    10-factor compute.

Invariant: monitor's decision rules (8 RULES) keep reading `composite`
and `signal` from the same variables, so no rule change needed. Rules
that reference `cata`, `qual`, `t.bull_score` still work because we still
call those local factor computes (they're cheap and needed by the rules).

Result after this patch + running scan right before monitor:
 - scan (15:00 CET, or whenever rescheduled) writes latest_<region>.json
 - monitor reads it and uses the same composite
 - portfolio page reads from state.json written by monitor
 - screener page reads from latest_<region>.json
 - stock page reads from latest_<region>.json
 All four pages display the same composite for the same symbol.
"""
from pathlib import Path

SRC = Path("/sessions/clever-intelligent-edison/mnt/uploads/monitor_v7 (2).py")
DST = Path("/sessions/clever-intelligent-edison/mnt/outputs/patches/monitor_v7.py")

text = SRC.read_text(encoding="utf-8")

# Edit 1: insert _load_scan_composites() helper just before load_state()
old1 = "def load_state():\n    \"\"\"Load portfolio state from GCS, fallback to local file."
new1 = (
    "def _load_scan_composites():\n"
    "    \"\"\"Track D.1 - read latest_<region>.json from GCS for sp500/nasdaq/russell2000.\n"
    "\n"
    "    Returns {SYMBOL: {composite, signal, price, _region}}.\n"
    "    Later regions overwrite earlier on collision (rare). Empty dict on\n"
    "    failure - callers fall back to local compute.\n"
    "\n"
    "    This is the single source of truth for the composite across the app:\n"
    "    portfolio page / stock page / screener page all eventually trace their\n"
    "    composite value back to these JSON files.\n"
    "    \"\"\"\n"
    "    out = {}\n"
    "    for region in (\"sp500\", \"nasdaq\", \"russell2000\"):\n"
    "        data = gcs_download(f\"latest_{region}.json\")\n"
    "        if not data:\n"
    "            log.warning(f\"Scan snapshot latest_{region}.json not found - monitor will fall back to local compute for that region\")\n"
    "            continue\n"
    "        stocks = data.get(\"stocks\") if isinstance(data, dict) else data\n"
    "        if not isinstance(stocks, list):\n"
    "            continue\n"
    "        n = 0\n"
    "        for s in stocks:\n"
    "            if not isinstance(s, dict):\n"
    "                continue\n"
    "            sym = s.get(\"symbol\")\n"
    "            if not sym:\n"
    "                continue\n"
    "            out[str(sym).upper()] = {\n"
    "                \"composite\": s.get(\"composite\"),\n"
    "                \"signal\": s.get(\"signal\"),\n"
    "                \"price\": s.get(\"price\"),\n"
    "                \"_region\": region,\n"
    "            }\n"
    "            n += 1\n"
    "        log.info(f\"Loaded {n} composites from latest_{region}.json\")\n"
    "    return out\n"
    "\n"
    "def load_state():\n"
    "    \"\"\"Load portfolio state from GCS, fallback to local file."
)
assert old1 in text, "edit 1 anchor (load_state docstring header) not found"
assert text.count(old1) == 1, f"edit 1 anchor not unique: {text.count(old1)} matches"
text = text.replace(old1, new1, 1)

# Edit 2: build scan_lookup at top of run_monitor()
old2 = (
    "    # Get all quotes at once\n"
    "    quotes = get_quotes_batch(syms)\n"
    "    today = datetime.now()\n"
    "    today_str = today.strftime(\"%Y-%m-%d\")\n"
    "\n"
    "    actions = []\n"
)
new2 = (
    "    # Get all quotes at once\n"
    "    quotes = get_quotes_batch(syms)\n"
    "    today = datetime.now()\n"
    "    today_str = today.strftime(\"%Y-%m-%d\")\n"
    "\n"
    "    # Track D.1: pre-load scan snapshots so composite reads are consistent\n"
    "    # with the screener. Without this, monitor would recompute locally with\n"
    "    # only 10 of 13 factors and produce a different number than the screener.\n"
    "    scan_lookup = _load_scan_composites()\n"
    "    log.info(f\"Scan snapshot lookup: {len(scan_lookup)} symbols indexed\")\n"
    "\n"
    "    actions = []\n"
)
assert old2 in text, "edit 2 anchor (quotes batch + actions init) not found"
assert text.count(old2) == 1, f"edit 2 anchor not unique: {text.count(old2)} matches"
text = text.replace(old2, new2, 1)

# Edit 3: prefer scan composite per position
old3 = (
    "        composite, signal, factors, reasons, coverage = compute_composite_v7(\n"
    "            t, a, v, price, ins, prox, earn, ups,\n"
    "            quality=qual, catalyst=cata,\n"
    "            weights=active_weights,\n"
    "        )\n"
)
new3 = (
    "        # Track D.1: prefer scan composite from latest_<region>.json.\n"
    "        # The screener computes composite with 13 factors; monitor's local\n"
    "        # fallback has only 10 (missing transcript, institutional,\n"
    "        # institutional_flow, sector_momentum, congressional - 22 pct of weight).\n"
    "        # When the symbol is in today's scan snapshot, use the scan value so\n"
    "        # all pages agree. Only fall back to local compute when scan doesn't\n"
    "        # cover the symbol (new add not yet scanned, delisted, off-region).\n"
    "        snap = scan_lookup.get(sym)\n"
    "        scan_comp = snap.get(\"composite\") if snap else None\n"
    "        if snap and isinstance(scan_comp, (int, float)) and scan_comp > 0:\n"
    "            composite = float(scan_comp)\n"
    "            signal = str(snap.get(\"signal\") or \"HOLD\").upper()\n"
    "            # Factors/reasons/coverage aren't used by decision rules downstream,\n"
    "            # but keep a well-typed empty shape so any future reader doesn't\n"
    "            # crash.\n"
    "            factors = {}\n"
    "            reasons = []\n"
    "            coverage = {\"count\": 0, \"pct\": 0, \"evaluated\": [], \"missing\": []}\n"
    "            log.info(f\"    {sym}: using scan composite {composite:.3f} from {snap.get('_region')}\")\n"
    "        else:\n"
    "            composite, signal, factors, reasons, coverage = compute_composite_v7(\n"
    "                t, a, v, price, ins, prox, earn, ups,\n"
    "                quality=qual, catalyst=cata,\n"
    "                weights=active_weights,\n"
    "            )\n"
    "            log.warning(f\"    {sym}: not in scan snapshots - using local 10-factor fallback composite {composite:.3f}\")\n"
)
assert old3 in text, "edit 3 anchor (compute_composite_v7 call in run_monitor) not found"
assert text.count(old3) == 1, f"edit 3 anchor not unique: {text.count(old3)} matches"
text = text.replace(old3, new3, 1)

DST.write_text(text, encoding="utf-8")

# Report
src_text = SRC.read_text(encoding="utf-8")
src_lines = src_text.count("\n")
dst_lines = text.count("\n")
print(f"source: {src_lines} lines, {SRC.stat().st_size} bytes")
print(f"dest:   {dst_lines} lines, {DST.stat().st_size} bytes")
print(f"delta:  +{dst_lines - src_lines} lines, +{DST.stat().st_size - SRC.stat().st_size} bytes")
print("OK")
