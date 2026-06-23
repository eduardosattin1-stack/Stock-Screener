"use client";
import React, { useState, useEffect, useCallback } from 'react';
import { useRouter } from "next/navigation";
import { Activity, RefreshCw, BarChart2, Target, Radar, Calendar, TrendingUp, TrendingDown, Award } from 'lucide-react';
import { useAuth } from "../AuthProvider";
import { getPortfolio } from "../portfolioStore";

// ── Regime Pulse (shared) ───────────────────────────────────────────────────
// Rich macro card used both inside the Daily Briefing (default view) and
// standalone on the Table view, so the regime read is available app-wide and
// consolidates the sub-signals ("the other values") into one card. Sub-signals
// come from the scan macro (data.macro.sub_scores/features) when present, else
// the lite /api/macro fallback.
const REGIME_PULSE_C: Record<string, string> = {
  RISK_ON: "var(--green)", NEUTRAL: "var(--amber)", CAUTIOUS: "var(--amber)", RISK_OFF: "var(--red)",
};
function regimeSig(label: string, v?: number, detail?: string) {
  if (v == null) return null;
  const bc = v >= 0.6 ? "var(--green)" : v >= 0.4 ? "var(--amber)" : "var(--red)";
  return (
    <div key={label} style={{ display: "flex", flexDirection: "column", gap: 3 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--text-muted)" }}>
        <span>{label}</span>{detail != null && <span style={{ color: "var(--text-light)" }}>{detail}</span>}
      </div>
      <div style={{ height: 4, background: "var(--bg-elevated)", borderRadius: 2, overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${Math.round(Math.max(0, Math.min(1, v)) * 100)}%`, background: bc, borderRadius: 2 }} />
      </div>
    </div>
  );
}
export function RegimePulseDetail({ macro }: { macro?: any }) {
  if (!macro) return null;
  const subs = macro.sub_scores || {};
  const feat = macro.features || {};
  const rd = macro.regime_detail || {};
  const bp = (x?: number) => (x == null ? undefined : `${x > 0 ? "+" : ""}${x}bp`);
  const cells = [
    regimeSig("Yield curve", subs.yield_curve, bp(feat.macro_yield_spread_2y)),
    regimeSig("Curve 3m", subs.yield_curve_3m, bp(feat.macro_yield_spread_3m)),
    regimeSig("Rate level", subs.yield_level, feat.macro_yield_level != null ? `${feat.macro_yield_level}%` : undefined),
    regimeSig("VIX", subs.vix, feat.macro_vix != null ? `${feat.macro_vix}` : undefined),
    regimeSig("CPI trend", subs.cpi_trend),
    regimeSig("Growth", subs.gdp_momentum),
    regimeSig("Jobs", subs.unemployment),
    regimeSig("Sentiment", subs.consumer_sentiment),
  ].filter(Boolean);
  const showGrowth = rd.growth && String(rd.growth).indexOf("Unknown") < 0;
  if (!cells.length && !rd.rates && !rd.credit) return null;
  return (
    <div style={{ borderTop: "1px dashed var(--border)", paddingTop: 12, marginTop: 12 }}>
      {cells.length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "9px 16px" }}>{cells}</div>
      )}
      {(rd.rates || rd.credit) && (
        <div style={{ marginTop: cells.length ? 12 : 0, fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-muted)" }}>
          Rates <b style={{ color: "var(--text)" }}>{rd.rates || "—"}</b> · Credit <b style={{ color: "var(--text)" }}>{rd.credit || "—"}</b>
          {showGrowth && <> · Growth <b style={{ color: "var(--text)" }}>{rd.growth}</b></>}
        </div>
      )}
    </div>
  );
}
export function RegimePulseCard({ macro }: { macro?: any }) {
  if (!macro || !macro.regime) return null;
  const c = REGIME_PULSE_C[macro.regime] || "var(--amber)";
  const score = macro.score ?? 0.5;
  return (
    <div style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 12, padding: 20, maxWidth: 380 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
        <Activity size={14} color="var(--amber)" />
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.18em", color: "var(--text-muted)", textTransform: "uppercase" }}>Regime Pulse</span>
        <span style={{ marginLeft: "auto", fontFamily: "var(--font-mono)", fontSize: 8, color: "var(--text-light)", fontStyle: "italic" }}>{macro.version || "v8"}</span>
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 4 }}>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 15, fontWeight: 700, color: c }}>{macro.regime}</span>
        <div style={{ flex: 1, height: 5, background: "var(--bg-elevated)", borderRadius: 3, overflow: "hidden" }}>
          <div style={{ height: "100%", width: `${Math.round(score * 100)}%`, background: c, borderRadius: 3 }} />
        </div>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700, color: c }}>{Math.round(score * 100)}</span>
      </div>
      <RegimePulseDetail macro={macro} />
    </div>
  );
}

// ── On Your Radar — personalized, client-computed ───────────────────────────
// Earnings within 10 days + >3% intraday moves on the names the user actually
// holds (per-user Firestore) or watches (localStorage). These are the only two
// data stores the server route can't reach, so this card is built in the client.
interface RadarItem { sym: string; kind: "earnings" | "move"; tag: "HELD" | "WATCH"; dte?: number; day?: number; name?: string; }

function useRadarItems(stocks: any[] | undefined, uid: string | undefined, nonce: number) {
  const [items, setItems] = useState<RadarItem[]>([]);
  const [counts, setCounts] = useState<{ held: number; watch: number }>({ held: 0, watch: 0 });
  const [status, setStatus] = useState<"loading" | "empty-none" | "empty-quiet" | "ready">("loading");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setStatus("loading");
      // Watchlist (localStorage) — flatten symbols across all baskets.
      let watch: string[] = [];
      try {
        const raw = typeof window !== "undefined" ? localStorage.getItem("cb_watchlist_baskets") : null;
        if (raw) watch = (JSON.parse(raw) || []).flatMap((b: any) => b?.symbols || []);
      } catch { /* ignore */ }
      // Holdings (per-user Firestore).
      let held: string[] = [];
      try { if (uid) held = ((await getPortfolio(uid)).positions || []).map((p) => p.symbol); } catch { /* ignore */ }

      const heldSet = new Set(held.map((s) => String(s).toUpperCase()));
      const watchSet = new Set(watch.map((s) => String(s).toUpperCase()));
      const union = Array.from(new Set([...heldSet, ...watchSet]));
      if (cancelled) return;
      setCounts({ held: heldSet.size, watch: watchSet.size });
      if (!union.length) { setStatus("empty-none"); setItems([]); return; }

      // Live day-change in batches of 12 (the /api/quotes cap).
      const quotes: Record<string, any> = {};
      for (let i = 0; i < union.length; i += 12) {
        const batch = union.slice(i, i + 12);
        try {
          const r = await fetch(`/api/quotes?symbols=${encodeURIComponent(batch.join(","))}`);
          const d = await r.json();
          for (const q of d?.quotes || []) quotes[String(q.symbol).toUpperCase()] = q;
        } catch { /* ignore */ }
      }
      // Earnings / sector / name from the loaded scan universe.
      const byScan: Record<string, any> = {};
      for (const s of stocks || []) byScan[String(s.symbol).toUpperCase()] = s;

      const out: RadarItem[] = [];
      for (const sym of union) {
        const q = quotes[sym];
        const sc = byScan[sym];
        const tag: "HELD" | "WATCH" = heldSet.has(sym) ? "HELD" : "WATCH";
        const name = q?.name || sc?.company_name;
        const dte = sc?.days_to_earnings;
        if (dte != null && dte >= 0 && dte <= 10) out.push({ sym, kind: "earnings", tag, dte, name });
        const day = q?.day;
        if (day != null && Math.abs(day) >= 3) out.push({ sym, kind: "move", tag, day, name });
      }
      // Earnings first (soonest), then moves (biggest).
      out.sort((a, b) => {
        const ak = a.kind === "earnings" ? 0 : 1, bk = b.kind === "earnings" ? 0 : 1;
        if (ak !== bk) return ak - bk;
        if (a.kind === "earnings") return (a.dte ?? 0) - (b.dte ?? 0);
        return Math.abs(b.day ?? 0) - Math.abs(a.day ?? 0);
      });
      if (cancelled) return;
      setItems(out);
      setStatus(out.length ? "ready" : "empty-quiet");
    })();
    return () => { cancelled = true; };
  }, [stocks, uid, nonce]);

  return { items, counts, status };
}

export function DailyBriefing({ macroRegime, macroScore, macro, stocks }: { macroRegime?: string | null; macroScore?: number | null; macro?: any; stocks?: any[] }) {
  const router = useRouter();
  const { user } = useAuth();
  const [briefing, setBriefing] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);

  const radar = useRadarItems(stocks, user?.uid, nonce);

  useEffect(() => {
    // Prefer the authoritative scan-macro regime/score (so Regime Pulse matches the
    // Sector-Performance footer). Wait for it briefly to avoid a lite-macro RISK_ON
    // flash; after a grace period, load the fallback so the card never hangs.
    let cancelled = false;
    const load = (rg?: string | null) => {
      const qs = rg ? `?regime=${encodeURIComponent(rg)}&score=${macroScore ?? ""}` : "";
      fetch(`/api/briefing${qs}`)
        .then(res => res.json())
        .then(data => { if (!cancelled) { setBriefing(data); setLoading(false); } })
        .catch(err => { console.error("Failed to fetch daily briefing:", err); if (!cancelled) setLoading(false); });
    };
    if (macroRegime) { load(macroRegime); }
    else { const t = setTimeout(() => { if (!cancelled) load(null); }, 1800); return () => { cancelled = true; clearTimeout(t); }; }
    return () => { cancelled = true; };
  }, [macroRegime, macroScore, nonce]);

  if (loading) {
    return (
      <div style={{ marginBottom: 48, background: "var(--bg-surface)", borderBottom: "1px solid var(--border)", padding: "32px 48px", borderRadius: "0 0 16px 16px", display: "flex", justifyContent: "center", alignItems: "center", height: "300px" }}>
        <RefreshCw size={24} color="var(--text-muted)" style={{ animation: "spin 2s linear infinite" }} />
      </div>
    );
  }

  if (!briefing || briefing.error) {
    return null;
  }

  const { headline, generated_at, regime_pulse, model_focus, basket_pulse, system_pulse, thermometer, debate } = briefing;

  const asOf = (() => {
    if (!generated_at) return null;
    const d = new Date(generated_at);
    return Number.isNaN(d.getTime()) ? null : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  })();

  const renderThermoItem = (label: string, data: any) => {
    if (!data) return null;
    const isPos = data.change_pct >= 0;
    const color = isPos ? "var(--green)" : "var(--red)";
    return (
      <div key={label} style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-muted)", fontWeight: 600 }}>{label}</div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text)", fontWeight: 700 }}>
            {data.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </span>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: color, fontWeight: 600 }}>
            {isPos ? "+" : ""}{data.change_pct.toFixed(2)}%
          </span>
        </div>
      </div>
    );
  };

  const tagChip = (tag: "HELD" | "WATCH") => (
    <span style={{ fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.08em", color: tag === "HELD" ? "var(--green)" : "var(--lavender)", background: tag === "HELD" ? "var(--green-light)" : "var(--purple-light)", padding: "1px 5px", borderRadius: 3 }}>{tag}</span>
  );

  return (
    <div style={{ marginBottom: 48, background: "var(--bg-surface)", borderBottom: "1px solid var(--border)", padding: "32px 48px", borderRadius: "0 0 16px 16px" }}>
      {/* ── HEADLINE STRIP & THERMOMETER ── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 32 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 16, maxWidth: "65%" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, whiteSpace: "nowrap" }}>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, letterSpacing: "0.18em", color: "var(--green)", textTransform: "uppercase", fontWeight: 700 }}>
              Daily Briefing
            </span>
            {asOf && (
              <button
                onClick={() => setNonce((n) => n + 1)}
                title="Refresh briefing"
                style={{ display: "inline-flex", alignItems: "center", gap: 4, background: "none", border: "none", cursor: "pointer", padding: 0, fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--text-light)" }}>
                <RefreshCw size={10} /> as of {asOf}
              </button>
            )}
          </div>
          <div style={{ fontFamily: "var(--font-serif)", fontSize: 22, fontWeight: 300, fontStyle: "italic", color: "var(--text)", lineHeight: 1.3 }}>
            {headline}
          </div>
        </div>

        {/* ── INDEX THERMOMETER ── */}
        {thermometer && Object.keys(thermometer).length > 0 && (
          <div style={{ display: "flex", gap: 24, background: "var(--bg)", padding: "12px 20px", borderRadius: 8, border: "1px solid var(--border)", boxShadow: "0 2px 8px rgba(0,0,0,0.2)" }}>
            {renderThermoItem("S&P 500", thermometer["SPX"])}
            {renderThermoItem("NASDAQ", thermometer["NDX"])}
            {renderThermoItem("RUSSELL", thermometer["RUT"])}
            {renderThermoItem("VIX", thermometer["VIX"])}
          </div>
        )}
      </div>

      {/* ── 3-CARD GRID ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 1 }}>

        {/* Card 1: Regime pulse */}
        <div style={{ background: "var(--bg)", padding: 24, border: "1px solid var(--border)", borderRadius: "12px 0 0 12px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
            <Activity size={14} color="var(--amber)" />
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.18em", color: "var(--text-muted)", textTransform: "uppercase" }}>Regime Pulse</span>
          </div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 14, fontWeight: 700, color: regime_pulse.regime === "RISK_ON" ? "var(--green)" : regime_pulse.regime === "RISK_OFF" ? "var(--red)" : "var(--amber)", marginBottom: 8 }}>
            {regime_pulse.regime} <span style={{ color: "var(--text-light)", fontWeight: 400 }}>{regime_pulse.score}</span>
          </div>
          <div style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.5, fontFamily: "var(--font-sans)", marginBottom: 12 }}>
            {regime_pulse.summary}
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-mono)", borderTop: "1px dashed var(--border)", paddingTop: 12 }}>
            <strong style={{ color: "var(--text)", fontWeight: 600 }}>Action:</strong> {regime_pulse.action}
          </div>
          <RegimePulseDetail macro={macro} />
        </div>

        {/* Card 2: On Your Radar (personalized) */}
        <div style={{ background: "var(--bg)", padding: 24, borderTop: "1px solid var(--border)", borderBottom: "1px solid var(--border)", display: "flex", flexDirection: "column" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Radar size={14} color="var(--green)" />
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.18em", color: "var(--text-muted)", textTransform: "uppercase" }}>On Your Radar</span>
            </div>
            {(radar.counts.held > 0 || radar.counts.watch > 0) && (
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--text-light)" }}>{radar.counts.held} held · {radar.counts.watch} watch</span>
            )}
          </div>

          {radar.status === "loading" && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--text-light)", fontFamily: "var(--font-mono)", fontSize: 11 }}>
              <RefreshCw size={12} style={{ animation: "spin 2s linear infinite" }} /> Scanning your names…
            </div>
          )}
          {radar.status === "empty-none" && (
            <div style={{ fontSize: 12, color: "var(--text-muted)", fontFamily: "var(--font-sans)", lineHeight: 1.5 }}>
              Add holdings or build a watchlist and this card will surface earnings dates and big moves on your names.
            </div>
          )}
          {radar.status === "empty-quiet" && (
            <div style={{ fontSize: 12, color: "var(--text-muted)", fontFamily: "var(--font-sans)", lineHeight: 1.5 }}>
              Nothing pressing — no earnings within 10 days and no moves over 3% across your {radar.counts.held + radar.counts.watch} name{radar.counts.held + radar.counts.watch !== 1 ? "s" : ""} today.
            </div>
          )}
          {radar.status === "ready" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {radar.items.slice(0, 5).map((it, i) => (
                <div key={`${it.sym}-${it.kind}-${i}`} onClick={() => router.push(`/stock/${encodeURIComponent(it.sym)}`)} style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                  {it.kind === "earnings" ? <Calendar size={12} color="var(--amber)" style={{ flexShrink: 0 }} /> : <TrendingUp size={12} color={(it.day ?? 0) >= 0 ? "var(--green)" : "var(--red)"} style={{ flexShrink: 0 }} />}
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700, color: "var(--text)" }}>{it.sym}</span>
                  {tagChip(it.tag)}
                  <span style={{ marginLeft: "auto", fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 600, color: it.kind === "earnings" ? "var(--amber)" : (it.day ?? 0) >= 0 ? "var(--green)" : "var(--red)" }}>
                    {it.kind === "earnings" ? (it.dte === 0 ? "Earnings today" : `Earnings ${it.dte}d`) : `${(it.day ?? 0) >= 0 ? "+" : ""}${(it.day ?? 0).toFixed(2)}%`}
                  </span>
                </div>
              ))}
              {radar.items.length > 5 && (
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--text-light)", marginTop: 2 }}>+{radar.items.length - 5} more on your names</div>
              )}
            </div>
          )}
        </div>

        {/* Card 3: Model Focus — weekly pulse: NEW D9/D10 model signals + weekly hot sector */}
        <div style={{ background: "var(--bg)", padding: 24, border: "1px solid var(--border)", borderRadius: "0 12px 12px 0" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Target size={14} color="var(--lavender)" />
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.18em", color: "var(--text-muted)", textTransform: "uppercase" }}>Model Focus</span>
            </div>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--lavender)", background: "var(--purple-light)", padding: "2px 6px", borderRadius: 4, letterSpacing: "0.1em" }}>WEEKLY</span>
          </div>

          <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, letterSpacing: "0.16em", color: "var(--text-light)", textTransform: "uppercase", marginBottom: 10 }}>New D9/D10 signals</div>
          {model_focus?.picks?.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
              {model_focus.picks.map((p: any) => (
                <div key={p.symbol} onClick={() => router.push(`/stock/${encodeURIComponent(p.symbol)}`)} style={{ cursor: "pointer" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700, color: "var(--text)" }}>{p.symbol}</span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--lavender)", background: "var(--purple-light)", padding: "1px 5px", borderRadius: 3 }}>D{p.decile}</span>
                    {p.evStr && <span style={{ marginLeft: "auto", fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 600, color: p.evNeg ? "var(--red)" : "var(--green)" }}>{p.evStr}</span>}
                  </div>
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--text-muted)", marginTop: 1 }}>{p.probLabel} {Math.round(p.prob * 100)}%{p.peak > 0.5 ? ` · peaked +${p.peak}%` : ""}</div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ fontSize: 12, color: "var(--text-muted)", fontFamily: "var(--font-sans)", lineHeight: 1.5 }}>
              No new D9/D10 signals entered this week.
            </div>
          )}

          {model_focus?.hot_sector && (
            <div style={{ borderTop: "1px dashed var(--border)", paddingTop: 12, marginTop: 12, fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-muted)" }}>
              Hot sector{model_focus.hot_sector.is_week ? " (1wk)" : ""}: <b style={{ color: "var(--text)" }}>{model_focus.hot_sector.name}</b> <span style={{ color: model_focus.hot_sector.neg ? "var(--red)" : "var(--green)" }}>{model_focus.hot_sector.neg ? "" : "+"}{model_focus.hot_sector.week}%</span>
            </div>
          )}
        </div>
      </div>

      {/* ── SYSTEM DEBATE & SYSTEM MISS ── */}
      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 24, marginTop: 32 }}>

        {/* Opposing One-Liners */}
        <div style={{ background: "var(--bg)", padding: 20, borderRadius: 8, border: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.18em", color: "var(--text-muted)", textTransform: "uppercase", marginBottom: 4 }}>System Debate</div>
          {debate.new_tickers?.length > 0 && (
            <div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--text-light)", marginBottom: 6 }}>Latest into the apex — tap to read the debate</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {debate.new_tickers.slice(0, 8).map((t: string) => (
                  <button key={t} onClick={() => router.push(`/stock/${encodeURIComponent(t)}?tab=debate`)} style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700, color: "var(--green)", background: "var(--green-light)", border: "none", borderRadius: 4, padding: "3px 8px", cursor: "pointer" }}>{t}</button>
                ))}
                {debate.new_tickers.length > 8 && <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-light)", alignSelf: "center" }}>+{debate.new_tickers.length - 8} more</span>}
              </div>
            </div>
          )}
          <div style={{ display: "flex", gap: 12 }}>
            <div style={{ flex: 1, paddingRight: 16, borderRight: "1px solid var(--border-subtle)" }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700, color: "var(--green)", marginRight: 8 }}>ACT</span>
              <span style={{ fontSize: 13, color: "var(--text-secondary)", fontFamily: "var(--font-sans)" }}>{debate.act}</span>
            </div>
            <div style={{ flex: 1, paddingLeft: 4 }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700, color: "var(--amber)", marginRight: 8 }}>WAIT</span>
              <span style={{ fontSize: 13, color: "var(--text-secondary)", fontFamily: "var(--font-sans)" }}>{debate.wait}</span>
            </div>
          </div>
          {/* Live-tracking footer (system pulse) */}
          <div style={{ display: "flex", gap: 20, borderTop: "1px dashed var(--border)", paddingTop: 12, marginTop: 4 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
              <RefreshCw size={12} /> Live tracking: <strong style={{ color: "var(--green)" }}>{system_pulse.live_mtd} MTD</strong> vs SPY {system_pulse.spy_mtd}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
              <BarChart2 size={12} /> {system_pulse.avg_coverage}
            </div>
          </div>
        </div>

        {/* 12-basket pulse — leader / laggard / top single name across the methodology baskets */}
        <div style={{ background: "var(--bg)", padding: 20, borderRadius: 8, border: "1px solid var(--border)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.18em", color: "var(--text-muted)", textTransform: "uppercase" }}>Basket Pulse</span>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--text-light)" }}>{basket_pulse?.total ?? 12} baskets</span>
          </div>
          {basket_pulse && (basket_pulse.leader || basket_pulse.top_name) ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
              {basket_pulse.leader && (
                <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-secondary)" }}><TrendingUp size={11} style={{ verticalAlign: -1, marginRight: 4, color: "var(--green)" }} />Leader: <b style={{ color: "var(--text)" }}>{basket_pulse.leader.label}</b></span>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700, color: basket_pulse.leader.ret >= 0 ? "var(--green)" : "var(--red)" }}>{basket_pulse.leader.ret >= 0 ? "+" : ""}{basket_pulse.leader.ret}%</span>
                </div>
              )}
              {basket_pulse.laggard && (
                <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-secondary)" }}><TrendingDown size={11} style={{ verticalAlign: -1, marginRight: 4, color: "var(--red)" }} />Laggard: <b style={{ color: "var(--text)" }}>{basket_pulse.laggard.label}</b></span>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700, color: basket_pulse.laggard.ret >= 0 ? "var(--green)" : "var(--red)" }}>{basket_pulse.laggard.ret >= 0 ? "+" : ""}{basket_pulse.laggard.ret}%</span>
                </div>
              )}
              {basket_pulse.top_name && (
                <div onClick={() => router.push(`/stock/${encodeURIComponent(basket_pulse.top_name.sym)}`)} style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8, cursor: "pointer" }}>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-secondary)" }}><Award size={11} style={{ verticalAlign: -1, marginRight: 4, color: "var(--amber)" }} />Top name: <b style={{ color: "var(--text)" }}>{basket_pulse.top_name.sym}</b></span>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700, color: basket_pulse.top_name.ret >= 0 ? "var(--green)" : "var(--red)" }}>{basket_pulse.top_name.ret >= 0 ? "+" : ""}{basket_pulse.top_name.ret}%</span>
                </div>
              )}
              <div style={{ borderTop: "1px dashed var(--border)", paddingTop: 10, marginTop: 2, fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-muted)" }}>
                {basket_pulse.green}/{basket_pulse.total} baskets green{basket_pulse.leader?.since ? ` · since ${basket_pulse.leader.since}` : ""}{basket_pulse.top_name?.since ? ` · top name since ${basket_pulse.top_name.since}` : ""}
              </div>
            </div>
          ) : (
            <div style={{ fontSize: 12, color: "var(--text-muted)", fontFamily: "var(--font-sans)", lineHeight: 1.5 }}>Basket tracking not available yet.</div>
          )}
        </div>

      </div>

    </div>
  );
}
