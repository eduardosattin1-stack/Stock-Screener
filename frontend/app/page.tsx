"use client";
import { useState, useEffect, useMemo } from "react";
import { TrendingUp, TrendingDown, ChevronDown, ChevronRight, Shield, Target, Search, Filter } from "lucide-react";

const GCS_URL = "/api/gcs/scans/latest.json";
const GCS_FALLBACK = "https://storage.googleapis.com/screener-signals-carbonbridge/scans/latest.json";

// ── Types (v6 superset, backward-compat with v5) ───────────────────────────
interface FactorScores {
  upside: number; technical: number; analyst: number; transcript: number;
  institutional: number; insider: number; earnings: number; news: number;
  proximity: number; catastrophe: number;
}

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
  // v6 fields (optional for backward compat)
  factor_scores?: FactorScores;
  insider_score?: number; insider_net_buys?: number; insider_buy_ratio?: number;
  inst_score?: number; inst_holders_change?: number; inst_accumulation?: number;
  transcript_sentiment?: number; transcript_summary?: string; transcript_score?: number;
  news_sentiment?: number; news_score?: number;
  proximity_52wk?: number; proximity_score?: number;
  earnings_momentum?: number; earnings_score?: number;
  upside_score?: number; catastrophe_score?: number;
}

interface ScanData {
  scan_date: string; region: string; version: string;
  weights?: Record<string, number>;
  summary: { total: number; buy: number; watch: number; hold: number; sell: number };
  stocks: StockData[];
}

// ── Theme constants ─────────────────────────────────────────────────────────
const SIG = {
  BUY:   { color: "#16a34a", bg: "#e8f5ee", border: "#b8dcc8" },
  WATCH: { color: "#d97706", bg: "#fffbeb", border: "#fde68a" },
  HOLD:  { color: "#94a3b8", bg: "#f8fafc", border: "#e2e8f0" },
  SELL:  { color: "#dc2626", bg: "#fef2f2", border: "#fecaca" },
} as const;

const CLS: Record<string, string> = {
  DEEP_VALUE: "#2563eb", VALUE: "#0891b2", QUALITY_GROWTH: "#7c3aed",
  GROWTH: "#818cf8", SPECULATIVE: "#dc2626", NEUTRAL: "#64748b", UNKNOWN: "#475569",
};

const FACTOR_LABELS: Record<string, string> = {
  upside: "Upside", technical: "Technical", analyst: "Analyst",
  transcript: "Transcript", institutional: "Institutional", insider: "Insider",
  earnings: "Earnings", news: "News", proximity: "52-Week", catastrophe: "Catastrophe",
};

const FACTOR_ORDER = ["upside", "technical", "analyst", "transcript", "institutional", "insider", "earnings", "news", "proximity", "catastrophe"];

// ── Helpers ─────────────────────────────────────────────────────────────────
const fmt = (n: number | null | undefined, d = 1) => n == null ? "—" : n.toFixed(d);
const fmtPct = (n: number | null | undefined) => n == null ? "—" : `${(n * 100).toFixed(0)}%`;
const fmtMcap = (n: number | null | undefined) => {
  if (n == null) return "—";
  if (n >= 1e12) return `$${(n / 1e12).toFixed(1)}T`;
  if (n >= 1e9) return `$${(n / 1e9).toFixed(0)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(0)}M`;
  return `$${n.toFixed(0)}`;
};

/** Build factor_scores from v5 data when v6 factor_scores is missing */
function inferFactorScores(s: StockData): FactorScores {
  if (s.factor_scores) return s.factor_scores;
  return {
    upside: Math.min(1, Math.max(0, (s.upside || 0) / 80)),
    technical: Math.min(1, (s.bull_score || 0) / 10),
    analyst: s.grade_score || 0,
    transcript: s.transcript_score ?? 0.5,
    institutional: s.inst_score ?? 0.5,
    insider: s.insider_score ?? 0.5,
    earnings: Math.min(1, (s.eps_beats || 0) / Math.max(1, s.eps_total || 1)),
    news: s.news_score ?? 0.5,
    proximity: s.proximity_score ?? (s.year_high > 0 ? (s.price - s.year_low) / (s.year_high - s.year_low) : 0.5),
    catastrophe: s.catastrophe_score ?? 1,
  };
}

// ── Mini Radar Chart (SVG, 10 axes) ─────────────────────────────────────────
function MiniRadar({ scores, size = 48 }: { scores: FactorScores; size?: number }) {
  const cx = size / 2, cy = size / 2, r = size / 2 - 4;
  const values = FACTOR_ORDER.map(k => (scores as any)[k] ?? 0);
  const n = values.length;
  const angle = (i: number) => (Math.PI * 2 * i) / n - Math.PI / 2;

  // Background grid
  const gridLevels = [0.33, 0.66, 1.0];
  const gridPaths = gridLevels.map(level => {
    const pts = Array.from({ length: n }, (_, i) => {
      const a = angle(i);
      return `${cx + Math.cos(a) * r * level},${cy + Math.sin(a) * r * level}`;
    });
    return pts.join(" ");
  });

  // Data polygon
  const dataPoints = values.map((v, i) => {
    const a = angle(i);
    const dist = Math.max(0.05, v) * r;
    return `${cx + Math.cos(a) * dist},${cy + Math.sin(a) * dist}`;
  });

  // Axis lines
  const axes = Array.from({ length: n }, (_, i) => {
    const a = angle(i);
    return { x2: cx + Math.cos(a) * r, y2: cy + Math.sin(a) * r };
  });

  const avg = values.reduce((a, b) => a + b, 0) / n;
  const fillColor = avg > 0.6 ? "#2d7a4f" : avg > 0.4 ? "#d97706" : "#dc2626";

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {/* Grid */}
      {gridPaths.map((pts, i) => (
        <polygon key={i} points={pts} fill="none" stroke="#e2e8e4" strokeWidth={0.5} opacity={0.6} />
      ))}
      {/* Axes */}
      {axes.map((a, i) => (
        <line key={i} x1={cx} y1={cy} x2={a.x2} y2={a.y2} stroke="#e2e8e4" strokeWidth={0.4} />
      ))}
      {/* Data */}
      <polygon points={dataPoints.join(" ")} fill={fillColor} fillOpacity={0.2} stroke={fillColor} strokeWidth={1.2} strokeLinejoin="round" />
      {/* Dots at each vertex */}
      {values.map((v, i) => {
        const a = angle(i);
        const dist = Math.max(0.05, v) * r;
        return <circle key={i} cx={cx + Math.cos(a) * dist} cy={cy + Math.sin(a) * dist} r={1.5} fill={fillColor} />;
      })}
    </svg>
  );
}

// ── Large Radar for expanded row ────────────────────────────────────────────
function LargeRadar({ scores, size = 180 }: { scores: FactorScores; size?: number }) {
  const cx = size / 2, cy = size / 2, r = size / 2 - 24;
  const values = FACTOR_ORDER.map(k => (scores as any)[k] ?? 0);
  const n = values.length;
  const angle = (i: number) => (Math.PI * 2 * i) / n - Math.PI / 2;

  const gridLevels = [0.25, 0.5, 0.75, 1.0];
  const gridPaths = gridLevels.map(level => {
    const pts = Array.from({ length: n }, (_, i) => {
      const a = angle(i);
      return `${cx + Math.cos(a) * r * level},${cy + Math.sin(a) * r * level}`;
    });
    return pts.join(" ");
  });

  const dataPoints = values.map((v, i) => {
    const a = angle(i);
    const dist = Math.max(0.05, v) * r;
    return `${cx + Math.cos(a) * dist},${cy + Math.sin(a) * dist}`;
  });

  const avg = values.reduce((a, b) => a + b, 0) / n;
  const fillColor = avg > 0.6 ? "#2d7a4f" : avg > 0.4 ? "#d97706" : "#dc2626";

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {gridPaths.map((pts, i) => (
        <polygon key={i} points={pts} fill="none" stroke="#d1d5db" strokeWidth={0.6} opacity={0.5} />
      ))}
      {FACTOR_ORDER.map((k, i) => {
        const a = angle(i);
        const lx = cx + Math.cos(a) * (r + 16);
        const ly = cy + Math.sin(a) * (r + 16);
        return (
          <g key={k}>
            <line x1={cx} y1={cy} x2={cx + Math.cos(a) * r} y2={cy + Math.sin(a) * r} stroke="#d1d5db" strokeWidth={0.5} />
            <text x={lx} y={ly} textAnchor="middle" dominantBaseline="middle"
              fontSize={7} fontFamily="var(--font-mono)" fill="#6b7280" fontWeight="500">
              {FACTOR_LABELS[k]?.slice(0, 6)}
            </text>
          </g>
        );
      })}
      <polygon points={dataPoints.join(" ")} fill={fillColor} fillOpacity={0.15} stroke={fillColor} strokeWidth={1.5} strokeLinejoin="round" />
      {values.map((v, i) => {
        const a = angle(i);
        const dist = Math.max(0.05, v) * r;
        return <circle key={i} cx={cx + Math.cos(a) * dist} cy={cy + Math.sin(a) * dist} r={2.5} fill={fillColor} stroke="#fff" strokeWidth={1} />;
      })}
    </svg>
  );
}

// ── Factor Score Bar (for expanded detail) ──────────────────────────────────
function FactorBar({ name, weight, score, detail }: { name: string; weight: number; score: number; detail: string }) {
  const color = score > 0.7 ? "#16a34a" : score > 0.4 ? "#d97706" : "#dc2626";
  return (
    <div style={{ padding: "6px 0", borderBottom: "1px solid var(--divider)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
          <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", fontWeight: 600, color: "var(--text)" }}>{name}</span>
          <span style={{ fontSize: 9, fontFamily: "var(--font-mono)", color: "var(--text-light)" }}>({weight}%)</span>
        </div>
        <span style={{ fontSize: 12, fontFamily: "var(--font-mono)", fontWeight: 700, color }}>{(score * 100).toFixed(0)}</span>
      </div>
      <div style={{ height: 5, borderRadius: 3, background: "var(--bg-elevated)", overflow: "hidden", marginBottom: 3 }}>
        <div style={{ height: "100%", width: `${score * 100}%`, borderRadius: 3, background: color, transition: "width 0.4s ease" }} />
      </div>
      <div style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--text-muted)", lineHeight: 1.4 }}>{detail}</div>
    </div>
  );
}

// ── MoS Bar (margin of safety visual) ───────────────────────────────────────
function MoSBar({ value }: { value: number }) {
  const pct = Math.max(-1, Math.min(1, value));
  const width = Math.abs(pct) * 100;
  const color = pct > 0.15 ? "#16a34a" : pct > 0 ? "#86efac" : pct > -0.2 ? "#d97706" : "#dc2626";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div style={{ width: 70, height: 5, background: "var(--bg-elevated)", borderRadius: 3, position: "relative", overflow: "hidden" }}>
        <div style={{
          position: "absolute", height: "100%", borderRadius: 3, background: color,
          ...(pct >= 0 ? { left: "50%", width: `${width / 2}%` } : { right: "50%", width: `${width / 2}%` })
        }} />
        <div style={{ position: "absolute", left: "50%", top: 0, bottom: 0, width: 1, background: "var(--border)" }} />
      </div>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color, fontWeight: 600 }}>{fmtPct(value)}</span>
    </div>
  );
}

// ── Insider Arrow ───────────────────────────────────────────────────────────
function InsiderCell({ score, netBuys }: { score?: number; netBuys?: number }) {
  if (score == null) return <span style={{ color: "var(--text-light)", fontSize: 10, fontFamily: "var(--font-mono)" }}>—</span>;
  const buying = (netBuys ?? 0) > 0;
  const color = score > 0.6 ? "#16a34a" : score > 0.4 ? "var(--text-muted)" : "#dc2626";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 3 }}>
      <span style={{ fontSize: 12, color }}>{buying ? "↑" : (netBuys ?? 0) < 0 ? "↓" : "→"}</span>
      <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", fontWeight: 600, color }}>{(score * 100).toFixed(0)}</span>
    </div>
  );
}

// ── Sentiment Cell ──────────────────────────────────────────────────────────
function SentimentCell({ value }: { value?: number }) {
  if (value == null) return <span style={{ color: "var(--text-light)", fontSize: 10, fontFamily: "var(--font-mono)" }}>—</span>;
  const color = value > 0.3 ? "#16a34a" : value > -0.1 ? "var(--text-muted)" : "#dc2626";
  const face = value > 0.3 ? "😊" : value > -0.1 ? "😐" : "😟";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 3 }}>
      <span style={{ fontSize: 11 }}>{face}</span>
      <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", color, fontWeight: 500 }}>{value > 0 ? "+" : ""}{value.toFixed(2)}</span>
    </div>
  );
}

// ── Composite Score Pill ────────────────────────────────────────────────────
function ScorePill({ value }: { value: number }) {
  const color = value > 0.65 ? "#16a34a" : value > 0.45 ? "#d97706" : "#dc2626";
  const bg = value > 0.65 ? "#e8f5ee" : value > 0.45 ? "#fffbeb" : "#fef2f2";
  return (
    <div style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
      <div style={{ width: 40, height: 4, borderRadius: 2, background: "var(--bg-elevated)", overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${value * 100}%`, borderRadius: 2, background: color }} />
      </div>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700, color }}>{value.toFixed(2)}</span>
    </div>
  );
}

// ── Build factor detail text ────────────────────────────────────────────────
function factorDetail(key: string, s: StockData): string {
  const cur = s.currency === "EUR" ? "€" : s.currency === "GBP" ? "£" : "$";
  switch (key) {
    case "upside": return `Target ${cur}${s.target?.toFixed(0) ?? "?"} (${s.upside > 0 ? "+" : ""}${s.upside?.toFixed(1) ?? "?"}%) · DCF ${cur}${s.dcf_value?.toFixed(0) ?? "?"} · MoS ${fmtPct(s.margin_of_safety)}`;
    case "technical": return `Bull ${s.bull_score}/10 · RSI ${s.rsi?.toFixed(0)} · MACD ${s.macd_signal} · ADX ${s.adx?.toFixed(0)}`;
    case "analyst": return `Grades ${s.grade_buy}/${s.grade_total} buy · Score ${(s.grade_score * 100).toFixed(0)}%`;
    case "transcript": return s.transcript_summary || "No transcript available";
    case "institutional": return s.inst_holders_change != null ? `Holders QoQ ${(s.inst_holders_change * 100).toFixed(1)}% · Shares QoQ ${((s.inst_accumulation ?? 0) * 100).toFixed(1)}%` : "No institutional data";
    case "insider": return s.insider_buy_ratio != null ? `Buy ratio ${s.insider_buy_ratio?.toFixed(1)} · Net buys ${s.insider_net_buys ?? 0}` : "No insider data";
    case "earnings": return `EPS beats ${s.eps_beats}/${s.eps_total} · Momentum ${s.earnings_momentum != null ? (s.earnings_momentum > 0 ? "+" : "") + (s.earnings_momentum * 100).toFixed(1) + "%" : "N/A"}`;
    case "news": return s.news_sentiment != null ? `Sentiment ${s.news_sentiment > 0 ? "+" : ""}${s.news_sentiment.toFixed(2)}` : "No news data";
    case "proximity": return `At ${s.proximity_52wk != null ? (s.proximity_52wk * 100).toFixed(0) : "?"}% of range · High ${cur}${s.year_high?.toFixed(0)} Low ${cur}${s.year_low?.toFixed(0)}`;
    case "catastrophe": {
      const flags = (s.reasons || []).filter(r => r.includes("⚠"));
      return flags.length > 0 ? flags.join(" · ") : "No red flags";
    }
    default: return "";
  }
}

// ── Stock Row ───────────────────────────────────────────────────────────────
function StockRow({ stock: s, expanded, onToggle, weights }: { stock: StockData; expanded: boolean; onToggle: () => void; weights: Record<string, number> }) {
  const scores = inferFactorScores(s);
  const sigStyle = SIG[s.signal as keyof typeof SIG] || SIG.HOLD;

  return (
    <>
      <tr onClick={onToggle} style={{ cursor: "pointer", borderBottom: "1px solid var(--border-subtle)", transition: "background 0.12s" }}
          onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "var(--bg-hover)"; }}
          onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = ""; }}>
        {/* Symbol + Classification */}
        <td style={{ padding: "10px 12px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {expanded ? <ChevronDown size={13} color="var(--text-light)" /> : <ChevronRight size={13} color="var(--text-light)" />}
            <a href={`/stock/${s.symbol}`} onClick={e => e.stopPropagation()}
              style={{ fontWeight: 700, letterSpacing: "0.04em", color: "var(--text)", fontSize: 13, fontFamily: "var(--font-mono)" }}>{s.symbol}</a>
            <span style={{ fontSize: 9, padding: "1px 5px", borderRadius: 3, fontWeight: 600, fontFamily: "var(--font-mono)",
              background: (CLS[s.classification] || "#475569") + "10", color: CLS[s.classification] || "#475569" }}>
              {s.classification?.replace("_", " ")}
            </span>
          </div>
        </td>
        {/* Price */}
        <td style={{ fontFamily: "var(--font-mono)", textAlign: "right", padding: "10px 12px", color: "var(--text)", fontSize: 12 }}>
          {s.currency !== "USD" && <span style={{ fontSize: 9, color: "var(--text-light)", marginRight: 3 }}>{s.currency}</span>}
          ${s.price?.toFixed(2)}
        </td>
        {/* Signal */}
        <td style={{ padding: "10px 12px" }}>
          <span style={{ display: "inline-block", padding: "3px 10px", borderRadius: 4, fontSize: 10, fontWeight: 700,
            letterSpacing: "0.07em", fontFamily: "var(--font-mono)",
            background: sigStyle.bg, color: sigStyle.color, border: `1px solid ${sigStyle.border}` }}>
            {s.signal}
          </span>
        </td>
        {/* Composite */}
        <td style={{ padding: "10px 12px", textAlign: "right" }}><ScorePill value={s.composite} /></td>
        {/* Radar */}
        <td style={{ padding: "6px 8px", textAlign: "center" }}><MiniRadar scores={scores} size={44} /></td>
        {/* Bull */}
        <td style={{ padding: "10px 8px" }}>
          <div style={{ display: "flex", gap: 2 }}>
            {Array.from({ length: 10 }, (_, i) => {
              const active = i < s.bull_score;
              const c = s.bull_score >= 7 ? "#16a34a" : s.bull_score >= 4 ? "#d97706" : "#dc2626";
              return <div key={i} style={{ width: 6, height: 6, borderRadius: "50%", background: active ? c : "var(--bg-elevated)", border: `1px solid ${active ? c : "var(--border)"}` }} />;
            })}
          </div>
        </td>
        {/* MoS */}
        <td style={{ padding: "10px 8px" }}><MoSBar value={s.margin_of_safety} /></td>
        {/* Upside */}
        <td style={{ fontFamily: "var(--font-mono)", textAlign: "right", padding: "10px 12px", fontSize: 12,
          color: s.upside > 20 ? "#16a34a" : s.upside > 0 ? "var(--text-muted)" : "#dc2626", fontWeight: 600 }}>
          {s.upside > 0 ? "+" : ""}{s.upside?.toFixed(0)}%
        </td>
        {/* Insider */}
        <td style={{ padding: "10px 8px", textAlign: "center" }}>
          <InsiderCell score={s.insider_score} netBuys={s.insider_net_buys} />
        </td>
        {/* Transcript */}
        <td style={{ padding: "10px 8px" }}>
          <SentimentCell value={s.transcript_sentiment} />
        </td>
      </tr>

      {/* ─── Expanded Detail ─── */}
      {expanded && (
        <tr>
          <td colSpan={10} style={{ padding: 0, background: "var(--bg-surface)" }}>
            <div style={{ padding: "16px 20px 20px 40px", animation: "fadeIn 0.2s ease" }}>
              <div style={{ display: "grid", gridTemplateColumns: "180px 1fr", gap: 24 }}>
                {/* Radar */}
                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
                  <LargeRadar scores={scores} />
                  <div style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
                    Avg: {((Object.values(scores).reduce((a, b) => a + b, 0)) / 10 * 100).toFixed(0)}
                  </div>
                </div>
                {/* Factor Bars */}
                <div>
                  <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: "var(--green)", fontFamily: "var(--font-mono)",
                    marginBottom: 8, paddingBottom: 6, borderBottom: "2px solid var(--green-light)", textTransform: "uppercase" }}>
                    10-Factor Breakdown
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 24px" }}>
                    {FACTOR_ORDER.map(key => (
                      <FactorBar key={key} name={FACTOR_LABELS[key]} weight={(weights[key] || 0) * 100}
                        score={(scores as any)[key] ?? 0} detail={factorDetail(key, s)} />
                    ))}
                  </div>
                </div>
              </div>
              {/* Transcript summary + reasons */}
              {(s.transcript_summary || (s.reasons && s.reasons.length > 0)) && (
                <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--border-subtle)" }}>
                  {s.transcript_summary && (
                    <div style={{ fontSize: 11, fontFamily: "var(--font-sans)", color: "var(--text-secondary)", marginBottom: 8, fontStyle: "italic" }}>
                      "{s.transcript_summary}"
                    </div>
                  )}
                  {s.reasons && s.reasons.length > 0 && (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                      {s.reasons.map((r, i) => (
                        <span key={i} style={{ fontSize: 9, padding: "2px 7px", borderRadius: 3, fontFamily: "var(--font-mono)",
                          background: r.includes("⚠") ? "#fef2f2" : "var(--green-light)",
                          border: `1px solid ${r.includes("⚠") ? "#fecaca" : "var(--green-border)"}`,
                          color: r.includes("⚠") ? "#dc2626" : "var(--text-muted)" }}>{r}</span>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ── Main Dashboard ──────────────────────────────────────────────────────────
export default function Dashboard() {
  const [data, setData] = useState<ScanData | null>(null);
  const [loading, setLoading] = useState(true);
  const [sortKey, setSortKey] = useState<keyof StockData>("composite");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [filter, setFilter] = useState("ALL");
  const [search, setSearch] = useState("");
  const [classFilter, setClassFilter] = useState("ALL");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  useEffect(() => {
    fetch(GCS_URL).then(r => { if (!r.ok) throw new Error(); return r.json(); })
      .then((d: ScanData) => { setData(d); setLoading(false); })
      .catch(() => {
        fetch(GCS_FALLBACK).then(r => r.json())
          .then((d: ScanData) => { setData(d); setLoading(false); })
          .catch(() => setLoading(false));
      });
  }, []);

  const weights = data?.weights || { upside: 0.15, technical: 0.15, analyst: 0.10, transcript: 0.15, institutional: 0.10, insider: 0.10, earnings: 0.10, news: 0.05, proximity: 0.05, catastrophe: 0.05 };

  const sorted = useMemo(() => {
    if (!data?.stocks) return [];
    let list = [...data.stocks];
    if (filter !== "ALL") list = list.filter(s => s.signal === filter);
    if (classFilter !== "ALL") list = list.filter(s => s.classification === classFilter);
    if (search) {
      const q = search.toUpperCase();
      list = list.filter(s => s.symbol.includes(q));
    }
    list.sort((a, b) => {
      const av = (a[sortKey] as number) ?? 0;
      const bv = (b[sortKey] as number) ?? 0;
      return sortDir === "desc" ? bv - av : av - bv;
    });
    return list;
  }, [data, sortKey, sortDir, filter, classFilter, search]);

  const toggleSort = (key: keyof StockData) => {
    if (sortKey === key) setSortDir(d => d === "desc" ? "asc" : "desc");
    else { setSortKey(key); setSortDir("desc"); }
  };

  if (loading) return (
    <div style={{ color: "var(--text-muted)", padding: 60, textAlign: "center", fontFamily: "var(--font-mono)", fontSize: 13 }}>
      Loading scan data...
    </div>
  );

  const sum = data?.summary || { total: 0, buy: 0, watch: 0, hold: 0, sell: 0 };
  const scanDate = data?.scan_date ? new Date(data.scan_date).toLocaleString() : "—";
  const classifications = [...new Set(data?.stocks?.map(s => s.classification) || [])].sort();

  const headerStyle = (key: string, align: "left" | "right" | "center" = "right"): React.CSSProperties => ({
    padding: "8px 12px", textAlign: align, cursor: "pointer",
    fontSize: 9, fontWeight: 700, letterSpacing: "0.1em", fontFamily: "var(--font-mono)",
    color: sortKey === key ? "var(--green)" : "var(--text-light)",
    userSelect: "none", whiteSpace: "nowrap", borderBottom: "2px solid var(--border)",
    background: "var(--bg)",
  });

  return (
    <div style={{ padding: "20px 24px", maxWidth: 1440, margin: "0 auto" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
        <div>
          <p style={{ fontSize: 12, color: "var(--text-muted)", fontFamily: "var(--font-mono)", marginTop: 4 }}>
            {data?.region?.toUpperCase()} · {scanDate} · {sum.total} stocks · {data?.version || "v5"}
          </p>
        </div>
        <div style={{ fontSize: 9, color: "var(--text-light)", textAlign: "right", fontFamily: "var(--font-mono)", lineHeight: 1.6 }}>
          {data?.weights ? FACTOR_ORDER.map(k => `${FACTOR_LABELS[k]} ${((data.weights as any)[k] * 100).toFixed(0)}%`).join(" · ") : "50% Value · 30% Tech · 20% Analyst"}
        </div>
      </div>

      {/* Signal Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 20 }}>
        {([
          { label: "BUY", count: sum.buy, icon: <TrendingUp size={15} />, ...SIG.BUY },
          { label: "WATCH", count: sum.watch, icon: <Target size={15} />, ...SIG.WATCH },
          { label: "HOLD", count: sum.hold, icon: <Shield size={15} />, ...SIG.HOLD },
          { label: "SELL", count: sum.sell, icon: <TrendingDown size={15} />, ...SIG.SELL },
        ] as const).map(({ label, count, icon, color, bg, border }) => (
          <div key={label} onClick={() => setFilter(f => f === label ? "ALL" : label)}
            style={{
              background: filter === label ? bg : "var(--bg)",
              border: `1px solid ${filter === label ? border : "var(--border)"}`,
              borderRadius: 8, padding: "12px 16px", cursor: "pointer", transition: "all 0.15s",
              boxShadow: filter === label ? "var(--shadow-md)" : "var(--shadow-sm)",
            }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.1em", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>{label}</span>
              <span style={{ color }}>{icon}</span>
            </div>
            <div style={{ fontSize: 26, fontWeight: 700, color, fontFamily: "var(--font-mono)", marginTop: 2 }}>{count || 0}</div>
          </div>
        ))}
      </div>

      {/* Search + Classification Filter */}
      <div style={{ display: "flex", gap: 10, marginBottom: 12 }}>
        <div style={{ position: "relative", flex: 1, maxWidth: 280 }}>
          <Search size={14} style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "var(--text-light)" }} />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search symbol..."
            style={{ width: "100%", padding: "7px 10px 7px 32px", fontSize: 12, fontFamily: "var(--font-mono)",
              border: "1px solid var(--border)", borderRadius: 6, background: "var(--bg)", color: "var(--text)",
              outline: "none" }} />
        </div>
        <div style={{ position: "relative" }}>
          <Filter size={12} style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "var(--text-light)" }} />
          <select value={classFilter} onChange={e => setClassFilter(e.target.value)}
            style={{ padding: "7px 12px 7px 30px", fontSize: 11, fontFamily: "var(--font-mono)",
              border: "1px solid var(--border)", borderRadius: 6, background: "var(--bg)", color: "var(--text)",
              outline: "none", cursor: "pointer", appearance: "auto" }}>
            <option value="ALL">All Classifications</option>
            {classifications.map(c => <option key={c} value={c}>{c?.replace("_", " ")}</option>)}
          </select>
        </div>
      </div>

      {/* Table */}
      <div style={{ background: "var(--bg)", borderRadius: 8, border: "1px solid var(--border)", overflow: "hidden", boxShadow: "var(--shadow-md)" }}>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr>
                <th style={headerStyle("symbol", "left")} onClick={() => toggleSort("symbol")}>SYMBOL</th>
                <th style={headerStyle("price")} onClick={() => toggleSort("price")}>PRICE</th>
                <th style={headerStyle("signal", "left")} onClick={() => toggleSort("signal")}>SIGNAL</th>
                <th style={headerStyle("composite")} onClick={() => toggleSort("composite")}>SCORE</th>
                <th style={{ ...headerStyle("composite", "center"), cursor: "default" }}>RADAR</th>
                <th style={headerStyle("bull_score", "left")} onClick={() => toggleSort("bull_score")}>BULL</th>
                <th style={headerStyle("margin_of_safety", "left")} onClick={() => toggleSort("margin_of_safety")}>MoS</th>
                <th style={headerStyle("upside")} onClick={() => toggleSort("upside")}>UPSIDE</th>
                <th style={headerStyle("insider_score", "center")} onClick={() => toggleSort("insider_score" as any)}>INSIDER</th>
                <th style={headerStyle("transcript_sentiment", "left")} onClick={() => toggleSort("transcript_sentiment" as any)}>TRNSCRPT</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map(s => (
                <StockRow key={s.symbol} stock={s} weights={weights} expanded={!!expanded[s.symbol]}
                  onToggle={() => setExpanded(e => ({ ...e, [s.symbol]: !e[s.symbol] }))} />
              ))}
            </tbody>
          </table>
        </div>
        {sorted.length === 0 && (
          <div style={{ textAlign: "center", padding: 40, color: "var(--text-muted)", fontSize: 13, fontFamily: "var(--font-mono)" }}>
            No stocks match this filter
          </div>
        )}
      </div>

      <div style={{ textAlign: "center", marginTop: 14, fontSize: 10, color: "var(--text-light)", fontFamily: "var(--font-mono)" }}>
        {sum.total} screened · {sorted.length} shown · Click row to expand · Click column to sort
      </div>
    </div>
  );
}
