import { NextResponse, NextRequest } from "next/server";
export const maxDuration = 180; // a full Loeb scan (Sonnet, up to ~90s) must outlast the route

const CLOUD_RUN = "https://stock-screener-606056076947.europe-west1.run.app";

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const symbol = searchParams.get("symbol") || "";
    const refresh = searchParams.get("refresh") || "";
    
    if (!symbol) {
      return NextResponse.json(
        { error: "Missing symbol parameter" },
        { status: 400 }
      );
    }
    
    const backendUrl = `${CLOUD_RUN}/catalysts/scan?symbol=${encodeURIComponent(symbol)}${refresh ? `&refresh=${encodeURIComponent(refresh)}` : ""}`;
    const res = await fetch(backendUrl, {
      cache: "no-store",
    });
    
    if (!res.ok) {
      return NextResponse.json(
        { error: `Backend returned ${res.status}` },
        { status: res.status }
      );
    }
    
    const data = await res.json();
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json(
      { error: "Failed to fetch catalyst scan from backend", details: err.message },
      { status: 500 }
    );
  }
}
