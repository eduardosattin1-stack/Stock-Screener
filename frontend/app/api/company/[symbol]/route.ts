// Dedicated server route for the Company Profile card.
//
// Fetches FMP endpoints in parallel (profile, shares-float, 13F top holders,
// positions summary) and returns a single aggregated response. This bypasses
// the generic /api/fmp proxy to avoid any endpoint-allow-list friction and
// reduces the round-trips from 4 to 1 from the browser.
//
// Called from CompanyProfileCard as: GET /api/company/{symbol}
//
// -- v7.3 FIX (Track C.1) ----------------------------------------------------
// Previous revision silently returned `{profile: null}` whenever the FMP
// profile call failed (429 rate limit, transient 5xx, cold-start race) AND
// cached that null for 3600s via Next's data cache. Users then saw
// "No profile data available" on the stock page for an hour with no way to
// tell why. Fixes applied:
//   1. `profile-symbol` fetched with `cache: "no-store"` -- never cache a
//      null profile. Float / 13F calls keep the 1h revalidate.
//   2. Per-endpoint failure reported in `errors{}` on the response body.
//   3. FMP's {"Error Message": ...} shape is unwrapped as an error rather
//      than passed through as data.
//   4. Server-side `console.error` on each failure for Vercel log triage.
//
// -- v7.3b FIX (Track C.1b) --------------------------------------------------
// Production logs confirmed the deployed FMP key returns HTTP 404 for three
// endpoints (profile-symbol, filings-extract-with-analytics-by-holder,
// positions-summary) while shares-float works -- classic FMP plan-tier split.
// The profile endpoint's "profile-symbol" path is newer and more plan-gated;
// two legacy endpoints return the same payload under broader plan access.
// This revision widens profile fetching to a fallback chain:
//     /stable/profile-symbol?symbol=X   (original)
//     /stable/profile?symbol=X          (alternative on /stable)
//     /api/v3/profile/{X}               (legacy v3)
// First endpoint returning a non-empty payload wins. Each attempt is logged
// to `errors.profile_attempts` for diagnosis. Holders/positions have no
// lower-tier alternatives and already degrade cleanly when null.
const FMP_STABLE = "https://financialmodelingprep.com/stable";
const FMP_V3 = "https://financialmodelingprep.com/api/v3";
const FMP_KEY = process.env.FMP_API_KEY || "18kyMYWfzP8U5tMsBkk5KDzeGKERr5rA";

type FmpResult<T> = { data: T[] | null; error: string | null };

async function fmpGetFrom<T = unknown>(
  base: string,
  endpoint: string,
  params: Record<string, string | number>,
  opts: { noStore?: boolean } = {},
): Promise<FmpResult<T>> {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => qs.set(k, String(v)));
  qs.set("apikey", FMP_KEY);
  const url = `${base}/${endpoint}?${qs}`;
  try {
    const init: RequestInit = opts.noStore
      ? { cache: "no-store" }
      : ({ next: { revalidate: 3600 } } as RequestInit);
    const r = await fetch(url, init);
    if (!r.ok) {
      const msg = `FMP ${endpoint} HTTP ${r.status}`;
      console.error(msg);
      return { data: null, error: msg };
    }
    const d = await r.json();
    if (d && !Array.isArray(d) && typeof d === "object" && "Error Message" in d) {
      const em = String((d as { "Error Message": unknown })["Error Message"]);
      console.error(`FMP ${endpoint} error: ${em}`);
      return { data: null, error: `FMP error: ${em.slice(0, 120)}` };
    }
    if (Array.isArray(d)) return { data: d as T[], error: null };
    if (d) return { data: [d as T], error: null };
    return { data: null, error: `FMP ${endpoint} empty response` };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    console.error(`FMP ${endpoint} threw: ${msg}`);
    return { data: null, error: `fetch failed: ${msg.slice(0, 120)}` };
  }
}

async function fmpGet<T = unknown>(
  endpoint: string,
  params: Record<string, string | number>,
  opts: { noStore?: boolean } = {},
): Promise<FmpResult<T>> {
  return fmpGetFrom<T>(FMP_STABLE, endpoint, params, opts);
}

/**
 * Try a chain of profile endpoints until one returns data.
 * Returns the first success, or a consolidated error + attempt log.
 */
async function fmpProfileChain(
  sym: string,
): Promise<FmpResult<Record<string, unknown>> & { attempts: string[] }> {
  const attempts: string[] = [];
  const tries: Array<{
    label: string;
    base: string;
    endpoint: string;
    params: Record<string, string | number>;
  }> = [
    { label: "stable/profile-symbol", base: FMP_STABLE, endpoint: "profile-symbol", params: { symbol: sym } },
    { label: "stable/profile",        base: FMP_STABLE, endpoint: "profile",        params: { symbol: sym } },
    { label: "v3/profile",            base: FMP_V3,     endpoint: `profile/${encodeURIComponent(sym)}`, params: {} },
  ];
  for (const t of tries) {
    const r = await fmpGetFrom<Record<string, unknown>>(t.base, t.endpoint, t.params, { noStore: true });
    if (r.data && r.data.length > 0) {
      const first = r.data[0];
      if (first && typeof first === "object" && !("_source" in first)) {
        (first as Record<string, unknown>)._source = t.label;
      }
      return { data: r.data, error: null, attempts: [...attempts, `${t.label}: ok`] };
    }
    attempts.push(`${t.label}: ${r.error ?? "empty"}`);
  }
  return { data: null, error: "all profile endpoints failed", attempts };
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

  const [profileRes, floatRes, holdersRes, positionsRes] = await Promise.all([
    fmpProfileChain(sym),
    fmpGet<Record<string, unknown>>("shares-float", { symbol: sym }),
    fmpGet<Record<string, unknown>>(
      "filings-extract-with-analytics-by-holder",
      { symbol: sym, year: year13f, quarter: quarter13f, limit: 10 },
    ),
    fmpGet<Record<string, unknown>>(
      "positions-summary",
      { symbol: sym, year: year13f, quarter: quarter13f },
    ),
  ]);

  const errors: Record<string, string | string[]> = {};
  if (profileRes.error) {
    errors.profile = profileRes.error;
    errors.profile_attempts = profileRes.attempts;
  }
  if (floatRes.error) errors.float = floatRes.error;
  if (holdersRes.error) errors.holders = holdersRes.error;
  if (positionsRes.error) errors.positions = positionsRes.error;

  const body = {
    symbol: sym,
    profile: profileRes.data?.[0] ?? null,
    float: floatRes.data?.[0] ?? null,
    holders: holdersRes.data ?? [],
    positions: positionsRes.data?.[0] ?? null,
    quarter: { year: year13f, quarter: quarter13f },
    ...(Object.keys(errors).length ? { errors } : {}),
  };

  const profileFailed = !body.profile;
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  headers["Cache-Control"] = profileFailed
    ? "no-store, max-age=0"
    : "public, s-maxage=3600, stale-while-revalidate=7200";

  return new Response(JSON.stringify(body), { status: 200, headers });
}

export const runtime = "nodejs";
