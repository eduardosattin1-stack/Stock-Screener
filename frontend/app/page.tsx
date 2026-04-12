"use client";
import { useState, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { TrendingUp, TrendingDown, ChevronDown, ChevronRight, Shield, Target } from "lucide-react";

const GCS_URL = "/api/gcs/scans/latest.json";

interface StockData {
  symbol: string; price: number; currency: string; market_cap: number;
  sma50: number; sma200: number; year_high: number; year_low: number; volume: number;
  rsi: number; macd_signal: string; adx: number; bb_pct: number; stoch_rsi: number;
  obv_trend: string; bull_score: number;
  target: number; upside: number; grade_buy: number; grade_total: number;
  grade_score: number; eps_beats: number; eps_total: number;
  revenue_cagr_3y: number; eps_cagr_3y: number; roe_avg: number;
  roe_consistent: boolean; roic_avg: number; gross_margin: number;
  gross_margin_trend: string; piotroski: number; altman_z: number;
  dcf_value: number; owner_earnings_yield: number; intrinsic_buffett: number;
  intrinsic_avg: number; margin_of_safety: number; value_score: number;
  composite: number; signal: string; classification: string; reasons: string[];
}

interface ScanData {
  scan_date: string; region: string; version: string;
  summary: { total: number; buy: number; watch: number; hold: number; sell: number };
  stocks: StockData[];
}

// ── Theme colors ──
const G = "#2d7a4f";
const GL = "#e8f5ee";
const GB = "#b8dcc8";
const A = "#d97706";
const AL = "#fffbeb";
const R = "#dc2626";
const RL = "#fef2f2";
const M = "#6b7280";
const ML = "#9ca3af";
const DIV = "#e5e7eb";
const BG = "#ffffff";
const TXT = "#1a1a1a";
const MONO = "'IBM Plex Mono', monospace";

const SIGNAL_COLORS: Record<string, { fg: string; bg: string; border: string }> = {
  BUY:   { fg: G, bg: GL, border: GB },
  WATCH: { fg: A, bg: AL, border: "#fde68a" },
  HOLD:  { fg: M, bg: "#f9fafb", border: DIV },
  SELL:  { fg: R, bg: RL, border: "#fecaca" },
};
const CLASS_COLORS: Record<string, string> = {
  DEEP_VALUE: "#2563eb", VALUE: "#0891b2", QUALITY_GROWTH: "#7c3aed",
  GROWTH: "#6366f1", SPECULATIVE: R, NEUTRAL: M, UNKNOWN: M,
};

function formatNum(n: number | undefined | null): string {
  if (n === undefined || n === null) return "—";
  if (Math.abs(n) >= 1e12) return `$${(n/1e12).toFixed(1)}T`;
  if (Math.abs(n) >= 1e9) return `$${(n/1e9).toFixed(1)}B`;
  if (Math.abs(n) >= 1e6) return `$${(n/1e6).toFixed(1)}M`;
  return n.toFixed(1);
}
function formatPct(n: number | undefined | null): string {
  if (n === undefined || n === null) return "—";
  return `${(n * 100).toFixed(0)}%`;
}

function BullDots({ score }: { score: number }) {
  const c = score >= 7 ? G : score >= 4 ? A : R;
  return (
    <div style={{ display: "flex", gap: 3 }}>
      {Array.from({ length: 10 }, (_, i) => (
        <div key={i} style={{
          width: 8, height: 8, borderRadius: "50%",
          background: i < score ? c : DIV,
          border: `1px solid ${i < score ? c : "#d1d5db"}`
        }} />
      ))}
    </div>
  );
}

function MoSBar({ value }: { value: number }) {
  const pct = Math.max(-1, Math.min(1, value));
  const width = Math.abs(pct) * 100;
  const color = pct > 0.15 ? G : pct > 0 ? "#5a9e7a" : pct > -0.2 ? A : R;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div style={{ width: 80, height: 6, background: DIV, borderRadius: 3, position: "relative", overflow: "hidden" }}>
        <div style={{
          position: "absolute", height: "100%", borderRadius: 3, background: color,
          ...(pct >= 0 ? { left: "50%", width: `${width/2}%` } : { right: "50%", width: `${width/2}%` })
        }} />
        <div style={{ position: "absolute", left: "50%", top: 0, bottom: 0, width: 1, background: "#d1d5db" }} />
      </div>
      <span style={{ fontFamily: MONO, fontSize: 12, color, fontWeight: 600 }}>{formatPct(value)}</span>
    </div>
  );
}

function StockRow({ stock, expanded, onToggle, onNavigate }: { stock: StockData; expanded: boolean; onToggle: () => void; onNavigate: () => void }) {
  const s = stock;
  const sig = SIGNAL_COLORS[s.signal] || SIGNAL_COLORS.HOLD;
  const clsC = CLASS_COLORS[s.classification] || M;
  return (
    <>
      <tr onClick={onToggle} style={{ cursor: "pointer", borderBottom: `1px solid ${DIV}`, transition: "background 0.15s" }}
          onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.background = "#f9fafb"; }}
          onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.background = "transparent"; }}>
        <td style={{ padding: "10px 12px", display: "flex", alignItems: "center", gap: 8 }}>
          {expanded ? <ChevronDown size={14} color={M} /> : <ChevronRight size={14} color={M} />}
          <span
            onClick={(e) => { e.stopPropagation(); onNavigate(); }}
            style={{ fontWeight: 700, letterSpacing: "0.05em", color: G, cursor: "pointer" }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.textDecoration = "underline"; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.textDecoration = "none"; }}
          >
            {s.symbol}
          </span>
          <span style={{ fontSize: 10, padding: "2px 6px", borderRadius: 3, background: `${clsC}10`, color: clsC, fontWeight: 600 }}>
            {s.classification?.replace("_", " ")}
          </span>
        </td>
        <td style={{ fontFamily: MONO, textAlign: "right", padding: "10px 12px", color: TXT }}>
          ${s.price?.toFixed(2)}
        </td>
        <td style={{ padding: "10px 12px" }}>
          <span style={{ display: "inline-block", padding: "3px 10px", borderRadius: 4, fontSize: 11, fontWeight: 700, letterSpacing: "0.08em",
            background: sig.bg, color: sig.fg, border: `1px solid ${sig.border}` }}>
            {s.signal}
          </span>
        </td>
        <td style={{ fontFamily: MONO, textAlign: "right", padding: "10px 12px", color: TXT, fontWeight: 600 }}>
          {s.composite?.toFixed(2)}
        </td>
        <td style={{ padding: "10px 12px" }}><BullDots score={s.bull_score} /></td>
        <td style={{ padding: "10px 12px" }}><MoSBar value={s.margin_of_safety} /></td>
        <td style={{ fontFamily: MONO, textAlign: "right", padding: "10px 12px", fontWeight: 600,
          color: s.upside > 20 ? G : s.upside > 0 ? M : R }}>
          {s.upside > 0 ? "+" : ""}{s.upside?.toFixed(0)}%
        </td>
        <td style={{ fontFamily: MONO, textAlign: "right", padding: "10px 12px", color: ML }}>
          {formatNum(s.market_cap)}
        </td>
      </tr>
      {expanded && (
        <tr style={{ background: "#f9fafb" }}>
          <td colSpan={8} style={{ padding: "0 12px 16px 36px" }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16, paddingTop: 12 }}>
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", color: G, marginBottom: 8 }}>TECHNICALS</div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 16px", fontSize: 12, fontFamily: MONO }}>
                  <span style={{ color: M }}>RSI</span><span style={{ color: s.rsi > 70 ? R : s.rsi < 30 ? G : TXT }}>{s.rsi?.toFixed(0)}</span>
                  <span style={{ color: M }}>MACD</span><span style={{ color: s.macd_signal?.includes("bullish") ? G : R }}>{s.macd_signal}</span>
                  <span style={{ color: M }}>ADX</span><span style={{ color: s.adx > 25 ? A : TXT }}>{s.adx?.toFixed(0)}</span>
                  <span style={{ color: M }}>BB %B</span><span style={{ color: TXT }}>{s.bb_pct?.toFixed(2)}</span>
                  <span style={{ color: M }}>StochRSI</span><span style={{ color: TXT }}>{s.stoch_rsi?.toFixed(0)}</span>
                  <span style={{ color: M }}>OBV</span><span style={{ color: s.obv_trend === "rising" ? G : s.obv_trend === "falling" ? R : M }}>{s.obv_trend}</span>
                </div>
              </div>
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", color: G, marginBottom: 8 }}>BUFFETT VALUE</div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 16px", fontSize: 12, fontFamily: MONO }}>
                  <span style={{ color: M }}>ROE</span><span style={{ color: s.roe_avg > 0.15 ? G : M }}>{formatPct(s.roe_avg)}</span>
                  <span style={{ color: M }}>ROIC</span><span style={{ color: TXT }}>{formatPct(s.roic_avg)}</span>
                  <span style={{ color: M }}>Gross M</span><span style={{ color: s.gross_margin > 0.5 ? G : M }}>{formatPct(s.gross_margin)} {s.gross_margin_trend === "expanding" ? "↑" : s.gross_margin_trend === "contracting" ? "↓" : "→"}</span>
                  <span style={{ color: M }}>Piotroski</span><span style={{ color: s.piotroski >= 7 ? G : s.piotroski >= 5 ? A : R }}>{s.piotroski}/9</span>
                  <span style={{ color: M }}>Altman Z</span><span style={{ color: s.altman_z > 3 ? G : s.altman_z > 1.8 ? A : R }}>{s.altman_z?.toFixed(1)}</span>
                  <span style={{ color: M }}>OE Yield</span><span style={{ color: s.owner_earnings_yield > 0.045 ? G : M }}>{formatPct(s.owner_earnings_yield)}</span>
                </div>
              </div>
              <div>
                <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", color: G, marginBottom: 8 }}>INTRINSIC VALUE</div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "4px 16px", fontSize: 12, fontFamily: MONO }}>
                  <span style={{ color: M }}>DCF</span><span style={{ color: TXT }}>${s.dcf_value?.toFixed(0)}</span>
                  <span style={{ color: M }}>Buffett</span><span style={{ color: TXT }}>{s.intrinsic_buffett ? `$${s.intrinsic_buffett.toFixed(0)}` : "N/A"}</span>
                  <span style={{ color: M }}>Rev CAGR</span><span style={{ color: TXT }}>{formatPct(s.revenue_cagr_3y)}</span>
                  <span style={{ color: M }}>EPS CAGR</span><span style={{ color: TXT }}>{formatPct(s.eps_cagr_3y)}</span>
                  <span style={{ color: M }}>Target</span><span style={{ color: TXT }}>${s.target?.toFixed(0)}</span>
                  <span style={{ color: M }}>EPS Beats</span><span style={{ color: TXT }}>{s.eps_beats}/{s.eps_total}</span>
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
  const router = useRouter();
  const [data, setData] = useState<ScanData | null>(null);
  const [loading, setLoading] = useState(true);
  const [sortKey, setSortKey] = useState<keyof StockData>("composite");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [filter, setFilter] = useState("ALL");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [source, setSource] = useState("loading");

  useEffect(() => {
    fetch(GCS_URL).then(r => r.json()).then((d: ScanData) => {
      setData(d); setSource("live"); setLoading(false);
    }).catch(() => {
      setData(null); setSource("error"); setLoading(false);
    });
  }, []);

  const sorted = useMemo(() => {
    if (!data?.stocks) return [];
    let list = [...data.stocks];
    if (filter !== "ALL") list = list.filter(s => s.signal === filter);
    list.sort((a, b) => {
      const av = (a[sortKey] as number) ?? 0;
      const bv = (b[sortKey] as number) ?? 0;
      return sortDir === "desc" ? bv - av : av - bv;
    });
    return list;
  }, [data, sortKey, sortDir, filter]);

  const toggleSort = (key: keyof StockData) => {
    if (sortKey === key) setSortDir(d => d === "desc" ? "asc" : "desc");
    else { setSortKey(key); setSortDir("desc"); }
  };

  if (loading) return (
    <div style={{ color: M, padding: 40, textAlign: "center", fontFamily: MONO }}>Loading scan data...</div>
  );
  if (!data) return (
    <div style={{ color: M, padding: 40, textAlign: "center", fontFamily: MONO }}>Failed to load scan data from GCS.</div>
  );

  const sum = data.summary || { total: 0, buy: 0, watch: 0, hold: 0, sell: 0 };
  const scanDate = data.scan_date ? new Date(data.scan_date).toLocaleString() : "—";

  const headerStyle = (key: string): React.CSSProperties => ({
    padding: "8px 12px", textAlign: key === "symbol" ? "left" : "right", cursor: "pointer",
    fontSize: 10, fontWeight: 700, letterSpacing: "0.1em",
    color: sortKey === key ? G : M,
    userSelect: "none", whiteSpace: "nowrap", borderBottom: `2px solid ${DIV}`,
  });

  const cardData = [
    { label: "BUY", count: sum.buy, icon: <TrendingUp size={16} />, fg: G, bg: GL, border: GB },
    { label: "WATCH", count: sum.watch, icon: <Target size={16} />, fg: A, bg: AL, border: "#fde68a" },
    { label: "HOLD", count: sum.hold, icon: <Shield size={16} />, fg: M, bg: "#f9fafb", border: DIV },
    { label: "SELL", count: sum.sell, icon: <TrendingDown size={16} />, fg: R, bg: RL, border: "#fecaca" },
  ];

  return (
    <div style={{ background: BG, color: TXT, fontFamily: "'IBM Plex Sans', -apple-system, sans-serif", minHeight: "100vh", padding: "24px 20px" }}>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0, letterSpacing: "-0.02em", color: TXT }}>
            <span style={{ color: G }}>●</span> Stock Screener v5
          </h1>
          <p style={{ fontSize: 12, color: M, margin: "4px 0 0", fontFamily: MONO }}>
            {data.region?.toUpperCase()} · {scanDate} · {source === "live" ? "Live from GCS" : source}
          </p>
        </div>
        <div style={{ fontSize: 10, color: ML, textAlign: "right", fontFamily: MONO }}>
          50% Buffett Value<br />30% Technical<br />20% Analyst
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 20 }}>
        {cardData.map(({ label, count, icon, fg, bg, border }) => (
          <div key={label} onClick={() => setFilter(f => f === label ? "ALL" : label)}
               style={{
                 background: filter === label ? bg : BG,
                 border: `1px solid ${filter === label ? border : DIV}`,
                 borderRadius: 8, padding: "14px 16px", cursor: "pointer", transition: "all 0.15s",
                 boxShadow: filter === label ? `0 2px 8px ${fg}15` : "0 1px 3px rgba(0,0,0,0.04)",
               }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", color: M }}>{label}</span>
              <span style={{ color: fg }}>{icon}</span>
            </div>
            <div style={{ fontSize: 28, fontWeight: 700, color: fg, fontFamily: MONO, marginTop: 4 }}>{count || 0}</div>
          </div>
        ))}
      </div>

      <div style={{ background: BG, borderRadius: 8, border: `1px solid ${DIV}`, overflow: "hidden", boxShadow: "0 1px 3px rgba(0,0,0,0.04)" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: "#f9fafb" }}>
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
                onToggle={() => setExpanded(e => ({ ...e, [s.symbol]: !e[s.symbol] }))}
                onNavigate={() => router.push(`/stock/${s.symbol}`)} />
            ))}
          </tbody>
        </table>
        {sorted.length === 0 && (
          <div style={{ textAlign: "center", padding: 40, color: M, fontSize: 13 }}>
            No stocks match this filter
          </div>
        )}
      </div>

      <div style={{ textAlign: "center", marginTop: 16, fontSize: 11, color: ML, fontFamily: MONO }}>
        {sum.total} stocks screened · {sorted.length} shown · Click symbol for detail · Click column to sort
      </div>
    </div>
  );
}
