import { useState, useEffect, useMemo } from "react";
import { TrendingUp, TrendingDown, AlertTriangle, ChevronDown, ChevronRight, BarChart3, Shield, Target, Activity, RefreshCw } from "lucide-react";

const GCS_URL = "https://storage.googleapis.com/screener-signals-carbonbridge/scans/latest.json";

// Embedded fallback data from first Nasdaq scan 2026-04-11
const FALLBACK = {"scan_date":"2026-04-11T17:24:00","region":"nasdaq100","version":"v5","summary":{"total":100,"buy":0,"watch":22,"hold":62,"sell":16},"stocks":[
{"symbol":"NVDA","price":188.63,"currency":"USD","sma50":145.2,"sma200":132.1,"year_high":195.95,"year_low":86.62,"market_cap":4584652476141,"volume":159395820,"rsi":61,"macd_signal":"bullish","adx":23,"bb_pct":0.72,"stoch_rsi":68,"obv_trend":"rising","bull_score":8,"target":278,"upside":47.3,"grade_buy":37,"grade_total":37,"grade_score":1.0,"eps_beats":7,"eps_total":7,"revenue_cagr_3y":1.0,"eps_cagr_3y":2.07,"roe_avg":0.59,"roe_consistent":false,"roic_avg":0.47,"gross_margin":0.71,"gross_margin_trend":"stable","piotroski":6,"altman_z":60.5,"dcf_value":238,"owner_earnings_yield":0.022,"intrinsic_buffett":168,"intrinsic_avg":203,"margin_of_safety":0.08,"value_score":0.55,"composite":0.66,"signal":"WATCH","classification":"QUALITY_GROWTH","reasons":[]},
{"symbol":"NTES","price":112.72,"currency":"USD","sma50":108,"sma200":99,"year_high":119,"year_low":82,"market_cap":72000000000,"volume":3200000,"rsi":43,"macd_signal":"bullish","adx":34,"bb_pct":0.41,"stoch_rsi":77,"obv_trend":"flat","bull_score":5,"target":150,"upside":32.9,"grade_buy":0,"grade_total":1,"grade_score":0,"eps_beats":2,"eps_total":7,"revenue_cagr_3y":0.05,"eps_cagr_3y":0.2,"roe_avg":0.21,"roe_consistent":true,"roic_avg":0.18,"gross_margin":0.64,"gross_margin_trend":"expanding","piotroski":8,"altman_z":7.0,"dcf_value":220,"owner_earnings_yield":0.135,"intrinsic_buffett":868,"intrinsic_avg":544,"margin_of_safety":3.82,"value_score":0.75,"composite":0.65,"signal":"WATCH","classification":"DEEP_VALUE","reasons":[]},
{"symbol":"PDD","price":100.17,"currency":"USD","sma50":112,"sma200":105,"year_high":164,"year_low":86,"market_cap":140000000000,"volume":12000000,"rsi":47,"macd_signal":"bullish","adx":12,"bb_pct":0.46,"stoch_rsi":63,"obv_trend":"flat","bull_score":4,"target":144,"upside":43.6,"grade_buy":0,"grade_total":0,"grade_score":0,"eps_beats":4,"eps_total":7,"revenue_cagr_3y":0.48,"eps_cagr_3y":0.44,"roe_avg":0.26,"roe_consistent":false,"roic_avg":0.22,"gross_margin":0.56,"gross_margin_trend":"contracting","piotroski":5,"altman_z":5.1,"dcf_value":279,"owner_earnings_yield":0.189,"intrinsic_buffett":2241,"intrinsic_avg":1260,"margin_of_safety":11.57,"value_score":0.8,"composite":0.62,"signal":"WATCH","classification":"DEEP_VALUE","reasons":[]},
{"symbol":"GOOGL","price":317.24,"currency":"USD","sma50":282,"sma200":275,"year_high":335,"year_low":197,"market_cap":3837000000000,"volume":18914000,"rsi":61,"macd_signal":"bullish","adx":28,"bb_pct":0.65,"stoch_rsi":55,"obv_trend":"flat","bull_score":7,"target":376,"upside":18.5,"grade_buy":32,"grade_total":38,"grade_score":0.84,"eps_beats":7,"eps_total":7,"revenue_cagr_3y":0.13,"eps_cagr_3y":0.33,"roe_avg":0.28,"roe_consistent":true,"roic_avg":0.24,"gross_margin":0.6,"gross_margin_trend":"expanding","piotroski":7,"altman_z":15.4,"dcf_value":152,"owner_earnings_yield":0.026,"intrinsic_buffett":223,"intrinsic_avg":187.5,"margin_of_safety":-0.41,"value_score":0.3,"composite":0.60,"signal":"WATCH","classification":"SPECULATIVE","reasons":[]},
{"symbol":"AMGN","price":351.02,"currency":"USD","sma50":340,"sma200":310,"year_high":365,"year_low":252,"market_cap":186000000000,"volume":2500000,"rsi":46,"macd_signal":"bullish","adx":18,"bb_pct":0.47,"stoch_rsi":77,"obv_trend":"flat","bull_score":6,"target":349,"upside":-0.5,"grade_buy":4,"grade_total":13,"grade_score":0.31,"eps_beats":6,"eps_total":7,"revenue_cagr_3y":0.12,"eps_cagr_3y":0.06,"roe_avg":1.07,"roe_consistent":true,"roic_avg":0.15,"gross_margin":0.71,"gross_margin_trend":"stable","piotroski":8,"altman_z":2.3,"dcf_value":1057,"owner_earnings_yield":0.046,"intrinsic_buffett":287,"intrinsic_avg":672,"margin_of_safety":0.91,"value_score":0.65,"composite":0.60,"signal":"WATCH","classification":"DEEP_VALUE","reasons":[]},
{"symbol":"BKNG","price":173.46,"currency":"USD","sma50":165,"sma200":155,"year_high":182,"year_low":122,"market_cap":141000000000,"volume":1800000,"rsi":50,"macd_signal":"bullish","adx":15,"bb_pct":0.59,"stoch_rsi":60,"obv_trend":"flat","bull_score":6,"target":238,"upside":37.3,"grade_buy":20,"grade_total":25,"grade_score":0.8,"eps_beats":7,"eps_total":7,"revenue_cagr_3y":0.16,"eps_cagr_3y":0.29,"roe_avg":-0.54,"roe_consistent":false,"roic_avg":0.1,"gross_margin":1.0,"gross_margin_trend":"stable","piotroski":7,"altman_z":6.4,"dcf_value":252,"owner_earnings_yield":0.066,"intrinsic_buffett":153,"intrinsic_avg":202.5,"margin_of_safety":0.17,"value_score":0.5,"composite":0.59,"signal":"WATCH","classification":"VALUE","reasons":[]},
{"symbol":"PYPL","price":45.24,"currency":"USD","sma50":44,"sma200":42,"year_high":55,"year_low":32,"market_cap":48000000000,"volume":8500000,"rsi":49,"macd_signal":"bullish","adx":4,"bb_pct":0.59,"stoch_rsi":66,"obv_trend":"rising","bull_score":7,"target":53,"upside":17.3,"grade_buy":2,"grade_total":18,"grade_score":0.11,"eps_beats":6,"eps_total":7,"revenue_cagr_3y":0.06,"eps_cagr_3y":0.37,"roe_avg":0.19,"roe_consistent":true,"roic_avg":0.15,"gross_margin":0.47,"gross_margin_trend":"stable","piotroski":7,"altman_z":1.9,"dcf_value":107,"owner_earnings_yield":0.129,"intrinsic_buffett":93,"intrinsic_avg":100,"margin_of_safety":1.21,"value_score":0.7,"composite":0.59,"signal":"WATCH","classification":"DEEP_VALUE","reasons":[]},
{"symbol":"META","price":629.86,"currency":"USD","sma50":580,"sma200":560,"year_high":740,"year_low":468,"market_cap":1580000000000,"volume":10200000,"rsi":57,"macd_signal":"bullish","adx":30,"bb_pct":0.45,"stoch_rsi":48,"obv_trend":"rising","bull_score":5,"target":848,"upside":34.6,"grade_buy":17,"grade_total":19,"grade_score":0.89,"eps_beats":7,"eps_total":7,"revenue_cagr_3y":0.2,"eps_cagr_3y":0.4,"roe_avg":0.27,"roe_consistent":true,"roic_avg":0.22,"gross_margin":0.82,"gross_margin_trend":"stable","piotroski":6,"altman_z":8.4,"dcf_value":276,"owner_earnings_yield":0.046,"intrinsic_buffett":605,"intrinsic_avg":440.5,"margin_of_safety":-0.3,"value_score":0.35,"composite":0.58,"signal":"WATCH","classification":"GROWTH","reasons":[]},
{"symbol":"ADBE","price":225.35,"currency":"USD","sma50":280,"sma200":310,"year_high":410,"year_low":210,"market_cap":98000000000,"volume":4200000,"rsi":29,"macd_signal":"bearish_cross","adx":42,"bb_pct":0.12,"stoch_rsi":15,"obv_trend":"falling","bull_score":1,"target":350,"upside":55.2,"grade_buy":8,"grade_total":25,"grade_score":0.32,"eps_beats":6,"eps_total":7,"revenue_cagr_3y":0.11,"eps_cagr_3y":0.18,"roe_avg":0.4,"roe_consistent":true,"roic_avg":0.3,"gross_margin":0.89,"gross_margin_trend":"stable","piotroski":7,"altman_z":7.0,"dcf_value":344,"owner_earnings_yield":0.112,"intrinsic_buffett":324,"intrinsic_avg":334,"margin_of_safety":0.48,"value_score":0.65,"composite":0.57,"signal":"WATCH","classification":"DEEP_VALUE","reasons":[]},
{"symbol":"MSFT","price":370.87,"currency":"USD","sma50":395,"sma200":410,"year_high":468,"year_low":338,"market_cap":2750000000000,"volume":22000000,"rsi":38,"macd_signal":"bullish","adx":36,"bb_pct":0.37,"stoch_rsi":40,"obv_trend":"falling","bull_score":3,"target":583,"upside":57.1,"grade_buy":20,"grade_total":22,"grade_score":0.91,"eps_beats":7,"eps_total":7,"revenue_cagr_3y":0.12,"eps_cagr_3y":0.12,"roe_avg":0.37,"roe_consistent":true,"roic_avg":0.28,"gross_margin":0.69,"gross_margin_trend":"stable","piotroski":7,"altman_z":7.9,"dcf_value":323,"owner_earnings_yield":0.037,"intrinsic_buffett":281,"intrinsic_avg":302,"margin_of_safety":-0.19,"value_score":0.35,"composite":0.47,"signal":"HOLD","classification":"NEUTRAL","reasons":[]},
{"symbol":"AAPL","price":260.48,"currency":"USD","sma50":248,"sma200":240,"year_high":275,"year_low":185,"market_cap":3828000000000,"volume":23400000,"rsi":56,"macd_signal":"bullish","adx":15,"bb_pct":0.62,"stoch_rsi":55,"obv_trend":"rising","bull_score":6,"target":317,"upside":21.6,"grade_buy":15,"grade_total":23,"grade_score":0.65,"eps_beats":7,"eps_total":7,"revenue_cagr_3y":0.02,"eps_cagr_3y":0.07,"roe_avg":1.64,"roe_consistent":true,"roic_avg":0.55,"gross_margin":0.47,"gross_margin_trend":"expanding","piotroski":9,"altman_z":10.2,"dcf_value":160,"owner_earnings_yield":0.033,"intrinsic_buffett":119,"intrinsic_avg":139.5,"margin_of_safety":-0.46,"value_score":0.25,"composite":0.49,"signal":"HOLD","classification":"SPECULATIVE","reasons":[]},
{"symbol":"PLTR","price":128.06,"currency":"USD","sma50":145,"sma200":78,"year_high":178,"year_low":38,"market_cap":310000000000,"volume":45000000,"rsi":34,"macd_signal":"bearish","adx":21,"bb_pct":0.22,"stoch_rsi":18,"obv_trend":"falling","bull_score":1,"target":199,"upside":55.2,"grade_buy":10,"grade_total":12,"grade_score":0.83,"eps_beats":7,"eps_total":7,"revenue_cagr_3y":0.33,"eps_cagr_3y":0,"roe_avg":0,"roe_consistent":false,"roic_avg":0,"gross_margin":0.82,"gross_margin_trend":"stable","piotroski":7,"altman_z":128.5,"dcf_value":10,"owner_earnings_yield":0.007,"intrinsic_buffett":22,"intrinsic_avg":16,"margin_of_safety":-0.88,"value_score":0.1,"composite":0.29,"signal":"SELL","classification":"QUALITY_GROWTH","reasons":[]},
{"symbol":"INTC","price":62.38,"currency":"USD","sma50":52,"sma200":30,"year_high":65,"year_low":18,"market_cap":271000000000,"volume":52000000,"rsi":75,"macd_signal":"bullish","adx":25,"bb_pct":0.85,"stoch_rsi":92,"obv_trend":"rising","bull_score":7,"target":50,"upside":-20.5,"grade_buy":5,"grade_total":23,"grade_score":0.22,"eps_beats":4,"eps_total":7,"revenue_cagr_3y":-0.06,"eps_cagr_3y":0,"roe_avg":0.02,"roe_consistent":false,"roic_avg":0.01,"gross_margin":0.35,"gross_margin_trend":"contracting","piotroski":4,"altman_z":3.0,"dcf_value":8,"owner_earnings_yield":-0.019,"intrinsic_buffett":0,"intrinsic_avg":8,"margin_of_safety":-0.87,"value_score":0.05,"composite":0.24,"signal":"SELL","classification":"SPECULATIVE","reasons":[]},
{"symbol":"SHOP","price":110.79,"currency":"USD","sma50":125,"sma200":118,"year_high":155,"year_low":72,"market_cap":142000000000,"volume":8000000,"rsi":39,"macd_signal":"bearish_cross","adx":18,"bb_pct":0.25,"stoch_rsi":22,"obv_trend":"falling","bull_score":0,"target":166,"upside":50.0,"grade_buy":12,"grade_total":18,"grade_score":0.67,"eps_beats":5,"eps_total":7,"revenue_cagr_3y":0.27,"eps_cagr_3y":0,"roe_avg":0.02,"roe_consistent":false,"roic_avg":0.01,"gross_margin":0.48,"gross_margin_trend":"stable","piotroski":6,"altman_z":53.3,"dcf_value":19,"owner_earnings_yield":0.015,"intrinsic_buffett":30,"intrinsic_avg":24.5,"margin_of_safety":-0.78,"value_score":0.08,"composite":0.22,"signal":"SELL","classification":"GROWTH","reasons":[]}
]};

const SIGNAL_COLORS = { BUY: "#22c55e", WATCH: "#f59e0b", HOLD: "#94a3b8", SELL: "#ef4444" };
const CLASS_COLORS = { DEEP_VALUE: "#22d3ee", VALUE: "#06b6d4", QUALITY_GROWTH: "#a78bfa", GROWTH: "#818cf8", SPECULATIVE: "#f87171", NEUTRAL: "#64748b", UNKNOWN: "#475569" };

function formatNum(n, decimals = 1) {
  if (n === undefined || n === null) return "—";
  if (Math.abs(n) >= 1e12) return `$${(n/1e12).toFixed(1)}T`;
  if (Math.abs(n) >= 1e9) return `$${(n/1e9).toFixed(1)}B`;
  if (Math.abs(n) >= 1e6) return `$${(n/1e6).toFixed(1)}M`;
  return n.toFixed(decimals);
}

function formatPct(n) {
  if (n === undefined || n === null) return "—";
  return `${(n * 100).toFixed(0)}%`;
}

function BullDots({ score }) {
  return (
    <div style={{ display: "flex", gap: 3 }}>
      {Array.from({ length: 10 }, (_, i) => (
        <div key={i} style={{
          width: 8, height: 8, borderRadius: "50%",
          background: i < score ? (score >= 7 ? "#22c55e" : score >= 4 ? "#f59e0b" : "#ef4444") : "#1e293b",
          border: "1px solid #334155"
        }} />
      ))}
    </div>
  );
}

function MoSBar({ value }) {
  const pct = Math.max(-1, Math.min(1, value));
  const width = Math.abs(pct) * 100;
  const color = pct > 0.15 ? "#22c55e" : pct > 0 ? "#86efac" : pct > -0.2 ? "#fbbf24" : "#ef4444";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div style={{ width: 80, height: 6, background: "#1e293b", borderRadius: 3, position: "relative", overflow: "hidden" }}>
        <div style={{
          position: "absolute", height: "100%", borderRadius: 3, background: color,
          ...(pct >= 0 ? { left: "50%", width: `${width/2}%` } : { right: "50%", width: `${width/2}%` })
        }} />
        <div style={{ position: "absolute", left: "50%", top: 0, bottom: 0, width: 1, background: "#475569" }} />
      </div>
      <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color }}>{formatPct(value)}</span>
    </div>
  );
}

function StockRow({ stock, expanded, onToggle }) {
  const s = stock;
  return (
    <>
      <tr onClick={onToggle} style={{ cursor: "pointer", borderBottom: "1px solid #1e293b", transition: "background 0.15s" }}
          onMouseEnter={e => e.currentTarget.style.background = "#0f172a"}
          onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
        <td style={{ padding: "10px 12px", display: "flex", alignItems: "center", gap: 8 }}>
          {expanded ? <ChevronDown size={14} color="#64748b" /> : <ChevronRight size={14} color="#64748b" />}
          <span style={{ fontWeight: 700, letterSpacing: "0.05em", color: "#f8fafc" }}>{s.symbol}</span>
          <span style={{ fontSize: 10, padding: "2px 6px", borderRadius: 3, background: CLASS_COLORS[s.classification] + "22", color: CLASS_COLORS[s.classification], fontWeight: 600 }}>
            {s.classification?.replace("_", " ")}
          </span>
        </td>
        <td style={{ fontFamily: "'JetBrains Mono', monospace", textAlign: "right", padding: "10px 12px", color: "#e2e8f0" }}>
          ${s.price?.toFixed(2)}
        </td>
        <td style={{ padding: "10px 12px" }}>
          <span style={{ display: "inline-block", padding: "3px 10px", borderRadius: 4, fontSize: 11, fontWeight: 700, letterSpacing: "0.08em",
            background: SIGNAL_COLORS[s.signal] + "18", color: SIGNAL_COLORS[s.signal], border: `1px solid ${SIGNAL_COLORS[s.signal]}44` }}>
            {s.signal}
          </span>
        </td>
        <td style={{ fontFamily: "'JetBrains Mono', monospace", textAlign: "right", padding: "10px 12px", color: "#e2e8f0" }}>
          {s.composite?.toFixed(2)}
        </td>
        <td style={{ padding: "10px 12px" }}><BullDots score={s.bull_score} /></td>
        <td style={{ padding: "10px 12px" }}><MoSBar value={s.margin_of_safety} /></td>
        <td style={{ fontFamily: "'JetBrains Mono', monospace", textAlign: "right", padding: "10px 12px",
          color: s.upside > 20 ? "#22c55e" : s.upside > 0 ? "#94a3b8" : "#ef4444" }}>
          {s.upside > 0 ? "+" : ""}{s.upside?.toFixed(0)}%
        </td>
        <td style={{ fontFamily: "'JetBrains Mono', monospace", textAlign: "right", padding: "10px 12px", color: "#94a3b8" }}>
          {formatNum(s.market_cap, 0)}
        </td>
      </tr>
      {expanded && (
        <tr style={{ background: "#0c1222" }}>
          <td colSpan={8} style={{ padding: "0 12px 16px 36px" }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16, paddingTop: 12 }}>
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", color: "#64748b", marginBottom: 8 }}>TECHNICALS</div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 16px", fontSize: 12, fontFamily: "'JetBrains Mono', monospace" }}>
                  <span style={{ color: "#94a3b8" }}>RSI</span><span style={{ color: s.rsi > 70 ? "#ef4444" : s.rsi < 30 ? "#22c55e" : "#e2e8f0" }}>{s.rsi?.toFixed(0)}</span>
                  <span style={{ color: "#94a3b8" }}>MACD</span><span style={{ color: s.macd_signal?.includes("bullish") ? "#22c55e" : "#ef4444" }}>{s.macd_signal}</span>
                  <span style={{ color: "#94a3b8" }}>ADX</span><span style={{ color: s.adx > 25 ? "#f59e0b" : "#e2e8f0" }}>{s.adx?.toFixed(0)}</span>
                  <span style={{ color: "#94a3b8" }}>BB %B</span><span>{s.bb_pct?.toFixed(2)}</span>
                  <span style={{ color: "#94a3b8" }}>StochRSI</span><span>{s.stoch_rsi?.toFixed(0)}</span>
                  <span style={{ color: "#94a3b8" }}>OBV</span><span style={{ color: s.obv_trend === "rising" ? "#22c55e" : s.obv_trend === "falling" ? "#ef4444" : "#94a3b8" }}>{s.obv_trend}</span>
                </div>
              </div>
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", color: "#64748b", marginBottom: 8 }}>BUFFETT VALUE</div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 16px", fontSize: 12, fontFamily: "'JetBrains Mono', monospace" }}>
                  <span style={{ color: "#94a3b8" }}>ROE</span><span style={{ color: s.roe_avg > 0.15 ? "#22c55e" : "#94a3b8" }}>{formatPct(s.roe_avg)}</span>
                  <span style={{ color: "#94a3b8" }}>ROIC</span><span>{formatPct(s.roic_avg)}</span>
                  <span style={{ color: "#94a3b8" }}>Gross M</span><span style={{ color: s.gross_margin > 0.5 ? "#22c55e" : "#94a3b8" }}>{formatPct(s.gross_margin)} {s.gross_margin_trend === "expanding" ? "↑" : s.gross_margin_trend === "contracting" ? "↓" : "→"}</span>
                  <span style={{ color: "#94a3b8" }}>Piotroski</span><span style={{ color: s.piotroski >= 7 ? "#22c55e" : s.piotroski >= 5 ? "#f59e0b" : "#ef4444" }}>{s.piotroski}/9</span>
                  <span style={{ color: "#94a3b8" }}>Altman Z</span><span style={{ color: s.altman_z > 3 ? "#22c55e" : s.altman_z > 1.8 ? "#f59e0b" : "#ef4444" }}>{s.altman_z?.toFixed(1)}</span>
                  <span style={{ color: "#94a3b8" }}>OE Yield</span><span style={{ color: s.owner_earnings_yield > 0.045 ? "#22c55e" : "#94a3b8" }}>{formatPct(s.owner_earnings_yield)}</span>
                </div>
              </div>
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", color: "#64748b", marginBottom: 8 }}>INTRINSIC VALUE</div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 16px", fontSize: 12, fontFamily: "'JetBrains Mono', monospace" }}>
                  <span style={{ color: "#94a3b8" }}>DCF</span><span>${s.dcf_value?.toFixed(0)}</span>
                  <span style={{ color: "#94a3b8" }}>Buffett</span><span>{s.intrinsic_buffett ? `$${s.intrinsic_buffett.toFixed(0)}` : "N/A"}</span>
                  <span style={{ color: "#94a3b8" }}>Rev CAGR</span><span>{formatPct(s.revenue_cagr_3y)}</span>
                  <span style={{ color: "#94a3b8" }}>EPS CAGR</span><span>{formatPct(s.eps_cagr_3y)}</span>
                  <span style={{ color: "#94a3b8" }}>Target</span><span>${s.target?.toFixed(0)}</span>
                  <span style={{ color: "#94a3b8" }}>EPS Beats</span><span>{s.eps_beats}/{s.eps_total}</span>
                </div>
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sortKey, setSortKey] = useState("composite");
  const [sortDir, setSortDir] = useState("desc");
  const [filter, setFilter] = useState("ALL");
  const [expanded, setExpanded] = useState({});
  const [source, setSource] = useState("embedded");

  useEffect(() => {
    fetch(GCS_URL).then(r => r.json()).then(d => {
      setData(d); setSource("live"); setLoading(false);
    }).catch(() => {
      setData(FALLBACK); setSource("embedded"); setLoading(false);
    });
  }, []);

  const sorted = useMemo(() => {
    if (!data?.stocks) return [];
    let list = [...data.stocks];
    if (filter !== "ALL") list = list.filter(s => s.signal === filter);
    list.sort((a, b) => {
      const av = a[sortKey] ?? 0, bv = b[sortKey] ?? 0;
      return sortDir === "desc" ? bv - av : av - bv;
    });
    return list;
  }, [data, sortKey, sortDir, filter]);

  const toggleSort = (key) => {
    if (sortKey === key) setSortDir(d => d === "desc" ? "asc" : "desc");
    else { setSortKey(key); setSortDir("desc"); }
  };

  if (loading) return <div style={{ color: "#94a3b8", padding: 40, textAlign: "center", fontFamily: "'JetBrains Mono', monospace" }}>Loading scan data...</div>;

  const sum = data?.summary || {};
  const scanDate = data?.scan_date ? new Date(data.scan_date).toLocaleString() : "—";

  const headerStyle = (key) => ({
    padding: "8px 12px", textAlign: key === "symbol" ? "left" : "right", cursor: "pointer",
    fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", color: sortKey === key ? "#f59e0b" : "#64748b",
    userSelect: "none", whiteSpace: "nowrap", borderBottom: "2px solid #1e293b"
  });

  return (
    <div style={{ background: "#020617", color: "#e2e8f0", fontFamily: "'DM Sans', -apple-system, sans-serif", minHeight: "100vh", padding: "24px 20px" }}>
      <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet" />

      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0, letterSpacing: "-0.02em" }}>
            <span style={{ color: "#22c55e" }}>●</span> Stock Screener v5
          </h1>
          <p style={{ fontSize: 12, color: "#64748b", margin: "4px 0 0", fontFamily: "'JetBrains Mono', monospace" }}>
            {data?.region?.toUpperCase()} · {scanDate} · {source === "live" ? "Live from GCS" : "Embedded data"}
          </p>
        </div>
        <div style={{ fontSize: 10, color: "#475569", textAlign: "right", fontFamily: "'JetBrains Mono', monospace" }}>
          50% Buffett Value<br />30% Technical<br />20% Analyst
        </div>
      </div>

      {/* Signal Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 20 }}>
        {[
          { label: "BUY", count: sum.buy, icon: <TrendingUp size={16} />, color: "#22c55e" },
          { label: "WATCH", count: sum.watch, icon: <Target size={16} />, color: "#f59e0b" },
          { label: "HOLD", count: sum.hold, icon: <Shield size={16} />, color: "#94a3b8" },
          { label: "SELL", count: sum.sell, icon: <TrendingDown size={16} />, color: "#ef4444" },
        ].map(({ label, count, icon, color }) => (
          <div key={label} onClick={() => setFilter(f => f === label ? "ALL" : label)}
               style={{ background: filter === label ? color + "15" : "#0f172a", border: `1px solid ${filter === label ? color + "44" : "#1e293b"}`,
                 borderRadius: 8, padding: "14px 16px", cursor: "pointer", transition: "all 0.15s" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", color: "#64748b" }}>{label}</span>
              <span style={{ color }}>{icon}</span>
            </div>
            <div style={{ fontSize: 28, fontWeight: 700, color, fontFamily: "'JetBrains Mono', monospace", marginTop: 4 }}>{count || 0}</div>
          </div>
        ))}
      </div>

      {/* Table */}
      <div style={{ background: "#0f172a", borderRadius: 8, border: "1px solid #1e293b", overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: "#0f172a" }}>
              <th style={{ ...headerStyle("symbol"), textAlign: "left" }} onClick={() => toggleSort("symbol")}>SYMBOL</th>
              <th style={headerStyle("price")} onClick={() => toggleSort("price")}>PRICE</th>
              <th style={{ ...headerStyle("signal"), textAlign: "left" }} onClick={() => toggleSort("signal")}>SIGNAL</th>
              <th style={headerStyle("composite")} onClick={() => toggleSort("composite")}>SCORE</th>
              <th style={{ ...headerStyle("bull_score"), textAlign: "left" }} onClick={() => toggleSort("bull_score")}>BULL</th>
              <th style={{ ...headerStyle("margin_of_safety"), textAlign: "left" }} onClick={() => toggleSort("margin_of_safety")}>MARGIN OF SAFETY</th>
              <th style={headerStyle("upside")} onClick={() => toggleSort("upside")}>UPSIDE</th>
              <th style={headerStyle("market_cap")} onClick={() => toggleSort("market_cap")}>MCAP</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map(s => (
              <StockRow key={s.symbol} stock={s} expanded={!!expanded[s.symbol]}
                onToggle={() => setExpanded(e => ({ ...e, [s.symbol]: !e[s.symbol] }))} />
            ))}
          </tbody>
        </table>
        {sorted.length === 0 && (
          <div style={{ textAlign: "center", padding: 40, color: "#475569", fontSize: 13 }}>
            No stocks match this filter
          </div>
        )}
      </div>

      <div style={{ textAlign: "center", marginTop: 16, fontSize: 11, color: "#334155", fontFamily: "'JetBrains Mono', monospace" }}>
        {sum.total} stocks screened · {sorted.length} shown · Click row to expand · Click column to sort
      </div>
    </div>
  );
}
