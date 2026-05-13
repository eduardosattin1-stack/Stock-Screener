"use client";
import { useState, useEffect, useMemo } from "react";
import { TrendingUp, ChevronDown, ChevronRight, Target, Search, Zap, Copy, CheckCircle2, ArrowRight, Clock } from "lucide-react";
import { Watchlist } from "./components/Watchlist";

const GCS_BASE = "/api/gcs/scans";
const GCS_FALLBACK = "https://storage.googleapis.com/screener-signals-carbonbridge/scans/latest.json";
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
  "STRONG BUY": { color:"#8b5cf6", bg:"#f5f3ff", border:"#ddd6fe" },
  BUY:   { color:"#10b981", bg:"#e8f5ee", border:"#b8dcc8" },
  WATCH: { color:"#f59e0b", bg:"#fffbeb", border:"#fde68a" },
  HOLD:  { color:"#6b7280", bg:"#f8fafc", border:"#e2e8f0" },
  SELL:  { color:"#ef4444", bg:"#fef2f2", border:"#fecaca" },
};
const CLS: Record<string,string> = { DEEP_VALUE:"#2563eb", VALUE:"#0891b2", QUALITY_GROWTH:"#7c3aed", GROWTH:"#818cf8", SPECULATIVE:"#ef4444", NEUTRAL:"#64748b" };

// v8 (Apr 2026) — 5-factor composite radar config
// Replaces the v7 13-factor list. The order drives radar axis layout
// (clockwise from top); FACTOR_WEIGHTS supplies the percent labels rendered
// in the expanded factor breakdown.
const FACTOR_ORDER = ["momentum","quality","growth","value","smart_money"];
const FACTOR_LABELS: Record<string,string> = { momentum:"Momentum", quality:"Quality", growth:"Growth", value:"Value", smart_money:"Smart Money" };
const FACTOR_WEIGHTS: Record<string,number> = { momentum:25, quality:20, growth:20, value:20, smart_money:15 };

// ── Helpers ─────────────────────────────────────────────────────────────────
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

// getProb: fallback table for stocks without live hit_prob field (rare).
// Numbers are rough approximations from v7.2 backtest calibration — used by
// the GAIN/DD column for projected gain & drawdown ranges per composite band.
// Note (Apr 2026): the P+10% column itself was removed after the LTR
// investigation showed per-stock probabilities aren't trustworthy at the
// 0.65 AUC ceiling. The Smart Money Score replaces it. hit_prob is still
// computed in the backend and written to JSON for diagnostic purposes — it
// just isn't rendered. probFallback below remains in use by GAIN/DD which
// reads from this same backtest-calibration table keyed on composite.
function getProb(c:number){if(c>=0.90)return{p10:85,gain:25.7,dd:-9.1,speed:18};if(c>=0.80)return{p10:75,gain:20.0,dd:-9.8,speed:22};if(c>=0.65)return{p10:62,gain:15.0,dd:-10.5,speed:26};if(c>=0.50)return{p10:50,gain:12.0,dd:-11.0,speed:30};return{p10:35,gain:9.0,dd:-11.0,speed:32};}

// v8 mode-aware factor reader. Compounder modes share the Momentum factors
// since they use the same v8 5-factor radar — the difference is the cohort
// gate (US exchange / sector-excluded global) and the ranking score
// (compounder_score_us/_global). FA mode has its own factors_v8_fallen_angel.
// Last-resort fallback returns an all-null FactorsV8 so the radar renders
// five dashed/empty axes rather than crashing.
function readFactorsV8(s:StockData, mode:string):FactorsV8 {
  const f = mode === "fallen_angel"
    ? (s.factors_v8_fallen_angel ?? s.factors_v8)
    : (s.factors_v8_momentum ?? s.factors_v8);   // compounder modes use momentum factors
  if (f) return f;
  return { momentum:null, quality:null, growth:null, value:null, smart_money:null };
}
// v1.2 (May 2026): readComposite handles 4 modes. Compounder modes use their
// dedicated rank score (compounder_score_us/_global) instead of the v8
// composite — that's how the compounder runners pick their baskets.
function readComposite(s:StockData, mode:string):number {
  if (mode === "fallen_angel")      return s.composite_fallen_angel ?? s.composite ?? 0;
  if (mode === "compounder_us")     return s.compounder_score_us ?? 0;
  if (mode === "compounder_global") return s.compounder_score_global ?? 0;
  return s.composite_momentum ?? s.composite ?? 0;
}
function readSignal(s:StockData, mode:string):string {
  // v1.2 (May 2026): signal_fallen_angel removed → derive from fallen_angel_flag.
  // signal (BUY/HOLD/SELL) removed → no fallback chain. signal_momentum and
  // signal_compounder_us/_global still exist (QUALIFIED/DISQUALIFIED).
  if (mode === "fallen_angel")      return s.fallen_angel_flag ? "QUALIFIED" : "DISQUALIFIED";
  if (mode === "compounder_us")     return s.signal_compounder_us ?? "DISQUALIFIED";
  if (mode === "compounder_global") return s.signal_compounder_global ?? "DISQUALIFIED";
  return s.signal_momentum ?? "DISQUALIFIED";
}

// v1.2: 4-mode universe gate. A stock passes the gate for a mode iff:
//   - Momentum: signal_momentum != "DISQUALIFIED"
//   - Fallen Angel: fallen_angel_flag == true
//   - Compounder US/Global: signal_compounder_us/_global == "QUALIFIED"
function isQualified(s:StockData, mode:string):boolean {
  if (mode === "fallen_angel")      return s.fallen_angel_flag === true;
  if (mode === "compounder_us")     return s.signal_compounder_us === "QUALIFIED";
  if (mode === "compounder_global") return s.signal_compounder_global === "QUALIFIED";
  const sig = s.signal_momentum;
  // Fallback: if signal_momentum absent (legacy scan), let row through
  if (sig == null) return true;
  return sig !== "DISQUALIFIED";
}

// ── ModeToggle (v8) ─────────────────────────────────────────────────────────
// Switches the entire table between Momentum and Fallen Angel views. Each
// stock has both composites computed at scan time, so toggling is purely a
// view state — no re-fetch. Default mode is Momentum (matches screener-table
// historical convention; sort by FA composite by clicking the header).
function ModeToggle({mode,onChange}:{mode:string;onChange:(m:string)=>void}){
  // v1.2 (May 2026): 2 modes → 4 modes. Momentum + FA + the two Compounder
  // baskets. Compounder modes share the v8 5-factor radar with Momentum
  // (same factors_v8_momentum data); the difference is the cohort gate
  // (US exchange vs global ex Fin/Ins/HC) and the ranking score
  // (compounder_score_us/_global = 3y-ROE × P/B × OpMargin-delta).
  const opts = [
    {k:"momentum",         l:"Momentum"},
    {k:"fallen_angel",     l:"Fallen Angel"},
    {k:"compounder_us",    l:"CMP-US"},
    {k:"compounder_global",l:"CMP-Global"},
  ];
  return(
    <div style={{display:"inline-flex",border:"1px solid var(--border,#e5e7eb)",borderRadius:6,overflow:"hidden",background:"#fff"}}>
      {opts.map((o,i)=>{
        const active = o.k === mode;
        return(
          <button key={o.k} onClick={()=>onChange(o.k)} style={{
            padding:"6px 12px",
            border:"none",
            borderRight: i < opts.length-1 ? "1px solid var(--border,#e5e7eb)" : "none",
            cursor:"pointer",
            background: active ? "var(--green,#2d7a4f)" : "transparent",
            color: active ? "#fff" : "var(--text)",
            fontSize:11,fontFamily:"var(--font-mono)",fontWeight:600,letterSpacing:"0.04em",
            transition:"background 0.15s",
          }}>
            {o.l}
          </button>
        );
      })}
    </div>
  );
}

// ── Mini Radar (5-axis v8) ──────────────────────────────────────────────────
// Used inline next to symbol in row when not expanded. With 5 axes each
// vertex has more breathing room than the 13-axis legacy version, so we can
// afford slightly bigger dots and a thicker stroke.
function MiniRadar({scores,size=44}:{scores:FactorsV8;size?:number}){
  const cx=size/2,cy=size/2,r=size/2-4;const raw=FACTOR_ORDER.map(k=>(scores as any)[k] as number|null);const vals=raw.map(v=>v??0);const n=vals.length;
  const ang=(i:number)=>(Math.PI*2*i)/n-Math.PI/2;
  const evaluated=raw.filter(v=>v!=null) as number[];const avg=evaluated.length?evaluated.reduce((a:number,b:number)=>a+b,0)/evaluated.length:0;
  const fill=avg>0.6?"#2d7a4f":avg>0.4?"#d97706":"#ef4444";
  const data=vals.map((v,i)=>`${cx+Math.cos(ang(i))*Math.max(0.05,v)*r},${cy+Math.sin(ang(i))*Math.max(0.05,v)*r}`).join(" ");
  const grid=[0.33,0.66,1].map(lv=>Array.from({length:n},(_,i)=>`${cx+Math.cos(ang(i))*r*lv},${cy+Math.sin(ang(i))*r*lv}`).join(" "));
  return(
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {grid.map((p,i)=><polygon key={i} points={p} fill="none" stroke="#e2e8e4" strokeWidth={0.5} opacity={0.6}/>)}
      {Array.from({length:n},(_,i)=><line key={i} x1={cx} y1={cy} x2={cx+Math.cos(ang(i))*r} y2={cy+Math.sin(ang(i))*r} stroke="#e2e8e4" strokeWidth={0.4}/>)}
      <polygon points={data} fill={fill} fillOpacity={0.2} stroke={fill} strokeWidth={1.4} strokeLinejoin="round"/>
      {vals.map((v,i)=><circle key={i} cx={cx+Math.cos(ang(i))*Math.max(0.05,v)*r} cy={cy+Math.sin(ang(i))*Math.max(0.05,v)*r} r={1.8} fill={raw[i]==null?"#d1d5db":fill}/>)}
    </svg>
  );
}

// ── Large Radar for expanded row (5-axis v8) ────────────────────────────────
// Bigger label area than the 13-axis version since five short labels fit
// without overlap. Numerical score rendered next to each label for at-a-
// glance reading inside the expanded factor breakdown panel.
function LargeRadar({scores,size=180}:{scores:FactorsV8;size?:number}){
  const cx=size/2,cy=size/2,r=size/2-30;const raw=FACTOR_ORDER.map(k=>(scores as any)[k] as number|null);const vals=raw.map(v=>v??0);const n=vals.length;
  const ang=(i:number)=>(Math.PI*2*i)/n-Math.PI/2;
  const evaluated=raw.filter(v=>v!=null) as number[];const avg=evaluated.length?evaluated.reduce((a:number,b:number)=>a+b,0)/evaluated.length:0;
  const fill=avg>0.6?"#2d7a4f":avg>0.4?"#d97706":"#ef4444";
  return(
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {[0.25,0.5,0.75,1].map((lv,i)=>{const pts=Array.from({length:n},(_,j)=>`${cx+Math.cos(ang(j))*r*lv},${cy+Math.sin(ang(j))*r*lv}`).join(" ");return<polygon key={i} points={pts} fill="none" stroke="#d1d5db" strokeWidth={i===3?1:0.5} opacity={0.5}/>;})}
      {FACTOR_ORDER.map((k,i)=>{const a=ang(i),lx=cx+Math.cos(a)*(r+22),ly=cy+Math.sin(a)*(r+22),v=raw[i],isNull=v==null,c=isNull?"#d1d5db":((v??0)>0.7?"#2d7a4f":(v??0)>0.4?"#d97706":"#ef4444");return<g key={k}><line x1={cx} y1={cy} x2={cx+Math.cos(a)*r} y2={cy+Math.sin(a)*r} stroke="#d1d5db" strokeWidth={0.5} strokeDasharray={isNull?"3,2":"none"}/><text x={lx} y={ly-4} textAnchor="middle" dominantBaseline="middle" fontSize={9} fontFamily="var(--font-mono)" fill={isNull?"#d1d5db":"#6b7280"} fontWeight="600">{FACTOR_LABELS[k]}</text><text x={lx} y={ly+7} textAnchor="middle" dominantBaseline="middle" fontSize={10} fontFamily="var(--font-mono)" fill={c} fontWeight="700">{isNull?"—":((v??0)*100).toFixed(0)}</text></g>;})}
      <polygon points={vals.map((v,i)=>`${cx+Math.cos(ang(i))*Math.max(0.05,v)*r},${cy+Math.sin(ang(i))*Math.max(0.05,v)*r}`).join(" ")} fill={fill} fillOpacity={0.15} stroke={fill} strokeWidth={1.8} strokeLinejoin="round"/>
      {vals.map((v,i)=><circle key={i} cx={cx+Math.cos(ang(i))*Math.max(0.05,v)*r} cy={cy+Math.sin(ang(i))*Math.max(0.05,v)*r} r={3} fill={raw[i]==null?"#d1d5db":fill} stroke="#fff" strokeWidth={1.2}/>)}
    </svg>
  );
}

// ── Factor Bar ──────────────────────────────────────────────────────────────
function FactorBar({name,weight,score}:{name:string;weight:number;score:number|null}){
  if(score==null) return<div style={{padding:"5px 0",borderBottom:"1px solid var(--divider)",opacity:0.45}}><div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:3}}><div style={{display:"flex",alignItems:"baseline",gap:4}}><span style={{fontSize:11,fontFamily:"var(--font-mono)",fontWeight:600,color:"#d1d5db"}}>{name}</span><span style={{fontSize:8,fontFamily:"var(--font-mono)",color:"#d1d5db"}}>({weight}%)</span></div><span style={{fontSize:10,fontFamily:"var(--font-mono)",color:"#d1d5db",fontStyle:"italic"}}>no data</span></div><div style={{height:4,borderRadius:2,background:"#edf0ee"}}><div style={{height:"100%",width:0}}/></div></div>;
  const c=score>0.7?"#10b981":score>0.4?"#f59e0b":"#ef4444";
  return(
    <div style={{padding:"5px 0",borderBottom:"1px solid var(--divider)"}}>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:3}}>
        <div style={{display:"flex",alignItems:"baseline",gap:4}}><span style={{fontSize:11,fontFamily:"var(--font-mono)",fontWeight:600,color:"var(--text)"}}>{name}</span><span style={{fontSize:8,fontFamily:"var(--font-mono)",color:"var(--text-light)"}}>({weight}%)</span></div>
        <span style={{fontSize:11,fontFamily:"var(--font-mono)",fontWeight:700,color:c}}>{(score*100).toFixed(0)}</span>
      </div>
      <div style={{height:4,borderRadius:2,background:"var(--bg-elevated,#edf0ee)",overflow:"hidden"}}><div style={{height:"100%",width:`${score*100}%`,borderRadius:2,background:c,transition:"width 0.3s"}}/></div>
    </div>
  );
}

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
  RISK_ON:  { color:"#10b981", bg:"#e8f5ee", border:"#b8dcc8", label:"RISK ON" },
  NEUTRAL:  { color:"#6b7280", bg:"#f8fafc", border:"#e2e8f0", label:"NEUTRAL" },
  CAUTIOUS: { color:"#d97706", bg:"#fffbeb", border:"#fde68a", label:"CAUTIOUS" },
  RISK_OFF: { color:"#ef4444", bg:"#fef2f2", border:"#fecaca", label:"RISK OFF" },
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
                <div key={key} style={{padding:"6px 8px",borderRadius:6,background:"#fff",border:"1px solid var(--border-subtle,#eef1ef)"}}>
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
          border:`1px solid ${selected.length>0 ? "var(--green,#2d7a4f)" : "var(--border,#e5e7eb)"}`,
          borderRadius:6,
          cursor: disabled ? "not-allowed" : "pointer",
          background: selected.length > 0 ? "var(--green-light,#e8f5ee)" : "#fff",
          color: disabled ? "var(--text-light)" : (selected.length > 0 ? "var(--green,#2d7a4f)" : "var(--text)"),
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
            background:"#fff", border:"1px solid var(--border,#e5e7eb)",
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
                      color: checked ? "var(--green,#2d7a4f)" : "var(--text)",
                      background: checked ? "var(--green-light,#e8f5ee)" : "transparent",
                    }}
                    onMouseEnter={e=>{(e.currentTarget as HTMLElement).style.background = checked ? "var(--green-light,#e8f5ee)" : "var(--bg-hover,#f0f4f1)";}}
                    onMouseLeave={e=>{(e.currentTarget as HTMLElement).style.background = checked ? "var(--green-light,#e8f5ee)" : "transparent";}}>
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
// /api/portfolio/add which proxies to Cloud Run.
function AddToPortfolioButton({stock:s}:{stock:StockData}){
  const [open,setOpen]=useState(false);
  const [shares,setShares]=useState("");
  const [price,setPrice]=useState(s.price?.toFixed(2)||"");
  const [notes,setNotes]=useState("");
  const [status,setStatus]=useState<"idle"|"saving"|"saved"|"error">("idle");
  const [err,setErr]=useState("");

  async function handleSave(e:React.MouseEvent){
    e.stopPropagation();
    const p=parseFloat(price), sh=parseFloat(shares);
    if(!p||p<=0){setErr("Price required");return;}
    if(!sh||sh<=0){setErr("Shares required");return;}
    setStatus("saving");setErr("");
    try {
      const res=await fetch("/api/portfolio/add",{
        method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({symbol:s.symbol,entry_price:p,shares:sh,notes}),
      });
      if(!res.ok){
        const t=await res.text().catch(()=>"");
        const isHtml=t.trimStart().toLowerCase().startsWith("<!doctype")||t.trimStart().startsWith("<");
        const body=isHtml?"(server returned HTML page)":t.slice(0,120);
        throw new Error(`HTTP ${res.status}${body?` – ${body}`:""}`);
      }
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
      borderRadius:6,background:"#fff",border:"1px solid var(--green-border,#b8dcc8)",
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
        background:"#fff",color:"var(--text-muted,#6b7280)",fontSize:10,fontFamily:"var(--font-mono)",
      }}>✕</button>
      {err&&<span style={{color:"#ef4444",fontSize:9,marginLeft:4}}>{err}</span>}
    </div>
  );
}

function StockRow({stock:s,expanded,onToggle,mode,rank}:{stock:StockData;expanded:boolean;onToggle:()=>void;mode:string;rank:number}){
  // v8 mode-aware bindings. The user's mode toggle drives which composite
  // and factor radar appear in the expanded row.
  const scoresActive = readFactorsV8(s, mode);
  const compActive = readComposite(s, mode);

  // v1.2 (May 2026): 4-mode divergence chip. Scan all 3 other modes and
  // surface the highest-scoring one IF it qualifies AND beats active by
  // ≥0.10. Tells the user "this stock is actually better viewed as CMP-US"
  // (or whichever) without forcing them to flip through all 4 modes.
  const otherModes = ["momentum","fallen_angel","compounder_us","compounder_global"].filter(m=>m!==mode);
  const otherLabels: Record<string,string> = {
    momentum:"Mom", fallen_angel:"FA",
    compounder_us:"CMP-US", compounder_global:"CMP-GL",
  };
  let bestOther = { mode:"", score:0, label:"" };
  for (const m of otherModes) {
    if (!isQualified(s, m)) continue;
    const c = readComposite(s, m);
    if (c > bestOther.score) bestOther = { mode:m, score:c, label:otherLabels[m] };
  }
  const otherIsHigher = bestOther.mode !== "" && (bestOther.score - compActive >= 0.10);
  // v1.2: scoresOther / probFallback / dual-comp column removed — see F2a + F2b notes.

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
                <a href={`/stock/${s.symbol}`} onClick={e=>e.stopPropagation()} style={{fontWeight:700,letterSpacing:"0.04em",color:"var(--text,#1a1a1a)",fontSize:13,fontFamily:"var(--font-mono)"}}>{s.symbol}</a>
                {s.has_catalyst&&<Zap size={10} color="#8b5cf6" fill="#8b5cf6"/>}
                {otherIsHigher&&<span style={{fontSize:8,padding:"1px 5px",borderRadius:3,background:"#fffbeb",color:"#d97706",fontFamily:"var(--font-mono)",fontWeight:700,border:"1px solid #fde68a"}} title={`${bestOther.label} composite is ${(bestOther.score-compActive).toFixed(2)} higher — switch mode to compare`}>↻ {bestOther.label}+{(bestOther.score-compActive).toFixed(2)}</span>}
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
        {/* COMP (active mode) — primary, larger, colored by score */}
        <td style={{padding:"10px 8px",textAlign:"right",fontFamily:"var(--font-mono)",fontSize:13,color:compActive>0.7?"#10b981":compActive>0.5?"var(--text)":compActive>0.3?"var(--text-muted)":"#ef4444",fontWeight:700}}>
          {compActive.toFixed(2)}
        </td>
        {/* v1.2 (May 2026): "COMP other" column dropped. With 4 modes the
            "other" concept becomes ambiguous (3 candidates). The divergence
            chip (↻ FA+0.12 next to the symbol) still highlights when a
            stock would score materially better in another mode. */}
        {/* VAL/GRW/QUAL columns removed in F2a. Sub-factor scores visible
            in the expanded row (LargeRadar + FactorBar). */}
        {/* UPSIDE — analyst consensus (v8 Value sub-component, kept for reference) */}
        <td style={{fontFamily:"var(--font-mono)",textAlign:"right",padding:"10px 12px",fontSize:12,color:s.upside>20?"#10b981":s.upside>0?"var(--text-muted)":"#ef4444",fontWeight:600}}>{s.upside>0?"+":""}{s.upside?.toFixed(0)}%</td>
        {/* SMART$ — LTR-derived weighted score; pass-2 only, US-only.
            Replaced P+10% column in Apr 2026 after LTR investigation showed
            per-stock hit probabilities aren't trustworthy at the 0.65 AUC ceiling. */}
        <td style={{padding:"10px 8px",textAlign:"center",fontFamily:"var(--font-mono)",fontSize:11}}>
          {(()=>{const sm = s.smart_money_score;
            if (sm == null) return <span style={{color:"var(--text-light,#9ca3af)"}} title="Requires US data: 13F flow + accumulation are pass-2 enrichment, US-only.">—</span>;
            const c = sm>0.7?"#10b981":sm>0.5?"var(--text-muted)":sm>0.3?"#d97706":"#ef4444";
            const wt = s.smart_money_weight ?? 1.0;
            const compStr = Object.entries(s.smart_money_components||{}).map(([k,v])=>`${k}=${(v*100).toFixed(0)}`).join(" · ");
            const tip = wt < 1.0
              ? `Score ${(sm*100).toFixed(0)} / max ${(wt*100).toFixed(0)} (some optional factors unavailable). Components: ${compStr}`
              : `Full coverage. Components: ${compStr}`;
            return <span style={{color:c,fontWeight:700}} title={tip}>{(sm*100).toFixed(0)}</span>;})()}
        </td>
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
        {/* IVR — Implied Volatility Rank (top-30 only, needs 20+ days IV history) */}
        <td style={{fontFamily:"var(--font-mono)",textAlign:"center",padding:"10px 6px",fontSize:11}}>
          {(()=>{
            const ivr=s.options_iv_rank;
            const iv=s.options_iv_current;
            const samples=s.options_iv_samples||0;
            if(ivr==null&&iv==null) return <span style={{color:"var(--text-light,#9ca3af)"}} title="Top-30 only; 20+ days of IV history needed for rank">—</span>;
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
        {/* v1.2 (May 2026): GAIN/DD column dropped. Static lookup-table band
            (same for every stock in a composite bucket) — provided no
            decision-useful information. Composite alone carries the message. */}
      </tr>
      {expanded&&(
        <tr><td colSpan={11} style={{padding:0,background:"var(--bg-surface,#f8faf9)"}}>
          <div style={{padding:"16px 20px 20px 40px",animation:"fadeIn 0.2s ease"}}>
            <div style={{display:"grid",gridTemplateColumns:"200px 1fr",gap:24}}>
              <div style={{display:"flex",flexDirection:"column",alignItems:"center",gap:8}}>
                <LargeRadar scores={scoresActive}/>
                <div style={{fontSize:10,fontFamily:"var(--font-mono)",color:"var(--text-muted)"}}>
                  {(()=>{const vals=Object.values(scoresActive).filter((v):v is number=>v!=null);return vals.length?Math.round(vals.reduce((a,b)=>a+b,0)/vals.length*100):0;})()} avg · {mode==="fallen_angel"?"FA":"Momentum"} mode
                </div>
              </div>
              <div>
                <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:8,paddingBottom:6,borderBottom:"2px solid var(--green-light,#e8f5ee)"}}>
                  <div style={{fontSize:10,fontWeight:700,letterSpacing:"0.08em",color:"var(--green,#2d7a4f)",fontFamily:"var(--font-mono)",textTransform:"uppercase"}}>5-Factor Breakdown · {mode==="fallen_angel"?"Fallen Angel":"Momentum"}</div>
                  <AddToPortfolioButton stock={s}/>
                </div>
                <div style={{display:"grid",gridTemplateColumns:"1fr",gap:0}}>
                  {FACTOR_ORDER.map(k=>{const w=FACTOR_WEIGHTS[k];return<FactorBar key={k} name={FACTOR_LABELS[k]} weight={w} score={(scoresActive as any)[k]}/>;})}
                </div>
                {/* Mode comparison strip */}
                {bestOther.score>0&&(
                  <div style={{marginTop:10,padding:"8px 12px",borderRadius:5,background:otherIsHigher?"#fffbeb":"#f8faf9",border:`1px solid ${otherIsHigher?"#fde68a":"var(--border-subtle,#eef1ef)"}`,fontSize:10,fontFamily:"var(--font-mono)",color:"var(--text-muted,#6b7280)",lineHeight:1.5}}>
                    <span style={{fontWeight:700,color:otherIsHigher?"#d97706":"var(--text)"}}>Best alternative — {bestOther.label}: {bestOther.score.toFixed(2)}</span>
                    {otherIsHigher && <span style={{marginLeft:6,color:"#d97706"}}>— leads active mode by {(bestOther.score-compActive).toFixed(2)}, worth checking that view</span>}
                  </div>
                )}
              </div>
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
    <div style={{background:"#fff",borderRadius:8,border:"1px solid var(--border,#e5e7eb)",boxShadow:"0 1px 3px rgba(0,0,0,0.06)",padding:"16px 18px",marginTop:16}}>
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
    OUTPERFORMING:{color:"#10b981",bg:"#e8f5ee",tip:"Alpha — beating peers"},
    SECTOR_TAILWIND:{color:"#3b82f6",bg:"#eff6ff",tip:"Rising tide — whole sector strong"},
    SECTOR_HEADWIND:{color:"#d97706",bg:"#fffbeb",tip:"Sector weakness — headwind"},
    LAGGING:{color:"#ef4444",bg:"#fef2f2",tip:"Underperforming peers"},
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
  | "active_comp"
  | "upside" | "smart_money" | "hit_prob";
// v1.2 (May 2026): removed orphan SortKeys (value_score/growth_score/quality_score) —
// those columns were dropped from the table. Added sector/country for the new
// SECTOR + CTRY columns. String-based sort handled in the sorted useMemo below.
// "other_comp" dropped — 4-mode world makes "other" ambiguous.

export default function Dashboard(){
  const [data,setData]=useState<ScanData|null>(null);
  const [loading,setLoading]=useState(true);

  // v1.2 (May 2026): mode toggle drives entire table view (sort target,
  // displayed composite, radar). Persisted to localStorage so the user's
  // preference survives reloads. 4 modes: momentum / fallen_angel /
  // compounder_us / compounder_global.
  const [mode,setMode]=useState<string>("momentum");
  useEffect(()=>{
    if (typeof window === "undefined") return;
    const saved = window.localStorage.getItem("cb_screener_mode");
    if (saved === "fallen_angel" || saved === "momentum" ||
        saved === "compounder_us" || saved === "compounder_global") setMode(saved);
  },[]);
  useEffect(()=>{
    if (typeof window !== "undefined") window.localStorage.setItem("cb_screener_mode", mode);
  },[mode]);

  const [sortKey,setSortKey]=useState<SortKey>("active_comp");
  const [sortDir,setSortDir]=useState<"asc"|"desc">("desc");
  const [search,setSearch]=useState("");
  const [expanded,setExpanded]=useState<Record<string,boolean>>({});

  // v1.2 (May 2026): filter state.
  // - cohortFilter: scope tab (matches the active mode's gate by default,
  //   but user can broaden to "all" or pivot to another cohort flag).
  // - sectorFilter: multi-select. Empty array = no filter.
  // - countryFilter: multi-select. Empty array = no filter.
  // - filterMenuOpen: tracks which dropdown is open (only one at a time).
  const [cohortFilter,setCohortFilter]=useState<string>("qualified");
  const [sectorFilter,setSectorFilter]=useState<string[]>([]);
  const [countryFilter,setCountryFilter]=useState<string[]>([]);
  const [filterMenuOpen,setFilterMenuOpen]=useState<"sector"|"country"|null>(null);

  useEffect(()=>{
    setLoading(true);
    fetch(`${GCS_BASE}/latest_global.json?t=${Date.now()}`)
      .then(r=>r.ok?r.json():null)
      .then(d=>{ setData(d); setLoading(false); })
      .catch(()=>{ setLoading(false); });
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

  const stocks: StockData[] = data?.stocks || [];

  // v1.2 (May 2026): filter dropdown options derived from loaded universe.
  // Memoized on `stocks` so they don't reshuffle on every keystroke.
  // CRITICAL: these are hooks — must be called unconditionally, BEFORE the
  // early `if (loading) return ...`. Placing them after the early return
  // violated Rules of Hooks (loading=true skipped the hook, loading=false
  // suddenly added 2 hooks → React error #310). The whole screener page
  // crashed on initial load until this was fixed.
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

  // Sort key extractor. Mode-aware so that toggling the mode re-ranks
  // the table without changing the sort key. "active_comp" follows the
  // selected mode (4 modes in v1.2).
  // sector/country are string sorts (handled in sorted useMemo).
  const extract = (s:StockData, key:SortKey):number => {
    switch(key){
      case "active_comp":   return readComposite(s, mode);
      case "piotroski":     return s.piotroski ?? 0;
      case "p_s":           return (s.p_s != null && s.p_s > 0) ? s.p_s : -1;
      case "upside":        return s.upside ?? 0;
      case "smart_money":   return s.smart_money_score ?? -1;
      case "hit_prob":      return s.hit_prob ?? -1;
      case "price":         return s.price ?? 0;
      case "symbol":        return s.symbol.charCodeAt(0);
      // sector/country handled by string-sort branch below
      default:              return 0;
    }
  };

  const sorted = useMemo(()=>{
    let list = [...stocks];
    if (search) {
      const q = search.toUpperCase();
      list = list.filter(s => s.symbol.includes(q) || (s.company_name||"").toUpperCase().includes(q));
    }
    // v1.2 (May 2026): cohort filter — narrows to a specific basket gate.
    //   "all"          → no cohort gate (sees disqualified rows too)
    //   "qualified"    → passes the ACTIVE mode's gate (default; was the
    //                    only behavior pre-v1.2)
    //   "fa_flagged"   → fallen_angel_flag == true (regardless of active mode)
    //   "cmp_us"       → signal_compounder_us == QUALIFIED
    //   "cmp_global"   → signal_compounder_global == QUALIFIED
    // Search overrides cohort filter — if the user typed a symbol they want
    // to find it regardless of which baskets it qualifies for.
    if (!search) {
      if (cohortFilter === "qualified")     list = list.filter(s => isQualified(s, mode));
      else if (cohortFilter === "fa_flagged")  list = list.filter(s => s.fallen_angel_flag === true);
      else if (cohortFilter === "cmp_us")      list = list.filter(s => s.signal_compounder_us === "QUALIFIED");
      else if (cohortFilter === "cmp_global")  list = list.filter(s => s.signal_compounder_global === "QUALIFIED");
      // "all" → no gate
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
      // v1.2: string sort for SECTOR + CTRY columns. Empty/null strings
      // sort to the end regardless of direction.
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
  // extract closes over `mode`; include it in deps so toggling mode re-sorts
  // eslint-disable-next-line react-hooks/exhaustive-deps
  },[stocks, sortKey, sortDir, search, mode, cohortFilter, sectorFilter, countryFilter]);

  // Hidden count for footer transparency. Reports stocks excluded by active
  // mode's gate (only meaningful when cohortFilter is the default "qualified").
  const hiddenCount = useMemo(()=>{
    if (search || cohortFilter !== "qualified") return 0;
    return stocks.filter(s => !isQualified(s, mode)).length;
  },[stocks, search, cohortFilter, mode]);

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
    color: sortKey === key ? "var(--green,#2d7a4f)" : "var(--text-light,#9ca3af)",
    userSelect:"none", whiteSpace:"nowrap",
    borderBottom:"2px solid var(--border,#e5e7eb)", background:"var(--bg,#fff)",
  });

  // Mode-driven COMP column label. v1.2 (May 2026): 4 modes.
  const activeCompLabel =
    mode === "fallen_angel"      ? "COMP (FA)" :
    mode === "compounder_us"     ? "CMP-US"    :
    mode === "compounder_global" ? "CMP-GL"    :
                                   "COMP (MOM)";
  // "Other comp" column has been retired in v1.2: with 4 modes the "other"
  // concept becomes ambiguous (3 candidates, not 1). Users switch modes to
  // compare; or open the stock detail page which shows all 4 modes' scores.

  // Cohort pills: scope tabs above the table. "qualified" follows the active
  // mode; the others narrow to a specific basket flag regardless of mode.
  const cohortPills:[string,string][] = [
    ["qualified", `${mode === "fallen_angel" ? "FA-qualified" : mode === "compounder_us" ? "CMP-US qualified" : mode === "compounder_global" ? "CMP-GL qualified" : "Mom-qualified"}`],
    ["all",       "All scanned"],
    ["fa_flagged","FA flagged"],
    ["cmp_us",    "Compounder US"],
    ["cmp_global","Compounder GL"],
  ];

  return(
    <div style={{display: "flex"}}>
      <div style={{flex: 1, padding:"20px 24px",maxWidth:1440,margin:"0 auto", minWidth: 0}}>
      {/* Header */}
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:8}}>
        <div>
          <p style={{fontSize:13,color:"var(--text)",fontFamily:"var(--font-mono)",fontWeight:700,marginBottom:2}}>
            CB Screener · {stocks.length} stocks · Global
          </p>
          <p style={{fontSize:11,color:"var(--text-muted)",fontFamily:"var(--font-mono)"}}>
            {scanDate} · v8 5-factor composite
          </p>
        </div>
        <div style={{display:"flex",flexDirection:"column",alignItems:"flex-end",gap:6}}>
          <ModeToggle mode={mode} onChange={setMode}/>
          <div style={{fontSize:9,color:"var(--text-light)",textAlign:"right",fontFamily:"var(--font-mono)",lineHeight:1.5}}>
            {FACTOR_ORDER.map(k=>`${FACTOR_LABELS[k]} ${FACTOR_WEIGHTS[k]}%`).join(" · ")}
          </div>
        </div>
      </div>

      {/* Macro ribbon — situational only */}
      <MacroRibbon macro={data?.macro}/>

      {/* v1.2 (May 2026): two-row filter strip.
          Row 1: search + sort status (unchanged from F2a)
          Row 2: cohort pills + sector multi-select + country multi-select */}
      <div style={{display:"flex",gap:10,marginBottom:8,marginTop:16,flexWrap:"wrap",alignItems:"center"}}>
        <div style={{position:"relative",flex:1,maxWidth:280}}>
          <Search size={14} style={{position:"absolute",left:10,top:"50%",transform:"translateY(-50%)",color:"var(--text-light)"}}/>
          <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search symbol or company..."
            style={{width:"100%",padding:"7px 10px 7px 32px",fontSize:12,fontFamily:"var(--font-mono)",
                    border:"1px solid var(--border)",borderRadius:6,background:"var(--bg)",color:"var(--text)",outline:"none"}}/>
        </div>
        <div style={{fontSize:10,color:"var(--text-light)",fontFamily:"var(--font-mono)"}}>
          Sorted by: <span style={{color:"var(--green,#2d7a4f)",fontWeight:700}}>{sortKey.replace(/_/g," ").toUpperCase()}</span> {sortDir === "desc" ? "↓" : "↑"}
        </div>
      </div>

      {/* Filter row 2: cohort pills + multi-select dropdowns */}
      <div style={{display:"flex",gap:10,marginBottom:12,flexWrap:"wrap",alignItems:"center"}}>
        {/* Cohort pills */}
        <div style={{display:"inline-flex",gap:0,border:"1px solid var(--border,#e5e7eb)",borderRadius:6,overflow:"hidden",background:"#fff"}}>
          {cohortPills.map(([k,l],i)=>{
            const active = cohortFilter === k;
            return(
              <button key={k} onClick={()=>setCohortFilter(k)} disabled={!!search}
                title={search ? "Filters bypassed while searching" : `Scope: ${l}`}
                style={{
                  padding:"5px 10px",
                  border:"none",
                  borderRight: i < cohortPills.length-1 ? "1px solid var(--border,#e5e7eb)" : "none",
                  cursor: search ? "not-allowed" : "pointer",
                  background: active && !search ? "var(--green,#2d7a4f)" : "transparent",
                  color: active && !search ? "#fff" : (search ? "var(--text-light)" : "var(--text)"),
                  fontSize:10,fontFamily:"var(--font-mono)",fontWeight:600,letterSpacing:"0.03em",
                  opacity: search ? 0.5 : 1,
                }}>
                {l}
              </button>
            );
          })}
        </div>

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
        {(sectorFilter.length > 0 || countryFilter.length > 0 || cohortFilter !== "qualified") && !search && (
          <button onClick={()=>{setSectorFilter([]); setCountryFilter([]); setCohortFilter("qualified");}}
            style={{padding:"5px 10px",border:"1px solid var(--border,#e5e7eb)",borderRadius:6,
                    cursor:"pointer",background:"transparent",color:"var(--text-muted)",
                    fontSize:10,fontFamily:"var(--font-mono)",fontWeight:600}}>
            Clear filters
          </button>
        )}
      </div>

      {/* Table */}
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
              <th style={hs("active_comp")} onClick={()=>toggleSort("active_comp")} title={`Composite for the active mode (${mode === "fallen_angel" ? "Fallen Angel" : mode === "compounder_us" ? "Compounder US" : mode === "compounder_global" ? "Compounder Global" : "Momentum"}). Sortable.`}>{activeCompLabel}</th>
              {/* v1.2 (May 2026): "COMP other" column dropped. 4-mode world
                  makes "other" ambiguous — users switch modes to compare or
                  open stock detail page (shows all 4 modes' scores). */}
              <th style={hs("upside")} onClick={()=>toggleSort("upside")} title="Analyst consensus upside %. Sub-component of v8 Value.">UPSIDE</th>
              <th style={hs("smart_money","center")} onClick={()=>toggleSort("smart_money")} title="Smart Money Score: weighted sum of institutional flow (25%), trend strength (23%), institutional accumulation (20%), PT velocity (10%), quality (10%), sector momentum (7%), congressional (5%). Pass-2 only; US-only. No weight redistribution — missing factors don't contribute, so the displayed value is also the ceiling of what the data allowed.">SMART$</th>
              <th style={hs("hit_prob","center")} onClick={()=>toggleSort("hit_prob")} title="P(+20% daily high in 4 weeks) — ML ensemble model (AUC 0.78). High P20 + Low IVR = underpriced options. D10 stocks hit 26% of the time.">P20</th>
              <th style={{...hs("static","center"),cursor:"default"}} title="Implied Volatility Rank — where current IV sits in trailing 60d. Top-30 only; 20+ days of IV history needed for rank.">IVR</th>
              {/* v1.2 (May 2026): dropped 4 columns — VAL, GRW, QUAL (v8 sub-factor
                  scores; shown alongside COMP they fed = redundant), and GAIN/DD
                  (static lookup-table band; same for every stock in a composite
                  bucket = useless). Composite now stands on its own; users open
                  the stock detail page for sub-factor breakdowns. */}
            </tr></thead>
            <tbody>{sorted.map((s,idx)=><StockRow key={s.symbol} stock={s} mode={mode} rank={idx+1} expanded={!!expanded[s.symbol]} onToggle={()=>setExpanded(e=>({...e,[s.symbol]:!e[s.symbol]}))}/>)}</tbody>
          </table>
        </div>
        {sorted.length===0&&<div style={{textAlign:"center",padding:40,color:"var(--text-muted)",fontSize:13,fontFamily:"var(--font-mono)"}}>No stocks match this filter</div>}
      </div>
      <div style={{textAlign:"center",marginTop:14,fontSize:10,color:"var(--text-light)",fontFamily:"var(--font-mono)"}}>
        {stocks.length} screened · {sorted.length} shown{hiddenCount>0?` · ${hiddenCount} excluded by ${mode==="fallen_angel"?"FA":mode==="compounder_us"?"CMP-US":mode==="compounder_global"?"CMP-GL":"Momentum"} gate`:""}{cohortFilter !== "qualified" && cohortFilter !== "all" ? ` · cohort: ${cohortFilter.replace(/_/g," ")}` : ""}{sectorFilter.length > 0 ? ` · sectors: ${sectorFilter.length}` : ""}{countryFilter.length > 0 ? ` · countries: ${countryFilter.length}` : ""} · click row to expand · click any column header to sort
      </div>
      <SectorConcentration data={data?.sector_concentration}/>
      </div>
      <Watchlist />
    </div>
  );
}
