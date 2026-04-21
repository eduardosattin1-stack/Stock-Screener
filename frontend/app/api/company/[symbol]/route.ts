// Dedicated server route for the Company Profile card.
//
// Fetches four FMP endpoints in parallel (profile, shares-float, 13F top holders,
// positions summary) and returns a single aggregated response. This bypasses the
// generic /api/fmp proxy to avoid any endpoint-allow-list friction and reduces
// the round-trips from 4 to 1 from the browser.
//
// Called from CompanyProfileCard as: GET /api/company/{symbol}
//
// ── v7.3 FIX (Track C.1) ────────────────────────────────────────────────────
// Previous revision silently returned `{profile: null}` whenever the FMP
// profile call failed (429 rate limit, transient 5xx, cold-start race) AND
// cached that null for 3600s via Next's data cache. Users then saw
// "No profile data available" on the stock page for an hour with no way to
// tell why. Fixes applied here:
//
//  1. `profile-symbol` is now fetched with `cache: "no-store"` — we never
//     want to cache a null profile. Float / 13F calls keep the 1h revalidate
//     because they are stable and cheaper to replay.
//  2. Per-endpoint failure is captured and reported in `errors{}` on the
//     response body, so the client can render a useful diagnostic
//     ("FMP 429 rate limited") and offer a Retry button instead of rendering
//     a dead card.
//  3. When an FMP call returns a non-array object with an `Error Message`
//     field (FMP's error shape on some endpoints), we unwrap it as an error
//     rather than silently passing the error object through as data.
//  4. Server-side logging of failures via `console.error` so Vercel function
//     logs surface the root cause.
//
// The response shape is a superset of the old shape — `profile`, `float`,
// `holders`, `positions`, `quarter` are unchanged. A new optional `errors`
// object carries per-endpoint diagnostics. Old clients ignoring `errors`
// continue to work.
const FMP_BASE = "https://financialmodelingprep.com/stable";
const FMP_KEY = process.env.FMP_API_KEY || "18kyMYWfzP8U5tMsBkk5KDzeGKERr5rA";

type FmpResult<T> = { data: T[] | null; error: string | null };

async function fmpGet<T = unknown>(
  endpoint: string,
  params: Record<string, string | number>,
  opts: { noStore?: boolean } = {},
): Promise<FmpResult<T>> {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => qs.set(k, String(v)));
  qs.set("apikey", FMP_KEY);
  const url = `${FMP_BASE}/${endpoint}?${qs}`;
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

export async function GET(_req: Request, ctx: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await ctx.params;
  const sym = (symbol || "").toUpperCase().replace(/[^A-Z0-9.\-]/g, "");
  if (!sym) return new Response("symbol required", { status: 400 });

  // Latest completed quarter with 45d 13F lag accommodation.
  const now = new Date();
  const q = Math.floor(now.getMonth() / 3) + 1;
  const year13f = q === 1 ? now.getFullYear() - 1 : now.getFullYear();
  const quarter13f = q === 1 ? 4 : q - 1;

  // Profile is the critical path for the card — NEVER cache a failure.
  // Float / 13F are stable; cache them 1h.
  const [profileRes, floatRes, holdersRes, positionsRes] = await Promise.all([
    fmpGet<Record<string, unknown>>("profile-symbol", { symbol: sym }, { noStore: true }),
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

  const errors: Record<string, string> = {};
  if (profileRes.error) errors.profile = profileRes.error;
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

  // If profile failed specifically, return 200 with error info but instruct
  // caches NOT to persist. Downstream CDNs shouldn't save a bricked card.
  const profileFailed = !body.profile;
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  headers["Cache-Control"] = profileFailed
    ? "no-store, max-age=0"
    : "public, s-maxage=3600, stale-while-revalidate=7200";

  return new Response(JSON.stringify(body), { status: 200, headers });
}

export const runtime = "nodejs";
