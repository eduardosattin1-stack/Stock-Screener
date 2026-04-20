// Dedicated server route for the Company Profile card.
//
// Fetches four FMP endpoints in parallel (profile, shares-float, 13F top holders,
// positions summary) and returns a single aggregated response. This bypasses the
// generic /api/fmp proxy to avoid any endpoint-allow-list friction and reduces
// the round-trips from 4 to 1 from the browser.
//
// Called from CompanyProfileCard as: GET /api/company/{symbol}
const FMP_BASE = "https://financialmodelingprep.com/stable";
const FMP_KEY = process.env.FMP_API_KEY || "18kyMYWfzP8U5tMsBkk5KDzeGKERr5rA";

async function fmpGet(endpoint: string, params: Record<string, string | number>) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => qs.set(k, String(v)));
  qs.set("apikey", FMP_KEY);
  try {
    const r = await fetch(`${FMP_BASE}/${endpoint}?${qs}`, {
      next: { revalidate: 3600 }, // cache 1hr — company profile data is stable
    });
    if (!r.ok) return null;
    const d = await r.json();
    return Array.isArray(d) ? d : d ? [d] : null;
  } catch {
    return null;
  }
}

export async function GET(_req: Request, ctx: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await ctx.params;
  const sym = (symbol || "").toUpperCase().replace(/[^A-Z0-9.\-]/g, "");
  if (!sym) return new Response("symbol required", { status: 400 });

  // Latest completed quarter with 45d 13F lag accommodation.
  const now = new Date();
  const q = Math.floor(now.getMonth() / 3) + 1;
  const year13f = q === 1 ? now.getFullYear() - 1 : now.getFullYear();
  const quarter13f = q === 1 ? 4 : q - 1;

  const [profileArr, floatArr, holdersArr, positionsArr] = await Promise.all([
    fmpGet("profile-symbol", { symbol: sym }),
    fmpGet("shares-float", { symbol: sym }),
    fmpGet("filings-extract-with-analytics-by-holder",
      { symbol: sym, year: year13f, quarter: quarter13f, limit: 10 }),
    fmpGet("positions-summary",
      { symbol: sym, year: year13f, quarter: quarter13f }),
  ]);

  const body = {
    symbol: sym,
    profile: profileArr?.[0] ?? null,
    float: floatArr?.[0] ?? null,
    holders: holdersArr ?? [],
    positions: positionsArr?.[0] ?? null,
    quarter: { year: year13f, quarter: quarter13f },
  };

  return new Response(JSON.stringify(body), {
    status: 200,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "public, s-maxage=3600, stale-while-revalidate=7200",
    },
  });
}

export const runtime = "nodejs";
