"use client";
import { useState, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { TrendingUp, TrendingDown, BarChart3, Target, Clock, Radio, ExternalLink, Award } from "lucide-react";

// ── Data sources ────────────────────────────────────────────────────────────
const SIGNAL_TRACKS = "/api/performance/signal-tracks";
const HIT_RATES     = "/api/performance/hit-rates";
const GCS_PORTFOLIO = "/api/gcs/portfolio";
const GCS_PERFORMANCE = "/api/gcs/performance";

// ── Types ───────────────────────────────────────────────────────────────────
interface SignalTrackOpen {
  symbol: string; region: string; entry_date: string; entry_price: number;
  entry_composite: number; entry_signal: string; sector?: string; industry?: string;
  classification?: string;
  last_price: number; last_composite: number; last_signal: string;
  last_updated: string; max_price: number; min_price: number; days_held: number;
}
interface SignalTrackClosed extends SignalTrackOpen {
  exit_date: string; exit_price: number; exit_composite: number; exit_signal: string;
  realized_pnl_pct: number; max_gain_pct: number; max_dd_pct: number;
}
interface HitRateOpen {
  symbol: string; region: string; entry_date: string; entry_price: number;
  entry_composite: number; entry_signal: string; entry_p10: number;
  sector?: string; classification?: string;
  last_price: number; last_updated: string; max_price: number;
  days_elapsed: number; hit_date: string | null;
}
interface HitRateClosed extends HitRateOpen {
  exit_date: string; exit_reason: "hit_10pct" | "window_closed";
  hit: boolean; max_gain_pct: number;
}
interface PortfolioHistoryEntry {
  symbol: string; action: string; date: string;
  entry_price: number; entry_date: string;
  exit_price: number; pnl_pct: number; reason: string; days_held: number;
  bucket?: "midcap" | "sp500" | null;
}

// Strategy tracker (gs://.../performance/strategy_history_{region}.json)
interface StrategyWeekClosed {
  entry_date: string;
  exit_date: string;
  n_positions: number;
  basket_return_pct: number;
  spy_return_pct: number;
  alpha_pp: number;
  positions: { symbol: string; entry: number; exit: number; return_pct: number }[];
}
interface StrategyHistory {
  region: string;
  strategy_version: string;
  inception_date: string | null;
  open_basket: { scan_date: string; basket: { symbol: string }[] } | null;
  weeks: StrategyWeekClosed[];
  summary: {
    weeks_closed: number;
    cum_strategy_return_pct: number;
    cum_spy_return_pct: number;
    cum_alpha_pp: number;
    annualized_return_pct: number;
    annualized_alpha_pp: number;
    weeks_positive_alpha: number;
    win_rate: number;
    best_week_alpha_pp: number;
    worst_week_alpha_pp: number;
  } | null;
  updated_at: string | null;
}
type BucketTag = "midcap" | "sp500" | null;
type BucketFilter = "all" | "midcap" | "sp500" | "untagged";
const PAGE_SIZE = 25;
const EXPECTED_ANNUAL_ALPHA: Record<"midcap"|"sp500", number> = {
  midcap: 19.95,
  sp500:  7.03,
};

// ── Theme ───────────────────────────────────────────────────────────────────
const T = {
  text: "#1a1a1a", muted: "#6b7280", light: "#9ca3af",
  green: "#2d7a4f", greenPos: "#10b981", greenLight: "#e8f5ee", greenBorder: "#b8dcc8",
  red: "#ef4444", redLight: "#fef2f2",
  amber: "#d97706", amberLight: "#fffbeb",
  purple: "#8b5cf6",
  border: "#e5e7eb", divider: "#f3f4f6",
  mono: "var(--font-mono, 'JetBrains Mono', monospace)",
  shadow: "0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)",
};

const SIG: Record<string, { color: string; bg: string; border: string }> = {
  "STRONG BUY": { color: T.purple, bg: "#f5f3ff", border: "#ddd6fe" },
  BUY:   { color: T.greenPos, bg: T.greenLight, border: T.greenBorder },
  WATCH: { color: T.amber, bg: T.amberLight, border: "#fde68a" },
  HOLD:  { color: T.muted, bg: "#f8fafc", border: "#e2e8f0" },
  SELL:  { color: T.red, bg: T.redLight, border: "#fecaca" },
};

// ── Atoms ───────────────────────────────────────────────────────────────────
function Card({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{ background: "#fff", borderRadius: 8, border: `1px solid ${T.border}`, boxShadow: T.shadow, padding: "16px 18px", ...style }}>
      {children}
    </div>
  );
}
function SH({ title, icon, sub }: { title: string; icon?: React.ReactNode; sub?: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, fontWeight: 600, letterSpacing: "0.08em", color: T.green, fontFamily: T.mono, textTransform: "uppercase", marginBottom: 12, paddingBottom: 8, borderBottom: `2px solid ${T.greenLight}` }}>
      {icon}{title}
      {sub && <span style={{ marginLeft: "auto", fontSize: 9, color: T.light, fontWeight: 400, textTransform: "none", letterSpacing: 0 }}>{sub}</span>}
    </div>
  );
}
function KPI({ label, value, sub, color }: { label: string; value: string; sub?: string; color?: string }) {
  return (
    <Card>
      <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: "0.1em", color: T.muted, fontFamily: T.mono }}>{label}</div>
      <div style={{ fontSize: 26, fontWeight: 700, color: color || T.text, fontFamily: T.mono, marginTop: 4 }}>{value}</div>
      {sub && <div style={{ fontSize: 9, color: T.light, fontFamily: T.mono, marginTop: 2 }}>{sub}</div>}
    </Card>
  );
}
function SignalBadge({ signal }: { signal: string }) {
  const s = SIG[signal] || SIG.HOLD;
  return (
    <span style={{ display: "inline-block", padding: "2px 7px", borderRadius: 4, fontSize: 9, fontWeight: 700, fontFamily: T.mono, letterSpacing: "0.07em", color: s.color, background: s.bg, border: `1px solid ${s.border}` }}>
      {signal}
    </span>
  );
}
function Empty({ icon, title, sub }: { icon: React.ReactNode; title: string; sub?: string }) {
  return (
    <Card style={{ padding: "60px 20px", textAlign: "center" }}>
      <div style={{ opacity: 0.4, marginBottom: 16 }}>{icon}</div>
      <div style={{ fontSize: 14, color: T.muted, fontFamily: T.mono, fontWeight: 600 }}>{title}</div>
      {sub && <div style={{ fontSize: 11, color: T.light, fontFamily: T.mono, marginTop: 8, maxWidth: 440, margin: "8px auto 0", lineHeight: 1.6 }}>{sub}</div>}
    </Card>
  );
}

const th: React.CSSProperties = { padding: "8px 10px", fontSize: 9, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", color: T.muted, fontFamily: T.mono, borderBottom: `2px solid ${T.border}`, whiteSpace: "nowrap" };
const td: React.CSSProperties = { padding: "9px 10px", fontSize: 11, fontFamily: T.mono, borderBottom: `1px solid ${T.divider}` };

// ══════════════════════════════════════════════════════════════════════════════
// TAB 1: SIGNAL PERFORMANCE (System 1 — BUY/STRONG BUY → SELL cycles)
// ══════════════════════════════════════════════════════════════════════════════
function SignalPerfTab({ router }: { router: ReturnType<typeof useRouter> }) {
  const [open, setOpen] = useState<SignalTrackOpen[]>([]);
  const [closed, setClosed] = useState<SignalTrackClosed[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<"exit_date" | "realized_pnl_pct" | "days_held" | "max_gain_pct">("exit_date");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  useEffect(() => {
    fetch(SIGNAL_TRACKS).then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((d: { open: SignalTrackOpen[]; closed: SignalTrackClosed[] }) => {
        setOpen(d.open || []); setClosed(d.closed || []); setLoading(false);
      })
      .catch(e => { setErr(e.message || "Failed to load"); setLoading(false); });
  }, []);

  const sortedClosed = useMemo(() => {
    const list = [...closed];
    list.sort((a, b) => {
      const av = (a as any)[sortKey]; const bv = (b as any)[sortKey];
      if (typeof av === "string") return sortDir === "desc" ? bv.localeCompare(av) : av.localeCompare(bv);
      return sortDir === "desc" ? (bv ?? 0) - (av ?? 0) : (av ?? 0) - (bv ?? 0);
    });
    return list.slice(0, 200);
  }, [closed, sortKey, sortDir]);

  const sortedOpen = useMemo(() => {
    const list = [...open];
    list.sort((a, b) => {
      const apnl = a.entry_price > 0 ? ((a.last_price - a.entry_price) / a.entry_price) * 100 : 0;
      const bpnl = b.entry_price > 0 ? ((b.last_price - b.entry_price) / b.entry_price) * 100 : 0;
      return bpnl - apnl;
    });
    return list;
  }, [open]);

  const toggleSort = (k: typeof sortKey) => {
    if (sortKey === k) setSortDir(d => d === "desc" ? "asc" : "desc");
    else { setSortKey(k); setSortDir("desc"); }
  };

  // Aggregate stats
  const stats = useMemo(() => {
    if (closed.length === 0) return null;
    const wins = closed.filter(c => c.realized_pnl_pct > 0).length;
    const totalPnl = closed.reduce((a, c) => a + c.realized_pnl_pct, 0);
    const totalDays = closed.reduce((a, c) => a + c.days_held, 0);
    const avgAnn = closed.reduce((a, c) => a + (c.days_held > 0 ? (c.realized_pnl_pct / c.days_held) * 365 : 0), 0) / closed.length;
    return {
      total: closed.length,
      win_rate: (wins / closed.length) * 100,
      avg_pnl: totalPnl / closed.length,
      avg_days: totalDays / closed.length,
      avg_ann: avgAnn,
      best: closed.reduce((a, c) => c.realized_pnl_pct > (a?.realized_pnl_pct ?? -Infinity) ? c : a, null as SignalTrackClosed | null),
      worst: closed.reduce((a, c) => c.realized_pnl_pct < (a?.realized_pnl_pct ?? Infinity) ? c : a, null as SignalTrackClosed | null),
    };
  }, [closed]);

  if (loading) return <Empty icon={<BarChart3 size={36} color={T.divider} />} title="Loading signal tracks…" />;
  if (err) return <Empty icon={<BarChart3 size={36} color={T.divider} />} title="Failed to load" sub={err} />;

  return (
    <>
      {/* KPIs (only when we have closed data) */}
      {stats && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 10, marginBottom: 20 }}>
          <KPI label="OPEN" value={String(open.length)} sub="Currently tracking" />
          <KPI label="CLOSED CYCLES" value={String(stats.total)} sub={`Best: ${stats.best?.symbol ?? "—"} ${stats.best ? `${stats.best.realized_pnl_pct >= 0 ? "+" : ""}${stats.best.realized_pnl_pct.toFixed(1)}%` : ""}`} />
          <KPI label="WIN RATE" value={`${stats.win_rate.toFixed(0)}%`} color={stats.win_rate >= 50 ? T.greenPos : T.red} sub={`Worst: ${stats.worst?.symbol ?? "—"} ${stats.worst ? `${stats.worst.realized_pnl_pct.toFixed(1)}%` : ""}`} />
          <KPI label="AVG P&L" value={`${stats.avg_pnl >= 0 ? "+" : ""}${stats.avg_pnl.toFixed(1)}%`} color={stats.avg_pnl >= 0 ? T.greenPos : T.red} sub={`Avg hold: ${stats.avg_days.toFixed(0)}d`} />
          <KPI label="AVG ANNUALIZED" value={`${stats.avg_ann >= 0 ? "+" : ""}${stats.avg_ann.toFixed(0)}%`} color={stats.avg_ann >= 0 ? T.greenPos : T.red} sub={`${stats.total} closed cycles`} />
        </div>
      )}

      {/* Open tracks */}
      <Card style={{ marginBottom: 20 }}>
        <SH title={`Open Tracks (${sortedOpen.length})`} icon={<TrendingUp size={12} />} sub="BUY/STRONG BUY not yet downgraded to SELL" />
        {sortedOpen.length === 0 ? (
          <div style={{ padding: 30, textAlign: "center", color: T.light, fontSize: 11, fontFamily: T.mono }}>
            No open tracks yet. First BUY signal will appear here on the next scan.
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead><tr>
                {["Symbol", "Entry Date", "Entry Price", "Current", "Unrealized", "Max Gain", "Max DD", "Days", "Entry Sig", "Cur Sig", "Composite"].map((h, i) => (
                  <th key={h} style={{ ...th, textAlign: i === 0 ? "left" : "right" }}>{h}</th>
                ))}
              </tr></thead>
              <tbody>
                {sortedOpen.map((t, i) => {
                  const ep = t.entry_price || 0;
                  const pnl = ep > 0 ? ((t.last_price - ep) / ep) * 100 : 0;
                  const maxG = ep > 0 ? ((t.max_price - ep) / ep) * 100 : 0;
                  const maxD = ep > 0 ? ((t.min_price - ep) / ep) * 100 : 0;
                  const pC = pnl >= 0 ? T.greenPos : T.red;
                  return (
                    <tr key={`${t.symbol}-${t.entry_date}-${i}`} style={{ cursor: "pointer" }}
                      onClick={() => router.push(`/stock/${t.symbol}`)}
                      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "#f8faf9"; }}
                      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = ""; }}>
                      <td style={{ ...td, textAlign: "left", fontWeight: 600, color: T.text }}>{t.symbol}</td>
                      <td style={{ ...td, textAlign: "right", color: T.muted }}>{t.entry_date}</td>
                      <td style={{ ...td, textAlign: "right", color: T.muted }}>${t.entry_price.toFixed(2)}</td>
                      <td style={{ ...td, textAlign: "right", fontWeight: 600, color: T.text }}>${t.last_price.toFixed(2)}</td>
                      <td style={{ ...td, textAlign: "right", fontWeight: 700, color: pC }}>{pnl >= 0 ? "+" : ""}{pnl.toFixed(1)}%</td>
                      <td style={{ ...td, textAlign: "right", color: T.greenPos }}>+{maxG.toFixed(1)}%</td>
                      <td style={{ ...td, textAlign: "right", color: T.red }}>{maxD.toFixed(1)}%</td>
                      <td style={{ ...td, textAlign: "right", color: T.muted }}>{t.days_held}d</td>
                      <td style={{ ...td, textAlign: "right" }}><SignalBadge signal={t.entry_signal} /></td>
                      <td style={{ ...td, textAlign: "right" }}><SignalBadge signal={t.last_signal} /></td>
                      <td style={{ ...td, textAlign: "right", color: T.muted }}>{t.last_composite?.toFixed(2) ?? "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Closed cycles */}
      <Card>
        <SH title={`Closed Cycles (${closed.length})`} icon={<Clock size={12} />} sub="BUY → SELL completed — click column to sort" />
        {closed.length === 0 ? (
          <div style={{ padding: 30, textAlign: "center", color: T.light, fontSize: 11, fontFamily: T.mono }}>
            No closed cycles yet. A cycle completes when a tracked BUY downgrades to SELL.
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead><tr>
                <th style={{ ...th, textAlign: "left" }}>Symbol</th>
                <th style={{ ...th, textAlign: "right" }}>Entry</th>
                <th style={{ ...th, textAlign: "right" }}>Exit</th>
                <th style={{ ...th, textAlign: "right", cursor: "pointer", color: sortKey === "realized_pnl_pct" ? T.green : T.muted }} onClick={() => toggleSort("realized_pnl_pct")}>Realized {sortKey === "realized_pnl_pct" ? (sortDir === "desc" ? "↓" : "↑") : ""}</th>
                <th style={{ ...th, textAlign: "right", cursor: "pointer", color: sortKey === "max_gain_pct" ? T.green : T.muted }} onClick={() => toggleSort("max_gain_pct")}>Max Gain {sortKey === "max_gain_pct" ? (sortDir === "desc" ? "↓" : "↑") : ""}</th>
                <th style={{ ...th, textAlign: "right" }}>Max DD</th>
                <th style={{ ...th, textAlign: "right", cursor: "pointer", color: sortKey === "days_held" ? T.green : T.muted }} onClick={() => toggleSort("days_held")}>Days {sortKey === "days_held" ? (sortDir === "desc" ? "↓" : "↑") : ""}</th>
                <th style={{ ...th, textAlign: "right" }}>Entry Sig</th>
                <th style={{ ...th, textAlign: "right", cursor: "pointer", color: sortKey === "exit_date" ? T.green : T.muted }} onClick={() => toggleSort("exit_date")}>Exit Date {sortKey === "exit_date" ? (sortDir === "desc" ? "↓" : "↑") : ""}</th>
              </tr></thead>
              <tbody>
                {sortedClosed.map((t, i) => {
                  const pC = t.realized_pnl_pct >= 0 ? T.greenPos : T.red;
                  return (
                    <tr key={`${t.symbol}-${t.exit_date}-${i}`}
                      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "#f8faf9"; }}
                      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = ""; }}>
                      <td style={{ ...td, textAlign: "left", fontWeight: 600, color: T.text, cursor: "pointer" }} onClick={() => router.push(`/stock/${t.symbol}`)}>{t.symbol}</td>
                      <td style={{ ...td, textAlign: "right", color: T.muted }}>${t.entry_price.toFixed(2)}</td>
                      <td style={{ ...td, textAlign: "right", color: T.text, fontWeight: 600 }}>${t.exit_price.toFixed(2)}</td>
                      <td style={{ ...td, textAlign: "right", fontWeight: 700, color: pC }}>{t.realized_pnl_pct >= 0 ? "+" : ""}{t.realized_pnl_pct.toFixed(1)}%</td>
                      <td style={{ ...td, textAlign: "right", color: T.greenPos }}>+{t.max_gain_pct.toFixed(1)}%</td>
                      <td style={{ ...td, textAlign: "right", color: T.red }}>{t.max_dd_pct.toFixed(1)}%</td>
                      <td style={{ ...td, textAlign: "right", color: T.muted }}>{t.days_held}d</td>
                      <td style={{ ...td, textAlign: "right" }}><SignalBadge signal={t.entry_signal} /></td>
                      <td style={{ ...td, textAlign: "right", color: T.light, fontSize: 10 }}>{t.exit_date}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB 2: P(+10%) HIT RATE (System 2 — 60d windows, p10 > 0.60)
// ══════════════════════════════════════════════════════════════════════════════
function HitRateTab({ router }: { router: ReturnType<typeof useRouter> }) {
  const [open, setOpen] = useState<HitRateOpen[]>([]);
  const [closed, setClosed] = useState<HitRateClosed[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetch(HIT_RATES).then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((d: { open: HitRateOpen[]; closed: HitRateClosed[] }) => {
        setOpen(d.open || []); setClosed(d.closed || []); setLoading(false);
      })
      .catch(e => { setErr(e.message || "Failed to load"); setLoading(false); });
  }, []);

  const stats = useMemo(() => {
    if (closed.length === 0) return null;
    const hits = closed.filter(c => c.hit).length;
    const avgGain = closed.reduce((a, c) => a + c.max_gain_pct, 0) / closed.length;
    const avgP10 = closed.reduce((a, c) => a + c.entry_p10, 0) / closed.length;
    // Buckets by predicted p10
    const buckets = [
      { label: "0.60–0.70", min: 0.60, max: 0.70, n: 0, hits: 0 },
      { label: "0.70–0.80", min: 0.70, max: 0.80, n: 0, hits: 0 },
      { label: "0.80–0.90", min: 0.80, max: 0.90, n: 0, hits: 0 },
      { label: "0.90+",     min: 0.90, max: 1.01, n: 0, hits: 0 },
    ];
    for (const c of closed) {
      for (const b of buckets) {
        if (c.entry_p10 >= b.min && c.entry_p10 < b.max) { b.n++; if (c.hit) b.hits++; break; }
      }
    }
    return {
      total: closed.length, hit_rate: (hits / closed.length) * 100,
      hits, misses: closed.length - hits,
      avg_gain: avgGain, avg_predicted_p10: avgP10 * 100,
      buckets,
    };
  }, [closed]);

  if (loading) return <Empty icon={<Target size={36} color={T.divider} />} title="Loading hit-rate windows…" />;
  if (err) return <Empty icon={<Target size={36} color={T.divider} />} title="Failed to load" sub={err} />;

  return (
    <>
      {stats && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 20 }}>
          <KPI label="OPEN WINDOWS" value={String(open.length)} sub="p10 > 0.60 currently tracked" />
          <KPI label="CLOSED" value={String(stats.total)} sub={`${stats.hits} hits / ${stats.misses} misses`} />
          <KPI label="LIVE HIT RATE" value={`${stats.hit_rate.toFixed(0)}%`} color={stats.hit_rate >= 50 ? T.greenPos : T.red} sub={`vs. predicted avg ${stats.avg_predicted_p10.toFixed(0)}%`} />
          <KPI label="AVG MAX GAIN" value={`${stats.avg_gain >= 0 ? "+" : ""}${stats.avg_gain.toFixed(1)}%`} color={stats.avg_gain >= 0 ? T.greenPos : T.red} sub="Across all closed windows" />
        </div>
      )}

      {/* Hit-rate by bucket */}
      {stats && stats.buckets.some(b => b.n > 0) && (
        <Card style={{ marginBottom: 20 }}>
          <SH title="Hit Rate by Predicted p10 Bucket" icon={<Award size={12} />} sub="Calibration check" />
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
            {stats.buckets.map(b => {
              const rate = b.n > 0 ? (b.hits / b.n) * 100 : 0;
              return (
                <div key={b.label} style={{ padding: "10px 12px", background: T.greenLight, borderRadius: 6, border: `1px solid ${T.greenBorder}` }}>
                  <div style={{ fontSize: 9, color: T.muted, fontFamily: T.mono, fontWeight: 600, letterSpacing: "0.08em" }}>p10 {b.label}</div>
                  <div style={{ fontSize: 22, fontWeight: 700, color: T.text, fontFamily: T.mono, marginTop: 4 }}>
                    {b.n > 0 ? `${rate.toFixed(0)}%` : "—"}
                  </div>
                  <div style={{ fontSize: 9, color: T.light, fontFamily: T.mono }}>
                    {b.hits}/{b.n} hit
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {/* Open windows */}
      <Card style={{ marginBottom: 20 }}>
        <SH title={`Open Windows (${open.length})`} icon={<Radio size={12} />} sub="60-day countdown — p10 > 0.60" />
        {open.length === 0 ? (
          <div style={{ padding: 30, textAlign: "center", color: T.light, fontSize: 11, fontFamily: T.mono }}>
            No open windows. Opens when a stock is scanned with ML p(+10%) &gt; 0.60.
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead><tr>
                {["Symbol", "Entry Date", "Entry Price", "p10", "Current", "Max Gain", "Days", "Hit Date"].map((h, i) => (
                  <th key={h} style={{ ...th, textAlign: i === 0 ? "left" : "right" }}>{h}</th>
                ))}
              </tr></thead>
              <tbody>
                {open.sort((a, b) => {
                  const ag = a.entry_price > 0 ? ((a.max_price - a.entry_price) / a.entry_price) : 0;
                  const bg = b.entry_price > 0 ? ((b.max_price - b.entry_price) / b.entry_price) : 0;
                  return bg - ag;
                }).map((t, i) => {
                  const ep = t.entry_price || 0;
                  const maxG = ep > 0 ? ((t.max_price - ep) / ep) * 100 : 0;
                  const currG = ep > 0 ? ((t.last_price - ep) / ep) * 100 : 0;
                  const hitExpected = maxG >= 10;
                  const daysLeft = 60 - t.days_elapsed;
                  return (
                    <tr key={`${t.symbol}-${t.entry_date}-${i}`} style={{ cursor: "pointer" }}
                      onClick={() => router.push(`/stock/${t.symbol}`)}
                      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "#f8faf9"; }}
                      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = ""; }}>
                      <td style={{ ...td, textAlign: "left", fontWeight: 600, color: T.text }}>{t.symbol}</td>
                      <td style={{ ...td, textAlign: "right", color: T.muted }}>{t.entry_date}</td>
                      <td style={{ ...td, textAlign: "right", color: T.muted }}>${t.entry_price.toFixed(2)}</td>
                      <td style={{ ...td, textAlign: "right", color: T.purple, fontWeight: 600 }}>{(t.entry_p10 * 100).toFixed(0)}%</td>
                      <td style={{ ...td, textAlign: "right", color: currG >= 0 ? T.greenPos : T.red, fontWeight: 600 }}>{currG >= 0 ? "+" : ""}{currG.toFixed(1)}%</td>
                      <td style={{ ...td, textAlign: "right", color: hitExpected ? T.greenPos : T.text, fontWeight: hitExpected ? 700 : 400 }}>
                        {hitExpected && "✓ "}+{maxG.toFixed(1)}%
                      </td>
                      <td style={{ ...td, textAlign: "right", color: daysLeft < 10 ? T.amber : T.muted }}>
                        {t.days_elapsed}/60d{daysLeft < 10 && ` (${daysLeft}d left)`}
                      </td>
                      <td style={{ ...td, textAlign: "right", color: T.light, fontSize: 10 }}>
                        {t.hit_date || "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Closed windows */}
      <Card>
        <SH title={`Closed Windows (${closed.length})`} icon={<Clock size={12} />} sub="60 days elapsed or +10% hit" />
        {closed.length === 0 ? (
          <div style={{ padding: 30, textAlign: "center", color: T.light, fontSize: 11, fontFamily: T.mono }}>
            No closed windows yet. Windows close at +10% hit or day 60.
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead><tr>
                {["Symbol", "Entry", "p10", "Max Gain", "Result", "Days to Hit", "Closed"].map((h, i) => (
                  <th key={h} style={{ ...th, textAlign: i === 0 ? "left" : "right" }}>{h}</th>
                ))}
              </tr></thead>
              <tbody>
                {closed.slice().reverse().slice(0, 200).map((t, i) => {
                  const daysToHit = t.hit_date && t.entry_date ? Math.max(0, Math.round((new Date(t.hit_date).getTime() - new Date(t.entry_date).getTime()) / 86400000)) : null;
                  return (
                    <tr key={`${t.symbol}-${t.exit_date}-${i}`}
                      onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "#f8faf9"; }}
                      onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = ""; }}>
                      <td style={{ ...td, textAlign: "left", fontWeight: 600, color: T.text, cursor: "pointer" }} onClick={() => router.push(`/stock/${t.symbol}`)}>{t.symbol}</td>
                      <td style={{ ...td, textAlign: "right", color: T.muted }}>{t.entry_date}</td>
                      <td style={{ ...td, textAlign: "right", color: T.purple, fontWeight: 600 }}>{(t.entry_p10 * 100).toFixed(0)}%</td>
                      <td style={{ ...td, textAlign: "right", color: t.max_gain_pct >= 10 ? T.greenPos : T.red, fontWeight: 700 }}>
                        {t.max_gain_pct >= 0 ? "+" : ""}{t.max_gain_pct.toFixed(1)}%
                      </td>
                      <td style={{ ...td, textAlign: "right" }}>
                        <span style={{ display: "inline-block", padding: "2px 7px", borderRadius: 4, fontSize: 9, fontWeight: 700, fontFamily: T.mono, color: t.hit ? T.greenPos : T.red, background: t.hit ? T.greenLight : T.redLight, border: `1px solid ${t.hit ? T.greenBorder : "#fecaca"}` }}>
                          {t.hit ? "✓ HIT" : "✗ MISS"}
                        </span>
                      </td>
                      <td style={{ ...td, textAlign: "right", color: T.muted }}>{daysToHit != null ? `${daysToHit}d` : "—"}</td>
                      <td style={{ ...td, textAlign: "right", color: T.light, fontSize: 10 }}>{t.exit_date}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// TAB 3: PORTFOLIO vs MODEL (side-by-side)
// ══════════════════════════════════════════════════════════════════════════════
function PortfolioVsModelTab({ router }: { router: ReturnType<typeof useRouter> }) {
  const [myHistory, setMyHistory]   = useState<PortfolioHistoryEntry[]>([]);
  const [midcapHist, setMidcapHist] = useState<StrategyHistory | null>(null);
  const [sp500Hist, setSp500Hist]   = useState<StrategyHistory | null>(null);
  const [loading, setLoading]       = useState(true);

  const [filter, setFilter]         = useState<BucketFilter>("all");
  const [yourPage, setYourPage]     = useState(1);
  const [midcapPage, setMidcapPage] = useState(1);
  const [sp500Page, setSp500Page]   = useState(1);

  useEffect(() => {
    setLoading(true);
    Promise.allSettled([
      fetch(`${GCS_PORTFOLIO}/state.json?t=${Date.now()}`).then(r => r.json()),
      fetch(`${GCS_PERFORMANCE}/strategy_history_midcap.json?t=${Date.now()}`).then(r => r.ok ? r.json() : null),
      fetch(`${GCS_PERFORMANCE}/strategy_history_sp500.json?t=${Date.now()}`).then(r => r.ok ? r.json() : null),
    ]).then(([myRes, midRes, spRes]) => {
      if (myRes.status  === "fulfilled") setMyHistory(myRes.value?.history || []);
      if (midRes.status === "fulfilled") setMidcapHist(midRes.value);
      if (spRes.status  === "fulfilled") setSp500Hist(spRes.value);
      setLoading(false);
    });
  }, []);

  const filteredHistory = useMemo(() => {
    const sorted = [...myHistory].sort((a, b) => (a.date < b.date ? 1 : -1));
    if (filter === "all")      return sorted;
    if (filter === "untagged") return sorted.filter(t => !t.bucket);
    return sorted.filter(t => t.bucket === filter);
  }, [myHistory, filter]);

  const youAlpha = useMemo(() => {
    const calc = (bucket: "midcap" | "sp500") => {
      const yourTrades = myHistory.filter(t => t.bucket === bucket);
      if (yourTrades.length === 0) return null;
      const yourMean = yourTrades.reduce((a, t) => a + t.pnl_pct, 0) / yourTrades.length;
      return { count: yourTrades.length, meanPct: yourMean };
    };
    return { midcap: calc("midcap"), sp500: calc("sp500") };
  }, [myHistory]);

  if (loading) return <Empty icon={<BarChart3 size={36} color={T.divider} />} title="Loading…" />;

  const midWeeks = midcapHist?.weeks || [];
  const spWeeks  = sp500Hist?.weeks  || [];
  const midSummary = midcapHist?.summary;
  const spSummary  = sp500Hist?.summary;

  return (
    <>
      <Card style={{ marginBottom: 16, background: T.greenLight, borderColor: T.greenBorder }}>
        <div style={{ fontSize: 11, fontFamily: T.mono, color: T.text, lineHeight: 1.6 }}>
          <strong>Three-panel view.</strong> Left: your closed trades (tag each by bucket
          when you add it). Center: the midcap basket's weekly closures. Right: SP500.
          Use the alpha banner above to see how your decisions compared to each model.
        </div>
      </Card>

      <AlphaBanner
        midcap={midSummary}
        sp500={spSummary}
        youMidcap={youAlpha.midcap}
        youSp500={youAlpha.sp500}
      />

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>

        {/* PANEL 1 — YOUR CLOSURES */}
        <Card>
          <SH
            title={`Your Closures (${filteredHistory.length})`}
            icon={<TrendingUp size={12} />}
            sub="From portfolio history"
          />
          <div style={{ display: "flex", gap: 5, padding: "8px 12px 6px", flexWrap: "wrap", borderBottom: `1px solid ${T.divider}` }}>
            {(["all","midcap","sp500","untagged"] as BucketFilter[]).map(f => (
              <button key={f} onClick={() => { setFilter(f); setYourPage(1); }}
                style={{
                  padding: "3px 8px", fontSize: 9, fontFamily: T.mono, fontWeight: 600,
                  letterSpacing: "0.05em", textTransform: "uppercase",
                  border: `1px solid ${filter===f ? T.greenBorder : T.border}`,
                  borderRadius: 3, cursor: "pointer",
                  background: filter===f ? T.greenLight : "transparent",
                  color:      filter===f ? T.green : T.muted,
                }}>{f}</button>
            ))}
          </div>

          {filteredHistory.length === 0 ? (
            <div style={{ padding: 24, textAlign: "center", color: T.light, fontSize: 11, fontFamily: T.mono }}>
              {myHistory.length === 0 ? "No closed positions yet." : "No matches for this filter."}
            </div>
          ) : (
            <PaginatedTable
              total={filteredHistory.length}
              page={yourPage}
              setPage={setYourPage}
              header={["Sym", "Bucket", "Entry", "Exit", "P&L", "Days"]}
              rows={filteredHistory.slice((yourPage-1)*PAGE_SIZE, yourPage*PAGE_SIZE).map((t, i) => {
                const pC = t.pnl_pct >= 0 ? T.greenPos : T.red;
                return (
                  <tr key={`${t.symbol}-${t.date}-${i}`}>
                    <td style={{ ...td, textAlign: "left", fontWeight: 600, color: T.text, cursor: "pointer" }}
                        onClick={() => router.push(`/stock/${t.symbol}`)}>
                      {t.symbol}
                    </td>
                    <td style={{ ...td, textAlign: "center" }}>
                      <BucketChip tag={t.bucket || null} />
                    </td>
                    <td style={{ ...td, textAlign: "right", color: T.muted }}>${t.entry_price.toFixed(2)}</td>
                    <td style={{ ...td, textAlign: "right", color: T.text, fontWeight: 600 }}>${t.exit_price.toFixed(2)}</td>
                    <td style={{ ...td, textAlign: "right", fontWeight: 700, color: pC }}>
                      {t.pnl_pct >= 0 ? "+" : ""}{t.pnl_pct.toFixed(1)}%
                    </td>
                    <td style={{ ...td, textAlign: "right", color: T.muted }}>{t.days_held}d</td>
                  </tr>
                );
              })}
            />
          )}
        </Card>

        {/* PANEL 2 — MIDCAP MODEL */}
        <Card>
          <SH
            title={`Midcap Model (${midWeeks.length})`}
            icon={<Target size={12} />}
            sub={midcapHist?.inception_date ? `since ${midcapHist.inception_date.slice(0,10)}` : "weekly basket closures"}
          />
          {midWeeks.length === 0 ? (
            <div style={{ padding: 24, textAlign: "center", color: T.light, fontSize: 11, fontFamily: T.mono }}>
              No closed weeks yet — first one appears after next Monday's basket regenerates.
            </div>
          ) : (
            <PaginatedTable
              total={midWeeks.length}
              page={midcapPage}
              setPage={setMidcapPage}
              header={["Week", "N", "Strat", "SPY", "Alpha"]}
              rows={[...midWeeks].reverse().slice((midcapPage-1)*PAGE_SIZE, midcapPage*PAGE_SIZE).map((w, i) => (
                <tr key={`mid-${w.entry_date}-${i}`}>
                  <td style={{ ...td, textAlign: "left", color: T.text, fontSize: 10 }}>
                    {w.entry_date.slice(5)} → {w.exit_date.slice(5)}
                  </td>
                  <td style={{ ...td, textAlign: "right", color: T.muted }}>{w.n_positions}</td>
                  <td style={{ ...td, textAlign: "right", fontWeight: 700,
                              color: w.basket_return_pct >= 0 ? T.greenPos : T.red }}>
                    {w.basket_return_pct >= 0 ? "+" : ""}{w.basket_return_pct.toFixed(2)}%
                  </td>
                  <td style={{ ...td, textAlign: "right", color: T.muted }}>
                    {w.spy_return_pct >= 0 ? "+" : ""}{w.spy_return_pct.toFixed(2)}%
                  </td>
                  <td style={{ ...td, textAlign: "right", fontWeight: 700,
                              color: w.alpha_pp >= 0 ? T.greenPos : T.red }}>
                    {w.alpha_pp >= 0 ? "+" : ""}{w.alpha_pp.toFixed(2)}pp
                  </td>
                </tr>
              ))}
            />
          )}
        </Card>

        {/* PANEL 3 — SP500 MODEL */}
        <Card>
          <SH
            title={`SP500 Model (${spWeeks.length})`}
            icon={<Target size={12} />}
            sub={sp500Hist?.inception_date ? `since ${sp500Hist.inception_date.slice(0,10)}` : "weekly basket closures"}
          />
          {spWeeks.length === 0 ? (
            <div style={{ padding: 24, textAlign: "center", color: T.light, fontSize: 11, fontFamily: T.mono }}>
              No closed weeks yet — first one appears after next Sunday's scheduled scan.
            </div>
          ) : (
            <PaginatedTable
              total={spWeeks.length}
              page={sp500Page}
              setPage={setSp500Page}
              header={["Week", "N", "Strat", "SPY", "Alpha"]}
              rows={[...spWeeks].reverse().slice((sp500Page-1)*PAGE_SIZE, sp500Page*PAGE_SIZE).map((w, i) => (
                <tr key={`sp-${w.entry_date}-${i}`}>
                  <td style={{ ...td, textAlign: "left", color: T.text, fontSize: 10 }}>
                    {w.entry_date.slice(5)} → {w.exit_date.slice(5)}
                  </td>
                  <td style={{ ...td, textAlign: "right", color: T.muted }}>{w.n_positions}</td>
                  <td style={{ ...td, textAlign: "right", fontWeight: 700,
                              color: w.basket_return_pct >= 0 ? T.greenPos : T.red }}>
                    {w.basket_return_pct >= 0 ? "+" : ""}{w.basket_return_pct.toFixed(2)}%
                  </td>
                  <td style={{ ...td, textAlign: "right", color: T.muted }}>
                    {w.spy_return_pct >= 0 ? "+" : ""}{w.spy_return_pct.toFixed(2)}%
                  </td>
                  <td style={{ ...td, textAlign: "right", fontWeight: 700,
                              color: w.alpha_pp >= 0 ? T.greenPos : T.red }}>
                    {w.alpha_pp >= 0 ? "+" : ""}{w.alpha_pp.toFixed(2)}pp
                  </td>
                </tr>
              ))}
            />
          )}
        </Card>
      </div>
    </>
  );
}

// ── Helper components for the 3-panel view ────────────────────────────────
function AlphaBanner({
  midcap, sp500, youMidcap, youSp500,
}: {
  midcap?: StrategyHistory["summary"];
  sp500?:  StrategyHistory["summary"];
  youMidcap: { count: number; meanPct: number } | null;
  youSp500:  { count: number; meanPct: number } | null;
}) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 16 }}>
      <BucketAlphaCard label="MIDCAP" modelSummary={midcap} you={youMidcap} expected={EXPECTED_ANNUAL_ALPHA.midcap} />
      <BucketAlphaCard label="SP500"  modelSummary={sp500}  you={youSp500}  expected={EXPECTED_ANNUAL_ALPHA.sp500} />
    </div>
  );
}

function BucketAlphaCard({
  label, modelSummary, you, expected,
}: {
  label: string;
  modelSummary?: StrategyHistory["summary"];
  you: { count: number; meanPct: number } | null;
  expected: number;
}) {
  const modelCumAlpha = modelSummary?.cum_alpha_pp ?? 0;
  const modelAnnAlpha = modelSummary?.annualized_alpha_pp ?? 0;
  const modelWeeks    = modelSummary?.weeks_closed ?? 0;
  const modelWinRate  = modelSummary?.win_rate ?? 0;
  const onTrack = modelWeeks > 0 && modelAnnAlpha >= expected * 0.7;
  const accent  = modelWeeks === 0 ? T.muted : (onTrack ? T.greenPos : T.amber);

  return (
    <div style={{
      background: "white", border: `1px solid ${T.border}`, borderRadius: 8,
      padding: 14, position: "relative", overflow: "hidden",
    }}>
      <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 3, background: accent }} />

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
        <div>
          <span style={{ fontSize: 10, fontFamily: T.mono, fontWeight: 700, letterSpacing: "0.1em", color: T.muted }}>{label}</span>
          <span style={{ marginLeft: 8, fontSize: 10, fontFamily: T.mono, color: T.light }}>
            {modelWeeks > 0 ? `${modelWeeks} weeks closed` : "no closed weeks yet"}
          </span>
        </div>
        <span style={{
          fontSize: 9, padding: "2px 7px", borderRadius: 3, fontFamily: T.mono,
          fontWeight: 700, letterSpacing: "0.05em",
          background: modelWeeks === 0 ? T.divider : (onTrack ? T.greenLight : T.amberLight),
          color:      modelWeeks === 0 ? T.muted   : (onTrack ? T.green       : T.amber),
          border: `1px solid ${modelWeeks === 0 ? T.border : (onTrack ? T.greenBorder : "#fde68a")}`,
        }}>
          {modelWeeks === 0 ? "PENDING" : (onTrack ? "ON TRACK" : "BELOW EXP")}
        </span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 10 }}>
        <StatBlock
          label="Model cum α"
          value={`${modelCumAlpha >= 0 ? "+" : ""}${modelCumAlpha.toFixed(2)}pp`}
          sub={modelWinRate ? `${(modelWinRate*100).toFixed(0)}% wins` : "—"}
          color={modelCumAlpha >= 0 ? T.greenPos : T.red}
        />
        <StatBlock
          label="Model ann. α"
          value={`${modelAnnAlpha >= 0 ? "+" : ""}${modelAnnAlpha.toFixed(1)}pp`}
          sub={`expected +${expected}pp/yr`}
          color={modelAnnAlpha >= 0 ? T.greenPos : T.red}
        />
        <StatBlock
          label="Your tagged"
          value={you ? `${you.meanPct >= 0 ? "+" : ""}${you.meanPct.toFixed(1)}%` : "—"}
          sub={you ? `${you.count} closed` : "tag trades to compare"}
          color={you ? (you.meanPct >= 0 ? T.greenPos : T.red) : T.muted}
        />
      </div>
    </div>
  );
}

function StatBlock({
  label, value, sub, color,
}: { label: string; value: string; sub?: string; color: string }) {
  return (
    <div>
      <div style={{ fontSize: 8, fontFamily: T.mono, fontWeight: 600, letterSpacing: "0.1em", color: T.muted, textTransform: "uppercase" }}>
        {label}
      </div>
      <div style={{ marginTop: 2, fontSize: 16, fontFamily: T.mono, fontWeight: 700, color }}>
        {value}
      </div>
      {sub && (
        <div style={{ marginTop: 1, fontSize: 9, fontFamily: T.mono, color: T.light }}>{sub}</div>
      )}
    </div>
  );
}

function BucketChip({ tag }: { tag: BucketTag }) {
  if (!tag) {
    return (
      <span style={{
        fontSize: 8, padding: "1px 5px", borderRadius: 3, fontFamily: T.mono,
        background: T.divider, color: T.light, border: `1px solid ${T.border}`,
        fontWeight: 600, letterSpacing: "0.05em",
      }}>—</span>
    );
  }
  const isMid = tag === "midcap";
  return (
    <span style={{
      fontSize: 8, padding: "1px 5px", borderRadius: 3, fontFamily: T.mono,
      fontWeight: 700, letterSpacing: "0.05em", textTransform: "uppercase",
      background: isMid ? T.greenLight  : "#eef2ff",
      color:      isMid ? T.green       : "#4338ca",
      border: `1px solid ${isMid ? T.greenBorder : "#c7d2fe"}`,
    }}>{tag}</span>
  );
}

function PaginatedTable({
  total, page, setPage, header, rows,
}: {
  total: number;
  page: number;
  setPage: (n: number) => void;
  header: string[];
  rows: React.ReactNode;
}) {
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  return (
    <>
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              {header.map((h, i) => (
                <th key={h} style={{
                  ...th,
                  textAlign: i === 0 ? "left" : (header[i] === "Bucket" ? "center" : "right"),
                }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
      {totalPages > 1 && (
        <div style={{
          padding: "8px 12px", borderTop: `1px solid ${T.divider}`,
          display: "flex", justifyContent: "space-between", alignItems: "center",
          fontSize: 10, fontFamily: T.mono, color: T.muted,
        }}>
          <span>page {page} / {totalPages} · {total} total</span>
          <span style={{ display: "flex", gap: 4 }}>
            <button onClick={() => setPage(Math.max(1, page-1))} disabled={page === 1}
              style={pageBtnStyle(page === 1)}>‹ prev</button>
            <button onClick={() => setPage(Math.min(totalPages, page+1))} disabled={page === totalPages}
              style={pageBtnStyle(page === totalPages)}>next ›</button>
          </span>
        </div>
      )}
    </>
  );
}

function pageBtnStyle(disabled: boolean): React.CSSProperties {
  return {
    padding: "2px 8px", fontSize: 10, fontFamily: T.mono, fontWeight: 600,
    border: `1px solid ${T.border}`, borderRadius: 3,
    background: disabled ? T.divider : "white",
    color: disabled ? T.light : T.muted,
    cursor: disabled ? "not-allowed" : "pointer",
  };
}

// ══════════════════════════════════════════════════════════════════════════════
// Shell
// ══════════════════════════════════════════════════════════════════════════════
export default function Performance() {
  const router = useRouter();
  const [tab, setTab] = useState<"signal" | "hitrate" | "compare">("signal");

  return (
    <div style={{ padding: "16px 20px", maxWidth: 1400, margin: "0 auto" }}>
      {/* Header */}
      <div style={{ marginBottom: 16, paddingBottom: 10, borderBottom: `1px solid ${T.border}` }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
          <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: "0.1em", color: T.text, fontFamily: T.mono }}>PERFORMANCE</span>
          <span style={{ fontSize: 12, color: T.muted, fontFamily: T.mono }}>/ tracking</span>
        </div>
        <p style={{ fontSize: 10, color: T.muted, fontFamily: T.mono, marginTop: 4 }}>
          Forward-only tracking from v7.2 deploy. System 1: composite model. System 2: ML time model.
        </p>
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 6, marginBottom: 16, borderBottom: `1px solid ${T.divider}`, paddingBottom: 2 }}>
        {[
          { key: "signal",  label: "Signal Performance", icon: <TrendingUp size={12} /> },
          { key: "hitrate", label: "P(+10%) Hit Rate",   icon: <Target size={12} /> },
          { key: "compare", label: "Portfolio vs Model", icon: <BarChart3 size={12} /> },
        ].map(({ key, label, icon }) => (
          <button key={key} onClick={() => setTab(key as "signal" | "hitrate" | "compare")}
            style={{
              display: "flex", alignItems: "center", gap: 5, padding: "7px 16px", fontSize: 12,
              fontFamily: T.mono, fontWeight: 600, border: "none", borderRadius: 6,
              cursor: "pointer",
              background: tab === key ? T.greenLight : "transparent",
              color:      tab === key ? T.green : T.muted,
              transition: "all 0.15s",
            }}>
            {icon} {label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {tab === "signal"  && <SignalPerfTab router={router} />}
      {tab === "hitrate" && <HitRateTab router={router} />}
      {tab === "compare" && <PortfolioVsModelTab router={router} />}
    </div>
  );
}
