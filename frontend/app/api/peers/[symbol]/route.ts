// Dedicated server route for the Peer Comparison panel on the stock detail page.
//
// Fan-out: 1 call to /stable/stock-peers gets the peer list, then in parallel
// we pull /stable/ratios-ttm for the target stock + every peer. Each TTM row
// gives us P/E, P/S, P/B, P/FCF and enterpriseValueMultipleTTM (= EV/EBITDA
// TTM) in a single payload.
//
// IMPORTANT (May 2026 fix): the FMP stable REST endpoint slugs are
//   /stable/stock-peers   (NOT /stable/peers — that 404s)
//   /stable/ratios-ttm    (NOT /stable/metrics-ratios-ttm — that 404s)
// The FMP MCP tool uses different friendly names internally (peers,
// metrics-ratios-ttm) which don't correspond to the actual REST paths.
// Always verify endpoints by fetching the docs page directly rather than
// trusting MCP parameter names.
//
// Called from PeersPanel as: GET /api/peers/{symbol}
//
// Returns: { symbol, target: PeerRow|null, peers: PeerRow[], errors? }
//   PeerRow = { symbol, companyName, mktCap, pe, ps, pb, pfcf, evEbitda }
//
// Caching: 1h browser/edge cache. Peer list is stable; TTM ratios update at
// most daily. If the upstream peers call fails we surface the error and
// return an empty peers list (panel will hide itself rather than render junk).

const FMP_STABLE = "https://financialmodelingprep.com/stable";
const FMP_KEY = process.env.FMP_API_KEY || "18kyMYWfzP8U5tMsBkk5KDzeGKERr5rA";

const MAX_PEERS = 8;

type FmpResult<T> = { data: T[] | null; error: string | null };

async function fmpGet<T = unknown>(
  endpoint: string,
  params: Record<string, string | number>,
): Promise<FmpResult<T>> {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => qs.set(k, String(v)));
  qs.set("apikey", FMP_KEY);
  const url = `${FMP_STABLE}/${endpoint}?${qs}`;
  try {
    const r = await fetch(url, { next: { revalidate: 3600 } } as RequestInit);
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

// Shape of ratios-ttm rows we care about. FMP returns dozens of fields per
// row but we only use these five.
type TtmRow = {
  symbol?: string;
  priceToEarningsRatioTTM?: number;
  priceToSalesRatioTTM?: number;
  priceToBookRatioTTM?: number;
  priceToFreeCashFlowRatioTTM?: number;
  enterpriseValueMultipleTTM?: number; // EV/EBITDA TTM
};

type PeerListRow = {
  symbol?: string;
  companyName?: string;
  mktCap?: number;
};

type PeerRow = {
  symbol: string;
  companyName: string;
  mktCap: number;
  pe: number | null;
  ps: number | null;
  pb: number | null;
  pfcf: number | null;
  evEbitda: number | null;
};

// FMP sometimes returns 0 for a metric instead of null when the underlying
// computation is undefined (e.g. negative earnings). Treat 0 and negatives as
// null so they don't pollute the median or render as misleadingly low values.
function safe(v: number | undefined | null): number | null {
  if (v == null || !isFinite(v) || v <= 0) return null;
  return v;
}

function toRow(symbol: string, name: string, mktCap: number, ttm: TtmRow | null): PeerRow {
  return {
    symbol,
    companyName: name,
    mktCap,
    pe:       safe(ttm?.priceToEarningsRatioTTM),
    ps:       safe(ttm?.priceToSalesRatioTTM),
    pb:       safe(ttm?.priceToBookRatioTTM),
    pfcf:     safe(ttm?.priceToFreeCashFlowRatioTTM),
    evEbitda: safe(ttm?.enterpriseValueMultipleTTM),
  };
}

export async function GET(_req: Request, ctx: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await ctx.params;
  const sym = (symbol || "").toUpperCase().replace(/[^A-Z0-9.\-]/g, "");
  if (!sym) return new Response("symbol required", { status: 400 });

  // 1. Get peer list. If this fails the whole panel gracefully degrades.
  const peersRes = await fmpGet<PeerListRow>("stock-peers", { symbol: sym });
  const errors: Record<string, string> = {};
  if (peersRes.error) errors.peers = peersRes.error;

  // Top-N peers by market cap. peers endpoint already returns mktCap so we
  // can sort here without additional calls. Filter out entries with missing
  // symbol or non-positive mktCap (FMP occasionally returns delisted shells).
  const rawPeers = (peersRes.data ?? [])
    .filter((p) => p.symbol && (p.mktCap ?? 0) > 0)
    .sort((a, b) => (b.mktCap ?? 0) - (a.mktCap ?? 0))
    .slice(0, MAX_PEERS);

  // 2. Fetch TTM ratios for target + all peers in parallel.
  const allSymbols = [sym, ...rawPeers.map((p) => p.symbol!)];
  const ttmResults = await Promise.all(
    allSymbols.map((s) => fmpGet<TtmRow>("ratios-ttm", { symbol: s })),
  );
  const ttmBySymbol = new Map<string, TtmRow>();
  ttmResults.forEach((r, i) => {
    const s = allSymbols[i];
    const row = r.data?.[0];
    if (row) ttmBySymbol.set(s, row);
  });

  // 3. Build target row. We need the company name + mktCap. peers endpoint
  // doesn't give those for the target itself, but the panel doesn't strictly
  // need them — page already shows the company name. We pass an empty name
  // and 0 mktCap; the client can fill in from its existing stock state.
  const target: PeerRow = toRow(sym, "", 0, ttmBySymbol.get(sym) ?? null);

  // 4. Build peer rows. Drop peers that returned no TTM data at all (no point
  // showing a row of dashes — usually means the peer is too small or thinly
  // traded for FMP to compute multiples).
  const peers: PeerRow[] = rawPeers
    .map((p) =>
      toRow(p.symbol!, p.companyName || p.symbol!, p.mktCap ?? 0, ttmBySymbol.get(p.symbol!) ?? null),
    )
    .filter((p) => p.pe != null || p.ps != null || p.pb != null || p.pfcf != null || p.evEbitda != null);

  return new Response(
    JSON.stringify({
      symbol: sym,
      target,
      peers,
      ...(Object.keys(errors).length ? { errors } : {}),
    }),
    {
      status: 200,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "public, s-maxage=3600, stale-while-revalidate=7200",
      },
    },
  );
}

export const runtime = "nodejs";
