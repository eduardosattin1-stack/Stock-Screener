"use client";
import { useState, useEffect, useMemo, Fragment, useCallback } from "react";
import {
  Radio, Activity, ChevronRight, ChevronDown, ExternalLink, RefreshCw, TrendingUp,
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
    avg_return_21d?: number;
    winners_21d?: number;
    measured_21d?: number;
  };
}
interface HistPoint { hour: string; mentions: number; sentiment: number; intent_purchase: number; authors: number; }
interface IntentRow { intent: string; count: number; avg_score: number; }
interface Mention {
  matched_text?: string; method?: string; intent?: string; intent_score?: number;
  content: string; source: string; timestamp: string; url?: string;
}
interface Quote { symbol: string; name?: string; price: number | null; day: number | null; ytd: number | null; year: number | null; }
interface Detail { history: HistPoint[]; intent: IntentRow[]; mentions: Mention[]; quote: Quote | null; }

const STATUSES = ["new", "investigating", "passed", "positioned", "closed"] as const;
type Status = (typeof STATUSES)[number];

// ── helpers ──
const n = (x: any): number | null => { const v = Number(x); return Number.isFinite(v) ? v : null; };
const f1 = (x: any) => { const v = n(x); return v == null ? "—" : v.toFixed(1); };
const f2 = (x: any) => { const v = n(x); return v == null ? "—" : v.toFixed(2); };
const pct = (x: any) => { const v = n(x); return v == null ? "—" : `${(v * 100).toFixed(0)}%`; };

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

  // stats + backtest once
  useEffect(() => {
    fetch(`${SOCIAL}/stats`).then((r) => (r.ok ? r.json() : null)).then(setStats).catch(() => {});
    fetch(`${SOCIAL}/backtest`).then((r) => (r.ok ? r.json() : null)).then(setBacktest).catch(() => {});
  }, []);

  const loadDetail = useCallback((sig: Signal) => {
    if (details[sig.id]) return;
    setDetails((d) => ({ ...d, [sig.id]: "loading" }));
    const id = sig.entity_id;
    const primary = tickerList(sig.tickers)[0] ?? "";
    const quoteP = isPrivate(primary)
      ? Promise.resolve(null)
      : fetch(`/api/quotes?symbols=${encodeURIComponent(primary)}`).then((r) => (r.ok ? r.json() : null)).then((d) => d?.quotes?.[0] ?? null).catch(() => null);
    Promise.all([
      fetch(`${SOCIAL}/entities/${id}/history?hours=168`).then((r) => (r.ok ? r.json() : [])).catch(() => []),
      fetch(`${SOCIAL}/entities/${id}/intent`).then((r) => (r.ok ? r.json() : [])).catch(() => []),
      fetch(`${SOCIAL}/entities/${id}/mentions?limit=8`).then((r) => (r.ok ? r.json() : [])).catch(() => []),
      quoteP,
    ]).then(([history, intent, mentions, quote]) => {
      setDetails((d) => ({ ...d, [sig.id]: { history, intent, mentions, quote } }));
    }).catch(() => {
      setDetails((d) => ({ ...d, [sig.id]: { history: [], intent: [], mentions: [], quote: null } }));
    });
  }, [details]);

  const toggleRow = (sig: Signal) => {
    const open = expanded === sig.id;
    setExpanded(open ? null : sig.id);
    if (!open) loadDetail(sig);
  };

  const maxScore = useMemo(() => Math.max(1, ...signals.map((s) => n(s.signal_score) ?? 0)), [signals]);

  const bt = backtest?.stats;
  const winRate = bt && bt.measured_21d ? (bt.winners_21d ?? 0) / bt.measured_21d : null;
  const freshness = signals[0]?.created_at
    ? new Date(signals[0].created_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
    : "—";
  const sources = stats?.source_counts ? Object.keys(stats.source_counts).length : null;

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
                  {signals.map((s, i) => {
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
                              <SignalDetail sig={s} detail={details[s.id]} />
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
              {signals.length} {status} signal{signals.length === 1 ? "" : "s"} · ranked by score (gap × materiality × corroboration, intent-weighted) · click a row to expand.
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ── drill-down (declared at module scope; receives the lazily-loaded detail bundle) ──
function SignalDetail({ sig, detail }: { sig: Signal; detail: Detail | "loading" | undefined }) {
  const tks = tickerList(sig.tickers);
  const primary = tks[0] ?? "PRIVATE";
  const loading = detail === undefined || detail === "loading";
  const d = (detail && detail !== "loading") ? detail : null;

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
              <div style={{ fontSize: 9, fontFamily: T.mono, color: T.light, letterSpacing: "0.05em", textTransform: "uppercase", marginBottom: 4 }}>Mentions · 7d</div>
              <Spark values={(d?.history ?? []).map((h) => Number(h.mentions))} />
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
