"use client";
import { useState, useEffect, useMemo } from "react";
import { TrendingUp, BarChart3, Target, Clock, ChevronDown, ChevronRight, Search, FlaskConical } from "lucide-react";

// ── Data sources ─────────────────────────────────────────────────────────────
const CALIBRATION_V2 = "/api/performance/calibration-v2";
const METHOD_TRACKS = "/api/performance/method-tracks"; // frozen v1 sim section only

// ══════════════════════════════════════════════════════════════════════════════
// /performance/calibration-v2 payload — contract C5 (verbatim)
// ══════════════════════════════════════════════════════════════════════════════
type RecState = "OPEN" | "TOUCHED" | "NO_TOUCH";

interface CalibRecord {
  symbol: string;
  entry_date: string;
  entry_price: number;
  sector: string | null;
  p10: number | null;
  p20: number | null;
  decile_30d: number | null;
  decile_60d: number | null;
  bars_elapsed_30d: number | null;
  bars_elapsed_60d: number | null;
  max_high_pct: number;
  max_dd_pct: number;
  state_30d: RecState | null;
  state_60d: RecState | null;
  touch_bar_30d: number | null;
  touch_bar_60d: number | null;
}

interface DecileRow {
  decile: number;
  n_total: number;
  n_matured: number;
  n_open: number;
  n_touched: number;
  matured_observed_rate: number | null;
  predicted_mean_p: number | null;
  expected_touches_to_date: number;
  observed_touches_to_date: number;
  ci_low: number;
  ci_high: number;
}

interface CurvePoint {
  scan_date: string;
  expected: number;
  observed: number;
  ci_low: number;
  ci_high: number;
}

type DecileKey = "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9" | "10";

interface HorizonBlock {
  horizon_bars: 30 | 60;
  barrier_pct: 10 | 20;
  cycle: {
    tracking_since: string;
    n_scan_dates: number;
    latest_scan_date: string;
    n_total: number;
    n_matured: number;
    n_open: number;
    n_touched: number;
    n_pending: number;
    n_dropped: number;
  };
  headline: {
    expected_touches_to_date: number;
    observed_touches_to_date: number;
    ci_low: number;
    ci_high: number;
    z: number | null;
  };
  health: {
    status: "HEALTHY" | "DRIFTING" | "DEGRADED" | "UNDER_SAMPLED";
    kill_switch_active: boolean;
    z_score: number | null;
    n_effective: number;
    consecutive_below_band: number;
    rule: string;
    computed_date: string;
  };
  deciles: DecileRow[]; // length 10 always, decile asc
  curve: {
    pooled: CurvePoint[];
    by_decile: Record<DecileKey, CurvePoint[]>;
  };
}

interface CalibrationV2 {
  schema_version: "calibration-v2";
  as_of: string;
  model: {
    version: string;
    trained_through: string;
    decile_threshold_source: string;
  };
  horizons: { "30d": HorizonBlock; "60d": HorizonBlock };
  records: CalibRecord[];
}

// ══════════════════════════════════════════════════════════════════════════════
// Frozen v1 simulation types — trimmed read_method_tracks() contract
// (SimBlock is NOT part of calibration-v2; this section keeps its own fetch.)
// ══════════════════════════════════════════════════════════════════════════════
interface MethodStats {
  n: number;
  barrier_hit_count: number; stopped_count: number; terminal_count: number;
  barrier_hit_rate: number; winning_trade_rate: number | null;
  mean_realized_return_pct: number; median_realized_return_pct: number;
  tail_p5_return_pct: number; tail_p95_return_pct: number;
  worst_drawdown_pct: number; best_runup_pct: number;
  portfolio_return_pct: number | null;
  underpowered: boolean;
}
interface SimCycleSummary {
  cycle_id: string;
  regime: string;
  total_predictions: number; n_picks: number;
  by_method: { stock: MethodStats; long_call: MethodStats };
}
interface SimRegimeBlock {
  regime: string;
  barrier_target_pct: number;
  hit_window_days: number;
  current_cycle: SimCycleSummary | null;
  archived_cycles: SimCycleSummary[];
}
interface SimTracks {
  regimes: Record<string, SimRegimeBlock>;
  as_of: string;
}
interface MethodRow {
  key: string;
  method: "stock" | "long_call";
  label: string;
  stats: MethodStats;
}

// ── Theme ───────────────────────────────────────────────────────────────────
const T = {
  bg: "var(--bg)",
  card: "var(--bg-surface)",
  text: "var(--text)",
  textMuted: "var(--text-muted)",
  textLight: "var(--text-light)",
  green: "var(--green)",
  greenPos: "var(--green)",
  greenLight: "var(--green-light)",
  red: "var(--red)",
  redLight: "var(--red-light)",
  amber: "var(--amber)",
  amberLight: "var(--amber-light)",
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
function SH({ title, icon, sub, accent }: { title: string; icon?: React.ReactNode; sub?: string; accent?: string }) {
  const c = accent || T.green;
  const underline = accent ? T.amberLight : T.greenLight;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, fontWeight: 600, letterSpacing: "0.08em", color: c, fontFamily: T.mono, textTransform: "uppercase", marginBottom: 12, paddingBottom: 8, borderBottom: `2px solid ${underline}` }}>
      {icon}{title}
      {sub && <span style={{ marginLeft: "auto", fontSize: 9, color: T.light, fontWeight: 400, textTransform: "none", letterSpacing: 0 }}>{sub}</span>}
    </div>
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
// SECTION 1 — Calibration headline cards (expected vs observed touches)
// ══════════════════════════════════════════════════════════════════════════════
function HealthChip({ health }: { health: HorizonBlock["health"] }) {
  const s = health.status;
  const color = s === "HEALTHY" ? T.greenPos : s === "DRIFTING" ? T.amber : s === "DEGRADED" ? T.red : T.muted;
  const bg = s === "HEALTHY" ? T.greenLight : s === "DRIFTING" ? T.amberLight : s === "DEGRADED" ? T.redLight : "var(--bg)";
  return (
    <span style={{ display: "inline-flex", gap: 5, alignItems: "center" }} title={`${health.rule} · computed ${health.computed_date}`}>
      <span style={{ padding: "2px 8px", borderRadius: 4, fontSize: 9, fontWeight: 700, fontFamily: T.mono, color, background: bg, border: s === "UNDER_SAMPLED" ? `1px solid ${T.divider}` : "none", whiteSpace: "nowrap" }}>
        {s.replace(/_/g, " ")}{s === "UNDER_SAMPLED" ? ` · n_eff ${health.n_effective.toFixed(1)}` : ""}
      </span>
      {health.kill_switch_active && (
        <span style={{ padding: "2px 8px", borderRadius: 4, fontSize: 9, fontWeight: 700, fontFamily: T.mono, color: "#fff", background: T.red, whiteSpace: "nowrap" }}>
          KILL SWITCH
        </span>
      )}
    </span>
  );
}

function HeadlineCard({ label, h, model }: { label: string; h: HorizonBlock; model: CalibrationV2["model"] }) {
  const hl = h.headline;
  const obs = hl.observed_touches_to_date;
  const exp = hl.expected_touches_to_date;
  // Observed color: green inside the 95% band, red below ci_low (model
  // overconfident — the failure that matters), amber above ci_high.
  const obsColor = obs < hl.ci_low ? T.red : obs > hl.ci_high ? T.amber : T.greenPos;
  const scaleMax = Math.max(hl.ci_high, obs, exp, 1) * 1.15;
  const pos = (v: number) => Math.min(100, Math.max(0, (v / scaleMax) * 100));
  const c = h.cycle;
  return (
    <Card>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: "0.1em", color: T.muted, fontFamily: T.mono }}>{label}</div>
        <div style={{ marginLeft: "auto" }}><HealthChip health={h.health} /></div>
      </div>
      <div style={{ fontSize: 26, fontWeight: 700, fontFamily: T.mono, marginTop: 4 }}>
        <span style={{ color: obsColor }}>{obs.toFixed(0)}</span>
        <span style={{ color: T.light, fontWeight: 400 }}> / </span>
        <span style={{ color: T.text }}>{exp.toFixed(1)}</span>
      </div>
      <div style={{ fontSize: 9, color: T.light, fontFamily: T.mono, marginTop: 2 }}>
        observed / expected touches · 95% band {hl.ci_low.toFixed(1)}–{hl.ci_high.toFixed(1)}{hl.z != null ? ` · z ${hl.z >= 0 ? "+" : ""}${hl.z.toFixed(2)}` : ""}
      </div>
      {/* Bullet bar: gray band rect, purple tick at expected, bold dot at observed */}
      <div style={{ position: "relative", height: 14, background: "var(--bg)", borderRadius: 4, border: `1px solid ${T.border}`, marginTop: 10 }}>
        <div style={{ position: "absolute", left: `${pos(hl.ci_low)}%`, width: `${Math.max(0, pos(hl.ci_high) - pos(hl.ci_low))}%`, top: 2, bottom: 2, background: T.divider, borderRadius: 2 }} title={`95% band ${hl.ci_low.toFixed(1)}–${hl.ci_high.toFixed(1)}`} />
        <div style={{ position: "absolute", left: `calc(${pos(exp)}% - 1px)`, top: 0, bottom: 0, width: 2, background: T.purple }} title={`expected ${exp.toFixed(1)}`} />
        <div style={{ position: "absolute", left: `calc(${pos(obs)}% - 5px)`, top: "50%", marginTop: -5, width: 10, height: 10, borderRadius: "50%", background: obsColor, border: `2px solid ${T.card}`, boxShadow: "0 0 0 1px rgba(0,0,0,0.08)" }} title={`observed ${obs.toFixed(0)}`} />
      </div>
      <div style={{ fontSize: 9, color: T.muted, fontFamily: T.mono, marginTop: 8 }}>
        n {c.n_total} · matured {c.n_matured} · open {c.n_open} · pending {c.n_pending} · dropped {c.n_dropped}
      </div>
      <div style={{ fontSize: 8, color: T.light, fontFamily: T.mono, marginTop: 4 }}>
        model {model.version} · thresholds {model.decile_threshold_source} · tracking since {c.tracking_since} · {c.n_scan_dates} scans
      </div>
    </Card>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// SECTION 2 — Per-decile calibration bars (server-computed; honest empty state)
// ══════════════════════════════════════════════════════════════════════════════
function DecileBars({ label, deciles }: { label: string; deciles: DecileRow[] }) {
  const rows = [...deciles].sort((a, b) => a.decile - b.decile);
  const scaleMax = Math.max(0.1, ...rows.flatMap(r => [r.matured_observed_rate ?? 0, r.predicted_mean_p ?? 0])) * 1.15;
  const H = 84;
  const totalMatured = rows.reduce((s, r) => s + r.n_matured, 0);
  const totalN = rows.reduce((s, r) => s + r.n_total, 0);
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontFamily: T.mono, fontSize: 10, fontWeight: 700, color: T.text, marginBottom: 6 }}>
        {label}<span style={{ color: T.light, fontWeight: 400 }}> · {totalMatured} matured / {totalN} total</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(10, 1fr)", gap: 5, alignItems: "end" }}>
        {rows.map(r => {
          const o = r.matured_observed_rate;
          const pr = r.predicted_mean_p;
          const empty = r.n_matured === 0;
          // Color by |observed − predicted| only once n_matured ≥ 5; below
          // that always muted. Never a red 0% on an empty decile.
          let barColor = T.light;
          if (!empty && o != null) {
            if (r.n_matured >= 5 && pr != null) {
              const gap = Math.abs(o - pr);
              barColor = gap <= 0.10 ? T.greenPos : gap <= 0.20 ? T.amber : T.red;
            } else {
              barColor = T.muted;
            }
          }
          return (
            <div key={r.decile} style={{ textAlign: "center", fontFamily: T.mono }}>
              <div
                style={{ position: "relative", height: H, background: "var(--bg)", borderRadius: 3, border: `1px solid ${T.border}` }}
                title={empty ? "no matured rows yet" : `observed ${(o! * 100).toFixed(0)}% over ${r.n_matured} matured`}>
                {empty ? (
                  <div style={{ position: "absolute", inset: 2, borderRadius: 2, background: `repeating-linear-gradient(45deg, ${T.divider}, ${T.divider} 3px, transparent 3px, transparent 7px)`, opacity: 0.6 }} />
                ) : (
                  o != null && <div style={{ position: "absolute", bottom: 0, left: 2, right: 2, height: Math.min(H - 2, (o / scaleMax) * H), background: barColor, opacity: 0.55, borderRadius: "0 0 2px 2px" }} />
                )}
                {pr != null && <div style={{ position: "absolute", bottom: Math.min(H - 2, (pr / scaleMax) * H), left: 0, right: 0, height: 2, background: T.purple }} title={`predicted ${(pr * 100).toFixed(0)}%`} />}
              </div>
              <div style={{ fontSize: 9, color: T.muted, marginTop: 3, fontWeight: 600 }}>D{r.decile}</div>
              <div style={{ fontSize: 10, color: empty ? T.light : barColor, fontWeight: 700 }} title={empty ? "no matured rows yet" : undefined}>
                {empty || o == null ? "—" : `${(o * 100).toFixed(0)}%`}
              </div>
              <div style={{ fontSize: 8, color: T.purple }}>{pr != null ? `p${(pr * 100).toFixed(0)}` : "·"}</div>
              <div style={{ fontSize: 8, color: T.light }}>n {r.n_matured}/{r.n_total}</div>
              <div style={{ fontSize: 8, color: T.light }} title="observed / expected touches to date (censoring-aware)">
                {r.observed_touches_to_date.toFixed(0)}/{r.expected_touches_to_date.toFixed(1)}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// SECTION 3 — Cumulative touch curve (inline SVG, nightly points)
// ══════════════════════════════════════════════════════════════════════════════
function TouchCurve({ horizons }: { horizons: CalibrationV2["horizons"] }) {
  const [hKey, setHKey] = useState<"30d" | "60d">("30d");
  const [dec, setDec] = useState<string>("pooled");
  const h = horizons[hKey];
  const points: CurvePoint[] = dec === "pooled"
    ? (h.curve.pooled ?? [])
    : ((h.curve.by_decile?.[dec as DecileKey] ?? []) as CurvePoint[]);

  const W = 720, HT = 230, padL = 42, padR = 12, padT = 12, padB = 26;
  const plotW = W - padL - padR, plotH = HT - padT - padB;
  const yMax = Math.max(1, ...points.map(p => Math.max(p.ci_high, p.observed, p.expected))) * 1.1;
  const X = (i: number) => points.length <= 1 ? padL + plotW / 2 : padL + (i * plotW) / (points.length - 1);
  const Y = (v: number) => padT + plotH - (Math.max(0, v) / yMax) * plotH;

  const bandPts = points.map((p, i) => `${X(i).toFixed(1)},${Y(p.ci_high).toFixed(1)}`)
    .concat(points.map((p, i) => `${X(i).toFixed(1)},${Y(p.ci_low).toFixed(1)}`).reverse())
    .join(" ");
  const expectedPts = points.map((p, i) => `${X(i).toFixed(1)},${Y(p.expected).toFixed(1)}`).join(" ");
  let observedPath = "";
  points.forEach((p, i) => {
    const x = X(i).toFixed(1), y = Y(p.observed).toFixed(1);
    observedPath += i === 0 ? `M ${x} ${y}` : ` H ${x} V ${y}`; // step-after
  });
  // Dedupe indices: with 1-2 points first/mid/last collide (duplicate React keys).
  const xIdx = points.length === 0 ? [] :
    Array.from(new Set([0, Math.floor((points.length - 1) / 2), points.length - 1]));
  const xLabels: Array<[number, string]> = xIdx.map(i => [i, points[i].scan_date]);

  return (
    <Card style={{ marginBottom: 20 }}>
      <SH title="Cumulative touch curve" icon={<TrendingUp size={12} />}
          sub="Expected (purple) vs observed (green step) cumulative touches by scan date · gray = 95% band · appended nightly" />
      <div style={{ display: "flex", gap: 14, alignItems: "center", flexWrap: "wrap", marginBottom: 10 }}>
        <FilterPills label="HORIZON" value={hKey} setValue={(v) => setHKey(v as "30d" | "60d")}
          options={[["30d", "30d +10%"], ["60d", "60d +20%"]]} />
        <FilterPills label="DECILE" value={dec} setValue={setDec}
          options={[["pooled", "Pooled"], ["10", "D10"], ["9", "D9"], ["8", "D8"], ["7", "D7"], ["6", "D6"], ["5", "D5"], ["4", "D4"], ["3", "D3"], ["2", "D2"], ["1", "D1"]]} />
        <span style={{ marginLeft: "auto", fontSize: 9, color: T.light, fontFamily: T.mono }}>{points.length} nightly points</span>
      </div>
      {points.length === 0 ? (
        <div style={{ padding: 30, textAlign: "center", color: T.light, fontSize: 11, fontFamily: T.mono }}>
          No curve points yet for this view — one point is appended per nightly run.
        </div>
      ) : (
        <svg viewBox={`0 0 ${W} ${HT}`} style={{ width: "100%", height: "auto", display: "block" }}>
          {/* y gridlines */}
          {[0, 0.5, 1].map(f => {
            const v = yMax * f;
            return (
              <g key={f}>
                <line x1={padL} y1={Y(v)} x2={W - padR} y2={Y(v)} stroke={T.divider} strokeWidth={1} strokeDasharray={f === 0 ? "" : "3 4"} />
                <text x={padL - 6} y={Y(v) + 3} textAnchor="end" fontSize={8} fill={T.light} fontFamily={T.mono}>{v.toFixed(0)}</text>
              </g>
            );
          })}
          {/* 95% band */}
          {points.length > 1 && <polygon points={bandPts} fill={T.divider} opacity={0.55} />}
          {/* expected */}
          {points.length > 1
            ? <polyline points={expectedPts} fill="none" stroke={T.purple} strokeWidth={1.8} />
            : <circle cx={X(0)} cy={Y(points[0].expected)} r={3} fill={T.purple} />}
          {/* observed step line */}
          {points.length > 1
            ? <path d={observedPath} fill="none" stroke={T.green} strokeWidth={2} />
            : <circle cx={X(0)} cy={Y(points[0].observed)} r={3} fill={T.green} />}
          {/* x labels */}
          {xLabels.map(([i, lbl]) => (
            <text key={`${i}-${lbl}`} x={X(i)} y={HT - 8} textAnchor={i === 0 ? "start" : i === points.length - 1 ? "end" : "middle"} fontSize={8} fill={T.light} fontFamily={T.mono}>{lbl}</text>
          ))}
        </svg>
      )}
    </Card>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// SECTION 4 — Per-record table (HARD RULE: one row per pick)
// ══════════════════════════════════════════════════════════════════════════════
type RecSortKey = "symbol" | "sector" | "entry" | "last" | "p10" | "p20" | "d30" | "d60" | "bars" | "maxplus" | "maxminus";

function SortTh({ label, k, sortKey, sortDir, onSort, style, title }: {
  label: string; k: RecSortKey; sortKey: RecSortKey; sortDir: "asc" | "desc";
  onSort: (k: RecSortKey) => void; style?: React.CSSProperties; title?: string;
}) {
  const active = sortKey === k;
  return (
    <th onClick={() => onSort(k)} title={title} style={{ ...th, cursor: "pointer", color: active ? T.text : T.muted, ...style }}>
      {label}{active ? (sortDir === "desc" ? " ↓" : " ↑") : ""}
    </th>
  );
}

const chipStyle = (color: string, bg: string, bordered = false): React.CSSProperties => ({
  display: "inline-block", padding: "2px 7px", borderRadius: 4, fontSize: 9, fontWeight: 700,
  color, background: bg, fontFamily: T.mono, whiteSpace: "nowrap",
  border: bordered ? `1px solid ${T.divider}` : "none",
});

function StateChip({ state, bars, K }: { state: RecState | null; bars: number | null; K: 30 | 60 }) {
  if (state == null) return <span style={{ color: T.light }}>—</span>;
  if (state === "TOUCHED") return <span style={chipStyle(T.greenPos, T.greenLight)}>TOUCHED</span>;
  if (state === "NO_TOUCH") return <span style={chipStyle(T.amber, T.amberLight)}>NO TOUCH</span>;
  return <span style={chipStyle(T.muted, "var(--bg)", true)}>OPEN {bars != null ? `${bars}/${K}` : `—/${K}`}</span>;
}

function RecordsTable({ records, asOf }: { records: CalibRecord[]; asOf: string }) {
  const [stateFilter, setStateFilter] = useState<"all" | "OPEN" | "TOUCHED" | "NO_TOUCH">("all");
  const [d8Only, setD8Only] = useState(false);
  const [sortKey, setSortKey] = useState<RecSortKey>("symbol");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [livePrices, setLivePrices] = useState<Record<string, number>>({});
  const [liveAsOf, setLiveAsOf] = useState<string>("");

  const barsOf = (r: CalibRecord): number | null => {
    if (r.bars_elapsed_30d == null && r.bars_elapsed_60d == null) return null;
    return Math.max(r.bars_elapsed_30d ?? 0, r.bars_elapsed_60d ?? 0);
  };

  const filtered = useMemo(() => records.filter(r =>
    (stateFilter === "all" || r.state_30d === stateFilter || r.state_60d === stateFilter) &&
    (!d8Only || (r.decile_30d ?? 0) >= 8 || (r.decile_60d ?? 0) >= 8)
  ), [records, stateFilter, d8Only]);

  const sorted = useMemo(() => {
    const val = (r: CalibRecord): number | string =>
      sortKey === "symbol" ? r.symbol
      : sortKey === "sector" ? (r.sector ?? "")
      : sortKey === "entry" ? r.entry_price
      : sortKey === "last" ? (livePrices[r.symbol] ?? -1)
      : sortKey === "p10" ? (r.p10 ?? -1)
      : sortKey === "p20" ? (r.p20 ?? -1)
      : sortKey === "d30" ? (r.decile_30d ?? -1)
      : sortKey === "d60" ? (r.decile_60d ?? -1)
      : sortKey === "bars" ? (barsOf(r) ?? -1)
      : sortKey === "maxplus" ? r.max_high_pct
      : r.max_dd_pct;
    const arr = [...filtered];
    arr.sort((a, b) => {
      const va = val(a), vb = val(b);
      if (typeof va === "string" || typeof vb === "string") {
        const c = String(va).localeCompare(String(vb));
        return sortDir === "asc" ? c : -c;
      }
      return sortDir === "asc" ? va - vb : vb - va;
    });
    return arr;
  }, [filtered, sortKey, sortDir, livePrices]);

  const onSort = (k: RecSortKey) => {
    if (k === sortKey) setSortDir(d => d === "asc" ? "desc" : "asc");
    else { setSortKey(k); setSortDir(k === "symbol" || k === "sector" ? "asc" : "desc"); }
  };

  // Live underlying prices — poll FMP quotes every 60s for the picks in view, cache-busted
  // (&t=) so the route's revalidate window doesn't stale them.
  const allSymbols = useMemo(() => Array.from(new Set(records.map(r => r.symbol))), [records]);
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

  return (
    <Card style={{ marginBottom: 20 }}>
      <SH title={`Per-record detail (${sorted.length} picks)`} icon={<Search size={12} />}
          sub={`One row per pick · clocks in trading bars, entry bar excluded · trailing 120 days · as of ${asOf}`} />

      <div style={{ display: "flex", gap: 14, padding: "10px 14px", borderBottom: `1px solid ${T.divider}`, alignItems: "center", flexWrap: "wrap", fontFamily: T.mono, fontSize: 11 }}>
        <FilterPills label="STATE" value={stateFilter} setValue={(v) => setStateFilter(v as typeof stateFilter)}
          options={[["all", "All"], ["OPEN", "Open"], ["TOUCHED", "Touched"], ["NO_TOUCH", "No touch"]]} />
        <button onClick={() => setD8Only(v => !v)}
          style={{
            padding: "3px 9px", fontSize: 10, fontFamily: T.mono, fontWeight: 600,
            border: "none", borderRadius: 4, cursor: "pointer",
            background: d8Only ? T.greenLight : "transparent",
            color: d8Only ? T.green : T.muted,
          }}>Decile ≥ 8</button>
        {liveAsOf && <span style={{ marginLeft: "auto", color: T.greenPos, fontSize: 10, fontWeight: 600 }}>● live · underlying as of {liveAsOf}</span>}
      </div>

      {sorted.length === 0 ? (
        <div style={{ padding: 30, textAlign: "center", color: T.light, fontSize: 11, fontFamily: T.mono }}>
          No records match the current filters.
        </div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontFamily: T.mono, fontSize: 11 }}>
            <thead>
              <tr>
                <SortTh label="Symbol" k="symbol" sortKey={sortKey} sortDir={sortDir} onSort={onSort} style={{ textAlign: "left" }} />
                <SortTh label="Sector" k="sector" sortKey={sortKey} sortDir={sortDir} onSort={onSort} style={{ textAlign: "left" }} />
                <SortTh label="Entry $" k="entry" sortKey={sortKey} sortDir={sortDir} onSort={onSort} style={{ textAlign: "right" }} />
                <SortTh label="Last $" k="last" sortKey={sortKey} sortDir={sortDir} onSort={onSort} style={{ textAlign: "right" }} />
                <SortTh label="p10" k="p10" sortKey={sortKey} sortDir={sortDir} onSort={onSort} title="Model P(+10% within 30 trading bars)" style={{ textAlign: "right" }} />
                <SortTh label="p20" k="p20" sortKey={sortKey} sortDir={sortDir} onSort={onSort} title="Model P(+20% within 60 trading bars)" style={{ textAlign: "right" }} />
                <SortTh label="D30" k="d30" sortKey={sortKey} sortDir={sortDir} onSort={onSort} title="Decile under the 30d/+10% regime (v4 OOS thresholds)" style={{ textAlign: "right" }} />
                <SortTh label="D60" k="d60" sortKey={sortKey} sortDir={sortDir} onSort={onSort} title="Decile under the 60d/+20% regime (v4 OOS thresholds)" style={{ textAlign: "right" }} />
                <SortTh label="Bars" k="bars" sortKey={sortKey} sortDir={sortDir} onSort={onSort} title="Trading bars elapsed since entry (entry bar excluded)" style={{ textAlign: "right" }} />
                <SortTh label="Max+" k="maxplus" sortKey={sortKey} sortDir={sortDir} onSort={onSort} style={{ textAlign: "right" }} />
                <SortTh label="Max−" k="maxminus" sortKey={sortKey} sortDir={sortDir} onSort={onSort} style={{ textAlign: "right" }} />
                <th style={{ ...th, textAlign: "right" }}>State 30d</th>
                <th style={{ ...th, textAlign: "right" }}>State 60d</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map(r => (
                <tr key={`${r.symbol}-${r.entry_date}`}
                    onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "var(--bg-hover)"; }}
                    onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = ""; }}>
                  <td style={{ ...td, textAlign: "left", fontWeight: 700, color: T.text }}>
                    {r.symbol}
                    <div style={{ fontSize: 9, fontWeight: 400, color: T.light }} title="Scan date this record was staged">entered {r.entry_date}</div>
                  </td>
                  <td style={{ ...td, textAlign: "left", color: T.light, fontSize: 10 }}>{r.sector ?? "—"}</td>
                  <td style={{ ...td, textAlign: "right", color: T.text }}>${r.entry_price.toFixed(2)}</td>
                  <td style={{ ...td, textAlign: "right", color: livePrices[r.symbol] != null ? T.text : T.light }}>
                    {livePrices[r.symbol] != null ? `$${livePrices[r.symbol].toFixed(2)}` : "—"}
                  </td>
                  <td style={{ ...td, textAlign: "right", color: T.muted }}>{r.p10 != null ? `${(r.p10 * 100).toFixed(0)}%` : "—"}</td>
                  <td style={{ ...td, textAlign: "right", color: T.muted }}>{r.p20 != null ? `${(r.p20 * 100).toFixed(0)}%` : "—"}</td>
                  <td style={{ ...td, textAlign: "right", color: (r.decile_30d ?? 0) >= 8 ? T.text : T.muted, fontWeight: (r.decile_30d ?? 0) >= 8 ? 700 : 400 }}>{r.decile_30d ?? "—"}</td>
                  <td style={{ ...td, textAlign: "right", color: (r.decile_60d ?? 0) >= 8 ? T.text : T.muted, fontWeight: (r.decile_60d ?? 0) >= 8 ? 700 : 400 }}>{r.decile_60d ?? "—"}</td>
                  <td style={{ ...td, textAlign: "right", color: T.muted }}>{barsOf(r) != null ? `${barsOf(r)} bars` : "—"}</td>
                  <td style={{ ...td, textAlign: "right", color: T.greenPos }}>+{r.max_high_pct.toFixed(1)}%</td>
                  <td style={{ ...td, textAlign: "right", color: T.red }}>{r.max_dd_pct.toFixed(1)}%</td>
                  <td style={{ ...td, textAlign: "right" }}><StateChip state={r.state_30d} bars={r.bars_elapsed_30d} K={30} /></td>
                  <td style={{ ...td, textAlign: "right" }}><StateChip state={r.state_60d} bars={r.bars_elapsed_60d} K={60} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// SECTION 5 — FROZEN V1 SIMULATION (collapsed; still fed by method-tracks)
// ══════════════════════════════════════════════════════════════════════════════
function FrozenSim() {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<SimTracks | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!open || data || err) return;
    fetch(METHOD_TRACKS)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((d: SimTracks) => { setData(d); setLoading(false); })
      .catch(e => { setErr(e.message || "Failed to load"); setLoading(false); });
  }, [open, data, err]);

  const { rows, cycleNotes } = useMemo(() => {
    const out: MethodRow[] = [];
    const notes: string[] = [];
    if (!data?.regimes) return { rows: out, cycleNotes: notes };
    for (const rname of ["30d_p10", "60d"]) {
      const r = data.regimes[rname];
      if (!r) continue;
      // Frozen tracker: when the current cycle is null/empty (n_picks 0), fall
      // back to the newest archived cycle so the section still shows history.
      const summary = r.current_cycle?.n_picks ? r.current_cycle : (r.archived_cycles?.[0] ?? null);
      if (!summary) continue;
      if (summary !== r.current_cycle) {
        notes.push(`${r.barrier_target_pct}%/${r.hit_window_days}d: archived cycle ${summary.cycle_id}`);
      }
      for (const m of ["stock", "long_call"] as const) {
        const stats = summary.by_method[m];
        if (!stats) continue;
        out.push({
          key: `${rname}-${m}`,
          method: m,
          label: `${m === "stock" ? "Stock" : "Long Call"} × ${r.barrier_target_pct}% / ${r.hit_window_days}d`,
          stats,
        });
      }
    }
    return { rows: out, cycleNotes: notes };
  }, [data]);

  return (
    <Card style={{ marginBottom: 20 }}>
      <div onClick={() => setOpen(o => !o)}
        style={{
          display: "flex", alignItems: "center", gap: 6, cursor: "pointer",
          fontSize: 11, fontWeight: 600, letterSpacing: "0.08em", color: T.amber,
          fontFamily: T.mono, textTransform: "uppercase",
          ...(open ? { marginBottom: 12, paddingBottom: 8, borderBottom: `2px solid ${T.amberLight}` } : {}),
        }}>
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <FlaskConical size={12} />
        FROZEN V1 SIMULATION — METHODOLOGY SUPERSEDED
        <span style={{ marginLeft: "auto", fontSize: 9, color: T.light, fontWeight: 400, textTransform: "none", letterSpacing: 0 }}>
          {open ? "collapse" : "expand"}
        </span>
      </div>

      {open && (
        <>
          <p style={{ fontSize: 10, color: T.muted, fontFamily: T.mono, margin: "0 0 14px", lineHeight: 1.6 }}>
            P&amp;L simulation of the legacy four exit/payoff methods on the same picks — calendar-day clock and
            in-sample decile thresholds; superseded by the calibration tracker above. Open rows are marked-to-market.
          </p>

          {loading && <div style={{ padding: 24, textAlign: "center", color: T.light, fontSize: 11, fontFamily: T.mono }}>Loading frozen sim…</div>}
          {err && <div style={{ padding: 24, textAlign: "center", color: T.light, fontSize: 11, fontFamily: T.mono }}>Failed to load: {err}</div>}

          {!loading && !err && (
            <>
              <SH title="Method comparison" icon={<TrendingUp size={12} />} accent={T.amber}
                  sub="Same picks, four exit/payoff structures tracked in parallel. Read tail_p5 + worst_DD before celebrating any win rate." />
              {cycleNotes.length > 0 && (
                <div style={{ fontSize: 9, color: T.light, fontFamily: T.mono, marginBottom: 10 }}>
                  Current cycle empty — showing {cycleNotes.join(" · ")}
                </div>
              )}
              {rows.length === 0 ? (
                <div style={{ padding: 24, textAlign: "center", color: T.light, fontSize: 11, fontFamily: T.mono }}>
                  No simulation data in the current cycle.
                </div>
              ) : (
                <div style={{ overflowX: "auto", marginBottom: 18 }}>
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

              {rows.length > 0 && (
                <>
                  <SH title="Exit breakdown" icon={<Clock size={12} />} accent={T.amber}
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
                </>
              )}
            </>
          )}
        </>
      )}
    </Card>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// Calibration view (sections 1-4)
// ══════════════════════════════════════════════════════════════════════════════
function CalibrationView({ data }: { data: CalibrationV2 }) {
  const h30 = data.horizons["30d"];
  const h60 = data.horizons["60d"];
  return (
    <>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 10, marginBottom: 16 }}>
        <HeadlineCard label="30D · +10% BARRIER — OBSERVED / EXPECTED TOUCHES" h={h30} model={data.model} />
        <HeadlineCard label="60D · +20% BARRIER — OBSERVED / EXPECTED TOUCHES" h={h60} model={data.model} />
      </div>

      <Card style={{ marginBottom: 20 }}>
        <SH title="Decile calibration" icon={<BarChart3 size={12} />}
            sub="Bars = observed touch rate over MATURED rows only · purple line = predicted mean p · hatched = no matured rows yet" />
        <div style={{ padding: "4px 14px 14px" }}>
          <DecileBars label="30d · +10%" deciles={h30.deciles} />
          <DecileBars label="60d · +20%" deciles={h60.deciles} />
        </div>
      </Card>

      <TouchCurve horizons={data.horizons} />

      <RecordsTable records={data.records} asOf={data.as_of} />
    </>
  );
}

// ══════════════════════════════════════════════════════════════════════════════
// Shell
// ══════════════════════════════════════════════════════════════════════════════
export default function Performance() {
  const [data, setData] = useState<CalibrationV2 | null>(null);
  const [loading, setLoading] = useState(true);
  const [notLive, setNotLive] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetch(CALIBRATION_V2)
      .then(async r => {
        if (r.status === 404) { setNotLive(true); return; }
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const text = await r.text();
        let d: unknown;
        try { d = JSON.parse(text); } catch { setNotLive(true); return; } // non-JSON body = endpoint not live
        const v = d as Partial<CalibrationV2> | null;
        // A versioned-but-partial summary (missing records/deciles) must show
        // the honest not-live card, not white-screen the page.
        if (!v || v.schema_version !== "calibration-v2" || !v.horizons?.["30d"] || !v.horizons?.["60d"]
            || !Array.isArray(v.records)
            || !Array.isArray(v.horizons?.["30d"]?.deciles)
            || !Array.isArray(v.horizons?.["60d"]?.deciles)) {
          setNotLive(true);
          return;
        }
        setData(v as CalibrationV2);
      })
      .catch(e => setErr(e?.message || "Failed to load"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div style={{ padding: "16px 20px", maxWidth: 1400, margin: "0 auto" }}>
      <div style={{ marginBottom: 16, paddingBottom: 10, borderBottom: `1px solid ${T.border}` }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
          <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: "0.1em", color: T.text, fontFamily: T.mono }}>SYSTEM PERFORMANCE</span>
          <span style={{ fontSize: 12, color: T.muted, fontFamily: T.mono }}>/ model calibration — does predicted P(touch) match observed touch frequency?</span>
        </div>
        <p style={{ fontSize: 10, color: T.muted, fontFamily: T.mono, marginTop: 4 }}>
          Forward calibration tracking: every staged pick is measured against the +10%/30-bar and +20%/60-bar touch
          barriers. Censoring-aware expected-vs-observed touch counts validate the model&apos;s predicted probabilities
          in real time. All clocks in trading bars, entry bar excluded. No stop-losses.
        </p>
      </div>

      {loading && <Empty icon={<Target size={36} color={T.divider} />} title="Loading calibration tracker…" />}

      {!loading && err && (
        <Empty icon={<Target size={36} color={T.divider} />} title="Failed to load calibration tracker" sub={err} />
      )}

      {!loading && !err && notLive && (
        <Empty icon={<Target size={36} color={T.divider} />}
               title="Calibration tracker v2 not live yet — first nightly run pending"
               sub="The v2 tracker stages picks at scan time and activates them on the next nightly run; this page lights up once the first summary is published." />
      )}

      {!loading && !err && data && <CalibrationView data={data} />}

      {!loading && <FrozenSim />}
    </div>
  );
}
