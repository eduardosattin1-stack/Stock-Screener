import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";


export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const objectPath = path.join("/");
  const encodedPath = encodeURIComponent(objectPath);
  const bucket = "screener-signals-carbonbridge";
  
  // Use www.googleapis.com to bypass CDN/edge cache
  const url = `https://www.googleapis.com/storage/v1/b/${bucket}/o/${encodedPath}?alt=media`;
  
  try {
    const res = await fetch(url, {
      method: "GET",
      cache: "no-store",
    });
    
    if (!res.ok) {
      return new NextResponse(res.statusText, { status: res.status });
    }
    
    const contentType = res.headers.get("content-type") || "application/json";
    const body = await res.arrayBuffer();
    
    return new NextResponse(body, {
      status: 200,
      headers: {
        "Content-Type": contentType,
        "Cache-Control": "no-cache, no-store, max-age=0, must-revalidate",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
      },
    });
  } catch (error: any) {
    return new NextResponse(error.message || "Internal Server Error", { status: 500 });
  }
}

export async function OPTIONS() {
  return new NextResponse(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    },
  });
}
