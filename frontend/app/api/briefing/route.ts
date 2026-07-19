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
  // GCS-first, public-file fallback — matches SpeculairTracker.tsx / stock page. The
  // plain public path resolves to the file frozen at the last frontend deploy, so
  // fetching it directly (as this route used to) silently serves stale apex NAV /
  // basket returns between deploys instead of tonight's live GCS state.
  const getGcsFirst = async (suffix: string, fb: any) => {
    const gcs = await get(`/api/gcs/scans/${suffix}`, null);
    if (gcs) return gcs;
    return get(`/${suffix}`, fb);
  };

  // ── Congress Watch raw pull — Senate + House STOCK Act filings via the /api/fmp
  //    proxy (FMP stable `senate-latest` / `house-latest`, the all-symbol feeds; the
  //    per-symbol variants are `senate-trades`/`house-trades`, see screener_v6
  //    compute_congressional). Paged newest-first; 4×100 per chamber is ~2-4 weeks of
  //    House volume — enough for a 30d big-trade sweep. Any failure → [] and the
  //    card simply doesn't render. Cached 30 min (revalidate) to spare the FMP quota. ──
  const pullCongress = async (endpoint: string) => {
    const out: any[] = [];
    try {
      for (let p = 0; p < 4; p++) {
        const res = await fetch(`${origin}/api/fmp?e=${endpoint}&page=${p}&limit=100`, {
          next: { revalidate: 1800 },
        });
        if (!res.ok) break;
        const d = await res.json();
        if (!Array.isArray(d) || !d.length) break;
        out.push(...d);
        if (d.length < 100) break;
      }
    } catch { /* card hides */ }
    return out;
  };

  const [macro, sectors, methodTracks, spec, apexTrkEqual, apexTrkWeighted, senateRaw, houseRaw] = await Promise.all([
    get("/api/macro", {}),
    get("/api/sectors", {}),
    get("/api/performance/method-tracks", { regimes: {} }),
    getGcsFirst("speculair_baskets.json", {}),
    getGcsFirst("speculair_apex_tracking.json", {}),
    getGcsFirst("speculair_apex_tracking_weighted.json", {}),
    pullCongress("senate-latest"),
    pullCongress("house-latest"),
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
  // Growth x inflation quadrant (JPM-style 2x2) — from the weekly classifier snapshot
  // published with the baskets (the /api/macro lite mirror carries no growth/inflation).
  // The backend publishes `quadrant` directly from the next weekly run; the label-derived
  // fallback keeps the chip alive until then. Display-labeling of published fields only —
  // no signal is computed here.
  const mrFull = spec?.macro_regime || {};
  const mrd = mrFull.regime_detail || {};
  const g = String(mrd.growth || ""), inf = String(mrd.inflation || "");
  const quadrantFallback = (g && inf && !g.startsWith("Unknown"))
    ? (g !== "decelerating"
        ? (inf === "decelerating" ? "GOLDILOCKS" : "REFLATION")
        : (inf === "decelerating" ? "RISK_OFF" : "STAGFLATION"))
    : null;
  const quadrant = mrFull.quadrant && mrFull.quadrant !== "UNKNOWN" ? mrFull.quadrant : quadrantFallback;
  const regime_pulse = {
    regime,
    score: r2(score),
    quadrant,
    quadrant_detail: quadrant ? `growth ${g || "?"} × inflation ${inf || "?"}` : null,
    regime_read: spec?.regime_read || null,
    summary: `Macro regime ${regime}. ${sentiment}`,
    action: `Rates ${rd.rates || "neutral"}, credit ${rd.credit || "stable"}, VIX ${vix ?? "—"}. ${stance}`,
  };

  // ── Apex basket stats (NAV / inception) — used by the headline + Model Focus ──
  // Director-weighted NAV (conviction-sized) is primary once it has genuine live-forward
  // history; equal-weight is the fallback before then. Same promotion rule as the Apex
  // Basket card on / (page.tsx) — keeps this one "Apex" number consistent everywhere
  // instead of the headline/sidebar quietly reporting a different chain than the card.
  const atWeighted = spec?.apex_tracking_weighted;
  const atIsWeighted = !!(atWeighted && (atWeighted.history || []).length >= 4);
  const at = atIsWeighted ? atWeighted : (spec?.apex_tracking || {});
  const sinceInc = num(at.since_inception_pct);
  const nOpen = num(at.n_open, (spec?.apex_basket || []).length);
  // Positions/last_prices for Basket Pulse's top/worst name — same promotion, so it
  // reflects entries from whichever book (weighted vs equal-weight) is authoritative.
  const apexTrk = atIsWeighted ? apexTrkWeighted : apexTrkEqual;

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
      enteredDaysAgo: isFresh(p.entryDate) && p.entryDate ? Math.max(0, Math.floor((NOW - Date.parse(p.entryDate)) / 86400000)) : null,
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

  // ── System Debate — surface the LAST names added to the apex as click-through chips
  //    so the user can open each stock's debate tab. Prefer names flagged fresh this
  //    run (held_since_prior === false); on a quiet run that flags none, fall back to
  //    the most-recently-dated entry cohort (then top-conviction) so the row is never
  //    empty. Plus the ACT / WAIT read. ──
  const ds = spec?.debate_stats || {};
  const watch = (spec?.capitulation_watchlist || []).length;
  const apexMembers: any[] = spec?.apex_basket || [];
  let new_tickers = apexMembers.filter((p: any) => !p.held_since_prior).map((p: any) => p.symbol);
  if (!new_tickers.length && apexMembers.length) {
    const dated = apexMembers.filter((p: any) => p.entry_date);
    if (dated.length) {
      const latest = dated.map((p: any) => String(p.entry_date)).sort().reverse()[0];
      new_tickers = dated.filter((p: any) => String(p.entry_date) === latest).map((p: any) => p.symbol);
    } else {
      new_tickers = apexMembers
        .slice()
        .sort((a: any, b: any) => num(b.conviction) - num(a.conviction))
        .slice(0, 6)
        .map((p: any) => p.symbol);
    }
  }
  // ── Bounded-risk setups — picks whose debate math (numeric-gate-checked, stamped at
  //    publish time by publish_to_frontend.risk_badge) shows a modest bear floor with
  //    real asymmetry, or a dated hard catalyst with a checked floor. We only relay the
  //    stamp, never compute it here. Union of the apex board and the per-methodology
  //    overlay — the overlay catches names the debate cleared but the Director didn't
  //    seat (e.g. carried records like VNT). Empty until a publish stamps the field. ──
  const boundedMap = new Map<string, any>();
  const addBadge = (p: any, seated: boolean) => {
    const b = p?.risk_badge;
    if (!b?.kind || !p.symbol || boundedMap.has(p.symbol)) return;
    boundedMap.set(p.symbol, {
      symbol: p.symbol,
      kind: b.kind,
      rr: b.rr_ratio ?? null,
      floor: b.floor_distance_pct ?? null,
      upside: b.upside_pct ?? null,
      seated,
    });
  };
  apexMembers.forEach((p: any) => addBadge(p, true));
  Object.values(spec?.per_methodology_baskets || {}).forEach((mb: any) => {
    const picks = Array.isArray(mb) ? mb : mb?.picks;
    (Array.isArray(picks) ? picks : []).forEach((p: any) => addBadge(p, false));
  });
  const bounded = [...boundedMap.values()].sort((a, b) => (b.rr ?? 0) - (a.rr ?? 0)).slice(0, 6);

  const debate = {
    new_tickers,
    bounded,
    act:
      ds.apex_selected != null
        ? `${ds.apex_selected} names cleared the full multi-agent debate into the apex${ds.fully_debated != null ? ` (of ${ds.fully_debated} debated)` : ""}.`
        : `${apex.length} names hold the apex after the debate.`,
    wait: `${watch} on the capitulation watchlist${ds.radar_filtered != null ? ` · ${ds.radar_filtered} filtered pre-debate` : ""}${ds.auto_vetoed != null ? ` · ${ds.auto_vetoed} auto-vetoed` : ""}.`,
  };

  // ── Congress Watch — big STOCK Act filings (last 30 days, both chambers) ──
  // Filed-date window (disclosureDate), not trade-date: the briefing tracks what
  // just became public. "Big" = range lower bound ≥ $100,001 (the FMP `amount` is
  // a STOCK Act band like "$100,001 - $250,000"). Exchanges are dropped; only
  // rows with a real ticker survive (many filings are bonds/funds with no symbol).
  const amtBounds = (a: any): [number, number] => {
    const nums = String(a || "").replace(/,/g, "").match(/\d+/g)?.map(Number) || [];
    return [nums[0] || 0, nums[1] || nums[0] || 0];
  };
  const amtFmt = (v: number) =>
    v >= 1e6 ? `$${r2(v / 1e6)}M` : v >= 1e3 ? `$${Math.round(v / 1e3)}K` : `$${v}`;
  const cutoffIso = new Date(NOW - 30 * 86400000).toISOString().slice(0, 10);
  const apexSyms = new Set(apexMembers.map((p: any) => String(p.symbol || "").toUpperCase()));
  const seenTrade = new Set<string>();
  const trades: any[] = [];
  const ingest = (rows: any[], chamber: "S" | "H") => {
    for (const t of rows) {
      const sym = String(t.symbol || "").trim().toUpperCase();
      const filed = String(t.disclosureDate || "").slice(0, 10);
      const rawType = String(t.type || "");
      if (!sym || sym.includes(" ") || filed < cutoffIso) continue;
      const side = /purchase|buy/i.test(rawType) ? "BUY" : /sale|sold/i.test(rawType) ? "SELL" : null;
      if (!side) continue; // exchanges / received / options exercises
      const [lo, hi] = amtBounds(t.amount);
      const who = `${t.firstName || ""} ${t.lastName || ""}`.trim() || t.office || "—";
      const key = `${sym}|${who}|${t.transactionDate}|${side}|${lo}`;
      if (seenTrade.has(key)) continue;
      seenTrade.add(key);
      trades.push({
        symbol: sym, side, lo,
        range: hi > lo ? `${amtFmt(lo)}–${amtFmt(hi)}` : `${amtFmt(lo)}+`,
        who, chamber,
        tx: String(t.transactionDate || "").slice(0, 10),
        filed,
        apex: apexSyms.has(sym),
      });
    }
  };
  ingest(senateRaw, "S");
  ingest(houseRaw, "H");
  const bigTrades = trades.filter((t) => t.lo >= 100001).sort((a, b) => b.lo - a.lo);
  // Hot names — most-filed tickers across ALL 30d trades (any size), with the buy/sell split.
  const bySym = new Map<string, { buys: number; sells: number }>();
  for (const t of trades) {
    const s = bySym.get(t.symbol) || { buys: 0, sells: 0 };
    if (t.side === "BUY") s.buys++; else s.sells++;
    bySym.set(t.symbol, s);
  }
  const hotNames = [...bySym.entries()]
    .map(([symbol, s]) => ({ symbol, ...s, n: s.buys + s.sells, apex: apexSyms.has(symbol) }))
    .filter((h) => h.n >= 3)
    .sort((a, b) => b.n - a.n)
    .slice(0, 6);
  const congress = trades.length
    ? {
        window_days: 30,
        total: trades.length,
        big_count: bigTrades.length,
        big_buys: bigTrades.filter((t) => t.side === "BUY").length,
        big_sells: bigTrades.filter((t) => t.side === "SELL").length,
        top: bigTrades.slice(0, 8),
        hot: hotNames,
        // Newest-first feeds: the oldest filed date actually fetched. If this is
        // later than the 30d cutoff, the window is coverage-truncated (House volume
        // can exceed the 400-row pull) — the card shows it as "since <date>".
        coverage_from: trades.reduce((m, t) => (t.filed < m ? t.filed : m), "9999-12-31"),
      }
    : null;

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
    congress,
  });
}
