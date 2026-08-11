"use client";

// BASKET 13 — the catalyst book, read by WHEN, not by conviction.
//
// 2026-08-11 redesign (Bruno): the previous page copied the apex card shape but kept
// an 11-field payload per seat plus four competing name-lists (board / held / on-deck /
// passes) — ~47k characters of agent prose on one screen. This page is ONE list (the
// held book) in THREE groups that fall straight out of the data:
//   1. Resolving soon        — a binding date is on the calendar (countdown is the headline)
//   2. Event happened        — the date passed; the next re-debate decides the close
//   3. No date yet           — the company has only guided a quarter/season
// Each card face carries five facts: symbol, countdown, live P&L, plain-English event,
// entry → current · target · floor. Everything else (rationale, Director view, latest
// re-underwrite, invalidation) lives under "details ▾". Machine tokens are translated
// at the display layer (FDA_approval_decision → "FDA decision"); the prose inside
// details is agent-authored and gets fixed upstream (house voice), not here.
//
// NAV is the WHOLE basket: prior (re-founded) books chain into the headline via their
// final_nav, so a re-founding no longer resets the public number to 100. The prior
// books' daily paths were never logged, so the chart shows the current book's path
// scaled onto the chained level (stated under the chart, not hidden).
//
// REMOVED (Bruno, 2026-08-11): the Director board table, memo + decision search, the
// counterfactual pass ledger, on-deck chips, the resolutions table, per-seat weight
// (wt) chips — per-seat sizing was never implemented, so printing 6.25% eight times
// said nothing. Deep history stays in the export + stock pages.
//
// Data: app/data/basket13.ts (auto-gen by backend/_basket13_export.py) +
// /basket13_dossiers.json (latest re-underwrites) + /api/quotes (60s live poll).

import { useState, useEffect, useMemo } from "react";
import Link from "next/link";
import { BASKET13 } from "../data/basket13";

const B13: any = BASKET13;

// ---------- helpers (house grammar) ----------
const fmtPx = (v: any) => (typeof v === "number" ? (v >= 10 ? v.toFixed(2) : v.toFixed(3)) : "–.––");
const fmtPct = (v: any, dp = 1) => (typeof v === "number" ? `${v >= 0 ? "+" : ""}${v.toFixed(dp)}%` : "—");
const perfColor = (v: any) => (typeof v !== "number" ? "var(--text-light)" : v >= 0 ? "var(--green)" : "var(--red)");
const dNice = (iso: any) => {
  const t = Date.parse(String(iso || ""));
  return Number.isFinite(t) ? new Date(t).toLocaleDateString("en-GB", { day: "numeric", month: "short" }) : "—";
};

const chip = (bg: string, fg: string): React.CSSProperties => ({
  fontSize: 10, padding: "2px 7px", borderRadius: 4, fontFamily: "var(--font-mono)",
  fontWeight: 700, background: bg, color: fg, whiteSpace: "nowrap",
});
const CHIP_AMBER = chip("var(--amber-light)", "var(--amber)");
const CHIP_GREEN = chip("var(--green-light)", "var(--green)");
const CHIP_MUTED = chip("var(--bg-elevated)", "var(--text-light)");
const CHIP_VIOLET = chip("var(--purple-light)", "var(--lavender)");

// ---------- display-layer translation (the machine token never reaches the reader) ----------
const DRIVER_PLAIN: Record<string, string> = {
  FDA_approval_decision: "FDA decision",
  FDA_clinical_readout: "Trial results",
  FDA_pathway_feedback: "FDA feedback",
  Forced_divest_flow: "Forced selling",
  Merger_close: "Takeover closing",
  Court_ruling: "Court ruling",
  Spin_off: "Spin-off",
  Lockup_expiry: "Lockup release",
};
const driverPlain = (d: any) => {
  const k = String(d || "").trim();
  return DRIVER_PLAIN[k] || (k ? k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()) : "Event");
};

// One sentence, hard-capped — the agent prose behind these fields runs to paragraphs;
// the full version lives on the stock page's debate tab, not here.
const firstSentence = (s: any, max = 200): string => {
  const t = String(s || "").trim();
  if (!t) return "";
  const cut = t.search(/(?<=[.!?])\s+(?=[A-Z$])/);
  const one = cut > 30 ? t.slice(0, cut + 1) : t;
  return one.length > max ? `${one.slice(0, max - 1).trimEnd()}…` : one;
};

// Per-seat radar flags, in the reader's words — SEAT-SPECIFIC facts only. The weekly
// skeptic's blanket verdict=REFUTED currently sits on nearly every seat, so repeating
// it per card would be the same noise the redesign removes; it renders ONCE as a
// book-level line under the hero instead. Raw reason survives as the tooltip.
const flagPlain = (reason: string): string | null => {
  if (/edge-gone/i.test(reason)) return "re-check: upside mostly priced in at this level — under review";
  return null;
};

// A milestone is a HARD date only when it LEADS with one ("2026-08-25 …"). Dates deeper
// in the prose are context (when guidance was published, the backstop, the review date)
// — AVIR's "company-guided 2026-07-28" is the day the company SAID "early 2027", not
// the event, and matching it put a 2027 readout in the "event happened" group.
const hardDate = (milestone: any): string | null => {
  const m = /^\s*(\d{4}-\d{2}-\d{2})/.exec(String(milestone || ""));
  return m ? m[1] : null;
};
// Soft label = the EARLIEST window mentioned, not the first pattern that happens to
// match — OLMA's own guide is `"fall 2026"` but a stray Q-token later in the prose
// used to win because the Q-pattern was checked first.
const softLabel = (milestone: any): string => {
  const s = String(milestone || "");
  const pats: [RegExp, (t: string) => string][] = [
    [/\b(Q[1-4][\s-]?20\d{2})\b/i, (t) => t.toUpperCase().replace(/[\s-]+/, " ")],
    [/\b((?:early|mid|late|spring|summer|fall|autumn|winter)[\s-]?20\d{2})\b/i, (t) => t.toLowerCase().replace(/[\s-]+/, " ")],
    [/\b(H[12][\s-]?20\d{2})\b/i, (t) => t.toUpperCase().replace(/[\s-]+/, " ")],
  ];
  let best: { i: number; label: string } | null = null;
  for (const [re, fmt] of pats) {
    const m = re.exec(s);
    if (m && (best == null || (m.index as number) < best.i)) best = { i: m.index as number, label: fmt(m[1]) };
  }
  return best ? best.label : "no date yet";
};

// ---------- NAV chart (base-100 dashed ref = whole-basket break-even) ----------
function NavChart({ marks }: { marks: any[] }) {
  const pts = (marks || []).filter((m) => typeof m?.nav === "number");
  if (pts.length < 2) return null;
  const W = 720, H = 200, PAD = 8;
  const navs = pts.map((m) => m.nav);
  const lo = Math.min(...navs, 100), hi = Math.max(...navs, 100);
  const span = Math.max(hi - lo, 0.5);
  const x = (i: number) => PAD + (i / (pts.length - 1)) * (W - 2 * PAD);
  const y = (v: number) => PAD + (1 - (v - lo) / span) * (H - 2 * PAD);
  const line = pts.map((m, i) => `${x(i).toFixed(1)},${y(m.nav).toFixed(1)}`).join(" ");
  const last = pts[pts.length - 1];
  const up = last.nav >= 100;
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
        <line x1={PAD} x2={W - PAD} y1={y(100)} y2={y(100)} stroke="var(--border)" strokeDasharray="4 4" strokeWidth={1} />
        <polyline points={line} fill="none" stroke={up ? "var(--green)" : "var(--red)"} strokeWidth={1.8} />
        <circle cx={x(pts.length - 1)} cy={y(last.nav)} r={3} fill={up ? "var(--green)" : "var(--red)"} />
        <text x={PAD} y={y(hi) - 2 < 10 ? 12 : y(hi) - 2} fontSize={9} fill="var(--text-light)" fontFamily="var(--font-mono)">{hi.toFixed(1)}</text>
        <text x={PAD} y={Math.min(y(lo) + 10, H - 2)} fontSize={9} fill="var(--text-light)" fontFamily="var(--font-mono)">{lo.toFixed(1)}</text>
      </svg>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 8.5, color: "var(--text-light)", fontFamily: "var(--font-mono)", marginTop: 2 }}>
        <span>{pts[0].date}</span>
        <span>NAV {last.nav.toFixed(2)} · {last.date}</span>
      </div>
    </div>
  );
}

function Sparkline({ marks, w = 130, h = 34 }: { marks: any[]; w?: number; h?: number }) {
  const pts = (marks || []).filter((m) => typeof m?.nav === "number");
  if (pts.length < 2) return null;
  const navs = pts.map((m) => m.nav);
  const lo = Math.min(...navs, 100), hi = Math.max(...navs, 100);
  const span = Math.max(hi - lo, 0.5);
  const x = (i: number) => (i / (pts.length - 1)) * w;
  const y = (v: number) => 2 + (1 - (v - lo) / span) * (h - 4);
  const line = pts.map((m, i) => `${x(i).toFixed(1)},${y(m.nav).toFixed(1)}`).join(" ");
  const up = pts[pts.length - 1].nav >= 100;
  return (
    <svg width={w} height={h} style={{ display: "block" }}>
      <line x1={0} x2={w} y1={y(100)} y2={y(100)} stroke="var(--border)" strokeDasharray="3 3" strokeWidth={1} />
      <polyline points={line} fill="none" stroke={up ? "var(--green)" : "var(--red)"} strokeWidth={1.5} />
      <circle cx={x(pts.length - 1)} cy={y(pts[pts.length - 1].nav)} r={2.5} fill={up ? "var(--green)" : "var(--red)"} />
    </svg>
  );
}

// ---------- page ----------
export default function CatalystsPage() {
  const entries: any[] = B13.entries || [];
  const held = entries.filter((e) => !e.resolution);
  const marks: any[] = B13.marks || [];
  const priorBooks: any[] = B13.prior_books || [];

  // Whole-basket NAV: chain every prior (re-founded) book's final level under the
  // current book, so the public number covers the basket's whole life instead of
  // restarting at 100 each re-founding. Prior books logged no daily path — only the
  // headline level is chained; the chart series is the current book scaled onto it.
  const chainFactor = priorBooks.reduce((f: number, b: any) =>
    (typeof b?.final_nav === "number" && b.final_nav > 0 ? f * (b.final_nav / 100) : f), 1);
  const chainedMarks = useMemo(
    () => marks.map((m: any) => ({ ...m, nav: typeof m.nav === "number" ? m.nav * chainFactor : m.nav })),
    [marks, chainFactor]);
  const lastMark = chainedMarks[chainedMarks.length - 1] || {};
  const sinceIncept = typeof lastMark.nav === "number" ? lastMark.nav - 100 : null;

  // Basket inception: the earliest start we can derive from real fields — each prior
  // resolution carries resolution_date + days_held; entry = the difference. Falls back
  // to the current book's first mark when there is no prior record.
  const inceptionDate = useMemo(() => {
    let min: number | null = null;
    for (const b of priorBooks) {
      for (const r of b.resolutions || []) {
        const t = Date.parse(String(r.resolution_date || ""));
        if (Number.isFinite(t) && typeof r.days_held === "number") {
          const s = t - r.days_held * 86400000;
          if (min == null || s < min) min = s;
        }
      }
    }
    if (min == null && marks[0]?.date) min = Date.parse(marks[0].date);
    return min != null ? new Date(min).toISOString().slice(0, 10) : null;
  }, [priorBooks, marks]);
  const daysLive = inceptionDate && lastMark.date
    ? Math.max(0, Math.round((Date.parse(lastMark.date) - Date.parse(inceptionDate)) / 86400000))
    : null;
  const closedCount = entries.filter((e) => e.resolution).length
    + priorBooks.reduce((n: number, b: any) => n + (b.resolutions || []).length, 0);

  // Director assessments — details-only context (the board table is gone from the page).
  const latest: any = B13.latest_debate || null;
  const assessBySym: Record<string, any> = useMemo(() => {
    const m: Record<string, any> = {};
    (latest?.assessments || []).forEach((a: any) => { if (a?.symbol) m[a.symbol] = a; });
    return m;
  }, [latest]);

  // live quotes — held seats only, 60s (batch-quote proxy)
  const [quotes, setQuotes] = useState<Record<string, any>>({});
  useEffect(() => {
    const syms = Array.from(new Set(held.map((e) => e.symbol)));
    if (!syms.length) return;
    let stop = false;
    const pull = () =>
      fetch(`/api/quotes?symbols=${encodeURIComponent(syms.join(","))}&light=1`)
        .then((r) => r.json())
        .then((d) => {
          if (stop || !Array.isArray(d?.quotes)) return;
          const m: Record<string, any> = {};
          d.quotes.forEach((q: any) => { m[q.symbol] = q; });
          setQuotes(m);
        })
        .catch(() => {});
    pull();
    const iv = setInterval(pull, 60000);
    return () => { stop = true; clearInterval(iv); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // latest re-underwrites (deep-dossier store) — per-seat context inside details ▾
  const [dossiers, setDossiers] = useState<Record<string, any>>({});
  useEffect(() => {
    fetch("/basket13_dossiers.json")
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => { if (j?.dossiers) setDossiers(j.dossiers); })
      .catch(() => {});
  }, []);

  const [moreSym, setMoreSym] = useState<string | null>(null);

  const livePx = (sym: string) => {
    const q = quotes[sym];
    const v = q?.price ?? q?.c;
    return typeof v === "number" ? v : null;
  };
  const liveRet = (e: any) => {
    const px = livePx(e.symbol);
    return px && e.entry_price ? (px / e.entry_price - 1) * 100 : null;
  };

  // ---------- the three groups, straight out of the data ----------
  const NOW = Date.now();
  const groups = useMemo(() => {
    const soon: any[] = [], landed: any[] = [], soft: any[] = [];
    for (const e of held) {
      const iso = hardDate(e.dated_milestone);
      if (iso) {
        const days = Math.ceil((Date.parse(iso) - NOW) / 86400000);
        const row = { e, iso, days };
        (days >= 0 ? soon : landed).push(row);
      } else {
        soft.push({ e, iso: null, days: null, label: softLabel(e.dated_milestone) });
      }
    }
    soon.sort((a, b) => a.days - b.days);
    landed.sort((a, b) => b.days - a.days); // most recently landed first
    soft.sort((a, b) => String(a.label).localeCompare(String(b.label)));
    return { soon, landed, soft };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [held]);

  // The blanket skeptic dispute, stated once. Seats stay until their event or a close
  // call at the re-debate — that is the sleeve's rule, so per-card repetition adds nothing.
  const refuted = held.filter((e) => /REFUTED/i.test(String(e.resolution_due?.reason || "")));

  // ---------- one seat card ----------
  const Seat = ({ row }: { row: any }) => {
    const e = row.e;
    const a = assessBySym[e.symbol];
    const doss = dossiers[e.symbol];
    const isPend = e.status === "PENDING_LIMIT";
    const px = livePx(e.symbol);
    const ret = liveRet(e);
    const isMore = moreSym === e.symbol;
    const due = e.resolution_due;
    const flag = due?.reason ? flagPlain(String(due.reason)) : null;
    const countdown = row.days == null
      ? <span style={CHIP_MUTED}>{row.label}</span>
      : row.days >= 0
        ? <span style={row.days <= 21 ? CHIP_AMBER : CHIP_GREEN}>{row.days === 0 ? "today" : `${row.days} day${row.days === 1 ? "" : "s"}`}</span>
        : <span style={CHIP_VIOLET}>{Math.abs(row.days)} day{Math.abs(row.days) === 1 ? "" : "s"} ago</span>;
    return (
      <div style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 10, padding: "13px 15px", display: "flex", flexDirection: "column", gap: 7 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
          <Link href={`/stock/${encodeURIComponent(e.symbol)}?tab=debate`}
            style={{ fontSize: 15, fontWeight: 700, fontFamily: "var(--font-mono)", color: "var(--text)", textDecoration: "none" }}>{e.symbol}</Link>
          {countdown}
          {isPend && <span style={CHIP_MUTED}>resting @ {fmtPx(e.limit_price)}</span>}
          <span style={{ marginLeft: "auto", fontSize: 14, fontWeight: 700, fontFamily: "var(--font-mono)", color: perfColor(ret) }}>
            {isPend ? "–.––" : fmtPct(ret)}
          </span>
        </div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text)" }}>
          {driverPlain(e.resolution_driver)}{row.iso ? ` · ${dNice(row.iso)}` : row.label ? ` · guided ${row.label}` : ""}
        </div>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 11.5, color: "var(--text-muted)", fontVariantNumeric: "tabular-nums" }}>
          ${fmtPx(e.entry_price ?? e.limit_price)} → <b style={{ color: "var(--text-secondary)" }}>${fmtPx(px)}</b>
          {typeof e.fair_value_target === "number" && <> · target <b style={{ color: "var(--green)" }}>${fmtPx(e.fair_value_target)}</b></>}
          {typeof e.downside_floor === "number" && <> · floor <b style={{ color: "var(--red)" }}>${fmtPx(e.downside_floor)}</b></>}
        </div>
        {flag && (
          <div title={String(due.reason)} style={{ fontFamily: "var(--font-mono)", fontSize: 10.5, color: "var(--amber)", cursor: "help" }}>
            ⚑ {flag}
          </div>
        )}
        <div style={{ borderTop: "1px solid var(--border-subtle)", paddingTop: 7 }}>
          {/* Concise on purpose (Bruno, 2026-08-11): one sentence per field, three fields
              max — the full agent-written record lives on the stock page's debate tab.
              Field order = the reader's questions in order: why is it here, what does the
              Director think now, what kills it. */}
          {isMore && (
            <div style={{ fontSize: 12, lineHeight: 1.55, color: "var(--text-secondary)", display: "flex", flexDirection: "column", gap: 6, marginBottom: 6 }}>
              {e.entry_rationale && <div><strong style={{ color: "var(--text)" }}>Why:</strong> {firstSentence(e.entry_rationale)}</div>}
              {a && <div><strong style={{ color: "var(--text)" }}>Director now:</strong> {a.would_seat ? "would keep it" : "would not seat it today"}{a.binding_reason ? ` — ${firstSentence(a.binding_reason, 160)}` : ""}</div>}
              {(doss?.kill_risk || e.invalidation) && <div><strong style={{ color: "var(--red)" }}>Kill risk:</strong> {firstSentence(typeof doss?.kill_risk === "string" ? doss.kill_risk : e.invalidation, 180)}</div>}
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 10 }}>
                the full record — thesis, re-checks, skeptic — is on the <Link href={`/stock/${encodeURIComponent(e.symbol)}?tab=debate`} style={{ color: "var(--green)" }}>stock page →</Link>
              </div>
            </div>
          )}
          <button onClick={() => setMoreSym(isMore ? null : e.symbol)}
            style={{ background: "none", border: "none", color: "var(--text-light)", fontSize: 10.5, fontFamily: "var(--font-mono)", cursor: "pointer", padding: 0 }}>
            {isMore ? "▴ less" : "details ▾"}
          </button>
        </div>
      </div>
    );
  };

  const GroupHead = ({ color, title, n }: { color: string; title: string; n: number }) => (
    <div style={{ display: "flex", alignItems: "center", gap: 9, margin: "6px 0 10px" }}>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color }}>{title}</span>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 10.5, color: "var(--text-light)" }}>{n}</span>
      <span style={{ flex: 1, height: 1, background: "var(--border-subtle)" }} />
    </div>
  );

  const GRID: React.CSSProperties = { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 12, marginBottom: 18 };

  return (
    <div style={{ maxWidth: 1180, margin: "0 auto", padding: "24px 16px 60px" }}>
      <div style={{ background: "var(--bg-surface)", border: "1px solid var(--green)", borderRadius: 12, padding: "20px 24px" }}>

        <div style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>Basket 13 — Catalyst Book</div>

        {/* How this book works — the commodities-page idiom: orient the reader BEFORE the
            positions. The three steps are a true sequence (enter → hold → close), and the
            mix line is computed from the live book, not hand-written. */}
        <div style={{ border: "1px solid var(--border)", background: "var(--bg)", borderRadius: 8, padding: "12px 16px", marginBottom: 18 }}>
          <div style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.1em", color: "var(--text-light)", fontFamily: "var(--font-mono)", marginBottom: 8 }}>How this book works</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: "10px 22px", fontSize: 12, lineHeight: 1.55, color: "var(--text-secondary)" }}>
            <div><b style={{ color: "var(--green)", fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.08em" }}>1 · ENTER</b><br />
              Only situations with a dated event attached — an FDA decision, trial results, a takeover closing, forced selling. Each candidate clears four checks (dossier → trade desk → skeptic → Director) before it gets a seat. No limit on how many seats, or of what kind.</div>
            <div><b style={{ color: "var(--green)", fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.08em" }}>2 · HOLD</b><br />
              Every seat carries the same slice; half the book stays in cash as the shock absorber. Nothing rebalances — adding a name dilutes every other seat, and that dilution is the only sizing rule.</div>
            <div><b style={{ color: "var(--green)", fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.08em" }}>3 · CLOSE</b><br />
              A seat leaves only when its event lands — win or lose — or the weekly debate rules the edge gone. Every close is graded afterwards against what the stock did next.</div>
          </div>
          {(() => {
            const mix = new Map<string, number>();
            for (const e of held) { const k = driverPlain(e.resolution_driver); mix.set(k, (mix.get(k) || 0) + 1); }
            const rows = [...mix.entries()].sort((a, b) => b[1] - a[1]);
            return rows.length ? (
              <div style={{ borderTop: "1px dashed var(--border)", marginTop: 10, paddingTop: 8, fontFamily: "var(--font-mono)", fontSize: 10.5, color: "var(--text-muted)" }}>
                In the book now: {rows.map(([k, n], i) => <span key={k}>{i > 0 && " · "}<b style={{ color: "var(--text)" }}>{k}</b> ×{n}</span>)}
              </div>
            ) : null;
          })()}
        </div>

        {/* whole-basket track record */}
        <div style={{ border: "1px solid var(--border)", background: "var(--bg)", borderRadius: 8, padding: "12px 16px", display: "flex", flexWrap: "wrap", alignItems: "center", gap: 18, justifyContent: "space-between", marginBottom: 18 }}>
          <div>
            <div style={{ fontSize: 20, fontWeight: 800, fontFamily: "var(--font-mono)", color: perfColor(sinceIncept) }}>{fmtPct(sinceIncept, 2)}</div>
            <div style={{ fontSize: 9, color: "var(--text-light)", fontFamily: "var(--font-mono)" }}>
              since {inceptionDate ? dNice(inceptionDate) : "—"}{daysLive != null ? ` · ${daysLive}d` : ""}
            </div>
          </div>
          <Sparkline marks={chainedMarks} />
          <div style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-muted)", textAlign: "right" }}>
            <b style={{ color: "var(--text)" }}>{held.length}</b> held · <b style={{ color: "var(--text)" }}>{closedCount}</b> closed
          </div>
        </div>

        {refuted.length > 0 && (
          <div title={refuted.map((e) => e.symbol).join(", ")}
            style={{ fontFamily: "var(--font-mono)", fontSize: 10.5, color: "var(--amber)", margin: "-8px 0 16px", cursor: "help" }}>
            ⚑ the weekly check currently disputes {refuted.length} of {held.length} held theses — seats stay until their event, or a close call at the next debate
          </div>
        )}

        <details style={{ marginBottom: 18 }}>
          <summary style={{ fontSize: 11, fontFamily: "var(--font-mono)", cursor: "pointer", color: "var(--text-light)" }}>
            ▸ NAV chart · {chainedMarks.length} marks
          </summary>
          <div style={{ paddingTop: 8 }}>
            <NavChart marks={chainedMarks} />
            {priorBooks.length > 0 && (
              <div style={{ fontSize: 8.5, color: "var(--text-light)", marginTop: 4 }}>
                Level covers the whole basket (earlier seats chained in at their closing level of {priorBooks[priorBooks.length - 1].final_nav}); the daily path shown starts {marks[0]?.date} — the earlier daily path wasn&apos;t logged.
              </div>
            )}
          </div>
        </details>

        {groups.soon.length > 0 && (
          <>
            <GroupHead color="var(--amber)" title="Resolving soon" n={groups.soon.length} />
            <div style={GRID}>{groups.soon.map((r: any) => <Seat key={r.e.symbol} row={r} />)}</div>
          </>
        )}
        {groups.landed.length > 0 && (
          <>
            <GroupHead color="var(--lavender)" title="Event happened — waiting on the close call" n={groups.landed.length} />
            <div style={GRID}>{groups.landed.map((r: any) => <Seat key={r.e.symbol} row={r} />)}</div>
          </>
        )}
        {groups.soft.length > 0 && (
          <>
            <GroupHead color="var(--text-light)" title="No date yet — only a guided window" n={groups.soft.length} />
            <div style={GRID}>{groups.soft.map((r: any) => <Seat key={r.e.symbol} row={r} />)}</div>
          </>
        )}
        {!held.length && (
          <div style={{ fontSize: 12, color: "var(--text-light)", fontFamily: "var(--font-mono)" }}>No open seats.</div>
        )}
      </div>
    </div>
  );
}
