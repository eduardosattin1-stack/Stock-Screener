import { NextRequest, NextResponse } from "next/server";

export const maxDuration = 60;

const CLOUD_RUN = "https://stock-screener-606056076947.europe-west1.run.app";

export async function GET(req: NextRequest) {
  const symbol = new URL(req.url).searchParams.get("symbol");
  if (!symbol) return NextResponse.json({ error: "symbol required" }, { status: 400 });

  try {
    const res = await fetch(`${CLOUD_RUN}/transcript?symbol=${symbol}`, {
      signal: AbortSignal.timeout(55000),
    });
    const text = await res.text();
    try {
      return NextResponse.json(JSON.parse(text));
    } catch {
      return NextResponse.json({ error: `Cloud Run returned status ${res.status}. Check /transcript endpoint.` }, { status: 502 });
    }
  } catch (e: any) {
    if (e.name === "TimeoutError" || e.name === "AbortError") {
      return NextResponse.json({ error: "Transcript analysis timed out (55s). Vercel Pro allows 60s, Hobby caps at 10s." }, { status: 504 });
    }
    return NextResponse.json({ error: e.message }, { status: 502 });
  }
}
