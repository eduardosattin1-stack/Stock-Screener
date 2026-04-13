"use client";
import { useState, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { Trash2, BarChart3, AlertTriangle, ChevronDown, ChevronRight, TrendingUp, TrendingDown, Zap, Plus, Edit2, CloudUpload } from "lucide-react";

const GCS_SCANS = "/api/gcs/scans";
const GCS_PORTFOLIO = "/api/gcs/portfolio";

interface Position { symbol:string; entry_price:number; entry_date:string; shares:number; notes:string; entry_composite?:number; entry_signal?:string; peak_price?:number; last_composite?:number; last_signal?:string; }
interface MonitorAction { symbol:string; action:string; urgency:string; current_price:number; entry_price:number; pnl_pct:number; entry_composite:number; current_composite:number; comp_change_pct:number; entry_signal:string; current_signal:string; days_held:number; catalyst_score:number; catalyst_flags:string[]; quality_score:number; bull_score:number; reasons:string[]; }
interface HistoryEntry { symbol:string; action:string; date:string; entry_price:number; exit_price:number; pnl_pct:number; reason:string; days_held:number; }
interface StockData { symbol:string; price:number; currency:string; composite:number; signal:string; classification:string; bull_score:number; }

const SIG: Record<string,{color:string;bg:string;border:string}> = {
  "STRONG BUY":{color:"#8b5cf6",bg:"#f5f3ff",border:"#ddd6fe"},
  BUY:{color:"#10b981",bg:"#e8f5ee",border:"#b8dcc8"},
  WATCH:{color:"#f59e0b",bg:"#fffbeb",border:"#fde68a"},
  HOLD:{color:"#6b7280",bg:"#f8fafc",border:"#e2e8f0"},
  SELL:{color:"#ef4444",bg:"#fef2f2",border:"#fecaca"},
};
const ACT_STYLE: Record<string,{color:string;bg:string;border:string;pulse?:boolean}> = {
  SELL:{color:"#ef4444",bg:"#fef2f2",border:"#fecaca",pulse:true},
  TRIM:{color:"#f59e0b",bg:"#fffbeb",border:"#fde68a"},
  ADD:{color:"#10b981",bg:"#e8f5ee",border:"#b8dcc8"},
  HOLD:{color:"#6b7280",bg:"transparent",border:"transparent"},
};

function getLocalPortfolio():Position[]{if(typeof window==="undefined")return[];try{return JSON.parse(localStorage.getItem("screener_portfolio")||"[]");}catch{return[];}}
function saveLocalPortfolio(p:Position[]){localStorage.setItem("screener_portfolio",JSON.stringify(p));}

export default function Portfolio(){
  const router=useRouter();
  const[portfolio,setPortfolio]=useState<Position[]>([]);
  const[monitors,setMonitors]=useState<Record<string,MonitorAction>>({});
  const[history,setHistory]=useState<HistoryEntry[]>([]);
  const[liveData,setLiveData]=useState<Record<string,StockData>>({});
  const[loading,setLoading]=useState(true);
  const[scanDate,setScanDate]=useState("—");
  const[tab,setTab]=useState<"positions"|"history">("positions");
  const[expandedRow,setExpandedRow]=useState<string|null>(null);
  const[source,setSource]=useState<"gcs"|"local">("local");
  
  // NEW: Modal State
  const [showModal, setShowModal] = useState(false);
  const [editForm, setEditForm] = useState({ symbol: '', entry_price: 0, shares: 0 });
  const [isSyncing, setIsSyncing] = useState(false);

  useEffect(()=>{
    Promise.allSettled([
      fetch(`${GCS_PORTFOLIO}/state.json`).then(r=>{if(!r.ok)throw new Error();return r.json();}),
      fetch(`${GCS_PORTFOLIO}/monitor.json`).then(r=>{if(!r.ok)throw new Error();return r.json();}),
      fetch(`${GCS_SCANS}/latest.json`).then(r=>r.json()),
    ]).then(([stateRes,monitorRes,scanRes])=>{
      if(stateRes.status==="fulfilled"&&stateRes.value?.positions){
        setPortfolio(stateRes.value.positions);
        if(stateRes.value.history) setHistory(stateRes.value.history);
        setSource("gcs");
      } else {
        setPortfolio(getLocalPortfolio());
        setSource("local");
      }
      if(monitorRes.status==="fulfilled"){
        const m:Record<string,MonitorAction>={};
        const d=monitorRes.value;
        if(Array.isArray(d)) d.forEach((a:MonitorAction)=>{m[a.symbol]=a;});
        else if(d&&typeof d==="object") Object.values(d).forEach((a:any)=>{if(a.symbol)m[a.symbol]=a;});
        setMonitors(m);
      }
      if(scanRes.status==="fulfilled"){
        const map:Record<string,StockData>={};
        scanRes.value.stocks?.forEach((s:StockData)=>{map[s.symbol]=s;});
        setLiveData(map);
        setScanDate(scanRes.value.scan_date?new Date(scanRes.value.scan_date).toLocaleString("en-GB",{day:"2-digit",month:"short",hour:"2-digit",minute:"2-digit"}):"—");
      }
      setLoading(false);
    });
  },[]);

  // NEW: Save Position Logic
  const handleSavePosition = () => {
    const current = [...portfolio];
    const idx = current.findIndex(p => p.symbol === editForm.symbol.toUpperCase());
    if (idx >= 0) {
      current[idx].shares = editForm.shares;
      current[idx].entry_price = editForm.entry_price;
    } else {
      current.push({
        symbol: editForm.symbol.toUpperCase(),
        entry_price: editForm.entry_price,
        shares: editForm.shares,
        entry_date: new Date().toISOString().split('T')[0],
        notes: "",
      });
    }
    setPortfolio(current);
    saveLocalPortfolio(current); // Always save locally as backup
    setSource("local"); // Data is now out of sync with GCS until they click Sync
    setShowModal(false);
  };

  // NEW: Sync to Cloud Logic
    const handleSync = async () => {
    setSyncing(true);
    try {
      // 1. Prepare the data to match what your route.ts expects
      const payload = {
        positions: positions,
        lastUpdated: new Date().toISOString(),
      };

      // 2. Send the POST request to your API
      const response = await fetch('/api/portfolio/sync', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error(`Server responded with ${response.status}`);
      }

      setLastSynced(new Date());
      alert('Sync successful! Google Cloud Storage updated.');
    } catch (error) {
      console.error('Sync failed:', error);
      alert('Failed to sync. Make sure your Vercel Environment Variables are set.');
    } finally {
      setSyncing(false);
    }
    };

  const removePosition = (sym: string) => {
    const pos = portfolio.find(p => p.symbol === sym);
    if (!pos) return;

    // 1. Ask the user for the exit price (defaults to current live price)
    const currentPrice = liveData[sym]?.price || pos.entry_price;
    const exitStr = window.prompt(`Closing ${sym}. Enter your final exit price:`, currentPrice.toString());
    
    // If they click Cancel on the prompt, abort the deletion
    if (exitStr === null) return; 

    const exitPrice = parseFloat(exitStr) || 0;
    const pnl_pct = (exitPrice - pos.entry_price) / pos.entry_price;
    const days_held = Math.floor((new Date().getTime() - new Date(pos.entry_date).getTime()) / (1000 * 3600 * 24));

    // 2. Create the History record
    const newHistoryEntry: HistoryEntry = {
      symbol: sym,
      action: "MANUAL SELL",
      date: new Date().toISOString().split('T')[0],
      entry_price: pos.entry_price,
      exit_price: exitPrice,
      pnl_pct: pnl_pct,
      reason: "Closed manually via UI",
      days_held: days_held >= 0 ? days_held : 0
    };

    // 3. Update the state: Remove from portfolio, add to history
    const updatedPortfolio = portfolio.filter(p => p.symbol !== sym);
    setPortfolio(updatedPortfolio);
    setHistory([newHistoryEntry, ...history]); // Put newest history at the top
    
    saveLocalPortfolio(updatedPortfolio);
    setSource("local"); // Prompts the user to hit "Sync to Cloud"
  };

  const stats=useMemo(()=>{
    let totalCost=0,totalValue=0,winners=0,losers=0;
    portfolio.forEach(p=>{const live=liveData[p.symbol];const cur=live?.price||p.entry_price;totalCost+=p.entry_price*p.shares;totalValue+=cur*p.shares;if(cur>p.entry_price)winners++;else if(cur<p.entry_price)losers++;});
    const pnl=totalValue-totalCost;
    return{totalCost,totalValue,pnl,pnlPct:totalCost>0?pnl/totalCost:0,winners,losers,positions:portfolio.length};
  },[portfolio,liveData]);

  const historyStats=useMemo(()=>{
    if(!history.length) return null;
    const wins=history.filter(h=>h.pnl_pct>0).length;
    const avgPnl=history.reduce((s,h)=>s+h.pnl_pct,0)/history.length;
    return{total:history.length,wins,winRate:wins/history.length,avgPnl};
  },[history]);

  const fmtMoney=(n:number)=>{if(Math.abs(n)>=1e6)return`$${(n/1e6).toFixed(1)}M`;if(Math.abs(n)>=1e3)return`$${(n/1e3).toFixed(1)}K`;return`$${n.toFixed(0)}`;};

  const cardStyle:React.CSSProperties={background:"#fff",borderRadius:8,border:"1px solid #e5e7eb",boxShadow:"0 1px 3px rgba(0,0,0,0.06)",padding:"14px 16px"};
  const thStyle:React.CSSProperties={padding:"9px 12px",fontSize:9,fontWeight:600,letterSpacing:"0.1em",textTransform:"uppercase",color:"#6b7280",fontFamily:"var(--font-mono)",borderBottom:"2px solid #e5e7eb",whiteSpace:"nowrap"};

  return(
    <div style={{minHeight:"100vh",padding:"20px 24px",maxWidth:1320,margin:"0 auto"}}>
      {/* Header */}
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:20,paddingBottom:12,borderBottom:"1px solid #f3f4f6"}}>
        <div style={{display:"flex",alignItems:"center",gap:12}}>
          <span style={{fontSize:14,fontWeight:600,color:"#1a1a1a",letterSpacing:"0.02em",fontFamily:"var(--font-mono)"}}>PORTFOLIO<span style={{color:"#9ca3af",fontWeight:400}}>/tracker</span></span>
          <span style={{fontSize:9,padding:"2px 6px",borderRadius:3,fontFamily:"var(--font-mono)",color:source==="gcs"?"#10b981":"#6b7280",background:source==="gcs"?"#e8f5ee":"#f8fafc",border:`1px solid ${source==="gcs"?"#b8dcc8":"#e2e8f0"}`}}>{source==="gcs"?"GCS":"Local (Unsynced)"}</span>
          {source === "local" && (
            <button onClick={handleSync} disabled={isSyncing} style={{display:"flex", alignItems:"center", gap:4, fontSize:10, padding:"4px 8px", borderRadius:4, border:"none", background:"#2563eb", color:"#fff", cursor:"pointer", fontFamily:"var(--font-mono)"}}>
              <CloudUpload size={12}/> {isSyncing ? "Syncing..." : "Sync to Cloud"}
            </button>
          )}
        </div>
        <span style={{fontSize:9,color:"#9ca3af",fontFamily:"var(--font-mono)"}}>Last scan: {scanDate}</span>
      </div>

      {/* Summary cards */}
      <div style={{display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:10,marginBottom:20}}>
        <div style={cardStyle}><div style={{fontSize:9,fontWeight:600,letterSpacing:"0.1em",color:"#6b7280",fontFamily:"var(--font-mono)"}}>POSITIONS</div><div style={{fontSize:26,fontWeight:700,color:"#1a1a1a",fontFamily:"var(--font-mono)",marginTop:4}}>{stats.positions}</div></div>
        <div style={cardStyle}><div style={{fontSize:9,fontWeight:600,letterSpacing:"0.1em",color:"#6b7280",fontFamily:"var(--font-mono)"}}>TOTAL VALUE</div><div style={{fontSize:26,fontWeight:700,color:"#1a1a1a",fontFamily:"var(--font-mono)",marginTop:4}}>{fmtMoney(stats.totalValue)}</div><div style={{fontSize:9,color:"#9ca3af",fontFamily:"var(--font-mono)"}}>Cost: {fmtMoney(stats.totalCost)}</div></div>
        <div style={{...cardStyle,border:`1px solid ${stats.pnl>=0?"#b8dcc8":"#fecaca"}`}}><div style={{fontSize:9,fontWeight:600,letterSpacing:"0.1em",color:"#6b7280",fontFamily:"var(--font-mono)"}}>TOTAL P&L</div><div style={{fontSize:26,fontWeight:700,fontFamily:"var(--font-mono)",marginTop:4,color:stats.pnl>=0?"#2d7a4f":"#ef4444"}}>{stats.pnl>=0?"+":""}{fmtMoney(stats.pnl)}</div><div style={{fontSize:9,fontFamily:"var(--font-mono)",color:stats.pnlPct>=0?"#2d7a4f":"#ef4444"}}>{stats.pnlPct>=0?"+":""}{(stats.pnlPct*100).toFixed(1)}%</div></div>
        <div style={cardStyle}><div style={{fontSize:9,fontWeight:600,letterSpacing:"0.1em",color:"#6b7280",fontFamily:"var(--font-mono)"}}>WIN / LOSS</div><div style={{display:"flex",alignItems:"baseline",gap:6,marginTop:6}}><span style={{fontSize:22,fontWeight:700,color:"#2d7a4f",fontFamily:"var(--font-mono)"}}>{stats.winners}</span><span style={{fontSize:12,color:"#9ca3af"}}>/</span><span style={{fontSize:22,fontWeight:700,color:"#ef4444",fontFamily:"var(--font-mono)"}}>{stats.losers}</span></div></div>
      </div>

      {/* Tabs & Controls */}
      <div style={{display:"flex", justifyContent:"space-between", alignItems:"center", marginBottom:16}}>
        <div style={{display:"flex",gap:4}}>
          {(["positions","history"] as const).map(t=>(
            <button key={t} onClick={()=>setTab(t)} style={{padding:"6px 14px",fontSize:11,fontFamily:"var(--font-mono)",fontWeight:600,border:"none",borderRadius:5,cursor:"pointer",background:tab===t?"#e8f5ee":"transparent",color:tab===t?"#2d7a4f":"#6b7280",transition:"all 0.15s",textTransform:"capitalize"}}>{t}{t==="history"&&history.length>0&&` (${history.length})`}</button>
          ))}
        </div>
        <button onClick={()=>{setEditForm({symbol:'',entry_price:0,shares:0}); setShowModal(true);}} style={{display:"flex", alignItems:"center", gap:6, padding:"6px 14px", fontSize:11, fontFamily:"var(--font-mono)", fontWeight:600, border:"1px solid #e5e7eb", borderRadius:5, cursor:"pointer", background:"#fff", color:"#1a1a1a"}}>
          <Plus size={13}/> Add Position
        </button>
      </div>

      {tab==="positions"&&(
        portfolio.length===0?(
          <div style={{...cardStyle,padding:"60px 20px",textAlign:"center"}}><BarChart3 size={32} color="#f3f4f6"/><div style={{fontSize:12,color:"#6b7280",fontFamily:"var(--font-mono)",marginTop:12}}>No positions yet</div><button onClick={()=>router.push("/")} style={{marginTop:16,fontSize:11,padding:"8px 16px",borderRadius:6,fontFamily:"var(--font-mono)",fontWeight:600,color:"#2d7a4f",background:"#e8f5ee",border:"1px solid #b8dcc8",cursor:"pointer"}}>Open Screener</button></div>
        ):(
          <div style={{...cardStyle,padding:0,overflow:"hidden"}}>
            <table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
              <thead><tr>
                {["Symbol","Action","Entry","Current","P&L","P&L %","Shares","Value","Signal","Composite",""].map((h,i)=>(
                  <th key={h||i} style={{...thStyle,textAlign:i===0?"left":i===10?"center":"right"}}>{h}</th>
                ))}
              </tr></thead>
              <tbody>
                {portfolio.map(p=>{
                  const live=liveData[p.symbol];const mon=monitors[p.symbol];
                  const cur=mon?.current_price||live?.price||p.entry_price;
                  const pnl=(cur-p.entry_price)*p.shares;const pnlPct=(cur-p.entry_price)/p.entry_price;
                  const val=cur*p.shares;const signal=mon?.current_signal||live?.signal||"—";
                  const composite=mon?.current_composite||live?.composite||0;
                  const pnlColor=pnl>=0?"#2d7a4f":"#ef4444";
                  const sigStyle=SIG[signal]||SIG.HOLD;
                  const actStyle=mon?ACT_STYLE[mon.action]||ACT_STYLE.HOLD:null;
                  const isExpanded=expandedRow===p.symbol;

                  return(
                    <>{/* eslint-disable-next-line react/jsx-key */}
                      <tr key={p.symbol} style={{borderBottom:"1px solid #f3f4f6",cursor:"pointer",transition:"background 0.1s"}}
                        onClick={()=>setExpandedRow(isExpanded?null:p.symbol)}
                        onMouseEnter={e=>{(e.currentTarget as HTMLElement).style.background="#f8faf9";}}
                        onMouseLeave={e=>{(e.currentTarget as HTMLElement).style.background="";}}>
                        <td style={{padding:"10px 12px"}}>
                          <div style={{display:"flex",alignItems:"center",gap:6}}>
                            {isExpanded?<ChevronDown size={11} color="#9ca3af"/>:<ChevronRight size={11} color="#9ca3af"/>}
                            <div>
                              <a href={`/stock/${p.symbol}`} onClick={e=>e.stopPropagation()} style={{fontWeight:600,color:"#1a1a1a",fontFamily:"var(--font-mono)",fontSize:12,letterSpacing:"0.04em"}}>{p.symbol}</a>
                              <div style={{fontSize:9,color:"#9ca3af",fontFamily:"var(--font-mono)"}}>{p.entry_date}</div>
                            </div>
                          </div>
                        </td>
                        <td style={{padding:"10px 8px",textAlign:"right"}}>
                          {actStyle&&mon?.action!=="HOLD"?(
                            <span style={{display:"inline-block",padding:"2px 7px",borderRadius:4,fontSize:9,fontWeight:700,fontFamily:"var(--font-mono)",letterSpacing:"0.07em",color:actStyle.color,background:actStyle.bg,border:`1px solid ${actStyle.border}`,animation:actStyle.pulse?"pulse 2s infinite":"none"}}>{mon!.action}</span>
                          ):<span style={{color:"#9ca3af",fontSize:9,fontFamily:"var(--font-mono)"}}>—</span>}
                        </td>
                        <td style={{fontFamily:"var(--font-mono)",textAlign:"right",padding:"10px 12px",color:"#6b7280",fontSize:11}}>${p.entry_price.toFixed(2)}</td>
                        <td style={{fontFamily:"var(--font-mono)",textAlign:"right",padding:"10px 12px",color:"#1a1a1a",fontSize:12,fontWeight:600}}>${cur.toFixed(2)}</td>
                        <td style={{fontFamily:"var(--font-mono)",textAlign:"right",padding:"10px 12px",color:pnlColor,fontSize:12,fontWeight:600}}>{pnl>=0?"+":""}{fmtMoney(pnl)}</td>
                        <td style={{fontFamily:"var(--font-mono)",textAlign:"right",padding:"10px 12px",color:pnlColor,fontSize:11,fontWeight:600}}>{pnlPct>=0?"+":""}{(pnlPct*100).toFixed(1)}%</td>
                        <td style={{fontFamily:"var(--font-mono)",textAlign:"right",padding:"10px 12px",color:"#6b7280",fontSize:11}}>{p.shares}</td>
                        <td style={{fontFamily:"var(--font-mono)",textAlign:"right",padding:"10px 12px",color:"#1a1a1a",fontSize:11}}>{fmtMoney(val)}</td>
                        <td style={{textAlign:"right",padding:"10px 12px"}}>{signal!=="—"?<span style={{display:"inline-block",padding:"2px 7px",borderRadius:4,fontSize:9,fontWeight:700,fontFamily:"var(--font-mono)",letterSpacing:"0.07em",color:sigStyle.color,background:sigStyle.bg,border:`1px solid ${sigStyle.border}`}}>{signal}</span>:<span style={{color:"#9ca3af",fontSize:10,fontFamily:"var(--font-mono)"}}>—</span>}</td>
                        <td style={{padding:"10px 12px",textAlign:"right"}}>
                          <div style={{display:"flex",alignItems:"center",justifyContent:"flex-end",gap:4}}>
                            {p.entry_composite!=null&&composite>0&&(
                              <span style={{fontSize:9,color:composite>=p.entry_composite?"#10b981":"#ef4444",fontFamily:"var(--font-mono)"}}>{composite>p.entry_composite?"↑":"↓"}</span>
                            )}
                            <span style={{fontFamily:"var(--font-mono)",fontSize:11,color:composite>0.6?"#2d7a4f":composite>0.4?"#1a1a1a":"#ef4444",fontWeight:600}}>{composite>0?composite.toFixed(2):"—"}</span>
                          </div>
                        </td>
                        <td style={{padding:"10px 6px",textAlign:"center"}}>
                          <div style={{display:"flex",gap:6,justifyContent:"center"}}>
                            <button onClick={e=>{e.stopPropagation(); setEditForm({symbol:p.symbol, entry_price:p.entry_price, shares:p.shares}); setShowModal(true);}} style={{background:"none",border:"none",cursor:"pointer",color:"#9ca3af"}}><Edit2 size={12}/></button>
                            <button onClick={e=>{e.stopPropagation();removePosition(p.symbol);}} style={{background:"none",border:"none",cursor:"pointer",color:"#9ca3af"}}><Trash2 size={12}/></button>
                          </div>
                        </td>
                      </tr>
                      {isExpanded&&mon&&mon.reasons?.length>0&&(
                        <tr key={`${p.symbol}-detail`}><td colSpan={11} style={{padding:"0 12px 12px 40px",background:"#f8faf9"}}>
                          <div style={{display:"flex",gap:16,paddingTop:8}}>
                            <div style={{flex:1}}>
                              <div style={{fontSize:9,fontWeight:600,letterSpacing:"0.08em",color:"#2d7a4f",fontFamily:"var(--font-mono)",marginBottom:6,textTransform:"uppercase"}}>Monitor Reasons</div>
                              <div style={{display:"flex",flexWrap:"wrap",gap:4}}>
                                {mon.reasons.map((r,i)=><span key={i} style={{fontSize:9,padding:"2px 7px",borderRadius:3,fontFamily:"var(--font-mono)",background:r.includes("⚠")?"#fef2f2":"#f8fafc",border:`1px solid ${r.includes("⚠")?"#fecaca":"#e2e8f0"}`,color:r.includes("⚠")?"#ef4444":"#6b7280"}}>{r}</span>)}
                              </div>
                            </div>
                            {mon.catalyst_flags?.length>0&&(
                              <div>
                                <div style={{fontSize:9,fontWeight:600,letterSpacing:"0.08em",color:"#8b5cf6",fontFamily:"var(--font-mono)",marginBottom:6,textTransform:"uppercase"}}>Catalysts</div>
                                <div style={{display:"flex",flexDirection:"column",gap:3}}>
                                  {mon.catalyst_flags.map((f,i)=><span key={i} style={{fontSize:9,fontFamily:"var(--font-mono)",color:"#8b5cf6",display:"flex",alignItems:"center",gap:3}}><Zap size={9}/>{f}</span>)}
                                </div>
                              </div>
                            )}
                            <div style={{textAlign:"right",fontSize:10,fontFamily:"var(--font-mono)",color:"#6b7280"}}>
                              <div>Held: {mon.days_held}d</div>
                              <div>Quality: {(mon.quality_score*100).toFixed(0)}</div>
                              <div>Bull: {mon.bull_score}/10</div>
                            </div>
                          </div>
                        </td></tr>
                      )}
                    </>
                  );
                })}
              </tbody>
            </table>
          </div>
        )
      )}

      {/* History Tab */}
      {tab==="history"&&(
        history.length===0?(
          <div style={{...cardStyle,padding:"40px 20px",textAlign:"center"}}><div style={{fontSize:12,color:"#6b7280",fontFamily:"var(--font-mono)"}}>No exit history yet</div><div style={{fontSize:10,color:"#9ca3af",fontFamily:"var(--font-mono)",marginTop:4}}>History populates as the monitor recommends exits</div></div>
        ):(
          <>
            {historyStats&&(
              <div style={{display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:10,marginBottom:16}}>
                <div style={cardStyle}><div style={{fontSize:9,fontWeight:600,letterSpacing:"0.1em",color:"#6b7280",fontFamily:"var(--font-mono)"}}>TRADES</div><div style={{fontSize:22,fontWeight:700,color:"#1a1a1a",fontFamily:"var(--font-mono)",marginTop:4}}>{historyStats.total}</div></div>
                <div style={cardStyle}><div style={{fontSize:9,fontWeight:600,letterSpacing:"0.1em",color:"#6b7280",fontFamily:"var(--font-mono)"}}>WIN RATE</div><div style={{fontSize:22,fontWeight:700,color:historyStats.winRate>=0.5?"#2d7a4f":"#ef4444",fontFamily:"var(--font-mono)",marginTop:4}}>{(historyStats.winRate*100).toFixed(0)}%</div></div>
                <div style={cardStyle}><div style={{fontSize:9,fontWeight:600,letterSpacing:"0.1em",color:"#6b7280",fontFamily:"var(--font-mono)"}}>AVG P&L</div><div style={{fontSize:22,fontWeight:700,color:historyStats.avgPnl>=0?"#2d7a4f":"#ef4444",fontFamily:"var(--font-mono)",marginTop:4}}>{historyStats.avgPnl>=0?"+":""}{(historyStats.avgPnl*100).toFixed(1)}%</div></div>
              </div>
            )}
            <div style={{...cardStyle,padding:0,overflow:"hidden"}}>
              <table style={{width:"100%",borderCollapse:"collapse",fontSize:12}}>
                <thead><tr>{["Symbol","Action","Date","Entry","Exit","P&L %","Days","Reason"].map((h,i)=><th key={h} style={{...thStyle,textAlign:i===0?"left":"right"}}>{h}</th>)}</tr></thead>
                <tbody>
                  {history.slice(0,20).map((h,i)=>{const c=h.pnl_pct>=0?"#2d7a4f":"#ef4444";return(
                    <tr key={i} style={{borderBottom:"1px solid #f3f4f6"}}>
                      <td style={{padding:"10px 12px",fontFamily:"var(--font-mono)",fontWeight:600,color:"#1a1a1a",fontSize:12}}>{h.symbol}</td>
                      <td style={{padding:"10px 12px",textAlign:"right",fontFamily:"var(--font-mono)",fontSize:10,color:"#6b7280"}}>{h.action}</td>
                      <td style={{padding:"10px 12px",textAlign:"right",fontFamily:"var(--font-mono)",fontSize:10,color:"#9ca3af"}}>{h.date}</td>
                      <td style={{padding:"10px 12px",textAlign:"right",fontFamily:"var(--font-mono)",fontSize:11,color:"#6b7280"}}>${h.entry_price.toFixed(2)}</td>
                      <td style={{padding:"10px 12px",textAlign:"right",fontFamily:"var(--font-mono)",fontSize:11,color:"#1a1a1a",fontWeight:600}}>${h.exit_price.toFixed(2)}</td>
                      <td style={{padding:"10px 12px",textAlign:"right",fontFamily:"var(--font-mono)",fontSize:11,fontWeight:700,color:c}}>{h.pnl_pct>=0?"+":""}{(h.pnl_pct*100).toFixed(1)}%</td>
                      <td style={{padding:"10px 12px",textAlign:"right",fontFamily:"var(--font-mono)",fontSize:10,color:"#9ca3af"}}>{h.days_held}d</td>
                      <td style={{padding:"10px 12px",textAlign:"right",fontFamily:"var(--font-mono)",fontSize:10,color:"#6b7280",maxWidth:200,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{h.reason}</td>
                    </tr>
                  );})}
                </tbody>
              </table>
            </div>
          </>
        )
      )}

      {/* ADD / EDIT MODAL */}
      {showModal && (
        <div style={{position:"fixed", top:0, left:0, right:0, bottom:0, background:"rgba(0,0,0,0.5)", zIndex:999, display:"flex", alignItems:"center", justifyContent:"center"}}>
          <div style={{background:"#fff", padding:24, borderRadius:8, width:320, boxShadow:"0 4px 6px rgba(0,0,0,0.1)"}}>
            <h3 style={{fontFamily:"var(--font-mono)", fontSize:14, marginBottom:16}}>{portfolio.find(p=>p.symbol===editForm.symbol.toUpperCase()) ? "Edit Position" : "Add Position"}</h3>
            <div style={{display:"flex", flexDirection:"column", gap:12, marginBottom:20}}>
              <div>
                <label style={{fontSize:10, color:"#6b7280", fontFamily:"var(--font-mono)", fontWeight:700}}>SYMBOL</label>
                <input value={editForm.symbol} onChange={e=>setEditForm({...editForm, symbol:e.target.value})} disabled={!!portfolio.find(p=>p.symbol===editForm.symbol.toUpperCase())} placeholder="AAPL" style={{width:"100%", padding:"8px", border:"1px solid #e5e7eb", borderRadius:4, marginTop:4, fontFamily:"var(--font-mono)", textTransform:"uppercase"}} />
              </div>
              <div>
                <label style={{fontSize:10, color:"#6b7280", fontFamily:"var(--font-mono)", fontWeight:700}}>ENTRY PRICE ($)</label>
                <input type="number" value={editForm.entry_price || ""} onChange={e=>setEditForm({...editForm, entry_price:parseFloat(e.target.value) || 0})} placeholder="150.00" style={{width:"100%", padding:"8px", border:"1px solid #e5e7eb", borderRadius:4, marginTop:4, fontFamily:"var(--font-mono)"}} />
              </div>
              <div>
                <label style={{fontSize:10, color:"#6b7280", fontFamily:"var(--font-mono)", fontWeight:700}}>SHARES</label>
                <input type="number" value={editForm.shares || ""} onChange={e=>setEditForm({...editForm, shares:parseFloat(e.target.value) || 0})} placeholder="10" style={{width:"100%", padding:"8px", border:"1px solid #e5e7eb", borderRadius:4, marginTop:4, fontFamily:"var(--font-mono)"}} />
              </div>
            </div>
            <div style={{display:"flex", justifyContent:"flex-end", gap:8}}>
              <button onClick={()=>setShowModal(false)} style={{padding:"8px 16px", borderRadius:4, border:"1px solid #e5e7eb", background:"#fff", cursor:"pointer", fontFamily:"var(--font-mono)", fontSize:11, fontWeight:600}}>Cancel</button>
              <button onClick={handleSavePosition} style={{padding:"8px 16px", borderRadius:4, border:"none", background:"#2d7a4f", color:"#fff", cursor:"pointer", fontFamily:"var(--font-mono)", fontSize:11, fontWeight:600}}>Save Position</button>
            </div>
          </div>
        </div>
      )}

      <div style={{textAlign:"center",marginTop:12,fontSize:9,color:"#9ca3af",fontFamily:"var(--font-mono)"}}>
        {source==="gcs"?"Positions in sync with Cloud Monitor":"Prices from latest scan · Stored locally"} · <a href="/" style={{color:"#2d7a4f"}}>Screener</a>
      </div>
    </div>
  );
}