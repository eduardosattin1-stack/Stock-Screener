// Per-symbol stock-row lookup — replaces the client downloading the FULL
// latest_global.json (~28MB, 2.5k names) on every stock-page view just to pick
// one row out of it.
//
// Data source: the public GCS URL (the scans bucket is world-readable), NOT
// the authenticated /api/gcs proxy — works identically on Vercel and local dev
// (where GCS credentials are absent). The scan updates once nightly.
//
// Caching, two layers:
//   1. Module-level in-memory cache of the parsed symbol->row map, TTL 15 min —
//      a warm serverless instance downloads/parses the 28MB file at most 4x/hr
//      regardless of how many stock pages are viewed. (Next's data cache can't
//      hold it: fetch responses >2MB are uncacheable, hence cache: "no-store" +
//      our own memory cache.)
//   2. CDN cache per symbol URL (s-maxage=900) — repeat views of the same
//      stock don't reach the function at all.
//
// Returns 200 {scan_date, stock} — stock null when the symbol isn't in the
// scan (a REAL answer: the client shows its debate-only / no-data view).
// Returns 502 only when GCS itself fails, so the client can fall back to its
// legacy full-download path.

const SCAN_URL = "https://storage.googleapis.com/screener-signals-carbonbridge/scans/latest_global.json";
const TTL_MS = 15 * 60 * 1000;

type ScanCache = { at: number; scanDate: string; bySymbol: Map<string, unknown> };
const g = globalThis as unknown as { __scanRowCache?: ScanCache | null; __scanRowPromise?: Promise<ScanCache> | null };

async function loadScan(): Promise<ScanCache> {
  const res = await fetch(SCAN_URL, { cache: "no-store" });
  if (!res.ok) throw new Error(`GCS ${res.status}`);
  const d = await res.json();
  const bySymbol = new Map<string, unknown>();
  for (const s of d?.stocks ?? []) {
    if (s?.symbol) bySymbol.set(String(s.symbol).toUpperCase(), s);
  }
  if (!bySymbol.size) throw new Error("scan JSON had no stocks");
  return { at: Date.now(), scanDate: d?.scan_date ?? "", bySymbol };
}

async function getScan(): Promise<ScanCache> {
  const c = g.__scanRowCache;
  if (c && Date.now() - c.at < TTL_MS) return c;
  // Single-flight: concurrent requests share one 28MB download.
  if (!g.__scanRowPromise) {
    g.__scanRowPromise = loadScan()
      .then((fresh) => { g.__scanRowCache = fresh; return fresh; })
      .finally(() => { g.__scanRowPromise = null; });
  }
  try {
    return await g.__scanRowPromise;
  } catch (e) {
    if (c) return c; // stale beats broken
    throw e;
  }
}

export async function GET(_req: Request, ctx: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await ctx.params;
  const sym = (symbol || "").toUpperCase().replace(/[^A-Z0-9.\-]/g, "");
  if (!sym) return new Response("symbol required", { status: 400 });

  let scan: ScanCache;
  try {
    scan = await getScan();
  } catch (e) {
    console.error(`stock-row: scan load failed: ${e instanceof Error ? e.message : e}`);
    return new Response(JSON.stringify({ error: "scan unavailable" }), {
      status: 502,
      headers: { "Content-Type": "application/json" },
    });
  }

  return new Response(
    JSON.stringify({ scan_date: scan.scanDate, stock: scan.bySymbol.get(sym) ?? null }),
    {
      status: 200,
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": "public, s-maxage=900, stale-while-revalidate=3600",
      },
    },
  );
}

export const runtime = "nodejs";
