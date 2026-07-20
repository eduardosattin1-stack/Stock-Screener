"use client";

// Per-basket page (/basket/[key]) — one page per Macro-Adaptive Methodology
// basket. Deliberately light: description + live stats + NAV-over-time chart
// (backend nav_history, base-100 on the tracking year, collected nightly since
// 2026-07-20) + per-record holdings table + recent rotations.

import { useState, useEffect, useMemo, useRef } from "react";
import { useParams } from "next/navigation";
import { ArrowLeft, RefreshCw } from "lucide-react";
import { METHODOLOGIES_CONFIG, methShortKey } from "../../methodologiesConfig";

const GCS = "/api/gcs/scans";
// Display fallback only — the true cadence is read from the tracking JSON's
// numeric rebalance_cadence_days stamp (written by backend REBALANCE_CADENCE_DAYS).
const CADENCE_DAYS_FALLBACK = 14;

type NavPt = { date: string; nav: number; ytd: number; rebalanced?: boolean };

const fmtDay = (s?: string) =>
  s ? new Date(s + "T00:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "";
const fmtDayYr = (s?: string) =>
  s ? new Date(s + "T00:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }) : "";
const pct = (v: number | null | undefined, dp = 1) =>
  v == null ? "—" : `${v > 0 ? "+" : ""}${(v * 100).toFixed(dp)}%`;
const perfColor = (v: number | null | undefined) =>
  v == null ? "var(--text-light)" : v > 0 ? "var(--green)" : v < 0 ? "var(--red)" : "var(--text-light)";

// ── NAV-over-time chart: single series (no legend — the title names it), 2px
//    line, subtle area, dashed base-100 reference, amber rebalance ticks,
//    crosshair + tooltip on hover. Recessive grid: baseline + min/max only.
function NavChart({ hist }: { hist: NavPt[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const W = 720, H = 240, padL = 44, padR = 14, padT = 16, padB = 26;

  if (!hist || hist.length < 2) {
    return (
      <div style={{ padding: "28px 16px", textAlign: "center", background: "var(--bg-elevated)", borderRadius: 8, border: "1px solid var(--border)" }}>
        <div style={{ fontSize: 12, color: "var(--text-light)", fontFamily: "var(--font-mono)" }}>
          {hist?.length === 1
            ? `Daily NAV series started ${fmtDayYr(hist[0].date)} — first point ${hist[0].nav.toFixed(1)}. The chart draws itself as nightly scans accumulate.`
            : "Daily NAV series starts with the next nightly scan (2026-07-20) — the chart fills in from there."}
        </div>
      </div>
    );
  }

  const navs = hist.map((h) => h.nav);
  const min = Math.min(...navs, 100), max = Math.max(...navs, 100);
  const range = max - min || 1;
  const x = (i: number) => padL + (i / (hist.length - 1)) * (W - padL - padR);
  const y = (v: number) => padT + (1 - (v - min) / range) * (H - padT - padB);
  const line = navs.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const area = `${line} L${x(hist.length - 1).toFixed(1)},${(H - padB).toFixed(1)} L${padL.toFixed(1)},${(H - padB).toFixed(1)} Z`;
  const baseY = y(100);
  const up = navs[navs.length - 1] >= 100;
  const color = up ? "var(--green)" : "var(--red)";
  const rebIdx = hist.map((h, i) => (h.rebalanced ? i : -1)).filter((i) => i >= 0);

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const r = svgRef.current?.getBoundingClientRect();
    if (!r) return;
    const px = ((e.clientX - r.left) / r.width) * W;
    const i = Math.round(((px - padL) / (W - padL - padR)) * (hist.length - 1));
    setHover(Math.max(0, Math.min(hist.length - 1, i)));
  };
  const h = hover != null ? hist[hover] : null;

  return (
    <div style={{ position: "relative" }}>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        style={{ width: "100%", height: "auto", display: "block", cursor: "crosshair" }}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
        role="img"
        aria-label="Basket NAV over time, base 100"
      >
        <path d={area} fill={up ? "var(--green-light)" : "var(--red-light)"} stroke="none" />
        {/* base-100 reference + min/max gridlines (recessive) */}
        <line x1={padL} y1={baseY} x2={W - padR} y2={baseY} stroke="var(--border)" strokeDasharray="3 4" strokeWidth={1} />
        <text x={padL - 6} y={baseY + 3} textAnchor="end" fontSize={9} fill="var(--text-light)" fontFamily="var(--font-mono)">100</text>
        <text x={padL - 6} y={y(max) + 3} textAnchor="end" fontSize={9} fill="var(--text-light)" fontFamily="var(--font-mono)">{max.toFixed(1)}</text>
        <text x={padL - 6} y={y(min) + 3} textAnchor="end" fontSize={9} fill="var(--text-light)" fontFamily="var(--font-mono)">{min.toFixed(1)}</text>
        {/* rebalance ticks along the baseline */}
        {rebIdx.map((i) => (
          <line key={i} x1={x(i)} y1={H - padB} x2={x(i)} y2={H - padB - 6} stroke="var(--amber)" strokeWidth={2} />
        ))}
        <path d={line} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        <circle cx={x(hist.length - 1)} cy={y(navs[navs.length - 1])} r={3} fill={color} />
        {/* first/last date labels */}
        <text x={padL} y={H - 8} fontSize={9} fill="var(--text-light)" fontFamily="var(--font-mono)">{fmtDay(hist[0].date)}</text>
        <text x={W - padR} y={H - 8} textAnchor="end" fontSize={9} fill="var(--text-light)" fontFamily="var(--font-mono)">{fmtDay(hist[hist.length - 1].date)}</text>
        {/* crosshair */}
        {hover != null && (
          <g>
            <line x1={x(hover)} y1={padT} x2={x(hover)} y2={H - padB} stroke="var(--text-light)" strokeWidth={1} strokeDasharray="2 3" />
            <circle cx={x(hover)} cy={y(navs[hover])} r={4} fill={color} stroke="var(--bg)" strokeWidth={2} />
          </g>
        )}
      </svg>
      {h && (
        <div
          style={{
            position: "absolute", top: 4, left: hover! < hist.length / 2 ? "auto" : 8, right: hover! < hist.length / 2 ? 8 : "auto",
            background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 10px",
            fontFamily: "var(--font-mono)", fontSize: 11, pointerEvents: "none", zIndex: 5,
          }}
        >
          <div style={{ color: "var(--text-light)", fontSize: 9 }}>{fmtDayYr(h.date)}{h.rebalanced ? " · rebalance" : ""}</div>
          <div>NAV <b>{h.nav.toFixed(2)}</b> <span style={{ color: perfColor(h.ytd) }}>{pct(h.ytd)} YTD</span></div>
        </div>
      )}
    </div>
  );
}

export default function BasketPage() {
  const params = useParams();
  const rawKey = decodeURIComponent(String(params?.key ?? ""));
  const cfg = METHODOLOGIES_CONFIG.find((m: any) => methShortKey(m.path) === rawKey);

  const [tracking, setTracking] = useState<any>(null);
  const [picks, setPicks] = useState<any>(null);
  const [pit, setPit] = useState<any>(null);
  const [quotes, setQuotes] = useState<Record<string, number>>({});
  const [showExits, setShowExits] = useState(false);

  useEffect(() => {
    fetch(`${GCS}/methodology_tracking.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .catch(() => fetch("/methodology_tracking.json").then((r) => (r.ok ? r.json() : null)).catch(() => null))
      .then(setTracking);
    fetch(`${GCS}/methodology_picks.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .catch(() => fetch("/methodology_picks.json").then((r) => (r.ok ? r.json() : null)).catch(() => null))
      .then(setPicks);
    // PIT baseline stats — the config literals are deprecated ("diverged by
    // multiples"); the dashboard corrects them at runtime, this page must too.
    fetch("/baseline_history.json")
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null)
      .then(setPit);
  }, []);

  const track = tracking?.methodologies?.[rawKey];
  const holdings: any[] = track?.current_holdings || [];
  // Tracked book empty (fresh basket / stale fallback file) → show the LIVE
  // screen picks instead, mirroring the dashboard's fallback, clearly labeled.
  const livePicks: any[] = picks?.methodologies?.[rawKey]?.picks || [];
  const usingLivePicks = !holdings.length && livePicks.length > 0;
  const displayHoldings: any[] = holdings.length ? holdings : livePicks;

  useEffect(() => {
    const syms = displayHoldings.map((hh) => hh.symbol).filter(Boolean);
    if (!syms.length) return;
    let cancelled = false;
    const chunks: string[][] = [];
    for (let i = 0; i < syms.length; i += 50) chunks.push(syms.slice(i, i + 50));
    Promise.all(chunks.map((c) =>
      // batch-quote (not quote) — FMP's quote endpoint is single-symbol.
      fetch(`/api/fmp?e=batch-quote&symbols=${encodeURIComponent(c.join(","))}`).then((r) => (r.ok ? r.json() : [])).catch(() => [])
    )).then((results) => {
      if (cancelled) return;
      const m: Record<string, number> = {};
      results.flat().forEach((q: any) => { if (q?.symbol && q?.price != null) m[q.symbol] = q.price; });
      setQuotes(m);
    });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [displayHoldings.map((hh) => hh.symbol).join(",")]);

  const navHist: NavPt[] = track?.nav_history || [];
  const rebs: any[] = track?.rebalances || [];
  const exits: any[] = track?.all_exits_2026 || [];
  const lastReb = rebs.length ? rebs[rebs.length - 1].date : null;
  const cadenceDays: number = tracking?.rebalance_cadence_days ?? CADENCE_DAYS_FALLBACK;
  const nextReb = useMemo(() => {
    if (!lastReb) return null;
    const d = new Date(lastReb + "T00:00:00");
    d.setDate(d.getDate() + cadenceDays);
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  }, [lastReb, cadenceDays]);

  // Everything below stays ABOVE the !cfg early return (rules of hooks — the
  // hook count must not differ between the found and not-found branches).
  const ytd: number | null = track?.ytd_return ?? null;
  const realized: number | null = track?.realized_ytd ?? null;
  // PIT-corrected baseline (preferred) with the config literal as last resort.
  const pitEq = pit?.methodologies?.[rawKey]?.equal;
  const b = pitEq
    ? { cagr: pitEq.cagr, mdd: pitEq.max_drawdown, sharpe: pitEq.sharpe }
    : (cfg as any)?.metrics?.baseline;
  const winRate = useMemo(() => {
    const rets = exits.map((e: any) => e.return).filter((v: any) => typeof v === "number");
    return rets.length ? (rets.filter((v: number) => v > 0).length / rets.length) * 100 : null;
  }, [exits]);
  const annualized = useMemo(() => {
    const start = track?.tracking_start;
    const last = navHist.length ? navHist[navHist.length - 1].date : null;
    if (ytd == null || !start || !last) return null;
    const days = Math.round((new Date(last + "T00:00:00").getTime() - new Date(start + "T00:00:00").getTime()) / 86400000);
    if (days < 14) return null;
    const ann = (Math.pow(1 + ytd, 365 / days) - 1) * 100;
    return isFinite(ann) ? `${ann >= 0 ? "+" : ""}${ann.toFixed(1)}%` : null;
  }, [ytd, track?.tracking_start, navHist]);
  const heroSpark = navHist.map((h) => h.nav);

  if (!cfg) {
    return (
      <div style={{ maxWidth: 860, margin: "0 auto", padding: 24 }}>
        <a href="/" style={{ color: "var(--text-light)", fontSize: 12, textDecoration: "none" }}>← Back</a>
        <div style={{ marginTop: 16, fontFamily: "var(--font-mono)", fontSize: 13 }}>Unknown basket &quot;{rawKey}&quot;.</div>
      </div>
    );
  }

  const tile = (label: string, value: React.ReactNode, color?: string) => (
    <div style={{ background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 8, padding: "10px 14px", minWidth: 108 }}>
      <div style={{ fontSize: 9, color: "var(--text-light)", textTransform: "uppercase", letterSpacing: 0.5 }}>{label}</div>
      <div style={{ fontSize: 16, fontFamily: "var(--font-mono)", fontWeight: 700, color: color || "var(--text)" , marginTop: 2 }}>{value}</div>
    </div>
  );

  return (
    <div style={{ maxWidth: 860, margin: "0 auto", padding: "20px 16px 48px" }}>
      <a href="/" style={{ display: "inline-flex", alignItems: "center", gap: 6, color: "var(--text-light)", fontSize: 12, textDecoration: "none" }}>
        <ArrowLeft size={13} /> Methodologies
      </a>

      <div style={{ display: "flex", alignItems: "baseline", gap: 10, flexWrap: "wrap", marginTop: 10 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, margin: 0 }}>{(cfg as any).name}</h1>
        <span style={{ fontSize: 9, fontFamily: "var(--font-mono)", color: "var(--text-light)" }}>({(cfg as any).path})</span>
        <span style={{ fontSize: 9, padding: "2px 6px", borderRadius: 3, background: "var(--bg-elevated)", border: "1px solid var(--border)", fontFamily: "var(--font-mono)" }}>
          {(cfg as any).regime}
        </span>
      </div>
      <p style={{ fontSize: 12, color: "var(--text-light)", lineHeight: 1.55, maxWidth: 720, marginTop: 8 }}>{(cfg as any).description}</p>
      <div style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 10, color: "var(--text-light)", fontFamily: "var(--font-mono)", marginBottom: 14 }}>
        <RefreshCw size={11} /> rotates every {cadenceDays} days (since Jul 20, 2026; monthly before)
        {lastReb && <> · last {fmtDay(lastReb)}{nextReb ? ` · next ~${nextReb}` : ""}</>}
      </div>

      {/* Live track record hero — same treatment as the Speculair basket headers */}
      <div style={{ display: "flex", alignItems: "center", gap: 18, padding: "10px 14px", marginBottom: 14, borderRadius: 8, background: "var(--bg)", border: "1px solid var(--border)" }}>
        <div>
          <div style={{ fontSize: 9, color: "var(--text-muted)", fontFamily: "var(--font-mono)", textTransform: "uppercase", letterSpacing: "0.04em" }}>Live track record</div>
          <div style={{ fontSize: 18, fontWeight: 800, fontFamily: "var(--font-mono)", color: perfColor(ytd) }}>{pct(ytd)}</div>
          <div style={{ fontSize: 9, color: "var(--text-light)", fontFamily: "var(--font-mono)" }}>
            since {track?.tracking_start || "—"}{annualized ? <> · ann. <b>{annualized}</b></> : null}
          </div>
        </div>
        {heroSpark.length > 1 && (() => {
          const mn = Math.min(...heroSpark), mx = Math.max(...heroSpark), r = (mx - mn) || 1, W = 130, HH = 34;
          const pts = heroSpark.map((v, i) => `${(i / (heroSpark.length - 1)) * W},${HH - ((v - mn) / r) * HH}`).join(" ");
          const up = heroSpark[heroSpark.length - 1] >= heroSpark[0];
          return <svg width={W} height={HH}><polyline points={pts} fill="none" stroke={up ? "var(--green)" : "var(--red)"} strokeWidth={1.5} /></svg>;
        })()}
        <div style={{ fontSize: 10, color: "var(--text-muted)", fontFamily: "var(--font-mono)", lineHeight: 1.5 }}>
          NAV {navHist.length ? navHist[navHist.length - 1].nav.toFixed(1) : "—"} · {holdings.length} held · {exits.length} closed{winRate != null ? ` · ${winRate.toFixed(1)}% win` : ""}
          <div style={{ fontSize: 8, color: "var(--text-light)", marginTop: 2 }}>equal-weight paper book · live-forward, not back-filled</div>
        </div>
      </div>

      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 18 }}>
        {tile("Realized YTD", pct(realized), perfColor(realized))}
        {tile("Holdings", holdings.length || "—")}
        {tile("Rebalances", track?.rebalance_count ?? rebs.length ?? "—")}
        {b && tile("Baseline CAGR", pct(b.cagr))}
        {b && tile("Baseline Sharpe", (b.sharpe ?? 0).toFixed(2))}
      </div>

      <div style={{ fontSize: 10, color: "var(--text-light)", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 6 }}>
        Tracked NAV — base 100 on the {tracking?.tracking_year ?? "current"} paper book
      </div>
      <NavChart hist={navHist} />

      {/* Per-record holdings — aggregates alone are never enough */}
      <div style={{ fontSize: 10, color: "var(--text-light)", textTransform: "uppercase", letterSpacing: 0.5, margin: "22px 0 6px" }}>
        {usingLivePicks ? `Live Screen Picks (${displayHoldings.length}) — paper tracking pending` : `Current Holdings (${holdings.length})`}
      </div>
      <div style={{ overflowX: "auto", border: "1px solid var(--border)", borderRadius: 8 }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "var(--font-mono)" }}>
          <thead>
            <tr style={{ color: "var(--text-light)", fontSize: 9, textTransform: "uppercase", textAlign: "left" }}>
              {["Symbol", "Entry", "Entry px", "Live px", "Return", "Weight"].map((hd, i) => (
                <th key={hd} style={{ padding: "7px 10px", borderBottom: "1px solid var(--border)", textAlign: i >= 2 ? "right" : "left" }}>{hd}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {displayHoldings.map((hh) => {
              const live = quotes[hh.symbol] ?? (usingLivePicks ? hh.price : undefined);
              const ret = live != null && hh.entry_price > 0 ? live / hh.entry_price - 1 : null;
              return (
                <tr key={hh.symbol}>
                  <td style={{ padding: "6px 10px", borderBottom: "1px solid var(--border)" }}>
                    <a href={`/stock/${hh.symbol}`} style={{ color: "var(--text)", textDecoration: "none", fontWeight: 700 }}>{hh.symbol}</a>
                  </td>
                  <td style={{ padding: "6px 10px", borderBottom: "1px solid var(--border)", color: "var(--text-light)" }}>{fmtDay(hh.entry_date)}</td>
                  <td style={{ padding: "6px 10px", borderBottom: "1px solid var(--border)", textAlign: "right" }}>{hh.entry_price?.toFixed(2)}</td>
                  <td style={{ padding: "6px 10px", borderBottom: "1px solid var(--border)", textAlign: "right" }}>{live != null ? live.toFixed(2) : "—"}</td>
                  <td style={{ padding: "6px 10px", borderBottom: "1px solid var(--border)", textAlign: "right", color: perfColor(ret), fontWeight: 700 }}>{pct(ret)}</td>
                  <td style={{ padding: "6px 10px", borderBottom: "1px solid var(--border)", textAlign: "right", color: "var(--text-light)" }}>{hh.weight != null ? `${(hh.weight * 100).toFixed(1)}%` : "—"}</td>
                </tr>
              );
            })}
            {!displayHoldings.length && (
              <tr><td colSpan={6} style={{ padding: 12, color: "var(--text-light)" }}>No tracked holdings yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Recent rotations */}
      {rebs.length > 0 && (
        <>
          <div style={{ fontSize: 10, color: "var(--text-light)", textTransform: "uppercase", letterSpacing: 0.5, margin: "22px 0 6px" }}>
            Recent Rotations
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {rebs.slice(-3).reverse().map((rb: any) => (
              <div key={rb.date} style={{ background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 8, padding: "8px 12px", fontSize: 11, fontFamily: "var(--font-mono)" }}>
                <span style={{ color: "var(--text-light)" }}>{fmtDayYr(rb.date)}</span>
                <span style={{ marginLeft: 10, color: "var(--green)" }}>+{(rb.entries || []).length} in</span>
                <span style={{ marginLeft: 8, color: "var(--red)" }}>−{(rb.exits || []).length} out</span>
                {(rb.entries || []).length > 0 && (
                  <span style={{ marginLeft: 10, color: "var(--text-light)", fontSize: 10 }}>
                    in: {(rb.entries || []).map((e: any) => e.symbol ?? e).slice(0, 8).join(", ")}
                  </span>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {/* Closed trades (toggle) */}
      {exits.length > 0 && (
        <div style={{ marginTop: 18 }}>
          <button
            onClick={() => setShowExits((v) => !v)}
            style={{ background: "none", border: "1px solid var(--border)", borderRadius: 6, color: "var(--text-light)", fontSize: 10, fontFamily: "var(--font-mono)", padding: "5px 10px", cursor: "pointer" }}
          >
            {showExits ? "Hide" : "Show"} closed trades ({exits.length})
          </button>
          {showExits && (
            <div style={{ overflowX: "auto", border: "1px solid var(--border)", borderRadius: 8, marginTop: 8 }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11, fontFamily: "var(--font-mono)" }}>
                <thead>
                  <tr style={{ color: "var(--text-light)", fontSize: 9, textTransform: "uppercase", textAlign: "left" }}>
                    {["Symbol", "Entry", "Exit", "Return"].map((hd, i) => (
                      <th key={hd} style={{ padding: "7px 10px", borderBottom: "1px solid var(--border)", textAlign: i === 3 ? "right" : "left" }}>{hd}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {exits.slice().reverse().map((ex: any, i: number) => (
                    <tr key={`${ex.symbol}-${i}`}>
                      <td style={{ padding: "6px 10px", borderBottom: "1px solid var(--border)" }}>
                        <a href={`/stock/${ex.symbol}`} style={{ color: "var(--text)", textDecoration: "none" }}>{ex.symbol}</a>
                        {ex.unpriced_exit && (
                          <span title="No live mark existed at exit — booked at the last known price" style={{ marginLeft: 6, fontSize: 8, color: "var(--amber)", border: "1px solid var(--amber)", borderRadius: 3, padding: "0px 3px" }}>unpriced</span>
                        )}
                      </td>
                      <td style={{ padding: "6px 10px", borderBottom: "1px solid var(--border)", color: "var(--text-light)" }}>{fmtDay(ex.entry_date)}</td>
                      <td style={{ padding: "6px 10px", borderBottom: "1px solid var(--border)", color: "var(--text-light)" }}>{fmtDay(ex.exit_date)}</td>
                      <td style={{ padding: "6px 10px", borderBottom: "1px solid var(--border)", textAlign: "right", color: perfColor(ex.return), fontWeight: 700 }}>{pct(ex.return)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {navHist.length < 30 && (
        <div style={{ marginTop: 20, fontSize: 10, color: "var(--text-light)", fontFamily: "var(--font-mono)" }}>
          Note: the NAV series is collected nightly since Jul 20, 2026 — history builds forward from there. Amber ticks mark rebalances.
        </div>
      )}
    </div>
  );
}
