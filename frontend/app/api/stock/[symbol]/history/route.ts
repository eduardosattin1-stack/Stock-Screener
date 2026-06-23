// Vercel API proxy → Cloud Run /stock/{SYMBOL}/history
// Returns [[date, price, composite], ...] for the dual-line price+composite chart.
const CLOUD_RUN = "https://stock-screener-606056076947.europe-west1.run.app";

export async function GET(_req: Request, ctx: { params: Promise<{ symbol: string }> }) {
  const { symbol } = await ctx.params;
  const sym = (symbol || "").toUpperCase().replace(/[^A-Z0-9.\-]/g, "");
  if (!sym) return new Response("symbol required", { status: 400 });
  try {
    const res = await fetch(`${CLOUD_RUN}/stock/${sym}/history`, {
      next: { revalidate: 300 },
    });
    const text = await res.text();
    if (!res.ok) return new Response(text || `Cloud Run ${res.status}`, { status: res.status });
    return new Response(text, { status: 200, headers: { "Content-Type": "application/json" } });
  } catch (e: any) {
    return new Response(`Proxy error: ${e?.message || e}`, { status: 502 });
  }
}

export const runtime = "nodejs";
