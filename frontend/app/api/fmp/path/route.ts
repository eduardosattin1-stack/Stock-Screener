// app/api/fmp/[...path]/route.ts
import { NextRequest, NextResponse } from "next/server";

const FMP_BASE = "https://financialmodelingprep.com/stable";

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const apiKey = process.env.FMP_API_KEY;
  if (!apiKey) {
    return NextResponse.json({ error: "FMP_API_KEY not set" }, { status: 500 });
  }

  const { path } = await params;
  const endpoint = path.join("/");
  const searchParams = new URL(req.url).searchParams;
  searchParams.set("apikey", apiKey);

  const url = `${FMP_BASE}/${endpoint}?${searchParams.toString()}`;

  try {
    const res = await fetch(url, { next: { revalidate: 300 } });
    const data = await res.json();
    return NextResponse.json(data, {
      headers: { "Cache-Control": "public, s-maxage=300, stale-while-revalidate=600" },
    });
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 502 });
  }
}
