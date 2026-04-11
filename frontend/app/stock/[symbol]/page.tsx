"use client";
import { useState, useEffect, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, TrendingUp, TrendingDown, AlertTriangle, ExternalLink, Plus, Check } from "lucide-react";

const GCS_BASE = "https://storage.googleapis.com/screener-signals-carbonbridge/scans";

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

interface PortfolioEntry {
  symbol: string; entry_price: number; entry_date: string; shares: number; notes: string;
}

const SIG_C: Record<string, string> = { BUY: "#2dd4a0", WATCH: "#e5a944", HOLD: "#7d8494", SELL: "#e5534b" };
const CLS_C: Record<string, string> = { DEEP_VALUE: "#3bc9db", VALUE: "#3bc9db", QUALITY_GROWTH: "#9775fa", GROWTH: "#9775fa", SPECULATIVE: "#e5534b", NEUTRAL: "#4a5060" };

const fmtPct = (n: number | null | undefined) => n == null ? "—" : `${(n * 100).toFixed(1)}%`;
const fmtUsd = (n: number | null | undefined) => n == null || n === 0 ? "—" : `$${n.toFixed(0)}`;

function Metric({ label, value, color, sub }: { label: string; value: string; color?: string; sub?: string }) {
  return (
    <div style={{ padding: "8px 0", borderBottom: "1px solid #161b26" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <span style={{ fontSize: 11, color: "#4a5060", fontFamily: "var(--font-mono)", fontWeight: 500 }}>{label}</span>
        <span style={{ fontSize: 12, color: color || "#c9cdd6", fontFamily: "var(--font-mono)", fontWeight: 600 }}>{value}</span>
      </div>
      {sub && <div style={{ fontSize: 9, color: "#3a4050", marginTop: 2, fontFamily: "var(--font-mono)" }}>{sub}</div>}
    </div>
  );
}

function SectionHeader({ title, action }: { title: string; action?: React.ReactNode }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center",
      fontSize: 10, fontWeight: 600, letterSpacing: "0.1em", color: "#4a5060", fontFamily: "var(--font-mono)",
      textTransform: "uppercase", marginBottom: 8, paddingBottom: 6, borderBottom: "1px solid #1e2433" }}>
      {title}
      {action}
    </div>
  );
}

function ScoreRing({ value, label, max, color }: { value: number; label: string; max: number; color: string }) {
  const pct = Math.min(value / max, 1);
  const radius = 28;
  const circ = 2 * Math.PI * radius;
  const offset = circ * (1 - pct);
  return (
    <div style={{ textAlign: "center" }}>
      <svg width="68" height="68" viewBox="0 0 68 68">
        <circle cx="34" cy="34" r={radius} fill="none" stroke="#1a1f2e" strokeWidth="4" />
        <circle cx="34" cy="34" r={radius} fill="none" stroke={color} strokeWidth="4"
          strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
          transform="rotate(-90 34 34)" style={{ transition: "stroke-dashoffset 0.5s" }} />
        <text x="34" y="32" textAnchor="middle" fill={color} fontSize="13" fontFamily="var(--font-mono)" fontWeight="600">{value}</text>
        <text x="34" y="44" textAnchor="middle" fill="#4a5060" fontSize="8" fontFamily="var(--font-mono)">/{max}</text>
      </svg>
      <div style={{ fontSize: 9, color: "#4a5060", fontFamily: "var(--font-mono)", marginTop: 2 }}>{label}</div>
    </div>
  );
}

function TargetBar({ price, target, dcf, buffett }: { price: number; target: number; dcf: number; buffett: number }) {
  const values = [price, target, dcf, buffett].filter(v => v > 0);
  if (values.length < 2) return null;
  const min = Math.min(...values) * 0.8;
  const max = Math.max(...values) * 1.1;
  const range = max - min;
  const pos = (v: number) => ((v - min) / range * 100);

  return (
    <div style={{ marginTop: 12, padding: "12px 0" }}>
      <div style={{ fontSize: 10, color: "#4a5060", fontFamily: "var(--font-mono)", marginBottom: 8, fontWeight: 600, letterSpacing: "0.08em" }}>
        PRICE vs INTRINSIC VALUE
      </div>
      <div style={{ position: "relative", height: 40, background: "#0e1117", borderRadius: 4, border: "1px solid #161b26" }}>
        <div style={{ position: "absolute", left: `${pos(price)}%`, top: 0, bottom: 0, width: 2, background: "#c9cdd6", zIndex: 2 }}>
          <div style={{ position: "absolute", top: -16, left: -12, fontSize: 9, color: "#c9cdd6", fontFamily: "var(--font-mono)", whiteSpace: "nowrap" }}>
            ${price.toFixed(0)}
          </div>
        </div>
        {target > 0 && (
          <div style={{ position: "absolute", left: `${pos(target)}%`, top: 8, width: 8, height: 8, borderRadius: "50%", background: "#e5a944", border: "2px solid #0e1117", transform: "translateX(-4px)" }}>
            <div style={{ position: "absolute", bottom: -14, left: -8, fontSize: 8, color: "#e5a944", fontFamily: "var(--font-mono)", whiteSpace: "nowrap" }}>Target</div>
          </div>
        )}
        {dcf > 0 && (
          <div style={{ position: "absolute", left: `${pos(dcf)}%`, top: 20, width: 8, height: 8, borderRadius: "50%", background: "#3bc9db", border: "2px solid #0e1117", transform: "translateX(-4px)" }}>
            <div style={{ position: "absolute", bottom: -14, left: -4, fontSize: 8, color: "#3bc9db", fontFamily: "var(--font-mono)", whiteSpace: "nowrap" }}>DCF</div>
          </div>
        )}
        {buffett > 0 && buffett < max && (
          <div style={{ position: "absolute", left: `${pos(buffett)}%`, top: 14, width: 8, height: 8, borderRadius: 2, background: "#9775fa", border: "2px solid #0e1117", transform: "translateX(-4px)" }}>
            <div style={{ position: "absolute", top: -14, left: -8, fontSize: 8, color: "#9775fa", fontFamily: "var(--font-mono)", whiteSpace: "nowrap" }}>Buffett</div>
          </div>
        )}
        {dcf > price && (
          <div style={{ position: "absolute", left: `${pos(price)}%`, top: 0, bottom: 0,
            width: `${pos(dcf) - pos(price)}%`, background: "#2dd4a010" }} />
        )}
      </div>
    </div>
  );
}

function BullDots({ score }: { score: number }) {
  const c = score >= 7 ? "#2dd4a0" : score >= 4 ? "#e5a944" : "#e5534b";
  return (
    <div style={{ display: "flex", gap: 3, alignItems: "center" }}>
      {Array.from({ length: 10 }, (_, i) => (
        <div key={i} style={{ width: 10, height: 10, borderRadius: "50%", background: i < score ? c : "#1a1f2e", border: "1px solid #1e2433" }} />
      ))}
    </div>
  );
}

// TradingView Advanced Chart Widget
function TradingViewChart({ symbol }: { symbol: string }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    containerRef.current.innerHTML = "";

    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
    script.async = true;
    script.innerHTML = JSON.stringify({
      autosize: true,
      symbol: symbol,
      interval: "D",
      timezone: "Europe/Amsterdam",
      theme: "dark",
      style: "1",
      locale: "en",
      backgroundColor: "#0e1117",
      gridColor: "#161b2620",
      hide_top_toolbar: false,
      hide_legend: false,
      allow_symbol_change: false,
      save_image: false,
      calendar: false,
      studies: ["STD;SMA"],
      support_host: "https://www.tradingview.com",
      width: "100%",
      height: "100%",
    });

    const wrapper = document.createElement("div");
    wrapper.className = "tradingview-widget-container__widget";
    wrapper.style.height = "100%";
    wrapper.style.width = "100%";

    containerRef.current.appendChild(wrapper);
    containerRef.current.appendChild(script);
  }, [symbol]);

  return (
    <div ref={containerRef} className="tradingview-widget-container"
      style={{ height: 380, background: "#0e1117", borderRadius: 5, border: "1px solid #161b26", overflow: "hidden" }} />
  );
}

// Portfolio helpers
function getPortfolio(): PortfolioEntry[] {
  if (typeof window === "undefined") return [];
  try { return JSON.parse(localStorage.getItem("screener_portfolio") || "[]"); } catch { return []; }
}
function savePortfolio(p: PortfolioEntry[]) {
  localStorage.setItem("screener_portfolio", JSON.stringify(p));
}

export default function StockDetail() {
  const params = useParams();
  const router = useRouter();
  const symbol = typeof params?.symbol === "string" ? params.symbol.toUpperCase() : "";
  const [stock, setStock] = useState<StockData | null>(null);
  const [loading, setLoading] = useState(true);
  const [inPortfolio, setInPortfolio] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);
  const [shares, setShares] = useState("100");
  const [notes, setNotes] = useState("");

  useEffect(() => {
    if (!symbol) return;
    fetch(`${GCS_BASE}/latest.json`)
      .then(r => r.json())
      .then(data => {
        const found = data.stocks?.find((s: StockData) => s.symbol === symbol);
        if (found) { setStock(found); setLoading(false); }
        else { setStock(null); setLoading(false); }
      })
      .catch(() => { setStock(null); setLoading(false); });

    const pf = getPortfolio();
    setInPortfolio(pf.some(p => p.symbol === symbol));
  }, [symbol]);

  const addToPortfolio = () => {
    if (!stock) return;
    const pf = getPortfolio();
    if (pf.some(p => p.symbol === symbol)) return;
    pf.push({
      symbol, entry_price: stock.price,
      entry_date: new Date().toISOString().split("T")[0],
      shares: parseInt(shares) || 100, notes,
    });
    savePortfolio(pf);
    setInPortfolio(true);
    setShowAddForm(false);
  };

  const removeFromPortfolio = () => {
    const pf = getPortfolio().filter(p => p.symbol !== symbol);
    savePortfolio(pf);
    setInPortfolio(false);
  };

  if (loading) return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <span style={{ color: "#4a5060", fontFamily: "var(--font-mono)", fontSize: 12 }}>Loading {symbol}...</span>
    </div>
  );

  if (!stock) return (
    <div style={{ minHeight: "100vh", padding: 40 }}>
      <button onClick={() => router.push("/")} style={{ background: "none", border: "none", color: "#4a5060", cursor: "pointer", display: "flex", alignItems: "center", gap: 6, fontFamily: "var(--font-mono)", fontSize: 12, marginBottom: 24 }}>
        <ArrowLeft size={14} /> Back
      </button>
      <div style={{ textAlign: "center", padding: 60, color: "#4a5060", fontFamily: "var(--font-mono)" }}>
        No data found for {symbol}. Run a scan first.
      </div>
    </div>
  );

  const s = stock;
  const sigColor = SIG_C[s.signal] || "#7d8494";
  const clsColor = CLS_C[s.classification] || "#4a5060";

  return (
    <div style={{ minHeight: "100vh", padding: "16px 20px", maxWidth: 1200, margin: "0 auto" }}>
      {/* Back nav */}
      <button onClick={() => router.push("/")} style={{ background: "none", border: "none", color: "#4a5060", cursor: "pointer",
        display: "flex", alignItems: "center", gap: 5, fontFamily: "var(--font-mono)", fontSize: 11, marginBottom: 16, padding: 0 }}>
        <ArrowLeft size={13} /> SCREENER/v5
      </button>

      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20, paddingBottom: 16, borderBottom: "1px solid #1e2433" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
            <h1 style={{ fontSize: 24, fontWeight: 700, color: "#e8eaf0", fontFamily: "var(--font-mono)", letterSpacing: "0.02em", margin: 0 }}>{s.symbol}</h1>
            <span style={{ fontSize: 10, padding: "3px 8px", borderRadius: 3, border: `1px solid ${clsColor}30`, color: clsColor,
              fontFamily: "var(--font-mono)", fontWeight: 600 }}>{s.classification?.replace("_", " ")}</span>
            <span style={{ fontSize: 11, padding: "3px 10px", borderRadius: 3, fontWeight: 700, fontFamily: "var(--font-mono)", letterSpacing: "0.07em",
              color: sigColor, background: `${sigColor}12`, border: `1px solid ${sigColor}25` }}>{s.signal}</span>
          </div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
            <span style={{ fontSize: 22, fontWeight: 700, color: "#e8eaf0", fontFamily: "var(--font-mono)" }}>
              {s.currency === "USD" ? "$" : s.currency + " "}{s.price.toFixed(2)}
            </span>
            <span style={{ fontSize: 11, color: "#4a5060", fontFamily: "var(--font-mono)" }}>
              52wk: {s.year_low.toFixed(0)}–{s.year_high.toFixed(0)}
            </span>
          </div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {/* Portfolio button */}
          {inPortfolio ? (
            <div style={{ display: "flex", gap: 6 }}>
              <span style={{ fontSize: 10, padding: "6px 10px", borderRadius: 3, fontFamily: "var(--font-mono)",
                color: "#2dd4a0", background: "#2dd4a008", border: "1px solid #2dd4a020", display: "flex", alignItems: "center", gap: 4 }}>
                <Check size={11} /> In Portfolio
              </span>
              <button onClick={removeFromPortfolio} style={{ fontSize: 9, padding: "6px 8px", borderRadius: 3,
                fontFamily: "var(--font-mono)", color: "#e5534b", background: "none", border: "1px solid #e5534b20",
                cursor: "pointer" }}>Remove</button>
            </div>
          ) : showAddForm ? (
            <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
              <input value={shares} onChange={e => setShares(e.target.value)} placeholder="Shares"
                style={{ width: 60, padding: "5px 7px", fontSize: 11, fontFamily: "var(--font-mono)", background: "#0e1117",
                  border: "1px solid #1e2433", borderRadius: 3, color: "#c9cdd6", outline: "none" }} />
              <input value={notes} onChange={e => setNotes(e.target.value)} placeholder="Notes (optional)"
                style={{ width: 120, padding: "5px 7px", fontSize: 11, fontFamily: "var(--font-mono)", background: "#0e1117",
                  border: "1px solid #1e2433", borderRadius: 3, color: "#c9cdd6", outline: "none" }} />
              <button onClick={addToPortfolio} style={{ fontSize: 10, padding: "5px 10px", borderRadius: 3,
                fontFamily: "var(--font-mono)", fontWeight: 600, color: "#08090e", background: "#2dd4a0",
                border: "none", cursor: "pointer" }}>Add</button>
              <button onClick={() => setShowAddForm(false)} style={{ fontSize: 10, padding: "5px 8px", borderRadius: 3,
                fontFamily: "var(--font-mono)", color: "#4a5060", background: "none", border: "1px solid #1e2433",
                cursor: "pointer" }}>Cancel</button>
            </div>
          ) : (
            <button onClick={() => setShowAddForm(true)} style={{ fontSize: 10, padding: "6px 12px", borderRadius: 3,
              fontFamily: "var(--font-mono)", fontWeight: 600, color: "#2dd4a0", background: "#2dd4a008",
              border: "1px solid #2dd4a020", cursor: "pointer", display: "flex", alignItems: "center", gap: 4 }}>
              <Plus size={12} /> Add to Portfolio
            </button>
          )}
          <div>
            <div style={{ fontSize: 11, color: "#4a5060", fontFamily: "var(--font-mono)", marginBottom: 4 }}>Composite Score</div>
            <div style={{ fontSize: 32, fontWeight: 700, fontFamily: "var(--font-mono)",
              color: s.composite > 0.6 ? "#2dd4a0" : s.composite > 0.4 ? "#c9cdd6" : "#e5534b" }}>
              {s.composite.toFixed(2)}
            </div>
          </div>
        </div>
      </div>

      {/* TradingView Chart */}
      <div style={{ marginBottom: 16 }}>
        <TradingViewChart symbol={s.symbol} />
      </div>

      {/* 3-column layout */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16, marginBottom: 16 }}>
        {/* Technical */}
        <div style={{ background: "#0e1117", borderRadius: 5, border: "1px solid #161b26", padding: "14px 16px" }}>
          <SectionHeader title="Technicals" />
          <div style={{ display: "flex", justifyContent: "center", gap: 16, margin: "12px 0" }}>
            <ScoreRing value={s.bull_score} label="Bull" max={10} color={s.bull_score >= 7 ? "#2dd4a0" : s.bull_score >= 4 ? "#e5a944" : "#e5534b"} />
            <ScoreRing value={Math.round(s.rsi)} label="RSI" max={100} color={s.rsi > 70 ? "#e5534b" : s.rsi < 30 ? "#2dd4a0" : "#7d8494"} />
            <ScoreRing value={Math.round(s.adx)} label="ADX" max={60} color={s.adx > 25 ? "#e5a944" : "#4a5060"} />
          </div>
          <Metric label="MACD" value={s.macd_signal} color={s.macd_signal?.includes("bullish") ? "#2dd4a0" : "#e5534b"} />
          <Metric label="Bollinger %B" value={s.bb_pct?.toFixed(2)} />
          <Metric label="Stoch RSI" value={s.stoch_rsi?.toFixed(0)} />
          <Metric label="OBV Trend" value={s.obv_trend} color={s.obv_trend === "rising" ? "#2dd4a0" : s.obv_trend === "falling" ? "#e5534b" : "#7d8494"} />
          <div style={{ marginTop: 8 }}>
            <div style={{ fontSize: 9, color: "#3a4050", fontFamily: "var(--font-mono)", marginBottom: 4 }}>MOMENTUM</div>
            <BullDots score={s.bull_score} />
          </div>
        </div>

        {/* Buffett Value */}
        <div style={{ background: "#0e1117", borderRadius: 5, border: "1px solid #161b26", padding: "14px 16px" }}>
          <SectionHeader title="Buffett Value" />
          <div style={{ display: "flex", justifyContent: "center", gap: 16, margin: "12px 0" }}>
            <ScoreRing value={s.piotroski} label="Piotroski" max={9} color={s.piotroski >= 7 ? "#2dd4a0" : s.piotroski >= 5 ? "#e5a944" : "#e5534b"} />
          </div>
          <Metric label="ROE (avg)" value={fmtPct(s.roe_avg)} color={s.roe_avg > 0.15 ? "#2dd4a0" : "#7d8494"} sub={s.roe_consistent ? "✓ Consistent >15% all years" : ""} />
          <Metric label="ROIC (avg)" value={fmtPct(s.roic_avg)} color={s.roic_avg > 0.12 ? "#2dd4a0" : "#7d8494"} />
          <Metric label="Gross Margin" value={fmtPct(s.gross_margin)} color={s.gross_margin > 0.5 ? "#2dd4a0" : "#7d8494"}
            sub={s.gross_margin_trend === "expanding" ? "↑ Expanding" : s.gross_margin_trend === "contracting" ? "↓ Contracting" : "→ Stable"} />
          <Metric label="Revenue CAGR 3Y" value={fmtPct(s.revenue_cagr_3y)} color={s.revenue_cagr_3y > 0.1 ? "#2dd4a0" : "#7d8494"} />
          <Metric label="EPS CAGR 3Y" value={fmtPct(s.eps_cagr_3y)} color={s.eps_cagr_3y > 0.1 ? "#2dd4a0" : "#7d8494"} />
          <Metric label="Altman Z" value={s.altman_z?.toFixed(1)} color={s.altman_z > 3 ? "#2dd4a0" : s.altman_z > 1.8 ? "#e5a944" : "#e5534b"}
            sub={s.altman_z > 3 ? "Safe zone" : s.altman_z > 1.8 ? "Grey zone" : "⚠ Distress zone"} />
          <Metric label="OE Yield" value={fmtPct(s.owner_earnings_yield)}
            color={s.owner_earnings_yield > 0.045 ? "#2dd4a0" : "#7d8494"} sub="vs 4.5% risk-free" />
        </div>

        {/* Analyst + Valuation */}
        <div style={{ background: "#0e1117", borderRadius: 5, border: "1px solid #161b26", padding: "14px 16px" }}>
          <SectionHeader title="Analyst & Valuation" />
          <div style={{ margin: "12px 0" }}>
            <div style={{ display: "flex", gap: 3, justifyContent: "center" }}>
              {Array.from({ length: s.eps_total || 1 }, (_, i) => (
                <div key={i} style={{ width: 20, height: 20, borderRadius: 3,
                  background: i < s.eps_beats ? "#2dd4a015" : "#e5534b15",
                  border: `1px solid ${i < s.eps_beats ? "#2dd4a030" : "#e5534b20"}`,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 9, color: i < s.eps_beats ? "#2dd4a0" : "#e5534b", fontFamily: "var(--font-mono)" }}>
                  {i < s.eps_beats ? "✓" : "✗"}
                </div>
              ))}
            </div>
            <div style={{ textAlign: "center", fontSize: 9, color: "#4a5060", fontFamily: "var(--font-mono)", marginTop: 4 }}>
              EPS beats: {s.eps_beats}/{s.eps_total}
            </div>
          </div>
          <Metric label="Price Target" value={fmtUsd(s.target)} sub={s.target > 0 ? `${s.upside > 0 ? "+" : ""}${s.upside?.toFixed(1)}% upside` : ""}
            color={s.upside > 20 ? "#2dd4a0" : s.upside > 0 ? "#7d8494" : "#e5534b"} />
          <Metric label="Buy Grades" value={s.grade_total > 0 ? `${s.grade_buy}/${s.grade_total}` : "—"}
            sub={s.grade_total > 0 ? `${(s.grade_score * 100).toFixed(0)}% bullish` : ""} />
          <Metric label="Margin of Safety" value={fmtPct(s.margin_of_safety)}
            color={s.margin_of_safety > 0.15 ? "#2dd4a0" : s.margin_of_safety > 0 ? "#5a9e7a" : "#e5534b"} />
          <Metric label="DCF Value" value={fmtUsd(s.dcf_value)} />
          <Metric label="Buffett Value" value={fmtUsd(s.intrinsic_buffett)} />
          <Metric label="Value Score" value={s.value_score?.toFixed(2)} color={s.value_score > 0.5 ? "#2dd4a0" : "#7d8494"} />
          <TargetBar price={s.price} target={s.target} dcf={s.dcf_value} buffett={s.intrinsic_buffett} />
        </div>
      </div>

      {/* Signal reasons */}
      {s.reasons && s.reasons.length > 0 && (
        <div style={{ background: "#0e1117", borderRadius: 5, border: "1px solid #161b26", padding: "14px 16px", marginBottom: 16 }}>
          <SectionHeader title="Active Signals" />
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
            {s.reasons.map((r, i) => (
              <span key={i} style={{ fontSize: 10, padding: "3px 8px", borderRadius: 3, fontFamily: "var(--font-mono)",
                background: r.includes("⚠") ? "#e5534b10" : "#2dd4a008",
                border: `1px solid ${r.includes("⚠") ? "#e5534b20" : "#2dd4a015"}`,
                color: r.includes("⚠") ? "#e5534b" : "#7d8494" }}>
                {r}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* External links */}
      <div style={{ background: "#0e1117", borderRadius: 5, border: "1px solid #161b26", padding: "14px 16px" }}>
        <SectionHeader title="Research" />
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          {[
            { label: "Yahoo Finance", url: `https://finance.yahoo.com/quote/${s.symbol}` },
            { label: "TradingView", url: `https://www.tradingview.com/symbols/${s.symbol}` },
            { label: "SEC Filings", url: `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${s.symbol}&type=10-K` },
            { label: "Macrotrends", url: `https://www.macrotrends.net/stocks/charts/${s.symbol}` },
          ].map(link => (
            <a key={link.label} href={link.url} target="_blank" rel="noopener noreferrer"
              style={{ fontSize: 10, padding: "5px 10px", borderRadius: 3, fontFamily: "var(--font-mono)",
                color: "#4a5060", background: "#151921", border: "1px solid #1e2433", textDecoration: "none",
                display: "flex", alignItems: "center", gap: 4, cursor: "pointer" }}>
              {link.label} <ExternalLink size={9} />
            </a>
          ))}
        </div>
      </div>
    </div>
  );
}
