import { NextRequest, NextResponse } from "next/server";

const CLOUD_RUN = "https://stock-screener-606056076947.europe-west1.run.app";

export async function GET(req: NextRequest) {
  const symbol = new URL(req.url).searchParams.get("symbol");
  if (!symbol) return NextResponse.json({ error: "symbol required" }, { status: 400 });

  try {
    const res = await fetch(`${CLOUD_RUN}/transcript?symbol=${symbol}`, { next: { revalidate: 3600 } });
    const data = await res.json();
    return NextResponse.json(data);
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 502 });
  }
}
