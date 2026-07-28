"use client";

// BASKET 13 — the catalyst book, in the SAME idiom as the Speculair apex/value books.
//
// 2026-07-28 revamp (Bruno): one Director, one basket, one ledger — and the same look
// and feel as the apex book: a green-bordered book card with a banner strip, the live
// track-record hero, and per-seat CARDS (conviction chip, vitals rows, clamped PM
// rationale with ▾ more). Below the book: the Director's searchable memo & decisions,
// the counterfactual scoreboard, and the resolutions ledger at the bottom.
//
// RETIRED (deliberately, not lost): the Loeb/Bloom deep-scan depth view, the
// candidates sidebar and the standalone watchlist cards. Per-name depth lives on the
// stock page's Speculair Debate tab, which serves the same week's debate.
//
// Data: app/data/basket13.ts (auto-gen by backend/_basket13_export.py) +
// /basket13_dossiers.json (latest re-underwrites) + /api/quotes (60s live poll).

import { useState, useEffect, useMemo } from "react";
import Link from "next/link";
import { Clock, Search, FileText, SkipForward } from "lucide-react";
import { BASKET13 } from "../data/basket13";

const B13: any = BASKET13;

// ---------- helpers (house grammar) ----------
const fmtPx = (v: any) => (typeof v === "number" ? (v >= 10 ? v.toFixed(2) : v.toFixed(3)) : "–.––");
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
const convChip = (c: number) =>
  chip(c >= 85 ? "var(--green-light)" : c >= 70 ? "var(--amber-light)" : "var(--bg-elevated)",
       c >= 85 ? "var(--green)" : c >= 70 ? "var(--amber)" : "var(--text-light)");

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
const VROW: React.CSSProperties = {
  display: "flex", justifyContent: "space-between", gap: 12, fontSize: 11,
  fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums", lineHeight: 1.8,
};
const VLAB: React.CSSProperties = { color: "var(--text-light)" };

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

  // latest re-underwrites (deep-dossier store) — per-seat kill-risk in the expanded card
  const [dossiers, setDossiers] = useState<Record<string, any>>({});
  useEffect(() => {
    fetch("/basket13_dossiers.json")
      .then((r) => (r.ok ? r.json() : null))
      .then((j) => { if (j?.dossiers) setDossiers(j.dossiers); })
      .catch(() => {});
  }, []);

  const [moreSym, setMoreSym] = useState<string | null>(null);
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

  // banner: expected book return ON NAV = sum(weight% x seat EV). Weights are %NAV so cash
  // drag is included — binary biotech EVs are large by design, and printing the honest
  // aggregate against the realized NAV is exactly the calibration this sleeve exists for.
  const bookExp = useMemo(() => {
    const rows = open.filter((e) => typeof e.expected_return_pct === "number" && e.weight_pct);
    return rows.length ? rows.reduce((s, e) => s + (e.weight_pct / 100) * e.expected_return_pct, 0) : null;
  }, [open]);

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

  // banner tokens — risk_stance/regime are PROSE in the director file; show the compact head
  // ("SELECTIVE-DEFENSIVE", "NEUTRAL / GOLDILOCKS / DISCIPLINE") with the full text on hover
  const stanceTok = latest?.risk_stance ? String(latest.risk_stance).trim().split(/\s+/)[0].toUpperCase() : null;
  const regimeTok = latest?.regime
    ? String(latest.regime).split("(")[0].split("/").map((p: string) => p.trim().split(/\s+/)[0].toUpperCase()).filter(Boolean).join(" / ")
    : null;

  // memo/decision search — "find the evidence later": filters the decision table AND the run history
  const q = memoQuery.trim().toLowerCase();
  const hit = (s: any) => !q || String(s || "").toLowerCase().includes(q);
  const assessRows = (latest?.assessments || []).filter(
    (a: any) => hit(a.symbol) || hit(a.binding_reason) || hit(a.posture) || hit(a.catalyst_status));
  const runRows = (B13.runs || []).filter((r: any) => hit(r.memo) || hit(r.run_date)).slice().reverse();

  return (
    <div style={{ maxWidth: 1240, margin: "0 auto", padding: "24px 16px 60px" }}>

      {/* ══ THE BOOK CARD — same grammar as the Speculair Apex Basket ══ */}
      <div style={{ background: "var(--bg-surface)", border: "1px solid var(--green)", borderRadius: 12, padding: "20px 24px", marginBottom: 16 }}>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
          <div style={{ fontSize: 16, fontWeight: 700 }}>Basket 13 — Catalyst Book</div>
          <div style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--text-light)" }}>
            {open.length} seats · resolve-on-event · <span style={CHIP_MUTED}>paper</span>
          </div>
        </div>
        <div style={{ fontSize: 11, color: "var(--text-light)", lineHeight: 1.6, margin: "6px 0 12px" }}>
          The catalyst book: dated-event special situations from the weekly multi-agent catalyst debate (dossier → CRO → skeptic → Director).
          Seats resolve on their event — they do not rebalance. Live-forward NAV, never back-filled.
        </div>

        {/* banner strip (goal-banner idiom) */}
        <div style={{ border: "1px solid var(--border)", background: "var(--bg)", borderRadius: 8, padding: "7px 12px", fontSize: 11, fontFamily: "var(--font-mono)", marginBottom: 12, display: "flex", flexWrap: "wrap", gap: 14 }}>
          <span>⚑ resolve-by-event · milestones within 2026</span>
          {stanceTok && <span title={String(latest.risk_stance)}>stance <strong style={{ color: "var(--amber)" }}>{stanceTok}</strong></span>}
          {regimeTok && <span title={String(latest.regime)}>macro <strong style={{ color: "var(--amber)" }}>{regimeTok}</strong></span>}
          {typeof bookExp === "number" && <span title="sum of weight% x seat EV over the open book — binary EVs are large by design; compare with the realized NAV above">book exp <strong style={{ color: "var(--green)" }}>{fmtPct(bookExp)}</strong> on NAV</span>}
        </div>

        {/* live track record hero */}
        <div style={{ border: "1px solid var(--border)", background: "var(--bg)", borderRadius: 8, padding: "12px 16px", display: "flex", flexWrap: "wrap", alignItems: "center", gap: 18, justifyContent: "space-between", marginBottom: 12 }}>
          <div>
            <div style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: "0.1em", color: "var(--text-light)", marginBottom: 4 }}>Live track record</div>
            <div style={{ fontSize: 20, fontWeight: 800, fontFamily: "var(--font-mono)", color: perfColor(sinceIncept) }}>{fmtPct(sinceIncept, 2)}</div>
            <div style={{ fontSize: 9, color: "var(--text-light)", fontFamily: "var(--font-mono)" }}>since {marks[0]?.date || "—"} · {days}d</div>
          </div>
          <Sparkline marks={marks} />
          <div style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--text-light)", textAlign: "right" }}>
            <div>NAV {typeof lastMark.nav === "number" ? lastMark.nav.toFixed(2) : "—"} · {open.length} held · {pending.length} resting · {resolved.length} resolved{resolved.length ? ` · win ${Math.round((wins / resolved.length) * 100)}%` : ""}</div>
            <div style={{ marginTop: 4 }}>debated {latest?.asof || "—"} · book stamped {B13.generated} · marked through {B13.marked_through || "—"}</div>
            <div style={{ fontSize: 8, marginTop: 4 }}>live-forward, not back-filled · equal-scrutiny paper sleeve</div>
          </div>
        </div>

        {/* NAV chart, tucked like the rotation log */}
        <details style={{ marginBottom: 14 }}>
          <summary style={{ fontSize: 11, fontFamily: "var(--font-mono)", cursor: "pointer", color: "var(--text-light)" }}>
            ▸ NAV chart · {marks.length} marks
          </summary>
          <div style={{ paddingTop: 8 }}><NavChart marks={marks} /></div>
        </details>

        {/* ── seat cards (apex pick-card idiom) ── */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(400px, 1fr))", gap: 14 }}>
          {[...open, ...pending].map((e) => {
            const a = assessBySym[e.symbol];
            const due = e.resolution_due;
            const refuted = due && /REFUTED/i.test(due.reason || "");
            const isPend = e.status === "PENDING_LIMIT";
            const px = livePx(e.symbol);
            const ret = liveRet(e);
            const basis = px || e.entry_price || e.limit_price;
            const tgtUp = typeof e.fair_value_target === "number" && basis ? (e.fair_value_target / basis - 1) * 100 : null;
            const isMore = moreSym === e.symbol;
            const doss = dossiers[e.symbol];
            return (
              <div key={e.symbol} style={{ background: "var(--bg)", border: `1px solid ${refuted ? "var(--red)" : due ? "var(--amber)" : "var(--border)"}`, borderRadius: 10, padding: "14px 16px" }}>
                {/* header row */}
                <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
                  <Link href={`/stock/${encodeURIComponent(e.symbol)}?tab=debate`}
                    style={{ fontSize: 15, fontWeight: 700, fontFamily: "var(--font-mono)", color: "var(--text)", textDecoration: "none" }}>{e.symbol}</Link>
                  {a && typeof a.conviction === "number" && <span style={convChip(a.conviction)}>★ {a.conviction}/100</span>}
                  <span style={CHIP_MUTED}>wt {e.weight_pct != null ? `${e.weight_pct}%` : "—"}</span>
                  {isPend && <span style={CHIP_MUTED}>RESTING lim {fmtPx(e.limit_price)}</span>}
                  {refuted && <span style={CHIP_RED} title={due.reason}>REFUTED — REVIEW</span>}
                  {due && !refuted && <span style={CHIP_AMBER} title={due.reason}>REVIEW DUE</span>}
                  {a && a.would_seat === false && !due && <span style={CHIP_AMBER} title={a.binding_reason}>DIR PASS</span>}
                  {a && a.would_seat === true && <span style={CHIP_GREEN} title={a.binding_reason}>DIR BACKS</span>}
                  <span style={{ marginLeft: "auto", fontSize: 13, fontWeight: 700, fontFamily: "var(--font-mono)", color: perfColor(ret) }}>
                    {isPend ? "–.––" : fmtPct(ret)}
                  </span>
                </div>
                {/* chips row */}
                <div style={{ display: "flex", gap: 4, flexWrap: "wrap", margin: "6px 0 8px" }}>
                  <span style={CHIP_MUTED}>{e.resolution_driver || "—"}</span>
                  {e.lane_canon && <span style={CHIP_MUTED}>{e.lane_canon}</span>}
                  {e.cro_verdict && <span style={chip("var(--bg-elevated)", "var(--lavender)")}>CRO {String(e.cro_verdict).slice(0, 18)}</span>}
                </div>
                {/* vitals */}
                <div style={{ marginBottom: 8 }}>
                  <div style={VROW}><span style={VLAB}>Entry:</span><span>{isPend ? `resting @ ${fmtPx(e.limit_price)}` : `$${fmtPx(e.entry_price)} (${e.entry_date || e.order_date})`}</span></div>
                  <div style={VROW}><span style={VLAB}>Current:</span><span>${fmtPx(px)}</span></div>
                  <div style={VROW}>
                    <span style={VLAB}>target upside / floor:</span>
                    <span>
                      <span style={{ color: "var(--green)", fontWeight: 700 }}>{fmtPct(tgtUp, 0)}</span>
                      {typeof e.downside_floor === "number" && <> · <span style={{ color: "var(--red)", fontWeight: 700 }}>floor ${fmtPx(e.downside_floor)}</span></>}
                    </span>
                  </div>
                  <div style={VROW}>
                    <span style={VLAB}>catalyst:</span>
                    <span title={e.dated_milestone || ""} style={{ maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", textAlign: "right" }}>{e.dated_milestone || "—"}</span>
                  </div>
                </div>
                {/* PM rationale, 6-line clamp with ▾ more (apex idiom) */}
                {(e.entry_rationale || due || a) && (
                  <div style={{ fontSize: 11, lineHeight: 1.55, color: "var(--text)", borderTop: "1px solid var(--border-subtle)", paddingTop: 8 }}>
                    <div style={isMore ? {} : { display: "-webkit-box", WebkitLineClamp: 6, WebkitBoxOrient: "vertical", overflow: "hidden" } as React.CSSProperties}>
                      {due && <div style={{ color: refuted ? "var(--red)" : "var(--amber)", fontWeight: 600, marginBottom: 4 }}>Radar ({due.date}): {due.reason}</div>}
                      <span style={{ color: "var(--text-light)" }}><strong>PM</strong> </span>{e.entry_rationale || "—"}
                      {isMore && (
                        <div style={{ marginTop: 8, color: "var(--text-light)" }}>
                          {a && <div style={{ marginBottom: 5 }}><strong>Director {latest?.asof}:</strong> {a.would_seat ? "would seat" : "would NOT seat"} · conviction {a.conviction} · {a.catalyst_status} — {a.binding_reason}</div>}
                          {doss && <div style={{ marginBottom: 5 }}><strong>Re-underwritten {doss.asof || ""}:</strong> {doss.thesis_summary || ""}{doss.kill_risk ? <span style={{ color: "var(--red)" }}> · kill risk: {typeof doss.kill_risk === "string" ? doss.kill_risk : JSON.stringify(doss.kill_risk)}</span> : null}</div>}
                          {e.invalidation && <div style={{ marginBottom: 5 }}><strong>Invalidation:</strong> {e.invalidation}</div>}
                          {e.review_trigger && <div style={{ marginBottom: 5 }}><strong>Review trigger:</strong> {e.review_trigger}</div>}
                          <div style={{ fontSize: 9 }}>expected {fmtPct(e.expected_return_pct)} · full debate on the <Link href={`/stock/${encodeURIComponent(e.symbol)}?tab=debate`} style={{ color: "var(--green)" }}>stock page →</Link></div>
                        </div>
                      )}
                    </div>
                    <button onClick={() => setMoreSym(isMore ? null : e.symbol)}
                      style={{ background: "none", border: "none", color: "var(--text-light)", fontSize: 10, fontFamily: "var(--font-mono)", cursor: "pointer", padding: "4px 0 0" }}>
                      {isMore ? "▴ less" : "▾ more"}
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
        <div style={{ fontSize: 8.5, color: "var(--text-light)", marginTop: 12 }}>
          Chips: the resolution radar flags a seat (never sells it) — exits are stamped by hand on primary sources. Paper — no orders are placed.
          Caps: ≤{B13.caps?.max_per_driver}/driver (FDA drivers exempt) · ≤{B13.caps?.max_super_pct}% per super-cluster · ≤{B13.caps?.max_names} names.
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

      {/* ── resolutions ledger (bottom, per Bruno) ── */}
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
    </div>
  );
}
