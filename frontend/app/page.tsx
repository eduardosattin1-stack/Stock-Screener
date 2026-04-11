"use client";
import { useState, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { TrendingUp, TrendingDown, ChevronRight, Shield, Target, Search } from "lucide-react";

const GCS_BASE = "/api/gcs/scans";

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

// Exchange-to-region mapping for client-side filtering
const EXCHANGE_REGION: Record<string, string> = {
  NASDAQ: "us", NYSE: "us", AMEX: "us",
  XETRA: "eu", PAR: "eu", LSE: "eu", AMS: "eu", MIL: "eu", STO: "eu", SIX: "eu", BME: "eu",
  JPX: "asia", HKSE: "asia", KSC: "asia", SHH: "asia", SHZ: "asia", BSE: "asia", SES: "asia", ASX: "asia",
  SAO: "latam",
};

const REGIONS = [
  { id: "all", label: "ALL" },
  { id: "us", label: "US" },
  { id: "eu", label: "EU" },
  { id: "asia", label: "ASIA" },
];

const SIG_C: Record<string, string> = { BUY: "#2dd4a0", WATCH: "#e5a944", HOLD: "#7d8494", SELL: "#e5534b" };
const CLS_C: Record<string, string> = { DEEP_VALUE: "#3bc9db", VALUE: "#3bc9db", QUALITY_GROWTH: "#9775fa", GROWTH: "#9775fa", SPECULATIVE: "#e5534b", NEUTRAL: "#4a5060" };

const fmtCap = (n: number) => n >= 1e12 ? `${(n/1e12).toFixed(1)}T` : n >= 1e9 ? `${(n/1e9).toFixed(0)}B` : `${(n/1e6).toFixed(0)}M`;
const fmtPct = (n: number | null | undefined) => n == null ? "—" : `${(n * 100).toFixed(0)}%`;

function BullDots({ score }: { score: number }) {
  const c = score >= 7 ? "#2dd4a0" : score >= 4 ? "#e5a944" : "#e5534b";
  return (
    <div style={{ display: "flex", gap: 2, alignItems: "center" }}>
      {Array.from({ length: 10 }, (_, i) => (
        <div key={i} style={{ width: 6, height: 6, borderRadius: "50%", background: i < score ? c : "#1a1f2e" }} />
      ))}
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "#4a5060", marginLeft: 4 }}>{score}</span>
    </div>
  );
}

function MoSBar({ value }: { value: number }) {
  const v = Math.max(-1, Math.min(1, value));
  const w = Math.abs(v) * 100;
  const c = v > 0.15 ? "#2dd4a0" : v > 0 ? "#5a9e7a" : v > -0.2 ? "#e5a944" : "#e5534b";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div style={{ width: 56, height: 3, background: "#1a1f2e", borderRadius: 2, position: "relative", overflow: "hidden" }}>
        <div style={{ position: "absolute", height: "100%", borderRadius: 2, background: c,
          ...(v >= 0 ? { left: "50%", width: `${w/2}%` } : { right: "50%", width: `${w/2}%` }) }} />
        <div style={{ position: "absolute", left: "50%", top: 0, bottom: 0, width: 1, background: "#1e2433" }} />
      </div>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: c, minWidth: 32 }}>{fmtPct(value)}</span>
    </div>
  );
}

export default function Dashboard() {
  const router = useRouter();
  const [data, setData] = useState<ScanData | null>(null);
  const [loading, setLoading] = useState(true);
  const [region, setRegion] = useState("all");
  const [sortKey, setSortKey] = useState<keyof StockData>("composite");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [sigFilter, setSigFilter] = useState("ALL");
  const [search, setSearch] = useState("");
  const [source, setSource] = useState("—");

  useEffect(() => {
    setLoading(true);
    fetch(`${GCS_BASE}/latest.json`)
      .then(r => { if (!r.ok) throw new Error(); return r.json(); })
      .then((d: ScanData) => { setData(d); setSource("live"); setLoading(false); })
      .catch(() => { setData(null); setSource("offline"); setLoading(false); });
  }, []);

  // Client-side region filtering
  const regionStocks = useMemo(() => {
    if (!data?.stocks) return [];
    if (region === "all") return data.stocks;
    return data.stocks.filter(s => {
      // Match by currency as a simple proxy when exchange isn't available
      if (region === "us") return s.currency === "USD" || s.currency === "USX";
      if (region === "eu") return ["EUR", "GBP", "CHF", "SEK", "DKK", "NOK"].includes(s.currency);
      if (region === "asia") return ["JPY", "HKD", "KRW", "CNY", "INR", "SGD", "AUD", "TWD"].includes(s.currency);
      return true;
    });
  }, [data, region]);

  // Compute summary from filtered stocks
  const sum = useMemo(() => {
    const stocks = regionStocks;
    return {
      total: stocks.length,
      buy: stocks.filter(s => s.signal === "BUY").length,
      watch: stocks.filter(s => s.signal === "WATCH").length,
      hold: stocks.filter(s => s.signal === "HOLD").length,
      sell: stocks.filter(s => s.signal === "SELL").length,
    };
  }, [regionStocks]);

  const sorted = useMemo(() => {
    let list = [...regionStocks];
    if (sigFilter !== "ALL") list = list.filter(s => s.signal === sigFilter);
    if (search) list = list.filter(s => s.symbol.toLowerCase().includes(search.toLowerCase()));
    list.sort((a, b) => {
      const av = (a[sortKey] as number) ?? 0, bv = (b[sortKey] as number) ?? 0;
      return sortDir === "desc" ? bv - av : av - bv;
    });
    return list;
  }, [regionStocks, sortKey, sortDir, sigFilter, search]);

  const toggleSort = (key: keyof StockData) => {
    if (sortKey === key) setSortDir(d => d === "desc" ? "asc" : "desc");
    else { setSortKey(key); setSortDir("desc"); }
  };

  const scanTime = data?.scan_date ? new Date(data.scan_date).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" }) : "—";

  const th = (key: string, align: string = "right"): React.CSSProperties => ({
    padding: "9px 12px", textAlign: align as "left"|"right"|"center", cursor: "pointer",
    fontSize: 9, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase",
    color: sortKey === key ? "#c9cdd6" : "#4a5060", fontFamily: "var(--font-mono)",
    borderBottom: "1px solid #1e2433", userSelect: "none", whiteSpace: "nowrap",
  });

  return (
    <div style={{ minHeight: "100vh", padding: "16px 20px", maxWidth: 1400, margin: "0 auto" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16, paddingBottom: 12, borderBottom: "1px solid #1e2433" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <span style={{ fontSize: 14, fontWeight: 600, color: "#c9cdd6", letterSpacing: "0.02em" }}>
            SCREENER<span style={{ color: "#4a5060", fontWeight: 400 }}>/v5</span>
          </span>
          <div style={{ display: "flex", gap: 1, background: "#0e1117", borderRadius: 4, padding: 2, border: "1px solid #1e2433" }}>
            {REGIONS.map(r => (
              <button key={r.id} onClick={() => setRegion(r.id)} style={{
                padding: "4px 10px", fontSize: 10, fontFamily: "var(--font-mono)", fontWeight: 600,
                border: "none", borderRadius: 3, cursor: "pointer",
                background: region === r.id ? "#1a1f2e" : "transparent",
                color: region === r.id ? "#c9cdd6" : "#4a5060",
                letterSpacing: "0.06em", transition: "all 0.15s",
              }}>{r.label}</button>
            ))}
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ position: "relative" }}>
            <Search size={12} style={{ position: "absolute", left: 7, top: 7, color: "#4a5060" }} />
            <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Symbol..."
              style={{ background: "#0e1117", border: "1px solid #1e2433", borderRadius: 3,
                padding: "5px 7px 5px 24px", fontSize: 11, color: "#c9cdd6", width: 120,
                fontFamily: "var(--font-mono)", outline: "none" }} />
          </div>
          <span style={{ fontSize: 9, color: "#4a5060", fontFamily: "var(--font-mono)" }}>{scanTime} · {source}</span>
        </div>
      </div>

      {/* Signal cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8, marginBottom: 14 }}>
        {([
          { key: "BUY", count: sum.buy, icon: <TrendingUp size={13} /> },
          { key: "WATCH", count: sum.watch, icon: <Target size={13} /> },
          { key: "HOLD", count: sum.hold, icon: <Shield size={13} /> },
          { key: "SELL", count: sum.sell, icon: <TrendingDown size={13} /> },
        ] as const).map(({ key, count, icon }) => {
          const active = sigFilter === key;
          const color = SIG_C[key];
          return (
            <button key={key} onClick={() => setSigFilter(f => f === key ? "ALL" : key)} style={{
              background: active ? `${color}08` : "#0e1117", textAlign: "left",
              border: `1px solid ${active ? `${color}25` : "#161b26"}`,
              borderRadius: 5, padding: "10px 12px", cursor: "pointer", transition: "all 0.15s",
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 9, fontWeight: 600, letterSpacing: "0.1em", color: "#4a5060", fontFamily: "var(--font-mono)" }}>{key}</span>
                <span style={{ color: active ? color : "#2a3040", opacity: 0.8 }}>{icon}</span>
              </div>
              <div style={{ fontSize: 20, fontWeight: 600, color: active ? color : "#7d8494", fontFamily: "var(--font-mono)", marginTop: 1 }}>{count}</div>
            </button>
          );
        })}
      </div>

      {loading ? (
        <div style={{ textAlign: "center", padding: 60, color: "#4a5060", fontFamily: "var(--font-mono)", fontSize: 11 }}>Loading...</div>
      ) : !data ? (
        <div style={{ textAlign: "center", padding: 60, color: "#4a5060", fontFamily: "var(--font-mono)", fontSize: 11 }}>
          No data — trigger a scan from Cloud Run or wait for 07:00 CET
        </div>
      ) : (
        <div style={{ background: "#0e1117", borderRadius: 5, border: "1px solid #161b26", overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr>
                <th style={{ ...th("symbol", "left"), paddingLeft: 14 }} onClick={() => toggleSort("symbol")}>Symbol</th>
                <th style={th("price")} onClick={() => toggleSort("price")}>Price</th>
                <th style={th("signal", "center")} onClick={() => toggleSort("signal")}>Signal</th>
                <th style={th("composite")} onClick={() => toggleSort("composite")}>Score</th>
                <th style={th("bull_score", "left")} onClick={() => toggleSort("bull_score")}>Momentum</th>
                <th style={th("margin_of_safety", "left")} onClick={() => toggleSort("margin_of_safety")}>Margin of Safety</th>
                <th style={th("upside")} onClick={() => toggleSort("upside")}>Analyst</th>
                <th style={th("piotroski")} onClick={() => toggleSort("piotroski")}>Piotroski</th>
                <th style={th("gross_margin")} onClick={() => toggleSort("gross_margin")}>Margin</th>
                <th style={th("roe_avg")} onClick={() => toggleSort("roe_avg")}>ROE</th>
                <th style={th("market_cap")} onClick={() => toggleSort("market_cap")}>MCap</th>
                <th style={{ ...th(""), cursor: "default" }}></th>
              </tr>
            </thead>
            <tbody>
              {sorted.map(s => (
                <tr key={s.symbol} onClick={() => router.push(`/stock/${s.symbol}`)}
                  style={{ cursor: "pointer", borderBottom: "1px solid #161b26", transition: "background 0.1s" }}
                  onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "#141820"; }}
                  onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = "transparent"; }}>
                  <td style={{ padding: "9px 12px 9px 14px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                      <span style={{ fontWeight: 600, color: "#e8eaf0", fontFamily: "var(--font-mono)", fontSize: 11.5, letterSpacing: "0.04em" }}>{s.symbol}</span>
                      <span style={{ fontSize: 8, padding: "1px 4px", borderRadius: 2, border: `1px solid ${(CLS_C[s.classification]||"#4a5060")}25`,
                        color: CLS_C[s.classification]||"#4a5060", fontFamily: "var(--font-mono)", fontWeight: 500 }}>
                        {s.classification?.replace("_", " ")}
                      </span>
                    </div>
                  </td>
                  <td style={{ fontFamily: "var(--font-mono)", textAlign: "right", padding: "9px 12px", color: "#c9cdd6", fontSize: 11.5 }}>
                    {s.price?.toFixed(2)}
                  </td>
                  <td style={{ textAlign: "center", padding: "9px 12px" }}>
                    <span style={{ display: "inline-block", padding: "2px 7px", borderRadius: 3, fontSize: 9, fontWeight: 600,
                      fontFamily: "var(--font-mono)", letterSpacing: "0.07em",
                      color: SIG_C[s.signal], background: `${SIG_C[s.signal]}10`, border: `1px solid ${SIG_C[s.signal]}20` }}>
                      {s.signal}
                    </span>
                  </td>
                  <td style={{ fontFamily: "var(--font-mono)", textAlign: "right", padding: "9px 12px", fontSize: 11.5,
                    color: s.composite > 0.6 ? "#2dd4a0" : s.composite > 0.4 ? "#c9cdd6" : "#e5534b" }}>
                    {s.composite?.toFixed(2)}
                  </td>
                  <td style={{ padding: "9px 12px" }}><BullDots score={s.bull_score} /></td>
                  <td style={{ padding: "9px 12px" }}><MoSBar value={s.margin_of_safety} /></td>
                  <td style={{ fontFamily: "var(--font-mono)", textAlign: "right", padding: "9px 12px", fontSize: 10.5,
                    color: s.upside > 20 ? "#2dd4a0" : s.upside > 0 ? "#7d8494" : "#e5534b" }}>
                    {s.target > 0 ? `${s.upside > 0 ? "+" : ""}${s.upside?.toFixed(0)}%` : "—"}
                  </td>
                  <td style={{ fontFamily: "var(--font-mono)", textAlign: "right", padding: "9px 12px", fontSize: 10.5,
                    color: s.piotroski >= 7 ? "#2dd4a0" : s.piotroski >= 5 ? "#7d8494" : "#e5534b" }}>
                    {s.piotroski}/9
                  </td>
                  <td style={{ fontFamily: "var(--font-mono)", textAlign: "right", padding: "9px 12px", fontSize: 10.5,
                    color: s.gross_margin > 0.6 ? "#2dd4a0" : s.gross_margin > 0.4 ? "#7d8494" : "#e5534b" }}>
                    {fmtPct(s.gross_margin)}
                  </td>
                  <td style={{ fontFamily: "var(--font-mono)", textAlign: "right", padding: "9px 12px", fontSize: 10.5,
                    color: s.roe_avg > 0.15 ? "#2dd4a0" : "#7d8494" }}>
                    {fmtPct(s.roe_avg)}
                  </td>
                  <td style={{ fontFamily: "var(--font-mono)", textAlign: "right", padding: "9px 12px", fontSize: 10.5, color: "#4a5060" }}>
                    {fmtCap(s.market_cap)}
                  </td>
                  <td style={{ padding: "9px 6px", textAlign: "center" }}>
                    <ChevronRight size={12} color="#2a3040" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {sorted.length === 0 && (
            <div style={{ textAlign: "center", padding: 40, color: "#4a5060", fontSize: 11, fontFamily: "var(--font-mono)" }}>
              {search ? `No results for "${search}"` : "No stocks match filter"}
            </div>
          )}
        </div>
      )}
      <div style={{ textAlign: "center", marginTop: 10, fontSize: 9, color: "#2a3040", fontFamily: "var(--font-mono)" }}>
        {sum.total} screened · {sorted.length} shown · Click row for detail · 50% Buffett + 30% Technical + 20% Analyst
      </div>
    </div>
  );
}
