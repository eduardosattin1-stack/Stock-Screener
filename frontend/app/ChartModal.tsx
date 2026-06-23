"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { X } from "lucide-react";

// Lightweight, self-contained price-chart popup for the Sectors-tab / radar cards.
// Pure SVG (no react-financial-charts): smooth area with gradient fill, range
// pills, and a hover crosshair + tooltip. Data from /api/series (any symbol).

type Pt = { t: number; c: number };
type Series = { points: Pt[]; first: number | null; last: number | null; min: number | null; max: number | null; changePct: number | null };

const RANGES = ["1D", "1W", "1M", "3M", "6M", "YTD", "1Y", "5Y"] as const;
type Range = (typeof RANGES)[number];

const UP = "#19c37d";
const DOWN = "#f1565b";

function fmtPrice(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return "—";
  const a = Math.abs(v);
  if (a >= 1000) return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (a >= 1) return v.toFixed(2);
  return v.toFixed(4);
}

export default function ChartModal({
  symbol,
  name,
  livePrice,
  liveDay,
  detailHref,
  onClose,
}: {
  symbol: string;
  name?: string | null;
  livePrice?: number | null;
  liveDay?: number | null;
  detailHref?: string;
  onClose: () => void;
}) {
  const [range, setRange] = useState<Range>("3M");
  const [data, setData] = useState<Series | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  // Esc to close + lock background scroll while open.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setErr(null);
    setHover(null);
    fetch(`/api/series?symbol=${encodeURIComponent(symbol)}&range=${range}`)
      .then((r) => r.json())
      .then((j) => {
        if (!alive) return;
        if (j?.error) setErr(j.error);
        else setData(j);
      })
      .catch((e) => alive && setErr(String(e?.message || e)))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [symbol, range]);

  const intraday = range === "1D" || range === "1W";
  const pts = data?.points || [];
  const up = (data?.changePct ?? 0) >= 0;
  const color = up ? UP : DOWN;
  // Fall back to the series' last close when no live price is passed in
  // (apex/watchlist/methodology picks don't carry a live quote).
  const headerPrice = livePrice != null ? livePrice : (data?.last ?? null);

  // SVG geometry (fixed viewBox, scales to container width).
  const W = 820, H = 300, padL = 10, padR = 62, padT = 18, padB = 24;
  const plotW = W - padL - padR, plotH = H - padT - padB, baseY = padT + plotH;

  const geo = useMemo(() => {
    if (pts.length < 2) return null;
    const min = data!.min!, max = data!.max!;
    const span = max - min || 1;
    const x = (i: number) => padL + (i / (pts.length - 1)) * plotW;
    const y = (c: number) => padT + (1 - (c - min) / span) * plotH;
    const line = pts.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(2)},${y(p.c).toFixed(2)}`).join(" ");
    const area = `${line} L${x(pts.length - 1).toFixed(2)},${baseY} L${x(0).toFixed(2)},${baseY} Z`;
    let lo = 0, hi = 0;
    pts.forEach((p, i) => {
      if (p.c < pts[lo].c) lo = i;
      if (p.c > pts[hi].c) hi = i;
    });
    return { x, y, line, area, lo, hi, firstY: y(pts[0].c) };
  }, [pts, data, plotW, plotH, baseY]);

  const onMove = (e: React.MouseEvent) => {
    if (!geo || !svgRef.current || pts.length < 2) return;
    const rect = svgRef.current.getBoundingClientRect();
    const vbX = ((e.clientX - rect.left) / rect.width) * W;
    const i = Math.round(((vbX - padL) / plotW) * (pts.length - 1));
    setHover(Math.max(0, Math.min(pts.length - 1, i)));
  };

  const hp = hover != null && pts[hover] ? pts[hover] : null;
  const fmtT = (t: number) =>
    new Date(t).toLocaleString(undefined, intraday ? { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" } : { year: "2-digit", month: "short", day: "numeric" });

  const dayColor = liveDay == null ? "var(--text-muted)" : liveDay >= 0 ? "var(--green)" : "var(--red)";
  const gid = "cg-" + symbol.replace(/[^A-Za-z0-9]/g, "");

  return (
    <div
      onClick={onClose}
      style={{ position: "fixed", inset: 0, zIndex: 1000, background: "rgba(4,10,9,0.66)", backdropFilter: "blur(4px)", display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ width: "min(860px, 94vw)", background: "var(--bg-card, #0c1a17)", border: "1px solid var(--border, #1c3330)", borderRadius: 16, padding: "18px 20px 16px", boxShadow: "0 24px 70px rgba(0,0,0,0.55)", fontFamily: "var(--font-sans)" }}
      >
        {/* Header */}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: 20, fontWeight: 700, letterSpacing: "-0.01em", color: "var(--text)" }}>{name || symbol}</div>
            <div style={{ fontSize: 11, color: "var(--text-light)", fontFamily: "var(--font-mono)", marginTop: 2 }}>{symbol}</div>
          </div>
          <div style={{ display: "flex", alignItems: "flex-start", gap: 14 }}>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: 22, fontWeight: 700, fontFamily: "var(--font-mono)", color: "var(--text)", lineHeight: 1.1 }}>{fmtPrice(headerPrice)}</div>
              <div style={{ fontSize: 12, fontFamily: "var(--font-mono)", color: dayColor, marginTop: 2 }}>
                {liveDay == null ? "" : `${liveDay >= 0 ? "+" : ""}${liveDay.toFixed(2)}% today`}
              </div>
            </div>
            <button onClick={onClose} aria-label="Close" style={{ background: "transparent", border: "none", color: "var(--text-light)", cursor: "pointer", padding: 2, lineHeight: 0 }}>
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Range return badge */}
        <div style={{ marginTop: 6, fontSize: 12, fontFamily: "var(--font-mono)", color, display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: color }} />
          {data?.changePct == null ? "" : `${up ? "▲" : "▼"} ${Math.abs(data.changePct).toFixed(2)}%`}
          <span style={{ color: "var(--text-light)" }}>over {range}</span>
        </div>

        {/* Chart */}
        <div style={{ position: "relative", marginTop: 8, height: 300 }}>
          {loading && <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, color: "var(--text-light)" }}>Loading…</div>}
          {err && !loading && <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, color: "var(--red)" }}>Couldn’t load chart — {err}</div>}
          {!loading && !err && !geo && <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, color: "var(--text-light)" }}>No data for this range.</div>}
          {!loading && !err && geo && (
            <svg ref={svgRef} viewBox={`0 0 ${W} ${H}`} width="100%" height="300" preserveAspectRatio="none" onMouseMove={onMove} onMouseLeave={() => setHover(null)} style={{ display: "block", cursor: "crosshair" }}>
              <defs>
                <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={color} stopOpacity={0.28} />
                  <stop offset="100%" stopColor={color} stopOpacity={0} />
                </linearGradient>
              </defs>
              {/* baseline (range open) */}
              <line x1={padL} y1={geo.firstY} x2={padL + plotW} y2={geo.firstY} stroke="var(--text-light)" strokeWidth={1} strokeDasharray="3 4" opacity={0.35} />
              <path d={geo.area} fill={`url(#${gid})`} />
              <path d={geo.line} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
              {/* min / max markers */}
              {[geo.hi, geo.lo].map((idx, k) => (
                <g key={k}>
                  <circle cx={geo.x(idx)} cy={geo.y(pts[idx].c)} r={2.6} fill={color} />
                  <text x={Math.min(Math.max(geo.x(idx), 26), padL + plotW - 26)} y={geo.y(pts[idx].c) + (k === 0 ? -7 : 13)} fill="var(--text-light)" fontSize={10} textAnchor="middle" fontFamily="var(--font-mono)">
                    {fmtPrice(pts[idx].c)}
                  </text>
                </g>
              ))}
              {/* last-price edge marker */}
              <circle cx={geo.x(pts.length - 1)} cy={geo.y(pts[pts.length - 1].c)} r={3} fill={color} />
              {/* hover crosshair */}
              {hp && hover != null && (
                <g>
                  <line x1={geo.x(hover)} y1={padT} x2={geo.x(hover)} y2={baseY} stroke="var(--text-muted)" strokeWidth={1} opacity={0.5} />
                  <circle cx={geo.x(hover)} cy={geo.y(hp.c)} r={3.4} fill="#fff" stroke={color} strokeWidth={2} />
                </g>
              )}
            </svg>
          )}
          {/* hover tooltip (HTML, positioned over the svg) */}
          {hp && hover != null && geo && (
            <div
              style={{
                position: "absolute",
                top: 0,
                left: `calc(${(geo.x(hover) / W) * 100}% )`,
                transform: `translateX(${hover > pts.length / 2 ? "-105%" : "5%"})`,
                pointerEvents: "none",
                background: "var(--bg, #07120f)",
                border: "1px solid var(--border, #1c3330)",
                borderRadius: 8,
                padding: "5px 8px",
                fontFamily: "var(--font-mono)",
                whiteSpace: "nowrap",
              }}
            >
              <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text)" }}>{fmtPrice(hp.c)}</div>
              <div style={{ fontSize: 10, color: "var(--text-light)" }}>{fmtT(hp.t)}</div>
            </div>
          )}
        </div>

        {/* Range pills */}
        <div style={{ display: "flex", gap: 6, marginTop: 10, flexWrap: "wrap" }}>
          {RANGES.map((r) => (
            <button
              key={r}
              onClick={() => setRange(r)}
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: 11,
                padding: "4px 10px",
                borderRadius: 7,
                cursor: "pointer",
                border: "1px solid " + (r === range ? color : "var(--border, #1c3330)"),
                background: r === range ? color + "22" : "transparent",
                color: r === range ? "var(--text)" : "var(--text-light)",
                fontWeight: r === range ? 700 : 400,
              }}
            >
              {r}
            </button>
          ))}
        </div>

        {/* Optional drill-into-dossier link (apex / methodology picks pass detailHref) */}
        {detailHref && (
          <div style={{ marginTop: 12, textAlign: "right" }}>
            <a href={detailHref} style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: UP, textDecoration: "none", fontWeight: 600 }}>
              View full analysis →
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
