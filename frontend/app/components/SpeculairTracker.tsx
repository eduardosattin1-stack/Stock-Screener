"use client";
import React, { useState, useEffect } from "react";
import { ChevronRight, RefreshCw } from "lucide-react";
import Link from "next/link";

interface Pick {
  symbol: string;
  // Apex: 0-100 Director conviction. Recovery sleeve: the 1-5 interrogator score.
  conviction: number;
  // Value Lens scores its own seats 0-100 and carries no regime conviction.
  value_score?: number;
  entry_price?: number;
  entry_date?: string;
  source_methodologies?: string[];
  // Debt-cycle badge fields (2026-07-27): deterministic payback-speed label +
  // whether the phase duration cap trimmed this seat's weight.
  duration_bucket?: string;
  duration_bucket_source?: string;
  cycle_capped?: boolean;
  cycle_cap_note?: string;
  cycle_cap_effect?: string;   // "advisory" (equal-weight book) | "live"
  phase_fit?: string;
}

type Quote = { price: number; changesPercentage: number };

// ── Terminal Ledger Rail — shared module grammar (see Watchlist.tsx) ─────────
const GRID = "minmax(0, 1fr) 52px 52px 52px 20px";
const fmtPrice = (p: number | null | undefined) => (p == null ? null : p >= 10000 ? `${(p / 1000).toFixed(1)}k` : p.toFixed(2));
const fmtPct = (pct: number | null | undefined) => (pct == null ? null : `${pct > 0 ? "+" : ""}${Math.abs(pct) >= 100 ? pct.toFixed(0) : pct.toFixed(1)}%`);
const PENDING = <span style={{ color: "var(--text-light)" }}>–.––</span>;

// Compact live tracker for the three live Speculair books — Apex, Value Lens and
// the (paper) Recovery sleeve. Designed to sit underneath the Watchlist inside the
// shared right rail. Each book gets the same two elements: a NAV stat card (its own
// chained track record) and a collapsible seat ledger.
export function SpeculairTracker() {
  const [baskets, setBaskets] = useState<any>(null);
  const [quotes, setQuotes] = useState<Record<string, Quote>>({});
  const [loading, setLoading] = useState(false);
  const [openApex, setOpenApex] = useState(true);
  const [openValue, setOpenValue] = useState(true);
  const [openRecovery, setOpenRecovery] = useState(false);
  const [trackingEqual, setTrackingEqual] = useState<any>(null);
  const [trackingWeighted, setTrackingWeighted] = useState<any>(null);
  const [valueApex, setValueApex] = useState<any>(null);
  const [recoverySleeve, setRecoverySleeve] = useState<any>(null);
  const [recoveryTracking, setRecoveryTracking] = useState<any>(null);

  // GCS first, public-file fallback (mirrors page.tsx) — the public copy is frozen
  // at the last frontend deploy, so it is a fallback only, never the primary read.
  const loadGcsFirst = (name: string, set: (d: any) => void, ok: (d: any) => boolean = Boolean) => {
    fetch(`/api/gcs/scans/${name}`)
      .then((r) => { if (r.ok) return r.json(); throw new Error("gcs"); })
      .then((d) => { if (d && ok(d)) set(d); else throw new Error("empty"); })
      .catch(() => {
        fetch(`/${name}`)
          .then((r) => (r.ok ? r.json() : null))
          .then((d) => { if (d && ok(d)) set(d); })
          .catch(() => {});
      });
  };

  useEffect(() => {
    loadGcsFirst("speculair_baskets.json", setBaskets);
    loadGcsFirst("speculair_value_apex.json", setValueApex);
    loadGcsFirst("speculair_recovery_sleeve.json", setRecoverySleeve);
    loadGcsFirst("speculair_recovery_tracking.json", setRecoveryTracking, (d) => !!d.nav);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Load Apex track record (chained NAV + closed rotations): GCS first, public fallback.
  // Two chains: equal-weight (original) and Director-weighted-by-conviction (promoted
  // once it has genuine live-forward history) — same promotion rule as the Apex Basket
  // card on / (page.tsx) and the Daily Briefing headline, so this "Apex since ..." figure
  // always matches those instead of quietly reporting a different chain.
  useEffect(() => {
    loadGcsFirst("speculair_apex_tracking.json", setTrackingEqual, (d) => !!d.nav);
    loadGcsFirst("speculair_apex_tracking_weighted.json", setTrackingWeighted, (d) => !!d.nav);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const trackingIsWeighted = !!(trackingWeighted && (trackingWeighted.history || []).length >= 4);
  const tracking = trackingIsWeighted ? trackingWeighted : trackingEqual;

  // Value Lens rides the same weighted-vs-equal promotion rule as the apex, so the
  // "Value Lens since ..." figure here matches the Daily Briefing's live-tracking row.
  const vtWeighted = valueApex?.value_tracking_weighted;
  const valueIsWeighted = !!(vtWeighted && (vtWeighted.history || []).length >= 4);
  const valueTracking = valueIsWeighted ? vtWeighted : valueApex?.value_tracking;
  // Recovery sleeve has one (equal-weight) chain; the standalone tracking file carries
  // the entry prices, the sleeve file the seat list. Either can stand in for the other's
  // NAV block so a single missing file doesn't blank the card.
  const recTracking = recoveryTracking || recoverySleeve?.tracking;

  const apex: Pick[] = baskets?.apex_basket || [];
  const value: Pick[] = valueApex?.apex_basket || [];
  const recovery: Pick[] = recoverySleeve?.sleeve || [];
  // Recovery picks carry no entry price of their own — the tracker's positions map does.
  const recPositions: Record<string, any> = recoveryTracking?.positions || {};
  const symbolsKey = Array.from(new Set([...apex, ...value, ...recovery].map((p) => p.symbol))).join(",");

  const fetchQuotes = async () => {
    if (!symbolsKey) return;
    setLoading(true);
    try {
      // batch-quote (not quote) — FMP's quote endpoint is single-symbol; a comma list returns []
      const res = await fetch(`/api/fmp?e=batch-quote&symbols=${encodeURIComponent(symbolsKey)}`);
      const data = await res.json();
      if (Array.isArray(data)) {
        const m: Record<string, Quote> = {};
        data.forEach((q: any) => { m[q.symbol] = { price: q.price, changesPercentage: q.changesPercentage ?? q.changePercentage }; });
        setQuotes((prev) => ({ ...prev, ...m }));
      }
    } catch (e) {
      console.error("SpeculairTracker fetch error:", e);
    }
    setLoading(false);
  };

  useEffect(() => {
    if (!symbolsKey) return;
    fetchQuotes();
    const id = setInterval(fetchQuotes, 30000); // 30s, matches Watchlist cadence
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbolsKey]);

  if (!baskets) return null;

  // Conviction chip — number only, theme vars (no hardcoded rgba/#hex). Two scales:
  // the apex/value books score 0-100, the recovery sleeve carries the interrogator's
  // 1-5 score. Rendering a "3" on the 0-100 ramp would read as near-zero conviction,
  // so the five-point scale prints as "3/5" and gets its own thresholds.
  const convStyle = (c: number, scale: "pct" | "five" = "pct") => {
    const hi = scale === "five" ? c >= 4 : c >= 85;
    const mid = scale === "five" ? c >= 3 : c >= 70;
    return {
      fontSize: 9, padding: "1px 4px", borderRadius: 3, fontFamily: "var(--font-mono)", fontWeight: 700, flexShrink: 0,
      background: hi ? "var(--green-light)" : mid ? "var(--amber-light)" : "var(--bg-elevated)",
      color: hi ? "var(--green)" : mid ? "var(--amber)" : "var(--text-light)",
    };
  };

  const fmtDay = (s?: string) => (s ? new Date(s + "T00:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "");

  // Entry price per book. Apex and Value publish it on the pick; the recovery sleeve
  // publishes only the seat (its entry lives in the tracker's positions map), so it
  // reads the tracker first and falls back to the pick if that file is missing.
  const apexEntry = (p: Pick) => p.entry_price || 0;
  const recEntry = (p: Pick) => Number(recPositions[p.symbol]?.entry_price) || p.entry_price || 0;

  // Live P&L% vs entry for one pick (null when either side is missing).
  const livePnl = (p: Pick, entryOf: (p: Pick) => number): number | null => {
    const q = quotes[p.symbol];
    const e = entryOf(p);
    return q?.price != null && e > 0 ? ((q.price / e) - 1) * 100 : null;
  };
  // Collapsed-section aggregate: mean live P&L across rows with data.
  const meanPnl = (rows: Pick[], entryOf: (p: Pick) => number): number | null => {
    const vals = rows.map((p) => livePnl(p, entryOf)).filter((v): v is number => v != null);
    return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
  };

  // NAV sparkline — scale always includes the base (100) so the dashed baseline
  // and above/below-water area fill read at a glance.
  const Sparkline = ({ navs, color }: { navs: number[]; color: string }) => {
    if (!navs || navs.length < 2) return null;
    const w = 88, h = 28, pad = 3;
    const min = Math.min(...navs, 100), max = Math.max(...navs, 100), range = max - min || 1;
    const xy = (v: number, i: number): [number, number] => [
      pad + (i / (navs.length - 1)) * (w - 2 * pad),
      pad + (1 - (v - min) / range) * (h - 2 * pad),
    ];
    const pts = navs.map((v, i) => xy(v, i).map((n) => n.toFixed(1)).join(",")).join(" ");
    const [lx, ly] = xy(navs[navs.length - 1], navs.length - 1);
    const baseY = pad + (1 - (100 - min) / range) * (h - 2 * pad);
    const area = `${pts} ${(w - pad).toFixed(1)},${(h - pad).toFixed(1)} ${pad.toFixed(1)},${(h - pad).toFixed(1)}`;
    const up = navs[navs.length - 1] >= 100;
    return (
      <svg width={w} height={h} style={{ display: "block", flexShrink: 0 }} aria-hidden="true">
        <polygon points={area} fill={up ? "var(--green-light)" : "var(--red-light)"} stroke="none" />
        <line x1={pad} y1={baseY} x2={w - pad} y2={baseY} stroke="var(--border)" strokeDasharray="2 3" strokeWidth={1} />
        <polyline points={pts} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
        <circle cx={lx} cy={ly} r={2} fill={color} />
      </svg>
    );
  };

  // NAV stat card — one per book, the rail's hero element. Same shape for all three
  // (chained paper NAV, base 100), so Apex / Value Lens / Recovery read on one ruler.
  const NavCard = ({ label, trk, note }: { label: string; trk: any; note?: string }) => {
    const n: number | null = trk?.nav ?? null;
    if (n == null) return null;
    const since = n - 100;
    const c = since > 0 ? "var(--green)" : since < 0 ? "var(--red)" : "var(--text-light)";
    const rotated: any[] = trk?.closed || [];
    // The value book's chain is embedded in speculair_value_apex.json and carries no
    // last_date of its own — fall back to the last NAV point so its card shows the
    // same "· Nd" age as the apex instead of silently dropping it.
    const hist: any[] = trk?.history || [];
    const lastDate = trk?.last_date || hist[hist.length - 1]?.date || null;
    const days = trk?.inception_date && lastDate
      ? Math.max(0, Math.round((new Date(lastDate + "T00:00:00").getTime() - new Date(trk.inception_date + "T00:00:00").getTime()) / 86400000))
      : null;
    return (
      <div style={{ margin: "8px 12px", padding: "8px 10px", background: "var(--bg)", border: "1px solid var(--border-subtle)", borderRadius: 6, display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 9, fontFamily: "var(--font-mono)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-light)" }}>
            {label} · since {fmtDay(trk.inception_date)}{days != null ? ` · ${days}d` : ""}
          </div>
          <div style={{ fontSize: 22, fontWeight: 800, fontFamily: "var(--font-mono)", letterSpacing: "-0.02em", fontVariantNumeric: "tabular-nums", color: c }}>
            {since > 0 ? "+" : ""}{since.toFixed(1)}%
          </div>
          <div style={{ fontSize: 9, fontFamily: "var(--font-mono)", color: "var(--text-light)", marginTop: 2 }}>
            NAV {n.toFixed(1)}{rotated.length ? ` · ${rotated.length} rotated` : ""}{note ? ` · ${note}` : ""}
          </div>
        </div>
        <Sparkline navs={hist.map((h: any) => h.nav)} color={c} />
      </div>
    );
  };

  // Column sub-header — repeated per book so the four numeric columns are labelled
  // wherever the eye lands in a three-book rail.
  const ColHeader = () => (
    <div style={{ display: "grid", gridTemplateColumns: GRID, gap: 6, height: 20, alignItems: "center", padding: "0 12px", background: "var(--bg)", fontSize: 9, fontWeight: 600, color: "var(--text-light)", textTransform: "uppercase", letterSpacing: "0.08em", borderBottom: "1px solid var(--border-subtle)", fontFamily: "var(--font-mono)" }}>
      <div>Symbol</div>
      <div style={{ textAlign: "right" }}>Entry</div>
      <div style={{ textAlign: "right" }}>Last</div>
      <div style={{ textAlign: "right" }}>P&amp;L</div>
      <div></div>
    </div>
  );

  // Shared data row (all three books): SYMBOL / ENTRY / LAST / P&L / gutter.
  const Row = ({ p, entryOf, score, scale = "pct" }: { p: Pick; entryOf: (p: Pick) => number; score: (p: Pick) => number | null; scale?: "pct" | "five" }) => {
    const q = quotes[p.symbol];
    const last = q?.price;
    const entry = entryOf(p);
    const perf = livePnl(p, entryOf);
    const sc = score(p);
    const color = perf == null ? "var(--text-light)" : perf > 0 ? "var(--green)" : perf < 0 ? "var(--red)" : "var(--text-light)";
    return (
      <div style={{ display: "grid", gridTemplateColumns: GRID, gap: 6, height: 28, alignItems: "center", padding: "0 12px", borderBottom: "1px solid var(--border-subtle)", fontSize: 11, fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums", transition: "background 0.1s" }}
           onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-hover)")} onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
        <div style={{ display: "flex", alignItems: "center", gap: 5, minWidth: 0 }}>
          <Link href={`/stock/${p.symbol}`} style={{ textDecoration: "none", color: "var(--text)", fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.symbol}</Link>
          {sc != null && <span style={convStyle(sc, scale)}>{scale === "five" ? `${sc}/5` : sc}</span>}
          {/* Payback-speed badge (debt-cycle layer): C = cash_now (FCF yield ≥4%),
              P = payback 2-3y, S = story (no FCF yet — capped hardest in DISCIPLINE/FORCING).
              Ring turns red + ✂ when the phase duration cap trimmed this seat. */}
          {p.duration_bucket && p.duration_bucket !== "unknown" && (() => {
            const b = p.duration_bucket;
            const letter = b === "cash_now" ? "C" : b === "payback_2_3y" ? "P" : "S";
            const bc = b === "cash_now" ? "var(--green)" : b === "payback_2_3y" ? "var(--amber)" : "var(--red)";
            // The book publishes EQUAL WEIGHT, so a cycle "trim" is an audit-trail event,
            // not a weight change. Only show ✂ (and the red ring) when the cap is LIVE;
            // when advisory, say so in the tooltip and leave the chip visually neutral —
            // a scissors icon on a seat whose weight did not move would be a lie.
            const capLive = !!p.cycle_capped && p.cycle_cap_effect !== "advisory";
            const tip = `Payback speed: ${b}${p.duration_bucket_source === "director_override" ? " (director override)" : ""}${p.phase_fit ? ` · Cycle fit: ${p.phase_fit}` : ""}${p.cycle_capped ? ` · ${p.cycle_cap_note || ""}` : ""}${p.cycle_capped && !capLive ? " (book is equal-weight: this seat's published weight is unchanged)" : ""}`;
            return (
              <span title={tip} style={{ fontFamily: "var(--font-mono)", fontSize: 8, fontWeight: 700, minWidth: 12, height: 12, lineHeight: "12px", textAlign: "center", borderRadius: 3, color: bc, background: "color-mix(in srgb, currentColor 12%, transparent)", border: `1px solid ${capLive ? "var(--red)" : `color-mix(in srgb, ${bc} 40%, transparent)`}`, cursor: "help", flexShrink: 0, padding: "0 2px" }}>
                {letter}{capLive ? "✂" : ""}
              </span>
            );
          })()}
        </div>
        <div style={{ textAlign: "right", color: "var(--text-light)" }}>{entry > 0 ? fmtPrice(entry) : PENDING}</div>
        <div style={{ textAlign: "right", color: "var(--text-secondary)" }}>{last != null ? fmtPrice(last) : PENDING}</div>
        <div style={{ textAlign: "right", color, fontWeight: 700 }}>{perf == null ? PENDING : fmtPct(perf)}</div>
        <span />
      </div>
    );
  };

  // Level-2 collapsible section header.
  const SectionHeader = ({ open, onClick, title, count, accent, agg }: { open: boolean; onClick: () => void; title: string; count: number; accent: string; agg?: number | null }) => (
    <button onClick={onClick} style={{ width: "100%", height: 26, display: "flex", alignItems: "center", gap: 6, padding: "0 12px", background: "none", border: "none", borderBottom: "1px solid var(--border-subtle)", cursor: "pointer", textAlign: "left" }}
      onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-hover)")} onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
      <ChevronRight size={12} color="var(--text-light)" style={{ flexShrink: 0, transform: open ? "rotate(90deg)" : "rotate(0deg)", transition: "transform 120ms ease" }} />
      <span style={{ width: 6, height: 6, borderRadius: 2, background: accent, flexShrink: 0 }} />
      <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", fontWeight: 700, color: "var(--text)", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{title}</span>
      <span style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{ fontSize: 10, color: "var(--text-light)", fontFamily: "var(--font-mono)" }}>{count}</span>
        {!open && agg != null && (
          <span style={{ fontSize: 10, fontWeight: 700, fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums", color: agg > 0 ? "var(--green)" : agg < 0 ? "var(--red)" : "var(--text-light)" }}>{fmtPct(agg)}</span>
        )}
      </span>
      <span style={{ width: 20, flexShrink: 0 }} />
    </button>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", fontFamily: "var(--font-sans)" }}>
      {/* Level-1 module band */}
      <div style={{ height: 28, boxSizing: "border-box", display: "flex", alignItems: "center", gap: 8, padding: "0 12px", background: "var(--bg)", borderTop: "1px solid var(--border)", borderBottom: "1px solid var(--border)" }}>
        <span style={{ width: 2, height: 10, borderRadius: 1, background: "var(--green)", flexShrink: 0 }} />
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-secondary)" }}>
          Specul<span style={{ color: "var(--lavender)" }}>AI</span>r
        </span>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-light)" }}>{apex.length + value.length + recovery.length}</span>
        <button onClick={fetchQuotes} title="Refresh"
          style={{ marginLeft: "auto", width: 20, height: 20, display: "flex", alignItems: "center", justifyContent: "center", background: "none", border: "none", cursor: "pointer", borderRadius: 4, color: "var(--text-light)" }}
          onMouseEnter={(e) => { e.currentTarget.style.background = "var(--bg-hover)"; e.currentTarget.style.color = "var(--text)"; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--text-light)"; }}>
          <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {/* ── APEX — the flagship book ── */}
      <NavCard label="Apex" trk={tracking} />
      <ColHeader />
      <SectionHeader open={openApex} onClick={() => setOpenApex(!openApex)} title="Apex Basket" count={apex.length} accent="var(--green)" agg={meanPnl(apex, apexEntry)} />
      {openApex && (apex.length > 0
        ? apex.map((p) => <Row key={p.symbol} p={p} entryOf={apexEntry} score={(x) => x.conviction ?? null} />)
        : <div style={{ padding: "14px 12px", fontSize: 11, color: "var(--text-light)", fontFamily: "var(--font-mono)", lineHeight: 1.5 }}>No Apex positions.</div>)}

      {/* ── VALUE LENS — the same research re-scored on price and balance sheet alone.
             Its chip is the value score (0-100), not the regime book's conviction. ── */}
      <NavCard label="Value Lens" trk={valueTracking} />
      <ColHeader />
      <SectionHeader open={openValue} onClick={() => setOpenValue(!openValue)} title="Value Lens" count={value.length} accent="var(--blue)" agg={meanPnl(value, apexEntry)} />
      {openValue && (value.length > 0
        ? value.map((p) => <Row key={p.symbol} p={p} entryOf={apexEntry} score={(x) => x.value_score ?? null} />)
        : <div style={{ padding: "14px 12px", fontSize: 11, color: "var(--text-light)", fontFamily: "var(--font-mono)", lineHeight: 1.5 }}>No Value Lens seats.</div>)}

      {/* ── RECOVERY SLEEVE — paper only, racing a frozen benchmark for a quarter to
             earn a real allocation. Labelled "paper" on the card so its NAV is never
             mistaken for one of the two live books above. ── */}
      <NavCard label="Recovery" trk={recTracking} note="paper" />
      <ColHeader />
      <SectionHeader open={openRecovery} onClick={() => setOpenRecovery(!openRecovery)} title="Recovery Sleeve" count={recovery.length} accent="var(--lavender)" agg={meanPnl(recovery, recEntry)} />
      {openRecovery && (recovery.length > 0
        ? recovery.map((p) => <Row key={p.symbol} p={p} entryOf={recEntry} score={(x) => x.conviction ?? null} scale="five" />)
        : <div style={{ padding: "14px 12px", fontSize: 11, color: "var(--text-light)", fontFamily: "var(--font-mono)", lineHeight: 1.5 }}>No Recovery seats.</div>)}

      {/* Footer — the weighting note applies to the apex chain (the value book runs the
          same promotion rule independently; the recovery sleeve is always equal-weight). */}
      <div style={{ padding: "6px 12px 8px", fontSize: 9, color: "var(--text-light)", fontFamily: "var(--font-mono)", lineHeight: 1.5 }}>
        Apex {trackingIsWeighted ? "Director-weighted" : "equal-weight"} NAV chain · 30s quotes{baskets.generated_at ? ` · gen ${new Date(baskets.generated_at).toLocaleDateString()}` : ""}
      </div>
    </div>
  );
}
