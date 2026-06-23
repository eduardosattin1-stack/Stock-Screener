// Vercel API proxy → Cloud Run /performance/calibration-v2
// Serves the precomputed calibration-v2 summary.json verbatim (single GCS
// read on the backend): expected-vs-observed touch headline, per-decile
// censoring-aware calibration, nightly touch curves, per-record list.
const CLOUD_RUN = "https://stock-screener-606056076947.europe-west1.run.app";

export async function GET() {
  try {
    const res = await fetch(`${CLOUD_RUN}/performance/calibration-v2`, {
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
