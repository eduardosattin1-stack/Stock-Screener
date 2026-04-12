"use client";
import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, TrendingUp, TrendingDown, AlertTriangle, ExternalLink, BarChart3, Loader2 } from "lucide-react";

const GCS_BASE = "https://storage.googleapis.com/screener-signals-carbonbridge/scans";
const FMP_PROXY = "/api/fmp"; // Next.js API route proxies to FMP with key

// ─── Types ───────────────────────────────────────────────────────────
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

interface GrowthData {
  revenueGrowth: number;
  operatingIncomeGrowth: number;
  epsdilutedGrowth: number;
  dividendsPerShareGrowth: number;
  freeCashFlowGrowth: number;
  bookValueperShareGrowth: number;
  threeYRevenueGrowthPerShare: number;
  fiveYRevenueGrowthPerShare: number;
  tenYRevenueGrowthPerShare: number;
  threeYNetIncomeGrowthPerShare: number;
  fiveYNetIncomeGrowthPerShare: number;
  tenYNetIncomeGrowthPerShare: number;
  threeYOperatingCFGrowthPerShare: number;
  fiveYOperatingCFGrowthPerShare: number;
  tenYOperatingCFGrowthPerShare: number;
  threeYShareholdersEquityGrowthPerShare: number;
  fiveYShareholdersEquityGrowthPerShare: number;
  tenYShareholdersEquityGrowthPerShare: number;
  threeYDividendperShareGrowthPerShare: number;
  fiveYDividendperShareGrowthPerShare: number;
  tenYDividendperShareGrowthPerShare: number;
}

interface RatioYear {
  date: string;
  fiscalYear: string;
  grossProfitMargin: number;
  operatingProfitMargin: number;
  netProfitMargin: number;
  returnOnEquity: number;
  returnOnAssets: number;
  returnOnCapitalEmployed: number;
  freeCashFlowOperatingCashFlowRatio: number;
  currentRatio: number;
  debtToEquityRatio: number;
  interestCoverageRatio: number;
  dividendPayoutRatio: number;
  revenuePerShare: number;
  netIncomePerShare: number;
  bookValuePerShare: number;
  freeCashFlowPerShare: number;
  operatingCashFlowPerShare: number;
  dividendPerShare: number;
  // valuation
  priceToEarningsRatio: number;
  priceToSalesRatio: number;
  priceToBookRatio: number;
  priceToFreeCashFlowRatio: number;
  priceToOperatingCashFlowRatio: number;
  priceToEarningsGrowthRatio: number;
  dividendYieldPercentage: number;
}

// ─── Constants ───────────────────────────────────────────────────────
const SIG_C: Record<string, string> = { BUY: "#2dd4a0", WATCH: "#e5a944", HOLD: "#7d8494", SELL: "#e5534b" };
const CLS_C: Record<string, string> = { DEEP_VALUE: "#3bc9db", VALUE: "#3bc9db", QUALITY_GROWTH: "#9775fa", GROWTH: "#9775fa", SPECULATIVE: "#e5534b", NEUTRAL: "#4a5060" };

// ─── Formatters ──────────────────────────────────────────────────────
const fmtPct = (n: number | null | undefined) => n == null ? "—" : `${(n * 100).toFixed(1)}%`;
const fmtUsd = (n: number | null | undefined) => n == null || n === 0 ? "—" : `$${n.toFixed(0)}`;
const fmtNum = (n: number | null | undefined, d = 1) => n == null ? "—" : n.toFixed(d);

/** Annualize a cumulative growth: (1+total)^(1/years) - 1 */
const annualize = (total: number | undefined, years: number): number | null => {
  if (total == null || total <= -1) return null;
  return Math.pow(1 + total, 1 / years) - 1;
};

const growthColor = (v: number | null) => {
  if (v == null) return "#4a5060";
  if (v > 0.15) return "#2dd4a0";
  if (v > 0.05) return "#5a9e7a";
  if (v > 0) return "#7d8494";
  return "#e5534b";
};

// ─── Shared Components ───────────────────────────────────────────────
function Metric({ label, value, color, sub }: { label: string; value: string; color?: string; sub?: string }) {
  return (
    <div style={{ padding: "8px 0", borderBottom: "1px solid var(--border-subtle)" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <span style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontWeight: 500 }}>{label}</span>
        <span style={{ fontSize: 12, color: color || "var(--text-primary)", fontFamily: "var(--font-mono)", fontWeight: 600 }}>{value}</span>
      </div>
      {sub && <div style={{ fontSize: 9, color: "#3a4050", marginTop: 2, fontFamily: "var(--font-mono)" }}>{sub}</div>}
    </div>
  );
}

function SectionHeader({ title, sub }: { title: string; sub?: string }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8, paddingBottom: 6, borderBottom: "1px solid var(--border)" }}>
      <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: "0.1em", color: "var(--text-muted)", fontFamily: "var(--font-mono)", textTransform: "uppercase" }}>
        {title}
      </div>
      {sub && <div style={{ fontSize: 9, color: "#3a4050", fontFamily: "var(--font-mono)" }}>{sub}</div>}
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
        <circle cx="34" cy="34" r={radius} fill="none" stroke="var(--bg-hover)" strokeWidth="4" />
        <circle cx="34" cy="34" r={radius} fill="none" stroke={color} strokeWidth="4"
          strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
          transform="rotate(-90 34 34)" style={{ transition: "stroke-dashoffset 0.5s" }} />
        <text x="34" y="32" textAnchor="middle" fill={color} fontSize="13" fontFamily="var(--font-mono)" fontWeight="600">{value}</text>
        <text x="34" y="44" textAnchor="middle" fill="var(--text-muted)" fontSize="8" fontFamily="var(--font-mono)">/{max}</text>
      </svg>
      <div style={{ fontSize: 9, color: "var(--text-muted)", fontFamily: "var(--font-mono)", marginTop: 2 }}>{label}</div>
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
      <div style={{ fontSize: 10, color: "var(--text-muted)", fontFamily: "var(--font-mono)", marginBottom: 8, fontWeight: 600, letterSpacing: "0.08em" }}>
        PRICE vs INTRINSIC VALUE
      </div>
      <div style={{ position: "relative", height: 40, background: "var(--bg-surface)", borderRadius: 4, border: "1px solid var(--border-subtle)" }}>
        <div style={{ position: "absolute", left: `${pos(price)}%`, top: 0, bottom: 0, width: 2, background: "var(--text-primary)", zIndex: 2 }}>
          <div style={{ position: "absolute", top: -16, left: -12, fontSize: 9, color: "var(--text-primary)", fontFamily: "var(--font-mono)", whiteSpace: "nowrap" }}>${price.toFixed(0)}</div>
        </div>
        {target > 0 && (
          <div style={{ position: "absolute", left: `${pos(target)}%`, top: 8, width: 8, height: 8, borderRadius: "50%", background: "var(--accent-amber)", border: "2px solid var(--bg-surface)", transform: "translateX(-4px)" }}>
            <div style={{ position: "absolute", bottom: -14, left: -8, fontSize: 8, color: "var(--accent-amber)", fontFamily: "var(--font-mono)", whiteSpace: "nowrap" }}>Target</div>
          </div>
        )}
        {dcf > 0 && (
          <div style={{ position: "absolute", left: `${pos(dcf)}%`, top: 20, width: 8, height: 8, borderRadius: "50%", background: "var(--accent-cyan)", border: "2px solid var(--bg-surface)", transform: "translateX(-4px)" }}>
            <div style={{ position: "absolute", bottom: -14, left: -4, fontSize: 8, color: "var(--accent-cyan)", fontFamily: "var(--font-mono)", whiteSpace: "nowrap" }}>DCF</div>
          </div>
        )}
        {buffett > 0 && buffett < max && (
          <div style={{ position: "absolute", left: `${pos(buffett)}%`, top: 14, width: 8, height: 8, borderRadius: 2, background: "var(--accent-purple)", border: "2px solid var(--bg-surface)", transform: "translateX(-4px)" }}>
            <div style={{ position: "absolute", top: -14, left: -8, fontSize: 8, color: "var(--accent-purple)", fontFamily: "var(--font-mono)", whiteSpace: "nowrap" }}>Buffett</div>
          </div>
        )}
        {dcf > price && (
          <div style={{ position: "absolute", left: `${pos(price)}%`, top: 0, bottom: 0, width: `${pos(dcf) - pos(price)}%`, background: "#2dd4a010" }} />
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
        <div key={i} style={{ width: 10, height: 10, borderRadius: "50%", background: i < score ? c : "var(--bg-hover)", border: "1px solid var(--border)" }} />
      ))}
    </div>
  );
}

// ─── Growth Rates Table ──────────────────────────────────────────────
function GrowthCell({ value }: { value: number | null }) {
  if (value == null) return <td style={cellStyle}>—</td>;
  const pct = (value * 100).toFixed(1);
  return <td style={{ ...cellStyle, color: growthColor(value), fontWeight: 600 }}>{pct}%</td>;
}

const cellStyle: React.CSSProperties = {
  padding: "6px 10px", textAlign: "right", fontSize: 11, fontFamily: "var(--font-mono)",
  borderBottom: "1px solid var(--border-subtle)", whiteSpace: "nowrap",
};
const headerCellStyle: React.CSSProperties = {
  ...cellStyle, color: "var(--text-muted)", fontWeight: 500, fontSize: 10, letterSpacing: "0.05em",
};
const labelCellStyle: React.CSSProperties = {
  ...cellStyle, textAlign: "left", color: "var(--text-secondary)", fontWeight: 500,
};

function GrowthRatesPanel({ data, loading }: { data: GrowthData | null; loading: boolean }) {
  if (loading) return <PanelLoader label="Growth Rates" />;
  if (!data) return <PanelEmpty label="Growth Rates" />;

  const rows: { label: string; y1: number | null; y3: number | null; y5: number | null; y10: number | null }[] = [
    {
      label: "Revenue",
      y1: data.revenueGrowth,
      y3: annualize(data.threeYRevenueGrowthPerShare, 3),
      y5: annualize(data.fiveYRevenueGrowthPerShare, 5),
      y10: annualize(data.tenYRevenueGrowthPerShare, 10),
    },
    {
      label: "Operating Income",
      y1: data.operatingIncomeGrowth,
      y3: null, y5: null, y10: null, // FMP doesn't have compound OpInc
    },
    {
      label: "EPS (diluted)",
      y1: data.epsdilutedGrowth,
      y3: annualize(data.threeYNetIncomeGrowthPerShare, 3),
      y5: annualize(data.fiveYNetIncomeGrowthPerShare, 5),
      y10: annualize(data.tenYNetIncomeGrowthPerShare, 10),
    },
    {
      label: "Dividends/Share",
      y1: data.dividendsPerShareGrowth,
      y3: annualize(data.threeYDividendperShareGrowthPerShare, 3),
      y5: annualize(data.fiveYDividendperShareGrowthPerShare, 5),
      y10: annualize(data.tenYDividendperShareGrowthPerShare, 10),
    },
    {
      label: "Book Value/Share",
      y1: data.bookValueperShareGrowth,
      y3: annualize(data.threeYShareholdersEquityGrowthPerShare, 3),
      y5: annualize(data.fiveYShareholdersEquityGrowthPerShare, 5),
      y10: annualize(data.tenYShareholdersEquityGrowthPerShare, 10),
    },
    {
      label: "Operating Cash Flow",
      y1: null, // not a direct field
      y3: annualize(data.threeYOperatingCFGrowthPerShare, 3),
      y5: annualize(data.fiveYOperatingCFGrowthPerShare, 5),
      y10: annualize(data.tenYOperatingCFGrowthPerShare, 10),
    },
    {
      label: "Free Cash Flow",
      y1: data.freeCashFlowGrowth,
      y3: null, y5: null, y10: null,
    },
  ];

  return (
    <div style={panelStyle}>
      <SectionHeader title="Growth Rates" sub="Compound Annual" />
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={{ ...headerCellStyle, textAlign: "left" }}>Metric</th>
              <th style={headerCellStyle}>1 Yr</th>
              <th style={headerCellStyle}>3 Yr</th>
              <th style={headerCellStyle}>5 Yr</th>
              <th style={headerCellStyle}>10 Yr</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.label}>
                <td style={labelCellStyle}>{r.label}</td>
                <GrowthCell value={r.y1} />
                <GrowthCell value={r.y3} />
                <GrowthCell value={r.y5} />
                <GrowthCell value={r.y10} />
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── Profitability Panel ─────────────────────────────────────────────
function ProfitabilityPanel({ ratios, loading }: { ratios: RatioYear[]; loading: boolean }) {
  if (loading) return <PanelLoader label="Profitability" />;
  if (!ratios.length) return <PanelEmpty label="Profitability" />;

  const current = ratios[0]; // most recent
  const avg5 = (field: keyof RatioYear) => {
    const vals = ratios.slice(0, 5).map(r => r[field] as number).filter(v => v != null && isFinite(v));
    return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
  };

  const metrics: { label: string; field: keyof RatioYear; threshold?: number }[] = [
    { label: "Return on Equity", field: "returnOnEquity", threshold: 0.15 },
    { label: "Return on Assets", field: "returnOnAssets", threshold: 0.08 },
    { label: "Return on Capital", field: "returnOnCapitalEmployed", threshold: 0.12 },
    { label: "Gross Margin", field: "grossProfitMargin", threshold: 0.40 },
    { label: "Operating Margin", field: "operatingProfitMargin", threshold: 0.15 },
    { label: "Net Margin", field: "netProfitMargin", threshold: 0.10 },
    { label: "FCF / Oper. CF", field: "freeCashFlowOperatingCashFlowRatio" },
    { label: "Current Ratio", field: "currentRatio" },
    { label: "Debt / Equity", field: "debtToEquityRatio" },
    { label: "Interest Coverage", field: "interestCoverageRatio" },
    { label: "Dividend Payout", field: "dividendPayoutRatio" },
  ];

  return (
    <div style={panelStyle}>
      <SectionHeader title="Profitability" sub={`FY ${current.fiscalYear}`} />
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={{ ...headerCellStyle, textAlign: "left" }}>Metric</th>
            <th style={headerCellStyle}>Current</th>
            <th style={headerCellStyle}>5Y Avg</th>
          </tr>
        </thead>
        <tbody>
          {metrics.map(({ label, field, threshold }) => {
            const cur = current[field] as number;
            const a5 = avg5(field);
            const isRatio = !label.includes("Margin") && !label.includes("Return") && !label.includes("Payout") && !label.includes("FCF");
            const fmt = (v: number | null) => {
              if (v == null || !isFinite(v)) return "—";
              if (isRatio) return v.toFixed(2);
              return (v * 100).toFixed(1) + "%";
            };
            const clr = (v: number | null) => {
              if (v == null || threshold == null) return "var(--text-primary)";
              return v >= threshold ? "var(--accent-green)" : "var(--text-secondary)";
            };
            return (
              <tr key={label}>
                <td style={labelCellStyle}>{label}</td>
                <td style={{ ...cellStyle, color: clr(cur), fontWeight: 600 }}>{fmt(cur)}</td>
                <td style={{ ...cellStyle, color: "var(--text-secondary)" }}>{fmt(a5)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ─── Valuation History Panel ─────────────────────────────────────────
function ValuationPanel({ ratios, loading }: { ratios: RatioYear[]; loading: boolean }) {
  if (loading) return <PanelLoader label="Valuation History" />;
  if (!ratios.length) return <PanelEmpty label="Valuation History" />;

  // Show up to 10 years, most recent first → reverse for left-to-right chronological
  const years = [...ratios].reverse();

  const metrics: { label: string; field: keyof RatioYear; decimals?: number }[] = [
    { label: "P/E", field: "priceToEarningsRatio", decimals: 1 },
    { label: "P/S", field: "priceToSalesRatio", decimals: 1 },
    { label: "P/B", field: "priceToBookRatio", decimals: 1 },
    { label: "P/CF", field: "priceToOperatingCashFlowRatio", decimals: 1 },
    { label: "P/FCF", field: "priceToFreeCashFlowRatio", decimals: 1 },
    { label: "Div Yield %", field: "dividendYieldPercentage", decimals: 2 },
  ];

  return (
    <div style={panelStyle}>
      <SectionHeader title="Valuation History" sub="Annual" />
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={{ ...headerCellStyle, textAlign: "left", position: "sticky", left: 0, background: "var(--bg-surface)", zIndex: 1 }}>Metric</th>
              {years.map(y => (
                <th key={y.fiscalYear} style={headerCellStyle}>{y.fiscalYear}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {metrics.map(({ label, field, decimals }) => (
              <tr key={label}>
                <td style={{ ...labelCellStyle, position: "sticky", left: 0, background: "var(--bg-surface)", zIndex: 1 }}>{label}</td>
                {years.map(y => {
                  const v = y[field] as number;
                  const s = v != null && isFinite(v) && v > 0 ? v.toFixed(decimals ?? 1) : "—";
                  return <td key={y.fiscalYear} style={{ ...cellStyle, color: "var(--text-primary)" }}>{s}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── Per-Share Data Panel ────────────────────────────────────────────
function PerSharePanel({ ratios, loading }: { ratios: RatioYear[]; loading: boolean }) {
  if (loading) return <PanelLoader label="Per Share Data" />;
  if (!ratios.length) return <PanelEmpty label="Per Share Data" />;

  const years = [...ratios].reverse();

  const metrics: { label: string; field: keyof RatioYear }[] = [
    { label: "Revenue / Share", field: "revenuePerShare" },
    { label: "EPS", field: "netIncomePerShare" },
    { label: "Book Value / Share", field: "bookValuePerShare" },
    { label: "Oper. CF / Share", field: "operatingCashFlowPerShare" },
    { label: "FCF / Share", field: "freeCashFlowPerShare" },
    { label: "Dividends / Share", field: "dividendPerShare" },
  ];

  return (
    <div style={panelStyle}>
      <SectionHeader title="Per Share Data" sub="Annual" />
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={{ ...headerCellStyle, textAlign: "left", position: "sticky", left: 0, background: "var(--bg-surface)", zIndex: 1 }}>Metric</th>
              {years.map(y => (
                <th key={y.fiscalYear} style={headerCellStyle}>{y.fiscalYear}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {metrics.map(({ label, field }) => (
              <tr key={label}>
                <td style={{ ...labelCellStyle, position: "sticky", left: 0, background: "var(--bg-surface)", zIndex: 1 }}>{label}</td>
                {years.map(y => {
                  const v = y[field] as number;
                  const s = v != null && isFinite(v) ? v.toFixed(2) : "—";
                  return <td key={y.fiscalYear} style={cellStyle}>{s}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─── Helpers ─────────────────────────────────────────────────────────
const panelStyle: React.CSSProperties = {
  background: "var(--bg-surface)", borderRadius: 5, border: "1px solid var(--border-subtle)", padding: "14px 16px", marginBottom: 16,
};

function PanelLoader({ label }: { label: string }) {
  return (
    <div style={panelStyle}>
      <SectionHeader title={label} />
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, padding: 24, color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: 11 }}>
        <Loader2 size={14} style={{ animation: "spin 1s linear infinite" }} />
        Fetching from FMP...
      </div>
      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

function PanelEmpty({ label }: { label: string }) {
  return (
    <div style={panelStyle}>
      <SectionHeader title={label} />
      <div style={{ textAlign: "center", padding: 24, color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: 11 }}>
        No data available
      </div>
    </div>
  );
}

// ─── FMP Fetch Helper ────────────────────────────────────────────────
async function fmpFetch(endpoint: string, params: Record<string, string | number>) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => qs.set(k, String(v)));
  try {
    const res = await fetch(`${FMP_PROXY}/${endpoint}?${qs.toString()}`);
    if (!res.ok) return null;
    const data = await res.json();
    return Array.isArray(data) ? data : data ? [data] : null;
  } catch {
    return null;
  }
}

// ─── Main Component ──────────────────────────────────────────────────
export default function StockDetail() {
  const params = useParams();
  const router = useRouter();
  const symbol = typeof params?.symbol === "string" ? params.symbol : "";
  const [stock, setStock] = useState<StockData | null>(null);
  const [loading, setLoading] = useState(true);

  // FMP live data
  const [growthData, setGrowthData] = useState<GrowthData | null>(null);
  const [ratios, setRatios] = useState<RatioYear[]>([]);
  const [fmpLoading, setFmpLoading] = useState(true);

  // Load scan data from GCS
  useEffect(() => {
    if (!symbol) return;
    fetch(`${GCS_BASE}/latest.json`)
      .then(r => r.json())
      .then(data => {
        const found = data.stocks?.find((s: StockData) => s.symbol === symbol.toUpperCase());
        if (found) { setStock(found); setLoading(false); }
        else { setStock(null); setLoading(false); }
      })
      .catch(() => { setStock(null); setLoading(false); });
  }, [symbol]);

  // Fetch live FMP data
  useEffect(() => {
    if (!symbol) return;
    setFmpLoading(true);
    const sym = symbol.toUpperCase();

    Promise.all([
      fmpFetch("financial-statement-growth", { symbol: sym, limit: 1 }),
      fmpFetch("metrics-ratios", { symbol: sym, period: "annual", limit: 10 }),
    ]).then(([growthRes, ratiosRes]) => {
      if (growthRes && growthRes.length) setGrowthData(growthRes[0] as GrowthData);
      if (ratiosRes && ratiosRes.length) setRatios(ratiosRes as RatioYear[]);
      setFmpLoading(false);
    }).catch(() => setFmpLoading(false));
  }, [symbol]);

  if (loading) return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <span style={{ color: "var(--text-muted)", fontFamily: "var(--font-mono)", fontSize: 12 }}>Loading {symbol}...</span>
    </div>
  );

  if (!stock) return (
    <div style={{ minHeight: "100vh", padding: 40 }}>
      <button onClick={() => router.push("/")} style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer", display: "flex", alignItems: "center", gap: 6, fontFamily: "var(--font-mono)", fontSize: 12, marginBottom: 24 }}>
        <ArrowLeft size={14} /> Back
      </button>
      <div style={{ textAlign: "center", padding: 60, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
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
      <button onClick={() => router.push("/")} style={{ background: "none", border: "none", color: "var(--text-muted)", cursor: "pointer",
        display: "flex", alignItems: "center", gap: 5, fontFamily: "var(--font-mono)", fontSize: 11, marginBottom: 16, padding: 0 }}>
        <ArrowLeft size={13} /> SCREENER/v5
      </button>

      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20, paddingBottom: 16, borderBottom: "1px solid var(--border)" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
            <h1 style={{ fontSize: 24, fontWeight: 700, color: "var(--text-bright)", fontFamily: "var(--font-mono)", letterSpacing: "0.02em", margin: 0 }}>{s.symbol}</h1>
            <span style={{ fontSize: 10, padding: "3px 8px", borderRadius: 3, border: `1px solid ${clsColor}30`, color: clsColor,
              fontFamily: "var(--font-mono)", fontWeight: 600 }}>{s.classification?.replace("_", " ")}</span>
            <span style={{ fontSize: 11, padding: "3px 10px", borderRadius: 3, fontWeight: 700, fontFamily: "var(--font-mono)", letterSpacing: "0.07em",
              color: sigColor, background: `${sigColor}12`, border: `1px solid ${sigColor}25` }}>{s.signal}</span>
          </div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
            <span style={{ fontSize: 28, fontWeight: 600, color: "var(--text-bright)", fontFamily: "var(--font-mono)" }}>${s.price.toFixed(2)}</span>
            <span style={{ fontSize: 13, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>{s.currency}</span>
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-mono)", marginBottom: 4 }}>Composite Score</div>
          <div style={{ fontSize: 32, fontWeight: 700, fontFamily: "var(--font-mono)",
            color: s.composite > 0.6 ? "#2dd4a0" : s.composite > 0.4 ? "var(--text-primary)" : "#e5534b" }}>
            {s.composite.toFixed(2)}
          </div>
        </div>
      </div>

      {/* Chart placeholder */}
      <div style={{ background: "var(--bg-surface)", borderRadius: 5, border: "1px solid var(--border-subtle)", padding: 20, marginBottom: 16, minHeight: 200, display: "flex", alignItems: "center", justifyContent: "center" }}>
        <div style={{ textAlign: "center" }}>
          <BarChart3 size={32} color="var(--border)" />
          <div style={{ fontSize: 11, color: "#2a3040", fontFamily: "var(--font-mono)", marginTop: 8 }}>
            TradingView chart — integrate with charting library
          </div>
          <div style={{ fontSize: 10, color: "var(--border)", fontFamily: "var(--font-mono)", marginTop: 2 }}>
            SMA50: {s.sma50.toFixed(0)} · SMA200: {s.sma200.toFixed(0)} · 52wk: {s.year_low.toFixed(0)}–{s.year_high.toFixed(0)}
          </div>
        </div>
      </div>

      {/* 3-column layout: Technicals / Buffett / Analyst */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16, marginBottom: 16 }}>
        {/* Technical */}
        <div style={panelStyle}>
          <SectionHeader title="Technicals" />
          <div style={{ display: "flex", justifyContent: "center", gap: 16, margin: "12px 0" }}>
            <ScoreRing value={s.bull_score} label="Bull" max={10} color={s.bull_score >= 7 ? "#2dd4a0" : s.bull_score >= 4 ? "#e5a944" : "#e5534b"} />
            <ScoreRing value={Math.round(s.rsi)} label="RSI" max={100} color={s.rsi > 70 ? "#e5534b" : s.rsi < 30 ? "#2dd4a0" : "#7d8494"} />
            <ScoreRing value={Math.round(s.adx)} label="ADX" max={60} color={s.adx > 25 ? "#e5a944" : "#4a5060"} />
          </div>
          <Metric label="MACD" value={s.macd_signal} color={s.macd_signal.includes("bullish") ? "#2dd4a0" : "#e5534b"} />
          <Metric label="Bollinger %B" value={s.bb_pct.toFixed(2)} />
          <Metric label="Stoch RSI" value={s.stoch_rsi.toFixed(0)} />
          <Metric label="OBV Trend" value={s.obv_trend} color={s.obv_trend === "rising" ? "#2dd4a0" : s.obv_trend === "falling" ? "#e5534b" : "#7d8494"} />
          <div style={{ marginTop: 8 }}>
            <div style={{ fontSize: 9, color: "#3a4050", fontFamily: "var(--font-mono)", marginBottom: 4 }}>MOMENTUM</div>
            <BullDots score={s.bull_score} />
          </div>
        </div>

        {/* Buffett Value */}
        <div style={panelStyle}>
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
          <Metric label="Altman Z" value={s.altman_z.toFixed(1)} color={s.altman_z > 3 ? "#2dd4a0" : s.altman_z > 1.8 ? "#e5a944" : "#e5534b"}
            sub={s.altman_z > 3 ? "Safe zone" : s.altman_z > 1.8 ? "Grey zone" : "⚠ Distress zone"} />
          <Metric label="OE Yield" value={fmtPct(s.owner_earnings_yield)}
            color={s.owner_earnings_yield > 0.045 ? "#2dd4a0" : "#7d8494"} sub="vs 4.5% risk-free" />
        </div>

        {/* Analyst + Valuation */}
        <div style={panelStyle}>
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
            <div style={{ textAlign: "center", fontSize: 9, color: "var(--text-muted)", fontFamily: "var(--font-mono)", marginTop: 4 }}>
              EPS beats: {s.eps_beats}/{s.eps_total}
            </div>
          </div>
          <Metric label="Price Target" value={fmtUsd(s.target)} sub={s.target > 0 ? `${s.upside > 0 ? "+" : ""}${s.upside.toFixed(1)}% upside` : ""}
            color={s.upside > 20 ? "#2dd4a0" : s.upside > 0 ? "#7d8494" : "#e5534b"} />
          <Metric label="Buy Grades" value={s.grade_total > 0 ? `${s.grade_buy}/${s.grade_total}` : "—"}
            sub={s.grade_total > 0 ? `${(s.grade_score * 100).toFixed(0)}% bullish` : ""} />
          <Metric label="Margin of Safety" value={fmtPct(s.margin_of_safety)}
            color={s.margin_of_safety > 0.15 ? "#2dd4a0" : s.margin_of_safety > 0 ? "#5a9e7a" : "#e5534b"} />
          <Metric label="DCF Value" value={fmtUsd(s.dcf_value)} />
          <Metric label="Buffett Value" value={fmtUsd(s.intrinsic_buffett)} />
          <Metric label="Value Score" value={s.value_score.toFixed(2)} color={s.value_score > 0.5 ? "#2dd4a0" : "#7d8494"} />
          <TargetBar price={s.price} target={s.target} dcf={s.dcf_value} buffett={s.intrinsic_buffett} />
        </div>
      </div>

      {/* ═══════════════════════════════════════════════════════════════
          NEW: Growth + Profitability + Valuation panels from FMP
          ═══════════════════════════════════════════════════════════════ */}

      {/* Growth Rates — full width */}
      <GrowthRatesPanel data={growthData} loading={fmpLoading} />

      {/* Profitability + Valuation — 2-column */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16, marginBottom: 16 }}>
        <ProfitabilityPanel ratios={ratios} loading={fmpLoading} />
        <ValuationPanel ratios={ratios} loading={fmpLoading} />
      </div>

      {/* Per Share Data — full width */}
      <PerSharePanel ratios={ratios} loading={fmpLoading} />

      {/* Signal reasons */}
      {s.reasons && s.reasons.length > 0 && (
        <div style={panelStyle}>
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

      {/* Transcript placeholder */}
      <div style={panelStyle}>
        <SectionHeader title="Transcript Insights" />
        <div style={{ textAlign: "center", padding: 24 }}>
          <button style={{ background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 4, padding: "8px 16px",
            color: "var(--text-secondary)", fontFamily: "var(--font-mono)", fontSize: 11, cursor: "pointer" }}>
            Analyze Latest Earnings Call
          </button>
          <div style={{ fontSize: 9, color: "#2a3040", fontFamily: "var(--font-mono)", marginTop: 6 }}>
            Requires ANTHROPIC_API_KEY — Claude will summarize the latest transcript
          </div>
        </div>
      </div>
    </div>
  );
}
