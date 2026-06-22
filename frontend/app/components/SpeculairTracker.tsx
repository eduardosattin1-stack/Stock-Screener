"use client";
import React, { useState, useEffect } from "react";
import { ChevronDown, ChevronRight, RefreshCw } from "lucide-react";
import Link from "next/link";

interface Pick {
  symbol: string;
  conviction: number;
  entry_price?: number;
  entry_date?: string;
  source_methodologies?: string[];
}

type Quote = { price: number; changesPercentage: number };

// Compact live tracker for the Speculair Apex Basket + Capitulation Watchlist.
// Designed to sit underneath the Watchlist inside the shared right rail.
export function SpeculairTracker() {
  const [baskets, setBaskets] = useState<any>(null);
  const [quotes, setQuotes] = useState<Record<string, Quote>>({});
  const [loading, setLoading] = useState(false);
  const [openApex, setOpenApex] = useState(true);
  const [openCap, setOpenCap] = useState(true);
  const [openClosed, setOpenClosed] = useState(false);
  const [tracking, setTracking] = useState<any>(null);

  // Load baskets: GCS first, public file fallback (mirrors page.tsx).
  useEffect(() => {
    fetch("/api/gcs/scans/speculair_baskets.json")
      .then((r) => { if (r.ok) return r.json(); throw new Error("gcs"); })
      .then((d) => { if (d) setBaskets(d); })
      .catch(() => {
        fetch("/speculair_baskets.json")
          .then((r) => (r.ok ? r.json() : null))
          .then((d) => { if (d) setBaskets(d); })
          .catch(() => {});
      });
  }, []);

  // Load Apex track record (chained NAV + closed rotations): GCS first, public fallback.
  useEffect(() => {
    fetch("/api/gcs/scans/speculair_apex_tracking.json")
      .then((r) => { if (r.ok) return r.json(); throw new Error("gcs"); })
      .then((d) => { if (d && d.nav) setTracking(d); })
      .catch(() => {
        fetch("/speculair_apex_tracking.json")
          .then((r) => (r.ok ? r.json() : null))
          .then((d) => { if (d && d.nav) setTracking(d); })
          .catch(() => {});
      });
  }, []);

  const apex: Pick[] = baskets?.apex_basket || [];
  const cap: Pick[] = baskets?.capitulation_watchlist || [];
  const symbolsKey = Array.from(new Set([...apex, ...cap].map((p) => p.symbol))).join(",");

  const fetchQuotes = async () => {
    if (!symbolsKey) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/fmp?e=quote&symbol=${symbolsKey}`);
      const data = await res.json();
      if (Array.isArray(data)) {
        const m: Record<string, Quote> = {};
        data.forEach((q: any) => { m[q.symbol] = { price: q.price, changesPercentage: q.changesPercentage }; });
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

  const gridCols = "minmax(0, 1.4fr) 1fr 1fr 1fr";

  const convStyle = (c: number) => ({
    fontSize: 8.5, padding: "1px 5px", borderRadius: 4, fontFamily: "var(--font-mono)", fontWeight: 700,
    background: c >= 85 ? "rgba(20,184,122,0.2)" : c >= 70 ? "rgba(234,179,8,0.2)" : "rgba(148,163,184,0.18)",
    color: c >= 85 ? "var(--green)" : c >= 70 ? "#eab308" : "var(--text-muted)",
  });

  // Apex track-record (paper-traded equal-weight NAV since basket inception).
  const navHist: { date: string; nav: number }[] = tracking?.history || [];
  const nav: number | null = tracking?.nav ?? null;
  const sinceInception = nav != null ? nav - 100 : null; // history is anchored to base 100
  const closed: any[] = tracking?.closed || [];
  const fmtDay = (s?: string) => (s ? new Date(s + "T00:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" }) : "");
  const daysSince = tracking?.inception_date && tracking?.last_date
    ? Math.max(0, Math.round((new Date(tracking.last_date + "T00:00:00").getTime() - new Date(tracking.inception_date + "T00:00:00").getTime()) / 86400000))
    : null;
  const perfColor = sinceInception == null ? "var(--text-muted)" : sinceInception > 0 ? "var(--green)" : sinceInception < 0 ? "var(--red)" : "var(--text-muted)";

  const Sparkline = ({ navs, color }: { navs: number[]; color: string }) => {
    if (!navs || navs.length < 2) return null;
    const w = 88, h = 28, pad = 3;
    const min = Math.min(...navs), max = Math.max(...navs), range = max - min || 1;
    const pts = navs.map((v, i) => {
      const x = pad + (i / (navs.length - 1)) * (w - 2 * pad);
      const y = pad + (1 - (v - min) / range) * (h - 2 * pad);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");
    return (
      <svg width={w} height={h} style={{ display: "block", flexShrink: 0 }} aria-hidden="true">
        <polyline points={pts} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
      </svg>
    );
  };

  const Row = ({ p }: { p: Pick }) => {
    const q = quotes[p.symbol];
    const last = q?.price;
    const entry = p.entry_price || 0;
    const perf = last != null && entry > 0 ? ((last / entry) - 1) * 100 : null;
    const color = perf == null ? "var(--text-muted)" : perf > 0 ? "var(--green)" : perf < 0 ? "var(--red)" : "var(--text-muted)";
    return (
      <div className="group" style={{ display: "grid", gridTemplateColumns: gridCols, gap: 6, padding: "8px 16px", borderBottom: "1px solid var(--border-subtle)", alignItems: "center", fontSize: 12, fontFamily: "var(--font-mono)", transition: "background 0.1s" }}
           onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-hover)")} onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
        <div style={{ display: "flex", alignItems: "center", gap: 5, minWidth: 0 }}>
          <Link href={`/stock/${p.symbol}`} style={{ textDecoration: "none", color: "var(--text)", fontWeight: 700, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.symbol}</Link>
          <span style={convStyle(p.conviction)}>★{p.conviction}</span>
        </div>
        <div style={{ textAlign: "right", color: "var(--text-muted)" }}>{entry > 0 ? entry.toFixed(2) : "—"}</div>
        <div style={{ textAlign: "right", color: "var(--text-light)" }}>{last != null ? last.toFixed(2) : "—"}</div>
        <div style={{ textAlign: "right", color, fontWeight: 700 }}>{perf == null ? "—" : `${perf > 0 ? "+" : ""}${perf.toFixed(1)}%`}</div>
      </div>
    );
  };

  const SectionHeader = ({ open, onClick, title, count, accent }: { open: boolean; onClick: () => void; title: string; count: number; accent: string }) => (
    <button onClick={onClick} style={{ width: "100%", display: "flex", alignItems: "center", gap: 6, padding: "10px 16px", background: "none", border: "none", borderBottom: "1px solid var(--border-subtle)", cursor: "pointer", textAlign: "left" }}>
      {open ? <ChevronDown size={13} color="var(--text-light)" /> : <ChevronRight size={13} color="var(--text-light)" />}
      <span style={{ width: 6, height: 6, borderRadius: 2, background: accent }} />
      <span style={{ fontSize: 12, fontWeight: 700, color: "var(--text)" }}>{title}</span>
      <span style={{ marginLeft: "auto", fontSize: 10, color: "var(--text-light)", fontFamily: "var(--font-mono)" }}>{count}</span>
    </button>
  );

  return (
    <div style={{ borderTop: "1px solid var(--border)", display: "flex", flexDirection: "column", fontFamily: "var(--font-sans)" }}>
      {/* Block header */}
      <div style={{ padding: "12px 16px 10px", borderBottom: "1px solid var(--border-subtle)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
          <span style={{ fontSize: 13, fontWeight: 800, color: "var(--text)", fontFamily: "var(--font-mono)", letterSpacing: "-0.02em" }}>
            specul<span style={{ color: "var(--lavender)" }}>AI</span>r
          </span>
          <span style={{ fontSize: 9, color: "var(--text-light)", fontFamily: "var(--font-mono)" }}>tracker</span>
        </div>
        <button onClick={fetchQuotes} title="Refresh" style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-light)", padding: 4, display: "flex" }}>
          <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      {/* Apex track record — NAV since inception + sparkline */}
      {tracking && sinceInception != null && (
        <div style={{ padding: "10px 16px", borderBottom: "1px solid var(--border-subtle)", display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
              <span style={{ fontSize: 20, fontWeight: 800, color: perfColor, fontFamily: "var(--font-mono)", letterSpacing: "-0.02em" }}>
                {sinceInception > 0 ? "+" : ""}{sinceInception.toFixed(1)}%
              </span>
              <span style={{ fontSize: 9, color: "var(--text-light)", fontFamily: "var(--font-mono)" }}>Apex since {fmtDay(tracking.inception_date)}</span>
            </div>
            <div style={{ fontSize: 8.5, color: "var(--text-muted)", fontFamily: "var(--font-mono)", marginTop: 2 }}>
              NAV {(nav ?? 0).toFixed(1)}{daysSince != null ? ` · ${daysSince}d` : ""}{closed.length ? ` · ${closed.length} rotated` : ""}
            </div>
          </div>
          <Sparkline navs={navHist.map((h) => h.nav)} color={perfColor} />
        </div>
      )}

      {/* Column sub-header */}
      <div style={{ display: "grid", gridTemplateColumns: gridCols, gap: 6, padding: "6px 16px", fontSize: 9, fontWeight: 600, color: "var(--text-light)", textTransform: "uppercase", borderBottom: "1px solid var(--border-subtle)", fontFamily: "var(--font-mono)" }}>
        <div>Symbol</div>
        <div style={{ textAlign: "right" }}>Entry</div>
        <div style={{ textAlign: "right" }}>Last</div>
        <div style={{ textAlign: "right" }}>P&amp;L</div>
      </div>

      {/* Apex Basket */}
      <SectionHeader open={openApex} onClick={() => setOpenApex(!openApex)} title="Apex Basket" count={apex.length} accent="var(--green)" />
      {openApex && (apex.length > 0
        ? apex.map((p) => <Row key={p.symbol} p={p} />)
        : <div style={{ padding: "12px 16px", fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>No Apex positions.</div>)}

      {/* Rotated out — realized returns logged when a name leaves the basket */}
      {tracking && (
        <>
          <SectionHeader open={openClosed} onClick={() => setOpenClosed(!openClosed)} title="Rotated out" count={closed.length} accent="var(--text-light)" />
          {openClosed && (closed.length > 0
            ? [...closed].reverse().map((c, i) => {
                const ret = typeof c.return_pct === "number" ? c.return_pct : null;
                const rc = ret == null ? "var(--text-muted)" : ret > 0 ? "var(--green)" : ret < 0 ? "var(--red)" : "var(--text-muted)";
                return (
                  <div key={`${c.symbol}-${c.exit_date}-${i}`} className="group" style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.6fr) 1fr", gap: 6, padding: "8px 16px", borderBottom: "1px solid var(--border-subtle)", alignItems: "center", fontSize: 12, fontFamily: "var(--font-mono)", transition: "background 0.1s" }}
                       onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-hover)")} onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
                    <div style={{ display: "flex", alignItems: "center", gap: 5, minWidth: 0 }}>
                      <Link href={`/stock/${c.symbol}`} style={{ textDecoration: "none", color: "var(--text)", fontWeight: 700 }}>{c.symbol}</Link>
                      <span style={{ fontSize: 8.5, color: "var(--text-muted)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{fmtDay(c.entry_date)}→{fmtDay(c.exit_date)}</span>
                    </div>
                    <div style={{ textAlign: "right", color: rc, fontWeight: 700 }}>{ret == null ? "—" : `${ret > 0 ? "+" : ""}${ret.toFixed(1)}%`}</div>
                  </div>
                );
              })
            : <div style={{ padding: "12px 16px", fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-mono)", lineHeight: 1.4 }}>No rotations yet — realized returns appear here as picks leave the basket.</div>)}
        </>
      )}

      {/* Beaten-Down (capitulation) watchlist */}
      <SectionHeader open={openCap} onClick={() => setOpenCap(!openCap)} title="Beaten-Down" count={cap.length} accent="var(--orange)" />
      {openCap && (cap.length > 0
        ? cap.map((p) => <Row key={p.symbol} p={p} />)
        : <div style={{ padding: "12px 16px", fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>No Capitulation setups.</div>)}

      {/* Footnote */}
      <div style={{ padding: "10px 16px", fontSize: 8.5, color: "var(--text-muted)", fontFamily: "var(--font-mono)", lineHeight: 1.4 }}>
        Rows: live P&amp;L vs entry · 30s · Apex NAV: equal-weight, since inception{baskets.generated_at ? ` · gen ${new Date(baskets.generated_at).toLocaleDateString()}` : ""}
      </div>
    </div>
  );
}
