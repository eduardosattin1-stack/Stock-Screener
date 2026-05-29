// Vercel API proxy → Cloud Run /performance/method-tracks
// Returns per-regime, per-method aggregate stats + recent archived cycles
// for the four-method comparison view (stock × {30d, 60d}, long_call × {30d, 60d}).
const CLOUD_RUN = "https://stock-screener-606056076947.europe-west1.run.app";

export async function GET() {
  try {
    const res = await fetch(`${CLOUD_RUN}/performance/method-tracks`, {
      next: { revalidate: 60 },
    });
    const text = await res.text();
    if (!res.ok) return new Response(text || `Cloud Run ${res.status}`, { status: res.status });
    return new Response(text, { status: 200, headers: { "Content-Type": "application/json" } });
  } catch (e: any) {
    return new Response(`Proxy error: ${e?.message || e}`, { status: 502 });
  }
}

export const runtime = "nodejs";
