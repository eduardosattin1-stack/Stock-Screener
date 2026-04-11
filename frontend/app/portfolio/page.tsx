"use client";
import { useState, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { Trash2, ChevronRight, TrendingUp, TrendingDown, DollarSign, BarChart3 } from "lucide-react";

const GCS_BASE = "https://storage.googleapis.com/screener-signals-carbonbridge/scans";

interface PortfolioEntry {
  symbol: string; entry_price: number; entry_date: string; shares: number; notes: string;
}

interface StockData {
  symbol: string; price: number; currency: string; market_cap: number;
  composite: number; signal: string; classification: string; bull_score: number;
  margin_of_safety: number; piotroski: number; roe_avg: number; gross_margin: number;
  target: number; upside: number;
}

const SIG_C: Record<string, string> = { BUY: "#2dd4a0", WATCH: "#e5a944", HOLD: "#7d8494", SELL: "#e5534b" };

function getPortfolio(): PortfolioEntry[] {
  if (typeof window === "undefined") return [];
  try { return JSON.parse(localStorage.getItem("screener_portfolio") || "[]"); } catch { return []; }
}
function savePortfolio(p: PortfolioEntry[]) {
  localStorage.setItem("screener_portfolio", JSON.stringify(p));
}

export default function Portfolio() {
  const router = useRouter();
  const [portfolio, setPortfolio] = useState<PortfolioEntry[]>([]);
  const [liveData, setLiveData] = useState<Record<string, StockData>>({});
  const [loading, setLoading] = useState(true);
  const [scanDate, setScanDate] = useState("—");

  useEffect(() => {
    const pf = getPortfolio();
    setPortfolio(pf);

    fetch(`${GCS_BASE}/latest.json`)
      .then(r => r.json())
      .then(data => {
        const map: Record<string, StockData> = {};
        data.stocks?.forEach((s: StockData) => { map[s.symbol] = s; });
        setLiveData(map);
        setScanDate(data.scan_date ? new Date(data.scan_date).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "—");
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const removePosition = (symbol: string) => {
    const updated = portfolio.filter(p => p.symbol !== symbol);
    setPortfolio(updated);
    savePortfolio(updated);
  };

  // Portfolio stats
  const stats = useMemo(() => {
    let totalCost = 0, totalValue = 0, winners = 0, losers = 0;
    portfolio.forEach(p => {
      const live = liveData[p.symbol];
      const currentPrice = live?.price || p.entry_price;
      const cost = p.entry_price * p.shares;
      const value = currentPrice * p.shares;
      totalCost += cost;
      totalValue += value;
      if (currentPrice > p.entry_price) winners++;
      else if (currentPrice < p.entry_price) losers++;
    });
    const totalPnL = totalValue - totalCost;
    const totalPnLPct = totalCost > 0 ? totalPnL / totalCost : 0;
    return { totalCost, totalValue, totalPnL, totalPnLPct, winners, losers, positions: portfolio.length };
  }, [portfolio, liveData]);

  const fmtMoney = (n: number) => {
    if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
    if (Math.abs(n) >= 1e3) return `$${(n / 1e3).toFixed(1)}K`;
    return `$${n.toFixed(0)}`;
  };

  return (
    <div style={{ minHeight: "100vh", padding: "16px 20px", maxWidth: 1200, margin: "0 auto" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20, paddingBottom: 12, borderBottom: "1px solid #1e2433" }}>
        <span style={{ fontSize: 14, fontWeight: 600, color: "#c9cdd6", letterSpacing: "0.02em" }}>
          PORTFOLIO<span style={{ color: "#4a5060", fontWeight: 400 }}>/tracker</span>
        </span>
        <span style={{ fontSize: 9, color: "#4a5060", fontFamily: "var(--font-mono)" }}>Last scan: {scanDate}</span>
      </div>

      {/* Summary cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8, marginBottom: 16 }}>
        <div style={{ background: "#0e1117", borderRadius: 5, border: "1px solid #161b26", padding: "12px 14px" }}>
          <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: "0.1em", color: "#4a5060", fontFamily: "var(--font-mono)" }}>POSITIONS</div>
          <div style={{ fontSize: 24, fontWeight: 700, color: "#c9cdd6", fontFamily: "var(--font-mono)", marginTop: 2 }}>{stats.positions}</div>
        </div>
        <div style={{ background: "#0e1117", borderRadius: 5, border: "1px solid #161b26", padding: "12px 14px" }}>
          <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: "0.1em", color: "#4a5060", fontFamily: "var(--font-mono)" }}>TOTAL VALUE</div>
          <div style={{ fontSize: 24, fontWeight: 700, color: "#c9cdd6", fontFamily: "var(--font-mono)", marginTop: 2 }}>{fmtMoney(stats.totalValue)}</div>
          <div style={{ fontSize: 9, color: "#4a5060", fontFamily: "var(--font-mono)" }}>Cost: {fmtMoney(stats.totalCost)}</div>
        </div>
        <div style={{ background: "#0e1117", borderRadius: 5, border: `1px solid ${stats.totalPnL >= 0 ? "#2dd4a015" : "#e5534b15"}`, padding: "12px 14px" }}>
          <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: "0.1em", color: "#4a5060", fontFamily: "var(--font-mono)" }}>TOTAL P&L</div>
          <div style={{ fontSize: 24, fontWeight: 700, fontFamily: "var(--font-mono)", marginTop: 2,
            color: stats.totalPnL >= 0 ? "#2dd4a0" : "#e5534b" }}>
            {stats.totalPnL >= 0 ? "+" : ""}{fmtMoney(stats.totalPnL)}
          </div>
          <div style={{ fontSize: 9, fontFamily: "var(--font-mono)",
            color: stats.totalPnLPct >= 0 ? "#2dd4a0" : "#e5534b" }}>
            {stats.totalPnLPct >= 0 ? "+" : ""}{(stats.totalPnLPct * 100).toFixed(1)}%
          </div>
        </div>
        <div style={{ background: "#0e1117", borderRadius: 5, border: "1px solid #161b26", padding: "12px 14px" }}>
          <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: "0.1em", color: "#4a5060", fontFamily: "var(--font-mono)" }}>WIN / LOSS</div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginTop: 6 }}>
            <span style={{ fontSize: 20, fontWeight: 700, color: "#2dd4a0", fontFamily: "var(--font-mono)" }}>{stats.winners}</span>
            <span style={{ fontSize: 12, color: "#4a5060" }}>/</span>
            <span style={{ fontSize: 20, fontWeight: 700, color: "#e5534b", fontFamily: "var(--font-mono)" }}>{stats.losers}</span>
          </div>
        </div>
      </div>

      {/* Positions table */}
      {portfolio.length === 0 ? (
        <div style={{ background: "#0e1117", borderRadius: 5, border: "1px solid #161b26", padding: "60px 20px", textAlign: "center" }}>
          <BarChart3 size={32} color="#1e2433" />
          <div style={{ fontSize: 12, color: "#4a5060", fontFamily: "var(--font-mono)", marginTop: 12 }}>
            No positions yet
          </div>
          <div style={{ fontSize: 10, color: "#2a3040", fontFamily: "var(--font-mono)", marginTop: 4 }}>
            Go to the screener, find a BUY signal, and click "Add to Portfolio" on the stock detail page
          </div>
          <button onClick={() => router.push("/")} style={{ marginTop: 16, fontSize: 11, padding: "8px 16px", borderRadius: 4,
            fontFamily: "var(--font-mono)", fontWeight: 600, color: "#2dd4a0", background: "#2dd4a008",
            border: "1px solid #2dd4a020", cursor: "pointer" }}>
            Open Screener
          </button>
        </div>
      ) : (
        <div style={{ background: "#0e1117", borderRadius: 5, border: "1px solid #161b26", overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr>
                {["Symbol", "Entry", "Current", "P&L", "P&L %", "Shares", "Value", "Signal", "Score", "Notes", ""].map((h, i) => (
                  <th key={h || i} style={{
                    padding: "9px 12px", textAlign: i === 0 ? "left" : i === 10 ? "center" : "right",
                    fontSize: 9, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase",
                    color: "#4a5060", fontFamily: "var(--font-mono)", borderBottom: "1px solid #1e2433",
                    whiteSpace: "nowrap",
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {portfolio.map(p => {
                const live = liveData[p.symbol];
                const currentPrice = live?.price || p.entry_price;
                const pnl = (currentPrice - p.entry_price) * p.shares;
                const pnlPct = (currentPrice - p.entry_price) / p.entry_price;
                const totalValue = currentPrice * p.shares;
                const signal = live?.signal || "—";
                const composite = live?.composite || 0;
                const pnlColor = pnl >= 0 ? "#2dd4a0" : "#e5534b";

                return (
                  <tr key={p.symbol} style={{ borderBottom: "1px solid #161b26", cursor: "pointer", transition: "background 0.1s" }}
                    onClick={() => router.push(`/stock/${p.symbol}`)}
                    onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "#141820"; }}
                    onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = "transparent"; }}>
                    <td style={{ padding: "10px 12px" }}>
                      <div style={{ fontWeight: 600, color: "#e8eaf0", fontFamily: "var(--font-mono)", fontSize: 11.5, letterSpacing: "0.04em" }}>{p.symbol}</div>
                      <div style={{ fontSize: 9, color: "#3a4050", fontFamily: "var(--font-mono)" }}>{p.entry_date}</div>
                    </td>
                    <td style={{ fontFamily: "var(--font-mono)", textAlign: "right", padding: "10px 12px", color: "#7d8494", fontSize: 11 }}>
                      ${p.entry_price.toFixed(2)}
                    </td>
                    <td style={{ fontFamily: "var(--font-mono)", textAlign: "right", padding: "10px 12px", color: "#c9cdd6", fontSize: 11.5, fontWeight: 600 }}>
                      ${currentPrice.toFixed(2)}
                    </td>
                    <td style={{ fontFamily: "var(--font-mono)", textAlign: "right", padding: "10px 12px", color: pnlColor, fontSize: 11.5, fontWeight: 600 }}>
                      {pnl >= 0 ? "+" : ""}{fmtMoney(pnl)}
                    </td>
                    <td style={{ fontFamily: "var(--font-mono)", textAlign: "right", padding: "10px 12px", fontSize: 11 }}>
                      <span style={{ color: pnlColor, fontWeight: 600 }}>{pnlPct >= 0 ? "+" : ""}{(pnlPct * 100).toFixed(1)}%</span>
                    </td>
                    <td style={{ fontFamily: "var(--font-mono)", textAlign: "right", padding: "10px 12px", color: "#4a5060", fontSize: 11 }}>
                      {p.shares}
                    </td>
                    <td style={{ fontFamily: "var(--font-mono)", textAlign: "right", padding: "10px 12px", color: "#c9cdd6", fontSize: 11 }}>
                      {fmtMoney(totalValue)}
                    </td>
                    <td style={{ textAlign: "right", padding: "10px 12px" }}>
                      {signal !== "—" ? (
                        <span style={{ display: "inline-block", padding: "2px 6px", borderRadius: 3, fontSize: 9, fontWeight: 600,
                          fontFamily: "var(--font-mono)", letterSpacing: "0.07em",
                          color: SIG_C[signal] || "#7d8494", background: `${SIG_C[signal] || "#7d8494"}10`,
                          border: `1px solid ${SIG_C[signal] || "#7d8494"}20` }}>
                          {signal}
                        </span>
                      ) : <span style={{ color: "#2a3040", fontSize: 10, fontFamily: "var(--font-mono)" }}>—</span>}
                    </td>
                    <td style={{ fontFamily: "var(--font-mono)", textAlign: "right", padding: "10px 12px", fontSize: 11,
                      color: composite > 0.6 ? "#2dd4a0" : composite > 0.4 ? "#c9cdd6" : "#e5534b" }}>
                      {composite > 0 ? composite.toFixed(2) : "—"}
                    </td>
                    <td style={{ padding: "10px 12px", maxWidth: 120 }}>
                      <span style={{ fontSize: 9, color: "#3a4050", fontFamily: "var(--font-mono)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", display: "block" }}>
                        {p.notes || "—"}
                      </span>
                    </td>
                    <td style={{ padding: "10px 6px", textAlign: "center" }}>
                      <button onClick={(e) => { e.stopPropagation(); removePosition(p.symbol); }}
                        style={{ background: "none", border: "none", cursor: "pointer", padding: 4, borderRadius: 3,
                          color: "#2a3040", transition: "color 0.15s" }}
                        onMouseEnter={e => { (e.currentTarget as HTMLElement).style.color = "#e5534b"; }}
                        onMouseLeave={e => { (e.currentTarget as HTMLElement).style.color = "#2a3040"; }}>
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

      <div style={{ textAlign: "center", marginTop: 10, fontSize: 9, color: "#2a3040", fontFamily: "var(--font-mono)" }}>
        Prices from latest scan · Entry prices locked at time of addition · Stored locally
      </div>
    </div>
  );
}
