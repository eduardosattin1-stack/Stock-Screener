import { NextResponse } from "next/server";

const FMP_BASE = "https://financialmodelingprep.com/stable";

// Sub-score computation functions (mirrors macro_regime.py logic)
function scoreYieldCurve(rates: any): number {
  const y10 = rates?.year10 ?? 4.3;
  const y2 = rates?.year2 ?? 3.8;
  const bp = (y10 - y2) * 100;
  if (bp >= 150) return 1.0;
  if (bp >= 100) return 0.85;
  if (bp >= 50) return 0.70;
  if (bp >= 20) return 0.55;
  if (bp >= 0) return 0.35;
  if (bp >= -50) return 0.15;
  return 0.0;
}

function scoreYieldCurve3m(rates: any): number {
  const y10 = rates?.year10 ?? 4.3;
  const m3 = rates?.month3 ?? 3.7;
  const bp = (y10 - m3) * 100;
  if (bp >= 200) return 1.0;
  if (bp >= 100) return 0.85;
  if (bp >= 50) return 0.70;
  if (bp >= 20) return 0.55;
  if (bp >= 0) return 0.35;
  if (bp >= -50) return 0.15;
  return 0.0;
}

function scoreYieldLevel(rates: any): number {
  const ffr = rates?.month3 ?? 3.7;
  if (ffr <= 2.0) return 1.0;
  if (ffr <= 3.0) return 0.80;
  if (ffr <= 4.0) return 0.60;
  if (ffr <= 5.0) return 0.40;
  if (ffr <= 6.0) return 0.20;
  return 0.0;
}

function scoreVix(vix: number): number {
  if (vix <= 12) return 1.0;
  if (vix <= 16) return 0.85;
  if (vix <= 20) return 0.65;
  if (vix <= 25) return 0.40;
  if (vix <= 30) return 0.20;
  if (vix <= 40) return 0.10;
  return 0.0;
}

function classifyRegime(score: number): string {
  if (score >= 0.65) return "RISK_ON";
  if (score >= 0.45) return "NEUTRAL";
  if (score >= 0.30) return "CAUTIOUS";
  return "RISK_OFF";
}

async function fmpGet(endpoint: string, params: Record<string, string>, apiKey: string) {
  const qs = new URLSearchParams({ ...params, apikey: apiKey });
  const res = await fetch(`${FMP_BASE}/${endpoint}?${qs}`, { next: { revalidate: 300 } });
  if (!res.ok) return null;
  const data = await res.json();
  return Array.isArray(data) ? data : data ? [data] : null;
}

export async function GET() {
  const apiKey = process.env.FMP_API_KEY;
  if (!apiKey) return NextResponse.json({ error: "FMP_API_KEY not set" }, { status: 500 });

  try {
    // Fetch treasury rates + VIX in parallel
    const [ratesRaw, vixRaw] = await Promise.all([
      fmpGet("treasury-rates", {}, apiKey),
      fmpGet("quote", { symbol: "^VIX" }, apiKey),
    ]);

    const rates = ratesRaw?.[0] ?? {};
    const vixPrice = Number(vixRaw?.[0]?.price ?? 20);

    // Compute sub-scores (core 4 — the FMP economic-indicators endpoints
    // for CPI/GDP/unemployment/sentiment require additional calls and parsing;
    // for the lightweight frontend-only route we compute what's cheap and
    // leave the rest for the backend-embedded version)
    const sCurve = scoreYieldCurve(rates);
    const sCurve3m = scoreYieldCurve3m(rates);
    const sLevel = scoreYieldLevel(rates);
    const sVix = scoreVix(vixPrice);

    const subScores: Record<string, number> = {
      yield_curve: sCurve,
      yield_curve_3m: sCurve3m,
      yield_level: sLevel,
      vix: sVix,
    };

    // Weighted composite (partial — using the 4 available signals)
    const weights: Record<string, number> = {
      yield_curve: 0.25, yield_curve_3m: 0.15, yield_level: 0.15, vix: 0.45,
    };
    let score = 0;
    for (const [k, w] of Object.entries(weights)) {
      score += (subScores[k] ?? 0.5) * w;
    }

    const yieldSpread2y = ((rates.year10 ?? 4.3) - (rates.year2 ?? 3.8)) * 100;
    const yieldSpread3m = ((rates.year10 ?? 4.3) - (rates.month3 ?? 3.7)) * 100;

    return NextResponse.json({
      regime: classifyRegime(score),
      score: Math.round(score * 10000) / 10000,
      sub_scores: subScores,
      features: {
        macro_regime_score: Math.round(score * 10000) / 10000,
        macro_vix: Math.round(vixPrice * 100) / 100,
        macro_yield_spread_2y: Math.round(yieldSpread2y * 100) / 100,
        macro_yield_spread_3m: Math.round(yieldSpread3m * 100) / 100,
        macro_yield_level: Math.round((rates.month3 ?? 3.7) * 100) / 100,
      },
      version: "v8-lite",
    });
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 502 });
  }
}
