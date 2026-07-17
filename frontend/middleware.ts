import { NextRequest, NextResponse } from "next/server";

// Host-based split for the public marketing domain. When speculair.* (any TLD —
// buy whichever is available) is pointed at this Vercel project, its ROOT serves
// the /welcome landing page while every other path still reaches the app. The
// app's existing vercel.app URL is unaffected: this only rewrites "/" and only
// for hosts that look like the marketing domain.
const MARKETING_HOST_RE = /^(www\.)?speculair\.[a-z.]+$/i;

export function middleware(req: NextRequest) {
  const host = (req.headers.get("host") || "").split(":")[0];
  if (MARKETING_HOST_RE.test(host)) {
    return NextResponse.rewrite(new URL("/welcome", req.url));
  }
  return NextResponse.next();
}

// Only run on the root path — zero overhead anywhere else.
export const config = { matcher: "/" };
