"use client";
import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, TrendingUp, TrendingDown, Minus, Activity, Brain, ChevronRight, RefreshCw } from "lucide-react";

// ── GCS paths ──────────────────────────────────────────────────────────────────
const GCS_SCANS = "/api/gcs/scans";
const GCS_SIGNALS = "/api/gcs/signals";
const CLOUD_RUN = "https://stock-screener-606056076947.europe-west1.run.app";

// ── Types ──────────────────────────────────────────────────────────────────────
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

interface SignalPoint { date: string; composite: number; signal: string; price: number; bull: number; mos: number; target?: number; }

// ── Theme ──────────────────────────────────────────────────────────────────────
const T = {
  bg: "#ffffff",
  card: "#ffffff",
  cardBorder: "#e5e7eb",
  cardShadow: "0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)",
  text: "#1a1a1a",
  textMuted: "#6b7280",
  textLight: "#9ca3af",
  green: "#2d7a4f",
  greenLight: "#e8f5ee",
  greenBorder: "#b8dcc8",
  red: "#dc2626",
  redLight: "#fef2f2",
  amber: "#d97706",
  amberLight: "#fffbeb",
  blue: "#2563eb",
  blueLight: "#eff6ff",
  purple: "#7c3aed",
  purpleLight: "#f5f3ff",
  divider: "#f3f4f6",
  mono: "'SF Mono', 'Cascadia Code', 'Fira Code', monospace",
  sans: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
};

const SIG_C: Record<string, { bg: string; fg: string; border: string }> = {
  BUY:   { bg: T.greenLight, fg: T.green, border: T.greenBorder },
  WATCH: { bg: T.amberLight, fg: T.amber, border: "#fde68a" },
  HOLD:  { bg: "#f9fafb", fg: T.textMuted, border: T.cardBorder },
  SELL:  { bg: T.redLight, fg: T.red, border: "#fecaca" },
};

const CLS_C: Record<string, string> = {
  DEEP_VALUE: T.blue, VALUE: T.blue, QUALITY_GROWTH: T.purple,
  GROWTH: T.purple, SPECULATIVE: T.red, NEUTRAL: T.textMuted,
};

// ── Helpers ────────────────────────────────────────────────────────────────────
const fmtPct = (n: number | null | undefined) => n == null ? "—" : `${(n * 100).toFixed(1)}%`;
const fmtPrice = (n: number | null | undefined, cur?: string) => {
  if (n == null || n === 0) return "—";
  const sym = cur === "EUR" ? "€" : cur === "GBP" ? "£" : cur === "JPY" ? "¥" : "$";
  return `${sym}${n.toFixed(2)}`;
};

// ── Shared components ──────────────────────────────────────────────────────────
function Card({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{
      background: T.card, borderRadius: 8, border: `1px solid ${T.cardBorder}`,
      boxShadow: T.cardShadow, padding: "16px 18px", ...style
    }}>
      {children}
    </div>
  );
}

function SectionHeader({ title, icon }: { title: string; icon?: React.ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, fontWeight: 600,
      letterSpacing: "0.08em", color: T.green, fontFamily: T.mono,
      textTransform: "uppercase", marginBottom: 12, paddingBottom: 8,
      borderBottom: `2px solid ${T.greenLight}` }}>
      {icon}
      {title}
    </div>
  );
}

function Metric({ label, value, color, sub }: { label: string; value: string; color?: string; sub?: string }) {
  return (
    <div style={{ padding: "7px 0", borderBottom: `1px solid ${T.divider}` }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <span style={{ fontSize: 11, color: T.textMuted, fontFamily: T.mono, fontWeight: 500 }}>{label}</span>
        <span style={{ fontSize: 12, color: color || T.text, fontFamily: T.mono, fontWeight: 600 }}>{value}</span>
      </div>
      {sub && <div style={{ fontSize: 9, color: T.textLight, marginTop: 2, fontFamily: T.mono }}>{sub}</div>}
    </div>
  );
}

function ScoreRing({ value, label, max, color }: { value: number; label: string; max: number; color: string }) {
  const pct = Math.min(value / max, 1);
  const r = 26, circ = 2 * Math.PI * r, offset = circ * (1 - pct);
  return (
    <div style={{ textAlign: "center" }}>
      <svg width="62" height="62" viewBox="0 0 62 62">
        <circle cx="31" cy="31" r={r} fill="none" stroke={T.divider} strokeWidth="4" />
        <circle cx="31" cy="31" r={r} fill="none" stroke={color} strokeWidth="4"
          strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
          transform="rotate(-90 31 31)" style={{ transition: "stroke-dashoffset 0.6s ease" }} />
        <text x="31" y="29" textAnchor="middle" fill={color} fontSize="13" fontFamily={T.mono} fontWeight="700">{value}</text>
        <text x="31" y="41" textAnchor="middle" fill={T.textLight} fontSize="8" fontFamily={T.mono}>/{max}</text>
      </svg>
      <div style={{ fontSize: 9, color: T.textMuted, fontFamily: T.mono, marginTop: 2 }}>{label}</div>
    </div>
  );
}

// ── MomentumPanel ──────────────────────────────────────────────────────────────
function MomentumPanel({ s }: { s: StockData }) {
  const sma50Above200 = s.sma50 > s.sma200;
  const priceAbove50 = s.price > s.sma50;
  const priceAbove200 = s.price > s.sma200;
  const goldenCross = sma50Above200;

  // RSI zone
  const rsiZone = s.rsi > 70 ? "Overbought" : s.rsi > 60 ? "Bullish" : s.rsi > 40 ? "Neutral" : s.rsi > 30 ? "Bearish" : "Oversold";
  const rsiColor = s.rsi > 70 ? T.red : s.rsi < 30 ? T.green : s.rsi > 60 ? T.green : s.rsi < 40 ? T.amber : T.textMuted;

  // 52-week position
  const range52 = s.year_high - s.year_low;
  const pos52 = range52 > 0 ? ((s.price - s.year_low) / range52) * 100 : 50;

  const indicators = [
    { label: "MACD", value: s.macd_signal, bullish: s.macd_signal?.includes("bullish") },
    { label: "ADX", value: s.adx?.toFixed(1), bullish: s.adx > 25 },
    { label: "BB %B", value: s.bb_pct?.toFixed(2), bullish: s.bb_pct > 0.2 && s.bb_pct < 0.8 },
    { label: "StochRSI", value: s.stoch_rsi?.toFixed(0), bullish: s.stoch_rsi > 20 && s.stoch_rsi < 80 },
    { label: "OBV", value: s.obv_trend, bullish: s.obv_trend === "rising" },
  ];

  return (
    <Card>
      <SectionHeader title="Momentum" icon={<Activity size={12} />} />

      {/* SMA Crossover */}
      <div style={{ marginBottom: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
          <div style={{
            width: 8, height: 8, borderRadius: "50%",
            background: goldenCross ? T.green : T.red,
            boxShadow: `0 0 6px ${goldenCross ? T.green : T.red}40`
          }} />
          <span style={{ fontSize: 11, fontFamily: T.mono, fontWeight: 600, color: goldenCross ? T.green : T.red }}>
            {goldenCross ? "Golden Cross" : "Death Cross"}
          </span>
          <span style={{ fontSize: 10, fontFamily: T.mono, color: T.textLight }}>
            SMA50 {sma50Above200 ? ">" : "<"} SMA200
          </span>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {[
            { label: `Price ${priceAbove50 ? ">" : "<"} SMA50`, ok: priceAbove50, val: `${fmtPrice(s.sma50)}` },
            { label: `Price ${priceAbove200 ? ">" : "<"} SMA200`, ok: priceAbove200, val: `${fmtPrice(s.sma200)}` },
          ].map((m, i) => (
            <div key={i} style={{
              flex: 1, padding: "6px 8px", borderRadius: 6, fontSize: 10, fontFamily: T.mono,
              background: m.ok ? T.greenLight : T.redLight,
              color: m.ok ? T.green : T.red,
              border: `1px solid ${m.ok ? T.greenBorder : "#fecaca"}`,
            }}>
              <div style={{ fontWeight: 600 }}>{m.label}</div>
              <div style={{ fontSize: 9, opacity: 0.8, marginTop: 1 }}>{m.val}</div>
            </div>
          ))}
        </div>
      </div>

      {/* RSI Slider */}
      <div style={{ marginBottom: 14 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
          <span style={{ fontSize: 10, fontFamily: T.mono, color: T.textMuted }}>RSI</span>
          <span style={{ fontSize: 11, fontFamily: T.mono, fontWeight: 600, color: rsiColor }}>
            {s.rsi?.toFixed(1)} — {rsiZone}
          </span>
        </div>
        <div style={{ position: "relative", height: 8, borderRadius: 4, overflow: "hidden",
          background: `linear-gradient(to right, ${T.green} 0%, ${T.green} 30%, ${T.divider} 30%, ${T.divider} 70%, ${T.red} 70%, ${T.red} 100%)` }}>
          <div style={{
            position: "absolute", left: `${(s.rsi / 100) * 100}%`, top: -2, width: 12, height: 12,
            borderRadius: "50%", background: "#fff", border: `2px solid ${rsiColor}`,
            transform: "translateX(-6px)", boxShadow: `0 1px 3px rgba(0,0,0,0.15)`,
          }} />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 8, fontFamily: T.mono, color: T.textLight, marginTop: 2 }}>
          <span>Oversold</span><span>Neutral</span><span>Overbought</span>
        </div>
      </div>

      {/* 52-Week Range */}
      <div style={{ marginBottom: 14 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
          <span style={{ fontSize: 10, fontFamily: T.mono, color: T.textMuted }}>52-Week Range</span>
          <span style={{ fontSize: 10, fontFamily: T.mono, color: T.textMuted }}>{pos52.toFixed(0)}%</span>
        </div>
        <div style={{ position: "relative", height: 6, borderRadius: 3, background: T.divider }}>
          <div style={{
            position: "absolute", left: 0, top: 0, bottom: 0, width: `${pos52}%`,
            borderRadius: 3, background: `linear-gradient(to right, ${T.green}, ${pos52 > 80 ? T.amber : T.green})`,
          }} />
          <div style={{
            position: "absolute", left: `${pos52}%`, top: -3, width: 12, height: 12,
            borderRadius: "50%", background: "#fff", border: `2px solid ${T.green}`,
            transform: "translateX(-6px)", boxShadow: "0 1px 2px rgba(0,0,0,0.1)",
          }} />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, fontFamily: T.mono, color: T.textLight, marginTop: 3 }}>
          <span>{fmtPrice(s.year_low, s.currency)}</span>
          <span style={{ fontWeight: 600, color: T.text }}>{fmtPrice(s.price, s.currency)}</span>
          <span>{fmtPrice(s.year_high, s.currency)}</span>
        </div>
      </div>

      {/* Indicator Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4 }}>
        {indicators.map((ind, i) => (
          <div key={i} style={{
            display: "flex", justifyContent: "space-between", alignItems: "center",
            padding: "5px 8px", borderRadius: 4, fontSize: 10, fontFamily: T.mono,
            background: ind.bullish ? T.greenLight : "#fafafa",
            border: `1px solid ${ind.bullish ? T.greenBorder : T.divider}`,
          }}>
            <span style={{ color: T.textMuted, fontWeight: 500 }}>{ind.label}</span>
            <span style={{ color: ind.bullish ? T.green : T.textMuted, fontWeight: 600 }}>{ind.value}</span>
          </div>
        ))}
      </div>

      {/* Bull Score Bar */}
      <div style={{ marginTop: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
          <span style={{ fontSize: 10, fontFamily: T.mono, color: T.textMuted }}>Bull Score</span>
          <span style={{ fontSize: 11, fontFamily: T.mono, fontWeight: 700,
            color: s.bull_score >= 7 ? T.green : s.bull_score >= 4 ? T.amber : T.red }}>
            {s.bull_score}/10
          </span>
        </div>
        <div style={{ display: "flex", gap: 3 }}>
          {Array.from({ length: 10 }, (_, i) => {
            const active = i < s.bull_score;
            const color = s.bull_score >= 7 ? T.green : s.bull_score >= 4 ? T.amber : T.red;
            return (
              <div key={i} style={{
                flex: 1, height: 6, borderRadius: 3,
                background: active ? color : T.divider,
                transition: "background 0.3s",
              }} />
            );
          })}
        </div>
      </div>
    </Card>
  );
}

// ── AnalystTrend ────────────────────────────────────────────────────────────────
function AnalystTrend({ symbol }: { symbol: string }) {
  const [points, setPoints] = useState<SignalPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const fetchSignals = async () => {
      const results: SignalPoint[] = [];
      const today = new Date();
      const promises: Promise<void>[] = [];

      for (let i = 0; i < 30; i++) {
        const d = new Date(today);
        d.setDate(d.getDate() - i);
        const dateStr = d.toISOString().split("T")[0];
        promises.push(
          fetch(`${GCS_SIGNALS}/${dateStr}.json`)
            .then(r => r.ok ? r.json() : null)
            .then(data => {
              if (data?.signals) {
                const sig = data.signals.find((s: any) => s.symbol === symbol);
                if (sig) results.push({ date: dateStr, composite: sig.composite, signal: sig.signal, price: sig.price, bull: sig.bull, mos: sig.mos, target: sig.target });
              }
            })
            .catch(() => {})
        );
      }
      await Promise.all(promises);
      results.sort((a, b) => a.date.localeCompare(b.date));
      setPoints(results);
      setLoading(false);
    };
    fetchSignals();
  }, [symbol]);

  // Draw sparkline
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || points.length < 2) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const w = canvas.offsetWidth;
    const h = canvas.offsetHeight;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);

    const composites = points.map(p => p.composite);
    const min = Math.min(...composites) * 0.95;
    const max = Math.max(...composites) * 1.05;
    const range = max - min || 1;

    // Fill gradient
    const gradient = ctx.createLinearGradient(0, 0, 0, h);
    gradient.addColorStop(0, "rgba(45, 122, 79, 0.15)");
    gradient.addColorStop(1, "rgba(45, 122, 79, 0)");

    ctx.beginPath();
    ctx.moveTo(0, h);
    points.forEach((p, i) => {
      const x = (i / (points.length - 1)) * w;
      const y = h - ((p.composite - min) / range) * h;
      if (i === 0) ctx.lineTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.lineTo(w, h);
    ctx.closePath();
    ctx.fillStyle = gradient;
    ctx.fill();

    // Line
    ctx.beginPath();
    points.forEach((p, i) => {
      const x = (i / (points.length - 1)) * w;
      const y = h - ((p.composite - min) / range) * h;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = T.green;
    ctx.lineWidth = 2;
    ctx.lineJoin = "round";
    ctx.stroke();

    // End dot
    const lastX = w;
    const lastY = h - ((composites[composites.length - 1] - min) / range) * h;
    ctx.beginPath();
    ctx.arc(lastX, lastY, 3, 0, Math.PI * 2);
    ctx.fillStyle = T.green;
    ctx.fill();
  }, [points]);

  // Trend label
  const trend = (() => {
    if (points.length < 3) return { label: "Insufficient data", icon: <Minus size={12} />, color: T.textLight };
    const first3 = points.slice(0, 3).reduce((s, p) => s + p.composite, 0) / 3;
    const last3 = points.slice(-3).reduce((s, p) => s + p.composite, 0) / 3;
    const diff = last3 - first3;
    if (diff > 0.03) return { label: "Rising", icon: <TrendingUp size={12} />, color: T.green };
    if (diff < -0.03) return { label: "Falling", icon: <TrendingDown size={12} />, color: T.red };
    return { label: "Stable", icon: <Minus size={12} />, color: T.amber };
  })();

  if (loading) return (
    <Card>
      <SectionHeader title="Signal Trend (30d)" icon={<TrendingUp size={12} />} />
      <div style={{ padding: 20, textAlign: "center", color: T.textLight, fontSize: 11, fontFamily: T.mono }}>
        Loading signal history...
      </div>
    </Card>
  );

  return (
    <Card>
      <SectionHeader title="Signal Trend (30d)" icon={<TrendingUp size={12} />} />
      {points.length < 2 ? (
        <div style={{ padding: 16, textAlign: "center", color: T.textLight, fontSize: 11, fontFamily: T.mono }}>
          Not enough signal history yet. Trend data populates after multiple daily scans.
        </div>
      ) : (
        <>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ color: trend.color }}>{trend.icon}</span>
              <span style={{ fontSize: 12, fontFamily: T.mono, fontWeight: 600, color: trend.color }}>{trend.label}</span>
            </div>
            <span style={{ fontSize: 10, fontFamily: T.mono, color: T.textLight }}>
              {points.length} data points
            </span>
          </div>
          <div style={{ position: "relative", height: 60 }}>
            <canvas ref={canvasRef} style={{ width: "100%", height: "100%", display: "block" }} />
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 8, fontFamily: T.mono, color: T.textLight, marginTop: 4 }}>
            <span>{points[0]?.date.slice(5)}</span>
            <span>{points[points.length - 1]?.date.slice(5)}</span>
          </div>
          {/* Signal changes */}
          {points.length > 1 && (() => {
            const changes: { date: string; from: string; to: string }[] = [];
            for (let i = 1; i < points.length; i++) {
              if (points[i].signal !== points[i - 1].signal) {
                changes.push({ date: points[i].date, from: points[i - 1].signal, to: points[i].signal });
              }
            }
            if (changes.length === 0) return null;
            return (
              <div style={{ marginTop: 8, paddingTop: 8, borderTop: `1px solid ${T.divider}` }}>
                <div style={{ fontSize: 9, fontFamily: T.mono, color: T.textMuted, marginBottom: 4 }}>Signal Changes</div>
                {changes.slice(-3).map((c, i) => (
                  <div key={i} style={{ fontSize: 10, fontFamily: T.mono, display: "flex", alignItems: "center", gap: 4, marginBottom: 2 }}>
                    <span style={{ color: T.textLight }}>{c.date.slice(5)}</span>
                    <span style={{ color: SIG_C[c.from]?.fg || T.textMuted }}>{c.from}</span>
                    <ChevronRight size={10} color={T.textLight} />
                    <span style={{ color: SIG_C[c.to]?.fg || T.textMuted, fontWeight: 600 }}>{c.to}</span>
                  </div>
                ))}
              </div>
            );
          })()}
        </>
      )}
    </Card>
  );
}

// ── TranscriptInsights ─────────────────────────────────────────────────────────
function TranscriptInsights({ symbol }: { symbol: string }) {
  const [analysis, setAnalysis] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchTranscript = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${CLOUD_RUN}/transcript?symbol=${symbol}`);
      if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
      const data = await res.json();
      setAnalysis(data.analysis || data.error || "No analysis returned.");
    } catch (e: any) {
      setError(e.message || "Failed to fetch transcript analysis.");
    } finally {
      setLoading(false);
    }
  }, [symbol]);

  return (
    <Card>
      <SectionHeader title="Transcript Insights" icon={<Brain size={12} />} />
      {analysis ? (
        <div>
          <div style={{ fontSize: 11, lineHeight: 1.7, color: T.text, fontFamily: T.sans, whiteSpace: "pre-wrap" }}>
            {analysis}
          </div>
          <button onClick={fetchTranscript} style={{
            marginTop: 12, background: "none", border: `1px solid ${T.cardBorder}`, borderRadius: 6,
            padding: "6px 12px", cursor: "pointer", fontSize: 10, fontFamily: T.mono,
            color: T.textMuted, display: "flex", alignItems: "center", gap: 4,
          }}>
            <RefreshCw size={10} /> Refresh
          </button>
        </div>
      ) : (
        <div style={{ textAlign: "center", padding: "20px 0" }}>
          <button
            onClick={fetchTranscript}
            disabled={loading}
            style={{
              background: loading ? T.divider : T.green,
              border: "none", borderRadius: 6, padding: "10px 20px",
              color: loading ? T.textMuted : "#fff",
              fontFamily: T.mono, fontSize: 11, fontWeight: 600,
              cursor: loading ? "not-allowed" : "pointer",
              display: "inline-flex", alignItems: "center", gap: 6,
              transition: "all 0.2s",
            }}
          >
            {loading ? (
              <><RefreshCw size={12} style={{ animation: "spin 1s linear infinite" }} /> Analyzing...</>
            ) : (
              <><Brain size={12} /> Analyze Latest Earnings Call</>
            )}
          </button>
          {error && (
            <div style={{ marginTop: 8, fontSize: 10, color: T.red, fontFamily: T.mono }}>{error}</div>
          )}
          <div style={{ fontSize: 9, color: T.textLight, fontFamily: T.mono, marginTop: 8 }}>
            Claude AI analyzes the latest earnings transcript for key themes, guidance, and risks
          </div>
        </div>
      )}
      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </Card>
  );
}

// ── TargetBar ──────────────────────────────────────────────────────────────────
function TargetBar({ price, target, dcf, buffett, currency }: { price: number; target: number; dcf: number; buffett: number; currency?: string }) {
  const values = [price, target, dcf, buffett].filter(v => v > 0);
  if (values.length < 2) return null;
  const min = Math.min(...values) * 0.8;
  const max = Math.max(...values) * 1.1;
  const range = max - min;
  const pos = (v: number) => ((v - min) / range * 100);

  return (
    <div style={{ marginTop: 12, padding: "12px 0" }}>
      <div style={{ fontSize: 10, color: T.textMuted, fontFamily: T.mono, marginBottom: 8, fontWeight: 600 }}>
        PRICE vs INTRINSIC VALUE
      </div>
      <div style={{ position: "relative", height: 36, background: T.divider, borderRadius: 6 }}>
        {dcf > price && (
          <div style={{ position: "absolute", left: `${pos(price)}%`, top: 0, bottom: 0,
            width: `${pos(dcf) - pos(price)}%`, background: `${T.green}12`, borderRadius: 4 }} />
        )}
        <div style={{ position: "absolute", left: `${pos(price)}%`, top: 0, bottom: 0, width: 2, background: T.text, zIndex: 2 }}>
          <div style={{ position: "absolute", top: -16, left: -14, fontSize: 9, color: T.text, fontFamily: T.mono, fontWeight: 600, whiteSpace: "nowrap" }}>
            {fmtPrice(price, currency)}
          </div>
        </div>
        {target > 0 && (
          <div style={{ position: "absolute", left: `${pos(target)}%`, top: 8, width: 8, height: 8, borderRadius: "50%", background: T.amber, transform: "translateX(-4px)" }}>
            <div style={{ position: "absolute", bottom: -14, left: -8, fontSize: 8, color: T.amber, fontFamily: T.mono, whiteSpace: "nowrap" }}>Target</div>
          </div>
        )}
        {dcf > 0 && (
          <div style={{ position: "absolute", left: `${pos(dcf)}%`, top: 18, width: 8, height: 8, borderRadius: "50%", background: T.blue, transform: "translateX(-4px)" }}>
            <div style={{ position: "absolute", bottom: -14, left: -4, fontSize: 8, color: T.blue, fontFamily: T.mono, whiteSpace: "nowrap" }}>DCF</div>
          </div>
        )}
        {buffett > 0 && buffett < max && (
          <div style={{ position: "absolute", left: `${pos(buffett)}%`, top: 13, width: 8, height: 8, borderRadius: 2, background: T.purple, transform: "translateX(-4px)" }}>
            <div style={{ position: "absolute", top: -14, left: -8, fontSize: 8, color: T.purple, fontFamily: T.mono, whiteSpace: "nowrap" }}>Buffett</div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main Page ──────────────────────────────────────────────────────────────────
export default function StockDetail() {
  const params = useParams();
  const router = useRouter();
  const symbol = typeof params?.symbol === "string" ? params.symbol : "";
  const [stock, setStock] = useState<StockData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!symbol) return;
    fetch(`${GCS_SCANS}/latest.json`)
      .then(r => r.json())
      .then(data => {
        const found = data.stocks?.find((s: StockData) => s.symbol === symbol.toUpperCase());
        if (found) { setStock(found); setLoading(false); }
        else { setStock(null); setLoading(false); }
      })
      .catch(() => { setStock(null); setLoading(false); });
  }, [symbol]);

  if (loading) return (
    <div style={{ minHeight: "100vh", background: T.bg, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <span style={{ color: T.textMuted, fontFamily: T.mono, fontSize: 12 }}>Loading {symbol}...</span>
    </div>
  );

  if (!stock) return (
    <div style={{ minHeight: "100vh", background: T.bg, padding: 40 }}>
      <button onClick={() => router.push("/")} style={{ background: "none", border: "none", color: T.green, cursor: "pointer",
        display: "flex", alignItems: "center", gap: 6, fontFamily: T.mono, fontSize: 12, marginBottom: 24, padding: 0 }}>
        <ArrowLeft size={14} /> Back
      </button>
      <div style={{ textAlign: "center", padding: 60, color: T.textMuted, fontFamily: T.mono }}>
        No data found for {symbol}. Run a scan first.
      </div>
    </div>
  );

  const s = stock;
  const sigStyle = SIG_C[s.signal] || SIG_C.HOLD;
  const clsColor = CLS_C[s.classification] || T.textMuted;

  return (
    <div style={{ minHeight: "100vh", background: T.bg, padding: "16px 24px", maxWidth: 1320, margin: "0 auto" }}>
      {/* Back nav */}
      <button onClick={() => router.push("/")} style={{ background: "none", border: "none", color: T.green, cursor: "pointer",
        display: "flex", alignItems: "center", gap: 5, fontFamily: T.mono, fontSize: 11, marginBottom: 16, padding: 0 }}>
        <ArrowLeft size={13} /> SCREENER/v5
      </button>

      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20,
        paddingBottom: 16, borderBottom: `1px solid ${T.divider}` }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
            <h1 style={{ fontSize: 26, fontWeight: 700, color: T.text, fontFamily: T.mono, letterSpacing: "0.02em", margin: 0 }}>{s.symbol}</h1>
            <span style={{ fontSize: 10, padding: "3px 8px", borderRadius: 4, border: `1px solid ${clsColor}30`, color: clsColor,
              fontFamily: T.mono, fontWeight: 600, background: `${clsColor}08` }}>
              {s.classification?.replace("_", " ")}
            </span>
            <span style={{ fontSize: 11, padding: "4px 12px", borderRadius: 4, fontWeight: 700, fontFamily: T.mono, letterSpacing: "0.07em",
              color: sigStyle.fg, background: sigStyle.bg, border: `1px solid ${sigStyle.border}` }}>
              {s.signal}
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
            <span style={{ fontSize: 30, fontWeight: 600, color: T.text, fontFamily: T.mono }}>{fmtPrice(s.price, s.currency)}</span>
            <span style={{ fontSize: 13, color: T.textMuted, fontFamily: T.mono }}>{s.currency}</span>
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 11, color: T.textMuted, fontFamily: T.mono, marginBottom: 4 }}>Composite Score</div>
          <div style={{ fontSize: 34, fontWeight: 700, fontFamily: T.mono,
            color: s.composite > 0.6 ? T.green : s.composite > 0.4 ? T.text : T.red }}>
            {s.composite.toFixed(2)}
          </div>
        </div>
      </div>

      {/* TradingView Chart */}
      <Card style={{ marginBottom: 16, padding: 0, overflow: "hidden" }}>
        <div id="tradingview-widget" style={{ height: 300 }}>
          <iframe
            src={`https://s.tradingview.com/widgetembed/?frameElementId=tradingview_widget&symbol=${s.symbol}&interval=D&hidesidetoolbar=1&symboledit=0&saveimage=0&toolbarbg=f1f3f6&studies=MASimple%409na%40na%40na~50~0~~&studies=MASimple%409na%40na%40na~200~0~~&theme=light&style=1&timezone=exchange&withdateranges=1&width=100%25&height=100%25&utm_source=localhost`}
            style={{ width: "100%", height: "100%", border: "none" }}
            allowFullScreen
          />
        </div>
      </Card>

      {/* 4-column layout */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 14, marginBottom: 16 }}>

        {/* Col 1: Momentum */}
        <MomentumPanel s={s} />

        {/* Col 2: Buffett Value */}
        <Card>
          <SectionHeader title="Buffett Value" />
          <div style={{ display: "flex", justifyContent: "center", gap: 12, margin: "8px 0 12px" }}>
            <ScoreRing value={s.piotroski} label="Piotroski" max={9} color={s.piotroski >= 7 ? T.green : s.piotroski >= 5 ? T.amber : T.red} />
          </div>
          <Metric label="ROE (avg)" value={fmtPct(s.roe_avg)} color={s.roe_avg > 0.15 ? T.green : T.textMuted}
            sub={s.roe_consistent ? "✓ Consistent >15%" : ""} />
          <Metric label="ROIC (avg)" value={fmtPct(s.roic_avg)} color={s.roic_avg > 0.12 ? T.green : T.textMuted} />
          <Metric label="Gross Margin" value={fmtPct(s.gross_margin)} color={s.gross_margin > 0.5 ? T.green : T.textMuted}
            sub={s.gross_margin_trend === "expanding" ? "↑ Expanding" : s.gross_margin_trend === "contracting" ? "↓ Contracting" : "→ Stable"} />
          <Metric label="Rev CAGR 3Y" value={fmtPct(s.revenue_cagr_3y)} color={s.revenue_cagr_3y > 0.1 ? T.green : T.textMuted} />
          <Metric label="EPS CAGR 3Y" value={fmtPct(s.eps_cagr_3y)} color={s.eps_cagr_3y > 0.1 ? T.green : T.textMuted} />
          <Metric label="Altman Z" value={s.altman_z?.toFixed(1)} color={s.altman_z > 3 ? T.green : s.altman_z > 1.8 ? T.amber : T.red}
            sub={s.altman_z > 3 ? "Safe zone" : s.altman_z > 1.8 ? "Grey zone" : "⚠ Distress"} />
          <Metric label="OE Yield" value={fmtPct(s.owner_earnings_yield)}
            color={s.owner_earnings_yield > 0.045 ? T.green : T.textMuted} sub="vs 4.5% risk-free" />
        </Card>

        {/* Col 3: Analyst & Valuation */}
        <Card>
          <SectionHeader title="Analyst & Valuation" />
          {/* EPS beats */}
          <div style={{ margin: "4px 0 10px" }}>
            <div style={{ display: "flex", gap: 3, justifyContent: "center" }}>
              {Array.from({ length: s.eps_total || 1 }, (_, i) => (
                <div key={i} style={{ width: 18, height: 18, borderRadius: 3,
                  background: i < s.eps_beats ? T.greenLight : T.redLight,
                  border: `1px solid ${i < s.eps_beats ? T.greenBorder : "#fecaca"}`,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 9, color: i < s.eps_beats ? T.green : T.red, fontFamily: T.mono }}>
                  {i < s.eps_beats ? "✓" : "✗"}
                </div>
              ))}
            </div>
            <div style={{ textAlign: "center", fontSize: 9, color: T.textMuted, fontFamily: T.mono, marginTop: 4 }}>
              EPS beats: {s.eps_beats}/{s.eps_total}
            </div>
          </div>
          <Metric label="Price Target" value={fmtPrice(s.target, s.currency)}
            sub={s.target > 0 ? `${s.upside > 0 ? "+" : ""}${s.upside.toFixed(1)}% upside` : ""}
            color={s.upside > 20 ? T.green : s.upside > 0 ? T.textMuted : T.red} />
          <Metric label="Buy Grades" value={s.grade_total > 0 ? `${s.grade_buy}/${s.grade_total}` : "—"}
            sub={s.grade_total > 0 ? `${(s.grade_score * 100).toFixed(0)}% bullish` : ""} />
          <Metric label="Margin of Safety" value={fmtPct(s.margin_of_safety)}
            color={s.margin_of_safety > 0.15 ? T.green : s.margin_of_safety > 0 ? "#5a9e7a" : T.red} />
          <Metric label="DCF Value" value={fmtPrice(s.dcf_value, s.currency)} />
          <Metric label="Buffett Value" value={fmtPrice(s.intrinsic_buffett, s.currency)} />
          <Metric label="Value Score" value={s.value_score?.toFixed(2)} color={s.value_score > 0.5 ? T.green : T.textMuted} />
          <TargetBar price={s.price} target={s.target} dcf={s.dcf_value} buffett={s.intrinsic_buffett} currency={s.currency} />
        </Card>

        {/* Col 4: Signal Trend + Transcript */}
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <AnalystTrend symbol={s.symbol} />
          <TranscriptInsights symbol={s.symbol} />
        </div>
      </div>

      {/* Signal reasons */}
      {s.reasons && s.reasons.length > 0 && (
        <Card style={{ marginBottom: 16 }}>
          <SectionHeader title="Active Signals" />
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 4 }}>
            {s.reasons.map((r, i) => (
              <span key={i} style={{ fontSize: 10, padding: "4px 10px", borderRadius: 4, fontFamily: T.mono,
                background: r.includes("⚠") ? T.redLight : T.greenLight,
                border: `1px solid ${r.includes("⚠") ? "#fecaca" : T.greenBorder}`,
                color: r.includes("⚠") ? T.red : T.textMuted }}>
                {r}
              </span>
            ))}
          </div>
        </Card>
      )}

      {/* Performance tracker */}
      <Card style={{ marginBottom: 16 }}>
        <SectionHeader title="Performance Since Signal" />
        <div style={{ textAlign: "center", padding: 20, color: T.textLight, fontFamily: T.mono, fontSize: 11 }}>
          Performance tracking populates after signal history accumulates.
          <br />First signal: {new Date().toLocaleDateString("en-GB")} at {fmtPrice(s.price, s.currency)}
        </div>
      </Card>
    </div>
  );
}
