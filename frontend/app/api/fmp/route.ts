import { NextRequest, NextResponse } from "next/server";

const FMP_BASE = "https://financialmodelingprep.com/stable";

export async function GET(req: NextRequest) {
  const apiKey = process.env.FMP_API_KEY;
  if (!apiKey) return NextResponse.json({ error: "FMP_API_KEY not set" }, { status: 500 });

  const url = new URL(req.url);
  const endpoint = url.searchParams.get("e");
  if (!endpoint) return NextResponse.json({ error: "missing ?e=endpoint" }, { status: 400 });

  const params = new URLSearchParams(url.search);
  params.delete("e");
  params.set("apikey", apiKey);

  try {
    const res = await fetch(`${FMP_BASE}/${endpoint}?${params}`, { next: { revalidate: 300 } });
    const data = await res.json();
    return NextResponse.json(data);
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 502 });
  }
}
