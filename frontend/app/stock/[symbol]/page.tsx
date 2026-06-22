"use client";
import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, TrendingUp, TrendingDown, Minus, Activity, Brain, RefreshCw, Loader2, Newspaper, BarChart2, Zap, Shield, ChevronUp, ChevronDown, Trash, Compass, Calendar, AlertCircle, PlayCircle, Star, Trash2, ExternalLink, AlertTriangle, Clock, Sparkles, Layers } from "lucide-react";
import { ReactFinancialChartTab } from "./ReactFinancialChartTab";
import { Tip, rrDisplay, toneColor } from "../../components/Tip";

const GCS_SCANS="/api/gcs/scans";const GCS_SIGNALS="/api/gcs/signals";const FMP="/api/fmp";

// ── Types ──────────────────────────────────────────────────────────────────────
interface FactorScores{technical:number|null;quality:number|null;proximity:number|null;catalyst:number|null;transcript:number|null;upside:number|null;institutional:number|null;analyst:number|null;insider:number|null;earnings:number|null;institutional_flow?:number|null;sector_momentum?:number|null;congressional?:number|null;}
interface StockData{
  symbol:string;price:number;currency:string;market_cap:number;
  sma50:number;sma200:number;year_high:number;year_low:number;volume:number;
  rsi:number;macd_signal:string;adx:number;bb_pct:number;stoch_rsi:number;
  obv_trend:string;bull_score:number;
  target:number;upside:number;grade_buy:number;grade_total:number;
  grade_score:number;eps_beats:number;eps_total:number;
  revenue_cagr_3y:number;eps_cagr_3y:number;roe_avg:number;
  roe_consistent:boolean;roic_avg:number;gross_margin:number;
  gross_margin_trend:string;piotroski:number;altman_z:number;
  dcf_value:number;owner_earnings_yield:number;intrinsic_buffett:number;
  intrinsic_avg:number;margin_of_safety:number;value_score:number;
  composite:number;classification:string;reasons:string[];
  dcf_fcff_mos?:number;
  rd_capitalized_dcf?:number;
  rd_capitalized_dcf_mos?:number;
  owner_earnings?:number;
  owner_earnings_mos?:number;
  epv_value?:number;
  epv_mos?:number;
  graham_revised?:number;
  graham_revised_mos?:number;
  iv15_deep_value?:number;
  iv15_deep_value_mos?:number;
  // signal?:string;  // REMOVED v1.2 (May 2026) — BUY/HOLD/SELL semantics gone
  factor_scores?:FactorScores;
  quality_score?:number;catalyst_score?:number;catalyst_flags?:string[];
  has_catalyst?:boolean;days_to_earnings?:number;
  insider_score?:number;insider_net_buys?:number;insider_buy_ratio?:number;
  inst_score?:number;inst_holders_change?:number;inst_accumulation?:number;
  transcript_sentiment?:number;transcript_summary?:string;transcript_score?:number;
  proximity_52wk?:number;proximity_score?:number;
  earnings_momentum?:number;earnings_score?:number;upside_score?:number;
  hit_prob?:number;               // legacy alias = P(+20% in 30 trading bars)
  // v4 calibrated horizons (asdict'd from backend Stock; same model behind /performance)
  hit_prob_60d?:number;           // P(+20% in 60 trading bars) — the OOS-calibrated horizon
  hit_prob_30d?:number;           // P(+20% in 30 trading bars)
  hit_prob_10pct_60d?:number;     // P(+10% in 60 trading bars)
  hit_prob_10pct_30d?:number;     // P(+10% in 30 trading bars)
  // Smart Money Score (Apr 2026) — LTR-derived weighted factor score.
  // Pass-2 / US-only. null for non-US stocks; partial coverage for pass-1.
  smart_money_score?:number|null;
  smart_money_components?:Record<string,number>;
  smart_money_weight?:number;
  factor_coverage?:number;factors_evaluated?:string[];factors_missing?:string[];
  // v7.2.1 Massive options enrichment
  options_iv_current?:number|null;
  options_iv_rank?:number|null;
  options_iv_samples?:number;
  options_spread?:{
    strategy:string;spot:number;expiration:string;dte:number;
    long_strike:number;short_strike:number;long_mid:number;short_mid:number;
    net_debit:number;max_gain_per_contract:number;max_loss_per_contract:number;
    break_even_price:number;break_even_move_pct:number;risk_reward:number;
    description:string;
  }|null;
  // v7.2.3 expanded Massive signals
  options_pc_ratio?:number|null;
  options_iv_30d?:number|null;
  options_iv_60d?:number|null;
  options_iv_90d?:number|null;
  options_term_structure?:string|null;
  options_implied_earnings_move?:{
    pct:number;call_mid:number;put_mid:number;straddle:number;strike:number;
    expiration:string;earnings_date:string;
  }|null;
  // ── v8 (Apr 2026) — 5-factor composite, dual-mode ──
  net_margin?:number;
  fcf_margin?:number;
  revenue_yoy?:number;
  eps_yoy?:number;
  fcf_yoy?:number;
  fcf_cagr_3y?:number;
  p_fcf?:number;
  earnings_yield?:number;
  intrinsic_bvps?:number;
  bvps_recent_cagr?:number;
  bvps_consistency?:number;
  bvps_upside?:number;
  intrinsic_upside?:number;
reversal_score?:number;
  // Buffett 5-year valuation (May 2026)
  buffett_method?:string;          // "bvps_roe" | "eps_cagr" | "fallback_analyst" | ""
  buffett_g_assumed?:number;
  buffett_roe_assumed?:number;
  buffett_pe_median?:number;
  buffett_eps_5y?:number;
  buffett_future_price?:number;
  buffett_fair_value?:number;
  buffett_evaluated?:boolean;
  buffett_fallback_reason?:string;
  buffett_history?:{
    rows:Array<{
      year:string; bvps:number; eps:number; dps:number;
      shares_mm:number; revenue_mm:number; net_income_mm:number;
      equity_mm:number; pe:number|null;
    }>;
    medians?:{roe?:number; payout?:number; pe?:number};
    cagrs?:{bvps_5y?:number; eps_5y?:number};
  };
  factors_v8?:FactorsV8;
  composite_v7?:number;
  composite_momentum?:number;
  composite_fallen_angel?:number;
  signal_momentum?:string;
  // signal_fallen_angel?:string;  // REMOVED v1.2 (May 2026) — replaced by fallen_angel_flag
  factors_v8_momentum?:FactorsV8;
  factors_v8_fallen_angel?:FactorsV8;

  // ── v1.2 (May 2026): Compounder + Fallen Angel flag + PT velocity ──
  fallen_angel_flag?:boolean;
  compounder_score_us?:number|null;
  compounder_score_global?:number|null;
  compounder_rank_us?:number|null;
  compounder_rank_global?:number|null;
  signal_compounder_us?:string;
  signal_compounder_global?:string;
  roe_compounder?:number|null;
  pb_compounder?:number|null;
  opmargin_delta_compounder?:number|null;
  // v1.2 May 2026: per-factor percentile breakdown (Stock's rank within
  // cohort on each metric, 1.0 = best). Used by CompounderBreakdownCard
  // to render contribution bars alongside the composite score.
  cmp_us_roe_pct?:number|null;
  cmp_us_pb_pct?:number|null;
  cmp_us_opd_pct?:number|null;
  cmp_global_roe_pct?:number|null;
  cmp_global_pb_pct?:number|null;
  cmp_global_opd_pct?:number|null;
  pt_velocity_60d?:number|null;
  pt_velocity_score?:number|null;
  company_name?:string;
  exchange?:string;
  country?:string;
  sector?:string;
  mode?:string;
}
interface FactorsV8{momentum:number|null;quality:number|null;growth:number|null;value:number|null;smart_money:number|null;}
interface SignalPoint{date:string;composite:number;signal:string;price:number;bull:number;mos:number;}
interface NewsItem{title:string;url:string;publishedDate:string;site:string;}
interface IncomeRow{date:string;calendarYear:string;period?:string;revenue:number;grossProfit:number;operatingIncome:number;netIncome:number;epsdiluted:number;ebitda:number;}
interface BalanceSheetRow{date:string;calendarYear:string;period?:string;totalAssets:number;totalLiabilities:number;totalEquity:number;totalDebt:number;cashAndCashEquivalents:number;shortTermDebt?:number;longTermDebt?:number;cashAndShortTermInvestments?:number;totalCurrentAssets?:number;totalCurrentLiabilities?:number;goodwill?:number;intangibleAssets?:number;goodwillAndIntangibleAssets?:number;netDebt?:number;}
interface CashFlowRow{date:string;calendarYear:string;period?:string;operatingCashFlow:number;capitalExpenditure:number;freeCashFlow:number;}
interface RatioYear{date:string;fiscalYear:string;grossProfitMargin:number;operatingProfitMargin:number;netProfitMargin:number;returnOnEquity:number;returnOnAssets:number;returnOnCapitalEmployed:number;currentRatio:number;debtToEquityRatio:number;priceToEarningsRatio:number;priceToSalesRatio:number;priceToBookRatio:number;priceToFreeCashFlowRatio:number;dividendYieldPercentage:number;freeCashFlowOperatingCashFlowRatio:number;interestCoverageRatio:number;dividendPayoutRatio:number;revenuePerShare:number;netIncomePerShare:number;bookValuePerShare:number;freeCashFlowPerShare:number;operatingCashFlowPerShare:number;dividendPerShare:number;priceToOperatingCashFlowRatio:number;priceToEarningsGrowthRatio:number;evToEBITDA?:number;}
interface CompositePoint{date:string;composite:number;signal:string;price:number;}
// Opus 4.8 nightly option-strategy routine — one best strategy per D9/D10 ML pick.
// Pushed to GCS scans/options_strategies.json by backend/opus_strategist.ps1.
interface OpusLeg{action?:string;right?:string;strike?:number;qty?:number;est_price?:number;}
interface OpusStrategy{
  structure:string;thesis?:string;expiration?:string;legs?:OpusLeg[];
  net?:number;net_type?:string;max_gain?:number;max_loss?:number;breakeven?:number;
  target_move_pct?:number;conviction?:number;rationale?:string;risk_note?:string;
  decile?:number;iv_rank?:number|null;
  // fill-aware EV (opus_ev.py, crosses the bid/ask) — preferred over the mid-based fields above
  ev?:number;pop?:number;net_fill?:number;max_gain_fill?:number;max_loss_fill?:number;breakeven_fill?:number;ev_method?:string;
}

// ── Theme ──────────────────────────────────────────────────────────────────────
const T={bg:"var(--bg)",card:"var(--bg-surface)",cardBorder:"var(--border)",cardShadow:"var(--shadow-md)",text:"var(--text)",textMuted:"var(--text-muted)",textLight:"var(--text-light)",green:"var(--green)",greenLight:"var(--green-light)",greenBorder:"var(--green-border)",red:"var(--red)",redLight:"var(--red-light)",amber:"var(--amber)",amberLight:"var(--amber-light)",blue:"var(--blue)",purple:"var(--purple)",divider:"var(--divider)",mono:"var(--font-mono)",sans:"var(--font-sans)"};
const SIG_C:Record<string,{bg:string;fg:string;border:string}>={"STRONG BUY":{bg:"var(--purple-light)",fg:"var(--purple)",border:"var(--purple)"},BUY:{bg:T.greenLight,fg:"var(--green)",border:T.greenBorder},WATCH:{bg:T.amberLight,fg:T.amber,border:"var(--amber)"},HOLD:{bg:"var(--bg-elevated)",fg:T.textMuted,border:T.cardBorder},SELL:{bg:T.redLight,fg:T.red,border:"var(--red)"}};
const CLS_C:Record<string,string>={DEEP_VALUE:T.blue,VALUE:T.blue,QUALITY_GROWTH:T.purple,GROWTH:"#818cf8",SPECULATIVE:T.red,NEUTRAL:T.textMuted};

// v8 (Apr 2026) — 5-factor composite radar
// FACTOR_ORDER drives radar axis order (clockwise from top); FW = weights;
// FL = display labels. The legacy 13-factor arrays were removed when the
// dashboard switched to v8. If you need to inspect old 13-factor scores
// they remain on the scan JSON under `factor_scores` (not rendered).
const FACTOR_ORDER=["momentum","quality","growth","value","smart_money"];
const FL:Record<string,string>={momentum:"Momentum",quality:"Quality",growth:"Growth",value:"Value",smart_money:"Smart Money"};
const FW:Record<string,number>={momentum:25,quality:20,growth:20,value:20,smart_money:15};

// ── Explanations & Tooltips ────────────────────────────────────────────────────
const TOOLTIPS: Record<string, string> = {
  // Quality & Value
  "ROE (avg)": "Return on Equity: Profit generated with shareholders' money.\n✅ Ideal: > 15% (Consistent)\n❌ Avoid: < 0%",
  "ROIC (avg)": "Return on Invested Capital: Efficiency of debt/equity to generate profit.\n✅ Ideal: > 12%\n❌ Avoid: < 5%",
  "Gross Margin": "Percentage of revenue remaining after COGS.\n✅ Ideal: > 40% (Expanding)\n❌ Avoid: Contracting margins",
  "Rev CAGR 3Y": "3-Year Revenue Growth.\n✅ Ideal: > 15%\n❌ Avoid: Negative growth",
  "EPS CAGR 3Y": "3-Year Earnings Per Share Growth.\n✅ Ideal: > 15%\n❌ Avoid: Negative growth",
  "OE Yield": "Owner Earnings Yield (Free Cash Flow).\n✅ Ideal: > 4.5% (Risk-free rate)\n❌ Avoid: < 0%",
  "Piotroski": "Financial health score (0-9).\n✅ Ideal: 7-9\n❌ Avoid: < 5",
  "Altman Z": "Bankruptcy risk probability.\n✅ Ideal: > 3.0 (Safe)\n❌ Avoid: < 1.8 (Distress)",
  
  // Factors
  "Technical": "Trend strength, moving averages, and RSI.\n✅ Ideal: > 70%\n❌ Avoid: < 30%",
  "Quality": "Piotroski, Altman Z, ROE, and Margins.\n✅ Ideal: > 60%\n❌ Avoid: < 40%",
  "Upside": "Agreement between Wall St targets and DCF.\n✅ Ideal: > 20% upside\n❌ Avoid: Overvalued",
  "Catalyst": "Recent M&A, earnings, or upgrades.\n✅ Ideal: Active positive events\n❌ Avoid: Downgrades/Lawsuits",
  "Transcript": "Sentiment analysis of management tone.\n✅ Ideal: Bullish/Confident\n❌ Avoid: Hedging/Bearish",
  "Institutional": "Fund flows over recent quarters.\n✅ Ideal: Accumulation\n❌ Avoid: Heavy distribution",
  "Analyst": "Wall Street consensus.\n✅ Ideal: High Buy ratios\n❌ Avoid: Sell ratings",
  "Insider": "Corporate insider trading.\n✅ Ideal: Net buying\n❌ Avoid: Heavy selling",
  "Earnings": "Track record of beating EPS estimates.\n✅ Ideal: High beat rate\n❌ Avoid: Consistent misses",
  
  // Momentum & Misc
  "52-Week": "Proximity to 52-week high.\n✅ Ideal: 60-80% (Healthy uptrend)\n❌ Avoid: < 30% or > 95%",
  "52-Week Range": "Proximity to 52-week high.\n✅ Ideal: 60-80% (Healthy uptrend)\n❌ Avoid: < 30% or > 95%",
  "Golden Cross": "50d SMA > 200d SMA.\n✅ Ideal: Active\n❌ Avoid: Death Cross",
  "Death Cross": "50d SMA < 200d SMA.\n❌ Avoid: Active",
  "RSI": "Relative Strength Index.\n✅ Ideal: 40-70 (Rising)\n❌ Avoid: > 85 (Overbought) or < 30 (Falling)",
  "MACD": "Trend-following momentum.\n✅ Ideal: Bullish crossover\n❌ Avoid: Bearish crossover",
  "ADX": "Trend strength index.\n✅ Ideal: > 25 (Strong trend)\n❌ Avoid: < 20 (Choppy/Weak)",
  "BB%B": "Bollinger Bands %B.\n✅ Ideal: 0.2 - 0.8\n❌ Avoid: > 1.0 (Overextended)",
  "StochRSI": "Stochastic RSI.\n✅ Ideal: 20-80\n❌ Avoid: Prolonged extremes",
  "OBV": "On-Balance Volume.\n✅ Ideal: Rising (Accumulation)\n❌ Avoid: Falling (Distribution)",
  "Bull Score": "Composite technical score (0-10).\n✅ Ideal: 7-10\n❌ Avoid: 0-3",

  // Sentiment Card
  "INSIDERS": "Net insider buying/selling over recent 2 quarters.\nAccumulating (net buys + high acquired/disposed ratio) is bullish — insiders have non-public information.\n✅ Ideal: Accumulating (3+ net buys)\n❌ Avoid: Heavy distribution",
  "INSTITUTIONS": "QoQ change in 13F institutional holder count and ownership %.\nRising holder count + rising ownership = broad accumulation.\n✅ Ideal: Holders +5% QoQ, Shares +2%\n❌ Avoid: Both declining",
  "TECHNICAL": "Combined read of bull score (0-10), MACD direction, and ADX trend strength.\nBullish = high bull score + MACD bullish + strong trend (ADX>25).\n✅ Ideal: Bullish/Constructive\n❌ Avoid: Bearish + Weak ADX",
  "52W RANGE": "Where current price sits between 52-week low (0%) and high (100%).\n65-85% = healthy uptrend. <20% = distressed. >95% = possibly extended.\n✅ Ideal: 60-80%\n❌ Avoid: <20% or >95%",

  // Smart Money Card
  "Inst Flow": "13F flow velocity — rate of new positions opening/closing + ownership % shift QoQ.\nMeasures institutional URGENCY, not just direction.\n✅ Ideal: > 60 (active accumulation)\n❌ Avoid: < 30 (active distribution)",
  "Trend": "SMA50 vs SMA200 trend direction, modulated by institutional flow.\nStrong distribution kills trend credit (prevents bull traps).\n✅ Ideal: Golden cross + accumulation\n❌ Avoid: Death cross or uptrend + distribution",
  "Inst Accum": "Static 13F ownership: are institutions holding more or less of the float?\nTop-5 concentration rising = smart money loading up.\n✅ Ideal: Rising concentration\n❌ Avoid: Top holders reducing",
  "Quality SM": "Piotroski + Altman Z + ROE + ROIC + Gross Margin blend.\nSame as the v7 quality factor. Ensures smart money is flowing into fundamentally sound companies.\n✅ Ideal: > 60\n❌ Avoid: < 30",
  "Sector Mom": "Stock's 60d return vs its sector average.\nOutperformance = sector leader, underperformance = laggard.\n✅ Ideal: > 50 (outperforming sector)\n❌ Avoid: < 30 (underperforming)",
  "Congress": "Net Senate + House trading activity, recency-weighted (90d half-life).\nCongressional members trade on privileged information.\n✅ Ideal: Net buying\n❌ Avoid: Net selling or no coverage",

  // Growth Rates Card
  "Revenue": "Total top-line sales. Most stable growth metric — less manipulable than earnings.\n✅ Ideal: 10-25% CAGR (sustainable growth)\n❌ Avoid: Negative or >50% (unsustainable)",
  "Gross Profit": "Revenue minus cost of goods sold. Measures pricing power and moat.\nExpanding gross profit faster than revenue = improving economics.\n✅ Ideal: Growing faster than revenue\n❌ Avoid: Shrinking while revenue grows",
  "Operating Income": "Revenue minus COGS and operating expenses. Shows operational leverage.\nFaster growth than revenue = operating leverage kicking in.\n✅ Ideal: > Revenue growth rate\n❌ Avoid: Negative or declining",
  "Net Income": "Bottom line profit after all expenses, taxes, interest.\nVolatile — one-time charges can distort. Cross-check with operating income.\n✅ Ideal: Positive and growing\n❌ Avoid: Negative trends",
  "EPS": "Earnings per diluted share. Directly drives stock price via P/E multiple.\nShows if growth is reaching shareholders (not diluted away).\n✅ Ideal: > 15% CAGR\n❌ Avoid: Declining despite revenue growth (margin compression)",
  "EBITDA": "Earnings before interest, taxes, depreciation, amortization.\nProxy for operating cash generation. Best for comparing across capital structures.\n✅ Ideal: Positive and growing\n❌ Avoid: Negative (company burns cash operationally)",
  "FCF/Share": "Free cash flow per diluted share. The cash actually available to shareholders.\nMore honest than EPS — harder to manipulate with accounting.\n✅ Ideal: Positive and growing faster than EPS\n❌ Avoid: Negative (company needs external funding)",

  // Valuation History Card
  "P/E": "Price to Earnings. How many years of current earnings you pay for one share.\nLower = cheaper. Compare within sector, not across.\n✅ Ideal: Below 5yr median (relatively cheap)\n❌ Avoid: 2x+ above sector median",
  "P/S": "Price to Sales. Revenue-based valuation — useful for unprofitable growth companies.\nIndustry-dependent: tech 5-15 normal, industrials 1-3 normal.\n✅ Ideal: Below historical median\n❌ Avoid: 3x+ above sector",
  "P/B": "Price to Book Value. What you pay per dollar of net assets.\n<1 = trading below liquidation value (deep value or value trap).\n✅ Ideal: 1-3 for industrials, higher OK for capital-light\n❌ Avoid: Negative book value",
  "P/FCF": "Price to Free Cash Flow. Like P/E but uses actual cash, not accounting earnings.\nMore conservative than P/E — ignores non-cash charges.\n✅ Ideal: < 20\n❌ Avoid: > 40 or negative FCF",
  "EV/EBITDA": "Enterprise Value / EBITDA. Debt-adjusted valuation — the acquirer's P/E.\nBest for comparing companies with different capital structures.\n✅ Ideal: < 12 (value), 12-20 (fair)\n❌ Avoid: > 25",
  "BVPS": "Book Value Per Share. Net assets per share — the liquidation floor.\nRising BVPS = company is getting richer over time.\n✅ Ideal: Steadily rising\n❌ Avoid: Declining (value destruction)",
  "Div%": "Dividend yield. Annual dividend as percentage of stock price.\nHigh yield + declining price = potential value trap.\n✅ Ideal: 1-4% with growing payout\n❌ Avoid: >8% (likely unsustainable)",

  // Liquidity & Debt
  "NET DEBT / (CASH)": "Total Debt minus Cash & Short-term Investments. Negative means the company has more cash than debt.\n✅ Ideal: Negative (Net Cash)\n❌ Avoid: Highly positive and rising",
  "D/E RATIO": "Debt to Equity: Total liabilities divided by shareholder equity.\n✅ Ideal: < 1.0\n❌ Avoid: > 2.0 (High leverage)",
  "INTEREST COVERAGE": "EBIT / Interest Expense: Ability to pay interest on outstanding debt.\n✅ Ideal: > 3.0x\n❌ Avoid: < 1.5x (At risk)",
  "NET DEBT / EBITDA": "How many years of EBITDA it would take to pay back all net debt.\n✅ Ideal: < 2.0x\n❌ Avoid: > 4.0x",
  "FINANCIAL LEVERAGE": "Total Assets / Total Equity: Measures how much of the assets are financed by equity.\n✅ Ideal: < 2.0x for non-financials\n❌ Avoid: > 5.0x",
  "CURRENT RATIO": "Current Assets / Current Liabilities: Ability to pay short-term obligations.\n✅ Ideal: > 1.2x\n❌ Avoid: < 1.0x",
  "CASH RATIO": "Cash & Equiv / Current Liabilities: Most conservative liquidity measure.\n✅ Ideal: > 0.5x\n❌ Avoid: < 0.1x",
  "WORKING CAPITAL": "Current Assets minus Current Liabilities.\n✅ Ideal: Positive\n❌ Avoid: Negative (Liquidity squeeze)",
  "TTM OCF / FCF": "Trailing 12-month Operating Cash Flow and Free Cash Flow.\n✅ Ideal: Strong positive conversion from Net Income",
  "GW + INTANGIBLES": "Goodwill and other non-physical assets. High % suggests expensive M&A history.\n❌ Avoid: > 50% of total assets",
};

// ── Helpers ────────────────────────────────────────────────────────────────────
const fmtPct=(n:number|null|undefined)=>n==null?"—":`${(n*100).toFixed(1)}%`;

// Currency symbol map. Stocks in the global universe come from many exchanges
// reporting in different currencies; the backend now correctly tags currency
// per ticker (2026-05-07 fix) and we should display the right symbol or code.
// Codes (vs glyphs) are shown for currencies where the glyph is ambiguous
// or absent on common keyboards (e.g. CHF, SEK, BRL).
const CURRENCY_SYMBOL: Record<string, string> = {
  USD: "$",  EUR: "€",  GBP: "£",  JPY: "¥",  CNY: "¥",  HKD: "HK$",
  CHF: "CHF ", SEK: "kr ", NOK: "kr ", DKK: "kr ", AUD: "A$",  CAD: "C$",
  NZD: "NZ$", SGD: "S$",  KRW: "₩",  INR: "₹",  BRL: "R$",  MXN: "Mex$",
  TWD: "NT$", THB: "฿",  IDR: "Rp ", MYR: "RM ", PHP: "₱",  ILS: "₪",
  TRY: "₺",  PLN: "zł ", CZK: "Kč ", HUF: "Ft ", ZAR: "R",   SAR: "SAR ",
  AED: "AED ",
};
const fmtPrice=(n:number|null|undefined,c?:string)=>{
  if(n==null||n===0)return"—";
  const sym=CURRENCY_SYMBOL[c??""]??"$";
  // For prices over 1000, drop decimals (avoids "¥30,060.00" being noise)
  return n>=1000?`${sym}${n.toLocaleString(undefined,{maximumFractionDigits:0})}`:`${sym}${n.toFixed(2)}`;
};

// Convert FMP ticker format to TradingView's EXCHANGE:SYMBOL format. Without
// this, non-US tickers like 1898.HK or 6857.T fail to load in the embedded
// chart with "This symbol doesn't exist". US tickers (no suffix) pass through
// untouched — TradingView accepts bare symbols like AAPL.
const TV_EXCHANGE_MAP: Record<string, string> = {
  // Asia
  T: "TSE",  HK: "HKEX",  KS: "KRX",  KQ: "KRX",  SS: "SSE",  SZ: "SZSE",
  TW: "TWSE", SI: "SGX",  AX: "ASX",  NZ: "NZX",  KL: "MYX",  JK: "IDX",
  BK: "SET",  BO: "BSE",  NS: "NSE",
  // Europe
  SW: "SIX",       AS: "EURONEXT",  PA: "EURONEXT",  BR: "EURONEXT",
  LS: "EURONEXT",  IR: "EURONEXT",  DE: "XETR",      F:  "XETR",
  MI: "MIL",       HE: "OMXHEX",    OL: "OMXOSL",    ST: "OMXSTO",
  CO: "OMXCOP",    L:  "LSE",       IL: "LSE",       MC: "BME",
  WA: "GPW",       IS: "BIST",      VI: "VIE",       AT: "ATHEX",
  // Americas / RoW
  TO: "TSX",  V:  "TSXV",  SA: "BMFBOVESPA",  MX: "BMV",
  JO: "JSE",  TA: "TASE",
};
function toTradingViewSymbol(symbol: string): string {
  if (!symbol || !symbol.includes(".")) return symbol;
  const idx = symbol.lastIndexOf(".");
  const base = symbol.slice(0, idx);
  const suffix = symbol.slice(idx + 1);
  const exchange = TV_EXCHANGE_MAP[suffix];
  return exchange ? `${exchange}:${base}` : symbol;
}
const gClr=(v:number|null)=>{if(v==null)return T.textLight;if(v>0.15)return T.green;if(v>0.05)return"#5a9e7a";if(v>0)return T.textMuted;return T.red;};
function safeCagr(s:number,e:number,y:number):number|null{if(!s||!e||s<=0||e<=0||y<=0)return null;return Math.pow(e/s,1/y)-1;}
// v8: read factors_v8 for the active mode. Falls back to s.factors_v8 if the
// per-mode dicts aren't present yet (older scan JSON). All five axes are
// always defined keys, but values can be null (= no data, weight redistributed).
function readFactorsV8(s:StockData,mode:string):FactorsV8{
  const f=mode==="fallen_angel"?(s.factors_v8_fallen_angel??s.factors_v8):(s.factors_v8_momentum??s.factors_v8);
  if(f) return f;
  // last-resort fallback: empty radar (all null) — happens for stocks scanned
  // before the v8 deploy and still cached in some flow.
  return{momentum:null,quality:null,growth:null,value:null,smart_money:null};
}
// getProb() removed v1.2 (May 2026) — was a static composite→prob lookup table
// used by the old ProbabilityCard. Replaced by P20Card which reads the actual
// ML output (s.hit_prob) instead of a hardcoded approximation.
async function fmpFetch(ep:string,p:Record<string,string|number>){const qs=new URLSearchParams();qs.set("e",ep);Object.entries(p).forEach(([k,v])=>qs.set(k,String(v)));try{const r=await fetch(`${FMP}?${qs}`);if(!r.ok)return null;const d=await r.json();return Array.isArray(d)?d:d?[d]:null;}catch{return null;}}

// ── Shared Components ──────────────────────────────────────────────────────────
function Card({children,style}:{children:React.ReactNode;style?:React.CSSProperties}){
  const [minimized, setMinimized] = useState(false);
  const childrenArray = React.Children.toArray(children);
  const firstChild = childrenArray[0];
  let header = firstChild;
  if (React.isValidElement(firstChild) && ((firstChild.type as any).name === 'SH' || firstChild.type === SH)) {
    header = React.cloneElement(firstChild as React.ReactElement<any>, {
      onToggle: () => setMinimized(!minimized),
      minimized: minimized
    });
  }
  return <div style={{background:T.card,borderRadius:8,border:`1px solid ${T.cardBorder}`,boxShadow:T.cardShadow,padding:minimized?"12px 18px":"16px 18px",...style}}>{header}{!minimized && childrenArray.slice(1)}</div>;
}
function SH({title,icon,sub,onToggle,minimized}:{title:string;icon?:React.ReactNode;sub?:string;onToggle?:()=>void;minimized?:boolean}){
  return <div style={{display:"flex",alignItems:"center",gap:6,fontSize:11,fontWeight:600,letterSpacing:"0.08em",color:T.green,fontFamily:T.mono,textTransform:"uppercase",marginBottom:minimized?0:12,paddingBottom:minimized?0:8,borderBottom:minimized?"none":`2px solid ${T.greenLight}`}}>{icon}{title}{sub&&<span style={{marginLeft:"auto",fontSize:9,color:T.textLight,fontWeight:400,textTransform:"none",letterSpacing:0}}>{sub}</span>}{onToggle&&<button onClick={(e)=>{e.preventDefault(); e.stopPropagation(); onToggle();}} style={{marginLeft:sub?8:"auto",background:"none",border:"none",cursor:"pointer",color:T.textLight,display:"flex",alignItems:"center",padding:4}}>{minimized?<ChevronDown size={14}/>:<ChevronUp size={14}/>}</button>}</div>;
}
function Metric({label,value,color,sub}:{label:string;value:string;color?:string;sub?:string}){const tip=TOOLTIPS[label]||"";return<div style={{padding:"7px 0",borderBottom:`1px solid ${T.divider}`}}><div style={{display:"flex",justifyContent:"space-between",alignItems:"baseline"}}><span title={tip} style={{fontSize:11,color:T.textMuted,fontFamily:T.mono,fontWeight:500,cursor:tip?"help":"default",borderBottom:tip?`1px dotted ${T.textLight}`:"none"}}>{label}</span><span style={{fontSize:12,color:color||T.text,fontFamily:T.mono,fontWeight:600}}>{value}</span></div>{sub&&<div style={{fontSize:9,color:T.textLight,marginTop:2,fontFamily:T.mono}}>{sub}</div>}</div>;}
function ScoreRing({value,label,max,color}:{value:number;label:string;max:number;color:string}){const p=Math.min(value/max,1),r=26,ci=2*Math.PI*r,of=ci*(1-p);return<div style={{textAlign:"center"}}><svg width="62" height="62" viewBox="0 0 62 62"><circle cx="31" cy="31" r={r} fill="none" stroke={T.divider} strokeWidth="4"/><circle cx="31" cy="31" r={r} fill="none" stroke={color} strokeWidth="4" strokeDasharray={ci} strokeDashoffset={of} strokeLinecap="round" transform="rotate(-90 31 31)" style={{transition:"stroke-dashoffset 0.6s ease"}}/><text x="31" y="29" textAnchor="middle" fill={color} fontSize="13" fontFamily={T.mono} fontWeight="700">{value}</text><text x="31" y="41" textAnchor="middle" fill={T.textLight} fontSize="8" fontFamily={T.mono}>/{max}</text></svg><div style={{fontSize:9,color:T.textMuted,fontFamily:T.mono,marginTop:2}}>{label}</div></div>;}

// ── v7 Factor Radar ────────────────────────────────────────────────────────────
// ── Add to Portfolio (stock detail header) ───────────────────────────────────
function AddToPortfolioStock({stock:s}:{stock:StockData}){
  const [open,setOpen]=useState(false);
  const [shares,setShares]=useState("");
  const [price,setPrice]=useState(s.price?.toFixed(2)||"");
  const [notes,setNotes]=useState("");
  const [status,setStatus]=useState<"idle"|"saving"|"saved"|"error">("idle");
  const [err,setErr]=useState("");
  async function handleSave(){
    const p=parseFloat(price),sh=parseFloat(shares);
    if(!p||p<=0){setErr("Price required");return;}
    if(!sh||sh<=0){setErr("Shares required");return;}
    setStatus("saving");setErr("");
    try{
      const r=await fetch("/api/portfolio/add",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({symbol:s.symbol,entry_price:p,shares:sh,notes})});
      if(!r.ok){
        // Keep the error message short: detect HTML bodies (Next.js 404 pages, etc.)
        // and substitute a concise message instead of dumping 10KB into the UI.
        const text=await r.text().catch(()=>"");
        const isHtml=text.trimStart().toLowerCase().startsWith("<!doctype")||text.trimStart().startsWith("<");
        const shortBody=isHtml?"(server returned HTML page)":text.slice(0,120);
        throw new Error(`HTTP ${r.status}${shortBody?` – ${shortBody}`:""}`);
      }
      setStatus("saved");setTimeout(()=>{setOpen(false);setStatus("idle");setShares("");setNotes("");},1500);
    } catch(e:any){setStatus("error");setErr((e?.message||"Failed").slice(0,160));}
  }
  if(!open){
    return(
      <button onClick={()=>setOpen(true)} style={{fontSize:11,fontFamily:T.mono,fontWeight:600,padding:"6px 14px",borderRadius:5,border:`1px solid ${T.greenBorder}`,background:T.greenLight,color:T.green,cursor:"pointer",letterSpacing:"0.05em",textTransform:"uppercase"}}>+ Add to Portfolio</button>
    );
  }
  return(
    <div style={{padding:"10px 12px",borderRadius:6,background:"var(--bg-surface)",border:`1px solid ${T.greenBorder}`,display:"flex",flexDirection:"column",gap:6,minWidth:280}}>
      <div style={{display:"flex",alignItems:"center",gap:6,fontSize:10,fontFamily:T.mono}}>
        <span style={{color:T.textMuted,fontWeight:600}}>{s.symbol}</span>
        <input type="number" placeholder="shares" value={shares} onChange={e=>{setShares(e.target.value);setErr("");}} autoFocus
          style={{width:60,padding:"4px 6px",border:`1px solid ${T.cardBorder}`,borderRadius:3,fontSize:10,fontFamily:T.mono}}/>
        <span style={{color:T.textLight}}>@</span>
        <input type="number" step="0.01" placeholder="price" value={price} onChange={e=>{setPrice(e.target.value);setErr("");}}
          style={{width:70,padding:"4px 6px",border:`1px solid ${T.cardBorder}`,borderRadius:3,fontSize:10,fontFamily:T.mono}}/>
      </div>
      <input type="text" placeholder="notes (optional)" value={notes} onChange={e=>setNotes(e.target.value)} maxLength={60}
        style={{padding:"4px 6px",border:`1px solid ${T.cardBorder}`,borderRadius:3,fontSize:10,fontFamily:T.mono}}/>
      <div style={{display:"flex",alignItems:"center",gap:6}}>
        <button onClick={handleSave} disabled={status==="saving"||status==="saved"} style={{flex:1,padding:"5px 10px",border:"none",borderRadius:3,cursor:status==="saving"?"wait":"pointer",background:status==="saved"?"var(--green)":status==="error"?T.red:T.green,color:"var(--bg-surface)",fontSize:10,fontFamily:T.mono,fontWeight:600}}>{status==="saving"?"Saving...":status==="saved"?"✓ Added":status==="error"?"! Retry":"Save"}</button>
        <button onClick={()=>{setOpen(false);setStatus("idle");setErr("");}} style={{padding:"5px 10px",border:`1px solid ${T.cardBorder}`,borderRadius:3,cursor:"pointer",background:"var(--bg-surface)",color:T.textMuted,fontSize:10,fontFamily:T.mono}}>Cancel</button>
      </div>
      {err&&<div style={{fontSize:9,color:T.red,fontFamily:T.mono}}>{err}</div>}
    </div>
  );
}

function AddOptionToPortfolio({stock:s, sp, ev, iv}:{stock:StockData, sp:any, ev:number, iv:number}){
  const [open,setOpen]=useState(false);
  const [contracts,setContracts]=useState("1");
  const [debit,setDebit]=useState(sp?.net_debit?.toFixed(2)||"");
  const [longStrike,setLongStrike]=useState(sp?.long_strike?.toString()||"");
  const [shortStrike,setShortStrike]=useState(sp?.short_strike?.toString()||"");
  const [notes,setNotes]=useState("");
  const [status,setStatus]=useState<"idle"|"saving"|"saved"|"error">("idle");
  const [err,setErr]=useState("");
  
  async function handleSave(){
    const c=parseInt(contracts),d=parseFloat(debit);
    if(!c||c<=0){setErr("Contracts required");return;}
    if(!d||d<=0){setErr("Debit required");return;}
    setStatus("saving");setErr("");
    try{
      const payload = {
        asset_type: "option",
        symbol: s.symbol,
        entry_price: d, // net debit
        shares: c * 100, // equivalent shares exposure
        notes,
        strategy: sp.strategy,
        expiration: sp.expiration,
        strikes: `${longStrike}/${shortStrike}`,
        ev,
        risk: sp.max_loss_per_contract,
        iv,
        contracts: c
      };
      const r=await fetch("/api/portfolio/add",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
      if(!r.ok){
        const text=await r.text().catch(()=>"");
        throw new Error(`HTTP ${r.status}`);
      }
      setStatus("saved");setTimeout(()=>{setOpen(false);setStatus("idle");setContracts("1");setNotes("");},1500);
    } catch(e:any){setStatus("error");setErr((e?.message||"Failed").slice(0,160));}
  }
  if(!open){
    return(
      <button onClick={()=>setOpen(true)} style={{fontSize:10,fontFamily:T.mono,fontWeight:600,padding:"4px 10px",borderRadius:4,border:`1px solid ${T.purple}60`,background:`${T.purple}10`,color:T.purple,cursor:"pointer",letterSpacing:"0.05em",textTransform:"uppercase"}}>+ Track Option</button>
    );
  }
  return(
    <div style={{marginTop: 10, padding:"10px 12px",borderRadius:6,background:"var(--bg-surface)",border:`1px solid ${T.purple}`,display:"flex",flexDirection:"column",gap:6}}>
      <div style={{display:"flex",alignItems:"center",gap:6,fontSize:10,fontFamily:T.mono}}>
        <span style={{color:T.textMuted,fontWeight:600}}>{sp.strategy.replace(" (estimated)", "")}</span>
        <input type="text" placeholder="Long" value={longStrike} onChange={e=>{setLongStrike(e.target.value);setErr("");}} 
          style={{width:40,padding:"4px 6px",border:`1px solid ${T.cardBorder}`,borderRadius:3,fontSize:10,fontFamily:T.mono,textAlign:"center"}}/>
        <span style={{color:T.textLight}}>/</span>
        <input type="text" placeholder="Short" value={shortStrike} onChange={e=>{setShortStrike(e.target.value);setErr("");}} 
          style={{width:40,padding:"4px 6px",border:`1px solid ${T.cardBorder}`,borderRadius:3,fontSize:10,fontFamily:T.mono,textAlign:"center"}}/>
        <input type="number" placeholder="contracts" value={contracts} onChange={e=>{setContracts(e.target.value);setErr("");}} autoFocus
          style={{width:50,padding:"4px 6px",border:`1px solid ${T.cardBorder}`,borderRadius:3,fontSize:10,fontFamily:T.mono}}/>
        <span style={{color:T.textLight}}>@ $</span>
        <input type="number" step="0.01" placeholder="debit" value={debit} onChange={e=>{setDebit(e.target.value);setErr("");}}
          style={{width:60,padding:"4px 6px",border:`1px solid ${T.cardBorder}`,borderRadius:3,fontSize:10,fontFamily:T.mono}}/>
      </div>
      <input type="text" placeholder="notes (optional)" value={notes} onChange={e=>setNotes(e.target.value)} maxLength={60}
        style={{padding:"4px 6px",border:`1px solid ${T.cardBorder}`,borderRadius:3,fontSize:10,fontFamily:T.mono}}/>
      <div style={{display:"flex",alignItems:"center",gap:6}}>
        <button onClick={handleSave} disabled={status==="saving"||status==="saved"} style={{flex:1,padding:"5px 10px",border:"none",borderRadius:3,cursor:status==="saving"?"wait":"pointer",background:status==="saved"?"var(--green)":status==="error"?T.red:T.purple,color:"var(--bg-surface)",fontSize:10,fontFamily:T.mono,fontWeight:600}}>{status==="saving"?"Saving...":status==="saved"?"✓ Tracked":status==="error"?"! Retry":"Track"}</button>
        <button onClick={()=>{setOpen(false);setStatus("idle");setErr("");}} style={{padding:"5px 10px",border:`1px solid ${T.cardBorder}`,borderRadius:3,cursor:"pointer",background:"var(--bg-surface)",color:T.textMuted,fontSize:10,fontFamily:T.mono}}>Cancel</button>
      </div>
      {err&&<div style={{fontSize:9,color:T.red,fontFamily:T.mono}}>{err}</div>}
    </div>
  );
}

function FactorRadar({scores,size=260}:{scores:FactorsV8;size?:number}){
  const cx=size/2,cy=size/2,r=size/2-44;const raw=FACTOR_ORDER.map(k=>(scores as any)[k] as number|null);const vals=raw.map(v=>v??0);const n=vals.length;
  const ang=(i:number)=>(Math.PI*2*i)/n-Math.PI/2;const grid=[0.25,0.5,0.75,1.0];
  const evaluated=raw.filter(v=>v!=null) as number[];const avg=evaluated.length?evaluated.reduce((a:number,b:number)=>a+b,0)/evaluated.length:0;
  const fill=avg>0.6?T.green:avg>0.4?T.amber:T.red;
  const covCount=evaluated.length;
  return(
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {grid.map((lv,gi)=>{const pts=Array.from({length:n},(_,i)=>`${cx+Math.cos(ang(i))*r*lv},${cy+Math.sin(ang(i))*r*lv}`).join(" ");return<polygon key={gi} points={pts} fill="none" stroke="#d1d5db" strokeWidth={gi===3?1:0.5} opacity={0.5}/>;})}
      {FACTOR_ORDER.map((k,i)=>{const a=ang(i),lx=cx+Math.cos(a)*(r+28),ly=cy+Math.sin(a)*(r+28),v=raw[i],isNull=v==null,c=isNull?"#d1d5db":((v??0)>0.7?"var(--green)":(v??0)>0.4?T.amber:T.red);return<g key={k}><line x1={cx} y1={cy} x2={cx+Math.cos(a)*r} y2={cy+Math.sin(a)*r} stroke="var(--border)" strokeWidth={0.6} strokeDasharray={isNull?"4,3":"none"}/><text x={lx} y={ly-5} textAnchor="middle" dominantBaseline="middle" fontSize={10} fontFamily={T.mono} fill={isNull?"#d1d5db":T.textMuted} fontWeight="600">{FL[k]}</text><text x={lx} y={ly+9} textAnchor="middle" dominantBaseline="middle" fontSize={12} fontFamily={T.mono} fill={c} fontWeight="700">{isNull?"—":((v??0)*100).toFixed(0)}</text></g>;})}
      <polygon points={vals.map((v,i)=>`${cx+Math.cos(ang(i))*Math.max(0.05,v)*r},${cy+Math.sin(ang(i))*Math.max(0.05,v)*r}`).join(" ")} fill={fill} fillOpacity={0.12} stroke={fill} strokeWidth={2} strokeLinejoin="round"/>
      {vals.map((v,i)=><circle key={i} cx={cx+Math.cos(ang(i))*Math.max(0.05,v)*r} cy={cy+Math.sin(ang(i))*Math.max(0.05,v)*r} r={4} fill={raw[i]==null?"#d1d5db":fill} stroke="var(--bg-surface)" strokeWidth={1.5}/>)}
      <text x={cx} y={size-4} textAnchor="middle" fontSize={9} fontFamily={T.mono} fill={T.textLight}>{covCount}/{FACTOR_ORDER.length} factors</text>
    </svg>
  );
}

function FactorBar({name,weight,score,detail}:{name:string;weight:number;score:number|null;detail:string}){
  if(score==null)return<div style={{padding:"8px 0",borderBottom:`1px solid ${T.divider}`,opacity:0.45}}><div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:4}}><div style={{display:"flex",alignItems:"baseline",gap:6}}><span style={{fontSize:12,fontFamily:T.mono,fontWeight:600,color:"#d1d5db"}}>{name}</span><span style={{fontSize:9,fontFamily:T.mono,color:"#d1d5db"}}>({weight}%)</span></div><span style={{fontSize:11,fontFamily:T.mono,color:"#d1d5db",fontStyle:"italic"}}>no data</span></div><div style={{height:5,borderRadius:3,background:T.divider}}><div style={{height:"100%",width:0}}/></div><div style={{fontSize:10,fontFamily:T.mono,color:"#d1d5db",lineHeight:1.5}}>Weight redistributed to evaluated factors</div></div>;
  const c=score>0.7?"var(--green)":score>0.4?T.amber:T.red;
  const tip=TOOLTIPS[name]||"";
  return(
    <div style={{padding:"8px 0",borderBottom:`1px solid ${T.divider}`}}>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:4}}>
        <div style={{display:"flex",alignItems:"baseline",gap:6}}>
          <span title={tip} style={{fontSize:12,fontFamily:T.mono,fontWeight:600,color:T.text,cursor:tip?"help":"default",borderBottom:tip?`1px dotted ${T.textLight}`:"none"}}>{name}</span>
          <span style={{fontSize:9,fontFamily:T.mono,color:T.textLight}}>({weight}%)</span>
        </div>
        <span style={{fontSize:13,fontFamily:T.mono,fontWeight:700,color:c}}>{(score*100).toFixed(0)}</span>
      </div>
      <div style={{height:5,borderRadius:3,background:T.divider,overflow:"hidden",marginBottom:4}}>
        <div style={{height:"100%",width:`${score*100}%`,borderRadius:3,background:c,transition:"width 0.4s ease"}}/>
      </div>
      <div style={{fontSize:10,fontFamily:T.mono,color:T.textMuted,lineHeight:1.5}}>{detail}</div>
    </div>
  );
}

// ── Compounder Breakdown Card — 3-factor cohort-relative scoring ──────────
// v1.2 (May 2026). Renders the Compounder model's contribution bars:
// ROE (3yr avg), P/B (lower is better — shown inverted as a percentile rank),
// OpMargin Δ (3yr change). Each factor is equal-weighted at 33.3%; the
// composite is the mean of the three percentiles within the chosen cohort
// (US or Global). The card always renders so it sits beside the v8 5-Factor
// card; it shows a disqualified state when the stock isn't in the chosen
// cohort.
//
// Cohort selection:
//   cohort="us"      — uses cmp_us_*_pct fields + compounder_score_us
//   cohort="global"  — uses cmp_global_*_pct + compounder_score_global
function CompounderBreakdownCard({s,cohort,active}:{
  s:StockData; cohort:"us"|"global"; active:boolean;
}){
  const isUS = cohort==="us";
  const score    = isUS ? s.compounder_score_us : s.compounder_score_global;
  const rank     = isUS ? s.compounder_rank_us : s.compounder_rank_global;
  const signal   = isUS ? s.signal_compounder_us : s.signal_compounder_global;
  const roe_pct  = isUS ? s.cmp_us_roe_pct : s.cmp_global_roe_pct;
  const pb_pct   = isUS ? s.cmp_us_pb_pct  : s.cmp_global_pb_pct;
  const opd_pct  = isUS ? s.cmp_us_opd_pct : s.cmp_global_opd_pct;
  const qualified = signal === "QUALIFIED";

  const cohortLabel = isUS ? "US cohort" : "Global cohort";
  const title = `Compounder (${isUS?"US":"Global"})`;
  const sub = qualified
    ? `${cohortLabel} · Composite ${(score??0).toFixed(2)} · Rank #${rank ?? "—"}`
    : `${cohortLabel} · Not qualified for this cohort`;

  // Raw metric values for the detail line under each bar
  const roeRaw = s.roe_compounder;
  const pbRaw  = s.pb_compounder;
  const opdRaw = s.opmargin_delta_compounder;
  const pct=(v:number|null|undefined,d=1)=>v==null?"?":`${(v*100).toFixed(d)}%`;
  const num=(v:number|null|undefined,d=2)=>v==null?"?":v.toFixed(d);
  const detailROE = `3yr avg ROE ${pct(roeRaw)}`;
  const detailPB  = `P/B ${num(pbRaw,2)}× — lower is better, so rank inverts`;
  const detailOPD = `OpMargin Δ ${roeRaw!=null && opdRaw!=null
    ? (opdRaw>=0?"+":"") + (opdRaw*100).toFixed(1) + "pp 3yr"
    : "?"}`;

  const wrap:React.CSSProperties = {
    marginBottom:0,
    ...(active ? {boxShadow:`0 0 0 2px ${T.green}`, borderColor:T.green} : {}),
  };

  return(
    <Card style={wrap}>
      <SH title={title} icon={<BarChart2 size={12}/>} sub={sub}/>
      {!qualified ? (
        <div style={{padding:"24px 8px",display:"flex",alignItems:"center",
          justifyContent:"center",fontSize:11,fontFamily:T.mono,color:T.textLight,
          lineHeight:1.6,textAlign:"center"}}>
          Stock is not part of the {isUS?"US":"Global"} Compounder cohort.<br/>
          {isUS
            ? "US gate: listed on US exchange, market cap ≥ $2B, ex Fin/Ins/HC."
            : "Global gate: any market, ex Fin/Ins/HC, all 3 metrics present."}
        </div>
      ) : (
        <div style={{display:"grid",gridTemplateColumns:"1fr",gap:0}}>
          <FactorBar name="ROE (3yr avg)"   weight={33} score={roe_pct ?? null} detail={detailROE}/>
          <FactorBar name="P/B (inverted)"  weight={33} score={pb_pct  ?? null} detail={detailPB}/>
          <FactorBar name="OpMargin Δ (3y)" weight={34} score={opd_pct ?? null} detail={detailOPD}/>
          <div style={{marginTop:10,padding:"10px 12px",borderRadius:5,
            background:T.greenLight,border:`1px solid ${T.greenBorder}`,
            fontSize:10,fontFamily:T.mono,color:T.text,lineHeight:1.5}}>
            <div style={{fontWeight:600,color:T.green,fontSize:9,letterSpacing:"0.08em",marginBottom:3}}>HOW THIS IS SCORED</div>
            Each bar is this stock's percentile rank within the {cohortLabel.toLowerCase()}
            on that metric (100 = best in cohort). Composite is the equal-weighted mean.
          </div>
        </div>
      )}
    </Card>
  );
}

function factorDetail(k:string,s:StockData,mode:string):string{
  const c=s.currency==="EUR"?"€":s.currency==="GBP"?"£":"$";
  const pct=(v:number|undefined|null,d=1)=>v==null?"?":`${(v*100).toFixed(d)}%`;
  const pctSigned=(v:number|undefined|null,d=1)=>v==null?"?":`${v>=0?"+":""}${(v*100).toFixed(d)}%`;
  switch(k){
    case"momentum":
      if(mode==="fallen_angel"){
        return `Reversal ${s.reversal_score??0}/10 · RSI ${s.rsi?.toFixed(0)} · MACD ${s.macd_signal} · 52w ${(s.proximity_52wk!=null?s.proximity_52wk*100:0).toFixed(0)}% of range`;
      }
      return `Bull ${s.bull_score}/10 · RSI ${s.rsi?.toFixed(0)} · MACD ${s.macd_signal} · ADX ${s.adx?.toFixed(0)}`;
    case"quality":
      // Net 35 + FCF 35 + ROIC 30. Piotroski/Altman shown for context, not in score.
      return `Net ${pct(s.net_margin)} · FCF ${pct(s.fcf_margin)} · ROIC ${pct(s.roic_avg)} · (Piotroski ${s.piotroski}/9 · Z ${s.altman_z?.toFixed(1)})`;
    case"growth":
      return `Rev ${pctSigned(s.revenue_yoy)} YoY / ${pctSigned(s.revenue_cagr_3y)} 3y · EPS ${pctSigned(s.eps_yoy)} / ${pctSigned(s.eps_cagr_3y)} · FCF ${pctSigned(s.fcf_yoy)} / ${pctSigned(s.fcf_cagr_3y)}`;
    case"value":{
      const iu=s.intrinsic_upside;
      const pf=s.p_fcf;
      const ey=s.earnings_yield;
      return `Intrinsic ${iu==null?"?":(iu>=0?"+":"")+iu.toFixed(0)+"%"} · P/FCF ${pf?pf.toFixed(1)+"x":"?"} · EarnYld ${ey?(ey*100).toFixed(1)+"%":"?"}`;
    }
    case"smart_money":{
      const parts:string[]=[];
      if(s.grade_total)parts.push(`Grades ${s.grade_buy}/${s.grade_total}`);
      if(s.insider_net_buys!=null)parts.push(`Insider net ${s.insider_net_buys>=0?"+":""}${s.insider_net_buys}`);
      if(s.eps_total)parts.push(`EPS beats ${s.eps_beats}/${s.eps_total}`);
      if(s.inst_holders_change!=null&&s.inst_holders_change!==0)parts.push(`Inst ${(s.inst_holders_change*100).toFixed(1)}% QoQ`);
      if(s.transcript_sentiment)parts.push(`Tone ${s.transcript_sentiment>=0?"+":""}${s.transcript_sentiment.toFixed(2)}`);
      return parts.length?parts.join(" · "):"No smart-money data yet";
    }
    default:return"";
  }
}

// ── Probability Card ───────────────────────────────────────────────────────────
// ── ProbabilityCard removed v1.2 (May 2026) ──────────────────────────────
// Replaced by P20Card (see below). The old card showed a 3-bar lookup table
// (P+5/P+10/P+20) derived from composite via getProb(); P20Card reads the
// actual ML model output (s.hit_prob = P(+20% daily high in 4w) from
// time_model_v2 ensemble) and shows calibrated decile + spread edge.

// ── Catalyst Timeline ──────────────────────────────────────────────────────────
function CatalystTimeline({s}:{s:StockData}){
  const items:(string|null)[] = [];
  if(s.days_to_earnings!=null&&s.days_to_earnings>=0) items.push(`Earnings in ${s.days_to_earnings} days${s.eps_beats!=null?` (${s.eps_beats}/${s.eps_total} beat streak)`:""}`);
  if(s.catalyst_flags) s.catalyst_flags.forEach(f=>items.push(f));
  if(!items.filter(Boolean).length) return null;
  return(
    <Card>
      <SH title="Catalyst Timeline" icon={<Zap size={12}/>}/>
      <div style={{display:"flex",flexDirection:"column",gap:8}}>
        {items.filter(Boolean).map((item,i)=>(
          <div key={i} style={{display:"flex",alignItems:"center",gap:10}}>
            <div style={{width:8,height:8,borderRadius:"50%",background:T.purple,flexShrink:0}}/>
            <span style={{fontSize:11,fontFamily:T.mono,color:T.text}}>{item}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}

// ── Composite History Chart ────────────────────────────────────────────────────
// ── SentimentCard — market positioning snapshot from data we already fetch ──
// This is NOT an options/IV card. It reads insider + institutional flows, price
// position in 52wk range, and short-term momentum to produce a plain-language
// read on "what does positioning look like right now". Labeled honestly.
function SentimentCard({s}:{s:StockData}){
  // ─── Inputs (all from existing scan data) ───
  const rsi = s.rsi ?? 50;
  const prox = s.proximity_52wk ?? 0.5;              // 0 = at low, 1 = at high
  const bull = s.bull_score ?? 5;                     // 0-10 technical composite
  const insiderNet = s.insider_net_buys ?? 0;         // net buy txns (recent ~2q)
  const insiderRatio = s.insider_buy_ratio ?? 0;      // acquired/disposed ratio
  const instHold = s.inst_holders_change ?? 0;        // QoQ holder count change
  const instAccum = s.inst_accumulation ?? 0;         // net shares accumulated
  const macd = s.macd_signal || "";
  const adx = s.adx ?? 0;

  // ─── Derived reads ───
  // 1. Insider posture
  let insiderLabel="Neutral", insiderColor=T.textMuted, insiderDetail="No recent activity";
  if(insiderNet>=3 || insiderRatio>=2){
    insiderLabel="Accumulating"; insiderColor=T.green;
    insiderDetail=`${insiderNet} net buys · ${insiderRatio.toFixed(1)}x acquired/disposed`;
  } else if(insiderNet<=-3 || (insiderRatio>0 && insiderRatio<0.3)){
    insiderLabel="Distributing"; insiderColor=T.red;
    insiderDetail=`${insiderNet} net buys · ${insiderRatio.toFixed(1)}x acquired/disposed`;
  } else if(insiderNet!==0 || insiderRatio!==0){
    insiderDetail=`${insiderNet>0?"+":""}${insiderNet} net buys · ${insiderRatio.toFixed(1)}x ratio`;
  }

  // 2. Institutional posture
  let instLabel="Flat", instColor=T.textMuted, instDetail="No QoQ change";
  if(instAccum>0.02 || instHold>0.02){
    instLabel="Accumulating"; instColor=T.green;
    instDetail=`Holders ${(instHold*100).toFixed(1)}% QoQ · Shares ${(instAccum*100).toFixed(1)}%`;
  } else if(instAccum<-0.02 || instHold<-0.02){
    instLabel="Distributing"; instColor=T.red;
    instDetail=`Holders ${(instHold*100).toFixed(1)}% QoQ · Shares ${(instAccum*100).toFixed(1)}%`;
  } else if(instAccum!==0 || instHold!==0){
    instDetail=`Holders ${(instHold*100).toFixed(1)}% · Shares ${(instAccum*100).toFixed(1)}%`;
  }

  // 3. Technical posture
  let techLabel="Neutral", techColor=T.textMuted;
  if(bull>=7 && (macd==="bullish"||macd==="Bullish")) {techLabel="Bullish"; techColor=T.green;}
  else if(bull>=6) {techLabel="Constructive"; techColor=T.green;}
  else if(bull<=3) {techLabel="Bearish"; techColor=T.red;}
  else if(bull<=4) {techLabel="Weak"; techColor=T.amber;}

  // 4. Range positioning — where in 52w range
  let rangeLabel="Mid-range", rangeColor=T.textMuted;
  if(prox>=0.85) {rangeLabel="Near highs"; rangeColor=T.amber;}
  else if(prox>=0.65) {rangeLabel="Upper range"; rangeColor=T.green;}
  else if(prox<=0.15) {rangeLabel="Near lows"; rangeColor=T.red;}
  else if(prox<=0.35) {rangeLabel="Lower range"; rangeColor=T.amber;}

  // 5. RSI overbought/oversold
  let rsiLabel="—", rsiColor=T.textMuted;
  if(rsi>=70) {rsiLabel="Overbought"; rsiColor=T.amber;}
  else if(rsi<=30) {rsiLabel="Oversold"; rsiColor=T.amber;}
  else if(rsi>=55) {rsiLabel="Strong"; rsiColor=T.green;}
  else if(rsi<=45) {rsiLabel="Weak"; rsiColor=T.red;}
  else rsiLabel="Balanced";

  // 6. Trend strength (ADX)
  let trendLabel="—";
  if(adx>=35) trendLabel="Strong trend";
  else if(adx>=25) trendLabel="Defined trend";
  else if(adx>0) trendLabel="Choppy";

  // ─── Plain-language synthesis ───
  // Build a one-line read: which way do the flows + price agree, and which
  // don't. The goal is helping the user pattern-match, not prescriptive calls.
  const agreesBull = [
    insiderLabel==="Accumulating",
    instLabel==="Accumulating",
    techLabel==="Bullish"||techLabel==="Constructive",
    prox>=0.5,
  ].filter(Boolean).length;
  const agreesBear = [
    insiderLabel==="Distributing",
    instLabel==="Distributing",
    techLabel==="Bearish"||techLabel==="Weak",
    prox<0.3,
  ].filter(Boolean).length;

  let synthesis = "Mixed signals — flows, technicals, and price position don't agree.";
  if(agreesBull>=3 && agreesBear===0){
    synthesis = "Positioning is aligned bullish: insiders and institutions are adding, technicals confirm, price is in the upper range. Watch for overbought exhaustion if RSI crosses 70.";
  } else if(agreesBear>=3 && agreesBull===0){
    synthesis = "Positioning is aligned bearish: insiders and institutions are reducing, technicals are weak, price is in the lower range. Oversold bounces may be fragile.";
  } else if(agreesBull>=2 && agreesBear<=1){
    synthesis = "Lean bullish. Insider and/or institutional accumulation with constructive technicals. Not a unanimous read — size accordingly.";
  } else if(agreesBear>=2 && agreesBull<=1){
    synthesis = "Lean bearish. Distribution or weakness in 2+ of insider/inst/technical/price. Bounces may lack follow-through.";
  } else if(insiderLabel==="Accumulating" && techLabel==="Weak"){
    synthesis = "Divergence: insiders buying into weakness. Classic contrarian setup but patient — technicals say not yet.";
  } else if(insiderLabel==="Distributing" && prox>=0.75){
    synthesis = "Divergence: insiders selling near 52w highs. Possible distribution into strength — caution for late entries.";
  } else if(prox>=0.85 && rsi>=70){
    synthesis = "Extended. Price at highs + overbought RSI — risk of short-term mean reversion, not necessarily reversal.";
  } else if(prox<=0.15 && rsi<=30){
    synthesis = "Oversold at lows. Reflex bounce is common here but confirmation from flows would de-risk re-entry.";
  }

  const chip=(label:string,value:string,color:string,detail?:string)=>{
    const tip=TOOLTIPS[label]||"";
    return(
    <div style={{padding:"8px 10px",borderRadius:5,border:`1px solid ${T.cardBorder}`,background:T.card}}>
      <div title={tip} style={{fontSize:9,color:T.textMuted,fontFamily:T.mono,fontWeight:600,letterSpacing:"0.08em",cursor:tip?"help":"default",borderBottom:tip?`1px dotted ${T.textLight}`:"none"}}>{label}</div>
      <div style={{fontSize:12,color:color,fontFamily:T.mono,fontWeight:700,marginTop:2}}>{value}</div>
      {detail && <div style={{fontSize:9,color:T.textLight,fontFamily:T.mono,marginTop:1,lineHeight:1.3}}>{detail}</div>}
    </div>
  );};

  return(
    <Card>
      <SH title="Sentiment Snapshot" icon={<Activity size={12}/>} sub="Positioning, not IV"/>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:6,marginBottom:10}}>
        {chip("INSIDERS", insiderLabel, insiderColor, insiderDetail)}
        {chip("INSTITUTIONS", instLabel, instColor, instDetail)}
        {chip("TECHNICAL", techLabel, techColor, `Bull ${bull}/10 · ${trendLabel}${adx>0?` (ADX ${adx.toFixed(0)})`:""}`)}
        {chip("52W RANGE", rangeLabel, rangeColor, `At ${(prox*100).toFixed(0)}% of range · RSI ${rsi.toFixed(0)} ${rsiLabel}`)}
      </div>
      <div style={{padding:"10px 12px",borderRadius:5,background:T.greenLight,border:`1px solid ${T.greenBorder}`,fontSize:11,fontFamily:T.sans,color:T.text,lineHeight:1.55}}>
        <span style={{fontWeight:600,color:T.green,fontFamily:T.mono,fontSize:9,letterSpacing:"0.08em",display:"block",marginBottom:4}}>READ</span>
        {synthesis}
      </div>
      <div style={{fontSize:9,color:T.textLight,fontFamily:T.mono,marginTop:8,lineHeight:1.4}}>
        Built from insider transactions, 13F flows, and price technicals. Does not include options IV or short interest — FMP stable REST doesn't expose those.
      </div>
    </Card>
  );
}

// ── CompanyProfileCard — business description + share structure + top holders ──
// Fetches three FMP endpoints in parallel: company profile, shares float,
// and top-10 13F holders. All are lightweight single-row lookups. No heavy
// processing client-side — mostly display.
//
// One quirk worth knowing: both freeFloat and institutional ownershipPercent
// can exceed 100% on some names. It's not a bug — shares borrowed for short-
// selling end up double-counted when both the lender's fund and the short
// seller's broker report them in 13F filings. We flag it honestly in the UI
// rather than hiding the number.
function CompanyProfileCard({symbol}:{symbol:string}){
  type Profile={
    companyName?:string; sector?:string; industry?:string; country?:string;
    fullTimeEmployees?:string; ceo?:string; website?:string; ipoDate?:string;
    description?:string; beta?:number; marketCap?:number; isAdr?:boolean;
    exchangeFullName?:string; address?:string; city?:string; state?:string;
  };
  type Float={floatShares?:number; outstandingShares?:number; freeFloat?:number};
  type Holder={
    investorName:string; ownership:number; marketValue:number;
    sharesNumber:number; changeInSharesNumberPercentage:number;
    avgPricePaid:number; holdingPeriod:number; isNew:boolean;
  };
  type Positions={
    investorsHolding?:number; investorsHoldingChange?:number;
    ownershipPercent?:number; newPositions?:number; closedPositions?:number;
  };

  const [profile,setProfile]=useState<Profile|null>(null);
  const [floatData,setFloatData]=useState<Float|null>(null);
  const [holders,setHolders]=useState<Holder[]>([]);
  const [positions,setPositions]=useState<Positions|null>(null);
  const [loading,setLoading]=useState(true);
  const [expanded,setExpanded]=useState(false);

  useEffect(()=>{
    let cancelled=false;
    setLoading(true);

    fetch(`/api/company/${encodeURIComponent(symbol)}`)
      .then(r=>r.ok?r.json():null)
      .then(d=>{
        if(cancelled||!d) return;
        setProfile(d.profile??null);
        setFloatData(d.float??null);
        setHolders((d.holders as Holder[])??[]);
        setPositions((d.positions as Positions)??null);
        setLoading(false);
      }).catch(()=>{if(!cancelled) setLoading(false);});

    return ()=>{cancelled=true;};
  },[symbol]);

  const fmtBn=(n?:number)=>{
    if(!n) return "—";
    if(n>=1e12) return `$${(n/1e12).toFixed(2)}T`;
    if(n>=1e9) return `$${(n/1e9).toFixed(2)}B`;
    if(n>=1e6) return `$${(n/1e6).toFixed(0)}M`;
    return `$${(n/1e3).toFixed(0)}K`;
  };
  const fmtShares=(n?:number)=>{
    if(!n) return "—";
    if(n>=1e9) return `${(n/1e9).toFixed(2)}B`;
    if(n>=1e6) return `${(n/1e6).toFixed(1)}M`;
    if(n>=1e3) return `${(n/1e3).toFixed(0)}K`;
    return String(n);
  };
  const ipoYear=profile?.ipoDate?profile.ipoDate.substring(0,4):"—";
  const empCount=profile?.fullTimeEmployees?Number(profile.fullTimeEmployees).toLocaleString():"—";
  const desc=profile?.description||"";
  const descShort=desc.length>280?desc.substring(0,280).replace(/\s+\S*$/,"")+"…":desc;
  const descLong=desc;

  const floatRatio=floatData?.floatShares&&floatData?.outstandingShares
    ?floatData.floatShares/floatData.outstandingShares:null;
  const floatExceeds100=floatData?.freeFloat && floatData.freeFloat>100;

  const instExceeds100=positions?.ownershipPercent && positions.ownershipPercent>100;

  // Top 5 holders sorted by ownership desc (API returns by market value — re-sort)
  const topHolders=[...holders].sort((a,b)=>(b.ownership||0)-(a.ownership||0)).slice(0,5);

  if(loading){
    return (
      <Card>
        <SH title="Company Profile" icon={<Activity size={12}/>}/>
        <div style={{padding:"20px 0",textAlign:"center",color:T.textMuted,fontSize:11,fontFamily:T.mono}}>
          <Loader2 size={14} style={{animation:"spin 1s linear infinite",verticalAlign:"middle",marginRight:6}}/>
          Loading company data…
        </div>
      </Card>
    );
  }

  if(!profile){
    return (
      <Card>
        <SH title="Company Profile" icon={<Activity size={12}/>}/>
        <div style={{padding:"20px 0",textAlign:"center",color:T.textMuted,fontSize:11,fontFamily:T.mono}}>
          No profile data available.
        </div>
      </Card>
    );
  }

  const metricBox=(label:string,value:string,sub?:string,color?:string)=>(
    <div>
      <div style={{fontSize:9,color:T.textMuted,fontFamily:T.mono,fontWeight:600,letterSpacing:"0.08em"}}>{label}</div>
      <div style={{fontSize:13,color:color||T.text,fontFamily:T.mono,fontWeight:700,marginTop:2}}>{value}</div>
      {sub && <div style={{fontSize:9,color:T.textLight,fontFamily:T.mono,marginTop:1}}>{sub}</div>}
    </div>
  );

  return (
    <Card>
      <SH title="Company Profile" icon={<Activity size={12}/>}
        sub={profile.exchangeFullName||profile.country||""}/>

      {/* Top strip: identity */}
      <div style={{display:"flex",flexWrap:"wrap",gap:"4px 14px",fontSize:11,fontFamily:T.mono,color:T.textMuted,marginBottom:12,paddingBottom:10,borderBottom:`1px solid ${T.divider}`}}>
        {profile.sector && <span><span style={{color:T.textLight}}>Sector:</span> <span style={{color:T.text,fontWeight:600}}>{profile.sector}</span></span>}
        {profile.industry && <span><span style={{color:T.textLight}}>Industry:</span> <span style={{color:T.text,fontWeight:600}}>{profile.industry}</span></span>}
        {profile.ceo && <span><span style={{color:T.textLight}}>CEO:</span> <span style={{color:T.text,fontWeight:600}}>{profile.ceo}</span></span>}
        <span><span style={{color:T.textLight}}>Employees:</span> <span style={{color:T.text,fontWeight:600}}>{empCount}</span></span>
        <span><span style={{color:T.textLight}}>IPO:</span> <span style={{color:T.text,fontWeight:600}}>{ipoYear}</span></span>
        {profile.isAdr && <span style={{color:T.blue,fontWeight:600}}>ADR</span>}
        {profile.website && <a href={profile.website} target="_blank" rel="noopener noreferrer" style={{color:T.green,textDecoration:"none",fontWeight:600}}>↗ website</a>}
      </div>

      {/* Business description */}
      {desc && (
        <div style={{marginBottom:14}}>
          <div style={{fontSize:9,color:T.textMuted,fontFamily:T.mono,fontWeight:600,letterSpacing:"0.08em",marginBottom:6}}>BUSINESS</div>
          <div style={{fontSize:12,color:T.text,fontFamily:T.sans,lineHeight:1.55}}>
            {expanded?descLong:descShort}
            {desc.length>280 && (
              <button onClick={()=>setExpanded(!expanded)} style={{marginLeft:6,background:"none",border:"none",color:T.green,cursor:"pointer",fontSize:11,fontFamily:T.mono,fontWeight:600,padding:0}}>
                {expanded?"show less":"show more"}
              </button>
            )}
          </div>
        </div>
      )}

      {/* Share structure */}
      <div style={{display:"grid",gridTemplateColumns:"repeat(4, 1fr)",gap:14,marginBottom:14,paddingBottom:14,borderBottom:`1px solid ${T.divider}`}}>
        {metricBox("MARKET CAP", fmtBn(profile.marketCap))}
        {metricBox("SHARES OUT", fmtShares(floatData?.outstandingShares))}
        {metricBox(
          "FREE FLOAT",
          floatData?.floatShares?fmtShares(floatData.floatShares):"—",
          floatRatio?`${(floatRatio*100).toFixed(0)}% of outstanding`:undefined,
          floatExceeds100?T.amber:undefined
        )}
        {metricBox(
          "BETA",
          profile.beta?profile.beta.toFixed(2):"—",
          profile.beta?(profile.beta<0.8?"Defensive":profile.beta>1.2?"High volatility":"Market-like"):undefined,
          profile.beta?(profile.beta<0.8?T.green:profile.beta>1.2?T.amber:T.textMuted):undefined
        )}
      </div>

      {floatExceeds100 && (
        <div style={{fontSize:10,color:T.amber,fontFamily:T.mono,marginBottom:10,padding:"6px 10px",background:T.amberLight,borderRadius:4,border:`1px solid var(--amber)`}}>
          ⚠ Free float exceeds 100% — typical when shares are heavily borrowed for short-selling (double-counted in reporting).
        </div>
      )}

      {/* Institutional ownership summary */}
      {positions && (
        <div style={{display:"grid",gridTemplateColumns:"repeat(4, 1fr)",gap:14,marginBottom:14}}>
          {metricBox("13F HOLDERS", String(positions.investorsHolding??"—"),
            positions.investorsHoldingChange!==undefined && positions.investorsHoldingChange!==null
              ?`${positions.investorsHoldingChange>0?"+":""}${positions.investorsHoldingChange} QoQ`
              :undefined,
            (positions.investorsHoldingChange??0)>0?T.green:(positions.investorsHoldingChange??0)<0?T.red:undefined)}
          {metricBox("INST OWNERSHIP",
            positions.ownershipPercent?`${positions.ownershipPercent.toFixed(0)}%`:"—",
            instExceeds100?"incl. lent shares":undefined,
            instExceeds100?T.amber:(positions.ownershipPercent??0)>70?T.green:undefined)}
          {metricBox("NEW POSITIONS",
            String(positions.newPositions??"—"),
            "this quarter",
            (positions.newPositions??0)>20?T.green:undefined)}
          {metricBox("CLOSED POSITIONS",
            String(positions.closedPositions??"—"),
            "this quarter",
            (positions.closedPositions??0)>20?T.red:undefined)}
        </div>
      )}

      {/* Top 5 holders table */}
      {topHolders.length>0 && (
        <div>
          <div style={{fontSize:9,color:T.textMuted,fontFamily:T.mono,fontWeight:600,letterSpacing:"0.08em",marginBottom:8}}>TOP 5 INSTITUTIONAL HOLDERS</div>
          <div style={{display:"grid",gridTemplateColumns:"2.5fr 0.7fr 0.9fr 0.9fr 0.9fr",gap:"4px 10px",fontSize:10,fontFamily:T.mono}}>
            <div style={{color:T.textLight,fontWeight:600,paddingBottom:4,borderBottom:`1px solid ${T.divider}`}}>HOLDER</div>
            <div style={{color:T.textLight,fontWeight:600,textAlign:"right",paddingBottom:4,borderBottom:`1px solid ${T.divider}`}}>% OWN</div>
            <div style={{color:T.textLight,fontWeight:600,textAlign:"right",paddingBottom:4,borderBottom:`1px solid ${T.divider}`}}>VALUE</div>
            <div style={{color:T.textLight,fontWeight:600,textAlign:"right",paddingBottom:4,borderBottom:`1px solid ${T.divider}`}}>Δ SHARES</div>
            <div style={{color:T.textLight,fontWeight:600,textAlign:"right",paddingBottom:4,borderBottom:`1px solid ${T.divider}`}}>AVG COST</div>
            {topHolders.map((h,i)=>{
              const chg=h.changeInSharesNumberPercentage||0;
              const chgColor=chg>1?T.green:chg<-1?T.red:T.textMuted;
              const chgLabel=h.isNew?"NEW":`${chg>0?"+":""}${chg.toFixed(1)}%`;
              return (
                <div key={i} style={{display:"contents"}}>
                  <div style={{color:T.text,fontWeight:600,padding:"5px 0",textTransform:"capitalize"}}>
                    {h.investorName.toLowerCase().replace(/\b\w/g,c=>c.toUpperCase())}
                    {h.holdingPeriod>=20 && <span style={{marginLeft:6,fontSize:9,color:T.textLight,fontWeight:400}}>since {Math.floor(h.holdingPeriod/4)}y</span>}
                  </div>
                  <div style={{color:T.text,textAlign:"right",padding:"5px 0"}}>{h.ownership.toFixed(2)}%</div>
                  <div style={{color:T.text,textAlign:"right",padding:"5px 0"}}>{fmtBn(h.marketValue)}</div>
                  <div style={{color:chgColor,textAlign:"right",padding:"5px 0",fontWeight:h.isNew?700:400}}>{chgLabel}</div>
                  <div style={{color:T.textMuted,textAlign:"right",padding:"5px 0"}}>${h.avgPricePaid.toFixed(2)}</div>
                </div>
              );
            })}
          </div>
          <div style={{fontSize:9,color:T.textLight,fontFamily:T.mono,marginTop:10,lineHeight:1.4}}>
            13F filings lag ~45 days. Data as of most recent completed quarter. Δ SHARES is QoQ position change.
          </div>
        </div>
      )}
    </Card>
  );
}


// ═══════════════════════════════════════════════════════════════════════
// P20Card v2 — Pure ML probability card. No options data.
// ═══════════════════════════════════════════════════════════════════════

function P20Card({s}:{s:StockData}){
  const p20 = s.hit_prob ?? 0;
  if(p20 <= 0) return null;

  const p20pct = p20 * 100;

  // Lower thresholds scaled from the v4 OOS distribution (model-pred baseline).
  const p5  = Math.min(p20 * 3.41, 0.80);
  const p10 = Math.min(p20 * 2.29, 0.65);
  const p15 = Math.min(p20 * 1.49, 0.50);

  // Decile = OOS-calibrated rank from the v4 holdout p20_60 thresholds
  // (calibration_tracking/v2/config.json → decile_thresholds.p20_60), computed
  // from the 60-bar +20% probability — the horizon the /performance calibration
  // tracker validates. NOT a client-side relative rank.
  const P20_60_DECILE_EDGES = [0.103,0.163,0.229,0.296,0.345,0.393,0.445,0.516,0.577];
  const p60 = s.hit_prob_60d ?? null;
  const decile = p60==null ? null : P20_60_DECILE_EDGES.reduce((d,t)=>p60>=t?d+1:d, 1);
  const signal = decile!=null
    ? (decile>=9?"STRONG":decile>=7?"MODERATE":decile>=5?"MILD":"WEAK")
    : (p20>=0.15?"STRONG":p20>=0.08?"MODERATE":p20>=0.03?"MILD":"WEAK");
  const signalColor = signal==="STRONG"?T.green:signal==="MODERATE"?T.amber:T.textMuted;

  const pBar=(threshold:string, pct:number, isRaw:boolean)=>{
    const w=Math.max(pct,2);
    const color=pct>=40?T.green:pct>=20?"var(--green)":pct>=10?T.amber:T.textMuted;
    return(
      <div style={{display:"flex",alignItems:"center",gap:8,padding:"5px 0",borderBottom:`1px solid ${T.divider}`}}>
        <div style={{width:50,fontSize:10,fontFamily:T.mono,color:T.textMuted,fontWeight:600,textAlign:"right"}}>{threshold}</div>
        <div style={{flex:1,height:16,background:T.divider,borderRadius:3,overflow:"hidden",position:"relative"}}>
          <div style={{width:`${w}%`,height:"100%",background:color,borderRadius:3,transition:"width 0.4s"}}/>
          <span style={{position:"absolute",left:8,top:0,lineHeight:"16px",fontSize:10,fontFamily:T.mono,fontWeight:700,color:w>30?"var(--bg-surface)":T.text}}>{pct.toFixed(0)}%</span>
        </div>
        <div style={{width:36,fontSize:9,fontFamily:T.mono,color:T.textLight,textAlign:"right"}}>{isRaw?"model":"est."}</div>
      </div>
    );
  };

  return(
    <Card>
      <SH title="Move Probability (ML)" icon={<TrendingUp size={12}/>}
        sub={decile!=null?`Decile ${decile}/10 · ${signal} signal`:`${signal} signal`}/>
      <div style={{display:"flex",alignItems:"baseline",gap:12,marginBottom:14,paddingBottom:14,borderBottom:`1px solid ${T.divider}`}}>
        <div>
          <div style={{fontSize:9,color:T.textMuted,fontFamily:T.mono,fontWeight:600,letterSpacing:"0.08em"}}>P(+20% IN 4W)</div>
          <div style={{fontSize:28,color:signalColor,fontFamily:T.mono,fontWeight:700,marginTop:2}}>{p20pct.toFixed(0)}%</div>
          <div style={{fontSize:9,color:T.textLight,fontFamily:T.mono,marginTop:1}}>{decile!=null?`D${decile}/10 · `:""}{(p20pct/5.3).toFixed(1)}x base rate</div>
        </div>
        <div style={{flex:1,fontSize:11,fontFamily:T.sans,color:T.textMuted,lineHeight:1.5,paddingLeft:16,borderLeft:`1px solid ${T.divider}`}}>
          {signal==="STRONG"
            ? "Top-decile ML signal — among the strongest move-probability names in the universe."
            : signal==="MODERATE"
            ? "Moderate ML move signal — mid-to-upper decile."
            : "Below the actionable threshold. Model sees limited near-term move probability."}
        </div>
      </div>
      <div style={{fontSize:9,color:T.textMuted,fontFamily:T.mono,fontWeight:600,letterSpacing:"0.08em",marginBottom:6}}>
        P(CLOSE ABOVE THRESHOLD IN 4 WEEKS)
      </div>
      {pBar("+5%", p5*100, false)}
      {pBar("+10%", p10*100, false)}
      {pBar("+15%", p15*100, false)}
      {pBar("+20%", p20*100, true)}
      <div style={{marginTop:10,fontSize:9,color:T.textLight,fontFamily:T.mono,lineHeight:1.5}}>
        time_model_v4 · TOP-3 ensemble · 48 features · OOS AUC 0.776.
        P(+20% in 4w) is direct model output; lower thresholds scaled from the OOS distribution.
        Decile = v4 OOS holdout thresholds (p20_60) — the same calibration shown on /performance. Not investment advice.
      </div>
    </Card>
  );
}


// ═══════════════════════════════════════════════════════════════════════
// MassiveOptionsCard v3 — Always proposes a spread (live or estimated).
// EV calculation drives the signal: green = edge, red = no edge.
// ═══════════════════════════════════════════════════════════════════════

function MassiveOptionsCard({s}:{s:StockData}){
  const hasIV=s.options_iv_current!=null||s.options_iv_rank!=null;
  const hasPositioning=s.options_pc_ratio!=null||s.options_term_structure!=null||s.options_implied_earnings_move!=null;
  const p20=s.hit_prob||0;
  // Require REAL options data to render. Non-US names are not options-enriched
  // (backend gates on country=="US"), so they get NO options card at all — never
  // a synthesized/mock spread. The ML move-probability lives in its own P20Card.
  if(!hasIV&&!hasPositioning) return null;

  const ivr=s.options_iv_rank;
  const iv=s.options_iv_current;
  const samples=s.options_iv_samples||0;
  // Theta-backed = real IV present AND enough samples for a reliable IV rank
  // (backend MIN_IV_SAMPLES_FOR_RANK=20). Only then is an "edge" claim legit.
  // Non-US names are not options-enriched (backend gates on country=="US"), so
  // iv is null and any synthesized spread/EV here is illustrative, NOT a tradable edge.
  const thetaBacked = iv!=null && samples>=20;
  const ivrColor=ivr==null?T.textMuted:ivr<=30?T.green:ivr<=60?T.amber:T.red;
  const ivrLabel=ivr==null?"Not enough data":ivr<=25?"Cheap premium":ivr<=40?"Normal":ivr<=60?"Elevated":"Rich — options expensive";
  const p20pct=p20*100;

  const p5close  = Math.min(p20 * 3.41, 0.80);
  const p10close = Math.min(p20 * 2.29, 0.65);
  const p15close = Math.min(p20 * 1.49, 0.50);

  const optionsSp = s.options_spread;
  const isLive = optionsSp != null;

  const roundStrike = (v:number):number => {
    const inc = s.price>=50?5:s.price>=10?2.5:1;
    return Math.round(v/inc)*inc;
  };

  // Synthesize estimated spread when Massive doesn't provide one
  const sp = optionsSp ?? (()=>{
    const spot = s.price;
    if(spot<=0 || p20<=0 || iv==null) return null;  // never invent a spread without real IV
    const long_strike = roundStrike(spot);
    const short_strike = roundStrike(spot*1.10);
    if(short_strike <= long_strike) return null;
    const width = short_strike - long_strike;
    const ivAnn = iv ?? 0.30;
    const ivFactor = Math.min(0.50, Math.max(0.15, ivAnn * 0.65));
    const net_debit = Math.round(width * ivFactor * 100) / 100;
    const max_gain = (width - net_debit) * 100;
    const max_loss = net_debit * 100;
    const break_even_price = long_strike + net_debit;
    const break_even_move_pct = spot > 0 ? ((break_even_price - spot) / spot) * 100 : 0;
    const risk_reward = max_loss > 0 ? max_gain / max_loss : 0;
    const exp = new Date(); exp.setDate(exp.getDate() + 30);
    while(exp.getDay() !== 5) exp.setDate(exp.getDate() + 1);
    const expStr = exp.toISOString().slice(0,10);
    return {
      strategy:"Bull Call Spread (estimated)", spot, expiration:expStr, dte:30,
      long_strike, short_strike, long_mid:net_debit*0.65, short_mid:net_debit*0.35,
      net_debit, max_gain_per_contract:max_gain, max_loss_per_contract:max_loss,
      break_even_price, break_even_move_pct, risk_reward,
      description:"Estimated from current price + IV. Verify with broker.",
    };
  })();

  function interpolateP(movePct:number):number{
    if(movePct<=0) return 0.85;
    const pts:[number,number][] = [[5,p5close],[10,p10close],[15,p15close],[20,p20]];
    if(movePct<=pts[0][0]) return Math.min(pts[0][1] + (pts[0][0]-movePct)*0.02, 0.90);
    if(movePct>=pts[pts.length-1][0]) return Math.max(pts[pts.length-1][1] - (movePct-pts[pts.length-1][0])*0.01, 0.01);
    for(let i=0;i<pts.length-1;i++){
      if(movePct>=pts[i][0]&&movePct<=pts[i+1][0]){
        const frac=(movePct-pts[i][0])/(pts[i+1][0]-pts[i][0]);
        return pts[i][1]+(pts[i+1][1]-pts[i][1])*frac;
      }
    }
    return p20;
  }

  const bePct = sp?.break_even_move_pct||0;
  const shortPct = sp ? ((sp.short_strike-sp.spot)/sp.spot*100) : 0;
  const pBreakeven = sp && p20>0 ? interpolateP(bePct) : 0;
  const pMaxProfit = sp && p20>0 ? interpolateP(shortPct) : 0;
  const ev = sp ? (pMaxProfit * sp.max_gain_per_contract - (1-pBreakeven) * sp.max_loss_per_contract) : 0;
  const evPositive = ev > 0;
  const evPerDollar = sp && sp.max_loss_per_contract > 0 ? ev / sp.max_loss_per_contract : 0;

  const showEdge = thetaBacked;   // only claim an edge when IV is real & rank reliable
  const assessment = !sp ? "NO DATA"
    : p20<=0 ? "NO MODEL"
    : !showEdge ? "EST. ONLY"
    : evPerDollar > 0.15 ? "★ STRONG EDGE"
    : evPerDollar > 0.05 ? "MODERATE EDGE"
    : evPerDollar > 0 ? "MARGINAL EDGE"
    : evPerDollar > -0.10 ? "SLIGHT NEGATIVE"
    : "NO EDGE";
  const assessColor = assessment==="EST. ONLY" ? T.textMuted
    : assessment.includes("STRONG") ? "var(--purple)"
    : assessment.includes("MODERATE") ? T.green
    : assessment.includes("MARGINAL") ? T.amber
    : T.red;
  const evColor = showEdge ? (evPositive?T.green:T.red) : T.textMuted;

  const metric=(label:string,value:string,sub?:string,color?:string)=>(
    <div>
      <div style={{fontSize:9,color:T.textMuted,fontFamily:T.mono,fontWeight:600,letterSpacing:"0.08em"}}>{label}</div>
      <div style={{fontSize:14,color:color||T.text,fontFamily:T.mono,fontWeight:700,marginTop:2}}>{value}</div>
      {sub&&<div style={{fontSize:9,color:T.textLight,fontFamily:T.mono,marginTop:1}}>{sub}</div>}
    </div>
  );

  return(
    <Card>
      <SH title="Options Intelligence" icon={<Zap size={12}/>}
        sub={sp ? (showEdge ? `${assessment} · EV ${ev>=0?"+":""}$${ev.toFixed(0)}/contract${!isLive?" · estimated":""}` : "rough estimate · no live options data") : "IV data only"}/>

      {/* IV strip */}
      <div style={{display:"grid",gridTemplateColumns:"repeat(4, 1fr)",gap:14,marginBottom:14,paddingBottom:14,borderBottom:`1px solid ${T.divider}`}}>
        {metric("IV RANK",ivr!=null?ivr.toFixed(0):"—",samples<20?`${samples}/20 samples`:ivrLabel,ivrColor)}
        {metric("CURRENT IV",iv!=null?`${(iv*100).toFixed(0)}%`:"—","ATM 30d annualized")}
        {metric("P20 (MODEL)",p20>0?`${p20pct.toFixed(0)}%`:"—",p20>=0.15?"D9-D10":p20>=0.08?"D7-D8":p20>=0.03?"D5-D6":"low signal",p20>=0.15?T.green:p20>=0.08?T.amber:T.textMuted)}
        {metric("ASSESSMENT",assessment.replace("★ ",""),sp?(showEdge?`EV/risk: ${evPerDollar>=0?"+":""}${(evPerDollar*100).toFixed(0)}%`:"no live IV — est. only"):"",assessColor)}
      </div>

      {/* Market positioning */}
      {(s.options_pc_ratio!=null||s.options_term_structure!=null||s.options_implied_earnings_move!=null)&&(
        <div style={{marginBottom:14,paddingBottom:14,borderBottom:`1px solid ${T.divider}`}}>
          <div style={{fontSize:9,color:T.textMuted,fontFamily:T.mono,fontWeight:600,letterSpacing:"0.08em",marginBottom:8}}>MARKET POSITIONING</div>
          <div style={{display:"grid",gridTemplateColumns:"repeat(3, 1fr)",gap:14}}>
            <div>
              <div style={{fontSize:10,color:T.textMuted,fontFamily:T.mono,fontWeight:600}}>P/C VOL RATIO</div>
              {s.options_pc_ratio!=null?(()=>{const pc=s.options_pc_ratio;const label=pc<0.5?"Heavy call buying":pc<1.0?"Mild bullish":pc<1.5?"Neutral/mild hedging":pc<2.5?"Elevated put buying":"Extreme fear";const color=pc<0.5?T.green:pc<1.5?T.textMuted:pc<2.5?T.amber:T.red;return(<><div style={{fontSize:16,color,fontFamily:T.mono,fontWeight:700,marginTop:2}}>{pc.toFixed(2)}</div><div style={{fontSize:9,color:T.textLight,fontFamily:T.mono,marginTop:1}}>{label}</div></>);})():(<div style={{fontSize:16,color:T.textLight,fontFamily:T.mono,marginTop:2}}>—</div>)}
            </div>
            <div>
              <div style={{fontSize:10,color:T.textMuted,fontFamily:T.mono,fontWeight:600}}>IV TERM STRUCTURE</div>
              {(s.options_iv_30d!=null||s.options_iv_60d!=null||s.options_iv_90d!=null)?(()=>{const ts=s.options_term_structure;const tsLabel=ts==="backwardation"?"⚠ Near-term event priced":ts==="contango"?"✓ Normal calm market":ts==="flat"?"→ Flat curve":"—";const tsColor=ts==="backwardation"?T.amber:ts==="contango"?T.green:T.textMuted;const iv30=s.options_iv_30d,iv60=s.options_iv_60d,iv90=s.options_iv_90d;return(<><div style={{display:"flex",alignItems:"baseline",gap:6,marginTop:2,fontFamily:T.mono}}><span style={{fontSize:12,fontWeight:700,color:T.text}}>{iv30!=null?`${(iv30*100).toFixed(0)}%`:"—"}</span><span style={{fontSize:9,color:T.textLight}}>→</span><span style={{fontSize:12,fontWeight:700,color:T.text}}>{iv60!=null?`${(iv60*100).toFixed(0)}%`:"—"}</span><span style={{fontSize:9,color:T.textLight}}>→</span><span style={{fontSize:12,fontWeight:700,color:T.text}}>{iv90!=null?`${(iv90*100).toFixed(0)}%`:"—"}</span></div><div style={{fontSize:9,color:tsColor,fontFamily:T.mono,marginTop:2,fontWeight:600}}>{tsLabel}</div><div style={{fontSize:8,color:T.textLight,fontFamily:T.mono,marginTop:1}}>30d · 60d · 90d</div></>);})():(<div style={{fontSize:16,color:T.textLight,fontFamily:T.mono,marginTop:2}}>—</div>)}
            </div>
            <div>
              <div style={{fontSize:10,color:T.textMuted,fontFamily:T.mono,fontWeight:600}}>IMPLIED EARNINGS MOVE</div>
              {s.options_implied_earnings_move?(()=>{const iem=s.options_implied_earnings_move;return(<><div style={{fontSize:16,color:T.text,fontFamily:T.mono,fontWeight:700,marginTop:2}}>±{iem.pct.toFixed(1)}%</div><div style={{fontSize:9,color:T.textLight,fontFamily:T.mono,marginTop:1}}>ATM straddle ${iem.straddle.toFixed(2)} · {iem.earnings_date}</div></>);})():(<><div style={{fontSize:16,color:T.textLight,fontFamily:T.mono,marginTop:2}}>—</div><div style={{fontSize:9,color:T.textLight,fontFamily:T.mono,marginTop:1}}>No earnings in next 60d</div></>)}
            </div>
          </div>
        </div>
      )}

      {/* ═══ SPREAD PROPOSAL ═══ */}
      {sp&&p20>0&&(<>
        {!isLive&&(
          <div style={{padding:"6px 10px",borderRadius:4,background:T.amberLight,border:"1px solid var(--amber)",fontSize:10,fontFamily:T.mono,color:T.amber,fontWeight:600,marginBottom:10,display:"inline-block"}}>
            ⚠ ESTIMATED SPREAD — {showEdge ? "verify strikes and premiums with your broker before trading" : "IV rank unreliable (<20 samples) — spread estimated from live IV; verify with your broker, not yet a tradable edge"}
          </div>
        )}
        <div style={{fontSize:9,color:T.textMuted,fontFamily:T.mono,fontWeight:600,letterSpacing:"0.08em",marginBottom:8}}>
          BULL CALL SPREAD {isLive?"(LIVE CHAIN)":"(ESTIMATED)"}
        </div>
        <div style={{display:"grid",gridTemplateColumns:"repeat(6, 1fr)",gap:14,marginBottom:14,paddingBottom:14,borderBottom:`1px solid ${T.divider}`}}>
          {metric("SPOT",`$${sp.spot.toFixed(2)}`)}
          {metric("LONG CALL",`$${sp.long_strike.toFixed(0)}`,isLive?`mid $${sp.long_mid.toFixed(2)}`:"ATM est.",T.green)}
          {metric("SHORT CALL",`$${sp.short_strike.toFixed(0)}`,isLive?`mid $${sp.short_mid.toFixed(2)}`:"~+10% est.",T.red)}
          {metric("EXPIRATION",sp.expiration,`~${sp.dte}d to expiry`)}
          {metric("NET DEBIT",`$${sp.net_debit.toFixed(2)}`,isLive?"per share (×100)":"estimated from IV")}
          {metric("BREAK-EVEN",`$${sp.break_even_price.toFixed(2)}`,`+${bePct.toFixed(1)}% from spot`)}
        </div>
        <div style={{display:"grid",gridTemplateColumns:"repeat(5, 1fr)",gap:14,marginBottom:14,paddingBottom:14,borderBottom:`1px solid ${T.divider}`}}>
          {metric("MAX GAIN",`+$${sp.max_gain_per_contract.toFixed(0)}`,"stock ≥ short strike",T.green)}
          {metric("MAX LOSS",`-$${sp.max_loss_per_contract.toFixed(0)}`,"stock ≤ long strike",T.red)}
          {metric("RISK / REWARD",`${sp.risk_reward.toFixed(2)} : 1`,sp.risk_reward>=1.5?"favorable":sp.risk_reward>=1.0?"even":"unfavorable",sp.risk_reward>=1.5?T.green:sp.risk_reward>=1.0?T.amber:T.red)}
          {metric("P(BREAKEVEN)",`~${Math.round(pBreakeven*100)}%`,`close ≥ +${bePct.toFixed(0)}%`,pBreakeven>=0.50?T.green:pBreakeven>=0.35?T.amber:T.red)}
          {metric("P(MAX PROFIT)",`~${Math.round(pMaxProfit*100)}%`,`close ≥ +${shortPct.toFixed(0)}%`,pMaxProfit>=0.25?T.green:pMaxProfit>=0.15?T.amber:T.red)}
        </div>

        {/* EV block */}
        <div style={{padding:"12px 14px",borderRadius:6,background:showEdge?(evPositive?"var(--green-light)":"var(--red-light)"):"var(--bg-elevated)",border:`1px solid ${showEdge?(evPositive?"var(--green-border)":"var(--red)"):T.divider}`,marginBottom:14}}>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:8}}>
            <div>
              <div style={{fontWeight:600,color:evColor,fontSize:9,fontFamily:T.mono,letterSpacing:"0.08em",marginBottom:4}}>EXPECTED VALUE{!showEdge?" (ILLUSTRATIVE)":!isLive?" (ESTIMATED)":""}</div>
              <div style={{fontSize:22,fontWeight:700,fontFamily:T.mono,color:evColor}}>
                {ev>=0?"+":""}${ev.toFixed(0)} <span style={{fontSize:11,fontWeight:500,color:T.textMuted}}>/ contract</span>
              </div>
            </div>
            <div style={{textAlign:"right"}}>
              <div style={{fontSize:9,color:T.textMuted,fontFamily:T.mono,fontWeight:600,marginBottom:2}}>EV / RISK</div>
              <div style={{fontSize:16,fontWeight:700,fontFamily:T.mono,color:evColor}}>
                {evPerDollar>=0?"+":""}{(evPerDollar*100).toFixed(0)}%
              </div>
            </div>
          </div>
          <div style={{fontSize:10,fontFamily:T.mono,color:T.textMuted,lineHeight:1.6}}>
            {Math.round(pMaxProfit*100)}% × ${sp.max_gain_per_contract.toFixed(0)} − {Math.round((1-pBreakeven)*100)}% × ${sp.max_loss_per_contract.toFixed(0)} = <b style={{color:evColor}}>{ev>=0?"+":""}${ev.toFixed(0)}</b>
            <span style={{fontSize:9,color:T.textLight,display:"block",marginTop:2}}>Note: EV calculation is an approximation using binary outcomes. The remaining {100 - Math.round(pMaxProfit*100) - Math.round((1-pBreakeven)*100)}% probability represents the area of partial gain or loss between strikes.</span>
          </div>
          <div style={{display:"flex",gap:8,marginTop:10,flexWrap:"wrap"}}>
            {[
              {label:"P(BE) > 50%", ok:pBreakeven>=0.50},
              {label:"P(BE) > 60%", ok:pBreakeven>=0.60},
              {label:"EV/risk > +10%", ok:evPerDollar>0.10},
              {label:"IVR ≤ 30", ok:ivr!=null&&ivr<=30},
            ].map((t,i)=>(
              <div key={i} style={{
                padding:"3px 8px",borderRadius:4,fontSize:9,fontFamily:T.mono,fontWeight:600,
                background:t.ok?"var(--green-light)":"var(--bg-elevated)",color:t.ok?T.green:T.textLight,
                border:`1px solid ${t.ok?"var(--green-border)":T.divider}`,
              }}>{t.ok?"✓":"○"} {t.label}</div>
            ))}
          </div>
        </div>

        {/* IBKR template for live spreads */}
        {isLive&&(
          <div style={{padding:"10px 12px",borderRadius:5,background:T.greenLight,border:`1px solid ${T.greenBorder}`,fontSize:11,fontFamily:T.mono,color:T.text,lineHeight:1.6,marginBottom:10}}>
            <div style={{fontWeight:600,color:T.green,fontSize:9,letterSpacing:"0.08em",marginBottom:4}}>IBKR EXECUTION</div>
            <div>Order type: <b>Debit Spread (Bull Call)</b></div>
            <div>Leg 1: BUY {s.symbol} {sp.expiration.replace(/-/g,"")} {sp.long_strike} C @ LMT ≤ ${sp.long_mid.toFixed(2)}</div>
            <div>Leg 2: SELL {s.symbol} {sp.expiration.replace(/-/g,"")} {sp.short_strike} C @ LMT ≥ ${sp.short_mid.toFixed(2)}</div>
            <div>Net: pay no more than <b>${sp.net_debit.toFixed(2)}/spread</b> (×100 = ${(sp.net_debit*100).toFixed(0)}/contract)</div>
          </div>
        )}

        {/* Broker lookup for estimated spreads */}
        {!isLive&&(
          <div style={{padding:"10px 12px",borderRadius:5,background:"var(--purple-light)",border:"1px solid var(--purple)",fontSize:11,fontFamily:T.mono,color:T.text,lineHeight:1.6,marginBottom:10}}>
            <div style={{fontWeight:600,color:"var(--purple)",fontSize:9,letterSpacing:"0.08em",marginBottom:4}}>VERIFY WITH BROKER</div>
            Look up: <b>{s.symbol} {sp.long_strike}/{sp.short_strike} call spread</b>, ~30 DTE.
            Actual premiums will differ — the EV above uses IV-estimated costs.
            If real net debit is lower, EV improves; if higher, EV worsens.
          </div>
        )}

        {/* Sizing */}
        <div style={{padding:"10px 12px",borderRadius:5,background:T.amberLight,border:"1px solid var(--amber)",fontSize:11,fontFamily:T.sans,color:T.text,lineHeight:1.55,marginBottom:8}}>
          <div style={{fontWeight:600,color:T.amber,fontFamily:T.mono,fontSize:9,letterSpacing:"0.08em",marginBottom:4}}>⚠ SIZING</div>
          Speculative overlay: <b>1-2% of portfolio per spread, max 5% total</b>. Probabilities are model estimates (AUC 0.78). Spreads can lose 100% of debit. {!evPositive && <><b style={{color:T.red}}>EV is negative — no statistical edge at current premiums.</b></>}
        </div>

        <div style={{marginTop: 10, display:"flex", justifyContent:"flex-end"}}>
          <AddOptionToPortfolio stock={s} sp={sp} ev={ev} iv={iv||0} />
        </div>
      </>)}

      {/* No spread possible (no P20 or can't construct) */}
      {(!sp || p20<=0)&&hasIV&&(
        <div style={{padding:"8px 12px",borderRadius:5,background:"var(--bg)",border:`1px solid ${T.divider}`,fontSize:10,fontFamily:T.mono,color:T.textMuted,marginTop:8}}>
          {p20<=0
            ? "ML model probability not available — spread EV cannot be calculated. IV data shown above for reference."
            : "Spread estimation requires stock price > $0 and P20 > 0%."}
        </div>
      )}

      <div style={{fontSize:9,color:T.textLight,fontFamily:T.mono,marginTop:8,lineHeight:1.4}}>
        Probabilities from time_model_v2 (OOS AUC 0.7836), calibrated against 21,650 OOS samples.
        {isLive?" IV/Greeks from Massive (ORATS-sourced).":" Spread estimated from price + IV; verify with broker."}
        {" "}EV = P(max profit) × gain − P(miss) × loss. Not investment advice.
      </div>
    </Card>
  );
}

// Keep old name as alias so the existing render block doesn't break
const MassiveSpreadCard=MassiveOptionsCard;

// ═══════════════════════════════════════════════════════════════════════
// OpusStrategyCard — Opus 4.8's chosen option strategy for a D9/D10 ML pick.
// Designed nightly on the gateway PC from REAL IBKR chains (greeks + IV-rank)
// against the model view; pushed to GCS scans/options_strategies.json. Only
// renders for covered symbols with a real structure (never mock / never "skip").
// ═══════════════════════════════════════════════════════════════════════
function OpusStrategyCard({st,symbol,price}:{st:OpusStrategy;symbol:string;price:number}){
  const conv=st.conviction??0;
  const convColor=conv>=8?T.green:conv>=6?T.amber:T.textMuted;
  // Prefer the fill-aware figures (cross the bid/ask) over Opus's mid-based ones.
  const net=st.net_fill??st.net;
  const maxG=st.max_gain_fill??st.max_gain;
  const maxL=st.max_loss_fill??st.max_loss;
  const be=st.breakeven_fill??st.breakeven;
  const isCredit=(net??0)>0||(st.net_fill==null&&(st.net_type==="credit"||((st.net??0)>0)));
  const ev=st.ev;
  const evColor=ev==null?T.textMuted:ev>=0?T.green:T.red;
  const legs=Array.isArray(st.legs)?st.legs:[];
  const m=(label:string,value:string,sub?:string,color?:string)=>(
    <div>
      <div style={{fontSize:9,color:T.textMuted,fontFamily:T.mono,fontWeight:600,letterSpacing:"0.08em"}}>{label}</div>
      <div style={{fontSize:14,color:color||T.text,fontFamily:T.mono,fontWeight:700,marginTop:2}}>{value}</div>
      {sub&&<div style={{fontSize:9,color:T.textLight,fontFamily:T.mono,marginTop:1}}>{sub}</div>}
    </div>
  );
  const fmt=(v?:number,dp=2)=>v==null?"—":`$${v.toFixed(dp)}`;
  return(
    <Card style={{borderColor:"var(--purple)"}}>
      <SH title="Opus Strategy" icon={<Sparkles size={12}/>}
        sub={`${st.structure.toUpperCase()}${st.decile?` · D${st.decile} pick`:""}${st.iv_rank!=null?` · IV-rank ${st.iv_rank.toFixed(0)}`:""}`}/>
      {st.thesis&&(
        <div style={{fontSize:12,fontFamily:T.sans,color:T.text,lineHeight:1.55,marginBottom:14,paddingBottom:14,borderBottom:`1px solid ${T.divider}`}}>
          {st.thesis}
        </div>
      )}

      {/* headline metrics — fill-aware (entry crosses the bid/ask) */}
      <div style={{display:"grid",gridTemplateColumns:"repeat(6, 1fr)",gap:14,marginBottom:14,paddingBottom:14,borderBottom:`1px solid ${T.divider}`}}>
        {m("EV / CONTRACT",ev==null?"—":`${ev>=0?"+":"−"}$${Math.abs(ev).toFixed(0)}`,st.pop!=null?`P(win) ${(st.pop*100).toFixed(0)}%`:"fill-aware",evColor)}
        {m("NET",net==null?"—":`${isCredit?"+":"-"}$${Math.abs(net).toFixed(2)}`,isCredit?"credit / share":"debit / share",isCredit?T.green:T.text)}
        {m("MAX GAIN",maxG==null?"—":`+${fmt(maxG)}`,"per share",T.green)}
        {m("MAX LOSS",maxL==null?"—":`-${fmt(Math.abs(maxL))}`,"per share",T.red)}
        {m("BREAK-EVEN",fmt(be),st.target_move_pct!=null?`target +${st.target_move_pct.toFixed(1)}%`:undefined)}
        {m("CONVICTION",`${conv}/10`,"structure fit",convColor)}
      </div>
      {ev!=null&&(
        <div style={{fontSize:9,color:T.textLight,fontFamily:T.mono,marginBottom:14,marginTop:-6,lineHeight:1.4}}>
          EV crosses the bid/ask (worst-case fill) · {st.ev_method||""} · ex-ante estimate, not realized
        </div>
      )}

      {/* legs */}
      {legs.length>0&&(
        <div style={{marginBottom:14,paddingBottom:14,borderBottom:`1px solid ${T.divider}`}}>
          <div style={{fontSize:9,color:T.textMuted,fontFamily:T.mono,fontWeight:600,letterSpacing:"0.08em",marginBottom:8}}>
            LEGS{st.expiration?` · ${st.expiration}`:""}
          </div>
          <div style={{display:"flex",flexDirection:"column",gap:6}}>
            {legs.map((l,i)=>{
              const buy=(l.action||"").toUpperCase()==="BUY";
              return(
                <div key={i} style={{display:"flex",alignItems:"center",gap:10,fontFamily:T.mono,fontSize:12}}>
                  <span style={{padding:"2px 7px",borderRadius:4,fontSize:9,fontWeight:700,letterSpacing:"0.05em",
                    background:buy?T.greenLight:T.redLight,color:buy?T.green:T.red,border:`1px solid ${buy?T.greenBorder:"var(--red)"}`}}>
                    {buy?"BUY":"SELL"}
                  </span>
                  <span style={{fontWeight:700,color:T.text}}>{l.qty??1}×</span>
                  <span style={{color:T.text}}>{symbol} {l.strike!=null?`$${l.strike}`:""} {l.right==="P"?"PUT":l.right==="C"?"CALL":(l.right||"")}</span>
                  {l.est_price!=null&&<span style={{color:T.textMuted}}>@ ~${l.est_price.toFixed(2)}</span>}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* rationale */}
      {st.rationale&&(
        <div style={{padding:"10px 12px",borderRadius:5,background:"var(--purple-light)",border:"1px solid var(--purple)",fontSize:11,fontFamily:T.sans,color:T.text,lineHeight:1.55,marginBottom:8}}>
          <div style={{fontWeight:600,color:"var(--purple)",fontFamily:T.mono,fontSize:9,letterSpacing:"0.08em",marginBottom:4}}>WHY THIS STRUCTURE</div>
          {st.rationale}
        </div>
      )}
      {st.risk_note&&(
        <div style={{padding:"10px 12px",borderRadius:5,background:T.amberLight,border:"1px solid var(--amber)",fontSize:11,fontFamily:T.sans,color:T.text,lineHeight:1.55,marginBottom:8}}>
          <div style={{fontWeight:600,color:T.amber,fontFamily:T.mono,fontSize:9,letterSpacing:"0.08em",marginBottom:4}}>⚠ RISK</div>
          {st.risk_note}
        </div>
      )}

      <div style={{fontSize:9,color:T.textLight,fontFamily:T.mono,marginTop:8,lineHeight:1.4}}>
        Designed by Opus 4.8 nightly from real IBKR option chains (greeks + IV-rank) against the v4 ML view.
        Prices are mid-of-book estimates — verify strikes/premiums with your broker. Not investment advice.
      </div>
    </Card>
  );
}

// ── PriceCompositeChart — dual-line price + composite over scan history ────────
function PriceCompositeChart({symbol, mode}:{symbol:string, mode?:string}){
  const[rows,setRows]=useState<any[][]>([]);
  const[loading,setLoading]=useState(true);
  const[err,setErr]=useState<string|null>(null);
  useEffect(()=>{
    fetch(`/api/stock/${encodeURIComponent(symbol)}/history`)
      .then(r=>{if(!r.ok)throw new Error(`HTTP ${r.status}`);return r.json();})
      .then(d=>{setRows(Array.isArray(d?.rows)?d.rows:[]);setLoading(false);})
      .catch(e=>{setErr(e.message||"Failed");setLoading(false);});
  },[symbol]);

  // Local state to toggle lines on/off
  const [active, setActive] = useState({
    mom: mode === "momentum" || !mode,
    fa: mode === "fallen_angel",
    cus: mode === "compounder_us",
    cgl: mode === "compounder_global"
  });

  // Sync toggles when the active tab (mode) changes
  useEffect(() => {
    setActive({
      mom: mode === "momentum" || !mode,
      fa: mode === "fallen_angel",
      cus: mode === "compounder_us",
      cgl: mode === "compounder_global"
    });
  }, [mode]);
  if(loading) return<Card><SH title="Track Record (All Models)" icon={<TrendingUp size={12}/>}/><div style={{padding:30,textAlign:"center",color:T.textLight,fontSize:11,fontFamily:T.mono}}>Loading history...</div></Card>;
  if(err) return<Card><SH title="Track Record (All Models)" icon={<TrendingUp size={12}/>}/><div style={{padding:30,textAlign:"center",color:T.textLight,fontSize:11,fontFamily:T.mono}}>{err}</div></Card>;
  if(rows.length<2) return<Card><SH title="Track Record (All Models)" icon={<TrendingUp size={12}/>}/><div style={{padding:30,textAlign:"center",color:T.textLight,fontSize:11,fontFamily:T.mono}}>Only {rows.length} scan{rows.length===1?"":"s"} recorded so far. Chart appears once 2+ scans have tracked this stock.</div></Card>;

  const W=720,H=240,PL=65,PR=65,PT=20,PB=30;
  
  const prices=rows.map(r=>r[1]||0);
  const mom=rows.map(r=>r[2]||0);
  const fa=rows.map(r=>r[3]||0);
  const cus=rows.map(r=>r[4]||0);
  const cgl=rows.map(r=>r[5]||0);

  const pMn=Math.min(...prices)*0.95,pMx=Math.max(...prices)*1.05;
  const pRng=(pMx-pMn)||1;

  const allComps = [...mom, ...fa, ...cus, ...cgl].filter(v=>v>0);
  const cMn = allComps.length > 0 ? Math.max(0, Math.min(...allComps) - 0.1) : 0;
  const cMx = allComps.length > 0 ? Math.min(1.0, Math.max(...allComps) + 0.1) : 1;
  const cRng=(cMx-cMn)||1;

  const xAt=(i:number)=>PL+((i)/(rows.length-1||1))*(W-PL-PR);
  const yPrice=(v:number)=>PT+(1-((v-pMn)/pRng))*(H-PT-PB);
  const yComp =(v:number)=>PT+(1-((v-cMn)/cRng))*(H-PT-PB);

  const buildPath = (data:number[], yFn:(v:number)=>number) => {
    const points = data.map((v,i)=>({v,i})).filter(p=>p.v>0);
    if(points.length===0) return "";
    return points.map((p,idx)=>`${idx===0?"M":"L"}${xAt(p.i).toFixed(1)} ${yFn(p.v).toFixed(1)}`).join(" ");
  };

  const pricePath=rows.map((r,i)=>`${i===0?"M":"L"}${xAt(i).toFixed(1)} ${yPrice(prices[i]).toFixed(1)}`).join(" ");
  const areaPath = `${pricePath} L${xAt(rows.length-1)} ${H-PB} L${xAt(0)} ${H-PB} Z`;

  const momPath = buildPath(mom, yComp);
  const faPath = buildPath(fa, yComp);
  const cusPath = buildPath(cus, yComp);
  const cglPath = buildPath(cgl, yComp);

  const lastValidIndex = (data:number[]) => {
    for(let i=data.length-1; i>=0; i--) if(data[i]>0) return i;
    return -1;
  };
  const iMom = lastValidIndex(mom);
  const iFa = lastValidIndex(fa);
  const iCus = lastValidIndex(cus);
  const iCgl = lastValidIndex(cgl);

  const last=rows[rows.length-1],first=rows[0];
  const pChg=first[1]>0?((last[1]-first[1])/first[1])*100:0;
  
  const fmtDate = (d: string) => {
    const parts = d.split('-');
    if(parts.length !== 3) return d.slice(5);
    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    // include the day — multiple scans in one month must not all read "May '26"
    return `${months[parseInt(parts[1], 10)-1]} ${parseInt(parts[2], 10)} '${parts[0].slice(-2)}`;
  };
  const tickIdxs=rows.length<=6?rows.map((_,i)=>i):[0,Math.floor(rows.length*0.2),Math.floor(rows.length*0.4),Math.floor(rows.length*0.6),Math.floor(rows.length*0.8),rows.length-1];

  return(
    <Card>
      <SH title="Track Record (All Models)" icon={<TrendingUp size={12}/>}
        sub={`${rows.length} scans · Price ${pChg>=0?"+":""}${pChg.toFixed(1)}%`}/>
      <div style={{overflow:"hidden", marginTop: 10, background:"transparent", padding: "10px 0"}}>
        <svg viewBox={`0 0 ${W} ${H}`} style={{width:"100%",height:"auto",display:"block"}} preserveAspectRatio="none">
          <defs>
            <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={T.green} stopOpacity={0.2} />
              <stop offset="100%" stopColor={T.green} stopOpacity={0.0} />
            </linearGradient>
          </defs>
          
          {[0,0.25,0.5,0.75,1].map(t=>(
            <line key={t} x1={PL} x2={W-PR} y1={PT+t*(H-PT-PB)} y2={PT+t*(H-PT-PB)}
              stroke={T.divider} strokeWidth={1} strokeDasharray={t===0||t===1?"none":"4 4"}/>
          ))}

          <path d={areaPath} fill="url(#priceGrad)" />
          <path d={pricePath} fill="none" stroke={T.green} strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round"/>
          
          {iMom >= 0 && <path d={momPath} fill="none" stroke="var(--purple)" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" strokeDasharray="6 4" opacity={active.mom?1:0.1} />}
          {iFa >= 0 && <path d={faPath} fill="none" stroke="var(--amber)" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" strokeDasharray="6 4" opacity={active.fa?1:0.1} />}
          {iCus >= 0 && <path d={cusPath} fill="none" stroke="var(--blue)" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" strokeDasharray="6 4" opacity={active.cus?1:0.1} />}
          {iCgl >= 0 && <path d={cglPath} fill="none" stroke="#06b6d4" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" strokeDasharray="6 4" opacity={active.cgl?1:0.1} />}

          <circle cx={xAt(rows.length-1)} cy={yPrice(last[1])} r={4} fill={T.green} stroke="var(--bg-surface)" strokeWidth={1.5} />
          {iMom >= 0 && <circle cx={xAt(iMom)} cy={yComp(mom[iMom])} r={3} fill="var(--purple)" opacity={active.mom?1:0.1} />}
          {iFa >= 0 && <circle cx={xAt(iFa)} cy={yComp(fa[iFa])} r={3} fill="var(--amber)" opacity={active.fa?1:0.1} />}
          {iCus >= 0 && <circle cx={xAt(iCus)} cy={yComp(cus[iCus])} r={3} fill="var(--blue)" opacity={active.cus?1:0.1} />}
          {iCgl >= 0 && <circle cx={xAt(iCgl)} cy={yComp(cgl[iCgl])} r={3} fill="#06b6d4" opacity={active.cgl?1:0.1} />}

          <text x={PL-8} y={yPrice(pMx)+3} textAnchor="end" fontSize={10} fontFamily={T.mono} fontWeight={600} fill={T.green}>${pMx.toFixed(2)}</text>
          <text x={PL-8} y={yPrice(pMn)+3} textAnchor="end" fontSize={10} fontFamily={T.mono} fontWeight={600} fill={T.green}>${pMn.toFixed(2)}</text>
          
          {allComps.length > 0 && <>
            <text x={W-PR+8} y={yComp(cMx)+3} textAnchor="start" fontSize={10} fontFamily={T.mono} fontWeight={600} fill={T.textMuted}>{cMx.toFixed(2)}</text>
            <text x={W-PR+8} y={yComp(cMn)+3} textAnchor="start" fontSize={10} fontFamily={T.mono} fontWeight={600} fill={T.textMuted}>{cMn.toFixed(2)}</text>
          </>}
          
          {tickIdxs.map(i=>(
            <text key={i} x={xAt(i)} y={H-8} textAnchor="middle" fontSize={9} fontFamily={T.mono} fill={T.textLight}>
              {fmtDate(rows[i][0])}
            </text>
          ))}
        </svg>
      </div>

      <div style={{display:"flex",justifyContent:"center",flexWrap:"wrap",gap:"12px 24px",marginTop:14,fontSize:10,fontFamily:T.mono,color:T.text,userSelect:"none"}}>
        <div style={{display:"inline-flex",alignItems:"center",gap:6,fontWeight:600}}>
          <span style={{width:12,height:12,borderRadius:3,background:T.green}}/> Price (Left)
        </div>
        {iMom >= 0 && <div onClick={()=>setActive(p=>({...p, mom:!p.mom}))} style={{display:"inline-flex",alignItems:"center",gap:6,opacity:active.mom?1:0.4,cursor:"pointer",transition:"opacity 0.2s"}}>
          <span style={{width:16,height:2,background:"var(--purple)",backgroundImage:`repeating-linear-gradient(90deg,var(--purple) 0 4px,transparent 4px 6px)`}}/> Momentum (Right)
        </div>}
        {iFa >= 0 && <div onClick={()=>setActive(p=>({...p, fa:!p.fa}))} style={{display:"inline-flex",alignItems:"center",gap:6,opacity:active.fa?1:0.4,cursor:"pointer",transition:"opacity 0.2s"}}>
          <span style={{width:16,height:2,background:"var(--amber)",backgroundImage:`repeating-linear-gradient(90deg,var(--amber) 0 4px,transparent 4px 6px)`}}/> Fallen Angel (Right)
        </div>}
        {iCus >= 0 && <div onClick={()=>setActive(p=>({...p, cus:!p.cus}))} style={{display:"inline-flex",alignItems:"center",gap:6,opacity:active.cus?1:0.4,cursor:"pointer",transition:"opacity 0.2s"}}>
          <span style={{width:16,height:2,background:"var(--blue)",backgroundImage:`repeating-linear-gradient(90deg,var(--blue) 0 4px,transparent 4px 6px)`}}/> CMP-US (Right)
        </div>}
        {iCgl >= 0 && <div onClick={()=>setActive(p=>({...p, cgl:!p.cgl}))} style={{display:"inline-flex",alignItems:"center",gap:6,opacity:active.cgl?1:0.4,cursor:"pointer",transition:"opacity 0.2s"}}>
          <span style={{width:16,height:2,background:"#06b6d4",backgroundImage:`repeating-linear-gradient(90deg,#06b6d4 0 4px,transparent 4px 6px)`}}/> CMP-Global (Right)
        </div>}
      </div>
    </Card>
  );
}

// v8 TargetBar: shows price + analyst consensus + Buffett 5y fair value.
// 2026-05-06: simplified after May 2026 Buffett rewrite. Previously a third
// "Combined" dot blended BVPS+analyst, but the backend retired that blend —
// intrinsic_avg now equals buffett_fair_value exactly, so the Combined and
// Fair Value dots showed the same number. Combined removed.
// DCF and Buffett earnings-compounding intrinsic remain on the Stock dict
// for diagnostics but no longer appear here. Keeping the chart simple
// matches the new five-factor brief.
function TargetBar({price,target,bvps,currency}:{price:number;target:number;bvps:number;currency?:string}){
  const vs=[price,target,bvps].filter(v=>v>0);
  if(vs.length<2)return null;
  const mn=Math.min(...vs)*0.85,mx=Math.max(...vs)*1.10,rng=mx-mn||1,pos=(v:number)=>((v-mn)/rng*100);
  const c$=(v:number)=>fmtPrice(v,currency);
  // 2026-05-06: simplified after May 2026 Buffett rewrite. The bvps prop
  // carries the Buffett 5y fair value (legacy name kept for diff stability).
  // Previously a separate "Combined" dot blended BVPS+analyst, but the
  // backend retired that blend — intrinsic_avg now equals buffett_fair_value
  // exactly, so two dots showed the same number. Combined removed.
  const upside=bvps>0?((bvps-price)/price*100):0;
  const upColor=upside>15?T.green:upside>0?"#5a9e7a":upside>-15?T.amber:T.red;

  return(
    <div style={{marginTop:12,padding:"12px 0"}}>
      <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:28}}>
        <div style={{fontSize:10,color:T.textMuted,fontFamily:T.mono,fontWeight:600}}>PRICE vs INTRINSIC</div>
        {bvps>0&&<div style={{fontSize:11,fontFamily:T.mono,fontWeight:700,color:upColor}}>
          {upside>=0?"+":""}{upside.toFixed(0)}% upside
        </div>}
      </div>

      <div style={{position:"relative",height:36,background:T.divider,borderRadius:6}}>
        {/* Highlight from price to fair value */}
        {bvps>price&&<div style={{position:"absolute",left:`${pos(price)}%`,top:0,bottom:0,width:`${pos(bvps)-pos(price)}%`,background:`var(--green)12`,borderRadius:4}}/>}

        {/* Current price line */}
        <div style={{position:"absolute",left:`${pos(price)}%`,top:0,bottom:0,width:2,background:T.text,zIndex:2}}>
          <div style={{position:"absolute",top:-22,left:"50%",transform:"translateX(-50%)",fontSize:11,color:T.text,fontFamily:T.mono,fontWeight:700,background:T.card,padding:"0 4px",whiteSpace:"nowrap"}}>{c$(price)}</div>
        </div>

        {/* Analyst consensus */}
        {target>0&&<div style={{position:"absolute",left:`${pos(target)}%`,top:18,width:8,height:8,borderRadius:"50%",background:T.amber,transform:"translateX(-4px)"}}>
          <div style={{position:"absolute",top:-16,left:"50%",transform:"translateX(-50%)",fontSize:9,color:T.amber,fontFamily:T.mono,fontWeight:700,whiteSpace:"nowrap"}}>{c$(target)}</div>
          <div style={{position:"absolute",bottom:-16,left:"50%",transform:"translateX(-50%)",fontSize:9,color:T.amber,fontFamily:T.mono,fontWeight:600,whiteSpace:"nowrap"}}>Analyst</div>
        </div>}

        {/* Buffett 5y fair value — the figure that drives Value scoring */}
        {bvps>0&&<div style={{position:"absolute",left:`${pos(bvps)}%`,top:6,width:10,height:10,borderRadius:"50%",background:T.green,transform:"translateX(-5px)",border:"2px solid white",boxShadow:"0 1px 3px rgba(0,0,0,0.2)"}}>
          <div style={{position:"absolute",top:-18,left:"50%",transform:"translateX(-50%)",fontSize:10,color:T.green,fontFamily:T.mono,fontWeight:700,whiteSpace:"nowrap"}}>{c$(bvps)}</div>
          <div style={{position:"absolute",bottom:-18,left:"50%",transform:"translateX(-50%)",fontSize:9,color:T.green,fontFamily:T.mono,fontWeight:600,whiteSpace:"nowrap"}}>Fair Value</div>
        </div>}
      </div>

      {/* Methodology key */}
      <div style={{marginTop:24,paddingTop:12,borderTop:`1px dashed ${T.divider}`,fontSize:9,color:T.textMuted,fontFamily:T.mono,lineHeight:1.6}}>
        <div style={{display:"flex",alignItems:"center",gap:6}}>
          <div style={{width:8,height:8,borderRadius:"50%",background:T.green,border:"2px solid white",boxShadow:"0 0 0 1px "+T.green}}/>
          <strong>Fair Value:</strong> Value 5y future price discounted at 10% hurdle (drives Value score)
        </div>
        <div style={{display:"flex",alignItems:"center",gap:6}}>
          <div style={{width:6,height:6,borderRadius:"50%",background:T.amber}}/>
          <strong>Analyst:</strong> Wall Street 12-month consensus
        </div>
      </div>
    </div>
  );
}

// ── ModeToggle: switches the dashboard between scoring views.
// v1.2 (May 2026): expanded from 2 modes (Momentum, Fallen Angel) to 4
// (+ Compounder US, Compounder Global). Stock data is computed for all
// modes at scan time; this re-points the radar/factor/signal/composite
// bindings. Compounder modes share the same v8 5-factor radar — the
// difference is gate membership (US exchange vs global, sector ex Fin/Ins/HC,
// 3-yr ROE + P/B + OpMargin delta scoring).
type ModeAvail = {momentum:boolean; fallen_angel:boolean; compounder_us:boolean; compounder_global:boolean};
function ModeToggle({mode,onChange,available}:{mode:string;onChange:(m:string)=>void;available:ModeAvail}){
  const opts=[
    {k:"momentum",         l:"Momentum"},
    {k:"fallen_angel",     l:"Fallen Angel"},
    {k:"compounder_us",    l:"CMP-US"},
    {k:"compounder_global",l:"CMP-Global"},
  ];
  return(
    <div style={{display:"inline-flex",border:`1px solid ${T.cardBorder}`,borderRadius:6,overflow:"hidden",background:"var(--bg-surface)"}}>
      {opts.map(o=>{
        const active=o.k===mode;
        const ok=(available as any)[o.k];
        return(
          <button key={o.k} onClick={()=>ok&&onChange(o.k)} disabled={!ok}
            style={{padding:"5px 10px",border:"none",cursor:ok?"pointer":"not-allowed",
              background:active?T.green:"transparent",color:active?"var(--bg-surface)":(ok?T.text:T.textLight),
              fontSize:10,fontFamily:T.mono,fontWeight:600,letterSpacing:"0.04em",
              borderRight:o.k!=="compounder_global"?`1px solid ${T.cardBorder}`:"none"}}>
            {o.l}{!ok&&" —"}
          </button>
        );
      })}
    </div>
  );
}

// ── BuffettBlock: 5-year projection summary (replaces BvpsBlock May 2026).
// Shows the method used (BVPS×ROE vs direct EPS CAGR vs analyst fallback),
// the assumptions, future price + fair value, and a flag when gate failed.
function BuffettBlock({s}:{s:StockData}){
  const c = s.currency==="EUR"?"€":s.currency==="GBP"?"£":"$";
  const evaluated = s.buffett_evaluated === true;
  const method = s.buffett_method || "";
  const isFallback = method === "fallback_analyst";

  if(!evaluated && !isFallback){
    // Neither Buffett nor analyst worked — render warning placeholder
    return (
      <div style={{padding:"10px 12px",borderRadius:6,background:T.amberLight,border:`1px solid var(--amber)`,marginTop:10}}>
        <div style={{fontSize:9,color:T.amber,fontFamily:T.mono,fontWeight:600,letterSpacing:"0.08em",marginBottom:4}}>VALUATION UNAVAILABLE</div>
        <div style={{fontSize:11,fontFamily:T.mono,color:T.text,lineHeight:1.5}}>
          {s.buffett_fallback_reason || "Insufficient history for projection, no analyst target."}
        </div>
      </div>
    );
  }

  if(isFallback){
    // Analyst fallback — yellow flag, simpler block
    return (
      <div style={{padding:"10px 12px",borderRadius:6,background:T.amberLight,border:`1px solid var(--amber)`,marginTop:10}}>
        <div style={{fontSize:9,color:T.amber,fontFamily:T.mono,fontWeight:600,letterSpacing:"0.08em",marginBottom:6}}>⚠ ANALYST-ONLY FALLBACK</div>
        <div style={{fontSize:11,fontFamily:T.mono,color:T.text,lineHeight:1.5,marginBottom:6}}>
          Value 5y projection unavailable: <span style={{color:T.amber,fontWeight:600}}>{s.buffett_fallback_reason}</span>
        </div>
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:"4px 14px",fontSize:11,fontFamily:T.mono}}>
          <span style={{color:T.textMuted}}>Analyst target</span>
          <span style={{textAlign:"right",fontWeight:600,color:T.text}}>{c}{s.target?.toFixed(2) || "—"}</span>
          <span style={{color:T.textMuted}}>Upside</span>
          <span style={{textAlign:"right",fontWeight:600,color:s.upside>0?T.green:T.red}}>{s.upside>=0?"+":""}{s.upside?.toFixed(0) || 0}%</span>
        </div>
      </div>
    );
  }

  // Full Buffett projection
  const methodLabel = method === "eps_cagr" ? "Min Growth (EPS, BVPS, Yield)" : "Value Projection";
  const methodColor = method === "bvps_roe" ? T.green : T.blue;
  const fairValue = s.buffett_fair_value || 0;
  const futurePrice = s.buffett_future_price || 0;
  const upside = s.intrinsic_upside ?? 0;
  const upsideColor = upside>15?T.green : upside>0?"#5a9e7a" : upside>-15?T.amber : T.red;

  return (
    <div style={{padding:"10px 12px",borderRadius:6,background:T.card,border:`1px solid ${T.divider}`,marginTop:10}}>
      <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:6}}>
        <span style={{fontSize:9,color:T.textMuted,fontFamily:T.mono,fontWeight:600,letterSpacing:"0.08em"}}>VALUE 5Y PROJECTION</span>
        <span style={{fontSize:9,color:methodColor,fontFamily:T.mono,fontWeight:600}}>{methodLabel}</span>
      </div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:"4px 14px",fontSize:11,fontFamily:T.mono}}>
        <span style={{color:T.textMuted}}>Growth assumption</span>
        <span style={{textAlign:"right",fontWeight:600,color:T.text}}>{((s.buffett_g_assumed||0)*100).toFixed(1)}%</span>
        {method === "bvps_roe" && (<>
          <span style={{color:T.textMuted}}>ROE (median 5y)</span>
          <span style={{textAlign:"right",fontWeight:600,color:T.text}}>{((s.buffett_roe_assumed||0)*100).toFixed(1)}%</span>
        </>)}
        <span style={{color:T.textMuted}}>P/E (median 5y)</span>
        <span style={{textAlign:"right",fontWeight:600,color:T.text}}>{(s.buffett_pe_median||0).toFixed(1)}x</span>
        <span style={{color:T.textMuted}}>EPS in 5y</span>
        <span style={{textAlign:"right",fontWeight:600,color:T.text}}>{c}{(s.buffett_eps_5y||0).toFixed(2)}</span>
        <span style={{color:T.textMuted}}>Future price (5y)</span>
        <span style={{textAlign:"right",fontWeight:700,color:T.green}}>{c}{futurePrice.toFixed(2)}</span>
        <span style={{color:T.textMuted}}>Fair value today (10% hurdle)</span>
        <span style={{textAlign:"right",fontWeight:700,color:T.green}}>{c}{fairValue.toFixed(2)}</span>
        <span style={{color:T.textMuted}}>Margin of safety</span>
        <span style={{textAlign:"right",fontWeight:700,color:upsideColor}}>{upside>=0?"+":""}{upside.toFixed(1)}%</span>
      </div>
    </div>
  );
}

// ── GrowthCard: dedicated card for the v8 Growth factor.
// Each row shows YoY (TTM) and 3-year CAGR for the three core metrics that
// feed Growth scoring: revenue, EPS, FCF. The 60/40 TTM-YoY / 3yr-CAGR
// blend is what compute_composite_v8 actually scores; presenting both
// numbers lets the user see whether growth is recent or sustained.
function GrowthCard({s}:{s:StockData}){
  const fmtG=(v:number|undefined)=>v==null?"—":`${v>=0?"+":""}${(v*100).toFixed(1)}%`;
  const colG=(v:number|undefined)=>{
    if(v==null)return T.textLight;
    if(v>0.15)return T.green;
    if(v>0.05)return"#5a9e7a";
    if(v>0)return T.text;
    if(v>-0.05)return T.amber;
    return T.red;
  };
  const rows:[string,number|undefined,number|undefined][]=[
    ["Revenue",s.revenue_yoy,s.revenue_cagr_3y],
    ["EPS",s.eps_yoy,s.eps_cagr_3y],
    ["FCF",s.fcf_yoy,s.fcf_cagr_3y],
  ];
  const score=s.factors_v8?.growth??s.factors_v8_momentum?.growth;
  const scoreColor=score==null?T.textLight:score>0.7?T.green:score>0.4?T.amber:T.red;
  return(
    <Card>
      <SH title="Growth" icon={<TrendingUp size={12}/>} sub={score!=null?`Score ${(score*100).toFixed(0)}/100`:"no data"}/>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:"4px 10px",fontSize:10,fontFamily:T.mono,color:T.textMuted,fontWeight:600,letterSpacing:"0.04em",marginBottom:6,paddingBottom:6,borderBottom:`1px solid ${T.divider}`}}>
        <div></div>
        <div style={{textAlign:"right"}}>YoY (TTM)</div>
        <div style={{textAlign:"right"}}>3y CAGR</div>
      </div>
      {rows.map(([label,yoy,cagr])=>(
        <div key={label} style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:"4px 10px",fontSize:12,fontFamily:T.mono,padding:"6px 0",borderBottom:`1px solid ${T.divider}`}}>
          <div style={{color:T.text,fontWeight:600}}>{label}</div>
          <div style={{textAlign:"right",color:colG(yoy),fontWeight:700}}>{fmtG(yoy)}</div>
          <div style={{textAlign:"right",color:colG(cagr),fontWeight:700}}>{fmtG(cagr)}</div>
        </div>
      ))}
      <div style={{marginTop:10,fontSize:9,fontFamily:T.mono,color:T.textLight,lineHeight:1.5}}>
        Score = 60% TTM YoY + 40% 3y CAGR, equal weight rev/EPS/FCF. Top tier ≥25% growth, bottom tier ≤0%.
      </div>
      {score!=null&&(
        <div style={{marginTop:10,height:5,borderRadius:3,background:T.divider,overflow:"hidden"}}>
          <div style={{height:"100%",width:`${score*100}%`,borderRadius:3,background:scoreColor,transition:"width 0.4s"}}/>
        </div>
      )}
    </Card>
  );
}

// ── SmartMoneyCard: 6-factor LTR-derived breakdown.
// Reads s.smart_money_components directly (populated by compute_smart_money_score
// in the backend). Components are already post-multiplier, so what's shown
// is what feeds the v8 composite's smart_money sub-factor.
//
// May 2026 — rewritten for Option C. Old version showed Analyst/Insider/
// Transcript/Earnings rows that no longer drive the score (LTR found those
// had little marginal predictive power). New version mirrors the 6 weights
// in compute_smart_money_score: institutional_flow 30, trend 28, inst 20,
// quality 10, sector 7, congressional 5.
function SmartMoneyCard({s}:{s:StockData}){
  const sm = s.smart_money_score;
  const wt = s.smart_money_weight ?? 0;
  const comps = s.smart_money_components ?? {};
  const scoreColor = sm == null ? T.textLight : sm > 0.6 ? T.green : sm > 0.4 ? T.amber : T.red;

  // Underlying trend % for context
  const trendPct = s.sma200 > 0 ? ((s.sma50 - s.sma200) / s.sma200) * 100 : 0;

  // Factor catalog: [key, weight%, display label, fallback msg when missing, tooltip key]
  // v1.2 (May 2026): added pt_velocity (10%). Weights rebalanced:
  //   instflow 30→25, trend 28→23, inst 20→20, quality 10→10,
  //   sectormom 7→7, congress 5→5, pt_velocity 0→10. Total still 100%.
  const FACTORS:[string,number,string,string,string][] = [
    ["institutional_flow", 25, "Inst flow",      "US-only · pass-2 only",    "Inst Flow"],
    ["trend_strength",     23, "Trend",          "missing SMA data",         "Trend"],
    ["institutional",      20, "Inst accum",     "US-only · pass-2 only",    "Inst Accum"],
    ["pt_velocity",        10, "PT velocity",    "60d bootstrap pending",    "PT Velocity"],
    ["quality",            10, "Quality",        "Piotroski/Altman missing", "Quality SM"],
    ["sector_momentum",     7, "Sector mom",     "non-NASDAQ stock",         "Sector Mom"],
    ["congressional",       5, "Congress",       "no recent trades",         "Congress"],
  ];

  type Tone = "good"|"bad"|"neutral"|"none";
  const toneColor = (t:Tone) => t==="good"?T.green : t==="bad"?T.red : t==="neutral"?T.textMuted : T.textLight;

  // PT velocity reads from the top-level row, not from smart_money_components
  // (the backend exposes pt_velocity_60d / pt_velocity_score separately on
  // the stock row for direct frontend access). Bootstrap fallback: when
  // pt_velocity_60d is null the rolling cache hasn't matured yet (60d window).
  const ptVelRaw = s.pt_velocity_60d;
  const ptVelScore = s.pt_velocity_score;

  const rows = FACTORS.map(([key, weight, label, missingMsg, tipKey])=>{
    const tip = TOOLTIPS[tipKey] || "";

    // pt_velocity has its own data path on the stock row
    if(key === "pt_velocity"){
      if(ptVelScore == null || ptVelRaw == null){
        return { key, weight, label, score:null, detail:missingMsg, tone:"none" as Tone, tip };
      }
      const tone:Tone = ptVelScore > 0.6 ? "good" : ptVelScore < 0.4 ? "bad" : "neutral";
      const sign = ptVelRaw >= 0 ? "+" : "";
      const detail = `${sign}${(ptVelRaw*100).toFixed(1)}% (60d) · ${(ptVelScore*100).toFixed(0)}/100`;
      return { key, weight, label, score:ptVelScore, detail, tone, tip };
    }

    const c = (comps as any)[key] as number|undefined;
    if(c == null){
      return { key, weight, label, score:null, detail:missingMsg, tone:"none" as Tone, tip };
    }
    const tone:Tone = c > 0.6 ? "good" : c < 0.4 ? "bad" : "neutral";

    let detail = `score ${(c*100).toFixed(0)}/100`;
    switch(key){
      case "institutional_flow":
        if(c > 0.6) detail = `Accumulating · ${(c*100).toFixed(0)}/100`;
        else if(c < 0.4) detail = `Distributing · ${(c*100).toFixed(0)}/100`;
        else detail = `Neutral · ${(c*100).toFixed(0)}/100`;
        break;
      case "trend_strength": {
        // Show raw trend % AND post-multiplier score so the user can see
        // when distribution muted the trend contribution.
        const rawTrendScore = (() => {
          const t = trendPct/100;
          if(t < -0.10) return 0.0;
          if(t < -0.02) return 0.20;
          if(t <  0.02) return 0.50;
          if(t <  0.10) return 0.75;
          return 1.0;
        })();
        const muted = rawTrendScore - c > 0.10;
        detail = `${trendPct>=0?"+":""}${trendPct.toFixed(1)}% (50d vs 200d) · ${(c*100).toFixed(0)}/100`;
        if(muted) detail += " · ⚠ muted by distribution";
        break;
      }
      case "institutional":
        if(s.inst_holders_change != null && s.inst_accumulation != null){
          detail = `Holders ${(s.inst_holders_change*100).toFixed(1)}% QoQ · Shares ${(s.inst_accumulation*100).toFixed(1)}%`;
        }
        break;
      case "quality":
        detail = `Pio ${s.piotroski}/9 · Z ${s.altman_z?.toFixed(1)} · ${(c*100).toFixed(0)}/100`;
        break;
      case "sector_momentum":
        detail = c > 0.6 ? `Sector leader · ${(c*100).toFixed(0)}` : c < 0.4 ? `Sector laggard · ${(c*100).toFixed(0)}` : `In line · ${(c*100).toFixed(0)}`;
        break;
      case "congressional":
        detail = c > 0.6 ? `Net buying · ${(c*100).toFixed(0)}` : c < 0.4 ? `Net selling · ${(c*100).toFixed(0)}` : `Mixed · ${(c*100).toFixed(0)}`;
        break;
    }
    return { key, weight, label, score:c, detail, tone, tip };
  });

  const subText = sm != null
    ? `Score ${(sm*100).toFixed(0)}/100 · ${(wt*100).toFixed(0)}% coverage`
    : "no data";

  return(
    <Card>
      <SH title="Smart Money" icon={<Brain size={12}/>} sub={subText}/>
      <div style={{display:"flex",flexDirection:"column",gap:0}}>
        {rows.map(r=>(
          <div key={r.key} style={{
            display:"flex",alignItems:"center",justifyContent:"space-between",
            padding:"7px 0",borderBottom:`1px solid ${T.divider}`,
            fontSize:11,fontFamily:T.mono,
            opacity:r.tone==="none"?0.5:1
          }}>
            <div style={{display:"flex",alignItems:"baseline",gap:6,flexShrink:0}}>
              <span title={r.tip} style={{color:T.text,fontWeight:600,cursor:r.tip?"help":"default",borderBottom:r.tip?`1px dotted ${T.textLight}`:"none"}}>{r.label}</span>
              <span style={{fontSize:9,color:T.textLight}}>({r.weight}%)</span>
            </div>
            <span style={{color:toneColor(r.tone),fontWeight:600,fontSize:10,textAlign:"right",maxWidth:"65%"}}>
              {r.detail}
            </span>
          </div>
        ))}
      </div>
      {sm != null && (
        <div style={{marginTop:10,height:5,borderRadius:3,background:T.divider,overflow:"hidden"}}>
          <div style={{height:"100%",width:`${sm*100}%`,borderRadius:3,background:scoreColor,transition:"width 0.4s"}}/>
        </div>
      )}
      <div style={{marginTop:8,fontSize:9,fontFamily:T.mono,color:T.textLight,lineHeight:1.4}}>
        LTR-derived 7-factor weighted score. Trend × min(1, inst_flow×2) — strong distribution kills trend credit. PT velocity (10%) added v1.2 (May 2026) — bootstrap ~60 days. No weight redistribution: missing factors lower the ceiling.
      </div>
    </Card>
  );
}

// ── MomentumPanel ──────────────────────────────────────────────────────────────
function MomentumPanel({s}:{s:StockData}){
  const gc=s.sma50>s.sma200,p50=s.price>s.sma50,p200=s.price>s.sma200;
  const rz=s.rsi>70?"Overbought":s.rsi>60?"Bullish":s.rsi>40?"Neutral":s.rsi>30?"Bearish":"Oversold";
  const rc=s.rsi>70?T.red:s.rsi<30?"var(--green)":s.rsi>60?"var(--green)":s.rsi<40?T.amber:T.textMuted;
  const r52=s.year_high-s.year_low,p52=r52>0?((s.price-s.year_low)/r52)*100:50;
  const crossTip=TOOLTIPS[gc?"Golden Cross":"Death Cross"];
  
  const inds=[
    {l:"MACD",v:s.macd_signal,b:s.macd_signal?.includes("bullish")},
    {l:"ADX",v:s.adx?.toFixed(1),b:s.adx>25},
    {l:"BB%B",v:s.bb_pct?.toFixed(2),b:s.bb_pct>0.2&&s.bb_pct<0.8},
    {l:"StochRSI",v:s.stoch_rsi?.toFixed(0),b:s.stoch_rsi>20&&s.stoch_rsi<80},
    {l:"OBV",v:s.obv_trend,b:s.obv_trend==="rising"}
  ];
  
  return(
    <Card>
      <SH title="Momentum" icon={<Activity size={12}/>}/>
      <div style={{marginBottom:14}}>
        <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:8}}>
          <div style={{width:8,height:8,borderRadius:"50%",background:gc?"var(--green)":T.red,boxShadow:`0 0 6px ${gc?"var(--green)":T.red}40`}}/>
          <span title={crossTip} style={{fontSize:11,fontFamily:T.mono,fontWeight:600,color:gc?"var(--green)":T.red,cursor:"help",borderBottom:`1px dotted ${gc?"var(--green)80":T.red+"80"}`}}>
            {gc?"Golden Cross":"Death Cross"}
          </span>
        </div>
        <div style={{display:"flex",gap:6}}>
          {[{l:`Price ${p50?">":"<"} SMA50`,ok:p50,v:fmtPrice(s.sma50)},{l:`Price ${p200?">":"<"} SMA200`,ok:p200,v:fmtPrice(s.sma200)}].map((m,i)=>(
            <div key={i} style={{flex:1,padding:"6px 8px",borderRadius:6,fontSize:10,fontFamily:T.mono,background:m.ok?T.greenLight:T.redLight,color:m.ok?"var(--green)":T.red,border:`1px solid ${m.ok?T.greenBorder:"var(--red)"}`}}>
              <div style={{fontWeight:600}}>{m.l}</div>
              <div style={{fontSize:9,opacity:0.8,marginTop:1}}>{m.v}</div>
            </div>
          ))}
        </div>
      </div>
      <div style={{marginBottom:14}}>
        <div style={{display:"flex",justifyContent:"space-between",marginBottom:4}}>
          <span title={TOOLTIPS["RSI"]} style={{fontSize:10,fontFamily:T.mono,color:T.textMuted,cursor:"help",borderBottom:`1px dotted ${T.textLight}`}}>RSI</span>
          <span style={{fontSize:11,fontFamily:T.mono,fontWeight:600,color:rc}}>{s.rsi?.toFixed(1)} — {rz}</span>
        </div>
        <div style={{position:"relative",height:8,borderRadius:4,overflow:"hidden",background:`linear-gradient(to right, var(--green) 0%, var(--green) 30%, ${T.divider} 30%, ${T.divider} 70%, ${T.red} 70%, ${T.red} 100%)`}}>
          <div style={{position:"absolute",left:`${s.rsi}%`,top:-2,width:12,height:12,borderRadius:"50%",background:"var(--bg-surface)",border:`2px solid ${rc}`,transform:"translateX(-6px)",boxShadow:"0 1px 3px rgba(0,0,0,0.15)"}}/>
        </div>
      </div>
      <div style={{marginBottom:14}}>
        <div style={{display:"flex",justifyContent:"space-between",marginBottom:4}}>
          <span title={TOOLTIPS["52-Week Range"]} style={{fontSize:10,fontFamily:T.mono,color:T.textMuted,cursor:"help",borderBottom:`1px dotted ${T.textLight}`}}>52-Week Range</span>
          <span style={{fontSize:10,fontFamily:T.mono,color:T.textMuted}}>{p52.toFixed(0)}%</span>
        </div>
        <div style={{position:"relative",height:6,borderRadius:3,background:T.divider}}>
          <div style={{position:"absolute",left:0,top:0,bottom:0,width:`${p52}%`,borderRadius:3,background:`linear-gradient(to right, var(--green), ${p52>80?T.amber:"var(--green)"})`}}/>
          <div style={{position:"absolute",left:`${p52}%`,top:-3,width:12,height:12,borderRadius:"50%",background:"var(--bg-surface)",border:"2px solid var(--green)",transform:"translateX(-6px)",boxShadow:"0 1px 2px rgba(0,0,0,0.1)"}}/>
        </div>
        <div style={{display:"flex",justifyContent:"space-between",fontSize:9,fontFamily:T.mono,color:T.textLight,marginTop:3}}>
          <span>{fmtPrice(s.year_low,s.currency)}</span>
          <span style={{fontWeight:600,color:T.text}}>{fmtPrice(s.price,s.currency)}</span>
          <span>{fmtPrice(s.year_high,s.currency)}</span>
        </div>
      </div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:4}}>
        {inds.map((d,i)=>(
          <div key={i} style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"5px 8px",borderRadius:4,fontSize:10,fontFamily:T.mono,background:d.b?T.greenLight:"var(--bg-elevated)",border:`1px solid ${d.b?T.greenBorder:T.divider}`}}>
            <span title={TOOLTIPS[d.l]} style={{color:T.textMuted,fontWeight:500,cursor:"help",borderBottom:`1px dotted ${T.textLight}`}}>{d.l}</span>
            <span style={{color:d.b?"var(--green)":T.textMuted,fontWeight:600}}>{d.v}</span>
          </div>
        ))}
      </div>
      <div style={{marginTop:12}}>
        <div style={{display:"flex",justifyContent:"space-between",marginBottom:4}}>
          <span title={TOOLTIPS["Bull Score"]} style={{fontSize:10,fontFamily:T.mono,color:T.textMuted,cursor:"help",borderBottom:`1px dotted ${T.textLight}`}}>Bull Score</span>
          <span style={{fontSize:11,fontFamily:T.mono,fontWeight:700,color:s.bull_score>=7?"var(--green)":s.bull_score>=4?T.amber:T.red}}>{s.bull_score}/10</span>
        </div>
        <div style={{display:"flex",gap:3}}>
          {Array.from({length:10},(_,i)=>{
            const a=i<s.bull_score,c=s.bull_score>=7?"var(--green)":s.bull_score>=4?T.amber:T.red;
            return <div key={i} style={{flex:1,height:6,borderRadius:3,background:a?c:T.divider}}/>;
          })}
        </div>
      </div>
    </Card>
  );
}

// ── TranscriptInsights ─────────────────────────────────────────────────────────
function TranscriptInsights({symbol, dossier}:{symbol:string; dossier?:string}) {
  const [analysis, setAnalysis] = useState<string|null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string|null>(null);
  const [qFound, setQFound] = useState(0);
  const [fromPipeline, setFromPipeline] = useState(false);

  useEffect(() => {
    // Prefer the Speculair pipeline's opus dossier when this name was debated — auto-show,
    // no API call needed (the Interrogator already read the transcripts during the debate).
    if (dossier && dossier.trim()) {
      setAnalysis(dossier);
      setFromPipeline(true);
      return;
    }
    const stored = localStorage.getItem(`transcript_insight_${symbol}`);
    if (stored) {
      try {
        const parsed = JSON.parse(stored);
        if (parsed.analysis) {
          setAnalysis(parsed.analysis);
          setQFound(parsed.quarters_found || 0);
        }
      } catch (e) {}
    }
  }, [symbol, dossier]);

  const f = useCallback(async () => {
    setLoading(true);
    setError(null);
    setFromPipeline(false);
    try {
      const r = await fetch(`/api/transcript?symbol=${symbol}&quarters=8`);
      const d = await r.json();
      if (d.error) setError(d.error);
      else {
        const txt = d.analysis || "No analysis.";
        setAnalysis(txt);
        setQFound(d.quarters_found || 0);
        localStorage.setItem(`transcript_insight_${symbol}`, JSON.stringify({
          analysis: txt,
          quarters_found: d.quarters_found || 0
        }));
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [symbol]);

  return (
    <Card>
      <SH title="Transcript Insights" icon={<Brain size={12} />} sub={fromPipeline ? "From Speculair debate · opus multi-quarter forensics" : (qFound > 0 ? `${qFound} quarters analyzed` : "")} />
      {analysis ? (
        <div>
          <div style={{ fontSize: 11, lineHeight: 1.7, color: T.text, fontFamily: T.sans, whiteSpace: "pre-wrap" }}>
            {analysis}
          </div>
          <button onClick={f} disabled={loading} style={{ marginTop: 12, background: "none", border: `1px solid ${T.cardBorder}`, borderRadius: 6, padding: "6px 12px", cursor: loading ? "not-allowed" : "pointer", fontSize: 10, fontFamily: T.mono, color: T.textMuted, display: "flex", alignItems: "center", gap: 4 }}>
            <RefreshCw size={10} style={loading ? { animation: "spin 1s linear infinite" } : undefined} /> {loading ? "Analyzing…" : fromPipeline ? "Re-analyze with Claude (8q)" : "Refresh"}
          </button>
        </div>
      ) : (
        <div style={{ textAlign: "center", padding: "20px 0" }}>
          <button onClick={f} disabled={loading} style={{ background: loading ? T.divider : T.green, border: "none", borderRadius: 6, padding: "10px 20px", color: loading ? T.textMuted : "var(--bg-surface)", fontFamily: T.mono, fontSize: 11, fontWeight: 600, cursor: loading ? "not-allowed" : "pointer", display: "inline-flex", alignItems: "center", gap: 6 }}>
            {loading ? (
              <><RefreshCw size={12} style={{ animation: "spin 1s linear infinite" }} /> Analyzing 8 quarters...</>
            ) : (
              <><Brain size={12} /> Analyze 2 Years of Earnings</>
            )}
          </button>
          {error && <div style={{ marginTop: 8, fontSize: 10, color: T.red, fontFamily: T.mono, maxWidth: 400, margin: "8px auto 0", lineHeight: 1.5 }}>{error}</div>}
          <div style={{ fontSize: 9, color: T.textLight, fontFamily: T.mono, marginTop: 8 }}>
            Claude analyzes narrative arc, tone shifts, guidance credibility across 8 quarters
          </div>
        </div>
      )}
    </Card>
  );
}

// ── News Feed ──────────────────────────────────────────────────────────────────
function NewsFeed({symbol}:{symbol:string}){const[news,setNews]=useState<NewsItem[]>([]);const[loading,setLoading]=useState(true);useEffect(()=>{fmpFetch("news/stock",{symbols:symbol,limit:15}).then(d=>{if(Array.isArray(d)){const u=symbol.toUpperCase();const filtered=(d as (NewsItem&{symbol?:string})[]).filter(n=>!n.symbol||n.symbol.toUpperCase()===u);setNews(filtered);}setLoading(false);}).catch(()=>setLoading(false));},[symbol]);return<Card><SH title="Recent News" icon={<Newspaper size={12}/>}/>{loading?<div style={{padding:20,textAlign:"center",color:T.textLight,fontSize:11,fontFamily:T.mono}}><Loader2 size={14} style={{animation:"spin 1s linear infinite"}}/></div>:news.length===0?<div style={{padding:16,textAlign:"center",color:T.textLight,fontSize:11,fontFamily:T.mono}}>No recent news</div>:<div style={{display:"flex",flexDirection:"column",gap:8}}>{news.slice(0,8).map((n,i)=><a key={i} href={n.url} target="_blank" rel="noopener noreferrer" style={{display:"block",padding:"10px 12px",borderRadius:6,border:`1px solid ${T.divider}`,background:"var(--bg)",textDecoration:"none"}}><div style={{fontSize:12,fontWeight:600,color:T.text,lineHeight:1.4,marginBottom:4}}>{n.title}</div><div style={{display:"flex",gap:8,fontSize:9,fontFamily:T.mono,color:T.textLight}}><span>{n.site}</span><span>·</span><span>{new Date(n.publishedDate).toLocaleDateString()}</span></div></a>)}</div>}</Card>;}

// ── FMP Growth/Profitability/Valuation ──────────────────────────────────────────
const cs_:React.CSSProperties={padding:"6px 10px",textAlign:"right",fontSize:11,fontFamily:T.mono,borderBottom:`1px solid ${T.divider}`,whiteSpace:"nowrap"};
const hs_:React.CSSProperties={...cs_,color:T.textMuted,fontWeight:500,fontSize:10};
const ls_:React.CSSProperties={...cs_,textAlign:"left",color:T.textMuted,fontWeight:500};
function GC({v}:{v:number|null}){if(v==null)return<td style={cs_}>—</td>;return<td style={{...cs_,color:gClr(v),fontWeight:600}}>{(v*100).toFixed(1)}%</td>;}

function GrowthPanel({incomes,loading,ratios}:{incomes:IncomeRow[];loading:boolean;ratios?:RatioYear[]}){if(loading)return<Card><SH title="Growth Rates" icon={<BarChart2 size={12}/>}/><div style={{padding:24,textAlign:"center",color:T.textLight,fontSize:11,fontFamily:T.mono}}><Loader2 size={14} style={{animation:"spin 1s linear infinite"}}/></div></Card>;if(!incomes.length)return null;const sorted=[...incomes].sort((a,b)=>a.date.localeCompare(b.date));const latest=sorted[sorted.length-1];const n=sorted.length;function cagr(f:keyof IncomeRow,y:number):number|null{if(n<y+1)return null;return safeCagr(sorted[n-1-y][f]as number,latest[f]as number,y);}function yoy(f:keyof IncomeRow):number|null{if(n<2)return null;const prev=sorted[n-2][f]as number,cur=latest[f]as number;if(!prev||prev<=0)return null;return(cur-prev)/prev;}const ms:[string,keyof IncomeRow][]=[["Revenue","revenue"],["Gross Profit","grossProfit"],["Operating Income","operatingIncome"],["Net Income","netIncome"],["EPS","epsdiluted"],["EBITDA","ebitda"]];const fcfSorted=ratios?[...ratios].sort((a,b)=>a.date.localeCompare(b.date)):[];const fcfN=fcfSorted.length;const fcfLatest=fcfN>0?fcfSorted[fcfN-1]:null;function fcfYoy():number|null{if(fcfN<2)return null;const prev=fcfSorted[fcfN-2].freeCashFlowPerShare,cur=fcfSorted[fcfN-1].freeCashFlowPerShare;if(!prev||prev<=0)return null;return(cur-prev)/prev;}function fcfCagr(y:number):number|null{if(fcfN<y+1)return null;return safeCagr(fcfSorted[fcfN-1-y].freeCashFlowPerShare,fcfSorted[fcfN-1].freeCashFlowPerShare,y);}return<Card><SH title="Growth Rates" icon={<BarChart2 size={12}/>} sub={`FY ${latest.calendarYear}`}/><div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse"}}><thead><tr><th style={{...hs_,textAlign:"left"}}>Metric</th><th style={hs_}>1Y</th><th style={hs_}>3Y</th><th style={hs_}>5Y</th><th style={hs_}>10Y</th></tr></thead><tbody>{ms.map(([l,f])=><tr key={l}><td style={ls_}><span title={TOOLTIPS[l]||""} style={{cursor:TOOLTIPS[l]?"help":"default",borderBottom:TOOLTIPS[l]?`1px dotted ${T.textLight}`:"none"}}>{l}</span></td><GC v={yoy(f)}/><GC v={cagr(f,3)}/><GC v={cagr(f,5)}/><GC v={cagr(f,10)}/></tr>)}{fcfLatest&&<tr><td style={ls_}><span title={TOOLTIPS["FCF/Share"]||""} style={{cursor:"help",borderBottom:`1px dotted ${T.textLight}`}}>FCF/Share</span></td><GC v={fcfYoy()}/><GC v={fcfCagr(3)}/><GC v={fcfCagr(5)}/><GC v={fcfCagr(10)}/></tr>}</tbody></table></div></Card>;}

function ProfitPanel({ratios,loading}:{ratios:RatioYear[];loading:boolean}){if(loading||!ratios.length)return null;const c=ratios[0];const avgN=(f:keyof RatioYear,n:number)=>{const vs=ratios.slice(0,n).map(r=>r[f]as number).filter(v=>v!=null&&isFinite(v));return vs.length>=Math.min(n,2)?vs.reduce((a,b)=>a+b,0)/vs.length:null;};const ms:[string,keyof RatioYear,number?,boolean?][]=[["ROE","returnOnEquity",0.15],["ROA","returnOnAssets",0.08],["Gross Margin","grossProfitMargin",0.40],["Op Margin","operatingProfitMargin",0.15],["Net Margin","netProfitMargin",0.10],["Current Ratio","currentRatio",undefined,true],["D/E","debtToEquityRatio",undefined,true]];const fmt=(v:number|null,isR?:boolean)=>{if(v==null||!isFinite(v))return"—";return isR?v.toFixed(2):(v*100).toFixed(1)+"%";};return<Card><SH title="Profitability" sub={`FY ${c.fiscalYear}`}/><div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse"}}><thead><tr><th style={{...hs_,textAlign:"left"}}>Metric</th><th style={hs_}>Current</th><th style={hs_}>3Y</th><th style={hs_}>5Y</th><th style={hs_}>10Y</th></tr></thead><tbody>{ms.map(([l,f,th,isR])=>{const cv=c[f]as number;const cl=(v:number|null)=>v!=null&&th!=null&&v>=th?"var(--green)":T.text;return<tr key={l}><td style={ls_}>{l}</td><td style={{...cs_,color:cl(cv),fontWeight:600}}>{fmt(cv,isR)}</td><td style={{...cs_,color:T.textMuted}}>{fmt(avgN(f,3),isR)}</td><td style={{...cs_,color:T.textMuted}}>{fmt(avgN(f,5),isR)}</td><td style={{...cs_,color:T.textMuted}}>{fmt(avgN(f,10),isR)}</td></tr>;})}</tbody></table></div></Card>;}

function ValPanel({ratios,loading}:{ratios:RatioYear[];loading:boolean}){if(loading||!ratios.length)return null;const yrs=[...ratios].reverse();const ttm=ratios[0];const ms:[string,keyof RatioYear,number?][]=[["P/E","priceToEarningsRatio"],["P/S","priceToSalesRatio"],["P/B","priceToBookRatio"],["P/FCF","priceToFreeCashFlowRatio"],["EV/EBITDA","evToEBITDA"],["BVPS","bookValuePerShare",2],["Div%","dividendYieldPercentage",2]];return<Card><SH title="Valuation History" sub="Annual"/><div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse"}}><thead><tr><th style={{...hs_,textAlign:"left",position:"sticky",left:0,background:T.card,zIndex:1}}>Metric</th>{yrs.map(y=><th key={y.fiscalYear} style={hs_}>{y.fiscalYear}</th>)}<th style={{...hs_,color:T.green,fontWeight:700}}>TTM</th></tr></thead><tbody>{ms.map(([l,f,d])=><tr key={l}><td style={{...ls_,position:"sticky",left:0,background:T.card,zIndex:1}}><span title={TOOLTIPS[l]||""} style={{cursor:TOOLTIPS[l]?"help":"default",borderBottom:TOOLTIPS[l]?`1px dotted ${T.textLight}`:"none"}}>{l}</span></td>{yrs.map(y=>{const v=y[f]as number;return<td key={y.fiscalYear} style={cs_}>{v!=null&&isFinite(v)&&v>0?v.toFixed(d??1):"—"}</td>;})}<td style={{...cs_,color:T.green,fontWeight:600}}>{(()=>{const v=ttm[f]as number;return v!=null&&isFinite(v)&&v>0?v.toFixed(d??1):"—";})()}</td></tr>)}</tbody></table></div></Card>;}

// ── Liquidity & Debt Profile Card ─────────────────────────────────────────────
function LiquidityProfileCard({
  balanceSheets, balanceSheetsQ, ratios, cashFlows, cashFlowsQ, incomes, incomesQ, s, loading
}: {
  balanceSheets: BalanceSheetRow[], balanceSheetsQ: BalanceSheetRow[], ratios: RatioYear[], 
  cashFlows: CashFlowRow[], cashFlowsQ: CashFlowRow[], incomes: IncomeRow[], incomesQ: IncomeRow[], s: StockData, loading: boolean
}) {
  if (loading || !balanceSheets.length) return null;
  const bsSorted = [...balanceSheets].sort((a,b)=>a.date.localeCompare(b.date));
  const bsQSorted = balanceSheetsQ && balanceSheetsQ.length > 0 ? [...balanceSheetsQ].sort((a,b)=>a.date.localeCompare(b.date)) : bsSorted;
  const latestBs = bsQSorted[bsQSorted.length-1] || bsSorted[bsSorted.length-1];
  const ttmRatio = ratios && ratios.length > 0 ? ratios[0] : null;

  const cash = latestBs.cashAndShortTermInvestments ?? latestBs.cashAndCashEquivalents ?? 0;
  const shortDebt = latestBs.shortTermDebt ?? 0;
  const longDebt = latestBs.longTermDebt ?? 0;
  const totalDebt = latestBs.totalDebt ?? (shortDebt + longDebt);
  const netDebt = totalDebt - cash;

  const currentAssets = latestBs.totalCurrentAssets ?? 0;
  const currentLiabilities = latestBs.totalCurrentLiabilities ?? 0;
  const workingCapital = currentAssets - currentLiabilities;
  const currentRatio = currentLiabilities > 0 ? currentAssets / currentLiabilities : null;
  const cashRatio = currentLiabilities > 0 ? cash / currentLiabilities : null;

  const totalAssets = latestBs.totalAssets ?? 0;
  const totalEquity = latestBs.totalEquity ?? 0;
  const goodwillIntangibles = latestBs.goodwillAndIntangibleAssets ?? ((latestBs.goodwill ?? 0) + (latestBs.intangibleAssets ?? 0));
  const financialLeverage = totalEquity > 0 ? totalAssets / totalEquity : null;

  let ttmOcf = 0;
  let ttmFcf = 0;
  if (cashFlowsQ && cashFlowsQ.length >= 4) {
    const cfQSorted = [...cashFlowsQ].sort((a,b)=>a.date.localeCompare(b.date));
    const last4 = cfQSorted.slice(-4);
    ttmOcf = last4.reduce((sum, row) => sum + (row.operatingCashFlow || 0), 0);
    ttmFcf = last4.reduce((sum, row) => sum + (row.freeCashFlow || 0), 0);
  } else if (cashFlows && cashFlows.length > 0) {
    const cfSorted = [...cashFlows].sort((a,b)=>a.date.localeCompare(b.date));
    ttmOcf = cfSorted[cfSorted.length-1].operatingCashFlow || 0;
    ttmFcf = cfSorted[cfSorted.length-1].freeCashFlow || 0;
  }

  let ttmEbitda = 0;
  if (incomesQ && incomesQ.length >= 4) {
    const incQSorted = [...incomesQ].sort((a,b)=>a.date.localeCompare(b.date));
    ttmEbitda = incQSorted.slice(-4).reduce((sum, row) => sum + (row.ebitda || 0), 0);
  } else if (incomes && incomes.length > 0) {
    const incSorted = [...incomes].sort((a,b)=>a.date.localeCompare(b.date));
    ttmEbitda = incSorted[incSorted.length-1].ebitda || 0;
  }

  const ev = (s?.market_cap || 0) + netDebt;
  const evToEbitda = ttmEbitda > 0 ? ev / ttmEbitda : null;
  const netDebtToEbitda = ttmEbitda > 0 ? netDebt / ttmEbitda : null;

  const bn = (n: number) => {
    const abs = Math.abs(n);
    const sign = n < 0 ? "-" : "";
    if (abs >= 1e9) return `${sign}$${(abs/1e9).toFixed(1)}B`;
    if (abs >= 1e6) return `${sign}$${(abs/1e6).toFixed(0)}M`;
    return `${sign}$${abs.toFixed(0)}`;
  };
  const bnNum = (n: number) => {
    const abs = Math.abs(n);
    if (abs >= 1e9) return (abs/1e9).toFixed(1);
    if (abs >= 1e6) return (abs/1e6).toFixed(0);
    return String(abs.toFixed(0));
  };
  const bnSuffix = cash >= 1e9 ? "bn" : cash >= 1e6 ? "m" : "";

  const hist = bsSorted.slice(-5);
  const maxVal = Math.max(...hist.map(b => Math.max(b.totalDebt||0, b.cashAndShortTermInvestments||b.cashAndCashEquivalents||0))) || 1;
  const h = 120; 

  const stackMax = Math.max(cash, totalDebt) || 1;

  const Chip = ({label, val}: {label:string, val:string|React.ReactNode}) => {
    const tip = TOOLTIPS[label] || "";
    return (
      <div style={{background:"var(--bg)", border:`1px solid ${T.divider}`, borderRadius:6, padding:"8px 10px", display:"flex", flexDirection:"column", justifyContent:"center"}}>
        <div title={tip} style={{fontSize:9, fontFamily:T.mono, color:T.textMuted, marginBottom:2, cursor:tip?"help":"default", borderBottom:tip?`1px dotted ${T.textLight}`:"none", width:"fit-content"}}>{label}</div>
        <div style={{fontSize:13, fontFamily:T.mono, color:T.text, fontWeight:700}}>{val}</div>
      </div>
    );
  };

  return (
    <Card>
      <SH title="Liquidity & Debt Profile" icon={<Activity size={12}/>} sub={latestBs.period ? `${latestBs.calendarYear} ${latestBs.period}` : `FY ${latestBs.calendarYear}`} />
      <div style={{display:"grid", gridTemplateColumns:"1fr 1.5fr 1fr", gap:20, marginTop:10}}>
        
        <div style={{display:"flex", gap:16, height:180, alignItems:"flex-end", paddingBottom:20}}>
          <div style={{flex:1, display:"flex", flexDirection:"column", alignItems:"center", height:"100%"}}>
            <div style={{fontSize:10, fontFamily:T.mono, color:T.textMuted, marginBottom:8}}>Cash ({bnSuffix})</div>
            <div style={{flex:1, width:40, position:"relative", display:"flex", alignItems:"flex-end"}}>
              <div title={`Total Cash: ${bn(cash)}`} style={{width:"100%", background:"var(--text-light)", height:`${Math.max(5, (cash/stackMax)*100)}%`, borderRadius:"4px 4px 0 0", display:"flex", alignItems:"center", justifyContent:"flex-start", paddingTop:4}}>
                <span style={{fontSize:9, fontFamily:T.mono, color:"#fff", fontWeight:700, writingMode:"vertical-rl", transform:"rotate(180deg)"}}>{cash>0?bnNum(cash):""}</span>
              </div>
            </div>
            <div style={{fontSize:9, fontFamily:T.mono, color:T.text, marginTop:8, fontWeight:600}}>CASH</div>
          </div>
          <div style={{flex:1, display:"flex", flexDirection:"column", alignItems:"center", height:"100%"}}>
            <div style={{fontSize:10, fontFamily:T.mono, color:T.textMuted, marginBottom:8}}>Debt ({bnSuffix})</div>
            <div style={{flex:1, width:40, position:"relative", display:"flex", flexDirection:"column", justifyContent:"flex-end"}}>
              <div style={{width:"100%", background:"var(--red)", height:`${Math.max(2, (shortDebt/stackMax)*100)}%`, borderRadius:"4px 4px 0 0", borderBottom:"1px solid var(--bg-surface)", display:"flex", alignItems:"center", justifyContent:"center"}} title="Short-Term Debt">
                <span style={{fontSize:9, fontFamily:T.mono, color:"#fff", fontWeight:700}}>{shortDebt>0?bnNum(shortDebt):""}</span>
              </div>
              <div style={{width:"100%", background:"#b91c1c", height:`${Math.max(2, (longDebt/stackMax)*100)}%`, display:"flex", alignItems:"center", justifyContent:"flex-start", paddingTop:4}} title="Long-Term Debt">
                <span style={{fontSize:9, fontFamily:T.mono, color:"#fff", fontWeight:700, writingMode:"vertical-rl", transform:"rotate(180deg)"}}>{longDebt>0?bnNum(longDebt):""}</span>
              </div>
            </div>
            <div style={{fontSize:9, fontFamily:T.mono, color:T.text, marginTop:8, fontWeight:600}}>DEBT</div>
          </div>
        </div>

        <div style={{borderLeft:`1px solid ${T.divider}`, borderRight:`1px solid ${T.divider}`, padding:"0 16px", display:"flex", flexDirection:"column", justifyContent:"space-between"}}>
          <div>
            <div style={{fontSize:10, color:T.textMuted, fontFamily:T.mono, fontWeight:600, marginBottom:16, textAlign:"center"}}>DEBT VS CASH TREND (ANNUAL)</div>
            <div style={{display:"flex", alignItems:"flex-end", justifyContent:"space-between", height:h, padding:"0 10px"}}>
              {hist.map((b, i) => {
                const c = b.cashAndShortTermInvestments ?? b.cashAndCashEquivalents ?? 0;
                const d = b.totalDebt ?? 0;
                const cHeight = Math.max(2, (c/maxVal)*h);
                const dHeight = Math.max(2, (d/maxVal)*h);
                return (
                  <div key={i} style={{display:"flex", flexDirection:"column", alignItems:"center", gap:4}}>
                    <div style={{display:"flex", gap:4, alignItems:"flex-end", height:h}}>
                      <div style={{width:14, background:"var(--text-light)", height:cHeight, borderRadius:"2px 2px 0 0"}} title={`Cash: ${bn(c)}`} />
                      <div style={{width:14, background:"#b91c1c", height:dHeight, borderRadius:"2px 2px 0 0"}} title={`Debt: ${bn(d)}`} />
                    </div>
                    <div style={{fontSize:9, fontFamily:T.mono, color:T.textLight}}>{b.calendarYear}</div>
                  </div>
                );
              })}
            </div>
          </div>
          <div style={{display:"flex", justifyContent:"center", gap:16, marginTop:12}}>
            <div style={{display:"flex", alignItems:"center", gap:4, fontSize:9, fontFamily:T.mono, color:T.textMuted}}>
              <div style={{width:8, height:8, background:"var(--text-light)", borderRadius:2}} /> Cash & Equiv
            </div>
            <div style={{display:"flex", alignItems:"center", gap:4, fontSize:9, fontFamily:T.mono, color:T.textMuted}}>
              <div style={{width:8, height:8, background:"#b91c1c", borderRadius:2}} /> Total Debt
            </div>
          </div>
        </div>

        <div style={{display:"flex", flexDirection:"column", gap:8}}>
          <div style={{fontSize:10, color:T.textMuted, fontFamily:T.mono, fontWeight:600, marginBottom:4}}>LEVERAGE</div>
          
          <Chip label="NET DEBT / (CASH)" val={<span style={{color:netDebt > 0 ? T.red : T.green}}>{netDebt > 0 ? bn(netDebt) : `(${bn(Math.abs(netDebt))})`}</span>} />
          <Chip label="D/E RATIO" val={ttmRatio?.debtToEquityRatio != null ? ttmRatio.debtToEquityRatio.toFixed(2) : "—"} />
          <Chip label="INTEREST COVERAGE" val={<span style={{color:ttmRatio?.interestCoverageRatio && ttmRatio.interestCoverageRatio > 3 ? T.green : T.red}}>{ttmRatio?.interestCoverageRatio != null ? `${ttmRatio.interestCoverageRatio.toFixed(1)}x` : "—"}</span>} />
          <Chip label="NET DEBT / EBITDA" val={netDebtToEbitda != null ? `${netDebtToEbitda.toFixed(2)}x` : "—"} />
          <Chip label="FINANCIAL LEVERAGE" val={financialLeverage ? `${financialLeverage.toFixed(2)}x` : "—"} />
        </div>

      </div>

    </Card>
  );
}

// ── Financial Charts Panel ──────────────────────────────────────────────────
function FinancialChartsPanel({
  incomes, balanceSheets, cashFlows,
  incomesQ, balanceSheetsQ, cashFlowsQ,
  loading
}: {
  incomes:IncomeRow[], balanceSheets:BalanceSheetRow[], cashFlows:CashFlowRow[],
  incomesQ:IncomeRow[], balanceSheetsQ:BalanceSheetRow[], cashFlowsQ:CashFlowRow[],
  loading:boolean
}) {
  const [isQuarterly, setIsQuarterly] = useState(false);
  const [showGrowth, setShowGrowth] = useState(false);
  const [activeChart, setActiveChart] = useState<"income"|"balance"|"cash">("income");
  const [activeKeys, setActiveKeys] = useState<Record<string, boolean>>({
    revenue: true, operatingIncome: true, netIncome: true,
    totalAssets: true, totalLiabilities: true, totalEquity: true,
    operatingCashFlow: true, freeCashFlow: true
  });

  const toggleKey = (k: string) => setActiveKeys(prev => ({...prev, [k]: !prev[k]}));

  if (loading) return <Card><SH title="Financials Overview"/><div style={{padding:40,textAlign:"center",color:T.textLight,fontSize:11,fontFamily:T.mono}}><Loader2 size={14} style={{animation:"spin 1s linear infinite"}}/></div></Card>;
  
  const srcIncs = isQuarterly ? incomesQ : incomes;
  const srcBals = isQuarterly ? balanceSheetsQ : balanceSheets;
  const srcCfs = isQuarterly ? cashFlowsQ : cashFlows;
  
  if (!srcIncs.length || !srcBals.length || !srcCfs.length) return null;

  const limit = isQuarterly ? 21 : 11;
  const incsRaw = [...srcIncs].sort((a,b)=>a.date.localeCompare(b.date)).slice(-limit);
  const balsRaw = [...srcBals].sort((a,b)=>a.date.localeCompare(b.date)).slice(-limit);
  const cfsRaw  = [...srcCfs].sort((a,b)=>a.date.localeCompare(b.date)).slice(-limit);

  const incs = incsRaw.slice(- (limit - 1));
  const bals = balsRaw.slice(- (limit - 1));
  const cfs  = cfsRaw.slice(- (limit - 1));
  
  const Chart = ({data, rawData, allKeys, allColors, allLabels}: {data:any[], rawData:any[], allKeys:string[], allColors:string[], allLabels:string[]}) => {
    const activeIndices = allKeys.map((k, i) => activeKeys[k] ? i : -1).filter(i => i !== -1);
    const keys = activeIndices.map(i => allKeys[i]);
    const colors = activeIndices.map(i => allColors[i]);
    const labels = activeIndices.map(i => allLabels[i]);
    
    // Removed early return for keys.length === 0 so toggles still render

    const W=700, H=240, PT=showGrowth ? 60 : 30, PB=20, PL=10, PR=10;

    const fmtN = (v: number) => {
      if (Math.abs(v) >= 1e9) return (v / 1e9).toFixed(1) + "B";
      if (Math.abs(v) >= 1e6) return (v / 1e6).toFixed(0) + "M";
      return v.toFixed(0);
    };

    const plotData = data.map((d, i) => {
      const prevD = rawData[i];
      const items = keys.map((k, j) => {
        const val = d[k] || 0;
        const prevVal = prevD ? (prevD[k] || 0) : 0;
        const pct = prevVal !== 0 && prevVal > 0 ? ((val - prevVal) / prevVal) * 100 : 0;
        const pctStr = (pct > 0 ? "+" : "") + pct.toFixed(0) + "%";
        return { val, plotVal: val, displayStr: fmtN(val), prevVal, pct, pctStr };
      });
      return { d, items };
    });

    const allPlotVals = plotData.flatMap(p => p.items.map(it => it.plotVal));
    let maxVal = Math.max(...allPlotVals, 0) * 1.1;
    let minVal = Math.min(...allPlotVals, 0) * 1.1;
    if (maxVal === 0 && minVal === 0) { maxVal = 10; minVal = -10; }
    const range = maxVal - minVal;
    
    const yPx = (val:number) => H - PB - ((val - minVal) / range) * (H - PT - PB);
    const zeroY = yPx(0);
    const n = data.length;
    const barW = (W - PL - PR) / (n * 1.5);

    return (
      <div style={{flex:1, width:"100%"}}>
        <div style={{display:"flex", gap:12, marginBottom:16, justifyContent:"center"}}>
          {allLabels.map((l, i) => {
            const k = allKeys[i];
            const isActive = activeKeys[k];
            return (
              <div key={k} onClick={()=>toggleKey(k)} style={{display:"flex", alignItems:"center", gap:6, fontSize:10, fontFamily:T.mono, color:isActive ? T.text : T.textLight, cursor:"pointer", background:isActive ? "var(--bg-surface)" : "transparent", padding:"4px 8px", borderRadius:4, border:`1px solid ${isActive ? T.divider : "transparent"}`, boxShadow:isActive ? "0 1px 2px rgba(0,0,0,0.05)" : "none", transition:"all 0.2s"}}>
                <div style={{width:10, height:10, borderRadius:2, background:isActive ? allColors[i] : T.divider}} />
                {l}
              </div>
            );
          })}
        </div>

        {keys.length === 0 ? (
          <div style={{height:220, display:"flex", alignItems:"center", justifyContent:"center", color:T.textLight, fontSize:11, fontFamily:T.mono}}>Select a metric to view</div>
        ) : (
        <svg viewBox={`0 0 ${W} ${H}`} style={{width:"100%", height:"auto", display:"block", background:T.card, borderRadius:4, border:`1px solid ${T.divider}`}}>
          {/* Zero line */}
          <line x1={PL} x2={W-PR} y1={zeroY} y2={zeroY} stroke={T.divider} strokeWidth={1} />
          
          {plotData.map(({ d, items }, i) => {
            const xCenter = PL + (i + 0.5) * ((W - PL - PR) / n);
            const clusterW = barW;
            const subBarW = clusterW / keys.length;
            
            return (
              <g key={i}>
                {items.map((item, j) => {
                  const { val, plotVal, displayStr, prevVal, pct, pctStr } = item;
                  const bx = xCenter - clusterW/2 + j*subBarW;
                  const by = plotVal >= 0 ? yPx(plotVal) : zeroY;
                  const bh = Math.abs(yPx(plotVal) - zeroY);
                  const isLatest = i === n - 1;
                  
                  return (
                    <g key={j}>
                      <rect x={bx} y={by} width={subBarW*0.9} height={bh} fill={colors[j]} rx={1}>
                        <title>{labels[j]} ({d.calendarYear}{d.period ? ` ${d.period}` : ''}): {displayStr} {showGrowth ? `(${pctStr})` : ''}</title>
                      </rect>
                      
                      {/* Discreet number label, rotated */}
                      <text 
                        x={bx + subBarW*0.45} 
                        y={plotVal >= 0 ? by - 3 : by + bh + 3} 
                        textAnchor={plotVal >= 0 ? "start" : "end"}
                        transform={`rotate(-90 ${bx + subBarW*0.45} ${plotVal >= 0 ? by - 3 : by + bh + 3})`}
                        fontSize={isLatest ? 7 : 5.5} 
                        fontFamily={T.mono} 
                        fill={isLatest ? colors[j] === "var(--border)" ? T.textMuted : colors[j] : T.textLight}
                        opacity={isLatest ? 1 : 0.6}
                        style={{pointerEvents:"none"}}
                      >
                        {displayStr}
                      </text>
                      
                      {/* Growth Bracket */}
                      {showGrowth && i > 0 && prevVal > 0 && val > 0 && (
                        (() => {
                          const prevXCenter = PL + (i - 1 + 0.5) * ((W - PL - PR) / n);
                          const prevBx = prevXCenter - clusterW/2 + j*subBarW;
                          const prevBy = yPx(prevVal);
                          // Bracket Y is dynamically placed above the taller of the two bars
                          const bracketY = Math.min(prevBy, by) - 14 - (j * 10);
                          const midX = (prevBx + bx) / 2 + subBarW/2;
                          const pillWidth = 28;
                          
                          return (
                            <g>
                              {/* Connector path */}
                              <path 
                                d={`M ${prevBx + subBarW/2} ${prevBy - 2} V ${bracketY} H ${bx + subBarW/2} V ${by - 4}`} 
                                fill="none" 
                                stroke={colors[j] === "var(--border)" ? "var(--text-light)" : colors[j]} 
                                strokeWidth={0.5} 
                                strokeDasharray="1,1" 
                                opacity={0.6} 
                              />
                              {/* Arrow head */}
                              <polygon 
                                points={`${bx + subBarW/2 - 2},${by - 6} ${bx + subBarW/2 + 2},${by - 6} ${bx + subBarW/2},${by - 2}`} 
                                fill={colors[j] === "var(--border)" ? "var(--text-light)" : colors[j]} 
                                opacity={0.6} 
                              />
                              {/* Pill */}
                              <rect 
                                x={midX - pillWidth/2} 
                                y={bracketY - 5.5} 
                                width={pillWidth} 
                                height={11} 
                                rx={5.5} 
                                fill={"var(--bg-surface)"} 
                                stroke={colors[j] === "var(--border)" ? "#d1d5db" : colors[j]} 
                                strokeWidth={0.5} 
                                opacity={0.9}
                              />
                              <text 
                                x={midX} 
                                y={bracketY + 2.5} 
                                fontSize={5} 
                                fontFamily={T.mono} 
                                fontWeight={700} 
                                fill={pct > 0 ? "var(--green)" : pct < 0 ? T.red : T.textMuted} 
                                textAnchor="middle"
                              >
                                {pctStr}
                              </text>
                            </g>
                          );
                        })()
                      )}
                    </g>
                  );
                })}
                {/* X axis labels */}
                {((isQuarterly ? i % 4 === 3 : i % 2 === 1) || d.isEstimate) && (
                  <text x={xCenter} y={H-5} textAnchor="middle" fontSize={8} fontFamily={T.mono} fill={d.isEstimate ? T.blue : T.textLight}>
                    {isQuarterly 
                      ? `${d.calendarYear?.replace(/^20/, "")}${d.period}` 
                      : (d.calendarYear?.replace(/^20/, "") || "—")}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
        )}
      </div>
    );
  };

  return (
    <Card>
      <div style={{display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:12}}>
        <SH title="Financials Overview" icon={<BarChart2 size={12}/>} sub={isQuarterly ? "Quarterly Trends" : "Annual Trends"} />
        <div style={{display:"flex", gap:12}}>
          <div style={{display:"flex", background:"var(--bg-elevated)", padding:2, borderRadius:6}}>
            <button onClick={()=>setIsQuarterly(false)} style={{padding:"4px 10px", fontSize:10, fontFamily:T.mono, fontWeight:600, border:"none", borderRadius:4, cursor:"pointer", background:!isQuarterly?"var(--bg-surface)":"transparent", color:!isQuarterly?T.text:T.textMuted, boxShadow:!isQuarterly?"0 1px 3px rgba(0,0,0,0.1)":"none"}}>Annual</button>
            <button onClick={()=>setIsQuarterly(true)} style={{padding:"4px 10px", fontSize:10, fontFamily:T.mono, fontWeight:600, border:"none", borderRadius:4, cursor:"pointer", background:isQuarterly?"var(--bg-surface)":"transparent", color:isQuarterly?T.text:T.textMuted, boxShadow:isQuarterly?"0 1px 3px rgba(0,0,0,0.1)":"none"}}>Quarterly</button>
          </div>
          <div style={{display:"flex", background:"var(--bg-elevated)", padding:2, borderRadius:6}}>
            <button onClick={()=>setShowGrowth(false)} style={{padding:"4px 10px", fontSize:10, fontFamily:T.mono, fontWeight:600, border:"none", borderRadius:4, cursor:"pointer", background:!showGrowth?"var(--bg-surface)":"transparent", color:!showGrowth?T.text:T.textMuted, boxShadow:!showGrowth?"0 1px 3px rgba(0,0,0,0.1)":"none"}}>Values</button>
            <button onClick={()=>setShowGrowth(true)} style={{padding:"4px 10px", fontSize:10, fontFamily:T.mono, fontWeight:600, border:"none", borderRadius:4, cursor:"pointer", background:showGrowth?"var(--bg-surface)":"transparent", color:showGrowth?T.text:T.textMuted, boxShadow:showGrowth?"0 1px 3px rgba(0,0,0,0.1)":"none"}}>Growth %</button>
          </div>
        </div>
      </div>
      
      {/* Chart Tabs */}
      <div style={{display:"flex", gap:24, borderBottom:`1px solid ${T.divider}`, marginBottom:20}}>
        {[
          {id:"income", label:"Income Statement"},
          {id:"balance", label:"Balance Sheet"},
          {id:"cash", label:"Cash Flow"}
        ].map(t => (
          <div 
            key={t.id} 
            onClick={()=>setActiveChart(t.id as any)} 
            style={{
              paddingBottom:8, 
              cursor:"pointer", 
              borderBottom:activeChart===t.id ? `2px solid ${T.text}` : "2px solid transparent", 
              color:activeChart===t.id ? T.text : T.textMuted, 
              fontSize:11, 
              fontFamily:T.mono, 
              fontWeight:600,
              transition: "all 0.2s"
            }}
          >
            {t.label}
          </div>
        ))}
      </div>

      <div>
        {activeChart === "income" && <Chart data={incs} rawData={incsRaw} allKeys={["revenue", "operatingIncome", "netIncome"]} allColors={[T.blue, T.amber, T.green]} allLabels={["Rev", "OpInc", "NetInc"]} />}
        {activeChart === "balance" && <Chart data={bals} rawData={balsRaw} allKeys={["totalAssets", "totalLiabilities", "totalEquity"]} allColors={[T.blue, T.red, T.green]} allLabels={["Assets", "Liabs", "Equity"]} />}
        {activeChart === "cash" && <Chart data={cfs} rawData={cfsRaw} allKeys={["operatingCashFlow", "freeCashFlow"]} allColors={["#64748b", T.blue]} allLabels={["OpCash", "FCF"]} />}
      </div>
    </Card>
  );
}

// ── Peer Comparison ────────────────────────────────────────────────────────────
// Compares TTM multiples (P/E, P/S, P/B, P/FCF, EV/EBITDA) of the target
// stock vs FMP's peer set, sorted by market cap. Median row at the bottom.
// Cells coloured: green if value < median * 0.95 (cheaper than peers),
// amber if > median * 1.05 (richer), neutral inside ±5% band.
//
// Data flow: GET /api/peers/{symbol} fans out the FMP calls server-side.
// Multiples are unitless ratios so the comparison is currency-agnostic — a
// JP-listed peer set for 6857.T compares fine even when one peer is an ADR.
// ── Peer Comparison ────────────────────────────────────────────────────────────
// Compares TTM multiples (P/E, P/S, P/B, P/FCF, EV/EBITDA) of the target
// stock vs FMP's peer set, with optional user-added tickers. Sorted by
// market cap. Median row reflects FMP peers only — user additions don't
// pollute the reference but still get coloured against it.
// Cells coloured: green if value < median * 0.95 (cheaper), amber if >
// median * 1.05 (richer), neutral inside ±5% band.
//
// Data flow:
//   FMP peers       → GET /api/peers/{symbol} (server fan-out, cached 1h)
//   User additions  → fmpFetch("ratios-ttm",...) per ticker (client)
// Multiples are unitless ratios so cross-currency peers compare directly.
interface PeerRow{symbol:string;companyName:string;mktCap:number;pe:number|null;ps:number|null;pb:number|null;pfcf:number|null;evEbitda:number|null;}
function PeersPanel({symbol,companyName}:{symbol:string;companyName:string}){
  const router=useRouter();
  const[data,setData]=useState<{target:PeerRow|null;peers:PeerRow[]}|null>(null);
  const[loading,setLoading]=useState(true);
  // User-added comparisons. Session-only — resets on page reload by design.
  const[extras,setExtras]=useState<PeerRow[]>([]);
  const[showInput,setShowInput]=useState(false);
  const[input,setInput]=useState("");
  const[addLoading,setAddLoading]=useState(false);
  const[addError,setAddError]=useState("");
  useEffect(()=>{if(!symbol)return;setLoading(true);setExtras([]);fetch(`/api/peers/${encodeURIComponent(symbol)}`).then(r=>r.ok?r.json():null).then(d=>{if(d?.target&&Array.isArray(d.peers))setData({target:d.target,peers:d.peers});setLoading(false);}).catch(()=>setLoading(false));},[symbol]);
  // FMP sometimes returns 0 for an undefined multiple (e.g. negative
  // earnings → P/E should be "n/a", not "0"). Treat ≤0 as null.
  const safeNum=(v:any):number|null=>{const n=typeof v==="number"?v:parseFloat(v);return isFinite(n)&&n>0?n:null;};
  async function addExtra(rawSym:string){
    const sym=rawSym.trim().toUpperCase().replace(/[^A-Z0-9.\-]/g,"");
    setAddError("");
    if(!sym){setAddError("enter a ticker");return;}
    if(data?.target&&sym===data.target.symbol){setAddError("that's the current stock");return;}
    if(extras.some(e=>e.symbol===sym)||data?.peers.some(p=>p.symbol===sym)){setAddError("already in table");return;}
    setAddLoading(true);
    try{
      // NOTE: the FMP stable REST slug is "ratios-ttm", NOT "metrics-ratios-ttm".
      // The /api/fmp proxy forwards e=ratios-ttm directly to /stable/ratios-ttm.
      const res=await fmpFetch("ratios-ttm",{symbol:sym});
      const row=Array.isArray(res)&&res.length?res[0]:null;
      if(!row){setAddError(`no data for ${sym}`);return;}
      const newRow:PeerRow={symbol:sym,companyName:"",mktCap:0,pe:safeNum(row.priceToEarningsRatioTTM),ps:safeNum(row.priceToSalesRatioTTM),pb:safeNum(row.priceToBookRatioTTM),pfcf:safeNum(row.priceToFreeCashFlowRatioTTM),evEbitda:safeNum(row.enterpriseValueMultipleTTM)};
      // If every metric came back null the ticker probably doesn't exist or
      // FMP doesn't cover it. Don't add a row of dashes.
      if(newRow.pe==null&&newRow.ps==null&&newRow.pb==null&&newRow.pfcf==null&&newRow.evEbitda==null){setAddError(`no metrics for ${sym}`);return;}
      setExtras(prev=>[...prev,newRow]);
      setInput("");setShowInput(false);
    }catch(e){setAddError("fetch failed");}
    finally{setAddLoading(false);}
  }
  function removeExtra(sym:string){setExtras(prev=>prev.filter(e=>e.symbol!==sym));}
  if(loading)return<Card><SH title="Peer Comparison" sub="TTM multiples"/><div style={{padding:24,textAlign:"center",color:T.textLight,fontSize:11,fontFamily:T.mono}}><Loader2 size={14} style={{animation:"spin 1s linear infinite"}}/></div></Card>;
  // Render whenever target loaded, even if FMP returned no peers — manual
  // add affordance needs to be reachable in that case.
  if(!data||!data.target)return null;
  const{target,peers}=data;
  type NumKey="pe"|"ps"|"pb"|"pfcf"|"evEbitda";
  const cols:[string,NumKey][]=[["P/E","pe"],["P/S","ps"],["P/B","pb"],["P/FCF","pfcf"],["EV/EBITDA","evEbitda"]];
  // Median computed from FMP peers only. User additions are coloured
  // against this reference but don't change it.
  const median=(vs:number[])=>{if(!vs.length)return null;const s=[...vs].sort((a,b)=>a-b);const m=Math.floor(s.length/2);return s.length%2?s[m]:(s[m-1]+s[m])/2;};
  const medians:Record<NumKey,number|null>={pe:null,ps:null,pb:null,pfcf:null,evEbitda:null};
  cols.forEach(([,k])=>{const vs=peers.map(p=>p[k]).filter((v):v is number=>v!=null);medians[k]=median(vs);});
  const cellColor=(v:number|null,med:number|null)=>{if(v==null||med==null)return T.text;if(v<med*0.95)return"var(--green)";if(v>med*1.05)return"var(--amber)";return T.text;};
  const fmtNum=(v:number|null)=>v==null?"—":v.toFixed(1);
  const targetName=target?.companyName||companyName||symbol;
  const renderRow=(row:PeerRow,opts:{isTarget?:boolean;isMedian?:boolean;isExtra?:boolean;label?:string}={})=>{
    const{isTarget,isMedian,isExtra,label}=opts;
    const bg=isTarget?T.greenLight:isMedian?"var(--bg)":isExtra?"var(--bg-surface)beb":"transparent";
    const labelText=isMedian?"Peer median":label||row.symbol;
    return<tr key={isMedian?"__median__":(isExtra?"x_"+row.symbol:row.symbol)} style={{background:bg}}>
      <td style={{...ls_,position:"sticky",left:0,background:bg,zIndex:1,fontWeight:isTarget||isMedian?700:500,color:isMedian?T.textMuted:T.text}}>
        {isTarget||isMedian?labelText:<span style={{display:"inline-flex",alignItems:"center",gap:6}}>
          <button onClick={()=>router.push(`/stock/${encodeURIComponent(row.symbol)}`)} style={{background:"none",border:"none",padding:0,color:T.green,cursor:"pointer",fontFamily:T.mono,fontSize:11,fontWeight:600,textDecoration:"underline"}}>{row.symbol}</button>
          {isExtra&&<button onClick={()=>removeExtra(row.symbol)} title="Remove" style={{background:"none",border:"none",padding:"0 2px",color:T.textLight,cursor:"pointer",fontSize:11,lineHeight:1}}>✕</button>}
        </span>}
        {!isTarget&&!isMedian&&row.companyName&&<span style={{display:"block",fontSize:9,color:T.textLight,fontWeight:400,marginTop:1}}>{row.companyName.slice(0,28)}</span>}
        {isTarget&&<span style={{display:"block",fontSize:9,color:T.textLight,fontWeight:400,marginTop:1}}>This stock</span>}
        {isExtra&&!row.companyName&&<span style={{display:"block",fontSize:9,color:T.textLight,fontWeight:400,marginTop:1}}>added</span>}
      </td>
      {cols.map(([,k])=>{const v=row[k];const med=medians[k];const color=isMedian?T.textMuted:cellColor(v,med);return<td key={k} style={{...cs_,color,fontWeight:isTarget||isMedian?700:600}}>{fmtNum(v)}</td>;})}
    </tr>;
  };
  const medianRow:PeerRow={symbol:"__median__",companyName:"",mktCap:0,pe:medians.pe,ps:medians.ps,pb:medians.pb,pfcf:medians.pfcf,evEbitda:medians.evEbitda};
  const subText=peers.length?`TTM multiples · ${peers.length} peers${extras.length?` + ${extras.length} added`:""}`:"TTM multiples · no FMP peers, add manually";
  return<Card>
    <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:8}}>
      <SH title="Peer Comparison" sub={subText}/>
      {!showInput?
        <button onClick={()=>setShowInput(true)} style={{background:"none",border:`1px solid ${T.green}`,color:T.green,padding:"3px 10px",borderRadius:4,fontSize:10,fontFamily:T.mono,fontWeight:600,cursor:"pointer"}}>+ Add ticker</button>
        :<div style={{display:"flex",alignItems:"center",gap:6}}>
          <input autoFocus value={input} onChange={e=>{setInput(e.target.value);setAddError("");}} onKeyDown={e=>{if(e.key==="Enter")addExtra(input);if(e.key==="Escape"){setShowInput(false);setInput("");setAddError("");}}} placeholder="e.g. NVDA" style={{padding:"4px 8px",border:`1px solid ${T.cardBorder}`,borderRadius:4,fontSize:11,fontFamily:T.mono,width:90,outline:"none"}}/>
          <button onClick={()=>addExtra(input)} disabled={addLoading} style={{background:T.green,color:"var(--bg-surface)",border:"none",padding:"4px 10px",borderRadius:4,fontSize:10,fontFamily:T.mono,fontWeight:600,cursor:"pointer",opacity:addLoading?0.5:1}}>{addLoading?"...":"Add"}</button>
          <button onClick={()=>{setShowInput(false);setInput("");setAddError("");}} title="Cancel" style={{background:"none",border:"none",padding:0,color:T.textLight,cursor:"pointer",fontSize:14,lineHeight:1}}>✕</button>
        </div>
      }
    </div>
    {addError&&<div style={{fontSize:10,color:"var(--amber)",fontFamily:T.mono,marginBottom:6}}>{addError}</div>}
    <div style={{overflowX:"auto"}}>
      <table style={{width:"100%",borderCollapse:"collapse"}}>
        <thead><tr>
          <th style={{...hs_,textAlign:"left",position:"sticky",left:0,background:T.card,zIndex:1}}>Company</th>
          {cols.map(([l])=><th key={l} style={hs_}>{l}</th>)}
        </tr></thead>
        <tbody>
          {renderRow(target,{isTarget:true,label:targetName.slice(0,28)||symbol})}
          {peers.map(p=>renderRow(p))}
          {peers.length>0&&renderRow(medianRow,{isMedian:true})}
          {extras.length>0&&<tr><td colSpan={cols.length+1} style={{padding:"6px 8px",fontSize:9,color:T.textLight,fontFamily:T.mono,textTransform:"uppercase",letterSpacing:0.5,borderTop:`1px dashed ${T.cardBorder}`}}>Your comparisons</td></tr>}
          {extras.map(p=>renderRow(p,{isExtra:true}))}
        </tbody>
      </table>
    </div>
    <div style={{fontSize:9,color:T.textLight,fontFamily:T.mono,marginTop:8,lineHeight:1.5}}>
      <span style={{color:"var(--green)",fontWeight:600}}>Green</span> = cheaper than peer median (&gt;5% below)
      &nbsp;·&nbsp;
      <span style={{color:"var(--amber)",fontWeight:600}}>Amber</span> = richer than peer median (&gt;5% above)
      &nbsp;·&nbsp; Peer median uses FMP peers only. Manual additions are scored against it but don't change it. Multiples are unitless so cross-currency comparison is meaningful.
    </div>
  </Card>;
}
 // ── Helpers for the Side-by-Side Comparison tab ──────────────────────────────
// Loads a stock's scan data by searching the three region files (sp500,
// europe, global) and picking the freshest match. Returns null if the
// symbol isn't present in any current scan — typical for tickers outside
// the current scanning universe (e.g. ONTO, ALAB at time of writing).
async function loadStockFromScans(symbol:string):Promise<StockData|null>{
  const sym=symbol.toUpperCase();
  const regions=["sp500","europe","global"] as const;
  const results=await Promise.all(regions.map(async r=>{
    try {
      const res = await fetch(`${GCS_SCANS}/latest_${r}.json`, { cache: 'no-store' });
      if (res.ok) return await res.json();
    } catch(e){}
    try {
      const res = await fetch(`/latest_${r}.json`, { cache: 'no-store' });
      if (res.ok) return await res.json();
    } catch(e){}
    return null;
  }));
  let best:StockData|null=null;
  let bestDate="";
  results.forEach(d=>{
    if(!d?.stocks) return;
    const f=d.stocks.find((x:StockData)=>x.symbol===sym);
    if(f && (d.scan_date||"")>bestDate){best=f; bestDate=d.scan_date||"";}
  });
  return best;
}
 
// Fetches the 10-year financial history bundle for one symbol — same calls
// and same EV/EBITDA join logic that the main page's useEffect performs.
// Used by the comparison tab to populate the right-hand stock's
// GrowthPanel, ProfitPanel, and ValPanel.
async function loadFmpForStock(symbol:string):Promise<{
  incomes:IncomeRow[]; ratios:RatioYear[]; balanceSheets:BalanceSheetRow[]; cashFlows:CashFlowRow[];
  incomesQ:IncomeRow[]; balanceSheetsQ:BalanceSheetRow[]; cashFlowsQ:CashFlowRow[];
}>{
  const sym=symbol.toUpperCase();
  const [inc,rat,km,bs,cf, incQ, bsQ, cfQ]=await Promise.all([
    fmpFetch("income-statement",{symbol:sym,period:"annual",limit:12}),
    fmpFetch("ratios",{symbol:sym,period:"annual",limit:10}),
    fmpFetch("key-metrics",{symbol:sym,period:"annual",limit:10}),
    fmpFetch("balance-sheet-statement",{symbol:sym,period:"annual",limit:12}),
    fmpFetch("cash-flow-statement",{symbol:sym,period:"annual",limit:12}),
    fmpFetch("income-statement",{symbol:sym,period:"quarter",limit:21}),
    fmpFetch("balance-sheet-statement",{symbol:sym,period:"quarter",limit:21}),
    fmpFetch("cash-flow-statement",{symbol:sym,period:"quarter",limit:21})
  ]);
  
  const mapInc = (r:any) => ({
    date:r.date, calendarYear:r.calendarYear||r.date?.slice(0,4), period:r.period,
    revenue:r.revenue, grossProfit:r.grossProfit,
    operatingIncome:r.operatingIncome, netIncome:r.netIncome,
    epsdiluted:r.epsdiluted||r.epsDiluted, ebitda:r.ebitda,
  });
  const mapBs = (r:any) => ({
    date:r.date, calendarYear:r.calendarYear||r.date?.slice(0,4), period:r.period,
    totalAssets:r.totalAssets, totalLiabilities:r.totalLiabilities,
    totalEquity:r.totalStockholdersEquity, totalDebt:r.totalDebt,
    cashAndCashEquivalents:r.cashAndCashEquivalents,
  });
  const mapCf = (r:any) => ({
    date:r.date, calendarYear:r.calendarYear||r.date?.slice(0,4), period:r.period,
    operatingCashFlow:r.operatingCashFlow, capitalExpenditure:r.capitalExpenditure,
    freeCashFlow:r.freeCashFlow,
  });

  const incomes:IncomeRow[]=inc?.length ? inc.map(mapInc) : [];
  const incomesQ:IncomeRow[]=incQ?.length ? incQ.map(mapInc) : [];
  const balanceSheets:BalanceSheetRow[]=bs?.length ? bs.map(mapBs) : [];
  const balanceSheetsQ:BalanceSheetRow[]=bsQ?.length ? bsQ.map(mapBs) : [];
  const cashFlows:CashFlowRow[]=cf?.length ? cf.map(mapCf) : [];
  const cashFlowsQ:CashFlowRow[]=cfQ?.length ? cfQ.map(mapCf) : [];

  let ratios:RatioYear[]=[];
  if(rat?.length){
    const evByYear=new Map<string,number>();
    (km||[]).forEach((k:any)=>{
      if(k?.fiscalYear!=null && k.evToEBITDA!=null) evByYear.set(String(k.fiscalYear),k.evToEBITDA);
    });
    ratios=rat.map((r:any)=>({...r,evToEBITDA:evByYear.get(String(r.fiscalYear))})) as RatioYear[];
  }
  
  return {incomes,ratios,balanceSheets,cashFlows,incomesQ,balanceSheetsQ,cashFlowsQ};
}
 
// ── QualityValueCard ─────────────────────────────────────────────────────────
// Extracted from inline JSX in StockDetail so it can be re-used in the
// side-by-side comparison tab. Includes Piotroski/Altman rings (diagnostic),
// the v8 quality+value driver metrics, Buffett 5y valuation block, and the
// Price vs Intrinsic target bar. No behavioural change vs the previous
// inline version — same components, same data sources.
function QualityValueCard({s}:{s:StockData}){
  return(
    <Card>
      <SH title="Quality & Value" icon={<Shield size={12}/>}/>
      <div style={{display:"flex",justifyContent:"center",gap:12,margin:"8px 0 12px"}}>
        <ScoreRing value={s.piotroski} label="Piotroski" max={9} color={s.piotroski>=7?"var(--green)":s.piotroski>=5?T.amber:T.red}/>
        <ScoreRing value={Math.round(s.altman_z>20?20:s.altman_z)} label="Altman Z" max={20} color={s.altman_z>3?"var(--green)":s.altman_z>1.8?T.amber:T.red}/>
      </div>
      <div style={{fontSize:9,color:T.textLight,fontFamily:T.mono,textAlign:"center",marginBottom:6,marginTop:-6}}>Diagnostic only</div>
      <Metric label="Net Margin" value={fmtPct(s.net_margin)} color={(s.net_margin??0)>0.20?"var(--green)":(s.net_margin??0)>0.10?T.amber:T.textMuted}/>
      <Metric label="FCF Margin" value={fmtPct(s.fcf_margin)} color={(s.fcf_margin??0)>0.15?"var(--green)":(s.fcf_margin??0)>0.08?T.amber:T.textMuted}/>
      <Metric label="ROE (avg)" value={fmtPct(s.roe_avg)} color={s.roe_avg>0.15?"var(--green)":T.textMuted} sub={s.roe_consistent?"✓ Consistent >15%":""}/>
      <Metric label="ROIC (avg)" value={fmtPct(s.roic_avg)} color={s.roic_avg>0.12?"var(--green)":T.textMuted}/>
      <Metric label="Gross Margin" value={fmtPct(s.gross_margin)} color={s.gross_margin>0.5?"var(--green)":T.textMuted} sub={s.gross_margin_trend==="expanding"?"↑ Expanding":s.gross_margin_trend==="contracting"?"↓ Contracting":"→ Stable"}/>
      <Metric label="P/FCF" value={(s.p_fcf??0)>0?(s.p_fcf as number).toFixed(1)+"x":"—"} color={(s.p_fcf??0)>0&&(s.p_fcf as number)<25?"var(--green)":(s.p_fcf??0)>0&&(s.p_fcf as number)<40?T.amber:T.textMuted}/>
      <Metric label="Earnings Yield" value={fmtPct(s.earnings_yield)} color={(s.earnings_yield??0)>0.05?"var(--green)":(s.earnings_yield??0)>0.03?T.amber:T.textMuted}/>
      <BuffettBlock s={s}/>
      <TargetBar price={s.price} target={s.target} bvps={s.buffett_fair_value??0} currency={s.currency}/>
    </Card>
  );
}
 
// ── ComparisonTab ────────────────────────────────────────────────────────────
// Side-by-side analysis of two stocks. "A" is whatever's loaded on the
// page (stockA + already-fetched fmpA from StockDetail). "B" is picked
// by the user — we load its scan data and FMP bundle in parallel on submit.
//
// Empty state: prompt for ticker. Loaded state: each scan-derived card and
// FMP table is rendered twice (left = A, right = B) so the user can read
// metrics directly across. 5-factor radar at top for at-a-glance composite.
//
// Scope: comparison stock must be in the current scan universe. Tickers
// outside it show an error and the user is prompted to pick another.
function ComparisonTab({stockA,fmpA}:{
  stockA:StockData;
  fmpA:{
    incomes:IncomeRow[]; ratios:RatioYear[]; balanceSheets:BalanceSheetRow[]; cashFlows:CashFlowRow[];
    incomesQ:IncomeRow[]; balanceSheetsQ:BalanceSheetRow[]; cashFlowsQ:CashFlowRow[];
  };
}){
  const [input,setInput]=useState("");
  const [stockB,setStockB]=useState<StockData|null>(null);
  const [fmpB,setFmpB]=useState<{
    incomes:IncomeRow[]; ratios:RatioYear[]; balanceSheets:BalanceSheetRow[]; cashFlows:CashFlowRow[];
    incomesQ:IncomeRow[]; balanceSheetsQ:BalanceSheetRow[]; cashFlowsQ:CashFlowRow[];
  }|null>(null);
  const [loading,setLoading]=useState(false);
  const [error,setError]=useState("");
 
  async function handleSubmit(){
    const sym=input.trim().toUpperCase().replace(/[^A-Z0-9.\-]/g,"");
    setError("");
    if(!sym){setError("Enter a ticker"); return;}
    if(sym===stockA.symbol){setError("Same stock — pick a different one"); return;}
    setLoading(true);
    try{
      const [scan,fmp]=await Promise.all([
        loadStockFromScans(sym),
        loadFmpForStock(sym),
      ]);
      if(!scan){
        setError(`${sym} isn't in the current scan universe. Currently SP500 only — try a large-cap US ticker.`);
        setLoading(false);
        return;
      }
      setStockB(scan);
      setFmpB(fmp);
    }catch(e:any){
      setError(`Failed to load ${sym}: ${e?.message||"unknown error"}`);
    }finally{
      setLoading(false);
    }
  }
 
  function reset(){
    setStockB(null);
    setFmpB(null);
    setInput("");
    setError("");
  }
 
  // Empty state — prompt for ticker
  if(!stockB){
    return(
      <Card>
        <SH title="Side-by-Side Comparison" icon={<Activity size={12}/>} sub="Compare any two stocks across all factor cards and multi-year tables"/>
        <div style={{padding:"32px 24px",textAlign:"center"}}>
          <div style={{fontSize:12,color:T.textMuted,fontFamily:T.sans,lineHeight:1.6,marginBottom:20,maxWidth:480,margin:"0 auto 20px"}}>
            Pick a ticker to compare against <strong style={{color:T.text}}>{stockA.symbol}</strong>. You'll see Quality &amp; Value, Growth, Smart Money, Momentum, plus 10-year Growth Rates, Profitability, and Valuation History — both stocks laid out left/right.
          </div>
          <div style={{display:"flex",justifyContent:"center",gap:8,marginBottom:12}}>
            <input autoFocus value={input}
              onChange={e=>{setInput(e.target.value); setError("");}}
              onKeyDown={e=>{if(e.key==="Enter") handleSubmit();}}
              placeholder="e.g. MSFT"
              style={{padding:"6px 12px",border:`1px solid ${T.cardBorder}`,borderRadius:5,fontSize:12,fontFamily:T.mono,width:120,outline:"none"}}/>
            <button onClick={handleSubmit} disabled={loading}
              style={{background:T.green,color:"var(--bg-surface)",border:"none",padding:"6px 16px",borderRadius:5,fontSize:11,fontFamily:T.mono,fontWeight:600,cursor:loading?"wait":"pointer",opacity:loading?0.6:1}}>
              {loading?"Loading…":"Compare"}
            </button>
          </div>
          {error && <div style={{fontSize:11,color:T.amber,fontFamily:T.mono,marginTop:8,lineHeight:1.4,maxWidth:420,margin:"8px auto 0"}}>{error}</div>}
        </div>
      </Card>
    );
  }
 
  // Loaded state — side-by-side render
  const ComparisonHeader=({s,isLeft}:{s:StockData; isLeft:boolean})=>{
    // v1.2 (May 2026): single BUY/HOLD/SELL signal badge removed.
    // Composite score (right side of header) is now the only summary signal.
    const compColor=(s.composite??0)>0.6?T.green:(s.composite??0)>0.4?T.text:T.red;
    return(
      <Card>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:8}}>
          <div>
            <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:4}}>
              <span style={{fontSize:20,fontWeight:700,color:T.text,fontFamily:T.mono}}>{s.symbol}</span>
            </div>
            <div style={{fontSize:18,fontWeight:600,color:T.text,fontFamily:T.mono}}>{fmtPrice(s.price,s.currency)} <span style={{fontSize:11,color:T.textMuted,fontWeight:400}}>{s.currency}</span></div>
          </div>
          <div style={{textAlign:"right"}}>
            <div style={{fontSize:9,color:T.textMuted,fontFamily:T.mono,marginBottom:2}}>COMPOSITE</div>
            <div style={{fontSize:24,fontWeight:700,fontFamily:T.mono,color:compColor}}>{(s.composite??0).toFixed(2)}</div>
          </div>
        </div>
        {!isLeft && (
          <button onClick={reset} style={{marginTop:6,fontSize:10,fontFamily:T.mono,color:T.green,background:"none",border:`1px solid ${T.greenBorder}`,padding:"3px 10px",borderRadius:4,cursor:"pointer",fontWeight:600}}>
            Change ticker
          </button>
        )}
      </Card>
    );
  };
 
  return(
    <>
      {/* Symbol header strip */}
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14,marginBottom:14}}>
        <ComparisonHeader s={stockA} isLeft={true}/>
        <ComparisonHeader s={stockB} isLeft={false}/>
      </div>
 
      {/* 5-factor radar */}
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14,marginBottom:14}}>
        <Card>
          <SH title={`${stockA.symbol} · 5-Factor`}/>
          <div style={{display:"flex",justifyContent:"center"}}>
            <FactorRadar scores={readFactorsV8(stockA,"momentum")} size={220}/>
          </div>
        </Card>
        <Card>
          <SH title={`${stockB.symbol} · 5-Factor`}/>
          <div style={{display:"flex",justifyContent:"center"}}>
            <FactorRadar scores={readFactorsV8(stockB,"momentum")} size={220}/>
          </div>
        </Card>
      </div>
 
      {/* Quality & Value */}
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14,marginBottom:14}}>
        <QualityValueCard s={stockA}/>
        <QualityValueCard s={stockB}/>
      </div>
 
      {/* Smart Money */}
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14,marginBottom:14}}>
        <SmartMoneyCard s={stockA}/>
        <SmartMoneyCard s={stockB}/>
      </div>
 
      {/* Momentum */}
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14,marginBottom:14}}>
        <MomentumPanel s={stockA}/>
        <MomentumPanel s={stockB}/>
      </div>
 
      {/* Growth Rates table (multi-year, FMP-sourced) */}
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14,marginBottom:14}}>
        <GrowthPanel incomes={fmpA.incomes} loading={false} ratios={fmpA.ratios}/>
        <GrowthPanel incomes={fmpB?.incomes||[]} loading={!fmpB} ratios={fmpB?.ratios}/>
      </div>
 
      {/* Profitability table */}
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14,marginBottom:14}}>
        <ProfitPanel ratios={fmpA.ratios} loading={false}/>
        <ProfitPanel ratios={fmpB?.ratios||[]} loading={!fmpB}/>
      </div>
 
      {/* Valuation History table */}
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14,marginBottom:14}}>
        <ValPanel ratios={fmpA.ratios} loading={false}/>
        <ValPanel ratios={fmpB?.ratios||[]} loading={!fmpB}/>
      </div>
    </>
  );
}
// ── Main Page ──────────────────────────────────────────────────────────────────
// ── TrackRecordTable: 10-year financial history per the Buffettology
// methodology spreadsheet. All data sourced from s.buffett_history (no
// extra API calls — populated by screener_v6 at scan time).
function TrackRecordTable({s}:{s:StockData}){
  const hist = s.buffett_history;
  if(!hist?.rows?.length){
    return (
      <Card>
        <SH title="Track Record" icon={<BarChart2 size={12}/>}/>
        <div style={{padding:30,textAlign:"center",color:T.textLight,fontSize:11,fontFamily:T.mono}}>
          No track record data available for this stock.
        </div>
      </Card>
    );
  }

  const rows = hist.rows;
  const c = s.currency==="EUR"?"€":s.currency==="GBP"?"£":"$";
  const fmtN = (n:number|null|undefined, d=2) => n==null?"—":n.toFixed(d);
  const fmtP = (n:number|null|undefined, d=1) => n==null?"—":(n*100).toFixed(d)+"%";
  const fmtBn = (n:number|null|undefined) => n==null?"—":(n>=1000?`${(n/1000).toFixed(1)}B`:`${n.toFixed(0)}M`);

  // Compute per-year derivatives
  const derived = rows.map((r,i)=>{
    const prev = i>0 ? rows[i-1] : null;
    const bookYieldShare = prev && prev.bvps>0 ? r.eps/prev.bvps : null;
    const roe = r.equity_mm>0 ? r.net_income_mm/r.equity_mm : null;
    const payout = r.eps>0 && r.dps>=0 ? r.dps/r.eps : null;
    const retention = payout!=null ? 1-payout : null;
    return {...r, bookYieldShare, roe, payout, retention};
  });

  // CAGR helper
  const cagr = (key:string) => {
    if(rows.length<2) return null;
    const first = (rows[0] as any)[key];
    const last = (rows[rows.length-1] as any)[key];
    if(!first || !last || first<=0 || last<=0) return null;
    return Math.pow(last/first, 1/(rows.length-1)) - 1;
  };
  const cumGrowth = (key:string) => {
    if(rows.length<2) return null;
    const first = (rows[0] as any)[key];
    const last = (rows[rows.length-1] as any)[key];
    if(!first || !last || first<=0) return null;
    return (last - first) / first;
  };

 // Median helper for derived series
  const median = (arr:(number|null|undefined)[]) => {
    const valid = arr.filter((v):v is number=>v!=null);
    if(!valid.length) return null;
    return [...valid].sort((a,b)=>a-b)[Math.floor(valid.length/2)];
  };

  type RowDef = {
    label:string;
    fn:(r:any)=>number|null|undefined;
    format:(v:number|null|undefined)=>string;
    showCagr?:boolean;
    showCum?:boolean;
    showMedian?:boolean;
    cagrKey?:string;
  };
  const sections:{title:string; rows:RowDef[]}[] = [
    {title:"INPUT DATA", rows:[
      {label:"Book Value per Share (BV)", fn:r=>r.bvps, format:v=>v==null?"—":c+fmtN(v), showCagr:true, showCum:true, cagrKey:"bvps"},
      {label:"Earnings per Share (EPS)", fn:r=>r.eps, format:v=>v==null?"—":c+fmtN(v), showCagr:true, showCum:true, cagrKey:"eps"},
      {label:"Dividends per Share", fn:r=>r.dps, format:v=>v==null?"—":c+fmtN(v), showCagr:true, showCum:true, cagrKey:"dps"},
      {label:"Shares Out (Millions)", fn:r=>r.shares_mm, format:v=>v==null?"—":fmtN(v,1), showCagr:true, showCum:true, cagrKey:"shares_mm"},
      {label:"P/E (year-end)", fn:r=>r.pe, format:v=>v==null?"—":fmtN(v,1)+"x", showMedian:true},
      {label:"Revenue", fn:r=>r.revenue_mm, format:v=>v==null?"—":c+fmtBn(v), showCagr:true, showCum:true, cagrKey:"revenue_mm"},
      {label:"Net Income", fn:r=>r.net_income_mm, format:v=>v==null?"—":c+fmtBn(v), showCagr:true, showCum:true, cagrKey:"net_income_mm"},
      {label:"Shareholder Equity", fn:r=>r.equity_mm, format:v=>v==null?"—":c+fmtBn(v), showCagr:true, showCum:true, cagrKey:"equity_mm"},
    ]},
    {title:"CALCULATED", rows:[
      {label:"Book Yield (per Share)", fn:(r:any)=>r.bookYieldShare, format:v=>fmtP(v,1), showMedian:true},
      {label:"Book Yield (ROE)", fn:(r:any)=>r.roe, format:v=>fmtP(v,1), showMedian:true},
      {label:"Payout Ratio", fn:(r:any)=>r.payout, format:v=>fmtP(v,1), showMedian:true},
      {label:"Retention Ratio", fn:(r:any)=>r.retention, format:v=>fmtP(v,1), showMedian:true},
    ]},
  ];

  const TRACK_TOOLTIPS:Record<string,string> = {
    "Book Value per Share (BV)": "Steadily rising BVPS indicates wealth creation over time.",
    "Earnings per Share (EPS)": "Consistent, predictable growth in EPS is the hallmark of a compounder.",
    "Dividends per Share": "A strong dividend growth history signals management confidence.",
    "Shares Out (Millions)": "shares out reducing over time --> strong buybacks.",
    "P/E (year-end)": "A stable or low P/E allows EPS growth to drive share price appreciation.",
    "Revenue": "Top-line growth fuels the entire income statement.",
    "Net Income": "Bottom-line profitability and its long-term compounding rate.",
    "Shareholder Equity": "Total net assets; steady compounding is a strong signal.",
    "Book Yield (per Share)": "EPS / prior-year BVPS. High yield implies efficient capital use.",
    "Book Yield (ROE)": "Net Income / Equity. >15% consistently is the quality threshold.",
    "Payout Ratio": "Dividends / EPS. Too high (>80%) leaves no room for reinvestment.",
    "Retention Ratio": "1 - Payout Ratio. Reinvested capital driving future growth.",
  };

  const cellStyle:React.CSSProperties = {padding:"6px 8px", textAlign:"right", fontSize:10, fontFamily:T.mono, borderBottom:`1px solid ${T.divider}`, whiteSpace:"nowrap"};
  const headStyle:React.CSSProperties = {...cellStyle, color:T.textMuted, fontWeight:600, fontSize:9};
  const labelStyle:React.CSSProperties = {...cellStyle, textAlign:"left", color:T.text, fontWeight:600, position:"sticky", left:0, background:T.card, zIndex:1};

  return (
    <Card>
      <SH title="Track Record" icon={<BarChart2 size={12}/>} sub={`${rows.length} years · ${rows[0].year}–${rows[rows.length-1].year}`}/>

      {/* Projection summary at top */}
      {s.buffett_evaluated && (
        <div style={{padding:"10px 12px",borderRadius:6,background:T.greenLight,border:`1px solid ${T.greenBorder}`,marginBottom:14,fontSize:11,fontFamily:T.mono,lineHeight:1.6}}>
          <div style={{fontWeight:600,color:T.green,fontSize:9,letterSpacing:"0.08em",marginBottom:4}}>VALUE 5Y PROJECTION</div>
          Method: <b>Min Growth (EPS, BVPS, Yield)</b> · 
          g = {((s.buffett_g_assumed||0)*100).toFixed(1)}% · 
          P/E = {(s.buffett_pe_median||0).toFixed(1)}x<br/>
          EPS₅ = {c}{(s.buffett_eps_5y||0).toFixed(2)} → 
          Future Price = <b>{c}{(s.buffett_future_price||0).toFixed(2)}</b> → 
          Fair Value today = <b>{c}{(s.buffett_fair_value||0).toFixed(2)}</b> 
          ({(s.intrinsic_upside||0)>=0?"+":""}{(s.intrinsic_upside||0).toFixed(1)}% MoS)
        </div>
      )}

      <div style={{overflowX:"auto"}}>
        <table style={{width:"100%",borderCollapse:"collapse"}}>
          <thead>
            <tr>
              <th style={{...headStyle, textAlign:"left", position:"sticky", left:0, background:T.card, zIndex:2}}>Metric</th>
              {rows.map(r=><th key={r.year} style={headStyle}>{r.year}</th>)}
              <th style={{...headStyle, color:T.green, fontWeight:700}}>CAGR</th>
              <th style={{...headStyle, color:T.green, fontWeight:700}}>Cum. Growth</th>
              <th style={{...headStyle, color:T.purple, fontWeight:700}}>Median</th>
            </tr>
          </thead>
          <tbody>
            {sections.map(sec=>(
              <React.Fragment key={sec.title}>
                <tr>
                  <td colSpan={rows.length+4} style={{...cellStyle, textAlign:"left", color:T.textMuted, fontWeight:600, fontSize:9, paddingTop:14, paddingBottom:6, letterSpacing:"0.08em"}}>{sec.title}</td>
                </tr>
                {sec.rows.map((rd,i)=>{
                  const series = derived.map(d=>rd.fn(d));
                  const cagrVal = rd.showCagr && rd.cagrKey ? cagr(rd.cagrKey) : null;
                  const cumVal = rd.showCum && rd.cagrKey ? cumGrowth(rd.cagrKey) : null;
                  const medVal = rd.showMedian ? median(series) : null;
                  return (
                    <tr key={i}>
                      <td style={labelStyle}>
                        <span title={TRACK_TOOLTIPS[rd.label]||""} style={{cursor:TRACK_TOOLTIPS[rd.label]?"help":"default",borderBottom:TRACK_TOOLTIPS[rd.label]?`1px dotted ${T.textLight}`:"none"}}>
                          {rd.label}
                        </span>
                      </td>
                      {series.map((v,j)=><td key={j} style={cellStyle}>{rd.format(v)}</td>)}
                      <td style={{...cellStyle,color:T.green,fontWeight:600}}>{cagrVal!=null?fmtP(cagrVal):"—"}</td>
                      <td style={{...cellStyle,color:T.green,fontWeight:600}}>{cumVal!=null?fmtP(cumVal):"—"}</td>
                      <td style={{...cellStyle,color:T.purple,fontWeight:600}}>{medVal!=null?rd.format(medVal):"—"}</td>
                    </tr>
                  );
                })}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{marginTop:12,fontSize:9,color:T.textLight,fontFamily:T.mono,lineHeight:1.5}}>
        Methodology adapted from "The Value Approach to Valuation". Book Yield (per share) = EPS / prior-year BVPS. Book Yield (ROE) = NetIncome / Equity. Retention = 1 − Payout. P/E shown is fiscal-year-end ratio; the spreadsheet's intra-year high/low not available without per-day price history.
      </div>
    </Card>
  );
}

function ScoringMethodologyCard() {
  return (
    <Card style={{ marginBottom: 16 }}>
      <SH title="Scoring Analysis & Methodology" icon={<Activity size={12} />} />
      <div style={{ fontSize: 11, color: T.textMuted, lineHeight: 1.6, marginTop: 12, padding: "10px 14px", borderRadius: 6, background: T.bg, border: `1px solid ${T.cardBorder}`, fontFamily: T.mono }}>
        Reference — how the per-stock <strong style={{ color: T.text }}>scoring engines</strong> are built. The live, tradeable books (Apex / Value / Disruptor + the Catalyst sleeve) are explained under <strong style={{ color: T.text }}>Discover → Speculair → “How the baskets work”</strong>. Of the factors below, <strong style={{ color: T.text }}>Smart Money</strong> remains a live 15% sub-factor of the v8 composite; the others are historical engine descriptions.
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 30, marginTop: 16 }}>
        <div>
          <h4 style={{ fontSize: 13, fontWeight: 700, color: T.text, marginBottom: 8, borderBottom: `1px solid ${T.divider}`, paddingBottom: 6 }}>MOMENTUM COMPOSITE</h4>
          <p style={{ fontSize: 12, color: T.textMuted, lineHeight: 1.6, marginBottom: 8 }}>
            Our default engine. A balanced 5-factor model designed to identify established market leaders currently exhibiting strong uptrends. It blends technical price action with fundamental quality and smart money footprints to capture sustainable momentum while mitigating downside risk.
          </p>
          <div style={{ fontSize: 11, color: T.text, lineHeight: 1.5, background: T.bg, padding: "10px 14px", borderRadius: 6, border: `1px solid ${T.cardBorder}` }}>
            <strong style={{ color: T.green }}>High-Scoring Signals:</strong>
            <ul style={{ margin: "6px 0 0", paddingLeft: 20 }}>
              <li><strong>Technical Momentum (25%):</strong> RSI between 55-70 (strong but not overbought), MACD bullish crossover, strong ADX (&gt;25).</li>
              <li><strong>Quality (20%):</strong> High Piotroski F-Score (7-9), safe Altman Z-Score (&gt;3.0), strong and expanding Gross Margins.</li>
              <li><strong>Growth (20%):</strong> Revenue and EPS CAGR &gt; 15% over 3 years, accelerating YoY free cash flow.</li>
              <li><strong>Value (20%):</strong> High Owner Earnings Yield (&gt;4.5%), trading below historical P/FCF medians.</li>
              <li><strong>Smart Money (15%):</strong> Rising institutional concentration, net positive insider transactions, and bullish management transcripts.</li>
            </ul>
          </div>
        </div>
        <div>
          <h4 style={{ fontSize: 13, fontWeight: 700, color: T.text, marginBottom: 8, borderBottom: `1px solid ${T.divider}`, paddingBottom: 6 }}>COMPOUNDER (US/GLOBAL)</h4>
          <p style={{ fontSize: 12, color: T.textMuted, lineHeight: 1.6, marginBottom: 8 }}>
            A precision quality-first engine focused on long-term capital appreciation. It filters for businesses with dominant market positions, robust pricing power, and impenetrable balance sheets. This model systematically rejects high-leverage and commodity-driven businesses to focus on sustainable compounders.
          </p>
          <div style={{ fontSize: 11, color: T.text, lineHeight: 1.5, background: T.bg, padding: "10px 14px", borderRadius: 6, border: `1px solid ${T.cardBorder}` }}>
            <strong style={{ color: T.green }}>High-Scoring Signals:</strong>
            <ul style={{ margin: "6px 0 0", paddingLeft: 20 }}>
              <li><strong>Return on Equity (ROE):</strong> Consistent 3-year average ROE &gt; 15%, indicating efficient compounding of shareholder capital.</li>
              <li><strong>Pricing Power:</strong> Expanding Gross Margins and Operating Margins (OpMargin Δ &gt; 0) over a 3-year period.</li>
              <li><strong>Capital Efficiency:</strong> Low Price-to-Book (P/B) relative to ROE, indicating the market has not fully priced in the compounding potential.</li>
              <li><strong>Balance Sheet:</strong> Low debt-to-equity and strong interest coverage, ensuring survival through macroeconomic cycles.</li>
            </ul>
          </div>
        </div>
        <div>
          <h4 style={{ fontSize: 13, fontWeight: 700, color: T.text, marginBottom: 8, borderBottom: `1px solid ${T.divider}`, paddingBottom: 6 }}>FALLEN ANGEL</h4>
          <p style={{ fontSize: 12, color: T.textMuted, lineHeight: 1.6, marginBottom: 8 }}>
            A contrarian mean-reversion engine designed to identify fundamentally sound businesses that have suffered severe short-term price dislocations. It seeks out "babies thrown out with the bathwater"—companies whose operational health remains intact despite negative market sentiment.
          </p>
          <div style={{ fontSize: 11, color: T.text, lineHeight: 1.5, background: T.bg, padding: "10px 14px", borderRadius: 6, border: `1px solid ${T.cardBorder}` }}>
            <strong style={{ color: T.green }}>High-Scoring Signals:</strong>
            <ul style={{ margin: "6px 0 0", paddingLeft: 20 }}>
              <li><strong>Price Dislocation:</strong> Trading near 52-week lows (0-20% of range) with deeply oversold RSI (&lt;30).</li>
              <li><strong>Fundamental Floor:</strong> Piotroski F-Score &gt; 6, ensuring the business is not structurally failing.</li>
              <li><strong>Valuation Compression:</strong> Price-to-Sales (P/S) and P/E ratios trading significantly below their 5-year historical medians.</li>
              <li><strong>Reversal Catalysts:</strong> Bullish divergence in MACD or stabilization in On-Balance Volume (OBV) amidst price weakness.</li>
            </ul>
          </div>
        </div>
        <div>
          <h4 style={{ fontSize: 13, fontWeight: 700, color: T.text, marginBottom: 8, borderBottom: `1px solid ${T.divider}`, paddingBottom: 6 }}>V8 SMART MONEY</h4>
          <p style={{ fontSize: 12, color: T.textMuted, lineHeight: 1.6, marginBottom: 8 }}>
            A sophisticated alternative-data engine that tracks institutional footprints. It ignores retail noise and focuses entirely on where the most informed capital is flowing, analyzing regulatory filings, congressional trades, and management sentiment.
          </p>
          <div style={{ fontSize: 11, color: T.text, lineHeight: 1.5, background: T.bg, padding: "10px 14px", borderRadius: 6, border: `1px solid ${T.cardBorder}` }}>
            <strong style={{ color: T.green }}>High-Scoring Signals:</strong>
            <ul style={{ margin: "6px 0 0", paddingLeft: 20 }}>
              <li><strong>13F Accumulation:</strong> High velocity of new institutional positions and increasing ownership percentage Quarter-over-Quarter.</li>
              <li><strong>Congressional Trading:</strong> Net buying activity by House and Senate members (recency-weighted).</li>
              <li><strong>Management Tone:</strong> High positive sentiment scores extracted from earnings call transcripts via NLP.</li>
              <li><strong>Insider Conviction:</strong> Cluster buying by multiple C-level executives or directors on the open market.</li>
            </ul>
          </div>
        </div>
      </div>
    </Card>
  );
}

function SpeculairDebateCard({ debateData, debateHistory = [], histIdx = 0, setHistIdx }: { debateData: any; debateHistory?: any[]; histIdx?: number; setHistIdx?: (i: number) => void }) {
  if (!debateData) return null;

  const type = debateData.type || "methodology_pick";
  const conviction = debateData.conviction || 3;
  const sourceMethodologies = debateData.source_methodologies || [];

  // Colors & Header configurations
  let bannerBg = "rgba(139, 92, 246, 0.05)";
  let bannerBorder = `2px solid ${T.purple}`;
  let bannerTitle = "SPECULAIR DEBATE CANDIDATE";
  let bannerIcon = <Brain size={18} color={T.purple} />;
  let bannerSub = `Debated Methodology Pick · Conviction Score: ${conviction}/5`;

  if (type === "apex") {
    bannerBg = "rgba(20, 184, 122, 0.05)";
    bannerBorder = `2px solid ${T.green}`;
    bannerTitle = "SPECULAIR APEX ALLOCATION";
    bannerIcon = <Star size={18} color={T.amber} fill={T.amber} style={{ filter: "drop-shadow(0 0 4px var(--amber))" }} />;
    bannerSub = `Apex Basket Position · Director Conviction: ${conviction}/100`;
  } else if (type === "watchlist") {
    bannerBg = "rgba(249, 115, 22, 0.05)";
    bannerBorder = `2px solid var(--orange)`;
    bannerTitle = "CAPITULATION WATCHLIST SETUP";
    bannerIcon = <AlertTriangle size={18} color="var(--orange)" />;
    bannerSub = `Watch & Wait Setup · Director Conviction: ${conviction}/100`;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* ── Status Banner ── */}
      <Card style={{ background: bannerBg, border: bannerBorder, padding: "20px 24px", borderRadius: 12, boxShadow: "0 4px 20px rgba(0,0,0,0.15)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {bannerIcon}
          <div>
            <h3 style={{ margin: 0, fontSize: 16, fontWeight: 800, letterSpacing: "0.05em", color: T.text, fontFamily: T.mono }}>{bannerTitle}</h3>
            <p style={{ margin: "4px 0 0", fontSize: 11, color: T.textMuted, fontFamily: T.mono }}>{bannerSub}</p>
          </div>
        </div>

        {/* ── Scale-out tier — the Scale-Director's verdict on this name's role in the AI build-out, set AFTER the debate ── */}
        {debateData.scale && (()=>{const sc=debateData.scale;const tc=sc.tier==="CORE"?"#2d7a4f":sc.tier==="LEVER"?"#8b5cf6":sc.tier==="TACTICAL"?"#d97706":"#9ca3af";return(
          <div style={{ marginTop: 14, paddingTop: 12, borderTop: `1px solid ${T.divider}` }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <span style={{ fontSize: 11, padding: "3px 10px", borderRadius: 4, border: `1px solid ${tc}66`, color: tc, background: `${tc}14`, fontFamily: T.mono, fontWeight: 800, letterSpacing: "0.05em", display: "inline-flex", alignItems: "center", gap: 6 }}>
                <Layers size={12} /> SCALE-OUT · {sc.tier}{sc.conviction != null ? ` ${sc.conviction}/100` : ""}
              </span>
              <span style={{ fontSize: 10, fontFamily: T.mono, color: T.textMuted }}>{sc.basket_label || sc.basket} layer</span>
              {sc.posture && <span style={{ fontSize: 10, fontFamily: T.mono, color: T.textLight }}>· {String(sc.posture).replace(/_/g, " ")}</span>}
              {sc.valuation_posture && <span style={{ fontSize: 10, fontFamily: T.mono, color: T.textLight }}>· {sc.valuation_posture} vs build-out</span>}
              {sc.expected_return_pct != null && <span style={{ fontSize: 10, fontFamily: T.mono, color: sc.expected_return_pct >= 0 ? T.green : T.red }}>· {sc.expected_return_pct >= 0 ? "+" : ""}{Number(sc.expected_return_pct).toFixed(0)}% to SoP</span>}
            </div>
            {sc.role && <p style={{ margin: "8px 0 0", fontSize: 11, color: T.text, fontFamily: T.mono, lineHeight: 1.5 }}>{sc.role}</p>}
            {sc.rationale && <p style={{ margin: "4px 0 0", fontSize: 10.5, color: T.textMuted, fontFamily: T.mono, lineHeight: 1.5 }}>{sc.rationale}</p>}
            {debateData.skeptic_verdict && (
              <p style={{ margin: "6px 0 0", fontSize: 10, fontFamily: T.mono, color: debateData.skeptic_verdict === "REFUTED" ? T.red : debateData.skeptic_verdict === "CONFIRMED" ? T.green : T.amber }}>
                Skeptic: {debateData.skeptic_verdict}{debateData.skeptic_kill_fact ? ` — ${debateData.skeptic_kill_fact}` : ""}
              </p>
            )}
          </div>
        );})()}

        {/* ── Catalyst strip — event-driven special-sit from the Basket-13 funnel, run through the full debate ── */}
        {debateData.catalyst && (()=>{const c=debateData.catalyst;const dc=Number(c.director_conviction)||0;const tc=(c.cro_verdict==="A"&&dc>=80)?"#2d7a4f":c.cro_verdict==="A"?"#2563eb":dc>=50?"#d97706":"#9ca3af";return(
          <div style={{ marginTop: 14, paddingTop: 12, borderTop: `1px solid ${T.divider}` }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <span style={{ fontSize: 11, padding: "3px 10px", borderRadius: 4, border: `1px solid ${tc}66`, color: tc, background: `${tc}14`, fontFamily: T.mono, fontWeight: 800, letterSpacing: "0.05em", display: "inline-flex", alignItems: "center", gap: 6 }}>
                <Zap size={12} /> CATALYST · {c.driver}{c.cro_verdict ? ` · verdict ${c.cro_verdict}` : ""}{c.cro_conviction != null ? ` (${c.cro_conviction}/5)` : ""}
              </span>
              {c.director_conviction != null && <span style={{ fontSize: 10, fontFamily: T.mono, color: tc, fontWeight: 700 }}>Director {c.director_conviction}/100</span>}
              {c.catalyst_status && <span style={{ fontSize: 10, fontFamily: T.mono, color: T.textLight }}>· {c.catalyst_status}</span>}
              {c.dated_milestone && <span style={{ fontSize: 10, fontFamily: T.mono, color: T.textLight }}>· {c.dated_milestone}</span>}
              {c.posture && <span style={{ fontSize: 10, fontFamily: T.mono, color: T.textLight }}>· {String(c.posture).replace(/_/g, " ")}</span>}
              {c.expected_return_pct != null && <span style={{ fontSize: 10, fontFamily: T.mono, color: c.expected_return_pct >= 0 ? T.green : T.red }}>· {c.expected_return_pct >= 0 ? "+" : ""}{Number(c.expected_return_pct).toFixed(0)}% to target</span>}
            </div>
            {(c.live_price != null && c.target_px != null) && <p style={{ margin: "8px 0 0", fontSize: 10.5, color: T.textMuted, fontFamily: T.mono }}>live {c.live_price} → target {c.target_px}{c.downside_floor != null ? ` / floor ${c.downside_floor}` : ""}</p>}
            {c.binding_reason && <p style={{ margin: "4px 0 0", fontSize: 11, color: T.text, fontFamily: T.mono, lineHeight: 1.5 }}>{c.binding_reason}</p>}
            {debateData.skeptic_verdict && <p style={{ margin: "6px 0 0", fontSize: 10, fontFamily: T.mono, color: debateData.skeptic_verdict === "REFUTED" ? T.red : debateData.skeptic_verdict === "CONFIRMED" ? T.green : T.amber }}>Skeptic: {debateData.skeptic_verdict}{debateData.skeptic_kill_fact ? ` — ${debateData.skeptic_kill_fact}` : ""}</p>}
          </div>
        );})()}

        {/* ── Debate history time-travel: scroll past Opus debates by date ── */}
        {debateHistory && debateHistory.length > 0 && (
          <div style={{ marginTop: 14, paddingTop: 12, borderTop: `1px solid ${T.divider}`, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <Clock size={13} color={T.textMuted} />
            <span style={{ fontSize: 10, fontFamily: T.mono, color: T.textMuted, textTransform: "uppercase", letterSpacing: "0.05em" }}>Debate history</span>
            <select value={histIdx} onChange={(e) => setHistIdx && setHistIdx(Number(e.target.value))}
              style={{ fontSize: 11, fontFamily: T.mono, background: T.card, color: T.text, border: `1px solid ${T.divider}`, borderRadius: 4, padding: "3px 8px", cursor: "pointer" }}>
              {debateHistory.map((h: any, i: number) => (
                <option key={i} value={i}>
                  {h.date}{i === 0 ? " · latest" : ""} — {h.verdict || "—"} / conv {h.conviction ?? "—"}{h.transcript_source === "web" ? " · web-sourced" : ""}
                </option>
              ))}
            </select>
            {histIdx > 0 && (
              <span style={{ fontSize: 9, padding: "2px 6px", borderRadius: 4, background: "rgba(217, 119, 6, 0.12)", color: T.amber, fontFamily: T.mono, border: `1px solid rgba(217,119,6,0.25)` }}>
                VIEWING PAST DEBATE — {debateData._histDate}
              </span>
            )}
          </div>
        )}

        {/* ── Entry price & details if Apex/Watchlist ── */}
        {(debateData.entry_price > 0 || sourceMethodologies.length > 0) && (
          <div style={{ marginTop: 16, paddingTop: 16, borderTop: `1px solid ${T.divider}`, display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
            {debateData.entry_price > 0 && (
              <div style={{ fontSize: 11, fontFamily: T.mono, color: T.textLight }}>
                Entry Date: <strong style={{ color: T.text }}>{debateData.entry_date}</strong> · Entry Price: <strong style={{ color: T.green }}>${debateData.entry_price.toFixed(2)}</strong>
              </div>
            )}
            {sourceMethodologies.length > 0 && (
              <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                <span style={{ fontSize: 10, fontFamily: T.mono, color: T.textMuted }}>Methodologies:</span>
                {sourceMethodologies.map((m: string) => (
                  <span key={m} style={{ fontSize: 9, padding: "2px 6px", borderRadius: 4, background: "rgba(59, 130, 246, 0.12)", color: T.blue, fontFamily: T.mono, border: `1px solid rgba(59, 130, 246, 0.2)` }}>
                    {m.replace(/_/g, " ").toUpperCase()}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}
      </Card>

      {/* ── Expectations Arbitrage & Forcing Function ── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        {/* Consensus Delta */}
        <Card style={{ flex: 1, minWidth: 280, display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: T.amber, textTransform: "uppercase", marginBottom: 12, paddingBottom: 6, borderBottom: `1px solid ${T.divider}` }}>
              <TrendingDown size={12} /> Expectations Arbitrage (Consensus Delta)
            </div>
            <p style={{ fontSize: 12, color: T.text, lineHeight: 1.6, fontFamily: T.sans, margin: 0, textAlign: "justify" }}>
              {debateData.consensus_delta || "No consensus delta recorded."}
            </p>
          </div>
        </Card>

        {/* Forcing Function */}
        <Card style={{ flex: 1, minWidth: 280, display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: T.green, textTransform: "uppercase", marginBottom: 12, paddingBottom: 6, borderBottom: `1px solid ${T.divider}` }}>
              <Zap size={12} /> TURNAROUND FORCING FUNCTION (CATALYST)
            </div>
            <p style={{ fontSize: 12, color: T.text, lineHeight: 1.6, fontFamily: T.sans, margin: 0, textAlign: "justify" }}>
              {debateData.forcing_function || "No imminent catalyst recorded."}
            </p>
          </div>
        </Card>
      </div>

      {/* ── Watchlist Capitulation Trigger / Valley of Death ── */}
      {(debateData.trigger_event || debateData.valley_of_death) && (
        <Card style={{ background: "rgba(239, 68, 68, 0.02)", border: `1px solid rgba(239, 68, 68, 0.15)` }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: T.red, textTransform: "uppercase", marginBottom: 8 }}>
            <AlertTriangle size={12} /> Temporal Risk (Valley of Death / Capitulation Trigger)
          </div>
          <p style={{ fontSize: 12, color: T.textLight, lineHeight: 1.6, fontFamily: T.sans, margin: 0 }}>
            {debateData.trigger_event || debateData.valley_of_death}
          </p>
        </Card>
      )}

      {/* ── Multi-Agent Barbell Debate ── */}
      <Card style={{ padding: "20px 24px" }}>
        <SH title="4-Agent Barbell Debate Thesis" icon={<Activity size={12} />} sub="Simulated Bull & Bear Scenario Mapping" />
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 20, marginTop: 16 }}>
          {/* Bull Thesis */}
          <div style={{ background: "rgba(20, 184, 122, 0.02)", border: `1px solid rgba(20, 184, 122, 0.15)`, padding: 16, borderRadius: 8 }}>
            <h4 style={{ margin: "0 0 10px", fontSize: 11, fontWeight: 700, fontFamily: T.mono, color: T.green, textTransform: "uppercase", letterSpacing: "0.05em" }}>
              Bull Case Thesis
            </h4>
            <p style={{ fontSize: 12, color: T.text, lineHeight: 1.6, fontFamily: T.sans, margin: 0, textAlign: "justify" }}>
              {debateData.bull_thesis || "No bull thesis recorded."}
            </p>
          </div>

          {/* Bear Thesis */}
          <div style={{ background: "rgba(239, 68, 68, 0.02)", border: `1px solid rgba(239, 68, 68, 0.15)`, padding: 16, borderRadius: 8 }}>
            <h4 style={{ margin: "0 0 10px", fontSize: 11, fontWeight: 700, fontFamily: T.mono, color: T.red, textTransform: "uppercase", letterSpacing: "0.05em" }}>
              Bear Case Thesis
            </h4>
            <p style={{ fontSize: 12, color: T.text, lineHeight: 1.6, fontFamily: T.sans, margin: 0, textAlign: "justify" }}>
              {debateData.bear_thesis || "No bear thesis recorded."}
            </p>
          </div>
        </div>
      </Card>

      {/* ── Forensic Interrogator Dossier (opus, multi-quarter) ── */}
      {debateData.interrogator_dossier && (
        <Card style={{ padding: "20px 24px" }}>
          <SH title="Forensic Interrogator Dossier" icon={<Brain size={12} />}
              sub={`Opus multi-quarter transcript forensics${debateData.interrogator_score ? ` · Credibility ${debateData.interrogator_score}/5` : ""}${debateData.trajectory ? ` · ${debateData.trajectory}` : ""}`} />
          <div style={{ marginTop: 12, fontSize: 12, lineHeight: 1.7, color: T.text, fontFamily: T.sans, whiteSpace: "pre-wrap" }}>
            {debateData.interrogator_dossier}
          </div>
        </Card>
      )}

      {/* ── Sum-of-Parts valuation + live catalyst status (CRO) ── */}
      {(debateData.sop_fair_value || debateData.catalyst_status || debateData.risk_reward) && (
        <Card style={{ padding: "16px 20px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: T.blue, textTransform: "uppercase", marginBottom: 10, paddingBottom: 6, borderBottom: `1px solid ${T.divider}` }}>
            <Activity size={12} /> Sum-of-Parts Valuation &amp; Catalyst Status (CRO)
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 16, alignItems: "center", marginBottom: debateData.sop_breakdown ? 10 : 0 }}>
            {debateData.sop_fair_value && <div style={{ fontSize: 12, fontFamily: T.mono, color: T.text }}>SoP fair value: <strong style={{ color: T.green }}>{String(debateData.sop_fair_value)}</strong></div>}
            {debateData.risk_reward && <div style={{ fontSize: 12, fontFamily: T.mono, color: T.text }}>Risk/reward: <strong>{String(debateData.risk_reward).slice(0, 90)}</strong></div>}
            {debateData.catalyst_status && (() => {
              const cs = String(debateData.catalyst_status).split(/[\s|—-]+/)[0].toUpperCase();
              const bad = /FIRED|SOFT|UNVERIF/.test(cs); const good = /PENDING/.test(cs);
              const c = good ? T.green : bad ? T.red : T.amber;
              return <span style={{ fontSize: 10, fontFamily: T.mono, padding: "2px 8px", borderRadius: 4, background: c + "22", color: c, border: `1px solid ${c}55` }}>CATALYST: {cs}</span>;
            })()}
          </div>
          {debateData.sop_breakdown && <p style={{ fontSize: 12, color: T.textLight, lineHeight: 1.6, fontFamily: T.sans, margin: 0, whiteSpace: "pre-wrap" }}>{String(debateData.sop_breakdown)}</p>}
        </Card>
      )}

      {/* ── CRO Final Synthesis ── */}
      {debateData.moderator_conclusion && (
        <Card style={{ padding: "16px 20px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: T.purple, textTransform: "uppercase", marginBottom: 8, paddingBottom: 6, borderBottom: `1px solid ${T.divider}` }}>
            <Activity size={12} /> Chief Risk Officer — Final Synthesis
          </div>
          <p style={{ fontSize: 12, color: T.text, lineHeight: 1.6, fontFamily: T.sans, margin: 0, whiteSpace: "pre-wrap" }}>
            {debateData.moderator_conclusion}
          </p>
        </Card>
      )}
    </div>
  );
}

function StockStoryCard({s, incomes, ratios}:{s:StockData, incomes?:IncomeRow[], ratios?:RatioYear[]}){
  type StoryData = {
    narrative:string,
    bullBear?:string,
    bullCatalysts?:string[],
    bearCatalysts?:string[],
    confidenceScore:number,
    timestamp?:number,
    persona?:string
  };

  const [storyList, setStoryList] = useState<StoryData[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string>("");
  const [showArchive, setShowArchive] = useState<boolean>(false);
  const [viewIndex, setViewIndex] = useState<number>(0);
  const [isLoaded, setIsLoaded] = useState<boolean>(false);
  const [selectedPersona, setSelectedPersona] = useState<string>("Objective CIO");
  const [showPersonasGuide, setShowPersonasGuide] = useState<boolean>(false);
  const PERSONAS = ["Objective CIO", "Warren Buffett", "Cathie Wood", "Ray Dalio", "Stanley Druckenmiller"];

  useEffect(() => {
    try {
      const stored = localStorage.getItem(`stock_story_${s.symbol}`);
      if (stored) {
        setStoryList(JSON.parse(stored));
      }
    } catch(e) {}
    setIsLoaded(true);
  }, [s.symbol]);

  async function generateStory() {
    setLoading(true);
    setError("");
    try {
      const trimmedIncomes = incomes ? [...incomes].sort((a,b)=>a.date.localeCompare(b.date)).slice(-5) : [];
      const trimmedRatios = ratios ? [...ratios].sort((a,b)=>a.date.localeCompare(b.date)).slice(-5) : [];

      const res = await fetch("/api/story", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          symbol: s.symbol, 
          stockData: s, 
          incomes: trimmedIncomes,
          ratios: trimmedRatios,
          persona: selectedPersona === "Objective CIO" ? null : selectedPersona 
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Failed to generate story");
      
      const newStory = { ...data.story, timestamp: Date.now(), persona: selectedPersona };
      const updated = [newStory, ...storyList];
      setStoryList(updated);
      localStorage.setItem(`stock_story_${s.symbol}`, JSON.stringify(updated));
      setViewIndex(0);
      setShowArchive(false);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  if (!isLoaded) return null; // Avoid hydration flash

  if (!storyList.length && !loading) {
    return (
      <div style={{display:"flex",flexDirection:"column",gap:16,maxWidth:800,margin:"0 auto",textAlign:"center",padding:"40px 20px"}}>
        <Card>
          <div style={{display:"flex",justifyContent:"center",marginBottom:16}}>
            <Brain size={32} color={T.green} />
          </div>
          <SH title="AI Institutional Narrative" sub="Powered by Gemini 3.1 Pro" />
          <p style={{fontSize:13,color:T.textMuted,fontFamily:T.sans,lineHeight:1.6,marginBottom:16,maxWidth:500,margin:"0 auto 16px"}}>
            Synthesize our multi-factor quantitative models, fundamental metrics, and options flow data into a comprehensive institutional-grade narrative.
          </p>
          
          <div style={{marginBottom: 24, display: "flex", flexDirection: "column", alignItems: "center", gap: 8}}>
            <div style={{fontSize: 11, fontFamily: T.mono, color: T.textMuted, fontWeight: 600}}>SELECT PERSONA</div>
            <div style={{display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "center", maxWidth: 600}}>
              {PERSONAS.map(p => (
                <button
                  key={p}
                  onClick={() => setSelectedPersona(p)}
                  style={{
                    background: selectedPersona === p ? T.greenLight : "transparent",
                    color: selectedPersona === p ? T.green : T.text,
                    border: `1px solid ${selectedPersona === p ? T.greenBorder : T.cardBorder}`,
                    padding: "6px 12px", borderRadius: 20, fontSize: 11, fontFamily: T.mono, fontWeight: 600, cursor: "pointer",
                    transition: "all 0.2s ease"
                  }}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>

          <button 
            onClick={generateStory}
            style={{background:T.green,color:"var(--bg-surface)",border:"none",padding:"10px 24px",borderRadius:6,fontSize:13,fontFamily:T.mono,fontWeight:600,cursor:"pointer",boxShadow:"0 2px 4px rgba(16,185,129,0.2)"}}
          >
            Generate Stock Story
          </button>
          {error && <div style={{color:T.red,fontSize:12,fontFamily:T.mono,marginTop:16}}>{error}</div>}
        </Card>
      </div>
    );
  }

  if (loading) {
    return (
      <div style={{display:"flex",flexDirection:"column",gap:16,maxWidth:800,margin:"0 auto",textAlign:"center",padding:"40px 20px"}}>
        <Card>
          <div style={{padding:40,textAlign:"center",color:T.textLight,fontSize:12,fontFamily:T.mono,display:"flex",flexDirection:"column",alignItems:"center",gap:16}}>
            <Loader2 size={24} style={{animation:"spin 1s linear infinite",color:T.green}}/>
            Analyzing quantitative models and synthesizing real-world narrative...
          </div>
        </Card>
      </div>
    );
  }

  const story = storyList[viewIndex];

  return (
    <div style={{display:"flex",flexDirection:"column",gap:16,width:"100%",margin:"0 auto"}}>
      {storyList.length > 1 && (
        <div style={{display:"flex",justifyContent:"flex-end",marginBottom:-8}}>
          <button 
            onClick={() => { setShowArchive(!showArchive); if (showArchive) setViewIndex(0); }}
            style={{background:"none",border:`1px solid ${T.cardBorder}`,borderRadius:4,padding:"4px 10px",fontSize:10,fontFamily:T.mono,color:T.textMuted,cursor:"pointer",display:"flex",alignItems:"center",gap:6}}
          >
            {showArchive ? "Hide Archive" : `View Archive (${storyList.length - 1})`}
          </button>
        </div>
      )}
      
      {showArchive && storyList.length > 1 && (
        <Card style={{marginBottom:8,background:T.bg,border:`1px dashed ${T.cardBorder}`}}>
          <SH title="Story Archive" icon={<Activity size={12}/>} sub="Previously generated narratives" />
          <div style={{display:"flex",flexDirection:"column",gap:8,marginTop:12}}>
            {storyList.map((sItem, idx) => (
              <div key={idx} style={{display:"flex", alignItems:"center", gap:8}}>
                <button 
                  onClick={() => setViewIndex(idx)}
                  style={{
                    flex:1, display:"flex",justifyContent:"space-between",alignItems:"center",
                    padding:"10px 14px",borderRadius:6,border:`1px solid ${viewIndex === idx ? T.greenBorder : T.cardBorder}`,
                    background:viewIndex === idx ? T.greenLight : "var(--bg-surface)",
                    cursor:"pointer",textAlign:"left"
                  }}
                >
                  <div style={{display:"flex",alignItems:"center",gap:12}}>
                    <div style={{fontSize:11,fontFamily:T.mono,fontWeight:600,color:viewIndex === idx ? T.green : T.text}}>
                      {idx === 0 ? "Latest Story" : `Archived Story ${storyList.length - idx}`}
                      <span style={{color: T.textLight, fontWeight: 400, marginLeft: 8}}>— {sItem.persona || "Objective CIO"}</span>
                    </div>
                    {sItem.timestamp && (
                      <div style={{fontSize:10,fontFamily:T.mono,color:T.textMuted}}>
                        {new Date(sItem.timestamp).toLocaleString(undefined, { month:'short', day:'numeric', hour:'numeric', minute:'2-digit' })}
                      </div>
                    )}
                  </div>
                  <div style={{fontSize:10,fontFamily:T.mono,color:T.textMuted,fontWeight:600}}>
                    Confidence: {sItem.confidenceScore}%
                  </div>
                </button>
                <button 
                  onClick={(e) => {
                    e.stopPropagation();
                    const updated = storyList.filter((_, i) => i !== idx);
                    setStoryList(updated);
                    localStorage.setItem(`stock_story_${s.symbol}`, JSON.stringify(updated));
                    if (viewIndex === idx) setViewIndex(0);
                    else if (viewIndex > idx) setViewIndex(viewIndex - 1);
                    if (updated.length <= 1) setShowArchive(false);
                  }}
                  style={{background:"transparent", border:`1px solid ${T.cardBorder}`, borderRadius: 6, padding: "10px", cursor:"pointer", display:"flex", alignItems:"center", justifyContent:"center"}}
                >
                  <Trash size={14} color={T.red} />
                </button>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card style={{padding: showPersonasGuide ? "16px 20px" : "12px 20px"}}>
        <div 
          onClick={() => setShowPersonasGuide(!showPersonasGuide)}
          style={{display:"flex", justifyContent:"space-between", alignItems:"center", cursor:"pointer", userSelect:"none"}}
        >
          <div style={{display:"flex", alignItems:"center", gap:8}}>
            <Brain size={14} color={T.green} />
            <span style={{fontSize:11, fontFamily:T.mono, fontWeight:600, color:T.text, letterSpacing:"0.05em", textTransform:"uppercase"}}>Investor Personas Guide</span>
          </div>
          {showPersonasGuide ? <ChevronUp size={16} color={T.textMuted} /> : <ChevronDown size={16} color={T.textMuted} />}
        </div>
        {showPersonasGuide && (
          <div style={{marginTop: 16, paddingTop: 16, borderTop: `1px solid ${T.divider}`, fontSize: 12, color: T.textMuted, fontFamily: T.sans, lineHeight: 1.6}}>
             <div style={{marginBottom:8}}><strong>Objective CIO:</strong> Provides a balanced, data-driven, risk-adjusted overview without emotional bias. Focuses on hard numbers, probability, and capital preservation.</div>
             <div style={{marginBottom:8}}><strong>Warren Buffett:</strong> Focuses on deep value, competitive moats, consistent return on equity, and margin of safety. Prefers predictable cash flows over speculative growth.</div>
             <div style={{marginBottom:8}}><strong>Cathie Wood:</strong> Seeks disruptive innovation, exponential growth trajectories, and paradigm-shifting technologies. Willing to accept higher valuation multiples for future market dominance.</div>
             <div style={{marginBottom:8}}><strong>Ray Dalio:</strong> Analyzes the macroeconomic environment, debt cycles, and secular shifts. Views the stock as a piece of a larger economic machine.</div>
             <div><strong>Stanley Druckenmiller:</strong> Emphasizes momentum, liquidity flows, and tactical catalysts. Looks for explosive setups combining strong fundamentals with powerful technical breakouts.</div>
          </div>
        )}
      </Card>

      <Card>
        <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:20, borderBottom:`1px solid ${T.divider}`, paddingBottom:12}}>
          <SH 
            title={story.persona || "Investment Narrative"} 
            icon={<Brain size={14} color={T.green} />} 
            sub={viewIndex > 0 ? `Archived Report (${new Date(story.timestamp||0).toLocaleDateString()})` : "Current Strategic Assessment"} 
          />
          <div style={{fontSize:11,fontWeight:700,fontFamily:T.mono,color:story?.confidenceScore && story.confidenceScore > 75 ? T.green : T.amber, background:story?.confidenceScore && story.confidenceScore > 75 ? T.greenLight : T.card, padding:"6px 12px", borderRadius:6, border:`1px solid ${story?.confidenceScore && story.confidenceScore > 75 ? T.greenBorder : T.cardBorder}`, boxShadow:"0 1px 2px rgba(0,0,0,0.05)"}}>
            Confidence: {story?.confidenceScore}%
          </div>
        </div>
        <div style={{fontSize:16,lineHeight:1.8,color:T.text,fontFamily:T.sans,whiteSpace:"pre-wrap",textAlign:"justify"}}>
          {story?.narrative}
        </div>
      </Card>

      {story?.bullBear && (
        <Card>
          <SH title="Multi-Agent Debate" icon={<Activity size={12}/>} sub="Gemini 3.1 Pro vs. Claude 4.7 Opus" />
          <div style={{fontSize:16,lineHeight:1.8,color:T.text,fontFamily:T.sans,textAlign:"justify"}}>
            {story.bullBear.split("Bear says:").map((part, i) => (
              <div key={i} style={{marginBottom: i === 0 ? 12 : 0, paddingBottom: i === 0 ? 12 : 0, borderBottom: i === 0 ? `1px dashed ${T.divider}` : "none"}}>
                {i === 0 ? <strong style={{color:T.green}}>Gemini (Bull): </strong> : <strong style={{color:T.red}}>Claude (Bear): </strong>}
                {part.replace("Bull says:", "").trim()}
              </div>
            ))}
          </div>
        </Card>
      )}

      {((story?.bullCatalysts?.length ?? 0) > 0 || (story?.bearCatalysts?.length ?? 0) > 0) && (
        <Card>
          <SH title="Thesis Catalysts" icon={<Zap size={12}/>} sub="Key events to monitor in upcoming earnings or news" />
          <div style={{display:"flex", gap:20, marginTop:16}}>
            {(story?.bullCatalysts?.length ?? 0) > 0 && (
              <div style={{flex:1, background:T.greenLight, padding:16, borderRadius:8, border:`1px solid ${T.greenBorder}`}}>
                <h4 style={{fontSize:12, fontFamily:T.mono, color:T.green, fontWeight:700, margin:"0 0 12px 0", textTransform:"uppercase"}}>Bull Confirmation</h4>
                <ul style={{margin:0, paddingLeft:16, fontSize:13, lineHeight:1.6, color:T.text, fontFamily:T.sans}}>
                  {story.bullCatalysts?.map((c: string, i: number) => <li key={i} style={{marginBottom:8}}>{c}</li>)}
                </ul>
              </div>
            )}
            {(story?.bearCatalysts?.length ?? 0) > 0 && (
              <div style={{flex:1, background:"var(--red-light)", padding:16, borderRadius:8, border:"1px solid var(--red)"}}>
                <h4 style={{fontSize:12, fontFamily:T.mono, color:T.red, fontWeight:700, margin:"0 0 12px 0", textTransform:"uppercase"}}>Bear Confirmation</h4>
                <ul style={{margin:0, paddingLeft:16, fontSize:13, lineHeight:1.6, color:T.text, fontFamily:T.sans}}>
                  {story.bearCatalysts?.map((c: string, i: number) => <li key={i} style={{marginBottom:8}}>{c}</li>)}
                </ul>
              </div>
            )}
          </div>
        </Card>
      )}
      
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginTop:8}}>
        <div style={{fontSize:10,color:T.textMuted,fontFamily:T.mono}}>
          Dynamically generated by Gemini 3.1 Pro. Not financial advice.
        </div>
        {viewIndex === 0 && (
          <div style={{display:"flex",alignItems:"center",gap:8, flexWrap: "wrap", justifyContent: "flex-end"}}>
            {error && <span style={{fontSize:10,color:T.red,fontFamily:T.mono}}>{error}</span>}
            <div style={{display: "flex", gap: 4, marginRight: 8}}>
              {PERSONAS.map(p => (
                <button
                  key={p}
                  onClick={() => setSelectedPersona(p)}
                  style={{
                    background: selectedPersona === p ? T.greenLight : "transparent",
                    color: selectedPersona === p ? T.green : T.textMuted,
                    border: `1px solid ${selectedPersona === p ? T.greenBorder : "transparent"}`,
                    padding: "3px 8px", borderRadius: 12, fontSize: 9, fontFamily: T.mono, fontWeight: 600, cursor: "pointer",
                  }}
                >
                  {p.split(" ")[0]}
                </button>
              ))}
            </div>
            <button 
              onClick={generateStory}
              style={{background:T.green,color:"var(--bg-surface)",border:"none",padding:"6px 16px",borderRadius:6,fontSize:10,fontFamily:T.mono,fontWeight:600,cursor:"pointer",boxShadow:"0 2px 4px rgba(16,185,129,0.2)"}}
            >
              Generate New Insight
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function FmpBasicChartTab({ s }: { s: StockData }) {
  const [data, setData] = useState<{date:string, close:number}[] | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    // Use window.fetch to hit the backend directly or via FMP proxy
    fetch(`/api/fmp?e=historical-price-full&symbol=${s.symbol.toUpperCase()}&timeseries=252`)
      .then(r => r.ok ? r.json() : null)
      .then(res => {
        const d = Array.isArray(res) ? res : res ? [res] : null;
        if (d && d[0] && d[0].historical) {
          setData(d[0].historical.slice().reverse()); // Oldest first
        } else {
          setData([]);
        }
        setLoading(false);
      })
      .catch(() => { setData([]); setLoading(false); });
  }, [s.symbol]);

  if (loading) return <Card style={{height: 700, display: "flex", alignItems: "center", justifyContent: "center", color: T.textMuted}}><Loader2 size={24} style={{animation:"spin 1s linear infinite"}}/></Card>;
  if (!data || data.length === 0) return <Card style={{height: 700, display: "flex", alignItems: "center", justifyContent: "center", color: T.textMuted}}>No historical data available.</Card>;

  const minP = Math.min(...data.map(d=>d.close)) * 0.95;
  const maxP = Math.max(...data.map(d=>d.close)) * 1.05;
  const range = maxP - minP || 1;
  const W = 800, H = 500;
  
  const pts = data.map((d, i) => {
    const x = (i / (data.length - 1)) * W;
    const y = H - ((d.close - minP) / range) * H;
    return `${x},${y}`;
  }).join(" ");

  return (
    <div>
      <Card style={{padding: 24, height: 700}}>
        <div style={{display:"flex", justifyContent:"space-between", marginBottom: 32}}>
          <SH title="Basic Price Chart" icon={<Activity size={12}/>} sub="Euronext restricted symbol fallback (FMP Data)" />
          <a href={`https://www.tradingview.com/chart/?symbol=${encodeURIComponent(toTradingViewSymbol(s.symbol))}`} target="_blank" rel="noreferrer" style={{fontSize: 10, color: T.blue, textDecoration:"underline", fontFamily: T.mono}}>Open in TradingView</a>
        </div>
        <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{overflow:"visible"}}>
          {/* Grid */}
          <line x1="0" y1="0" x2={W} y2="0" stroke={T.divider} strokeWidth="1" />
          <line x1="0" y1={H/2} x2={W} y2={H/2} stroke={T.divider} strokeWidth="1" />
          <line x1="0" y1={H} x2={W} y2={H} stroke={T.divider} strokeWidth="1" />
          
          {/* Line */}
          <polyline points={pts} fill="none" stroke={T.green} strokeWidth="2" strokeLinejoin="round" />
          
          {/* Current price dot */}
          <circle cx={W} cy={H - ((data[data.length-1].close - minP) / range) * H} r="4" fill={T.green} />
        </svg>
        <div style={{display:"flex", justifyContent:"space-between", marginTop: 16, fontSize:10, color:T.textMuted, fontFamily: T.mono}}>
          <span>{data[0].date}</span>
          <span>{data[data.length-1].date}</span>
        </div>
      </Card>
      <CustomAlertPanel symbol={s.symbol} />
    </div>
  );
}

function CustomAlertPanel({ symbol }: { symbol: string }) {
  const [metric, setMetric] = useState("Price");
  const [condition, setCondition] = useState(">");
  const [value, setValue] = useState("");
  const [email, setEmail] = useState("");
  const [status, setStatus] = useState("");

  const handleSave = async () => {
    if (!value || !email) return setStatus("Please fill all fields.");
    setStatus("Saving...");
    try {
      const r = await fetch("/api/alerts/add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol, metric, condition, value: parseFloat(value), email })
      });
      if (r.ok) setStatus("Alert saved successfully!");
      else setStatus("Failed to save alert.");
    } catch(e) {
      setStatus("Error saving alert.");
    }
    setTimeout(() => setStatus(""), 3000);
  };

  return (
    <Card style={{marginTop: 16}}>
      <SH title="Custom Alert" icon={<Zap size={12}/>} sub="Sends email when triggered" />
      <div style={{display:"flex", gap: 10, alignItems:"center", flexWrap: "wrap", fontSize:12, fontFamily:T.mono}}>
        <span style={{color: T.textMuted}}>Alert me when</span>
        <select value={metric} onChange={e=>setMetric(e.target.value)} style={{padding: "4px 8px", borderRadius:4, border: `1px solid ${T.cardBorder}`, color: T.text, outline: "none"}}>
          <option>Price</option>
          <option>RSI (14)</option>
          <option>MACD</option>
          <option>VWMA</option>
          <option>OBV</option>
        </select>
        <select value={condition} onChange={e=>setCondition(e.target.value)} style={{padding: "4px 8px", borderRadius:4, border: `1px solid ${T.cardBorder}`, color: T.text, outline: "none"}}>
          <option value=">">goes above</option>
          <option value="<">goes below</option>
        </select>
        <input type="number" placeholder="Value" value={value} onChange={e=>setValue(e.target.value)} style={{padding: "4px 8px", borderRadius:4, border: `1px solid ${T.cardBorder}`, width: 80, color: T.text, outline: "none"}} />
        <span style={{color: T.textMuted}}>Send to:</span>
        <input type="email" placeholder="Email address" value={email} onChange={e=>setEmail(e.target.value)} style={{padding: "4px 8px", borderRadius:4, border: `1px solid ${T.cardBorder}`, width: 180, color: T.text, outline: "none"}} />
        <button onClick={handleSave} style={{padding: "5px 12px", background: T.greenLight, color: T.green, border: `1px solid ${T.greenBorder}`, borderRadius: 4, fontWeight: 600, cursor: "pointer"}}>Save Alert</button>
      </div>
      {status && <div style={{marginTop: 8, fontSize: 10, color: status.includes("success") ? T.green : T.red, fontFamily: T.mono}}>{status}</div>}
    </Card>
  );
}

function AdvancedChartTab({ s }: { s: StockData }) {
  const container = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!container.current) return;
    container.current.innerHTML = "";
    
    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    script.type = "text/javascript";
    script.async = true;
    script.innerHTML = JSON.stringify({
      "autosize": true,
      "symbol": toTradingViewSymbol(s.symbol),
      "interval": "D",
      "timezone": "exchange",
      "theme": "dark",
      "style": "1",
      "locale": "en",
      "enable_publishing": false,
      "backgroundColor": "#0a1817",
      "gridColor": "#1c3330",
      "hide_top_toolbar": false,
      "hide_legend": false,
      "save_image": false,
      "allow_symbol_change": true,
      "studies": [
        "VWMA@tv-basicstudies",
        "MAExp@tv-basicstudies",
        "MAExp@tv-basicstudies",
        "MASimple@tv-basicstudies",
        "RSI@tv-basicstudies",
        "MACD@tv-basicstudies",
        "RelativeVolume@tv-basicstudies",
        "ADX@tv-basicstudies",
        "BB%B@tv-basicstudies",
        "OBV@tv-basicstudies"
      ]
    });
    
    container.current.appendChild(script);
  }, [s.symbol]);

  return (
    <div>
      <Card style={{ height: "1200px", padding: 0, overflow: "hidden", border: `1px solid ${T.cardBorder}` }}>
        <div className="tradingview-widget-container" ref={container} style={{ height: "100%", width: "100%" }} />
      </Card>
      <CustomAlertPanel symbol={s.symbol} />
    </div>
  );
}

interface BloomCatalyst {
  title: string;
  detected: boolean;
  description: string;
  evidence: string;
}

interface LoebCriterion {
  rating?: string;
  ratio?: string;
  detected?: boolean;
  analysis: string;
}

interface OptionsSignals {
  iv_current: number | null;
  skew_25d: number | null;
  term_structure: string;
  pc_oi_ratio: number | null;
  total_oi: number | null;
  implied_earnings_move_pct: number | null;
  market_sentiment_flag: string;
  overall_interpretation: string;
}

interface RecentEvent {
  date: string;
  type: "filing" | "news" | "transcript";
  title: string;
  link: string;
}

interface ScoreAdjustment {
  factor: string;
  adjustment: number;
  reason: string;
}

interface CatalystScanReport {
  symbol: string;
  company_name: string;
  price: number;
  market_cap: number;
  catalyst_density_score: number;
  upside_downside_ratio: number;
  analysis_summary: string;
  recommendation: "BUY" | "WATCH" | "HOLD" | "SELL";
  bloom_catalysts: {
    catalyst_1: BloomCatalyst;
    catalyst_2: BloomCatalyst;
    catalyst_3: BloomCatalyst;
  };
  loeb_criteria: {
    catalyst_density: LoebCriterion;
    sum_of_parts: LoebCriterion;
    activism_potential: LoebCriterion;
    risk_reward: LoebCriterion;
  };
  options_signals: OptionsSignals;
  recent_events: RecentEvent[];
  cache_timestamp?: string;
  is_merger_arb?: boolean;
  catalyst_nature?: "mechanical_execution" | "pricing_dislocation";
  catalyst_nature_rationale?: string;
  re_rate_status?: "pending" | "partial" | "complete";
  merger_arb_data?: {
    acquirer_symbol?: string;
    acquirer_name?: string;
    acquirer_price?: number;
    cash_component?: number;
    stock_component_ratio?: number;
    implied_deal_value?: number;
    gross_spread_val?: number;
    gross_spread_pct?: number;
    expected_close?: string;
    unhedged_downside?: number;
    unhedged_rr_asymmetry?: string;
    pre_announce_price?: number;
    deal_status?: string;
  } | null;
  convergence_score?: number;
  independent_track_count?: number;
  unfired_independent_track_count?: number;
  is_dher_pattern?: boolean;
  tracks?: Array<{
    track_type: string;
    evidence: string;
    counterparty: string | null;
    dated_event: boolean;
    event_date: string | null;
    fired: boolean;
    independence_score?: number;
  }>;
  options_confirmation_score?: number;
  credit_health?: {
    grade?: string;
    net_debt_ebitda?: number;
    distress_flags?: string[];
  };
  adjusted_loeb_score?: number;
  final_adjusted_loeb?: number;
  score_adjustments?: ScoreAdjustment[];
  distressed_setup_flag?: boolean;
  credit_event_risk_flag?: boolean;
  credit_health_layer3_adjustment_applied?: boolean;
}

function CatalystTabContent({ symbol }: { symbol: string }) {
  const [report, setReport] = useState<CatalystScanReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [customAcquirerPrice, setCustomAcquirerPrice] = useState<number | "">("");

  const fetchReport = useCallback((forceRefresh: boolean = false) => {
    if (!symbol) return;
    setLoading(true);
    setError(null);
    fetch(`/api/catalysts/scan?symbol=${symbol}${forceRefresh ? "&refresh=true" : ""}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP error ${r.status}`);
        return r.json();
      })
      .then((data: CatalystScanReport) => {
        setReport(data);
        setCustomAcquirerPrice(data.merger_arb_data?.acquirer_price ?? "");
        setLoading(false);
      })
      .catch((err) => {
        console.error(err);
        setError("Failed to load catalyst scan report.");
        setLoading(false);
      });
  }, [symbol]);

  useEffect(() => {
    fetchReport(false);
  }, [fetchReport]);

  const handleForceRefresh = () => {
    fetchReport(true);
  };

  if (loading) {
    return (
      <Card style={{ padding: 40, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 16 }}>
        <Loader2 size={24} style={{ animation: "spin 1s linear infinite", color: T.green }} />
        <div style={{ fontSize: 12, fontFamily: T.mono, color: T.textLight }}>
          Running multi-strategy cognitive extraction pipeline for {symbol}...
        </div>
      </Card>
    );
  }

  if (error || !report) {
    return (
      <Card style={{ padding: 40, textAlign: "center", color: T.red }}>
        <AlertCircle size={24} style={{ margin: "0 auto 8px" }} />
        <div style={{ fontSize: 12, fontFamily: T.mono }}>{error || "No catalyst report found"}</div>
      </Card>
    );
  }

  const getRecommendationStyle = (rec?: string) => {
    switch (rec) {
      case "BUY":
        return { color: T.green, backgroundColor: T.greenLight, borderColor: T.greenBorder };
      case "WATCH":
        return { color: T.amber, backgroundColor: T.amberLight, borderColor: T.amber };
      case "HOLD":
        return { color: T.textMuted, backgroundColor: T.card, borderColor: T.cardBorder };
      case "SELL":
        return { color: T.red, backgroundColor: T.redLight, borderColor: T.red };
      default:
        return { color: T.text, backgroundColor: T.card, borderColor: T.cardBorder };
    }
  };

  // Dynamic merger arb math calculation based on customAcquirerPrice input
  const mergerArbComputed = useMemo(() => {
    if (!report || (!report.is_merger_arb && !report.merger_arb_data) || !report.merger_arb_data) return null;
    
    const data = report.merger_arb_data;
    const isPE = !data.acquirer_symbol || data.acquirer_symbol === "CASH" || data.acquirer_symbol === "NONE";
    
    const acquirerPriceToUse = customAcquirerPrice !== "" ? customAcquirerPrice : (data.acquirer_price || 0);
    const cashComponent = data.cash_component || 0;
    const stockComponentRatio = data.stock_component_ratio || 0;
    const targetPrice = report.price || 0;
    const preAnnouncePrice = data.pre_announce_price || (targetPrice * 0.85);

    const impliedDealValue = cashComponent + (stockComponentRatio * acquirerPriceToUse);
    const grossSpreadVal = impliedDealValue - targetPrice;
    const grossSpreadPct = targetPrice > 0 ? (grossSpreadVal / targetPrice) * 100 : 0;
    const unhedgedDownside = targetPrice - preAnnouncePrice;
    const unhedgedRRVal = grossSpreadVal > 0 ? -(unhedgedDownside / grossSpreadVal) : -99.9;
    const unhedgedRRString = grossSpreadVal > 0 ? `${unhedgedRRVal.toFixed(1)}:1` : "N/A (Negative Spread)";
    
    // Dynamic rounded strikes for options suggestion builder
    const roundStrike = (val: number, step = 2.5) => Math.round(val / step) * step;
    
    const longPutStrike = roundStrike(targetPrice, targetPrice < 50 ? 2.5 : 5.0);
    let shortPutStrike = roundStrike(preAnnouncePrice, preAnnouncePrice < 50 ? 2.5 : 5.0);
    if (longPutStrike <= shortPutStrike) {
      shortPutStrike = longPutStrike - (targetPrice < 50 ? 2.5 : 5.0);
    }
    
    const dealValStrike = roundStrike(impliedDealValue, impliedDealValue < 50 ? 2.5 : 5.0);
    
    const targetHedges = [
      {
        strategy: "Bear Put Spread (Downside Protection)",
        description: `Buy ${longPutStrike} Put / Sell ${shortPutStrike} Put on ${report.symbol} to hedge drop to pre-announce reference ($${preAnnouncePrice.toFixed(2)}).`,
        legs: `Buy $${longPutStrike} P / Sell $${shortPutStrike} P`
      },
      {
        strategy: "Covered Call (Yield Enhancement)",
        description: `Buy ${report.symbol} stock and Sell ${dealValStrike} Call to collect premium and buffer downside, capping upside at deal price.`,
        legs: `Buy Stock / Sell $${dealValStrike} C`
      }
    ];
    
    const acquirerHedges = [];
    if (stockComponentRatio > 0 && data.acquirer_symbol && data.acquirer_symbol !== "CASH") {
      const acqSpot = acquirerPriceToUse;
      if (acqSpot > 0) {
        const acqShortStrike = roundStrike(acqSpot, acqSpot < 50 ? 2.5 : 5.0);
        const acqLongStrike = roundStrike(acqSpot * 1.10, acqSpot < 50 ? 2.5 : 5.0);
        acquirerHedges.push({
          strategy: "Bear Call Spread (Short Protection)",
          description: `Sell $${acqShortStrike} Call / Buy $${acqLongStrike} Call on ${data.acquirer_symbol} to hedge long target exposure if acquirer shares plummet.`,
          legs: `Sell $${acqShortStrike} C / Buy $${acqLongStrike} C`
        });
        
        const acqLongPut = roundStrike(acqSpot, acqSpot < 50 ? 2.5 : 5.0);
        const acqShortPut = roundStrike(acqSpot * 0.85, acqSpot < 50 ? 2.5 : 5.0);
        acquirerHedges.push({
          strategy: "Bear Put Spread (Synthetic Short)",
          description: `Buy $${acqLongPut} Put / Sell $${acqShortPut} Put on ${data.acquirer_symbol} to gain short exposure to the acquirer component without borrow cost.`,
          legs: `Buy $${acqLongPut} P / Sell $${acqShortPut} P`
        });
      }
    }

    return {
      impliedDealValue,
      grossSpreadVal,
      grossSpreadPct,
      unhedgedDownside,
      unhedgedRRString,
      acquirerPriceToUse,
      isPE,
      targetHedges,
      acquirerHedges
    };
  }, [report, customAcquirerPrice]);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* Detail dashboard layout */}
      <Card>
        <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", borderBottom: `1px solid ${T.divider}`, paddingBottom: 12, marginBottom: 16, gap: 12 }}>
          <SH title={`${report.company_name} Catalyst Overview`} icon={<Zap size={14} color={T.green} />} sub={`Loeb & Bloom Cognitive Catalyst Scan`} />
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            {report.cache_timestamp && (
              <span style={{ fontSize: 10, color: T.textLight, fontFamily: T.mono }}>
                Last Scan: <strong style={{ color: T.text }}>{new Date(report.cache_timestamp).toLocaleString()}</strong>
              </span>
            )}
            <button
              onClick={() => handleForceRefresh()}
              disabled={loading}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                background: "transparent",
                border: `1px solid ${T.cardBorder}`,
                borderRadius: 6,
                padding: "3px 8px",
                fontSize: 10,
                fontWeight: 700,
                color: T.green,
                cursor: "pointer",
                transition: "all 0.15s",
                fontFamily: T.mono,
              }}
            >
              <RefreshCw size={11} className={loading ? "animate-spin" : ""} style={{ animation: loading ? "spin 1s linear infinite" : "none" }} />
              RE-SCAN
            </button>
            {report.recommendation && (
              <span style={{ 
                fontSize: 10, fontWeight: 800, padding: "3px 9px", borderRadius: 6,
                borderWidth: 1, borderStyle: "solid",
                ...getRecommendationStyle(report.recommendation)
              }}>
                {report.recommendation}
              </span>
            )}
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 16px", background: "rgba(168,85,247,0.06)", borderRadius: 6, border: `1px solid ${T.purple || "var(--purple)"}` }}>
            <div>
              <Tip k="CATALYST_SCORE"><div style={{ fontSize: 8, fontWeight: 700, color: T.textMuted, letterSpacing: "0.05em", textTransform: "uppercase" }}>Loeb Catalyst Score</div></Tip>
              <div style={{ fontSize: 9, color: T.textLight }}>Refined Catalyst Density</div>
            </div>
            <div style={{ marginLeft: "auto", fontSize: 24, fontWeight: 800, color: T.purple || "var(--purple)", fontFamily: T.mono }}>
              {(report.adjusted_loeb_score ?? report.catalyst_density_score)?.toFixed(1) || "N/A"}
            </div>
          </div>
          
          {(() => { const rr = rrDisplay(report as any); return (
          <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "12px 16px", background: "rgba(255,255,255,0.03)", borderRadius: 6, border: `1px solid ${toneColor(rr.tone)}` }}>
            <div>
              <Tip k="RR" extra={rr.rawForTooltip}><div style={{ fontSize: 8, fontWeight: 700, color: T.textMuted, letterSpacing: "0.05em", textTransform: "uppercase" }}>Risk / Reward</div></Tip>
              <div style={{ fontSize: 9, color: T.textLight }}>vs live price</div>
            </div>
            <div style={{ marginLeft: "auto", fontSize: 17, fontWeight: 800, color: toneColor(rr.tone), fontFamily: T.mono }}>
              {rr.text}
            </div>
          </div>
          ); })()}
        </div>

        <div>
          <div style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", color: T.textMuted, letterSpacing: "0.08em", marginBottom: 6 }}>
            Opportunistic AI Thesis Summary
          </div>
          <p style={{ fontSize: 13, color: T.text, lineHeight: 1.6, margin: 0, fontFamily: T.sans }}>
            {report.analysis_summary}
          </p>

          {/* Skeptic correction — reconciles a thesis whose prose argues a higher score than the skeptic's final */}
          {(report as any).verify_verdict === "CONFIRMED_WITH_CORRECTIONS" && report.bloom_catalysts?.catalyst_3?.evidence && (
            <div style={{ marginTop: 10, padding: "9px 12px", background: "rgba(217,151,6,0.06)", border: "1px solid rgba(217,151,6,0.25)", borderRadius: 6 }}>
              <Tip k="CONFIRMED_WITH_CORRECTIONS"><span style={{ fontSize: 9, fontWeight: 800, textTransform: "uppercase", color: "#d97706", letterSpacing: "0.05em" }}>⚠ Skeptic correction</span></Tip>
              <div style={{ fontSize: 10.5, color: T.textLight, lineHeight: 1.5, marginTop: 4 }}>{report.bloom_catalysts.catalyst_3.evidence}</div>
            </div>
          )}

          {/* Post-board enforcement audit (manual §6/§9): driver tag + corrections trail */}
          {((report as any).resolution_driver || ((report as any).corrections?.length > 0)) && (
            <div style={{ marginTop: 12, padding: "10px 14px", background: "rgba(196,181,253,0.05)", border: `1px solid rgba(196,181,253,0.18)`, borderRadius: 6 }}>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: (report as any).corrections?.length ? 6 : 0 }}>
                <span style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", color: T.purple || "var(--purple)", letterSpacing: "0.06em" }}>Post-board pass</span>
                {(report as any).resolution_driver && (
                  <span style={{ fontSize: 9, fontFamily: T.mono, padding: "1px 6px", borderRadius: 3, background: "rgba(196,181,253,0.14)", color: T.purple || "var(--purple)", border: "1px solid rgba(196,181,253,0.20)" }}>
                    ⛓ driver: {String((report as any).resolution_driver).replace(/_/g, " ")}
                  </span>
                )}
                {(report as any).lane_canon && (
                  <span style={{ fontSize: 9, fontFamily: T.mono, color: T.textLight }}>lane: {String((report as any).lane_canon).replace(/_/g, " ")}</span>
                )}
              </div>
              {(report as any).corrections?.length > 0 && (
                <div style={{ fontSize: 10, color: T.textLight, lineHeight: 1.5 }}>
                  <span style={{ color: T.textMuted, fontWeight: 700 }}>Corrections applied: </span>
                  {(report as any).corrections.join(" · ")}
                  {(report as any).adjusted_loeb_score_orig != null && (report as any).adjusted_loeb_score_orig !== report.adjusted_loeb_score && (
                    <span> · score {(report as any).adjusted_loeb_score_orig} → {report.adjusted_loeb_score}</span>
                  )}
                  {(report as any).tier_orig && (report as any).tier_orig !== (report as any).tier && (
                    <span> · tier {(report as any).tier_orig} → {(report as any).tier}</span>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Phase-2 computed edge / valuation build (the EDGE axis, with the work shown) */}
          {(report as any).valuation_method && (
            <div style={{ marginTop: 12, padding: "12px 14px", background: "rgba(20,184,122,0.04)", border: `1px solid ${T.cardBorder || "var(--border)"}`, borderRadius: 6 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
                <span style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", color: T.green, letterSpacing: "0.06em" }}>Edge · computed R:R</span>
                <span style={{ fontSize: 9, fontFamily: T.mono, color: T.textMuted }}>({(report as any).valuation_method})</span>
                {(report as any).edge_grade && (report as any).edge_grade !== "?" && (
                  <span style={{ fontSize: 9, fontWeight: 800, padding: "1px 6px", borderRadius: 3, background: (report as any).edge_grade === "H" ? "rgba(20,184,122,0.18)" : (report as any).edge_grade === "M" ? "rgba(217,151,6,0.18)" : "rgba(239,68,68,0.16)", color: (report as any).edge_grade === "H" ? T.green : (report as any).edge_grade === "M" ? "#d97706" : "#ef4444" }}>EDGE {(report as any).edge_grade}</span>
                )}
                {((report as any).edge_flags || []).map((f: string) => (<Tip key={f} k={f.split(":")[0]}><span style={{ fontSize: 8, fontFamily: T.mono, color: "#d97706", border: "1px solid rgba(217,151,6,0.3)", borderRadius: 3, padding: "1px 4px" }}>{f}</span></Tip>))}
              </div>
              {(report as any).valuation_method === "binary_prob" ? (
                <div style={{ display: "flex", gap: 14, flexWrap: "wrap", fontSize: 11, fontFamily: T.mono, color: T.text }}>
                  <span>P(win) <b>{(((report as any).win_prob || 0) * 100).toFixed(0)}%</b></span>
                  <span style={{ color: T.green }}>up-leg <b>+${((report as any).up_leg || 0).toFixed(2)}</b></span>
                  <span style={{ color: "#ef4444" }}>down-leg <b>−${((report as any).down_leg || 0).toFixed(2)}</b></span>
                  <span>payoff <b>{((report as any).payoff || 0).toFixed(2)}×</b></span>
                  <span>EV <b style={{ color: ((report as any).ev_pct || 0) >= 0 ? T.green : "#ef4444" }}>{((report as any).ev_pct || 0) >= 0 ? "+" : ""}{(((report as any).ev_pct || 0) * 100).toFixed(1)}%</b></span>
                  <span style={{ color: T.textMuted }}>(barbell — not a single R:R)</span>
                </div>
              ) : (
                <div style={{ display: "flex", gap: 14, flexWrap: "wrap", fontSize: 11, fontFamily: T.mono, color: T.text }}>
                  <Tip k="RR" extra={rrDisplay(report as any).rawForTooltip}><span>R:R <b style={{ color: toneColor(rrDisplay(report as any).tone) }}>{rrDisplay(report as any).text}</b></span></Tip>
                  <span style={{ color: T.green }}>target <b>${(((report as any).sop_built ?? (report as any).fair_value_target) || 0).toFixed(2)}</b>{(report as any).sop_built != null ? <span style={{ color: T.textMuted, fontWeight: 400 }}> (build)</span> : null}</span>
                  <span>live <b>${((report as any).live_price || report.price || 0).toFixed(2)}</b></span>
                  <span style={{ color: "#ef4444" }}>floor <b>${((report as any).downside_floor || 0).toFixed(2)}</b></span>
                  {(report as any).drift != null && (<span style={{ color: T.textMuted }}>drift {((report as any).drift * 100).toFixed(1)}%</span>)}
                </div>
              )}
              {((report as any).edge_flags || []).includes("SOP_TARGET_MISMATCH") && (
                <div style={{ fontSize: 9, color: "#d97706", marginTop: 4 }}>⚠ asserted target ${((report as any).fair_value_target || 0).toFixed(2)} ≠ reconciled build ${((report as any).sop_built || 0).toFixed(2)} — R:R uses the build (premium/advocacy stripped)</div>
              )}
              {(report as any).valuation?.advocacy_target != null && (
                <div style={{ fontSize: 9, color: T.textMuted, marginTop: 2 }}>advocacy ceiling ${Number((report as any).valuation.advocacy_target).toFixed(2)} — activist target, displayed only (never in the R:R)</div>
              )}
              {(report as any).valuation?.valuation_basis && (
                <div style={{ fontSize: 10, color: T.textLight, marginTop: 6, lineHeight: 1.5 }}><span style={{ color: T.textMuted, fontWeight: 700 }}>Basis: </span>{(report as any).valuation.valuation_basis}</div>
              )}
              {(report as any).valuation?.sop_components?.length > 0 && (
                <div style={{ marginTop: 8 }}>
                  <div style={{ fontSize: 8, fontWeight: 700, textTransform: "uppercase", color: T.textMuted, marginBottom: 4 }}>Sum-of-parts build</div>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 10, fontFamily: T.mono }}>
                    <thead><tr style={{ color: T.textMuted }}><th style={{ textAlign: "left", padding: "2px 4px" }}>Segment</th><th style={{ textAlign: "right" }}>Metric</th><th style={{ textAlign: "right" }}>×</th><th style={{ textAlign: "right", padding: "2px 4px" }}>EV</th></tr></thead>
                    <tbody>
                      {(report as any).valuation.sop_components.map((s: any, idx: number) => (
                        <tr key={idx} style={{ borderTop: `1px solid ${T.cardBorder || "var(--border)"}` }}>
                          <td style={{ padding: "2px 4px", color: T.text }} title={s.basis}>{s.segment}</td>
                          <td style={{ textAlign: "right", color: T.textLight }}>{s.metric_value != null ? `${s.metric_value} ${s.driver_metric || ""}` : "—"}</td>
                          <td style={{ textAlign: "right", color: T.textLight }}>{s.multiple != null ? `${s.multiple}×` : "—"}</td>
                          <td style={{ textAlign: "right", padding: "2px 4px", color: T.text }}>{s.ev_contribution != null ? `$${Number(s.ev_contribution).toLocaleString()}` : "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <div style={{ fontSize: 9, color: T.textMuted, marginTop: 4 }}>− net debt ${Number((report as any).valuation.net_debt || 0).toLocaleString()} − adj ${Number((report as any).valuation.adjustments || 0).toLocaleString()} ÷ {Number((report as any).valuation.shares_out || 0).toLocaleString()} sh = <b style={{ color: T.green }}>${((report as any).fair_value_target || 0).toFixed(2)}</b></div>
                </div>
              )}
            </div>
          )}

          {/* Catalyst Nature Timing & Re-rate Distinction */}
          {(report.catalyst_nature || report.re_rate_status) && (
            <div style={{ marginTop: 12, padding: "10px 14px", background: "rgba(255,255,255,0.02)", border: `1px solid ${T.cardBorder || "var(--border)"}`, borderRadius: 6 }}>
              <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 6 }}>
                {report.catalyst_nature && (
                  <span style={{
                    fontSize: 9,
                    fontWeight: 700,
                    padding: "2px 6px",
                    borderRadius: 4,
                    background: report.catalyst_nature === "pricing_dislocation" ? "rgba(20, 184, 122, 0.12)" : "rgba(59, 130, 246, 0.12)",
                    color: report.catalyst_nature === "pricing_dislocation" ? T.green || "var(--green)" : T.blue || "var(--blue)",
                    border: `1px solid ${report.catalyst_nature === "pricing_dislocation" ? T.green || "var(--green)" : T.blue || "var(--blue)"}`
                  }}>
                    {report.catalyst_nature === "pricing_dislocation" ? "ALPHA-BEARING DISLOCATION" : "MECHANICAL EXECUTION"}
                  </span>
                )}
                {report.re_rate_status && (
                  <span style={{
                    fontSize: 9,
                    fontWeight: 700,
                    padding: "2px 6px",
                    borderRadius: 4,
                    background: report.re_rate_status === "complete" ? "rgba(239, 68, 68, 0.12)" : (report.re_rate_status === "partial" ? "rgba(245, 158, 11, 0.12)" : "rgba(20, 184, 122, 0.12)"),
                    color: report.re_rate_status === "complete" ? T.red || "var(--red)" : (report.re_rate_status === "partial" ? T.amber || "var(--amber)" : T.green || "var(--green)"),
                    border: `1px solid ${report.re_rate_status === "complete" ? T.red || "var(--red)" : (report.re_rate_status === "partial" ? T.amber || "var(--amber)" : T.green || "var(--green)")}`
                  }}>
                    RE-RATE: {report.re_rate_status.toUpperCase()}
                  </span>
                )}
              </div>
              {report.catalyst_nature_rationale && (
                <div style={{ fontSize: 11, color: T.textLight || "var(--text-light)", lineHeight: 1.4 }}>
                  <strong style={{ color: T.text || "var(--text)" }}>Trade Timing Insight:</strong> {report.catalyst_nature_rationale}
                </div>
              )}
            </div>
          )}
        </div>
      </Card>

      {/* MERGER ARBITRAGE CARD (DYNAMIC MATH & RISK) */}
      {report.merger_arb_data && mergerArbComputed && (
        <Card style={{ 
          background: "linear-gradient(135deg, rgba(20,184,122,0.04) 0%, rgba(59,130,246,0.04) 100%)", 
          border: `1px solid ${T.cardBorder || "var(--border)"}`, 
          borderRadius: 8, 
          padding: 20,
          boxShadow: "var(--shadow-md)"
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: T.blue || "var(--blue)", textTransform: "uppercase", marginBottom: 16, paddingBottom: 6, borderBottom: `2px solid ${T.blue || "var(--blue)"}` }}>
            <TrendingUp size={12} /> Active Merger Arbitrage Deal & Spread Analysis
          </div>
          
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1.5fr 1.5fr", gap: 20, marginBottom: 16 }}>
            
            {/* Deal Terms column */}
            <div>
              <div style={{ fontSize: 9, fontWeight: 700, color: T.textMuted || "var(--text-muted)", textTransform: "uppercase", marginBottom: 8 }}>Deal Terms</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <div style={{ fontSize: 11 }}>
                  Acquirer: <strong style={{ color: T.text || "var(--text)" }}>{report.merger_arb_data.acquirer_name || "Private Equity"}</strong> {report.merger_arb_data.acquirer_symbol && report.merger_arb_data.acquirer_symbol !== "CASH" && <span style={{ color: T.textMuted || "var(--text-muted)" }}>({report.merger_arb_data.acquirer_symbol})</span>}
                </div>
                <div style={{ fontSize: 11 }}>
                  Cash Component: <strong style={{ color: T.text || "var(--text)" }}>${report.merger_arb_data.cash_component?.toFixed(2) || "0.00"}</strong>
                </div>
                <div style={{ fontSize: 11 }}>
                  Stock Component: <strong style={{ color: T.text || "var(--text)" }}>{report.merger_arb_data.stock_component_ratio ? `${report.merger_arb_data.stock_component_ratio.toFixed(4)} shares` : "None (All-Cash)"}</strong>
                </div>
                
                {report.merger_arb_data.acquirer_symbol && report.merger_arb_data.acquirer_symbol !== "CASH" && (
                  <div style={{ marginTop: 6 }}>
                    <label style={{ fontSize: 8, color: T.textMuted || "var(--text-muted)", textTransform: "uppercase", display: "block", marginBottom: 2 }}>
                      Acquirer Price Input
                    </label>
                    <input
                      type="number"
                      step="0.01"
                      value={customAcquirerPrice}
                      onChange={(e) => setCustomAcquirerPrice(e.target.value === "" ? "" : parseFloat(e.target.value))}
                      style={{
                        background: "rgba(0,0,0,0.2)",
                        border: `1px solid ${T.cardBorder || "var(--border)"}`,
                        borderRadius: 4,
                        padding: "4px 8px",
                        fontSize: 11,
                        color: T.text || "var(--text)",
                        fontFamily: T.mono || "var(--font-mono)",
                        width: "100%",
                        outline: "none"
                      }}
                    />
                    {customAcquirerPrice !== "" && (
                      <button
                        type="button"
                        onClick={() => setCustomAcquirerPrice("")}
                        style={{
                          background: "none",
                          border: "none",
                          color: T.textMuted || "var(--text-muted)",
                          fontSize: 8,
                          textTransform: "uppercase",
                          cursor: "pointer",
                          padding: 0,
                          marginTop: 4,
                          display: "block"
                        }}
                      >
                        Reset to Live (${report.merger_arb_data.acquirer_price?.toFixed(2)})
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* Spread Valuation column */}
            <div style={{ borderLeft: `1px solid ${T.cardBorder || "var(--border)"}`, paddingLeft: 20 }}>
              <div style={{ fontSize: 9, fontWeight: 700, color: T.textMuted || "var(--text-muted)", textTransform: "uppercase", marginBottom: 8 }}>Live Spread Math</div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div>
                  <div style={{ fontSize: 9, color: T.textLight || "var(--text-light)" }}>Implied Deal Value</div>
                  <div style={{ fontSize: 16, fontWeight: 800, color: T.text || "var(--text)", marginTop: 2, fontFamily: T.mono || "var(--font-mono)" }}>
                    ${mergerArbComputed.impliedDealValue.toFixed(2)}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: 9, color: T.textLight || "var(--text-light)" }}>Gross Deal Spread</div>
                  <div style={{ 
                    fontSize: 16, 
                    fontWeight: 800, 
                    color: mergerArbComputed.grossSpreadVal >= 0 ? T.green || "var(--green)" : T.red || "var(--red)", 
                    marginTop: 2, 
                    fontFamily: T.mono || "var(--font-mono)" 
                  }}>
                    {mergerArbComputed.grossSpreadVal >= 0 ? "+" : ""}${mergerArbComputed.grossSpreadVal.toFixed(2)} ({mergerArbComputed.grossSpreadPct.toFixed(1)}%)
                  </div>
                </div>
              </div>
              <div style={{ fontSize: 10, color: T.textLight || "var(--text-light)", marginTop: 8 }}>
                Expected Close: <strong style={{ color: T.text || "var(--text)" }}>{report.merger_arb_data.expected_close || "N/A"}</strong>
              </div>
            </div>

            {/* Risk & Hedging column */}
            <div style={{ borderLeft: `1px solid ${T.cardBorder || "var(--border)"}`, paddingLeft: 20 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <span style={{ fontSize: 9, fontWeight: 700, color: T.textMuted || "var(--text-muted)", textTransform: "uppercase" }}>Unhedged Risk Profile</span>
                <span style={{ fontSize: 8, padding: "1px 5px", borderRadius: 3, background: T.redLight || "var(--red-light)", color: T.red || "var(--red)", fontWeight: 700 }}>NEGATIVE ASYMMETRY</span>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1.2fr", gap: 12 }}>
                <div>
                  <div style={{ fontSize: 9, color: T.textLight || "var(--text-light)" }}>Downside if Break</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: T.red || "var(--red)", marginTop: 2, fontFamily: T.mono || "var(--font-mono)" }}>
                    -${mergerArbComputed.unhedgedDownside.toFixed(2)}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: 9, color: T.textLight || "var(--text-light)" }}>Unhedged R/R</div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: T.red || "var(--red)", marginTop: 2, fontFamily: T.mono || "var(--font-mono)" }}>
                    {mergerArbComputed.unhedgedRRString}
                  </div>
                </div>
              </div>
              <div style={{ fontSize: 10, color: T.textLight || "var(--text-light)", marginTop: 8 }}>
                Pre-Announce Reference: <span style={{ color: T.text || "var(--text)" }}>${report.merger_arb_data.pre_announce_price?.toFixed(2) || "N/A"}</span>
              </div>
            </div>

          </div>

          <div style={{ display: "flex", gap: 8, background: "rgba(239, 68, 68, 0.05)", border: `1px solid rgba(239, 68, 68, 0.2)`, borderRadius: 6, padding: "10px 12px", fontSize: 11, color: T.textLight || "var(--text-light)", lineHeight: 1.5, marginBottom: 16 }}>
            <AlertTriangle size={16} color={T.red || "var(--red)"} style={{ flexShrink: 0, marginTop: 1 }} />
            <div>
              <strong style={{ color: T.red || "var(--red)" }}>Risk Warning:</strong> Entering an unhedged long position in {report.symbol} at current levels has a negative unhedged risk/reward of {mergerArbComputed.unhedgedRRString}. To execute a standard risk-arbitrage trade, investors typically buy the target ({report.symbol}) and short the acquirer ({report.merger_arb_data.acquirer_symbol && report.merger_arb_data.acquirer_symbol !== "CASH" ? report.merger_arb_data.acquirer_symbol : "PE"}) at the exchange ratio of {report.merger_arb_data.stock_component_ratio || 0} to lock in the spread.
            </div>
          </div>

          {/* Hedged Option Builder Suggestions */}
          <div style={{ borderTop: `1px dashed ${T.cardBorder || "var(--border)"}`, paddingTop: 16 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: T.green || "var(--green)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 12 }}>
              Hedged Option Builder Suggestions
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
              <div>
                <div style={{ fontSize: 9, color: T.textMuted || "var(--text-muted)", textTransform: "uppercase", marginBottom: 6 }}>Target Hedges ({report.symbol})</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {mergerArbComputed.targetHedges.map((hedge, idx) => (
                    <div key={idx} style={{ background: "rgba(255,255,255,0.01)", border: `1px solid ${T.cardBorder || "var(--border)"}`, borderRadius: 6, padding: "8px 10px" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                        <span style={{ fontSize: 10, fontWeight: 700, color: T.text || "var(--text)" }}>{hedge.strategy}</span>
                        <span style={{ fontSize: 8, padding: "1px 4px", borderRadius: 3, background: "rgba(20,184,122,0.1)", color: T.green || "var(--green)", fontFamily: T.mono || "var(--font-mono)" }}>{hedge.legs}</span>
                      </div>
                      <div style={{ fontSize: 9, color: T.textLight || "var(--text-light)", lineHeight: 1.3 }}>{hedge.description}</div>
                    </div>
                  ))}
                </div>
              </div>
              
              <div>
                <div style={{ fontSize: 9, color: T.textMuted || "var(--text-muted)", textTransform: "uppercase", marginBottom: 6 }}>
                  Acquirer Hedges {report.merger_arb_data.acquirer_symbol ? `(${report.merger_arb_data.acquirer_symbol})` : ""}
                </div>
                {mergerArbComputed.acquirerHedges.length > 0 ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    {mergerArbComputed.acquirerHedges.map((hedge, idx) => (
                      <div key={idx} style={{ background: "rgba(255,255,255,0.01)", border: `1px solid ${T.cardBorder || "var(--border)"}`, borderRadius: 6, padding: "8px 10px" }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                          <span style={{ fontSize: 10, fontWeight: 700, color: T.text || "var(--text)" }}>{hedge.strategy}</span>
                          <span style={{ fontSize: 8, padding: "1px 4px", borderRadius: 3, background: "rgba(59,130,246,0.15)", color: T.blue || "var(--blue)", fontFamily: T.mono || "var(--font-mono)" }}>{hedge.legs}</span>
                        </div>
                        <div style={{ fontSize: 9, color: T.textLight || "var(--text-light)", lineHeight: 1.3 }}>{hedge.description}</div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", border: `1px dashed ${T.cardBorder || "var(--border)"}`, borderRadius: 6, padding: 16, fontSize: 10, color: T.textMuted || "var(--text-muted)", minHeight: 90 }}>
                    No stock component (All-Cash transaction) - no acquirer hedge required.
                  </div>
                )}
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* Bloom timeline stages */}
      <Card>
        <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: T.green, textTransform: "uppercase", marginBottom: 16, paddingBottom: 6, borderBottom: `2px solid ${T.greenLight || "var(--green-light)"}` }}>
          <Compass size={12} /> Bloom Catalyst Timeline Stages
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16 }}>
          {/* Catalyst 1 */}
          {report.bloom_catalysts?.catalyst_1 && (
            <div style={{ 
              background: "rgba(0,0,0,0.15)", borderRadius: 6, padding: 14, 
              border: `1px solid ${report.bloom_catalysts.catalyst_1.detected ? T.purple || "var(--purple)" : T.cardBorder}`,
              opacity: report.bloom_catalysts.catalyst_1.detected ? 1 : 0.45
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <span style={{ fontSize: 9, color: T.textMuted, textTransform: "uppercase" }}>Stage 1</span>
                <span style={{ fontSize: 8, padding: "1px 5px", borderRadius: 3, background: report.bloom_catalysts.catalyst_1.detected ? "rgba(168,85,247,0.18)" : "rgba(255,255,255,0.03)", color: report.bloom_catalysts.catalyst_1.detected ? T.purple || "var(--purple)" : T.textMuted }}>
                  {report.bloom_catalysts.catalyst_1.detected ? "DETECTED" : "INACTIVE"}
                </span>
              </div>
              <div style={{ fontSize: 12, fontWeight: 700, color: report.bloom_catalysts.catalyst_1.detected ? T.text : T.textLight, marginBottom: 6 }}>
                <Tip k="STAGE_CATALYST">{report.bloom_catalysts.catalyst_1.title}</Tip>
              </div>
              <div style={{ fontSize: 11, color: T.textLight, lineHeight: 1.5, marginBottom: 8, fontFamily: T.sans }}>
                {report.bloom_catalysts.catalyst_1.description}
              </div>
              {report.bloom_catalysts.catalyst_1.detected && (
                <div style={{ fontSize: 9, color: T.purple || "var(--purple)", background: "rgba(168,85,247,0.06)", padding: "6px 8px", borderRadius: 4 }}>
                  <strong>Evidence:</strong> {report.bloom_catalysts.catalyst_1.evidence}
                </div>
              )}
            </div>
          )}

          {/* Catalyst 2 */}
          {report.bloom_catalysts?.catalyst_2 && (
            <div style={{ 
              background: "rgba(0,0,0,0.15)", borderRadius: 6, padding: 14, 
              border: `1px solid ${report.bloom_catalysts.catalyst_2.detected ? T.green : T.cardBorder}`,
              opacity: report.bloom_catalysts.catalyst_2.detected ? 1 : 0.45
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <span style={{ fontSize: 9, color: T.textMuted, textTransform: "uppercase" }}>Stage 2</span>
                <span style={{ fontSize: 8, padding: "1px 5px", borderRadius: 3, background: report.bloom_catalysts.catalyst_2.detected ? T.greenLight : "rgba(255,255,255,0.03)", color: report.bloom_catalysts.catalyst_2.detected ? T.green : T.textMuted }}>
                  {report.bloom_catalysts.catalyst_2.detected ? "ACTIVE" : "INACTIVE"}
                </span>
              </div>
              <div style={{ fontSize: 12, fontWeight: 700, color: report.bloom_catalysts.catalyst_2.detected ? T.text : T.textLight, marginBottom: 6 }}>
                <Tip k="STAGE_MILESTONE">{report.bloom_catalysts.catalyst_2.title}</Tip>
              </div>
              <div style={{ fontSize: 11, color: T.textLight, lineHeight: 1.5, marginBottom: 8, fontFamily: T.sans }}>
                {report.bloom_catalysts.catalyst_2.description}
              </div>
              {report.bloom_catalysts.catalyst_2.detected && (
                <div style={{ fontSize: 9, color: T.green, background: "rgba(20,184,122,0.06)", padding: "6px 8px", borderRadius: 4 }}>
                  <strong>Evidence:</strong> {report.bloom_catalysts.catalyst_2.evidence}
                </div>
              )}
            </div>
          )}

          {/* Catalyst 3 */}
          {report.bloom_catalysts?.catalyst_3 && (
            <div style={{ 
              background: "rgba(0,0,0,0.15)", borderRadius: 6, padding: 14, 
              border: `1px solid ${report.bloom_catalysts.catalyst_3.detected ? T.blue || "var(--blue)" : T.cardBorder}`,
              opacity: report.bloom_catalysts.catalyst_3.detected ? 1 : 0.45
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                <span style={{ fontSize: 9, color: T.textMuted, textTransform: "uppercase" }}>Stage 3</span>
                <span style={{ fontSize: 8, padding: "1px 5px", borderRadius: 3, background: report.bloom_catalysts.catalyst_3.detected ? "rgba(59,130,246,0.18)" : "rgba(255,255,255,0.03)", color: report.bloom_catalysts.catalyst_3.detected ? T.blue || "var(--blue)" : T.textMuted }}>
                  {report.bloom_catalysts.catalyst_3.detected ? "TRIGGERED" : "INACTIVE"}
                </span>
              </div>
              <div style={{ fontSize: 12, fontWeight: 700, color: report.bloom_catalysts.catalyst_3.detected ? T.text : T.textLight, marginBottom: 6 }}>
                <Tip k="STAGE_VERIFY">{report.bloom_catalysts.catalyst_3.title}</Tip>
              </div>
              <div style={{ fontSize: 11, color: T.textLight, lineHeight: 1.5, marginBottom: 8, fontFamily: T.sans }}>
                {report.bloom_catalysts.catalyst_3.description}
              </div>
              {report.bloom_catalysts.catalyst_3.detected && (
                <div style={{ fontSize: 9, color: T.blue || "var(--blue)", background: "rgba(59,130,246,0.06)", padding: "6px 8px", borderRadius: 4 }}>
                  <strong>Evidence:</strong> {report.bloom_catalysts.catalyst_3.evidence}
                </div>
              )}
            </div>
          )}
        </div>
      </Card>

      {/* Loeb criteria & activism */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <Card>
          {report.loeb_criteria?.catalyst_density && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontSize: 9, fontWeight: 700, color: T.textMuted, textTransform: "uppercase" }}>Catalyst Density (12-24M)</span>
                <span style={{ fontSize: 9, fontWeight: 700, color: T.purple || "var(--purple)" }}>
                  {report.loeb_criteria.catalyst_density.rating} Density
                </span>
              </div>
              <div style={{ fontSize: 12, color: T.text, lineHeight: 1.5, fontFamily: T.sans }}>
                {report.loeb_criteria.catalyst_density.analysis}
              </div>
            </div>
          )}
          {report.loeb_criteria?.sum_of_parts?.analysis && !["N/A.", "N/A", "-"].includes(report.loeb_criteria.sum_of_parts.analysis) && (
            <div style={{ borderTop: `1px solid ${T.divider}`, paddingTop: 14 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontSize: 9, fontWeight: 700, color: T.textMuted, textTransform: "uppercase" }}>Sum-of-Parts Discount</span>
                <span style={{ fontSize: 9, fontWeight: 700, color: report.loeb_criteria.sum_of_parts.detected ? T.green : T.textMuted }}>
                  {report.loeb_criteria.sum_of_parts.detected ? "SoP Dislocation Detected" : "No Dislocation"}
                </span>
              </div>
              <div style={{ fontSize: 12, color: T.text, lineHeight: 1.5, fontFamily: T.sans }}>
                {report.loeb_criteria.sum_of_parts.analysis}
              </div>
            </div>
          )}
        </Card>

        <Card>
          {report.loeb_criteria?.activism_potential?.analysis && !["-", "N/A.", "N/A"].includes(report.loeb_criteria.activism_potential.analysis) && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontSize: 9, fontWeight: 700, color: T.textMuted, textTransform: "uppercase" }}>Activism Footprint</span>
                <span style={{ fontSize: 9, fontWeight: 700, color: T.purple || "var(--purple)" }}>
                  {report.loeb_criteria.activism_potential.rating}
                </span>
              </div>
              <div style={{ fontSize: 12, color: T.text, lineHeight: 1.5, fontFamily: T.sans }}>
                {report.loeb_criteria.activism_potential.analysis}
              </div>
            </div>
          )}
          {report.loeb_criteria?.risk_reward?.analysis && (
            <div style={{ borderTop: `1px solid ${T.divider}`, paddingTop: 14 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{ fontSize: 9, fontWeight: 700, color: T.textMuted, textTransform: "uppercase" }}>Asymmetric Risk/Reward</span>
              </div>
              <div style={{ fontSize: 12, color: T.text, lineHeight: 1.5, fontFamily: T.sans }}>
                {report.loeb_criteria.risk_reward.analysis}
              </div>
            </div>
          )}
        </Card>
      </div>

      {/* Options signals */}
      {report.options_signals && (
        <Card>
          <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: T.green, textTransform: "uppercase", marginBottom: 16, paddingBottom: 6, borderBottom: `2px solid ${T.greenLight || "var(--green-light)"}` }}>
            <TrendingUp size={12} /> Options Market Catalyst Signals (ThetaData Pipeline)
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 12, marginBottom: 16 }}>
            <div style={{ background: "rgba(0,0,0,0.15)", padding: "10px 12px", borderRadius: 6, border: `1px solid ${T.cardBorder}` }}>
              <div style={{ fontSize: 8, color: T.textMuted, textTransform: "uppercase" }}>ATM IV</div>
              <div style={{ fontSize: 14, fontWeight: 700, marginTop: 4, fontFamily: T.mono }}>
                {report.options_signals.iv_current != null ? `${(report.options_signals.iv_current * 100).toFixed(1)}%` : "N/A"}
              </div>
            </div>
            <div style={{ background: "rgba(0,0,0,0.15)", padding: "10px 12px", borderRadius: 6, border: `1px solid ${T.cardBorder}` }}>
              <div style={{ fontSize: 8, color: T.textMuted, textTransform: "uppercase" }}>Skew (25d)</div>
              <div style={{ fontSize: 14, fontWeight: 700, marginTop: 4, fontFamily: T.mono, color: report.options_signals.skew_25d && report.options_signals.skew_25d < 0 ? T.green : T.text }}>
                {report.options_signals.skew_25d != null ? `${report.options_signals.skew_25d.toFixed(2)}` : "N/A"}
              </div>
            </div>
            <div style={{ background: "rgba(0,0,0,0.15)", padding: "10px 12px", borderRadius: 6, border: `1px solid ${T.cardBorder}` }}>
              <div style={{ fontSize: 8, color: T.textMuted, textTransform: "uppercase" }}>Structure</div>
              <div style={{ fontSize: 14, fontWeight: 700, marginTop: 4, fontFamily: T.mono, color: report.options_signals.term_structure === "backwardation" ? T.purple || "var(--purple)" : T.text }}>
                {report.options_signals.term_structure || "N/A"}
              </div>
            </div>
            <div style={{ background: "rgba(0,0,0,0.15)", padding: "10px 12px", borderRadius: 6, border: `1px solid ${T.cardBorder}` }}>
              <div style={{ fontSize: 8, color: T.textMuted, textTransform: "uppercase" }}>P/C Ratio</div>
              <div style={{ fontSize: 14, fontWeight: 700, marginTop: 4, fontFamily: T.mono }}>
                {report.options_signals.pc_oi_ratio != null ? report.options_signals.pc_oi_ratio.toFixed(2) : "N/A"}
              </div>
            </div>
            <div style={{ background: "rgba(0,0,0,0.15)", padding: "10px 12px", borderRadius: 6, border: `1px solid ${T.cardBorder}` }}>
              <div style={{ fontSize: 8, color: T.textMuted, textTransform: "uppercase" }}>Total OI</div>
              <div style={{ fontSize: 14, fontWeight: 700, marginTop: 4, fontFamily: T.mono }}>
                {report.options_signals.total_oi != null ? report.options_signals.total_oi.toLocaleString() : "N/A"}
              </div>
            </div>
            <div style={{ background: "rgba(0,0,0,0.15)", padding: "10px 12px", borderRadius: 6, border: `1px solid ${T.cardBorder}` }}>
              <div style={{ fontSize: 8, color: T.textMuted, textTransform: "uppercase" }}>Implied Move</div>
              <div style={{ fontSize: 14, fontWeight: 700, marginTop: 4, fontFamily: T.mono, color: T.purple || "var(--purple)" }}>
                {report.options_signals.implied_earnings_move_pct != null ? `±${report.options_signals.implied_earnings_move_pct.toFixed(1)}%` : "N/A"}
              </div>
            </div>
          </div>
          <div style={{ display: "flex", gap: 10, background: "rgba(0, 0, 0, 0.12)", border: `1px solid ${T.cardBorder}`, borderRadius: 6, padding: "12px 14px" }}>
            <div style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", background: "rgba(20,184,122,0.18)", color: T.green, padding: "2px 6px", borderRadius: 4, height: "fit-content", whiteSpace: "nowrap" }}>
              {report.options_signals.market_sentiment_flag}
            </div>
            <div style={{ fontSize: 11, color: T.textLight, lineHeight: 1.5, fontFamily: T.sans }}>
              {report.options_signals.overall_interpretation}
            </div>
          </div>
        </Card>
      )}

      {/* Evidence Feed */}
      {report.recent_events && report.recent_events.length > 0 && (
        <Card>
          <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: T.green, textTransform: "uppercase", marginBottom: 16, paddingBottom: 6, borderBottom: `2px solid ${T.greenLight || "var(--green-light)"}` }}>
            <Calendar size={12} /> Catalyst Evidence Feed (Filings & News Context)
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {report.recent_events.map((ev, idx) => (
              <div 
                key={idx} 
                style={{ 
                  display: "flex", 
                  alignItems: "center", 
                  gap: 12, 
                  padding: "8px 12px", 
                  background: "rgba(255,255,255,0.02)", 
                  border: `1px solid ${T.cardBorder}`, 
                  borderRadius: 6 
                }}
              >
                <span style={{ fontSize: 9, fontFamily: T.mono, color: T.textMuted, width: 80, flexShrink: 0 }}>
                  {ev.date.split(" ")[0]}
                </span>
                <span style={{ 
                  fontSize: 8, fontWeight: 700, padding: "2px 6px", borderRadius: 4, 
                  background: ev.type === "filing" ? "rgba(59,130,246,0.12)" : "rgba(168,85,247,0.12)",
                  color: ev.type === "filing" ? T.blue || "var(--blue)" : T.purple || "var(--purple)",
                  textTransform: "uppercase",
                  width: 50,
                  textAlign: "center"
                }}>
                  {ev.type}
                </span>
                <span style={{ fontSize: 12, color: T.text, flex: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", fontFamily: T.sans }}>
                  {ev.title}
                </span>
                {ev.link && (
                  <a 
                    href={ev.link} 
                    target="_blank" 
                    rel="noreferrer" 
                    style={{ color: T.green, display: "inline-flex", alignItems: "center", gap: 4, fontSize: 10, fontFamily: T.mono }}
                  >
                    link <ExternalLink size={10} />
                  </a>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

function MultiValuationCard({s}:{s:StockData}){
  const price = s.price;
  
  const models = [
    { name: "DCF-FCFF Valuation", fv: s.dcf_value, mos: s.dcf_fcff_mos, key: "dcf" },
    { name: "R&D Capitalized DCF", fv: s.rd_capitalized_dcf, mos: s.rd_capitalized_dcf_mos, key: "rd" },
    { name: "Owner Earnings Yield", fv: s.owner_earnings, mos: s.owner_earnings_mos, key: "oe" },
    { name: "EPV (Greenwald Valuation)", fv: s.epv_value, mos: s.epv_mos, key: "epv" },
    { name: "Graham Revised Valuation", fv: s.graham_revised, mos: s.graham_revised_mos, key: "graham" },
    { name: "IV15 Deep Value", fv: s.iv15_deep_value, mos: s.iv15_deep_value_mos, key: "iv15" },
  ];

  return (
    <Card style={{ marginBottom: 16 }}>
      <SH title="Multi-Valuation Comparison" icon={<Activity size={12} />} sub="At-a-glance comparison of all 6 absolute fair value models" />
      <div style={{ marginTop: 14 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16, padding: "8px 12px", background: T.bg, borderRadius: 6, border: `1px solid ${T.cardBorder}` }}>
          <span style={{ fontSize: 11, fontFamily: T.mono, color: T.textMuted }}>CURRENT STOCK PRICE</span>
          <span style={{ fontSize: 16, fontFamily: T.mono, fontWeight: 700, color: T.text }}>{fmtPrice(price, s.currency)} {s.currency}</span>
        </div>
        
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {models.map(m => {
            const fvVal = m.fv ?? 0;
            const hasVal = fvVal > 0;
            const mosPct = m.mos != null ? m.mos * 100 : 0;
            const mosColor = mosPct > 15 ? T.green : mosPct > 0 ? "#5a9e7a" : mosPct > -15 ? T.amber : T.red;
            
            // Visual progress bar geometry
            const minVal = Math.min(price, fvVal) * 0.8;
            const maxVal = Math.max(price, fvVal) * 1.2;
            const range = maxVal - minVal || 1;
            const pricePos = ((price - minVal) / range) * 100;
            const fvPos = hasVal ? ((fvVal - minVal) / range) * 100 : 0;
            
            return (
              <div key={m.key} style={{ display: "grid", gridTemplateColumns: "220px 100px 100px 1fr", alignItems: "center", gap: 14, padding: "10px 0", borderBottom: `1px solid ${T.divider}` }}>
                <span style={{ fontSize: 12, fontWeight: 600, color: T.text }}>{m.name}</span>
                <span style={{ fontSize: 12, fontFamily: T.mono, fontWeight: 700, color: hasVal ? T.text : T.textLight, textAlign: "right" }}>
                  {hasVal ? fmtPrice(fvVal, s.currency) : "—"}
                </span>
                <span style={{ fontSize: 11, fontFamily: T.mono, fontWeight: 700, color: hasVal ? mosColor : T.textLight, textAlign: "right" }}>
                  {hasVal ? `${mosPct >= 0 ? "+" : ""}${mosPct.toFixed(1)}%` : "—"}
                </span>
                <div style={{ position: "relative", height: 16, background: T.divider, borderRadius: 4, overflow: "hidden", margin: "0 8px" }}>
                  {hasVal ? (
                    <>
                      {/* Highlight area */}
                      {fvVal > price ? (
                        <div style={{ position: "absolute", left: `${pricePos}%`, width: `${fvPos - pricePos}%`, height: "100%", background: "var(--green)20" }} />
                      ) : (
                        <div style={{ position: "absolute", left: `${fvPos}%`, width: `${pricePos - fvPos}%`, height: "100%", background: "var(--red)10" }} />
                      )}
                      {/* Price pointer */}
                      <div style={{ position: "absolute", left: `${pricePos}%`, width: 3, height: "100%", background: T.text, zIndex: 3 }} title="Current Price" />
                      {/* FV pointer */}
                      <div style={{ position: "absolute", left: `${fvPos}%`, width: 8, height: 8, borderRadius: "50%", background: mosColor, top: 4, transform: "translateX(-4px)", border: "1.5px solid white", zIndex: 4 }} title="Fair Value" />
                    </>
                  ) : (
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", fontSize: 9, fontFamily: T.mono, color: T.textLight }}>valuation unavailable</div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </Card>
  );
}

// Radar peer-comps card — the intelligent business-model peer group (clusters by economics/end-market,
// not just GICS) with relative valuation/trend/momentum. Sourced from scans/peer_groups.json.
function RadarPeersCard({ pg }: { pg: any }) {
  if (!pg) return null;
  const peers: string[] = Array.isArray(pg.peers) ? pg.peers : [];
  const verdict: string = pg.verdict || "";
  const vColor = /cheap/i.test(verdict) ? T.green : /rich/i.test(verdict) ? T.red : T.amber;
  return (
    <Card style={{ marginBottom: 16 }}>
      <SH title="Comparable Peers — Radar" sub="Business-model peers (not just sector) · relative valuation / trend / momentum" />
      {peers.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
          {peers.map((p) => (
            <a key={p} href={`/stock/${p}`} style={{ textDecoration: "none" }}>
              <span style={{ fontSize: 11, padding: "3px 9px", borderRadius: 4, background: "rgba(59,130,246,0.10)", color: T.blue, fontFamily: T.mono, border: `1px solid rgba(59,130,246,0.2)`, cursor: "pointer" }}>{p}</span>
            </a>
          ))}
        </div>
      )}
      {verdict && (
        <div style={{ marginTop: 10 }}>
          <span style={{ fontSize: 10, fontFamily: T.mono, padding: "2px 8px", borderRadius: 4, background: vColor + "22", color: vColor, border: `1px solid ${vColor}55`, textTransform: "uppercase", letterSpacing: "0.05em" }}>{verdict.replace(/_/g, " ")}</span>
        </div>
      )}
      {pg.relative_comps && <p style={{ fontSize: 12, color: T.text, lineHeight: 1.6, fontFamily: T.sans, margin: "10px 0 0", textAlign: "justify" }}>{pg.relative_comps}</p>}
      {pg.rationale && <p style={{ fontSize: 11, color: T.textMuted, lineHeight: 1.5, fontFamily: T.sans, margin: "8px 0 0", fontStyle: "italic" }}>Why these peers: {pg.rationale}</p>}
    </Card>
  );
}

export default function StockDetail(){
  const params=useParams();const router=useRouter();const symbol=typeof params?.symbol==="string"?params.symbol:"";
  const[stock,setStock]=useState<StockData|null>(null);const[loading,setLoading]=useState(true);
  // Live options from IBKR (pushed to GCS by ibkr_options_batch on the gateway host).
  const[liveOptions,setLiveOptions]=useState<any>(null);
  const[opusStrategy,setOpusStrategy]=useState<OpusStrategy|null>(null);
  const[incomes,setIncomes]=useState<IncomeRow[]>([]);const[ratios,setRatios]=useState<RatioYear[]>([]);
  const[balanceSheets,setBalanceSheets]=useState<BalanceSheetRow[]>([]);const[cashFlows,setCashFlows]=useState<CashFlowRow[]>([]);
  const[incomesQ,setIncomesQ]=useState<IncomeRow[]>([]);
  const[balanceSheetsQ,setBalanceSheetsQ]=useState<BalanceSheetRow[]>([]);const[cashFlowsQ,setCashFlowsQ]=useState<CashFlowRow[]>([]);
  const[fmpLoading,setFmpLoading]=useState(true);
  // May 2026: stock-page tab system. "overview" = existing dashboard,
  // "track" = Buffett 10y track record table.
  const [activeTab, setActiveTab] = useState<"overview"|"story"|"catalyst"|"transcript"|"track"|"compare"|"chart"|"methodology"|"debate">("overview");
  const [speculairBaskets, setSpeculairBaskets] = useState<any>(null);
  // Per-symbol Opus debate HISTORY (dated). Drives the debate-panel time-travel dropdown.
  const [debateHistory, setDebateHistory] = useState<any[]>([]);
  const [histIdx, setHistIdx] = useState(0);  // 0 = latest (history is sorted newest-first)

  useEffect(() => {
    fetch(`${GCS_SCANS}/speculair_baskets.json`)
      .then((r) => { if (r.ok) return r.json(); throw new Error("GCS fetch failed"); })
      .then((d) => { if (d) setSpeculairBaskets(d); })
      .catch(() => {
        fetch("/speculair_baskets.json")
          .then((r) => (r.ok ? r.json() : null))
          .then((d) => { if (d) setSpeculairBaskets(d); })
          .catch((e) => console.error("Error loading speculair baskets:", e));
      });
  }, [symbol]);

  // Load this symbol's dated debate history (GCS first, public fallback). Sorted newest-first so
  // index 0 is the latest debate; the dropdown lets the user scroll back through prior runs.
  useEffect(() => {
    if (!symbol) return;
    const sym = symbol.toUpperCase();
    setDebateHistory([]); setHistIdx(0);
    const sortNew = (d: any[]) => [...d].sort((a, b) => (b.date || "").localeCompare(a.date || ""));
    fetch(`${GCS_SCANS}/speculair_debate_history/${sym}.json`)
      .then((r) => { if (r.ok) return r.json(); throw new Error("no gcs history"); })
      .then((d) => { if (Array.isArray(d) && d.length) setDebateHistory(sortNew(d)); })
      .catch(() => {
        fetch(`/speculair_debate_history/${sym}.json`)
          .then((r) => (r.ok ? r.json() : null))
          .then((d) => { if (Array.isArray(d) && d.length) setDebateHistory(sortNew(d)); })
          .catch(() => {});
      });
  }, [symbol]);

  // Radar peer-comps: intelligent business-model peer grouping (better than the GICS "similar stocks").
  const [peerGroup, setPeerGroup] = useState<any>(null);
  useEffect(() => {
    if (!symbol) return;
    const sym = symbol.toUpperCase();
    setPeerGroup(null);
    const pick = (d: any) => { if (d && typeof d === "object") setPeerGroup(d[sym] || d[symbol] || null); };
    fetch(`${GCS_SCANS}/peer_groups.json`)
      .then((r) => { if (r.ok) return r.json(); throw new Error("no gcs peers"); })
      .then(pick)
      .catch(() => {
        fetch(`/peer_groups.json`).then((r) => (r.ok ? r.json() : null)).then(pick).catch(() => {});
      });
  }, [symbol]);

  // Deep-link: ?tab=debate (from a Speculair pick's "View full analysis →") opens the
  // multi-agent debate directly instead of landing on Overview with the tab buried 8th.
  useEffect(() => {
    if (typeof window !== "undefined" && new URLSearchParams(window.location.search).get("tab") === "debate") {
      setActiveTab("debate");
    }
  }, []);

  const debateData = useMemo(() => {
    const basketPick = (() => {
    if (!speculairBaskets || !symbol) return null;
    const sym = symbol.toUpperCase();

    // 1. Check apex_basket
    const apexItem = (speculairBaskets.apex_basket || []).find(
      (p: any) => p.symbol?.toUpperCase() === sym
    );
    if (apexItem) {
      return { ...apexItem, type: "apex" };
    }

    // 2. Check capitulation_watchlist
    const wlItem = (speculairBaskets.capitulation_watchlist || []).find(
      (p: any) => p.symbol?.toUpperCase() === sym
    );
    if (wlItem) {
      return { ...wlItem, type: "watchlist" };
    }

    // 3. Check per_methodology_baskets
    const methBaskets = speculairBaskets.per_methodology_baskets || {};
    let foundPick: any = null;
    const selectedMethodologies: string[] = [];
    
    Object.entries(methBaskets).forEach(([methKey, methData]: [string, any]) => {
      const p = (methData.picks || []).find(
        (x: any) => x.symbol?.toUpperCase() === sym
      );
      if (p) {
        selectedMethodologies.push(methKey);
        if (!foundPick) {
          foundPick = { ...p };
        } else {
          // Merge
          foundPick.bull_thesis = foundPick.bull_thesis || p.bull_thesis;
          foundPick.bear_thesis = foundPick.bear_thesis || p.bear_thesis;
          foundPick.forcing_function = foundPick.forcing_function || p.forcing_function;
          foundPick.consensus_delta = foundPick.consensus_delta || p.consensus_delta;
        }
      }
    });

    if (foundPick) {
      return { ...foundPick, type: "methodology_pick", source_methodologies: selectedMethodologies };
    }

    return null;
    })();
    // Overlay the SELECTED dated history entry (default = latest) over the basket metadata so the
    // debate panels reflect whichever past debate the user picks, while preserving the basket's
    // type / entry_price / source_methodologies. Falls back to the basket pick when no history.
    if (debateHistory.length) {
      const sel = debateHistory[histIdx] || debateHistory[0];
      // Narrative (bull/bear/dossier/verdict/etc.) time-travels with the selection; banner-level
      // fields (type, director-vs-moderator conviction scale, entry data, methodologies) stay anchored
      // to the CURRENT basket so the status banner isn't corrupted by an older entry's moderator scale.
      return {
        ...(basketPick || {}), ...sel,
        type: (basketPick && basketPick.type) || "methodology_pick",
        conviction: (basketPick && basketPick.conviction != null) ? basketPick.conviction : (sel.conviction ?? 3),
        entry_price: basketPick ? basketPick.entry_price : undefined,
        entry_date: basketPick ? basketPick.entry_date : undefined,
        source_methodologies: (basketPick && basketPick.source_methodologies) || [],
        _fromHistory: true, _histDate: sel.date, _histIsLatest: histIdx === 0,
      };
    }
    return basketPick;
  }, [speculairBaskets, symbol, debateHistory, histIdx]);

  const hasDebate = !!debateData;

  useEffect(()=>{
    if(!symbol)return;
    const sym=symbol.toUpperCase();
    const regions=["sp500","europe","global"] as const;
    Promise.all(regions.map(async r=>{
      try {
        const res = await fetch(`${GCS_SCANS}/latest_${r}.json`, { cache: 'no-store' });
        if (res.ok) return await res.json();
      } catch(e){}
      try {
        const res = await fetch(`/latest_${r}.json`, { cache: 'no-store' });
        if (res.ok) return await res.json();
      } catch(e){}
      return null;
    })).then(results=>{
      let best:StockData|null=null, bestDate="";
      results.forEach(d=>{
        if(!d?.stocks)return;
        const f=d.stocks.find((x:StockData)=>x.symbol===sym);
        if(f&&(d.scan_date||"")>bestDate){best=f; bestDate=d.scan_date||"";}
      });
      if(!best){
        fetch(`${GCS_SCANS}/latest_global.json`, { cache: 'no-store' })
          .then(r=>{
            if (r.ok) return r.json();
            throw new Error("GCS fetch failed");
          })
          .then(d=>{
            const f=d.stocks?.find((s:StockData)=>s.symbol===sym);
            setStock(f||null); setLoading(false);
          })
          .catch(()=>{
            fetch("/latest_global.json")
              .then(r=>r.ok?r.json():null)
              .then(d=>{
                const f=d?.stocks?.find((s:StockData)=>s.symbol===sym);
                setStock(f||null); setLoading(false);
              })
              .catch(()=>{setStock(null); setLoading(false);});
          });
      } else {
        setStock(best); setLoading(false);
      }
    }).catch(()=>{setStock(null); setLoading(false);});
  },[symbol]);
  // Live IBKR options (US + EU) pushed to GCS by the gateway host's batch job.
  useEffect(()=>{
    if(!symbol)return;
    setLiveOptions(null);
    fetch(`${GCS_SCANS}/options_latest.json`,{cache:'no-store'})
      .then(r=>r.ok?r.json():null)
      .then(d=>{const o=d?.options?.[symbol.toUpperCase()]; if(o)setLiveOptions(o);})
      .catch(()=>{});
  },[symbol]);
  // Opus 4.8 nightly option-strategy (D9/D10 picks) pushed to GCS by opus_strategist.ps1.
  useEffect(()=>{
    if(!symbol)return;
    setOpusStrategy(null);
    fetch(`${GCS_SCANS}/options_strategies.json`,{cache:'no-store'})
      .then(r=>r.ok?r.json():null)
      .then(d=>{const o=d?.strategies?.[symbol.toUpperCase()]; if(o)setOpusStrategy(o);})
      .catch(()=>{});
  },[symbol]);
  useEffect(()=>{
    if(!symbol)return;
    setFmpLoading(true);
    const sym=symbol.toUpperCase();
    Promise.all([
      fmpFetch("income-statement",{symbol:sym,period:"annual",limit:12}),
      fmpFetch("ratios",{symbol:sym,period:"annual",limit:10}),
      fmpFetch("key-metrics",{symbol:sym,period:"annual",limit:10}),
      fmpFetch("balance-sheet-statement",{symbol:sym,period:"annual",limit:12}),
      fmpFetch("cash-flow-statement",{symbol:sym,period:"annual",limit:12}),
      fmpFetch("income-statement",{symbol:sym,period:"quarter",limit:21}),
      fmpFetch("balance-sheet-statement",{symbol:sym,period:"quarter",limit:21}),
      fmpFetch("cash-flow-statement",{symbol:sym,period:"quarter",limit:21}),
      fmpFetch("analyst-estimates",{symbol:sym,limit:2})
    ]).then(([inc,rat,km,bs,cf,incQ,bsQ,cfQ,est])=>{
      const mapInc = (r:any) => ({date:r.date, calendarYear:r.calendarYear||r.date?.slice(0,4), period:r.period, revenue:r.revenue, grossProfit:r.grossProfit, operatingIncome:r.operatingIncome, netIncome:r.netIncome, epsdiluted:r.epsdiluted||r.epsDiluted, ebitda:r.ebitda});
      const mapBs = (r:any) => ({date:r.date, calendarYear:r.calendarYear||r.date?.slice(0,4), period:r.period, totalAssets:r.totalAssets, totalLiabilities:r.totalLiabilities, totalEquity:r.totalStockholdersEquity, totalDebt:r.totalDebt, cashAndCashEquivalents:r.cashAndCashEquivalents, shortTermDebt:r.shortTermDebt, longTermDebt:r.longTermDebt, cashAndShortTermInvestments:r.cashAndShortTermInvestments});
      const mapCf = (r:any) => ({date:r.date, calendarYear:r.calendarYear||r.date?.slice(0,4), period:r.period, operatingCashFlow:r.operatingCashFlow, capitalExpenditure:r.capitalExpenditure, freeCashFlow:r.freeCashFlow});

      let finalIncomes = inc?.length ? inc.map(mapInc) : [];
      
      // Append consensus estimates as FY(e)
      if (est?.length) {
        // Sort ascending by date so we append the nearest future year first
        const sortedEst = [...est].sort((a:any, b:any) => String(a.date).localeCompare(String(b.date)));
        // Only take future estimates (date > last actual income date)
        const lastActualDate = finalIncomes.length > 0 ? finalIncomes[0].date : "1900-01-01";
        const futureEst = sortedEst.filter(e => e.date > lastActualDate);
        
        const mappedEst = futureEst.map(e => ({
          date: e.date,
          calendarYear: (e.date?.slice(0,4) || "FY") + "e",
          period: "FY",
          revenue: e.estimatedRevenueAvg,
          grossProfit: 0, // FMP doesn't typically provide gross profit consensus easily in this endpoint
          operatingIncome: e.estimatedEbitAvg || 0,
          netIncome: e.estimatedNetIncomeAvg || 0,
          epsdiluted: e.estimatedEpsAvg || 0,
          ebitda: e.estimatedEbitdaAvg || 0,
          isEstimate: true
        }));
        
        // Final array puts oldest at the end (descending order), so we unshift future estimates to the start
        finalIncomes = [...mappedEst.reverse(), ...finalIncomes];
      }

      setIncomes(finalIncomes);
      if(incQ?.length) setIncomesQ(incQ.map(mapInc));
      
      if(rat?.length){
        const evByYear=new Map<string,number>();
        (km||[]).forEach((k:any)=>{if(k?.fiscalYear!=null&&k.evToEBITDA!=null)evByYear.set(String(k.fiscalYear),k.evToEBITDA);});
        setRatios(rat.map((r:any)=>({...r,evToEBITDA:evByYear.get(String(r.fiscalYear))})) as RatioYear[]);
      }
      
      if(bs?.length) setBalanceSheets(bs.map(mapBs));
      if(bsQ?.length) setBalanceSheetsQ(bsQ.map(mapBs));
      if(cf?.length) setCashFlows(cf.map(mapCf));
      if(cfQ?.length) setCashFlowsQ(cfQ.map(mapCf));
      
      setFmpLoading(false);
    }).catch(()=>setFmpLoading(false));
  },[symbol]);

  if(loading)return<div style={{minHeight:"100vh",display:"flex",alignItems:"center",justifyContent:"center"}}><span style={{color:T.textMuted,fontFamily:T.mono,fontSize:12}}>Loading {symbol}...</span></div>;
  if(!stock){
    // Debate-only view: a name NOT in the screened universe (e.g. a Basket-13 special-sit like FIP)
    // but WITH a Speculair catalyst debate — render the debate instead of bailing to "No data".
    if(hasDebate){
      const c=debateData?.catalyst;const dc=Number(c?.director_conviction)||0;
      const tc=c?(c.cro_verdict==="A"&&dc>=80?"#2d7a4f":c.cro_verdict==="A"?"#2563eb":dc>=50?"#d97706":"#9ca3af"):"#9ca3af";
      return(
        <div style={{minHeight:"100vh",padding:"16px 24px",maxWidth:1320,margin:"0 auto"}}>
          <button onClick={()=>router.push("/")} style={{background:"none",border:"none",color:T.green,cursor:"pointer",display:"flex",alignItems:"center",gap:5,fontFamily:T.mono,fontSize:11,marginBottom:16,padding:0}}><ArrowLeft size={13}/> SCREENER</button>
          <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:6,flexWrap:"wrap"}}>
            <h1 style={{fontSize:26,fontWeight:700,color:T.text,fontFamily:T.mono,margin:0}}>{symbol?.toUpperCase()}</h1>
            {c&&<span style={{fontSize:10,padding:"3px 8px",borderRadius:4,border:`1px solid ${tc}66`,color:tc,fontFamily:T.mono,fontWeight:700,background:`${tc}14`,display:"inline-flex",alignItems:"center",gap:5}}><Zap size={11}/> CATALYST · {c.driver}{c.cro_verdict?` · ${c.cro_verdict}`:""}{c.director_conviction!=null?` ${c.director_conviction}`:""}</span>}
          </div>
          <p style={{margin:"0 0 16px",fontSize:11,color:T.textMuted,fontFamily:T.mono,lineHeight:1.5}}>Not in the screened universe — <strong>Speculair catalyst debate only</strong> (a Basket-13 special-sit). Trade it from the <span onClick={()=>router.push("/catalysts")} style={{color:T.green,cursor:"pointer",textDecoration:"underline"}}>13th Basket</span> view.</p>
          <SpeculairDebateCard debateData={debateData} debateHistory={debateHistory} histIdx={histIdx} setHistIdx={setHistIdx}/>
        </div>
      );
    }
    return<div style={{minHeight:"100vh",padding:40}}><button onClick={()=>router.push("/")} style={{background:"none",border:"none",color:T.green,cursor:"pointer",display:"flex",alignItems:"center",gap:6,fontFamily:T.mono,fontSize:12,marginBottom:24,padding:0}}><ArrowLeft size={14}/> Back</button><div style={{textAlign:"center",padding:60,color:T.textMuted,fontFamily:T.mono}}>No data for {symbol}.</div></div>;
  }

  const s=stock,clsColor=CLS_C[s.classification]||T.textMuted;

  return(
    <div style={{minHeight:"100vh",padding:"16px 24px",maxWidth:1320,margin:"0 auto"}}>
      <button onClick={()=>router.push("/")} style={{background:"none",border:"none",color:T.green,cursor:"pointer",display:"flex",alignItems:"center",gap:5,fontFamily:T.mono,fontSize:11,marginBottom:16,padding:0}}><ArrowLeft size={13}/> SCREENER</button>

      <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:20,paddingBottom:16,borderBottom:`1px solid ${T.divider}`}}>
        <div>
          <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:6,flexWrap:"wrap"}}>
            <h1 style={{fontSize:26,fontWeight:700,color:T.text,fontFamily:T.mono,margin:0}}>{s.symbol}</h1>
            <span style={{fontSize:10,padding:"3px 8px",borderRadius:4,border:`1px solid ${clsColor}30`,color:clsColor,fontFamily:T.mono,fontWeight:600,background:`${clsColor}08`}}>{s.classification?.replace("_"," ")}</span>
            {s.has_catalyst&&<Zap size={14} color={T.purple} fill={T.purple}/>}
            {/* Scale-out tier badge — set by the Scale-Director AFTER the multi-agent debate (see speculair_debate_history scale block) */}
            {debateData?.scale?.tier && (()=>{const sc=debateData.scale;const tc=sc.tier==="CORE"?"#2d7a4f":sc.tier==="LEVER"?"#8b5cf6":sc.tier==="TACTICAL"?"#d97706":"#9ca3af";return(
              <span title={[sc.role,sc.rationale].filter(Boolean).join(" — ")} style={{fontSize:10,padding:"3px 8px",borderRadius:4,border:`1px solid ${tc}66`,color:tc,fontFamily:T.mono,fontWeight:700,background:`${tc}14`,display:"inline-flex",alignItems:"center",gap:5,cursor:"help"}}>
                <Layers size={11}/> SCALE · {sc.basket_label||sc.basket} · {sc.tier}{sc.conviction!=null?` ${sc.conviction}`:""}
              </span>
            );})()}
            {/* Catalyst badge — event-driven special-sit (Basket-13 funnel run through the full debate); CRO verdict + Director 0-100 */}
            {debateData?.catalyst && (()=>{const c=debateData.catalyst;const dc=Number(c.director_conviction)||0;const tc=(c.cro_verdict==="A"&&dc>=80)?"#2d7a4f":c.cro_verdict==="A"?"#2563eb":dc>=50?"#d97706":"#9ca3af";return(
              <span title={c.binding_reason||""} style={{fontSize:10,padding:"3px 8px",borderRadius:4,border:`1px solid ${tc}66`,color:tc,fontFamily:T.mono,fontWeight:700,background:`${tc}14`,display:"inline-flex",alignItems:"center",gap:5,cursor:"help"}}>
                <Zap size={11}/> CATALYST · {c.driver}{c.cro_verdict?` · ${c.cro_verdict}`:""}{c.director_conviction!=null?` ${c.director_conviction}`:""}
              </span>
            );})()}
          </div>
          <div style={{display:"flex",alignItems:"baseline",gap:12}}><span style={{fontSize:30,fontWeight:600,color:T.text,fontFamily:T.mono}}>{fmtPrice(s.price,s.currency)}</span><span style={{fontSize:13,color:T.textMuted,fontFamily:T.mono}}>{s.currency}</span></div>
        </div>
        <div style={{display:"flex",flexDirection:"column",alignItems:"flex-end",gap:8}}>
          <AddToPortfolioStock stock={s}/>
        </div>
      </div>

{/* TradingView */}
      {activeTab !== "chart" && !toTradingViewSymbol(s.symbol).startsWith("EURONEXT:") && (
        <Card style={{marginBottom:16,padding:0,overflow:"hidden"}}><div style={{height:300}}><iframe src={`https://s.tradingview.com/widgetembed/?frameElementId=tv&symbol=${encodeURIComponent(toTradingViewSymbol(s.symbol))}&interval=D&hidesidetoolbar=1&symboledit=0&saveimage=0&toolbarbg=0a1817&studies=MASimple%409na%40na%40na~50~0~~&studies=MASimple%409na%40na%40na~200~0~~&theme=dark&style=1&timezone=exchange&withdateranges=1&width=100%25&height=100%25`} style={{width:"100%",height:"100%",border:"none"}} allowFullScreen/></div></Card>
      )}
      {activeTab !== "chart" && toTradingViewSymbol(s.symbol).startsWith("EURONEXT:") && (
         <Card style={{marginBottom:16,padding:24,textAlign:"center",color:T.textMuted,fontFamily:T.mono,fontSize:11}}>
           <Activity size={16} style={{margin:"0 auto 8px",color:T.textLight}}/>
           Euronext widget data is restricted by TradingView. Open the Chart tab for an FMP historical fallback.
         </Card>
      )}

      {/* Tab bar */}
      <div style={{display:"flex",gap:0,marginBottom:16,borderBottom:`1px solid ${T.cardBorder}`}}>
        {(hasDebate
          ? (["overview","story","catalyst","transcript","track","compare","chart","debate","methodology"] as const)
          : (["overview","story","catalyst","transcript","track","compare","chart","methodology"] as const)
        ).map((tab) => (
          <button key={tab} onClick={()=>setActiveTab(tab)}
            style={{
              padding:"10px 20px",border:"none",cursor:"pointer",background:"transparent",
              fontFamily:T.mono,fontSize:11,fontWeight:600,letterSpacing:"0.05em",textTransform:"uppercase",
              color:activeTab===tab?T.green:T.textMuted,
              borderBottom:activeTab===tab?`2px solid ${T.green}`:"2px solid transparent",
              marginBottom:-1,
            }}>
            {tab==="overview"?"Overview"
             :tab==="story"?"Investor Personas"
             :tab==="catalyst"?"Catalyst Watch"
             :tab==="transcript"?"Transcript"
             :tab==="track"?"Track Record"
             :tab==="compare"?"Compare"
             :tab==="chart"?"Chart"
             :tab==="debate"?"Speculair Debate"
             :"Scoring Methodology"}
          </button>
        ))}
      </div>

      {activeTab==="track" ? (
        <TrackRecordTable s={s}/>
      ) : activeTab==="compare" ? (
        <ComparisonTab stockA={s} fmpA={{incomes,ratios,balanceSheets,cashFlows,incomesQ,balanceSheetsQ,cashFlowsQ}}/>
      ) : activeTab==="story" ? (
        <div style={{display:"flex",flexDirection:"column",gap:16}}>
          <StockStoryCard s={s} incomes={incomes} ratios={ratios} />
        </div>
      ) : activeTab==="catalyst" ? (
        <CatalystTabContent symbol={s.symbol} />
      ) : activeTab==="debate" ? (
        <SpeculairDebateCard debateData={debateData} debateHistory={debateHistory} histIdx={histIdx} setHistIdx={setHistIdx} />
      ) : activeTab==="methodology" ? (
        <ScoringMethodologyCard />
      ) : activeTab==="transcript" ? (
        <TranscriptInsights symbol={s.symbol} dossier={debateData?.interrogator_dossier} />
      ) : activeTab==="chart" ? (
        <ReactFinancialChartTab symbol={s.symbol} />
      ) : (
        <>
          
      {/* Company profile */}
      <div style={{marginBottom:16}}>
        <CompanyProfileCard symbol={s.symbol}/>
      </div>

      {/* Multi-Valuation Comparison Card */}
      <MultiValuationCard s={s} />

      {/* Catalyst + Sentiment */}
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14,marginBottom:16}}>
        <CatalystTimeline s={s}/>
        <SentimentCard s={s}/>
      </div>

      {/* P20 Move Probability Card — full width, shows probability ladder + spread edge */}
      {(s.hit_prob??0)>0&&<div style={{marginBottom:16}}><P20Card s={s}/></div>}

      {/* Massive options card — spread suggestion + IV data */}
      {(()=>{
        // Merge live IBKR options (from GCS) into the stock for the card.
        const so:StockData = liveOptions ? {...s,
          options_iv_current: liveOptions.iv_current ?? s.options_iv_current,
          options_iv_rank: liveOptions.iv_rank ?? s.options_iv_rank,
          options_iv_samples: liveOptions.iv_samples ?? s.options_iv_samples,
          options_spread: liveOptions.spread ?? s.options_spread,
        } : s;
        const show = so.options_iv_current!=null||so.options_iv_rank!=null||so.options_spread||so.options_pc_ratio!=null||so.options_term_structure||so.options_implied_earnings_move;
        return show ? <div style={{marginBottom:16}}><MassiveOptionsCard s={so}/></div> : null;
      })()}

      {/* Opus 4.8 nightly option-strategy (D9/D10 picks only) */}
      {opusStrategy && (opusStrategy.structure||"").toLowerCase()!=="skip" &&
        <div style={{marginBottom:16}}><OpusStrategyCard st={opusStrategy} symbol={s.symbol} price={s.price}/></div>}

      {/* ═══ v8: Quality / Growth / Value+Smart Money — 3 columns of factor detail ═══ */}
       <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14,marginBottom:16}}>
        <div>
          <QualityValueCard s={s}/>
        </div>
        <div style={{display:"flex",flexDirection:"column",gap:14}}>
          <SmartMoneyCard s={s}/>
          <MomentumPanel s={s}/>
        </div>
      </div>

      {/* Financial Charts */}
      <div style={{marginBottom:16}}>
        <FinancialChartsPanel 
          incomes={incomes} balanceSheets={balanceSheets} cashFlows={cashFlows} 
          incomesQ={incomesQ} balanceSheetsQ={balanceSheetsQ} cashFlowsQ={cashFlowsQ}
          loading={fmpLoading} 
        />
      </div>

      <div style={{marginBottom:16}}>
        <LiquidityProfileCard 
          balanceSheets={balanceSheets} 
          balanceSheetsQ={balanceSheetsQ} 
          ratios={ratios} 
          cashFlows={cashFlows}
          cashFlowsQ={cashFlowsQ}
          incomes={incomes}
          incomesQ={incomesQ}
          s={s} 
          loading={fmpLoading} 
        />
      </div>

      {/* FMP Panels — multi-year tables (separate from v8 scoring; pure historical context) */}
      <GrowthPanel incomes={incomes} loading={fmpLoading} ratios={ratios}/>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14,margin:"16px 0"}}><ProfitPanel ratios={ratios} loading={fmpLoading}/><ValPanel ratios={ratios} loading={fmpLoading}/></div>
      {peerGroup && <RadarPeersCard pg={peerGroup} />}
      <div style={{display:"grid",gridTemplateColumns:"2fr 1fr",gap:14,margin:"16px 0"}}>
        <PeersPanel symbol={s.symbol} companyName={s.symbol}/>
        <NewsFeed symbol={s.symbol}/>
      </div>

{/* Active signals */}
      {s.reasons?.length>0&&<Card style={{marginBottom:16}}><SH title="Active Signals"/><div style={{display:"flex",flexWrap:"wrap",gap:6,marginTop:4}}>{s.reasons.map((r,i)=><span key={i} style={{fontSize:10,padding:"4px 10px",borderRadius:4,fontFamily:T.mono,background:r.includes("⚠")?T.redLight:T.greenLight,border:`1px solid ${r.includes("⚠")?"var(--red)":T.greenBorder}`,color:r.includes("⚠")?T.red:T.textMuted}}>{r}</span>)}</div></Card>}
        </>
      )}
    </div>
  );
}
