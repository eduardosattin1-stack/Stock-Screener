import { NextResponse } from "next/server";

// Daily Briefing — assembled entirely from LIVE wired data. No dependency on the
// (stale, composite-era) backend /briefing endpoint. Sources:
//   ?regime / ?score (query)        authoritative scan macro, passed by the page
//                                   (keeps the briefing in sync with the footer regime)
//   /api/macro                      fallback regime + rates/credit/VIX posture
//   /api/sectors                    index thermometer + hottest GICS sector
//   /api/performance/method-tracks  D8+ model-calibrated picks (decile, p20, EV) + worst miss
//   /speculair_baskets.json         apex basket NAV, debate stats, top picks, watchlist

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

  const [macro, sectors, methodTracks, spec] = await Promise.all([
    get("/api/macro", {}),
    get("/api/sectors", {}),
    get("/api/performance/method-tracks", { regimes: {} }),
    get("/speculair_baskets.json", {}),
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

  // ── Portfolio Pulse (Apex basket NAV — from speculair apex_tracking) ──
  const at = spec?.apex_tracking || {};
  const hist: any[] = at.history || [];
  const lastRet = hist.length ? num(hist[hist.length - 1].ret) * 100 : num(at.since_inception_pct);
  const sinceInc = num(at.since_inception_pct);
  const nOpen = num(at.n_open, (spec?.apex_basket || []).length);
  const nClosed = num(at.n_closed);
  const wr = at.win_rate;
  const portfolio_pulse = {
    pnl_delta_pct: r2(lastRet),
    triggers_count: 0,
    triggers_text: `${nOpen} names held since ${at.inception_date || "inception"} · ${sign(sinceInc)}${r2(sinceInc)}% since inception (NAV $${r2(num(at.nav, 100))}).`,
    downgrades_count: nClosed,
    downgrades_text:
      nClosed > 0
        ? `${nClosed} rotated out · win rate ${wr != null ? Math.round(num(wr) * 100) + "%" : "—"}.`
        : "No rotations yet — director re-runs on its monthly cadence.",
  };

  // ── Active Strategy (Apex top conviction — from speculair apex_basket) ──
  const apex: any[] = (spec?.apex_basket || [])
    .slice()
    .sort((a: any, b: any) => num(b.conviction) - num(a.conviction));
  const active_strategy = {
    name: "APEX",
    top_picks: apex.slice(0, 3).map((p: any) => ({
      symbol: p.symbol,
      score: num(p.conviction),
      is_new: !p.held_since_prior,
    })),
    avg_coverage: `${apex.length} names · ${regime} regime`,
  };

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
      });
    }
  }

  // D8+ = the model's current highest-conviction tier (D9/D10 legitimately empty —
  // the live model's top probability clips below those thresholds; do not back-fill).
  const d8 = stockRows
    .filter((r) => r.decile >= 8)
    .sort(
      (a, b) =>
        (a.outcome === "OPEN" ? 0 : 1) - (b.outcome === "OPEN" ? 0 : 1) ||
        b.prob - a.prob ||
        b.decile - a.decile
    );

  // ── Surprising Movers (top D8 model picks + hottest GICS sector) ──
  const surprising_movers: any[] = [];
  for (const p of d8.slice(0, 2)) {
    const peakTxt = p.maxPlus > 0.5 ? ` · peaked +${r2(p.maxPlus)}%` : "";
    const tagTxt = p.outcome !== "OPEN" ? ` · ${String(p.outcome).replace(/_/g, " ").toLowerCase()}` : "";
    surprising_movers.push({
      symbol: p.symbol,
      delta: `D${p.decile}`,
      reason: `${p.probLabel} ${Math.round(p.prob * 100)}%${peakTxt}${tagTxt}.`,
      evStr: p.ev != null ? `EV ${usd(p.ev)}` : null,
      evNeg: p.ev != null && p.ev < 0,
    });
  }
  const secs: any[] = (sectors?.sectors || []).filter((s: any) => s.day != null);
  const hotSec = secs.slice().sort((a, b) => num(b.day) - num(a.day))[0];
  if (hotSec) {
    surprising_movers.push({
      symbol: hotSec.name,
      delta: `${sign(num(hotSec.day))}${r2(num(hotSec.day))}%`,
      neg: num(hotSec.day) < 0,
      reason: `Hottest GICS sector on the tape today (${hotSec.symbol}).`,
    });
  }

  // ── System pulse footer (live tracking — from method-tracks 30d stock cycle) ──
  const stock30 = methodTracks?.regimes?.["30d_p10"]?.current_cycle?.by_method?.stock || {};
  const system_pulse = {
    live_mtd: `${sign(num(stock30.portfolio_return_pct))}${r2(num(stock30.portfolio_return_pct))}%`,
    spy_mtd: spxR?.ytd != null ? `${sign(num(spxR.ytd))}${r2(num(spxR.ytd))}% YTD` : "—",
    avg_coverage: `${Math.round(num(stock30.winning_trade_rate) * 100)}% win · ${num(stock30.n)} tracked (30d)`,
  };

  // ── System Debate ACT / WAIT (from speculair debate_stats + watchlist) ──
  const ds = spec?.debate_stats || {};
  const watch = (spec?.capitulation_watchlist || []).length;
  const debate = {
    act:
      ds.apex_selected != null
        ? `${ds.apex_selected} names cleared the full multi-agent debate into the apex${ds.fully_debated != null ? ` (of ${ds.fully_debated} debated)` : ""}.`
        : `${apex.length} names hold the apex after the debate.`,
    wait: `${watch} on the capitulation watchlist${ds.radar_filtered != null ? ` · ${ds.radar_filtered} filtered pre-debate` : ""}${ds.auto_vetoed != null ? ` · ${ds.auto_vetoed} auto-vetoed` : ""}.`,
  };

  // ── System Miss (worst open tracker position — real drawdown, with model context) ──
  const worst = stockRows.filter((r) => r.outcome === "OPEN").sort((a, b) => a.liveRet - b.liveRet)[0];
  const miss = worst
    ? {
        symbol: worst.symbol,
        loss_pct: r2(worst.liveRet),
        reason: `D${worst.decile} model pick (${worst.probLabel} ${Math.round(worst.prob * 100)}%) but ${worst.liveRet < 0 ? "down" : "flat"} ${r2(Math.abs(worst.liveRet))}% — ${worst.sector || "—"}. Watching whether the window redeems it.`,
      }
    : { symbol: "—", loss_pct: 0, reason: "No open tracker positions underwater yet." };

  // ── Headline ──
  const headline = `${sentiment} Apex basket ${sign(sinceInc)}${r2(sinceInc)}% since inception, ${nOpen} names live.`;

  return NextResponse.json({
    headline,
    regime_pulse,
    portfolio_pulse,
    active_strategy,
    surprising_movers,
    system_pulse,
    thermometer,
    debate,
    miss,
  });
}
