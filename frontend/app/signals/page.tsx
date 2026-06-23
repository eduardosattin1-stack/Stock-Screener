"use client";
import { useState, useEffect, useMemo, Fragment } from "react";
import { useRouter } from "next/navigation";
import { Target, TrendingUp, AlertTriangle, ShieldCheck, ChevronRight, ChevronDown, ExternalLink } from "lucide-react";

// Reads the SAME nightly scan the Discover page reads (gs://.../scans/latest_global.json,
// regenerated every night). Surfaces the six ML outputs already on every scored record:
//   hit_prob_10pct_30d / _60d  → P(+10%) at 30d / 60d
//   hit_prob_30d / hit_prob_60d → P(+20%) at 30d / 60d
//   expected_dd_30d / _60d     → expected max drawdown
//
// DATA-QUALITY GATE (UI proxy): the model was trained on fundamentals + options features,
// so a probability is only trustworthy when those inputs are REAL (not median-imputed).
// Here we show only names carrying real options data (options_iv_current) + fundamentals.
// The strict per-feature no-imputation guarantee will be enforced in the backend scan;
// GCS keeps the full set (incl. incomplete names) for model fine-tuning.
const GCS_BASE = "/api/gcs/scans";

const T = {
  bg: "var(--bg)",
  surface: "var(--bg-surface)",
  elevated: "var(--bg-elevated)",
  hover: "var(--bg-hover)",
  border: "var(--border)",
  text: "var(--text)",
  muted: "var(--text-muted)",
  light: "var(--text-light)",
  green: "#14b87a",
  amber: "#f5b942",
  red: "#ef5a5a",
  purple: "#c4b5fd",
  mono: "var(--font-mono)",
};

interface MLStock {
  symbol: string;
  company_name?: string;
  sector?: string;
  country?: string;
  price: number;
  currency: string;
  composite?: number;
  hit_prob?: number;
  hit_prob_10pct_30d?: number;
  hit_prob_10pct_60d?: number;
  hit_prob_30d?: number;
  hit_prob_60d?: number;
  expected_dd_30d?: number;
  expected_dd_60d?: number;
  options_iv_current?: number | null;
  options_iv_rank?: number | null;
  // fundamentals (presence used by the quality gate)
  pe?: number | null;
  roe_avg?: number | null;
  net_margin?: number | null;
}

interface ScanData {
  scan_date: string;
  region: string;
  stock_count?: number;
  stocks: MLStock[];
}

// The "focused" probability = which of the four the list is ranked by.
const probOf = (s: MLStock, tgt: 10 | 20, hz: 30 | 60): number => {
  if (tgt === 10) return (hz === 30 ? s.hit_prob_10pct_30d : s.hit_prob_10pct_60d) ?? 0;
  return (hz === 30 ? s.hit_prob_30d : s.hit_prob_60d) ?? 0;
};
const ddOf = (s: MLStock, hz: 30 | 60): number | undefined => (hz === 30 ? s.expected_dd_30d : s.expected_dd_60d);

const isScored = (s: MLStock) =>
  (s.hit_prob_10pct_30d ?? 0) > 0 || (s.hit_prob_10pct_60d ?? 0) > 0 ||
  (s.hit_prob_30d ?? 0) > 0 || (s.hit_prob_60d ?? 0) > 0;
const hasOptions = (s: MLStock) => s.options_iv_current != null;
const hasFundamentals = (s: MLStock) => s.pe != null || s.roe_avg != null || s.net_margin != null;
// UI proxy for "passed strict data-quality check": real options + fundamentals present.
const qualifies = (s: MLStock) => isScored(s) && hasOptions(s) && hasFundamentals(s);

const CURRENCY_SYMBOL: Record<string, string> = {
  USD: "$", EUR: "€", GBP: "£", JPY: "¥", CHF: "CHF ", CAD: "C$", AUD: "A$",
  HKD: "HK$", CNY: "¥", SEK: "kr ", NOK: "kr ", DKK: "kr ", SGD: "S$",
  KRW: "₩", INR: "₹", BRL: "R$", MXN: "$", TWD: "NT$",
};
const fmtPrice = (n: number | null | undefined, c?: string) => {
  if (n == null || n === 0) return "—";
  const sym = CURRENCY_SYMBOL[c ?? ""] ?? "$";
  return n >= 1000
    ? `${sym}${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
    : `${sym}${n.toFixed(2)}`;
};
const pct0 = (p: number | null | undefined) => (p == null ? "—" : `${(p * 100).toFixed(0)}%`);

// Eyeballed magnitude bands — p(10) runs much higher than p(20), so separate thresholds.
function probColor(p: number | null | undefined, tgt: 10 | 20): string {
  if (p == null || p <= 0) return T.light;
  if (tgt === 10) return p >= 0.45 ? T.green : p >= 0.30 ? T.amber : T.muted;
  return p >= 0.15 ? T.green : p >= 0.08 ? T.amber : T.muted;
}
function ddColor(dd: number | null | undefined): string {
  if (dd == null || dd === 0) return T.light;
  return dd <= -12 ? T.red : dd <= -8 ? T.amber : T.muted;
}
function ivrColor(ivr: number | null | undefined): string {
  if (ivr == null) return T.light;
  return ivr <= 30 ? T.green : ivr <= 60 ? T.amber : T.red;
}

// ── Module-scope presentational components (must not be declared during render) ──
function Toggle({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: "5px 11px", fontSize: 11, fontFamily: T.mono, fontWeight: 600, cursor: "pointer",
        border: `1px solid ${active ? T.green : T.border}`, borderRadius: 5,
        background: active ? "var(--green-light)" : "transparent", color: active ? T.green : T.muted,
        transition: "all 0.15s",
      }}
    >
      {children}
    </button>
  );
}

function StatCard({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: string }) {
  return (
    <div style={{ flex: "1 1 0", minWidth: 150, padding: "14px 16px", background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8 }}>
      <div style={{ fontSize: 9.5, fontFamily: T.mono, fontWeight: 600, letterSpacing: "0.08em", color: T.light, textTransform: "uppercase" }}>{label}</div>
      <div style={{ fontSize: 24, fontFamily: T.mono, fontWeight: 800, color: accent ?? T.text, marginTop: 6, lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: 10, fontFamily: T.mono, color: T.muted, marginTop: 5 }}>{sub}</div>}
    </div>
  );
}

function ProbChip({ label, p, tgt, focus }: { label: string; p: number | undefined; tgt: 10 | 20; focus?: boolean }) {
  return (
    <div style={{ padding: "7px 10px", borderRadius: 6, border: `1px solid ${focus ? T.green : T.border}`, background: focus ? "var(--green-light)" : T.bg, minWidth: 84 }}>
      <div style={{ fontSize: 8.5, fontFamily: T.mono, color: T.light, letterSpacing: "0.05em", textTransform: "uppercase" }}>{label}</div>
      <div style={{ fontSize: 16, fontFamily: T.mono, fontWeight: 800, color: probColor(p, tgt), marginTop: 2 }}>{pct0(p)}</div>
    </div>
  );
}

const PCT_OPTIONS: { pct: number; label: string }[] = [
  { pct: 10, label: "Top 10%" },
  { pct: 20, label: "Top 20%" },
  { pct: 30, label: "Top 30%" },
  { pct: 50, label: "Top 50%" },
  { pct: 100, label: "All" },
];

export default function MLPicks() {
  const router = useRouter();
  const [data, setData] = useState<ScanData | null>(null);
  const [loading, setLoading] = useState(true);
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [horizon, setHorizon] = useState<30 | 60>(30);
  const [target, setTarget] = useState<10 | 20>(20);
  const [topPct, setTopPct] = useState<number>(20);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [hover, setHover] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${GCS_BASE}/latest_global.json?t=${Date.now()}`)
      .then((r) => { if (r.ok) return r.json(); throw new Error("gcs"); })
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => {
        fetch("/latest_global.json")
          .then((r) => (r.ok ? r.json() : null))
          .then((d) => { if (d) setData(d); setLoading(false); })
          .catch(() => setLoading(false));
      });
  }, []);

  const total = data?.stock_count ?? data?.stocks?.length ?? 0;
  const scoredCount = useMemo(() => (data?.stocks ?? []).filter(isScored).length, [data]);

  // Only quality-passed names reach the UI: real options + fundamentals, no imputation.
  const qualified = useMemo(() => (data?.stocks ?? []).filter(qualifies), [data]);

  // Decile by the focused probability over the QUALIFIED set (10 = top 10%). Rank-based,
  // so it adapts to whichever metric is selected regardless of absolute scale.
  const decileOf = useMemo(() => {
    const ranked = [...qualified].sort((a, b) => probOf(b, target, horizon) - probOf(a, target, horizon));
    const n = ranked.length || 1;
    const m = new Map<string, number>();
    ranked.forEach((s, i) => m.set(s.symbol, Math.max(1, Math.ceil(((n - i) / n) * 10))));
    return m;
  }, [qualified, target, horizon]);

  const minDecile = 11 - topPct / 10; // Top10%→10, 20%→9, 30%→8, 50%→6, All→1

  const visible = useMemo(() => {
    const filtered = qualified.filter((s) => (decileOf.get(s.symbol) ?? 1) >= minDecile);
    filtered.sort((a, b) => {
      const va = probOf(a, target, horizon), vb = probOf(b, target, horizon);
      return sortDir === "asc" ? va - vb : vb - va;
    });
    return filtered;
  }, [qualified, decileOf, minDecile, target, horizon, sortDir]);

  const focusLabel = `P(+${target}% / ${horizon}d)`;
  const best = visible[0];
  const scanWhen = data?.scan_date ? new Date(data.scan_date) : null;
  const freshness = scanWhen
    ? scanWhen.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
    : "—";

  const hdr: React.CSSProperties = { padding: "9px 8px", fontSize: 9.5, fontFamily: T.mono, fontWeight: 700, letterSpacing: "0.05em", textAlign: "right", color: T.light, textTransform: "uppercase", whiteSpace: "nowrap" };

  return (
    <div style={{ minHeight: "100vh", background: T.bg, padding: "24px 24px 80px" }}>
      <div style={{ maxWidth: 1000, margin: "0 auto" }}>
        {/* Header */}
        <div style={{ display: "flex", alignItems: "flex-start", gap: 12, marginBottom: 4 }}>
          <Target size={20} style={{ color: T.green, marginTop: 2 }} />
          <div>
            <h1 style={{ fontSize: 19, fontWeight: 800, fontFamily: T.mono, color: T.text, letterSpacing: "-0.02em" }}>
              ML PICKS <span style={{ color: T.light, fontWeight: 500 }}>/ probability of gain</span>
            </h1>
            <p style={{ fontSize: 11, fontFamily: T.mono, color: T.muted, marginTop: 4, lineHeight: 1.5 }}>
              Data-quality-gated names ranked by the model&apos;s P(+10%) / P(+20%) over 30 / 60 days. One line per
              name — click to expand all four probabilities + drawdown. Fresh as of <span style={{ color: T.text }}>{freshness}</span>{data?.region ? ` · ${data.region}` : ""}.
            </p>
          </div>
        </div>

        {/* Data-quality banner */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", background: "var(--green-light)", border: `1px solid ${T.border}`, borderRadius: 6, margin: "12px 0 8px" }}>
          <ShieldCheck size={13} style={{ color: T.green, flexShrink: 0 }} />
          <span style={{ fontSize: 10.5, fontFamily: T.mono, color: T.muted, lineHeight: 1.45 }}>
            Showing only names carrying <span style={{ color: T.text }}>real options + fundamentals</span> — no median-imputed inputs. The strict per-feature gate moves to the backend next; GCS still stores the full set for model fine-tuning.
          </span>
        </div>
        {/* Forward-validation caveat */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", background: "var(--amber-light)", border: `1px solid ${T.border}`, borderRadius: 6, margin: "0 0 18px" }}>
          <AlertTriangle size={13} style={{ color: T.amber, flexShrink: 0 }} />
          <span style={{ fontSize: 10.5, fontFamily: T.mono, color: T.muted, lineHeight: 1.45 }}>
            Raw model probability — forward-validation still accumulating (see <span style={{ color: T.purple, cursor: "pointer" }} onClick={() => router.push("/performance")}>Performance → P20 Cycles</span>). A ranking signal, not a realized hit rate.
          </span>
        </div>

        {loading ? (
          <div style={{ textAlign: "center", padding: "80px 0", fontFamily: T.mono, fontSize: 12, color: T.light }}>Loading nightly scan…</div>
        ) : qualified.length === 0 ? (
          <div style={{ textAlign: "center", padding: "80px 0", fontFamily: T.mono, fontSize: 12, color: T.light, lineHeight: 1.6 }}>
            No names passed the data-quality gate in the current scan.<br />
            ({scoredCount} scored, but none carry both real options and fundamentals yet.)
          </div>
        ) : (
          <>
            {/* Stat cards */}
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 18 }}>
              <StatCard label="Quality-passed" value={String(qualified.length)} sub={`of ${scoredCount} scored · ${total} scanned`} accent={T.green} />
              <StatCard label="Shown" value={String(visible.length)} sub={topPct === 100 ? "all quality-passed" : `top ${topPct}% by ${focusLabel}`} />
              <StatCard label={`Best ${focusLabel}`} value={best ? pct0(probOf(best, target, horizon)) : "—"} sub={best?.symbol} />
            </div>

            {/* Controls */}
            <div style={{ display: "flex", alignItems: "center", gap: 18, flexWrap: "wrap", marginBottom: 14 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                <span style={{ fontSize: 9.5, fontFamily: T.mono, fontWeight: 700, letterSpacing: "0.06em", color: T.light, textTransform: "uppercase" }}>Target</span>
                <Toggle active={target === 10} onClick={() => setTarget(10)}>+10%</Toggle>
                <Toggle active={target === 20} onClick={() => setTarget(20)}>+20%</Toggle>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                <span style={{ fontSize: 9.5, fontFamily: T.mono, fontWeight: 700, letterSpacing: "0.06em", color: T.light, textTransform: "uppercase" }}>Horizon</span>
                <Toggle active={horizon === 30} onClick={() => setHorizon(30)}>30d</Toggle>
                <Toggle active={horizon === 60} onClick={() => setHorizon(60)}>60d</Toggle>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                <span style={{ fontSize: 9.5, fontFamily: T.mono, fontWeight: 700, letterSpacing: "0.06em", color: T.light, textTransform: "uppercase" }}>Show</span>
                {PCT_OPTIONS.map((o) => (
                  <Toggle key={o.pct} active={topPct === o.pct} onClick={() => setTopPct(o.pct)}>{o.label}</Toggle>
                ))}
              </div>
            </div>

            {/* Compact table */}
            <div style={{ overflowX: "auto", border: `1px solid ${T.border}`, borderRadius: 8, background: T.surface }}>
              <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 720, tableLayout: "fixed" }}>
                <thead>
                  <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                    <th style={{ ...hdr, textAlign: "center", width: 40 }}>#</th>
                    <th style={{ ...hdr, textAlign: "left", width: 340 }}>Symbol</th>
                    <th style={{ ...hdr, width: 100 }}>Price</th>
                    <th
                      onClick={() => setSortDir((d) => (d === "asc" ? "desc" : "asc"))}
                      title="Click to flip sort direction"
                      style={{ ...hdr, width: 120, color: T.text, cursor: "pointer", background: "var(--green-light)" }}
                    >
                      {focusLabel}{sortDir === "desc" ? " ↓" : " ↑"}
                    </th>
                    <th style={{ ...hdr, textAlign: "center", width: 90 }} title="Decile of the focused probability among quality-passed names (10 = top 10%)">Decile</th>
                    <th style={{ ...hdr, width: 100 }} title={`Expected max drawdown over ${horizon} days`}>Exp.DD</th>
                    <th style={{ ...hdr, width: 88 }} title="ATM implied volatility — a model input (options_iv_current)">IV</th>
                    <th style={{ ...hdr, width: 82 }} title="IV Rank — current IV vs its 52-week range (0 = cheap, 100 = rich). Populates once the thetadata IV-history pipeline is live.">IVR</th>
                    <th style={{ ...hdr, width: 40 }} />
                  </tr>
                </thead>
                <tbody>
                  {visible.map((s, i) => {
                    const isOpen = expanded === s.symbol;
                    const fp = probOf(s, target, horizon);
                    const dec = decileOf.get(s.symbol) ?? 1;
                    const dd = ddOf(s, horizon);
                    const iv = s.options_iv_current;
                    const cell: React.CSSProperties = { padding: "8px 8px", fontSize: 11.5, fontFamily: T.mono, textAlign: "right", fontWeight: 600 };
                    return (
                      <Fragment key={s.symbol}>
                        <tr
                          onClick={() => setExpanded(isOpen ? null : s.symbol)}
                          onMouseEnter={() => setHover(s.symbol)}
                          onMouseLeave={() => setHover(null)}
                          style={{ borderBottom: isOpen ? "none" : `1px solid ${T.border}`, cursor: "pointer", background: isOpen ? T.elevated : hover === s.symbol ? T.hover : "transparent", transition: "background 0.1s" }}
                        >
                          <td style={{ padding: "8px 8px", fontSize: 11, fontFamily: T.mono, textAlign: "center", color: i < 3 ? T.green : T.light, fontWeight: i < 3 ? 800 : 500 }}>{i + 1}</td>
                          <td style={{ padding: "8px 8px" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                              {isOpen ? <ChevronDown size={12} style={{ color: T.muted }} /> : <ChevronRight size={12} style={{ color: hover === s.symbol ? T.muted : T.light }} />}
                              <span style={{ fontSize: 12.5, fontFamily: T.mono, fontWeight: 700, color: T.text }}>{s.symbol}</span>
                            </div>
                            <div style={{ fontSize: 9.5, fontFamily: T.mono, color: T.light, marginTop: 1, marginLeft: 18, maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                              {[s.company_name, s.sector].filter(Boolean).join(" · ") || s.country || ""}
                            </div>
                          </td>
                          <td style={{ ...cell, color: T.muted, fontWeight: 500 }}>{fmtPrice(s.price, s.currency)}</td>
                          <td style={{ ...cell, fontSize: 13, fontWeight: 800, color: probColor(fp, target), background: "var(--green-light)" }}>{pct0(fp)}</td>
                          <td style={{ padding: "8px 8px", textAlign: "center" }}>
                            <span style={{ fontSize: 10, fontFamily: T.mono, fontWeight: 700, color: dec >= 9 ? T.green : dec >= 7 ? T.amber : T.muted, border: `1px solid ${T.border}`, borderRadius: 4, padding: "2px 6px" }}>D{dec}</span>
                          </td>
                          <td style={{ ...cell, color: ddColor(dd), fontWeight: 500 }}>{dd ? `${dd.toFixed(1)}%` : "—"}</td>
                          <td style={{ ...cell, color: T.muted, fontWeight: 500 }}>{iv != null ? `${(iv * 100).toFixed(0)}%` : "—"}</td>
                          <td style={{ ...cell, color: ivrColor(s.options_iv_rank), fontWeight: 500 }}>{s.options_iv_rank != null ? s.options_iv_rank.toFixed(0) : "—"}</td>
                          <td style={{ textAlign: "center", color: T.light }}>{hover === s.symbol && !isOpen ? "›" : ""}</td>
                        </tr>
                        {isOpen && (
                          <tr style={{ borderBottom: `1px solid ${T.border}`, background: T.elevated }}>
                            <td colSpan={9} style={{ padding: "4px 16px 14px 42px" }}>
                              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                                <ProbChip label="P10 · 30d" p={s.hit_prob_10pct_30d} tgt={10} focus={target === 10 && horizon === 30} />
                                <ProbChip label="P10 · 60d" p={s.hit_prob_10pct_60d} tgt={10} focus={target === 10 && horizon === 60} />
                                <ProbChip label="P20 · 30d" p={s.hit_prob_30d} tgt={20} focus={target === 20 && horizon === 30} />
                                <ProbChip label="P20 · 60d" p={s.hit_prob_60d} tgt={20} focus={target === 20 && horizon === 60} />
                                <div style={{ width: 1, height: 36, background: T.border }} />
                                <div style={{ fontSize: 10, fontFamily: T.mono, color: T.muted, lineHeight: 1.6 }}>
                                  <div>Exp. drawdown: <span style={{ color: ddColor(s.expected_dd_30d) }}>{s.expected_dd_30d ? `${s.expected_dd_30d.toFixed(1)}%` : "—"}</span> (30d) · <span style={{ color: ddColor(s.expected_dd_60d) }}>{s.expected_dd_60d ? `${s.expected_dd_60d.toFixed(1)}%` : "—"}</span> (60d)</div>
                                  <div>Composite: {s.composite != null ? (s.composite * 100).toFixed(0) : "—"} · ATM IV: {iv != null ? `${(iv * 100).toFixed(0)}%` : "—"}</div>
                                  <div style={{ color: T.green }}>Data: options ✓ · fundamentals ✓</div>
                                </div>
                                <button
                                  onClick={(e) => { e.stopPropagation(); router.push(`/stock/${s.symbol}`); }}
                                  style={{ marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: 5, padding: "6px 12px", fontSize: 11, fontFamily: T.mono, fontWeight: 600, cursor: "pointer", border: `1px solid ${T.green}`, borderRadius: 5, background: "var(--green-light)", color: T.green }}
                                >
                                  Full dossier <ExternalLink size={12} />
                                </button>
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div style={{ marginTop: 12, fontSize: 10, fontFamily: T.mono, color: T.light, display: "flex", alignItems: "center", gap: 6 }}>
              <TrendingUp size={11} />
              {visible.length} shown of {qualified.length} quality-passed ({scoredCount} scored) · ranked by {focusLabel} · click a row to expand.
            </div>
          </>
        )}
      </div>
    </div>
  );
}
