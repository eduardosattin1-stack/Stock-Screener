// Vercel API proxy → Cloud Run /portfolio/close

const CLOUD_RUN = "https://stock-screener-606056076947.europe-west1.run.app";

export async function POST(req: Request) {
  let body: any;
  try {
    body = await req.json();
  } catch {
    return new Response("Invalid JSON body", { status: 400 });
  }

  const { symbol, exit_price, reason } = body || {};
  if (!symbol || typeof symbol !== "string") return new Response("symbol required", { status: 400 });
  if (!exit_price || typeof exit_price !== "number" || exit_price <= 0) return new Response("exit_price required (positive number)", { status: 400 });

  try {
    const res = await fetch(`${CLOUD_RUN}/portfolio/close`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbol: symbol.toUpperCase().trim(),
        exit_price,
        reason: (reason || "User close").slice(0, 200),
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
