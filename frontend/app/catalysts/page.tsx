"use client";

// BASKET 13 — the catalyst book, in the same idiom as the apex/value books.
//
// 2026-07-28 revamp (Bruno): one Director, one basket, one ledger. The page is
// basket-first — NAV track record, the held seats, the Director's memo + decision
// history (searchable), the resolutions ledger, and the counterfactual scoreboard
// (every pass priced at pass time and graded vs SPY by the daily mark).
//
// RETIRED here (deliberately, not lost): the Loeb/Bloom deep-scan depth view, the
// candidates sidebar and the standalone watchlist cards. The deep scan's
// deterministic evidence (arb math, credit gate) feeds the debate pipeline, not
// this page; per-name depth now lives on the stock page's Speculair Debate tab,
// which serves the same week's multi-agent debate for every name here.
//
// Data: app/data/basket13.ts (auto-gen by backend/_basket13_export.py) +
// /basket13_dossiers.json (latest re-underwrites) + /api/quotes (60s live poll).

import { useState, useEffect, useMemo } from "react";
import Link from "next/link";
import { Activity, Clock, Search, ChevronDown, ChevronRight, FileText, Scale, SkipForward } from "lucide-react";
import { BASKET13 } from "../data/basket13";

const B13: any = BASKET13;

// ---------- helpers (house grammar) ----------
const fmtPx = (v: any) => (typeof v === "number" ? (v >= 100 ? v.toFixed(2) : v >= 10 ? v.toFixed(2) : v.toFixed(3)) : "–.––");
const fmtPct = (v: any, dp = 1) => (typeof v === "number" ? `${v >= 0 ? "+" : ""}${v.toFixed(dp)}%` : "—");
const perfColor = (v: any) => (typeof v !== "number" ? "var(--text-light)" : v >= 0 ? "var(--green)" : "var(--red)");
const dShort = (d: any) => (typeof d === "string" ? d.slice(2) : "—");

const chip = (bg: string, fg: string): React.CSSProperties => ({
  fontSize: 9, padding: "1px 5px", borderRadius: 3, fontFamily: "var(--font-mono)",
  fontWeight: 700, background: bg, color: fg, whiteSpace: "nowrap",
});
const CHIP_GREEN = chip("var(--green-light)", "var(--green)");
const CHIP_AMBER = chip("var(--amber-light)", "var(--amber)");
const CHIP_RED = chip("var(--red-light)", "var(--red)");
const CHIP_MUTED = chip("var(--bg-elevated)", "var(--text-light)");

const TH: React.CSSProperties = {
  fontSize: 9, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-light)",
  padding: "6px 8px", textAlign: "left", fontWeight: 600, whiteSpace: "nowrap",
};
const TD: React.CSSProperties = {
  fontSize: 11, fontFamily: "var(--font-mono)", padding: "6px 8px",
  borderTop: "1px solid var(--border-subtle)", fontVariantNumeric: "tabular-nums", whiteSpace: "nowrap",
};
const CARD: React.CSSProperties = {
  background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: 12,
  padding: "18px 22px", marginBottom: 16,
};
const CARD_TITLE: React.CSSProperties = {
  fontSize: 13, fontWeight: 700, display: "flex", alignItems: "center", gap: 6,
  textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 12,
};

// ---------- NAV chart (basket/[key] idiom: base-100 dashed ref, min/max labels only) ----------
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
  const open = entries.filter((e) => !e.resolution && e.status !== "PENDING_LIMIT");
  const pending = entries.filter((e) => !e.resolution && e.status === "PENDING_LIMIT");
  const resolved = entries.filter((e) => e.resolution);
  const marks: any[] = B13.marks || [];
  const lastMark = marks[marks.length - 1] || {};
  const latest: any = B13.latest_debate || null;
  const assessBySym: Record<string, any> = useMemo(() => {
    const m: Record<string, any> = {};
    (latest?.assessments || []).forEach((a: any) => { if (a?.symbol) m[a.symbol] = a; });
    return m;
  }, [latest]);

  // live quotes — held + pending + on-deck, 60s (batch-quote proxy)
  const [quotes, setQuotes] = useState<Record<string, any>>({});
  useEffect(() => {
    const syms = Array.from(new Set([
      ...entries.filter((e) => !e.resolution).map((e) => e.symbol),
      ...(B13.watchlist || []).map((w: any) => w.symbol),
    ]));
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

  // latest re-underwrites (deep-dossier store) — per-seat kill-risk in the expanded row
  const [dossiers, setDossiers] = useState<Record<string, any>>({});
  useEffect(() => {
    fetch("/basket13_dossiers.json")
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => { if (j?.dossiers) setDossiers(j.dossiers); })
      .catch(() => {});
  }, []);

  const [expanded, setExpanded] = useState<string | null>(null);
  const [memoQuery, setMemoQuery] = useState("");
  const [showAllPasses, setShowAllPasses] = useState(false);

  const livePx = (sym: string) => {
    const q = quotes[sym];
    const v = q?.price ?? q?.c;
    return typeof v === "number" ? v : null;
  };
  const liveRet = (e: any) => {
    const px = livePx(e.symbol);
    return px && e.entry_price ? (px / e.entry_price - 1) * 100 : null;
  };

  // hero numbers
  const sinceIncept = typeof lastMark.nav === "number" ? lastMark.nav - 100 : null;
  const wins = resolved.filter((e) => (e.resolution?.realized_return_pct ?? 0) > 0).length;
  const days = marks.length >= 2
    ? Math.round((new Date(lastMark.date).getTime() - new Date(marks[0].date).getTime()) / 86400000)
    : 0;

  // counterfactual ledger (priced passes only; artifacts without price0 excluded from stats)
  const passes: any[] = (B13.non_selections || []).filter((n: any) => typeof n?.alpha_pp === "number");
  const goodPasses = passes.filter((n) => n.alpha_pp <= 0).length;
  const medianAlpha = useMemo(() => {
    if (!passes.length) return null;
    const a = passes.map((n) => n.alpha_pp).sort((x, y) => x - y);
    const mid = Math.floor(a.length / 2);
    return a.length % 2 ? a[mid] : (a[mid - 1] + a[mid]) / 2;
  }, [passes]);
  const passesSorted = useMemo(
    () => [...passes].sort((a, b) => (b.date || "").localeCompare(a.date || "") || (b.alpha_pp - a.alpha_pp)),
    [passes]);

  // memo/decision search — "find the evidence later": filters the decision table AND the run history
  const q = memoQuery.trim().toLowerCase();
  const hit = (s: any) => !q || String(s || "").toLowerCase().includes(q);
  const assessRows = (latest?.assessments || []).filter(
    (a: any) => hit(a.symbol) || hit(a.binding_reason) || hit(a.posture) || hit(a.catalyst_status));
  const runRows = (B13.runs || []).filter((r: any) => hit(r.memo) || hit(r.run_date)).slice().reverse();

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto", padding: "24px 16px 60px" }}>

      {/* ── hero: live track record (apex idiom) ── */}
      <div style={{ ...CARD, border: "1px solid var(--green)" }}>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 18, justifyContent: "space-between" }}>
          <div>
            <div style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.1em", color: "var(--text-light)", marginBottom: 4 }}>
              Basket 13 — Catalyst book · <span style={CHIP_MUTED}>paper</span>
            </div>
            <div style={{ fontSize: 22, fontWeight: 800, fontFamily: "var(--font-mono)", color: perfColor(sinceIncept) }}>
              {fmtPct(sinceIncept, 2)}
            </div>
            <div style={{ fontSize: 9, color: "var(--text-light)", fontFamily: "var(--font-mono)" }}>
              since {marks[0]?.date || "—"} · {days}d
            </div>
          </div>
          <Sparkline marks={marks} />
          <div style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--text-light)", textAlign: "right" }}>
            <div>NAV {typeof lastMark.nav === "number" ? lastMark.nav.toFixed(2) : "—"} · {open.length} held · {pending.length} resting · {resolved.length} resolved{resolved.length ? ` · win ${Math.round((wins / resolved.length) * 100)}%` : ""}</div>
            <div style={{ marginTop: 4 }}>
              debated {latest?.asof || "—"} · book stamped {B13.generated} · marked through {B13.marked_through || "—"}
            </div>
            <div style={{ fontSize: 8, marginTop: 4 }}>live-forward, not back-filled · equal-scrutiny paper sleeve</div>
          </div>
        </div>
      </div>

      {/* ── NAV chart ── */}
      <div style={CARD}>
        <div style={CARD_TITLE}><Activity size={13} /> Track record</div>
        <NavChart marks={marks} />
      </div>

      {/* ── held seats ── */}
      <div style={CARD}>
        <div style={CARD_TITLE}><Scale size={13} /> The basket — {open.length} seats{pending.length ? ` + ${pending.length} resting limits` : ""}</div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead><tr>
              <th style={TH}></th><th style={TH}>Symbol</th><th style={TH}>Driver</th>
              <th style={TH}>Entry</th><th style={{ ...TH, textAlign: "right" }}>Entry px</th>
              <th style={{ ...TH, textAlign: "right" }}>Live</th><th style={{ ...TH, textAlign: "right" }}>Return</th>
              <th style={{ ...TH, textAlign: "right" }}>Wt</th><th style={TH}>Milestone</th><th style={TH}>Status</th>
            </tr></thead>
            <tbody>
              {[...open, ...pending].map((e) => {
                const ret = liveRet(e);
                const a = assessBySym[e.symbol];
                const due = e.resolution_due;
                const refuted = due && /REFUTED/i.test(due.reason || "");
                const isOpen = expanded === e.symbol;
                const doss = dossiers[e.symbol];
                return (
                  <FragmentRow key={e.symbol}>
                    <tr onClick={() => setExpanded(isOpen ? null : e.symbol)} style={{ cursor: "pointer" }}>
                      <td style={{ ...TD, width: 18, color: "var(--text-light)" }}>{isOpen ? <ChevronDown size={11} /> : <ChevronRight size={11} />}</td>
                      <td style={TD}>
                        <Link href={`/stock/${encodeURIComponent(e.symbol)}?tab=debate`} onClick={(ev) => ev.stopPropagation()}
                          style={{ fontWeight: 700, color: "var(--text)", textDecoration: "none" }}>{e.symbol}</Link>
                      </td>
                      <td style={{ ...TD, fontSize: 9.5, color: "var(--text-light)", maxWidth: 150, overflow: "hidden", textOverflow: "ellipsis" }}>{e.resolution_driver || "—"}</td>
                      <td style={{ ...TD, color: "var(--text-light)" }}>{dShort(e.entry_date || e.order_date)}</td>
                      <td style={{ ...TD, textAlign: "right" }}>{e.status === "PENDING_LIMIT" ? `lim ${fmtPx(e.limit_price)}` : fmtPx(e.entry_price)}</td>
                      <td style={{ ...TD, textAlign: "right" }}>{fmtPx(livePx(e.symbol))}</td>
                      <td style={{ ...TD, textAlign: "right", color: perfColor(ret), fontWeight: 700 }}>{e.status === "PENDING_LIMIT" ? "–.––" : fmtPct(ret)}</td>
                      <td style={{ ...TD, textAlign: "right" }}>{e.weight_pct != null ? `${e.weight_pct}%` : "—"}</td>
                      <td style={{ ...TD, color: "var(--text-light)" }}>{e.dated_milestone || "—"}</td>
                      <td style={TD}>
                        <span style={{ display: "inline-flex", gap: 4 }}>
                          {e.status === "PENDING_LIMIT" && <span style={CHIP_MUTED}>RESTING</span>}
                          {refuted && <span style={CHIP_RED} title={due.reason}>REFUTED — REVIEW</span>}
                          {due && !refuted && <span style={CHIP_AMBER} title={due.reason}>REVIEW DUE</span>}
                          {a && a.would_seat === false && !due && (
                            <span style={CHIP_AMBER} title={a.binding_reason}>DIR PASS</span>)}
                          {a && a.would_seat === true && <span style={CHIP_GREEN} title={a.binding_reason}>DIR BACKS</span>}
                          {!a && !due && <span style={CHIP_MUTED}>HELD</span>}
                        </span>
                      </td>
                    </tr>
                    {isOpen && (
                      <tr><td colSpan={10} style={{ ...TD, whiteSpace: "normal", background: "var(--bg)", fontFamily: "var(--font-sans)", fontSize: 11, lineHeight: 1.55, padding: "10px 14px" }}>
                        {due && <div style={{ color: refuted ? "var(--red)" : "var(--amber)", fontWeight: 600, marginBottom: 6 }}>Resolution radar ({due.date}): {due.reason}</div>}
                        {a && <div style={{ marginBottom: 6 }}><strong>Director {latest?.asof}:</strong> {a.would_seat ? "would seat" : "would NOT seat"} · conviction {a.conviction} · {a.catalyst_status} — {a.binding_reason}</div>}
                        {doss && <div style={{ marginBottom: 6 }}><strong>Re-underwritten {doss.asof || ""}:</strong> {doss.thesis_summary || ""}{doss.kill_risk ? <span style={{ color: "var(--red)" }}> · kill risk: {typeof doss.kill_risk === "string" ? doss.kill_risk : JSON.stringify(doss.kill_risk)}</span> : null}</div>}
                        {e.entry_rationale && <div style={{ marginBottom: 6 }}><strong>Entry rationale ({dShort(e.order_date)}):</strong> {e.entry_rationale}</div>}
                        {e.invalidation && <div style={{ marginBottom: 6 }}><strong>Invalidation:</strong> {e.invalidation}</div>}
                        {e.review_trigger && <div><strong>Review trigger:</strong> {e.review_trigger}</div>}
                        <div style={{ marginTop: 6, fontSize: 9, color: "var(--text-light)" }}>
                          floor {fmtPx(e.downside_floor)} · target {fmtPx(e.fair_value_target)} · expected {fmtPct(e.expected_return_pct)} · CRO {e.cro_verdict || "—"} · full debate on the <Link href={`/stock/${encodeURIComponent(e.symbol)}?tab=debate`} style={{ color: "var(--green)" }}>stock page →</Link>
                        </div>
                      </td></tr>
                    )}
                  </FragmentRow>
                );
              })}
            </tbody>
          </table>
        </div>
        <div style={{ fontSize: 8.5, color: "var(--text-light)", marginTop: 8 }}>
          Seats resolve on their event — they do not rebalance. Chips: the resolution radar flags a seat (never sells it); exits are stamped by hand on primary sources.
        </div>
      </div>

      {/* ── director memo + decision history (searchable) ── */}
      <div style={CARD}>
        <div style={CARD_TITLE}><FileText size={13} /> Director — memo & decisions</div>
        {latest?.memo && (
          <div style={{ marginBottom: 12 }}>
            <div style={{ fontSize: 9, color: "var(--text-light)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 4 }}>
              Latest debate · {latest.asof} · {latest.regime || ""} {latest.risk_stance ? `· ${latest.risk_stance}` : ""}
            </div>
            <pre style={{ whiteSpace: "pre-wrap", fontSize: 11, fontFamily: "var(--font-mono)", lineHeight: 1.5, margin: 0, background: "var(--bg)", border: "1px solid var(--border-subtle)", borderRadius: 8, padding: "10px 12px" }}>{latest.memo}</pre>
          </div>
        )}
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 8 }}>
          <Search size={12} style={{ color: "var(--text-light)" }} />
          <input value={memoQuery} onChange={(e) => setMemoQuery(e.target.value)}
            placeholder="search decisions & memos (symbol, reason, status…)"
            style={{ flex: 1, maxWidth: 380, background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, color: "var(--text)", fontSize: 11, fontFamily: "var(--font-mono)", padding: "5px 8px", outline: "none" }} />
        </div>
        {latest && (
          <div style={{ overflowX: "auto", marginBottom: 10 }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead><tr>
                <th style={TH}>Symbol</th><th style={TH}>Decision</th><th style={{ ...TH, textAlign: "right" }}>Conv</th>
                <th style={TH}>Status</th><th style={TH}>Binding reason</th>
              </tr></thead>
              <tbody>
                {assessRows.map((a: any) => (
                  <tr key={a.symbol}>
                    <td style={TD}><Link href={`/stock/${encodeURIComponent(a.symbol)}?tab=debate`} style={{ color: "var(--text)", fontWeight: 700, textDecoration: "none" }}>{a.symbol}</Link></td>
                    <td style={TD}><span style={a.would_seat ? CHIP_GREEN : CHIP_MUTED}>{a.would_seat ? "SEAT" : "PASS"}</span></td>
                    <td style={{ ...TD, textAlign: "right" }}>{a.conviction ?? "—"}</td>
                    <td style={{ ...TD, fontSize: 9.5 }}>{a.catalyst_status || "—"}</td>
                    <td style={{ ...TD, whiteSpace: "normal", fontFamily: "var(--font-sans)", fontSize: 10.5, lineHeight: 1.45, color: "var(--text-light)", minWidth: 280 }}>{a.binding_reason || "—"}</td>
                  </tr>
                ))}
                {!assessRows.length && <tr><td colSpan={5} style={{ ...TD, color: "var(--text-light)" }}>no decisions match “{memoQuery}”</td></tr>}
              </tbody>
            </table>
          </div>
        )}
        <div style={{ fontSize: 9, color: "var(--text-light)", textTransform: "uppercase", letterSpacing: "0.08em", margin: "10px 0 4px" }}>Run history — {runRows.length} shown</div>
        {runRows.map((r: any, i: number) => (
          <details key={`${r.run_date}-${i}`} style={{ marginBottom: 6 }}>
            <summary style={{ fontSize: 11, fontFamily: "var(--font-mono)", cursor: "pointer", color: "var(--text)" }}>
              {r.run_date || "run"} {r.stamped_at ? `· stamped ${r.stamped_at}` : ""}{r.added?.length ? ` · +${r.added.length}` : ""}{r.passed?.length ? ` · ${r.passed.length} passed` : ""}
            </summary>
            <pre style={{ whiteSpace: "pre-wrap", fontSize: 10.5, fontFamily: "var(--font-mono)", lineHeight: 1.5, background: "var(--bg)", border: "1px solid var(--border-subtle)", borderRadius: 8, padding: "8px 10px", marginTop: 4 }}>{r.memo || "(no memo recorded on this run)"}</pre>
          </details>
        ))}
      </div>

      {/* ── resolutions ledger ── */}
      {resolved.length > 0 && (
        <div style={CARD}>
          <div style={CARD_TITLE}><Clock size={13} /> Resolutions — {resolved.length} closed, win {resolved.length ? Math.round((wins / resolved.length) * 100) : 0}%</div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead><tr>
                <th style={TH}>Symbol</th><th style={TH}>Type</th><th style={TH}>Resolved</th>
                <th style={{ ...TH, textAlign: "right" }}>Entry→Exit</th>
                <th style={{ ...TH, textAlign: "right" }}>Realized</th>
                <th style={{ ...TH, textAlign: "right" }}>Expected</th>
                <th style={{ ...TH, textAlign: "right" }}>Days</th>
                <th style={TH}>After the exit</th>
              </tr></thead>
              <tbody>
                {[...resolved].sort((a, b) => String(b.resolution?.resolution_date || b.resolution?.date || "").localeCompare(String(a.resolution?.resolution_date || a.resolution?.date || ""))).map((e) => {
                  const r = e.resolution || {};
                  // realized_return_pct is stored as a FRACTION in the tracker (0.0533 = +5.33%)
                  const realized = typeof r.realized_return_pct === "number" ? r.realized_return_pct * 100 : null;
                  const pt = (e.post_track || [])[Math.max(0, (e.post_track || []).length - 1)];
                  return (
                    <tr key={e.symbol}>
                      <td style={TD}><Link href={`/stock/${encodeURIComponent(e.symbol)}?tab=debate`} style={{ color: "var(--text)", fontWeight: 700, textDecoration: "none" }}>{e.symbol}</Link></td>
                      <td style={TD}><span style={(realized ?? 0) > 0 ? CHIP_GREEN : CHIP_RED}>{r.resolution_type || r.type || "—"}</span></td>
                      <td style={{ ...TD, color: "var(--text-light)" }}>{dShort(r.resolution_date || r.date)}</td>
                      <td style={{ ...TD, textAlign: "right", color: "var(--text-light)" }}>{fmtPx(e.entry_price)}→{fmtPx(r.exit_price)}</td>
                      <td style={{ ...TD, textAlign: "right", fontWeight: 700, color: perfColor(realized) }}>{fmtPct(realized)}</td>
                      <td style={{ ...TD, textAlign: "right", color: "var(--text-light)" }}>{fmtPct(e.expected_return_pct)}</td>
                      <td style={{ ...TD, textAlign: "right", color: "var(--text-light)" }}>{r.days_held ?? "—"}</td>
                      <td style={TD}>
                        {e.post_track_status ? (
                          <span style={e.post_track_status === "ROUND_TRIP" ? CHIP_GREEN : e.post_track_status === "RERATE_COMPLETED" ? CHIP_RED : CHIP_MUTED}
                            title={pt ? `since exit ${fmtPct(pt.since_exit_pct)} (${pt.date})` : ""}>
                            {e.post_track_status === "RERATE_COMPLETED" ? "FINISHED WITHOUT US" : e.post_track_status === "ROUND_TRIP" ? "ROUND-TRIPPED" : e.post_track_status === "WINDOW_CLOSED" ? "WINDOW CLOSED" : `TRACKING ${pt ? fmtPct(pt.since_exit_pct) : ""}`}
                          </span>
                        ) : <span style={CHIP_MUTED}>—</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div style={{ fontSize: 8.5, color: "var(--text-light)", marginTop: 8 }}>
            “After the exit” grades the exit itself for 90 days: green = the tape round-tripped (right to leave), red = the re-rate finished without us (left too early).
          </div>
        </div>
      )}

      {/* ── counterfactual scoreboard ── */}
      <div style={CARD}>
        <div style={CARD_TITLE}><SkipForward size={13} /> Debated & passed — the counterfactual scoreboard</div>
        <div style={{ fontSize: 10.5, color: "var(--text-light)", marginBottom: 10, lineHeight: 1.5 }}>
          Every pass is priced at pass time and graded daily against SPY. <span style={{ color: "var(--green)" }}>Green alpha = the pass lagged the market (right to pass)</span>; <span style={{ color: "var(--red)" }}>red = it beat the market (a miss)</span>.
          {passes.length ? <> {goodPasses} of {passes.length} graded passes were right · median alpha {typeof medianAlpha === "number" ? `${medianAlpha >= 0 ? "+" : ""}${medianAlpha.toFixed(1)}pp` : "—"}.</> : null}
        </div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead><tr>
              <th style={TH}>Symbol</th><th style={TH}>Passed</th>
              <th style={{ ...TH, textAlign: "right" }}>Since</th>
              <th style={{ ...TH, textAlign: "right" }}>SPY</th>
              <th style={{ ...TH, textAlign: "right" }}>Alpha</th>
              <th style={TH}>Why we passed</th>
            </tr></thead>
            <tbody>
              {(showAllPasses ? passesSorted : passesSorted.slice(0, 15)).map((n, i) => (
                <tr key={`${n.symbol}-${n.date}-${i}`}>
                  <td style={TD}><Link href={`/stock/${encodeURIComponent(n.symbol)}`} style={{ color: "var(--text)", fontWeight: 700, textDecoration: "none" }}>{n.symbol}</Link>{n.source === "weekly_director" && <span style={{ ...CHIP_MUTED, marginLeft: 5 }}>this week</span>}</td>
                  <td style={{ ...TD, color: "var(--text-light)" }}>{dShort(n.date)}{n.backfilled ? "*" : ""}</td>
                  <td style={{ ...TD, textAlign: "right", color: perfColor(n.since_pass_pct) }}>{fmtPct(n.since_pass_pct)}</td>
                  <td style={{ ...TD, textAlign: "right", color: "var(--text-light)" }}>{fmtPct(n.spy_since_pass_pct)}</td>
                  <td style={{ ...TD, textAlign: "right", fontWeight: 700, color: n.alpha_pp > 0 ? "var(--red)" : "var(--green)" }}>{`${n.alpha_pp >= 0 ? "+" : ""}${n.alpha_pp.toFixed(1)}pp`}</td>
                  <td style={{ ...TD, whiteSpace: "normal", fontFamily: "var(--font-sans)", fontSize: 10.5, lineHeight: 1.45, color: "var(--text-light)", minWidth: 260 }}>{n.passed_because || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {passesSorted.length > 15 && (
          <button onClick={() => setShowAllPasses(!showAllPasses)}
            style={{ marginTop: 8, background: "none", border: "1px solid var(--border)", borderRadius: 6, color: "var(--text-light)", fontSize: 10, fontFamily: "var(--font-mono)", padding: "4px 10px", cursor: "pointer" }}>
            {showAllPasses ? "show fewer" : `show all ${passesSorted.length} passes`}
          </button>
        )}
        <div style={{ fontSize: 8.5, color: "var(--text-light)", marginTop: 8 }}>
          * priced retroactively from the pass-day close (backfilled 2026-07-28); passes from today forward are priced live at decision time.
        </div>

        {/* on-deck: conditional passes still tracked (compact — the old watchlist cards are retired) */}
        {(B13.watchlist || []).length > 0 && (
          <div style={{ marginTop: 14, borderTop: "1px solid var(--border-subtle)", paddingTop: 10 }}>
            <div style={{ fontSize: 9, color: "var(--text-light)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6 }}>
              On deck — conditional passes ({(B13.watchlist || []).length}, cohort NAV {(B13.watchlist_marks || []).slice(-1)[0]?.nav ?? "—"})
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {(B13.watchlist || []).map((w: any) => {
                const px = livePx(w.symbol);
                const ret = px && w.entry_price ? (px / w.entry_price - 1) * 100 : null;
                return (
                  <span key={w.symbol} style={{ ...CHIP_MUTED, fontSize: 10, padding: "3px 8px" }}
                    title={`${w.blocked_by || ""} — would enter if: ${w.would_enter_if || "?"}`}>
                    {w.symbol} <span style={{ color: perfColor(ret) }}>{fmtPct(ret)}</span>
                  </span>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* ── footer ── */}
      <div style={{ fontSize: 8.5, color: "var(--text-light)", lineHeight: 1.6 }}>
        Paper sleeve — no orders are placed; entries are stamped at CRO-verified live prices, resting limits never get fiction fills.
        Caps: ≤{B13.caps?.max_per_driver}/driver (FDA drivers exempt) · ≤{B13.caps?.max_super_pct}% per super-cluster · ≤{B13.caps?.max_names} names.
        Per-name depth (bull/bear, skeptic, valuation) lives on each stock page&apos;s Speculair Debate tab — same debate, same week.
      </div>
    </div>
  );
}

// React needs keyed fragments for the expandable two-row pattern
function FragmentRow({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
