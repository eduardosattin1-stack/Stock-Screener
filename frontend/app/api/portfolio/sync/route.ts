import { NextResponse } from 'next/server';
import { Storage } from '@google-cloud/storage';

// 1. Initialize Storage with the environment variables you added to Vercel
const storage = new Storage({
  projectId: process.env.GCP_PROJECT_ID,
  credentials: {
    client_email: process.env.GCP_CLIENT_EMAIL,
    // CRITICAL: We must fix the formatting of the private key for Vercel
    private_key: process.env.GCP_PRIVATE_KEY?.replace(/\\n/g, '\n'),
  },
});

// 2. Use the variable from Vercel or fall back to your hardcoded name
const bucketName = process.env.GCP_BUCKET_NAME || 'screener-signals-carbonbridge';

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const bucket = storage.bucket(bucketName);
    const file = bucket.file('portfolio/state.json');

    // Upload the structured JSON exactly how monitor_v7.py expects it
    await file.save(JSON.stringify(body, null, 2), {
      metadata: {
        contentType: 'application/json',
        cacheControl: 'no-cache',
      },
      resumable: false,
    });

    return NextResponse.json({ success: true });
  } catch (error: any) {
    // This will now show up in your Vercel Logs if it fails
    console.error('GCS Upload Error:', error.message);
    return NextResponse.json(
      { error: 'Failed to upload to GCS', details: error.message }, 
      { status: 500 }
    );
  }
}