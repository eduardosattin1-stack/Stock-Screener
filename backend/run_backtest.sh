#!/bin/bash
# =============================================================================
# BACKTEST DEPLOYMENT — Run on Google Cloud Shell
# =============================================================================
# 
# Usage:
#   1. Open Cloud Shell: https://shell.cloud.google.com
#   2. cd Stock-Screener/backend
#   3. chmod +x run_backtest.sh && ./run_backtest.sh
#
# Or run directly:
#   python backtest_full.py --region nasdaq100 --windows 6
#   python backtest_full.py --region sp500 --windows 12
#   python backtest_full.py --region global --windows 6
#   python backtest_full.py --region europe --windows 6
# =============================================================================

set -e

echo "============================================="
echo "  Stock Screener v6 — Full Backtest + ML"
echo "============================================="

# Check environment
if [ -z "$FMP_API_KEY" ]; then
    export FMP_API_KEY="18kyMYWfzP8U5tMsBkk5KDzeGKERr5rA"
    echo "Set FMP_API_KEY from default"
fi

# Install dependencies
echo "Installing dependencies..."
pip install scikit-learn requests --quiet 2>/dev/null || pip install scikit-learn requests --break-system-packages --quiet

# Create output directory
mkdir -p backtest_output

# ─── Run 1: NASDAQ 100 (6 windows, ~100 stocks × 6 = 600 samples) ───
echo ""
echo "═══════════════════════════════════════════"
echo "  Running NASDAQ 100 backtest (6 windows)"
echo "═══════════════════════════════════════════"
python backtest_full.py \
    --region nasdaq100 \
    --windows 6 \
    --output backtest_output/nasdaq100

# ─── Run 2: Europe (6 windows, ~185 stocks × 6 = 1100 samples) ───
echo ""
echo "═══════════════════════════════════════════"
echo "  Running Europe backtest (6 windows)"
echo "═══════════════════════════════════════════"
python backtest_full.py \
    --region europe \
    --windows 6 \
    --output backtest_output/europe

# ─── Run 3: Combined ML training ───
echo ""
echo "═══════════════════════════════════════════"
echo "  Combining data + Final ML training"
echo "═══════════════════════════════════════════"

# Merge CSVs
python3 -c "
import csv, glob, os

all_rows = []
header = None
for f in glob.glob('backtest_output/*/training_data.csv'):
    with open(f) as fh:
        reader = csv.DictReader(fh)
        if header is None:
            header = reader.fieldnames
        for row in reader:
            all_rows.append(row)

out = 'backtest_output/combined_training.csv'
with open(out, 'w', newline='') as fh:
    writer = csv.DictWriter(fh, fieldnames=header)
    writer.writeheader()
    writer.writerows(all_rows)
print(f'Combined: {len(all_rows)} samples → {out}')
"

# Retrain ML on combined data
python backtest_full.py \
    --train-only backtest_output/combined_training.csv \
    --output backtest_output/combined

echo ""
echo "============================================="
echo "  BACKTEST COMPLETE"
echo "============================================="
echo ""
echo "Outputs:"
echo "  backtest_output/nasdaq100/training_data.csv"
echo "  backtest_output/nasdaq100/v7_weights.json"
echo "  backtest_output/nasdaq100/backtest_report.txt"
echo "  backtest_output/europe/training_data.csv"
echo "  backtest_output/europe/v7_weights.json"
echo "  backtest_output/combined/v7_weights.json  ← USE THIS"
echo "  backtest_output/combined/backtest_report.txt"
echo ""
echo "Expected samples: ~1700 (100 NQ + 185 EU × 6 windows)"
echo "Expected runtime: ~20-30 minutes (FMP API calls)"
echo ""
echo "Next: Copy v7_weights.json into screener_v7.py"
