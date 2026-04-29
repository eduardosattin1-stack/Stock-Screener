"use client";
import { useState, useEffect, useMemo } from "react";
import { TrendingUp, ChevronDown, ChevronRight, Target, Search, Zap, Copy, CheckCircle2, ArrowRight, Clock } from "lucide-react";

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
interface MacroData { regime:"RISK_ON"|"NEUTRAL"|"CAUTIOUS"|"RISK_OFF"; score:number; sub_scores:{ yield_curve:number; yield_level:number; vix:number; cpi_trend:number; gdp_momentum:number; }; }
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
  composite:number; signal:string; classification:string; reasons:string[];
  factor_scores?:FactorScores;
  // v7 fields kept on the wire (diagnostic only, no longer drive composite)
  quality_score?:number; catalyst_score?:number; catalyst_flags?:string[];
  has_catalyst?:boolean; days_to_earnings?:number;
  insider_score?:number; insider_net_buys?:number;
  transcript_sentiment?:number; transcript_summary?:string; transcript_score?:number;
  inst_score?:number; proximity_score?:number; earnings_score?:number;
  upside_score?:number;
  hit_prob?:number;
  factor_coverage?:number;
  factors_evaluated?:string[];
  factors_missing?:string[];
  // v7.2.1 Tradier options enrichment (top-30 US stocks only)
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
  signal_fallen_angel?:string;
  factors_v8?:FactorsV8;
  factors_v8_momentum?:FactorsV8;
  factors_v8_fallen_angel?:FactorsV8;
  composite_v7?:number;
  // v8 derived fields available on the row (used in expanded panel)
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

// getProb: fallback table for stocks without live hit_prob field (rare).
// Numbers are rough approximations from v7.2 backtest calibration — the live ML
// model's `hit_prob` on each stock is more accurate. See calibration docs.
function getProb(c:number){if(c>=0.90)return{p10:85,gain:25.7,dd:-9.1,speed:18};if(c>=0.80)return{p10:75,gain:20.0,dd:-9.8,speed:22};if(c>=0.65)return{p10:62,gain:15.0,dd:-10.5,speed:26};if(c>=0.50)return{p10:50,gain:12.0,dd:-11.0,speed:30};return{p10:35,gain:9.0,dd:-11.0,speed:32};}

// v8 mode-aware factor reader. Falls back to s.factors_v8 (no per-mode
// breakdown) for stocks scanned before the dual-mode deploy. Last-resort
// fallback returns an all-null FactorsV8 so the radar still renders five
// dashed/empty axes rather than crashing.
function readFactorsV8(s:StockData, mode:string):FactorsV8 {
  const f = mode === "fallen_angel" ? (s.factors_v8_fallen_angel ?? s.factors_v8) : (s.factors_v8_momentum ?? s.factors_v8);
  if (f) return f;
  return { momentum:null, quality:null, growth:null, value:null, smart_money:null };
}
// Pull the active-mode composite, falling back to s.composite when the
// dual-mode fields are absent (older scan JSON).
function readComposite(s:StockData, mode:string):number {
  if (mode === "fallen_angel") return s.composite_fallen_angel ?? s.composite ?? 0;
  return s.composite_momentum ?? s.composite ?? 0;
}
function readSignal(s:StockData, mode:string):string {
  if (mode === "fallen_angel") return s.signal_fallen_angel ?? s.signal ?? "HOLD";
  return s.signal_momentum ?? s.signal ?? "HOLD";
}

// v8 universe gate: a stock passes the gate for a mode iff its signal for
// that mode is not "DISQUALIFIED". The backend writes "DISQUALIFIED" for
// stocks failing the structural setup test (Momentum: trend intact + not
// extended; Fallen Angel: deep drawdown + below SMA200 + Pio≥7 + Z>2.5 +
// ROE>12% + cap>$2B). For older scan JSON without per-mode signals the
// fallback is to assume qualified — better to over-show than under-show
// during the migration window.
function isQualified(s:StockData, mode:string):boolean {
  const sig = mode === "fallen_angel" ? s.signal_fallen_angel : s.signal_momentum;
  // Fallback: if per-mode signal is absent (legacy scan), let the row through
  if (sig == null) return true;
  return sig !== "DISQUALIFIED";
}

// ── ModeToggle (v8) ─────────────────────────────────────────────────────────
// Switches the entire table between Momentum and Fallen Angel views. Each
// stock has both composites computed at scan time, so toggling is purely a
// view state — no re-fetch. Default mode is Momentum (matches screener-table
// historical convention; sort by FA composite by clicking the header).
function ModeToggle({mode,onChange}:{mode:string;onChange:(m:string)=>void}){
  const opts = [{k:"momentum",l:"Momentum"},{k:"fallen_angel",l:"Fallen Angel"}];
  return(
    <div style={{display:"inline-flex",border:"1px solid var(--border,#e5e7eb)",borderRadius:6,overflow:"hidden",background:"#fff"}}>
      {opts.map(o=>{
        const active = o.k === mode;
        return(
          <button key={o.k} onClick={()=>onChange(o.k)} style={{
            padding:"6px 14px",border:"none",cursor:"pointer",
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
function MacroRibbon({macro}:{macro?:MacroData}){
  if(!macro) return null;
  const subs=macro.sub_scores||{};
  const items:[string,number|undefined][]=[
    ["Yield curve", subs.yield_curve],
    ["VIX", subs.vix],
    ["CPI", subs.cpi_trend],
    ["GDP", subs.gdp_momentum],
  ];
  const items_present = items.filter(([_,v])=>v!=null);
  if(items_present.length === 0) return null;
  return(
    <div style={{display:"flex",alignItems:"center",gap:18,padding:"6px 14px",marginBottom:14,background:"transparent",borderTop:"1px solid var(--border-subtle,#eef1ef)",borderBottom:"1px solid var(--border-subtle,#eef1ef)"}}>
      <span style={{fontSize:9,fontFamily:"var(--font-mono)",color:"var(--text-light,#9ca3af)",fontWeight:600,letterSpacing:"0.1em"}}>MACRO</span>
      {items_present.map(([label,val])=>{
        const v = val ?? 0;
        const c = v>0.6 ? "#10b981" : v>0.4 ? "#d97706" : "#ef4444";
        return(
          <div key={label} style={{display:"flex",alignItems:"center",gap:6}}>
            <div style={{width:5,height:5,borderRadius:"50%",background:c,opacity:0.85}}/>
            <span style={{fontSize:9,fontFamily:"var(--font-mono)",color:"var(--text-muted,#6b7280)"}}>{label}</span>
          </div>
        );
      })}
      <span style={{fontSize:8,fontFamily:"var(--font-mono)",color:"var(--text-light,#9ca3af)",marginLeft:"auto",fontStyle:"italic"}}>situational only — strategy is regime-agnostic</span>
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
  // v8 mode-aware bindings. The user's mode toggle drives which composite,
  // signal, and factor radar appear in the row. The "other" composite is
  // shown in a small permanent column so divergences between modes pop
  // visually without forcing a toggle flip.
  const scoresActive = readFactorsV8(s, mode);
  const scoresOther = readFactorsV8(s, mode === "fallen_angel" ? "momentum" : "fallen_angel");
  const compActive = readComposite(s, mode);
  const otherMode = mode === "fallen_angel" ? "momentum" : "fallen_angel";
  const compOther = readComposite(s, otherMode);
  const otherLabel = mode === "fallen_angel" ? "Mom" : "FA";
  // Only flag a divergence chip when the OTHER mode also qualifies the stock
  // (otherwise the chip would point at a 0.0 disqualified composite, which
  // is meaningless and was misleading users into thinking NVDA was a fallen
  // angel candidate). Magnitude threshold ≥0.10 unchanged.
  const otherQualifies = isQualified(s, otherMode);
  const otherIsHigher = otherQualifies && (compOther - compActive >= 0.10);
  // hit_prob currently keys off the `composite` field which the backend
  // sets to the Momentum composite by default (Option B convention). When
  // FA mode is active the displayed P+10% lags slightly on FA-leaning
  // stocks; acceptable because the ML model was trained on the v7 composite
  // anyway. Document in tooltip rather than re-engineer.
  const isLive = s.hit_prob != null && s.hit_prob > 0;
  const p10 = isLive ? Math.round(s.hit_prob! * 100) : getProb(compActive).p10;
  const probFallback = getProb(compActive);

  return(
    <>
      <tr onClick={onToggle} style={{cursor:"pointer",borderBottom:"1px solid var(--border-subtle,#eef1ef)",transition:"background 0.12s",borderLeft:"3px solid transparent"}}
        onMouseEnter={e=>{(e.currentTarget as HTMLElement).style.background="var(--bg-hover,#f0f4f1)";}}
        onMouseLeave={e=>{(e.currentTarget as HTMLElement).style.background="";}}>
        {/* SYMBOL + sector + mini radar (5-axis active mode) */}
        <td style={{padding:"10px 12px"}}>
          <div style={{display:"flex",alignItems:"center",gap:8}}>
            {expanded?<ChevronDown size={13} color="var(--text-light,#9ca3af)"/>:<ChevronRight size={13} color="var(--text-light,#9ca3af)"/>}
            <MiniRadar scores={scoresActive}/>
            <div>
              <div style={{display:"flex",alignItems:"center",gap:6}}>
                <a href={`/stock/${s.symbol}`} onClick={e=>e.stopPropagation()} style={{fontWeight:700,letterSpacing:"0.04em",color:"var(--text,#1a1a1a)",fontSize:13,fontFamily:"var(--font-mono)"}}>{s.symbol}</a>
                {s.has_catalyst&&<Zap size={10} color="#8b5cf6" fill="#8b5cf6"/>}
                {otherIsHigher&&<span style={{fontSize:8,padding:"1px 5px",borderRadius:3,background:"#fffbeb",color:"#d97706",fontFamily:"var(--font-mono)",fontWeight:700,border:"1px solid #fde68a"}} title={`${otherLabel} composite is ${(compOther-compActive).toFixed(2)} higher — switch mode to compare`}>↻ {otherLabel}+{(compOther-compActive).toFixed(2)}</span>}
              </div>
              {s.sector&&<div style={{fontSize:9,fontFamily:"var(--font-mono)",color:"var(--text-light,#9ca3af)",marginTop:1}}>{s.sector}{s.industry?` / ${s.industry}`:""}</div>}
            </div>
          </div>
        </td>
        {/* PRICE */}
        <td style={{fontFamily:"var(--font-mono)",textAlign:"right",padding:"10px 12px",color:"var(--text)",fontSize:12}}>{s.currency!=="USD"&&<span style={{fontSize:9,color:"var(--text-light)",marginRight:3}}>{s.currency}</span>}${s.price?.toFixed(2)}</td>
        {/* PIO — diagnostic only (not in v8 composite) */}
        <td style={{fontFamily:"var(--font-mono)",textAlign:"center",padding:"10px 6px",fontSize:11,fontWeight:600,color:s.piotroski<=3?"#92400e":"var(--text-muted,#6b7280)"}} title="Piotroski 0-9 — diagnostic only, not in v8 composite">
          {s.piotroski}
        </td>
        {/* COMP (active mode) — primary, larger, colored by score */}
        <td style={{padding:"10px 8px",textAlign:"right",fontFamily:"var(--font-mono)",fontSize:13,color:compActive>0.7?"#10b981":compActive>0.5?"var(--text)":compActive>0.3?"var(--text-muted)":"#ef4444",fontWeight:700}}>
          {compActive.toFixed(2)}
        </td>
        {/* COMP (other mode) — secondary, smaller, amber if it's leading.
            Shows "—" when the other mode disqualifies this stock. */}
        <td style={{padding:"10px 8px",textAlign:"right",fontFamily:"var(--font-mono)",fontSize:11,color:otherIsHigher?"#d97706":"var(--text-light,#9ca3af)",fontWeight:otherIsHigher?700:500}}
          title={otherQualifies?`${otherLabel} composite — ${otherIsHigher?"leads active mode by ≥0.10":"trails active mode"}`:`${otherLabel} mode disqualifies this stock (failed setup gate)`}>
          {otherQualifies ? compOther.toFixed(2) : "—"}
        </td>
        {/* VALUE — sub-factor score from v8 Value (replaces DCF MoS) */}
        <td style={{padding:"10px 8px",textAlign:"center",fontFamily:"var(--font-mono)",fontSize:11}}>
          {(()=>{const v = scoresActive.value;
            if (v == null) return <span style={{color:"var(--text-light,#9ca3af)"}}>—</span>;
            const c = v>0.7?"#10b981":v>0.5?"var(--text-muted)":v>0.3?"#d97706":"#ef4444";
            return <span style={{color:c,fontWeight:700}}>{(v*100).toFixed(0)}</span>;})()}
        </td>
        {/* GROWTH — v8 Growth factor score */}
        <td style={{padding:"10px 8px",textAlign:"center",fontFamily:"var(--font-mono)",fontSize:11}}>
          {(()=>{const g = scoresActive.growth;
            if (g == null) return <span style={{color:"var(--text-light,#9ca3af)"}}>—</span>;
            const c = g>0.7?"#10b981":g>0.5?"var(--text-muted)":g>0.3?"#d97706":"#ef4444";
            return <span style={{color:c,fontWeight:700}}>{(g*100).toFixed(0)}</span>;})()}
        </td>
        {/* QUALITY — v8 Quality factor score */}
        <td style={{padding:"10px 8px",textAlign:"center",fontFamily:"var(--font-mono)",fontSize:11}}>
          {(()=>{const q = scoresActive.quality;
            if (q == null) return <span style={{color:"var(--text-light,#9ca3af)"}}>—</span>;
            const c = q>0.7?"#10b981":q>0.5?"var(--text-muted)":q>0.3?"#d97706":"#ef4444";
            return <span style={{color:c,fontWeight:700}}>{(q*100).toFixed(0)}</span>;})()}
        </td>
        {/* UPSIDE — analyst consensus (v8 Value sub-component, kept for reference) */}
        <td style={{fontFamily:"var(--font-mono)",textAlign:"right",padding:"10px 12px",fontSize:12,color:s.upside>20?"#10b981":s.upside>0?"var(--text-muted)":"#ef4444",fontWeight:600}}>{s.upside>0?"+":""}{s.upside?.toFixed(0)}%</td>
        {/* P+10% — labeled experimental */}
        <td style={{fontFamily:"var(--font-mono)",textAlign:"center",padding:"10px 6px",fontSize:11,fontWeight:700,color:p10>60?"#10b981":p10>40?"#d97706":"#ef4444"}} title="ML probability of touching +10% within prediction window. Trained on legacy v7 composite — slight lag on FA-mode-leaning stocks.">
          {p10}%{isLive&&<span style={{fontSize:7,color:"var(--text-light)",marginLeft:2}}>ml</span>}
        </td>
        {/* IVR — Implied Volatility Rank (top-30 only, needs 20+ days IV history) */}
        <td style={{fontFamily:"var(--font-mono)",textAlign:"center",padding:"10px 6px",fontSize:11}}>
          {(()=>{
            const ivr=s.tradier_iv_rank;
            const iv=s.tradier_iv_current;
            const samples=s.tradier_iv_samples||0;
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
        {/* GAIN/DD */}
        <td style={{fontFamily:"var(--font-mono)",textAlign:"right",padding:"10px 12px",fontSize:11}}>
          <span style={{color:"#10b981",fontWeight:600}}>+{probFallback.gain}%</span>
          <span style={{color:"var(--text-light,#9ca3af)",margin:"0 2px"}}>/</span>
          <span style={{color:"#ef4444",fontWeight:600}}>{probFallback.dd}%</span>
        </td>
      </tr>
      {expanded&&(
        <tr><td colSpan={12} style={{padding:0,background:"var(--bg-surface,#f8faf9)"}}>
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
                {compOther>0&&(
                  <div style={{marginTop:10,padding:"8px 12px",borderRadius:5,background:otherIsHigher?"#fffbeb":"#f8faf9",border:`1px solid ${otherIsHigher?"#fde68a":"var(--border-subtle,#eef1ef)"}`,fontSize:10,fontFamily:"var(--font-mono)",color:"var(--text-muted,#6b7280)",lineHeight:1.5}}>
                    <span style={{fontWeight:700,color:otherIsHigher?"#d97706":"var(--text)"}}>{otherLabel} composite: {compOther.toFixed(2)}</span>
                    {otherIsHigher && <span style={{marginLeft:6,color:"#d97706"}}>— leads active mode by {(compOther-compActive).toFixed(2)}, worth checking the {otherLabel==="FA"?"Fallen Angel":"Momentum"} view</span>}
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
  | "symbol" | "price" | "piotroski"
  | "active_comp" | "other_comp"
  | "value_score" | "growth_score" | "quality_score"
  | "upside";

export default function Dashboard(){
  const [data,setData]=useState<ScanData|null>(null);
  const [loading,setLoading]=useState(true);

  // v8: mode toggle drives entire table view (sort target, displayed
  // composite, radar, factor breakdown). Persisted to localStorage so the
  // user's preference survives reloads.
  const [mode,setMode]=useState<string>("momentum");
  useEffect(()=>{
    if (typeof window === "undefined") return;
    const saved = window.localStorage.getItem("cb_screener_mode");
    if (saved === "fallen_angel" || saved === "momentum") setMode(saved);
  },[]);
  useEffect(()=>{
    if (typeof window !== "undefined") window.localStorage.setItem("cb_screener_mode", mode);
  },[mode]);

  const [sortKey,setSortKey]=useState<SortKey>("active_comp");
  const [sortDir,setSortDir]=useState<"asc"|"desc">("desc");
  const [search,setSearch]=useState("");
  const [expanded,setExpanded]=useState<Record<string,boolean>>({});

  useEffect(()=>{
    setLoading(true);
    fetch(`${GCS_BASE}/latest_sp500.json?t=${Date.now()}`)
      .then(r=>r.ok?r.json():null)
      .then(d=>{ setData(d); setLoading(false); })
      .catch(()=>{ setLoading(false); });
  },[]);

  const stocks: StockData[] = data?.stocks || [];

  // Sort key extractor. Mode-aware so that toggling the mode re-ranks
  // the table without changing the sort key. "active_comp" follows the
  // selected mode; "other_comp" follows whichever isn't selected.
  const extract = (s:StockData, key:SortKey):number => {
    const fA = readFactorsV8(s, mode);
    const otherMode = mode === "fallen_angel" ? "momentum" : "fallen_angel";
    switch(key){
      case "active_comp":   return readComposite(s, mode);
      case "other_comp":    return readComposite(s, otherMode);
      case "value_score":   return fA.value ?? -1;
      case "growth_score":  return fA.growth ?? -1;
      case "quality_score": return fA.quality ?? -1;
      case "piotroski":     return s.piotroski ?? 0;
      case "upside":        return s.upside ?? 0;
      case "price":         return s.price ?? 0;
      case "symbol":        return s.symbol.charCodeAt(0); // alphabetic via numeric proxy
      default:              return 0;
    }
  };

  const sorted = useMemo(()=>{
    let list = [...stocks];
    if (search) {
      const q = search.toUpperCase();
      list = list.filter(s => s.symbol.includes(q) || (s.company_name||"").toUpperCase().includes(q));
    }
    // v8 universe gate filter: hide stocks the active mode disqualifies
    // (signal === "DISQUALIFIED"). Sort key "other_comp" is excluded from
    // gating because it ranks by the inactive mode — the user explicitly
    // wants to see the FA list while the active mode is Momentum, etc.
    // Search overrides the gate too — if the user searched for a specific
    // symbol they want to find it whether it qualifies or not.
    if (!search && sortKey !== "other_comp") {
      list = list.filter(s => isQualified(s, mode));
    }
    if (sortKey === "symbol") {
      list.sort((a,b)=>{
        const cmp = a.symbol.localeCompare(b.symbol);
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
  },[stocks, sortKey, sortDir, search, mode]);

  // Hidden count for footer transparency. We compute this only when the
  // gate filter is active (no search, normal sort), otherwise it would
  // confusingly report "0 hidden" while showing disqualified stocks.
  const hiddenCount = useMemo(()=>{
    if (search || sortKey === "other_comp") return 0;
    return stocks.filter(s => !isQualified(s, mode)).length;
  },[stocks, search, sortKey, mode]);

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

  // Mode-driven column labels
  const activeCompLabel = mode === "fallen_angel" ? "COMP (FA)" : "COMP (MOM)";
  const otherCompLabel  = mode === "fallen_angel" ? "MOM" : "FA";

  return(
    <div style={{padding:"20px 24px",maxWidth:1440,margin:"0 auto"}}>
      {/* Header */}
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:8}}>
        <div>
          <p style={{fontSize:13,color:"var(--text)",fontFamily:"var(--font-mono)",fontWeight:700,marginBottom:2}}>
            CB Screener · {stocks.length} stocks · S&P 500
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

      {/* Filters — search only */}
      <div style={{display:"flex",gap:10,marginBottom:12,marginTop:16,flexWrap:"wrap",alignItems:"center"}}>
        <div style={{position:"relative",flex:1,maxWidth:280}}>
          <Search size={14} style={{position:"absolute",left:10,top:"50%",transform:"translateY(-50%)",color:"var(--text-light)"}}/>
          <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search symbol..."
            style={{width:"100%",padding:"7px 10px 7px 32px",fontSize:12,fontFamily:"var(--font-mono)",
                    border:"1px solid var(--border)",borderRadius:6,background:"var(--bg)",color:"var(--text)",outline:"none"}}/>
        </div>
        <div style={{fontSize:10,color:"var(--text-light)",fontFamily:"var(--font-mono)"}}>
          Sorted by: <span style={{color:"var(--green,#2d7a4f)",fontWeight:700}}>{sortKey.replace("_"," ").toUpperCase()}</span> {sortDir === "desc" ? "↓" : "↑"}
        </div>
      </div>

      {/* Table */}
      <div style={{background:"var(--bg)",borderRadius:8,border:"1px solid var(--border)",overflow:"hidden",boxShadow:"0 1px 3px rgba(0,0,0,0.06)"}}>
        <div style={{overflowX:"auto"}}>
          <table style={{width:"100%",borderCollapse:"collapse",fontSize:13}}>
            <thead><tr>
              <th style={hs("symbol","left")} onClick={()=>toggleSort("symbol")}>SYMBOL</th>
              <th style={hs("price")} onClick={()=>toggleSort("price")}>PRICE</th>
              <th style={hs("piotroski","center")} onClick={()=>toggleSort("piotroski")} title="Piotroski 0-9 — diagnostic only, not in v8 composite">PIO</th>
              <th style={hs("active_comp")} onClick={()=>toggleSort("active_comp")} title={`Composite for the active mode (${mode === "fallen_angel" ? "Fallen Angel" : "Momentum"}). Sortable.`}>{activeCompLabel}</th>
              <th style={hs("other_comp")} onClick={()=>toggleSort("other_comp")} title={`Composite for the inactive mode. Sortable — click to rank by ${otherCompLabel === "FA" ? "Fallen Angel" : "Momentum"} composite without switching the view.`}>{otherCompLabel}</th>
              <th style={hs("value_score","center")} onClick={()=>toggleSort("value_score")} title="v8 Value factor score: intrinsic upside (40%) + P/FCF (30%) + earnings yield (30%)">VAL</th>
              <th style={hs("growth_score","center")} onClick={()=>toggleSort("growth_score")} title="v8 Growth factor score: revenue + EPS + FCF, each 60% TTM YoY + 40% 3y CAGR">GRW</th>
              <th style={hs("quality_score","center")} onClick={()=>toggleSort("quality_score")} title="v8 Quality factor score: net margin (35%) + FCF margin (35%) + ROIC (30%)">QUAL</th>
              <th style={hs("upside")} onClick={()=>toggleSort("upside")} title="Analyst consensus upside %. Sub-component of v8 Value.">UPSIDE</th>
              <th style={{...hs("static","center"),cursor:"default"}} title="ML probability of touching +10%. Trained on legacy v7 composite.">P+10% ml</th>
              <th style={{...hs("static","center"),cursor:"default"}} title="Implied Volatility Rank — where current IV sits in trailing 60d. Top-30 only; 20+ days of IV history needed for rank.">IVR</th>
              <th style={{...hs("static","right"),cursor:"default"}}>GAIN/DD</th>
            </tr></thead>
            <tbody>{sorted.map((s,idx)=><StockRow key={s.symbol} stock={s} mode={mode} rank={idx+1} expanded={!!expanded[s.symbol]} onToggle={()=>setExpanded(e=>({...e,[s.symbol]:!e[s.symbol]}))}/>)}</tbody>
          </table>
        </div>
        {sorted.length===0&&<div style={{textAlign:"center",padding:40,color:"var(--text-muted)",fontSize:13,fontFamily:"var(--font-mono)"}}>No stocks match this filter</div>}
      </div>
      <div style={{textAlign:"center",marginTop:14,fontSize:10,color:"var(--text-light)",fontFamily:"var(--font-mono)"}}>
        {stocks.length} screened · {sorted.length} shown{hiddenCount>0?` · ${hiddenCount} hidden by ${mode==="fallen_angel"?"FA":"Momentum"} setup gate`:""} · click row to expand · click any column header to sort
      </div>
      <SectorConcentration data={data?.sector_concentration}/>
    </div>
  );
}
