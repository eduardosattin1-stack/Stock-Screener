import { NextResponse } from "next/server";

export async function GET() {
  try {
    const res = await fetch("http://127.0.0.1:8080/briefing", {
      next: { revalidate: 60 },
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
      { error: "Failed to fetch daily briefing from backend", details: err.message },
      { status: 500 }
    );
  }
}
