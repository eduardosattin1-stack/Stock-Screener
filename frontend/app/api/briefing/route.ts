import { NextResponse } from "next/server";

// Daily Briefing — assembled entirely from LIVE wired data. No dependency on the
// (stale, composite-era) backend /briefing endpoint. Sources:
//   ?regime / ?score (query)        authoritative scan macro, passed by the page
//                                   (keeps the briefing in sync with the footer regime)
//   /api/macro                      fallback regime + rates/credit/VIX posture
//   /api/sectors                    index thermometer + hottest GICS sector
//   /api/performance/method-tracks  D8+ model-calibrated picks (decile, p20, EV) + worst miss
//   /speculair_baskets.json         apex basket NAV, debate stats, top picks
//
// The personalized "On Your Radar" card (earnings + big moves on the user's held /
// watched names) is computed CLIENT-SIDE in DailyBriefing.tsx — portfolio lives in
// per-user Firestore and the watchlist in localStorage, neither reachable here.

export const runtime = "nodejs";

const num = (v: any, d = 0) => (Number.isFinite(Number(v)) ? Number(v) : d);
const r2 = (v: number) => Math.round(v * 100) / 100;
const sign = (v: number) => (v >= 0 ? "+" : "");
const usd = (v: number) => `${v >= 0 ? "+$" : "-$"}${Math.abs(Math.round(v))}`;

function marketSentiment(spx: number, ndx: number): string {
  if (spx > 0.75 && ndx > 1.0) return "Aggressive risk-on tape. Tech leading a broad rally.";
  if (spx < -0.75 && ndx < -1.0) return "Broad selloff underway. High-beta tech hit hardest.";
  if (spx > 0.3 && ndx > 0.3) return "Solid upside momentum across major indices.";
  if (spx < -0.3 && ndx < -0.3) return "Market under pressure. Capital preservation first.";
  if (spx >= 0 && ndx < 0) return "Capital rotating out of tech into the broader market.";
  if (spx < 0 && ndx >= 0) return "Tech showing relative strength while the broader market lags.";
  return "Choppy consolidation. No clear directional conviction.";
}

export async function GET(req: Request) {
  const url = new URL(req.url);
  const origin = url.origin;
  const qRegime = url.searchParams.get("regime");
  const qScore = url.searchParams.get("score");
  const get = async (path: string, fb: any) => {
    try {
      const res = await fetch(`${origin}${path}`, { cache: "no-store" });
      return res.ok ? await res.json() : fb;
    } catch {
      return fb;
    }
  };

  const [macro, sectors, methodTracks, spec, apexTrk] = await Promise.all([
    get("/api/macro", {}),
    get("/api/sectors", {}),
    get("/api/performance/method-tracks", { regimes: {} }),
    get("/speculair_baskets.json", {}),
    get("/speculair_apex_tracking.json", {}),
  ]);

  // ── Index thermometer + market sentiment (from /api/sectors) ──
  const idx: any[] = sectors?.indices || [];
  const findIdx = (frag: string) =>
    idx.find((row) => (row.symbol || "").includes(frag) || (row.name || "").includes(frag));
  const spxR = findIdx("GSPC") || findIdx("S&P");
  const ndxR = findIdx("NDX") || findIdx("NASDAQ");
  const rutR = findIdx("RUT") || findIdx("Russell");
  const vix = sectors?.macro?.vix ?? null;
  const vixCh = sectors?.macro?.vixChange ?? null;

  const thermometer: Record<string, any> = {};
  if (spxR?.price != null) thermometer.SPX = { price: spxR.price, change_pct: num(spxR.day) };
  if (ndxR?.price != null) thermometer.NDX = { price: ndxR.price, change_pct: num(ndxR.day) };
  if (rutR?.price != null) thermometer.RUT = { price: rutR.price, change_pct: num(rutR.day) };
  if (vix != null) thermometer.VIX = { price: vix, change_pct: num(vixCh) };
  const sentiment = marketSentiment(num(spxR?.day), num(ndxR?.day));

  // ── Regime Pulse — prefer the authoritative scan macro (passed by the page) so the
  //    briefing agrees with the Sector-Performance footer; fall back to lite /api/macro. ──
  const regime = qRegime || macro?.regime || "NEUTRAL";
  const score = qScore && qScore !== "undefined" ? num(qScore, 0.5) : num(macro?.score, 0.5);
  const rd = macro?.regime_detail || {};
  const stance =
    regime === "RISK_ON" ? "Risk-on — lean into growth & momentum."
    : regime === "RISK_OFF" ? "Risk-off — prioritise quality and downside protection."
    : regime === "CAUTIOUS" ? "Cautious — debate-backed, high-conviction names only."
    : "Balanced — hold the apex; let the director gate new entries.";
  const regime_pulse = {
    regime,
    score: r2(score),
    summary: `Macro regime ${regime}. ${sentiment}`,
    action: `Rates ${rd.rates || "neutral"}, credit ${rd.credit || "stable"}, VIX ${vix ?? "—"}. ${stance}`,
  };

  // ── Apex basket stats (NAV / inception) — used by the headline + Model Focus ──
  const at = spec?.apex_tracking || {};
  const sinceInc = num(at.since_inception_pct);
  const nOpen = num(at.n_open, (spec?.apex_basket || []).length);

  // ── Four-method tracker: collect stock prediction rows (decile/p20/EV, live state) ──
  // decile is model-calibrated (OOS thresholds) — NOT a client-side relative rank.
  // EV (edge_dollars_at_entry) lives on the long_call row; join by symbol.
  const stockRows: any[] = [];
  for (const rg of ["60d", "30d_p10"]) {
    const preds: any[] = methodTracks?.regimes?.[rg]?.current_cycle?.predictions || [];
    const calls = new Map<string, any>();
    for (const p of preds) if (p.method === "long_call") calls.set(p.symbol, p);
    for (const p of preds) {
      if (p.method !== "stock") continue;
      const call = calls.get(p.symbol);
      const ev = call && call.edge_dollars_at_entry != null ? num(call.edge_dollars_at_entry) : null;
      const liveRet =
        num(p.current_price) > 0 && num(p.entry_price) > 0
          ? (num(p.current_price) / num(p.entry_price) - 1) * 100
          : num(p.realized_return_pct);
      stockRows.push({
        symbol: p.symbol,
        decile: num(p.decile),
        prob: num(p.p20),
        probLabel: rg === "60d" ? "P(+20%/60d)" : "P(+10%/30d)",
        ev,
        maxPlus: num(p.max_high_observed_pct),
        liveRet,
        outcome: p.outcome_tag || "OPEN",
        sector: p.sector || "",
        entryDate: p.entry_date || null,
        daysOpen: num(p.days_observed),
      });
    }
  }

  // ── Model Focus — WEEKLY pulse: the model's NEW top-tier (D9/D10) signals from
  //    this week + the week's hottest sector. D9+ only (the highest-conviction tier)
  //    and only fresh entries (≤7d) so the card reads as "what newly qualified",
  //    not a standing list. Apex/debate names move to the System Debate card. ──
  const NOW = Date.now();
  const isFresh = (d: string | null) => { const t = Date.parse(d || ""); return Number.isFinite(t) ? NOW - t <= 7 * 86400000 : false; };
  const d9new = stockRows
    .filter((r) => r.decile >= 9 && r.outcome === "OPEN" && isFresh(r.entryDate))
    .sort((a, b) => b.decile - a.decile || (Date.parse(b.entryDate || "") || 0) - (Date.parse(a.entryDate || "") || 0));
  const seenP = new Set<string>();
  const picks: any[] = [];
  for (const p of d9new) { const k = p.symbol.toUpperCase(); if (seenP.has(k)) continue; seenP.add(k); picks.push(p); }

  const apex: any[] = (spec?.apex_basket || [])
    .slice()
    .sort((a: any, b: any) => num(b.conviction) - num(a.conviction));
  const secs: any[] = (sectors?.sectors || []).filter((s: any) => s.week != null || s.day != null);
  const hotSec = secs.slice().sort((a, b) => num(b.week ?? b.day) - num(a.week ?? a.day))[0];
  const model_focus = {
    regime,
    picks: picks.slice(0, 3).map((p: any) => ({
      symbol: p.symbol,
      decile: p.decile,
      prob: r2(p.prob),
      probLabel: p.probLabel,
      ev: p.ev,
      evStr: p.ev != null ? `EV ${usd(p.ev)}` : null,
      evNeg: p.ev != null && p.ev < 0,
      peak: r2(p.maxPlus),
    })),
    hot_sector: hotSec
      ? {
          name: hotSec.name,
          symbol: hotSec.symbol,
          week: r2(num(hotSec.week ?? hotSec.day)),
          is_week: hotSec.week != null,
          neg: num(hotSec.week ?? hotSec.day) < 0,
        }
      : null,
  };

  // ── 12-basket pulse ──
  // Portfolio-level read across the 12 Speculair methodology baskets. Returns are
  // real and time-referenced: basket-level since each basket's tracking_start;
  // single-name compounder/loser from the apex book's live entry-vs-last prices.
  const BLABEL: Record<string, string> = {
    dcf_fcff: "DCF-FCFF", earnings_yield_gap: "Earnings Yield", ev_gross_profit: "Gross Profit.",
    rd_capitalized_dcf: "R&D DCF", owner_earnings: "Owner Earn.", epv: "EPV", graham_revised: "Graham",
    acquirers_multiple: "Acquirer's", ev_gp: "EV/GP", iv15_deep_value: "IV15 Deep",
    convergence: "Convergence", fundamental_momentum: "Fund. Mom.",
  };
  const md = (d: any) => { const x = new Date(d); return Number.isNaN(x.getTime()) ? "" : x.toLocaleDateString("en-US", { month: "short", day: "numeric" }); };
  const pmb: Record<string, any> = spec?.per_methodology_baskets || {};
  const basketRets = Object.keys(pmb).map((k) => ({ key: k, label: BLABEL[k] || k, ret: r2(num(pmb[k]?.ytd_return) * 100), start: pmb[k]?.tracking_start }));
  basketRets.sort((a, b) => b.ret - a.ret);
  const leaderB = basketRets[0] || null;
  const laggardB = basketRets[basketRets.length - 1] || null;
  const greenB = basketRets.filter((b) => b.ret > 0).length;
  const apos: Record<string, any> = apexTrk?.positions || {};
  const alp: Record<string, any> = apexTrk?.last_prices || {};
  const nameRets = Object.keys(apos).map((sym) => {
    const e = num(apos[sym]?.entry_price); const last = num(alp[sym]);
    return e > 0 && last > 0 ? { sym, ret: r2((last / e - 1) * 100), since: md(apos[sym]?.entry_date) } : null;
  }).filter(Boolean).sort((a: any, b: any) => b.ret - a.ret) as any[];
  const basket_pulse = {
    total: basketRets.length,
    green: greenB,
    leader: leaderB ? { label: leaderB.label, ret: leaderB.ret, since: md(leaderB.start) } : null,
    laggard: laggardB ? { label: laggardB.label, ret: laggardB.ret, since: md(laggardB.start) } : null,
    top_name: nameRets[0] || null,
    worst_name: nameRets.length > 1 ? nameRets[nameRets.length - 1] : null,
  };

  // ── System pulse footer (live tracking — from method-tracks 30d stock cycle) ──
  const stock30 = methodTracks?.regimes?.["30d_p10"]?.current_cycle?.by_method?.stock || {};
  const system_pulse = {
    live_mtd: `${sign(num(stock30.portfolio_return_pct))}${r2(num(stock30.portfolio_return_pct))}%`,
    spy_mtd: spxR?.ytd != null ? `${sign(num(spxR.ytd))}${r2(num(spxR.ytd))}% YTD` : "—",
    avg_coverage: `${Math.round(num(stock30.winning_trade_rate) * 100)}% win · ${num(stock30.n)} tracked (30d)`,
  };

  // ── System Debate — surface the names that NEWLY cleared the debate into the apex
  //    (held_since_prior === false) as click-through chips so the user can open each
  //    stock's debate tab. Plus the ACT / WAIT read. ──
  const ds = spec?.debate_stats || {};
  const watch = (spec?.capitulation_watchlist || []).length;
  const new_tickers = (spec?.apex_basket || []).filter((p: any) => !p.held_since_prior).map((p: any) => p.symbol);
  const debate = {
    new_tickers,
    act:
      ds.apex_selected != null
        ? `${ds.apex_selected} names cleared the full multi-agent debate into the apex${ds.fully_debated != null ? ` (of ${ds.fully_debated} debated)` : ""}.`
        : `${apex.length} names hold the apex after the debate.`,
    wait: `${watch} on the capitulation watchlist${ds.radar_filtered != null ? ` · ${ds.radar_filtered} filtered pre-debate` : ""}${ds.auto_vetoed != null ? ` · ${ds.auto_vetoed} auto-vetoed` : ""}.`,
  };

  // ── Headline ──
  const headline = `${sentiment} Apex basket ${sign(sinceInc)}${r2(sinceInc)}% since inception, ${nOpen} names live.`;

  return NextResponse.json({
    headline,
    generated_at: new Date().toISOString(),
    regime_pulse,
    model_focus,
    basket_pulse,
    system_pulse,
    thermometer,
    debate,
  });
}
