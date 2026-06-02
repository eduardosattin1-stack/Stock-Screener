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
  const symbols = (new URL(req.url).searchParams.get("symbols") || "")
    .split(",").map((s) => s.trim()).filter(Boolean).slice(0, 12);
  if (!symbols.length) return NextResponse.json({ quotes: [] });

  try {
    const [qrows, ...changes] = await Promise.all([
      fmpGet("batch-quote", { symbols: symbols.join(",") }, 30),
      ...symbols.map((s) => fmpGet("stock-price-change", { symbol: s }, 300).then((r) => r?.[0] ?? null).catch(() => null)),
    ]);
    const qmap: Record<string, any> = {};
    for (const q of qrows || []) qmap[q.symbol] = q;

    const quotes = symbols.map((s, i) => {
      const q = qmap[s];
      const c = changes[i];
      return { symbol: s, name: q?.name ?? s, price: num(q, "price"), day: num(q, "changePercentage"), ytd: num(c, "ytd"), year: num(c, "1Y") };
    });
    return NextResponse.json({ quotes });
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 502 });
  }
}
