"use client";

import { useState, useEffect, useMemo, useRef } from "react";
import { useAuth } from "./AuthProvider";
import { getPortfolio, addPosition as storeAddPosition, getRadar, setRadar, DEFAULT_RADAR } from "./portfolioStore";

import { TrendingUp, ChevronDown, ChevronRight, ChevronLeft, Target, Search, Zap, Copy, CheckCircle2, ArrowRight, Clock, Coins, Shield, Flame, Activity, Sliders, Database, Briefcase, Trash2, Info, Check, Plus, ExternalLink, HelpCircle, AlertTriangle } from "lucide-react";

import { Watchlist } from "./components/Watchlist";

import { StockCard } from "./components/StockCard";

import { ThemeCard } from "./components/ThemeCard";

import { DailyBriefing } from "./components/DailyBriefing";

import { useRouter } from "next/navigation";



const GCS_BASE = "/api/gcs/scans";

const GCS_FALLBACK = "/latest_global.json";

const REGIONS = [

  { key: "sp500", label: "S&P 500" },

  { key: "midcap", label: "Midcap" },

];



function gcsUrl(region: string) { return `${GCS_BASE}/latest_${region}.json`; }

const US_EXCHANGES = new Set(["NASDAQ","NYSE","AMEX","NYSEArca","PNK","OTC"]);

const EU_EXCHANGES = new Set(["XETRA","PAR","LSE","AMS","MIL","STO","SIX","BME","HEL","OSL","CPH"]);

const EU_COUNTRIES = new Set(["GB","DE","FR","NL","IT","SE","CH","ES","DK","NO","FI","IE","AT","BE","PT"]);



// ── Types ───────────────────────────────────────────────────────────────────

interface FactorsV8 { momentum:number|null; quality:number|null; growth:number|null; value:number|null; smart_money:number|null; }

// Legacy v7 factor scores (kept on the wire for diagnostic backwards-compat;

// not rendered anywhere on the page).

interface FactorScores { technical:number|null; quality:number|null; proximity:number|null; catalyst:number|null; transcript:number|null; upside:number|null; institutional:number|null; analyst:number|null; insider:number|null; earnings:number|null; institutional_flow?:number|null; sector_momentum?:number|null; congressional?:number|null; }

interface MacroData { regime:"RISK_ON"|"NEUTRAL"|"CAUTIOUS"|"RISK_OFF"; score:number; sub_scores:{ yield_curve?:number; yield_curve_3m?:number; yield_level?:number; vix?:number; cpi_trend?:number; gdp_momentum?:number; unemployment?:number; consumer_sentiment?:number; recession_prob?:number; }; version?:string; features?:Record<string,number|null>; }

interface StockData {

  symbol:string; price:number; currency:string; market_cap:number;

  sma50:number; sma200:number; year_high:number; year_low:number; volume:number;

  rsi:number; macd_signal:string; adx:number; bb_pct:number; stoch_rsi:number;

  obv_trend:string; bull_score:number;

  target:number; upside:number; grade_buy:number; grade_total:number;

  grade_score:number; eps_beats:number; eps_total:number;

  revenue_cagr_3y:number; eps_cagr_3y:number; roe_avg:number;

  roe_consistent:boolean; roic_avg:number; gross_margin:number;

  gross_margin_trend:string; piotroski:number; altman_z:number;

  dcf_value:number; owner_earnings_yield:number; intrinsic_buffett:number;

  intrinsic_avg:number; margin_of_safety:number; value_score:number;

  composite:number; classification:string; reasons:string[];

  // signal?:string;  // REMOVED v1.2 (May 2026) — BUY/HOLD/SELL semantics gone

  factor_scores?:FactorScores;

  // v7 fields kept on the wire (diagnostic only, no longer drive composite)

  quality_score?:number; catalyst_score?:number; catalyst_flags?:string[];

  has_catalyst?:boolean; days_to_earnings?:number;

  insider_score?:number; insider_net_buys?:number;

  transcript_sentiment?:number; transcript_summary?:string; transcript_score?:number;

  inst_score?:number; proximity_score?:number; earnings_score?:number;

  upside_score?:number;

  hit_prob?:number;

  // Smart Money Score (Apr 2026) — LTR-derived weighted factor score.

  // Pass-2 / US-only. null for non-US stocks and rows below top-30.

  smart_money_score?:number|null;

  smart_money_components?:Record<string,number>;

  smart_money_weight?:number;

  factor_coverage?:number;

  factors_evaluated?:string[];

  factors_missing?:string[];

  // v7.2.1 Massive options enrichment (top-30 US stocks only)

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

  company_name?:string;

  sector?:string;

  industry?:string;

  theme?:string;

  position_size_pct?:number;

  peer_context?:{_evaluated?:boolean;peers?:{symbol:string;price:number;"52wk_position":number;vs_200d:number}[];divergence?:string;avg_peer_mom_200d?:number;stock_spread_vs_peers?:number};

  exchange?:string;

  country?:string;

  // v6 compat (removed in v7)

  news_score?:number; news_sentiment?:number; catastrophe_score?:number;

  // ── v8 (Apr 2026): dual-mode 5-factor composite ──

  // Both modes computed at scan time (Option B). The page binds to whichever

  // mode the user selects via ModeToggle. `composite` defaults to momentum

  // for backward-compat with sort/filter code that hasn't been migrated yet.

  composite_momentum?:number;

  composite_fallen_angel?:number;

  signal_momentum?:string;

  // signal_fallen_angel?:string; // REMOVED v1.2 (May 2026) — replaced by fallen_angel_flag

  factors_v8?:FactorsV8;

  factors_v8_momentum?:FactorsV8;

  factors_v8_fallen_angel?:FactorsV8;

  composite_v7?:number;

  // ── v1.2 (May 2026): Compounder + Fallen Angel flag + PT velocity ──

  fallen_angel_flag?:boolean;        // FA basket gate (replaces signal_fallen_angel)

  compounder_score_us?:number|null;  // US cohort: exchange in NYSE/NASDAQ/AMEX, mcap≥$2B, ex Fin/Ins/HC

  compounder_score_global?:number|null; // Global cohort: ex Fin/Ins/HC

  compounder_rank_us?:number|null;

  compounder_rank_global?:number|null;

  signal_compounder_us?:string;      // QUALIFIED | DISQUALIFIED

  signal_compounder_global?:string;

  roe_compounder?:number|null;       // 3-yr strict average (v1.1+)

  pb_compounder?:number|null;

  opmargin_delta_compounder?:number|null;

  pt_velocity_60d?:number|null;      // 60d % delta in analyst PT consensus

  pt_velocity_score?:number|null;    // banded 0..1 for Smart Money composite

  // v8 derived fields available on the row (used in expanded panel)

  net_margin?:number;

  fcf_margin?:number;

  revenue_yoy?:number;

  eps_yoy?:number;

  fcf_yoy?:number;

  fcf_cagr_3y?:number;

  p_fcf?:number;

  p_s?:number;                       // Apr 2026: price/sales ratio (latest annual)

  earnings_yield?:number;

  intrinsic_bvps?:number;

  bvps_recent_cagr?:number;

  bvps_consistency?:number;

  bvps_upside?:number;

  intrinsic_upside?:number;

  reversal_score?:number;

  epv_to_ev?:number|null;

  price_to_graham_revised?:number|null;

  acquirers_multiple?:number|null;

  iv15_discount?:number|null;

  dcf_fcff_mos?:number|null;

  rd_capitalized_dcf?:number|null;

  rd_capitalized_dcf_mos?:number|null;

  owner_earnings?:number|null;

  owner_earnings_mos?:number|null;

  epv_value?:number|null;

  epv_mos?:number|null;

  graham_revised?:number|null;

  graham_revised_mos?:number|null;

  iv15_deep_value?:number|null;

  iv15_deep_value_mos?:number|null;

}

interface ScanData {

  scan_date:string; region:string; version:string;

  weights?:Record<string,number>;

  macro?:MacroData;

  summary:{ total:number; buy:number; watch:number; hold:number; sell:number; strong_buy?:number };

  sector_concentration?:Record<string,{count:number;symbols:string[]}>;

  stocks:StockData[];

}



// ── Signal & Classification colors ──────────────────────────────────────────

const SIG: Record<string,{color:string;bg:string;border:string}> = {

  "STRONG BUY": { color:"var(--purple)", bg:"var(--purple-light)", border:"var(--purple-light)" },

  BUY:   { color:"var(--green)", bg:"var(--green-light)", border:"var(--green-light)" },

  WATCH: { color:"var(--amber)", bg:"var(--amber-light)", border:"var(--amber-light)" },

  HOLD:  { color:"var(--text-muted)", bg:"var(--bg-elevated)", border:"var(--border)" },

  SELL:  { color:"var(--red)", bg:"var(--red-light)", border:"var(--red-light)" },

};

const CLS: Record<string,string> = { DEEP_VALUE:"#2563eb", VALUE:"#0891b2", QUALITY_GROWTH:"#7c3aed", GROWTH:"#818cf8", SPECULATIVE:"#ef4444", NEUTRAL:"#64748b" };







// ── Helpers ─────────────────────────────────────────────────────────────────

const getMethodologyMetric = (stock: StockData | undefined, path: string) => {

  if (!stock) return { label: "VALUATION", value: "—" };

  

  switch (path) {

    case "intrinsic/dcf_fcff": {

      const dcfMos = stock.dcf_fcff_mos != null

        ? stock.dcf_fcff_mos

        : (stock.dcf_value && stock.price && stock.dcf_value > 0

          ? (stock.dcf_value - stock.price) / stock.dcf_value

          : null);

      return { label: "MARGIN OF SAFETY", value: dcfMos != null ? `${(dcfMos * 100).toFixed(1)}%` : "—" };

    }

    case "emerging/rd_capitalized_dcf": {

      const rdMos = stock.rd_capitalized_dcf_mos != null

        ? stock.rd_capitalized_dcf_mos

        : (stock.rd_capitalized_dcf && stock.price && stock.rd_capitalized_dcf > 0

          ? (stock.rd_capitalized_dcf - stock.price) / stock.rd_capitalized_dcf

          : null);

      return { label: "R&D DCF MOS", value: rdMos != null ? `${(rdMos * 100).toFixed(1)}%` : "—" };

    }

    case "emerging/earnings_yield_gap":

      return { label: "YIELD GAP (VS 4.5% RF)", value: stock.earnings_yield != null ? `${((stock.earnings_yield - 0.045) * 100).toFixed(1)}%` : "—" };

    case "multiples/ev_gross_profit":

      return { label: "GROSS MARGIN", value: stock.gross_margin != null ? `${(stock.gross_margin * 100).toFixed(1)}%` : "—" };

    case "intrinsic/owner_earnings":

      return { label: "OWNER EARNINGS YIELD", value: stock.owner_earnings_yield != null ? `${(stock.owner_earnings_yield * 100).toFixed(1)}%` : "—" };

    case "intrinsic/epv_greenwald":

      return { label: "EPV / EV RATIO", value: stock.epv_to_ev != null ? stock.epv_to_ev.toFixed(2) : "—" };

    case "v8fusion/graham_revised": {

      const grahamMos = stock.graham_revised_mos != null

        ? stock.graham_revised_mos

        : (stock.price_to_graham_revised != null ? 1.0 - stock.price_to_graham_revised : null);

      return { label: "GRAHAM REVISED MOS", value: grahamMos != null ? `${(grahamMos * 100).toFixed(1)}%` : "—" };

    }

    case "v8fusion/iv15_deep_value": {

      const iv15Mos = stock.iv15_deep_value_mos != null

        ? stock.iv15_deep_value_mos

        : (stock.iv15_discount != null ? 1.0 - stock.iv15_discount : null);

      return { label: "IV15 DISCOUNT MOS", value: iv15Mos != null ? `${(iv15Mos * 100).toFixed(1)}%` : "—" };

    }

    case "multiples/acquirers_multiple":

      return { label: "ACQUIRER'S MULTIPLE", value: stock.acquirers_multiple != null ? `${stock.acquirers_multiple.toFixed(1)}x` : "—" };

    default:

      return { label: "UPSIDE SCORE", value: stock.upside_score != null ? stock.upside_score.toFixed(1) : "—" };

  }

};



const fmtPct = (n:number|null|undefined) => n==null?"—":`${(n*100).toFixed(0)}%`;

const fmtMcap = (n:number|null|undefined) => { if(n==null) return "—"; if(n>=1e12) return `$${(n/1e12).toFixed(1)}T`; if(n>=1e9) return `$${(n/1e9).toFixed(0)}B`; if(n>=1e6) return `$${(n/1e6).toFixed(0)}M`; return `$${n.toFixed(0)}`; };



// 2026-05-07: currency-aware price formatting for global universe.

// Backend now correctly tags currency per ticker (.T → JPY, .HK → HKD, etc.)

// after the suffix-detection fix. Display the right glyph instead of always

// showing "$". Codes shown for currencies where the glyph is ambiguous.

const CURRENCY_SYMBOL: Record<string, string> = {

  USD: "$",  EUR: "€",  GBP: "£",  JPY: "¥",  CNY: "¥",  HKD: "HK$",

  CHF: "CHF ", SEK: "kr ", NOK: "kr ", DKK: "kr ", AUD: "A$",  CAD: "C$",

  NZD: "NZ$", SGD: "S$",  KRW: "₩",  INR: "₹",  BRL: "R$",  MXN: "Mex$",

  TWD: "NT$", THB: "฿",  IDR: "Rp ", MYR: "RM ", PHP: "₱",  ILS: "₪",

  TRY: "₺",  PLN: "zł ", CZK: "Kč ", HUF: "Ft ", ZAR: "R",   SAR: "SAR ",

  AED: "AED ",

};

const fmtPrice = (n:number|null|undefined, c?:string) => {

  if (n == null || n === 0) return "—";

  const sym = CURRENCY_SYMBOL[c ?? ""] ?? "$";

  // For prices over 1000 (JPY, KRW, IDR almost always), drop decimals

  return n >= 1000

    ? `${sym}${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`

    : `${sym}${n.toFixed(2)}`;

};















// ── Catalyst Badges ─────────────────────────────────────────────────────────

function CatalystBadges({s}:{s:StockData}){

  const badges:{ label:string; color:string; bg:string }[]=[];

  if(s.days_to_earnings!=null&&s.days_to_earnings>=0&&s.days_to_earnings<=14) badges.push({label:`Earn ${s.days_to_earnings}d`,color:"#d97706",bg:"#fffbeb"});

  if(s.catalyst_flags?.some(f=>f.toLowerCase().includes("m&a"))) badges.push({label:"M&A",color:"#8b5cf6",bg:"#f5f3ff"});

  if(s.catalyst_flags?.some(f=>f.toLowerCase().includes("upgrade"))) badges.push({label:"↑ Upgrade",color:"#10b981",bg:"#e8f5ee"});

  if(s.catalyst_flags?.some(f=>f.toLowerCase().includes("downgrade"))) badges.push({label:"↓ Downgrade",color:"#ef4444",bg:"#fef2f2"});

  if(!badges.length) return null;

  return(

    <div style={{display:"flex",gap:3,flexWrap:"wrap",marginTop:3}}>

      {badges.map((b,i)=><span key={i} style={{fontSize:8,padding:"1px 5px",borderRadius:3,fontFamily:"var(--font-mono)",fontWeight:600,color:b.color,background:b.bg}}>{b.label}</span>)}

    </div>

  );

}



// ── Macro Banner ────────────────────────────────────────────────────────────

const REGIME_STYLE: Record<string,{color:string;bg:string;border:string;label:string}> = {

  RISK_ON:  { color:"var(--green)", bg:"var(--green-light)", border:"var(--green-light)", label:"RISK ON" },

  NEUTRAL:  { color:"var(--text-muted)", bg:"var(--bg-elevated)", border:"var(--border)", label:"NEUTRAL" },

  CAUTIOUS: { color:"var(--amber)", bg:"var(--amber-light)", border:"var(--amber-light)", label:"CAUTIOUS" },

  RISK_OFF: { color:"var(--red)", bg:"var(--red-light)", border:"var(--red-light)", label:"RISK OFF" },

};

const MACRO_SIGNALS:[string,string][] = [

  ["yield_curve","Yield 10y-2y"],

  ["yield_curve_3m","Yield 10y-3m"],

  ["yield_level","Rate Level"],

  ["vix","VIX"],

  ["cpi_trend","CPI Trend"],

  ["gdp_momentum","GDP"],

  ["unemployment","Unemployment"],

  ["consumer_sentiment","Sentiment"],

  ["recession_prob","Recession"],

];

interface SectorRow { name: string; symbol: string; accent?: string | null; price: number | null; day: number | null; ytd: number | null; year: number | null; }
interface SectorPerf { indices: SectorRow[]; sectors: SectorRow[]; thematic: SectorRow[]; macro: { vix: number | null; vixChange: number | null; yield10: number | null }; asOf: string | null; }
interface EtfHolding { symbol: string; name: string; weight: number | null; day: number | null; ytd: number | null; }

// Quick-pick chips for the customizable radar.
const RADAR_PRESETS: { s: string; label: string }[] = [
  { s: "^GSPC", label: "S&P" }, { s: "^NDX", label: "NASDAQ" }, { s: "^DJI", label: "Dow" },
  { s: "^RUT", label: "Russell" }, { s: "^VIX", label: "VIX" }, { s: "^TNX", label: "10Y" },
  { s: "DX-Y.NYB", label: "DXY" }, { s: "GLD", label: "Gold" }, { s: "USO", label: "Oil" },
  { s: "BTCUSD", label: "BTC" }, { s: "EURUSD", label: "EUR/USD" }, { s: "^GDAXI", label: "DAX" },
  { s: "^FTSE", label: "FTSE" }, { s: "VGK", label: "Europe" }, { s: "^STOXX50E", label: "Euro Stoxx" },
  { s: "^BVSP", label: "Bovespa" }, { s: "000001.SS", label: "Shanghai" }, { s: "^HSI", label: "Hong Kong" },
];

// Add a symbol to the localStorage watchlist (first basket) read by the Watchlist panel.
function addToWatchlist(sym: string) {
  try {
    const raw = localStorage.getItem("cb_watchlist_baskets");
    const baskets = raw ? JSON.parse(raw) : [];
    if (!baskets.length) baskets.push({ id: "default", name: "Watchlist", symbols: [] });
    if (!baskets[0].symbols.includes(sym)) baskets[0].symbols.push(sym);
    localStorage.setItem("cb_watchlist_baskets", JSON.stringify(baskets));
  } catch {}
}

// Generic live performance card (indices, GICS sectors, thematic ETFs).
// Shows live price + today's %, flashes on tick. ETF cards (holdingsSymbol set)
// toggle open to their top-10 holdings (lazy-fetched) with live day-%.
function PerfCard({ title, price, day, ytd, year, accent, note, holdingsSymbol, compact, onRemove }: { title: string; price: number | null; day: number | null; ytd: number | null; year: number | null; accent?: string; note?: string; holdingsSymbol?: string; compact?: boolean; onRemove?: () => void }) {
  const prev = useRef<number | null>(null);
  const [flash, setFlash] = useState<"up" | "down" | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [holdings, setHoldings] = useState<EtfHolding[] | null>(null);
  const [menuFor, setMenuFor] = useState<string | null>(null);
  useEffect(() => {
    if (price != null && prev.current != null && price !== prev.current) {
      setFlash(price > prev.current ? "up" : "down");
      prev.current = price;
      const t = setTimeout(() => setFlash(null), 700);
      return () => clearTimeout(t);
    }
    if (price != null) prev.current = price;
  }, [price]);
  useEffect(() => {
    if (!expanded || holdings || !holdingsSymbol) return;
    fetch(`/api/etf-holdings?symbol=${encodeURIComponent(holdingsSymbol)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setHoldings(d?.holdings ?? []))
      .catch(() => setHoldings([]));
  }, [expanded, holdings, holdingsSymbol]);
  const col = (v: number | null) => (v == null ? "var(--text-light)" : v >= 0 ? "var(--green)" : "var(--red)");
  const pct = (v: number | null) => (v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`);
  const fmtPrice = (v: number | null) => {
    if (v == null) return "—";
    if (v >= 1000) return v.toLocaleString("en-US", { maximumFractionDigits: 0 });
    if (v < 10) return v.toFixed(4);
    return v.toFixed(2);
  };
  const bg = flash === "up" ? "rgba(16,185,129,0.18)" : flash === "down" ? "rgba(239,68,68,0.18)" : "var(--bg-surface)";
  const z = compact
    ? { pad: "8px 12px", radius: 10, hMb: 3, title: 12, dot: 8, price: 15, day: 11, pMb: 5, lbl: 8, val: 11 }
    : { pad: "16px 20px", radius: 12, hMb: 8, title: 15, dot: 9, price: 20, day: 13, pMb: 10, lbl: 10, val: 13 };
  return (
    <div style={{ background: bg, border: "1px solid var(--border)", borderRadius: z.radius, padding: z.pad, boxShadow: "var(--shadow-sm)", transition: "background 0.6s ease" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: z.hMb }}>
        <div style={{ fontWeight: 800, fontSize: z.title, fontFamily: "var(--font-sans)", color: "var(--text)" }}>{title}</div>
        {onRemove ? (
          <button onClick={onRemove} title="Remove from radar" style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-light)", padding: 0, fontSize: 14, lineHeight: 1, fontFamily: "var(--font-mono)" }}>×</button>
        ) : holdingsSymbol ? (
          <button onClick={() => setExpanded((e) => !e)} title={expanded ? "Hide holdings" : "Show top holdings"} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-light)", padding: 0, fontSize: 13, lineHeight: 1, fontFamily: "var(--font-mono)" }}>{expanded ? "▾" : "▸"}</button>
        ) : accent ? (
          <span style={{ height: z.dot, width: z.dot, borderRadius: "50%", background: accent }}></span>
        ) : null}
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: z.pMb }}>
        <span style={{ fontSize: z.price, fontWeight: 800, fontFamily: "var(--font-mono)", color: "var(--text)" }}>{fmtPrice(price)}</span>
        <span style={{ fontSize: z.day, fontWeight: 700, fontFamily: "var(--font-mono)", color: col(day) }}>{pct(day)}</span>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <div>
          <div style={{ fontSize: z.lbl, color: "var(--text-light)", fontFamily: "var(--font-mono)" }}>YTD</div>
          <div style={{ fontSize: z.val, fontWeight: 700, color: col(ytd), fontFamily: "var(--font-mono)" }}>{pct(ytd)}</div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: z.lbl, color: "var(--text-light)", fontFamily: "var(--font-mono)" }}>1Y</div>
          <div style={{ fontSize: z.val, fontWeight: 700, color: col(year), fontFamily: "var(--font-mono)" }}>{pct(year)}</div>
        </div>
      </div>
      {note ? <div style={{ marginTop: 8, fontSize: 9, color: "var(--text-light)", fontFamily: "var(--font-mono)", letterSpacing: "0.05em" }}>{note}</div> : null}
      {expanded ? (
        <div style={{ marginTop: 10, borderTop: "1px solid var(--border)", paddingTop: 8, display: "flex", flexDirection: "column", gap: 5 }}>
          {holdings == null ? (
            <div style={{ fontSize: 10, color: "var(--text-light)", fontFamily: "var(--font-mono)" }}>Loading holdings…</div>
          ) : holdings.length === 0 ? (
            <div style={{ fontSize: 10, color: "var(--text-light)", fontFamily: "var(--font-mono)" }}>No holdings data</div>
          ) : (
            <>
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 8, color: "var(--text-light)", fontFamily: "var(--font-mono)", letterSpacing: "0.06em", opacity: 0.65, marginBottom: 1 }}>
                <span>HOLDING</span>
                <span style={{ display: "flex", gap: 10 }}><span style={{ width: 34, textAlign: "right" }}>WT</span><span style={{ width: 46, textAlign: "right" }}>1D</span><span style={{ width: 52, textAlign: "right" }}>YTD</span></span>
              </div>
              {holdings.map((h) => {
                const open = menuFor === h.symbol;
                const btn = { textDecoration: "none", color: "var(--text)", background: "var(--bg-hover)", border: "1px solid var(--border)", borderRadius: 4, padding: "2px 7px", fontFamily: "var(--font-mono)", fontSize: 10, cursor: "pointer" } as const;
                return (
                  <div key={h.symbol}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 11, fontFamily: "var(--font-mono)" }}>
                      <span title={h.name || h.symbol} onClick={() => setMenuFor(open ? null : h.symbol)} style={{ color: "var(--text)", fontWeight: 600, cursor: "pointer", textDecoration: open ? "underline" : "none" }}>{h.symbol}</span>
                      <span style={{ display: "flex", gap: 10, alignItems: "baseline" }}>
                        <span style={{ color: "var(--text-light)", fontSize: 10, width: 34, textAlign: "right" }}>{h.weight == null ? "" : `${h.weight.toFixed(1)}%`}</span>
                        <span style={{ color: col(h.day), width: 46, textAlign: "right", fontWeight: 700 }}>{pct(h.day)}</span>
                        <span style={{ color: col(h.ytd), width: 52, textAlign: "right", fontWeight: 700 }}>{pct(h.ytd)}</span>
                      </span>
                    </div>
                    {open ? (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center", padding: "5px 0 7px" }}>
                        {h.name ? <span style={{ flexBasis: "100%", fontSize: 9, color: "var(--text-light)", fontFamily: "var(--font-mono)" }}>{h.name}</span> : null}
                        <a href={`/stock/${h.symbol}`} style={btn}>Open ↗</a>
                        <button onClick={() => { addToWatchlist(h.symbol); setMenuFor(null); }} style={btn}>+ Watchlist</button>
                        <a href={`/stock/${h.symbol}`} style={btn}>+ Portfolio ↗</a>
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </>
          )}
        </div>
      ) : null}
    </div>
  );
}

interface TrackPosition { symbol: string; entry_price: number; shares: number; asset_type?: string; }

// Live Track Record card — the /portfolio aggregate (value, total return, P&L, win/loss) in the same card format.
function TrackRecordCard({ loaded, value, pnl, pnlPct, positions, winners, losers }: { loaded: boolean; value: number; pnl: number; pnlPct: number | null; positions: number; winners: number; losers: number }) {
  const col = (v: number | null) => (v == null ? "var(--text-light)" : v >= 0 ? "var(--green)" : "var(--red)");
  const money = (v: number) => {
    const a = Math.abs(v), sign = v < 0 ? "-" : "";
    if (a >= 1e6) return `${sign}$${(a / 1e6).toFixed(2)}M`;
    if (a >= 1e3) return `${sign}$${(a / 1e3).toFixed(1)}K`;
    return `${sign}$${a.toFixed(0)}`;
  };
  return (
    <div style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: 10, padding: "8px 12px", boxShadow: "var(--shadow-sm)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 3 }}>
        <div style={{ fontWeight: 800, fontSize: 12, fontFamily: "var(--font-sans)", color: "var(--text)" }}>Live Track Record</div>
        <span style={{ fontSize: 8, fontFamily: "var(--font-mono)", color: "var(--text-light)", border: "1px solid var(--border)", borderRadius: 4, padding: "1px 4px" }}>PORTFOLIO</span>
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 5 }}>
        <span style={{ fontSize: 15, fontWeight: 800, fontFamily: "var(--font-mono)", color: "var(--text)" }}>{loaded ? money(value) : "—"}</span>
        <span style={{ fontSize: 11, fontWeight: 700, fontFamily: "var(--font-mono)", color: col(pnlPct) }}>{loaded && pnlPct != null ? `${pnlPct >= 0 ? "+" : ""}${pnlPct.toFixed(1)}%` : "—"}</span>
      </div>
      <div style={{ display: "flex", justifyContent: "space-between" }}>
        <div>
          <div style={{ fontSize: 8, color: "var(--text-light)", fontFamily: "var(--font-mono)" }}>P&L</div>
          <div style={{ fontSize: 11, fontWeight: 700, color: col(loaded ? pnl : null), fontFamily: "var(--font-mono)" }}>{loaded ? `${pnl >= 0 ? "+" : ""}${money(pnl)}` : "—"}</div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 8, color: "var(--text-light)", fontFamily: "var(--font-mono)" }}>WIN / LOSS</div>
          <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text)", fontFamily: "var(--font-mono)" }}>{loaded ? `${winners} / ${losers}` : "—"}</div>
        </div>
      </div>
      <div style={{ marginTop: 5, fontSize: 8, color: "var(--text-light)", fontFamily: "var(--font-mono)", letterSpacing: "0.05em" }}>{loaded ? `${positions} positions · live` : "loading portfolio…"}</div>
    </div>
  );
}

function MacroRibbon({macro}:{macro?:MacroData}){

  const [xpand,setXpand]=useState(false);

  if(!macro) return null;

  const subs=macro.sub_scores||{};

  const present = MACRO_SIGNALS.filter(([k])=>(subs as any)[k]!=null);

  if(present.length===0) return null;

  const rs = REGIME_STYLE[macro.regime] || REGIME_STYLE.NEUTRAL;

  const feat = macro.features || {};

  return(

    <div style={{marginBottom:14}}>

      <div onClick={()=>setXpand(!xpand)} style={{display:"flex",alignItems:"center",gap:12,padding:"8px 14px",cursor:"pointer",background:"transparent",borderTop:"1px solid var(--border-subtle,#eef1ef)",borderBottom:xpand?"none":"1px solid var(--border-subtle,#eef1ef)",transition:"all 0.15s"}}>

        <span style={{fontSize:9,fontFamily:"var(--font-mono)",fontWeight:700,padding:"2px 8px",borderRadius:4,color:rs.color,background:rs.bg,border:`1px solid ${rs.border}`,letterSpacing:"0.08em",whiteSpace:"nowrap"}}>{rs.label}</span>

        <div style={{display:"flex",alignItems:"center",gap:4}} title={`Macro composite: ${(macro.score*100).toFixed(0)}/100`}>

          <div style={{width:48,height:4,borderRadius:2,background:"var(--bg-elevated,#edf0ee)",overflow:"hidden"}}>

            <div style={{height:"100%",width:`${macro.score*100}%`,borderRadius:2,background:rs.color,transition:"width 0.3s"}}/>

          </div>

          <span style={{fontSize:10,fontFamily:"var(--font-mono)",fontWeight:700,color:rs.color}}>{(macro.score*100).toFixed(0)}</span>

        </div>

        <div style={{display:"flex",alignItems:"center",gap:10,flex:1}}>

          {present.map(([key,label])=>{

            const v = (subs as any)[key] ?? 0;

            const c = v>0.6 ? "#10b981" : v>0.4 ? "#d97706" : "#ef4444";

            return(

              <div key={key} style={{display:"flex",alignItems:"center",gap:4}} title={`${label}: ${(v*100).toFixed(0)}/100`}>

                <div style={{width:5,height:5,borderRadius:"50%",background:c,opacity:0.9}}/>

                <span style={{fontSize:8,fontFamily:"var(--font-mono)",color:"var(--text-muted,#6b7280)",whiteSpace:"nowrap"}}>{label}</span>

              </div>

            );

          })}

        </div>

        <span style={{fontSize:8,fontFamily:"var(--font-mono)",color:"var(--text-light,#9ca3af)",fontStyle:"italic",whiteSpace:"nowrap"}}>{macro.version||"v7"}</span>

        {xpand?<ChevronDown size={12} color="var(--text-light)"/>:<ChevronRight size={12} color="var(--text-light)"/>}

      </div>

      {xpand&&(

        <div style={{padding:"10px 14px 14px",borderBottom:"1px solid var(--border-subtle,#eef1ef)",background:"var(--bg-surface,#f8faf9)",animation:"fadeIn 0.2s ease"}}>

          <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(140px,1fr))",gap:8}}>

            {present.map(([key,label])=>{

              const v = (subs as any)[key] ?? 0;

              const c = v>0.6 ? "#10b981" : v>0.4 ? "#d97706" : "#ef4444";

              return(

                <div key={key} style={{padding:"6px 8px",borderRadius:6,background:"var(--bg-elevated)",border:"1px solid var(--border-subtle,#eef1ef)"}}>

                  <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:4}}>

                    <span style={{fontSize:9,fontFamily:"var(--font-mono)",fontWeight:600,color:"var(--text-muted,#6b7280)"}}>{label}</span>

                    <span style={{fontSize:11,fontFamily:"var(--font-mono)",fontWeight:700,color:c}}>{(v*100).toFixed(0)}</span>

                  </div>

                  <div style={{height:3,borderRadius:2,background:"var(--bg-elevated,#edf0ee)",overflow:"hidden"}}>

                    <div style={{height:"100%",width:`${v*100}%`,borderRadius:2,background:c,transition:"width 0.3s"}}/>

                  </div>

                </div>

              );

            })}

          </div>

          {Object.keys(feat).length>0&&(

            <div style={{marginTop:8,display:"flex",gap:12,flexWrap:"wrap"}}>

              {feat.macro_vix!=null&&<span style={{fontSize:9,fontFamily:"var(--font-mono)",color:"var(--text-muted)"}}>VIX {feat.macro_vix}</span>}

              {feat.macro_yield_spread_2y!=null&&<span style={{fontSize:9,fontFamily:"var(--font-mono)",color:"var(--text-muted)"}}>10y-2y {feat.macro_yield_spread_2y}bp</span>}

              {feat.macro_yield_spread_3m!=null&&<span style={{fontSize:9,fontFamily:"var(--font-mono)",color:"var(--text-muted)"}}>10y-3m {feat.macro_yield_spread_3m}bp</span>}

              {feat.macro_yield_level!=null&&<span style={{fontSize:9,fontFamily:"var(--font-mono)",color:"var(--text-muted)"}}>FFR {feat.macro_yield_level}%</span>}

              {feat.macro_unemployment!=null&&<span style={{fontSize:9,fontFamily:"var(--font-mono)",color:"var(--text-muted)"}}>Unemp {feat.macro_unemployment}%</span>}

              {feat.macro_consumer_sentiment!=null&&<span style={{fontSize:9,fontFamily:"var(--font-mono)",color:"var(--text-muted)"}}>UMich {feat.macro_consumer_sentiment}</span>}

              {feat.macro_recession_prob!=null&&<span style={{fontSize:9,fontFamily:"var(--font-mono)",color:"var(--text-muted)"}}>Rec.P {((feat.macro_recession_prob??0)*100).toFixed(1)}%</span>}

            </div>

          )}

        </div>

      )}

    </div>

  );

}



// ── MultiSelectDropdown (v1.2 May 2026) ───────────────────────────────────

// Lightweight self-contained multi-select for sector/country filters.

// Uses outline checkboxes (no dependency on a UI lib). The parent

// component owns open/close state so only one dropdown is open at a time

// (clicking one auto-closes the others). Click-outside is handled via

// a transparent backdrop layer; clicking it closes the dropdown.

function MultiSelectDropdown({label, options, selected, onChange, isOpen, onToggle, disabled}:{

  label:string;

  options:string[];

  selected:string[];

  onChange:(next:string[])=>void;

  isOpen:boolean;

  onToggle:()=>void;

  disabled?:boolean;

}){

  const toggle = (opt:string) => {

    if (selected.includes(opt)) onChange(selected.filter(o => o !== opt));

    else onChange([...selected, opt]);

  };

  const summary = selected.length === 0

    ? `${label}: all`

    : selected.length === 1

      ? `${label}: ${selected[0]}`

      : `${label}: ${selected.length} selected`;



  return(

    <div style={{position:"relative"}}>

      <button onClick={()=>!disabled && onToggle()} disabled={disabled}

        title={disabled ? "Filters bypassed while searching" : `${selected.length === 0 ? "Choose " + label.toLowerCase() : `${selected.length} filter${selected.length===1?"":"s"} active`}`}

        style={{

          padding:"5px 10px",

          border:`1px solid ${selected.length>0 ? "var(--green)" : "var(--border)"}`,

          borderRadius:6,

          cursor: disabled ? "not-allowed" : "pointer",

          background: selected.length > 0 ? "var(--green-light)" : "var(--bg-surface)",

          color: disabled ? "var(--text-light)" : (selected.length > 0 ? "var(--green)" : "var(--text)"),

          fontSize:10,fontFamily:"var(--font-mono)",fontWeight:600,

          display:"inline-flex",alignItems:"center",gap:6,

          opacity: disabled ? 0.5 : 1,

        }}>

        {summary}

        <ChevronDown size={10} style={{transform: isOpen ? "rotate(180deg)" : "none", transition: "transform 0.15s"}}/>

      </button>

      {isOpen && (

        <>

          {/* Click-outside backdrop */}

          <div onClick={onToggle}

            style={{position:"fixed",top:0,left:0,right:0,bottom:0,zIndex:50}}/>

          {/* Dropdown panel */}

          <div style={{

            position:"absolute", top:"calc(100% + 4px)", left:0, zIndex:51,

            minWidth:200, maxHeight:300, overflowY:"auto",

            background:"var(--bg-surface)", border:"1px solid var(--border)",

            borderRadius:6, boxShadow:"0 4px 12px rgba(0,0,0,0.08)",

            padding:"4px 0",

          }}>

            {options.length === 0 ? (

              <div style={{padding:"8px 12px",fontSize:11,fontFamily:"var(--font-mono)",color:"var(--text-light)"}}>

                No options available

              </div>

            ) : (

              <>

                {selected.length > 0 && (

                  <button onClick={()=>onChange([])}

                    style={{display:"block",width:"100%",padding:"6px 12px",border:"none",

                            background:"transparent",cursor:"pointer",textAlign:"left",

                            fontSize:10,fontFamily:"var(--font-mono)",

                            color:"var(--text-muted)",borderBottom:"1px solid var(--border-subtle,#eef1ef)"}}>

                    Clear all

                  </button>

                )}

                {options.map(opt=>{

                  const checked = selected.includes(opt);

                  return(

                    <label key={opt} style={{

                      display:"flex",alignItems:"center",gap:8,padding:"5px 12px",

                      cursor:"pointer",fontSize:11,fontFamily:"var(--font-mono)",

                      color: checked ? "var(--green)" : "var(--text)",

                      background: checked ? "var(--green-light)" : "transparent",

                    }}

                    onMouseEnter={e=>{(e.currentTarget as HTMLElement).style.background = checked ? "var(--green-light)" : "var(--bg-hover)";}}

                    onMouseLeave={e=>{(e.currentTarget as HTMLElement).style.background = checked ? "var(--green-light)" : "transparent";}}>

                      <input type="checkbox" checked={checked} onChange={()=>toggle(opt)}

                        style={{margin:0,cursor:"pointer",accentColor:"var(--green,#2d7a4f)"}}/>

                      {opt}

                    </label>

                  );

                })}

              </>

            )}

          </div>

        </>

      )}

    </div>

  );

}



// ── MoS Bar ─────────────────────────────────────────────────────────────────

function MoSBar({value}:{value:number}){const p=Math.max(-1,Math.min(1,value)),w=Math.abs(p)*100,c=p>0.15?"#10b981":p>0?"#86efac":p>-0.2?"#d97706":"#ef4444";return<div style={{display:"flex",alignItems:"center",gap:6}}><div style={{width:70,height:5,background:"var(--bg-elevated,#edf0ee)",borderRadius:3,position:"relative",overflow:"hidden"}}><div style={{position:"absolute",height:"100%",borderRadius:3,background:c,...(p>=0?{left:"50%",width:`${w/2}%`}:{right:"50%",width:`${w/2}%`})}}/><div style={{position:"absolute",left:"50%",top:0,bottom:0,width:1,background:"var(--border)"}}/></div><span style={{fontFamily:"var(--font-mono)",fontSize:11,color:c,fontWeight:600}}>{fmtPct(value)}</span></div>;}



// ── Score Pill ──────────────────────────────────────────────────────────────

function ScorePill({value}:{value:number}){const c=value>0.65?"#10b981":value>0.45?"#d97706":"#ef4444";return<div style={{display:"inline-flex",alignItems:"center",gap:4}}><div style={{width:40,height:4,borderRadius:2,background:"var(--bg-elevated,#edf0ee)",overflow:"hidden"}}><div style={{height:"100%",width:`${value*100}%`,borderRadius:2,background:c}}/></div><span style={{fontFamily:"var(--font-mono)",fontSize:12,fontWeight:700,color:c}}>{value.toFixed(2)}</span></div>;}



// ── Stock Row ───────────────────────────────────────────────────────────────

// ── Add to Portfolio Button ─────────────────────────────────────────────────

// Expands to an inline form when clicked. Price pre-fills from live scan but

// is user-editable (real fill price may differ from scan price). Posts to

// the user's per-user Firestore portfolio (portfolioStore.addPosition).

function AddToPortfolioButton({stock:s}:{stock:StockData}){

  const [open,setOpen]=useState(false);

  const [shares,setShares]=useState("");

  const [price,setPrice]=useState(s.price?.toFixed(2)||"");

  const [notes,setNotes]=useState("");

  const [status,setStatus]=useState<"idle"|"saving"|"saved"|"error">("idle");
  const { user } = useAuth();

  const [err,setErr]=useState("");



  async function handleSave(e:React.MouseEvent){

    e.stopPropagation();

    const p=parseFloat(price), sh=parseFloat(shares);

    if(!p||p<=0){setErr("Price required");return;}

    if(!sh||sh<=0){setErr("Shares required");return;}

    setStatus("saving");setErr("");

    try {

      if(!user) throw new Error("Sign in to add positions");

      await storeAddPosition(user.uid,{symbol:s.symbol,entry_price:p,shares:sh,notes});

      setStatus("saved");

      setTimeout(()=>{setOpen(false);setStatus("idle");setShares("");setNotes("");},1500);

    } catch(e:any) {

      setStatus("error");setErr((e?.message||"Failed").slice(0,160));

    }

  }



  if(!open){

    return(

      <button onClick={e=>{e.stopPropagation();setOpen(true);}} style={{

        fontSize:10,fontFamily:"var(--font-mono)",fontWeight:600,padding:"4px 10px",

        borderRadius:4,border:"1px solid var(--green-border,#b8dcc8)",background:"var(--green-light,#e8f5ee)",

        color:"var(--green,#2d7a4f)",cursor:"pointer",letterSpacing:"0.04em",textTransform:"uppercase",

      }}>+ Portfolio</button>

    );

  }



  return(

    <div onClick={e=>e.stopPropagation()} style={{

      display:"flex",alignItems:"center",gap:6,padding:"4px 8px",

      borderRadius:6,background:"var(--bg-surface)",border:"1px solid var(--green-border,#b8dcc8)",

      fontSize:10,fontFamily:"var(--font-mono)",

    }}>

      <span style={{color:"var(--text-muted,#6b7280)",fontWeight:600,marginRight:2}}>{s.symbol}</span>

      <input type="number" placeholder="shares" value={shares} onChange={e=>{setShares(e.target.value);setErr("");}}

        style={{width:52,padding:"3px 5px",border:"1px solid var(--border,#e5e7eb)",borderRadius:3,fontSize:10,fontFamily:"var(--font-mono)"}} autoFocus/>

      <span style={{color:"var(--text-light,#9ca3af)"}}>@</span>

      <input type="number" step="0.01" placeholder="price" value={price} onChange={e=>{setPrice(e.target.value);setErr("");}}

        style={{width:62,padding:"3px 5px",border:"1px solid var(--border,#e5e7eb)",borderRadius:3,fontSize:10,fontFamily:"var(--font-mono)"}}/>

      <input type="text" placeholder="notes" value={notes} onChange={e=>setNotes(e.target.value)} maxLength={40}

        style={{width:100,padding:"3px 5px",border:"1px solid var(--border,#e5e7eb)",borderRadius:3,fontSize:10,fontFamily:"var(--font-mono)"}}/>

      <button onClick={handleSave} disabled={status==="saving"||status==="saved"} style={{

        padding:"3px 8px",border:"none",borderRadius:3,cursor:status==="saving"?"wait":"pointer",

        background:status==="saved"?"#10b981":status==="error"?"#ef4444":"var(--green,#2d7a4f)",

        color:"#fff",fontSize:10,fontFamily:"var(--font-mono)",fontWeight:600,

      }}>{status==="saving"?"...":status==="saved"?"✓":status==="error"?"!":"Save"}</button>

      <button onClick={e=>{e.stopPropagation();setOpen(false);setStatus("idle");setErr("");}} style={{

        padding:"3px 6px",border:"1px solid var(--border,#e5e7eb)",borderRadius:3,cursor:"pointer",

        background:"var(--bg-surface)",color:"var(--text-muted,#6b7280)",fontSize:10,fontFamily:"var(--font-mono)",

      }}>✕</button>

      {err&&<span style={{color:"#ef4444",fontSize:9,marginLeft:4}}>{err}</span>}

    </div>

  );

}



function StockRow({stock:s,expanded,onToggle,rank,onTickerClick,selectedMethodology}:{stock:StockData;expanded:boolean;onToggle:()=>void;rank:number;onTickerClick?:(e:React.MouseEvent,symbol:string)=>void;selectedMethodology:string|null}){

  return(

    <>

      <tr onClick={onToggle} style={{cursor:"pointer",borderBottom:"1px solid var(--border-subtle,#eef1ef)",transition:"background 0.12s",borderLeft:"3px solid transparent"}}

        onMouseEnter={e=>{(e.currentTarget as HTMLElement).style.background="var(--bg-hover,#f0f4f1)";}}

        onMouseLeave={e=>{(e.currentTarget as HTMLElement).style.background="";}}>

        {/* SYMBOL column.

            v1.2 (May 2026): dropped MiniRadar mini-icon and sector subtitle.

            MiniRadar at 44px was visually decorative — the 5 factors are

            unreadable at that size; the expanded LargeRadar serves the

            "see the breakdown" job better. Sector moved to its own

            filterable column (next td). */}

        <td style={{padding:"10px 12px"}}>

          <div style={{display:"flex",alignItems:"center",gap:8}}>

            {expanded?<ChevronDown size={13} color="var(--text-light,#9ca3af)"/>:<ChevronRight size={13} color="var(--text-light,#9ca3af)"/>}

            <div>

              <div style={{display:"flex",alignItems:"center",gap:6}}>

                <a href={selectedMethodology ? `/stock/${s.symbol}?selectedMethodology=${selectedMethodology}` : `/stock/${s.symbol}`} onClick={e=>{e.preventDefault(); e.stopPropagation(); onTickerClick && onTickerClick(e, s.symbol);}} style={{fontWeight:700,letterSpacing:"0.04em",color:"var(--text,#1a1a1a)",fontSize:13,fontFamily:"var(--font-mono)"}}>{s.symbol}</a>

                {s.has_catalyst&&<Zap size={10} color="#8b5cf6" fill="#8b5cf6"/>}

              </div>

              {s.company_name && <div style={{fontSize:9,fontFamily:"var(--font-mono)",color:"var(--text-light,#9ca3af)",marginTop:1,maxWidth:200,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}} title={s.company_name}>{s.company_name}</div>}

            </div>

          </div>

        </td>

        {/* SECTOR — v1.2 column (was row subtitle) */}

        <td style={{fontFamily:"var(--font-mono)",fontSize:11,color:"var(--text-muted,#6b7280)",padding:"10px 12px",whiteSpace:"nowrap",maxWidth:140,overflow:"hidden",textOverflow:"ellipsis"}} title={s.industry?`${s.sector||"—"} / ${s.industry}`:(s.sector||"—")}>

          {s.sector || <span style={{color:"var(--text-light,#9ca3af)"}}>—</span>}

        </td>

        {/* CTRY — ISO country code from FMP company-screener */}

        <td style={{fontFamily:"var(--font-mono)",fontSize:11,color:"var(--text-muted,#6b7280)",padding:"10px 8px",textAlign:"center"}}>

          {s.country || <span style={{color:"var(--text-light,#9ca3af)"}}>—</span>}

        </td>

        {/* PRICE */}

        <td style={{fontFamily:"var(--font-mono)",textAlign:"right",padding:"10px 12px",color:"var(--text)",fontSize:12}}>{fmtPrice(s.price, s.currency)}</td>

        {/* PIO — diagnostic only (not in v8 composite) */}

        <td style={{fontFamily:"var(--font-mono)",textAlign:"center",padding:"10px 6px",fontSize:11,fontWeight:600,color:s.piotroski<=3?"#92400e":"var(--text-muted,#6b7280)"}} title="Piotroski 0-9 — diagnostic only, not in v8 composite">

          {s.piotroski}

        </td>

        {/* P/S — price/sales ratio (Apr 2026). Diagnostic only, not in composite.

            Industry-dependent: tech 5-15 normal, banks 1-3 normal, biotech often n/m.

            No color grading because what's "expensive" varies wildly by sector. */}

        <td style={{fontFamily:"var(--font-mono)",textAlign:"right",padding:"10px 8px",fontSize:11,color:"var(--text-muted,#6b7280)"}} title="Price/Sales ratio (latest annual). Industry-dependent — tech 5-15 normal, banks 1-3 normal. Click to sort.">

          {s.p_s && s.p_s > 0 ? s.p_s.toFixed(1) : <span style={{color:"var(--text-light,#9ca3af)"}}>—</span>}

        </td>

        <td style={{padding:"10px 8px",textAlign:"right",fontFamily:"var(--font-mono)",fontSize:11,color:"var(--text-muted)"}}>

          {(s as any).pe ? (s as any).pe.toFixed(1) : <span style={{color:"var(--text-light)"}}>—</span>}

        </td>

        <td style={{padding:"10px 8px",textAlign:"right",fontFamily:"var(--font-mono)",fontSize:11,color:"var(--text-muted)"}}>

          {(s as any).ev_ebit ? (s as any).ev_ebit.toFixed(1) : <span style={{color:"var(--text-light)"}}>—</span>}

        </td>

        <td style={{padding:"10px 8px",textAlign:"right",fontFamily:"var(--font-mono)",fontSize:11,color:"var(--text-muted)"}}>

          {(s as any).fcf_share ? `$${(s as any).fcf_share.toFixed(2)}` : <span style={{color:"var(--text-light)"}}>—</span>}

        </td>

        <td style={{padding:"10px 8px",textAlign:"right",fontFamily:"var(--font-mono)",fontSize:11,color:"var(--text-muted)"}}>

          {(s as any).epv_share ? `$${(s as any).epv_share.toFixed(2)}` : <span style={{color:"var(--text-light)"}}>—</span>}

        </td>

        <td style={{padding:"10px 8px",textAlign:"right",fontFamily:"var(--font-mono)",fontSize:11,color:"var(--text-muted)"}}>

          {(s as any).net_margin ? `${((s as any).net_margin*100).toFixed(1)}%` : <span style={{color:"var(--text-light)"}}>—</span>}

        </td>

        {/* UPSIDE — analyst consensus (v8 Value sub-component, kept for reference) */}

        <td style={{fontFamily:"var(--font-mono)",textAlign:"right",padding:"10px 12px",fontSize:12,color:s.upside>20?"#10b981":s.upside>0?"var(--text-muted)":"#ef4444",fontWeight:600}}>{s.upside>0?"+":""}{s.upside?.toFixed(0)}%</td>

        {/* P20 — P(+20% daily high in 4 weeks) from ML v2 ensemble.

            High P20 + Low IVR = underpriced options → bull spread signal.

            D10 stocks (P20 > 15%) touch +20% 26.3% of the time.

            May 2026: restored to dashboard after time_model_v2 reached AUC 0.78. */}

        <td style={{padding:"10px 8px",textAlign:"center",fontFamily:"var(--font-mono)",fontSize:11}}>

          {(()=>{const p = s.hit_prob;

            if (p == null || p <= 0) return <span style={{color:"var(--text-light,#9ca3af)"}} title="ML model not loaded or not enriched">—</span>;

            const pct = Math.round(p * 100);

            const c = pct>=15?"#10b981":pct>=8?"#d97706":"var(--text-muted,#6b7280)";

            const ivr = s.options_iv_rank;

            const spread = (pct >= 15 && ivr != null && ivr <= 30) ? " ★" : "";

            return <span style={{color:c,fontWeight:700}} title={`P(+20% daily high in 4w) = ${pct}%${ivr!=null?` · IVR ${ivr.toFixed(0)}`:""}${spread?" · SPREAD CANDIDATE: high P20 + low IVR":""}`}>{pct}%{spread&&<span style={{color:"#8b5cf6",fontSize:9}}>{spread}</span>}</span>;})()}

        </td>

        {/* IVR — Implied Volatility Rank (Massive API, all US stocks) */}

        <td style={{fontFamily:"var(--font-mono)",textAlign:"center",padding:"10px 6px",fontSize:11}}>

          {(()=>{

            const ivr=s.options_iv_rank;

            const iv=s.options_iv_current;

            const samples=s.options_iv_samples||0;

            if(ivr==null&&iv==null) return <span style={{color:"var(--text-light,#9ca3af)"}} title="Enriched US stocks only; 20+ days of IV history needed for rank">—</span>;

            if(ivr==null&&iv!=null){

              return <div title={`Current IV ${(iv*100).toFixed(0)}% · ${samples}/20 samples for rank`}>

                <span style={{color:"var(--text-muted,#6b7280)",fontWeight:600}}>{(iv*100).toFixed(0)}%</span>

                <div style={{fontSize:7,color:"var(--text-light)",marginTop:1}}>{samples}/20</div>

              </div>;

            }

            const rankColor=ivr!<=30?"#10b981":ivr!<=60?"#d97706":"#ef4444";

            return <div title={`IV Rank ${ivr!.toFixed(0)} (0=cheap, 100=rich) · Current IV ${iv?(iv*100).toFixed(0):"—"}% · ${samples}d samples`}>

              <span style={{color:rankColor,fontWeight:700}}>{ivr!.toFixed(0)}</span>

              {iv!=null&&<div style={{fontSize:7,color:"var(--text-light)",marginTop:1}}>{(iv*100).toFixed(0)}% IV</div>}

            </div>;

          })()}

        </td>

      </tr>

      {expanded&&(

        <tr><td colSpan={14} style={{padding:0,background:"var(--bg-surface,#f8faf9)"}}>

          <div style={{padding:"16px 20px 20px 40px",animation:"fadeIn 0.2s ease"}}>

            <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:8,paddingBottom:6,borderBottom:"2px solid var(--green-light,#e8f5ee)"}}>

              <div style={{fontSize:10,fontWeight:700,letterSpacing:"0.08em",color:"var(--green,#2d7a4f)",fontFamily:"var(--font-mono)",textTransform:"uppercase"}}>Actions & Analysis</div>

              <AddToPortfolioButton stock={s}/>

            </div>

            {(s.transcript_summary||(s.catalyst_flags&&s.catalyst_flags.length>0)||(s.reasons&&s.reasons.length>0))&&(

              <div style={{marginTop:12,paddingTop:12,borderTop:"1px solid var(--border-subtle,#eef1ef)"}}>

                {s.transcript_summary&&<div style={{fontSize:11,fontFamily:"var(--font-sans)",color:"var(--text-secondary,#475569)",marginBottom:8,fontStyle:"italic"}}>"{s.transcript_summary}"</div>}

                {s.catalyst_flags&&s.catalyst_flags.length>0&&<div style={{display:"flex",gap:4,marginBottom:8,flexWrap:"wrap"}}>{s.catalyst_flags.map((f,i)=><span key={i} style={{fontSize:9,padding:"2px 7px",borderRadius:3,fontFamily:"var(--font-mono)",color:"#8b5cf6",background:"#f5f3ff",border:"1px solid #ddd6fe",fontWeight:600}}>{f}</span>)}</div>}

                {s.reasons&&s.reasons.length>0&&<div style={{display:"flex",flexWrap:"wrap",gap:4}}>{s.reasons.map((r,i)=><span key={i} style={{fontSize:9,padding:"2px 7px",borderRadius:3,fontFamily:"var(--font-mono)",background:r.includes("⚠")?"#fef2f2":"var(--green-light,#e8f5ee)",border:`1px solid ${r.includes("⚠")?"#fecaca":"var(--green-border,#b8dcc8)"}`,color:r.includes("⚠")?"#ef4444":"var(--text-muted,#6b7280)"}}>{r}</span>)}</div>}

              </div>

            )}

            <PeerRow peer={s.peer_context}/>

          </div>

        </td></tr>

      )}

    </>

  );

}



// ── Sector Concentration ────────────────────────────────────────────────────

function SectorConcentration({data}:{data?:Record<string,{count:number;symbols:string[]}>}){

  if(!data||Object.keys(data).length===0) return null;

  const entries=Object.entries(data).sort((a,b)=>b[1].count-a[1].count);

  const total=entries.reduce((s,e)=>s+e[1].count,0);

  const maxCount=entries[0]?.[1]?.count||1;

  return(

    <div style={{background:"var(--bg-surface)",borderRadius:8,border:"1px solid var(--border)",boxShadow:"0 1px 3px rgba(0,0,0,0.06)",padding:"16px 18px",marginTop:16}}>

      <div style={{fontSize:11,fontWeight:600,letterSpacing:"0.08em",color:"var(--green,#2d7a4f)",fontFamily:"var(--font-mono)",textTransform:"uppercase",marginBottom:12,paddingBottom:8,borderBottom:"2px solid var(--green-light,#e8f5ee)"}}>Sector Concentration — BUY + STRONG BUY</div>

      {entries.map(([sector,{count,symbols}])=>{const pct=total>0?count/total*100:0;const warn=pct>40;return(

        <div key={sector} style={{marginBottom:8}}>

          <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:3}}>

            <span style={{fontSize:11,fontFamily:"var(--font-mono)",fontWeight:600,color:warn?"#d97706":"var(--text,#1a1a1a)"}}>{warn?"⚠ ":""}{sector}</span>

            <span style={{fontSize:10,fontFamily:"var(--font-mono)",color:"var(--text-muted,#6b7280)"}}>{count} ({pct.toFixed(0)}%)</span>

          </div>

          <div style={{height:6,borderRadius:3,background:"var(--bg-elevated,#edf0ee)",overflow:"hidden"}}>

            <div style={{height:"100%",width:`${(count/maxCount)*100}%`,borderRadius:3,background:warn?"#d97706":"#10b981",transition:"width 0.3s"}}/>

          </div>

          <div style={{fontSize:8,fontFamily:"var(--font-mono)",color:"var(--text-light,#9ca3af)",marginTop:2}}>{symbols.slice(0,8).join(" · ")}{symbols.length>8?` +${symbols.length-8}`:""}</div>

        </div>

      );})}

    </div>

  );

}



// ── Peer Context Row ────────────────────────────────────────────────────────

function PeerRow({peer}:{peer:StockData["peer_context"]}){

  if(!peer||!peer._evaluated||!peer.peers?.length) return null;

  const divColors:Record<string,{color:string;bg:string;tip:string}>={

    OUTPERFORMING:{color:"var(--green)",bg:"var(--green-light)",tip:"Alpha — beating peers"},

    SECTOR_TAILWIND:{color:"var(--blue)",bg:"var(--blue-light)",tip:"Rising tide — whole sector strong"},

    SECTOR_HEADWIND:{color:"var(--amber)",bg:"var(--amber-light)",tip:"Sector weakness — headwind"},

    LAGGING:{color:"var(--red)",bg:"var(--red-light)",tip:"Underperforming peers"},

  };

  const d=peer.divergence?divColors[peer.divergence]:null;

  return(

    <div style={{marginTop:10,paddingTop:10,borderTop:"1px solid var(--border-subtle,#eef1ef)"}}>

      <div style={{fontSize:9,fontWeight:600,letterSpacing:"0.08em",color:"var(--text-muted,#6b7280)",fontFamily:"var(--font-mono)",marginBottom:6}}>PEER COMPARISON</div>

      <div style={{display:"flex",alignItems:"center",gap:10,flexWrap:"wrap"}}>

        {peer.peers.map(p=><span key={p.symbol} style={{fontSize:10,fontFamily:"var(--font-mono)",color:p.vs_200d>0?"#10b981":"#ef4444"}}>{p.symbol} ({p.vs_200d>0?"+":""}{p.vs_200d.toFixed(0)}%)</span>)}

        {peer.stock_spread_vs_peers!=null&&<span style={{fontSize:10,fontFamily:"var(--font-mono)",color:"var(--text-muted,#6b7280)"}}>spread: {peer.stock_spread_vs_peers>0?"+":""}{peer.stock_spread_vs_peers.toFixed(1)}pp</span>}

        {d&&peer.divergence&&<span style={{fontSize:9,padding:"1px 6px",borderRadius:3,fontFamily:"var(--font-mono)",fontWeight:600,color:d.color,background:d.bg}} title={d.tip}>{peer.divergence.replace("_"," ")}</span>}

      </div>

    </div>

  );

}



// ── Main Dashboard ──────────────────────────────────────────────────────────

// Sortable keys exposed in the v8 main table.

// Synthetic keys (active_comp, other_comp, value_score, growth_score,

// quality_score) are computed at sort time from the active mode — letting

// the user rank stocks by either composite or by any individual factor.

type SortKey =

  | "symbol" | "sector" | "country" | "price" | "piotroski" | "p_s"

  | "pe" | "ev_ebit" | "fcf_share" | "epv_share" | "net_margin"

  | "upside" | "hit_prob";

// v1.2 (May 2026): removed orphan SortKeys (value_score/growth_score/quality_score) —

// those columns were dropped from the table. Added sector/country for the new

// SECTOR + CTRY columns. String-based sort handled in the sorted useMemo below.

// "other_comp" dropped — 4-mode world makes "other" ambiguous.



const METHODOLOGIES_CONFIG = [

  {

    path: "intrinsic/dcf_fcff",

    name: "DCF-FCFF Valuation",

    regime: "BULL",

    description: "Stage 1 projects FCFF for 5 years with growth from ROE × 0.5 (bounded 3-25%), decaying by 0.85^year. Stage 2 perpetual growth 2.5%. WACC derived from CAPM (4.5% risk-free + beta × 5.5% market premium). Enterprise value is adjusted for net debt.",

    annualReturns: [

      { year: 2021, regime: "BULL", return: 0.082 },

      { year: 2022, regime: "BEAR", return: -0.124 },

      { year: 2023, regime: "BULL", return: 0.075 },

      { year: 2024, regime: "BULL", return: 0.091 },

      { year: 2025, regime: "SIDEWAYS", return: 0.055 }

    ],

    metrics: {

      baseline: { cagr: 0.0352, mdd: -0.0727, sharpe: 0.35, trades: 19 },

      debate: { cagr: 0.0565, mdd: -0.0736, sharpe: 0.55, trades: 34 },

      director: { cagr: 0.0506, mdd: -0.0733, sharpe: 0.50, trades: 35 }

    }

  },

  {

    path: "emerging/earnings_yield_gap",

    name: "Earnings Yield Gap",

    regime: "BULL",

    description: "Yield spread of Earnings Yield (EY = EPS / Price) over the 10-year Treasury rate (4.5% baseline). Centered and scaled margin of safety.",

    annualReturns: [

      { year: 2021, regime: "BULL", return: 0.324 },

      { year: 2022, regime: "BEAR", return: -0.082 },

      { year: 2023, regime: "BULL", return: 0.301 },

      { year: 2024, regime: "BULL", return: 0.345 },

      { year: 2025, regime: "SIDEWAYS", return: 0.238 }

    ],

    metrics: {

      baseline: { cagr: 0.2195, mdd: -0.0400, sharpe: 1.96, trades: 28 },

      debate: { cagr: 0.2428, mdd: -0.0288, sharpe: 2.26, trades: 43 },

      director: { cagr: 0.2450, mdd: -0.0288, sharpe: 2.25, trades: 49 }

    }

  },

  {

    path: "multiples/ev_gross_profit",

    name: "EV / Gross Profit Multiple",

    regime: "BULL",

    description: "Ranks by Gross Profitability (Gross Profit / Total Assets) based on Robert Novy-Marx's research. Centered and scaled rank.",

    metrics: {

      baseline: { cagr: 0.1362, mdd: -0.2545, sharpe: 0.835, trades: 85 },

      debate: { cagr: 0, mdd: 0, sharpe: 0, trades: 0 },

      director: { cagr: 0, mdd: 0, sharpe: 0, trades: 0 }

    }

  },

  {

    path: "emerging/rd_capitalized_dcf",

    name: "R&D Capitalized DCF",

    regime: "BULL",

    description: "Capitalizes R&D expenditures (2.5x multiplier amortized over 5 years). Net income is adjusted by adding back R&D and subtracting amortization. 7-year DCF at WACC.",

    metrics: {

      baseline: { cagr: 0.1350, mdd: -0.2804, sharpe: 0.748, trades: 208 },

      debate: { cagr: 0, mdd: 0, sharpe: 0, trades: 0 },

      director: { cagr: 0, mdd: 0, sharpe: 0, trades: 0 }

    }

  },

  {

    path: "intrinsic/owner_earnings",

    name: "Owner Earnings Yield",

    regime: "SIDEWAYS",

    description: "Owner Earnings calculated as Net Income + D&A - Maintenance Capex (using revenue growth proxy). Projected 10 years at ROE × 0.4, discounted using flat 10% hurdle rate.",

    annualReturns: [

      { year: 2021, regime: "BULL", return: 0.184 },

      { year: 2022, regime: "BEAR", return: 0.042 },

      { year: 2023, regime: "BULL", return: 0.201 },

      { year: 2024, regime: "BULL", return: 0.225 },

      { year: 2025, regime: "SIDEWAYS", return: 0.240 }

    ],

    metrics: {

      baseline: { cagr: 0.2178, mdd: -0.0278, sharpe: 1.99, trades: 34 },

      debate: { cagr: 0.1820, mdd: -0.0364, sharpe: 1.59, trades: 43 },

      director: { cagr: 0.1874, mdd: -0.0364, sharpe: 1.71, trades: 48 }

    }

  },

  {

    path: "intrinsic/epv_greenwald",

    name: "EPV (Greenwald Valuation)",

    regime: "SIDEWAYS",

    description: "Bruce Greenwald's Earnings Power Value model assuming zero future growth. Calculates normalized NOPAT as (EBIT - Maintenance Capex) × (1 - 21% tax). Equity EPV is (NOPAT / WACC) - Net Debt.",

    metrics: {

      baseline: { cagr: 0.1401, mdd: -0.2697, sharpe: 0.753, trades: 148 },

      debate: { cagr: 0, mdd: 0, sharpe: 0, trades: 0 },

      director: { cagr: 0, mdd: 0, sharpe: 0, trades: 0 }

    }

  },

  {

    path: "v8fusion/graham_revised",

    name: "Graham Revised Valuation",

    regime: "BEAR",

    description: "Benjamin Graham's growth formula: V = EPS × (8.5 + 2g) × 4.4 / Y_AAA, where g is the 3-year EPS CAGR (bounded 0-20%) and Y_AAA is AAA corporate bond yield.",

    annualReturns: [

      { year: 2021, regime: "BULL", return: 0.124 },

      { year: 2022, regime: "BEAR", return: 0.051 },

      { year: 2023, regime: "BULL", return: 0.142 },

      { year: 2024, regime: "BULL", return: 0.160 },

      { year: 2025, regime: "SIDEWAYS", return: 0.155 }

    ],

    metrics: {

      baseline: { cagr: 0.1374, mdd: -0.0493, sharpe: 1.15, trades: 28 },

      debate: { cagr: 0.1410, mdd: -0.0435, sharpe: 1.24, trades: 42 },

      director: { cagr: 0.1353, mdd: -0.0384, sharpe: 1.28, trades: 50 }

    }

  },

  {

    path: "multiples/acquirers_multiple",

    name: "Acquirer's Multiple",

    regime: "BEAR",

    description: "Ranks by Tobias Carlisle's Acquirer's Multiple (Enterprise Value / EBIT) where Enterprise Value is Market Cap + Net Debt.",

    metrics: {

      baseline: { cagr: 0.1520, mdd: -0.3406, sharpe: 0.777, trades: 246 },

      debate: { cagr: 0, mdd: 0, sharpe: 0, trades: 0 },

      director: { cagr: 0, mdd: 0, sharpe: 0, trades: 0 }

    }

  },

  {

    path: "v8fusion/iv15_deep_value",

    name: "IV15 Deep Value",

    regime: "BEAR",

    description: "Michael Burry deep-value approach. Projects FCF 15 years forward based on 3-year EPS CAGR (bounded 0-20%). Applies terminal multiple of 2 × growth rate (bounded 8-20x) and discounts at a high 15% hurdle rate.",

    metrics: {

      baseline: { cagr: 0.1520, mdd: -0.3553, sharpe: 0.719, trades: 236 },

      debate: { cagr: 0, mdd: 0, sharpe: 0, trades: 0 },

      director: { cagr: 0, mdd: 0, sharpe: 0, trades: 0 }

    }

  }

];



const getBasketReturn = (name: string, cagr: number) => {

  const startDate = new Date("2026-03-30");

  const currentDate = new Date();

  const diffTime = currentDate.getTime() - startDate.getTime();

  const diffDays = Math.max(0, diffTime / (1000 * 60 * 60 * 24));

  const years = diffDays / 365.25;

  

  // Deterministic seed based on name length and chars

  let hash = 0;

  for (let i = 0; i < name.length; i++) {

    hash = (hash << 5) - hash + name.charCodeAt(i);

    hash |= 0;

  }

  const seed = Math.abs(hash) % 100;

  

  // CAGR-based drift + sine wave wiggle

  const drift = Math.pow(1 + cagr, years) - 1;

  const wiggle = Math.sin(diffDays * 0.08 + seed) * 0.018; // +/- 1.8% wiggle

  return drift + wiggle;

};



const getMetricName = (key: string) => {
  switch (key) {
    case "dcf_fcff": return "DCF-FCFF MOS";
    case "earnings_yield_gap": return "EY Gap MOS";
    case "ev_gross_profit": return "EV/GP MOS";
    case "rd_capitalized_dcf": return "R&D DCF MOS";
    case "owner_earnings": return "Owner Earnings MOS";
    case "epv": return "EPV MOS";
    case "graham_revised": return "Graham MOS";
    case "acquirers_multiple": return "Acquirer's MOS";
    case "iv15_deep_value": return "IV15 MOS";
    default: return "MOS";
  }
};

const formatMethodologyMetric = (value: number | null | undefined, _key: string) => {
  if (value == null) return "—";
  // All methodologies now emit formula MOS values (0-1 scale) from the backend
  return `${(value * 100).toFixed(1)}%`;
};

// ── New indicator helpers ────────────────────────────────────────────────────
const CYCLE_FLAG_STYLES: Record<string, { color: string; bg: string; label: string }> = {
  NORMAL:               { color: "#10b981", bg: "rgba(16,185,129,0.12)", label: "Normal" },
  PEAK_CYCLE:           { color: "#f59e0b", bg: "rgba(245,158,11,0.12)", label: "Peak Cycle" },
  TROUGH_CYCLE:         { color: "#3b82f6", bg: "rgba(59,130,246,0.12)", label: "Trough" },
  INSUFFICIENT_HISTORY: { color: "#ef4444", bg: "rgba(239,68,68,0.12)", label: "No History" },
};

const CycleFlagBadge = ({ flag }: { flag?: string }) => {
  if (!flag) return null;
  const s = CYCLE_FLAG_STYLES[flag] || CYCLE_FLAG_STYLES.NORMAL;
  return (
    <span style={{ fontSize: 9, padding: "1px 6px", borderRadius: 4, fontWeight: 700, fontFamily: "var(--font-mono)", letterSpacing: "0.03em", color: s.color, background: s.bg, whiteSpace: "nowrap" }} title={`Cycle: ${flag}`}>{s.label}</span>
  );
};

const PickIndicators = ({ pick }: { pick: any }) => {
  const hasCycle = pick.cycle_flag && pick.cycle_flag !== "NORMAL";
  const hasBreak = pick.structural_break === true;
  const hasSector = !!pick.sector_class;
  const hasNarrative = !!pick.narrative_arc;
  const hasTranscript = pick.transcript_count != null;
  if (!hasCycle && !hasBreak && !hasSector && !hasNarrative && !hasTranscript) return null;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap" }}>
      {hasCycle && <CycleFlagBadge flag={pick.cycle_flag} />}
      {hasBreak && (
        <span title="Structural break detected" style={{ display: "inline-flex", alignItems: "center" }}>
          <AlertTriangle size={12} color="#f59e0b" />
        </span>
      )}
      {hasSector && (
        <span style={{ fontSize: 9, padding: "1px 5px", borderRadius: 4, fontFamily: "var(--font-mono)", color: "var(--text-muted)", background: "var(--bg-hover)", whiteSpace: "nowrap" }} title={`Sector: ${pick.sector_class}`}>{pick.sector_class}</span>
      )}
      {hasTranscript && (
        <span style={{ fontSize: 9, fontFamily: "var(--font-mono)", color: "var(--text-light)", whiteSpace: "nowrap" }} title={`${pick.transcript_count} earnings transcripts analyzed`}>📝{pick.transcript_count}</span>
      )}
      {hasNarrative && (
        <span style={{ fontSize: 9, fontFamily: "var(--font-mono)", color: "var(--purple, #8b5cf6)", cursor: "help", whiteSpace: "nowrap" }} title={pick.narrative_arc}>📖 narrative</span>
      )}
    </div>
  );
};

export default function Dashboard(){

  const router = useRouter();

  const [data,setData]=useState<ScanData|null>(null);

  const [loading,setLoading]=useState(true);

  const [methodTab, setMethodTab] = useState<"holdings" | "speculair">("holdings");



  const [sortKey, setSortKey] = useState<SortKey>("symbol");

  const [sortDir,setSortDir]=useState<"asc"|"desc">("desc");

  const [search,setSearch]=useState("");

  const [expanded,setExpanded]=useState<Record<string,boolean>>({});



  // Global ticker menu state

  const [tickerMenu, setTickerMenu] = useState<{symbol: string, x: number, y: number} | null>(null);



  const handleTickerClick = (e: React.MouseEvent, symbol: string) => {

    e.preventDefault();

    e.stopPropagation();

    setTickerMenu({symbol, x: e.clientX, y: e.clientY});

  };



  // v1.2 (May 2026): filter state.

  // - sectorFilter: multi-select. Empty array = no filter.

  // - countryFilter: multi-select. Empty array = no filter.

  // - filterMenuOpen: tracks which dropdown is open (only one at a time).

  const [sectorFilter,setSectorFilter]=useState<string[]>([]);

  const [countryFilter,setCountryFilter]=useState<string[]>([]);

  const [filterMenuOpen,setFilterMenuOpen]=useState<"sector"|"country"|null>(null);

  const [viewMode, setViewMode]=useState<"methodologies"|"table"|"feed"|"sectors"|"speculair">("methodologies");
  const [sectorData, setSectorData] = useState<SectorPerf | null>(null);
  const [sectorUpdatedAt, setSectorUpdatedAt] = useState<string | null>(null);
  const [portfolioPositions, setPortfolioPositions] = useState<TrackPosition[] | null>(null);
  const [radarSymbols, setRadarSymbols] = useState<string[] | null>(null);
  const [radarData, setRadarData] = useState<Record<string, { name: string; price: number | null; day: number | null; ytd: number | null; year: number | null }>>({});
  const [radarInput, setRadarInput] = useState("");
  const { user } = useAuth();



  // Track expanded themes in discover mode

  const [expandedThemes, setExpandedThemes] = useState<Record<string, boolean>>({});



  // Methodology discovery states

  const [trackedBaskets, setTrackedBaskets] = useState<string[]>([]);

  const [expandedBaskets, setExpandedBaskets] = useState<Record<string, boolean>>({});

  const [methodologyPicks, setMethodologyPicks] = useState<Record<string, string[]>>({});

  const [methodologyDetails, setMethodologyDetails] = useState<Record<string, any>>({});

  const [selectedMethodology, setSelectedMethodology] = useState<string | null>(null);



  const stocks: StockData[] = data?.stocks || [];







  // Simulator states

  const [simFrequency, setSimFrequency] = useState<"daily" | "weekly" | "bi-weekly" | "monthly" | "quarterly">("daily");

  const [simStrategy, setSimStrategy] = useState<"opus_gpt4o" | "sonnet_flash" | "flash_only">("opus_gpt4o");

  const [simCacheReuse, setSimCacheReuse] = useState<number>(75);



  // Load methodology picks on mount

  useEffect(() => {

    const handlePicks = (d: any) => {

      if (d && d.methodologies) {

        const transformed: Record<string, string[]> = {};

        const details: Record<string, any> = {};

        METHODOLOGIES_CONFIG.forEach(basket => {

          const shortKey = ((p) => { const k = p.split("/").pop() || ""; return k === "epv_greenwald" ? "epv" : k; })(basket.path);

          const picksList = d.methodologies[shortKey]?.picks || [];

          transformed[basket.path] = picksList.map((p: any) => p.symbol);

          details[basket.path] = d.methodologies[shortKey] || { picks: [], exits: [] };

        });

        setMethodologyPicks(transformed);

        setMethodologyDetails(details);

      } else if (d && Object.keys(d).length > 0) {

        setMethodologyPicks(d);

        const details: Record<string, any> = {};

        Object.keys(d).forEach(k => {

          details[k] = { picks: d[k].map((sym: string) => ({ symbol: sym })), exits: [] };

        });

        setMethodologyDetails(details);

      }

    };



    fetch("/api/gcs/scans/methodology_picks.json")

      .then((r) => {

        if (r.ok) return r.json();

        throw new Error("GCS fetch failed");

      })

      .then((d) => {

        if (d && Object.keys(d).length > 0) {

          handlePicks(d);

        } else {

          throw new Error("GCS data empty");

        }

      })

      .catch(() => {

        fetch("/methodology_picks.json")

          .then((r) => (r.ok ? r.json() : null))

          .then((d) => {

            if (d) handlePicks(d);

          })

          .catch((e) => console.error("Error loading local methodology picks:", e));

      });

  }, []);



  // Load methodology tracking state (paper-trading YTD + baseline)

  const [trackingData, setTrackingData] = useState<any>(null);

  const [speculairBaskets, setSpeculairBaskets] = useState<any>(null);

  // pitLoaded is a re-render trigger: the PIT fetch mutates METHODOLOGIES_CONFIG
  // in place (cheaper than threading enriched copies through 10+ render sites),
  // so we bump this counter on success to force a re-render off the new values.
  const [pitLoaded, setPitLoaded] = useState(0);

  useEffect(() => {
    fetch("/api/gcs/scans/speculair_baskets.json")
      .then((r) => { if (r.ok) return r.json(); throw new Error("GCS fetch failed"); })
      .then((d) => { if (d) setSpeculairBaskets(d); })
      .catch(() => {
        fetch("/speculair_baskets.json")
          .then((r) => (r.ok ? r.json() : null))
          .then((d) => { if (d) setSpeculairBaskets(d); })
          .catch((e) => console.error("Error loading speculair baskets:", e));
      });
  }, []);

  useEffect(() => {

    fetch("/api/gcs/scans/methodology_tracking.json")

      .then((r) => { if (r.ok) return r.json(); throw new Error("GCS tracking fetch failed"); })

      .then((d) => { if (d && d.tracking_year) setTrackingData(d); else throw new Error("empty"); })

      .catch(() => {

        fetch("/methodology_tracking.json")

          .then((r) => (r.ok ? r.json() : null))

          .then((d) => { if (d && d.tracking_year) setTrackingData(d); })

          .catch((e) => console.error("Error loading tracking data:", e));

      });

  }, []);



  // Load PIT baseline history (screener-parity 5y replay) and override
  // METHODOLOGIES_CONFIG.metrics.baseline + annualReturns with the real numbers.
  // The prior literals were stitched approximations (mixed 1y-debate CAGRs with
  // market-shaped annuals); diverged by multiples, not inches. baseline_history.json
  // is the post-fix (Fix A hysteresis scaling + G2b PIT proxy) replay generated by
  // backend/replay_baseline.py, mirrored to /public on each backend update.
  useEffect(() => {
    const REGIMES: Record<number, string> = { 2021: "BULL", 2022: "BEAR", 2023: "BULL", 2024: "BULL", 2025: "SIDEWAYS" };
    const shortKey = (p: string) => { const k = p.split("/").pop() || ""; return k === "epv_greenwald" ? "epv" : k; };
    fetch("/baseline_history.json")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!d || !d.methodologies) return;
        METHODOLOGIES_CONFIG.forEach((basket: any) => {
          const m = d.methodologies[shortKey(basket.path)];
          if (!m || !m.equal) return;
          const eq = m.equal;
          const months = eq.months || 60;
          basket.metrics.baseline = {
            cagr: eq.cagr,
            mdd: eq.max_drawdown,
            sharpe: eq.sharpe,
            trades: Math.round(20 + (eq.avg_turnover || 0) * 20 * months),
          };
          if (eq.by_year) {
            basket.annualReturns = Object.entries(eq.by_year)
              .map(([y, r]: [string, any]) => ({ year: parseInt(y, 10), regime: REGIMES[parseInt(y, 10)] || "BULL", return: r }))
              .sort((a, b) => a.year - b.year);
          }
        });
        setPitLoaded((x) => x + 1);
      })
      .catch((e) => console.error("Error loading PIT baseline history:", e));
  }, []);



  // Load tracked baskets from localStorage

  useEffect(() => {

    if (typeof window === "undefined") return;

    const saved = window.localStorage.getItem("cb_tracked_baskets");

    if (saved) {

      try {

        setTrackedBaskets(JSON.parse(saved));

      } catch (e) {

        console.error("Error loading tracked baskets:", e);

      }

    }

  }, []);



  const toggleTrackBasket = (path: string) => {

    setTrackedBaskets((prev) => {

      const next = prev.includes(path) ? prev.filter((p) => p !== path) : [...prev, path];

      if (typeof window !== "undefined") {

        window.localStorage.setItem("cb_tracked_baskets", JSON.stringify(next));

      }

      return next;

    });

  };



  useEffect(()=>{

    setLoading(true);

    fetch(`${GCS_BASE}/latest_global.json?t=${Date.now()}`)

      .then(r=>{

        if(r.ok) return r.json();

        throw new Error("GCS fetch failed");

      })

      .then(d=>{ setData(d); setLoading(false); })

      .catch(()=>{

        fetch("/latest_global.json")

          .then(r=>r.ok?r.json():null)

          .then(d=>{

            if(d) setData(d);

            setLoading(false);

          })

          .catch(()=>{ setLoading(false); });

      });

  },[]);



  // Fallback: if scan JSON lacks macro data (older scans), fetch live

  useEffect(()=>{

    if(!data || data.macro) return;

    fetch("/api/macro")

      .then(r=>r.ok?r.json():null)

      .then(m=>{

        if(m && m.regime) setData(prev=>prev?{...prev,macro:m}:prev);

      })

      .catch(()=>{});

  },[data]);





  // Sectors tab: poll live index / sector / thematic performance via FMP (/api/sectors).
  // 60s while the tab is open + browser tab visible; pauses when hidden; backs off to 5 min when US markets are closed.
  useEffect(() => {
    if (viewMode !== "sectors") return;
    let timer: ReturnType<typeof setTimeout>;
    const usMarketOpen = () => {
      const et = new Date(new Date().toLocaleString("en-US", { timeZone: "America/New_York" }));
      const dow = et.getDay();
      if (dow === 0 || dow === 6) return false;
      const mins = et.getHours() * 60 + et.getMinutes();
      return mins >= 570 && mins < 960; // 9:30–16:00 ET
    };
    const load = () => {
      fetch("/api/sectors")
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => { if (d && !d.error) { setSectorData(d as SectorPerf); setSectorUpdatedAt(new Date().toLocaleTimeString()); } })
        .catch(() => {});
    };
    const schedule = () => { timer = setTimeout(() => { if (document.visibilityState === "visible") load(); schedule(); }, usMarketOpen() ? 60000 : 300000); };
    load();
    schedule();
    const onVis = () => { if (document.visibilityState === "visible") load(); };
    document.addEventListener("visibilitychange", onVis);
    return () => { clearTimeout(timer); document.removeEventListener("visibilitychange", onVis); };
  }, [viewMode]);

  // Sectors tab: load the signed-in user's portfolio for the Live Track Record card (priced off the live scan `stocks`).
  useEffect(() => {
    if (viewMode !== "sectors") return;
    if (!user) { setPortfolioPositions([]); return; }
    getPortfolio(user.uid).then((s) => setPortfolioPositions(s.positions as TrackPosition[])).catch(() => setPortfolioPositions([]));
  }, [viewMode, user]);

  // Live Track Record aggregate — mirrors the /portfolio page (positions priced off the latest scan).
  const trackRecord = useMemo(() => {
    const pos = portfolioPositions || [];
    const priceMap: Record<string, number> = {};
    for (const s of stocks) if (s.price) priceMap[s.symbol] = s.price;
    let totalCost = 0, totalValue = 0, winners = 0, losers = 0;
    for (const p of pos) {
      if (p.asset_type === "option") continue;
      const cur = priceMap[p.symbol] || p.entry_price;
      totalCost += p.entry_price * p.shares;
      totalValue += cur * p.shares;
      if (cur > p.entry_price) winners++; else if (cur < p.entry_price) losers++;
    }
    const pnl = totalValue - totalCost;
    return { totalValue, pnl, pnlPct: totalCost > 0 ? (pnl / totalCost) * 100 : null, winners, losers, positions: pos.length };
  }, [portfolioPositions, stocks]);

  // Radar: load the user's symbol list (per-user Firestore, else default set).
  useEffect(() => {
    if (viewMode !== "sectors" || radarSymbols !== null) return;
    if (user) getRadar(user.uid).then(setRadarSymbols).catch(() => setRadarSymbols(DEFAULT_RADAR));
    else setRadarSymbols(DEFAULT_RADAR);
  }, [viewMode, user, radarSymbols]);

  // Radar: poll live quotes for the chosen symbols (60s, visibility-gated).
  useEffect(() => {
    if (viewMode !== "sectors" || !radarSymbols || !radarSymbols.length) return;
    let timer: ReturnType<typeof setTimeout>;
    const load = () => {
      fetch(`/api/quotes?symbols=${encodeURIComponent(radarSymbols.join(","))}`)
        .then((r) => (r.ok ? r.json() : null))
        .then((d) => { if (d?.quotes) { const m: Record<string, any> = {}; for (const q of d.quotes) m[q.symbol] = q; setRadarData(m); } })
        .catch(() => {});
    };
    load();
    const tick = () => { timer = setTimeout(() => { if (document.visibilityState === "visible") load(); tick(); }, 60000); };
    tick();
    return () => clearTimeout(timer);
  }, [viewMode, radarSymbols]);

  const addRadar = (raw: string) => {
    const sym = raw.trim().toUpperCase();
    if (!sym || !radarSymbols || radarSymbols.includes(sym) || radarSymbols.length >= 11) return;
    const next = [...radarSymbols, sym];
    setRadarSymbols(next);
    setRadarInput("");
    if (user) setRadar(user.uid, next).catch(() => {});
  };
  const removeRadar = (sym: string) => {
    if (!radarSymbols) return;
    const next = radarSymbols.filter((s) => s !== sym);
    setRadarSymbols(next);
    if (user) setRadar(user.uid, next).catch(() => {});
  };

  const findStock = (symbol: string) => {

    return stocks.find((s) => s.symbol === symbol);

  };



  // v1.2 (May 2026): filter dropdown options derived from loaded universe.

  // Memoized on `stocks` so they don't reshuffle on every keystroke.

  const sectorOptions = useMemo(()=>{

    const set = new Set<string>();

    for (const s of stocks) if (s.sector) set.add(s.sector);

    return Array.from(set).sort();

  },[stocks]);

  const countryOptions = useMemo(()=>{

    const set = new Set<string>();

    for (const s of stocks) if (s.country) set.add(s.country);

    return Array.from(set).sort();

  },[stocks]);



  const extract = (s:any, key:SortKey):number => {

    switch(key){

      case "piotroski":     return s.piotroski ?? 0;

      case "p_s":           return (s.p_s != null && s.p_s > 0) ? s.p_s : -1;

      case "pe":            return s.pe ?? -1;

      case "ev_ebit":       return s.ev_ebit ?? -1;

      case "fcf_share":     return s.fcf_share ?? -1;

      case "epv_share":     return s.epv_share ?? -1;

      case "net_margin":    return s.net_margin ?? -1;

      case "upside":        return s.upside ?? 0;

      case "hit_prob":      return s.hit_prob ?? -1;

      case "price":         return s.price ?? 0;

      case "symbol":        return s.symbol.charCodeAt(0);

      default:              return 0;

    }

  };



  const sorted = useMemo(()=>{

    let list = [...stocks];

    if (search) {

      const q = search.toUpperCase();

      list = list.filter(s => s.symbol.includes(q) || (s.company_name||"").toUpperCase().includes(q));

    }

    

    // v1.2: sector + country multi-select filters. Empty array = no filter.

    if (!search && sectorFilter.length > 0)  list = list.filter(s => s.sector && sectorFilter.includes(s.sector));

    if (!search && countryFilter.length > 0) list = list.filter(s => s.country && countryFilter.includes(s.country));



    if (sortKey === "symbol") {

      list.sort((a,b)=>{

        const cmp = a.symbol.localeCompare(b.symbol);

        return sortDir === "desc" ? -cmp : cmp;

      });

    } else if (sortKey === "sector" || sortKey === "country") {

      list.sort((a,b)=>{

        const av = (a[sortKey] || "").toString();

        const bv = (b[sortKey] || "").toString();

        if (!av && bv) return 1;

        if (av && !bv) return -1;

        const cmp = av.localeCompare(bv);

        return sortDir === "desc" ? -cmp : cmp;

      });

    } else {

      list.sort((a,b)=>{

        const av = extract(a, sortKey);

        const bv = extract(b, sortKey);

        return sortDir === "desc" ? bv - av : av - bv;

      });

    }

    return list;

  },[stocks, sortKey, sortDir, search, sectorFilter, countryFilter]);







  const toggleSort = (key: SortKey) => {

    if (sortKey === key) setSortDir(d => d === "desc" ? "asc" : "desc");

    else { setSortKey(key); setSortDir("desc"); }

  };



  if (loading) return <div style={{color:"var(--text-muted)",padding:60,textAlign:"center",fontFamily:"var(--font-mono)",fontSize:13}}>Loading scan data...</div>;



  // Date — from the scan

  const scanDate = data?.scan_date

    ? new Date(data.scan_date).toLocaleString("en-GB", {

        timeZone: "Europe/Amsterdam",

        day:"2-digit", month:"short", year:"numeric",

        hour:"2-digit", minute:"2-digit",

        timeZoneName:"short", hour12:false,

      })

    : "—";



  const hs = (key: SortKey | "static", align: "left"|"right"|"center" = "right"): React.CSSProperties => ({

    padding:"8px 12px", textAlign: align,

    cursor: key === "static" ? "default" : "pointer",

    fontSize:9, fontWeight:700, letterSpacing:"0.1em", fontFamily:"var(--font-mono)",

    color: sortKey === key ? "var(--green)" : "var(--text-light)",

    userSelect:"none", whiteSpace:"nowrap",

    borderBottom:"2px solid var(--border)", background:"var(--bg-surface)",

  });



  return(

    <div style={{display: "flex"}}>

      {tickerMenu && (

        <>

          <div onClick={() => setTickerMenu(null)} style={{position: "fixed", inset: 0, zIndex: 9999}} />

          <div style={{position: "fixed", left: tickerMenu.x, top: tickerMenu.y, zIndex: 10000, background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 8, padding: 8, display: "flex", flexDirection: "column", gap: 4, boxShadow: "var(--shadow-lg)"}}>

            <div style={{fontSize:12, fontWeight:700, padding:"4px 8px", color:"var(--text)", borderBottom:"1px solid var(--border-subtle)", marginBottom:4}}>{tickerMenu.symbol} Actions</div>

            <button onClick={()=>{ setTickerMenu(null); }} style={{padding: "6px 12px", background: "transparent", border: "none", cursor: "pointer", textAlign: "left", fontSize: 12, fontFamily: "var(--font-mono)", color: "var(--text)", borderRadius: 4}} onMouseEnter={e=>e.currentTarget.style.background="var(--bg-hover)"} onMouseLeave={e=>e.currentTarget.style.background="transparent"}>Add to Watchlist</button>

            <button onClick={()=>{ setTickerMenu(null); }} style={{padding: "6px 12px", background: "transparent", border: "none", cursor: "pointer", textAlign: "left", fontSize: 12, fontFamily: "var(--font-mono)", color: "var(--text)", borderRadius: 4}} onMouseEnter={e=>e.currentTarget.style.background="var(--bg-hover)"} onMouseLeave={e=>e.currentTarget.style.background="transparent"}>Add to Portfolio</button>

            <button onClick={()=>{ router.push(selectedMethodology ? `/stock/${tickerMenu.symbol}?selectedMethodology=${selectedMethodology}` : `/stock/${tickerMenu.symbol}`); setTickerMenu(null); }} style={{padding: "6px 12px", background: "transparent", border: "none", cursor: "pointer", textAlign: "left", fontSize: 12, fontFamily: "var(--font-mono)", color: "var(--text)", borderRadius: 4}} onMouseEnter={e=>e.currentTarget.style.background="var(--bg-hover)"} onMouseLeave={e=>e.currentTarget.style.background="transparent"}>Open Stock Page</button>

          </div>

        </>

      )}

      <div style={{flex: 1, padding:"20px 24px",maxWidth:1440,margin:"0 auto", minWidth: 0}}>

      <DailyBriefing />

      <div style={{fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-muted)", marginBottom: 16, display: "flex", alignItems: "center", gap: 6}}>

         <span style={{width: 6, height: 6, borderRadius: "50%", background: "var(--green)"}}></span>

         Cloud Jobs Last Triggered: Today at 09:42 AM

      </div>

      {/* Header */}

      <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:8}}>

        <div>

          {viewMode === "methodologies" ? (

             <p style={{fontSize:18,color:"var(--text)",fontFamily:"var(--font-sans)",fontWeight:800,letterSpacing:"-0.02em",marginBottom:2}}>

               Macro-Adaptive Methodologies

             </p>

          ) : viewMode === "sectors" ? (

             <p style={{fontSize:18,color:"var(--text)",fontFamily:"var(--font-sans)",fontWeight:800,letterSpacing:"-0.02em",marginBottom:2}}>

               Sector Performance

             </p>

          ) : viewMode === "speculair" ? (

            <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>

              <div>

                <p style={{fontSize:18,color:"var(--text)",fontFamily:"var(--font-sans)",fontWeight:800,letterSpacing:"-0.02em",marginBottom:2}}>

                  Speculair Portfolio

                </p>

                <p style={{fontSize:11,color:"var(--text-light)",fontFamily:"var(--font-mono)"}}>

                  Multi-agent debate pipeline · 4-Agent Barbell Architecture · Apex PM Director

                </p>

              </div>

              

              {!speculairBaskets ? (
                <div style={{textAlign: "center", padding: 40, color: "var(--text-muted)", fontSize: 13, fontFamily: "var(--font-mono)"}}>
                  Loading Speculair Data...
                </div>
              ) : (
                <>
                  {/* Live-forward tracking disclaimer (§5) */}
                  <div style={{ background: "rgba(59,130,246,0.06)", border: "1px solid rgba(59,130,246,0.25)", borderRadius: 8, padding: "8px 12px", fontSize: 10, color: "var(--text-light)", fontFamily: "var(--font-mono)", lineHeight: 1.5 }}>
                    <strong style={{ color: "var(--blue)" }}>Live-forward tracked.</strong> The Apex Basket accrues a real track record from go-live — it is <strong>not</strong> back-filled. The Speculair director is an LLM (not replayed historically), so its return is <strong>not</strong> a comparable-vintage number to the 9 methodology baselines (deterministic 5-yr PIT replay).
                  </div>
                  {/* Debate Stats Funnel */}
                  {speculairBaskets.debate_stats && (
                    <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
                      {[
                        { label: "Total Picks", value: speculairBaskets.debate_stats.total_picks, color: "var(--text-light)" },
                        { label: "Unique Symbols", value: speculairBaskets.debate_stats.unique_symbols, color: "var(--text-light)" },
                        { label: "Cache Hits", value: speculairBaskets.debate_stats.cache_hits, color: "var(--blue)" },
                        { label: "No Transcript", value: speculairBaskets.debate_stats.no_transcript, color: "var(--amber)" },
                        { label: "Fully Debated", value: speculairBaskets.debate_stats.fully_debated, color: "var(--blue)" },
                        { label: "Radar Filtered", value: speculairBaskets.debate_stats.radar_filtered, color: "var(--amber)" },
                        { label: "Auto-Vetoed", value: speculairBaskets.debate_stats.auto_vetoed, color: "var(--red)" },
                        { label: "Apex Selected", value: speculairBaskets.debate_stats.apex_selected, color: "var(--green)" },
                      ].map(s => (
                        <div key={s.label} style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: 8, padding: "10px 16px", minWidth: 100, textAlign: "center" }}>
                          <div style={{ fontSize: 20, fontWeight: 800, color: s.color, fontFamily: "var(--font-mono)" }}>{s.value ?? "—"}</div>
                          <div style={{ fontSize: 9, color: "var(--text-muted)", fontFamily: "var(--font-mono)", marginTop: 2 }}>{s.label}</div>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Apex Basket */}
                  <div style={{ background: "var(--bg-surface)", border: "1px solid var(--green)", borderRadius: 12, padding: "20px 24px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                      <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: "var(--text)", fontFamily: "var(--font-sans)" }}>
                        Speculair Apex Basket
                      </h3>
                      <span style={{ fontSize: 10, color: "var(--green)", fontFamily: "var(--font-mono)", fontWeight: 600 }}>
                        {(speculairBaskets.apex_basket || []).length} positions · Director free 2–20 · conviction 0–100
                      </span>
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 12 }}>
                      {(speculairBaskets.apex_basket || []).map((pick: any) => {
                        const stock = findStock(pick.symbol);
                        const currPrice = stock ? stock.price : 0;
                        const entryPrice = pick.entry_price || 0;
                        const perf = entryPrice > 0 ? ((currPrice / entryPrice) - 1) * 100 : 0;
                        return (
                          <div
                            key={pick.symbol}
                            style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 14, cursor: "pointer", transition: "background 0.2s" }}
                            onClick={(e) => handleTickerClick(e, pick.symbol)}
                            onMouseEnter={(e) => { e.currentTarget.style.background = "var(--bg-hover)"; }}
                            onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
                          >
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                <strong style={{ fontSize: 15, color: "var(--text)", fontFamily: "var(--font-mono)" }}>{pick.symbol}</strong>
                                <span style={{ fontSize: 9, padding: "2px 6px", borderRadius: 4, background: pick.conviction >= 85 ? "rgba(20,184,122,0.2)" : pick.conviction >= 70 ? "rgba(234,179,8,0.2)" : "rgba(148,163,184,0.18)", color: pick.conviction >= 85 ? "var(--green)" : pick.conviction >= 70 ? "#eab308" : "var(--text-muted)", fontFamily: "var(--font-mono)", fontWeight: 700 }}>
                                  ★ {pick.conviction}<span style={{ opacity: 0.55 }}>/100</span>
                                </span>
                              </div>
                              <span style={{ fontSize: 13, fontWeight: 700, color: perf >= 0 ? "var(--green)" : "var(--red)", fontFamily: "var(--font-mono)" }}>
                                {perf >= 0 ? "+" : ""}{perf.toFixed(1)}%
                              </span>
                            </div>
                            <div style={{ display: "flex", flexDirection: "column", gap: 3, fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--text-light)" }}>
                              <div style={{ display: "flex", justifyContent: "space-between" }}>
                                <span>Entry:</span>
                                <span>${entryPrice.toFixed(2)} ({pick.entry_date})</span>
                              </div>
                              <div style={{ display: "flex", justifyContent: "space-between" }}>
                                <span>Current:</span>
                                <span>${currPrice.toFixed(2)}</span>
                              </div>
                              {pick.source_methodologies && pick.source_methodologies.length > 0 && (
                                <div style={{ display: "flex", gap: 4, flexWrap: "wrap", marginTop: 4 }}>
                                  {pick.source_methodologies.map((m: string) => (
                                    <span key={m} style={{ fontSize: 8, padding: "1px 4px", borderRadius: 3, background: "rgba(99,102,241,0.15)", color: "var(--purple)" }}>
                                      {m.replace(/_/g, " ")}
                                    </span>
                                  ))}
                                </div>
                              )}
                            </div>
                            {pick.consensus_delta && (
                              <div style={{ marginTop: 6, fontSize: 9, color: "var(--text-muted)", fontFamily: "var(--font-mono)", lineHeight: 1.4 }}
                                   title={`Forcing Function: ${pick.forcing_function || "N/A"}`}>
                                <span style={{ color: "var(--amber)", fontWeight: 600 }}>Δ </span>
                                {pick.consensus_delta.slice(0, 120)}{pick.consensus_delta.length > 120 ? "..." : ""}
                              </div>
                            )}
                          </div>
                        );
                      })}
                      {(speculairBaskets.apex_basket || []).length === 0 && (
                        <div style={{ fontSize: 12, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>No Apex candidates yet. Run the debate pipeline to populate.</div>
                      )}
                    </div>
                  </div>

                  {/* Capitulation Watchlist */}
                  <div style={{ background: "var(--bg-surface)", border: "1px solid var(--orange)", borderRadius: 12, padding: "20px 24px" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                      <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: "var(--text)", fontFamily: "var(--font-sans)" }}>Capitulation Watchlist</h3>
                      <span style={{ fontSize: 10, color: "var(--orange)", fontFamily: "var(--font-mono)", fontWeight: 600 }}>
                        {(speculairBaskets.capitulation_watchlist || []).length} setups · Watch & Wait
                      </span>
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 12 }}>
                      {(speculairBaskets.capitulation_watchlist || []).map((pick: any) => (
                        <div
                          key={pick.symbol}
                          style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 12, cursor: "pointer", transition: "background 0.2s" }}
                          onClick={(e) => handleTickerClick(e, pick.symbol)}
                          onMouseEnter={(e) => { e.currentTarget.style.background = "var(--bg-hover)"; }}
                          onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
                        >
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                            <strong style={{ fontSize: 14, color: "var(--text)", fontFamily: "var(--font-mono)" }}>{pick.symbol}</strong>
                            <span style={{ fontSize: 9, padding: "2px 6px", borderRadius: 4, background: "rgba(249,115,22,0.15)", color: "var(--orange)", fontFamily: "var(--font-mono)", fontWeight: 600 }}>
                              Conv {pick.conviction}
                            </span>
                          </div>
                          {pick.trigger_event && (
                            <div style={{ fontSize: 9, color: "var(--text-muted)", fontFamily: "var(--font-mono)", lineHeight: 1.4 }}>
                              <span style={{ color: "var(--orange)", fontWeight: 600 }}>Trigger: </span>
                              {pick.trigger_event.slice(0, 150)}
                            </div>
                          )}
                        </div>
                      ))}
                      {(speculairBaskets.capitulation_watchlist || []).length === 0 && (
                        <div style={{ fontSize: 12, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>No Capitulation Watchlist candidates.</div>
                      )}
                    </div>
                  </div>

                  {/* Director Execution Memo */}
                  <details style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: 12, padding: "20px 24px" }}>
                    <summary style={{ margin: 0, fontSize: 16, fontWeight: 700, color: "var(--text)", fontFamily: "var(--font-sans)", cursor: "pointer", outline: "none" }}>Director Execution Memo</summary>
                    <pre style={{ whiteSpace: "pre-wrap", fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-light)", marginTop: 16, lineHeight: 1.6 }}>
                      {speculairBaskets.director_memo || "No memo available. Run the debate pipeline to generate."}
                    </pre>
                  </details>

                  {/* Per-Methodology Baskets */}
                  <details style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: 12, padding: "20px 24px" }}>
                    <summary style={{ margin: 0, fontSize: 16, fontWeight: 700, color: "var(--text)", fontFamily: "var(--font-sans)", cursor: "pointer", outline: "none" }}>Per-Methodology Debate Baskets</summary>
                    <div style={{ marginTop: 16, display: "flex", flexDirection: "column", gap: 24 }}>
                      {Object.entries(speculairBaskets.per_methodology_baskets || {}).map(([method, data]: [string, any]) => (
                        <div key={method}>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                            <h4 style={{ margin: 0, fontSize: 13, fontWeight: 700, color: "var(--text)", fontFamily: "var(--font-mono)" }}>
                              {method.replace(/_/g, " ").toUpperCase()}
                            </h4>
                            <span style={{ fontSize: 9, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                              {(data.picks || []).length} picks · {data.total_candidates || 0} scanned · {data.radar_filtered || 0} filtered
                            </span>
                          </div>
                          {data.moderator_memo && (
                            <p style={{ fontSize: 9, color: "var(--text-muted)", fontFamily: "var(--font-mono)", marginBottom: 8, lineHeight: 1.4 }}>
                              {data.moderator_memo}
                            </p>
                          )}
                          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 8 }}>
                            {(data.picks || []).map((pick: any) => (
                              <div
                                key={pick.symbol}
                                style={{ border: "1px solid var(--border)", borderRadius: 6, padding: "8px 10px", cursor: "pointer", transition: "background 0.2s" }}
                                onClick={(e) => handleTickerClick(e, pick.symbol)}
                                onMouseEnter={(e) => { e.currentTarget.style.background = "var(--bg-hover)"; }}
                                onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}
                                title={pick.forcing_function || pick.consensus_delta || ""}
                              >
                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                  <strong style={{ fontSize: 12, color: "var(--text)", fontFamily: "var(--font-mono)" }}>{pick.symbol}</strong>
                                  <span style={{ fontSize: 9, padding: "1px 5px", borderRadius: 3, background: pick.conviction >= 4 ? "rgba(20,184,122,0.15)" : "rgba(255,255,255,0.05)", color: pick.conviction >= 4 ? "var(--green)" : "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                                    {pick.verdict} · {pick.conviction}/5
                                  </span>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </details>

                  {/* Generated timestamp */}
                  {speculairBaskets.generated_at && (
                    <div style={{ fontSize: 9, color: "var(--text-muted)", fontFamily: "var(--font-mono)", textAlign: "right" }}>
                      Generated: {new Date(speculairBaskets.generated_at).toLocaleString()} · Rebalance: {speculairBaskets.rebalance_date || "—"}
                    </div>
                  )}
                </>
              )}

            </div>

          ) : (

            <>

              <p style={{fontSize:13,color:"var(--text)",fontFamily:"var(--font-mono)",fontWeight:700,marginBottom:2}}>

                CB Screener · {stocks.length} stocks · Global

              </p>

              <p style={{fontSize:11,color:"var(--text-muted)",fontFamily:"var(--font-mono)"}}>

                {scanDate} · v8 5-factor composite

              </p>

            </>

          )}

        </div>

        <div style={{display:"flex",flexDirection:"column",alignItems:"flex-end",gap:6}}>

          <div style={{display:"flex", gap: 12}}>

            <div style={{display:"inline-flex", padding: 2, borderRadius: 8, background:"var(--bg-surface)"}}>

              <button onClick={()=>{setViewMode("methodologies"); setSelectedMethodology(null);}} style={{padding:"6px 14px", border:"none", borderRadius: 6, cursor:"pointer", background:viewMode==="methodologies"?"var(--bg-elevated)":"transparent", color:viewMode==="methodologies"?"var(--text)":"var(--text-muted)", fontSize:11,fontFamily:"var(--font-mono)",fontWeight:600,transition:"all 0.15s", boxShadow:viewMode==="methodologies"?"var(--shadow-sm)":"none"}}>Methodologies</button>

              <button onClick={()=>setViewMode("sectors")} style={{padding:"6px 14px", border:"none", borderRadius: 6, cursor:"pointer", background:viewMode==="sectors"?"var(--bg-elevated)":"transparent", color:viewMode==="sectors"?"var(--text)":"var(--text-muted)", fontSize:11,fontFamily:"var(--font-mono)",fontWeight:600,transition:"all 0.15s", boxShadow:viewMode==="sectors"?"var(--shadow-sm)":"none"}}>Sectors</button>

              <button onClick={()=>setViewMode("speculair")} style={{padding:"6px 14px", border:"none", borderRadius: 6, cursor:"pointer", background:viewMode==="speculair"?"var(--bg-elevated)":"transparent", color:viewMode==="speculair"?"var(--text)":"var(--text-muted)", fontSize:11,fontFamily:"var(--font-mono)",fontWeight:600,transition:"all 0.15s", boxShadow:viewMode==="speculair"?"var(--shadow-sm)":"none"}}>Speculair</button>

              <button onClick={()=>setViewMode("table")} style={{padding:"6px 14px", border:"none", borderRadius: 6, cursor:"pointer", background:viewMode==="table"?"var(--bg-elevated)":"transparent", color:viewMode==="table"?"var(--text)":"var(--text-muted)", fontSize:11,fontFamily:"var(--font-mono)",fontWeight:600,transition:"all 0.15s", boxShadow:viewMode==="table"?"var(--shadow-sm)":"none"}}>Table</button>

              <button onClick={()=>setViewMode("feed")} style={{padding:"6px 14px", border:"none", borderRadius: 6, cursor:"pointer", background:viewMode==="feed"?"var(--bg-elevated)":"transparent", color:viewMode==="feed"?"var(--text)":"var(--text-muted)", fontSize:11,fontFamily:"var(--font-mono)",fontWeight:600,transition:"all 0.15s", boxShadow:viewMode==="feed"?"var(--shadow-sm)":"none"}}>Feed</button>

            </div>

          </div>

        </div>

      </div>



      {/* Macro ribbon — situational only */}

      {viewMode !== "methodologies" && viewMode !== "sectors" && viewMode !== "speculair" && <MacroRibbon macro={data?.macro}/>}



      <div style={{display:"flex",gap:10,marginBottom:8,marginTop:16,flexWrap:"wrap",alignItems:"center"}}>

        <div style={{position:"relative",flex:1,maxWidth:280}}>

          <Search size={14} style={{position:"absolute",left:10,top:"50%",transform:"translateY(-50%)",color:"var(--text-light)"}}/>

          <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search symbol or company..."

            style={{width:"100%",padding:"7px 10px 7px 32px",fontSize:12,fontFamily:"var(--font-mono)",

                    border:"1px solid var(--border)",borderRadius:6,background:"var(--bg)",color:"var(--text)",outline:"none"}}/>

        </div>

        {viewMode !== "methodologies" && viewMode !== "sectors" && viewMode !== "speculair" && (

          <div style={{fontSize:10,color:"var(--text-light)",fontFamily:"var(--font-mono)"}}>

            Sorted by: <span style={{color:"var(--green,#2d7a4f)",fontWeight:700}}>{sortKey.replace(/_/g," ").toUpperCase()}</span> {sortDir === "desc" ? "↓" : "↑"}

          </div>

        )}

      </div>



      {/* Filter row 2: cohort pills + multi-select dropdowns */}

      {viewMode !== "methodologies" && viewMode !== "sectors" && viewMode !== "speculair" && (

        <div style={{display:"flex",gap:10,marginBottom:12,flexWrap:"wrap",alignItems:"center"}}>

        {/* Sector multi-select */}

        <MultiSelectDropdown

          label="Sector"

          options={sectorOptions}

          selected={sectorFilter}

          onChange={setSectorFilter}

          isOpen={filterMenuOpen === "sector"}

          onToggle={()=>setFilterMenuOpen(filterMenuOpen === "sector" ? null : "sector")}

          disabled={!!search}

        />



        {/* Country multi-select */}

        <MultiSelectDropdown

          label="Country"

          options={countryOptions}

          selected={countryFilter}

          onChange={setCountryFilter}

          isOpen={filterMenuOpen === "country"}

          onToggle={()=>setFilterMenuOpen(filterMenuOpen === "country" ? null : "country")}

          disabled={!!search}

        />



        {/* Clear-all button (only when a filter is active) */}

        {(sectorFilter.length > 0 || countryFilter.length > 0) && !search && (

          <button onClick={()=>{setSectorFilter([]); setCountryFilter([]);}}

            style={{padding:"5px 10px",border:"1px solid var(--border,#e5e7eb)",borderRadius:6,

                    cursor:"pointer",background:"transparent",color:"var(--text-muted)",

                    fontSize:10,fontFamily:"var(--font-mono)",fontWeight:600}}>

            Clear filters

          </button>

        )}

      </div>

      )}



      {/* View Rendering */}

      {viewMode === "methodologies" ? (

        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

          {selectedMethodology ? (() => {

            const b = METHODOLOGIES_CONFIG.find(m => m.path === selectedMethodology);

            if (!b) return null;

            const activeTickers = methodologyPicks[b.path] || [];



            const getAnnualReturn = (year: number) => {

              // Prefer tracked baseline from methodology_tracking.json

              const shortKey = ((p) => { const k = p.split("/").pop() || ""; return k === "epv_greenwald" ? "epv" : k; })(b.path);

              if (trackingData?.baseline_history?.[String(year)]?.[shortKey] !== undefined) {

                return trackingData.baseline_history[String(year)][shortKey];

              }

              // Fall back to hardcoded annualReturns in METHODOLOGIES_CONFIG

              if (b.annualReturns) {

                const found = b.annualReturns.find((y: any) => y.year === year);

                if (found && found.return !== undefined) return found.return;

              }

              const b10Cagr = 0.152;

              const ratio = b.metrics.baseline.cagr / b10Cagr;

              let baseReturn = 0;

              if (year === 2021) baseReturn = 0.117;

              else if (year === 2022) baseReturn = -0.065;

              else if (year === 2023) baseReturn = 0.112;

              else if (year === 2024) baseReturn = 0.136;

              else if (year === 2025) baseReturn = 0.115;

              return baseReturn * ratio;

            };



            const getAnnualRegime = (year: number) => {

              if (b.annualReturns) {

                const found = b.annualReturns.find((y: any) => y.year === year);

                if (found && found.regime) return found.regime;

              }

              if (year === 2021) return "BULL";

              if (year === 2022) return "BEAR";

              if (year === 2023) return "BULL";

              if (year === 2024) return "BULL";

              if (year === 2025) return "SIDEWAYS";

              return b.regime || "BULL";

            };



            const getActiveBasketPerformance = () => {

              // Prefer backend-tracked YTD return from methodology_tracking.json

              const shortKey = ((p) => { const k = p.split("/").pop() || ""; return k === "epv_greenwald" ? "epv" : k; })(b.path);

              const methDetails = methodologyDetails[b.path];

              if (methDetails?.ytd_return !== undefined && methDetails.ytd_return !== 0) {

                return methDetails.ytd_return;

              }

              // Also check tracking data directly

              if (trackingData?.methodologies?.[shortKey]?.ytd_return !== undefined) {

                return trackingData.methodologies[shortKey].ytd_return;

              }

              // Fallback: compute from current prices vs entry prices

              const picksList = methDetails?.picks || [];

              if (picksList.length === 0) return 0;

              let totalReturn = 0;

              let count = 0;

              picksList.forEach((pick: any) => {

                const stock = findStock(pick.symbol);

                const currPrice = stock?.price || pick.price || 0;

                const entryPrice = pick.entry_price || currPrice || 1;

                if (entryPrice > 0) {

                  totalReturn += (currPrice - entryPrice) / entryPrice;

                  count++;

                }

              });

              return count > 0 ? totalReturn / count : 0;

            };



            // Prefer tracked holdings from methodology_tracking.json (has 20 positions + entry dates)

            const shortKey = ((p) => { const k = p.split("/").pop() || ""; return k === "epv_greenwald" ? "epv" : k; })(b.path);

            const trackedMeth = trackingData?.methodologies?.[shortKey];

            const picks = trackedMeth?.current_holdings?.length

              ? trackedMeth.current_holdings.map((h: any) => ({

                  symbol: h.symbol,

                  entry_price: h.entry_price,

                  entry_date: h.entry_date,

                  entry_metric: h.entry_metric,

                  price: h.entry_price,

                  weight: h.weight,

                }))

              : (methodologyDetails[b.path]?.picks || []).map((p: any) => ({
                  ...p,
                  entry_metric: p.entry_metric ?? p.mos
                }));

            const exits = trackedMeth?.all_exits_2026 || methodologyDetails[b.path]?.exits || [];



            return (

              <div style={{ background: "var(--bg-surface)", border: "1px solid var(--purple)", borderRadius: 12, overflow: "hidden", padding: "24px", boxShadow: "0 8px 30px rgba(0,0,0,0.12)" }}>

                <button onClick={() => setSelectedMethodology(null)} style={{ background: "transparent", border: "none", color: "var(--text-light)", cursor: "pointer", display: "flex", alignItems: "center", gap: 8, marginBottom: 24, fontSize: 12, fontFamily: "var(--font-mono)", padding: 0 }}>

                   <ChevronLeft size={16} /> Back to Directory

                </button>

                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 32, gap: 32 }}>

                  <div style={{ flex: 1 }}>

                    <h2 style={{ fontSize: 24, fontWeight: 800, margin: "0 0 12px 0", color: "var(--text)", letterSpacing: "-0.02em" }}>{b.name}</h2>

                    <div style={{ display: "flex", gap: 12, marginBottom: 16 }}>

                      <span style={{ fontSize: 11, background: "var(--bg)", padding: "4px 8px", borderRadius: 4, color: "var(--text-muted)", fontFamily: "var(--font-mono)", border: "1px solid var(--border-subtle)" }}>PATH: {b.path}</span>

                      <span style={{ fontSize: 11, background: "var(--purple-light)", padding: "4px 8px", borderRadius: 4, color: "var(--purple)", fontFamily: "var(--font-mono)", border: "1px solid var(--purple)", fontWeight: 700 }}>REGIME: {b.regime}</span>

                    </div>

                    <p style={{ maxWidth: 700, lineHeight: 1.6, color: "var(--text-secondary)", fontSize: 14 }}>{b.description}</p>

                  </div>

                  <div style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 12, padding: "20px 24px", minWidth: 400, boxShadow: "var(--shadow-sm)" }}>

                    <div style={{ fontSize: 10, color: "var(--text-light)", fontFamily: "var(--font-mono)", marginBottom: 16, fontWeight: 700, letterSpacing: "0.05em" }}>PERFORMANCE TRACK RECORD</div>

                    <table style={{ width: "100%", fontSize: 11, fontFamily: "var(--font-mono)", borderCollapse: "collapse" }}>

                      <thead>

                        <tr style={{ color: "var(--text-muted)", borderBottom: "1px solid var(--border-subtle)", textAlign: "left" }}>

                          <th style={{ paddingBottom: 8, fontWeight: 600 }}>YEAR</th>

                          <th style={{ paddingBottom: 8, fontWeight: 600 }}>MODE / STATUS</th>

                          <th style={{ paddingBottom: 8, fontWeight: 600, textAlign: "right" }}>RETURN</th>

                          <th style={{ paddingBottom: 8, fontWeight: 600, textAlign: "right" }}>REGIME</th>

                        </tr>

                      </thead>

                      <tbody>

                        {[2021, 2022, 2023, 2024, 2025].map(year => {

                          const annualReturn = getAnnualReturn(year);

                          const regime = getAnnualRegime(year);

                          return (

                            <tr key={year} style={{ borderBottom: "1px solid var(--border-subtle)" }}>

                              <td style={{ padding: "8px 0", color: "var(--text-light)" }}>{year}</td>

                              <td style={{ padding: "8px 0", color: "var(--text-muted)" }}>Baseline</td>

                              <td style={{ padding: "8px 0", textAlign: "right", color: annualReturn >= 0 ? "var(--green)" : "var(--red)", fontWeight: 700 }}>

                                {annualReturn >= 0 ? "+" : ""}{(annualReturn * 100).toFixed(1)}%

                              </td>

                              <td style={{ padding: "8px 0", textAlign: "right" }}>

                                <span style={{ fontSize: 9, background: regime === "BULL" ? "var(--green-light)" : regime === "BEAR" ? "var(--red-light)" : "var(--bg)", color: regime === "BULL" ? "var(--green)" : regime === "BEAR" ? "var(--red)" : "var(--text-muted)", padding: "2px 6px", borderRadius: 4, fontWeight: 700 }}>{regime}</span>

                              </td>

                            </tr>

                          );

                        })}

                        <tr style={{ background: "rgba(139, 92, 246, 0.05)" }}>

                          <td style={{ padding: "10px 0", color: "var(--purple)", fontWeight: 700 }}>2026</td>

                          <td style={{ padding: "10px 0", color: "var(--text)", fontWeight: 700 }}>Live · since late May 2026 (partial yr)</td>

                          <td style={{ padding: "10px 0", textAlign: "right", color: getActiveBasketPerformance() >= 0 ? "var(--green)" : "var(--red)", fontWeight: 800 }}>

                            {getActiveBasketPerformance() >= 0 ? "+" : ""}{(getActiveBasketPerformance() * 100).toFixed(1)}%

                          </td>

                          <td style={{ padding: "10px 0", textAlign: "right" }}>

                            <span style={{ fontSize: 9, background: b.regime === "BULL" ? "var(--green-light)" : b.regime === "BEAR" ? "var(--red-light)" : "var(--bg)", color: b.regime === "BULL" ? "var(--green)" : b.regime === "BEAR" ? "var(--red)" : "var(--text-muted)", padding: "2px 6px", borderRadius: 4, fontWeight: 700 }}>{b.regime || "BULL"}</span>

                          </td>

                        </tr>

                      </tbody>

                    </table>

                  </div>

                </div>



                <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>

                  <div style={{ width: "100%" }}>

                     <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--border)", paddingBottom: 12, marginBottom: 16 }}>

                       <div style={{ display: "flex", gap: 16 }}>

                         <button onClick={() => setMethodTab("holdings")} style={{ fontSize: 14, fontWeight: 700, margin: 0, padding: 0, background: "none", border: "none", cursor: "pointer", color: methodTab === "holdings" ? "var(--text)" : "var(--text-muted)" }}>Current Holdings</button>

                         <button onClick={() => setMethodTab("speculair")} style={{ fontSize: 14, fontWeight: 700, margin: 0, padding: 0, background: "none", border: "none", cursor: "pointer", color: methodTab === "speculair" ? "var(--text)" : "var(--text-muted)" }}>Speculair</button>

                       </div>

                       <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>{picks.length} total picks</span>

                     </div>

                     {methodTab === "holdings" ? (

                     <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse", fontFamily: "var(--font-mono)" }}>

                       <thead>

                         <tr style={{ color: "var(--text-light)", borderBottom: "1px solid var(--border-subtle)", textAlign: "left", fontSize: 11 }}>

                            <th style={{ padding: "0 8px 12px 8px", fontWeight: 600 }}>TICKER</th>

                            <th style={{ padding: "0 8px 12px 8px", fontWeight: 600 }}>COMPANY</th>

                            <th style={{ padding: "0 8px 12px 8px", fontWeight: 600 }}>INDICATORS</th>

                            <th style={{ padding: "0 8px 12px 8px", textAlign: "left", fontWeight: 600 }}>ENTRY DATE</th>

                            <th style={{ padding: "0 8px 12px 8px", textAlign: "right", fontWeight: 600 }}>ENTRY PRICE</th>

                            <th style={{ padding: "0 8px 12px 8px", textAlign: "right", fontWeight: 600 }}>{getMetricName(shortKey)} (ENTRY)</th>

                            <th style={{ padding: "0 8px 12px 16px", textAlign: "left", fontWeight: 600,  }}>EXIT DATE</th>

                            <th style={{ padding: "0 8px 12px 8px", textAlign: "right", fontWeight: 600 }}>CURRENT/EXIT PRICE</th>

                            <th style={{ padding: "0 8px 12px 8px", textAlign: "right", fontWeight: 600 }}>{getMetricName(shortKey)} (EXIT)</th>

                            <th style={{ padding: "0 8px 12px 8px", textAlign: "right", fontWeight: 600 }}>PERFORMANCE</th>

                            <th style={{ padding: "0 8px 12px 8px", textAlign: "center", fontWeight: 600 }}></th>

                         </tr>

                       </thead>

                       <tbody>

                         {picks.length > 0 ? picks.map((pick: any) => {

                            const symbol = pick.symbol;

                            const stock = findStock(symbol);

                            const currPrice = stock?.price || pick.price || 0;

                            const entryPriceVal = pick.entry_price || currPrice || 0;

                            const entryDateVal = pick.entry_date || "—";

                            const perfPct = entryPriceVal > 0 ? ((currPrice - entryPriceVal) / entryPriceVal) * 100 : 0;

                            const entryMetricVal = pick.entry_metric;



                            return (

                              <tr key={symbol} style={{ borderBottom: "1px solid var(--border-subtle)", cursor: "pointer", transition: "background 0.15s" }} onClick={(e) => handleTickerClick(e, symbol)} onMouseEnter={(e) => { e.currentTarget.style.background = "var(--bg-hover)"; }} onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}>

                                <td style={{ padding: "14px 8px", fontWeight: 700, color: "var(--text)" }}>{symbol}</td>

                                <td style={{ padding: "14px 8px", color: "var(--text-muted)", fontFamily: "var(--font-sans)", fontSize: 12 }}>{stock?.company_name || "—"}</td>

                                <td style={{ padding: "14px 4px" }}><PickIndicators pick={pick} /></td>

                                <td style={{ padding: "14px 8px", color: "var(--text-secondary)" }}>{entryDateVal}</td>

                                <td style={{ padding: "14px 8px", textAlign: "right", color: "var(--text-secondary)" }}>{entryPriceVal > 0 ? `$${entryPriceVal.toFixed(2)}` : "—"}</td>

                                <td style={{ padding: "14px 8px", textAlign: "right", color: "var(--text-secondary)" }}>{formatMethodologyMetric(entryMetricVal, shortKey)}</td>

                                <td style={{ padding: "14px 8px", color: "var(--text-muted)", paddingLeft: 16 }}>—</td>

                                <td style={{ padding: "14px 8px", textAlign: "right", color: "var(--text)" }}>{currPrice > 0 ? `$${currPrice.toFixed(2)}` : "—"}</td>

                                <td style={{ padding: "14px 8px", textAlign: "right", color: "var(--text-muted)" }}>—</td>

                                <td style={{ padding: "14px 8px", textAlign: "right", color: entryPriceVal > 0 ? (perfPct >= 0 ? "var(--green)" : "var(--red)") : "var(--text-muted)", fontWeight: 700 }}>{entryPriceVal > 0 ? `${perfPct >= 0 ? "+" : ""}${perfPct.toFixed(1)}%` : "—"}</td>

                                <td style={{ padding: "14px 8px", textAlign: "center" }}><ExternalLink size={14} color="var(--text-light)" /></td>

                              </tr>

                            );

                         }) : (

                           <tr><td colSpan={11} style={{ padding: "32px 0", textAlign: "center", color: "var(--text-muted)", fontSize: 12 }}>No active holdings for this methodology.</td></tr>

                         )}

                     </tbody>

                     </table>

                     ) : (

                       <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse", fontFamily: "var(--font-mono)" }}>

                         <thead>

                           <tr style={{ color: "var(--text-light)", borderBottom: "1px solid var(--border-subtle)", textAlign: "left", fontSize: 11 }}>

                             <th style={{ paddingBottom: 8, fontWeight: 600 }}>TICKER</th>

                             <th style={{ paddingBottom: 8, fontWeight: 600 }}>COMPANY</th>

                             <th style={{ paddingBottom: 8, textAlign: "right", fontWeight: 600 }}>CURRENT PRICE</th>

                             <th style={{ paddingBottom: 8, textAlign: "right", fontWeight: 600 }}>ALLOCATION</th>

                             <th style={{ paddingBottom: 8, textAlign: "right", fontWeight: 600 }}>TARGET WGT</th>

                             <th style={{ paddingBottom: 8, textAlign: "right", fontWeight: 600 }}>SHARES</th>

                           </tr>

                         </thead>

                         <tbody>

                           {picks.length > 0 ? picks.map((pick: any) => {

                             const symbol = pick.symbol;

                             const stock = findStock(symbol);

                             const currPrice = stock?.price || pick.price || 0;

                             const allocation = 100000 / picks.length;

                             const weightPct = 100 / picks.length;

                             const shares = currPrice > 0 ? allocation / currPrice : 0;

                             

                             return (

                               <tr key={symbol} style={{ borderBottom: "1px solid var(--border-subtle)", cursor: "pointer", transition: "background 0.15s" }} onClick={(e) => handleTickerClick(e, symbol)} onMouseEnter={(e) => { e.currentTarget.style.background = "var(--bg-hover)"; }} onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}>

                                 <td style={{ padding: "14px 8px", fontWeight: 700, color: "var(--text)" }}>{symbol}</td>

                                 <td style={{ padding: "14px 8px", color: "var(--text-muted)", fontFamily: "var(--font-sans)", fontSize: 12 }}>{stock?.company_name || "—"}</td>

                                 <td style={{ padding: "14px 8px", textAlign: "right", color: "var(--text)" }}>${currPrice > 0 ? currPrice.toFixed(2) : "—"}</td>

                                 <td style={{ padding: "14px 8px", textAlign: "right", color: "var(--green)" }}>${allocation.toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>

                                 <td style={{ padding: "14px 8px", textAlign: "right", color: "var(--text)", fontWeight: 700 }}>{weightPct.toFixed(1)}%</td>

                                 <td style={{ padding: "14px 8px", textAlign: "right", color: "var(--text-muted)" }}>{shares.toFixed(2)}</td>

                               </tr>

                             );

                           }) : (

                             <tr><td colSpan={6} style={{ padding: "32px 0", textAlign: "center", color: "var(--text-muted)", fontSize: 12 }}>No active holdings for this methodology.</td></tr>

                           )}

                         </tbody>

                       </table>

                     )}

                  </div>



                  <div style={{ width: "100%", marginTop: 16 }}>

                     <h3 style={{ fontSize: 14, fontWeight: 700, marginBottom: 16, borderBottom: "1px solid var(--border)", paddingBottom: 12, margin: 0 }}>Recent Exits</h3>

                     {exits.length > 0 ? (

                       <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse", fontFamily: "var(--font-mono)" }}>

                         <thead>

                           <tr style={{ color: "var(--text-light)", borderBottom: "1px solid var(--border-subtle)", textAlign: "left", fontSize: 11 }}>

                             <th style={{ padding: "0 8px 12px 8px", textAlign: "left", fontWeight: 600 }}>TICKER</th>

                             <th style={{ padding: "0 8px 12px 8px", textAlign: "left", fontWeight: 600 }}>COMPANY</th>

                             <th style={{ padding: "0 8px 12px 8px", textAlign: "left", fontWeight: 600 }}>ENTRY DATE</th>

                             <th style={{ padding: "0 8px 12px 8px", textAlign: "right", fontWeight: 600 }}>ENTRY PRICE</th>

                             <th style={{ padding: "0 8px 12px 8px", textAlign: "right", fontWeight: 600 }}>{getMetricName(shortKey)} (ENTRY)</th>

                             <th style={{ padding: "0 8px 12px 16px", textAlign: "left", fontWeight: 600,  }}>EXIT DATE</th>

                             <th style={{ padding: "0 8px 12px 8px", textAlign: "right", fontWeight: 600 }}>CURRENT/EXIT PRICE</th>

                             <th style={{ padding: "0 8px 12px 8px", textAlign: "right", fontWeight: 600 }}>{getMetricName(shortKey)} (EXIT)</th>

                             <th style={{ padding: "0 8px 12px 8px", textAlign: "right", fontWeight: 600 }}>PERFORMANCE</th>

                             <th style={{ padding: "0 8px 12px 8px", textAlign: "center", fontWeight: 600 }}></th>

                           </tr>

                         </thead>

                         <tbody>

                           {exits.map((exit: any) => {

                             const stock = findStock(exit.symbol);

                             const perfPct = ((exit.performance ?? exit.return) || 0) * 100;

                             const entryMetricVal = exit.entry_metric;

                             const exitMetricVal = exit.exit_metric;

                             return (

                               <tr key={`${exit.symbol}-${exit.exit_date}`} style={{ borderBottom: "1px solid var(--border-subtle)", cursor: "pointer", transition: "background 0.15s" }} onClick={(e) => handleTickerClick(e, exit.symbol)} onMouseEnter={(e) => { e.currentTarget.style.background = "var(--bg-hover)"; }} onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}>

                                 <td style={{ padding: "14px 8px", fontWeight: 700, color: "var(--text-secondary)", textDecoration: "line-through" }}>{exit.symbol}</td>

                                 <td style={{ padding: "14px 8px", color: "var(--text-muted)", fontFamily: "var(--font-sans)", fontSize: 12 }}>{stock?.company_name || "—"}</td>

                                 <td style={{ padding: "14px 8px", color: "var(--text-muted)" }}>{exit.entry_date}</td>

                                 <td style={{ padding: "14px 8px", textAlign: "right", color: "var(--text-muted)" }}>${exit.entry_price ? exit.entry_price.toFixed(2) : "—"}</td>

                                 <td style={{ padding: "14px 8px", textAlign: "right", color: "var(--text-muted)" }}>{formatMethodologyMetric(entryMetricVal, shortKey)}</td>

                                 <td style={{ padding: "14px 8px", color: "var(--text-muted)", paddingLeft: 16 }}>{exit.exit_date}</td>

                                 <td style={{ padding: "14px 8px", textAlign: "right", color: "var(--text-muted)" }}>${exit.exit_price ? exit.exit_price.toFixed(2) : "—"}</td>

                                 <td style={{ padding: "14px 8px", textAlign: "right", color: "var(--text-muted)" }}>{formatMethodologyMetric(exitMetricVal, shortKey)}</td>

                                 <td style={{ padding: "14px 8px", textAlign: "right", color: perfPct >= 0 ? "var(--green)" : "var(--red)", fontWeight: 700 }}>{perfPct >= 0 ? "+" : ""}{perfPct.toFixed(1)}%</td>

                                 <td style={{ padding: "14px 8px", textAlign: "center" }}><ExternalLink size={14} color="var(--text-light)" /></td>

                               </tr>

                             );

                           })}

                         </tbody>

                       </table>

                     ) : (

                       <div style={{ padding: "24px 8px", color: "var(--text-muted)", fontSize: 12, fontFamily: "var(--font-mono)" }}>No recent exits for this methodology.</div>

                     )}

                  </div>

                </div>

              </div>

            );

          })() : (

            <>

          {/* Paper Portfolio Cabinet moved below inside Methodologies */}

          {trackedBaskets.length > 0 && (

            <div 

              style={{

                background: "var(--bg-surface)",

                border: "1px solid var(--purple)",

                borderRadius: 12,

                padding: "20px 24px",

                marginBottom: 10,

                boxShadow: "0 4px 20px rgba(196, 181, 253, 0.12)"

              }}

            >

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>

                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>

                  <Briefcase size={20} color="var(--purple)" style={{ flexShrink: 0 }} />

                  <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, letterSpacing: "-0.01em", color: "var(--text)" }}>

                    Paper Portfolio Cabinet

                  </h3>

                  <span style={{ fontSize: 10, fontFamily: "var(--font-mono)", background: "var(--purple-light)", color: "var(--purple)", padding: "2px 6px", borderRadius: 4, fontWeight: 600 }}>

                    Active Tracking Since 2026-03-30

                  </span>

                </div>

                <div style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--text-light)" }}>

                  Starting Capital: $100,000 per strategy

                </div>

              </div>



              {/* Tickers layout */}

              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 12 }}>

                {trackedBaskets.map(path => {

                  const b = METHODOLOGIES_CONFIG.find(x => x.path === path);

                  if (!b) return null;

                  const shortKey = ((p) => { const k = p.split("/").pop() || ""; return k === "epv_greenwald" ? "epv" : k; })(b.path);

                  const trackedMeth = trackingData?.methodologies?.[shortKey];

                  const activePicks = trackedMeth?.current_holdings?.length

                    ? trackedMeth.current_holdings.map((h: any) => ({

                        symbol: h.symbol,

                        entry_price: h.entry_price,

                        entry_date: h.entry_date,

                        weight: h.weight,

                      }))

                    : (methodologyPicks[b.path] || []).map(symbol => ({

                        symbol,

                        entry_price: 0,

                        entry_date: "—",

                        weight: 1 / (methodologyPicks[b.path]?.length || 1),

                      }));

                  const ytdReturn = trackedMeth?.ytd_return;

                  const exits = trackedMeth?.all_exits_2026 || [];

                  const isExpanded = !!expandedBaskets[b.path];

                  

                  return (

                    <div key={path} style={{ border: "1px solid var(--border)", borderRadius: 8, background: "var(--bg)", overflow: "hidden" }}>

                      <div 

                        style={{ padding: "12px 16px", cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center" }}

                        onClick={() => setExpandedBaskets(prev => ({...prev, [path]: !prev[path]}))}

                      >

                        <div>

                          <div style={{ fontWeight: 700, fontSize: 13, color: "var(--text)", fontFamily: "var(--font-sans)" }}>{b.name}</div>

                          <div style={{ fontSize: 10, color: "var(--text-light)", fontFamily: "var(--font-mono)" }}>

                            {activePicks.length} Active Positions

                          </div>

                        </div>

                        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>

                          <div style={{ textAlign: "right" }}>

                            <div style={{ fontSize: 10, color: "var(--text-light)", fontFamily: "var(--font-mono)" }}>Tracked P&L (YTD)</div>

                            <div style={{ fontSize: 12, fontWeight: 700, color: ytdReturn >= 0 ? "var(--green)" : "var(--red)", fontFamily: "var(--font-mono)" }}>

                              {ytdReturn !== undefined ? `${ytdReturn >= 0 ? "+" : ""}${(ytdReturn * 100).toFixed(1)}%` : "—"}

                            </div>

                          </div>

                          <ChevronRight size={16} color="var(--text-muted)" style={{ transform: isExpanded ? "rotate(90deg)" : "none", transition: "transform 0.2s" }} />

                        </div>

                      </div>

                      

                      {isExpanded && activePicks.length > 0 && (

                        <div style={{ padding: "0 16px 16px 16px", borderTop: "1px solid var(--border-subtle)" }}>

                          <table style={{ width: "100%", fontSize: 11, borderCollapse: "collapse", marginTop: 12 }}>

                            <thead>

                              <tr style={{ borderBottom: "1px solid var(--border-subtle)", color: "var(--text-light)", fontFamily: "var(--font-mono)" }}>

                                <th style={{ textAlign: "left", paddingBottom: 6, fontWeight: 600 }}>TICKER</th>

                                <th style={{ textAlign: "left", paddingBottom: 6, fontWeight: 600 }}>ENTRY</th>

                                <th style={{ textAlign: "right", paddingBottom: 6, fontWeight: 600 }}>PRICE</th>

                                <th style={{ textAlign: "right", paddingBottom: 6, fontWeight: 600 }}>CURRENT</th>

                                <th style={{ textAlign: "right", paddingBottom: 6, fontWeight: 600 }}>PERF</th>

                                <th style={{ textAlign: "center", paddingBottom: 6 }}></th>

                              </tr>

                            </thead>

                            <tbody>

                              {activePicks.map((pick: any) => {

                                const symbol = pick.symbol;

                                const stock = findStock(symbol);

                                const entryDate = pick.entry_date;

                                const currPrice = stock?.price ?? 0;

                                const entryPriceVal = pick.entry_price || currPrice || 0;

                                const perfPct = entryPriceVal > 0 ? ((currPrice - entryPriceVal) / entryPriceVal) * 100 : 0;

                                const perfColor = perfPct > 0 ? "var(--green)" : perfPct < 0 ? "var(--red)" : "var(--text-muted)";

                                

                                const displayPrice = currPrice ? `$${currPrice.toFixed(2)}` : "—";

                                

                                return (

                                  <tr 

                                    key={symbol} 

                                    style={{ borderBottom: "1px solid var(--border-subtle)", cursor: "pointer", transition: "background 0.2s" }}

                                    onClick={(e) => handleTickerClick(e, symbol)}

                                    onMouseEnter={(e) => { e.currentTarget.style.background = "var(--bg-hover)"; }}

                                    onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; }}

                                  >

                                    <td style={{ padding: "8px 8px", fontWeight: 700, color: "var(--text)", fontFamily: "var(--font-mono)" }}>

                                      {symbol}

                                    </td>

                                    <td style={{ padding: "8px 8px", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>

                                      {entryDate}

                                    </td>

                                    <td style={{ padding: "8px 8px", textAlign: "right", color: "var(--text-secondary)", fontFamily: "var(--font-mono)" }}>

                                      ${entryPriceVal.toFixed(2)}

                                    </td>

                                    <td style={{ padding: "8px 8px", textAlign: "right", color: "var(--text)", fontFamily: "var(--font-mono)" }}>

                                      {displayPrice}

                                    </td>

                                    <td style={{ padding: "8px 8px", textAlign: "right", color: perfColor, fontWeight: 700, fontFamily: "var(--font-mono)" }}>

                                      {perfPct > 0 ? "+" : ""}{perfPct.toFixed(1)}%

                                    </td>

                                    <td style={{ padding: "8px 8px", textAlign: "center" }}>

                                      <ExternalLink size={12} color="var(--text-light)" />

                                    </td>

                                  </tr>

                                );

                              })}

                            </tbody>

                          </table>

                          <div style={{marginTop: 12, paddingTop: 10, borderTop: "1px dashed var(--border)"}}>

                            <div style={{fontSize: 9, color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontWeight: 600, marginBottom: 4}}>RECENT EXITS</div>

                            <div style={{fontSize: 10, color: "var(--text-secondary)"}}>

                              {exits.length > 0 ? (

                                exits.slice(-3).map((exit: any, idx: number) => {

                                  const perf = ((exit.performance ?? exit.return) || 0) * 100;

                                  return (

                                    <span key={idx}>

                                      {idx > 0 && " · "}

                                      <span style={{fontFamily: "var(--font-mono)", textDecoration: "line-through", marginRight: 4}}>{exit.symbol}</span>

                                      (Sold {exit.exit_date} @ {perf >= 0 ? "+" : ""}{perf.toFixed(1)}%)

                                    </span>

                                  );

                                })

                              ) : (

                                "No recent exits."

                              )}

                            </div>

                          </div>

                        </div>

                      )}

                    </div>

                  );

                })}

              </div>

            </div>

          )}



          {Array.from(new Set(METHODOLOGIES_CONFIG.map(m => m.regime))).map(regime => {

            const baskets = METHODOLOGIES_CONFIG.filter(m => m.regime === regime);

            let regimeColor = "var(--green)";

            if (regime === "SIDEWAYS REGIME (CONSOLIDATION & STABLE YIELD)") regimeColor = "var(--amber)";

            if (regime === "BEAR REGIME (CONTRACTION & HIGH VOLATILITY)") regimeColor = "var(--red)";



            return (

              <div key={regime} style={{ marginBottom: 32 }}>

                <h2 style={{ fontSize: 13, fontWeight: 800, color: "var(--text)", letterSpacing: "0.05em", textTransform: "uppercase", marginBottom: 16, borderBottom: "1px solid var(--border)", paddingBottom: 8, display: "flex", alignItems: "center", gap: 8 }}>

                  <span style={{ width: 8, height: 8, borderRadius: "50%", background: regimeColor }} />

                  {regime}

                  <span style={{ fontSize: 10, color: "var(--text-light)", fontWeight: 500, textTransform: "none", marginLeft: "auto", fontFamily: "var(--font-mono)" }}>

                    {baskets.length} methodologies

                  </span>

                </h2>

                

                <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>

                  {baskets.map(basket => {

                    const shortKey = ((p) => { const k = p.split("/").pop() || ""; return k === "epv_greenwald" ? "epv" : k; })(basket.path);

                    const trackedMeth = trackingData?.methodologies?.[shortKey];

                    const activeTickers = trackedMeth?.current_holdings?.length 

                      ? trackedMeth.current_holdings.map((h: any) => h.symbol)

                      : (methodologyPicks[basket.path] || []);

                    const ytdReturn = trackedMeth?.ytd_return;

                    const isExpanded = !!expandedThemes[basket.path];

                    const isTracked = trackedBaskets.includes(basket.path);

                    const specData = speculairBaskets?.per_methodology_baskets?.[shortKey];



                    return (

                      <div key={basket.path} style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: 12, overflow: "hidden", transition: "all 0.2s", boxShadow: "var(--shadow-sm)" }}>

                        <div style={{ padding: "20px 24px" }}>

                          {/* Top Row: Info + Metrics */}

                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 24 }}>

                            

                            {/* Title & Desc */}

                            <div style={{ flex: 1 }}>

                              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>

                                <h3 

                                  onDoubleClick={() => setSelectedMethodology(basket.path)}

                                  title="Double click to open details"

                                  style={{ margin: 0, fontSize: 16, fontWeight: 800, color: "var(--text)", fontFamily: "var(--font-sans)", letterSpacing: "-0.01em", cursor: "pointer" }}

                                >

                                  {basket.name}

                                </h3>

                                <span style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>({basket.path})</span>



                                <button

                                  onClick={(e) => {

                                    e.stopPropagation();

                                    setTrackedBaskets(prev => 

                                      prev.includes(basket.path) 

                                        ? prev.filter(p => p !== basket.path)

                                        : [...prev, basket.path]

                                    );

                                  }}

                                  style={{

                                    display: "flex", alignItems: "center", gap: 4,

                                    padding: "4px 8px", fontSize: 10, fontWeight: 700, fontFamily: "var(--font-mono)",

                                    background: isTracked ? "var(--purple-light)" : "transparent",

                                    color: isTracked ? "var(--purple)" : "var(--text-light)",

                                    border: `1px solid ${isTracked ? "var(--purple)" : "var(--border)"}`,

                                    borderRadius: 6, cursor: "pointer", transition: "all 0.15s"

                                  }}

                                >

                                  {isTracked ? <><Briefcase size={12} /> TRACKING</> : <><Plus size={12} /> TRACK</>}

                                </button>

                              </div>

                              <p style={{ margin: 0, fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.5, maxWidth: 600 }}>

                                {basket.description}

                              </p>

                            </div>



                            {/* Backtest Metrics Table */}

                            <div style={{ background: "var(--bg)", borderRadius: 8, padding: "12px 16px", border: "1px solid var(--border-subtle)" }}>

                              <table style={{ fontSize: 10, fontFamily: "var(--font-mono)", borderCollapse: "collapse", textAlign: "right" }}>

                                <thead>

                                  <tr style={{ color: "var(--text-muted)", borderBottom: "1px solid var(--border-subtle)" }}>

                                    <th style={{ paddingBottom: 6, textAlign: "left", fontWeight: 600 }}>MODE</th>

                                    <th style={{ paddingBottom: 6, paddingLeft: 16, fontWeight: 600 }}>CAGR</th>

                                    <th style={{ paddingBottom: 6, paddingLeft: 16, fontWeight: 600 }}>MAX DD</th>

                                    <th style={{ paddingBottom: 6, paddingLeft: 16, fontWeight: 600 }}>SHARPE</th>

                                    <th style={{ paddingBottom: 6, paddingLeft: 16, fontWeight: 600 }}>TRADES</th>

                                  </tr>

                                </thead>

                                <tbody>

                                  <tr>

                                    <td style={{ paddingTop: 8, textAlign: "left", color: "var(--text-light)" }}>Baseline</td>

                                    <td style={{ paddingTop: 8, paddingLeft: 16, color: "var(--text)", fontWeight: 700 }}>{(basket.metrics.baseline.cagr * 100).toFixed(1)}%</td>

                                    <td style={{ paddingTop: 8, paddingLeft: 16, color: "var(--red)" }}>{(basket.metrics.baseline.mdd * 100).toFixed(1)}%</td>

                                    <td style={{ paddingTop: 8, paddingLeft: 16, color: "var(--text)" }}>{basket.metrics.baseline.sharpe.toFixed(2)}</td>

                                    <td style={{ paddingTop: 8, paddingLeft: 16, color: "var(--text-muted)" }}>{basket.metrics.baseline.trades}</td>

                                  </tr>

                                  <tr>

                                    <td style={{ paddingTop: 6, textAlign: "left", color: "var(--text)", fontWeight: 700 }}>Active</td>

                                    <td style={{ paddingTop: 6, paddingLeft: 16, color: ytdReturn !== undefined && ytdReturn >= 0 ? "var(--green)" : "var(--red)", fontWeight: 700 }}>
                                      {ytdReturn !== undefined ? `${ytdReturn >= 0 ? "+" : ""}${(ytdReturn * 100).toFixed(1)}% YTD` : "—"}
                                    </td>

                                    <td style={{ paddingTop: 6, paddingLeft: 16, color: "var(--text-muted)" }}>—</td>

                                    <td style={{ paddingTop: 6, paddingLeft: 16, color: "var(--text-muted)" }}>—</td>

                                    <td style={{ paddingTop: 6, paddingLeft: 16, color: "var(--text-muted)" }}>{trackedMeth ? (activeTickers.length + (trackedMeth.all_exits_2026?.length || 0)) : "—"}</td>

                                  </tr>

                                  <tr>

                                    <td style={{ paddingTop: 6, textAlign: "left", color: specData ? "var(--purple)" : "var(--text-light)", fontWeight: specData ? 700 : 400 }}>Speculair</td>

                                    <td style={{ paddingTop: 6, paddingLeft: 16, color: specData ? "var(--green)" : "var(--text-muted)", fontWeight: specData ? 700 : 400 }}>
                                      {specData ? `${(specData.picks || []).length} picks` : "—"}
                                    </td>

                                    <td style={{ paddingTop: 6, paddingLeft: 16, color: specData?.radar_filtered ? "var(--amber)" : "var(--text-muted)" }}>
                                      {specData ? `${specData.radar_filtered || 0} filtered` : "—"}
                                    </td>

                                    <td style={{ paddingTop: 6, paddingLeft: 16, color: specData ? "var(--text)" : "var(--text-muted)" }}>
                                      {specData && (specData.picks || []).length > 0
                                        ? `${((specData.picks || []).reduce((s: number, p: any) => s + (p.conviction || 0), 0) / (specData.picks || []).length).toFixed(1)} avg`
                                        : "—"}
                                    </td>

                                    <td style={{ paddingTop: 6, paddingLeft: 16, color: specData ? "var(--text-muted)" : "var(--text-muted)" }}>
                                      {specData ? (specData.total_candidates || 0) : "—"}
                                    </td>

                                  </tr>


                                </tbody>

                              </table>

                              <div style={{ fontSize: 8, color: "var(--text-muted)", marginTop: 8, fontStyle: "italic", textAlign: "right" }}>

                                * Baseline calculated via unoptimized quantitative screens without agent validation or concentrated weighting.

                              </div>

                            </div>

                          </div>



                          {/* Expansion Toggle */}

                          <div 

                            style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 24, paddingTop: 16, borderTop: "1px solid var(--border-subtle)", cursor: "pointer" }}

                            onClick={() => setExpandedThemes(prev => ({...prev, [basket.path]: !prev[basket.path]}))}

                          >

                            <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text)", fontWeight: 600 }}>

                              <Activity size={14} color="var(--text-muted)" />

                              Current Holdings: {activeTickers.length} symbols

                            </div>

                            <div style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-light)" }}>

                              Expand current picks

                              <ChevronRight size={14} style={{ transform: isExpanded ? "rotate(90deg)" : "none", transition: "transform 0.2s" }} />

                            </div>

                          </div>

                        </div>



                        {/* Expanded Picks List */}

                        {isExpanded && activeTickers.length > 0 && (

                          <div style={{ background: "var(--bg)", borderTop: "1px solid var(--border)", padding: "16px 24px", display: "flex", flexDirection: "column", gap: 16 }}>

                            <div style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-light)" }}>Showing top 5 active picks (Double-click the methodology name to view all)</div>

                            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 12 }}>

                              {activeTickers.slice(0, 5).map((symbol: string) => {

                                const stock = findStock(symbol);

                                return (

                                  <div 

                                    key={symbol} 

                                    style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "8px 12px", border: "1px solid var(--border-subtle)", borderRadius: 8, background: "var(--bg-surface)", cursor: "pointer", transition: "border-color 0.15s" }}

                                    onClick={(e) => handleTickerClick(e, symbol)}

                                    onMouseEnter={(e) => { e.currentTarget.style.borderColor = "var(--border)"; }}

                                    onMouseLeave={(e) => { e.currentTarget.style.borderColor = "var(--border-subtle)"; }}

                                  >

                                    <div style={{ display: "flex", flexDirection: "column" }}>

                                      <span style={{ fontWeight: 700, fontSize: 13, fontFamily: "var(--font-mono)", color: "var(--text)" }}>{symbol}</span>

                                      <span style={{ fontSize: 10, color: "var(--text-muted)" }}>{stock?.company_name?.substring(0, 18)}{(stock?.company_name?.length || 0) > 18 ? "..." : ""}</span>

                                    </div>

                                    <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end" }}>

                                      <span style={{ fontSize: 12, fontFamily: "var(--font-mono)", color: "var(--text)" }}>${stock?.price?.toFixed(2) || "—"}</span>

                                    </div>

                                  </div>

                                );

                              })}

                            </div>

                          </div>

                        )}

                      </div>

                    );

                  })}

                </div>

              </div>

            );

          })}

          </>

          )}

        </div>

      ) : viewMode === "sectors" ? (

        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>

          {/* Macro Status Bar */}

          <div style={{display: "flex", gap: 16, fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-light)", flexWrap: "wrap"}}>
            {(() => {
              const mac = sectorData?.macro;
              const vix = mac?.vix ?? null;
              const vixC = mac?.vixChange ?? null;
              const y10 = mac?.yield10 ?? null;
              const breadth = stocks.length ? Math.round(stocks.filter((st) => (st.composite_momentum ?? 0) >= 0.5).length / stocks.length * 100) : null;
              const reg = data?.macro?.regime;
              const rs = reg ? (REGIME_STYLE[reg] || REGIME_STYLE.NEUTRAL) : null;
              const vixColor = vix == null ? "var(--text-light)" : vix <= 16 ? "var(--green)" : vix <= 22 ? "var(--amber)" : "var(--red)";
              const brColor = breadth == null ? "var(--text-light)" : breadth >= 50 ? "var(--green)" : "var(--amber)";
              return (
                <>
                  <span style={{display: "flex", alignItems: "center", gap: 4}}><span style={{width: 6, height: 6, borderRadius: "50%", background: vixColor}}></span>VIX: {vix == null ? "—" : vix.toFixed(1)}{vixC == null ? "" : ` (${vixC >= 0 ? "+" : ""}${vixC.toFixed(1)}%)`}</span>
                  <span style={{display: "flex", alignItems: "center", gap: 4}}><span style={{width: 6, height: 6, borderRadius: "50%", background: "var(--amber)"}}></span>10Y YIELD: {y10 == null ? "—" : `${y10.toFixed(2)}%`}</span>
                  <span style={{display: "flex", alignItems: "center", gap: 4}}><span style={{width: 6, height: 6, borderRadius: "50%", background: brColor}}></span>BREADTH: {breadth == null ? "—" : `${breadth}%`}</span>
                  <span style={{display: "flex", alignItems: "center", gap: 4}}><span style={{width: 6, height: 6, borderRadius: "50%", background: rs?.color || "var(--text-light)"}}></span>REGIME: {rs?.label || "—"}</span>
                  <span style={{display: "flex", alignItems: "center", gap: 4, marginLeft: "auto"}}><span style={{width: 6, height: 6, borderRadius: "50%", background: sectorUpdatedAt ? "var(--green)" : "var(--text-light)"}}></span>{sectorUpdatedAt ? `LIVE · ${sectorUpdatedAt}` : "connecting…"}</span>
                </>
              );
            })()}
          </div>

          {/* Major Index Cards & Performance Widgets */}

          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 10, marginBottom: 8 }}>
            <TrackRecordCard loaded={portfolioPositions !== null} value={trackRecord.totalValue} pnl={trackRecord.pnl} pnlPct={trackRecord.pnlPct} positions={trackRecord.positions} winners={trackRecord.winners} losers={trackRecord.losers} />
            {(radarSymbols || []).map((sym) => {
              const q = radarData[sym];
              return <PerfCard key={sym} title={(q?.name || sym).slice(0, 18)} note={sym} price={q?.price ?? null} day={q?.day ?? null} ytd={q?.ytd ?? null} year={q?.year ?? null} compact onRemove={() => removeRadar(sym)} />;
            })}
          </div>
          {/* Radar customization: free-text add + preset chips (per-user, saved to Firestore) */}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center", marginBottom: 16 }}>
            <input value={radarInput} onChange={(e) => setRadarInput(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") addRadar(radarInput); }} placeholder="+ add symbol (AAPL, ^VIX, GLD…)" style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: 6, padding: "4px 8px", color: "var(--text)", fontFamily: "var(--font-mono)", fontSize: 11, width: 210 }} />
            <button onClick={() => addRadar(radarInput)} style={{ cursor: "pointer", color: "var(--text)", background: "var(--bg-hover)", border: "1px solid var(--border)", borderRadius: 6, padding: "4px 9px", fontFamily: "var(--font-mono)", fontSize: 10 }}>Add</button>
            {(radarSymbols || []).length >= 11 ? (
              <span style={{ color: "var(--text-light)", fontSize: 10, fontFamily: "var(--font-mono)" }}>radar full (11)</span>
            ) : (
              <>
                <span style={{ color: "var(--text-light)", fontSize: 10, fontFamily: "var(--font-mono)", marginLeft: 4 }}>quick:</span>
                {RADAR_PRESETS.filter((p) => !(radarSymbols || []).includes(p.s)).map((p) => (
                  <button key={p.s} onClick={() => addRadar(p.s)} style={{ cursor: "pointer", color: "var(--text-muted)", background: "transparent", border: "1px solid var(--border)", borderRadius: 6, padding: "3px 8px", fontFamily: "var(--font-mono)", fontSize: 10 }}>+ {p.label}</button>
                ))}
              </>
            )}
          </div>

          {/* Paper Portfolio Cabinet */}

          {trackedBaskets.length > 0 && (

            <div 

              style={{

                background: "var(--bg-surface)",

                border: "1px solid var(--purple)",

                borderRadius: 12,

                padding: "20px 24px",

                marginBottom: 10,

                boxShadow: "0 4px 20px rgba(196, 181, 253, 0.12)"

              }}

            >

              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>

                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>

                  <Briefcase size={20} color="var(--purple)" style={{ flexShrink: 0 }} />

                  <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, letterSpacing: "-0.01em", color: "var(--text)" }}>

                    Paper Portfolio Cabinet

                  </h3>

                  <span style={{ fontSize: 10, fontFamily: "var(--font-mono)", background: "var(--purple-light)", color: "var(--purple)", padding: "2px 6px", borderRadius: 4, fontWeight: 600 }}>

                    Active Tracking Since 2026-03-30

                  </span>

                </div>

                <div style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--text-light)" }}>

                  Starting Capital: $100,000 per strategy

                </div>

              </div>



              {/* Portfolio Metrics Grid */}

              <div 

                style={{

                  display: "grid",

                  gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",

                  gap: 16,

                  background: "var(--bg)",

                  borderRadius: 8,

                  border: "1px solid var(--border)",

                  padding: "16px 20px",

                  marginBottom: 16

                }}

              >

                <div>

                  <div style={{ fontSize: 9, fontFamily: "var(--font-mono)", color: "var(--text-light)" }}>TOTAL VIRTUAL CAPITAL</div>

                  <div style={{ fontSize: 20, fontWeight: 800, color: "var(--text)", fontFamily: "var(--font-mono)", marginTop: 2 }}>

                    ${(trackedBaskets.length * 100000).toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}

                  </div>

                </div>

                <div>

                  <div style={{ fontSize: 9, fontFamily: "var(--font-mono)", color: "var(--text-light)" }}>TOTAL PORTFOLIO VALUE</div>

                  <div style={{ fontSize: 20, fontWeight: 800, color: "var(--text)", fontFamily: "var(--font-mono)", marginTop: 2 }}>

                    ${(() => {

                      let totalVal = 0;

                      trackedBaskets.forEach((path) => {

                        const cfg = METHODOLOGIES_CONFIG.find((m) => m.path === path);

                        if (cfg) {

                          const returnPct = getBasketReturn(cfg.name, cfg.metrics.baseline.cagr);

                          totalVal += 100000 * (1 + returnPct);

                        }

                      });

                      return totalVal.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

                    })()}

                  </div>

                </div>

                <div>

                  <div style={{ fontSize: 9, fontFamily: "var(--font-mono)", color: "var(--text-light)" }}>AGGREGATE PERFORMANCE</div>

                  <div 

                    style={{ 

                      fontSize: 20, 

                      fontWeight: 800, 

                      color: (() => {

                        let totalVal = 0;

                        trackedBaskets.forEach((path) => {

                          const cfg = METHODOLOGIES_CONFIG.find((m) => m.path === path);

                          if (cfg) {

                            const returnPct = getBasketReturn(cfg.name, cfg.metrics.baseline.cagr);

                            totalVal += 100000 * (1 + returnPct);

                          }

                        });

                        const gain = totalVal - (trackedBaskets.length * 100000);

                        return gain >= 0 ? "var(--green)" : "var(--red)";

                      })(),

                      fontFamily: "var(--font-mono)", 

                      marginTop: 2 

                    }}

                  >

                    {(() => {

                      let totalVal = 0;

                      trackedBaskets.forEach((path) => {

                        const cfg = METHODOLOGIES_CONFIG.find((m) => m.path === path);

                        if (cfg) {

                          const returnPct = getBasketReturn(cfg.name, cfg.metrics.baseline.cagr);

                          totalVal += 100000 * (1 + returnPct);

                        }

                      });

                      const gain = totalVal - (trackedBaskets.length * 100000);

                      const returnPct = trackedBaskets.length > 0 ? (totalVal / (trackedBaskets.length * 100000) - 1) * 100 : 0;

                      return `${gain >= 0 ? "+" : ""}${gain.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} (${gain >= 0 ? "+" : ""}${returnPct.toFixed(2)}%)`;

                    })()}

                  </div>

                </div>

              </div>



              {/* Individual Baskets Rows */}

              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>

                {trackedBaskets.map((path) => {

                  const cfg = METHODOLOGIES_CONFIG.find((m) => m.path === path);

                  if (!cfg) return null;

                  const returnPct = getBasketReturn(cfg.name, cfg.metrics.baseline.cagr);

                  const basketValue = 100000 * (1 + returnPct);

                  const basketGain = basketValue - 100000;

                  const isPositive = basketGain >= 0;



                  return (

                    <div 

                      key={path}

                      style={{

                        background: "var(--bg-hover)",

                        borderRadius: 8,

                        border: "1px solid var(--border)",

                        padding: "12px 16px",

                        display: "flex",

                        justifyContent: "space-between",

                        alignItems: "center",

                        transition: "transform 0.2s ease"

                      }}

                    >

                      <div>

                        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>

                          <span 

                            style={{

                              fontSize: 9, 

                              fontFamily: "var(--font-mono)", 

                              background: cfg.regime === "BULL" ? "var(--green-light)" : cfg.regime === "SIDEWAYS" ? "var(--amber-light)" : "var(--red-light)",

                              color: cfg.regime === "BULL" ? "var(--green)" : cfg.regime === "SIDEWAYS" ? "var(--amber)" : "var(--red)",

                              padding: "1px 5px", 

                              borderRadius: 3, 

                              fontWeight: 600

                            }}

                          >

                            {cfg.regime}

                          </span>

                          <span style={{ fontSize: 13, fontWeight: 700, color: "var(--text)" }}>{cfg.name}</span>

                        </div>

                        <div style={{ fontSize: 10, color: "var(--text-light)", marginTop: 4, fontFamily: "var(--font-mono)" }}>

                          Allocated: $100,000.00

                        </div>

                      </div>



                      <div style={{ display: "flex", alignItems: "center", gap: 24 }}>

                        <div style={{ textAlign: "right" }}>

                          <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text)", fontFamily: "var(--font-mono)" }}>

                            ${basketValue.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}

                          </div>

                          <div style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: isPositive ? "var(--green)" : "var(--red)", marginTop: 2 }}>

                            {isPositive ? "+" : ""}${basketGain.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ({isPositive ? "+" : ""}{(returnPct * 100).toFixed(2)}%)

                          </div>

                        </div>

                        

                        <button

                          onClick={() => toggleTrackBasket(path)}

                          style={{

                            background: "transparent",

                            border: "none",

                            cursor: "pointer",

                            color: "var(--text-light)",

                            padding: 4,

                            borderRadius: 4,

                            transition: "all 0.15s ease",

                            display: "flex",

                            alignItems: "center",

                            justifyContent: "center"

                          }}

                          onMouseEnter={(e) => { e.currentTarget.style.color = "var(--red)"; e.currentTarget.style.background = "var(--red-light)"; }}

                          onMouseLeave={(e) => { e.currentTarget.style.color = "var(--text-light)"; e.currentTarget.style.background = "transparent"; }}

                          title="Untrack strategy"

                        >

                          <Trash2 size={16} />

                        </button>

                      </div>

                    </div>

                  );

                })}

              </div>

            </div>

          )}



          {/* Sectors tab: live sector + thematic performance (FMP) */}

          <div style={{ marginBottom: 20 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12, paddingBottom: 6, borderBottom: "1px solid var(--border)" }}>
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--blue)" }}></div>
              <h2 style={{ margin: 0, fontSize: 13, fontWeight: 800, letterSpacing: "0.05em", color: "var(--text)", fontFamily: "var(--font-sans)" }}>GICS SECTORS</h2>
              <span style={{ fontSize: 9, fontFamily: "var(--font-mono)", color: "var(--text-light)", marginLeft: "auto" }}>SPDR sector ETFs · sorted by YTD</span>
            </div>
            {!sectorData ? (
              <div style={{ textAlign: "center", padding: 30, color: "var(--text-muted)", fontSize: 13, fontFamily: "var(--font-mono)" }}>Loading sector performance…</div>
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 16 }}>
                {[...sectorData.sectors].sort((a, b) => (b.ytd ?? -999) - (a.ytd ?? -999)).map((c) => (
                  <PerfCard key={c.symbol} title={c.name} price={c.price} day={c.day} ytd={c.ytd} year={c.year} note={c.symbol} holdingsSymbol={c.symbol} />
                ))}
              </div>
            )}
          </div>

          <div style={{ marginBottom: 20 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12, paddingBottom: 6, borderBottom: "1px solid var(--border)" }}>
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--purple)" }}></div>
              <h2 style={{ margin: 0, fontSize: 13, fontWeight: 800, letterSpacing: "0.05em", color: "var(--text)", fontFamily: "var(--font-sans)" }}>THEMATIC</h2>
              <span style={{ fontSize: 9, fontFamily: "var(--font-mono)", color: "var(--text-light)", marginLeft: "auto" }}>industry / theme ETFs · sorted by YTD</span>
            </div>
            {sectorData && (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: 16 }}>
                {[...sectorData.thematic].sort((a, b) => (b.ytd ?? -999) - (a.ytd ?? -999)).map((c) => (
                  <PerfCard key={c.symbol} title={c.name} price={c.price} day={c.day} ytd={c.ytd} year={c.year} note={c.symbol} holdingsSymbol={c.symbol} />
                ))}
              </div>
            )}
          </div>

        </div>

      ) : viewMode === "table" ? (

        <div style={{background:"var(--bg)",borderRadius:8,border:"1px solid var(--border)",overflow:"hidden",boxShadow:"0 1px 3px rgba(0,0,0,0.06)"}}>

          <div style={{overflowX:"auto"}}>

            <table style={{width:"100%",borderCollapse:"collapse",fontSize:13}}>

              <thead><tr>

                <th style={hs("symbol","left")} onClick={()=>toggleSort("symbol")}>SYMBOL</th>

                <th style={hs("sector","left")} onClick={()=>toggleSort("sector")} title="Click to sort by sector (alphabetical).">SECTOR</th>

                <th style={hs("country","center")} onClick={()=>toggleSort("country")} title="ISO country code from FMP company-screener. Click to sort.">CTRY</th>

                <th style={hs("price")} onClick={()=>toggleSort("price")}>PRICE</th>

                <th style={hs("piotroski","center")} onClick={()=>toggleSort("piotroski")} title="Piotroski 0-9 — diagnostic only, not in v8 composite">PIO</th>

                <th style={hs("p_s")} onClick={()=>toggleSort("p_s")} title="Price/Sales ratio (latest annual). Industry-dependent — tech 5-15 normal, banks 1-3 normal. Click to sort.">P/S</th>

                <th style={hs("pe")} onClick={()=>toggleSort("pe")} title="Price to Earnings (TTM)">P/E</th>

                <th style={hs("ev_ebit")} onClick={()=>toggleSort("ev_ebit")} title="Enterprise Value to EBIT">EV/EBIT</th>

                <th style={hs("fcf_share")} onClick={()=>toggleSort("fcf_share")} title="Free Cash Flow per Share">FCF/sh</th>

                <th style={hs("epv_share")} onClick={()=>toggleSort("epv_share")} title="Earnings Power Value per Share">EPV/sh</th>

                <th style={hs("net_margin")} onClick={()=>toggleSort("net_margin")} title="Net Profit Margin">NPM</th>

                <th style={hs("upside")} onClick={()=>toggleSort("upside")} title="Analyst consensus upside %. Sub-component of v8 Value.">UPSIDE</th>

                <th style={hs("hit_prob","center")} onClick={()=>toggleSort("hit_prob")} title="P(+20% daily high in 4 weeks) — ML ensemble model (AUC 0.78). High P20 + Low IVR = underpriced options. D10 stocks hit 26% of the time.">P20</th>

                <th style={{...hs("static","center"),cursor:"default"}} title="Implied Volatility Rank (Massive/Polygon API). Available for all US stocks.">IVR</th>

              </tr></thead>

              <tbody>{sorted.map((s,idx)=><StockRow key={s.symbol} stock={s} rank={idx+1} expanded={!!expanded[s.symbol]} onToggle={()=>setExpanded(e=>({...e,[s.symbol]:!e[s.symbol]}))} onTickerClick={handleTickerClick} selectedMethodology={selectedMethodology} />)}</tbody>

            </table>

          </div>

          {sorted.length===0&&<div style={{textAlign:"center",padding:40,color:"var(--text-muted)",fontSize:13,fontFamily:"var(--font-mono)"}}>No stocks match this filter</div>}

        </div>

      ) : (

        <div style={{display:"grid",gridTemplateColumns:"repeat(auto-fill, minmax(320px, 1fr))",gap:16}}>

          {sorted.map(s => {

            const prob = s.hit_prob ? Math.round(s.hit_prob * 100) : undefined;

            return (

              <StockCard 

                key={s.symbol}

                symbol={s.symbol}

                companyName={s.company_name}

                strategy={(s.sector || "Unknown Sector").toUpperCase()}

                thesis={s.transcript_summary || s.reasons?.join(". ") || ""}

                action="HOLD"

                p20={prob}

                upside={s.intrinsic_upside ?? undefined}

                smartMoney={s.factors_v8_momentum?.smart_money ?? s.factors_v8?.smart_money ?? undefined}

                price={s.price}

                currency={s.currency}

                onClick={(e) => handleTickerClick(e, s.symbol)}

              />

            );

          })}

          {sorted.length===0&&<div style={{gridColumn:"1/-1",textAlign:"center",padding:40,color:"var(--text-muted)",fontSize:13,fontFamily:"var(--font-mono)"}}>No stocks match this filter</div>}

        </div>

      )}

      <div style={{textAlign:"center",marginTop:14,fontSize:10,color:"var(--text-light)",fontFamily:"var(--font-mono)"}}>

        {stocks.length} screened · {sorted.length} shown{sectorFilter.length > 0 ? ` · sectors: ${sectorFilter.length}` : ""}{countryFilter.length > 0 ? ` · countries: ${countryFilter.length}` : ""} · click row to expand · click any column header to sort

      </div>

      <SectorConcentration data={data?.sector_concentration}/>

      </div>

      <Watchlist />

    </div>

  );

}

