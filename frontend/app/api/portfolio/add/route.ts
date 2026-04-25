// Vercel API proxy → Cloud Run /portfolio/add
// Frontend never touches Cloud Run directly (would hit CORS).
// Unauthenticated per user decision; endpoint is discoverable but low-value target.

const CLOUD_RUN = "https://stock-screener-606056076947.europe-west1.run.app";

export async function POST(req: Request) {
  let body: any;
  try {
    body = await req.json();
  } catch {
    return new Response("Invalid JSON body", { status: 400 });
  }

  const { symbol, entry_price, shares, notes, bucket } = body || {};
  if (!symbol || typeof symbol !== "string") return new Response("symbol required", { status: 400 });
  if (!entry_price || typeof entry_price !== "number" || entry_price <= 0) return new Response("entry_price required (positive number)", { status: 400 });
  if (shares == null || typeof shares !== "number" || shares <= 0) return new Response("shares required (positive number)", { status: 400 });
  // bucket is optional; must be "midcap" | "sp500" | null/undefined
  const validBucket = bucket === "midcap" || bucket === "sp500" ? bucket : null;

  try {
    const res = await fetch(`${CLOUD_RUN}/portfolio/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbol: symbol.toUpperCase().trim(),
        entry_price,
        shares,
        notes: (notes || "").slice(0, 200),
        bucket: validBucket,
      }),
    });
    const text = await res.text();
    if (!res.ok) return new Response(text || `Cloud Run ${res.status}`, { status: res.status });
    return new Response(text, { status: 200, headers: { "Content-Type": "application/json" } });
  } catch (e: any) {
    return new Response(`Proxy error: ${e?.message || e}`, { status: 502 });
  }
}

export const runtime = "nodejs";
