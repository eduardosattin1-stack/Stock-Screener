import { NextRequest, NextResponse } from "next/server";

// Price series for the card chart popup. Works for ANY symbol on the Sectors
// tab / radar — indices (caret-encoded), sector & thematic ETFs, crypto, forex.
//   • Intraday ranges (1D/1W) → historical-chart/{5min,1hour}.
//   • Daily ranges (1M…5Y/YTD) → historical-price-eod/light.
// Returned points are ascending by time as { t: epochMs, c: close }.
const FMP_BASE = "https://financialmodelingprep.com/stable";

type Src = "i5" | "i60" | "eod";
const RANGES: Record<string, { src: Src; days: number | null }> = {
  "1D": { src: "i5", days: 1 },
  "1W": { src: "i60", days: 7 },
  "1M": { src: "eod", days: 31 },
  "3M": { src: "eod", days: 93 },
  "6M": { src: "eod", days: 186 },
  YTD: { src: "eod", days: null },
  "1Y": { src: "eod", days: 366 },
  "5Y": { src: "eod", days: 1827 },
};

async function fmpGet(endpoint: string, params: Record<string, string>, revalidate: number) {
  const apiKey = process.env.FMP_API_KEY as string;
  const qs = new URLSearchParams({ ...params, apikey: apiKey });
  const res = await fetch(`${FMP_BASE}/${endpoint}?${qs}`, { next: { revalidate } });
  if (!res.ok) return null;
  const data = await res.json();
  return Array.isArray(data) ? data : null;
}

export async function GET(req: NextRequest) {
  if (!process.env.FMP_API_KEY) return NextResponse.json({ error: "FMP_API_KEY not set" }, { status: 500 });
  const sp = new URL(req.url).searchParams;
  const symbol = (sp.get("symbol") || "").trim();
  const range = (sp.get("range") || "1M").toUpperCase();
  if (!symbol) return NextResponse.json({ error: "missing ?symbol" }, { status: 400 });
  const cfg = RANGES[range] || RANGES["1M"];

  try {
    let pts: { t: number; c: number }[] = [];

    if (cfg.src === "eod") {
      const rows = await fmpGet("historical-price-eod/light", { symbol }, 300);
      pts = (rows || [])
        .map((r: any) => ({ t: Date.parse(r.date), c: Number(r.price) }))
        .filter((p) => Number.isFinite(p.t) && Number.isFinite(p.c))
        .sort((a, b) => a.t - b.t);
      const latest = pts.length ? pts[pts.length - 1].t : Date.now();
      const cutoff =
        cfg.days == null ? Date.parse(new Date(latest).getFullYear() + "-01-01") : latest - cfg.days * 86_400_000;
      pts = pts.filter((p) => p.t >= cutoff);
    } else {
      const ep = cfg.src === "i5" ? "historical-chart/5min" : "historical-chart/1hour";
      const rows = await fmpGet(ep, { symbol }, 120);
      let all = (rows || [])
        .map((r: any) => ({ t: Date.parse(r.date), c: Number(r.close) }))
        .filter((p) => Number.isFinite(p.t) && Number.isFinite(p.c))
        .sort((a, b) => a.t - b.t);
      if (cfg.src === "i5") {
        // Latest trading session only (fall back to last ~78 bars if sparse).
        const lastDay = all.length ? new Date(all[all.length - 1].t).toDateString() : "";
        const day = all.filter((p) => new Date(p.t).toDateString() === lastDay);
        pts = day.length >= 5 ? day : all.slice(-78);
      } else {
        const latest = all.length ? all[all.length - 1].t : Date.now();
        pts = all.filter((p) => p.t >= latest - 7 * 86_400_000);
      }
    }

    if (pts.length < 2) return NextResponse.json({ symbol, range, points: [], first: null, last: null, min: null, max: null });
    const closes = pts.map((p) => p.c);
    const first = pts[0].c;
    const last = pts[pts.length - 1].c;
    return NextResponse.json({
      symbol,
      range,
      points: pts,
      first,
      last,
      min: Math.min(...closes),
      max: Math.max(...closes),
      changePct: first ? ((last - first) / first) * 100 : null,
    });
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 502 });
  }
}
