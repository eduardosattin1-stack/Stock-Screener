import { NextResponse } from "next/server";

// Daily Briefing — assembled entirely from LIVE wired data. No dependency on the
// (stale, composite-era) backend /briefing endpoint. Sources:
//   ?regime / ?score (query)        authoritative scan macro, passed by the page
//                                   (keeps the briefing in sync with the footer regime)
//   /api/macro                      fallback regime + rates/credit/VIX posture
//   /api/sectors                    index thermometer + hottest GICS sector
//   /api/performance/calibration-v2 D9+ live model-calibrated picks (decile, p10/p20) for Model Focus
//   /speculair_baskets.json         apex basket NAV, debate stats, top picks
//
// "On Your Radar" surfaces what's actually in the Speculair system's live books
// (apex + value lens), not a signed-in user's personal holdings — computed
// entirely server-side here, no Firestore/localStorage dependency.

export const runtime = "nodejs";

// Catalyst-flags overlay for "On Your Radar" — a short, scannable note per
// symbol (screener_v6.compute_catalyst_score: earnings beat/miss streaks,
// analyst upgrade/downgrade bursts, M&A/activist activity), e.g. "Earnings in
// 13d, 6/7 beats" or "⚠ 7 downgrades in 7d · M&A/activist activity detected".
// This is the SAME short-note style the old portfolio-based radar card used —
// preferred over the apex book's own (much longer) forcing_function text,
// which needs truncation to fit the card and reads worse for it. Fetched from
// the public scan URL directly (not the authenticated GCS proxy — works
// locally without credentials), mirroring /api/stock/[symbol]/row's own
// 15-min in-memory cache + single-flight pattern so repeat briefing loads on a
// warm instance don't re-download the ~28MB scan.
const CATALYST_SCAN_URL = "https://storage.googleapis.com/screener-signals-carbonbridge/scans/latest_global.json";
const CATALYST_TTL_MS = 15 * 60 * 1000;
type CatalystCache = { at: number; bySymbol: Map<string, string[]> };
const cg = globalThis as unknown as { __briefingCatalystCache?: CatalystCache | null; __briefingCatalystPromise?: Promise<CatalystCache> | null };
async function loadCatalystFlags(): Promise<CatalystCache> {
  const res = await fetch(CATALYST_SCAN_URL, { cache: "no-store" });
  if (!res.ok) throw new Error(`scan ${res.status}`);
  const d = await res.json();
  const bySymbol = new Map<string, string[]>();
  for (const s of d?.stocks ?? []) {
    if (s?.symbol && Array.isArray(s.catalyst_flags) && s.catalyst_flags.length) {
      bySymbol.set(String(s.symbol).toUpperCase(), s.catalyst_flags);
    }
  }
  return { at: Date.now(), bySymbol };
}
async function getCatalystFlags(): Promise<Map<string, string[]>> {
  const c = cg.__briefingCatalystCache;
  if (c && Date.now() - c.at < CATALYST_TTL_MS) return c.bySymbol;
  if (!cg.__briefingCatalystPromise) {
    cg.__briefingCatalystPromise = loadCatalystFlags()
      .then((fresh) => { cg.__briefingCatalystCache = fresh; return fresh; })
      .finally(() => { cg.__briefingCatalystPromise = null; });
  }
  try {
    return (await cg.__briefingCatalystPromise).bySymbol;
  } catch {
    return c?.bySymbol || new Map();
  }
}

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
  const NOW = Date.now();
  const isoDate = (ms: number) => new Date(ms).toISOString().slice(0, 10);

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

  // ── Target Watch raw pull — analyst price-target changes via FMP stable
  //    `price-target-latest-news` (all-symbol, newest-first). Verified against the
  //    live plan 2026-07-19: ~1000 rows ≈ 4-5 trading days, so 8×1000 spans ~30d;
  //    rows carry no prior-target field but ~80% of titles embed it ("raised to
  //    $32 from $30"), which the aggregation below parses. Same failure posture
  //    as Congress Watch: any error → [] → no card. ──
  const pullTargets = async () => {
    const pages = await Promise.all(
      Array.from({ length: 8 }, (_, p) =>
        fetch(`${origin}/api/fmp?e=price-target-latest-news&page=${p}&limit=1000`, {
          next: { revalidate: 1800 },
        })
          .then((r) => (r.ok ? r.json() : []))
          .catch(() => []),
      ),
    );
    return pages.flatMap((d) => (Array.isArray(d) ? d : []));
  };

  const [macro, sectors, calibV2, spec, apexTrkEqual, apexTrkWeighted, valueApex, methodologyTracking, catalystFlags, spyHistRaw, senateRaw, houseRaw, targetsRaw] = await Promise.all([
    get("/api/macro", {}),
    get("/api/sectors", {}),
    get("/api/performance/calibration-v2", { records: [] }),
    getGcsFirst("speculair_baskets.json", {}),
    getGcsFirst("speculair_apex_tracking.json", {}),
    getGcsFirst("speculair_apex_tracking_weighted.json", {}),
    getGcsFirst("speculair_value_apex.json", {}),
    // Per-basket nav_history (uniform start 2026-07-20 across all 12 baskets, unlike
    // their staggered tracking_start) — powers the basket_pulse MTD/week winner below.
    getGcsFirst("methodology_tracking.json", {}),
    // Real market catalyst signal for the "On Your Radar" short-note overlay below.
    getCatalystFlags().catch(() => new Map<string, string[]>()),
    // SPY (^GSPC) daily closes spanning both books' inception dates + the 30d MTD anchor,
    // so "live tracking" can measure SPY over the SAME windows as each book below —
    // never a mismatched MTD-vs-YTD comparison. 95d back is a safety margin past either
    // book's inception (~50d old as of writing).
    get(`/api/fmp?e=historical-price-eod/light&symbol=%5EGSPC&from=${isoDate(NOW - 95 * 86400000)}&to=${isoDate(NOW)}`, []),
    pullCongress("senate-latest"),
    pullCongress("house-latest"),
    pullTargets(),
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
  // Dalio debt-cycle chip (2026-07-27) — published with the weekly baskets. phaseFallback
  // mirrors quadrantFallback's job for the pre-regeneration snapshot: the phase cannot be
  // derived from labels (it is a path-dependent state machine), so the fallback is simply
  // "absent chip" rather than a synthesized value — display-labeling only, no signal here.
  const dc = spec?.debt_cycle || {};
  const phase = dc.debt_cycle_phase && dc.debt_cycle_phase !== "UNKNOWN" ? dc.debt_cycle_phase : null;
  const rrPhase = spec?.regime_read?.phase_falsifiers;
  const cycleFalsifiers = (Array.isArray(rrPhase) ? rrPhase : [])
    .filter((f: any) => f && f.condition)
    .sort((a: any, b: any) => String(a.check_by || "9999").localeCompare(String(b.check_by || "9999")))
    .slice(0, 3);
  const cycle_pulse = phase ? {
    phase,
    weeks_in_phase: dc.weeks_in_phase ?? null,
    confidence: dc.confidence || null,
    phase_basis: dc.phase_basis || null,
    phase_detail: dc.phase_detail || null,
    duration_caps: dc.duration_caps || null,
    cap_binding: dc.cap_binding || [],
    transition_blocked: !!dc.transition_blocked,
    transition_implied: dc.transition_implied || null,
    reserve_asset_note: dc.reserve_asset_check?.note || null,
    phase_view: spec?.regime_read?.phase_view || null,
    falsifiers: cycleFalsifiers,
  } : null;
  const regime_pulse = {
    regime,
    score: r2(score),
    quadrant,
    quadrant_detail: quadrant ? `growth ${g || "?"} × inflation ${inf || "?"}` : null,
    regime_read: spec?.regime_read || null,
    cycle: cycle_pulse,
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

  // ── Model Focus source: calibration_tracking v2 — the SAME live decile system
  //    the TradeBot trades. The frozen/superseded four-method tracker
  //    (methodTracks) is REMOVED from this app entirely as of 2026-07-23 (not
  //    just routed around) — it can no longer be a data source for anything,
  //    by construction, per [[feedback_no_hardcoded_decile_snapshots]]. That
  //    tracker's deciles could name a stock D9 that the live model no longer
  //    even scores
  //    (surfaced 2026-07-23 — Model Focus showed picks with hit_prob_60d=0 in
  //    that day's scan). One row per (record, horizon) so the D9/D10 filter can
  //    match either window; a symbol can appear from both regimes or from
  //    several entry dates — the pick-list dedup below already keeps the
  //    highest-decile, most-recent one per symbol. No live-quote join here (v2
  //    records carry no current price), so EV/liveRet are not available —
  //    "peak" (maxPlus, from max_high_pct) covers the card's "peaked +X%" line.
  const calibRecords: any[] = calibV2?.records || [];
  const stockRows: any[] = [];
  for (const rg of ["60d", "30d"] as const) {
    for (const r of calibRecords) {
      const decile = rg === "60d" ? r.decile_60d : r.decile_30d;
      if (decile == null) continue; // not priced for this horizon
      stockRows.push({
        symbol: r.symbol,
        decile: num(decile),
        prob: num(rg === "60d" ? r.p20 : r.p10),
        probLabel: rg === "60d" ? "P(+20%/60d)" : "P(+10%/30d)",
        ev: null,
        maxPlus: num(r.max_high_pct),
        outcome: (rg === "60d" ? r.state_60d : r.state_30d) || null,
        sector: r.sector || "",
        entryDate: r.entry_date || null,
        daysOpen: num(rg === "60d" ? r.bars_elapsed_60d : r.bars_elapsed_30d),
      });
    }
  }

  // ── Model Focus — WEEKLY pulse: the model's NEW top-tier (D9/D10) signals from
  //    this week + the week's hottest sector. D9+ only (the highest-conviction tier)
  //    and only fresh entries (≤7d) so the card reads as "what newly qualified",
  //    not a standing list. Apex/debate names move to the System Debate card. ──
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
  const hotSecs = secs.slice().sort((a, b) => num(b.week ?? b.day) - num(a.week ?? a.day));
  const model_focus = {
    regime,
    picks_total: picks.length,
    picks: picks.slice(0, 4).map((p: any) => ({
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
    hot_sectors: hotSecs.slice(0, 3).map((s) => ({
      name: s.name,
      symbol: s.symbol,
      week: r2(num(s.week ?? s.day)),
      is_week: s.week != null,
      neg: num(s.week ?? s.day) < 0,
    })),
  };

  // ── On Your Radar — what's actually in the Speculair system's live books, not a
  //    signed-in user's personal holdings. Basket13 is deliberately excluded here:
  //    its event-driven special situations (merger arb, FDA decisions, lockups)
  //    don't have short catalyst_flags-style notes for most names, and its own
  //    long-form reasoning reads as clutter in this card — that reasoning already
  //    lives on the 13th Basket page itself.
  //    - Apex: real market catalyst_flags (earnings beat/miss streaks, analyst
  //      upgrade/downgrade bursts, M&A/activist activity) when the scan covers
  //      the symbol — a short, scannable note, e.g. "Earnings in 13d, 6/7 beats".
  //      Falls back to the debate-authored forcing_function (FIRED is already
  //      resolved — not forward-looking, so it's excluded from the radar either way).
  //    - Value Lens: deliberately catalyst-free by design (the pure-value re-grade
  //      strips the catalyst overlay) — its radar signal is MoS% + the thesis-break
  //      price level to watch instead. ──
  const truncate = (s: any, n: number) => {
    const t = String(s || "").trim();
    return t.length > n ? `${t.slice(0, n - 1).trimEnd()}…` : t;
  };
  const radarSeen = new Set<string>();
  const radarItems: any[] = [];
  for (const p of (spec?.apex_basket || [])) {
    const sym = String(p?.symbol || "").toUpperCase();
    if (!sym || radarSeen.has(sym)) continue;
    if (p.catalyst_status !== "PENDING_HARD" && p.catalyst_status !== "SOFT_EXTENDED") continue;
    radarSeen.add(sym);
    const flags = catalystFlags.get(sym);
    const text = flags?.length ? flags.slice(0, 2).join(" · ") : truncate(p.forcing_function, 90);
    const urgent = p.catalyst_status === "PENDING_HARD" || Boolean(flags?.some((f: string) => f.includes("⚠")));
    radarItems.push({ symbol: p.symbol, source: "apex", urgent, text });
  }
  for (const p of (valueApex?.apex_basket || [])) {
    const sym = String(p?.symbol || "").toUpperCase();
    if (!sym || radarSeen.has(sym)) continue;
    const mos = p.sop_mos_pct;
    const breakPx = p.thesis_break_px;
    if (mos == null && breakPx == null) continue;
    radarSeen.add(sym);
    const parts: string[] = [];
    if (mos != null) parts.push(`MoS ${sign(num(mos))}${r2(num(mos))}%`);
    if (breakPx != null) parts.push(`thesis breaks below $${num(breakPx)}`);
    radarItems.push({ symbol: p.symbol, source: "value", urgent: false, text: parts.join(" · ") });
  }
  radarItems.sort((a, b) => (b.urgent ? 1 : 0) - (a.urgent ? 1 : 0));
  const radar_watch = { total: radarItems.length, items: radarItems.slice(0, 5) };

  // Shared NAV-window helper (reused below for basket MTD/week AND the Live
  // Tracking section further down) — return from the earliest history point ON
  // OR AFTER `sinceMs` to the latest. Never fabricates a window: with only a few
  // days of history it returns whatever real window exists rather than a fake
  // 30d/7d figure, and self-corrects as more nightly snapshots accumulate.
  const navReturnSince = (history: any[] | undefined, sinceMs: number): number | null => {
    if (!history?.length) return null;
    const latest = history[history.length - 1];
    let anchor = history[0];
    for (const h of history) { if (Date.parse(h.date) >= sinceMs) { anchor = h; break; } }
    if (!anchor?.nav || !latest?.nav) return null;
    return ((latest.nav / anchor.nav) - 1) * 100;
  };
  const THIRTY_D_AGO = NOW - 30 * 86400000;
  const SEVEN_D_AGO = NOW - 7 * 86400000;

  // ── 12-basket pulse ──
  // Portfolio-level read across the 12 Speculair methodology baskets.
  const BLABEL: Record<string, string> = {
    dcf_fcff: "DCF-FCFF", earnings_yield_gap: "Earnings Yield", ev_gross_profit: "Gross Profit.",
    rd_capitalized_dcf: "R&D DCF", owner_earnings: "Owner Earn.", epv: "EPV", graham_revised: "Graham",
    acquirers_multiple: "Acquirer's", ev_gp: "EV/GP", iv15_deep_value: "IV15 Deep",
    convergence: "Convergence", fundamental_momentum: "Fund. Mom.",
  };
  const md = (d: any) => { const x = new Date(d); return Number.isNaN(x.getTime()) ? "" : x.toLocaleDateString("en-US", { month: "short", day: "numeric" }); };
  const pmb: Record<string, any> = spec?.per_methodology_baskets || {};
  const basketRets = Object.keys(pmb).map((k) => ({ key: k, label: BLABEL[k] || k, ret: r2(num(pmb[k]?.ytd_return) * 100), start: pmb[k]?.tracking_start }));
  // Leader/Laggard: previously ranked ALL 12 by since-their-OWN-tracking_start
  // return — but 3 of the 12 started weeks later (06-02/06-04/06-10 vs the
  // majority's 05-27), so a later-started basket simply having had less time
  // to compound (or less time to draw down) made the "race" unfair. Restrict
  // the comparison to the cohort sharing the most common tracking_start (the
  // real majority launch date) — apples-to-apples, never a fabricated
  // since-May-27 return for a basket that didn't exist yet on May 27.
  const startCounts = new Map<string, number>();
  for (const b of basketRets) if (b.start) startCounts.set(b.start, (startCounts.get(b.start) || 0) + 1);
  const commonStart = [...startCounts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] || null;
  const comparableB = (commonStart ? basketRets.filter((b) => b.start === commonStart) : basketRets.slice())
    .sort((a, b) => b.ret - a.ret);
  const leaderB = comparableB[0] || null;
  const laggardB = comparableB[comparableB.length - 1] || null;
  const greenB = basketRets.filter((b) => b.ret > 0).length;

  // MTD/week basket winner — from methodology_tracking.json's nav_history, which
  // (unlike tracking_start) begins on the SAME date for all 12 baskets, so this
  // comparison is always apples-to-apples regardless of each basket's own launch
  // date. The log only started 2026-07-20, so right now both windows fall back to
  // that same short real span (week ≈ MTD) — honest given the real data, and it
  // naturally differentiates as more nightly snapshots accumulate.
  const methTrackMeths = methodologyTracking?.methodologies || {};
  const basketWindows = Object.keys(pmb).map((k) => {
    const hist = methTrackMeths[k]?.nav_history || [];
    return { key: k, label: BLABEL[k] || k, mtd: navReturnSince(hist, THIRTY_D_AGO), week: navReturnSince(hist, SEVEN_D_AGO), since: md(hist[0]?.date) };
  }).filter((b) => b.mtd != null).sort((a, b) => (b.mtd as number) - (a.mtd as number));
  const mtdWinnerB = basketWindows[0] || null;

  const apos: Record<string, any> = apexTrk?.positions || {};
  const alp: Record<string, any> = apexTrk?.last_prices || {};
  const nameRets = Object.keys(apos).map((sym) => {
    const e = num(apos[sym]?.entry_price); const last = num(alp[sym]);
    return e > 0 && last > 0 ? { sym, ret: r2((last / e - 1) * 100), since: md(apos[sym]?.entry_date) } : null;
  }).filter(Boolean).sort((a: any, b: any) => b.ret - a.ret) as any[];
  const basket_pulse = {
    total: basketRets.length,
    green: greenB,
    since_common: md(commonStart),
    leader: leaderB ? { label: leaderB.label, ret: leaderB.ret } : null,
    laggard: laggardB ? { label: laggardB.label, ret: laggardB.ret } : null,
    mtd_winner: mtdWinnerB ? { label: mtdWinnerB.label, mtd: r2(mtdWinnerB.mtd as number), week: mtdWinnerB.week != null ? r2(mtdWinnerB.week) : null, since: mtdWinnerB.since } : null,
    top_name: nameRets[0] || null,
    worst_name: nameRets.length > 1 ? nameRets[nameRets.length - 1] : null,
  };

  // ── System pulse footer — live calibration_tracking v2 coverage stat, NOT
  //    the frozen four-method tracker's win-rate (removed 2026-07-23; see
  //    [[feedback_no_hardcoded_decile_snapshots]]). matched_touch_pct is the
  //    touch rate among MATURED (resolved) picks only — a real, live number,
  //    not a fabricated one. ──
  const cyc30 = calibV2?.horizons?.["30d"]?.cycle || {};
  const matchedTouchPct = num(cyc30.n_matured) > 0 ? Math.round((num(cyc30.n_touched) / num(cyc30.n_matured)) * 100) : null;

  // Live tracking — Apex + Value Lens vs SPY, MATCHED windows. Previously this
  // compared the apex book's trailing-30d return against SPY's calendar-YTD
  // (two different spans dressed up as one comparison — the "MTD vs YTD" bug).
  // Fixed by measuring BOTH books over the same two windows — their own
  // trailing-30d ("MTD") and their own inception-to-date — and measuring SPY
  // over those SAME windows instead of a fixed calendar YTD. No book gets a
  // fabricated calendar-YTD either: both launched in June, so a Jan-1 baseline
  // would silently claim performance for months the book didn't exist.
  const apexMtdPct = navReturnSince(at.history, THIRTY_D_AGO);

  const vtWeighted = valueApex?.value_tracking_weighted;
  const vtIsWeighted = !!(vtWeighted && (vtWeighted.history || []).length >= 4);
  const vt = vtIsWeighted ? vtWeighted : (valueApex?.value_tracking || {});
  const valueMtdPct = navReturnSince(vt.history, THIRTY_D_AGO);

  const spySeries: { date: string; price: number }[] = (Array.isArray(spyHistRaw) ? spyHistRaw : [])
    .map((r: any) => ({ date: String(r.date || ""), price: num(r.price) }))
    .filter((p) => p.date && p.price > 0)
    .sort((a, b) => a.date.localeCompare(b.date));
  const spyPriceOn = (dateStr: string | null | undefined): number | null => {
    if (!dateStr || !spySeries.length) return null;
    const target = Date.parse(dateStr);
    if (!Number.isFinite(target)) return null;
    let anchor = spySeries[0];
    for (const p of spySeries) { if (Date.parse(p.date) >= target) { anchor = p; break; } }
    return anchor?.price ?? null;
  };
  const spyNow = num(spxR?.price, NaN);
  const spyReturnSinceDate = (dateStr: string | null | undefined): number | null => {
    const anchor = spyPriceOn(dateStr);
    return Number.isFinite(spyNow) && anchor ? ((spyNow / anchor) - 1) * 100 : null;
  };
  const spyMtdPct = spyReturnSinceDate(isoDate(THIRTY_D_AGO));

  const live_tracking = {
    spy_mtd_pct: spyMtdPct != null ? r2(spyMtdPct) : null,
    books: ([
      at?.since_inception_pct != null ? {
        key: "apex", label: "Apex",
        mtd_pct: apexMtdPct != null ? r2(apexMtdPct) : null,
        since_inception_pct: r2(sinceInc),
        since_label: md(at.inception_date),
        spy_since_inception_pct: (() => { const v = spyReturnSinceDate(at.inception_date); return v != null ? r2(v) : null; })(),
      } : null,
      vt?.since_inception_pct != null ? {
        key: "value", label: "Value Lens",
        mtd_pct: valueMtdPct != null ? r2(valueMtdPct) : null,
        since_inception_pct: r2(num(vt.since_inception_pct)),
        since_label: md(vt.inception_date),
        spy_since_inception_pct: (() => { const v = spyReturnSinceDate(vt.inception_date); return v != null ? r2(v) : null; })(),
      } : null,
    ] as any[]).filter(Boolean),
  };

  const system_pulse = {
    live_tracking,
    avg_coverage: matchedTouchPct != null
      ? `${matchedTouchPct}% touched of matured · ${num(cyc30.n_total)} tracked (30d live)`
      : `${num(cyc30.n_total)} tracked (30d live)`,
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

  // ── Target Watch — most substantial analyst price-target changes (last 30d) ──
  // Real deltas only: the prior target is parsed from the news title ("raised to
  // $250 from $220 at Firm"); rows without a parseable prior are dropped, never
  // approximated from priceWhenPosted. One row per symbol per direction — the
  // largest move wins, `n` counts that symbol's other same-direction changes.
  const PRIOR_RE = /from\s+\$([0-9][0-9,.]*)/i;
  const tRows: any[] = [];
  const seenTarget = new Set<string>();
  for (const r of targetsRaw) {
    const sym = String(r.symbol || "").trim().toUpperCase();
    const date = String(r.publishedDate || "").slice(0, 10);
    const pt = num(r.priceTarget);
    if (!sym || sym.includes(" ") || !pt || date < cutoffIso) continue;
    const m = PRIOR_RE.exec(String(r.newsTitle || ""));
    if (!m) continue;
    const prior = Number(m[1].replace(/,/g, "").replace(/\.$/, ""));
    if (!Number.isFinite(prior) || prior <= 0 || prior === pt) continue;
    const firm = String(r.analystCompany || r.analystName || "—");
    const key = `${sym}|${firm}|${date}|${pt}`;
    if (seenTarget.has(key)) continue;
    seenTarget.add(key);
    const px = num(r.priceWhenPosted);
    tRows.push({
      symbol: sym, firm, prior, target: pt,
      delta: r2(((pt - prior) / prior) * 100),
      implied: px > 0 ? r2((pt / px - 1) * 100) : null,
      date,
      apex: apexSyms.has(sym),
    });
  }
  const bestByDir = new Map<string, any>();
  for (const t of tRows) {
    const k = `${t.symbol}|${t.delta >= 0 ? "up" : "down"}`;
    const cur = bestByDir.get(k);
    if (!cur) bestByDir.set(k, { ...t, n: 1 });
    else if (Math.abs(t.delta) > Math.abs(cur.delta)) bestByDir.set(k, { ...t, n: cur.n + 1 });
    else cur.n++;
  }
  const tBest = [...bestByDir.values()];
  const target_watch = tRows.length
    ? {
        window_days: 30,
        total_changes: tRows.length,
        raises_count: tRows.filter((t) => t.delta > 0).length,
        cuts_count: tRows.filter((t) => t.delta < 0).length,
        raises: tBest.filter((t) => t.delta > 0).sort((a, b) => b.delta - a.delta).slice(0, 6),
        cuts: tBest.filter((t) => t.delta < 0).sort((a, b) => a.delta - b.delta).slice(0, 6),
        // Oldest published date actually fetched — if later than the 30d cutoff,
        // the window is truncated by feed depth (8×1000 rows) and the card says so.
        coverage_from: tRows.reduce((m, t) => (t.date < m ? t.date : m), "9999-12-31"),
      }
    : null;

  // ── Headline ──
  const headline = `${sentiment} Apex basket ${sign(sinceInc)}${r2(sinceInc)}% since inception, ${nOpen} names live.`;

  return NextResponse.json({
    headline,
    generated_at: new Date().toISOString(),
    regime_pulse,
    model_focus,
    radar_watch,
    basket_pulse,
    system_pulse,
    thermometer,
    debate,
    congress,
    target_watch,
  });
}
