import { NextRequest, NextResponse } from "next/server";
import { Storage } from "@google-cloud/storage";

export const dynamic = "force-dynamic";

// Initialize Storage with the environment variables added to Vercel
const storage = new Storage({
  projectId: process.env.GCP_PROJECT_ID,
  credentials: {
    client_email: process.env.GCP_CLIENT_EMAIL,
    // Format the private key for Vercel
    private_key: process.env.GCP_PRIVATE_KEY?.replace(/\\n/g, '\n'),
  },
});

const bucketName = process.env.GCP_BUCKET_NAME || 'screener-signals-carbonbridge';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const objectPath = path.join("/");
  
  try {
    const bucket = storage.bucket(bucketName);
    const file = bucket.file(objectPath);
    
    // Check if file exists first
    const [exists] = await file.exists();
    if (!exists) {
      return new NextResponse("Not Found", { status: 404 });
    }
    
    // Download file content
    const [content] = await file.download();
    
    // Determine content type
    let contentType = "application/json";
    if (objectPath.endsWith(".html")) {
      contentType = "text/html";
    } else if (objectPath.endsWith(".txt")) {
      contentType = "text/plain";
    }
    
    return new NextResponse(new Uint8Array(content), {
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
    console.error(`GCS Proxy GET Error for ${objectPath}:`, error.message);
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

