"use client";
import { useState, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { Trash2, BarChart3 } from "lucide-react";

const GCS_BASE = "/api/gcs/scans";

interface PortfolioEntry { symbol: string; entry_price: number; entry_date: string; shares: number; notes: string; }
interface StockData { symbol: string; price: number; currency: string; market_cap: number; composite: number; signal: string; classification: string; bull_score: number; margin_of_safety: number; piotroski: number; roe_avg: number; gross_margin: number; target: number; upside: number; }

const SIG: Record<string, { color: string; bg: string; border: string }> = {
  BUY: { color: "#16a34a", bg: "#e8f5ee", border: "#b8dcc8" },
  WATCH: { color: "#d97706", bg: "#fffbeb", border: "#fde68a" },
  HOLD: { color: "#94a3b8", bg: "#f8fafc", border: "#e2e8f0" },
  SELL: { color: "#dc2626", bg: "#fef2f2", border: "#fecaca" },
};

function getPortfolio(): PortfolioEntry[] {
  if (typeof window === "undefined") return [];
  try { return JSON.parse(localStorage.getItem("screener_portfolio") || "[]"); } catch { return []; }
}
function savePortfolio(p: PortfolioEntry[]) { localStorage.setItem("screener_portfolio", JSON.stringify(p)); }

export default function Portfolio() {
  const router = useRouter();
  const [portfolio, setPortfolio] = useState<PortfolioEntry[]>([]);
  const [liveData, setLiveData] = useState<Record<string, StockData>>({});
  const [loading, setLoading] = useState(true);
  const [scanDate, setScanDate] = useState("—");

  useEffect(() => {
    setPortfolio(getPortfolio());
    fetch(`${GCS_BASE}/latest.json`).then(r => r.json()).then(data => {
      const map: Record<string, StockData> = {};
      data.stocks?.forEach((s: StockData) => { map[s.symbol] = s; });
      setLiveData(map);
      setScanDate(data.scan_date ? new Date(data.scan_date).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "—");
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  const removePosition = (symbol: string) => {
    const updated = portfolio.filter(p => p.symbol !== symbol);
    setPortfolio(updated); savePortfolio(updated);
  };

  const stats = useMemo(() => {
    let totalCost = 0, totalValue = 0, winners = 0, losers = 0;
    portfolio.forEach(p => {
      const live = liveData[p.symbol];
      const cur = live?.price || p.entry_price;
      totalCost += p.entry_price * p.shares;
      totalValue += cur * p.shares;
      if (cur > p.entry_price) winners++; else if (cur < p.entry_price) losers++;
    });
    return { totalCost, totalValue, totalPnL: totalValue - totalCost, totalPnLPct: totalCost > 0 ? (totalValue - totalCost) / totalCost : 0, winners, losers, positions: portfolio.length };
  }, [portfolio, liveData]);

  const fmtMoney = (n: number) => {
    if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
    if (Math.abs(n) >= 1e3) return `$${(n / 1e3).toFixed(1)}K`;
    return `$${n.toFixed(0)}`;
  };

  const T = {
    mono: "var(--font-mono, 'JetBrains Mono', monospace)",
    text: "#1a1a1a", muted: "#6b7280", light: "#9ca3af",
    green: "#2d7a4f", red: "#dc2626",
    cardBg: "#ffffff", cardBorder: "#e5e7eb", divider: "#f3f4f6",
    shadow: "0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)",
  };

  const cardStyle: React.CSSProperties = {
    background: T.cardBg, borderRadius: 8, border: `1px solid ${T.cardBorder}`,
    boxShadow: T.shadow, padding: "14px 16px",
  };

  const thStyle: React.CSSProperties = {
    padding: "9px 12px", fontSize: 9, fontWeight: 600, letterSpacing: "0.1em",
    textTransform: "uppercase", color: T.muted, fontFamily: T.mono,
    borderBottom: `2px solid ${T.cardBorder}`, whiteSpace: "nowrap",
  };

  return (
    <div style={{ minHeight: "100vh", padding: "20px 24px", maxWidth: 1280, margin: "0 auto" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20, paddingBottom: 12, borderBottom: `1px solid ${T.divider}` }}>
        <span style={{ fontSize: 14, fontWeight: 600, color: T.text, letterSpacing: "0.02em", fontFamily: T.mono }}>
          PORTFOLIO<span style={{ color: T.light, fontWeight: 400 }}>/tracker</span>
        </span>
        <span style={{ fontSize: 9, color: T.light, fontFamily: T.mono }}>Last scan: {scanDate}</span>
      </div>

      {/* Summary cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 20 }}>
        <div style={cardStyle}>
          <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: "0.1em", color: T.muted, fontFamily: T.mono }}>POSITIONS</div>
          <div style={{ fontSize: 26, fontWeight: 700, color: T.text, fontFamily: T.mono, marginTop: 4 }}>{stats.positions}</div>
        </div>
        <div style={cardStyle}>
          <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: "0.1em", color: T.muted, fontFamily: T.mono }}>TOTAL VALUE</div>
          <div style={{ fontSize: 26, fontWeight: 700, color: T.text, fontFamily: T.mono, marginTop: 4 }}>{fmtMoney(stats.totalValue)}</div>
          <div style={{ fontSize: 9, color: T.light, fontFamily: T.mono }}>Cost: {fmtMoney(stats.totalCost)}</div>
        </div>
        <div style={{ ...cardStyle, border: `1px solid ${stats.totalPnL >= 0 ? "#b8dcc8" : "#fecaca"}` }}>
          <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: "0.1em", color: T.muted, fontFamily: T.mono }}>TOTAL P&L</div>
          <div style={{ fontSize: 26, fontWeight: 700, fontFamily: T.mono, marginTop: 4, color: stats.totalPnL >= 0 ? T.green : T.red }}>
            {stats.totalPnL >= 0 ? "+" : ""}{fmtMoney(stats.totalPnL)}
          </div>
          <div style={{ fontSize: 9, fontFamily: T.mono, color: stats.totalPnLPct >= 0 ? T.green : T.red }}>
            {stats.totalPnLPct >= 0 ? "+" : ""}{(stats.totalPnLPct * 100).toFixed(1)}%
          </div>
        </div>
        <div style={cardStyle}>
          <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: "0.1em", color: T.muted, fontFamily: T.mono }}>WIN / LOSS</div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginTop: 6 }}>
            <span style={{ fontSize: 22, fontWeight: 700, color: T.green, fontFamily: T.mono }}>{stats.winners}</span>
            <span style={{ fontSize: 12, color: T.light }}>/</span>
            <span style={{ fontSize: 22, fontWeight: 700, color: T.red, fontFamily: T.mono }}>{stats.losers}</span>
          </div>
        </div>
      </div>

      {/* Positions table */}
      {portfolio.length === 0 ? (
        <div style={{ ...cardStyle, padding: "60px 20px", textAlign: "center" }}>
          <BarChart3 size={32} color={T.divider} />
          <div style={{ fontSize: 12, color: T.muted, fontFamily: T.mono, marginTop: 12 }}>No positions yet</div>
          <div style={{ fontSize: 10, color: T.light, fontFamily: T.mono, marginTop: 4 }}>
            Go to the screener, find a BUY signal, and click "Add to Portfolio" on the stock detail page
          </div>
          <button onClick={() => router.push("/")} style={{ marginTop: 16, fontSize: 11, padding: "8px 16px", borderRadius: 6,
            fontFamily: T.mono, fontWeight: 600, color: T.green, background: "#e8f5ee",
            border: "1px solid #b8dcc8", cursor: "pointer" }}>Open Screener</button>
        </div>
      ) : (
        <div style={{ ...cardStyle, padding: 0, overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr>
                {["Symbol", "Entry", "Current", "P&L", "P&L %", "Shares", "Value", "Signal", "Score", "Notes", ""].map((h, i) => (
                  <th key={h || i} style={{ ...thStyle, textAlign: i === 0 ? "left" : i === 10 ? "center" : "right" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {portfolio.map(p => {
                const live = liveData[p.symbol];
                const cur = live?.price || p.entry_price;
                const pnl = (cur - p.entry_price) * p.shares;
                const pnlPct = (cur - p.entry_price) / p.entry_price;
                const val = cur * p.shares;
                const signal = live?.signal || "—";
                const composite = live?.composite || 0;
                const pnlColor = pnl >= 0 ? T.green : T.red;
                const sigStyle = SIG[signal] || SIG.HOLD;

                return (
                  <tr key={p.symbol} style={{ borderBottom: `1px solid ${T.divider}`, cursor: "pointer", transition: "background 0.1s" }}
                    onClick={() => router.push(`/stock/${p.symbol}`)}
                    onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "#f8faf9"; }}
                    onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = ""; }}>
                    <td style={{ padding: "10px 12px" }}>
                      <div style={{ fontWeight: 600, color: T.text, fontFamily: T.mono, fontSize: 12, letterSpacing: "0.04em" }}>{p.symbol}</div>
                      <div style={{ fontSize: 9, color: T.light, fontFamily: T.mono }}>{p.entry_date}</div>
                    </td>
                    <td style={{ fontFamily: T.mono, textAlign: "right", padding: "10px 12px", color: T.muted, fontSize: 11 }}>${p.entry_price.toFixed(2)}</td>
                    <td style={{ fontFamily: T.mono, textAlign: "right", padding: "10px 12px", color: T.text, fontSize: 12, fontWeight: 600 }}>${cur.toFixed(2)}</td>
                    <td style={{ fontFamily: T.mono, textAlign: "right", padding: "10px 12px", color: pnlColor, fontSize: 12, fontWeight: 600 }}>{pnl >= 0 ? "+" : ""}{fmtMoney(pnl)}</td>
                    <td style={{ fontFamily: T.mono, textAlign: "right", padding: "10px 12px", color: pnlColor, fontSize: 11, fontWeight: 600 }}>{pnlPct >= 0 ? "+" : ""}{(pnlPct * 100).toFixed(1)}%</td>
                    <td style={{ fontFamily: T.mono, textAlign: "right", padding: "10px 12px", color: T.muted, fontSize: 11 }}>{p.shares}</td>
                    <td style={{ fontFamily: T.mono, textAlign: "right", padding: "10px 12px", color: T.text, fontSize: 11 }}>{fmtMoney(val)}</td>
                    <td style={{ textAlign: "right", padding: "10px 12px" }}>
                      {signal !== "—" ? (
                        <span style={{ display: "inline-block", padding: "2px 7px", borderRadius: 4, fontSize: 9, fontWeight: 700,
                          fontFamily: T.mono, letterSpacing: "0.07em",
                          color: sigStyle.color, background: sigStyle.bg, border: `1px solid ${sigStyle.border}` }}>{signal}</span>
                      ) : <span style={{ color: T.light, fontSize: 10, fontFamily: T.mono }}>—</span>}
                    </td>
                    <td style={{ fontFamily: T.mono, textAlign: "right", padding: "10px 12px", fontSize: 11,
                      color: composite > 0.6 ? T.green : composite > 0.4 ? T.text : T.red, fontWeight: 600 }}>
                      {composite > 0 ? composite.toFixed(2) : "—"}
                    </td>
                    <td style={{ padding: "10px 12px", maxWidth: 120 }}>
                      <span style={{ fontSize: 9, color: T.light, fontFamily: T.mono, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", display: "block" }}>
                        {p.notes || "—"}
                      </span>
                    </td>
                    <td style={{ padding: "10px 6px", textAlign: "center" }}>
                      <button onClick={e => { e.stopPropagation(); removePosition(p.symbol); }}
                        style={{ background: "none", border: "none", cursor: "pointer", padding: 4, borderRadius: 3, color: T.light, transition: "color 0.15s" }}
                        onMouseEnter={e => { (e.currentTarget as HTMLElement).style.color = T.red; }}
                        onMouseLeave={e => { (e.currentTarget as HTMLElement).style.color = T.light; }}>
                        <Trash2 size={12} />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <div style={{ textAlign: "center", marginTop: 12, fontSize: 9, color: T.light, fontFamily: T.mono }}>
        Prices from latest scan · Entry prices locked at time of addition · Stored locally
      </div>
    </div>
  );
}
