import { NextRequest, NextResponse } from "next/server";
import { Storage } from "@google-cloud/storage";

// Social Arb data path. The old Cloud Run FastAPI backend is gone (that URL now serves another app),
// and Social Arb now runs locally + publishes a denormalized snapshot to GCS (scans/social_arb.json,
// written by backend/publish_gcs.py). This route reads that snapshot and serves the slices the /social
// page expects, so the page is UNCHANGED. Endpoints not in the snapshot (drill-downs, themes, resolver,
// backtest) degrade to empties — the page .catches them. If SOCIAL_API_URL is ever set again, we fall
// back to proxying it for paths the snapshot can't serve.
export const dynamic = "force-dynamic";

const storage = new Storage({
  projectId: process.env.GCP_PROJECT_ID,
  credentials: {
    client_email: process.env.GCP_CLIENT_EMAIL,
    private_key: process.env.GCP_PRIVATE_KEY?.replace(/\\n/g, "\n"),
  },
});
const bucketName = process.env.GCP_BUCKET_NAME || "screener-signals-carbonbridge";
const BLOB = "scans/social_arb.json";
const LEGACY = process.env.SOCIAL_API_URL || "";

const passHeaders = {
  "Content-Type": "application/json",
  "Cache-Control": "no-cache, no-store, max-age=0, must-revalidate",
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

const json = (data: unknown, status = 200) =>
  new NextResponse(JSON.stringify(data), { status, headers: passHeaders });

async function readSnapshot(): Promise<any | null> {
  try {
    const file = storage.bucket(bucketName).file(BLOB);
    const [exists] = await file.exists();
    if (!exists) return null;
    const [content] = await file.download();
    return JSON.parse(content.toString("utf-8"));
  } catch (e: any) {
    console.error("social snapshot read failed:", e?.message);
    return null;
  }
}

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const p = path.join("/");
  const q = new URL(request.url).searchParams;
  const snap = await readSnapshot();

  // --- signals board ---
  if (p === "signals") {
    let sigs: any[] = (snap?.signals ?? []) as any[];
    const status = q.get("status");
    const track = q.get("track");
    const limit = parseInt(q.get("limit") || "100", 10);
    if (status) sigs = sigs.filter((s) => (s.status || "new") === status);
    if (track) sigs = sigs.filter((s) => (s.signal_track || "") === track);
    return json(sigs.slice(0, Number.isFinite(limit) ? limit : 100));
  }
  if (p === "stats") return json(snap?.stats ?? {});
  if (p === "backtest") return json(snap?.backtest ?? {});
  if (p === "themes") return json(snap?.themes ?? []);
  if (p === "resolver/health") return json(snap?.resolver ?? {});

  // --- single signal detail ---
  if (/^signals\/\d+$/.test(p)) {
    const id = Number(p.split("/")[1]);
    const found = (snap?.signals ?? []).find((s: any) => s.id === id);
    return found ? json(found) : json({ error: "not_found" }, 404);
  }

  // --- per-entity drill-downs not in the snapshot → graceful empties (page handles) ---
  if (p.startsWith("entities/")) {
    if (p.endsWith("/intent") || p.endsWith("/mentions")) return json([]);
    return json([]); // history / other
  }

  return json([]);
}

// Verdict write-back can't persist without a live backend; accept it so the UI doesn't error.
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  return json({ status: "ok", persisted: false, note: "read-only GCS snapshot", path: path.join("/") });
}

export async function OPTIONS() {
  return new NextResponse(null, { status: 204, headers: passHeaders });
}
