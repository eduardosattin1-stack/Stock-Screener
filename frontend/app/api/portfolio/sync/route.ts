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

// Full-state overwrite of portfolio/state.json.
//
// DANGER: this replaces the WHOLE document. The portfolio is now mirrored from
// IBKR (backend/ibkr_portfolio_sync.py) and enriched nightly by monitor_prices.py;
// a naive overwrite here would silently wipe both. Nothing in the app calls this
// route — it's kept only as a manual seed/restore escape hatch. Two guards:
//   1. NEVER overwrite a state that carries `ibkr_sync` unless ?confirm=1.
//   2. Write with an ifGenerationMatch precondition so a concurrent sync/monitor
//      write can't be clobbered (412 -> caller retries).
export async function POST(req: Request) {
  try {
    const url = new URL(req.url);
    const confirm = url.searchParams.get('confirm') === '1';
    const body = await req.json();
    const bucket = storage.bucket(bucketName);
    const file = bucket.file('portfolio/state.json');

    // Read current object (generation + whether it's an IBKR mirror).
    let generation = '0'; // "0" == object must not yet exist
    let isMirror = false;
    try {
      const [meta] = await file.getMetadata();
      generation = String(meta.generation ?? '0');
      const [buf] = await file.download();
      const cur = JSON.parse(buf.toString());
      isMirror = !!cur?.ibkr_sync;
    } catch {
      // 404 / unparseable -> treat as create (generation stays "0")
    }

    if (isMirror && !confirm) {
      return NextResponse.json(
        { error: 'Refusing to overwrite IBKR-mirrored portfolio state. Pass ?confirm=1 to force.' },
        { status: 409 },
      );
    }

    await file.save(JSON.stringify(body, null, 2), {
      resumable: false,
      preconditionOpts: { ifGenerationMatch: Number(generation) },
      metadata: { contentType: 'application/json', cacheControl: 'no-cache' },
    });

    return NextResponse.json({ success: true });
  } catch (error: any) {
    const precond = error?.code === 412;
    console.error('GCS Upload Error:', error.message);
    return NextResponse.json(
      { error: precond ? 'State changed since read — retry' : 'Failed to upload to GCS', details: error.message },
      { status: precond ? 412 : 500 },
    );
  }
}
