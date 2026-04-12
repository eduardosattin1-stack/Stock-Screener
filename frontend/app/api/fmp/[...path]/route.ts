// app/api/fmp/[...path]/route.ts
import { NextRequest, NextResponse } from "next/server";

const FMP_BASE = "https://financialmodelingprep.com/stable";

export async function GET(req: NextRequest) {
  const apiKey = process.env.FMP_API_KEY;
  if (!apiKey) {
    return NextResponse.json({ error: "FMP_API_KEY not set" }, { status: 500 });
  }

  // Extract path from URL instead of params
  const url = new URL(req.url);
  const fullPath = url.pathname.replace("/api/fmp/", "");
  const searchParams = new URLSearchParams(url.search);
  searchParams.set("apikey", apiKey);

  const fmpUrl = `${FMP_BASE}/${fullPath}?${searchParams.toString()}`;

  try {
    const res = await fetch(fmpUrl, { next: { revalidate: 300 } });
    const data = await res.json();
    return NextResponse.json(data, {
      headers: { "Cache-Control": "public, s-maxage=300, stale-while-revalidate=600" },
    });
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 502 });
  }
}