"use client";
import { useState, useEffect, useMemo, Fragment } from "react";
import { TrendingUp, BarChart3, Target, Clock, ChevronDown, ChevronRight, Search } from "lucide-react";

// ── Data source ─────────────────────────────────────────────────────────────
const METHOD_TRACKS = "/api/performance/method-tracks";

// ── Four-method tracking types — matches read_method_tracks() output ────────
interface MethodStats {
  n: number;
  barrier_hit_count: number; stopped_count: number; terminal_count: number;
  barrier_hit_rate: number; winning_trade_rate: number | null;
  mean_realized_return_pct: number; median_realized_return_pct: number;
  tail_p5_return_pct: number; tail_p95_return_pct: number;
  mean_max_runup_pct: number; mean_max_drawdown_pct: number;
  worst_drawdown_pct: number; best_runup_pct: number;
  total_cost_basis: number; total_realized_pnl_dollars: number;
  portfolio_return_pct: number | null;
  underpowered: boolean;
  by_decile: Record<string, { n: number; hits: number; hit_rate: number }>;
}
interface MethodCalibration {
  d10_hit_rate: number; d10_n: number;
  d1_hit_rate: number; d1_n: number;
  d10_baseline: number; d1_baseline: number;
  observed_odds_ratio: number | null; baseline_odds_ratio: number;
  kill_switch_threshold: number; healthy: boolean;
  by_decile: Record<string, { n: number; hits: number; hit_rate: number }>;
}
// Per-pick prediction row — full schema from signal_tracker.py.
// 4 rows per pick (2 methods × 2 regimes); each carries shared entry
// context plus method-specific fields (stop_price | chosen_leg_*).
interface MethodPredRow {
  symbol: string;
  entry_date: string;
  cycle_id: string;
  region?: string;
  regime: string;             // "30d_p10" | "60d"
  method: "stock" | "long_call";
  company_name?: string | null;
  sector?: string | null;
  country?: string | null;
  market_cap?: number | null;
  entry_price: number;
  p20: number;
  decile: number;
  signal_strength: string;
  mode_qualifications?: string[];
  composite?: number | null;
  expected_dd?: number | null;
  ivr_at_entry?: number | null;
  iv_at_entry?: number | null;
  skew_25d?: number | null;
  pc_oi_ratio?: number | null;
  barrier_target_pct: number;
  barrier_price: number;
  hit_window_days: number;
  fate_window_ends?: string;
  outcome: string;            // "OPEN" | "CLOSED"
  outcome_tag: string;        // "OPEN" | "SOLD_AT_TOUCH" | "STOPPED" | "TERMINAL"
  current_price: number;
  last_updated: string;
  days_observed: number;
  max_high_observed_pct: number;
  max_drawdown_observed_pct: number;
  realized_return_pct: number | null;
  resolution_date: string | null;
  // Stock arm fields
  stop_loss_pct?: number | null;
  stop_price?: number | null;
  // Long-call arm fields
  chosen_leg_strike?: number | null;
  chosen_leg_expiration?: string | null;
  chosen_leg_dte_at_entry?: number | null;
  entry_quote_ask?: number | null;
  entry_quote_bid?: number | null;
  entry_quote_mid?: number | null;
  entry_iv_at_strike?: number | null;
  entry_delta?: number | null;
  entry_gamma?: number | null;
  entry_theta?: number | null;
  entry_vega?: number | null;
  model_fair_value_at_entry?: number | null;
  edge_dollars_at_entry?: number | null;
  edge_pct_at_entry?: number | null;
  current_quote_ask?: number | null;
  current_quote_bid?: number | null;
  current_quote_mid?: number | null;
  current_iv_at_strike?: number | null;
  current_delta?: number | null;
  current_theta?: number | null;
  unrealized_pnl?: number | null;
  unrealized_pnl_pct?: number | null;
  realized_pnl_at_resolve?: number | null;
  quote_last_repriced?: string | null;
}
interface MethodCycleSummary {
  cycle_id: string;
  archived_date?: string;
  regime: string;
  total_predictions: number; n_picks: number;
  by_method: { stock: MethodStats; long_call: MethodStats };
  calibration: MethodCalibration;
  predictions?: MethodPredRow[];  // present on current and archived summaries
}
interface MethodRegimeBlock {
  regime: string;
  barrier_target_pct: number;
  hit_window_days: number;
  current_cycle: MethodCycleSummary | null;
  archived_cycles: MethodCycleSummary[];
}
interface MethodTracks {
  regimes: Record<string, MethodRegimeBlock>;
  as_of: string;
}

// ── v1.2 cycles types — matches signal_tracker.py output ──────────────────
// ── BORING strategy tracker ────────────────────────────────────────────────
// ── COMPOSITE / MOMENTUM / FA strategy tracker ─────────────────────────────
// ── Theme ───────────────────────────────────────────────────────────────────
const T = {
  bg: "var(--bg)",
  card: "var(--bg-surface)",
  cardBorder: "var(--border)",
  cardShadow: "var(--shadow-md)",
  text: "var(--text)",
  textMuted: "var(--text-muted)",
  textLight: "var(--text-light)",
  green: "var(--green)",
  greenPos: "var(--green)",
  greenLight: "var(--green-light)",
  greenBorder: "var(--green-border)",
  red: "var(--red)",
  redLight: "var(--red-light)",
  amber: "var(--amber)",
  amberLight: "var(--amber-light)",
  blue: "var(--blue)",
  purple: "var(--purple)",
  border: "var(--border)",
  divider: "var(--divider)",
  mono: "var(--font-mono, 'JetBrains Mono', monospace)",
  shadow: "var(--shadow-md)",
  // Aliases — used extensively throughout this file
  light: "var(--text-light)",
  muted: "var(--text-muted)",
};

// ── Atoms ───────────────────────────────────────────────────────────────────
function Card({ children, style }: { children: React.ReactNode; style?: React.CSSProperties }) {
  return (
    <div style={{ background: T.card, borderRadius: 8, border: `1px solid ${T.border}`, boxShadow: T.shadow, padding: "16px 18px", ...style }}>
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
// ── Four-method comparison view ─────────────────────────────────────────────
// Rows: {stock, long_call} × {30d_p10, 60d} = 4 method arms tracked in
// parallel on the same daily picks. Columns surface the risk-adjusted
// picture (tail_p5, max DD) alongside the central tendency (mean ROI,
// portfolio return) so a win-rate doesn't hide the disaster tail.

interface MethodRow {
  key: string;
  regime: string;
  method: "stock" | "long_call";
  label: string;
  barrierPct: number;
  windowDays: number;
  stats: MethodStats;
}

function MethodsTab() {
  const [data, setData] = useState<MethodTracks | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [view, setView] = useState<"current" | "archived">("current");
  const [archivedIdx, setArchivedIdx] = useState(0);

  useEffect(() => {
    fetch(METHOD_TRACKS)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((d: MethodTracks) => { setData(d); setLoading(false); })
      .catch(e => { setErr(e.message || "Failed to load"); setLoading(false); });
  }, []);

  const rows: MethodRow[] = useMemo(() => {
    if (!data?.regimes) return [];
    const out: MethodRow[] = [];
    for (const rname of ["30d_p10", "60d"]) {
      const r = data.regimes[rname];
      if (!r) continue;
      const summary = view === "current"
        ? r.current_cycle
        : (r.archived_cycles[archivedIdx] ?? null);
      if (!summary) continue;
      for (const m of ["stock", "long_call"] as const) {
        const stats = summary.by_method[m];
        if (!stats) continue;
        out.push({
          key: `${rname}-${m}`,
          regime: rname,
          method: m,
          label: `${m === "stock" ? "Stock" : "Long Call"} × ${r.barrier_target_pct}% / ${r.hit_window_days}d`,
          barrierPct: r.barrier_target_pct,
          windowDays: r.hit_window_days,
          stats,
        });
      }
    }
    return out;
  }, [data, view, archivedIdx]);

  const summaryForView = (rname: string): MethodCycleSummary | null => {
    if (!data?.regimes[rname]) return null;
    return view === "current"
      ? data.regimes[rname].current_cycle
      : (data.regimes[rname].archived_cycles[archivedIdx] ?? null);
  };

  const archivedOptions = useMemo(() => {
    if (!data?.regimes) return [];
    // Union of archived cycle ids across regimes
    const ids = new Set<string>();
    for (const r of Object.values(data.regimes)) {
      for (const a of r.archived_cycles) ids.add(a.cycle_id);
    }
    return Array.from(ids).sort().reverse();
  }, [data]);

  const totalPicks = useMemo(() => {
    if (!data?.regimes) return 0;
    let n = 0;
    for (const rname of ["30d_p10", "60d"]) {
      const s = summaryForView(rname);
      n += s?.n_picks ?? 0;
    }
    return n;
  }, [data, view, archivedIdx]);

  if (loading) return <Empty icon={<BarChart3 size={36} color={T.divider} />} title="Loading method tracks…" />;
  if (err) return <Empty icon={<BarChart3 size={36} color={T.divider} />} title="Failed to load" sub={err} />;
  if (!data) return <Empty icon={<BarChart3 size={36} color={T.divider} />} title="No method data" />;

  const cal30 = summaryForView("30d_p10")?.calibration;
  const cal60 = summaryForView("60d")?.calibration;

  return (
    <>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 16 }}>
        <KPI label="PICKS (THIS VIEW)" value={String(totalPicks)} sub={view === "current" ? "Live collecting cycle" : `Archived ${archivedOptions[archivedIdx] ?? ""}`} />
        <KPI label="METHODS TRACKED" value="4" sub="{stock, call} × {30d/+10%, 60d/+20%}" />
        <KPI label="CALIBRATION (30D)" value={cal30 ? `${(cal30.d10_hit_rate * 100).toFixed(0)}%` : "—"} color={cal30?.healthy ? T.greenPos : T.red} sub={`D10 n=${cal30?.d10_n ?? 0} vs ${(cal30?.d10_baseline ?? 0) * 100 | 0}% baseline`} />
        <KPI label="CALIBRATION (60D)" value={cal60 ? `${(cal60.d10_hit_rate * 100).toFixed(0)}%` : "—"} color={cal60?.healthy ? T.greenPos : T.red} sub={`D10 n=${cal60?.d10_n ?? 0} vs ${(cal60?.d10_baseline ?? 0) * 100 | 0}% baseline`} />
      </div>

      <div style={{ display: "flex", gap: 8, marginBottom: 12, alignItems: "center" }}>
        <button onClick={() => setView("current")}
          style={{
            padding: "6px 14px", fontSize: 11, fontFamily: T.mono, fontWeight: 600,
            border: "none", borderRadius: 5, cursor: "pointer",
            background: view === "current" ? T.greenLight : "transparent",
            color: view === "current" ? T.green : T.muted,
          }}>Current cycle</button>
        <button onClick={() => setView("archived")}
          disabled={archivedOptions.length === 0}
          style={{
            padding: "6px 14px", fontSize: 11, fontFamily: T.mono, fontWeight: 600,
            border: "none", borderRadius: 5, cursor: archivedOptions.length === 0 ? "not-allowed" : "pointer",
            background: view === "archived" ? T.greenLight : "transparent",
            color: view === "archived" ? T.green : T.muted,
            opacity: archivedOptions.length === 0 ? 0.4 : 1,
          }}>Archived ({archivedOptions.length})</button>
        {view === "archived" && archivedOptions.length > 0 && (
          <select value={archivedIdx} onChange={e => setArchivedIdx(parseInt(e.target.value))}
            style={{ fontSize: 11, fontFamily: T.mono, padding: "4px 8px", borderRadius: 4, border: `1px solid ${T.divider}`, background: "var(--bg-elevated, #fff)", color: T.text }}>
            {archivedOptions.map((cid, i) => <option key={cid} value={i}>{cid}</option>)}
          </select>
        )}
      </div>

      <Card style={{ marginBottom: 20 }}>
        <SH title="Method comparison" icon={<TrendingUp size={12} />}
            sub={`Same picks, four exit/payoff structures tracked in parallel. Read tail_p5 + worst_DD before celebrating any win rate.`} />
        {rows.length === 0 ? (
          <div style={{ padding: 30, textAlign: "center", color: T.light, fontSize: 11, fontFamily: T.mono }}>
            No data for this view yet. New schema starts collecting from the next scan.
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: T.mono }}>
              <thead><tr>
                {["Method", "n", "Hit %", "Win %", "Mean ROI", "Median", "Tail p5", "Tail p95", "Worst DD", "Best Runup", "Port Ret", "Flag"].map((h, i) => (
                  <th key={h} style={{ ...th, textAlign: i === 0 ? "left" : "right" }}>{h}</th>
                ))}
              </tr></thead>
              <tbody>
                {rows.map(r => {
                  const s = r.stats;
                  const meanC = s.mean_realized_return_pct >= 0 ? T.greenPos : T.red;
                  const tailC = s.tail_p5_return_pct >= -10 ? T.greenPos : s.tail_p5_return_pct >= -25 ? T.muted : T.red;
                  const portC = (s.portfolio_return_pct ?? 0) >= 0 ? T.greenPos : T.red;
                  const winC = (s.winning_trade_rate ?? 0) >= 0.5 ? T.greenPos : T.red;
                  return (
                    <tr key={r.key}
                        onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "var(--bg-hover)"; }}
                        onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = ""; }}>
                      <td style={{ ...td, textAlign: "left", fontWeight: 600, color: T.text }}>{r.label}</td>
                      <td style={{ ...td, textAlign: "right", color: T.muted }}>{s.n}</td>
                      <td style={{ ...td, textAlign: "right", color: T.text }}>{(s.barrier_hit_rate * 100).toFixed(0)}%
                        <span style={{ color: T.light, fontSize: 9, marginLeft: 4 }}>
                          ({s.barrier_hit_count}/{s.n})
                        </span>
                      </td>
                      <td style={{ ...td, textAlign: "right", color: winC, fontWeight: 600 }}>
                        {s.winning_trade_rate !== null ? `${(s.winning_trade_rate * 100).toFixed(0)}%` : "—"}
                      </td>
                      <td style={{ ...td, textAlign: "right", color: meanC, fontWeight: 700 }}>
                        {s.mean_realized_return_pct >= 0 ? "+" : ""}{s.mean_realized_return_pct.toFixed(1)}%
                      </td>
                      <td style={{ ...td, textAlign: "right", color: T.muted }}>
                        {s.median_realized_return_pct >= 0 ? "+" : ""}{s.median_realized_return_pct.toFixed(1)}%
                      </td>
                      <td style={{ ...td, textAlign: "right", color: tailC, fontWeight: 700 }}>
                        {s.tail_p5_return_pct.toFixed(1)}%
                      </td>
                      <td style={{ ...td, textAlign: "right", color: T.muted }}>
                        +{s.tail_p95_return_pct.toFixed(1)}%
                      </td>
                      <td style={{ ...td, textAlign: "right", color: T.red }}>{s.worst_drawdown_pct.toFixed(1)}%</td>
                      <td style={{ ...td, textAlign: "right", color: T.greenPos }}>+{s.best_runup_pct.toFixed(1)}%</td>
                      <td style={{ ...td, textAlign: "right", color: portC, fontWeight: 600 }}>
                        {s.portfolio_return_pct !== null ? `${s.portfolio_return_pct >= 0 ? "+" : ""}${s.portfolio_return_pct.toFixed(1)}%` : "—"}
                      </td>
                      <td style={{ ...td, textAlign: "right", color: T.muted, fontSize: 9 }}>
                        {s.underpowered ? <span style={{ color: T.red, fontWeight: 700 }}>n&lt;20</span> : "OK"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card style={{ marginBottom: 20 }}>
        <SH title="Exit breakdown" icon={<Clock size={12} />}
            sub="How each method closed its rows" />
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: T.mono }}>
            <thead><tr>
              {["Method", "Sold at touch", "Stopped", "Window end", "Total"].map((h, i) => (
                <th key={h} style={{ ...th, textAlign: i === 0 ? "left" : "right" }}>{h}</th>
              ))}
            </tr></thead>
            <tbody>
              {rows.map(r => (
                <tr key={`exit-${r.key}`}>
                  <td style={{ ...td, textAlign: "left", fontWeight: 600, color: T.text }}>{r.label}</td>
                  <td style={{ ...td, textAlign: "right", color: T.greenPos }}>{r.stats.barrier_hit_count}</td>
                  <td style={{ ...td, textAlign: "right", color: r.method === "long_call" ? T.light : T.red }}>
                    {r.method === "long_call" ? "—" : r.stats.stopped_count}
                  </td>
                  <td style={{ ...td, textAlign: "right", color: T.muted }}>{r.stats.terminal_count}</td>
                  <td style={{ ...td, textAlign: "right", color: T.text, fontWeight: 600 }}>{r.stats.n}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card style={{ marginBottom: 20 }}>
        <SH title="Decile calibration" icon={<Target size={12} />}
            sub="Predicted probability (purple line) vs observed win rate (bars), per decile. Calibrated = bars reach the line. Win rates accrue over the 30/60d window — early in a cycle the bars sit below the line until picks resolve (not miscalibration). Decile spread also shows whether the model uses the full probability range." />
        <div style={{ padding: "4px 14px 14px" }}>
          <DecileCalibration summary={summaryForView("30d_p10")} label="30d · +10%" />
          <DecileCalibration summary={summaryForView("60d")} label="60d · +20%" />
        </div>
      </Card>

      <PicksTable
        rows={(() => {
          const out: MethodPredRow[] = [];
          for (const rname of ["30d_p10", "60d"]) {
            const s = summaryForView(rname);
            if (s?.predictions) out.push(...s.predictions);
          }
          // Stable order: by symbol, then 30d before 60d, then stock before call
          out.sort((a, b) => {
            if (a.symbol !== b.symbol) return a.symbol.localeCompare(b.symbol);
            if (a.regime !== b.regime) return a.regime === "30d_p10" ? -1 : 1;
            return a.method === "stock" ? -1 : 1;
          });
          return out;
        })()}
        cycleLabel={view === "current" ? "Current cycle" : (archivedOptions[archivedIdx] ?? "")}
      />
    </>
  );
}

// ── Per-pick detail table ───────────────────────────────────────────────────
// One row per prediction row (so 4 rows per qualifying pick). Lets you read
// each pick's entry context (price, ATM IV, IVR, decile) alongside the
// method-specific fields (stop_price for stocks; chosen leg / entry ask /
// edge for calls) and the live mark / outcome / realized return.
type PickSortKey = "symbol" | "decile" | "entry" | "iv" | "ivr" | "last" | "maxplus" | "expdd" | "maxminus" | "days";

function SortTh({ label, k, sortKey, sortDir, onSort, style, title }: {
  label: string; k: PickSortKey; sortKey: PickSortKey; sortDir: "asc" | "desc";
  onSort: (k: PickSortKey) => void; style?: React.CSSProperties; title?: string;
}) {
  const active = sortKey === k;
  return (
    <th onClick={() => onSort(k)} title={title} style={{ ...th, cursor: "pointer", color: active ? T.text : T.muted, ...style }}>
      {label}{active ? (sortDir === "desc" ? " ↓" : " ↑") : ""}
    </th>
  );
}

interface PickGroup {
  symbol: string; rows: MethodPredRow[];
  sector?: string | null; entry_date?: string; decile: number; entry_price: number;
  iv_at_entry?: number | null; ivr_at_entry?: number | null;
  last: number; maxPlus: number; expDd?: number | null; maxMinus: number; days: number;
  touches: number; stops: number; open: number;
}

// Calibration: predicted probability (avg p20 per decile, purple line) vs observed
// win rate (bars). Calibrated = bars reach the line. Early in a cycle the bars sit
// far below the line because the 30/60d windows haven't elapsed — that gap closes
// as picks resolve, it is not miscalibration.
function DecileCalibration({ summary, label }: { summary: MethodCycleSummary | null; label: string }) {
  if (!summary) return null;
  const byDec = summary.calibration?.by_decile || {};
  const predAgg: Record<number, { sum: number; n: number }> = {};
  for (const p of (summary.predictions || [])) {
    if (p.method !== "stock" || !p.decile) continue;   // one arm per pick for the prob
    (predAgg[p.decile] = predAgg[p.decile] || { sum: 0, n: 0 });
    predAgg[p.decile].sum += p.p20 ?? 0; predAgg[p.decile].n += 1;
  }
  const decs = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
  const obs = (d: number) => { const c = byDec[String(d)]; return c && c.n > 0 ? c.hit_rate : null; };
  const pred = (d: number) => { const a = predAgg[d]; return a && a.n ? a.sum / a.n : null; };
  const nOf = (d: number) => byDec[String(d)]?.n ?? 0;
  const scaleMax = Math.max(0.1, ...decs.flatMap(d => [obs(d) ?? 0, pred(d) ?? 0])) * 1.15;
  const H = 84;
  const totalN = decs.reduce((s, d) => s + nOf(d), 0);
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontFamily: T.mono, fontSize: 10, fontWeight: 700, color: T.text, marginBottom: 6 }}>
        {label}<span style={{ color: T.light, fontWeight: 400 }}> · n={totalN}</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(10, 1fr)", gap: 5, alignItems: "end" }}>
        {decs.map(d => {
          const o = obs(d), pr = pred(d), n = nOf(d);
          const oc = o == null ? T.light : o >= 0.15 ? T.greenPos : o >= 0.05 ? T.amber : T.red;
          return (
            <div key={d} style={{ textAlign: "center", fontFamily: T.mono }}>
              <div style={{ position: "relative", height: H, background: "var(--bg)", borderRadius: 3, border: `1px solid ${T.border}` }}>
                {o != null && <div style={{ position: "absolute", bottom: 0, left: 2, right: 2, height: (o / scaleMax) * H, background: oc, opacity: 0.5, borderRadius: "0 0 2px 2px" }} />}
                {pr != null && <div style={{ position: "absolute", bottom: Math.min(H - 2, (pr / scaleMax) * H), left: 0, right: 0, height: 2, background: T.purple }} title={`predicted ${(pr * 100).toFixed(0)}%`} />}
              </div>
              <div style={{ fontSize: 9, color: T.muted, marginTop: 3, fontWeight: 600 }}>D{d}</div>
              <div style={{ fontSize: 10, color: oc, fontWeight: 700 }}>{o != null ? `${(o * 100).toFixed(0)}%` : "—"}</div>
              <div style={{ fontSize: 8, color: T.purple }}>{pr != null ? `p${(pr * 100).toFixed(0)}` : "·"}</div>
              <div style={{ fontSize: 8, color: T.light }}>n{n}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function PicksTable({ rows, cycleLabel }: { rows: MethodPredRow[]; cycleLabel: string }) {
  const [methodFilter, setMethodFilter] = useState<"all" | "stock" | "long_call">("all");
  const [regimeFilter, setRegimeFilter] = useState<"all" | "30d_p10" | "60d">("all");
  const [outcomeFilter, setOutcomeFilter] = useState<"all" | "OPEN" | "SOLD_AT_TOUCH" | "STOPPED" | "TERMINAL">("all");
  const [sortKey, setSortKey] = useState<PickSortKey>("symbol");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [livePrices, setLivePrices] = useState<Record<string, number>>({});
  const [liveAsOf, setLiveAsOf] = useState<string>("");

  const filtered = useMemo(() => rows.filter(r =>
    (methodFilter === "all" || r.method === methodFilter) &&
    (regimeFilter === "all" || r.regime === regimeFilter) &&
    (outcomeFilter === "all" || r.outcome_tag === outcomeFilter)
  ), [rows, methodFilter, regimeFilter, outcomeFilter]);

  // Group prediction rows by symbol → one summary line per pick (entry context is
  // shared across the 4 method rows; outcomes are rolled up from the underlying).
  const groups = useMemo<PickGroup[]>(() => {
    const m = new Map<string, MethodPredRow[]>();
    for (const r of filtered) { const a = m.get(r.symbol); if (a) a.push(r); else m.set(r.symbol, [r]); }
    const arr: PickGroup[] = Array.from(m.entries()).map(([symbol, rs]) => {
      const stockRows = rs.filter(x => x.method === "stock");
      const base = stockRows[0] ?? rs[0];
      const outcomeRows = stockRows.length ? stockRows : rs;
      return {
        symbol, rows: rs, sector: base.sector, entry_date: base.entry_date, decile: base.decile, entry_price: base.entry_price,
        iv_at_entry: base.iv_at_entry, ivr_at_entry: base.ivr_at_entry, last: base.current_price,
        maxPlus: Math.max(...outcomeRows.map(x => x.max_high_observed_pct)),
        expDd: ((): number | null => { const v = outcomeRows.map(x => x.expected_dd).filter((d): d is number => d != null); return v.length ? Math.min(...v) : null; })(),
        maxMinus: Math.min(...outcomeRows.map(x => x.max_drawdown_observed_pct)),
        days: Math.max(...rs.map(x => x.days_observed)),
        touches: rs.filter(x => x.outcome_tag === "SOLD_AT_TOUCH").length,
        stops: rs.filter(x => x.outcome_tag === "STOPPED").length,
        open: rs.filter(x => x.outcome_tag === "OPEN").length,
      };
    });
    const val = (g: PickGroup): number | string =>
      sortKey === "symbol" ? g.symbol : sortKey === "decile" ? g.decile : sortKey === "entry" ? g.entry_price
      : sortKey === "iv" ? (g.iv_at_entry ?? -1) : sortKey === "ivr" ? (g.ivr_at_entry ?? -1)
      : sortKey === "last" ? g.last : sortKey === "maxplus" ? g.maxPlus : sortKey === "expdd" ? (g.expDd ?? 0) : sortKey === "maxminus" ? g.maxMinus : g.days;
    arr.sort((a, b) => {
      const va = val(a), vb = val(b);
      if (typeof va === "string" || typeof vb === "string") {
        const c = String(va).localeCompare(String(vb)); return sortDir === "asc" ? c : -c;
      }
      return sortDir === "asc" ? va - vb : vb - va;
    });
    return arr;
  }, [filtered, sortKey, sortDir]);

  const onSort = (k: PickSortKey) => {
    if (k === sortKey) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortKey(k); setSortDir(k === "symbol" ? "asc" : "desc"); }
  };
  const toggleExpand = (sym: string) => setExpanded(prev => {
    const next = new Set(prev); if (next.has(sym)) next.delete(sym); else next.add(sym); return next;
  });

  // Live underlying prices — poll FMP quotes every 60s for the picks in view, cache-busted
  // (&t=) so the route's revalidate window doesn't stale them. Option marks aren't repriced here.
  const allSymbols = useMemo(() => Array.from(new Set(rows.map(r => r.symbol))), [rows]);
  useEffect(() => {
    if (!allSymbols.length) return;
    let cancelled = false;
    const poll = async () => {
      const out: Record<string, number> = {};
      for (let i = 0; i < allSymbols.length; i += 40) {
        const chunk = allSymbols.slice(i, i + 40);
        try {
          const res = await fetch(`/api/fmp?e=batch-quote&symbols=${chunk.join(",")}&t=${Date.now()}`);
          if (!res.ok) continue;
          const arr = await res.json();
          if (Array.isArray(arr)) for (const q of arr) {
            if (q && typeof q.symbol === "string" && typeof q.price === "number") out[q.symbol] = q.price;
          }
        } catch { /* ignore a failed chunk */ }
      }
      if (!cancelled && Object.keys(out).length) {
        setLivePrices(prev => ({ ...prev, ...out }));
        setLiveAsOf(new Date().toLocaleTimeString());
      }
    };
    poll();
    const id = setInterval(poll, 60000);
    return () => { cancelled = true; clearInterval(id); };
  }, [allSymbols]);

  const methodLabel = (r: MethodPredRow) => {
    const barrier = r.regime === "30d_p10" ? "+10%/30d" : "+20%/60d";
    return `${r.method === "stock" ? "Stock" : "Call"} ${barrier}`;
  };
  const outcomeColor = (tag: string) =>
    tag === "SOLD_AT_TOUCH" ? T.greenPos
    : tag === "STOPPED" ? T.red
    : tag === "TERMINAL" ? T.muted
    : T.text;

  return (
    <Card>
      <SH title={`Per-pick detail (${groups.length} picks · ${filtered.length} rows)`} icon={<Search size={12} />}
          sub={`${cycleLabel} — one row per pick; click to expand its method lines. Entry context (price, IV, IVR, decile) is shared across the 4 methods. Sortable by any summary column.`} />

      <div style={{ display: "flex", gap: 14, padding: "10px 14px", borderBottom: `1px solid ${T.divider}`, alignItems: "center", flexWrap: "wrap", fontFamily: T.mono, fontSize: 11 }}>
        <FilterPills label="METHOD" value={methodFilter} setValue={setMethodFilter as any}
          options={[["all","All"],["stock","Stock"],["long_call","Call"]]} />
        <FilterPills label="REGIME" value={regimeFilter} setValue={setRegimeFilter as any}
          options={[["all","All"],["30d_p10","30d +10%"],["60d","60d +20%"]]} />
        <FilterPills label="OUTCOME" value={outcomeFilter} setValue={setOutcomeFilter as any}
          options={[["all","All"],["OPEN","Open"],["SOLD_AT_TOUCH","Touch"],["STOPPED","Stop"],["TERMINAL","Term"]]} />
        {liveAsOf && <span style={{ marginLeft: "auto", color: T.greenPos, fontSize: 10, fontWeight: 600 }}>● live · underlying as of {liveAsOf}</span>}
      </div>

      {filtered.length === 0 ? (
        <div style={{ padding: 30, textAlign: "center", color: T.light, fontSize: 11, fontFamily: T.mono }}>
          No rows match the current filters.
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: T.mono, fontSize: 11 }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${T.divider}` }}>
                <th colSpan={4} style={{ ...th, fontSize: 9, color: T.light, textAlign: "left", paddingLeft: 8, paddingBottom: 2 }}>PICK</th>
                <th colSpan={4} style={{ ...th, fontSize: 9, color: T.light, textAlign: "left", paddingBottom: 2, borderLeft: `1px dashed ${T.divider}` }}>ENTRY CONTEXT</th>
                <th colSpan={5} style={{ ...th, fontSize: 9, color: T.light, textAlign: "left", paddingBottom: 2, borderLeft: `1px dashed ${T.divider}` }}>METHOD-SPECIFIC</th>
                <th colSpan={6} style={{ ...th, fontSize: 9, color: T.light, textAlign: "left", paddingBottom: 2, borderLeft: `1px dashed ${T.divider}` }}>OUTCOME</th>
              </tr>
              <tr>
                <SortTh label="Symbol" k="symbol" sortKey={sortKey} sortDir={sortDir} onSort={onSort} style={{ textAlign: "left" }} />
                <th style={{ ...th, textAlign: "left" }}>Sector</th>
                <th style={{ ...th, textAlign: "left" }}>Method</th>
                <SortTh label="D" k="decile" sortKey={sortKey} sortDir={sortDir} onSort={onSort} style={{ textAlign: "right" }} />
                <SortTh label="Entry $" k="entry" sortKey={sortKey} sortDir={sortDir} onSort={onSort} style={{ textAlign: "right", borderLeft: `1px dashed ${T.divider}` }} />
                <th style={{ ...th, textAlign: "right" }}>Barrier</th>
                <SortTh label="ATM IV" k="iv" sortKey={sortKey} sortDir={sortDir} onSort={onSort} style={{ textAlign: "right" }} />
                <SortTh label="IVR" k="ivr" sortKey={sortKey} sortDir={sortDir} onSort={onSort} style={{ textAlign: "right" }} />
                <th style={{ ...th, textAlign: "right", borderLeft: `1px dashed ${T.divider}` }}>Stop</th>
                <th style={{ ...th, textAlign: "right" }}>Strike</th>
                <th style={{ ...th, textAlign: "right" }}>Ask</th>
                <th style={{ ...th, textAlign: "right" }}>Edge</th>
                <th style={{ ...th, textAlign: "right" }} title="Expected value: model fair value per share vs the ask you pay">EV</th>
                <SortTh label="Last $" k="last" sortKey={sortKey} sortDir={sortDir} onSort={onSort} style={{ textAlign: "right", borderLeft: `1px dashed ${T.divider}` }} />
                <SortTh label="Max+" k="maxplus" sortKey={sortKey} sortDir={sortDir} onSort={onSort} style={{ textAlign: "right" }} />
                <SortTh label="Exp.DD" k="expdd" sortKey={sortKey} sortDir={sortDir} onSort={onSort} title="Model's predicted max drawdown at entry — compare against the realized Max−" style={{ textAlign: "right" }} />
                <SortTh label="Max−" k="maxminus" sortKey={sortKey} sortDir={sortDir} onSort={onSort} style={{ textAlign: "right" }} />
                <SortTh label="Days" k="days" sortKey={sortKey} sortDir={sortDir} onSort={onSort} style={{ textAlign: "right" }} />
                <th style={{ ...th, textAlign: "right" }}>Result</th>
              </tr>
            </thead>
            <tbody>
              {groups.map((g) => {
                const isOpen = expanded.has(g.symbol);
                return (
                  <Fragment key={g.symbol}>
                    {/* Summary row — one per symbol; click to expand the method lines */}
                    <tr style={{ borderTop: `1px solid ${T.divider}`, cursor: "pointer" }}
                        onClick={() => toggleExpand(g.symbol)}
                        onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "var(--bg-hover)"; }}
                        onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = ""; }}>
                      <td style={{ ...td, textAlign: "left", fontWeight: 700, color: T.text }}>
                        <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
                          {isOpen ? <ChevronDown size={11} style={{ color: T.muted }} /> : <ChevronRight size={11} style={{ color: T.light }} />}
                          {g.symbol}
                        </span>
                        {g.entry_date && <div style={{ fontSize: 9, fontWeight: 400, color: T.light, marginLeft: 16 }} title="When this pick's entry price + ML were recorded">entered {g.entry_date}</div>}
                      </td>
                      <td style={{ ...td, textAlign: "left", color: T.light, fontSize: 10 }}>{g.sector ?? "—"}</td>
                      <td style={{ ...td, textAlign: "left", color: T.light }}>{g.rows.length} method{g.rows.length === 1 ? "" : "s"}</td>
                      <td style={{ ...td, textAlign: "right", color: T.muted }}>{g.decile}</td>
                      <td style={{ ...td, textAlign: "right", color: T.text, borderLeft: `1px dashed ${T.divider}` }}>${g.entry_price.toFixed(2)}</td>
                      <td style={{ ...td, textAlign: "right", color: T.light }}>—</td>
                      <td style={{ ...td, textAlign: "right", color: T.muted }}>{g.iv_at_entry != null ? `${(g.iv_at_entry * 100).toFixed(0)}%` : "—"}</td>
                      <td style={{ ...td, textAlign: "right", color: T.muted }}>{g.ivr_at_entry != null ? `${g.ivr_at_entry}` : "—"}</td>
                      <td style={{ ...td, textAlign: "right", color: T.light, borderLeft: `1px dashed ${T.divider}` }}>—</td>
                      <td style={{ ...td, textAlign: "right", color: T.light }}>—</td>
                      <td style={{ ...td, textAlign: "right", color: T.light }}>—</td>
                      <td style={{ ...td, textAlign: "right", color: T.light }}>—</td>
                      <td style={{ ...td, textAlign: "right", color: T.light }}>—</td>
                      <td style={{ ...td, textAlign: "right", color: T.text, borderLeft: `1px dashed ${T.divider}` }}>${(livePrices[g.symbol] ?? g.last).toFixed(2)}</td>
                      <td style={{ ...td, textAlign: "right", color: T.greenPos }}>+{g.maxPlus.toFixed(1)}%</td>
                      <td style={{ ...td, textAlign: "right", color: T.amber }} title="Predicted max drawdown (model, at entry)">{g.expDd != null ? `${g.expDd.toFixed(1)}%` : "—"}</td>
                      <td style={{ ...td, textAlign: "right", color: T.red }}>{g.maxMinus.toFixed(1)}%</td>
                      <td style={{ ...td, textAlign: "right", color: T.muted }}>{g.days}d</td>
                      <td style={{ ...td, textAlign: "right", fontSize: 10, fontWeight: 700 }}>
                        <span style={{ display: "inline-flex", gap: 6, justifyContent: "flex-end", flexWrap: "wrap" }}>
                          {g.touches > 0 && <span style={{ color: T.greenPos }}>TOUCH×{g.touches}</span>}
                          {g.stops > 0 && <span style={{ color: T.red }}>STOP×{g.stops}</span>}
                          {g.open > 0 && <span style={{ color: T.muted }}>OPEN×{g.open}</span>}
                        </span>
                      </td>
                    </tr>

                    {/* Expanded: the individual method lines (Stock/Call × 30d/60d) */}
                    {isOpen && g.rows.map((r, i) => {
                      const realized = r.realized_return_pct;
                      const realizedC = realized === null || realized === undefined
                        ? T.muted : realized >= 0 ? T.greenPos : T.red;
                      return (
                        <tr key={`${g.symbol}-${r.regime}-${r.method}-${i}`} style={{ background: "var(--bg-elevated)" }}>
                          <td style={{ ...td }}></td>
                          <td style={{ ...td }}></td>
                          <td style={{ ...td, textAlign: "left", color: T.muted, paddingLeft: 22 }}>{methodLabel(r)}</td>
                          <td style={{ ...td, textAlign: "right", color: T.muted }}>{r.decile}</td>
                          <td style={{ ...td, textAlign: "right", color: T.text, borderLeft: `1px dashed ${T.divider}` }}>${r.entry_price.toFixed(2)}</td>
                          <td style={{ ...td, textAlign: "right", color: T.muted }}>
                            ${r.barrier_price.toFixed(2)}<span style={{ color: T.light, fontSize: 9, marginLeft: 3 }}>(+{r.barrier_target_pct}%)</span>
                          </td>
                          <td style={{ ...td, textAlign: "right", color: T.muted }}>{r.iv_at_entry != null ? `${(r.iv_at_entry * 100).toFixed(0)}%` : "—"}</td>
                          <td style={{ ...td, textAlign: "right", color: T.muted }}>{r.ivr_at_entry != null ? `${r.ivr_at_entry}` : "—"}</td>
                          <td style={{ ...td, textAlign: "right", color: r.stop_price != null ? T.red : T.light, borderLeft: `1px dashed ${T.divider}` }}>
                            {r.method === "stock" ? (r.stop_price != null ? `$${r.stop_price.toFixed(2)}` : "—") : "—"}
                          </td>
                          <td style={{ ...td, textAlign: "right", color: T.muted }}>{r.method === "long_call" && r.chosen_leg_strike != null ? `$${r.chosen_leg_strike.toFixed(0)}` : "—"}</td>
                          <td style={{ ...td, textAlign: "right", color: T.muted }}>{r.method === "long_call" && r.entry_quote_ask != null ? `$${r.entry_quote_ask.toFixed(2)}` : "—"}</td>
                          <td style={{ ...td, textAlign: "right", color: (r.edge_pct_at_entry ?? 0) > 0 ? T.greenPos : T.red, fontWeight: 600 }}>
                            {r.method === "long_call" && r.edge_pct_at_entry != null ? `${(r.edge_pct_at_entry * 100).toFixed(0)}%` : "—"}
                          </td>
                          <td style={{ ...td, textAlign: "right", fontWeight: 600, color: r.method === "long_call" && r.edge_dollars_at_entry != null ? (r.edge_dollars_at_entry >= 0 ? T.greenPos : T.red) : T.light }}
                              title={r.method === "long_call" ? "EV at touch per contract = (barrier - strike - ask) x 100" : ""}>
                            {r.method === "long_call" && r.edge_dollars_at_entry != null ? `${r.edge_dollars_at_entry >= 0 ? "+" : ""}$${r.edge_dollars_at_entry.toFixed(0)}` : "—"}
                          </td>
                          <td style={{ ...td, textAlign: "right", color: T.text, borderLeft: `1px dashed ${T.divider}` }}>${(r.method === "stock" ? (livePrices[r.symbol] ?? r.current_price) : r.current_price).toFixed(2)}</td>
                          <td style={{ ...td, textAlign: "right", color: T.greenPos }}>+{r.max_high_observed_pct.toFixed(1)}%</td>
                          <td style={{ ...td, textAlign: "right", color: T.amber }}>{r.expected_dd != null ? `${r.expected_dd.toFixed(1)}%` : "—"}</td>
                          <td style={{ ...td, textAlign: "right", color: T.red }}>{r.max_drawdown_observed_pct.toFixed(1)}%</td>
                          <td style={{ ...td, textAlign: "right", color: T.muted }}>{r.days_observed}d</td>
                          <td style={{ ...td, textAlign: "right", color: outcomeColor(r.outcome_tag), fontWeight: 700, fontSize: 10 }}>
                            <div>{r.outcome_tag.replace(/_/g, " ")}</div>
                            {realized !== null && realized !== undefined && (
                              <div style={{ color: realizedC, fontSize: 10, fontWeight: 700 }}>{realized >= 0 ? "+" : ""}{realized.toFixed(1)}%</div>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

function FilterPills({ label, value, setValue, options }: {
  label: string; value: string; setValue: (v: string) => void;
  options: Array<[string, string]>;
}) {
  return (
    <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
      <span style={{ color: T.light, fontSize: 9, fontWeight: 700, letterSpacing: 0.5 }}>{label}</span>
      {options.map(([v, lbl]) => (
        <button key={v} onClick={() => setValue(v)}
          style={{
            padding: "3px 9px", fontSize: 10, fontFamily: T.mono, fontWeight: 600,
            border: "none", borderRadius: 4, cursor: "pointer",
            background: value === v ? T.greenLight : "transparent",
            color: value === v ? T.green : T.muted,
          }}>{lbl}</button>
      ))}
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// Shell
// ══════════════════════════════════════════════════════════════════════════════
export default function Performance() {
  return (
    <div style={{ padding: "16px 20px", maxWidth: 1400, margin: "0 auto" }}>
      <div style={{ marginBottom: 16, paddingBottom: 10, borderBottom: `1px solid ${T.border}` }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
          <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: "0.1em", color: T.text, fontFamily: T.mono }}>SYSTEM PERFORMANCE</span>
          <span style={{ fontSize: 12, color: T.muted, fontFamily: T.mono }}>/ method validation</span>
        </div>
        <p style={{ fontSize: 10, color: T.muted, fontFamily: T.mono, marginTop: 4 }}>
          Forward-only paper-tracking: every enriched pick is tracked over 30/60 days across four exit/payoff methods - stock and long-call against the +10%/30d and +20%/60d barriers - decile-bucketed for calibration validation. Predicted vs realized, per pick.
        </p>
      </div>

      <MethodsTab />
    </div>
  );
}
