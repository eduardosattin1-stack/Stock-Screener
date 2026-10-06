import { NextRequest, NextResponse } from "next/server";

const FMP_BASE = "https://financialmodelingprep.com/stable";

// Allowlist (2026-10-06): this route used to forward ANY ?e= endpoint with the server key,
// unauthenticated — anyone could spend the plan through it. Only the endpoints the UI calls:
//   batch-quote            page.tsx, basket, performance, Watchlist, SpeculairTracker
//   stock-price-change     briefing route
//   historical-price-eod/* briefing route (^GSPC), stock chart tab
//   price-target-latest-news, senate-latest, house-latest   briefing route
//   statements/ratios/key-metrics/ratios-ttm/analyst-estimates/news/stock   stock page
// Add an endpoint here when a page needs it — never forward arbitrary paths.
const ALLOWED_ENDPOINTS = new Set([
  "batch-quote",
  "stock-price-change",
  "historical-price-eod/full",
  "historical-price-eod/light",
  "price-target-latest-news",
  "senate-latest",
  "house-latest",
  "income-statement",
  "balance-sheet-statement",
  "cash-flow-statement",
  "ratios",
  "ratios-ttm",
  "key-metrics",
  "analyst-estimates",
  "news/stock",
]);
// `t` is the performance page's cache-buster (fresh quotes, bypasses the 300s data cache).
const ALLOWED_PARAMS = new Set(["symbol", "symbols", "period", "limit", "page", "from", "to", "t"]);
const MAX_LIMIT = 1000;   // briefing pulls price-target-latest-news at limit=1000

export async function GET(req: NextRequest) {
  const apiKey = process.env.FMP_API_KEY;
  if (!apiKey) return NextResponse.json({ error: "FMP_API_KEY not set" }, { status: 500 });

  const url = new URL(req.url);
  const endpoint = url.searchParams.get("e");
  if (!endpoint) return NextResponse.json({ error: "missing ?e=endpoint" }, { status: 400 });
  if (!ALLOWED_ENDPOINTS.has(endpoint)) return NextResponse.json({ error: "endpoint not allowed" }, { status: 403 });

  // Forward only known params; anything else is dropped.
  const params = new URLSearchParams();
  url.searchParams.forEach((value, name) => {
    if (ALLOWED_PARAMS.has(name)) params.set(name, value);
  });
  const limit = params.get("limit");
  if (limit !== null) {
    const n = Number(limit);
    if (!Number.isFinite(n) || n < 1) params.delete("limit");
    else params.set("limit", String(Math.min(Math.floor(n), MAX_LIMIT)));
  }
  params.set("apikey", apiKey);

  try {
    const res = await fetch(`${FMP_BASE}/${endpoint}?${params}`, { next: { revalidate: 300 } });
    const data = await res.json();
    return NextResponse.json(data);
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 502 });
  }
}
