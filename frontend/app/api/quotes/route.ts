import { NextRequest, NextResponse } from "next/server";

// Live data for an arbitrary set of symbols (the user's customizable radar).
// batch-quote → price + day% + name (one call); stock-price-change → ytd + 1Y (per symbol).
const FMP_BASE = "https://financialmodelingprep.com/stable";

async function fmpGet(endpoint: string, params: Record<string, string>, revalidate: number) {
  const apiKey = process.env.FMP_API_KEY as string;
  const qs = new URLSearchParams({ ...params, apikey: apiKey });
  const res = await fetch(`${FMP_BASE}/${endpoint}?${qs}`, { next: { revalidate } });
  if (!res.ok) return null;
  const data = await res.json();
  return Array.isArray(data) ? data : data ? [data] : null;
}

const num = (o: any, k: string): number | null => {
  const v = o == null ? null : Number(o[k]);
  return Number.isFinite(v as number) ? (v as number) : null;
};

export async function GET(req: NextRequest) {
  if (!process.env.FMP_API_KEY) return NextResponse.json({ error: "FMP_API_KEY not set" }, { status: 500 });
  const url = new URL(req.url);
  // light=1: price + day% only, from the single batch-quote call — skips the per-symbol
  // stock-price-change (ytd/1Y) fan-out, so the 12-symbol cap (which exists ONLY to bound
  // that fan-out) lifts to 60. Used by the Basket 13 + watchlist live ticker, which renders
  // just price + day% (was silently dropping the tail past 12 symbols).
  const light = url.searchParams.get("light") === "1";
  const symbols = (url.searchParams.get("symbols") || "")
    .split(",").map((s) => s.trim()).filter(Boolean).slice(0, light ? 60 : 12);
  if (!symbols.length) return NextResponse.json({ quotes: [] });

  try {
    const qrows = await fmpGet("batch-quote", { symbols: symbols.join(",") }, 30);
    const qmap: Record<string, any> = {};
    for (const q of qrows || []) qmap[q.symbol] = q;
    const changes: any[] = light ? [] : await Promise.all(
      symbols.map((s) => fmpGet("stock-price-change", { symbol: s }, 300).then((r) => r?.[0] ?? null).catch(() => null)),
    );

    const quotes = symbols.map((s, i) => {
      const q = qmap[s];
      const c = light ? null : changes[i];
      return { symbol: s, name: q?.name ?? s, price: num(q, "price"), day: num(q, "changePercentage"), ytd: num(c, "ytd"), year: num(c, "1Y") };
    });
    return NextResponse.json({ quotes });
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 502 });
  }
}
