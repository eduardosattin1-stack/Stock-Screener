import { NextRequest, NextResponse } from "next/server";

// Same-origin proxy to the live Social Arb signal-engine backend (FastAPI on Cloud Run,
// europe-west1). The /social page calls /api/social/<path> and we forward to
// SOCIAL_API_URL/api/<path><querystring>. Keeps the page same-origin (no CORS / mixed-content),
// hides the upstream URL server-side, and leaves a clean seam to swap in a GCS snapshot later
// without touching the page. The URL is public (was NEXT_PUBLIC in the standalone dashboard),
// so we default to it and let an env var override per-environment.
export const dynamic = "force-dynamic";

const BASE =
  process.env.SOCIAL_API_URL ||
  "https://social-arb-backend-921050972210.europe-west1.run.app";

const upstream = (path: string[], search: string) =>
  `${BASE}/api/${path.join("/")}${search}`;

const passHeaders = {
  "Cache-Control": "no-cache, no-store, max-age=0, must-revalidate",
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const search = new URL(request.url).search;
  try {
    const res = await fetch(upstream(path, search), { cache: "no-store" });
    const body = await res.text();
    return new NextResponse(body, {
      status: res.status,
      headers: { "Content-Type": "application/json", ...passHeaders },
    });
  } catch (error: any) {
    console.error(`Social proxy GET ${path.join("/")}:`, error?.message);
    return NextResponse.json(
      { error: "social_upstream_unreachable", detail: error?.message ?? "" },
      { status: 502, headers: passHeaders }
    );
  }
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const search = new URL(request.url).search;
  try {
    const payload = await request.text();
    const res = await fetch(upstream(path, search), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: payload,
      cache: "no-store",
    });
    const body = await res.text();
    return new NextResponse(body, {
      status: res.status,
      headers: { "Content-Type": "application/json", ...passHeaders },
    });
  } catch (error: any) {
    console.error(`Social proxy POST ${path.join("/")}:`, error?.message);
    return NextResponse.json(
      { error: "social_upstream_unreachable", detail: error?.message ?? "" },
      { status: 502, headers: passHeaders }
    );
  }
}

export async function OPTIONS() {
  return new NextResponse(null, { status: 204, headers: passHeaders });
}
