"use client";
import { useState, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { TrendingUp, TrendingDown, BarChart3, Target, Clock, Radio, ChevronDown, ChevronRight, ExternalLink } from "lucide-react";

const GCS_PERF = "/api/gcs/performance/tracker.json";
const GCS_SIGNALS = "/api/gcs/signals";
const GCS_SCANS = "/api/gcs/scans";

// ── Types ───────────────────────────────────────────────────────────────────
interface OpenTrade { entry_date:string; entry_price:number; entry_signal:string; entry_composite:number; sector:string; industry:string; peak_price:number; position_size_pct:number; regime_at_entry:string; last_price:number; last_composite:number; last_signal:string; last_updated:string; }
interface ClosedTrade { symbol?:string; entry_date:string; entry_price:number; entry_signal:string; entry_composite:number; sector:string; industry:string; peak_price:number; position_size_pct:number; regime_at_entry:string; exit_date:string; exit_price:number; exit_signal:string; exit_composite:number; pnl_pct:number; days_held:number; annualized_return:number; regime_at_exit:string; }
interface TrackerStats { total_closed:number; win_rate:number; avg_pnl_pct:number; avg_days_held:number; avg_annualized:number; best_trade:string; worst_trade:string; backtest_expected_ann:number; open_positions:number; open_avg_pnl:number; sector_exposure:Record<string,number>; current_regime:string; updated:string; }
interface TrackerData { version:string; open_trades:Record<string,OpenTrade>; closed_trades:ClosedTrade[]; stats:TrackerStats; }
interface SignalEntry { symbol:string; date:string; price:number; composite:number; signal:string; bull?:number; mos?:number; target?:number; }

// ── Theme ───────────────────────────────────────────────────────────────────
const T = { text:"#1a1a1a", muted:"#6b7280", light:"#9ca3af", green:"#2d7a4f", greenLight:"#e8f5ee", greenBorder:"#b8dcc8", red:"#ef4444", redLight:"#fef2f2", amber:"#d97706", amberLight:"#fffbeb", purple:"#8b5cf6", border:"#e5e7eb", divider:"#f3f4f6", mono:"var(--font-mono, 'JetBrains Mono', monospace)", shadow:"0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)" };
const SIG:Record<string,{color:string;bg:string;border:string}>={"STRONG BUY":{color:T.purple,bg:"#f5f3ff",border:"#ddd6fe"},BUY:{color:"#10b981",bg:T.greenLight,border:T.greenBorder},WATCH:{color:T.amber,bg:T.amberLight,border:"#fde68a"},HOLD:{color:T.muted,bg:"#f8fafc",border:"#e2e8f0"},SELL:{color:T.red,bg:T.redLight,border:"#fecaca"}};
const REGIME:Record<string,{emoji:string;color:string}>={RISK_ON:{emoji:"🟢",color:"#10b981"},NEUTRAL:{emoji:"⚪",color:T.muted},RISK_OFF:{emoji:"🟠",color:T.amber},CRISIS:{emoji:"🔴",color:T.red}};

// ── Components ──────────────────────────────────────────────────────────────
function Card({children,style}:{children:React.ReactNode;style?:React.CSSProperties}){return<div style={{background:"#fff",borderRadius:8,border:`1px solid ${T.border}`,boxShadow:T.shadow,padding:"16px 18px",...style}}>{children}</div>;}
function SH({title,icon,sub}:{title:string;icon?:React.ReactNode;sub?:string}){return<div style={{display:"flex",alignItems:"center",gap:6,fontSize:11,fontWeight:600,letterSpacing:"0.08em",color:T.green,fontFamily:T.mono,textTransform:"uppercase",marginBottom:12,paddingBottom:8,borderBottom:`2px solid ${T.greenLight}`}}>{icon}{title}{sub&&<span style={{marginLeft:"auto",fontSize:9,color:T.light,fontWeight:400,textTransform:"none",letterSpacing:0}}>{sub}</span>}</div>;}
function KPI({label,value,sub,color}:{label:string;value:string;sub?:string;color?:string}){return<Card><div style={{fontSize:9,fontWeight:600,letterSpacing:"0.1em",color:T.muted,fontFamily:T.mono}}>{label}</div><div style={{fontSize:26,fontWeight:700,color:color||T.text,fontFamily:T.mono,marginTop:4}}>{value}</div>{sub&&<div style={{fontSize:9,color:T.light,fontFamily:T.mono,marginTop:2}}>{sub}</div>}</Card>;}
function SignalBadge({signal}:{signal:string}){const s=SIG[signal]||SIG.HOLD;return<span style={{display:"inline-block",padding:"2px 7px",borderRadius:4,fontSize:9,fontWeight:700,fontFamily:T.mono,letterSpacing:"0.07em",color:s.color,background:s.bg,border:`1px solid ${s.border}`}}>{signal}</span>;}
function RegimeBadge({regime}:{regime:string}){const r=REGIME[regime]||REGIME.NEUTRAL;return<span style={{fontSize:10,fontFamily:T.mono,color:r.color}}>{r.emoji} {regime}</span>;}
const th:React.CSSProperties={padding:"8px 10px",fontSize:9,fontWeight:600,letterSpacing:"0.1em",textTransform:"uppercase",color:T.muted,fontFamily:T.mono,borderBottom:`2px solid ${T.border}`,whiteSpace:"nowrap"};
const td:React.CSSProperties={padding:"9px 10px",fontSize:11,fontFamily:T.mono,borderBottom:`1px solid ${T.divider}`};

// ══════════════════════════════════════════════════════════════════════════════
// TAB 1: TRACKER
// ══════════════════════════════════════════════════════════════════════════════
function ComparisonBar({live,backtest}:{live:number;backtest:number}){const pct=backtest>0?(live/backtest)*100:0;const gap=live-backtest;const barColor=pct>=80?"#10b981":pct>=50?T.amber:T.red;return<Card><SH title="Backtest vs Live" icon={<Target size={12}/>}/><div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:16,marginBottom:16}}><div><div style={{fontSize:9,color:T.muted,fontFamily:T.mono}}>Backtest expected</div><div style={{fontSize:22,fontWeight:700,color:T.muted,fontFamily:T.mono}}>+{backtest.toFixed(0)}%/yr</div></div><div><div style={{fontSize:9,color:T.muted,fontFamily:T.mono}}>Live actual</div><div style={{fontSize:22,fontWeight:700,color:live>=0?"#10b981":T.red,fontFamily:T.mono}}>{live>=0?"+":""}{live.toFixed(1)}%/yr</div></div><div><div style={{fontSize:9,color:T.muted,fontFamily:T.mono}}>Gap</div><div style={{fontSize:22,fontWeight:700,color:gap>=0?"#10b981":T.red,fontFamily:T.mono}}>{gap>=0?"+":""}{gap.toFixed(1)}pp</div></div></div><div style={{position:"relative",height:24,background:T.divider,borderRadius:6,overflow:"hidden"}}><div style={{height:"100%",width:`${Math.min(pct,100)}%`,background:barColor,borderRadius:6,transition:"width 0.6s ease"}}/><div style={{position:"absolute",right:8,top:"50%",transform:"translateY(-50%)",fontSize:10,fontFamily:T.mono,fontWeight:600,color:pct>50?"#fff":T.text}}>{pct.toFixed(0)}% of backtest</div></div></Card>;}

function SectorExposure({sectors}:{sectors:Record<string,number>}){const entries=Object.entries(sectors).sort((a,b)=>b[1]-a[1]);const maxCount=entries[0]?.[1]||1;const colors=["#10b981","#3b82f6","#8b5cf6","#f59e0b","#ef4444","#ec4899","#14b8a6","#f97316"];return<Card><SH title="Sector Exposure" sub="Open trades" icon={<BarChart3 size={12}/>}/>{entries.map(([sector,count],i)=><div key={sector} style={{marginBottom:6}}><div style={{display:"flex",justifyContent:"space-between",marginBottom:2}}><span style={{fontSize:10,fontFamily:T.mono,color:T.text,fontWeight:500}}>{sector}</span><span style={{fontSize:10,fontFamily:T.mono,color:T.muted}}>{count}</span></div><div style={{height:5,borderRadius:3,background:T.divider,overflow:"hidden"}}><div style={{height:"100%",width:`${(count/maxCount)*100}%`,borderRadius:3,background:colors[i%colors.length]}}/></div></div>)}</Card>;}

function TrackerTab({data,router}:{data:TrackerData|null;router:ReturnType<typeof useRouter>}){
  const[closedSort,setClosedSort]=useState<"date"|"pnl"|"days">("date");
  const[closedDir,setClosedDir]=useState<"asc"|"desc">("desc");

  const openTrades=useMemo(()=>{if(!data?.open_trades)return[];return Object.entries(data.open_trades).map(([symbol,t])=>({symbol,...t,pnl_pct:t.entry_price>0?((t.last_price-t.entry_price)/t.entry_price)*100:0,days_held:Math.floor((Date.now()-new Date(t.entry_date).getTime())/86400000)})).sort((a,b)=>b.pnl_pct-a.pnl_pct);},[data]);

  const sortedClosed=useMemo(()=>{if(!data?.closed_trades)return[];const list=[...data.closed_trades];switch(closedSort){case"pnl":list.sort((a,b)=>closedDir==="desc"?b.pnl_pct-a.pnl_pct:a.pnl_pct-b.pnl_pct);break;case"days":list.sort((a,b)=>closedDir==="desc"?b.days_held-a.days_held:a.days_held-b.days_held);break;default:list.sort((a,b)=>closedDir==="desc"?b.exit_date.localeCompare(a.exit_date):a.exit_date.localeCompare(b.exit_date));}return list.slice(0,30);},[data,closedSort,closedDir]);

  const toggleSort=(key:"date"|"pnl"|"days")=>{if(closedSort===key)setClosedDir(d=>d==="desc"?"asc":"desc");else{setClosedSort(key);setClosedDir("desc");}};

  if(!data) return<Card style={{padding:"60px 20px",textAlign:"center"}}><BarChart3 size={36} color={T.divider}/><div style={{fontSize:14,color:T.muted,fontFamily:T.mono,marginTop:16,fontWeight:600}}>No Performance Data Yet</div><div style={{fontSize:11,color:T.light,fontFamily:T.mono,marginTop:8,maxWidth:400,margin:"8px auto 0",lineHeight:1.6}}>Performance tracking starts after the first v7.1 scan runs. Paper trades are auto-opened for every BUY/STRONG BUY signal.</div></Card>;

  const s=data.stats;
  return(
    <>
      <div style={{display:"grid",gridTemplateColumns:"repeat(5,1fr)",gap:10,marginBottom:20}}>
        <KPI label="OPEN" value={String(s.open_positions)} sub={`Avg P&L: ${s.open_avg_pnl>=0?"+":""}${s.open_avg_pnl.toFixed(1)}%`}/>
        <KPI label="CLOSED" value={String(s.total_closed)} sub={`Best: ${s.best_trade}`}/>
        <KPI label="WIN RATE" value={`${s.win_rate.toFixed(0)}%`} color={s.win_rate>=50?"#10b981":T.red} sub={`Worst: ${s.worst_trade}`}/>
        <KPI label="AVG P&L" value={`${s.avg_pnl_pct>=0?"+":""}${s.avg_pnl_pct.toFixed(1)}%`} color={s.avg_pnl_pct>=0?"#10b981":T.red} sub={`Avg hold: ${s.avg_days_held}d`}/>
        <KPI label="ANNUALIZED" value={`${s.avg_annualized>=0?"+":""}${s.avg_annualized.toFixed(0)}%`} color={s.avg_annualized>=0?"#10b981":T.red} sub={`Backtest: +${s.backtest_expected_ann.toFixed(0)}%`}/>
      </div>
      <div style={{display:"grid",gridTemplateColumns:"2fr 1fr",gap:14,marginBottom:20}}>
        <ComparisonBar live={s.avg_annualized} backtest={s.backtest_expected_ann}/>
        {s.sector_exposure&&Object.keys(s.sector_exposure).length>0&&<SectorExposure sectors={s.sector_exposure}/>}
      </div>

      {/* Open Positions */}
      <Card style={{marginBottom:20}}>
        <SH title={`Open Positions (${openTrades.length})`} icon={<TrendingUp size={12}/>} sub="Sorted by unrealized P&L"/>
        {openTrades.length===0?<div style={{padding:20,textAlign:"center",color:T.light,fontSize:11,fontFamily:T.mono}}>No open trades</div>:(
          <div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse"}}><thead><tr>{["Symbol","Entry","Current","P&L","Days","Signal","Sector","Size","Regime"].map((h,i)=><th key={h} style={{...th,textAlign:i===0?"left":"right"}}>{h}</th>)}</tr></thead><tbody>{openTrades.map(t=>{const pC=t.pnl_pct>=0?"#10b981":T.red;return<tr key={t.symbol} style={{cursor:"pointer"}} onClick={()=>router.push(`/stock/${t.symbol}`)} onMouseEnter={e=>{(e.currentTarget as HTMLElement).style.background="#f8faf9";}} onMouseLeave={e=>{(e.currentTarget as HTMLElement).style.background="";}}><td style={{...td,textAlign:"left",fontWeight:600,color:T.text}}>{t.symbol}</td><td style={{...td,textAlign:"right",color:T.muted}}>${t.entry_price.toFixed(2)}</td><td style={{...td,textAlign:"right",fontWeight:600,color:T.text}}>${t.last_price.toFixed(2)}</td><td style={{...td,textAlign:"right",fontWeight:700,color:pC}}>{t.pnl_pct>=0?"+":""}{t.pnl_pct.toFixed(1)}%</td><td style={{...td,textAlign:"right",color:T.muted}}>{t.days_held}d</td><td style={{...td,textAlign:"right"}}><SignalBadge signal={t.last_signal}/></td><td style={{...td,textAlign:"right",color:T.light,fontSize:10}}>{t.sector?.slice(0,12)||"—"}</td><td style={{...td,textAlign:"right",color:T.muted}}>{t.position_size_pct?.toFixed(0)||"—"}%</td><td style={{...td,textAlign:"right"}}><RegimeBadge regime={t.regime_at_entry}/></td></tr>;})}</tbody></table></div>
        )}
      </Card>

      {/* Closed Trades */}
      <Card>
        <SH title={`Closed Trades (${data.closed_trades?.length||0})`} icon={<Clock size={12}/>} sub="Click column to sort"/>
        {sortedClosed.length===0?<div style={{padding:20,textAlign:"center",color:T.light,fontSize:11,fontFamily:T.mono}}>No closed trades yet</div>:(
          <div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse"}}><thead><tr><th style={{...th,textAlign:"left"}}>Symbol</th><th style={{...th,textAlign:"right"}}>Entry</th><th style={{...th,textAlign:"right"}}>Exit</th><th style={{...th,textAlign:"right",cursor:"pointer",color:closedSort==="pnl"?T.green:T.muted}} onClick={()=>toggleSort("pnl")}>P&L {closedSort==="pnl"?(closedDir==="desc"?"↓":"↑"):""}</th><th style={{...th,textAlign:"right",cursor:"pointer",color:closedSort==="days"?T.green:T.muted}} onClick={()=>toggleSort("days")}>Days {closedSort==="days"?(closedDir==="desc"?"↓":"↑"):""}</th><th style={{...th,textAlign:"right"}}>Ann%</th><th style={{...th,textAlign:"right"}}>Entry</th><th style={{...th,textAlign:"right"}}>Exit</th><th style={{...th,textAlign:"right",cursor:"pointer",color:closedSort==="date"?T.green:T.muted}} onClick={()=>toggleSort("date")}>Date {closedSort==="date"?(closedDir==="desc"?"↓":"↑"):""}</th></tr></thead><tbody>{sortedClosed.map((t,i)=>{const pC=t.pnl_pct>=0?"#10b981":T.red;return<tr key={i} onMouseEnter={e=>{(e.currentTarget as HTMLElement).style.background="#f8faf9";}} onMouseLeave={e=>{(e.currentTarget as HTMLElement).style.background="";}}><td style={{...td,textAlign:"left",fontWeight:600,color:T.text}}>{t.symbol||`Trade ${i+1}`}</td><td style={{...td,textAlign:"right",color:T.muted}}>${t.entry_price.toFixed(2)}</td><td style={{...td,textAlign:"right",color:T.text,fontWeight:600}}>${t.exit_price.toFixed(2)}</td><td style={{...td,textAlign:"right",fontWeight:700,color:pC}}>{t.pnl_pct>=0?"+":""}{t.pnl_pct.toFixed(1)}%</td><td style={{...td,textAlign:"right",color:T.muted}}>{t.days_held}d</td><td style={{...td,textAlign:"right",fontWeight:600,color:t.annualized_return>=0?"#10b981":T.red}}>{t.annualized_return>=0?"+":""}{t.annualized_return.toFixed(0)}%</td><td style={{...td,textAlign:"right"}}><SignalBadge signal={t.entry_signal}/></td><td style={{...td,textAlign:"right"}}><SignalBadge signal={t.exit_signal}/></td><td style={{...td,textAlign:"right",color:T.light,fontSize:10}}>{t.exit_date}</td></tr>;})}</tbody></table></div>
        )}
      </Card>
    </>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB 2: SIGNAL HISTORY — per-stock signal evolution over time
// ══════════════════════════════════════════════════════════════════════════════
function SignalHistoryTab(){
  const[signals,setSignals]=useState<Record<string,SignalEntry[]>>({});
  const[loading,setLoading]=useState(true);
  const[search,setSearch]=useState("");
  const router=useRouter();

  useEffect(()=>{
    // Fetch last 30 days of signal files
    const dates:string[]=[];
    const now=new Date();
    for(let i=0;i<30;i++){const d=new Date(now);d.setDate(d.getDate()-i);if(d.getDay()!==0&&d.getDay()!==6)dates.push(d.toISOString().split("T")[0]);}

    Promise.allSettled(dates.map(dt=>fetch(`${GCS_SIGNALS}/${dt}.json`).then(r=>{if(!r.ok)throw new Error();return r.json();}).then(data=>{const entries:SignalEntry[]=data.signals||[];return{date:dt,entries};}))).then(results=>{
      const bySymbol:Record<string,SignalEntry[]>={};
      results.forEach(r=>{if(r.status==="fulfilled"){const{date,entries}=r.value;entries.forEach(e=>{if(!bySymbol[e.symbol])bySymbol[e.symbol]=[];bySymbol[e.symbol].push({...e,date});});}});
      // Sort each stock's entries chronologically
      Object.values(bySymbol).forEach(arr=>arr.sort((a,b)=>a.date.localeCompare(b.date)));
      setSignals(bySymbol);
      setLoading(false);
    });
  },[]);

  const symbols=useMemo(()=>{
    let list=Object.keys(signals).sort();
    if(search){const q=search.toUpperCase();list=list.filter(s=>s.includes(q));}
    return list;
  },[signals,search]);

  if(loading) return<div style={{padding:40,textAlign:"center",color:T.muted,fontFamily:T.mono,fontSize:12}}>Loading signal history (30 days)...</div>;

  const totalSymbols=Object.keys(signals).length;
  if(totalSymbols===0) return<Card style={{padding:"60px 20px",textAlign:"center"}}><Radio size={36} color={T.divider}/><div style={{fontSize:14,color:T.muted,fontFamily:T.mono,marginTop:16,fontWeight:600}}>No Signal History Yet</div><div style={{fontSize:11,color:T.light,fontFamily:T.mono,marginTop:8,maxWidth:400,margin:"8px auto 0",lineHeight:1.6}}>Signal history accumulates as the screener runs daily. After 2-4 weeks, you'll see how each stock's signal evolved and which calls were right.</div></Card>;

  return(
    <>
      <div style={{display:"flex",gap:10,marginBottom:16}}>
        <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search symbol..." style={{flex:1,maxWidth:280,padding:"7px 12px",fontSize:12,fontFamily:T.mono,border:`1px solid ${T.border}`,borderRadius:6,outline:"none"}}/>
        <span style={{fontSize:10,fontFamily:T.mono,color:T.light,alignSelf:"center"}}>{totalSymbols} stocks tracked · {Object.values(signals).reduce((s,a)=>s+a.length,0)} data points</span>
      </div>
      <Card style={{padding:0,overflow:"hidden"}}>
        <div style={{overflowX:"auto"}}>
          <table style={{width:"100%",borderCollapse:"collapse"}}>
            <thead><tr>
              <th style={{...th,textAlign:"left"}}>Symbol</th>
              <th style={{...th,textAlign:"left"}}>Signal Timeline</th>
              <th style={{...th,textAlign:"right"}}>Latest</th>
              <th style={{...th,textAlign:"right"}}>Composite</th>
              <th style={{...th,textAlign:"right"}}>Price</th>
              <th style={{...th,textAlign:"right"}}>First Seen</th>
              <th style={{...th,textAlign:"right"}}>Days</th>
            </tr></thead>
            <tbody>
              {symbols.slice(0,100).map(sym=>{
                const entries=signals[sym];
                const latest=entries[entries.length-1];
                const first=entries[0];
                const days=Math.floor((new Date(latest.date).getTime()-new Date(first.date).getTime())/86400000);
                const priceDelta=first.price>0?((latest.price-first.price)/first.price*100):0;
                // Build signal timeline as colored dots
                const timeline=entries.map(e=>e.signal);

                return(
                  <tr key={sym} style={{cursor:"pointer"}} onClick={()=>router.push(`/stock/${sym}`)}
                    onMouseEnter={e=>{(e.currentTarget as HTMLElement).style.background="#f8faf9";}}
                    onMouseLeave={e=>{(e.currentTarget as HTMLElement).style.background="";}}>
                    <td style={{...td,textAlign:"left",fontWeight:600,color:T.text}}>{sym}</td>
                    <td style={{...td,textAlign:"left",padding:"9px 6px"}}>
                      <div style={{display:"flex",gap:2,alignItems:"center"}}>
                        {timeline.map((sig,i)=>{const c=(SIG[sig]||SIG.HOLD).color;return<div key={i} style={{width:8,height:8,borderRadius:"50%",background:c,border:`1px solid ${c}`,flexShrink:0}} title={`${entries[i].date}: ${sig} (${entries[i].composite.toFixed(2)})`}/>;})}
                      </div>
                    </td>
                    <td style={{...td,textAlign:"right"}}><SignalBadge signal={latest.signal}/></td>
                    <td style={{...td,textAlign:"right",fontWeight:600,color:latest.composite>0.6?"#10b981":latest.composite>0.4?T.text:T.red}}>{latest.composite.toFixed(2)}</td>
                    <td style={{...td,textAlign:"right"}}>
                      <span style={{color:T.text}}>${latest.price.toFixed(2)}</span>
                      {priceDelta!==0&&<span style={{fontSize:9,marginLeft:4,color:priceDelta>0?"#10b981":T.red}}>{priceDelta>0?"+":""}{priceDelta.toFixed(1)}%</span>}
                    </td>
                    <td style={{...td,textAlign:"right",color:T.light,fontSize:10}}>{first.date}</td>
                    <td style={{...td,textAlign:"right",color:T.muted}}>{days}d</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB 3: HIT RATES — aggregate accuracy by signal type
// ══════════════════════════════════════════════════════════════════════════════
function HitRatesTab(){
  const[data,setData]=useState<TrackerData|null>(null);
  const[loading,setLoading]=useState(true);

  useEffect(()=>{fetch(GCS_PERF).then(r=>{if(!r.ok)throw new Error();return r.json();}).then(d=>{setData(d);setLoading(false);}).catch(()=>setLoading(false));},[]);

  if(loading) return<div style={{padding:40,textAlign:"center",color:T.muted,fontFamily:T.mono,fontSize:12}}>Loading...</div>;

  const closed=data?.closed_trades||[];
  if(closed.length<3) return<Card style={{padding:"60px 20px",textAlign:"center"}}><Radio size={36} color={T.divider}/><div style={{fontSize:14,color:T.muted,fontFamily:T.mono,marginTop:16,fontWeight:600}}>Need More Data</div><div style={{fontSize:11,color:T.light,fontFamily:T.mono,marginTop:8,maxWidth:400,margin:"8px auto 0",lineHeight:1.6}}>Hit rate analysis requires at least 3 closed trades. The screener will accumulate trades over time as signals trigger entries and exits.</div></Card>;

  // Group by entry signal
  const groups:Record<string,{wins:number;losses:number;avgPnl:number;avgDays:number;count:number}>={};
  closed.forEach(t=>{
    const sig=t.entry_signal||"UNKNOWN";
    if(!groups[sig]) groups[sig]={wins:0,losses:0,avgPnl:0,avgDays:0,count:0};
    groups[sig].count++;
    groups[sig].avgPnl+=t.pnl_pct;
    groups[sig].avgDays+=t.days_held;
    if(t.pnl_pct>0) groups[sig].wins++; else groups[sig].losses++;
  });
  Object.values(groups).forEach(g=>{g.avgPnl/=g.count;g.avgDays/=g.count;});

  const signalOrder=["STRONG BUY","BUY","WATCH","HOLD","SELL"];

  return(
    <>
      <Card style={{marginBottom:20}}>
        <SH title="Hit Rate by Entry Signal" icon={<Target size={12}/>} sub={`${closed.length} closed trades`}/>
        <div style={{display:"grid",gridTemplateColumns:`repeat(${Object.keys(groups).length},1fr)`,gap:14}}>
          {signalOrder.filter(s=>groups[s]).map(sig=>{
            const g=groups[sig];const winRate=g.count>0?g.wins/g.count*100:0;const sc=SIG[sig]||SIG.HOLD;
            return(
              <div key={sig} style={{textAlign:"center",padding:"12px 8px",borderRadius:8,border:`1px solid ${sc.border}`,background:sc.bg}}>
                <SignalBadge signal={sig}/>
                <div style={{fontSize:28,fontWeight:700,color:winRate>=50?"#10b981":T.red,fontFamily:T.mono,marginTop:8}}>{winRate.toFixed(0)}%</div>
                <div style={{fontSize:9,color:T.muted,fontFamily:T.mono}}>win rate</div>
                <div style={{fontSize:11,fontFamily:T.mono,color:g.avgPnl>=0?"#10b981":T.red,marginTop:6,fontWeight:600}}>{g.avgPnl>=0?"+":""}{g.avgPnl.toFixed(1)}% avg</div>
                <div style={{fontSize:9,color:T.light,fontFamily:T.mono,marginTop:2}}>{g.count} trades · {g.avgDays.toFixed(0)}d avg</div>
              </div>
            );
          })}
        </div>
      </Card>

      {/* Backtest reference */}
      <Card>
        <SH title="Backtest Reference" icon={<BarChart3 size={12}/>} sub="15,120 samples · Jan 2024 → Dec 2025"/>
        <div style={{overflowX:"auto"}}>
          <table style={{width:"100%",borderCollapse:"collapse"}}>
            <thead><tr><th style={{...th,textAlign:"left"}}>Composite Band</th><th style={{...th,textAlign:"right"}}>P(+10% 60d)</th><th style={{...th,textAlign:"right"}}>Exp. Gain</th><th style={{...th,textAlign:"right"}}>Exp. DD</th><th style={{...th,textAlign:"right"}}>Avg Speed</th></tr></thead>
            <tbody>
              {[{band:"≥ 0.90",p:72,g:25.7,d:-9.1,s:18},{band:"0.85–0.90",p:53,g:17.9,d:-9.8,s:22},{band:"0.80–0.85",p:53,g:17.9,d:-9.8,s:22},{band:"0.75–0.80",p:44,g:12.8,d:-10.8,s:24},{band:"0.70–0.75",p:44,g:12.8,d:-10.8,s:24},{band:"0.65–0.70",p:43,g:12.1,d:-10.3,s:26},{band:"< 0.65",p:37,g:10.7,d:-10.7,s:22}].map(r=>(
                <tr key={r.band}>
                  <td style={{...td,textAlign:"left",fontWeight:600}}>{r.band}</td>
                  <td style={{...td,textAlign:"right",fontWeight:700,color:r.p>60?"#10b981":r.p>40?T.amber:T.red}}>{r.p}%</td>
                  <td style={{...td,textAlign:"right",color:"#10b981"}}>+{r.g}%</td>
                  <td style={{...td,textAlign:"right",color:T.red}}>{r.d}%</td>
                  <td style={{...td,textAlign:"right",color:T.muted}}>{r.s}d</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{fontSize:9,color:T.light,fontFamily:T.mono,marginTop:8}}>Top-20 portfolio backtest: +63%/yr, +43% alpha over S&P 500. GBM model 61.6% accuracy.</div>
      </Card>
    </>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// MAIN PAGE
// ══════════════════════════════════════════════════════════════════════════════
export default function PerformancePage(){
  const router=useRouter();
  const[tab,setTab]=useState<"tracker"|"signals"|"hitrates">("tracker");
  const[trackerData,setTrackerData]=useState<TrackerData|null>(null);
  const[loading,setLoading]=useState(true);

  useEffect(()=>{fetch(GCS_PERF).then(r=>{if(!r.ok)throw new Error();return r.json();}).then(d=>{setTrackerData(d);setLoading(false);}).catch(()=>setLoading(false));},[]);

  const s=trackerData?.stats;

  return(
    <div style={{minHeight:"100vh",padding:"20px 24px",maxWidth:1320,margin:"0 auto"}}>
      {/* Header */}
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:20,paddingBottom:12,borderBottom:`1px solid ${T.divider}`}}>
        <div>
          <span style={{fontSize:14,fontWeight:600,color:T.text,fontFamily:T.mono}}>PERFORMANCE<span style={{color:T.light,fontWeight:400}}>/tracker</span></span>
          <div style={{fontSize:10,color:T.light,fontFamily:T.mono,marginTop:2}}>v7.1 signals — paper trades + signal history</div>
        </div>
        {s&&<div style={{display:"flex",alignItems:"center",gap:12}}><RegimeBadge regime={s.current_regime}/><span style={{fontSize:9,color:T.light,fontFamily:T.mono}}>Updated: {s.updated}</span></div>}
      </div>

      {/* Tabs */}
      <div style={{display:"flex",gap:4,marginBottom:20}}>
        {([["tracker","Tracker",<TrendingUp key="t" size={12}/>],["signals","Signal History",<Radio key="s" size={12}/>],["hitrates","Hit Rates",<Target key="h" size={12}/>]] as const).map(([key,label,icon])=>(
          <button key={key} onClick={()=>setTab(key as any)} style={{display:"flex",alignItems:"center",gap:5,padding:"7px 16px",fontSize:12,fontFamily:T.mono,fontWeight:600,border:"none",borderRadius:6,cursor:"pointer",background:tab===key?T.greenLight:"transparent",color:tab===key?T.green:T.muted,transition:"all 0.15s"}}>{icon} {label}</button>
        ))}
      </div>

      {/* Tab content */}
      {tab==="tracker"&&<TrackerTab data={trackerData} router={router}/>}
      {tab==="signals"&&<SignalHistoryTab/>}
      {tab==="hitrates"&&<HitRatesTab/>}

      <div style={{textAlign:"center",marginTop:14,fontSize:9,color:T.light,fontFamily:T.mono}}>
        Paper trades auto-opened on BUY/STRONG BUY, closed on signal downgrade · Backtest: 15,120 samples Jan24→Dec25
      </div>
    </div>
  );
}
