import { NextResponse } from "next/server";

export async function POST(req: Request) {
  try {
    const body = await req.json();
    const { symbol, metric, condition, value, email } = body || {};

    if (!symbol || !metric || !condition || value === undefined || !email) {
      return NextResponse.json({ error: "Missing required fields" }, { status: 400 });
    }

    // In a full implementation, this would save to the backend database via a Cloud Run proxy
    // For now, we mock the success response to complete the UI flow.
    console.log(`[ALERT CREATED] ${email} wants to be alerted when ${symbol} ${metric} ${condition} ${value}`);

    return NextResponse.json({ success: true, message: "Alert saved successfully." });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}
