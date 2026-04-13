"use client";
import { useState, useEffect, useMemo } from "react";
import { TrendingUp, TrendingDown, ChevronDown, ChevronRight, Shield, Target, Search, Filter, Zap, Star, Plus, Check } from "lucide-react";

const GCS_URL = "/api/gcs/scans/latest.json";
const GCS_FALLBACK = "https://storage.googleapis.com/screener-signals-carbonbridge/scans/latest.json";

// ── Types ───────────────────────────────────────────────────────────────────
interface FactorScores { technical:number; quality:number; proximity:number; catalyst:number; transcript:number; upside:number; institutional:number; analyst:number; insider:number; earnings:number; }
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
  // v7 fields - ADDED MISSING TYPES HERE TO FIX VERCEL BUILD
  quality_score?:number; 
  catalyst_score?:number; 
  catalyst_flags?:string[];
  has_catalyst?:boolean; 
  days_to_earnings?:number;
  insider_score?:number; 
  insider_net_buys?:number;
  transcript_sentiment?:number; 
  transcript_summary?:string; 
  transcript_score?:number;
  proximity_score?:number;   // Fixed missing property
  earnings_score?:number;    // Fixed missing property
  upside_score?:number;      // Fixed missing property
  inst_score?:number;        // Fixed missing property
}

interface ScanData {
  scan_date:string; region:string; version:string;
  weights?:Record<string,number>;
  macro?:MacroData;
  summary:{ total:number; buy:number; watch:number; hold:number; sell:number; strong_buy?:number };
  stocks:StockData[];
}

const SIG: Record<string,{color:string;bg:string;border:string}> = {
  "STRONG BUY": { color:"#8b5cf6", bg:"#f5f3ff", border:"#ddd6fe" },
  BUY:   { color:"#10b981", bg:"#e8f5ee", border:"#b8dcc8" },
  WATCH: { color:"#f59e0b", bg:"#fffbeb", border:"#fde68a" },
  HOLD:  { color:"#6b7280", bg:"#f8fafc", border:"#e2e8f0" },
  SELL:  { color:"#ef4444", bg:"#fef2f2", border:"#fecaca" },
};
const CLS: Record<string,string> = { DEEP_VALUE:"#2563eb", VALUE:"#0891b2", QUALITY_GROWTH:"#7c3aed", GROWTH:"#818cf8", SPECULATIVE:"#ef4444", NEUTRAL:"#64748b" };

const FACTOR_ORDER = ["technical","quality","proximity","catalyst","transcript","upside","institutional","analyst","insider","earnings"];
const FACTOR_LABELS: Record<string,string> = { technical:"Technical", quality:"Quality", proximity:"52-Week", catalyst:"Catalyst", transcript:"Transcript", upside:"Upside", institutional:"Institutional", analyst:"Analyst", insider:"Insider", earnings:"Earnings" };
const FACTOR_WEIGHTS: Record<string,number> = { technical:35, quality:15, proximity:12, catalyst:8, transcript:7, upside:6, institutional:5, analyst:5, insider:4, earnings:3 };

// ── Helpers ─────────────────────────────────────────────────────────────────
const fmtPct = (n:number|null|undefined) => n==null?"—":`${(n*100).toFixed(0)}%`;

function inferFactors(s:StockData):FactorScores {
  if(s.factor_scores) return s.factor_scores;
  return {
    technical: Math.min(1,(s.bull_score||0)/10),
    quality: s.quality_score ?? Math.min(1, ((s.piotroski||0)/9*0.4 + Math.min(1,(s.altman_z||0)/10)*0.2 + Math.min(1,(s.roe_avg||0)/0.3)*0.2 + Math.min(1,(s.gross_margin||0))*0.2)),
    proximity: s.proximity_score ?? (s.year_high>0?(s.price-s.year_low)/(s.year_high-s.year_low):0.5),
    catalyst: s.catalyst_score ?? 0.5,
    transcript: s.transcript_score ?? 0.5,
    upside: s.upside_score ?? Math.min(1,Math.max(0,(s.upside||0)/80)),
    institutional: s.inst_score ?? 0.5,
    analyst: s.grade_score || 0,
    insider: s.insider_score ?? 0.5,
    earnings: s.earnings_score ?? Math.min(1,(s.eps_beats||0)/Math.max(1,s.eps_total||1)),
  };
}

// ── Components ──────────────────────────────────────────────────────────────
function MiniRadar({scores,size=44}:{scores:FactorScores;size?:number}){
  const cx=size/2,cy=size/2,r=size/2-4;const vals=FACTOR_ORDER.map(k=>(scores as any)[k]??0);const n=vals.length;
  const ang=(i:number)=>(Math.PI*2*i)/n-Math.PI/2;
  const avg=vals.reduce((a,b)=>a+b,0)/n;const fill=avg>0.6?"#2d7a4f":avg>0.4?"#d97706":"#ef4444";
  const data=vals.map((v,i)=>`${cx+Math.cos(ang(i))*Math.max(0.05,v)*r},${cy+Math.sin(ang(i))*Math.max(0.05,v)*r}`).join(" ");
  const grid=[0.33,0.66,1].map(lv=>Array.from({length:n},(_,i)=>`${cx+Math.cos(ang(i))*r*lv},${cy+Math.sin(ang(i))*r*lv}`).join(" "));
  return(
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {grid.map((p,i)=><polygon key={i} points={p} fill="none" stroke="#e2e8e4" strokeWidth={0.5} opacity={0.6}/>)}
      {Array.from({length:n},(_,i)=><line key={i} x1={cx} y1={cy} x2={cx+Math.cos(ang(i))*r} y2={cy+Math.sin(ang(i))*r} stroke="#e2e8e4" strokeWidth={0.4}/>)}
      <polygon points={data} fill={fill} fillOpacity={0.2} stroke={fill} strokeWidth={1.2} strokeLinejoin="round"/>
      {vals.map((v,i)=><circle key={i} cx={cx+Math.cos(ang(i))*Math.max(0.05,v)*r} cy={cy+Math.sin(ang(i))*Math.max(0.05,v)*r} r={1.5} fill={fill}/>)}
    </svg>
  );
}

function LargeRadar({scores,size=180}:{scores:FactorScores;size?:number}){
  const cx=size/2,cy=size/2,r=size/2-24;const vals=FACTOR_ORDER.map(k=>(scores as any)[k]??0);const n=vals.length;
  const ang=(i:number)=>(Math.PI*2*i)/n-Math.PI/2;
  const avg=vals.reduce((a,b)=>a+b,0)/n;const fill=avg>0.6?"#2d7a4f":avg>0.4?"#d97706":"#ef4444";
  return(
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {[0.25,0.5,0.75,1].map((lv,i)=>{const pts=Array.from({length:n},(_,j)=>`${cx+Math.cos(ang(j))*r*lv},${cy+Math.sin(ang(j))*r*lv}`).join(" ");return<polygon key={i} points={pts} fill="none" stroke="#d1d5db" strokeWidth={i===3?1:0.5} opacity={0.5}/>;})}
      {FACTOR_ORDER.map((k,i)=>{const a=ang(i),lx=cx+Math.cos(a)*(r+16),ly=cy+Math.sin(a)*(r+16),v=vals[i],c=v>0.7?"#2d7a4f":v>0.4?"#d97706":"#ef4444";return<g key={k}><line x1={cx} y1={cy} x2={cx+Math.cos(a)*r} y2={cy+Math.sin(a)*r} stroke="#d1d5db" strokeWidth={0.5}/><text x={lx} y={ly} textAnchor="middle" dominantBaseline="middle" fontSize={7} fontFamily="var(--font-mono)" fill="#6b7280" fontWeight="500">{FACTOR_LABELS[k]?.slice(0,6)}</text></g>;})}
      <polygon points={vals.map((v,i)=>`${cx+Math.cos(ang(i))*Math.max(0.05,v)*r},${cy+Math.sin(ang(i))*Math.max(0.05,v)*r}`).join(" ")} fill={fill} fillOpacity={0.15} stroke={fill} strokeWidth={1.5} strokeLinejoin="round"/>
      {vals.map((v,i)=><circle key={i} cx={cx+Math.cos(ang(i))*Math.max(0.05,v)*r} cy={cy+Math.sin(ang(i))*Math.max(0.05,v)*r} r={2.5} fill={fill} stroke="#fff" strokeWidth={1}/>)}
    </svg>
  );
}

function FactorBar({name,weight,score}:{name:string;weight:number;score:number}){
  const c=score>0.7?"#10b981":score>0.4?"#f59e0b":"#ef4444";
  return(
    <div style={{padding:"5px 0",borderBottom:"1px solid var(--divider)"}}>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:3}}>
        <div style={{display:"flex",alignItems:"baseline",gap:4}}><span style={{fontSize:11,fontFamily:"var(--font-mono)",fontWeight:600,color:"var(--text)"}}>{name}</span><span style={{fontSize:8,fontFamily:"var(--font-mono)",color:"var(--text-light)"}}>({weight}%)</span></div>
        <span style={{fontSize:11,fontFamily:"var(--font-mono)",fontWeight:700,color:c}}>{(score*100).toFixed(0)}</span>
      </div>
      <div style={{height:4,borderRadius:2,background:"#edf0ee",overflow:"hidden"}}><div style={{height:"100%",width:`${score*100}%`,borderRadius:2,background:c,transition:"width 0.3s"}}/></div>
    </div>
  );
}

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

function MacroBanner({macro}:{macro?:MacroData}){
  if(!macro) return null;
  const cfg:{[k:string]:{emoji:string;label:string;color:string;bg:string;border:string}} = {
    RISK_ON:  {emoji:"🟢",label:"RISK ON — Momentum favored",color:"#10b981",bg:"#e8f5ee",border:"#b8dcc8"},
    NEUTRAL:  {emoji:"⚪",label:"NEUTRAL — Base weights",color:"#6b7280",bg:"#f8fafc",border:"#e2e8f0"},
    CAUTIOUS: {emoji:"🟡",label:"CAUTIOUS — Quality over momentum",color:"#d97706",bg:"#fffbeb",border:"#fde68a"},
    RISK_OFF: {emoji:"🔴",label:"RISK OFF — Defensive mode",color:"#ef4444",bg:"#fef2f2",border:"#fecaca"},
  };
  const c=cfg[macro.regime]||cfg.NEUTRAL;
  const subs=macro.sub_scores||{};
  const subItems:[string,number][]=[["Yield Curve",subs.yield_curve],["Yield Level",subs.yield_level],["VIX",subs.vix],["CPI",subs.cpi_trend],["GDP",subs.gdp_momentum]];
  return(
    <div style={{background:c.bg,border:`1px solid ${c.border}`,borderRadius:8,padding:"10px 16px",marginBottom:16,display:"flex",justifyContent:"space-between",alignItems:"center"}}>
      <div style={{display:"flex",alignItems:"center",gap:8}}>
        <span style={{fontSize:14}}>{c.emoji}</span>
        <span style={{fontSize:12,fontFamily:"var(--font-mono)",fontWeight:600,color:c.color}}>{c.label}</span>
        <span style={{fontSize:10,fontFamily:"var(--font-mono)",color:c.color,opacity:0.7}}>Score: {(macro.score*100).toFixed(0)}</span>
      </div>
      <div style={{display:"flex",gap:8}}>
        {subItems.map(([label,val])=>val!=null&&(
          <div key={label} style={{textAlign:"center"}}>
            <div style={{width:30,height:4,borderRadius:2,background:"#e5e7eb",overflow:"hidden"}}><div style={{height:"100%",width:`${(val??0)*100}%`,borderRadius:2,background:c.color,opacity:0.6}}/></div>
            <div style={{fontSize:7,fontFamily:"var(--font-mono)",color:"#9ca3af",marginTop:2}}>{label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function MoSBar({value}:{value:number}){const p=Math.max(-1,Math.min(1,value)),w=Math.abs(p)*100,c=p>0.15?"#10b981":p>0?"#86efac":p>-0.2?"#d97706":"#ef4444";return<div style={{display:"flex",alignItems:"center",gap:6}}><div style={{width:70,height:5,background:"#edf0ee",borderRadius:3,position:"relative",overflow:"hidden"}}><div style={{position:"absolute",height:"100%",borderRadius:3,background:c,...(p>=0?{left:"50%",width:`${w/2}%`}:{right:"50%",width:`${w/2}%`})}}/><div style={{position:"absolute",left:"50%",top:0,bottom:0,width:1,background:"var(--border)"}}/></div><span style={{fontFamily:"var(--font-mono)",fontSize:11,color:c,fontWeight:600}}>{fmtPct(value)}</span></div>;}

function ScorePill({value}:{value:number}){const c=value>0.65?"#10b981":value>0.45?"#d97706":"#ef4444";return<div style={{display:"inline-flex",alignItems:"center",gap:4}}><div style={{width:40,height:4,borderRadius:2,background:"#edf0ee",overflow:"hidden"}}><div style={{height:"100%",width:`${value*100}%`,borderRadius:2,background:c}}/></div><span style={{fontFamily:"var(--font-mono)",fontSize:12,fontWeight:700,color:c}}>{value.toFixed(2)}</span></div>;}

// ── Stock Row ───────────────────────────────────────────────────────────────
function StockRow({stock:s, expanded, onToggle, onAdd, isInPortfolio}: { 
  stock: StockData; expanded: boolean; onToggle: () => void; onAdd: (e: React.MouseEvent) => void; isInPortfolio: boolean; 
}) {
  const scores = inferFactors(s);
  const sigStyle = SIG[s.signal] || SIG.HOLD;
  return (
    <>
      <tr onClick={onToggle} style={{cursor:"pointer",borderBottom:"1px solid #eef1ef",transition:"background 0.12s"}}>
        <td style={{padding:"10px 12px"}}>
          <div style={{display:"flex",alignItems:"center",gap:8}}>
            {expanded?<ChevronDown size={13} color="#9ca3af"/>:<ChevronRight size={13} color="#9ca3af"/>}
            <div>
              <div style={{display:"flex",alignItems:"center",gap:6}}>
                <button
                  onClick={onAdd}
                  disabled={isInPortfolio}
                  style={{
                    border: "none",
                    background: isInPortfolio ? "#e8f5ee" : "#edf0ee",
                    color: isInPortfolio ? "#10b981" : "#9ca3af",
                    borderRadius: 4,
                    padding: "2px 4px",
                    cursor: isInPortfolio ? "default" : "pointer",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    transition: "all 0.2s"
                  }}
                >
                  {isInPortfolio ? <Check size={10} /> : <Plus size={10} />}
                </button>
                <a href={`/stock/${s.symbol}`} onClick={e=>e.stopPropagation()} style={{fontWeight:700,letterSpacing:"0.04em",color:"#1a1a1a",fontSize:13,fontFamily:"var(--font-mono)"}}>{s.symbol}</a>
                <span style={{fontSize:9,padding:"1px 5px",borderRadius:3,fontWeight:600,fontFamily:"var(--font-mono)",background:(CLS[s.classification]||"#475569")+"10",color:CLS[s.classification]||"#475569"}}>{s.classification?.replace("_"," ")}</span>
                {s.has_catalyst&&<Zap size={10} color="#8b5cf6" fill="#8b5cf6"/>}
              </div>
              <CatalystBadges s={s}/>
            </div>
          </div>
        </td>
        <td style={{fontFamily:"var(--font-mono)",textAlign:"right",padding:"10px 12px",color:"#1a1a1a",fontSize:12}}>{s.currency!=="USD"&&<span style={{fontSize:9,color:"#9ca3af",marginRight:3}}>{s.currency}</span>}${s.price?.toFixed(2)}</td>
        <td style={{padding:"10px 12px"}}><span style={{display:"inline-block",padding:"3px 10px",borderRadius:4,fontSize:10,fontWeight:700,letterSpacing:"0.07em",fontFamily:"var(--font-mono)",background:sigStyle.bg,color:sigStyle.color,border:`1px solid ${sigStyle.border}`}}>{s.signal}</span></td>
        <td style={{padding:"10px 12px",textAlign:"right"}}><ScorePill value={s.composite}/></td>
        <td style={{padding:"6px 8px",textAlign:"center"}}><MiniRadar scores={scores} size={44}/></td>
        <td style={{padding:"10px 8px"}}><div style={{display:"flex",gap:2}}>{Array.from({length:10},(_,i)=>{const a=i<s.bull_score,c=s.bull_score>=7?"#10b981":s.bull_score>=4?"#d97706":"#ef4444";return<div key={i} style={{width:6,height:6,borderRadius:"50%",background:a?c:"#edf0ee",border:`1px solid ${a?c:"#e5e7eb"}`}}/>;})}</div></td>
        <td style={{padding:"10px 8px"}}><MoSBar value={s.margin_of_safety}/></td>
        <td style={{fontFamily:"var(--font-mono)",textAlign:"right",padding:"10px 12px",fontSize:12,color:s.upside>20?"#10b981":s.upside>0?"#475569":"#ef4444",fontWeight:600}}>{s.upside>0?"+":""}{s.upside?.toFixed(0)}%</td>
        <td style={{padding:"10px 8px",textAlign:"center"}}>{s.insider_score!=null?<span style={{fontSize:11,fontFamily:"var(--font-mono)",fontWeight:600,color:s.insider_score>0.6?"#10b981":s.insider_score>0.4?"#475569":"#ef4444"}}>{(s.insider_net_buys??0)>0?"↑":(s.insider_net_buys??0)<0?"↓":"→"} {(s.insider_score*100).toFixed(0)}</span>:<span style={{color:"#9ca3af",fontSize:10,fontFamily:"var(--font-mono)"}}>—</span>}</td>
        <td style={{padding:"10px 8px"}}>{s.transcript_sentiment!=null?<span style={{fontSize:11,fontFamily:"var(--font-mono)",color:s.transcript_sentiment>0.3?"#10b981":s.transcript_sentiment>-0.1?"#475569":"#ef4444"}}>{s.transcript_sentiment>0.3?"😊":s.transcript_sentiment>-0.1?"😐":"😟"} {s.transcript_sentiment>0?"+":""}{s.transcript_sentiment.toFixed(2)}</span>:<span style={{color:"#9ca3af",fontSize:10,fontFamily:"var(--font-mono)"}}>—</span>}</td>
      </tr>
      {expanded&&(
        <tr><td colSpan={10} style={{padding:0,background:"#f8faf9"}}>
          <div style={{padding:"16px 20px 20px 40px",animation:"fadeIn 0.2s ease"}}>
            <div style={{display:"grid",gridTemplateColumns:"180px 1fr",gap:24}}>
              <div style={{display:"flex",flexDirection:"column",alignItems:"center",gap:8}}>
                <LargeRadar scores={scores}/>
                <div style={{fontSize:10,fontFamily:"var(--font-mono)",color:"#6b7280"}}>{((Object.values(scores).reduce((a,b)=>a+b,0))/10*100).toFixed(0)} avg</div>
              </div>
              <div>
                <div style={{fontSize:10,fontWeight:700,letterSpacing:"0.08em",color:"#2d7a4f",fontFamily:"var(--font-mono)",marginBottom:8,paddingBottom:6,borderBottom:"2px solid #e8f5ee",textTransform:"uppercase"}}>10-Factor Breakdown</div>
                <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:"0 24px"}}>
                  {FACTOR_ORDER.map(k=><FactorBar key={k} name={FACTOR_LABELS[k]} weight={FACTOR_WEIGHTS[k]} score={(scores as any)[k]??0}/>)}
                </div>
              </div>
            </div>
          </div>
        </td></tr>
      )}
    </>
  );
}

// ── Main Dashboard ──────────────────────────────────────────────────────────
export default function Dashboard(){
  const[data,setData]=useState<ScanData|null>(null);const[loading,setLoading]=useState(true);
  const[sortKey,setSortKey]=useState<keyof StockData>("composite");const[sortDir,setSortDir]=useState<"asc"|"desc">("desc");
  const[filter,setFilter]=useState("ALL");const[search,setSearch]=useState("");const[classFilter,setClassFilter]=useState("ALL");
  const[expanded,setExpanded]=useState<Record<string,boolean>>({});
  const[portfolioSymbols, setPortfolioSymbols] = useState<string[]>([]);

  useEffect(()=>{
    fetch(GCS_URL).then(r=>{if(!r.ok)throw new Error();return r.json();}).then((d:ScanData)=>{setData(d);setLoading(false);}).catch(()=>{fetch(GCS_FALLBACK).then(r=>r.json()).then((d:ScanData)=>{setData(d);setLoading(false);}).catch(()=>setLoading(false));});
    
    // SYNC KEY WITH PORTFOLIO PAGE: 'screener_portfolio'
    const savedString = localStorage.getItem("screener_portfolio") || "[]";
    try {
      const saved = JSON.parse(savedString);
      setPortfolioSymbols(saved.map((p: any) => p.symbol));
    } catch(e) {
      setPortfolioSymbols([]);
    }
  },[]);

  const handleAdd = (e: React.MouseEvent, s: StockData) => {
    e.stopPropagation();
    const savedString = localStorage.getItem("screener_portfolio") || "[]";
    let current = [];
    try {
        current = JSON.parse(savedString);
    } catch(e) {
        current = [];
    }
    
    if (!current.find((p: any) => p.symbol === s.symbol)) {
      const newItem = { 
        symbol: s.symbol, 
        entry_price: s.price, 
        entry_date: new Date().toISOString().split('T')[0],
        shares: 0, 
        notes: "",
        entry_composite: s.composite,
        entry_signal: s.signal
      };
      const updated = [...current, newItem];
      localStorage.setItem("screener_portfolio", JSON.stringify(updated));
      setPortfolioSymbols(updated.map((p: any) => p.symbol));
    }
  };

  const sorted=useMemo(()=>{
    if(!data?.stocks) return [];
    let list=[...data.stocks];
    if(filter!=="ALL") list=list.filter(s=>s.signal===filter);
    if(classFilter!=="ALL") list=list.filter(s=>s.classification===classFilter);
    if(search){const q=search.toUpperCase();list=list.filter(s=>s.symbol.includes(q));}
    list.sort((a,b)=>{
      const av=(a[sortKey]as any)??0,bv=(b[sortKey]as any)??0;
      return sortDir==="desc"? (bv > av ? 1 : -1) : (av > bv ? 1 : -1);
    });
    return list;
  },[data,sortKey,sortDir,filter,classFilter,search]);

  const toggleSort=(key:keyof StockData)=>{if(sortKey===key)setSortDir(d=>d==="desc"?"asc":"desc");else{setSortKey(key);setSortDir("desc");}};

  if(loading) return<div style={{color:"#6b7280",padding:60,textAlign:"center",fontFamily:"var(--font-mono)",fontSize:13}}>Loading scan data...</div>;

  const sum=data?.summary||{total:0,buy:0,watch:0,hold:0,sell:0,strong_buy:0};
  const scanDate=data?.scan_date?new Date(data.scan_date).toLocaleString():"—";
  const classifications=[...new Set(data?.stocks?.map(s=>s.classification)||[])].sort();

  const hs=(key:string,align:"left"|"right"|"center"="right"):React.CSSProperties=>({
    padding:"8px 12px",textAlign:align,cursor:"pointer",fontSize:9,fontWeight:700,letterSpacing:"0.1em",fontFamily:"var(--font-mono)",
    color:sortKey===key?"#2d7a4f":"#9ca3af",userSelect:"none",whiteSpace:"nowrap",borderBottom:"2px solid #e5e7eb",background:"#fff"
  });

  const signalCards = [
    ...(sum.strong_buy ? [{ label:"STRONG BUY",count:sum.strong_buy,icon:<Star size={15}/>,s:SIG["STRONG BUY"] }] : []),
    { label:"BUY",count:sum.buy,icon:<TrendingUp size={15}/>,s:SIG.BUY },
    { label:"WATCH",count:sum.watch,icon:<Target size={15}/>,s:SIG.WATCH },
    { label:"HOLD",count:sum.hold,icon:<Shield size={15}/>,s:SIG.HOLD },
    { label:"SELL",count:sum.sell,icon:<TrendingDown size={15}/>,s:SIG.SELL },
  ];

  return(
    <div style={{padding:"20px 24px",maxWidth:1440,margin:"0 auto"}}>
      <MacroBanner macro={data?.macro}/>
      <div style={{display:"grid",gridTemplateColumns:`repeat(${signalCards.length},1fr)`,gap:10,marginBottom:20}}>
        {signalCards.map(({label,count,icon,s:st})=>(
          <div key={label} onClick={()=>setFilter(f=>f===label?"ALL":label)} style={{
            background:filter===label?st.bg:"#fff",border:`1px solid ${filter===label?st.border:"#e5e7eb"}`,
            borderRadius:8,padding:"12px 16px",cursor:"pointer",transition:"all 0.15s"
          }}>
            <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}>
              <span style={{fontSize:10,fontWeight:700,letterSpacing:"0.1em",color:"#6b7280",fontFamily:"var(--font-mono)"}}>{label}</span>
              <span style={{color:st.color}}>{icon}</span>
            </div>
            <div style={{fontSize:26,fontWeight:700,color:st.color,fontFamily:"var(--font-mono)",marginTop:2}}>{count||0}</div>
          </div>
        ))}
      </div>

      <div style={{display:"flex",gap:10,marginBottom:12}}>
        <div style={{position:"relative",flex:1,maxWidth:280}}>
          <Search size={14} style={{position:"absolute",left:10,top:"50%",transform:"translateY(-50%)",color:"#9ca3af"}}/>
          <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search symbol..." style={{width:"100%",padding:"7px 10px 7px 32px",fontSize:12,fontFamily:"var(--font-mono)",border:"1px solid #e2e8e4",borderRadius:6,outline:"none"}}/>
        </div>
      </div>

      <div style={{background:"#fff",borderRadius:8,border:"1px solid #e2e8e4",overflow:"hidden"}}>
        <div style={{overflowX:"auto"}}>
          <table style={{width:"100%",borderCollapse:"collapse",fontSize:13}}>
            <thead><tr>
              <th style={hs("symbol","left")} onClick={()=>toggleSort("symbol")}>SYMBOL</th>
              <th style={hs("price")} onClick={()=>toggleSort("price")}>PRICE</th>
              <th style={hs("signal","left")} onClick={()=>toggleSort("signal")}>SIGNAL</th>
              <th style={hs("composite")} onClick={()=>toggleSort("composite")}>SCORE</th>
              <th style={{...hs("composite","center"),cursor:"default"}}>RADAR</th>
              <th style={hs("bull_score","left")} onClick={()=>toggleSort("bull_score")}>BULL</th>
              <th style={hs("margin_of_safety","left")} onClick={()=>toggleSort("margin_of_safety")}>MoS</th>
              <th style={hs("upside")} onClick={()=>toggleSort("upside")}>UPSIDE</th>
              <th style={hs("insider_score","center")}>INSIDER</th>
              <th style={hs("transcript_sentiment","left")}>TRNSCRPT</th>
            </tr></thead>
            <tbody>
              {sorted.map(s=>(
                <StockRow 
                  key={s.symbol} 
                  stock={s} 
                  expanded={!!expanded[s.symbol]} 
                  onToggle={()=>setExpanded(e=>({...e,[s.symbol]:!e[s.symbol]}))}
                  onAdd={(e) => handleAdd(e, s)}
                  isInPortfolio={portfolioSymbols.includes(s.symbol)}
                />
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}