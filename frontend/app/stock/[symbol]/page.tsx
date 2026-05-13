"use client";
import React, { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, TrendingUp, TrendingDown, Minus, Activity, Brain, RefreshCw, Loader2, Newspaper, BarChart2, Zap, Shield, ChevronUp, ChevronDown } from "lucide-react";

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
  // signal?:string;  // REMOVED v1.2 (May 2026) — BUY/HOLD/SELL semantics gone
  factor_scores?:FactorScores;
  quality_score?:number;catalyst_score?:number;catalyst_flags?:string[];
  has_catalyst?:boolean;days_to_earnings?:number;
  insider_score?:number;insider_net_buys?:number;insider_buy_ratio?:number;
  inst_score?:number;inst_holders_change?:number;inst_accumulation?:number;
  transcript_sentiment?:number;transcript_summary?:string;transcript_score?:number;
  proximity_52wk?:number;proximity_score?:number;
  earnings_momentum?:number;earnings_score?:number;upside_score?:number;
  hit_prob?:number;
  // Smart Money Score (Apr 2026) — LTR-derived weighted factor score.
  // Pass-2 / US-only. null for non-US stocks; partial coverage for pass-1.
  smart_money_score?:number|null;
  smart_money_components?:Record<string,number>;
  smart_money_weight?:number;
  factor_coverage?:number;factors_evaluated?:string[];factors_missing?:string[];
  // v7.2.1 Tradier options enrichment
  tradier_iv_current?:number|null;
  tradier_iv_rank?:number|null;
  tradier_iv_samples?:number;
  tradier_spread?:{
    strategy:string;spot:number;expiration:string;dte:number;
    long_strike:number;short_strike:number;long_mid:number;short_mid:number;
    net_debit:number;max_gain_per_contract:number;max_loss_per_contract:number;
    break_even_price:number;break_even_move_pct:number;risk_reward:number;
    description:string;
  }|null;
  // v7.2.3 expanded Tradier signals
  tradier_pc_ratio?:number|null;
  tradier_iv_30d?:number|null;
  tradier_iv_60d?:number|null;
  tradier_iv_90d?:number|null;
  tradier_term_structure?:string|null;
  tradier_implied_earnings_move?:{
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
interface BalanceSheetRow{date:string;calendarYear:string;period?:string;totalAssets:number;totalLiabilities:number;totalEquity:number;totalDebt:number;cashAndCashEquivalents:number;shortTermDebt?:number;longTermDebt?:number;cashAndShortTermInvestments?:number;}
interface CashFlowRow{date:string;calendarYear:string;period?:string;operatingCashFlow:number;capitalExpenditure:number;freeCashFlow:number;}
interface RatioYear{date:string;fiscalYear:string;grossProfitMargin:number;operatingProfitMargin:number;netProfitMargin:number;returnOnEquity:number;returnOnAssets:number;returnOnCapitalEmployed:number;currentRatio:number;debtToEquityRatio:number;priceToEarningsRatio:number;priceToSalesRatio:number;priceToBookRatio:number;priceToFreeCashFlowRatio:number;dividendYieldPercentage:number;freeCashFlowOperatingCashFlowRatio:number;interestCoverageRatio:number;dividendPayoutRatio:number;revenuePerShare:number;netIncomePerShare:number;bookValuePerShare:number;freeCashFlowPerShare:number;operatingCashFlowPerShare:number;dividendPerShare:number;priceToOperatingCashFlowRatio:number;priceToEarningsGrowthRatio:number;evToEBITDA?:number;}
interface CompositePoint{date:string;composite:number;signal:string;price:number;}

// ── Theme ──────────────────────────────────────────────────────────────────────
const T={bg:"#ffffff",card:"#ffffff",cardBorder:"#e5e7eb",cardShadow:"0 1px 3px rgba(0,0,0,0.06),0 1px 2px rgba(0,0,0,0.04)",text:"#1a1a1a",textMuted:"#6b7280",textLight:"#9ca3af",green:"#2d7a4f",greenLight:"#e8f5ee",greenBorder:"#b8dcc8",red:"#ef4444",redLight:"#fef2f2",amber:"#f59e0b",amberLight:"#fffbeb",blue:"#2563eb",purple:"#8b5cf6",divider:"#f3f4f6",mono:"'JetBrains Mono','SF Mono',monospace",sans:"'DM Sans',-apple-system,sans-serif"};
const SIG_C:Record<string,{bg:string;fg:string;border:string}>={"STRONG BUY":{bg:"#f5f3ff",fg:"#8b5cf6",border:"#ddd6fe"},BUY:{bg:T.greenLight,fg:"#10b981",border:T.greenBorder},WATCH:{bg:T.amberLight,fg:T.amber,border:"#fde68a"},HOLD:{bg:"#f9fafb",fg:T.textMuted,border:T.cardBorder},SELL:{bg:T.redLight,fg:T.red,border:"#fecaca"}};
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
  "Div%": "Dividend yield. Annual dividend as percentage of stock price.\nHigh yield + declining price = potential value trap.\n✅ Ideal: 1-4% with growing payout\n❌ Avoid: >8% (likely unsustainable)"
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
    <div style={{padding:"10px 12px",borderRadius:6,background:"#fff",border:`1px solid ${T.greenBorder}`,display:"flex",flexDirection:"column",gap:6,minWidth:280}}>
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
        <button onClick={handleSave} disabled={status==="saving"||status==="saved"} style={{flex:1,padding:"5px 10px",border:"none",borderRadius:3,cursor:status==="saving"?"wait":"pointer",background:status==="saved"?"#10b981":status==="error"?T.red:T.green,color:"#fff",fontSize:10,fontFamily:T.mono,fontWeight:600}}>{status==="saving"?"Saving...":status==="saved"?"✓ Added":status==="error"?"! Retry":"Save"}</button>
        <button onClick={()=>{setOpen(false);setStatus("idle");setErr("");}} style={{padding:"5px 10px",border:`1px solid ${T.cardBorder}`,borderRadius:3,cursor:"pointer",background:"#fff",color:T.textMuted,fontSize:10,fontFamily:T.mono}}>Cancel</button>
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
    <div style={{marginTop: 10, padding:"10px 12px",borderRadius:6,background:"#fff",border:`1px solid ${T.purple}`,display:"flex",flexDirection:"column",gap:6}}>
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
        <button onClick={handleSave} disabled={status==="saving"||status==="saved"} style={{flex:1,padding:"5px 10px",border:"none",borderRadius:3,cursor:status==="saving"?"wait":"pointer",background:status==="saved"?"#10b981":status==="error"?T.red:T.purple,color:"#fff",fontSize:10,fontFamily:T.mono,fontWeight:600}}>{status==="saving"?"Saving...":status==="saved"?"✓ Tracked":status==="error"?"! Retry":"Track"}</button>
        <button onClick={()=>{setOpen(false);setStatus("idle");setErr("");}} style={{padding:"5px 10px",border:`1px solid ${T.cardBorder}`,borderRadius:3,cursor:"pointer",background:"#fff",color:T.textMuted,fontSize:10,fontFamily:T.mono}}>Cancel</button>
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
      {FACTOR_ORDER.map((k,i)=>{const a=ang(i),lx=cx+Math.cos(a)*(r+28),ly=cy+Math.sin(a)*(r+28),v=raw[i],isNull=v==null,c=isNull?"#d1d5db":((v??0)>0.7?"#10b981":(v??0)>0.4?T.amber:T.red);return<g key={k}><line x1={cx} y1={cy} x2={cx+Math.cos(a)*r} y2={cy+Math.sin(a)*r} stroke="#e5e7eb" strokeWidth={0.6} strokeDasharray={isNull?"4,3":"none"}/><text x={lx} y={ly-5} textAnchor="middle" dominantBaseline="middle" fontSize={10} fontFamily={T.mono} fill={isNull?"#d1d5db":T.textMuted} fontWeight="600">{FL[k]}</text><text x={lx} y={ly+9} textAnchor="middle" dominantBaseline="middle" fontSize={12} fontFamily={T.mono} fill={c} fontWeight="700">{isNull?"—":((v??0)*100).toFixed(0)}</text></g>;})}
      <polygon points={vals.map((v,i)=>`${cx+Math.cos(ang(i))*Math.max(0.05,v)*r},${cy+Math.sin(ang(i))*Math.max(0.05,v)*r}`).join(" ")} fill={fill} fillOpacity={0.12} stroke={fill} strokeWidth={2} strokeLinejoin="round"/>
      {vals.map((v,i)=><circle key={i} cx={cx+Math.cos(ang(i))*Math.max(0.05,v)*r} cy={cy+Math.sin(ang(i))*Math.max(0.05,v)*r} r={4} fill={raw[i]==null?"#d1d5db":fill} stroke="#fff" strokeWidth={1.5}/>)}
      <text x={cx} y={size-4} textAnchor="middle" fontSize={9} fontFamily={T.mono} fill={T.textLight}>{covCount}/{FACTOR_ORDER.length} factors</text>
    </svg>
  );
}

function FactorBar({name,weight,score,detail}:{name:string;weight:number;score:number|null;detail:string}){
  if(score==null)return<div style={{padding:"8px 0",borderBottom:`1px solid ${T.divider}`,opacity:0.45}}><div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:4}}><div style={{display:"flex",alignItems:"baseline",gap:6}}><span style={{fontSize:12,fontFamily:T.mono,fontWeight:600,color:"#d1d5db"}}>{name}</span><span style={{fontSize:9,fontFamily:T.mono,color:"#d1d5db"}}>({weight}%)</span></div><span style={{fontSize:11,fontFamily:T.mono,color:"#d1d5db",fontStyle:"italic"}}>no data</span></div><div style={{height:5,borderRadius:3,background:T.divider}}><div style={{height:"100%",width:0}}/></div><div style={{fontSize:10,fontFamily:T.mono,color:"#d1d5db",lineHeight:1.5}}>Weight redistributed to evaluated factors</div></div>;
  const c=score>0.7?"#10b981":score>0.4?T.amber:T.red;
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
    <div style={{padding:"8px 10px",borderRadius:5,border:`1px solid ${T.cardBorder}`,background:"#fafbfc"}}>
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
        <div style={{fontSize:10,color:T.amber,fontFamily:T.mono,marginBottom:10,padding:"6px 10px",background:T.amberLight,borderRadius:4,border:`1px solid #fde68a`}}>
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

  // Calibrated multipliers from backtest (21,650 OOS samples, May 2026)
  const p5  = Math.min(p20 * 3.41, 0.80);
  const p10 = Math.min(p20 * 2.29, 0.65);
  const p15 = Math.min(p20 * 1.49, 0.50);

  const decile = p20>=0.17?10:p20>=0.07?9:p20>=0.05?8:p20>=0.03?7:p20>=0.02?6:p20>=0.013?5:p20>=0.009?4:p20>=0.006?3:p20>=0.004?2:1;
  const signal = p20>=0.15?"STRONG":p20>=0.08?"MODERATE":p20>=0.03?"MILD":"WEAK";
  const signalColor = signal==="STRONG"?T.green:signal==="MODERATE"?T.amber:T.textMuted;

  const pBar=(threshold:string, pct:number, isRaw:boolean)=>{
    const w=Math.max(pct,2);
    const color=pct>=40?T.green:pct>=20?"#10b981":pct>=10?T.amber:T.textMuted;
    return(
      <div style={{display:"flex",alignItems:"center",gap:8,padding:"5px 0",borderBottom:`1px solid ${T.divider}`}}>
        <div style={{width:50,fontSize:10,fontFamily:T.mono,color:T.textMuted,fontWeight:600,textAlign:"right"}}>{threshold}</div>
        <div style={{flex:1,height:16,background:T.divider,borderRadius:3,overflow:"hidden",position:"relative"}}>
          <div style={{width:`${w}%`,height:"100%",background:color,borderRadius:3,transition:"width 0.4s"}}/>
          <span style={{position:"absolute",left:8,top:0,lineHeight:"16px",fontSize:10,fontFamily:T.mono,fontWeight:700,color:w>30?"#fff":T.text}}>{pct.toFixed(0)}%</span>
        </div>
        <div style={{width:36,fontSize:9,fontFamily:T.mono,color:T.textLight,textAlign:"right"}}>{isRaw?"model":"est."}</div>
      </div>
    );
  };

  return(
    <Card>
      <SH title="Move Probability (ML)" icon={<TrendingUp size={12}/>}
        sub={`Decile ${decile} · ${signal} signal`}/>
      <div style={{display:"flex",alignItems:"baseline",gap:12,marginBottom:14,paddingBottom:14,borderBottom:`1px solid ${T.divider}`}}>
        <div>
          <div style={{fontSize:9,color:T.textMuted,fontFamily:T.mono,fontWeight:600,letterSpacing:"0.08em"}}>P(+20% IN 4W)</div>
          <div style={{fontSize:28,color:signalColor,fontFamily:T.mono,fontWeight:700,marginTop:2}}>{p20pct.toFixed(0)}%</div>
          <div style={{fontSize:9,color:T.textLight,fontFamily:T.mono,marginTop:1}}>D{decile} · {(p20pct/5.3).toFixed(1)}x base rate</div>
        </div>
        <div style={{flex:1,fontSize:11,fontFamily:T.sans,color:T.textMuted,lineHeight:1.5,paddingLeft:16,borderLeft:`1px solid ${T.divider}`}}>
          {signal==="STRONG"
            ? "Model sees elevated move probability. Top decile stocks touched +20% in 22% of cases (vs 1% for D1)."
            : signal==="MODERATE"
            ? "Moderate move signal. D7-D9 range: ~10-15% touch rate, 54-57% close above +5%."
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
        time_model_v2 · TOP3 ensemble (XGB+GBM+LGB) · 43 features · OOS AUC 0.7836.
        P(+20%) is direct model output; lower thresholds scaled from calibrated backtest distributions.
        D10 hit rate: 26.3% vs D1: 0.5% (53x odds ratio). Not investment advice.
      </div>
    </Card>
  );
}


// ═══════════════════════════════════════════════════════════════════════
// TradierOptionsCard v3 — Always proposes a spread (live or estimated).
// EV calculation drives the signal: green = edge, red = no edge.
// ═══════════════════════════════════════════════════════════════════════

function TradierOptionsCard({s}:{s:StockData}){
  const hasIV=s.tradier_iv_current!=null||s.tradier_iv_rank!=null;
  const hasPositioning=s.tradier_pc_ratio!=null||s.tradier_term_structure!=null||s.tradier_implied_earnings_move!=null;
  const p20=s.hit_prob||0;
  if(!hasIV&&!hasPositioning&&p20<=0) return null;

  const ivr=s.tradier_iv_rank;
  const iv=s.tradier_iv_current;
  const samples=s.tradier_iv_samples||0;
  const ivrColor=ivr==null?T.textMuted:ivr<=30?T.green:ivr<=60?T.amber:T.red;
  const ivrLabel=ivr==null?"Not enough data":ivr<=25?"Cheap premium":ivr<=40?"Normal":ivr<=60?"Elevated":"Rich — options expensive";
  const p20pct=p20*100;

  const p5close  = Math.min(p20 * 3.41, 0.80);
  const p10close = Math.min(p20 * 2.29, 0.65);
  const p15close = Math.min(p20 * 1.49, 0.50);

  const tradierSp = s.tradier_spread;
  const isLive = tradierSp != null;

  const roundStrike = (v:number):number => {
    const inc = s.price>=50?5:s.price>=10?2.5:1;
    return Math.round(v/inc)*inc;
  };

  // Synthesize estimated spread when Tradier doesn't provide one
  const sp = tradierSp ?? (()=>{
    const spot = s.price;
    if(spot<=0 || p20<=0) return null;
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

  const assessment = !sp ? "NO DATA"
    : p20<=0 ? "NO MODEL"
    : evPerDollar > 0.15 ? "★ STRONG EDGE"
    : evPerDollar > 0.05 ? "MODERATE EDGE"
    : evPerDollar > 0 ? "MARGINAL EDGE"
    : evPerDollar > -0.10 ? "SLIGHT NEGATIVE"
    : "NO EDGE";
  const assessColor = assessment.includes("STRONG") ? "#8b5cf6"
    : assessment.includes("MODERATE") ? T.green
    : assessment.includes("MARGINAL") ? T.amber
    : T.red;

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
        sub={sp ? `${assessment} · EV ${ev>=0?"+":""}$${ev.toFixed(0)}/contract${!isLive?" · estimated":""}` : "IV data only"}/>

      {/* IV strip */}
      <div style={{display:"grid",gridTemplateColumns:"repeat(4, 1fr)",gap:14,marginBottom:14,paddingBottom:14,borderBottom:`1px solid ${T.divider}`}}>
        {metric("IV RANK",ivr!=null?ivr.toFixed(0):"—",samples<20?`${samples}/20 samples`:ivrLabel,ivrColor)}
        {metric("CURRENT IV",iv!=null?`${(iv*100).toFixed(0)}%`:"—","ATM 30d annualized")}
        {metric("P20 (MODEL)",p20>0?`${p20pct.toFixed(0)}%`:"—",p20>=0.15?"D9-D10":p20>=0.08?"D7-D8":p20>=0.03?"D5-D6":"low signal",p20>=0.15?T.green:p20>=0.08?T.amber:T.textMuted)}
        {metric("ASSESSMENT",assessment.replace("★ ",""),sp?`EV/risk: ${evPerDollar>=0?"+":""}${(evPerDollar*100).toFixed(0)}%`:"",assessColor)}
      </div>

      {/* Market positioning */}
      {(s.tradier_pc_ratio!=null||s.tradier_term_structure!=null||s.tradier_implied_earnings_move!=null)&&(
        <div style={{marginBottom:14,paddingBottom:14,borderBottom:`1px solid ${T.divider}`}}>
          <div style={{fontSize:9,color:T.textMuted,fontFamily:T.mono,fontWeight:600,letterSpacing:"0.08em",marginBottom:8}}>MARKET POSITIONING</div>
          <div style={{display:"grid",gridTemplateColumns:"repeat(3, 1fr)",gap:14}}>
            <div>
              <div style={{fontSize:10,color:T.textMuted,fontFamily:T.mono,fontWeight:600}}>P/C VOL RATIO</div>
              {s.tradier_pc_ratio!=null?(()=>{const pc=s.tradier_pc_ratio;const label=pc<0.5?"Heavy call buying":pc<1.0?"Mild bullish":pc<1.5?"Neutral/mild hedging":pc<2.5?"Elevated put buying":"Extreme fear";const color=pc<0.5?T.green:pc<1.5?T.textMuted:pc<2.5?T.amber:T.red;return(<><div style={{fontSize:16,color,fontFamily:T.mono,fontWeight:700,marginTop:2}}>{pc.toFixed(2)}</div><div style={{fontSize:9,color:T.textLight,fontFamily:T.mono,marginTop:1}}>{label}</div></>);})():(<div style={{fontSize:16,color:T.textLight,fontFamily:T.mono,marginTop:2}}>—</div>)}
            </div>
            <div>
              <div style={{fontSize:10,color:T.textMuted,fontFamily:T.mono,fontWeight:600}}>IV TERM STRUCTURE</div>
              {(s.tradier_iv_30d!=null||s.tradier_iv_60d!=null||s.tradier_iv_90d!=null)?(()=>{const ts=s.tradier_term_structure;const tsLabel=ts==="backwardation"?"⚠ Near-term event priced":ts==="contango"?"✓ Normal calm market":ts==="flat"?"→ Flat curve":"—";const tsColor=ts==="backwardation"?T.amber:ts==="contango"?T.green:T.textMuted;const iv30=s.tradier_iv_30d,iv60=s.tradier_iv_60d,iv90=s.tradier_iv_90d;return(<><div style={{display:"flex",alignItems:"baseline",gap:6,marginTop:2,fontFamily:T.mono}}><span style={{fontSize:12,fontWeight:700,color:T.text}}>{iv30!=null?`${(iv30*100).toFixed(0)}%`:"—"}</span><span style={{fontSize:9,color:T.textLight}}>→</span><span style={{fontSize:12,fontWeight:700,color:T.text}}>{iv60!=null?`${(iv60*100).toFixed(0)}%`:"—"}</span><span style={{fontSize:9,color:T.textLight}}>→</span><span style={{fontSize:12,fontWeight:700,color:T.text}}>{iv90!=null?`${(iv90*100).toFixed(0)}%`:"—"}</span></div><div style={{fontSize:9,color:tsColor,fontFamily:T.mono,marginTop:2,fontWeight:600}}>{tsLabel}</div><div style={{fontSize:8,color:T.textLight,fontFamily:T.mono,marginTop:1}}>30d · 60d · 90d</div></>);})():(<div style={{fontSize:16,color:T.textLight,fontFamily:T.mono,marginTop:2}}>—</div>)}
            </div>
            <div>
              <div style={{fontSize:10,color:T.textMuted,fontFamily:T.mono,fontWeight:600}}>IMPLIED EARNINGS MOVE</div>
              {s.tradier_implied_earnings_move?(()=>{const iem=s.tradier_implied_earnings_move;return(<><div style={{fontSize:16,color:T.text,fontFamily:T.mono,fontWeight:700,marginTop:2}}>±{iem.pct.toFixed(1)}%</div><div style={{fontSize:9,color:T.textLight,fontFamily:T.mono,marginTop:1}}>ATM straddle ${iem.straddle.toFixed(2)} · {iem.earnings_date}</div></>);})():(<><div style={{fontSize:16,color:T.textLight,fontFamily:T.mono,marginTop:2}}>—</div><div style={{fontSize:9,color:T.textLight,fontFamily:T.mono,marginTop:1}}>No earnings in next 60d</div></>)}
            </div>
          </div>
        </div>
      )}

      {/* ═══ SPREAD PROPOSAL ═══ */}
      {sp&&p20>0&&(<>
        {!isLive&&(
          <div style={{padding:"6px 10px",borderRadius:4,background:T.amberLight,border:"1px solid #fde68a",fontSize:10,fontFamily:T.mono,color:T.amber,fontWeight:600,marginBottom:10,display:"inline-block"}}>
            ⚠ ESTIMATED SPREAD — verify strikes and premiums with your broker before trading
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
        <div style={{padding:"12px 14px",borderRadius:6,background:evPositive?"#f0fdf4":"#fef2f2",border:`1px solid ${evPositive?"#bbf7d0":"#fecaca"}`,marginBottom:14}}>
          <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:8}}>
            <div>
              <div style={{fontWeight:600,color:evPositive?T.green:T.red,fontSize:9,fontFamily:T.mono,letterSpacing:"0.08em",marginBottom:4}}>EXPECTED VALUE{!isLive?" (ESTIMATED)":""}</div>
              <div style={{fontSize:22,fontWeight:700,fontFamily:T.mono,color:evPositive?T.green:T.red}}>
                {ev>=0?"+":""}${ev.toFixed(0)} <span style={{fontSize:11,fontWeight:500,color:T.textMuted}}>/ contract</span>
              </div>
            </div>
            <div style={{textAlign:"right"}}>
              <div style={{fontSize:9,color:T.textMuted,fontFamily:T.mono,fontWeight:600,marginBottom:2}}>EV / RISK</div>
              <div style={{fontSize:16,fontWeight:700,fontFamily:T.mono,color:evPositive?T.green:T.red}}>
                {evPerDollar>=0?"+":""}{(evPerDollar*100).toFixed(0)}%
              </div>
            </div>
          </div>
          <div style={{fontSize:10,fontFamily:T.mono,color:T.textMuted,lineHeight:1.6}}>
            {Math.round(pMaxProfit*100)}% × ${sp.max_gain_per_contract.toFixed(0)} − {Math.round((1-pBreakeven)*100)}% × ${sp.max_loss_per_contract.toFixed(0)} = <b style={{color:evPositive?T.green:T.red}}>{ev>=0?"+":""}${ev.toFixed(0)}</b>
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
                background:t.ok?"#f0fdf4":"#f9fafb",color:t.ok?T.green:T.textLight,
                border:`1px solid ${t.ok?"#bbf7d0":T.divider}`,
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
          <div style={{padding:"10px 12px",borderRadius:5,background:"#f5f3ff",border:"1px solid #ddd6fe",fontSize:11,fontFamily:T.mono,color:T.text,lineHeight:1.6,marginBottom:10}}>
            <div style={{fontWeight:600,color:"#8b5cf6",fontSize:9,letterSpacing:"0.08em",marginBottom:4}}>VERIFY WITH BROKER</div>
            Look up: <b>{s.symbol} {sp.long_strike}/{sp.short_strike} call spread</b>, ~30 DTE.
            Actual premiums will differ — the EV above uses IV-estimated costs.
            If real net debit is lower, EV improves; if higher, EV worsens.
          </div>
        )}

        {/* Sizing */}
        <div style={{padding:"10px 12px",borderRadius:5,background:T.amberLight,border:"1px solid #fde68a",fontSize:11,fontFamily:T.sans,color:T.text,lineHeight:1.55,marginBottom:8}}>
          <div style={{fontWeight:600,color:T.amber,fontFamily:T.mono,fontSize:9,letterSpacing:"0.08em",marginBottom:4}}>⚠ SIZING</div>
          Speculative overlay: <b>1-2% of portfolio per spread, max 5% total</b>. Probabilities are model estimates (AUC 0.78). Spreads can lose 100% of debit. {!evPositive && <><b style={{color:T.red}}>EV is negative — no statistical edge at current premiums.</b></>}
        </div>

        <div style={{marginTop: 10, display:"flex", justifyContent:"flex-end"}}>
          <AddOptionToPortfolio stock={s} sp={sp} ev={ev} iv={iv||0} />
        </div>
      </>)}

      {/* No spread possible (no P20 or can't construct) */}
      {(!sp || p20<=0)&&hasIV&&(
        <div style={{padding:"8px 12px",borderRadius:5,background:"#f8faf9",border:`1px solid ${T.divider}`,fontSize:10,fontFamily:T.mono,color:T.textMuted,marginTop:8}}>
          {p20<=0
            ? "ML model probability not available — spread EV cannot be calculated. IV data shown above for reference."
            : "Spread estimation requires stock price > $0 and P20 > 0%."}
        </div>
      )}

      <div style={{fontSize:9,color:T.textLight,fontFamily:T.mono,marginTop:8,lineHeight:1.4}}>
        Probabilities from time_model_v2 (OOS AUC 0.7836), calibrated against 21,650 OOS samples.
        {isLive?" IV/Greeks from Tradier (ORATS-sourced).":" Spread estimated from price + IV; verify with broker."}
        {" "}EV = P(max profit) × gain − P(miss) × loss. Not investment advice.
      </div>
    </Card>
  );
}

// Keep old name as alias so the existing render block doesn't break
const TradierSpreadCard=TradierOptionsCard;

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
  if(loading) return<Card><SH title="Track Record (All Models)" icon={<TrendingUp size={12}/>}/><div style={{padding:30,textAlign:"center",color:T.textLight,fontSize:11,fontFamily:T.mono}}>Loading history...</div></Card>;
  if(err) return<Card><SH title="Track Record (All Models)" icon={<TrendingUp size={12}/>}/><div style={{padding:30,textAlign:"center",color:T.textLight,fontSize:11,fontFamily:T.mono}}>{err}</div></Card>;
  if(rows.length<2) return<Card><SH title="Track Record (All Models)" icon={<TrendingUp size={12}/>}/><div style={{padding:30,textAlign:"center",color:T.textLight,fontSize:11,fontFamily:T.mono}}>Only {rows.length} scan{rows.length===1?"":"s"} recorded so far. Chart appears once 2+ scans have tracked this stock.</div></Card>;

  const W=720,H=240,PL=46,PR=46,PT=20,PB=30;
  
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
  
  const fmtDate=(d:string)=>d.slice(5);
  const tickIdxs=rows.length<=6?rows.map((_,i)=>i):[0,Math.floor(rows.length*0.2),Math.floor(rows.length*0.4),Math.floor(rows.length*0.6),Math.floor(rows.length*0.8),rows.length-1];

  return(
    <Card>
      <SH title="Track Record (All Models)" icon={<TrendingUp size={12}/>}
        sub={`${rows.length} scans · Price ${pChg>=0?"+":""}${pChg.toFixed(1)}%`}/>
      <div style={{overflow:"hidden", marginTop: 10, background:"#fafbfc", borderRadius: 8, border:`1px solid ${T.divider}`, padding: "10px 0"}}>
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
          
          {iMom >= 0 && <path d={momPath} fill="none" stroke="#8b5cf6" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" strokeDasharray="6 4" opacity={mode==="momentum"||!mode?1:0.3} />}
          {iFa >= 0 && <path d={faPath} fill="none" stroke="#f59e0b" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" strokeDasharray="6 4" opacity={mode==="fallen_angel"?1:0.3} />}
          {iCus >= 0 && <path d={cusPath} fill="none" stroke="#3b82f6" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" strokeDasharray="6 4" opacity={mode==="compounder_us"?1:0.3} />}
          {iCgl >= 0 && <path d={cglPath} fill="none" stroke="#06b6d4" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round" strokeDasharray="6 4" opacity={mode==="compounder_global"?1:0.3} />}

          <circle cx={xAt(rows.length-1)} cy={yPrice(last[1])} r={4} fill={T.green} stroke="#fff" strokeWidth={1.5} />
          {iMom >= 0 && <circle cx={xAt(iMom)} cy={yComp(mom[iMom])} r={3} fill="#8b5cf6" opacity={mode==="momentum"||!mode?1:0.3} />}
          {iFa >= 0 && <circle cx={xAt(iFa)} cy={yComp(fa[iFa])} r={3} fill="#f59e0b" opacity={mode==="fallen_angel"?1:0.3} />}
          {iCus >= 0 && <circle cx={xAt(iCus)} cy={yComp(cus[iCus])} r={3} fill="#3b82f6" opacity={mode==="compounder_us"?1:0.3} />}
          {iCgl >= 0 && <circle cx={xAt(iCgl)} cy={yComp(cgl[iCgl])} r={3} fill="#06b6d4" opacity={mode==="compounder_global"?1:0.3} />}

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

      <div style={{display:"flex",justifyContent:"center",flexWrap:"wrap",gap:"12px 24px",marginTop:14,fontSize:10,fontFamily:T.mono,color:T.text}}>
        <div style={{display:"inline-flex",alignItems:"center",gap:6,fontWeight:600}}>
          <span style={{width:12,height:12,borderRadius:3,background:T.green}}/> Price (Left)
        </div>
        {iMom >= 0 && <div style={{display:"inline-flex",alignItems:"center",gap:6,opacity:mode==="momentum"||!mode?1:0.5}}>
          <span style={{width:16,height:2,background:"#8b5cf6",backgroundImage:`repeating-linear-gradient(90deg,#8b5cf6 0 4px,transparent 4px 6px)`}}/> Momentum (Right)
        </div>}
        {iFa >= 0 && <div style={{display:"inline-flex",alignItems:"center",gap:6,opacity:mode==="fallen_angel"?1:0.5}}>
          <span style={{width:16,height:2,background:"#f59e0b",backgroundImage:`repeating-linear-gradient(90deg,#f59e0b 0 4px,transparent 4px 6px)`}}/> Fallen Angel (Right)
        </div>}
        {iCus >= 0 && <div style={{display:"inline-flex",alignItems:"center",gap:6,opacity:mode==="compounder_us"?1:0.5}}>
          <span style={{width:16,height:2,background:"#3b82f6",backgroundImage:`repeating-linear-gradient(90deg,#3b82f6 0 4px,transparent 4px 6px)`}}/> CMP-US (Right)
        </div>}
        {iCgl >= 0 && <div style={{display:"inline-flex",alignItems:"center",gap:6,opacity:mode==="compounder_global"?1:0.5}}>
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
        {bvps>price&&<div style={{position:"absolute",left:`${pos(price)}%`,top:0,bottom:0,width:`${pos(bvps)-pos(price)}%`,background:`#10b98112`,borderRadius:4}}/>}

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
    <div style={{display:"inline-flex",border:`1px solid ${T.cardBorder}`,borderRadius:6,overflow:"hidden",background:"#fff"}}>
      {opts.map(o=>{
        const active=o.k===mode;
        const ok=(available as any)[o.k];
        return(
          <button key={o.k} onClick={()=>ok&&onChange(o.k)} disabled={!ok}
            style={{padding:"5px 10px",border:"none",cursor:ok?"pointer":"not-allowed",
              background:active?T.green:"transparent",color:active?"#fff":(ok?T.text:T.textLight),
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
      <div style={{padding:"10px 12px",borderRadius:6,background:T.amberLight,border:`1px solid #fde68a`,marginTop:10}}>
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
      <div style={{padding:"10px 12px",borderRadius:6,background:T.amberLight,border:`1px solid #fde68a`,marginTop:10}}>
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
    <div style={{padding:"10px 12px",borderRadius:6,background:"#fafbfc",border:`1px solid ${T.divider}`,marginTop:10}}>
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
  const rc=s.rsi>70?T.red:s.rsi<30?"#10b981":s.rsi>60?"#10b981":s.rsi<40?T.amber:T.textMuted;
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
          <div style={{width:8,height:8,borderRadius:"50%",background:gc?"#10b981":T.red,boxShadow:`0 0 6px ${gc?"#10b981":T.red}40`}}/>
          <span title={crossTip} style={{fontSize:11,fontFamily:T.mono,fontWeight:600,color:gc?"#10b981":T.red,cursor:"help",borderBottom:`1px dotted ${gc?"#10b98180":T.red+"80"}`}}>
            {gc?"Golden Cross":"Death Cross"}
          </span>
        </div>
        <div style={{display:"flex",gap:6}}>
          {[{l:`Price ${p50?">":"<"} SMA50`,ok:p50,v:fmtPrice(s.sma50)},{l:`Price ${p200?">":"<"} SMA200`,ok:p200,v:fmtPrice(s.sma200)}].map((m,i)=>(
            <div key={i} style={{flex:1,padding:"6px 8px",borderRadius:6,fontSize:10,fontFamily:T.mono,background:m.ok?T.greenLight:T.redLight,color:m.ok?"#10b981":T.red,border:`1px solid ${m.ok?T.greenBorder:"#fecaca"}`}}>
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
        <div style={{position:"relative",height:8,borderRadius:4,overflow:"hidden",background:`linear-gradient(to right, #10b981 0%, #10b981 30%, ${T.divider} 30%, ${T.divider} 70%, ${T.red} 70%, ${T.red} 100%)`}}>
          <div style={{position:"absolute",left:`${s.rsi}%`,top:-2,width:12,height:12,borderRadius:"50%",background:"#fff",border:`2px solid ${rc}`,transform:"translateX(-6px)",boxShadow:"0 1px 3px rgba(0,0,0,0.15)"}}/>
        </div>
      </div>
      <div style={{marginBottom:14}}>
        <div style={{display:"flex",justifyContent:"space-between",marginBottom:4}}>
          <span title={TOOLTIPS["52-Week Range"]} style={{fontSize:10,fontFamily:T.mono,color:T.textMuted,cursor:"help",borderBottom:`1px dotted ${T.textLight}`}}>52-Week Range</span>
          <span style={{fontSize:10,fontFamily:T.mono,color:T.textMuted}}>{p52.toFixed(0)}%</span>
        </div>
        <div style={{position:"relative",height:6,borderRadius:3,background:T.divider}}>
          <div style={{position:"absolute",left:0,top:0,bottom:0,width:`${p52}%`,borderRadius:3,background:`linear-gradient(to right, #10b981, ${p52>80?T.amber:"#10b981"})`}}/>
          <div style={{position:"absolute",left:`${p52}%`,top:-3,width:12,height:12,borderRadius:"50%",background:"#fff",border:"2px solid #10b981",transform:"translateX(-6px)",boxShadow:"0 1px 2px rgba(0,0,0,0.1)"}}/>
        </div>
        <div style={{display:"flex",justifyContent:"space-between",fontSize:9,fontFamily:T.mono,color:T.textLight,marginTop:3}}>
          <span>{fmtPrice(s.year_low,s.currency)}</span>
          <span style={{fontWeight:600,color:T.text}}>{fmtPrice(s.price,s.currency)}</span>
          <span>{fmtPrice(s.year_high,s.currency)}</span>
        </div>
      </div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:4}}>
        {inds.map((d,i)=>(
          <div key={i} style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"5px 8px",borderRadius:4,fontSize:10,fontFamily:T.mono,background:d.b?T.greenLight:"#fafafa",border:`1px solid ${d.b?T.greenBorder:T.divider}`}}>
            <span title={TOOLTIPS[d.l]} style={{color:T.textMuted,fontWeight:500,cursor:"help",borderBottom:`1px dotted ${T.textLight}`}}>{d.l}</span>
            <span style={{color:d.b?"#10b981":T.textMuted,fontWeight:600}}>{d.v}</span>
          </div>
        ))}
      </div>
      <div style={{marginTop:12}}>
        <div style={{display:"flex",justifyContent:"space-between",marginBottom:4}}>
          <span title={TOOLTIPS["Bull Score"]} style={{fontSize:10,fontFamily:T.mono,color:T.textMuted,cursor:"help",borderBottom:`1px dotted ${T.textLight}`}}>Bull Score</span>
          <span style={{fontSize:11,fontFamily:T.mono,fontWeight:700,color:s.bull_score>=7?"#10b981":s.bull_score>=4?T.amber:T.red}}>{s.bull_score}/10</span>
        </div>
        <div style={{display:"flex",gap:3}}>
          {Array.from({length:10},(_,i)=>{
            const a=i<s.bull_score,c=s.bull_score>=7?"#10b981":s.bull_score>=4?T.amber:T.red;
            return <div key={i} style={{flex:1,height:6,borderRadius:3,background:a?c:T.divider}}/>;
          })}
        </div>
      </div>
    </Card>
  );
}

// ── TranscriptInsights ─────────────────────────────────────────────────────────
function TranscriptInsights({symbol}:{symbol:string}) {
  const [analysis, setAnalysis] = useState<string|null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string|null>(null);
  const [qFound, setQFound] = useState(0);

  useEffect(() => {
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
  }, [symbol]);

  const f = useCallback(async () => {
    setLoading(true);
    setError(null);
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
      <SH title="Transcript Insights" icon={<Brain size={12} />} sub={qFound > 0 ? `${qFound} quarters analyzed` : ""} />
      {analysis ? (
        <div>
          <div style={{ fontSize: 11, lineHeight: 1.7, color: T.text, fontFamily: T.sans, whiteSpace: "pre-wrap" }}>
            {analysis}
          </div>
          <button onClick={f} style={{ marginTop: 12, background: "none", border: `1px solid ${T.cardBorder}`, borderRadius: 6, padding: "6px 12px", cursor: "pointer", fontSize: 10, fontFamily: T.mono, color: T.textMuted, display: "flex", alignItems: "center", gap: 4 }}>
            <RefreshCw size={10} /> Refresh
          </button>
        </div>
      ) : (
        <div style={{ textAlign: "center", padding: "20px 0" }}>
          <button onClick={f} disabled={loading} style={{ background: loading ? T.divider : T.green, border: "none", borderRadius: 6, padding: "10px 20px", color: loading ? T.textMuted : "#fff", fontFamily: T.mono, fontSize: 11, fontWeight: 600, cursor: loading ? "not-allowed" : "pointer", display: "inline-flex", alignItems: "center", gap: 6 }}>
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
function NewsFeed({symbol}:{symbol:string}){const[news,setNews]=useState<NewsItem[]>([]);const[loading,setLoading]=useState(true);useEffect(()=>{fmpFetch("news/stock",{symbols:symbol,limit:15}).then(d=>{if(Array.isArray(d)){const u=symbol.toUpperCase();const filtered=(d as (NewsItem&{symbol?:string})[]).filter(n=>!n.symbol||n.symbol.toUpperCase()===u);setNews(filtered);}setLoading(false);}).catch(()=>setLoading(false));},[symbol]);return<Card><SH title="Recent News" icon={<Newspaper size={12}/>}/>{loading?<div style={{padding:20,textAlign:"center",color:T.textLight,fontSize:11,fontFamily:T.mono}}><Loader2 size={14} style={{animation:"spin 1s linear infinite"}}/></div>:news.length===0?<div style={{padding:16,textAlign:"center",color:T.textLight,fontSize:11,fontFamily:T.mono}}>No recent news</div>:<div style={{display:"flex",flexDirection:"column",gap:8}}>{news.slice(0,8).map((n,i)=><a key={i} href={n.url} target="_blank" rel="noopener noreferrer" style={{display:"block",padding:"10px 12px",borderRadius:6,border:`1px solid ${T.divider}`,background:"#f8faf9",textDecoration:"none"}}><div style={{fontSize:12,fontWeight:600,color:T.text,lineHeight:1.4,marginBottom:4}}>{n.title}</div><div style={{display:"flex",gap:8,fontSize:9,fontFamily:T.mono,color:T.textLight}}><span>{n.site}</span><span>·</span><span>{new Date(n.publishedDate).toLocaleDateString()}</span></div></a>)}</div>}</Card>;}

// ── FMP Growth/Profitability/Valuation ──────────────────────────────────────────
const cs_:React.CSSProperties={padding:"6px 10px",textAlign:"right",fontSize:11,fontFamily:T.mono,borderBottom:`1px solid ${T.divider}`,whiteSpace:"nowrap"};
const hs_:React.CSSProperties={...cs_,color:T.textMuted,fontWeight:500,fontSize:10};
const ls_:React.CSSProperties={...cs_,textAlign:"left",color:T.textMuted,fontWeight:500};
function GC({v}:{v:number|null}){if(v==null)return<td style={cs_}>—</td>;return<td style={{...cs_,color:gClr(v),fontWeight:600}}>{(v*100).toFixed(1)}%</td>;}

function GrowthPanel({incomes,loading,ratios}:{incomes:IncomeRow[];loading:boolean;ratios?:RatioYear[]}){if(loading)return<Card><SH title="Growth Rates" icon={<BarChart2 size={12}/>}/><div style={{padding:24,textAlign:"center",color:T.textLight,fontSize:11,fontFamily:T.mono}}><Loader2 size={14} style={{animation:"spin 1s linear infinite"}}/></div></Card>;if(!incomes.length)return null;const sorted=[...incomes].sort((a,b)=>a.date.localeCompare(b.date));const latest=sorted[sorted.length-1];const n=sorted.length;function cagr(f:keyof IncomeRow,y:number):number|null{if(n<y+1)return null;return safeCagr(sorted[n-1-y][f]as number,latest[f]as number,y);}function yoy(f:keyof IncomeRow):number|null{if(n<2)return null;const prev=sorted[n-2][f]as number,cur=latest[f]as number;if(!prev||prev<=0)return null;return(cur-prev)/prev;}const ms:[string,keyof IncomeRow][]=[["Revenue","revenue"],["Gross Profit","grossProfit"],["Operating Income","operatingIncome"],["Net Income","netIncome"],["EPS","epsdiluted"],["EBITDA","ebitda"]];const fcfSorted=ratios?[...ratios].sort((a,b)=>a.date.localeCompare(b.date)):[];const fcfN=fcfSorted.length;const fcfLatest=fcfN>0?fcfSorted[fcfN-1]:null;function fcfYoy():number|null{if(fcfN<2)return null;const prev=fcfSorted[fcfN-2].freeCashFlowPerShare,cur=fcfSorted[fcfN-1].freeCashFlowPerShare;if(!prev||prev<=0)return null;return(cur-prev)/prev;}function fcfCagr(y:number):number|null{if(fcfN<y+1)return null;return safeCagr(fcfSorted[fcfN-1-y].freeCashFlowPerShare,fcfSorted[fcfN-1].freeCashFlowPerShare,y);}return<Card><SH title="Growth Rates" icon={<BarChart2 size={12}/>} sub={`FY ${latest.calendarYear}`}/><div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse"}}><thead><tr><th style={{...hs_,textAlign:"left"}}>Metric</th><th style={hs_}>1Y</th><th style={hs_}>3Y</th><th style={hs_}>5Y</th><th style={hs_}>10Y</th></tr></thead><tbody>{ms.map(([l,f])=><tr key={l}><td style={ls_}><span title={TOOLTIPS[l]||""} style={{cursor:TOOLTIPS[l]?"help":"default",borderBottom:TOOLTIPS[l]?`1px dotted ${T.textLight}`:"none"}}>{l}</span></td><GC v={yoy(f)}/><GC v={cagr(f,3)}/><GC v={cagr(f,5)}/><GC v={cagr(f,10)}/></tr>)}{fcfLatest&&<tr><td style={ls_}><span title={TOOLTIPS["FCF/Share"]||""} style={{cursor:"help",borderBottom:`1px dotted ${T.textLight}`}}>FCF/Share</span></td><GC v={fcfYoy()}/><GC v={fcfCagr(3)}/><GC v={fcfCagr(5)}/><GC v={fcfCagr(10)}/></tr>}</tbody></table></div></Card>;}

function ProfitPanel({ratios,loading}:{ratios:RatioYear[];loading:boolean}){if(loading||!ratios.length)return null;const c=ratios[0];const avgN=(f:keyof RatioYear,n:number)=>{const vs=ratios.slice(0,n).map(r=>r[f]as number).filter(v=>v!=null&&isFinite(v));return vs.length>=Math.min(n,2)?vs.reduce((a,b)=>a+b,0)/vs.length:null;};const ms:[string,keyof RatioYear,number?,boolean?][]=[["ROE","returnOnEquity",0.15],["ROA","returnOnAssets",0.08],["Gross Margin","grossProfitMargin",0.40],["Op Margin","operatingProfitMargin",0.15],["Net Margin","netProfitMargin",0.10],["Current Ratio","currentRatio",undefined,true],["D/E","debtToEquityRatio",undefined,true]];const fmt=(v:number|null,isR?:boolean)=>{if(v==null||!isFinite(v))return"—";return isR?v.toFixed(2):(v*100).toFixed(1)+"%";};return<Card><SH title="Profitability" sub={`FY ${c.fiscalYear}`}/><div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse"}}><thead><tr><th style={{...hs_,textAlign:"left"}}>Metric</th><th style={hs_}>Current</th><th style={hs_}>3Y</th><th style={hs_}>5Y</th><th style={hs_}>10Y</th></tr></thead><tbody>{ms.map(([l,f,th,isR])=>{const cv=c[f]as number;const cl=(v:number|null)=>v!=null&&th!=null&&v>=th?"#10b981":T.text;return<tr key={l}><td style={ls_}>{l}</td><td style={{...cs_,color:cl(cv),fontWeight:600}}>{fmt(cv,isR)}</td><td style={{...cs_,color:T.textMuted}}>{fmt(avgN(f,3),isR)}</td><td style={{...cs_,color:T.textMuted}}>{fmt(avgN(f,5),isR)}</td><td style={{...cs_,color:T.textMuted}}>{fmt(avgN(f,10),isR)}</td></tr>;})}</tbody></table></div></Card>;}

function ValPanel({ratios,loading}:{ratios:RatioYear[];loading:boolean}){if(loading||!ratios.length)return null;const yrs=[...ratios].reverse();const ttm=ratios[0];const ms:[string,keyof RatioYear,number?][]=[["P/E","priceToEarningsRatio"],["P/S","priceToSalesRatio"],["P/B","priceToBookRatio"],["P/FCF","priceToFreeCashFlowRatio"],["EV/EBITDA","evToEBITDA"],["BVPS","bookValuePerShare",2],["Div%","dividendYieldPercentage",2]];return<Card><SH title="Valuation History" sub="Annual"/><div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse"}}><thead><tr><th style={{...hs_,textAlign:"left",position:"sticky",left:0,background:T.card,zIndex:1}}>Metric</th>{yrs.map(y=><th key={y.fiscalYear} style={hs_}>{y.fiscalYear}</th>)}<th style={{...hs_,color:T.green,fontWeight:700}}>TTM</th></tr></thead><tbody>{ms.map(([l,f,d])=><tr key={l}><td style={{...ls_,position:"sticky",left:0,background:T.card,zIndex:1}}><span title={TOOLTIPS[l]||""} style={{cursor:TOOLTIPS[l]?"help":"default",borderBottom:TOOLTIPS[l]?`1px dotted ${T.textLight}`:"none"}}>{l}</span></td>{yrs.map(y=>{const v=y[f]as number;return<td key={y.fiscalYear} style={cs_}>{v!=null&&isFinite(v)&&v>0?v.toFixed(d??1):"—"}</td>;})}<td style={{...cs_,color:T.green,fontWeight:600}}>{(()=>{const v=ttm[f]as number;return v!=null&&isFinite(v)&&v>0?v.toFixed(d??1):"—";})()}</td></tr>)}</tbody></table></div></Card>;}

// ── Liquidity & Debt Profile Card ─────────────────────────────────────────────
function LiquidityProfileCard({balanceSheets, ratios, loading}: {balanceSheets: BalanceSheetRow[], ratios: RatioYear[], loading: boolean}) {
  if (loading || !balanceSheets.length) return null;
  const bsSorted = [...balanceSheets].sort((a,b)=>a.date.localeCompare(b.date));
  const latestBs = bsSorted[bsSorted.length-1];
  const ttmRatio = ratios && ratios.length > 0 ? ratios[0] : null;

  const cash = latestBs.cashAndShortTermInvestments ?? latestBs.cashAndCashEquivalents ?? 0;
  const shortDebt = latestBs.shortTermDebt ?? 0;
  const longDebt = latestBs.longTermDebt ?? 0;
  const totalDebt = latestBs.totalDebt ?? (shortDebt + longDebt);
  const netDebt = totalDebt - cash;

  const bn = (n: number) => n >= 1e9 ? `$${(n/1e9).toFixed(1)}B` : n >= 1e6 ? `$${(n/1e6).toFixed(0)}M` : `$${n}`;
  const bnNum = (n: number) => n >= 1e9 ? (n/1e9).toFixed(1) : n >= 1e6 ? (n/1e6).toFixed(0) : String(n);
  const bnSuffix = cash >= 1e9 ? "bn" : cash >= 1e6 ? "m" : "";

  const hist = bsSorted.slice(-5);
  const maxVal = Math.max(...hist.map(b => Math.max(b.totalDebt||0, b.cashAndShortTermInvestments||b.cashAndCashEquivalents||0))) || 1;
  const h = 120; 

  const stackMax = Math.max(cash, totalDebt) || 1;

  return (
    <Card>
      <SH title="Liquidity & Debt Profile" icon={<Activity size={12}/>} sub={`FY ${latestBs.calendarYear}`} />
      <div style={{display:"grid", gridTemplateColumns:"1fr 1.5fr 1fr", gap:20, marginTop:10}}>
        
        <div style={{display:"flex", gap:16, height:180, alignItems:"flex-end", paddingBottom:20}}>
          <div style={{flex:1, display:"flex", flexDirection:"column", alignItems:"center", height:"100%"}}>
            <div style={{fontSize:10, fontFamily:T.mono, color:T.textMuted, marginBottom:8}}>Cash ({bnSuffix})</div>
            <div style={{flex:1, width:40, position:"relative", display:"flex", alignItems:"flex-end"}}>
              <div style={{width:"100%", background:"#9ca3af", height:`${Math.max(5, (cash/stackMax)*100)}%`, borderRadius:"4px 4px 0 0", display:"flex", alignItems:"center", justifyContent:"center"}}>
                <span style={{fontSize:9, fontFamily:T.mono, color:"#fff", fontWeight:700, writingMode:"vertical-rl", transform:"rotate(180deg)"}}>{cash>0?bnNum(cash):""}</span>
              </div>
            </div>
            <div style={{fontSize:9, fontFamily:T.mono, color:T.text, marginTop:8, fontWeight:600}}>CASH</div>
          </div>
          <div style={{flex:1, display:"flex", flexDirection:"column", alignItems:"center", height:"100%"}}>
            <div style={{fontSize:10, fontFamily:T.mono, color:T.textMuted, marginBottom:8}}>Debt ({bnSuffix})</div>
            <div style={{flex:1, width:40, position:"relative", display:"flex", flexDirection:"column", justifyContent:"flex-end"}}>
              <div style={{width:"100%", background:"#ef4444", height:`${Math.max(2, (shortDebt/stackMax)*100)}%`, borderRadius:"4px 4px 0 0", borderBottom:"1px solid #fff", display:"flex", alignItems:"center", justifyContent:"center"}} title="Short-Term Debt">
                <span style={{fontSize:9, fontFamily:T.mono, color:"#fff", fontWeight:700}}>{shortDebt>0?bnNum(shortDebt):""}</span>
              </div>
              <div style={{width:"100%", background:"#b91c1c", height:`${Math.max(2, (longDebt/stackMax)*100)}%`, display:"flex", alignItems:"center", justifyContent:"center"}} title="Long-Term Debt">
                <span style={{fontSize:9, fontFamily:T.mono, color:"#fff", fontWeight:700, writingMode:"vertical-rl", transform:"rotate(180deg)"}}>{longDebt>0?bnNum(longDebt):""}</span>
              </div>
            </div>
            <div style={{fontSize:9, fontFamily:T.mono, color:T.text, marginTop:8, fontWeight:600}}>DEBT</div>
          </div>
        </div>

        <div style={{borderLeft:`1px solid ${T.divider}`, borderRight:`1px solid ${T.divider}`, padding:"0 16px", display:"flex", flexDirection:"column", justifyContent:"space-between"}}>
          <div>
            <div style={{fontSize:10, color:T.textMuted, fontFamily:T.mono, fontWeight:600, marginBottom:16, textAlign:"center"}}>DEBT VS CASH TREND</div>
            <div style={{display:"flex", alignItems:"flex-end", justifyContent:"space-between", height:h, padding:"0 10px"}}>
              {hist.map((b, i) => {
                const c = b.cashAndShortTermInvestments ?? b.cashAndCashEquivalents ?? 0;
                const d = b.totalDebt ?? 0;
                const cHeight = Math.max(2, (c/maxVal)*h);
                const dHeight = Math.max(2, (d/maxVal)*h);
                return (
                  <div key={i} style={{display:"flex", flexDirection:"column", alignItems:"center", gap:4}}>
                    <div style={{display:"flex", gap:4, alignItems:"flex-end", height:h}}>
                      <div style={{width:14, background:"#9ca3af", height:cHeight, borderRadius:"2px 2px 0 0"}} title={`Cash: ${bn(c)}`} />
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
              <div style={{width:8, height:8, background:"#9ca3af", borderRadius:2}} /> Cash & Equiv
            </div>
            <div style={{display:"flex", alignItems:"center", gap:4, fontSize:9, fontFamily:T.mono, color:T.textMuted}}>
              <div style={{width:8, height:8, background:"#b91c1c", borderRadius:2}} /> Total Debt
            </div>
          </div>
        </div>

        <div style={{display:"flex", flexDirection:"column", gap:12}}>
          <div style={{fontSize:10, color:T.textMuted, fontFamily:T.mono, fontWeight:600, marginBottom:4}}>POSITION INSIGHTS</div>
          
          <div style={{background:"#f8faf9", border:`1px solid ${T.divider}`, borderRadius:6, padding:"8px 10px"}}>
            <div style={{fontSize:9, fontFamily:T.mono, color:T.textMuted, marginBottom:2}}>NET DEBT / (CASH)</div>
            <div style={{fontSize:13, fontFamily:T.mono, color:netDebt > 0 ? T.red : T.green, fontWeight:700}}>
              {netDebt > 0 ? bn(netDebt) : `(${bn(Math.abs(netDebt))})`}
            </div>
          </div>
          
          <div style={{background:"#f8faf9", border:`1px solid ${T.divider}`, borderRadius:6, padding:"8px 10px"}}>
            <div style={{fontSize:9, fontFamily:T.mono, color:T.textMuted, marginBottom:2}}>D/E RATIO</div>
            <div style={{fontSize:13, fontFamily:T.mono, color:T.text, fontWeight:700}}>
              {ttmRatio?.debtToEquityRatio != null ? ttmRatio.debtToEquityRatio.toFixed(2) : "—"}
            </div>
          </div>
          
          <div style={{background:"#f8faf9", border:`1px solid ${T.divider}`, borderRadius:6, padding:"8px 10px"}}>
            <div style={{fontSize:9, fontFamily:T.mono, color:T.textMuted, marginBottom:2}}>INTEREST COVERAGE</div>
            <div style={{fontSize:13, fontFamily:T.mono, color:ttmRatio?.interestCoverageRatio && ttmRatio.interestCoverageRatio > 3 ? T.green : T.red, fontWeight:700}}>
              {ttmRatio?.interestCoverageRatio != null ? `${ttmRatio.interestCoverageRatio.toFixed(1)}x` : "—"}
            </div>
          </div>
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
    
    if (keys.length === 0) {
      return <div style={{height:220, display:"flex", alignItems:"center", justifyContent:"center", color:T.textLight, fontSize:11, fontFamily:T.mono}}>Select a metric to view</div>;
    }

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
              <div key={k} onClick={()=>toggleKey(k)} style={{display:"flex", alignItems:"center", gap:6, fontSize:10, fontFamily:T.mono, color:isActive ? T.text : T.textLight, cursor:"pointer", background:isActive ? "#fff" : "transparent", padding:"4px 8px", borderRadius:4, border:`1px solid ${isActive ? T.divider : "transparent"}`, boxShadow:isActive ? "0 1px 2px rgba(0,0,0,0.05)" : "none", transition:"all 0.2s"}}>
                <div style={{width:10, height:10, borderRadius:2, background:isActive ? allColors[i] : T.divider}} />
                {l}
              </div>
            );
          })}
        </div>

        <svg viewBox={`0 0 ${W} ${H}`} style={{width:"100%", height:"auto", display:"block", background:"#fafbfc", borderRadius:4, border:`1px solid ${T.divider}`}}>
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
                        fill={isLatest ? colors[j] === "#e5e7eb" ? T.textMuted : colors[j] : T.textLight}
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
                                stroke={colors[j] === "#e5e7eb" ? "#9ca3af" : colors[j]} 
                                strokeWidth={0.5} 
                                strokeDasharray="1,1" 
                                opacity={0.6} 
                              />
                              {/* Arrow head */}
                              <polygon 
                                points={`${bx + subBarW/2 - 2},${by - 6} ${bx + subBarW/2 + 2},${by - 6} ${bx + subBarW/2},${by - 2}`} 
                                fill={colors[j] === "#e5e7eb" ? "#9ca3af" : colors[j]} 
                                opacity={0.6} 
                              />
                              {/* Pill */}
                              <rect 
                                x={midX - pillWidth/2} 
                                y={bracketY - 5.5} 
                                width={pillWidth} 
                                height={11} 
                                rx={5.5} 
                                fill={"#fff"} 
                                stroke={colors[j] === "#e5e7eb" ? "#d1d5db" : colors[j]} 
                                strokeWidth={0.5} 
                                opacity={0.9}
                              />
                              <text 
                                x={midX} 
                                y={bracketY + 2.5} 
                                fontSize={5} 
                                fontFamily={T.mono} 
                                fontWeight={700} 
                                fill={pct > 0 ? "#10b981" : pct < 0 ? T.red : T.textMuted} 
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
      </div>
    );
  };

  return (
    <Card>
      <div style={{display:"flex", justifyContent:"space-between", alignItems:"flex-start", marginBottom:12}}>
        <SH title="Financials Overview" icon={<BarChart2 size={12}/>} sub={isQuarterly ? "Quarterly Trends" : "Annual Trends"} />
        <div style={{display:"flex", gap:12}}>
          <div style={{display:"flex", background:"#f1f5f9", padding:2, borderRadius:6}}>
            <button onClick={()=>setIsQuarterly(false)} style={{padding:"4px 10px", fontSize:10, fontFamily:T.mono, fontWeight:600, border:"none", borderRadius:4, cursor:"pointer", background:!isQuarterly?"#fff":"transparent", color:!isQuarterly?T.text:T.textMuted, boxShadow:!isQuarterly?"0 1px 3px rgba(0,0,0,0.1)":"none"}}>Annual</button>
            <button onClick={()=>setIsQuarterly(true)} style={{padding:"4px 10px", fontSize:10, fontFamily:T.mono, fontWeight:600, border:"none", borderRadius:4, cursor:"pointer", background:isQuarterly?"#fff":"transparent", color:isQuarterly?T.text:T.textMuted, boxShadow:isQuarterly?"0 1px 3px rgba(0,0,0,0.1)":"none"}}>Quarterly</button>
          </div>
          <div style={{display:"flex", background:"#f1f5f9", padding:2, borderRadius:6}}>
            <button onClick={()=>setShowGrowth(false)} style={{padding:"4px 10px", fontSize:10, fontFamily:T.mono, fontWeight:600, border:"none", borderRadius:4, cursor:"pointer", background:!showGrowth?"#fff":"transparent", color:!showGrowth?T.text:T.textMuted, boxShadow:!showGrowth?"0 1px 3px rgba(0,0,0,0.1)":"none"}}>Values</button>
            <button onClick={()=>setShowGrowth(true)} style={{padding:"4px 10px", fontSize:10, fontFamily:T.mono, fontWeight:600, border:"none", borderRadius:4, cursor:"pointer", background:showGrowth?"#fff":"transparent", color:showGrowth?T.text:T.textMuted, boxShadow:showGrowth?"0 1px 3px rgba(0,0,0,0.1)":"none"}}>Growth %</button>
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
        {activeChart === "income" && <Chart data={incs} rawData={incsRaw} allKeys={["revenue", "operatingIncome", "netIncome"]} allColors={["#e5e7eb", T.amber, T.green]} allLabels={["Rev", "OpInc", "NetInc"]} />}
        {activeChart === "balance" && <Chart data={bals} rawData={balsRaw} allKeys={["totalAssets", "totalLiabilities", "totalEquity"]} allColors={["#e5e7eb", T.red, T.green]} allLabels={["Assets", "Liabs", "Equity"]} />}
        {activeChart === "cash" && <Chart data={cfs} rawData={cfsRaw} allKeys={["operatingCashFlow", "freeCashFlow"]} allColors={["#d1d5db", T.blue]} allLabels={["OpCash", "FCF"]} />}
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
  const cellColor=(v:number|null,med:number|null)=>{if(v==null||med==null)return T.text;if(v<med*0.95)return"#10b981";if(v>med*1.05)return"#d97706";return T.text;};
  const fmtNum=(v:number|null)=>v==null?"—":v.toFixed(1);
  const targetName=target?.companyName||companyName||symbol;
  const renderRow=(row:PeerRow,opts:{isTarget?:boolean;isMedian?:boolean;isExtra?:boolean;label?:string}={})=>{
    const{isTarget,isMedian,isExtra,label}=opts;
    const bg=isTarget?T.greenLight:isMedian?"#f8faf9":isExtra?"#fffbeb":"transparent";
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
          <button onClick={()=>addExtra(input)} disabled={addLoading} style={{background:T.green,color:"#fff",border:"none",padding:"4px 10px",borderRadius:4,fontSize:10,fontFamily:T.mono,fontWeight:600,cursor:"pointer",opacity:addLoading?0.5:1}}>{addLoading?"...":"Add"}</button>
          <button onClick={()=>{setShowInput(false);setInput("");setAddError("");}} title="Cancel" style={{background:"none",border:"none",padding:0,color:T.textLight,cursor:"pointer",fontSize:14,lineHeight:1}}>✕</button>
        </div>
      }
    </div>
    {addError&&<div style={{fontSize:10,color:"#d97706",fontFamily:T.mono,marginBottom:6}}>{addError}</div>}
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
      <span style={{color:"#10b981",fontWeight:600}}>Green</span> = cheaper than peer median (&gt;5% below)
      &nbsp;·&nbsp;
      <span style={{color:"#d97706",fontWeight:600}}>Amber</span> = richer than peer median (&gt;5% above)
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
  const results=await Promise.all(regions.map(r=>
    fetch(`${GCS_SCANS}/latest_${r}.json`, { cache: 'no-store' }).then(res=>res.ok?res.json():null).catch(()=>null)
  ));
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
        <ScoreRing value={s.piotroski} label="Piotroski" max={9} color={s.piotroski>=7?"#10b981":s.piotroski>=5?T.amber:T.red}/>
        <ScoreRing value={Math.round(s.altman_z>20?20:s.altman_z)} label="Altman Z" max={20} color={s.altman_z>3?"#10b981":s.altman_z>1.8?T.amber:T.red}/>
      </div>
      <div style={{fontSize:9,color:T.textLight,fontFamily:T.mono,textAlign:"center",marginBottom:6,marginTop:-6}}>Diagnostic only — not in v8 composite</div>
      <Metric label="Net Margin" value={fmtPct(s.net_margin)} color={(s.net_margin??0)>0.20?"#10b981":(s.net_margin??0)>0.10?T.amber:T.textMuted}/>
      <Metric label="FCF Margin" value={fmtPct(s.fcf_margin)} color={(s.fcf_margin??0)>0.15?"#10b981":(s.fcf_margin??0)>0.08?T.amber:T.textMuted}/>
      <Metric label="ROE (avg)" value={fmtPct(s.roe_avg)} color={s.roe_avg>0.15?"#10b981":T.textMuted} sub={s.roe_consistent?"✓ Consistent >15%":""}/>
      <Metric label="ROIC (avg)" value={fmtPct(s.roic_avg)} color={s.roic_avg>0.12?"#10b981":T.textMuted}/>
      <Metric label="Gross Margin" value={fmtPct(s.gross_margin)} color={s.gross_margin>0.5?"#10b981":T.textMuted} sub={s.gross_margin_trend==="expanding"?"↑ Expanding":s.gross_margin_trend==="contracting"?"↓ Contracting":"→ Stable"}/>
      <Metric label="P/FCF" value={(s.p_fcf??0)>0?(s.p_fcf as number).toFixed(1)+"x":"—"} color={(s.p_fcf??0)>0&&(s.p_fcf as number)<25?"#10b981":(s.p_fcf??0)>0&&(s.p_fcf as number)<40?T.amber:T.textMuted}/>
      <Metric label="Earnings Yield" value={fmtPct(s.earnings_yield)} color={(s.earnings_yield??0)>0.05?"#10b981":(s.earnings_yield??0)>0.03?T.amber:T.textMuted}/>
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
              style={{background:T.green,color:"#fff",border:"none",padding:"6px 16px",borderRadius:5,fontSize:11,fontFamily:T.mono,fontWeight:600,cursor:loading?"wait":"pointer",opacity:loading?0.6:1}}>
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
    const compColor=s.composite>0.6?T.green:s.composite>0.4?T.text:T.red;
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
            <div style={{fontSize:24,fontWeight:700,fontFamily:T.mono,color:compColor}}>{s.composite.toFixed(2)}</div>
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

function ScoreEducationCard() {
  return (
    <Card style={{ marginBottom: 16 }}>
      <SH title="Scoring Analysis & Methodology" icon={<Activity size={12} />} />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 20, marginTop: 12 }}>
        <div>
          <h4 style={{ fontSize: 11, fontWeight: 700, color: T.text, marginBottom: 4 }}>MOMENTUM COMPOSITE</h4>
          <p style={{ fontSize: 11, color: T.textMuted, lineHeight: 1.5 }}>
            Our default engine. Balanced 5-factor model: Technical Momentum (25%), Quality (20%), Growth (20%), Value (20%), and Smart Money Flow (15%). Optimized for finding established leaders in strong uptrends.
          </p>
        </div>
        <div>
          <h4 style={{ fontSize: 11, fontWeight: 700, color: T.text, marginBottom: 4 }}>COMPOUNDER (US/GLOBAL)</h4>
          <p style={{ fontSize: 11, color: T.textMuted, lineHeight: 1.5 }}>
            A precision quality-first engine. It filters for high ROE (&gt;15%), strong pricing power (Expanding Gross Margins), and robust Balance Sheets. Rejects high-leverage and commodity businesses.
          </p>
        </div>
        <div>
          <h4 style={{ fontSize: 11, fontWeight: 700, color: T.text, marginBottom: 4 }}>FALLEN ANGEL</h4>
          <p style={{ fontSize: 11, color: T.textMuted, lineHeight: 1.5 }}>
            Contrarian Mean-Reversion engine. Identifies fundamentally strong businesses (Piotroski &gt; 6) that have suffered severe short-term price dislocation. Optimized for sharp reversals.
          </p>
        </div>
        <div>
          <h4 style={{ fontSize: 11, fontWeight: 700, color: T.text, marginBottom: 4 }}>V8 SMART MONEY</h4>
          <p style={{ fontSize: 11, color: T.textMuted, lineHeight: 1.5 }}>
            Focuses on institutional footprints. Weighs 13F accumulation velocity, congressional trading activity, and management transcript sentiment. Follows the capital, not the noise.
          </p>
        </div>
      </div>
    </Card>
  );
}

function StockStoryCard({s, incomes, ratios}:{s:StockData, incomes?:IncomeRow[], ratios?:RatioYear[]}){
  type StoryData = {
    narrative:string,
    bullBear?:string,
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
            style={{background:T.green,color:"#fff",border:"none",padding:"10px 24px",borderRadius:6,fontSize:13,fontFamily:T.mono,fontWeight:600,cursor:"pointer",boxShadow:"0 2px 4px rgba(16,185,129,0.2)"}}
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
    <div style={{display:"flex",flexDirection:"column",gap:16,maxWidth:800,margin:"0 auto"}}>
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
              <button 
                key={idx}
                onClick={() => setViewIndex(idx)}
                style={{
                  display:"flex",justifyContent:"space-between",alignItems:"center",
                  padding:"10px 14px",borderRadius:6,border:`1px solid ${viewIndex === idx ? T.greenBorder : T.cardBorder}`,
                  background:viewIndex === idx ? T.greenLight : "#fff",
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
            ))}
          </div>
        </Card>
      )}

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
          <SH title="Multi-Agent Debate" icon={<Activity size={12}/>} sub="Gemini 3.1 Pro vs. Claude Opus" />
          <div style={{fontSize:13,lineHeight:1.6,color:T.text,fontFamily:T.sans}}>
            {story.bullBear.split("Bear says:").map((part, i) => (
              <div key={i} style={{marginBottom: i === 0 ? 12 : 0, paddingBottom: i === 0 ? 12 : 0, borderBottom: i === 0 ? `1px dashed ${T.divider}` : "none"}}>
                {i === 0 ? <strong style={{color:T.green}}>Gemini (Bull): </strong> : <strong style={{color:T.red}}>Claude (Bear): </strong>}
                {part.replace("Bull says:", "").trim()}
              </div>
            ))}
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
              style={{background:T.green,color:"#fff",border:"none",padding:"6px 16px",borderRadius:6,fontSize:10,fontFamily:T.mono,fontWeight:600,cursor:"pointer",boxShadow:"0 2px 4px rgba(16,185,129,0.2)"}}
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
      "theme": "light",
      "style": "1",
      "locale": "en",
      "enable_publishing": false,
      "backgroundColor": "rgba(255, 255, 255, 1)",
      "gridColor": "rgba(240, 243, 250, 0)",
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

export default function StockDetail(){
  const params=useParams();const router=useRouter();const symbol=typeof params?.symbol==="string"?params.symbol:"";
  const[stock,setStock]=useState<StockData|null>(null);const[loading,setLoading]=useState(true);
  const[incomes,setIncomes]=useState<IncomeRow[]>([]);const[ratios,setRatios]=useState<RatioYear[]>([]);
  const[balanceSheets,setBalanceSheets]=useState<BalanceSheetRow[]>([]);const[cashFlows,setCashFlows]=useState<CashFlowRow[]>([]);
  const[incomesQ,setIncomesQ]=useState<IncomeRow[]>([]);
  const[balanceSheetsQ,setBalanceSheetsQ]=useState<BalanceSheetRow[]>([]);const[cashFlowsQ,setCashFlowsQ]=useState<CashFlowRow[]>([]);
  const[fmpLoading,setFmpLoading]=useState(true);
  const [mode,setMode]=useState<string>("momentum");
  // May 2026: stock-page tab system. "overview" = existing dashboard,
  // "track" = Buffett 10y track record table.
  const [activeTab, setActiveTab] = useState<"overview"|"story"|"transcript"|"track"|"compare"|"chart">("overview");
  const [scoreView, setScoreView] = useState<"both"|"v8"|"cmp">("both");

  useEffect(()=>{
    if(!symbol)return;
    const sym=symbol.toUpperCase();
    const regions=["sp500","europe","global"] as const;
    Promise.all(regions.map(r=>
      fetch(`${GCS_SCANS}/latest_${r}.json`, { cache: 'no-store' }).then(res=>res.ok?res.json():null).catch(()=>null)
    )).then(results=>{
      let best:StockData|null=null, bestDate="";
      results.forEach(d=>{
        if(!d?.stocks)return;
        const f=d.stocks.find((x:StockData)=>x.symbol===sym);
        if(f&&(d.scan_date||"")>bestDate){best=f; bestDate=d.scan_date||"";}
      });
      if(!best){
        fetch(`${GCS_SCANS}/latest_global.json`, { cache: 'no-store' }).then(r=>r.json()).then(d=>{
          const f=d.stocks?.find((s:StockData)=>s.symbol===sym);
          setStock(f||null); setLoading(false);
        }).catch(()=>{setStock(null); setLoading(false);});
      } else {
        setStock(best); setLoading(false);
      }
    }).catch(()=>{setStock(null); setLoading(false);});
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

  useEffect(()=>{
    if (!stock) return;
    const momOK = (stock.signal_momentum ?? "QUALIFIED") !== "DISQUALIFIED";
    const faOK  = stock.fallen_angel_flag === true;
    const cuOK  = (stock.signal_compounder_us ?? "DISQUALIFIED") === "QUALIFIED";
    const cgOK  = (stock.signal_compounder_global ?? "DISQUALIFIED") === "QUALIFIED";
    const currentOK = mode==="momentum"?momOK : mode==="fallen_angel"?faOK
                    : mode==="compounder_us"?cuOK : mode==="compounder_global"?cgOK : true;
    if (!currentOK) {
      if (momOK) setMode("momentum");
      else if (cuOK) setMode("compounder_us");
      else if (cgOK) setMode("compounder_global");
      else if (faOK) setMode("fallen_angel");
    }
  },[stock, mode]);

  if(loading)return<div style={{minHeight:"100vh",display:"flex",alignItems:"center",justifyContent:"center"}}><span style={{color:T.textMuted,fontFamily:T.mono,fontSize:12}}>Loading {symbol}...</span></div>;
  if(!stock)return<div style={{minHeight:"100vh",padding:40}}><button onClick={()=>router.push("/")} style={{background:"none",border:"none",color:T.green,cursor:"pointer",display:"flex",alignItems:"center",gap:6,fontFamily:T.mono,fontSize:12,marginBottom:24,padding:0}}><ArrowLeft size={14}/> Back</button><div style={{textAlign:"center",padding:60,color:T.textMuted,fontFamily:T.mono}}>No data for {symbol}.</div></div>;

  const s=stock,clsColor=CLS_C[s.classification]||T.textMuted;

  const haveMom = (s.signal_momentum ?? "QUALIFIED") !== "DISQUALIFIED";
  const haveFA  = s.fallen_angel_flag === true;
  const haveCmpUS = (s.signal_compounder_us ?? "DISQUALIFIED") === "QUALIFIED";
  const haveCmpGL = (s.signal_compounder_global ?? "DISQUALIFIED") === "QUALIFIED";
  const compMode = mode==="fallen_angel" ? (s.composite_fallen_angel ?? s.composite)
                 : mode==="compounder_us" ? (s.compounder_score_us ?? 0)
                 : mode==="compounder_global" ? (s.compounder_score_global ?? 0)
                 : (s.composite_momentum ?? s.composite);
  const sigMode = mode==="fallen_angel"      ? (s.fallen_angel_flag ? "QUALIFIED" : "DISQUALIFIED")
                : mode==="compounder_us"     ? (s.signal_compounder_us ?? "DISQUALIFIED")
                : mode==="compounder_global" ? (s.signal_compounder_global ?? "DISQUALIFIED")
                :                              (s.signal_momentum ?? "QUALIFIED");
  const factorsMode=readFactorsV8(s,mode);
  const sigStyle=SIG_C[sigMode]||SIG_C.HOLD;
  const evaluatedCount=Object.values(factorsMode).filter(v=>v!=null).length;

  const faAdvantage=(s.composite_fallen_angel??0)-(s.composite_momentum??0);
  const showFAHint=haveFA&&faAdvantage>=0.10&&mode==="momentum";

  const cohortBadges:[string,string,boolean][] = [
    ["MOM",      "Momentum",         haveMom],
    ["FA",       "Fallen Angel",     haveFA],
    ["CMP-US",   "Compounder US",    haveCmpUS],
    ["CMP-GL",   "Compounder Global",haveCmpGL],
  ];

  return(
    <div style={{minHeight:"100vh",padding:"16px 24px",maxWidth:1320,margin:"0 auto"}}>
      <button onClick={()=>router.push("/")} style={{background:"none",border:"none",color:T.green,cursor:"pointer",display:"flex",alignItems:"center",gap:5,fontFamily:T.mono,fontSize:11,marginBottom:16,padding:0}}><ArrowLeft size={13}/> SCREENER</button>

      <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:20,paddingBottom:16,borderBottom:`1px solid ${T.divider}`}}>
        <div>
          <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:6,flexWrap:"wrap"}}>
            <h1 style={{fontSize:26,fontWeight:700,color:T.text,fontFamily:T.mono,margin:0}}>{s.symbol}</h1>
            <span style={{fontSize:10,padding:"3px 8px",borderRadius:4,border:`1px solid ${clsColor}30`,color:clsColor,fontFamily:T.mono,fontWeight:600,background:`${clsColor}08`}}>{s.classification?.replace("_"," ")}</span>
            <div style={{display:"inline-flex",gap:4}}>
              {cohortBadges.map(([short,full,ok])=>(
                <span key={short} title={`${full}: ${ok?"qualified":"not qualified"}`}
                  style={{fontSize:9,padding:"3px 7px",borderRadius:3,fontWeight:700,
                    fontFamily:T.mono,letterSpacing:"0.06em",
                    color:ok?T.green:T.textLight,
                    background:ok?T.greenLight:"transparent",
                    border:`1px solid ${ok?T.greenBorder:T.cardBorder}`}}>
                  {ok?"✓":"·"} {short}
                </span>
              ))}
            </div>
            {s.has_catalyst&&<Zap size={14} color={T.purple} fill={T.purple}/>}
            <ModeToggle mode={mode} onChange={setMode} available={{momentum:haveMom,fallen_angel:haveFA,compounder_us:haveCmpUS,compounder_global:haveCmpGL}}/>
            {showFAHint&&<span style={{fontSize:10,padding:"3px 8px",borderRadius:4,background:T.amberLight,color:T.amber,fontFamily:T.mono,fontWeight:600,border:"1px solid #fde68a",cursor:"pointer"}} onClick={()=>setMode("fallen_angel")} title="Fallen Angel composite is materially higher — click to switch view">↻ Fallen Angel scores +{(faAdvantage*100).toFixed(0)}</span>}
          </div>
          <div style={{display:"flex",alignItems:"baseline",gap:12}}><span style={{fontSize:30,fontWeight:600,color:T.text,fontFamily:T.mono}}>{fmtPrice(s.price,s.currency)}</span><span style={{fontSize:13,color:T.textMuted,fontFamily:T.mono}}>{s.currency}</span></div>
        </div>
        <div style={{display:"flex",flexDirection:"column",alignItems:"flex-end",gap:8}}>
          <AddToPortfolioStock stock={s}/>
          <div style={{textAlign:"right"}}>
            <div style={{fontSize:11,color:T.textMuted,fontFamily:T.mono,marginBottom:4}}>Composite ({mode==="fallen_angel"?"FA":mode==="compounder_us"?"CMP-US":mode==="compounder_global"?"CMP-GL":"Mom"})</div>
            <div style={{fontSize:34,fontWeight:700,fontFamily:T.mono,color:compMode>0.6?T.green:compMode>0.4?T.text:T.red}}>{compMode.toFixed(2)}</div>
            {haveFA&&<div style={{fontSize:9,color:T.textLight,fontFamily:T.mono,marginTop:2}}>
              {mode==="momentum"?`FA: ${(s.composite_fallen_angel??0).toFixed(2)}`:`Mom: ${(s.composite_momentum??0).toFixed(2)}`}
            </div>}
          </div>
        </div>
      </div>

{/* TradingView */}
      {activeTab !== "chart" && !toTradingViewSymbol(s.symbol).startsWith("EURONEXT:") && (
        <Card style={{marginBottom:16,padding:0,overflow:"hidden"}}><div style={{height:300}}><iframe src={`https://s.tradingview.com/widgetembed/?frameElementId=tv&symbol=${encodeURIComponent(toTradingViewSymbol(s.symbol))}&interval=D&hidesidetoolbar=1&symboledit=0&saveimage=0&toolbarbg=f1f3f6&studies=MASimple%409na%40na%40na~50~0~~&studies=MASimple%409na%40na%40na~200~0~~&theme=light&style=1&timezone=exchange&withdateranges=1&width=100%25&height=100%25`} style={{width:"100%",height:"100%",border:"none"}} allowFullScreen/></div></Card>
      )}
      {activeTab !== "chart" && toTradingViewSymbol(s.symbol).startsWith("EURONEXT:") && (
         <Card style={{marginBottom:16,padding:24,textAlign:"center",color:T.textMuted,fontFamily:T.mono,fontSize:11}}>
           <Activity size={16} style={{margin:"0 auto 8px",color:T.textLight}}/>
           Euronext widget data is restricted by TradingView. Open the Chart tab for an FMP historical fallback.
         </Card>
      )}

      {/* Tab bar */}
      <div style={{display:"flex",gap:0,marginBottom:16,borderBottom:`1px solid ${T.cardBorder}`}}>
        {(["overview","story","transcript","track","compare","chart"] as const).map(tab=>(
          <button key={tab} onClick={()=>setActiveTab(tab)}
            style={{
              padding:"10px 20px",border:"none",cursor:"pointer",background:"transparent",
              fontFamily:T.mono,fontSize:11,fontWeight:600,letterSpacing:"0.05em",textTransform:"uppercase",
              color:activeTab===tab?T.green:T.textMuted,
              borderBottom:activeTab===tab?`2px solid ${T.green}`:"2px solid transparent",
              marginBottom:-1,
            }}>
            {tab==="overview"?"Overview":tab==="story"?"Stock Story":tab==="transcript"?"Transcript":tab==="track"?"Track Record":tab==="compare"?"Compare":"Chart"}
          </button>
        ))}
      </div>

      {activeTab==="track" ? (
        <TrackRecordTable s={s}/>
      ) : activeTab==="compare" ? (
        <ComparisonTab stockA={s} fmpA={{incomes,ratios,balanceSheets,cashFlows,incomesQ,balanceSheetsQ,cashFlowsQ}}/>
      ) : activeTab==="story" ? (
        <div style={{display:"flex",flexDirection:"column",gap:16}}>
          <ScoreEducationCard />
          <StockStoryCard s={s} incomes={incomes} ratios={ratios} />
        </div>
      ) : activeTab==="transcript" ? (
        <TranscriptInsights symbol={s.symbol} />
      ) : activeTab==="chart" ? (
        toTradingViewSymbol(s.symbol).startsWith("EURONEXT:") 
          ? <FmpBasicChartTab s={s}/> 
          : <AdvancedChartTab s={s}/>
      ) : (
        <>
          
      {/* ═══ SCORING — side-by-side cards for every mode ═══ */}
      {/* v1.2 (May 2026): the v8 5-Factor card always renders (it's the
          general factor view used by Momentum and Fallen Angel). The
          Compounder breakdown sits beside it, defaulting to the cohort
          that matches the active mode. For Mom/FA, the Compounder card
          shows US first, falling back to Global. The card matching the
          active mode gets a highlight border.                            */}
      {(()=>{
        const modeLabel =
          mode==="fallen_angel"     ? "Fallen Angel"
          : mode==="compounder_us"  ? "Compounder US"
          : mode==="compounder_global" ? "Compounder Global"
          : "Momentum";
        // Which Compounder cohort to display alongside (US preferred when
        // the active mode isn't Compounder-specific; for CMP modes, show
        // the matching cohort).
        const cmpCohort: "us"|"global" =
          mode==="compounder_global" ? "global"
          : mode==="compounder_us"   ? "us"
          : (haveCmpUS ? "us" : "global");
        const v8Active = mode==="momentum" || mode==="fallen_angel";
        const cmpActive = mode==="compounder_us" || mode==="compounder_global";
        const v8Style: React.CSSProperties = v8Active
          ? {marginBottom:0, boxShadow:`0 0 0 2px ${T.green}`, borderColor:T.green}
          : {marginBottom:0};
        return (
          <div style={{marginBottom:16}}>
            <div style={{display:"flex",justifyContent:"flex-end",marginBottom:6}}>
              <div style={{display:"flex", background:T.card, border:`1px solid ${T.cardBorder}`, padding:2, borderRadius:6}}>
                <button onClick={()=>setScoreView("v8")} style={{padding:"3px 8px", fontSize:9, fontFamily:T.mono, fontWeight:600, border:"none", borderRadius:4, cursor:"pointer", background:scoreView==="v8"?T.greenLight:"transparent", color:scoreView==="v8"?T.green:T.textMuted}}>5-Factor</button>
                <button onClick={()=>setScoreView("both")} style={{padding:"3px 8px", fontSize:9, fontFamily:T.mono, fontWeight:600, border:"none", borderRadius:4, cursor:"pointer", background:scoreView==="both"?T.greenLight:"transparent", color:scoreView==="both"?T.green:T.textMuted}}>Both</button>
                <button onClick={()=>setScoreView("cmp")} style={{padding:"3px 8px", fontSize:9, fontFamily:T.mono, fontWeight:600, border:"none", borderRadius:4, cursor:"pointer", background:scoreView==="cmp"?T.greenLight:"transparent", color:scoreView==="cmp"?T.green:T.textMuted}}>Compounder</button>
              </div>
            </div>
            <div style={{display:"grid",gridTemplateColumns:scoreView==="both"?"1fr 1fr":"1fr",gap:14}}>
              {scoreView!=="cmp" && (
                <Card style={v8Style}>
                  <SH title="5-Factor Analysis" icon={<BarChart2 size={12}/>}
                    sub={`${modeLabel} mode · Composite ${compMode.toFixed(2)} · ${evaluatedCount}/5 factors`}/>
                  <div style={{display:"flex",flexDirection:"column",alignItems:"center",marginBottom:8}}>
                    <FactorRadar scores={factorsMode} size={220}/>
                  </div>
                  <div style={{display:"grid",gridTemplateColumns:"1fr",gap:0}}>
                    {FACTOR_ORDER.map(k=>(
                      <FactorBar key={k} name={FL[k]} weight={FW[k]}
                        score={(factorsMode as any)[k]} detail={factorDetail(k,s,mode)}/>
                    ))}
                  </div>
                </Card>
              )}
              {scoreView!=="v8" && (
                <CompounderBreakdownCard s={s} cohort={cmpCohort} active={cmpActive}/>
              )}
            </div>
          </div>
        );
      })()}

      {/* Company profile */}
      <div style={{marginBottom:16}}>
        <CompanyProfileCard symbol={s.symbol}/>
      </div>

      {/* Catalyst + Sentiment */}
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14,marginBottom:16}}>
        <CatalystTimeline s={s}/>
        <SentimentCard s={s}/>
      </div>

      {/* P20 Move Probability Card — full width, shows probability ladder + spread edge */}
      {(s.hit_prob??0)>0&&<div style={{marginBottom:16}}><P20Card s={s}/></div>}

      {/* Tradier options card — spread suggestion + IV data */}
      {((s.hit_prob??0)>0||s.tradier_iv_current!=null||s.tradier_iv_rank!=null||s.tradier_spread||s.tradier_pc_ratio!=null||s.tradier_term_structure||s.tradier_implied_earnings_move)&&<div style={{marginBottom:16}}><TradierOptionsCard s={s}/></div>}

      {/* Price + Composite chart */}
      <div style={{marginBottom:16}}>
        <PriceCompositeChart symbol={s.symbol} mode={s.mode}/>
      </div>

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
        <LiquidityProfileCard balanceSheets={balanceSheets} ratios={ratios} loading={fmpLoading} />
      </div>

      {/* FMP Panels — multi-year tables (separate from v8 scoring; pure historical context) */}
      <GrowthPanel incomes={incomes} loading={fmpLoading} ratios={ratios}/>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14,margin:"16px 0"}}><ProfitPanel ratios={ratios} loading={fmpLoading}/><ValPanel ratios={ratios} loading={fmpLoading}/></div>
      <div style={{display:"grid",gridTemplateColumns:"2fr 1fr",gap:14,margin:"16px 0"}}>
        <PeersPanel symbol={s.symbol} companyName={s.symbol}/>
        <NewsFeed symbol={s.symbol}/>
      </div>

{/* Active signals */}
      {s.reasons?.length>0&&<Card style={{marginBottom:16}}><SH title="Active Signals"/><div style={{display:"flex",flexWrap:"wrap",gap:6,marginTop:4}}>{s.reasons.map((r,i)=><span key={i} style={{fontSize:10,padding:"4px 10px",borderRadius:4,fontFamily:T.mono,background:r.includes("⚠")?T.redLight:T.greenLight,border:`1px solid ${r.includes("⚠")?"#fecaca":T.greenBorder}`,color:r.includes("⚠")?T.red:T.textMuted}}>{r}</span>)}</div></Card>}
        </>
      )}
    </div>
  );
}
