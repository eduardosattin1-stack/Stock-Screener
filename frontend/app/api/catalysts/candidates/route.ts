import { NextResponse } from "next/server";
export const maxDuration = 60;

const CLOUD_RUN = "https://stock-screener-606056076947.europe-west1.run.app";

export async function GET() {
  try {
    const res = await fetch(`${CLOUD_RUN}/catalysts/candidates`, {
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
      { error: "Failed to fetch catalyst candidates from backend", details: err.message },
      { status: 500 }
    );
  }
}
