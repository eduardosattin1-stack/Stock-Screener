import { NextResponse } from 'next/server';
import { Storage } from '@google-cloud/storage';

const storage = new Storage();
const bucketName = 'screener-signals-carbonbridge';

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const bucket = storage.bucket(bucketName);
    const file = bucket.file('portfolio/state.json');

    // Upload the structured JSON exactly how monitor_v7.py expects it
    await file.save(JSON.stringify(body, null, 2), {
      contentType: 'application/json',
      cacheControl: 'no-cache', // Ensure the python script gets the freshest version
    });

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error('GCS Upload Error:', error);
    return NextResponse.json({ error: 'Failed to upload to GCS' }, { status: 500 });
  }
}