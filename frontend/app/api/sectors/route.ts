import { NextResponse } from "next/server";

// Live data for the Sectors tab. Everything here is real FMP — the tab was
// previously a hardcoded mockup (static index cards + a duplicate of the
// Methodologies baskets).
//
// Two data layers, cached independently so polling stays cheap:
//   • batch-quote  → live price + today's % for ALL symbols in ONE call.
//     Cached 30s — this is the part that ticks when the client polls (60s).
//   • stock-price-change → ytd / 1Y per symbol. Cached 300s; these barely
//     move intraday, so they refresh every ~5 min, not every poll.
// Net: ~1 FMP call/min while a user watches the tab (plus 22 every 5 min).
//
// NOTE: the FMP MCP abstracts price-change as `quote-change`, but the real
// stable REST path is `stock-price-change` (`quote-change` 404s to []).
const FMP_BASE = "https://financialmodelingprep.com/stable";

type Row = { name: string; symbol: string; accent?: string; invert?: boolean };

// Major index / macro proxy cards (the header strip).
const INDICES: Row[] = [
  { name: "S&P 500", symbol: "^GSPC", accent: "#3b82f6" },
  { name: "NASDAQ 100", symbol: "^NDX", accent: "#f59e0b" },
  { name: "DAX", symbol: "^GDAXI", accent: "#6366f1" },
  { name: "Russell 2000", symbol: "^RUT", accent: "#ec4899" },
  { name: "Bitcoin", symbol: "BTCUSD", accent: "#f97316" },
  // EURUSD is quoted USD-per-EUR; invert to read as USD/EUR (USD strength).
  { name: "USD/EUR", symbol: "EURUSD", accent: "#8b5cf6", invert: true },
];

// 11 GICS sectors via SPDR sector ETFs.
const SECTORS: Row[] = [
  { name: "Technology", symbol: "XLK" },
  { name: "Health Care", symbol: "XLV" },
  { name: "Financials", symbol: "XLF" },
  { name: "Consumer Discretionary", symbol: "XLY" },
  { name: "Communication Svcs", symbol: "XLC" },
  { name: "Industrials", symbol: "XLI" },
  { name: "Consumer Staples", symbol: "XLP" },
  { name: "Energy", symbol: "XLE" },
  { name: "Utilities", symbol: "XLU" },
  { name: "Real Estate", symbol: "XLRE" },
  { name: "Materials", symbol: "XLB" },
];

// Thematic industry/theme ETFs (Bruno's pick).
const THEMATIC: Row[] = [
  { name: "Semiconductors", symbol: "SMH" },
  { name: "Nuclear / SMR", symbol: "NUKZ" },
  { name: "Quantum", symbol: "QTUM" },
  { name: "Robotics & AI", symbol: "BOTZ" },
  { name: "Rare Earth / Minerals", symbol: "REMX" },
];

async function fmpGet(endpoint: string, params: Record<string, string>, revalidate: number) {
  const apiKey = process.env.FMP_API_KEY as string;
  const qs = new URLSearchParams({ ...params, apikey: apiKey });
  const res = await fetch(`${FMP_BASE}/${endpoint}?${qs}`, { next: { revalidate } });
  if (!res.ok) return null;
  const data = await res.json();
  return Array.isArray(data) ? data : data ? [data] : null;
}

// Convert a % / level on the reciprocal pair (EURUSD -> USD/EUR).
const invertPct = (r: number) => (1 / (1 + r / 100) - 1) * 100;

// 5D (week) / ytd / 1Y per symbol (slow layer, long cache).
async function changeFor(item: Row): Promise<{ week: number | null; ytd: number | null; year: number | null }> {
  const rows = await fmpGet("stock-price-change", { symbol: item.symbol }, 300);
  const c = rows?.[0] ?? null;
  const pick = (k: string): number | null => {
    const v = c == null ? null : Number(c[k]);
    if (!Number.isFinite(v as number)) return null;
    return item.invert ? invertPct(v as number) : (v as number);
  };
  return { week: pick("5D"), ytd: pick("ytd"), year: pick("1Y") };
}

export async function GET() {
  if (!process.env.FMP_API_KEY) return NextResponse.json({ error: "FMP_API_KEY not set" }, { status: 500 });

  try {
    const universe = [...INDICES, ...SECTORS, ...THEMATIC];
    const symbols = universe.map((u) => u.symbol);

    const [quoteRows, ratesRaw, gdpRaw, ...changes] = await Promise.all([
      fmpGet("batch-quote", { symbols: [...symbols, "^VIX", "^W5000"].join(",") }, 30),
      fmpGet("treasury-rates", {}, 300),
      fmpGet("economic-indicators", { name: "GDP" }, 86400),
      ...universe.map((u) => changeFor(u).catch(() => ({ week: null, ytd: null, year: null }))),
    ]);

    const qmap: Record<string, any> = {};
    for (const q of quoteRows || []) qmap[q.symbol] = q;

    const rows = universe.map((item, i) => {
      const q = qmap[item.symbol];
      let price = q && Number.isFinite(Number(q.price)) ? Number(q.price) : null;
      let day = q && Number.isFinite(Number(q.changePercentage)) ? Number(q.changePercentage) : null;
      if (item.invert) {
        if (price) price = 1 / price;
        if (day != null) day = invertPct(day);
      }
      const ch = changes[i] || { week: null, ytd: null, year: null };
      return { name: item.name, symbol: item.symbol, accent: item.accent ?? null, price, day, week: ch.week, ytd: ch.ytd, year: ch.year };
    });

    const n = INDICES.length;
    const m = SECTORS.length;
    const vixQ = qmap["^VIX"];
    const vix = vixQ && Number.isFinite(Number(vixQ.price)) ? Number(vixQ.price) : null;
    const vixChange = vixQ && Number.isFinite(Number(vixQ.changePercentage)) ? Number(vixQ.changePercentage) : null;
    const yield10 = Number(ratesRaw?.[0]?.year10);
    // Buffett indicator (proxy): Wilshire 5000 total-market index / nominal GDP × 100.
    const wPrice = Number(qmap["^W5000"]?.price);
    const gdp = Number(gdpRaw?.[0]?.value);
    const buffett = Number.isFinite(wPrice) && Number.isFinite(gdp) && gdp > 0 ? Math.round((wPrice / gdp) * 100) : null;

    return NextResponse.json({
      indices: rows.slice(0, n),
      sectors: rows.slice(n, n + m),
      thematic: rows.slice(n + m),
      macro: {
        vix: vix != null ? Math.round(vix * 100) / 100 : null,
        vixChange: vixChange != null ? Math.round(vixChange * 100) / 100 : null,
        yield10: Number.isFinite(yield10) ? yield10 : null,
        buffett,
      },
      asOf: ratesRaw?.[0]?.date ?? null,
    });
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 502 });
  }
}
