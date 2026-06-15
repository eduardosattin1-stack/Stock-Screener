"use client";
import { useState, useEffect, useMemo, Fragment, useCallback } from "react";
import {
  Radio, Activity, ChevronRight, ChevronDown, ExternalLink, RefreshCw, TrendingUp,
  Layers, Cpu,
} from "lucide-react";
import { Tip } from "../components/Tip";

// SOCIAL ARB — consumer-behavior signal board.
// Reads the live Social Arb signal engine (FastAPI on Cloud Run) through the same-origin proxy
// at /api/social/<path>. Mirrors the Catalyst Watch / ML-Picks board idiom: one dense table,
// click a row to expand the drill-down (demand/awareness, mention history, intent mix, evidence
// posts, live ticker). No chart lib — hand-rolled <svg>, matching the rest of the app.
//
// Data-contract notes (see backend/routes_signals.py):
//   - signal_score is UNBOUNDED (gap×materiality×corroboration-weighted); rank-relative, not /100.
//   - direction is only "long" | "watch" today (no short side wired yet); novelty is always false.
//   - evidence_post_ids / narrative are not written by the generator — narrative is null on
//     generated rows (present only on hand-seeded ones); evidence is reconstructed via entity_id.
const SOCIAL = "/api/social";

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

interface Signal {
  id: number;
  created_at: string;
  entity_id: number;
  entity_name: string;
  tickers: string | null;
  direction: "long" | "watch" | string;
  signal_score: number;
  gap_score: number;
  demand_index: number;
  awareness_index: number;
  velocity_z: number;
  corroboration: number | null;
  intent_purchase_share: number | null;
  materiality: number;
  novelty: boolean;
  narrative: string | null;
  status: string;
  signal_track?: string;
}

interface Stats {
  total_posts?: number;
  source_counts?: Record<string, number>;
  avg_sentiment?: number;
  positive_count?: number;
  negative_count?: number;
}
interface Backtest {
  stats?: {
    total_signals?: number;
    avg_return_5d?: number;
    avg_return_21d?: number;
    avg_return_63d?: number;
    winners_21d?: number;
    measured_21d?: number;
    thesis_hit_rate?: number;
    labeled?: number;
    validated?: number;
  };
  top_signals?: { entity_name: string; tickers?: string | null; return_21d?: number; created_at?: string }[];
  validated_cases?: {
    entity_name: string; tickers?: string | null; track?: string; signal_date?: string;
    awareness_closed?: boolean; rev_accel?: boolean; rev_growth_post?: number;
    rerate_excess_21d?: number; rerate_excess_126d?: number; validated?: boolean;
  }[];
  mode?: string;
}
interface HistPoint { hour: string; mentions: number; sentiment: number; intent_purchase: number; authors: number; }
interface IntentRow { intent: string; count: number; avg_score: number; }
interface Mention {
  matched_text?: string; method?: string; intent?: string; intent_score?: number;
  content: string; source: string; timestamp: string; url?: string;
}
interface Quote { symbol: string; name?: string; price: number | null; day: number | null; ytd: number | null; year: number | null; }
interface Detail { intent: IntentRow[]; mentions: Mention[]; quote: Quote | null; }

// Theme baskets (GET /api/social/themes) — seeded consumer themes mapped to revenue-weighted
// ticker baskets. The gap is the alpha: a basket can light up before any single signal fires.
interface ThemeConstituent {
  ticker: string; exchange?: string | null; revenue_share_est: number;
  mcap_usd?: number | null; allocated_score: number; rationale?: string | null;
}
interface Theme {
  theme_id: number; name: string; demand_index: number; awareness_index: number;
  gap_score: number; mention_count_7d: number; tradeable: boolean;
  constituents: ThemeConstituent[];
}
// Resolver / entity-graph health (GET /api/social/resolver/health) — surfaces the keystone:
// unknown names → MiMo proposes → FMP confirms → tradeable ticker. mimo_reachable exposes the
// config blocker (null = MIMO_BASE_URL unset, false = unreachable, true = online).
interface ResolverHealth {
  queue: { pending: number; resolving: number; done: number; failed: number };
  cache: { auto: number; approved: number; review: number; rejected: number; total: number };
  entities_total: number; entity_tickers_total: number; revenue_share_populated: number;
  last_resolved_at: string | null; mimo_reachable: boolean | null;
  top_pending: { norm_query: string; mention_count: number }[];
  review_queue_count: number;
}

const STATUSES = ["new", "investigating", "passed", "positioned", "closed"] as const;
type Status = (typeof STATUSES)[number];

// ── helpers ──
const n = (x: any): number | null => { const v = Number(x); return Number.isFinite(v) ? v : null; };
const f1 = (x: any) => { const v = n(x); return v == null ? "—" : v.toFixed(1); };
const f2 = (x: any) => { const v = n(x); return v == null ? "—" : v.toFixed(2); };
const pct = (x: any) => { const v = n(x); return v == null ? "—" : `${(v * 100).toFixed(0)}%`; };
const fmtRet = (x: any) => { const v = n(x); return v == null ? "—" : `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}%`; };
const retColor = (x: any) => { const v = n(x); return v == null ? T.muted : v > 0 ? T.green : v < 0 ? T.red : T.muted; };
const fmtMcap = (x: any) => { const v = n(x); if (v == null || v <= 0) return "—"; if (v >= 1e12) return `$${(v / 1e12).toFixed(1)}T`; if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`; if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`; return `$${v.toFixed(0)}`; };

function timeAgo(iso: string): string {
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return "—";
  const mins = Math.max(0, Math.round((Date.now() - t) / 60000));
  if (mins < 60) return `${mins}m`;
  const hrs = Math.round(mins / 60);
  if (hrs < 48) return `${hrs}h`;
  return `${Math.round(hrs / 24)}d`;
}

function tickerList(s: string | null): string[] {
  if (!s) return [];
  return s.split(",").map((x) => x.trim()).filter(Boolean);
}
const isPrivate = (t: string) => !t || t.toUpperCase() === "PRIVATE";

function gapGrade(gap: number | null): { label: string; color: string; bg: string } {
  const g = gap ?? 0;
  if (g >= 2) return { label: "WIDE", color: T.green, bg: "rgba(20,184,122,0.18)" };
  if (g >= 1) return { label: "OPEN", color: T.amber, bg: "rgba(245,185,66,0.16)" };
  if (g <= 0) return { label: "CLOSED", color: T.red, bg: "rgba(239,90,90,0.14)" };
  return { label: "TIGHT", color: T.muted, bg: "rgba(255,255,255,0.05)" };
}

// ── module-scope presentational components (must not be declared during render) ──
function StatCard({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: string }) {
  return (
    <div style={{ flex: "1 1 0", minWidth: 150, padding: "14px 16px", background: T.surface, border: `1px solid ${T.border}`, borderRadius: 8 }}>
      <div style={{ fontSize: 9.5, fontFamily: T.mono, fontWeight: 600, letterSpacing: "0.08em", color: T.light, textTransform: "uppercase" }}>{label}</div>
      <div style={{ fontSize: 24, fontFamily: T.mono, fontWeight: 800, color: accent ?? T.text, marginTop: 6, lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: 10, fontFamily: T.mono, color: T.muted, marginTop: 5 }}>{sub}</div>}
    </div>
  );
}

function Toggle({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button onClick={onClick} style={{
      padding: "5px 11px", fontSize: 11, fontFamily: T.mono, fontWeight: 600, cursor: "pointer",
      border: `1px solid ${active ? T.green : T.border}`, borderRadius: 5,
      background: active ? "var(--green-light)" : "transparent", color: active ? T.green : T.muted,
      transition: "all 0.15s", textTransform: "capitalize",
    }}>{children}</button>
  );
}

function Chip({ text, color, bg, border }: { text: string; color: string; bg: string; border?: string }) {
  return (
    <span style={{ fontSize: 8.5, fontFamily: T.mono, fontWeight: 800, letterSpacing: "0.04em", padding: "2px 6px", borderRadius: 3, color, background: bg, border: `1px solid ${border ?? "transparent"}` }}>{text}</span>
  );
}

function MetricBlock({ label, value, accent, tip }: { label: string; value: string; accent?: string; tip?: string }) {
  const head = <span style={{ fontSize: 8.5, fontFamily: T.mono, color: T.light, letterSpacing: "0.05em", textTransform: "uppercase" }}>{label}</span>;
  return (
    <div style={{ padding: "7px 10px", borderRadius: 6, border: `1px solid ${T.border}`, background: T.bg, minWidth: 78 }}>
      <div>{tip ? <Tip k={tip}>{head}</Tip> : head}</div>
      <div style={{ fontSize: 15, fontFamily: T.mono, fontWeight: 800, color: accent ?? T.text, marginTop: 2 }}>{value}</div>
    </div>
  );
}

// Hand-rolled sparkline (matches the Track-Record NAV <svg> idiom — no chart lib).
function Spark({ values, color = T.green, w = 320, h = 56 }: { values: number[]; color?: string; w?: number; h?: number }) {
  const pts = values.filter((v) => Number.isFinite(v));
  if (pts.length < 2) return <div style={{ fontSize: 10, fontFamily: T.mono, color: T.light, padding: "16px 0" }}>not enough history</div>;
  const PX = 4, PY = 6;
  const max = Math.max(...pts), min = Math.min(...pts);
  const span = max - min || 1;
  const xOf = (i: number) => PX + (i / (pts.length - 1)) * (w - 2 * PX);
  const yOf = (v: number) => PY + (1 - (v - min) / span) * (h - 2 * PY);
  const poly = pts.map((v, i) => `${xOf(i).toFixed(1)},${yOf(v).toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} style={{ width: "100%", height: h, display: "block" }}>
      <polyline points={poly} fill="none" stroke={color} strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={xOf(pts.length - 1)} cy={yOf(pts[pts.length - 1])} r="2.6" fill={color} />
    </svg>
  );
}

function IntentBars({ rows }: { rows: IntentRow[] }) {
  if (!rows.length) return <div style={{ fontSize: 10, fontFamily: T.mono, color: T.light }}>no intent data</div>;
  const max = Math.max(...rows.map((r) => r.count), 1);
  const good = new Set(["purchased", "intends_to_purchase", "switching_to", "recommends", "sold_out_unavailable"]);
  const bad = new Set(["switching_from", "canceled_churned", "complains"]);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      {rows.slice(0, 8).map((r) => {
        const col = good.has(r.intent) ? T.green : bad.has(r.intent) ? T.red : T.muted;
        return (
          <div key={r.intent} style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 9.5, fontFamily: T.mono, color: T.muted, width: 120, textAlign: "right", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.intent.replace(/_/g, " ")}</span>
            <div style={{ flex: 1, height: 8, background: "rgba(255,255,255,0.04)", borderRadius: 2, overflow: "hidden" }}>
              <div style={{ width: `${(r.count / max) * 100}%`, height: "100%", background: col, opacity: 0.7 }} />
            </div>
            <span style={{ fontSize: 9.5, fontFamily: T.mono, color: T.light, width: 26, textAlign: "right" }}>{r.count}</span>
          </div>
        );
      })}
    </div>
  );
}

function TickerCard({ primary, quote }: { primary: string; quote: Quote | null }) {
  if (isPrivate(primary)) {
    return (
      <div style={{ padding: "12px 14px", border: `1px solid ${T.border}`, borderRadius: 8, background: T.bg }}>
        <div style={{ fontSize: 11, fontFamily: T.mono, fontWeight: 800, color: T.text }}>PRIVATE</div>
        <div style={{ fontSize: 10, fontFamily: T.mono, color: T.light, marginTop: 4, lineHeight: 1.5 }}>No public listing mapped — tracked as a behavior signal only.</div>
      </div>
    );
  }
  const dayCol = (quote?.day ?? 0) >= 0 ? T.green : T.red;
  return (
    <div style={{ padding: "12px 14px", border: `1px solid ${T.border}`, borderRadius: 8, background: T.bg, minWidth: 180 }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 10 }}>
        <span style={{ fontSize: 13, fontFamily: T.mono, fontWeight: 800, color: T.text }}>{primary}</span>
        <span style={{ fontSize: 13, fontFamily: T.mono, fontWeight: 700, color: T.text }}>{quote?.price != null ? `$${quote.price.toFixed(2)}` : "—"}</span>
      </div>
      {quote?.name && <div style={{ fontSize: 9.5, fontFamily: T.mono, color: T.light, marginTop: 2, maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{quote.name}</div>}
      <div style={{ display: "flex", gap: 12, marginTop: 8, fontSize: 10, fontFamily: T.mono }}>
        <span style={{ color: dayCol }}>{quote?.day != null ? `${quote.day >= 0 ? "+" : ""}${quote.day.toFixed(2)}% 1D` : "—"}</span>
        <span style={{ color: T.muted }}>{quote?.year != null ? `${quote.year >= 0 ? "+" : ""}${quote.year.toFixed(0)}% 1Y` : ""}</span>
      </div>
    </div>
  );
}

export default function SocialArb() {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [backtest, setBacktest] = useState<Backtest | null>(null);
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<Status>("new");
  const [expanded, setExpanded] = useState<number | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const [details, setDetails] = useState<Record<number, Detail | "loading">>({});
  const [histWindow, setHistWindow] = useState<number>(168);            // 7d default; 2160=90d, 17520=2y
  const [histCache, setHistCache] = useState<Record<string, HistPoint[] | "loading">>({});
  const [corrOnly, setCorrOnly] = useState(false);
  const [trackFilter, setTrackFilter] = useState<string>("all");
  const [themes, setThemes] = useState<Theme[] | null>(null);
  const [resolver, setResolver] = useState<ResolverHealth | null>(null);

  // signals re-fetch when the status filter changes
  useEffect(() => {
    let live = true;
    setLoading(true);
    fetch(`${SOCIAL}/signals?status=${status}&limit=100&t=${Date.now()}`)
      .then((r) => (r.ok ? r.json() : []))
      .then((d) => { if (live) { setSignals(Array.isArray(d) ? d : []); setLoading(false); } })
      .catch(() => { if (live) { setSignals([]); setLoading(false); } });
    return () => { live = false; };
  }, [status]);

  // stats + backtest + theme baskets + resolver health, once.
  // themes/resolver are hidden until their endpoints are live (404 → stays null), so the page is
  // unchanged until the backend serves them, then the sections appear.
  useEffect(() => {
    fetch(`${SOCIAL}/stats`).then((r) => (r.ok ? r.json() : null)).then(setStats).catch(() => {});
    fetch(`${SOCIAL}/backtest`).then((r) => (r.ok ? r.json() : null)).then(setBacktest).catch(() => {});
    fetch(`${SOCIAL}/themes`).then((r) => (r.ok ? r.json() : null))
      .then((d) => setThemes(Array.isArray(d?.themes) ? d.themes : null)).catch(() => {});
    fetch(`${SOCIAL}/resolver/health`).then((r) => (r.ok ? r.json() : null))
      .then((d) => setResolver(d && d.queue ? d : null)).catch(() => {});
  }, []);

  const loadHistory = useCallback((entityId: number, hours: number) => {
    const key = `${entityId}:${hours}`;
    if (histCache[key]) return;
    setHistCache((h) => ({ ...h, [key]: "loading" }));
    fetch(`${SOCIAL}/entities/${entityId}/history?hours=${hours}`)
      .then((r) => (r.ok ? r.json() : []))
      .then((rows) => setHistCache((h) => ({ ...h, [key]: Array.isArray(rows) ? rows : [] })))
      .catch(() => setHistCache((h) => ({ ...h, [key]: [] })));
  }, [histCache]);

  const loadDetail = useCallback((sig: Signal) => {
    if (details[sig.id]) return;
    setDetails((d) => ({ ...d, [sig.id]: "loading" }));
    const id = sig.entity_id;
    const primary = tickerList(sig.tickers)[0] ?? "";
    const quoteP = isPrivate(primary)
      ? Promise.resolve(null)
      : fetch(`/api/quotes?symbols=${encodeURIComponent(primary)}`).then((r) => (r.ok ? r.json() : null)).then((d) => d?.quotes?.[0] ?? null).catch(() => null);
    Promise.all([
      fetch(`${SOCIAL}/entities/${id}/intent`).then((r) => (r.ok ? r.json() : [])).catch(() => []),
      fetch(`${SOCIAL}/entities/${id}/mentions?limit=8`).then((r) => (r.ok ? r.json() : [])).catch(() => []),
      quoteP,
    ]).then(([intent, mentions, quote]) => {
      setDetails((d) => ({ ...d, [sig.id]: { intent, mentions, quote } }));
    }).catch(() => {
      setDetails((d) => ({ ...d, [sig.id]: { intent: [], mentions: [], quote: null } }));
    });
  }, [details]);

  const toggleRow = (sig: Signal) => {
    const open = expanded === sig.id;
    setExpanded(open ? null : sig.id);
    if (!open) { loadDetail(sig); loadHistory(sig.entity_id, histWindow); }
  };

  const changeHistWindow = (hours: number) => {
    setHistWindow(hours);
    const openSig = signals.find((s) => s.id === expanded);
    if (openSig) loadHistory(openSig.entity_id, hours);
  };

  const maxScore = useMemo(() => Math.max(1, ...signals.map((s) => n(s.signal_score) ?? 0)), [signals]);

  const bt = backtest?.stats;
  const winRate = bt && bt.measured_21d ? (bt.winners_21d ?? 0) / bt.measured_21d : null;
  const freshness = signals[0]?.created_at
    ? new Date(signals[0].created_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
    : "—";
  const sources = stats?.source_counts ? Object.keys(stats.source_counts).length : null;

  // Data-quality read from the post mix: today the corpus is ~all HackerNews and the awareness side
  // (finance news / StockTwits) is thin, so "demand" is mostly tech/dev buzz and gap ≈ demand.
  const srcCounts = stats?.source_counts ?? {};
  const totalSrc = Object.values(srcCounts).reduce((a, b) => a + b, 0) || 1;
  const hnShare = (srcCounts["HackerNews"] ?? 0) / totalSrc;
  const awarenessShare = Object.entries(srcCounts).filter(([k]) => k.startsWith("News:") || k.startsWith("Premium:")).reduce((a, [, v]) => a + v, 0) / totalSrc;
  const thinData = hnShare > 0.6 || awarenessShare < 0.05;
  const visibleSignals = signals.filter((s) =>
    (trackFilter === "all" || (s.signal_track || "mixed") === trackFilter) &&
    (!corrOnly || (n(s.corroboration) ?? 1) >= 2)
  );

  const hdr: React.CSSProperties = { padding: "9px 8px", fontSize: 9.5, fontFamily: T.mono, fontWeight: 700, letterSpacing: "0.05em", textAlign: "right", color: T.light, textTransform: "uppercase", whiteSpace: "nowrap" };

  return (
    <div style={{ minHeight: "100vh", background: T.bg, padding: "24px 24px 80px" }}>
      <div style={{ maxWidth: 1080, margin: "0 auto" }}>
        {/* Header */}
        <div style={{ display: "flex", alignItems: "flex-start", gap: 12, marginBottom: 12 }}>
          <Radio size={20} style={{ color: T.green, marginTop: 2 }} />
          <div>
            <h1 style={{ fontSize: 19, fontWeight: 800, fontFamily: T.mono, color: T.text, letterSpacing: "-0.02em" }}>
              SOCIAL ARB <span style={{ color: T.light, fontWeight: 500 }}>/ consumer-behavior signals</span>
            </h1>
            <p style={{ fontSize: 11, fontFamily: T.mono, color: T.muted, marginTop: 4, lineHeight: 1.5 }}>
              Ranked by the demand/awareness gap. One line per signal — click to expand mention history,
              intent mix, and evidence. Fresh as of <span style={{ color: T.text }}>{freshness}</span>.
            </p>
          </div>
        </div>

        {/* Strategy glass banner */}
        <div style={{
          display: "flex", alignItems: "center", gap: 10, padding: "10px 14px", marginBottom: 18,
          borderRadius: 8, backdropFilter: "blur(8px)",
          background: "linear-gradient(90deg, rgba(20,184,122,0.15) 0%, rgba(196,181,253,0.15) 100%)",
          border: "1px solid rgba(20,184,122,0.3)", boxShadow: "0 4px 20px rgba(0,0,0,0.15)",
        }}>
          <Activity size={14} style={{ color: T.green, flexShrink: 0 }} />
          <span style={{ fontSize: 10.5, fontFamily: T.mono, color: T.muted, lineHeight: 1.5 }}>
            Detects consumer-behavior change in public chatter <span style={{ color: T.text }}>before</span> the financial
            world catches on — <span style={{ color: T.text }}>the demand−awareness gap is the trade</span>. It closes when
            finance media and traders pile in.
          </span>
        </div>

        {/* Data-quality banner (auto-clears as the source mix broadens / awareness populates) */}
        {thinData && (
          <div style={{ display: "flex", alignItems: "flex-start", gap: 10, padding: "10px 14px", marginBottom: 18, borderRadius: 8, background: "var(--amber-light)", border: `1px solid ${T.border}` }}>
            <Activity size={14} style={{ color: T.amber, flexShrink: 0, marginTop: 1 }} />
            <span style={{ fontSize: 10.5, fontFamily: T.mono, color: T.muted, lineHeight: 1.5 }}>
              <span style={{ color: T.amber, fontWeight: 700 }}>Early data — read with care.</span> {(hnShare * 100).toFixed(0)}% of posts are HackerNews and the awareness side (finance news / StockTwits) is thin, so &quot;demand&quot; is mostly developer / early-adopter buzz and <span style={{ color: T.text }}>gap ≈ demand</span>. Treat single-platform (×1) rows as early-adopter signal, not confirmed consumer behavior. Source diversification is in progress; this note clears as the mix broadens.
            </span>
          </div>
        )}

        {/* KPIs */}
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 18 }}>
          <StatCard label="Open signals" value={String(signals.length)} sub={`status · ${status}`} accent={T.green} />
          <StatCard label="Posts ingested" value={stats?.total_posts != null ? String(stats.total_posts) : "—"} sub={sources != null ? `${sources} sources` : undefined} />
          <StatCard label="Avg sentiment" value={stats?.avg_sentiment != null ? stats.avg_sentiment.toFixed(2) : "—"} sub={stats?.positive_count != null ? `${stats.positive_count}+ / ${stats.negative_count ?? 0}−` : undefined} />
          <StatCard label="Backtest win (21d)" value={winRate != null ? pct(winRate) : "—"} sub={bt?.measured_21d ? `${bt.winners_21d}/${bt.measured_21d} measured` : "accruing"} />
        </div>

        {/* Status filter */}
        <div style={{ display: "flex", alignItems: "center", gap: 7, flexWrap: "wrap", marginBottom: 14 }}>
          <span style={{ fontSize: 9.5, fontFamily: T.mono, fontWeight: 700, letterSpacing: "0.06em", color: T.light, textTransform: "uppercase" }}>Status</span>
          {STATUSES.map((s) => (
            <Toggle key={s} active={status === s} onClick={() => { setStatus(s); setExpanded(null); }}>{s}</Toggle>
          ))}
          <span style={{ width: 1, height: 18, background: T.border, margin: "0 4px" }} />
          <Toggle active={corrOnly} onClick={() => { setCorrOnly((v) => !v); setExpanded(null); }}>corroborated ≥2</Toggle>
        </div>

        {/* Track filter (source-class lane: HN→dev-tools, Reddit/YouTube→consumer, StockTwits/News→investor) */}
        <div style={{ display: "flex", alignItems: "center", gap: 7, flexWrap: "wrap", marginBottom: 14 }}>
          <span style={{ fontSize: 9.5, fontFamily: T.mono, fontWeight: 700, letterSpacing: "0.06em", color: T.light, textTransform: "uppercase" }}>Track</span>
          {([["all", "All"], ["consumer", "Consumer"], ["investor", "Investor"], ["dev-tools", "Dev Tools"], ["mixed", "Mixed"]] as [string, string][]).map(([val, lbl]) => (
            <Toggle key={val} active={trackFilter === val} onClick={() => { setTrackFilter(val); setExpanded(null); }}>{lbl}</Toggle>
          ))}
        </div>

        {loading ? (
          <div style={{ textAlign: "center", padding: "80px 0", fontFamily: T.mono, fontSize: 12, color: T.light }}>
            <RefreshCw size={16} className="animate-spin" style={{ display: "inline", verticalAlign: "middle", marginRight: 8 }} />
            Loading signals…
          </div>
        ) : signals.length === 0 ? (
          <div style={{ textAlign: "center", padding: "80px 0", fontFamily: T.mono, fontSize: 12, color: T.light, lineHeight: 1.6 }}>
            No <span style={{ color: T.text }}>{status}</span> signals right now.<br />
            Signals accrue as the pipeline accumulates baseline history per entity.
          </div>
        ) : (
          <>
            {/* Board */}
            <div style={{ overflowX: "auto", border: `1px solid ${T.border}`, borderRadius: 8, background: T.surface }}>
              <table style={{ width: "100%", borderCollapse: "collapse", minWidth: 880, tableLayout: "fixed" }}>
                <thead>
                  <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                    <th style={{ ...hdr, textAlign: "center", width: 40 }}>#</th>
                    <th style={{ ...hdr, textAlign: "left", width: 300 }}>Entity / ticker</th>
                    <th style={{ ...hdr, textAlign: "center", width: 70 }}><Tip k="SA_DIRECTION">Dir</Tip></th>
                    <th style={{ ...hdr, width: 80 }}><Tip k="SA_DEMAND">Demand</Tip></th>
                    <th style={{ ...hdr, width: 86 }}><Tip k="SA_AWARENESS">Awareness</Tip></th>
                    <th style={{ ...hdr, width: 90 }}><Tip k="SA_GAP">Gap</Tip></th>
                    <th style={{ ...hdr, width: 60 }}><Tip k="SA_VELOCITY">Vel z</Tip></th>
                    <th style={{ ...hdr, textAlign: "center", width: 60 }}><Tip k="SA_CORROBORATION">Corr</Tip></th>
                    <th style={{ ...hdr, width: 72 }}><Tip k="SA_MATERIALITY">Mat.</Tip></th>
                    <th style={{ ...hdr, width: 150, color: T.text }}><Tip k="SA_SCORE">Score</Tip></th>
                    <th style={{ ...hdr, width: 48 }}>Age</th>
                    <th style={{ ...hdr, width: 30 }} />
                  </tr>
                </thead>
                <tbody>
                  {visibleSignals.map((s, i) => {
                    const isOpen = expanded === s.id;
                    const grade = gapGrade(n(s.gap_score));
                    const score = n(s.signal_score) ?? 0;
                    const dir = (s.direction || "watch").toLowerCase();
                    const tks = tickerList(s.tickers);
                    const cell: React.CSSProperties = { padding: "8px 8px", fontSize: 11.5, fontFamily: T.mono, textAlign: "right", fontWeight: 600 };
                    return (
                      <Fragment key={s.id}>
                        <tr
                          onClick={() => toggleRow(s)}
                          onMouseEnter={() => setHover(s.id)}
                          onMouseLeave={() => setHover(null)}
                          style={{ borderBottom: isOpen ? "none" : `1px solid ${T.border}`, cursor: "pointer", background: isOpen ? T.elevated : hover === s.id ? T.hover : "transparent", transition: "background 0.1s" }}
                        >
                          <td style={{ padding: "8px 8px", fontSize: 11, fontFamily: T.mono, textAlign: "center", color: i < 3 ? T.green : T.light, fontWeight: i < 3 ? 800 : 500 }}>{i + 1}</td>
                          <td style={{ padding: "8px 8px" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                              {isOpen ? <ChevronDown size={12} style={{ color: T.muted }} /> : <ChevronRight size={12} style={{ color: hover === s.id ? T.muted : T.light }} />}
                              <span style={{ fontSize: 12.5, fontFamily: T.mono, fontWeight: 700, color: T.text }}>{s.entity_name}</span>
                            </div>
                            <div style={{ display: "flex", gap: 4, marginTop: 3, marginLeft: 18, flexWrap: "wrap" }}>
                              {tks.length === 0 && <span style={{ fontSize: 9, fontFamily: T.mono, color: T.light }}>no ticker</span>}
                              {tks.map((t) => (
                                <Chip key={t} text={isPrivate(t) ? "PRIVATE" : t}
                                  color={isPrivate(t) ? T.light : T.purple}
                                  bg={isPrivate(t) ? "rgba(255,255,255,0.05)" : "rgba(196,181,253,0.14)"}
                                  border={isPrivate(t) ? undefined : "rgba(196,181,253,0.25)"} />
                              ))}
                              {s.signal_track && s.signal_track !== "mixed" && (
                                <Chip text={s.signal_track}
                                  color={s.signal_track === "consumer" ? T.green : s.signal_track === "dev-tools" ? T.amber : T.purple}
                                  bg={s.signal_track === "consumer" ? "rgba(20,184,122,0.14)" : s.signal_track === "dev-tools" ? "rgba(245,185,66,0.16)" : "rgba(196,181,253,0.14)"} />
                              )}
                            </div>
                          </td>
                          <td style={{ padding: "8px 8px", textAlign: "center" }}>
                            <Chip text={dir === "long" ? "LONG" : "WATCH"}
                              color={dir === "long" ? T.green : T.amber}
                              bg={dir === "long" ? "rgba(20,184,122,0.18)" : "rgba(245,185,66,0.16)"} />
                          </td>
                          <td style={{ ...cell, color: T.text }}>{f2(s.demand_index)}</td>
                          <td style={{ ...cell, color: T.muted }}>{f2(s.awareness_index)}</td>
                          <td style={{ padding: "8px 8px", textAlign: "right" }}>
                            <span style={{ fontSize: 11.5, fontFamily: T.mono, fontWeight: 800, color: grade.color }}>{f2(s.gap_score)} </span>
                            <Chip text={grade.label} color={grade.color} bg={grade.bg} />
                          </td>
                          <td style={{ ...cell, color: (n(s.velocity_z) ?? 0) >= 2.5 ? T.green : T.muted }}>{f1(s.velocity_z)}</td>
                          <td style={{ padding: "8px 8px", textAlign: "center" }}>
                            <span style={{ fontSize: 10, fontFamily: T.mono, fontWeight: 700, color: (n(s.corroboration) ?? 1) >= 2 ? T.green : T.muted, border: `1px solid ${T.border}`, borderRadius: 4, padding: "2px 6px" }}>×{s.corroboration ?? 1}</span>
                          </td>
                          <td style={{ ...cell, color: T.muted }}>{f2(s.materiality)}</td>
                          <td style={{ padding: "8px 8px" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                              <div style={{ flex: 1, height: 6, background: "rgba(255,255,255,0.05)", borderRadius: 3, overflow: "hidden" }}>
                                <div style={{ width: `${Math.min(100, (score / maxScore) * 100)}%`, height: "100%", background: T.green, opacity: 0.8 }} />
                              </div>
                              <span style={{ fontSize: 12, fontFamily: T.mono, fontWeight: 800, color: T.text, width: 40, textAlign: "right" }}>{score >= 100 ? score.toFixed(0) : score.toFixed(1)}</span>
                            </div>
                          </td>
                          <td style={{ ...cell, color: T.light, fontWeight: 500 }}>{timeAgo(s.created_at)}</td>
                          <td style={{ textAlign: "center", color: T.light }}>{hover === s.id && !isOpen ? "›" : ""}</td>
                        </tr>
                        {isOpen && (
                          <tr style={{ borderBottom: `1px solid ${T.border}`, background: T.elevated }}>
                            <td colSpan={12} style={{ padding: "4px 16px 18px 42px" }}>
                              <SignalDetail
                                sig={s}
                                detail={details[s.id]}
                                history={histCache[`${s.entity_id}:${histWindow}`]}
                                histWindow={histWindow}
                                onWindow={changeHistWindow}
                              />
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
              {visibleSignals.length}{corrOnly ? ` of ${signals.length}` : ""} {corrOnly ? "corroborated " : ""}{status} signal{visibleSignals.length === 1 ? "" : "s"} · ranked by score (gap × materiality × corroboration × value-tier) · click a row to expand.
            </div>
          </>
        )}

        <TrackRecord backtest={backtest} />
        <ThemesBaskets themes={themes} />
        <ResolverHealth health={resolver} />
      </div>
    </div>
  );
}

// ── drill-down (declared at module scope; receives the lazily-loaded detail bundle) ──
function SignalDetail({ sig, detail, history, histWindow, onWindow }: {
  sig: Signal; detail: Detail | "loading" | undefined;
  history: HistPoint[] | "loading" | undefined; histWindow: number; onWindow: (h: number) => void;
}) {
  const tks = tickerList(sig.tickers);
  const primary = tks[0] ?? "PRIVATE";
  const loading = detail === undefined || detail === "loading";
  const d = (detail && detail !== "loading") ? detail : null;
  const histLoading = history === undefined || history === "loading";
  const histRows: HistPoint[] = Array.isArray(history) ? history : [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {/* score breakdown */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <MetricBlock label="Gap" value={f2(sig.gap_score)} accent={gapGrade(n(sig.gap_score)).color} tip="SA_GAP" />
        <MetricBlock label="Demand" value={f2(sig.demand_index)} tip="SA_DEMAND" />
        <MetricBlock label="Awareness" value={f2(sig.awareness_index)} tip="SA_AWARENESS" />
        <MetricBlock label="Velocity z" value={f1(sig.velocity_z)} tip="SA_VELOCITY" />
        <MetricBlock label="Corrob." value={`×${sig.corroboration ?? 1}`} tip="SA_CORROBORATION" />
        <MetricBlock label="Materiality" value={f2(sig.materiality)} tip="SA_MATERIALITY" />
        <MetricBlock label="Intent" value={pct(sig.intent_purchase_share)} tip="SA_INTENT" />
        <MetricBlock label="Score" value={(n(sig.signal_score) ?? 0).toFixed(1)} accent={T.green} tip="SA_SCORE" />
      </div>

      {sig.narrative && (
        <div style={{ fontSize: 11, fontFamily: T.mono, color: T.muted, lineHeight: 1.6, borderLeft: `2px solid ${T.green}`, paddingLeft: 12 }}>
          {sig.narrative}
        </div>
      )}

      {loading ? (
        <div style={{ fontFamily: T.mono, fontSize: 11, color: T.light, padding: "10px 0" }}>
          <RefreshCw size={13} className="animate-spin" style={{ display: "inline", verticalAlign: "middle", marginRight: 6 }} />
          Loading evidence…
        </div>
      ) : (
        <div style={{ display: "flex", gap: 18, flexWrap: "wrap" }}>
          {/* left: charts */}
          <div style={{ flex: "2 1 360px", minWidth: 300, display: "flex", flexDirection: "column", gap: 12 }}>
            <div>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
                <div style={{ fontSize: 9, fontFamily: T.mono, color: T.light, letterSpacing: "0.05em", textTransform: "uppercase" }}>Mentions</div>
                <div style={{ display: "flex", gap: 4 }}>
                  {([[168, "7d"], [2160, "90d"], [17520, "2y"]] as [number, string][]).map(([h, lbl]) => (
                    <button key={lbl} onClick={(e) => { e.stopPropagation(); onWindow(h); }}
                      style={{ fontSize: 8.5, fontFamily: T.mono, fontWeight: 600, padding: "1px 7px", borderRadius: 4, cursor: "pointer",
                        border: `1px solid ${histWindow === h ? T.green : T.border}`,
                        background: histWindow === h ? "var(--green-light)" : "transparent",
                        color: histWindow === h ? T.green : T.muted }}>{lbl}</button>
                  ))}
                </div>
              </div>
              {histLoading
                ? <div style={{ fontSize: 10, fontFamily: T.mono, color: T.light, padding: "16px 0" }}>loading history…</div>
                : <Spark values={histRows.map((h) => Number(h.mentions))} />}
            </div>
            <div>
              <div style={{ fontSize: 9, fontFamily: T.mono, color: T.light, letterSpacing: "0.05em", textTransform: "uppercase", marginBottom: 6 }}>Intent mix</div>
              <IntentBars rows={d?.intent ?? []} />
            </div>
          </div>
          {/* right: ticker */}
          <div style={{ flex: "1 1 200px", minWidth: 190 }}>
            <div style={{ fontSize: 9, fontFamily: T.mono, color: T.light, letterSpacing: "0.05em", textTransform: "uppercase", marginBottom: 6 }}>Mapped ticker</div>
            <TickerCard primary={primary} quote={d?.quote ?? null} />
          </div>
        </div>
      )}

      {/* evidence posts */}
      {d && d.mentions.length > 0 && (
        <div>
          <div style={{ fontSize: 9, fontFamily: T.mono, color: T.light, letterSpacing: "0.05em", textTransform: "uppercase", marginBottom: 6 }}>Evidence · top mentions</div>
          <div style={{ display: "flex", gap: 5, flexWrap: "wrap", marginBottom: 8 }}>
            {Object.entries(d.mentions.reduce((acc, m) => { acc[m.source] = (acc[m.source] || 0) + 1; return acc; }, {} as Record<string, number>))
              .sort((a, b) => b[1] - a[1])
              .map(([src, c]) => (
                <Chip key={src} text={`${src} ×${c}`} color={T.muted} bg="rgba(255,255,255,0.06)" />
              ))}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
            {d.mentions.map((m, idx) => (
              <div key={idx} style={{ padding: "8px 10px", border: `1px solid ${T.border}`, borderRadius: 6, background: T.bg }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4, flexWrap: "wrap" }}>
                  <Chip text={m.source} color={T.muted} bg="rgba(255,255,255,0.06)" />
                  {m.intent && m.intent !== "neutral" && <Chip text={m.intent.replace(/_/g, " ")} color={T.green} bg="rgba(20,184,122,0.14)" />}
                  <span style={{ fontSize: 9, fontFamily: T.mono, color: T.light }}>{timeAgo(m.timestamp)} ago</span>
                  {m.url && (
                    <a href={m.url} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()} style={{ marginLeft: "auto", color: T.purple, display: "inline-flex", alignItems: "center", gap: 3, fontSize: 9.5, fontFamily: T.mono }}>
                      open <ExternalLink size={10} />
                    </a>
                  )}
                </div>
                <div style={{ fontSize: 10.5, fontFamily: T.mono, color: T.muted, lineHeight: 1.5, maxHeight: 48, overflow: "hidden" }}>{m.content}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── track record (backtest forward returns; accrues from each signal's emission) ──
function TrackRecord({ backtest }: { backtest: Backtest | null }) {
  const st = backtest?.stats;
  const measured = st?.measured_21d ?? 0;
  const top = (backtest?.top_signals ?? []).filter(Boolean);
  const cases = (backtest?.validated_cases ?? []).filter(Boolean);
  const hit = st?.thesis_hit_rate;
  const isReplay = backtest?.mode === "replay";
  const th: React.CSSProperties = { padding: "7px 8px", fontSize: 9, fontFamily: T.mono, fontWeight: 700, letterSpacing: "0.05em", textAlign: "right", color: T.light, textTransform: "uppercase" };
  return (
    <div style={{ marginTop: 32 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 10, flexWrap: "wrap" }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 7, fontSize: 12, fontFamily: T.mono, fontWeight: 800, letterSpacing: "0.04em", color: T.text }}>
          <TrendingUp size={13} style={{ color: T.green }} /> TRACK RECORD
        </span>
        <span style={{ fontSize: 9.5, fontFamily: T.mono, color: T.light }}>
          forward returns from each signal&apos;s emission · fills in at +5 / +21 / +63d
        </span>
      </div>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 14 }}>
        <StatCard label="Signals tracked" value={String(st?.total_signals ?? 0)} accent={T.green} />
        <StatCard label="Avg +5d" value={fmtRet(st?.avg_return_5d)} accent={retColor(st?.avg_return_5d)} />
        <StatCard label="Avg +21d" value={fmtRet(st?.avg_return_21d)} accent={retColor(st?.avg_return_21d)} />
        <StatCard label="Avg +63d" value={fmtRet(st?.avg_return_63d)} accent={retColor(st?.avg_return_63d)} />
        <StatCard label="Win (21d)" value={measured ? pct((st?.winners_21d ?? 0) / measured) : "—"} sub={measured ? `${st?.winners_21d ?? 0}/${measured} measured` : "accruing"} />
      </div>
      {measured === 0 && (
        <div style={{ fontSize: 10.5, fontFamily: T.mono, color: T.muted, lineHeight: 1.5, padding: "9px 12px", background: "var(--amber-light)", border: `1px solid ${T.border}`, borderRadius: 6 }}>
          No resolved windows yet — returns measure forward from each signal&apos;s emission date, so the track
          record fills in over the coming weeks. A retroactive 2-year history would need point-in-time replay.
        </div>
      )}
      {top.length > 0 && (
        <div style={{ overflowX: "auto", border: `1px solid ${T.border}`, borderRadius: 8, background: T.surface, marginTop: 12 }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: T.mono }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                <th style={{ ...th, textAlign: "left" }}>Entity</th>
                <th style={th}>Ticker</th>
                <th style={th}>+21d</th>
                <th style={th}>Emitted</th>
              </tr>
            </thead>
            <tbody>
              {top.map((r, i) => (
                <tr key={i} style={{ borderTop: `1px solid ${T.border}` }}>
                  <td style={{ padding: "6px 8px", color: T.text }}>{r.entity_name}</td>
                  <td style={{ padding: "6px 8px", textAlign: "right", color: T.purple }}>{r.tickers || "—"}</td>
                  <td style={{ padding: "6px 8px", textAlign: "right", color: retColor(r.return_21d), fontWeight: 700 }}>{fmtRet(r.return_21d)}</td>
                  <td style={{ padding: "6px 8px", textAlign: "right", color: T.light }}>{r.created_at ? new Date(r.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Thesis validation: low-awareness demand spike → awareness-close + revenue accel + re-rate? */}
      <div style={{ marginTop: 22 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 8, flexWrap: "wrap" }}>
          <span style={{ fontSize: 11, fontFamily: T.mono, fontWeight: 800, letterSpacing: "0.04em", color: T.text }}>THESIS VALIDATION</span>
          <span style={{ fontSize: 9.5, fontFamily: T.mono, color: T.light }}>
            a signal &quot;worked&quot; if within ~1–6mo: awareness closed + revenue accelerated + the stock re-rated vs SPY/sector
          </span>
          {isReplay && <Chip text="replay · dev-tools (HN) only" color={T.amber} bg="rgba(245,185,66,0.16)" />}
        </div>
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: cases.length ? 12 : 0 }}>
          <StatCard label="Thesis hit-rate" value={hit != null ? pct(hit) : "—"} sub={st?.labeled ? `${st?.validated ?? 0}/${st?.labeled} labeled` : "accruing"} accent={hit != null && hit > 0 ? T.green : undefined} />
        </div>
        {cases.length === 0 ? (
          <div style={{ fontSize: 10.5, fontFamily: T.mono, color: T.muted, lineHeight: 1.5, padding: "9px 12px", background: "var(--amber-light)", border: `1px solid ${T.border}`, borderRadius: 6 }}>
            No validated cases yet — each step resolves on its own clock: re-rate at +1–6mo, revenue after the next earnings. Historical replay validates the <span style={{ color: T.text }}>dev-tools (HN)</span> lane only; the consumer thesis validates <span style={{ color: T.text }}>forward</span> as signals resolve.
          </div>
        ) : (
          <div style={{ overflowX: "auto", border: `1px solid ${T.border}`, borderRadius: 8, background: T.surface }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 10.5, fontFamily: T.mono }}>
              <thead>
                <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                  <th style={{ ...th, textAlign: "left" }}>Entity</th>
                  <th style={th}>Ticker</th>
                  <th style={th}>Signal</th>
                  <th style={{ ...th, textAlign: "center" }}>Awareness↑</th>
                  <th style={{ ...th, textAlign: "center" }}>Revenue↑</th>
                  <th style={th}>Re-rate +126d</th>
                  <th style={{ ...th, textAlign: "center" }}>Validated</th>
                </tr>
              </thead>
              <tbody>
                {cases.map((c, i) => (
                  <tr key={i} style={{ borderTop: `1px solid ${T.border}`, background: c.validated ? "rgba(20,184,122,0.06)" : "transparent" }}>
                    <td style={{ padding: "6px 8px", color: T.text }}>{c.entity_name}</td>
                    <td style={{ padding: "6px 8px", textAlign: "right", color: T.purple }}>{c.tickers || "—"}</td>
                    <td style={{ padding: "6px 8px", textAlign: "right", color: T.light }}>{c.signal_date ? new Date(c.signal_date).toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "—"}</td>
                    <td style={{ padding: "6px 8px", textAlign: "center", color: c.awareness_closed ? T.green : T.light }}>{c.awareness_closed ? "✓" : "—"}</td>
                    <td style={{ padding: "6px 8px", textAlign: "center", color: c.rev_accel ? T.green : T.light }}>{c.rev_accel ? "✓" : "—"}</td>
                    <td style={{ padding: "6px 8px", textAlign: "right", color: retColor(c.rerate_excess_126d), fontWeight: 700 }}>{fmtRet(c.rerate_excess_126d)}</td>
                    <td style={{ padding: "6px 8px", textAlign: "center" }}>{c.validated ? <Chip text="YES" color={T.green} bg="rgba(20,184,122,0.18)" /> : <span style={{ color: T.light }}>—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ── theme baskets (GET /api/social/themes) ──
// Seeded consumer themes → revenue-weighted ticker baskets. Hidden until the endpoint is live.
// The whole point: a basket is visible (and rankable by gap) before any single signal fires, so
// you see which names a demand surge would hit. Sorted server-side by gap desc, then mentions desc.
function ThemesBaskets({ themes }: { themes: Theme[] | null }) {
  if (!themes || themes.length === 0) return null;
  return (
    <div style={{ marginTop: 34 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 10, flexWrap: "wrap" }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 7, fontSize: 12, fontFamily: T.mono, fontWeight: 800, letterSpacing: "0.04em", color: T.text }}>
          <Layers size={13} style={{ color: T.green }} /> THEME BASKETS
        </span>
        <span style={{ fontSize: 9.5, fontFamily: T.mono, color: T.light }}>
          seeded consumer themes → revenue-weighted ticker baskets · the gap is the alpha — a basket ranks before any one signal fires
        </span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {themes.map((t) => {
          const grade = gapGrade(n(t.gap_score));
          const cons = (t.constituents ?? []).filter(Boolean);
          const maxShare = Math.max(0.01, ...cons.map((c) => n(c.revenue_share_est) ?? 0));
          return (
            <div key={t.theme_id} style={{ border: `1px solid ${T.border}`, borderRadius: 8, background: T.surface, padding: "12px 14px" }}>
              {/* header: theme name + tradeable + gap */}
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, flexWrap: "wrap" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <span style={{ fontSize: 13, fontFamily: T.mono, fontWeight: 800, color: T.text }}>{t.name}</span>
                  {t.tradeable
                    ? <Chip text="TRADEABLE" color={T.green} bg="rgba(20,184,122,0.18)" border="rgba(20,184,122,0.3)" />
                    : (t.mention_count_7d ?? 0) > 0
                      ? <Chip text="DEMAND BUILDING" color={T.amber} bg="rgba(245,185,66,0.16)" />
                      : <Chip text="WATCHING" color={T.light} bg="rgba(255,255,255,0.05)" />}
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ fontSize: 13, fontFamily: T.mono, fontWeight: 800, color: grade.color }}>{f2(t.gap_score)}</span>
                  <Chip text={grade.label} color={grade.color} bg={grade.bg} />
                </div>
              </div>
              {/* metrics */}
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 10 }}>
                <MetricBlock label="Demand" value={f2(t.demand_index)} tip="SA_DEMAND" />
                <MetricBlock label="Awareness" value={f2(t.awareness_index)} tip="SA_AWARENESS" />
                <MetricBlock label="Gap" value={f2(t.gap_score)} accent={grade.color} tip="SA_GAP" />
                <MetricBlock label="Mentions 7d" value={String(t.mention_count_7d ?? 0)} />
                <MetricBlock label="Names" value={String(cons.length)} />
              </div>
              {/* constituents — ranked by revenue share */}
              {cons.length === 0 ? (
                <div style={{ fontSize: 10, fontFamily: T.mono, color: T.light, marginTop: 10 }}>no mapped constituents yet</div>
              ) : (
                <div style={{ marginTop: 12 }}>
                  <div style={{ fontSize: 8.5, fontFamily: T.mono, color: T.light, letterSpacing: "0.05em", textTransform: "uppercase", marginBottom: 6 }}>
                    Basket · ranked by revenue exposure
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    {cons.map((c, i) => (
                      <div key={`${c.ticker}-${i}`} style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                        <span style={{ width: 92, display: "flex", alignItems: "center", gap: 5 }}>
                          <Chip text={isPrivate(c.ticker) ? "PRIVATE" : c.ticker}
                            color={isPrivate(c.ticker) ? T.light : T.purple}
                            bg={isPrivate(c.ticker) ? "rgba(255,255,255,0.05)" : "rgba(196,181,253,0.14)"}
                            border={isPrivate(c.ticker) ? undefined : "rgba(196,181,253,0.25)"} />
                        </span>
                        <span style={{ width: 38, fontSize: 9, fontFamily: T.mono, color: T.light }}>{c.exchange || ""}</span>
                        {/* revenue-share bar */}
                        <div style={{ flex: "1 1 120px", minWidth: 100, display: "flex", alignItems: "center", gap: 7 }}>
                          <div style={{ flex: 1, height: 7, background: "rgba(255,255,255,0.05)", borderRadius: 3, overflow: "hidden" }}>
                            <div style={{ width: `${((n(c.revenue_share_est) ?? 0) / maxShare) * 100}%`, height: "100%", background: T.purple, opacity: 0.65 }} />
                          </div>
                          <span style={{ fontSize: 10, fontFamily: T.mono, fontWeight: 700, color: T.muted, width: 38, textAlign: "right" }}>{pct(c.revenue_share_est)}</span>
                        </div>
                        <span style={{ fontSize: 9.5, fontFamily: T.mono, color: T.light, width: 64, textAlign: "right" }}>{fmtMcap(c.mcap_usd)}</span>
                        <span style={{ fontSize: 10, fontFamily: T.mono, fontWeight: 700, color: (n(c.allocated_score) ?? 0) > 0 ? T.green : T.muted, width: 54, textAlign: "right" }}>
                          {`${(n(c.allocated_score) ?? 0) >= 0 ? "+" : ""}${(n(c.allocated_score) ?? 0).toFixed(2)}`}
                        </span>
                        {c.rationale && (
                          <span style={{ flex: "1 1 160px", minWidth: 120, fontSize: 9.5, fontFamily: T.mono, color: T.light, lineHeight: 1.45, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={c.rationale}>{c.rationale}</span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
      <div style={{ marginTop: 10, fontSize: 9.5, fontFamily: T.mono, color: T.light, lineHeight: 1.5 }}>
        Allocated score = theme gap × revenue exposure. A theme &quot;lights up&quot; when demand surges while awareness stays low —
        the basket points at which listed names carry the exposure.
      </div>
    </div>
  );
}

// ── resolver / entity-graph health (GET /api/social/resolver/health) ──
// Makes the keystone visible: unknown names → MiMo proposes → FMP confirms → tradeable ticker.
// mimo_reachable surfaces the config blocker at a glance. Hidden until the endpoint is live.
function ResolverHealth({ health }: { health: ResolverHealth | null }) {
  if (!health) return null;
  const h = health;
  const resolved = (h.cache?.auto ?? 0) + (h.cache?.approved ?? 0);
  const reachable = h.mimo_reachable;
  const status = reachable === true
    ? { color: T.green, text: "MiMo reachable — resolver online", bg: "var(--green-light)" }
    : reachable === false
      ? { color: T.red, text: "MiMo unreachable — resolver stalled, queue not draining", bg: "var(--amber-light)" }
      : { color: T.amber, text: "MiMo not configured (MIMO_BASE_URL unset) — queue not draining", bg: "var(--amber-light)" };
  const th: React.CSSProperties = { padding: "7px 8px", fontSize: 9, fontFamily: T.mono, fontWeight: 700, letterSpacing: "0.05em", textAlign: "right", color: T.light, textTransform: "uppercase" };
  const pendCt = h.queue?.pending ?? 0;
  const breakdown = (label: string, parts: [string, number, string][]) => (
    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
      <span style={{ fontSize: 8.5, fontFamily: T.mono, color: T.light, letterSpacing: "0.05em", textTransform: "uppercase", width: 56 }}>{label}</span>
      {parts.map(([k, v, col]) => (
        <span key={k} style={{ fontSize: 9.5, fontFamily: T.mono, color: T.muted, border: `1px solid ${T.border}`, borderRadius: 4, padding: "2px 7px" }}>
          {k} <span style={{ color: col, fontWeight: 800 }}>{v}</span>
        </span>
      ))}
    </div>
  );
  return (
    <div style={{ marginTop: 34 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 10, flexWrap: "wrap" }}>
        <span style={{ display: "inline-flex", alignItems: "center", gap: 7, fontSize: 12, fontFamily: T.mono, fontWeight: 800, letterSpacing: "0.04em", color: T.text }}>
          <Cpu size={13} style={{ color: T.green }} /> RESOLVER HEALTH
        </span>
        <span style={{ fontSize: 9.5, fontFamily: T.mono, color: T.light }}>
          unknown names → MiMo proposes → FMP confirms → tradeable ticker · bias to &quot;unknown&quot; over a wrong ticker
        </span>
      </div>

      {/* status banner */}
      <div style={{ display: "flex", alignItems: "center", gap: 9, padding: "9px 13px", marginBottom: 14, borderRadius: 8, background: status.bg, border: `1px solid ${T.border}` }}>
        <span style={{ width: 9, height: 9, borderRadius: "50%", background: status.color, flexShrink: 0, boxShadow: `0 0 8px ${status.color}` }} />
        <span style={{ fontSize: 10.5, fontFamily: T.mono, fontWeight: 700, color: status.color }}>{status.text}</span>
        {h.last_resolved_at && (
          <span style={{ fontSize: 9.5, fontFamily: T.mono, color: T.light, marginLeft: "auto" }}>last resolved {timeAgo(h.last_resolved_at)} ago</span>
        )}
      </div>

      {/* KPIs */}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 14 }}>
        <StatCard label="Queue pending" value={String(pendCt)} sub={pendCt > 0 ? "awaiting resolution" : "drained"} accent={pendCt > 0 ? T.amber : T.green} />
        <StatCard label="Resolved" value={String(resolved)} sub={`${h.cache?.auto ?? 0} auto · ${h.cache?.approved ?? 0} approved`} accent={resolved > 0 ? T.green : undefined} />
        <StatCard label="In review" value={String(h.review_queue_count ?? 0)} sub={(h.review_queue_count ?? 0) > 0 ? "needs a human call" : "clear"} accent={(h.review_queue_count ?? 0) > 0 ? T.amber : undefined} />
        <StatCard label="Tickers mapped" value={String(h.entity_tickers_total ?? 0)} sub={`of ${h.entities_total ?? 0} entities`} />
        <StatCard label="Revenue-share" value={String(h.revenue_share_populated ?? 0)} sub="constituents weighted" />
      </div>

      {/* queue + cache breakdowns */}
      <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 14 }}>
        {breakdown("Queue", [
          ["pending", h.queue?.pending ?? 0, T.amber],
          ["resolving", h.queue?.resolving ?? 0, T.muted],
          ["done", h.queue?.done ?? 0, T.green],
          ["failed", h.queue?.failed ?? 0, T.red],
        ])}
        {breakdown("Cache", [
          ["auto", h.cache?.auto ?? 0, T.green],
          ["approved", h.cache?.approved ?? 0, T.green],
          ["review", h.cache?.review ?? 0, T.amber],
          ["rejected", h.cache?.rejected ?? 0, T.red],
        ])}
      </div>

      {/* top pending — the alpha stuck behind the resolver */}
      {(h.top_pending ?? []).length > 0 && (
        <div style={{ overflowX: "auto", border: `1px solid ${T.border}`, borderRadius: 8, background: T.surface }}>
          <div style={{ padding: "8px 12px", fontSize: 8.5, fontFamily: T.mono, color: T.light, letterSpacing: "0.05em", textTransform: "uppercase", borderBottom: `1px solid ${T.border}` }}>
            Stuck behind the resolver · top unresolved names by mentions
          </div>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 10.5, fontFamily: T.mono }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                <th style={{ ...th, textAlign: "left" }}>Name (normalized)</th>
                <th style={th}>Mentions</th>
              </tr>
            </thead>
            <tbody>
              {(h.top_pending ?? []).map((p, i) => (
                <tr key={i} style={{ borderTop: `1px solid ${T.border}` }}>
                  <td style={{ padding: "6px 10px", color: T.text }}>{p.norm_query}</td>
                  <td style={{ padding: "6px 10px", textAlign: "right", color: T.muted, fontWeight: 700 }}>{p.mention_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
