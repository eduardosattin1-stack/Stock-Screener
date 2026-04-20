// Vercel API proxy → Cloud Run /performance/signal-tracks
// Reads GCS-backed signal_tracking open+closed lists.
const CLOUD_RUN = "https://stock-screener-606056076947.europe-west1.run.app";

export async function GET() {
  try {
    const res = await fetch(`${CLOUD_RUN}/performance/signal-tracks`, {
      // revalidate at most every 60s to match Cloud Run's Cache-Control
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
