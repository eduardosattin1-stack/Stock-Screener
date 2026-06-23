import { NextRequest, NextResponse } from "next/server";

// Symbol/company typeahead for the top-nav search box. Queries FMP's stable
// search-symbol (ticker prefix) + search-name (company name) in parallel, then
// merges, dedupes by symbol, and ranks so the primary US listing for a query
// surfaces first. Returns a small, display-ready list for the dropdown.
const FMP_BASE = "https://financialmodelingprep.com/stable";

interface Hit { symbol: string; name: string; exchange: string; currency: string }

async function fmpSearch(endpoint: string, query: string, apiKey: string): Promise<any[]> {
  // Pull a wide pool (FMP ranks by its own relevance, which buries household names
  // like Microsoft for a partial query) so the ranker below can resurface them.
  const qs = new URLSearchParams({ query, limit: "40", apikey: apiKey });
  try {
    const res = await fetch(`${FMP_BASE}/${endpoint}?${qs}`, { next: { revalidate: 3600 } });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
  }
}

// The screener universe is US + Western Europe, so liquid listings in those
// markets should outrank obscure foreign micro-caps and crypto/forex noise that
// FMP's prefix search drags in (e.g. "micro" → MICRO.BK before Microsoft).
// Currency is a robust geography proxy that doesn't require enumerating every
// exchange code FMP might return.
const EU_CCY = new Set(["EUR", "GBP", "GBX", "CHF", "SEK", "NOK", "DKK", "ISK"]);
const NOISE_EX = new Set(["CRYPTO", "FOREX", "COMMODITY"]);
const OTC_EX = new Set(["OTC", "PNK", "OTCBB", "OTCMKTS"]);

function score(h: Hit, Q: string): number {
  const sym = h.symbol.toUpperCase();
  const name = (h.name || "").toUpperCase();
  const ex = (h.exchange || "").toUpperCase();
  const ccy = (h.currency || "").toUpperCase();
  let s = 0;
  // How well the query matches. An exact ticker always wins ("SOC" → SOC). Past
  // that, a ticker-prefix hit is weighted the SAME as a company-name-prefix hit —
  // a foreign listing whose ticker happens to spell the query (SIEMENS.NS,
  // MICRO.BK) is no more relevant than the real listing whose *name* starts with
  // it, so geography below can be the decider.
  if (sym === Q) s += 1000;
  else if (sym.startsWith(Q)) s += 250;
  else if (sym.includes(Q)) s += 80;
  if (name.startsWith(Q)) s += 250;
  else if (name.includes(Q)) s += 110;
  // Geography/quality — the decisive tiebreaker. Strong enough that a US/EU
  // primary listing outranks an obscure foreign dup even when the foreign one
  // matches on both ticker and name.
  if (NOISE_EX.has(ex)) s -= 500;           // crypto / forex / commodity noise
  else if (OTC_EX.has(ex)) s -= 80;         // US OTC ADRs: keep, but below primaries
  else if (ccy === "USD") s += 260;
  else if (EU_CCY.has(ccy)) s += 180;
  else s -= 260;                            // non-US/EU listing (INR, THB, HKD, MXN, AUD, …)
  if (!sym.includes(".")) s += 60;          // prefer the primary (US) listing over .DE/.MX/etc cross-listings
  return s;
}

export async function GET(req: NextRequest) {
  const apiKey = process.env.FMP_API_KEY;
  if (!apiKey) return NextResponse.json({ error: "FMP_API_KEY not set" }, { status: 500 });

  const q = (new URL(req.url).searchParams.get("q") || "").trim();
  if (q.length < 1) return NextResponse.json({ results: [] });

  const [bySymbol, byName] = await Promise.all([
    fmpSearch("search-symbol", q, apiKey),
    fmpSearch("search-name", q, apiKey),
  ]);

  const Q = q.toUpperCase();
  const seen = new Set<string>();
  const merged: Hit[] = [];
  for (const r of [...bySymbol, ...byName]) {
    const symbol = String(r?.symbol || "").trim();
    if (!symbol || seen.has(symbol.toUpperCase())) continue;
    seen.add(symbol.toUpperCase());
    merged.push({
      symbol,
      name: String(r?.name || ""),
      exchange: String(r?.exchange || ""),
      currency: String(r?.currency || ""),
    });
  }

  merged.sort((a, b) => score(b, Q) - score(a, Q));
  return NextResponse.json({ results: merged.slice(0, 8) });
}
