import { NextRequest, NextResponse } from "next/server";

// Top holdings of an ETF (sector or thematic) with today's live % move, for the
// expandable cards on the Sectors tab. Holdings change slowly (cache 1h); the
// per-holding day-% comes from one batch-quote (cache 30s).
// FMP stable REST path is `etf/holdings` (NOT `etf-holdings`, which 404s to []).
const FMP_BASE = "https://financialmodelingprep.com/stable";

// Curated pure-play baskets for themes where the ETF's own holdings aren't
// representative: NUKZ returns nothing from FMP, and QTUM (Defiance Quantum) is
// diluted with broad semis rather than pure-play quantum names. Keyed by the
// card's ETF symbol; when present, these replace the ETF holdings on expand
// (no ETF weight → weight shows blank; sorted by YTD).
const CURATED: Record<string, { symbol: string; name: string }[]> = {
  QTUM: [
    { symbol: "IONQ", name: "IonQ" },
    { symbol: "RGTI", name: "Rigetti Computing" },
    { symbol: "QBTS", name: "D-Wave Quantum" },
    { symbol: "QUBT", name: "Quantum Computing Inc" },
    { symbol: "ARQQ", name: "Arqit Quantum" },
    { symbol: "IBM", name: "IBM (quantum systems)" },
    { symbol: "GOOGL", name: "Alphabet (Google Quantum AI)" },
  ],
  NUKZ: [
    { symbol: "OKLO", name: "Oklo (Aurora-INL criticality mid-2026)" },
    { symbol: "SMR", name: "NuScale Power" },
    { symbol: "XE", name: "X-Energy (post-lockup Oct–Nov 2026)" },
    { symbol: "BWXT", name: "BWX Technologies" },
    { symbol: "CCJ", name: "Cameco" },
    { symbol: "LEU", name: "Centrus Energy" },
  ],
  REMX: [
    { symbol: "MP", name: "MP Materials (also primary humanoid-magnet play)" },
    { symbol: "LYC.AX", name: "Lynas Rare Earths (US OTC: LYSCF)" },
    { symbol: "UUUU", name: "Energy Fuels" },
    { symbol: "NEO.TO", name: "NEO Performance Materials" },
    { symbol: "ILU.AX", name: "Iluka Resources" },
    { symbol: "REMX", name: "VanEck Rare Earth/Strategic Metals ETF" },
  ],
  BOTZ: [
    { symbol: "TSLA", name: "Tesla (Optimus)" },
    { symbol: "SHA.DE", name: "Schaeffler (actuators; equity preferred)" },
    { symbol: "6324.T", name: "Harmonic Drive (harmonic reducers, Tokyo)" },
    { symbol: "KOID", name: "KraneShares Humanoid Robotics ETF" },
    { symbol: "2049.TW", name: "Hiwin (ball screws, Taiwan)" },
    { symbol: "RRX", name: "Regal Rexnord (motors/gearing)" },
    { symbol: "MOG-A", name: "Moog (precision motion)" },
    { symbol: "OUST", name: "Ouster (industrial LiDAR)" },
  ],
};

async function fmpGet(endpoint: string, params: Record<string, string>, revalidate: number) {
  const apiKey = process.env.FMP_API_KEY as string;
  const qs = new URLSearchParams({ ...params, apikey: apiKey });
  const res = await fetch(`${FMP_BASE}/${endpoint}?${qs}`, { next: { revalidate } });
  if (!res.ok) return null;
  const data = await res.json();
  return Array.isArray(data) ? data : data ? [data] : null;
}

export async function GET(req: NextRequest) {
  if (!process.env.FMP_API_KEY) return NextResponse.json({ error: "FMP_API_KEY not set" }, { status: 500 });
  const symbol = new URL(req.url).searchParams.get("symbol");
  if (!symbol) return NextResponse.json({ error: "missing ?symbol" }, { status: 400 });

  try {
    const curated = CURATED[symbol.toUpperCase()];
    let top: { symbol: string; name: string; weight: number | null }[];
    if (curated) {
      top = curated.map((c) => ({ symbol: c.symbol, name: c.name, weight: null }));
    } else {
      const raw = await fmpGet("etf/holdings", { symbol }, 3600);
      top = (raw || [])
        .filter((h: any) => h.asset && String(h.asset).trim())
        .sort((a: any, b: any) => (Number(b.weightPercentage) || 0) - (Number(a.weightPercentage) || 0))
        .slice(0, 10)
        .map((h: any) => ({ symbol: String(h.asset), name: h.name ?? "", weight: Number(h.weightPercentage) || null }));
    }

    // Per-holding day-% + YTD from stock-price-change (one call each, parallel; cached 60s).
    const holdings = await Promise.all(
      top.map(async (t) => {
        const rows = await fmpGet("stock-price-change", { symbol: t.symbol }, 60);
        const c = rows?.[0] ?? null;
        const num = (k: string): number | null => {
          const v = c == null ? null : Number((c as any)[k]);
          return Number.isFinite(v as number) ? (v as number) : null;
        };
        return { ...t, day: num("1D"), ytd: num("ytd") };
      }),
    );
    if (curated) holdings.sort((a, b) => (b.ytd ?? -999) - (a.ytd ?? -999));
    return NextResponse.json({ symbol, holdings });
  } catch (e: any) {
    return NextResponse.json({ error: e.message }, { status: 502 });
  }
}
