"use client";
import { useState, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { TrendingUp, TrendingDown, BarChart3, Target, Clock, Radio, ExternalLink, Award } from "lucide-react";


// ── Data sources ────────────────────────────────────────────────────────────
const SIGNAL_TRACKS = "/api/performance/signal-tracks";
const HIT_RATES     = "/api/performance/hit-rates";
const GCS_PERFORMANCE = "/api/gcs/performance";
// v1.2 (May 2026): cycles data is written directly to GCS by signal_tracker.py
// and read via the standard /api/gcs proxy — no backend bridge needed.
const GCS_CYCLES_ROOT = "/api/gcs/hit_rate_tracking";

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

// ── v1.2 cycles types — matches signal_tracker.py output ──────────────────
interface CycleState {
  collecting_cycle_id: string | null;
  collecting_start: string | null;
  collecting_ends: string | null;
  resolving_cycle_ids: string[];
  archived_cycle_ids: string[];
}
interface RollingHealth {
  computed_date: string | null;
  window_days: number;
  d10_n: number; d10_hits: number; d10_hit_rate: number;
  d1_n: number;  d1_hits: number;  d1_hit_rate: number;
  baseline_d10: number; baseline_d1: number;
  kill_switch_threshold: number;
  kill_switch_active: boolean;
  status: "HEALTHY" | "DEGRADED" | "UNDER_SAMPLED" | "NOT_YET_COMPUTED";
}
interface Prediction {
  symbol: string; entry_date: string; cycle_id: string; region: string;
  entry_price: number; target_price: number; fate_window_ends: string;
  p20: number; decile: number; signal_strength: string;
  mode_qualifications: string[];
  composite?: number; sector?: string; country?: string; market_cap?: number;
  ivr_at_entry?: number; iv_at_entry?: number;
  outcome: "OPEN" | "HIT" | "EXPIRED";
  max_high_observed_pct: number;
  max_drawdown_observed_pct: number;
  current_price: number;
  last_updated: string; days_observed: number;
  realized_return_pct?: number | null;
  realized_contract_pnl?: number | null;
  resolution_date?: string;
  // Optional EV/spread block — absent on rows that couldn't synthesize a spread
  is_live_spread?: boolean;
  long_strike?: number; short_strike?: number;
  net_debit?: number;
  max_gain_per_contract?: number; max_loss_per_contract?: number;
  break_even_price?: number; break_even_move_pct?: number;
  p_breakeven?: number; p_max_profit?: number;
  ev_dollars?: number; ev_per_dollar?: number;
  assessment?: string;
}
interface CycleSummary {
  cycle_id: string; archived_date: string;
  total_predictions: number;
  hit_count: number; expired_count: number; hit_rate: number;
  mean_realized_return_pct: number;
  mean_max_runup_pct: number; mean_max_drawdown_pct: number;
  best_runup_pct: number; worst_drawdown_pct: number;
  aggregate_ev_dollars: number; aggregate_realized_pnl_dollars: number;
  ev_realization_ratio: number;
  hit_rate_by_decile: Record<string, { n: number; hits: number; hit_rate: number }>;
  hit_rate_by_signal_strength: Record<string, { n: number; hits: number; hit_rate: number }>;
  calibration_check: {
    d10_hit_rate: number; d10_n: number; d1_hit_rate: number; d1_n: number;
    d10_baseline: number; d1_baseline: number;
    observed_odds_ratio: number | null; baseline_odds_ratio: number;
    kill_switch_threshold: number; healthy: boolean;
  };
  predictions: Prediction[];
}
// ── BORING strategy tracker ────────────────────────────────────────────────
interface BoringPosition {
  symbol: string;
  entry: number;
  exit: number | null;
  return_pct: number | null;
}
interface BoringWeekClosed {
  entry_date: string;
  exit_date: string;
  n_positions: number;
  basket_return_pct: number;
  spy_return_pct: number;
  alpha_pp: number;
  spy_entry_price: number;
  spy_exit_price: number;
  positions: BoringPosition[];
}
interface BoringWeeklyMark {
  date: string;
  basket_return_pct: number;
  spy_return_pct: number;
  alpha_pp: number;
  spy_price: number;
  days_held: number;
  n_priced: number;
}
interface BoringDailyMark {
  price: number;
  return_pct: number;
  ts: string;
}
interface BoringInterimMark {
  date: string;
  basket_return_pct: number;
  spy_return_pct: number;
  alpha_pp: number;
  spy_price: number | null;
  days_held: number;
  n_priced: number;
}
interface BoringOpenBasket {
  scan_date: string;
  inception_date: string;
  scheduled_exit_date: string;
  spy_entry_price: number;
  basket: {
    symbol: string;
    entry_price: number;
    ps_ratio_at_entry: number;
    piotroski_at_entry: number;
  }[];
  weekly_marks: BoringWeeklyMark[];
  daily_last_marks?: Record<string, BoringDailyMark>;
  today_interim_mark?: BoringInterimMark;
}
interface BoringHistory {
  region: string;
  strategy_version: string;
  inception_date: string | null;
  open_basket: BoringOpenBasket | null;
  weeks: BoringWeekClosed[];
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
  last_monitor_run?: string;
}
// ── COMPOSITE / MOMENTUM / FA strategy tracker ─────────────────────────────
interface CompositePosition {
  symbol: string;
  entry_price: number;
  entry_date: string;
  // Mode-appropriate entry score. Mom/FA baskets write composite_at_entry
  // (the v8 5-factor composite); Compounder baskets write
  // compounder_score_at_entry (the equal-weight rank percentile from ROE/PB/
  // OpMΔ). Whichever is present is the one to display; the helper at the
  // render site resolves to a single number.
  composite_at_entry?: number;
  compounder_score_at_entry?: number;
  compounder_rank_at_entry?: number | null;
  piotroski_at_entry: number | null;
  last_price: number;
  last_marked: string;
  return_pct: number;
}
interface CompositeRotation {
  date: string;
  n_removed: number;
  n_added: number;
  removed: {
    symbol: string;
    entry_price: number;
    exit_price: number;
    entry_date: string;
    exit_date: string;
    return_pct: number;
    days_held: number;
    composite_at_entry?: number | null;
    compounder_score_at_entry?: number | null;
  }[];
  added: {
    symbol: string;
    entry_price: number;
    composite_at_entry?: number;
    compounder_score_at_entry?: number;
  }[];
}
interface CompositeWeeklyMark {
  date: string;
  basket_avg_return_pct: number;
  spy_return_pct: number;
  alpha_pp: number;
  spy_price: number;
  n_positions: number;
  days_since_inception: number;
}
interface CompositeHistory {
  region: string;
  strategy_version: string;
  inception_date: string | null;
  spy_inception_price: number | null;
  current_basket: CompositePosition[];
  rotations: CompositeRotation[];
  weekly_marks: CompositeWeeklyMark[];
  summary: {
    weeks_tracked: number;
    n_positions_open: number;
    n_rotations: number;
    n_positions_closed: number;
    open_avg_return_pct: number;
    realized_avg_return_pct: number;
    realized_wins: number;
    realized_win_rate: number;
    cum_basket_return_pct: number;
    cum_spy_return_pct: number;
    cum_alpha_pp: number;
    annualized_return_pct: number;
    annualized_alpha_pp: number;
  } | null;
  updated_at: string | null;
  last_monitor_run?: string;
}
// ── Theme ───────────────────────────────────────────────────────────────────
const T = {
  text: "#1a1a1a", muted: "#6b7280", light: "#9ca3af",
  green: "#2d7a4f", greenPos: "#10b981", greenLight: "#e8f5ee", greenBorder: "#b8dcc8",
  red: "#ef4444", redLight: "#fef2f2",
  amber: "#d97706", amberLight: "#fffbeb",
  purple: "#8b5cf6",
  blue: "#3b82f6",
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
// TAB 1: SIGNAL PERFORMANCE
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
      {stats && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 10, marginBottom: 20 }}>
          <KPI label="OPEN" value={String(open.length)} sub="Currently tracking" />
          <KPI label="CLOSED CYCLES" value={String(stats.total)} sub={`Best: ${stats.best?.symbol ?? "—"} ${stats.best ? `${stats.best.realized_pnl_pct >= 0 ? "+" : ""}${stats.best.realized_pnl_pct.toFixed(1)}%` : ""}`} />
          <KPI label="WIN RATE" value={`${stats.win_rate.toFixed(0)}%`} color={stats.win_rate >= 50 ? T.greenPos : T.red} sub={`Worst: ${stats.worst?.symbol ?? "—"} ${stats.worst ? `${stats.worst.realized_pnl_pct.toFixed(1)}%` : ""}`} />
          <KPI label="AVG P&L" value={`${stats.avg_pnl >= 0 ? "+" : ""}${stats.avg_pnl.toFixed(1)}%`} color={stats.avg_pnl >= 0 ? T.greenPos : T.red} sub={`Avg hold: ${stats.avg_days.toFixed(0)}d`} />
          <KPI label="AVG ANNUALIZED" value={`${stats.avg_ann >= 0 ? "+" : ""}${stats.avg_ann.toFixed(0)}%`} color={stats.avg_ann >= 0 ? T.greenPos : T.red} sub={`${stats.total} closed cycles`} />
        </div>
      )}

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
// TAB 3: STRATEGIES (BORING + COMPOSITE + MOMENTUM + FALLEN ANGEL)
// ══════════════════════════════════════════════════════════════════════════════
function StrategiesTab() {
  // ── ALL HOOKS FIRST — Rules of Hooks: no early returns before all hooks called ─
  // v1.2 (May 2026): BORING and COMPOSITE retired; replaced by COMPOUNDER US
  // and COMPOUNDER GLOBAL. Old runners' history JSONs preserved in GCS but
  // no longer fetched here. The 4-card grid below maps to the 4 active
  // strategies: Compounder US / Compounder Global / Momentum / Fallen Angel.
  const [compounderUs, setCompounderUs] = useState<CompositeHistory | null>(null);
  const [compounderGlobal, setCompounderGlobal] = useState<CompositeHistory | null>(null);
  const [momentum, setMomentum] = useState<CompositeHistory | null>(null);
  const [fa, setFa] = useState<CompositeHistory | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.allSettled([
      fetch(`${GCS_PERFORMANCE}/strategy_history_compounder_us.json?t=${Date.now()}`)
        .then(r => r.ok ? r.json() : null),
      fetch(`${GCS_PERFORMANCE}/strategy_history_compounder_global.json?t=${Date.now()}`)
        .then(r => r.ok ? r.json() : null),
      fetch(`${GCS_PERFORMANCE}/strategy_history_momentum.json?t=${Date.now()}`)
        .then(r => r.ok ? r.json() : null),
      fetch(`${GCS_PERFORMANCE}/strategy_history_fa.json?t=${Date.now()}`)
        .then(r => r.ok ? r.json() : null),
    ]).then(([cu, cg, m, f]) => {
      if (cu.status === "fulfilled") setCompounderUs(cu.value);
      if (cg.status === "fulfilled") setCompounderGlobal(cg.value);
      if (m.status === "fulfilled") setMomentum(m.value);
      if (f.status === "fulfilled") setFa(f.value);
      setLoading(false);
    });
  }, []);

  // v1.2 (May 2026): BORING-specific today_interim_mark merge logic removed.
  // BORING strategy retired. The remaining 4 strategies (Compounder US/Global,
  // Momentum, Fallen Angel) all use the standard CompositeHistory shape with
  // weekly_marks — no interim daily marks. If interim marks become needed
  // for any compounder strategy later, restore that pattern here.

  // ── Early returns AFTER all hooks ──────────────────────────────────────
  if (loading) {
    return <Empty icon={<BarChart3 size={36} color={T.divider} />} title="Loading…" />;
  }

  if (!compounderUs && !compounderGlobal && !momentum && !fa) {
    return (
      <Empty
        icon={<BarChart3 size={36} color={T.divider} />}
        title="No strategies running"
        sub="Strategy histories will appear here after the runners execute on Friday."
      />
    );
  }

  const fmtPct = (v: number | null | undefined, dp = 2) =>
    v === null || v === undefined ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(dp)}%`;
  const fmtPp = (v: number | null | undefined, dp = 2) =>
    v === null || v === undefined ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(dp)}pp`;

  // v1.2: 4 active strategies — Compounder US, Compounder Global, Momentum, FA
  const chartPoints = buildCombinedChart(compounderUs, compounderGlobal, momentum, fa);

  return (
    <>
      {/* Hero / methodology */}
      <Card style={{ marginBottom: 16, background: T.greenLight, borderColor: T.greenBorder }}>
        <div style={{ fontSize: 11, fontFamily: T.mono, color: T.text, lineHeight: 1.6 }}>
          Four paper-tracked strategies, all global universe, equal-weighted top-10:
          {" "}<strong>COMPOUNDER US</strong> (US-listed exchange-based, 3y-ROE × P/B × OpM-delta, weekly rotation) ·
          {" "}<strong>COMPOUNDER GLOBAL</strong> (global ex Fin/Ins/HC, same scoring, weekly rotation) ·
          {" "}<strong>MOMENTUM</strong> (top by composite_momentum, weekly rotation) ·
          {" "}<strong>FALLEN ANGEL</strong> (FA-flag qualifiers: rev&gt;15% + RSI&lt;40 + composite&lt;0.50, weekly rotation, can be empty).
          Compared against SPY. Prices refreshed daily Mon–Fri after US close.
        </div>
      </Card>

      {/* 4 KPI cards — v1.2: BORING + COMPOSITE retired, replaced by CMP-US + CMP-Global */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 16 }}>
        <StrategyKPICard
          title="COMPOUNDER US"
          subtitle="weekly rotation · 3y-ROE rank"
          inception={compounderUs?.inception_date}
          summary={compounderUs?.summary ? {
            cycles: compounderUs.summary.n_rotations,
            cum_alpha: compounderUs.summary.cum_alpha_pp,
            ann_return: compounderUs.summary.cum_basket_return_pct,
            win_rate: compounderUs.summary.realized_win_rate * 100,
            cyclesLabel: "rotations",
            winRateLabel: "of closed positions",
            annReturnLabel: "BASKET RTN",
          } : null}
          marks={compounderUs?.weekly_marks?.map(m => ({
            date: m.date,
            basket_return_pct: m.basket_avg_return_pct,
            spy_return_pct: m.spy_return_pct,
            alpha_pp: m.alpha_pp,
          }))}
          openCount={compounderUs?.current_basket?.length ?? 0}
        />
        <StrategyKPICard
          title="COMPOUNDER GLOBAL"
          subtitle="weekly rotation · 3y-ROE rank"
          inception={compounderGlobal?.inception_date}
          summary={compounderGlobal?.summary ? {
            cycles: compounderGlobal.summary.n_rotations,
            cum_alpha: compounderGlobal.summary.cum_alpha_pp,
            ann_return: compounderGlobal.summary.cum_basket_return_pct,
            win_rate: compounderGlobal.summary.realized_win_rate * 100,
            cyclesLabel: "rotations",
            winRateLabel: "of closed positions",
            annReturnLabel: "BASKET RTN",
          } : null}
          marks={compounderGlobal?.weekly_marks?.map(m => ({
            date: m.date,
            basket_return_pct: m.basket_avg_return_pct,
            spy_return_pct: m.spy_return_pct,
            alpha_pp: m.alpha_pp,
          }))}
          openCount={compounderGlobal?.current_basket?.length ?? 0}
        />
        <StrategyKPICard
          title="MOMENTUM"
          subtitle="weekly rotation · momentum rank"
          inception={momentum?.inception_date}
          summary={momentum?.summary ? {
            cycles: momentum.summary.n_rotations,
            cum_alpha: momentum.summary.cum_alpha_pp,
            ann_return: momentum.summary.cum_basket_return_pct,
            win_rate: momentum.summary.realized_win_rate * 100,
            cyclesLabel: "rotations",
            winRateLabel: "of closed positions",
            annReturnLabel: "BASKET RTN",
          } : null}
          marks={momentum?.weekly_marks?.map(m => ({
            date: m.date,
            basket_return_pct: m.basket_avg_return_pct,
            spy_return_pct: m.spy_return_pct,
            alpha_pp: m.alpha_pp,
          }))}
          openCount={momentum?.current_basket?.length ?? 0}
        />
        <StrategyKPICard
          title="FALLEN ANGEL"
          subtitle="weekly rotation · FA flag"
          inception={fa?.inception_date}
          summary={fa?.summary ? {
            cycles: fa.summary.n_rotations,
            cum_alpha: fa.summary.cum_alpha_pp,
            ann_return: fa.summary.cum_basket_return_pct,
            win_rate: fa.summary.realized_win_rate * 100,
            cyclesLabel: "rotations",
            winRateLabel: "of closed positions",
            annReturnLabel: "BASKET RTN",
          } : null}
          marks={fa?.weekly_marks?.map(m => ({
            date: m.date,
            basket_return_pct: m.basket_avg_return_pct,
            spy_return_pct: m.spy_return_pct,
            alpha_pp: m.alpha_pp,
          }))}
          openCount={fa?.current_basket?.length ?? 0}
        />
      </div>

      {/* Combined chart */}
      {chartPoints.length > 1 && (
        <Card style={{ marginBottom: 16 }}>
          <SH title="CUMULATIVE RETURN — 4 STRATEGIES vs SPY" icon={<TrendingUp size={11} />} />
          <CombinedCumulativeChart points={chartPoints} />
        </Card>
      )}

      {/* Compounder US details — current basket + closed cycles */}
      {compounderUs && compounderUs.current_basket && compounderUs.current_basket.length > 0 && (
        <BasketDetails
          title="COMPOUNDER US · CURRENT BASKET"
          inception={compounderUs.inception_date}
          rotations={compounderUs.summary?.n_rotations ?? 0}
          basket={compounderUs.current_basket}
          fmtPct={fmtPct}
        />
      )}
      {compounderUs?.rotations && compounderUs.rotations.length > 0 && (
        <RotationsTable
          title={`COMPOUNDER US · ROTATIONS (${compounderUs.rotations.length})`}
          rotations={compounderUs.rotations}
          fmtPct={fmtPct}
        />
      )}

      {/* Compounder Global details */}
      {compounderGlobal && compounderGlobal.current_basket && compounderGlobal.current_basket.length > 0 && (
        <BasketDetails
          title="COMPOUNDER GLOBAL · CURRENT BASKET"
          inception={compounderGlobal.inception_date}
          rotations={compounderGlobal.summary?.n_rotations ?? 0}
          basket={compounderGlobal.current_basket}
          fmtPct={fmtPct}
        />
      )}
      {compounderGlobal?.rotations && compounderGlobal.rotations.length > 0 && (
        <RotationsTable
          title={`COMPOUNDER GLOBAL · ROTATIONS (${compounderGlobal.rotations.length})`}
          rotations={compounderGlobal.rotations}
          fmtPct={fmtPct}
        />
      )}

      {/* ── BORING + COMPOSITE retired v1.2 (May 2026) ──────────────────────
          JSON history files preserved in GCS (strategy_history_boring.json,
          strategy_history_composite.json) but no longer fetched here. To
          revive: re-add the useState/useEffect calls at the top of this
          function and the corresponding detail panels below. ──────── */}

      {/* MOMENTUM details */}
      {momentum && momentum.current_basket && momentum.current_basket.length > 0 && (
        <BasketDetails
          title="MOMENTUM · CURRENT BASKET"
          inception={momentum.inception_date}
          rotations={momentum.summary?.n_rotations ?? 0}
          basket={momentum.current_basket}
          fmtPct={fmtPct}
        />
      )}
      {momentum && momentum.rotations && momentum.rotations.length > 0 && (
        <RotationsTable
          title={`MOMENTUM · ROTATIONS (${momentum.rotations.length})`}
          rotations={momentum.rotations}
          fmtPct={fmtPct}
        />
      )}

      {/* FALLEN ANGEL details */}
      {fa && fa.current_basket && fa.current_basket.length > 0 && (
        <BasketDetails
          title="FALLEN ANGEL · CURRENT BASKET"
          inception={fa.inception_date}
          rotations={fa.summary?.n_rotations ?? 0}
          basket={fa.current_basket}
          fmtPct={fmtPct}
        />
      )}
      {fa && fa.current_basket && fa.current_basket.length === 0 && fa.inception_date && (
        <Card style={{ marginBottom: 16 }}>
          <SH
            title="FALLEN ANGEL · NO POSITIONS"
            icon={<Target size={11} />}
            sub={`Inception ${fa.inception_date} · waiting for FA gate qualifiers`}
          />
          <div style={{ padding: "12px 4px", fontSize: 11, fontFamily: T.mono, color: T.muted }}>
            No stocks currently pass the FA gate (drawdown {">"} 35%, Pio≥7, Altman {">"} 2.5,
            ROE {">"} 12%, mkt cap {">"} $2B). Sitting in cash. Strategy retries each Friday.
          </div>
        </Card>
      )}
      {fa && fa.rotations && fa.rotations.length > 0 && (
        <RotationsTable
          title={`FALLEN ANGEL · ROTATIONS (${fa.rotations.length})`}
          rotations={fa.rotations}
          fmtPct={fmtPct}
        />
      )}
    </>
  );
}

// ── BORING basket table ─ DEPRECATED v1.2 (May 2026) ────────────────────
// BORING strategy retired. Component kept for revival reference but not
// referenced anywhere. Safe to delete in a follow-up cleanup.
function BoringBasketTable({
  basket, dailyMarks, interimMark, spyEntryPrice,
}: {
  basket: BoringOpenBasket["basket"];
  dailyMarks: Record<string, BoringDailyMark> | undefined;
  interimMark: BoringInterimMark | undefined;
  spyEntryPrice: number;
}) {
  const fmtPct = (v: number | null | undefined, dp = 2) =>
    v === null || v === undefined ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(dp)}%`;
  const fmtPp = (v: number | null | undefined, dp = 2) =>
    v === null || v === undefined ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(dp)}pp`;
  const hasDaily = dailyMarks && Object.keys(dailyMarks).length > 0;

  return (
    <>
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={th}>#</th>
            <th style={{ ...th, textAlign: "left" }}>Symbol</th>
            <th style={{ ...th, textAlign: "right" }}>Entry</th>
            {hasDaily && <th style={{ ...th, textAlign: "right" }}>Last</th>}
            {hasDaily && <th style={{ ...th, textAlign: "right" }}>Return</th>}
            <th style={{ ...th, textAlign: "right" }}>P/S</th>
            <th style={{ ...th, textAlign: "right" }}>Pio</th>
          </tr>
        </thead>
        <tbody>
          {basket.map((p, i) => {
            const dm = dailyMarks?.[p.symbol];
            return (
              <tr key={p.symbol}>
                <td style={{ ...td, color: T.muted }}>{i + 1}</td>
                <td style={{ ...td, fontWeight: 600 }}>                   <a href={`/stock/${p.symbol}`} style={{ color: T.text, textDecoration: "none" }}>                     {p.symbol}                   </a>                 </td>
                <td style={{ ...td, textAlign: "right" }}>${p.entry_price.toFixed(2)}</td>
                {hasDaily && (
                  <td style={{ ...td, textAlign: "right", color: T.text, fontWeight: 600 }}>
                    {dm ? `$${dm.price.toFixed(2)}` : "—"}
                  </td>
                )}
                {hasDaily && (
                  <td style={{
                    ...td, textAlign: "right",
                    color: dm ? (dm.return_pct >= 0 ? T.green : T.red) : T.muted,
                    fontWeight: 600,
                  }}>
                    {dm ? fmtPct(dm.return_pct) : "—"}
                  </td>
                )}
                <td style={{ ...td, textAlign: "right" }}>{p.ps_ratio_at_entry.toFixed(2)}</td>
                <td style={{ ...td, textAlign: "right" }}>{p.piotroski_at_entry}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {interimMark && (
        <div style={{
          fontSize: 10, fontFamily: T.mono, color: T.muted,
          marginTop: 10, paddingTop: 8, borderTop: `1px solid ${T.divider}`,
        }}>
          Today's interim mark ({interimMark.date}, day {interimMark.days_held}/182):
          basket {fmtPct(interimMark.basket_return_pct)} ·
          {" "}SPY {fmtPct(interimMark.spy_return_pct)} ·
          {" "}alpha{" "}
          <span style={{ color: interimMark.alpha_pp >= 0 ? T.green : T.red, fontWeight: 700 }}>
            {fmtPp(interimMark.alpha_pp)}
          </span>
          {" "}(refreshes daily, weekly mark every Friday)
        </div>
      )}
    </>
  );
}

// ── Helpers — composite/momentum/fa table ──────────────────────────────
function BasketDetails({
  title, inception, rotations, basket, fmtPct,
}: {
  title: string;
  inception: string | null | undefined;
  rotations: number;
  basket: CompositePosition[];
  fmtPct: (v: number | null | undefined, dp?: number) => string;
}) {
  return (
    <Card style={{ marginBottom: 16 }}>
      <SH
        title={title}
        icon={<Target size={11} />}
        sub={`Inception ${inception ?? "—"} · ${rotations} rotations`}
      />
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={th}>#</th>
            <th style={{ ...th, textAlign: "left" }}>Symbol</th>
            <th style={{ ...th, textAlign: "right" }}>Entry</th>
            <th style={{ ...th, textAlign: "right" }}>Last</th>
            <th style={{ ...th, textAlign: "right" }}>Return</th>
            <th style={{ ...th, textAlign: "right" }}>Days</th>
            <th style={{ ...th, textAlign: "right" }}>Score@entry</th>
          </tr>
        </thead>
        <tbody>
          {basket.map((p, i) => {
            const daysHeld = Math.floor(
              (Date.now() - new Date(p.entry_date).getTime()) / (1000 * 60 * 60 * 24)
            );
            return (
              <tr key={p.symbol}>
                <td style={{ ...td, color: T.muted }}>{i + 1}</td>
                <td style={{ ...td, fontWeight: 600 }}>                   <a href={`/stock/${p.symbol}`} style={{ color: T.text, textDecoration: "none" }}>                     {p.symbol}                   </a>                 </td>
                <td style={{ ...td, textAlign: "right" }}>${p.entry_price.toFixed(2)}</td>
                <td style={{ ...td, textAlign: "right" }}>${(p.last_price ?? p.entry_price).toFixed(2)}</td>
                <td style={{
                  ...td, textAlign: "right",
                  color: (p.return_pct ?? 0) >= 0 ? T.green : T.red, fontWeight: 600,
                }}>{fmtPct(p.return_pct)}</td>
                <td style={{ ...td, textAlign: "right", color: T.muted }}>{daysHeld}d</td>
                <td style={{ ...td, textAlign: "right" }}>{(p.composite_at_entry ?? p.compounder_score_at_entry ?? 0).toFixed(3)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Card>
  );
}

function RotationsTable({
  title, rotations, fmtPct,
}: {
  title: string;
  rotations: CompositeRotation[];
  fmtPct: (v: number | null | undefined, dp?: number) => string;
}) {
  return (
    <Card style={{ marginBottom: 16 }}>
      <SH title={title} icon={<Clock size={11} />} />
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={{ ...th, textAlign: "left" }}>Date</th>
            <th style={{ ...th, textAlign: "right" }}>Out</th>
            <th style={{ ...th, textAlign: "right" }}>In</th>
            <th style={{ ...th, textAlign: "left" }}>Removed</th>
            <th style={{ ...th, textAlign: "left" }}>Added</th>
            <th style={{ ...th, textAlign: "right" }}>Avg P&L (closed)</th>
          </tr>
        </thead>
        <tbody>
          {[...rotations].reverse().slice(0, 20).map((r, i) => {
            const avgClosed = r.removed.length > 0
              ? r.removed.reduce((a, p) => a + (p.return_pct ?? 0), 0) / r.removed.length
              : null;
            return (
              <tr key={i}>
                <td style={td}>{r.date}</td>
                <td style={{ ...td, textAlign: "right", color: T.muted }}>{r.n_removed}</td>
                <td style={{ ...td, textAlign: "right", color: T.muted }}>{r.n_added}</td>
                <td style={{ ...td, fontSize: 10 }}>
                  {r.removed.map((x, idx) => (
                    <span key={x.symbol}>
                      <a href={`/stock/${x.symbol}`} style={{ color: T.text, textDecoration: "none" }}>{x.symbol}</a>
                      {idx < r.removed.length - 1 ? ", " : ""}
                    </span>
                  ))}
                </td>
                <td style={{ ...td, fontSize: 10 }}>
                  {r.added.map((x, idx) => (
                    <span key={x.symbol}>
                      <a href={`/stock/${x.symbol}`} style={{ color: T.text, textDecoration: "none" }}>{x.symbol}</a>
                      {idx < r.added.length - 1 ? ", " : ""}
                    </span>
                  ))}
                </td>
                <td style={{
                  ...td, textAlign: "right",
                  color: avgClosed !== null && avgClosed >= 0 ? T.green : T.red,
                }}>{fmtPct(avgClosed)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Card>
  );
}

// ── Combined chart ────────────────────────────────────────────────────────

interface ChartPoint {
  date: string;
  // v1.2 (May 2026): field names match the 4 active strategies.
  // BORING + COMPOSITE retired; replaced by CMP-US + CMP-Global.
  compounder_us_pct: number | null;
  compounder_global_pct: number | null;
  momentum_pct: number | null;
  fa_pct: number | null;
  spy_pct: number | null;
}

function buildCombinedChart(
  compounderUs: CompositeHistory | null,
  compounderGlobal: CompositeHistory | null,
  momentum: CompositeHistory | null,
  fa: CompositeHistory | null,
): ChartPoint[] {
  const dateSet = new Set<string>();

  // v1.2: all 4 strategies use the standard CompositeHistory.weekly_marks
  // shape — no more BORING-specific exit_date / today_interim_mark path.
  const collectMarks = (h: CompositeHistory | null) => {
    const out: { date: string; strat: number; spy: number }[] = [];
    if (!h || !h.weekly_marks) return out;
    for (const m of h.weekly_marks) {
      out.push({ date: m.date, strat: m.basket_avg_return_pct, spy: m.spy_return_pct });
      dateSet.add(m.date);
    }
    const lastMonitor = h.last_monitor_run;
    const lastWeekly = h.weekly_marks.length > 0 ? h.weekly_marks[h.weekly_marks.length - 1] : null;
    if (lastMonitor && h.summary &&
        (!lastWeekly || lastMonitor > lastWeekly.date)) {
      out.push({
        date: lastMonitor,
        strat: h.summary.cum_basket_return_pct,
        spy: h.summary.cum_spy_return_pct,
      });
      dateSet.add(lastMonitor);
    }
    return out;
  };

  const cuPoints = collectMarks(compounderUs);
  const cgPoints = collectMarks(compounderGlobal);
  const momentumPoints = collectMarks(momentum);
  const faPoints = collectMarks(fa);

  const dates = Array.from(dateSet).sort();
  const out: ChartPoint[] = [];
  for (const d of dates) {
    const cu = cuPoints.find(p => p.date === d);
    const cg = cgPoints.find(p => p.date === d);
    const m = momentumPoints.find(p => p.date === d);
    const f = faPoints.find(p => p.date === d);
    const spy = cu?.spy ?? cg?.spy ?? m?.spy ?? f?.spy ?? null;
    out.push({
      date: d,
      compounder_us_pct: cu?.strat ?? null,
      compounder_global_pct: cg?.strat ?? null,
      momentum_pct: m?.strat ?? null,
      fa_pct: f?.strat ?? null,
      spy_pct: spy,
    });
  }
  return out;
}

interface KPISummary {
  cycles: number;
  cum_alpha: number;
  ann_return: number;
  win_rate: number;
  cyclesLabel?: string;
  winRateLabel?: string;
  // Optional overrides used for in-flight strategies (e.g. BORING showing
  // synthetic stats before the first 26w cycle closes)
  cyclesValueOverride?: string;       // e.g. "3 / 182" instead of "3"
  cumAlphaLabel?: string;
  annReturnLabel?: string;
  annReturnValueOverride?: string;    // e.g. "+3.3%" raw return (not annualized)
}
// ── buildBoringSummary ─ DEPRECATED v1.2 (May 2026) ──────────────────────
// BORING strategy retired; helper preserved for revival but unused.
function buildBoringSummary(boring: BoringHistory | null): KPISummary | null {
  if (!boring) return null;

  // Closed-cycle path: use runner-computed summary
  if (boring.summary && boring.summary.weeks_closed > 0) {
    return {
      cycles: boring.summary.weeks_closed,
      cum_alpha: boring.summary.cum_alpha_pp,
      ann_return: boring.summary.annualized_return_pct,
      win_rate: boring.summary.win_rate * 100,
    };
  }

  // In-flight path: synthesize from open basket
  const ob = boring.open_basket;
  if (!ob) return null;

  // Latest mark = today_interim_mark (from monitor_prices.py daily) or last weekly_mark
  const im = ob.today_interim_mark;
  const lastWeekly = ob.weekly_marks?.[ob.weekly_marks.length - 1];
  const latestMark = im ?? lastWeekly;
  if (!latestMark) return null;

  const daysHeld = im?.days_held ?? lastWeekly?.days_held ?? 0;

  // Win rate = % of open basket positions currently in green
  const dailyMarks = ob.daily_last_marks ?? {};
  const positions = ob.basket ?? [];
  const positiveCount = positions.filter(p =>
    (dailyMarks[p.symbol]?.return_pct ?? 0) > 0
  ).length;
  const winRate = positions.length > 0 ? (positiveCount / positions.length) * 100 : 0;

  return {
    cycles: daysHeld,
    cyclesValueOverride: `${daysHeld} / 182`,
    cyclesLabel: "DAY OF HOLD",
    cum_alpha: latestMark.alpha_pp,
    ann_return: latestMark.basket_return_pct,
    annReturnLabel: "BASKET RTN",     // raw return — NOT annualized while <30d
    win_rate: winRate,
    winRateLabel: "of open positions",
  };
}

function StrategyKPICard({
  title, subtitle, inception, summary, marks, openCount,
}: {
  title: string;
  subtitle: string;
  inception: string | null | undefined;
  summary: KPISummary | null;
  marks?: { date: string; basket_return_pct: number; spy_return_pct: number; alpha_pp: number }[];
  openCount: number;
}) {
  const lastMark = marks && marks.length > 0 ? marks[marks.length - 1] : null;
  return (
    <Card>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
        <span style={{ fontSize: 13, fontWeight: 700, fontFamily: T.mono, color: T.text }}>{title}</span>
        <span style={{ fontSize: 9, fontFamily: T.mono, color: T.muted }}>{subtitle}</span>
      </div>
      <div style={{ fontSize: 10, color: T.muted, fontFamily: T.mono, marginBottom: 12 }}>
        {inception ? `Inception ${inception.slice(0, 10)} · ${openCount} positions open` : `Not running yet`}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 8, marginBottom: 10 }}>
        <KPIMini
          label={summary?.cyclesLabel?.toUpperCase() || "CYCLES CLOSED"}
          value={summary ? (summary.cyclesValueOverride ?? `${summary.cycles}`) : "—"}
        />
        <KPIMini
          label={summary?.cumAlphaLabel?.toUpperCase() || "CUM ALPHA"}
          value={summary ? `${summary.cum_alpha >= 0 ? "+" : ""}${summary.cum_alpha.toFixed(2)}pp` : "—"}
          accent={summary && summary.cum_alpha >= 0 ? "green" : (summary ? "red" : undefined)}
        />
        <KPIMini
          label={summary?.annReturnLabel?.toUpperCase() || "ANN. RETURN"}
          value={summary ? (summary.annReturnValueOverride ?? `${summary.ann_return >= 0 ? "+" : ""}${summary.ann_return.toFixed(1)}%`) : "—"}
        />
        <KPIMini
          label="WIN RATE"
          value={summary ? `${summary.win_rate.toFixed(0)}%` : "—"}
          sub={summary?.winRateLabel || "vs SPY"}
        />
      </div>

      {lastMark && (
        <div style={{ fontSize: 10, fontFamily: T.mono, color: T.muted,
                      borderTop: `1px solid ${T.divider}`, paddingTop: 8 }}>
          Last mark {lastMark.date}: basket {lastMark.basket_return_pct >= 0 ? "+" : ""}
          {lastMark.basket_return_pct.toFixed(2)}% · SPY {lastMark.spy_return_pct >= 0 ? "+" : ""}
          {lastMark.spy_return_pct.toFixed(2)}% · alpha{" "}
          <span style={{ color: lastMark.alpha_pp >= 0 ? T.green : T.red, fontWeight: 700 }}>
            {lastMark.alpha_pp >= 0 ? "+" : ""}{lastMark.alpha_pp.toFixed(2)}pp
          </span>
        </div>
      )}
    </Card>
  );
}

function KPIMini({ label, value, sub, accent }: {
  label: string; value: string; sub?: string; accent?: "green" | "red";
}) {
  const color = accent === "green" ? T.green : accent === "red" ? T.red : T.text;
  return (
    <div style={{ padding: "8px 10px", background: T.divider, borderRadius: 4 }}>
      <div style={{ fontSize: 8, fontFamily: T.mono, color: T.muted, letterSpacing: "0.08em", fontWeight: 600 }}>
        {label}
      </div>
      <div style={{ fontSize: 16, fontWeight: 700, fontFamily: T.mono, color, marginTop: 2 }}>
        {value}
      </div>
      {sub && (
        <div style={{ fontSize: 8, color: T.muted, fontFamily: T.mono, marginTop: 1 }}>
          {sub}
        </div>
      )}
    </div>
  );
}

function CombinedCumulativeChart({ points }: { points: ChartPoint[] }) {
  if (points.length < 2) {
    return (
      <div style={{ fontSize: 10, color: T.muted, fontFamily: T.mono, padding: "20px 0", textAlign: "center" }}>
        Need at least 2 data points for chart. Currently {points.length}.
      </div>
    );
  }
  const W = 800, H = 240, P = 30;
  const allValues: number[] = [];
  for (const p of points) {
    if (p.compounder_us_pct !== null) allValues.push(p.compounder_us_pct);
    if (p.compounder_global_pct !== null) allValues.push(p.compounder_global_pct);
    if (p.momentum_pct !== null) allValues.push(p.momentum_pct);
    if (p.fa_pct !== null) allValues.push(p.fa_pct);
    if (p.spy_pct !== null) allValues.push(p.spy_pct);
  }
  const maxY = Math.max(...allValues, 5);
  const minY = Math.min(...allValues, -5);
  const xScale = (i: number) => P + (i / (points.length - 1)) * (W - 2 * P);
  const yScale = (v: number) => H - P - ((v - minY) / (maxY - minY || 1)) * (H - 2 * P);

  const buildPath = (key: keyof ChartPoint) => {
    let path = "";
    let started = false;
    for (let i = 0; i < points.length; i++) {
      const v = points[i][key] as number | null;
      if (v === null) continue;
      const cmd = started ? "L" : "M";
      path += `${cmd} ${xScale(i).toFixed(1)},${yScale(v).toFixed(1)} `;
      started = true;
    }
    return path;
  };

  const cuPath = buildPath("compounder_us_pct");
  const cgPath = buildPath("compounder_global_pct");
  const momentumPath = buildPath("momentum_pct");
  const faPath = buildPath("fa_pct");
  const spyPath = buildPath("spy_pct");
  const zeroY = yScale(0);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: H, fontFamily: T.mono }}>
      <line x1={P} x2={W - P} y1={zeroY} y2={zeroY} stroke={T.divider} strokeDasharray="2,3" />
      <path d={spyPath} fill="none" stroke={T.muted} strokeWidth="1.5" />
      <path d={faPath} fill="none" stroke={T.amber} strokeWidth="2" />
      <path d={momentumPath} fill="none" stroke={T.blue} strokeWidth="2" />
      <path d={cgPath} fill="none" stroke={T.purple} strokeWidth="2" />
      <path d={cuPath} fill="none" stroke={T.green} strokeWidth="2" />
      <text x={P} y={P - 8} fontSize="9" fill={T.muted}>cumulative %</text>
      <text x={P + 100} y={P - 8} fontSize="9" fill={T.green}>● CMP-US</text>
      <text x={P + 175} y={P - 8} fontSize="9" fill={T.purple}>● CMP-GL</text>
      <text x={P + 250} y={P - 8} fontSize="9" fill={T.blue}>● MOMENTUM</text>
      <text x={P + 350} y={P - 8} fontSize="9" fill={T.amber}>● FA</text>
      <text x={P + 400} y={P - 8} fontSize="9" fill={T.muted}>● SPY</text>
      <text x={P} y={zeroY - 4} fontSize="9" fill={T.muted}>0%</text>
      <text x={W - P} y={H - 5} fontSize="9" fill={T.muted} textAnchor="end">{points[points.length - 1].date}</text>
    </svg>
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

const PAGE_SIZE = 25;


// ══════════════════════════════════════════════════════════════════════════════
// CyclesTab — v1.2 (Commit 2, May 2026)
// ══════════════════════════════════════════════════════════════════════════════
// P20 ML-prediction cycles + calibration tracking. Three layers:
//   1. Top:    current collecting cycle live stats + kill-switch banner
//   2. Middle: rolling 90-day D10 hit rate (model-health card)
//   3. Bottom: archived cycles list — click a card for the per-prediction
//              breakdown with hit/expire outcomes and EV vs realized P&L
//
// All data is read directly from GCS via /api/gcs proxy. No backend endpoint
// changes needed — signal_tracker.py writes these files on every scan.
//
// ══════════════════════════════════════════════════════════════════════════════

function CyclesTab() {
  const [state, setState]   = useState<CycleState | null>(null);
  const [health, setHealth] = useState<RollingHealth | null>(null);
  const [archives, setArchives] = useState<Record<string, CycleSummary>>({});
  // Open predictions for any cycle that's currently collecting or resolving.
  // Keyed by cycle_id so we can render multiple cycles in parallel.
  const [openCycles, setOpenCycles] = useState<Record<string, Prediction[]>>({});
  const [selectedArchive, setSelectedArchive] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  // Initial load — state + health, then fan out to cycle files.
  useEffect(() => {
    const t = Date.now();
    Promise.all([
      fetch(`${GCS_CYCLES_ROOT}/current_cycle.json?t=${t}`).then(r => r.ok ? r.json() : null),
      fetch(`${GCS_CYCLES_ROOT}/rolling_health.json?t=${t}`).then(r => r.ok ? r.json() : null),
    ])
      .then(([s, h]: [CycleState | null, RollingHealth | null]) => {
        setState(s);
        setHealth(h);

        if (!s) { setLoading(false); return; }

        // Fetch open predictions for collecting + resolving cycles in parallel.
        const liveIds = [
          ...(s.collecting_cycle_id ? [s.collecting_cycle_id] : []),
          ...s.resolving_cycle_ids,
        ];
        const openPromises = liveIds.map(id =>
          fetch(`${GCS_CYCLES_ROOT}/cycles/${id}/open.json?t=${t}`)
            .then(r => r.ok ? r.json() : null)
            .then((d: { predictions?: Prediction[] } | null) => ({ id, preds: d?.predictions || [] }))
            .catch(() => ({ id, preds: [] }))
        );

        // Fetch the most recent N archived cycles (show last 12 by default).
        const archivedToFetch = s.archived_cycle_ids.slice(-12);
        const archivePromises = archivedToFetch.map(id =>
          fetch(`${GCS_CYCLES_ROOT}/cycles/${id}/archived.json?t=${t}`)
            .then(r => r.ok ? r.json() : null)
            .then((d: CycleSummary | null) => ({ id, data: d }))
            .catch(() => ({ id, data: null }))
        );

        return Promise.all([Promise.all(openPromises), Promise.all(archivePromises)])
          .then(([opens, archs]) => {
            const openMap: Record<string, Prediction[]> = {};
            opens.forEach(o => { openMap[o.id] = o.preds; });
            setOpenCycles(openMap);

            const archMap: Record<string, CycleSummary> = {};
            archs.forEach(a => { if (a.data) archMap[a.id] = a.data; });
            setArchives(archMap);
          });
      })
      .catch(e => setErr(e?.message || "Failed to load cycles"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <Empty icon={<Target size={36} color={T.divider} />} title="Loading cycles…" />;
  }
  if (err) {
    return <Empty icon={<Target size={36} color={T.divider} />} title="Failed to load cycles" sub={err} />;
  }
  if (!state || !state.collecting_cycle_id) {
    return (
      <Empty icon={<Target size={36} color={T.divider} />}
        title="No cycles yet"
        sub="Cycles begin tracking once the first scan with hit_prob > 0 stocks completes."/>
    );
  }

  const collectingPreds = openCycles[state.collecting_cycle_id] || [];
  const resolvingTotal  = state.resolving_cycle_ids.reduce(
    (a, id) => a + ((openCycles[id] || []).length), 0);

  // Derive live decile distribution and aggregate stats for the collecting cycle
  const liveDecileDist: Record<number, number> = {};
  let liveHitsSoFar = 0;
  for (const p of collectingPreds) {
    liveDecileDist[p.decile] = (liveDecileDist[p.decile] || 0) + 1;
    if (p.outcome === "HIT") liveHitsSoFar++;
  }
  const daysIntoCycle = state.collecting_start
    ? Math.max(0, Math.floor((Date.now() - new Date(state.collecting_start + "T00:00:00").getTime()) / 86400000))
    : 0;
  const cycleEndsIn = state.collecting_ends
    ? Math.max(0, Math.floor((new Date(state.collecting_ends + "T00:00:00").getTime() - Date.now()) / 86400000))
    : 0;

  // Pick a sorted archive list (newest first) for display
  const archiveList = state.archived_cycle_ids
    .slice()
    .reverse()
    .map(id => archives[id])
    .filter((a): a is CycleSummary => !!a);

  return (
    <>
      {/* ─── Kill switch banner ─── shown only when active. Demands attention. */}
      {health?.kill_switch_active && (
        <div style={{
          padding: "12px 16px", marginBottom: 16, borderRadius: 6,
          background: "#fef2f2", border: `2px solid ${T.red}`,
          display: "flex", alignItems: "center", gap: 12,
        }}>
          <div style={{ fontSize: 22 }}>⚠</div>
          <div>
            <div style={{ fontFamily: T.mono, fontSize: 12, fontWeight: 700, color: T.red, letterSpacing: "0.05em" }}>
              KILL SWITCH ACTIVE — MODEL DEGRADATION DETECTED
            </div>
            <div style={{ fontFamily: T.mono, fontSize: 11, color: T.text, marginTop: 3, lineHeight: 1.5 }}>
              Rolling 90-day D10 hit rate is {(health.d10_hit_rate * 100).toFixed(1)}%, below the {(health.kill_switch_threshold * 100).toFixed(0)}% floor.
              Baseline calibration is {(health.baseline_d10 * 100).toFixed(1)}%. The model needs retraining.
            </div>
          </div>
        </div>
      )}

      {/* ─── KPI strip: collecting cycle + cumulative ─── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 20 }}>
        <KPI label="COLLECTING" value={`Cycle ${state.collecting_cycle_id}`}
          sub={`Day ${daysIntoCycle}/30 · closes in ${cycleEndsIn}d`}/>
        <KPI label="LIVE PREDICTIONS"
          value={String(collectingPreds.length)}
          sub={`${liveHitsSoFar} already hit · ${collectingPreds.length - liveHitsSoFar} still tracking`}/>
        <KPI label="RESOLVING" value={String(resolvingTotal)}
          sub={`${state.resolving_cycle_ids.length} cycle(s) past collection`}/>
        <KPI label="ARCHIVED" value={String(state.archived_cycle_ids.length)}
          sub="Total cycles fully resolved"/>
      </div>

      {/* ─── Rolling 90d D10 health card ─── */}
      {health && (
        <Card style={{ marginBottom: 20 }}>
          <SH title="90-Day Rolling Calibration"
            icon={<Award size={12}/>}
            sub={`D10 vs baseline · ${health.status} · ${health.computed_date || "—"}`}/>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14, padding: "8px 0" }}>
            <CalibrationStat
              label="D10 OBSERVED"
              value={`${(health.d10_hit_rate * 100).toFixed(1)}%`}
              sub={`n=${health.d10_n} · baseline ${(health.baseline_d10 * 100).toFixed(1)}%`}
              color={health.kill_switch_active ? T.red : health.d10_n >= 10 ? T.green : T.muted}/>
            <CalibrationStat
              label="D1 OBSERVED"
              value={`${(health.d1_hit_rate * 100).toFixed(1)}%`}
              sub={`n=${health.d1_n} · baseline ${(health.baseline_d1 * 100).toFixed(1)}%`}
              color={T.muted}/>
            <CalibrationStat
              label="ODDS RATIO"
              value={health.d1_hit_rate > 0 ? `${(health.d10_hit_rate / health.d1_hit_rate).toFixed(1)}x` : "—"}
              sub={`baseline ${(health.baseline_d10 / health.baseline_d1).toFixed(1)}x`}
              color={T.text}/>
            <CalibrationStat
              label="STATUS"
              value={health.status.replace("_", " ")}
              sub={`kill switch < ${(health.kill_switch_threshold * 100).toFixed(0)}% D10`}
              color={health.kill_switch_active ? T.red : health.status === "HEALTHY" ? T.green : T.amber}/>
          </div>
          <div style={{ marginTop: 10, fontSize: 9, color: T.light, fontFamily: T.mono, lineHeight: 1.5 }}>
            Computed across all predictions in collecting + resolving + last 6 archived cycles whose entry date falls within
            the trailing {health.window_days} days. OPEN predictions still in their 28-day fate window are excluded to avoid
            artificially deflating the rate.
          </div>
        </Card>
      )}

      {/* ─── Collecting cycle: decile distribution + live status ─── */}
      <Card style={{ marginBottom: 20 }}>
        <SH title={`Collecting Cycle ${state.collecting_cycle_id}`}
          icon={<Radio size={12}/>}
          sub={`Day ${daysIntoCycle}/30 · ${collectingPreds.length} predictions captured so far`}/>
        {collectingPreds.length === 0 ? (
          <div style={{ padding: "20px 8px", textAlign: "center", fontFamily: T.mono, fontSize: 11, color: T.muted }}>
            No predictions in this cycle yet. New predictions enter as the model emits hit_prob &gt; 0 stocks.
          </div>
        ) : (
          <>
            <div style={{ fontFamily: T.mono, fontSize: 9, color: T.muted, fontWeight: 600, letterSpacing: "0.08em", marginBottom: 6 }}>
              PREDICTIONS BY DECILE
            </div>
            <DecileBarChart distribution={liveDecileDist}/>
            <div style={{ marginTop: 14, overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    {["Symbol", "Entry", "P20", "Dec", "Strength", "Days", "Current", "Max ↑", "Max ↓", "Status", "EV/contract"].map((h, i) => (
                      <th key={h} style={{ ...th, textAlign: i === 0 ? "left" : "right" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {collectingPreds
                    .slice()
                    .sort((a, b) => b.p20 - a.p20)
                    .slice(0, 30)
                    .map(p => <PredictionRow key={`${p.symbol}-${p.entry_date}`} p={p}/>)}
                </tbody>
              </table>
              {collectingPreds.length > 30 && (
                <div style={{ padding: "8px 12px", fontSize: 10, fontFamily: T.mono, color: T.muted, textAlign: "center" }}>
                  Showing top 30 by P20 · {collectingPreds.length - 30} more in cycle
                </div>
              )}
            </div>
          </>
        )}
      </Card>

      {/* ─── Archived cycles ─── */}
      <Card>
        <SH title={`Archived Cycles (${archiveList.length})`}
          icon={<Clock size={12}/>}
          sub="Click a card for the per-prediction breakdown"/>
        {archiveList.length === 0 ? (
          <div style={{ padding: "20px 8px", textAlign: "center", fontFamily: T.mono, fontSize: 11, color: T.muted }}>
            No archived cycles yet. The first cycle archives ~58 days after open (30d collect + 28d fate window).
          </div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 12 }}>
            {archiveList.map(a => (
              <ArchiveCard key={a.cycle_id} summary={a}
                expanded={selectedArchive === a.cycle_id}
                onToggle={() => setSelectedArchive(selectedArchive === a.cycle_id ? null : a.cycle_id)}/>
            ))}
          </div>
        )}
        {selectedArchive && archives[selectedArchive] && (
          <div style={{ marginTop: 18, paddingTop: 16, borderTop: `2px solid ${T.divider}` }}>
            <ArchiveDrillDown summary={archives[selectedArchive]}/>
          </div>
        )}
      </Card>
    </>
  );
}


// ─── Small components used inside CyclesTab ──────────────────────────────────

function CalibrationStat({ label, value, sub, color }: {
  label: string; value: string; sub: string; color: string;
}) {
  return (
    <div style={{ padding: "10px 12px", background: T.greenLight, borderRadius: 6, border: `1px solid ${T.greenBorder}` }}>
      <div style={{ fontSize: 9, color: T.muted, fontFamily: T.mono, fontWeight: 600, letterSpacing: "0.08em" }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color, fontFamily: T.mono, marginTop: 4 }}>{value}</div>
      <div style={{ fontSize: 9, color: T.light, fontFamily: T.mono, marginTop: 2 }}>{sub}</div>
    </div>
  );
}

function DecileBarChart({ distribution }: { distribution: Record<number, number> }) {
  // Horizontal bars for D1..D10 showing prediction count per decile.
  const maxN = Math.max(1, ...Object.values(distribution));
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
      {[10, 9, 8, 7, 6, 5, 4, 3, 2, 1].map(d => {
        const n = distribution[d] || 0;
        const w = (n / maxN) * 100;
        // D10 highlighted green, D1 red, gradient in between for visual weight
        const c = d >= 8 ? T.green : d >= 5 ? T.amber : T.light;
        return (
          <div key={d} style={{ display: "flex", alignItems: "center", gap: 8, fontFamily: T.mono, fontSize: 10 }}>
            <div style={{ width: 28, color: T.muted, fontWeight: 600, textAlign: "right" }}>D{d}</div>
            <div style={{ flex: 1, height: 14, background: T.divider, borderRadius: 3, position: "relative", overflow: "hidden" }}>
              <div style={{ width: `${w}%`, height: "100%", background: c, transition: "width 0.4s" }}/>
              {n > 0 && (
                <span style={{ position: "absolute", left: 6, top: 0, lineHeight: "14px", fontSize: 9, color: w > 25 ? "#fff" : T.text, fontWeight: 700 }}>
                  {n}
                </span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function PredictionRow({ p }: { p: Prediction }) {
  const statusColor = p.outcome === "HIT" ? T.greenPos : p.outcome === "EXPIRED" ? T.red : T.muted;
  const evValue = p.ev_dollars;
  const evColor = evValue == null ? T.light : evValue > 0 ? T.greenPos : T.red;
  return (
    <tr>
      <td style={{ ...td, textAlign: "left", fontWeight: 600 }}>{p.symbol}</td>
      <td style={{ ...td, textAlign: "right" }}>${p.entry_price.toFixed(2)}</td>
      <td style={{ ...td, textAlign: "right" }}>{(p.p20 * 100).toFixed(1)}%</td>
      <td style={{ ...td, textAlign: "right" }}>D{p.decile}</td>
      <td style={{ ...td, textAlign: "right", color: T.muted, fontSize: 10 }}>{p.signal_strength}</td>
      <td style={{ ...td, textAlign: "right" }}>{p.days_observed}/28</td>
      <td style={{ ...td, textAlign: "right" }}>${p.current_price.toFixed(2)}</td>
      <td style={{ ...td, textAlign: "right", color: T.greenPos, fontWeight: 600 }}>
        {p.max_high_observed_pct >= 0 ? "+" : ""}{p.max_high_observed_pct.toFixed(1)}%
      </td>
      <td style={{ ...td, textAlign: "right", color: p.max_drawdown_observed_pct < 0 ? T.red : T.muted, fontWeight: 600 }}>
        {p.max_drawdown_observed_pct.toFixed(1)}%
      </td>
      <td style={{ ...td, textAlign: "right", color: statusColor, fontWeight: 600 }}>{p.outcome}</td>
      <td style={{ ...td, textAlign: "right", color: evColor, fontSize: 10 }}>
        {evValue == null ? "—" : `${evValue >= 0 ? "+" : ""}$${evValue.toFixed(0)}`}
      </td>
    </tr>
  );
}

function ArchiveCard({ summary, expanded, onToggle }: {
  summary: CycleSummary; expanded: boolean; onToggle: () => void;
}) {
  const cc = summary.calibration_check;
  const healthy = cc.healthy;
  return (
    <div onClick={onToggle}
      style={{
        padding: "12px 14px", borderRadius: 6,
        background: expanded ? T.greenLight : "white",
        border: `1px solid ${expanded ? T.green : T.border}`,
        cursor: "pointer", transition: "all 0.15s",
      }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 8 }}>
        <div style={{ fontFamily: T.mono, fontSize: 11, fontWeight: 700, color: T.text }}>
          {summary.cycle_id}
        </div>
        <div style={{ fontFamily: T.mono, fontSize: 9, color: T.muted }}>
          {summary.archived_date}
        </div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 8 }}>
        <div>
          <div style={{ fontSize: 9, color: T.muted, fontFamily: T.mono, fontWeight: 600 }}>HIT RATE</div>
          <div style={{ fontSize: 18, fontWeight: 700, fontFamily: T.mono, color: T.text }}>
            {(summary.hit_rate * 100).toFixed(1)}%
          </div>
          <div style={{ fontSize: 9, color: T.light, fontFamily: T.mono }}>
            {summary.hit_count}/{summary.total_predictions} preds
          </div>
        </div>
        <div>
          <div style={{ fontSize: 9, color: T.muted, fontFamily: T.mono, fontWeight: 600 }}>D10 vs D1</div>
          <div style={{ fontSize: 18, fontWeight: 700, fontFamily: T.mono, color: healthy ? T.green : T.red }}>
            {(cc.d10_hit_rate * 100).toFixed(0)}% / {(cc.d1_hit_rate * 100).toFixed(0)}%
          </div>
          <div style={{ fontSize: 9, color: T.light, fontFamily: T.mono }}>
            {cc.observed_odds_ratio != null ? `${cc.observed_odds_ratio.toFixed(1)}x odds` : "—"}
          </div>
        </div>
      </div>
      <div style={{ display: "flex", gap: 10, fontSize: 9, fontFamily: T.mono, color: T.muted }}>
        <span>↑ {summary.best_runup_pct >= 0 ? "+" : ""}{summary.best_runup_pct.toFixed(0)}%</span>
        <span>↓ {summary.worst_drawdown_pct.toFixed(0)}%</span>
        <span>EV ${summary.aggregate_ev_dollars.toFixed(0)} → {summary.aggregate_realized_pnl_dollars >= 0 ? "+" : ""}${summary.aggregate_realized_pnl_dollars.toFixed(0)}</span>
      </div>
    </div>
  );
}

function ArchiveDrillDown({ summary }: { summary: CycleSummary }) {
  // Decile bars sourced from the archived summary (hit_rate_by_decile).
  const decileDist: Record<number, number> = {};
  Object.entries(summary.hit_rate_by_decile).forEach(([k, v]) => {
    decileDist[Number(k)] = v.n;
  });
  return (
    <>
      <div style={{ fontFamily: T.mono, fontSize: 11, fontWeight: 700, color: T.text, marginBottom: 10, letterSpacing: "0.05em" }}>
        Cycle {summary.cycle_id} · Per-prediction outcomes
      </div>

      {/* Per-decile hit rate grid */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(10, 1fr)", gap: 6, marginBottom: 14 }}>
        {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(d => {
          const cell = summary.hit_rate_by_decile[String(d)] || { n: 0, hits: 0, hit_rate: 0 };
          const c = cell.n === 0 ? T.light : cell.hit_rate >= 0.15 ? T.green : cell.hit_rate >= 0.05 ? T.amber : T.red;
          return (
            <div key={d} style={{ textAlign: "center", padding: "8px 4px", background: T.greenLight, borderRadius: 4, border: `1px solid ${T.greenBorder}` }}>
              <div style={{ fontSize: 9, color: T.muted, fontFamily: T.mono, fontWeight: 600 }}>D{d}</div>
              <div style={{ fontSize: 14, fontWeight: 700, color: c, fontFamily: T.mono }}>
                {cell.n > 0 ? `${(cell.hit_rate * 100).toFixed(0)}%` : "—"}
              </div>
              <div style={{ fontSize: 8, color: T.light, fontFamily: T.mono }}>{cell.hits}/{cell.n}</div>
            </div>
          );
        })}
      </div>

      {/* All predictions in the cycle, sorted by P20 desc */}
      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              {["Symbol", "Entry", "P20", "Dec", "Days", "Final", "Max ↑", "Max ↓", "Outcome", "EV", "Realized"].map((h, i) => (
                <th key={h} style={{ ...th, textAlign: i === 0 ? "left" : "right" }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {summary.predictions
              .slice()
              .sort((a, b) => b.p20 - a.p20)
              .map(p => {
                const statusColor = p.outcome === "HIT" ? T.greenPos : T.red;
                const realized = p.realized_contract_pnl;
                const realizedColor = realized == null ? T.light : realized >= 0 ? T.greenPos : T.red;
                return (
                  <tr key={`${p.symbol}-${p.entry_date}`}>
                    <td style={{ ...td, textAlign: "left", fontWeight: 600 }}>{p.symbol}</td>
                    <td style={{ ...td, textAlign: "right" }}>${p.entry_price.toFixed(2)}</td>
                    <td style={{ ...td, textAlign: "right" }}>{(p.p20 * 100).toFixed(1)}%</td>
                    <td style={{ ...td, textAlign: "right" }}>D{p.decile}</td>
                    <td style={{ ...td, textAlign: "right" }}>{p.days_observed}</td>
                    <td style={{ ...td, textAlign: "right" }}>${p.current_price.toFixed(2)}</td>
                    <td style={{ ...td, textAlign: "right", color: T.greenPos, fontWeight: 600 }}>
                      +{p.max_high_observed_pct.toFixed(1)}%
                    </td>
                    <td style={{ ...td, textAlign: "right", color: T.red, fontWeight: 600 }}>
                      {p.max_drawdown_observed_pct.toFixed(1)}%
                    </td>
                    <td style={{ ...td, textAlign: "right", color: statusColor, fontWeight: 600 }}>{p.outcome}</td>
                    <td style={{ ...td, textAlign: "right" }}>
                      {p.ev_dollars == null ? "—" : `${p.ev_dollars >= 0 ? "+" : ""}$${p.ev_dollars.toFixed(0)}`}
                    </td>
                    <td style={{ ...td, textAlign: "right", color: realizedColor, fontWeight: 600 }}>
                      {realized == null ? "—" : `${realized >= 0 ? "+" : ""}$${realized.toFixed(0)}`}
                    </td>
                  </tr>
                );
              })}
          </tbody>
        </table>
      </div>
    </>
  );
}


// ══════════════════════════════════════════════════════════════════════════════
// Shell
// ══════════════════════════════════════════════════════════════════════════════
export default function Performance() {
  const router = useRouter();
  const [tab, setTab] = useState<"strategies" | "cycles" | "signal" | "hitrate">("strategies");

  return (
    <div style={{ padding: "16px 20px", maxWidth: 1400, margin: "0 auto" }}>
      <div style={{ marginBottom: 16, paddingBottom: 10, borderBottom: `1px solid ${T.border}` }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
          <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: "0.1em", color: T.text, fontFamily: T.mono }}>PERFORMANCE</span>
          <span style={{ fontSize: 12, color: T.muted, fontFamily: T.mono }}>/ tracking</span>
        </div>
        <p style={{ fontSize: 10, color: T.muted, fontFamily: T.mono, marginTop: 4 }}>
          Forward-only paper-tracking. 4 strategies: BORING (26w hold) · COMPOSITE (rotation) · MOMENTUM (rotation) · FALLEN ANGEL (rotation, gate). Daily price refresh.
          P20 prediction cycles run in parallel: every enriched stock tracked over 28 days, decile-bucketed for calibration validation.
        </p>
      </div>

      <div style={{ display: "flex", gap: 6, marginBottom: 16, borderBottom: `1px solid ${T.divider}`, paddingBottom: 2 }}>
        {[
          { key: "strategies", label: "Strategies",         icon: <BarChart3 size={12} /> },
          { key: "cycles",     label: "P20 Cycles",         icon: <Target size={12} /> },
          { key: "signal",     label: "Signal Performance", icon: <TrendingUp size={12} /> },
          { key: "hitrate",    label: "Legacy Hit Rate",    icon: <Award size={12} /> },
        ].map(({ key, label, icon }) => (
          <button key={key} onClick={() => setTab(key as typeof tab)}
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

      {tab === "strategies" && <StrategiesTab />}
      {tab === "cycles"     && <CyclesTab />}
      {tab === "signal"     && <SignalPerfTab router={router} />}
      {tab === "hitrate"    && <HitRateTab router={router} />}
    </div>
  );
}
