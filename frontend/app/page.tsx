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
  // v7 fields
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

// v7 factor config
// v7.2 factor config — 13 factors, ordered by weight for natural radar clockwise reading
const FACTOR_ORDER = ["technical","upside","quality","proximity","institutional_flow","transcript","earnings","catalyst","institutional","sector_momentum","analyst","insider","congressional"];
// Short labels (≤10 chars) so radar vertex labels don't overlap at 13 vertices
const FACTOR_LABELS: Record<string,string> = { technical:"Technical", quality:"Quality", proximity:"52-Week", catalyst:"Catalyst", transcript:"Transcript", upside:"Upside", institutional:"Inst Hold", analyst:"Analyst", insider:"Insider", earnings:"Earnings", institutional_flow:"Inst Flow", sector_momentum:"Sector Mom", congressional:"Congress" };
// v7.2 weights from 45K-sample backtest (tech capped at 25%)
const FACTOR_WEIGHTS: Record<string,number> = { technical:25, upside:14, quality:12, proximity:12, institutional_flow:9, transcript:6, earnings:5, catalyst:5, institutional:3, sector_momentum:3, analyst:3, insider:2, congressional:1 };

// ── Helpers ─────────────────────────────────────────────────────────────────
const fmtPct = (n:number|null|undefined) => n==null?"—":`${(n*100).toFixed(0)}%`;
const fmtMcap = (n:number|null|undefined) => { if(n==null) return "—"; if(n>=1e12) return `$${(n/1e12).toFixed(1)}T`; if(n>=1e9) return `$${(n/1e9).toFixed(0)}B`; if(n>=1e6) return `$${(n/1e6).toFixed(0)}M`; return `$${n.toFixed(0)}`; };

// getProb: fallback table for stocks without live hit_prob field (rare).
// Numbers are rough approximations from v7.2 backtest calibration — the live ML
// model's `hit_prob` on each stock is more accurate. See calibration docs.
function getProb(c:number){if(c>=0.90)return{p10:85,gain:25.7,dd:-9.1,speed:18};if(c>=0.80)return{p10:75,gain:20.0,dd:-9.8,speed:22};if(c>=0.65)return{p10:62,gain:15.0,dd:-10.5,speed:26};if(c>=0.50)return{p10:50,gain:12.0,dd:-11.0,speed:30};return{p10:35,gain:9.0,dd:-11.0,speed:32};}

function inferFactors(s:StockData):FactorScores {
  if(s.factor_scores) return s.factor_scores;
  return {
    technical: Math.min(1,(s.bull_score||0)/10),
    quality: s.quality_score ?? Math.min(1, ((s.piotroski||0)/9*0.4 + Math.min(1,(s.altman_z||0)/10)*0.2 + Math.min(1,(s.roe_avg||0)/0.3)*0.2 + Math.min(1,(s.gross_margin||0))*0.2)),
    upside: s.upside_score ?? Math.min(1,Math.max(0,(s.upside||0)/80)),
    proximity: s.proximity_score ?? (s.year_high>0?(s.price-s.year_low)/(s.year_high-s.year_low):0.5),
    catalyst: s.catalyst_score ?? 0.5,
    transcript: s.transcript_score ?? null,
    institutional: s.inst_score ?? null,
    analyst: s.grade_score || null,
    insider: s.insider_score ?? null,
    earnings: s.earnings_score ?? Math.min(1,(s.eps_beats||0)/Math.max(1,s.eps_total||1)),
    // v7.2 new factors — null when no factor_scores present (legacy scans, EU stocks, etc.)
    institutional_flow: null,
    sector_momentum: null,
    congressional: null,
  } as FactorScores;
}

// ── Mini Radar ──────────────────────────────────────────────────────────────
function MiniRadar({scores,size=44}:{scores:FactorScores;size?:number}){
  const cx=size/2,cy=size/2,r=size/2-4;const raw=FACTOR_ORDER.map(k=>(scores as any)[k]);const vals=raw.map(v=>v??0);const n=vals.length;
  const ang=(i:number)=>(Math.PI*2*i)/n-Math.PI/2;
  const evaluated=raw.filter(v=>v!=null);const avg=evaluated.length?evaluated.reduce((a:number,b:number)=>a+b,0)/evaluated.length:0;
  const fill=avg>0.6?"#2d7a4f":avg>0.4?"#d97706":"#ef4444";
  const data=vals.map((v,i)=>`${cx+Math.cos(ang(i))*Math.max(0.05,v)*r},${cy+Math.sin(ang(i))*Math.max(0.05,v)*r}`).join(" ");
  const grid=[0.33,0.66,1].map(lv=>Array.from({length:n},(_,i)=>`${cx+Math.cos(ang(i))*r*lv},${cy+Math.sin(ang(i))*r*lv}`).join(" "));
  return(
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {grid.map((p,i)=><polygon key={i} points={p} fill="none" stroke="#e2e8e4" strokeWidth={0.5} opacity={0.6}/>)}
      {Array.from({length:n},(_,i)=><line key={i} x1={cx} y1={cy} x2={cx+Math.cos(ang(i))*r} y2={cy+Math.sin(ang(i))*r} stroke="#e2e8e4" strokeWidth={0.4}/>)}
      <polygon points={data} fill={fill} fillOpacity={0.2} stroke={fill} strokeWidth={1.2} strokeLinejoin="round"/>
      {vals.map((v,i)=><circle key={i} cx={cx+Math.cos(ang(i))*Math.max(0.05,v)*r} cy={cy+Math.sin(ang(i))*Math.max(0.05,v)*r} r={1.5} fill={raw[i]==null?"#d1d5db":fill}/>)}
    </svg>
  );
}

// ── Large Radar for expanded row ────────────────────────────────────────────
function LargeRadar({scores,size=180}:{scores:FactorScores;size?:number}){
  const cx=size/2,cy=size/2,r=size/2-24;const raw=FACTOR_ORDER.map(k=>(scores as any)[k]);const vals=raw.map(v=>v??0);const n=vals.length;
  const ang=(i:number)=>(Math.PI*2*i)/n-Math.PI/2;
  const evaluated=raw.filter(v=>v!=null);const avg=evaluated.length?evaluated.reduce((a:number,b:number)=>a+b,0)/evaluated.length:0;
  const fill=avg>0.6?"#2d7a4f":avg>0.4?"#d97706":"#ef4444";
  return(
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {[0.25,0.5,0.75,1].map((lv,i)=>{const pts=Array.from({length:n},(_,j)=>`${cx+Math.cos(ang(j))*r*lv},${cy+Math.sin(ang(j))*r*lv}`).join(" ");return<polygon key={i} points={pts} fill="none" stroke="#d1d5db" strokeWidth={i===3?1:0.5} opacity={0.5}/>;})}
      {FACTOR_ORDER.map((k,i)=>{const a=ang(i),lx=cx+Math.cos(a)*(r+18),ly=cy+Math.sin(a)*(r+18),v=raw[i],isNull=v==null,c=isNull?"#d1d5db":((v??0)>0.7?"#2d7a4f":(v??0)>0.4?"#d97706":"#ef4444");return<g key={k}><line x1={cx} y1={cy} x2={cx+Math.cos(a)*r} y2={cy+Math.sin(a)*r} stroke="#d1d5db" strokeWidth={0.5} strokeDasharray={isNull?"2,2":"none"}/><text x={lx} y={ly} textAnchor="middle" dominantBaseline="middle" fontSize={6.5} fontFamily="var(--font-mono)" fill={isNull?"#d1d5db":"#6b7280"} fontWeight="500">{FACTOR_LABELS[k]}</text></g>;})}
      <polygon points={vals.map((v,i)=>`${cx+Math.cos(ang(i))*Math.max(0.05,v)*r},${cy+Math.sin(ang(i))*Math.max(0.05,v)*r}`).join(" ")} fill={fill} fillOpacity={0.15} stroke={fill} strokeWidth={1.5} strokeLinejoin="round"/>
      {vals.map((v,i)=><circle key={i} cx={cx+Math.cos(ang(i))*Math.max(0.05,v)*r} cy={cy+Math.sin(ang(i))*Math.max(0.05,v)*r} r={2.5} fill={raw[i]==null?"#d1d5db":fill} stroke="#fff" strokeWidth={1}/>)}
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

// ── Strategy status decoration (basket / bucket / universe) ────────────────
type StatusKind = "basket" | "bucket" | "universe";
interface StrategyDeco {
  status: StatusKind;
  basketRank?: number;        // rank in current basket (if basket)
  basketRegion?: "midcap"|"sp500"|"both";
  inMidcap?: boolean;          // present in latest_midcap.json
  inSp500?: boolean;           // present in latest_sp500.json
}
type StockWithDeco = StockData & { _deco?: StrategyDeco };

function StatusBadge({deco,piotroski}:{deco?:StrategyDeco;piotroski:number}){
  if(!deco){
    return <span style={{fontSize:9,color:"var(--text-light,#9ca3af)",fontFamily:"var(--font-mono)"}}>—</span>;
  }
  if(deco.status === "basket"){
    return(
      <span style={{display:"inline-flex",alignItems:"center",gap:4,padding:"2px 7px",borderRadius:4,fontSize:10,fontWeight:700,letterSpacing:"0.04em",fontFamily:"var(--font-mono)",background:"#e8f5ee",color:"#2d7a4f",border:"1px solid #b8dcc8"}}>
        ⭐ #{deco.basketRank}
      </span>
    );
  }
  if(deco.status === "bucket"){
    return(
      <span style={{display:"inline-flex",alignItems:"center",gap:4,padding:"2px 7px",borderRadius:4,fontSize:10,fontWeight:600,letterSpacing:"0.04em",fontFamily:"var(--font-mono)",background:"#fffbeb",color:"#92400e",border:"1px solid #fde68a"}}>
        ◐ Pio {piotroski}
      </span>
    );
  }
  return <span style={{fontSize:9,color:"var(--text-light,#9ca3af)",fontFamily:"var(--font-mono)"}}>—</span>;
}

function RegionBadge({deco}:{deco?:StrategyDeco}){
  if(!deco) return <span style={{fontSize:9,color:"var(--text-light,#9ca3af)",fontFamily:"var(--font-mono)"}}>—</span>;
  const inBoth = deco.inMidcap && deco.inSp500;
  const label = inBoth ? "M+S" : deco.inMidcap ? "M" : deco.inSp500 ? "S" : "—";
  const color = inBoth ? "#7c3aed" : deco.inMidcap ? "#2d7a4f" : deco.inSp500 ? "#4338ca" : "var(--text-light,#9ca3af)";
  const bg    = inBoth ? "#f5f3ff" : deco.inMidcap ? "#e8f5ee" : deco.inSp500 ? "#eef2ff" : "transparent";
  const bd    = inBoth ? "#ddd6fe" : deco.inMidcap ? "#b8dcc8" : deco.inSp500 ? "#c7d2fe" : "transparent";
  return(
    <span style={{display:"inline-block",padding:"1px 5px",borderRadius:3,fontSize:9,fontWeight:700,letterSpacing:"0.05em",fontFamily:"var(--font-mono)",background:bg,color,border:`1px solid ${bd}`}}>{label}</span>
  );
}

function StockRow({stock:s,expanded,onToggle,weights,rank}:{stock:StockWithDeco;expanded:boolean;onToggle:()=>void;weights:Record<string,number>;rank:number}){
  const scores=inferFactors(s);
  const isInBasket = s._deco?.status === "basket";
  const isLive=s.hit_prob!=null&&s.hit_prob>0;
  const p10=isLive?Math.round(s.hit_prob!*100):getProb(s.composite).p10;
  const probFallback=getProb(s.composite);
  return(
    <>
      <tr onClick={onToggle} style={{cursor:"pointer",borderBottom:"1px solid var(--border-subtle,#eef1ef)",transition:"background 0.12s",borderLeft:isInBasket?"3px solid #2d7a4f":"3px solid transparent"}}
        onMouseEnter={e=>{(e.currentTarget as HTMLElement).style.background="var(--bg-hover,#f0f4f1)";}}
        onMouseLeave={e=>{(e.currentTarget as HTMLElement).style.background="";}}>
        {/* SYMBOL + sector */}
        <td style={{padding:"10px 12px"}}>
          <div style={{display:"flex",alignItems:"center",gap:8}}>
            {expanded?<ChevronDown size={13} color="var(--text-light,#9ca3af)"/>:<ChevronRight size={13} color="var(--text-light,#9ca3af)"/>}
            <div>
              <div style={{display:"flex",alignItems:"center",gap:6}}>
                <a href={`/stock/${s.symbol}`} onClick={e=>e.stopPropagation()} style={{fontWeight:700,letterSpacing:"0.04em",color:"var(--text,#1a1a1a)",fontSize:13,fontFamily:"var(--font-mono)"}}>{s.symbol}</a>
                {s.has_catalyst&&<Zap size={10} color="#8b5cf6" fill="#8b5cf6"/>}
              </div>
              {s.sector&&<div style={{fontSize:9,fontFamily:"var(--font-mono)",color:"var(--text-light,#9ca3af)",marginTop:1}}>{s.sector}{s.industry?` / ${s.industry}`:""}</div>}
            </div>
          </div>
        </td>
        {/* STATUS — basket / bucket / universe */}
        <td style={{padding:"10px 8px",textAlign:"center"}}>
          <StatusBadge deco={s._deco} piotroski={s.piotroski}/>
        </td>
        {/* REGION badge */}
        <td style={{padding:"10px 6px",textAlign:"center"}}>
          <RegionBadge deco={s._deco}/>
        </td>
        {/* PRICE */}
        <td style={{fontFamily:"var(--font-mono)",textAlign:"right",padding:"10px 12px",color:"var(--text)",fontSize:12}}>{s.currency!=="USD"&&<span style={{fontSize:9,color:"var(--text-light)",marginRight:3}}>{s.currency}</span>}${s.price?.toFixed(2)}</td>
        {/* PIO — the bucket-defining factor */}
        <td style={{fontFamily:"var(--font-mono)",textAlign:"center",padding:"10px 6px",fontSize:11,fontWeight:600,color:s.piotroski<=3?"#92400e":"var(--text-muted,#6b7280)"}}>
          {s.piotroski}
        </td>
        {/* COMPOSITE — demoted (smaller, no big bar) */}
        <td style={{padding:"10px 8px",textAlign:"right",fontFamily:"var(--font-mono)",fontSize:11,color:"var(--text-muted,#6b7280)",fontWeight:500}}>
          {s.composite.toFixed(2)}
        </td>
        {/* VALUE (DCF MoS) */}
        <td style={{padding:"10px 8px"}}><MoSBar value={s.margin_of_safety}/></td>
        {/* UPSIDE — analyst */}
        <td style={{fontFamily:"var(--font-mono)",textAlign:"right",padding:"10px 12px",fontSize:12,color:s.upside>20?"#10b981":s.upside>0?"var(--text-muted)":"#ef4444",fontWeight:600}}>{s.upside>0?"+":""}{s.upside?.toFixed(0)}%</td>
        {/* P+10% — labeled experimental */}
        <td style={{fontFamily:"var(--font-mono)",textAlign:"center",padding:"10px 6px",fontSize:11,fontWeight:700,color:p10>60?"#10b981":p10>40?"#d97706":"#ef4444"}} title="ML probability of touching +10% within prediction window. Experimental — known underconfidence in 0.4-0.8 bin.">
          {p10}%{isLive&&<span style={{fontSize:7,color:"var(--text-light)",marginLeft:2}}>ml</span>}
        </td>
        {/* GAIN/DD */}
        <td style={{fontFamily:"var(--font-mono)",textAlign:"right",padding:"10px 12px",fontSize:11}}>
          <span style={{color:"#10b981",fontWeight:600}}>+{probFallback.gain}%</span>
          <span style={{color:"var(--text-light,#9ca3af)",margin:"0 2px"}}>/</span>
          <span style={{color:"#ef4444",fontWeight:600}}>{probFallback.dd}%</span>
        </td>
      </tr>
      {expanded&&(
        <tr><td colSpan={10} style={{padding:0,background:"var(--bg-surface,#f8faf9)"}}>
          <div style={{padding:"16px 20px 20px 40px",animation:"fadeIn 0.2s ease"}}>
            <div style={{display:"grid",gridTemplateColumns:"180px 1fr",gap:24}}>
              <div style={{display:"flex",flexDirection:"column",alignItems:"center",gap:8}}>
                <LargeRadar scores={scores}/>
                <div style={{fontSize:10,fontFamily:"var(--font-mono)",color:"var(--text-muted)"}}>
                  {(()=>{const vals=Object.values(scores).filter((v):v is number=>v!=null);return vals.length?Math.round(vals.reduce((a,b)=>a+b,0)/vals.length*100):0;})()} avg
                </div>
              </div>
              <div>
                <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:8,paddingBottom:6,borderBottom:"2px solid var(--green-light,#e8f5ee)"}}>
                  <div style={{fontSize:10,fontWeight:700,letterSpacing:"0.08em",color:"var(--green,#2d7a4f)",fontFamily:"var(--font-mono)",textTransform:"uppercase"}}>13-Factor Breakdown</div>
                  <AddToPortfolioButton stock={s}/>
                </div>
                <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:"0 24px"}}>
                  {FACTOR_ORDER.map(k=>{const w=weights[k];const pct=w!=null?(w<=1?Math.round(w*100):Math.round(w)):FACTOR_WEIGHTS[k];return<FactorBar key={k} name={FACTOR_LABELS[k]} weight={pct} score={(scores as any)[k]}/>;})}
                </div>
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
interface BasketPick {
  rank:number; symbol:string; price:number; composite_raw:number;
  piotroski:number|null; altman_z:number|null;
  rsi:number|null; momentum_20d:number|null; prox_raw:number|null;
}
interface BasketPayload {
  strategy_version:string; region:string; scan_date:string; generated_at:string;
  universe_size:number; allowlist_size:number; bucket_size:number;
  n_picks:number; basket:BasketPick[];
}
interface PortfolioPos { symbol:string; entry_price:number; entry_date:string; shares:number; notes?:string; }
 
type BasketAction = "HOLD"|"SELL"|"BUY"|"NEW";
interface BasketDiff {
  symbol:string; action:BasketAction;
  target_price?:number; current_shares?:number; target_shares?:number;
  delta_shares?:number; composite?:number; piotroski?:number|null;
  entry_price?:number; entry_date?:string;
}
 
const BASKET_REGIONS = [
  { key:"midcap", label:"MIDCAP", url:"/api/gcs/scans/strategy_basket_midcap.json" },
  { key:"sp500",  label:"S&P 500", url:"/api/gcs/scans/strategy_basket_sp500.json" },
];
 
function getLocalPortfolio():PortfolioPos[]{
  if(typeof window==="undefined") return [];
  try { return JSON.parse(localStorage.getItem("screener_portfolio")||"[]"); }
  catch { return []; }
}
 
function StrategyBasketCard(){
  const [basketRegion,setBasketRegion]=useState<"midcap"|"sp500">("midcap");
  const [basket,setBasket]=useState<BasketPayload|null>(null);
  const [err,setErr]=useState<string|null>(null);
  const [portfolio,setPortfolio]=useState<PortfolioPos[]>([]);
  const [capital,setCapital]=useState(100000);
  const [copied,setCopied]=useState(false);
  const [expanded,setExpanded]=useState(true);
 
  useEffect(()=>{
    setPortfolio(getLocalPortfolio());
    const cfg=BASKET_REGIONS.find(r=>r.key===basketRegion);
    if(!cfg) return;
    setBasket(null); setErr(null);
    fetch(cfg.url)
      .then(r=>{if(!r.ok)throw new Error(`HTTP ${r.status}`);return r.json();})
      .then(setBasket)
      .catch(e=>setErr(String(e)));
  },[basketRegion]);
 
  const diff=useMemo<BasketDiff[]>(()=>{
    if(!basket) return [];
    const perPos=capital/basket.n_picks;
    const targetSyms=new Set(basket.basket.map(b=>b.symbol));
    const rows:BasketDiff[]=[];
    for(const pick of basket.basket){
      const held=portfolio.find(p=>p.symbol===pick.symbol);
      const targetShares=Math.floor(perPos/pick.price);
      if(held){
        rows.push({
          symbol:pick.symbol, action:"HOLD", target_price:pick.price,
          current_shares:held.shares, target_shares:targetShares,
          delta_shares:targetShares-held.shares,
          composite:pick.composite_raw, piotroski:pick.piotroski,
          entry_price:held.entry_price, entry_date:held.entry_date,
        });
      } else {
        rows.push({
          symbol:pick.symbol,
          action:portfolio.length===0?"NEW":"BUY",
          target_price:pick.price, target_shares:targetShares, delta_shares:targetShares,
          composite:pick.composite_raw, piotroski:pick.piotroski,
        });
      }
    }
    for(const p of portfolio){
      if(!targetSyms.has(p.symbol)){
        rows.push({
          symbol:p.symbol, action:"SELL",
          current_shares:p.shares, target_shares:0, delta_shares:-p.shares,
          entry_price:p.entry_price, entry_date:p.entry_date,
        });
      }
    }
    const order:Record<BasketAction,number>={NEW:0,SELL:1,BUY:2,HOLD:3};
    rows.sort((a,b)=>order[a.action]-order[b.action]);
    return rows;
  },[basket,portfolio,capital]);
 
  const copyTickets=()=>{
    if(!basket) return;
    const lines:string[]=[];
    lines.push(`# CB Screener — Strategy Basket`);
    lines.push(`# Region: ${basket.region}  Scan: ${basket.scan_date}  Capital: $${capital.toLocaleString()}`);
    lines.push("");
    for(const r of diff){
      if(r.action==="SELL") lines.push(`SELL  ${r.current_shares} × ${r.symbol}`);
      else if(r.action==="BUY"||r.action==="NEW")
        lines.push(`BUY   ${r.target_shares} × ${r.symbol}  @ limit $${((r.target_price||0)*1.003).toFixed(2)}`);
    }
    navigator.clipboard.writeText(lines.join("\n"));
    setCopied(true); setTimeout(()=>setCopied(false),2000);
  };
 
  // Style maps reusing the page's existing CSS-var color palette
  const ACTION_STYLE:Record<BasketAction,{color:string;bg:string;border:string}>={
    NEW:  { color:"#10b981", bg:"#e8f5ee", border:"#b8dcc8" },
    BUY:  { color:"#10b981", bg:"#e8f5ee", border:"#b8dcc8" },
    SELL: { color:"#ef4444", bg:"#fef2f2", border:"#fecaca" },
    HOLD: { color:"#6b7280", bg:"#f8fafc", border:"#e2e8f0" },
  };
 
  if(err){
    return (
      <div style={{
        background:"var(--bg)", border:"1px solid #fecaca", borderRadius:8,
        padding:"14px 18px", marginBottom:14, fontFamily:"var(--font-mono)", fontSize:12, color:"#b91c1c",
      }}>
        <div style={{display:"flex",alignItems:"center",gap:8,fontWeight:600}}>
          <Target size={14}/> Strategy basket unavailable
        </div>
        <div style={{marginTop:4,color:"#dc2626",fontSize:11}}>{err}</div>
        <div style={{marginTop:6,fontSize:10,color:"#9b2828"}}>
          Run backend: <code>python3 strategy_basket.py --region {basketRegion}</code>
        </div>
      </div>
    );
  }
  if(!basket){
    return (
      <div style={{padding:"14px 18px",marginBottom:14,fontFamily:"var(--font-mono)",fontSize:12,color:"var(--text-muted)"}}>
        Loading strategy basket…
      </div>
    );
  }
 
  const counts=diff.reduce((acc,r)=>{acc[r.action]=(acc[r.action]||0)+1;return acc;},{} as Record<BasketAction,number>);
 
  return (
    <div style={{
      background:"var(--bg)", border:"1px solid var(--border,#e5e7eb)", borderRadius:8,
      marginBottom:16, overflow:"hidden", boxShadow:"0 1px 3px rgba(0,0,0,0.06)",
    }}>
      {/* Header */}
      <div style={{
        padding:"12px 18px",
        background:"linear-gradient(to right, #eef2ff, transparent)",
        borderBottom:"1px solid var(--border,#e5e7eb)",
        display:"flex", justifyContent:"space-between", alignItems:"flex-start", gap:12,
      }}>
        <div style={{flex:1}}>
          <div style={{display:"flex",alignItems:"center",gap:8}}>
            <Target size={15} style={{color:"#4f46e5"}}/>
            <span style={{fontSize:14,fontWeight:700,color:"var(--text,#0f172a)"}}>Strategy Basket</span>
            <span style={{
              fontSize:9,padding:"2px 6px",borderRadius:4,
              background:"#e0e7ff",color:"#4338ca",fontFamily:"var(--font-mono)",fontWeight:700,letterSpacing:"0.05em",
            }}>v{basket.strategy_version}</span>
            <button onClick={()=>setExpanded(x=>!x)} style={{
              marginLeft:6,padding:"2px 6px",fontSize:10,fontFamily:"var(--font-mono)",
              border:"1px solid var(--border)",borderRadius:4,background:"var(--bg)",color:"var(--text-muted)",cursor:"pointer",
            }}>
              {expanded?"hide":"show"}
            </button>
          </div>
          <div style={{
            marginTop:4,fontSize:10,color:"var(--text-muted)",fontFamily:"var(--font-mono)",
            display:"flex",gap:12,flexWrap:"wrap",alignItems:"center",
          }}>
            <span style={{display:"flex",alignItems:"center",gap:4}}>
              <Clock size={10}/>scan {basket.scan_date}
            </span>
            <span>Pio≤3 · top {basket.n_picks} · weekly</span>
            <span>{basket.allowlist_size} clean univ → {basket.bucket_size} bucket → {basket.n_picks} basket</span>
          </div>
        </div>
        <div style={{display:"flex",gap:6,alignItems:"center"}}>
          {BASKET_REGIONS.map(r=>(
            <button key={r.key} onClick={()=>setBasketRegion(r.key as "midcap"|"sp500")} style={{
              padding:"4px 10px",fontSize:10,fontFamily:"var(--font-mono)",fontWeight:600,
              border:`1px solid ${basketRegion===r.key?"#a5b4fc":"var(--border)"}`,borderRadius:4,cursor:"pointer",
              background:basketRegion===r.key?"#eef2ff":"transparent",
              color:basketRegion===r.key?"#4338ca":"var(--text-muted)",
            }}>{r.label}</button>
          ))}
          <input type="number" value={capital} step={10000}
            onChange={e=>setCapital(Number(e.target.value)||0)}
            style={{
              width:90,padding:"4px 8px",fontSize:11,fontFamily:"var(--font-mono)",
              border:"1px solid var(--border)",borderRadius:4,background:"var(--bg)",
              color:"var(--text)",outline:"none",textAlign:"right",
            }} title="capital allocated"/>
          <button onClick={copyTickets} style={{
            display:"flex",alignItems:"center",gap:4,padding:"4px 10px",fontSize:11,
            fontFamily:"var(--font-mono)",fontWeight:600,border:"1px solid var(--border)",borderRadius:4,
            background:copied?"#e8f5ee":"var(--bg)",color:copied?"#10b981":"var(--text)",
            cursor:"pointer",
          }}>
            {copied?<><CheckCircle2 size={11}/>Copied</>:<><Copy size={11}/>Copy tickets</>}
          </button>
        </div>
      </div>
 
      {/* Diff summary */}
      <div style={{
        display:"flex",borderBottom:"1px solid var(--border)",background:"var(--bg)",
      }}>
        {(["NEW","SELL","BUY","HOLD"] as BasketAction[]).map(a=>counts[a]?(
          <div key={a} style={{
            flex:1,padding:"8px 14px",borderRight:"1px solid var(--border)",
            display:"flex",alignItems:"center",gap:8,fontFamily:"var(--font-mono)",
          }}>
            <span style={{
              fontSize:9,padding:"2px 6px",borderRadius:3,
              background:ACTION_STYLE[a].bg,color:ACTION_STYLE[a].color,
              border:`1px solid ${ACTION_STYLE[a].border}`,fontWeight:700,letterSpacing:"0.05em",
            }}>{a}</span>
            <span style={{fontSize:13,fontWeight:700,color:"var(--text)"}}>{counts[a]}</span>
          </div>
        ):null)}
        <div style={{
          flex:1,padding:"8px 14px",fontSize:10,color:"var(--text-muted)",fontFamily:"var(--font-mono)",
          display:"flex",alignItems:"center",justifyContent:"flex-end",
        }}>
          per position: ${(capital/basket.n_picks).toLocaleString(undefined,{maximumFractionDigits:0})}
        </div>
      </div>
 
      {/* Diff table */}
      {expanded && (
        <div style={{overflowX:"auto"}}>
          <table style={{width:"100%",borderCollapse:"collapse",fontSize:12,fontFamily:"var(--font-mono)"}}>
            <thead>
              <tr style={{background:"var(--bg-elevated,#f8fafc)"}}>
                <th style={{textAlign:"left",padding:"7px 14px",fontSize:9,fontWeight:700,letterSpacing:"0.1em",color:"var(--text-light)",borderBottom:"1px solid var(--border)"}}>ACTION</th>
                <th style={{textAlign:"left",padding:"7px 8px",fontSize:9,fontWeight:700,letterSpacing:"0.1em",color:"var(--text-light)",borderBottom:"1px solid var(--border)"}}>SYMBOL</th>
                <th style={{textAlign:"right",padding:"7px 8px",fontSize:9,fontWeight:700,letterSpacing:"0.1em",color:"var(--text-light)",borderBottom:"1px solid var(--border)"}}>TARGET $</th>
                <th style={{textAlign:"right",padding:"7px 8px",fontSize:9,fontWeight:700,letterSpacing:"0.1em",color:"var(--text-light)",borderBottom:"1px solid var(--border)"}}>NOW</th>
                <th style={{padding:"7px 4px",borderBottom:"1px solid var(--border)"}}/>
                <th style={{textAlign:"right",padding:"7px 8px",fontSize:9,fontWeight:700,letterSpacing:"0.1em",color:"var(--text-light)",borderBottom:"1px solid var(--border)"}}>TARGET</th>
                <th style={{textAlign:"right",padding:"7px 8px",fontSize:9,fontWeight:700,letterSpacing:"0.1em",color:"var(--text-light)",borderBottom:"1px solid var(--border)"}}>Δ SHARES</th>
                <th style={{textAlign:"right",padding:"7px 8px",fontSize:9,fontWeight:700,letterSpacing:"0.1em",color:"var(--text-light)",borderBottom:"1px solid var(--border)"}}>COMP</th>
                <th style={{textAlign:"right",padding:"7px 8px",fontSize:9,fontWeight:700,letterSpacing:"0.1em",color:"var(--text-light)",borderBottom:"1px solid var(--border)"}}>PIO</th>
              </tr>
            </thead>
            <tbody>
              {diff.map(r=>(
                <tr key={r.symbol+r.action} style={{borderBottom:"1px solid var(--border)"}}>
                  <td style={{padding:"7px 14px"}}>
                    <span style={{
                      fontSize:9,padding:"2px 6px",borderRadius:3,
                      background:ACTION_STYLE[r.action].bg,color:ACTION_STYLE[r.action].color,
                      border:`1px solid ${ACTION_STYLE[r.action].border}`,fontWeight:700,letterSpacing:"0.05em",
                    }}>{r.action}</span>
                  </td>
                  <td style={{padding:"7px 8px",fontWeight:600,color:"var(--text)"}}>{r.symbol}</td>
                  <td style={{padding:"7px 8px",textAlign:"right"}}>{r.target_price?`$${r.target_price.toFixed(2)}`:"—"}</td>
                  <td style={{padding:"7px 8px",textAlign:"right",color:"var(--text-muted)"}}>{r.current_shares??"—"}</td>
                  <td style={{padding:"7px 4px",textAlign:"center",color:"var(--text-light)"}}>
                    {r.current_shares!==undefined&&r.target_shares!==undefined?<ArrowRight size={11}/>:null}
                  </td>
                  <td style={{padding:"7px 8px",textAlign:"right"}}>{r.target_shares??"—"}</td>
                  <td style={{
                    padding:"7px 8px",textAlign:"right",fontWeight:700,
                    color:(r.delta_shares??0)>0?"#10b981":(r.delta_shares??0)<0?"#ef4444":"var(--text-light)",
                  }}>
                    {r.delta_shares?(r.delta_shares>0?"+":"")+r.delta_shares:"—"}
                  </td>
                  <td style={{padding:"7px 8px",textAlign:"right",color:"var(--text-muted)"}}>
                    {r.composite!=null?r.composite.toFixed(3):"—"}
                  </td>
                  <td style={{padding:"7px 8px",textAlign:"right",color:"var(--text-muted)"}}>
                    {r.piotroski!=null?r.piotroski:"—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
 
      {/* Footer */}
      <div style={{
        padding:"6px 14px",fontSize:9,color:"var(--text-light)",fontFamily:"var(--font-mono)",
        background:"var(--bg-elevated,#f8fafc)",borderTop:"1px solid var(--border)",
        display:"flex",alignItems:"center",gap:6,
      }}>
        <TrendingUp size={10}/>
        IBKR Pro · limit at target +0.3% · log fills for slippage · backtest +20pp/yr alpha
      </div>
    </div>
  );
}

// ── Main Dashboard ──────────────────────────────────────────────────────────
export default function Dashboard(){
  const[sp500Data,setSp500Data]=useState<ScanData|null>(null);
  const[midcapData,setMidcapData]=useState<ScanData|null>(null);
  const[sp500Basket,setSp500Basket]=useState<{basket:{symbol:string;rank:number}[]}|null>(null);
  const[midcapBasket,setMidcapBasket]=useState<{basket:{symbol:string;rank:number}[]}|null>(null);
  const[loading,setLoading]=useState(true);

  const[sortKey,setSortKey]=useState<keyof StockData|"piotroski">("composite");
  const[sortDir,setSortDir]=useState<"asc"|"desc">("desc");
  const[search,setSearch]=useState("");
  const[statusFilter,setStatusFilter]=useState<"ALL"|"basket"|"bucket"|"universe">("ALL");
  const[regionFilter,setRegionFilter]=useState<"ALL"|"midcap"|"sp500">("ALL");
  const[expanded,setExpanded]=useState<Record<string,boolean>>({});

  useEffect(()=>{
    setLoading(true);
    Promise.allSettled([
      fetch(`${GCS_BASE}/latest_sp500.json?t=${Date.now()}`).then(r=>r.ok?r.json():null),
      fetch(`${GCS_BASE}/latest_midcap.json?t=${Date.now()}`).then(r=>r.ok?r.json():null),
      fetch(`${GCS_BASE}/strategy_basket_sp500.json?t=${Date.now()}`).then(r=>r.ok?r.json():null),
      fetch(`${GCS_BASE}/strategy_basket_midcap.json?t=${Date.now()}`).then(r=>r.ok?r.json():null),
    ]).then(([sp,mid,spB,midB])=>{
      if(sp.status==="fulfilled")  setSp500Data(sp.value);
      if(mid.status==="fulfilled") setMidcapData(mid.value);
      if(spB.status==="fulfilled") setSp500Basket(spB.value);
      if(midB.status==="fulfilled")setMidcapBasket(midB.value);
      setLoading(false);
    });
  },[]);

  // Reference data — prefer sp500 for weights/macro, fall back to midcap
  const refData = sp500Data || midcapData;
  const weights = refData?.weights || FACTOR_WEIGHTS;

  // Build deduplicated, decorated stock list from both regions.
  const decoratedStocks = useMemo<StockWithDeco[]>(()=>{
    const sp500Stocks  = sp500Data?.stocks  || [];
    const midcapStocks = midcapData?.stocks || [];
    const sp500SymSet  = new Set(sp500Stocks.map(s=>s.symbol.toUpperCase()));
    const midcapSymSet = new Set(midcapStocks.map(s=>s.symbol.toUpperCase()));

    const sp500BasketMap  = new Map((sp500Basket?.basket||[]).map(b=>[b.symbol.toUpperCase(),b.rank]));
    const midcapBasketMap = new Map((midcapBasket?.basket||[]).map(b=>[b.symbol.toUpperCase(),b.rank]));

    // Dedupe by symbol — prefer the entry with more complete data
    const merged = new Map<string,StockData>();
    for (const s of sp500Stocks)  merged.set(s.symbol.toUpperCase(), s);
    for (const s of midcapStocks) {
      const key = s.symbol.toUpperCase();
      if (!merged.has(key)) merged.set(key, s);
    }

    const result: StockWithDeco[] = [];
    for (const [sym, s] of merged) {
      const inMidcap = midcapSymSet.has(sym);
      const inSp500  = sp500SymSet.has(sym);
      const sp500Rank  = sp500BasketMap.get(sym);
      const midcapRank = midcapBasketMap.get(sym);
      const inAnyBasket = sp500Rank != null || midcapRank != null;
      const inAnyBucket = (s.piotroski ?? 99) <= 3;

      const status: StatusKind = inAnyBasket ? "basket" : inAnyBucket ? "bucket" : "universe";
      const basketRank = midcapRank ?? sp500Rank;
      const basketRegion: StrategyDeco["basketRegion"] =
        midcapRank!=null && sp500Rank!=null ? "both" :
        midcapRank!=null ? "midcap" :
        sp500Rank!=null  ? "sp500"  : undefined;

      result.push({ ...s, _deco: { status, basketRank, basketRegion, inMidcap, inSp500 }});
    }
    return result;
  },[sp500Data,midcapData,sp500Basket,midcapBasket]);

  // Apply filters + sort
  const sorted = useMemo(()=>{
    let list = [...decoratedStocks];
    if (statusFilter !== "ALL") list = list.filter(s => s._deco?.status === statusFilter);
    if (regionFilter !== "ALL") {
      list = list.filter(s => regionFilter === "midcap" ? s._deco?.inMidcap : s._deco?.inSp500);
    }
    if (search) {
      const q = search.toUpperCase();
      list = list.filter(s => s.symbol.includes(q) || (s.company_name||"").toUpperCase().includes(q));
    }
    list.sort((a,b)=>{
      // Custom: basket rank always sorts to top
      const aR = a._deco?.basketRank ?? 999;
      const bR = b._deco?.basketRank ?? 999;
      if (aR !== bR) return aR - bR;
      const av = (a as any)[sortKey] ?? 0;
      const bv = (b as any)[sortKey] ?? 0;
      return sortDir === "desc" ? bv - av : av - bv;
    });
    return list;
  },[decoratedStocks, sortKey, sortDir, statusFilter, regionFilter, search]);

  const toggleSort = (key: keyof StockData | "piotroski") => {
    if (sortKey === key) setSortDir(d => d === "desc" ? "asc" : "desc");
    else { setSortKey(key); setSortDir("desc"); }
  };

  if (loading) return <div style={{color:"var(--text-muted)",padding:60,textAlign:"center",fontFamily:"var(--font-mono)",fontSize:13}}>Loading scan data...</div>;

  // Universe summary counts
  const totalCount  = decoratedStocks.length;
  const basketCount = decoratedStocks.filter(s => s._deco?.status === "basket").length;
  const bucketCount = decoratedStocks.filter(s => s._deco?.status === "bucket").length;
  const universeOnly = totalCount - basketCount - bucketCount;

  // Date — pick whichever scan is newest
  const newestScan = [sp500Data?.scan_date, midcapData?.scan_date].filter(Boolean).sort().pop();
  const scanDate = newestScan
    ? new Date(newestScan).toLocaleString("en-GB", {
        timeZone: "Europe/Amsterdam",
        day:"2-digit", month:"short", year:"numeric",
        hour:"2-digit", minute:"2-digit",
        timeZoneName:"short", hour12:false,
      })
    : "—";

  const hs = (key: keyof StockData | "piotroski" | "static", align: "left"|"right"|"center" = "right"): React.CSSProperties => ({
    padding:"8px 12px", textAlign: align,
    cursor: key === "static" ? "default" : "pointer",
    fontSize:9, fontWeight:700, letterSpacing:"0.1em", fontFamily:"var(--font-mono)",
    color: sortKey === key ? "var(--green,#2d7a4f)" : "var(--text-light,#9ca3af)",
    userSelect:"none", whiteSpace:"nowrap",
    borderBottom:"2px solid var(--border,#e5e7eb)", background:"var(--bg,#fff)",
  });

  return(
    <div style={{padding:"20px 24px",maxWidth:1440,margin:"0 auto"}}>
      {/* Header */}
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:8}}>
        <div>
          <p style={{fontSize:13,color:"var(--text)",fontFamily:"var(--font-mono)",fontWeight:700,marginBottom:2}}>
            CB Screener · {totalCount} stocks · v1.0 strategy
          </p>
          <p style={{fontSize:11,color:"var(--text-muted)",fontFamily:"var(--font-mono)"}}>
            {scanDate} · {basketCount} in basket · {bucketCount} in Pio≤3 bucket · {universeOnly} universe only
          </p>
        </div>
        <div style={{fontSize:9,color:"var(--text-light)",textAlign:"right",fontFamily:"var(--font-mono)",lineHeight:1.6}}>
          weights: {FACTOR_ORDER.slice(0,5).map(k=>`${FACTOR_LABELS[k]} ${FACTOR_WEIGHTS[k]}%`).join(" · ")}
        </div>
      </div>

      {/* Macro ribbon — situational only */}
      <MacroRibbon macro={refData?.macro}/>

      {/* Strategy basket card */}
      <StrategyBasketCard/>

      {/* Filters */}
      <div style={{display:"flex",gap:10,marginBottom:12,marginTop:16,flexWrap:"wrap"}}>
        <div style={{position:"relative",flex:1,maxWidth:280}}>
          <Search size={14} style={{position:"absolute",left:10,top:"50%",transform:"translateY(-50%)",color:"var(--text-light)"}}/>
          <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search symbol..."
            style={{width:"100%",padding:"7px 10px 7px 32px",fontSize:12,fontFamily:"var(--font-mono)",
                    border:"1px solid var(--border)",borderRadius:6,background:"var(--bg)",color:"var(--text)",outline:"none"}}/>
        </div>

        {/* Status filter chips */}
        <div style={{display:"flex",gap:4,alignItems:"center"}}>
          {([
            ["ALL",      `All (${totalCount})`],
            ["basket",   `⭐ Basket (${basketCount})`],
            ["bucket",   `◐ Bucket (${bucketCount})`],
            ["universe", `Universe (${universeOnly})`],
          ] as [typeof statusFilter,string][]).map(([key,label])=>(
            <button key={key} onClick={()=>setStatusFilter(key)}
              style={{
                padding:"6px 11px",fontSize:10,fontFamily:"var(--font-mono)",fontWeight:600,
                border:`1px solid ${statusFilter===key?"var(--green-border,#b8dcc8)":"var(--border,#e5e7eb)"}`,
                borderRadius:5,cursor:"pointer",
                background:statusFilter===key?"var(--green-light,#e8f5ee)":"transparent",
                color:statusFilter===key?"var(--green,#2d7a4f)":"var(--text-muted,#6b7280)",
              }}>{label}</button>
          ))}
        </div>

        {/* Region filter chips */}
        <div style={{display:"flex",gap:4,alignItems:"center"}}>
          {([
            ["ALL","All regions"],
            ["midcap","Midcap"],
            ["sp500","SP500"],
          ] as [typeof regionFilter,string][]).map(([key,label])=>(
            <button key={key} onClick={()=>setRegionFilter(key)}
              style={{
                padding:"6px 11px",fontSize:10,fontFamily:"var(--font-mono)",fontWeight:600,
                border:`1px solid ${regionFilter===key?"var(--green-border,#b8dcc8)":"var(--border,#e5e7eb)"}`,
                borderRadius:5,cursor:"pointer",
                background:regionFilter===key?"var(--green-light,#e8f5ee)":"transparent",
                color:regionFilter===key?"var(--green,#2d7a4f)":"var(--text-muted,#6b7280)",
              }}>{label}</button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div style={{background:"var(--bg)",borderRadius:8,border:"1px solid var(--border)",overflow:"hidden",boxShadow:"0 1px 3px rgba(0,0,0,0.06)"}}>
        <div style={{overflowX:"auto"}}>
          <table style={{width:"100%",borderCollapse:"collapse",fontSize:13}}>
            <thead><tr>
              <th style={hs("symbol","left")} onClick={()=>toggleSort("symbol")}>SYMBOL</th>
              <th style={{...hs("static","center"),cursor:"default"}}>STATUS</th>
              <th style={{...hs("static","center"),cursor:"default"}}>REGION</th>
              <th style={hs("price")} onClick={()=>toggleSort("price")}>PRICE</th>
              <th style={hs("piotroski","center")} onClick={()=>toggleSort("piotroski")}>PIO</th>
              <th style={hs("composite")} onClick={()=>toggleSort("composite")}>COMP</th>
              <th style={hs("margin_of_safety","left")} onClick={()=>toggleSort("margin_of_safety")} title="DCF Margin of Safety — negative = overvalued vs intrinsic">VALUE</th>
              <th style={hs("upside")} onClick={()=>toggleSort("upside")}>UPSIDE</th>
              <th style={{...hs("static","center"),cursor:"default"}} title="ML probability of touching +10%. Experimental.">P+10% ml</th>
              <th style={{...hs("static","right"),cursor:"default"}}>GAIN/DD</th>
            </tr></thead>
            <tbody>{sorted.map((s,idx)=><StockRow key={s.symbol} stock={s} weights={weights} rank={idx+1} expanded={!!expanded[s.symbol]} onToggle={()=>setExpanded(e=>({...e,[s.symbol]:!e[s.symbol]}))}/>)}</tbody>
          </table>
        </div>
        {sorted.length===0&&<div style={{textAlign:"center",padding:40,color:"var(--text-muted)",fontSize:13,fontFamily:"var(--font-mono)"}}>No stocks match this filter</div>}
      </div>
      <div style={{textAlign:"center",marginTop:14,fontSize:10,color:"var(--text-light)",fontFamily:"var(--font-mono)"}}>
        {totalCount} screened · {sorted.length} shown · ⭐ = in current basket · ◐ = in Pio≤3 bucket · click row to expand
      </div>
      <SectorConcentration data={refData?.sector_concentration}/>
    </div>
  );
}
