"use client";
import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, TrendingUp, TrendingDown, Minus, Activity, Brain, RefreshCw, Loader2, Newspaper, BarChart2, Zap, Shield } from "lucide-react";

const GCS_SCANS="/api/gcs/scans";const GCS_SIGNALS="/api/gcs/signals";const FMP="/api/fmp";

// ── Types ──────────────────────────────────────────────────────────────────────
interface FactorScores{technical:number|null;quality:number|null;proximity:number|null;catalyst:number|null;transcript:number|null;upside:number|null;institutional:number|null;analyst:number|null;insider:number|null;earnings:number|null;}
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
  composite:number;signal:string;classification:string;reasons:string[];
  factor_scores?:FactorScores;
  quality_score?:number;catalyst_score?:number;catalyst_flags?:string[];
  has_catalyst?:boolean;days_to_earnings?:number;
  insider_score?:number;insider_net_buys?:number;insider_buy_ratio?:number;
  inst_score?:number;inst_holders_change?:number;inst_accumulation?:number;
  transcript_sentiment?:number;transcript_summary?:string;transcript_score?:number;
  proximity_52wk?:number;proximity_score?:number;
  earnings_momentum?:number;earnings_score?:number;upside_score?:number;
  hit_prob?:number;
  factor_coverage?:number;factors_evaluated?:string[];factors_missing?:string[];
}
interface SignalPoint{date:string;composite:number;signal:string;price:number;bull:number;mos:number;}
interface NewsItem{title:string;url:string;publishedDate:string;site:string;}
interface IncomeRow{date:string;calendarYear:string;revenue:number;grossProfit:number;operatingIncome:number;netIncome:number;epsdiluted:number;ebitda:number;}
interface RatioYear{date:string;fiscalYear:string;grossProfitMargin:number;operatingProfitMargin:number;netProfitMargin:number;returnOnEquity:number;returnOnAssets:number;returnOnCapitalEmployed:number;currentRatio:number;debtToEquityRatio:number;priceToEarningsRatio:number;priceToSalesRatio:number;priceToBookRatio:number;priceToFreeCashFlowRatio:number;dividendYieldPercentage:number;freeCashFlowOperatingCashFlowRatio:number;interestCoverageRatio:number;dividendPayoutRatio:number;revenuePerShare:number;netIncomePerShare:number;bookValuePerShare:number;freeCashFlowPerShare:number;operatingCashFlowPerShare:number;dividendPerShare:number;priceToOperatingCashFlowRatio:number;priceToEarningsGrowthRatio:number;}
interface CompositePoint{date:string;composite:number;signal:string;price:number;}

// ── Theme ──────────────────────────────────────────────────────────────────────
const T={bg:"#ffffff",card:"#ffffff",cardBorder:"#e5e7eb",cardShadow:"0 1px 3px rgba(0,0,0,0.06),0 1px 2px rgba(0,0,0,0.04)",text:"#1a1a1a",textMuted:"#6b7280",textLight:"#9ca3af",green:"#2d7a4f",greenLight:"#e8f5ee",greenBorder:"#b8dcc8",red:"#ef4444",redLight:"#fef2f2",amber:"#f59e0b",amberLight:"#fffbeb",blue:"#2563eb",purple:"#8b5cf6",divider:"#f3f4f6",mono:"'JetBrains Mono','SF Mono',monospace",sans:"'DM Sans',-apple-system,sans-serif"};
const SIG_C:Record<string,{bg:string;fg:string;border:string}>={"STRONG BUY":{bg:"#f5f3ff",fg:"#8b5cf6",border:"#ddd6fe"},BUY:{bg:T.greenLight,fg:"#10b981",border:T.greenBorder},WATCH:{bg:T.amberLight,fg:T.amber,border:"#fde68a"},HOLD:{bg:"#f9fafb",fg:T.textMuted,border:T.cardBorder},SELL:{bg:T.redLight,fg:T.red,border:"#fecaca"}};
const CLS_C:Record<string,string>={DEEP_VALUE:T.blue,VALUE:T.blue,QUALITY_GROWTH:T.purple,GROWTH:"#818cf8",SPECULATIVE:T.red,NEUTRAL:T.textMuted};

// v7 factors
const FACTOR_ORDER=["technical","quality","upside","proximity","catalyst","transcript","institutional","analyst","insider","earnings"];
const FL:Record<string,string>={technical:"Technical",quality:"Quality",upside:"Upside",proximity:"52-Week",catalyst:"Catalyst",transcript:"Transcript",institutional:"Institutional",analyst:"Analyst",insider:"Insider",earnings:"Earnings"};
const FW:Record<string,number>={technical:35,quality:14,upside:10,proximity:8,catalyst:8,transcript:7,institutional:5,analyst:5,insider:4,earnings:4};

// ── Helpers ────────────────────────────────────────────────────────────────────
const fmtPct=(n:number|null|undefined)=>n==null?"—":`${(n*100).toFixed(1)}%`;
const fmtPrice=(n:number|null|undefined,c?:string)=>{if(n==null||n===0)return"—";return`${c==="EUR"?"€":c==="GBP"?"£":"$"}${n.toFixed(2)}`;};
const gClr=(v:number|null)=>{if(v==null)return T.textLight;if(v>0.15)return T.green;if(v>0.05)return"#5a9e7a";if(v>0)return T.textMuted;return T.red;};
function safeCagr(s:number,e:number,y:number):number|null{if(!s||!e||s<=0||e<=0||y<=0)return null;return Math.pow(e/s,1/y)-1;}
function inferFactors(s:StockData):FactorScores{if(s.factor_scores)return s.factor_scores;return{technical:Math.min(1,(s.bull_score||0)/10),quality:s.quality_score??Math.min(1,((s.piotroski||0)/9*0.4+Math.min(1,(s.altman_z||0)/10)*0.2+Math.min(1,(s.roe_avg||0)/0.3)*0.2+Math.min(1,(s.gross_margin||0))*0.2)),upside:s.upside_score??Math.min(1,Math.max(0,(s.upside||0)/80)),proximity:s.proximity_score??(s.year_high>0?(s.price-s.year_low)/(s.year_high-s.year_low):0.5),catalyst:s.catalyst_score??0.5,transcript:s.transcript_score??null,institutional:s.inst_score??null,analyst:s.grade_score||null,insider:s.insider_score??null,earnings:s.earnings_score??Math.min(1,(s.eps_beats||0)/Math.max(1,s.eps_total||1))} as FactorScores;}
function getProb(c:number){if(c>=0.90)return{p5:79,p10:72,p20:42,gain:25.7,dd:-9.1,speed:18};if(c>=0.85)return{p5:68,p10:53,p20:28,gain:17.9,dd:-9.8,speed:22};if(c>=0.80)return{p5:65,p10:53,p20:28,gain:17.9,dd:-9.8,speed:22};if(c>=0.75)return{p5:60,p10:44,p20:20,gain:12.8,dd:-10.8,speed:24};if(c>=0.70)return{p5:58,p10:44,p20:18,gain:12.8,dd:-10.8,speed:24};if(c>=0.65)return{p5:55,p10:43,p20:16,gain:12.1,dd:-10.3,speed:26};return{p5:48,p10:37,p20:12,gain:10.7,dd:-10.7,speed:22};}
async function fmpFetch(ep:string,p:Record<string,string|number>){const qs=new URLSearchParams();qs.set("e",ep);Object.entries(p).forEach(([k,v])=>qs.set(k,String(v)));try{const r=await fetch(`${FMP}?${qs}`);if(!r.ok)return null;const d=await r.json();return Array.isArray(d)?d:d?[d]:null;}catch{return null;}}

// ── Shared Components ──────────────────────────────────────────────────────────
function Card({children,style}:{children:React.ReactNode;style?:React.CSSProperties}){return<div style={{background:T.card,borderRadius:8,border:`1px solid ${T.cardBorder}`,boxShadow:T.cardShadow,padding:"16px 18px",...style}}>{children}</div>;}
function SH({title,icon,sub}:{title:string;icon?:React.ReactNode;sub?:string}){return<div style={{display:"flex",alignItems:"center",gap:6,fontSize:11,fontWeight:600,letterSpacing:"0.08em",color:T.green,fontFamily:T.mono,textTransform:"uppercase",marginBottom:12,paddingBottom:8,borderBottom:`2px solid ${T.greenLight}`}}>{icon}{title}{sub&&<span style={{marginLeft:"auto",fontSize:9,color:T.textLight,fontWeight:400,textTransform:"none",letterSpacing:0}}>{sub}</span>}</div>;}
function Metric({label,value,color,sub}:{label:string;value:string;color?:string;sub?:string}){return<div style={{padding:"7px 0",borderBottom:`1px solid ${T.divider}`}}><div style={{display:"flex",justifyContent:"space-between",alignItems:"baseline"}}><span style={{fontSize:11,color:T.textMuted,fontFamily:T.mono,fontWeight:500}}>{label}</span><span style={{fontSize:12,color:color||T.text,fontFamily:T.mono,fontWeight:600}}>{value}</span></div>{sub&&<div style={{fontSize:9,color:T.textLight,marginTop:2,fontFamily:T.mono}}>{sub}</div>}</div>;}
function ScoreRing({value,label,max,color}:{value:number;label:string;max:number;color:string}){const p=Math.min(value/max,1),r=26,ci=2*Math.PI*r,of=ci*(1-p);return<div style={{textAlign:"center"}}><svg width="62" height="62" viewBox="0 0 62 62"><circle cx="31" cy="31" r={r} fill="none" stroke={T.divider} strokeWidth="4"/><circle cx="31" cy="31" r={r} fill="none" stroke={color} strokeWidth="4" strokeDasharray={ci} strokeDashoffset={of} strokeLinecap="round" transform="rotate(-90 31 31)" style={{transition:"stroke-dashoffset 0.6s ease"}}/><text x="31" y="29" textAnchor="middle" fill={color} fontSize="13" fontFamily={T.mono} fontWeight="700">{value}</text><text x="31" y="41" textAnchor="middle" fill={T.textLight} fontSize="8" fontFamily={T.mono}>/{max}</text></svg><div style={{fontSize:9,color:T.textMuted,fontFamily:T.mono,marginTop:2}}>{label}</div></div>;}

// ── v7 Factor Radar ────────────────────────────────────────────────────────────
function FactorRadar({scores,size=260}:{scores:FactorScores;size?:number}){
  const cx=size/2,cy=size/2,r=size/2-36;const raw=FACTOR_ORDER.map(k=>(scores as any)[k]);const vals=raw.map(v=>v??0);const n=vals.length;
  const ang=(i:number)=>(Math.PI*2*i)/n-Math.PI/2;const grid=[0.25,0.5,0.75,1.0];
  const evaluated=raw.filter(v=>v!=null);const avg=evaluated.length?evaluated.reduce((a:number,b:number)=>a+b,0)/evaluated.length:0;
  const fill=avg>0.6?T.green:avg>0.4?T.amber:T.red;
  const covCount=evaluated.length;
  return(
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {grid.map((lv,gi)=>{const pts=Array.from({length:n},(_,i)=>`${cx+Math.cos(ang(i))*r*lv},${cy+Math.sin(ang(i))*r*lv}`).join(" ");return<polygon key={gi} points={pts} fill="none" stroke="#d1d5db" strokeWidth={gi===3?1:0.5} opacity={0.5}/>;})}
      {FACTOR_ORDER.map((k,i)=>{const a=ang(i),lx=cx+Math.cos(a)*(r+24),ly=cy+Math.sin(a)*(r+24),v=raw[i],isNull=v==null,c=isNull?"#d1d5db":((v??0)>0.7?"#10b981":(v??0)>0.4?T.amber:T.red);return<g key={k}><line x1={cx} y1={cy} x2={cx+Math.cos(a)*r} y2={cy+Math.sin(a)*r} stroke={isNull?"#e5e7eb":"#e5e7eb"} strokeWidth={0.6} strokeDasharray={isNull?"4,3":"none"}/><text x={lx} y={ly-5} textAnchor="middle" dominantBaseline="middle" fontSize={9} fontFamily={T.mono} fill={isNull?"#d1d5db":T.textMuted} fontWeight="600">{FL[k]}</text><text x={lx} y={ly+7} textAnchor="middle" dominantBaseline="middle" fontSize={10} fontFamily={T.mono} fill={c} fontWeight="700">{isNull?"—":((v??0)*100).toFixed(0)}</text></g>;})}
      <polygon points={vals.map((v,i)=>`${cx+Math.cos(ang(i))*Math.max(0.05,v)*r},${cy+Math.sin(ang(i))*Math.max(0.05,v)*r}`).join(" ")} fill={fill} fillOpacity={0.12} stroke={fill} strokeWidth={2} strokeLinejoin="round"/>
      {vals.map((v,i)=><circle key={i} cx={cx+Math.cos(ang(i))*Math.max(0.05,v)*r} cy={cy+Math.sin(ang(i))*Math.max(0.05,v)*r} r={3.5} fill={raw[i]==null?"#d1d5db":fill} stroke="#fff" strokeWidth={1.5}/>)}
      <text x={cx} y={size-4} textAnchor="middle" fontSize={9} fontFamily={T.mono} fill={T.textLight}>{covCount}/10 factors</text>
    </svg>
  );
}

function FactorBar({name,weight,score,detail}:{name:string;weight:number;score:number|null;detail:string}){if(score==null)return<div style={{padding:"8px 0",borderBottom:`1px solid ${T.divider}`,opacity:0.45}}><div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:4}}><div style={{display:"flex",alignItems:"baseline",gap:6}}><span style={{fontSize:12,fontFamily:T.mono,fontWeight:600,color:"#d1d5db"}}>{name}</span><span style={{fontSize:9,fontFamily:T.mono,color:"#d1d5db"}}>({weight}%)</span></div><span style={{fontSize:11,fontFamily:T.mono,color:"#d1d5db",fontStyle:"italic"}}>no data</span></div><div style={{height:5,borderRadius:3,background:T.divider}}><div style={{height:"100%",width:0}}/></div><div style={{fontSize:10,fontFamily:T.mono,color:"#d1d5db",lineHeight:1.5}}>Weight redistributed to evaluated factors</div></div>;const c=score>0.7?"#10b981":score>0.4?T.amber:T.red;return<div style={{padding:"8px 0",borderBottom:`1px solid ${T.divider}`}}><div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:4}}><div style={{display:"flex",alignItems:"baseline",gap:6}}><span style={{fontSize:12,fontFamily:T.mono,fontWeight:600,color:T.text}}>{name}</span><span style={{fontSize:9,fontFamily:T.mono,color:T.textLight}}>({weight}%)</span></div><span style={{fontSize:13,fontFamily:T.mono,fontWeight:700,color:c}}>{(score*100).toFixed(0)}</span></div><div style={{height:5,borderRadius:3,background:T.divider,overflow:"hidden",marginBottom:4}}><div style={{height:"100%",width:`${score*100}%`,borderRadius:3,background:c,transition:"width 0.4s ease"}}/></div><div style={{fontSize:10,fontFamily:T.mono,color:T.textMuted,lineHeight:1.5}}>{detail}</div></div>;}

function factorDetail(k:string,s:StockData):string{const c=s.currency==="EUR"?"€":s.currency==="GBP"?"£":"$";switch(k){case"upside":return`Target ${c}${s.target?.toFixed(0)??"?"} (${s.upside>0?"+":""}${s.upside?.toFixed(1)??"?"}%) · DCF ${c}${s.dcf_value?.toFixed(0)??"?"} · MoS ${fmtPct(s.margin_of_safety)}`;case"technical":return`Bull ${s.bull_score}/10 · RSI ${s.rsi?.toFixed(0)} · MACD ${s.macd_signal} · ADX ${s.adx?.toFixed(0)}`;case"quality":return`Piotroski ${s.piotroski}/9 · Altman Z ${s.altman_z?.toFixed(1)} · ROE ${fmtPct(s.roe_avg)} · GM ${fmtPct(s.gross_margin)}`;case"analyst":return`Grades ${s.grade_buy}/${s.grade_total} buy · Score ${(s.grade_score*100).toFixed(0)}%`;case"transcript":return s.transcript_summary||"No transcript available";case"institutional":return s.inst_holders_change!=null?`Holders QoQ ${(s.inst_holders_change*100).toFixed(1)}% · Shares QoQ ${((s.inst_accumulation??0)*100).toFixed(1)}%`:"No data";case"insider":return s.insider_buy_ratio!=null?`Buy ratio ${s.insider_buy_ratio?.toFixed(1)} · Net buys ${s.insider_net_buys??0}`:"No data";case"earnings":return`EPS beats ${s.eps_beats}/${s.eps_total}${s.earnings_momentum!=null?` · Momentum ${s.earnings_momentum>0?"+":""}${(s.earnings_momentum*100).toFixed(1)}%`:""}`;case"catalyst":return s.catalyst_flags?.length?s.catalyst_flags.join(" · "):"No active catalysts";case"proximity":return`At ${s.proximity_52wk!=null?(s.proximity_52wk*100).toFixed(0):"?"}% of range · High ${c}${s.year_high?.toFixed(0)} Low ${c}${s.year_low?.toFixed(0)}`;default:return"";}}

// ── Probability Card ───────────────────────────────────────────────────────────
function ProbabilityCard({s}:{s:StockData}){
  const isLive=s.hit_prob!=null&&s.hit_prob>0;
  const pFallback=getProb(s.composite);
  const p10=isLive?Math.round(s.hit_prob!*100):pFallback.p10;
  const p5=isLive?Math.min(100,Math.round(p10*1.3)):pFallback.p5;
  const p20=isLive?Math.max(0,Math.round(p10*0.45)):pFallback.p20;
  const bars:[string,number][]=[["P(+5% in 30d)",p5],["P(+10% in 60d)",p10],["P(+20% in 60d)",p20]];
  return(
    <Card>
      <SH title={isLive?"Live ML Probability":"ML Probability"} icon={<BarChart2 size={12}/>} sub={isLive?"Gradient Boosting":`Composite ${s.composite.toFixed(2)}`}/>
      {bars.map(([label,val])=>(
        <div key={label} style={{marginBottom:10}}>
          <div style={{display:"flex",justifyContent:"space-between",marginBottom:3}}>
            <span style={{fontSize:11,fontFamily:T.mono,color:T.textMuted}}>{label}</span>
            <span style={{fontSize:12,fontFamily:T.mono,fontWeight:700,color:val>60?"#10b981":val>40?T.amber:T.red}}>{val}%</span>
          </div>
          <div style={{height:6,borderRadius:3,background:T.divider,overflow:"hidden"}}><div style={{height:"100%",width:`${val}%`,borderRadius:3,background:val>60?"#10b981":val>40?T.amber:T.red,transition:"width 0.4s"}}/></div>
        </div>
      ))}
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:8,marginTop:12,paddingTop:12,borderTop:`1px solid ${T.divider}`}}>
        <div style={{textAlign:"center"}}><div style={{fontSize:16,fontWeight:700,color:"#10b981",fontFamily:T.mono}}>+{pFallback.gain}%</div><div style={{fontSize:9,color:T.textLight,fontFamily:T.mono}}>Exp. max gain</div></div>
        <div style={{textAlign:"center"}}><div style={{fontSize:16,fontWeight:700,color:T.red,fontFamily:T.mono}}>{pFallback.dd}%</div><div style={{fontSize:9,color:T.textLight,fontFamily:T.mono}}>Exp. max DD</div></div>
        <div style={{textAlign:"center"}}><div style={{fontSize:16,fontWeight:700,color:T.text,fontFamily:T.mono}}>{pFallback.speed}d</div><div style={{fontSize:9,color:T.textLight,fontFamily:T.mono}}>Avg to +10%</div></div>
      </div>
    </Card>
  );
}

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
function CompositeChart({symbol}:{symbol:string}){
  const[data,setData]=useState<CompositePoint[]>([]);const[loading,setLoading]=useState(true);const canvasRef=useRef<HTMLCanvasElement>(null);
  useEffect(()=>{fetch(`/api/gcs/portfolio/composite_history.json`).then(r=>r.ok?r.json():null).then(d=>{if(d&&d[symbol])setData(d[symbol]);setLoading(false);}).catch(()=>setLoading(false));},[symbol]);
  useEffect(()=>{const cv=canvasRef.current;if(!cv||data.length<2)return;const ctx=cv.getContext("2d");if(!ctx)return;const dpr=window.devicePixelRatio||1,w=cv.offsetWidth,h=cv.offsetHeight;cv.width=w*dpr;cv.height=h*dpr;ctx.scale(dpr,dpr);ctx.clearRect(0,0,w,h);const vals=data.map(p=>p.composite),mn=Math.min(...vals)*0.95,mx=Math.max(...vals)*1.05,rng=mx-mn||1;const gr=ctx.createLinearGradient(0,0,0,h);gr.addColorStop(0,"rgba(45,122,79,0.15)");gr.addColorStop(1,"rgba(45,122,79,0)");ctx.beginPath();ctx.moveTo(0,h);data.forEach((p,i)=>{ctx.lineTo((i/(data.length-1))*w,h-((p.composite-mn)/rng)*h);});ctx.lineTo(w,h);ctx.closePath();ctx.fillStyle=gr;ctx.fill();ctx.beginPath();data.forEach((p,i)=>{const x=(i/(data.length-1))*w,y=h-((p.composite-mn)/rng)*h;if(i===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);});ctx.strokeStyle=T.green;ctx.lineWidth=2;ctx.lineJoin="round";ctx.stroke();},[data]);
  if(loading)return<Card><SH title="Composite History" icon={<TrendingUp size={12}/>}/><div style={{padding:20,textAlign:"center",color:T.textLight,fontSize:11,fontFamily:T.mono}}>Loading...</div></Card>;
  if(data.length<2)return null;
  const first=data[0],last=data[data.length-1],change=last.composite-first.composite;
  return(
    <Card>
      <SH title="Composite History" icon={<TrendingUp size={12}/>} sub={`${data.length} days · ${change>=0?"+":""}${(change*100).toFixed(1)}pts`}/>
      <div style={{position:"relative",height:80}}><canvas ref={canvasRef} style={{width:"100%",height:"100%",display:"block"}}/></div>
      <div style={{display:"flex",justifyContent:"space-between",fontSize:8,fontFamily:T.mono,color:T.textLight,marginTop:4}}><span>{first.date.slice(5)}</span><span>{last.date.slice(5)}</span></div>
    </Card>
  );
}

// ── MomentumPanel ──────────────────────────────────────────────────────────────
function MomentumPanel({s}:{s:StockData}){const gc=s.sma50>s.sma200,p50=s.price>s.sma50,p200=s.price>s.sma200;const rz=s.rsi>70?"Overbought":s.rsi>60?"Bullish":s.rsi>40?"Neutral":s.rsi>30?"Bearish":"Oversold";const rc=s.rsi>70?T.red:s.rsi<30?"#10b981":s.rsi>60?"#10b981":s.rsi<40?T.amber:T.textMuted;const r52=s.year_high-s.year_low,p52=r52>0?((s.price-s.year_low)/r52)*100:50;const inds=[{l:"MACD",v:s.macd_signal,b:s.macd_signal?.includes("bullish")},{l:"ADX",v:s.adx?.toFixed(1),b:s.adx>25},{l:"BB%B",v:s.bb_pct?.toFixed(2),b:s.bb_pct>0.2&&s.bb_pct<0.8},{l:"StochRSI",v:s.stoch_rsi?.toFixed(0),b:s.stoch_rsi>20&&s.stoch_rsi<80},{l:"OBV",v:s.obv_trend,b:s.obv_trend==="rising"}];return<Card><SH title="Momentum" icon={<Activity size={12}/>}/><div style={{marginBottom:14}}><div style={{display:"flex",alignItems:"center",gap:8,marginBottom:8}}><div style={{width:8,height:8,borderRadius:"50%",background:gc?"#10b981":T.red,boxShadow:`0 0 6px ${gc?"#10b981":T.red}40`}}/><span style={{fontSize:11,fontFamily:T.mono,fontWeight:600,color:gc?"#10b981":T.red}}>{gc?"Golden Cross":"Death Cross"}</span></div><div style={{display:"flex",gap:6}}>{[{l:`Price ${p50?">":"<"} SMA50`,ok:p50,v:fmtPrice(s.sma50)},{l:`Price ${p200?">":"<"} SMA200`,ok:p200,v:fmtPrice(s.sma200)}].map((m,i)=><div key={i} style={{flex:1,padding:"6px 8px",borderRadius:6,fontSize:10,fontFamily:T.mono,background:m.ok?T.greenLight:T.redLight,color:m.ok?"#10b981":T.red,border:`1px solid ${m.ok?T.greenBorder:"#fecaca"}`}}><div style={{fontWeight:600}}>{m.l}</div><div style={{fontSize:9,opacity:0.8,marginTop:1}}>{m.v}</div></div>)}</div></div><div style={{marginBottom:14}}><div style={{display:"flex",justifyContent:"space-between",marginBottom:4}}><span style={{fontSize:10,fontFamily:T.mono,color:T.textMuted}}>RSI</span><span style={{fontSize:11,fontFamily:T.mono,fontWeight:600,color:rc}}>{s.rsi?.toFixed(1)} — {rz}</span></div><div style={{position:"relative",height:8,borderRadius:4,overflow:"hidden",background:`linear-gradient(to right, #10b981 0%, #10b981 30%, ${T.divider} 30%, ${T.divider} 70%, ${T.red} 70%, ${T.red} 100%)`}}><div style={{position:"absolute",left:`${s.rsi}%`,top:-2,width:12,height:12,borderRadius:"50%",background:"#fff",border:`2px solid ${rc}`,transform:"translateX(-6px)",boxShadow:"0 1px 3px rgba(0,0,0,0.15)"}}/></div></div><div style={{marginBottom:14}}><div style={{display:"flex",justifyContent:"space-between",marginBottom:4}}><span style={{fontSize:10,fontFamily:T.mono,color:T.textMuted}}>52-Week Range</span><span style={{fontSize:10,fontFamily:T.mono,color:T.textMuted}}>{p52.toFixed(0)}%</span></div><div style={{position:"relative",height:6,borderRadius:3,background:T.divider}}><div style={{position:"absolute",left:0,top:0,bottom:0,width:`${p52}%`,borderRadius:3,background:`linear-gradient(to right, #10b981, ${p52>80?T.amber:"#10b981"})`}}/><div style={{position:"absolute",left:`${p52}%`,top:-3,width:12,height:12,borderRadius:"50%",background:"#fff",border:"2px solid #10b981",transform:"translateX(-6px)",boxShadow:"0 1px 2px rgba(0,0,0,0.1)"}}/></div><div style={{display:"flex",justifyContent:"space-between",fontSize:9,fontFamily:T.mono,color:T.textLight,marginTop:3}}><span>{fmtPrice(s.year_low,s.currency)}</span><span style={{fontWeight:600,color:T.text}}>{fmtPrice(s.price,s.currency)}</span><span>{fmtPrice(s.year_high,s.currency)}</span></div></div><div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:4}}>{inds.map((d,i)=><div key={i} style={{display:"flex",justifyContent:"space-between",alignItems:"center",padding:"5px 8px",borderRadius:4,fontSize:10,fontFamily:T.mono,background:d.b?T.greenLight:"#fafafa",border:`1px solid ${d.b?T.greenBorder:T.divider}`}}><span style={{color:T.textMuted,fontWeight:500}}>{d.l}</span><span style={{color:d.b?"#10b981":T.textMuted,fontWeight:600}}>{d.v}</span></div>)}</div><div style={{marginTop:12}}><div style={{display:"flex",justifyContent:"space-between",marginBottom:4}}><span style={{fontSize:10,fontFamily:T.mono,color:T.textMuted}}>Bull Score</span><span style={{fontSize:11,fontFamily:T.mono,fontWeight:700,color:s.bull_score>=7?"#10b981":s.bull_score>=4?T.amber:T.red}}>{s.bull_score}/10</span></div><div style={{display:"flex",gap:3}}>{Array.from({length:10},(_,i)=>{const a=i<s.bull_score,c=s.bull_score>=7?"#10b981":s.bull_score>=4?T.amber:T.red;return<div key={i} style={{flex:1,height:6,borderRadius:3,background:a?c:T.divider}}/>;})}</div></div></Card>;}

// ── TranscriptInsights ─────────────────────────────────────────────────────────
function TranscriptInsights({symbol}:{symbol:string}){const[analysis,setAnalysis]=useState<string|null>(null);const[loading,setLoading]=useState(false);const[error,setError]=useState<string|null>(null);const[qFound,setQFound]=useState(0);const f=useCallback(async()=>{setLoading(true);setError(null);try{const r=await fetch(`/api/transcript?symbol=${symbol}&quarters=8`);const d=await r.json();if(d.error)setError(d.error);else{setAnalysis(d.analysis||"No analysis.");setQFound(d.quarters_found||0);}}catch(e:any){setError(e.message);}finally{setLoading(false);}},[symbol]);return<Card><SH title="Transcript Insights" icon={<Brain size={12}/>} sub={qFound>0?`${qFound} quarters analyzed`:""}/>{analysis?<div><div style={{fontSize:11,lineHeight:1.7,color:T.text,fontFamily:T.sans,whiteSpace:"pre-wrap"}}>{analysis}</div><button onClick={f} style={{marginTop:12,background:"none",border:`1px solid ${T.cardBorder}`,borderRadius:6,padding:"6px 12px",cursor:"pointer",fontSize:10,fontFamily:T.mono,color:T.textMuted,display:"flex",alignItems:"center",gap:4}}><RefreshCw size={10}/> Refresh</button></div>:<div style={{textAlign:"center",padding:"20px 0"}}><button onClick={f} disabled={loading} style={{background:loading?T.divider:T.green,border:"none",borderRadius:6,padding:"10px 20px",color:loading?T.textMuted:"#fff",fontFamily:T.mono,fontSize:11,fontWeight:600,cursor:loading?"not-allowed":"pointer",display:"inline-flex",alignItems:"center",gap:6}}>{loading?<><RefreshCw size={12} style={{animation:"spin 1s linear infinite"}}/> Analyzing 8 quarters...</>:<><Brain size={12}/> Analyze 2 Years of Earnings</>}</button>{error&&<div style={{marginTop:8,fontSize:10,color:T.red,fontFamily:T.mono,maxWidth:400,margin:"8px auto 0",lineHeight:1.5}}>{error}</div>}<div style={{fontSize:9,color:T.textLight,fontFamily:T.mono,marginTop:8}}>Claude analyzes narrative arc, tone shifts, guidance credibility across 8 quarters</div></div>}</Card>;}

// ── TargetBar ──────────────────────────────────────────────────────────────────
function TargetBar({price,target,dcf,buffett,currency}:{price:number;target:number;dcf:number;buffett:number;currency?:string}){const vs=[price,target,dcf,buffett].filter(v=>v>0);if(vs.length<2)return null;const mn=Math.min(...vs)*0.8,mx=Math.max(...vs)*1.1,rng=mx-mn,pos=(v:number)=>((v-mn)/rng*100);const c$=(v:number)=>{const s=currency==="EUR"?"€":currency==="GBP"?"£":"$";return`${s}${v.toFixed(0)}`;};return<div style={{marginTop:12,padding:"12px 0"}}><div style={{fontSize:10,color:T.textMuted,fontFamily:T.mono,marginBottom:8,fontWeight:600}}>PRICE vs INTRINSIC VALUE</div><div style={{position:"relative",height:50,background:T.divider,borderRadius:6}}>{dcf>price&&<div style={{position:"absolute",left:`${pos(price)}%`,top:0,bottom:0,width:`${pos(dcf)-pos(price)}%`,background:`#10b98112`,borderRadius:4}}/>}<div style={{position:"absolute",left:`${pos(price)}%`,top:0,bottom:0,width:2,background:T.text,zIndex:2}}><div style={{position:"absolute",top:-16,left:-14,fontSize:10,color:T.text,fontFamily:T.mono,fontWeight:700,whiteSpace:"nowrap"}}>{c$(price)}</div></div>{target>0&&<div style={{position:"absolute",left:`${pos(target)}%`,top:10,width:8,height:8,borderRadius:"50%",background:T.amber,transform:"translateX(-4px)"}}><div style={{position:"absolute",top:-18,left:"50%",transform:"translateX(-50%)",fontSize:8,color:T.amber,fontFamily:T.mono,fontWeight:600,whiteSpace:"nowrap"}}>{c$(target)}</div><div style={{position:"absolute",bottom:-13,left:"50%",transform:"translateX(-50%)",fontSize:8,color:T.amber,fontFamily:T.mono,whiteSpace:"nowrap"}}>Target</div></div>}{dcf>0&&<div style={{position:"absolute",left:`${pos(dcf)}%`,top:25,width:8,height:8,borderRadius:"50%",background:T.blue,transform:"translateX(-4px)"}}><div style={{position:"absolute",top:-18,left:"50%",transform:"translateX(-50%)",fontSize:8,color:T.blue,fontFamily:T.mono,fontWeight:600,whiteSpace:"nowrap"}}>{c$(dcf)}</div><div style={{position:"absolute",bottom:-13,left:"50%",transform:"translateX(-50%)",fontSize:8,color:T.blue,fontFamily:T.mono,whiteSpace:"nowrap"}}>DCF</div></div>}{buffett>0&&buffett<mx&&<div style={{position:"absolute",left:`${pos(buffett)}%`,top:17,width:8,height:8,borderRadius:2,background:T.purple,transform:"translateX(-4px)"}}><div style={{position:"absolute",top:-18,left:"50%",transform:"translateX(-50%)",fontSize:8,color:T.purple,fontFamily:T.mono,fontWeight:600,whiteSpace:"nowrap"}}>{c$(buffett)}</div><div style={{position:"absolute",bottom:-13,left:"50%",transform:"translateX(-50%)",fontSize:8,color:T.purple,fontFamily:T.mono,whiteSpace:"nowrap"}}>Buffett</div></div>}</div></div>;}

// ── News Feed ──────────────────────────────────────────────────────────────────
function NewsFeed({symbol}:{symbol:string}){const[news,setNews]=useState<NewsItem[]>([]);const[loading,setLoading]=useState(true);useEffect(()=>{fmpFetch("news/stock",{symbols:symbol,limit:15}).then(d=>{if(d)setNews(d as NewsItem[]);setLoading(false);}).catch(()=>setLoading(false));},[symbol]);return<Card><SH title="Recent News" icon={<Newspaper size={12}/>}/>{loading?<div style={{padding:20,textAlign:"center",color:T.textLight,fontSize:11,fontFamily:T.mono}}><Loader2 size={14} style={{animation:"spin 1s linear infinite"}}/></div>:news.length===0?<div style={{padding:16,textAlign:"center",color:T.textLight,fontSize:11,fontFamily:T.mono}}>No recent news</div>:<div style={{display:"flex",flexDirection:"column",gap:8}}>{news.slice(0,8).map((n,i)=><a key={i} href={n.url} target="_blank" rel="noopener noreferrer" style={{display:"block",padding:"10px 12px",borderRadius:6,border:`1px solid ${T.divider}`,background:"#f8faf9",textDecoration:"none"}}><div style={{fontSize:12,fontWeight:600,color:T.text,lineHeight:1.4,marginBottom:4}}>{n.title}</div><div style={{display:"flex",gap:8,fontSize:9,fontFamily:T.mono,color:T.textLight}}><span>{n.site}</span><span>·</span><span>{new Date(n.publishedDate).toLocaleDateString()}</span></div></a>)}</div>}</Card>;}

// ── FMP Growth/Profitability/Valuation ──────────────────────────────────────────
const cs_:React.CSSProperties={padding:"6px 10px",textAlign:"right",fontSize:11,fontFamily:T.mono,borderBottom:`1px solid ${T.divider}`,whiteSpace:"nowrap"};
const hs_:React.CSSProperties={...cs_,color:T.textMuted,fontWeight:500,fontSize:10};
const ls_:React.CSSProperties={...cs_,textAlign:"left",color:T.textMuted,fontWeight:500};
function GC({v}:{v:number|null}){if(v==null)return<td style={cs_}>—</td>;return<td style={{...cs_,color:gClr(v),fontWeight:600}}>{(v*100).toFixed(1)}%</td>;}

function GrowthPanel({incomes,loading}:{incomes:IncomeRow[];loading:boolean}){if(loading)return<Card><SH title="Growth Rates" icon={<BarChart2 size={12}/>}/><div style={{padding:24,textAlign:"center",color:T.textLight,fontSize:11,fontFamily:T.mono}}><Loader2 size={14} style={{animation:"spin 1s linear infinite"}}/></div></Card>;if(!incomes.length)return null;const sorted=[...incomes].sort((a,b)=>a.date.localeCompare(b.date));const latest=sorted[sorted.length-1];const n=sorted.length;function cagr(f:keyof IncomeRow,y:number):number|null{if(n<y+1)return null;return safeCagr(sorted[n-1-y][f]as number,latest[f]as number,y);}function yoy(f:keyof IncomeRow):number|null{if(n<2)return null;const prev=sorted[n-2][f]as number,cur=latest[f]as number;if(!prev||prev<=0)return null;return(cur-prev)/prev;}const ms:[string,keyof IncomeRow][]=[["Revenue","revenue"],["Gross Profit","grossProfit"],["Operating Income","operatingIncome"],["Net Income","netIncome"],["EPS","epsdiluted"],["EBITDA","ebitda"]];return<Card><SH title="Growth Rates" icon={<BarChart2 size={12}/>} sub={`FY ${latest.calendarYear}`}/><div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse"}}><thead><tr><th style={{...hs_,textAlign:"left"}}>Metric</th><th style={hs_}>1Y</th><th style={hs_}>3Y</th><th style={hs_}>5Y</th><th style={hs_}>10Y</th></tr></thead><tbody>{ms.map(([l,f])=><tr key={l}><td style={ls_}>{l}</td><GC v={yoy(f)}/><GC v={cagr(f,3)}/><GC v={cagr(f,5)}/><GC v={cagr(f,10)}/></tr>)}</tbody></table></div></Card>;}

function ProfitPanel({ratios,loading}:{ratios:RatioYear[];loading:boolean}){if(loading||!ratios.length)return null;const c=ratios[0];const avgN=(f:keyof RatioYear,n:number)=>{const vs=ratios.slice(0,n).map(r=>r[f]as number).filter(v=>v!=null&&isFinite(v));return vs.length>=Math.min(n,2)?vs.reduce((a,b)=>a+b,0)/vs.length:null;};const ms:[string,keyof RatioYear,number?,boolean?][]=[["ROE","returnOnEquity",0.15],["ROA","returnOnAssets",0.08],["Gross Margin","grossProfitMargin",0.40],["Op Margin","operatingProfitMargin",0.15],["Net Margin","netProfitMargin",0.10],["Current Ratio","currentRatio",undefined,true],["D/E","debtToEquityRatio",undefined,true]];const fmt=(v:number|null,isR?:boolean)=>{if(v==null||!isFinite(v))return"—";return isR?v.toFixed(2):(v*100).toFixed(1)+"%";};return<Card><SH title="Profitability" sub={`FY ${c.fiscalYear}`}/><div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse"}}><thead><tr><th style={{...hs_,textAlign:"left"}}>Metric</th><th style={hs_}>Current</th><th style={hs_}>3Y</th><th style={hs_}>5Y</th><th style={hs_}>10Y</th></tr></thead><tbody>{ms.map(([l,f,th,isR])=>{const cv=c[f]as number;const cl=(v:number|null)=>v!=null&&th!=null&&v>=th?"#10b981":T.text;return<tr key={l}><td style={ls_}>{l}</td><td style={{...cs_,color:cl(cv),fontWeight:600}}>{fmt(cv,isR)}</td><td style={{...cs_,color:T.textMuted}}>{fmt(avgN(f,3),isR)}</td><td style={{...cs_,color:T.textMuted}}>{fmt(avgN(f,5),isR)}</td><td style={{...cs_,color:T.textMuted}}>{fmt(avgN(f,10),isR)}</td></tr>;})}</tbody></table></div></Card>;}

function ValPanel({ratios,loading}:{ratios:RatioYear[];loading:boolean}){if(loading||!ratios.length)return null;const yrs=[...ratios].reverse();const ttm=ratios[0];const ms:[string,keyof RatioYear,number?][]=[["P/E","priceToEarningsRatio"],["P/S","priceToSalesRatio"],["P/B","priceToBookRatio"],["P/FCF","priceToFreeCashFlowRatio"],["Div%","dividendYieldPercentage",2]];return<Card><SH title="Valuation History" sub="Annual"/><div style={{overflowX:"auto"}}><table style={{width:"100%",borderCollapse:"collapse"}}><thead><tr><th style={{...hs_,textAlign:"left",position:"sticky",left:0,background:T.card,zIndex:1}}>Metric</th>{yrs.map(y=><th key={y.fiscalYear} style={hs_}>{y.fiscalYear}</th>)}<th style={{...hs_,color:T.green,fontWeight:700}}>TTM</th></tr></thead><tbody>{ms.map(([l,f,d])=><tr key={l}><td style={{...ls_,position:"sticky",left:0,background:T.card,zIndex:1}}>{l}</td>{yrs.map(y=>{const v=y[f]as number;return<td key={y.fiscalYear} style={cs_}>{v!=null&&isFinite(v)&&v>0?v.toFixed(d??1):"—"}</td>;})}<td style={{...cs_,color:T.green,fontWeight:600}}>{(()=>{const v=ttm[f]as number;return v!=null&&isFinite(v)&&v>0?v.toFixed(d??1):"—";})()}</td></tr>)}</tbody></table></div></Card>;}

// ── Main Page ──────────────────────────────────────────────────────────────────
export default function StockDetail(){
  const params=useParams();const router=useRouter();const symbol=typeof params?.symbol==="string"?params.symbol:"";
  const[stock,setStock]=useState<StockData|null>(null);const[loading,setLoading]=useState(true);
  const[incomes,setIncomes]=useState<IncomeRow[]>([]);const[ratios,setRatios]=useState<RatioYear[]>([]);const[fmpLoading,setFmpLoading]=useState(true);

  useEffect(()=>{if(!symbol)return;fetch(`${GCS_SCANS}/latest.json`).then(r=>r.json()).then(d=>{const f=d.stocks?.find((s:StockData)=>s.symbol===symbol.toUpperCase());setStock(f||null);setLoading(false);}).catch(()=>{setStock(null);setLoading(false);});},[symbol]);
  useEffect(()=>{if(!symbol)return;setFmpLoading(true);const sym=symbol.toUpperCase();Promise.all([fmpFetch("income-statement",{symbol:sym,period:"annual",limit:11}),fmpFetch("ratios",{symbol:sym,period:"annual",limit:10})]).then(([inc,rat])=>{if(inc?.length)setIncomes(inc.map((r:any)=>({date:r.date,calendarYear:r.calendarYear||r.date?.slice(0,4),revenue:r.revenue,grossProfit:r.grossProfit,operatingIncome:r.operatingIncome,netIncome:r.netIncome,epsdiluted:r.epsdiluted||r.epsDiluted,ebitda:r.ebitda})));if(rat?.length)setRatios(rat as RatioYear[]);setFmpLoading(false);}).catch(()=>setFmpLoading(false));},[symbol]);

  if(loading)return<div style={{minHeight:"100vh",display:"flex",alignItems:"center",justifyContent:"center"}}><span style={{color:T.textMuted,fontFamily:T.mono,fontSize:12}}>Loading {symbol}...</span></div>;
  if(!stock)return<div style={{minHeight:"100vh",padding:40}}><button onClick={()=>router.push("/")} style={{background:"none",border:"none",color:T.green,cursor:"pointer",display:"flex",alignItems:"center",gap:6,fontFamily:T.mono,fontSize:12,marginBottom:24,padding:0}}><ArrowLeft size={14}/> Back</button><div style={{textAlign:"center",padding:60,color:T.textMuted,fontFamily:T.mono}}>No data for {symbol}.</div></div>;

  const s=stock,sigStyle=SIG_C[s.signal]||SIG_C.HOLD,clsColor=CLS_C[s.classification]||T.textMuted,scores=inferFactors(s);

  return(
    <div style={{minHeight:"100vh",padding:"16px 24px",maxWidth:1320,margin:"0 auto"}}>
      <button onClick={()=>router.push("/")} style={{background:"none",border:"none",color:T.green,cursor:"pointer",display:"flex",alignItems:"center",gap:5,fontFamily:T.mono,fontSize:11,marginBottom:16,padding:0}}><ArrowLeft size={13}/> SCREENER</button>

      {/* Header */}
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"flex-start",marginBottom:20,paddingBottom:16,borderBottom:`1px solid ${T.divider}`}}>
        <div>
          <div style={{display:"flex",alignItems:"center",gap:10,marginBottom:6}}>
            <h1 style={{fontSize:26,fontWeight:700,color:T.text,fontFamily:T.mono,margin:0}}>{s.symbol}</h1>
            <span style={{fontSize:10,padding:"3px 8px",borderRadius:4,border:`1px solid ${clsColor}30`,color:clsColor,fontFamily:T.mono,fontWeight:600,background:`${clsColor}08`}}>{s.classification?.replace("_"," ")}</span>
            <span style={{fontSize:11,padding:"4px 12px",borderRadius:4,fontWeight:700,fontFamily:T.mono,letterSpacing:"0.07em",color:sigStyle.fg,background:sigStyle.bg,border:`1px solid ${sigStyle.border}`}}>{s.signal}</span>
            {s.has_catalyst&&<Zap size={14} color={T.purple} fill={T.purple}/>}
          </div>
          <div style={{display:"flex",alignItems:"baseline",gap:12}}><span style={{fontSize:30,fontWeight:600,color:T.text,fontFamily:T.mono}}>{fmtPrice(s.price,s.currency)}</span><span style={{fontSize:13,color:T.textMuted,fontFamily:T.mono}}>{s.currency}</span></div>
        </div>
        <div style={{textAlign:"right"}}><div style={{fontSize:11,color:T.textMuted,fontFamily:T.mono,marginBottom:4}}>Composite</div><div style={{fontSize:34,fontWeight:700,fontFamily:T.mono,color:s.composite>0.6?T.green:s.composite>0.4?T.text:T.red}}>{s.composite.toFixed(2)}</div></div>
      </div>

      {/* TradingView */}
      <Card style={{marginBottom:16,padding:0,overflow:"hidden"}}><div style={{height:300}}><iframe src={`https://s.tradingview.com/widgetembed/?frameElementId=tv&symbol=${s.symbol}&interval=D&hidesidetoolbar=1&symboledit=0&saveimage=0&toolbarbg=f1f3f6&studies=MASimple%409na%40na%40na~50~0~~&studies=MASimple%409na%40na%40na~200~0~~&theme=light&style=1&timezone=exchange&withdateranges=1&width=100%25&height=100%25`} style={{width:"100%",height:"100%",border:"none"}} allowFullScreen/></div></Card>

      {/* ═══ v7 FACTOR BREAKDOWN ═══ */}
      <Card style={{marginBottom:16}}>
        <SH title="10-Factor Analysis" icon={<BarChart2 size={12}/>} sub={`Composite ${s.composite.toFixed(2)} · ${s.factor_coverage??FACTOR_ORDER.filter(k=>(scores as any)[k]!=null).length}/10 factors`}/>
        <div style={{display:"grid",gridTemplateColumns:"260px 1fr",gap:24}}>
          <div style={{display:"flex",flexDirection:"column",alignItems:"center"}}><FactorRadar scores={scores}/></div>
          <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:"0 20px"}}>{FACTOR_ORDER.map(k=><FactorBar key={k} name={FL[k]} weight={FW[k]} score={(scores as any)[k]} detail={factorDetail(k,s)}/>)}</div>
        </div>
      </Card>

      {/* Probability + Catalyst + Composite History */}
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:14,marginBottom:16}}>
        <ProbabilityCard s={s}/>
        <CatalystTimeline s={s}/>
        <CompositeChart symbol={s.symbol}/>
      </div>

      {/* 3-column: Momentum / Quality+Value / Transcript */}
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr 1fr",gap:14,marginBottom:16}}>
        <MomentumPanel s={s}/>
        <Card>
          <SH title="Quality & Value" icon={<Shield size={12}/>}/>
          <div style={{display:"flex",justifyContent:"center",gap:12,margin:"8px 0 12px"}}><ScoreRing value={s.piotroski} label="Piotroski" max={9} color={s.piotroski>=7?"#10b981":s.piotroski>=5?T.amber:T.red}/><ScoreRing value={Math.round(s.altman_z>20?20:s.altman_z)} label="Altman Z" max={20} color={s.altman_z>3?"#10b981":s.altman_z>1.8?T.amber:T.red}/></div>
          <Metric label="ROE (avg)" value={fmtPct(s.roe_avg)} color={s.roe_avg>0.15?"#10b981":T.textMuted} sub={s.roe_consistent?"✓ Consistent >15%":""}/>
          <Metric label="ROIC (avg)" value={fmtPct(s.roic_avg)} color={s.roic_avg>0.12?"#10b981":T.textMuted}/>
          <Metric label="Gross Margin" value={fmtPct(s.gross_margin)} color={s.gross_margin>0.5?"#10b981":T.textMuted} sub={s.gross_margin_trend==="expanding"?"↑ Expanding":s.gross_margin_trend==="contracting"?"↓ Contracting":"→ Stable"}/>
          <Metric label="Rev CAGR 3Y" value={fmtPct(s.revenue_cagr_3y)} color={s.revenue_cagr_3y>0.1?"#10b981":T.textMuted}/>
          <Metric label="EPS CAGR 3Y" value={fmtPct(s.eps_cagr_3y)} color={s.eps_cagr_3y>0.1?"#10b981":T.textMuted}/>
          <Metric label="OE Yield" value={fmtPct(s.owner_earnings_yield)} color={s.owner_earnings_yield>0.045?"#10b981":T.textMuted} sub="vs 4.5% risk-free"/>
          <TargetBar price={s.price} target={s.target} dcf={s.dcf_value} buffett={s.intrinsic_buffett} currency={s.currency}/>
        </Card>
        <TranscriptInsights symbol={s.symbol}/>
      </div>

      {/* FMP Panels */}
      <GrowthPanel incomes={incomes} loading={fmpLoading}/>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:14,margin:"16px 0"}}><ProfitPanel ratios={ratios} loading={fmpLoading}/><ValPanel ratios={ratios} loading={fmpLoading}/></div>

      {/* News */}
      <div style={{marginBottom:16}}><NewsFeed symbol={s.symbol}/></div>

      {/* Signals */}
      {s.reasons?.length>0&&<Card style={{marginBottom:16}}><SH title="Active Signals"/><div style={{display:"flex",flexWrap:"wrap",gap:6,marginTop:4}}>{s.reasons.map((r,i)=><span key={i} style={{fontSize:10,padding:"4px 10px",borderRadius:4,fontFamily:T.mono,background:r.includes("⚠")?T.redLight:T.greenLight,border:`1px solid ${r.includes("⚠")?"#fecaca":T.greenBorder}`,color:r.includes("⚠")?T.red:T.textMuted}}>{r}</span>)}</div></Card>}
    </div>
  );
}
