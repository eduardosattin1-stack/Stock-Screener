#!/usr/bin/env python3
"""
B12: Dual-Agent Trade Diagnostics
===================================
Agent BRUNO:  Analyzes top winners & losers per method, diagnoses value traps,
              proposes detection filters.
Agent CIO:    Critiques/enhances Bruno's proposals with institutional lens.

Uses Claude claude-sonnet-4-20250514 for both agents.
"""
import os, json, logging, time
from pathlib import Path
import pandas as pd
import numpy as np
import anthropic

logging.basicConfig(level=logging.INFO, format="%(asctime)s [B12] %(message)s")
log = logging.getLogger("b12")

BACKEND = Path(__file__).resolve().parent.parent
OUT_DIR = Path(__file__).resolve().parent / "b12_agent_report"
OUT_DIR.mkdir(parents=True, exist_ok=True)

import os
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = "claude-sonnet-4-6"

# ── Method definitions ──
METHODS = {
    "B7_HMM_Static": {
        "trade_log": "b7_hmm_results/trade_log.csv",
        "description": "HMM Regime-Switching Static Ensemble. Buys 15 stocks at first BEAR signal, holds until exit. Linear regime-weighted scoring (IV15, Acquirer's Multiple, EPV). No rotation.",
        "scoring": "score = iv15_discount * w_dcf + acquirers_multiple * w_acq + epv_to_ev * w_epv. Regime-dependent weights.",
    },
    "B8_Linear_Rotation": {
        "trade_log": "b8_rotation_results/trade_log_best.csv",
        "description": "Monthly continuous rotation with linear regime-weighted scoring. 15 positions, 15% absolute upgrade threshold. Quality gates: ROE>15%, ROIC>10%, NM>10%.",
        "scoring": "Same linear scoring as B7 but with monthly re-ranking and forced upgrades when new candidates score 15% above worst holding.",
    },
    "B9v1_GARP_Raw": {
        "trade_log": "b9_garp_results/trade_log_garp.csv",
        "description": "Multiplicative GARP scoring with raw scores. FAILED due to extreme score variance causing 434 unnecessary swaps. Included for diagnostic purposes.",
        "scoring": "raw = (1/iv15) * (1+eps_growth_3y) * net_margin. Absolute threshold comparison caused churn.",
    },
    "B9v2_GARP_Ranked": {
        "trade_log": "b9v2_results/trade_log_champion.csv",
        "description": "Percentile-rank normalized GARP. 25 positions. Upgrade only when holding drops below 40th percentile AND candidate is above 80th. Regime-adaptive formula.",
        "scoring": "BULL: (1/iv15)*(1+eps_g)*nm. BEAR: am_rank*(1+roe)*(1+epv_rank). SIDEWAYS: 50/50 blend. All converted to percentile ranks.",
    },
    "B10_Dual_Engine": {
        "trade_log": "b10_dual_results/trade_log.csv",
        "description": "50/50 split: Engine A (Linear Value, 15 pos) + Engine B (GARP Growth, 25 pos). Symbol overlap blocked. Monthly rebalance.",
        "scoring": "Engine A: linear regime-weighted. Engine B: multiplicative GARP percentile-ranked. Overlap protection.",
    },
    "B11_Dynamic_Exits": {
        "trade_log": "b11_dynamic_exits/trade_log_combined.csv",
        "description": "B10 Dual-Engine with valuation ceiling removed. Trailing HWM exit (-20% from peak) replaces iv15_discount>1.20. Lets winners ride.",
        "scoring": "Same dual scoring. Exit: stop_loss OR trailing_hwm OR margin_collapse. NO valuation cap.",
    },
}


def load_fundamentals_at_entry(symbol, entry_date):
    """Load the fundamental snapshot closest to entry date from master_features."""
    try:
        mf = pd.read_parquet(BACKEND / "master_features.parquet",
                             columns=["scan_date","symbol","price","iv15_discount",
                                      "acquirers_multiple","epv_to_ev","net_margin",
                                      "roe","roic","eps_growth_1y","eps_growth_3y",
                                      "rev_growth_1y","rev_growth_3y","gross_margin",
                                      "roa","current_ratio"])
        mf["scan_date"] = pd.to_datetime(mf["scan_date"])
        entry_dt = pd.to_datetime(entry_date)
        sub = mf[(mf["symbol"]==symbol) & (mf["scan_date"]<=entry_dt)]
        if sub.empty:
            sub = mf[mf["symbol"]==symbol]
        if sub.empty:
            return {}
        row = sub.sort_values("scan_date").iloc[-1]
        return row.to_dict()
    except Exception as e:
        return {"error": str(e)}


def build_method_context(method_name, method_info, n_top=5):
    """Build the analysis context for one method."""
    trade_path = Path(__file__).resolve().parent / method_info["trade_log"]
    if not trade_path.exists():
        return None

    tdf = pd.read_csv(trade_path)
    if "net_return" not in tdf.columns or len(tdf) == 0:
        return None

    tdf = tdf.sort_values("net_return", ascending=False)
    winners = tdf.head(n_top)
    losers = tdf.tail(n_top).sort_values("net_return")

    # Load fundamentals at entry for each
    mf = pd.read_parquet(BACKEND / "master_features.parquet",
                         columns=["scan_date","symbol","price","iv15_discount",
                                  "acquirers_multiple","epv_to_ev","net_margin",
                                  "roe","roic","eps_growth_1y","eps_growth_3y",
                                  "rev_growth_1y","rev_growth_3y","gross_margin",
                                  "roa","current_ratio"])
    mf["scan_date"] = pd.to_datetime(mf["scan_date"])

    def enrich(row):
        entry_dt = pd.to_datetime(row["entry_date"])
        sub = mf[(mf["symbol"]==row["symbol"]) & (mf["scan_date"]<=entry_dt)]
        if sub.empty:
            sub = mf[mf["symbol"]==row["symbol"]]
        if sub.empty:
            return {}
        snap = sub.sort_values("scan_date").iloc[-1]
        return {
            "EV/EBIT": round(snap.get("acquirers_multiple", 0), 1),
            "IV15_Disc": round(snap.get("iv15_discount", 0), 2),
            "EPV/EV": round(snap.get("epv_to_ev", 0), 2),
            "Net_Margin": round(snap.get("net_margin", 0) * 100, 1),
            "ROE": round(snap.get("roe", 0) * 100, 1),
            "ROIC": round(snap.get("roic", 0) * 100, 1),
            "EPS_G_1Y": round(snap.get("eps_growth_1y", 0) * 100, 1),
            "EPS_G_3Y": round(snap.get("eps_growth_3y", 0) * 100, 1),
            "Rev_G_1Y": round(snap.get("rev_growth_1y", 0) * 100, 1),
            "Gross_Margin": round(snap.get("gross_margin", 0) * 100, 1),
        }

    w_data = []
    for _, r in winners.iterrows():
        f = enrich(r)
        w_data.append({
            "symbol": r["symbol"],
            "net_return": round(r["net_return"] * 100, 1),
            "days_held": int(r["days_held"]),
            "entry_date": str(r["entry_date"])[:10],
            "exit_reason": r.get("exit_reason", "N/A"),
            "regime": r.get("entry_regime", "N/A"),
            **f
        })

    l_data = []
    for _, r in losers.iterrows():
        f = enrich(r)
        l_data.append({
            "symbol": r["symbol"],
            "net_return": round(r["net_return"] * 100, 1),
            "days_held": int(r["days_held"]),
            "entry_date": str(r["entry_date"])[:10],
            "exit_reason": r.get("exit_reason", "N/A"),
            "regime": r.get("entry_regime", "N/A"),
            **f
        })

    # Summary stats
    wr = (tdf["net_return"] > 0).mean() * 100
    avg_win = tdf[tdf["net_return"]>0]["net_return"].mean()*100 if (tdf["net_return"]>0).any() else 0
    avg_loss = tdf[tdf["net_return"]<=0]["net_return"].mean()*100 if (tdf["net_return"]<=0).any() else 0

    return {
        "method": method_name,
        "description": method_info["description"],
        "scoring": method_info["scoring"],
        "total_trades": len(tdf),
        "win_rate": round(wr, 1),
        "avg_winner": round(avg_win, 1),
        "avg_loser": round(avg_loss, 1),
        "winners": w_data,
        "losers": l_data,
    }


def call_bruno(context):
    """Agent BRUNO: Diagnoses value traps and proposes detection filters."""
    client = anthropic.Anthropic(api_key=API_KEY)

    prompt = f"""You are **Bruno**, a senior quantitative portfolio analyst specializing in value trap detection and factor-based stock selection. You have 20 years of experience at Renaissance Technologies and AQR.

You are analyzing the results of a systematic backtest method. Your job is to:

1. **Analyze the Top-5 Winners**: What fundamental characteristics made these stocks succeed? What patterns do you see?
2. **Diagnose the Bottom-5 Losers**: Why did these stocks fail despite passing the quality gates? Classify each loser:
   - **Value Trap**: Cheap on metrics but fundamentally deteriorating (secular decline, margin compression, debt spiral)
   - **Cyclical Trap**: Bought at peak earnings, mean-reversion destroyed the position
   - **Momentum Trap**: No price momentum support despite good fundamentals
   - **Quality Mirage**: High ROE/ROIC driven by leverage or accounting, not true quality
3. **Propose Specific Filters**: For each failure type, propose a concrete, implementable filter that could have prevented the loss. Use the available factors: iv15_discount, acquirers_multiple, epv_to_ev, net_margin, roe, roic, eps_growth_1y, eps_growth_3y, rev_growth_1y, gross_margin, mom_26w.
4. **Rate the Method**: Score the method 1-10 on: (a) stock picking quality, (b) entry timing, (c) exit discipline, (d) value trap avoidance.

Be specific. Use the actual data provided. Write like you're presenting to a CIO at a $5B fund.

## Method: {context['method']}
{context['description']}

**Scoring Formula:** {context['scoring']}

**Summary:** {context['total_trades']} trades | Win Rate: {context['win_rate']}% | Avg Winner: +{context['avg_winner']}% | Avg Loser: {context['avg_loser']}%

## Top-5 Winners
{json.dumps(context['winners'], indent=2)}

## Bottom-5 Losers
{json.dumps(context['losers'], indent=2)}

Provide your analysis in structured markdown with clear headers."""

    resp = client.messages.create(
        model=MODEL,
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )
    return resp.content[0].text


def call_cio(context, bruno_analysis):
    """Agent CIO: Critiques/enhances Bruno's proposals."""
    client = anthropic.Anthropic(api_key=API_KEY)

    prompt = f"""You are the **Chief Investment Officer (CIO)** of a $5B systematic equity fund. You have seen hundreds of backtests and know that most "alpha" is overfitting.

Your portfolio analyst Bruno has just presented his analysis of a backtest method. Your job is to:

1. **Challenge Bruno's Diagnoses**: Are his value trap classifications correct? Is he being too generous or too harsh?
2. **Stress-Test the Proposed Filters**: Would Bruno's filters cause harmful side effects? (e.g., filtering out MO also filters out PM, which was a winner). Quantify the trade-off.
3. **Identify Overfitting Risk**: Are Bruno's proposed filters data-snooped? Would they work out-of-sample?
4. **Provide Your Own Enhancement**: Suggest ONE structural improvement to the method that Bruno missed. Focus on portfolio construction, not individual stock selection.
5. **Final Verdict**: Would you approve this method for live deployment? Under what conditions?

Be skeptical but constructive. Your reputation depends on not deploying overfitted strategies.

## Method: {context['method']}
{context['description']}
Win Rate: {context['win_rate']}% | {context['total_trades']} trades

## Bruno's Analysis:
{bruno_analysis}

Provide your critique in structured markdown."""

    resp = client.messages.create(
        model=MODEL,
        max_tokens=3000,
        messages=[{"role": "user", "content": prompt}]
    )
    return resp.content[0].text


def run():
    log.info("=" * 60)
    log.info("B12: DUAL-AGENT TRADE DIAGNOSTICS")
    log.info("  Agent BRUNO: Value Trap Analyst")
    log.info("  Agent CIO: Institutional Critic")
    log.info("  Model: %s", MODEL)
    log.info("=" * 60)

    report_parts = []
    report_parts.append("# B12: Dual-Agent Trade Diagnostics Report\n")
    report_parts.append(f"**Model:** {MODEL}  \n")
    report_parts.append(f"**Date:** 2026-05-19  \n")
    report_parts.append("**Agents:** Bruno (Value Trap Analyst) + CIO (Institutional Critic)\n\n---\n\n")

    for method_name, method_info in METHODS.items():
        log.info("\n" + "=" * 40)
        log.info("Analyzing: %s", method_name)
        log.info("=" * 40)

        context = build_method_context(method_name, method_info, n_top=5)
        if context is None:
            log.warning("  No trade data found for %s, skipping.", method_name)
            continue

        log.info("  %d trades, WR=%.0f%%, %d winners, %d losers loaded",
                 context["total_trades"], context["win_rate"],
                 len(context["winners"]), len(context["losers"]))

        # Call Agent Bruno
        log.info("  Calling Agent BRUNO...")
        try:
            bruno_out = call_bruno(context)
            log.info("  Bruno responded (%d chars)", len(bruno_out))
        except Exception as e:
            log.error("  Bruno failed: %s", e)
            bruno_out = f"*Bruno agent error: {e}*"

        time.sleep(2)  # Rate limit

        # Call Agent CIO
        log.info("  Calling Agent CIO...")
        try:
            cio_out = call_cio(context, bruno_out)
            log.info("  CIO responded (%d chars)", len(cio_out))
        except Exception as e:
            log.error("  CIO failed: %s", e)
            cio_out = f"*CIO agent error: {e}*"

        time.sleep(2)

        # Build method section
        section = f"## {method_name}\n\n"
        section += f"**Description:** {method_info['description']}  \n"
        section += f"**Trades:** {context['total_trades']} | **Win Rate:** {context['win_rate']}% | "
        section += f"**Avg Winner:** +{context['avg_winner']}% | **Avg Loser:** {context['avg_loser']}%\n\n"

        # Winners table
        section += "### Top-5 Winners\n\n"
        section += "| Symbol | Return | Days | Entry | Regime | EV/EBIT | IV15 | ROE | EPS G 3Y | Rev G 1Y |\n"
        section += "|--------|--------|------|-------|--------|---------|------|-----|----------|----------|\n"
        for w in context["winners"]:
            section += "| %s | +%.0f%% | %d | %s | %s | %.1fx | %.2f | %.0f%% | %.0f%% | %.0f%% |\n" % (
                w["symbol"], w["net_return"], w["days_held"], w["entry_date"],
                w.get("regime","?"), w.get("EV/EBIT",0), w.get("IV15_Disc",0),
                w.get("ROE",0), w.get("EPS_G_3Y",0), w.get("Rev_G_1Y",0))

        # Losers table
        section += "\n### Bottom-5 Losers\n\n"
        section += "| Symbol | Return | Days | Entry | Regime | Exit | EV/EBIT | IV15 | ROE | EPS G 3Y | Rev G 1Y |\n"
        section += "|--------|--------|------|-------|--------|------|---------|------|-----|----------|----------|\n"
        for l in context["losers"]:
            section += "| %s | %.1f%% | %d | %s | %s | %s | %.1fx | %.2f | %.0f%% | %.0f%% | %.0f%% |\n" % (
                l["symbol"], l["net_return"], l["days_held"], l["entry_date"],
                l.get("regime","?"), l.get("exit_reason","?"),
                l.get("EV/EBIT",0), l.get("IV15_Disc",0),
                l.get("ROE",0), l.get("EPS_G_3Y",0), l.get("Rev_G_1Y",0))

        section += f"\n### 🔍 Agent BRUNO — Value Trap Analysis\n\n{bruno_out}\n\n"
        section += f"### 🏛️ Agent CIO — Institutional Critique\n\n{cio_out}\n\n"
        section += "---\n\n"

        report_parts.append(section)

        # Save per-method JSON
        with open(OUT_DIR / f"{method_name}_analysis.json", "w") as f:
            json.dump({
                "method": method_name,
                "context": context,
                "bruno": bruno_out,
                "cio": cio_out,
            }, f, indent=2, default=str)

    # Write full report
    full_report = "".join(report_parts)
    report_path = OUT_DIR / "full_diagnostic_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(full_report)

    log.info("\n" + "=" * 60)
    log.info("B12 COMPLETE — Report saved to %s", report_path)
    log.info("=" * 60)


if __name__ == "__main__":
    run()
