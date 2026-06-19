"use client";
import React, { useState, useEffect } from 'react';
import { Activity, Clock, AlertTriangle, Zap, RefreshCw, BarChart2, Shield, Target } from 'lucide-react';

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

export function DailyBriefing({ macroRegime, macroScore, macro }: { macroRegime?: string | null; macroScore?: number | null; macro?: any }) {
  const [briefing, setBriefing] = useState<any>(null);
  const [loading, setLoading] = useState(true);

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
  }, [macroRegime, macroScore]);

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

  const {
    headline,
    regime_pulse,
    portfolio_pulse,
    active_strategy,
    surprising_movers,
    system_pulse,
    thermometer,
    debate,
    miss
  } = briefing;

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

  return (
    <div style={{ marginBottom: 48, background: "var(--bg-surface)", borderBottom: "1px solid var(--border)", padding: "32px 48px", borderRadius: "0 0 16px 16px" }}>
      {/* ── HEADLINE STRIP & THERMOMETER ── */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 32 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 16, maxWidth: "65%" }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, letterSpacing: "0.18em", color: "var(--green)", textTransform: "uppercase", fontWeight: 700, whiteSpace: "nowrap" }}>
            Daily Briefing
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

      {/* ── 4-CARD GRID ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 1 }}>
        
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

        {/* Card 2: Portfolio pulse */}
        <div style={{ background: "var(--bg)", padding: 24, borderTop: "1px solid var(--border)", borderBottom: "1px solid var(--border)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
            <Shield size={14} color="var(--text-muted)" />
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.18em", color: "var(--text-muted)", textTransform: "uppercase" }}>Portfolio Pulse</span>
          </div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 8 }}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 14, fontWeight: 700, color: portfolio_pulse.pnl_delta_pct >= 0 ? "var(--green)" : "var(--red)" }}>
              {portfolio_pulse.pnl_delta_pct > 0 ? "+" : ""}{portfolio_pulse.pnl_delta_pct}%
            </div>
            <div style={{ fontSize: 11, color: "var(--text-light)", fontFamily: "var(--font-mono)" }}>vs yesterday</div>
          </div>
          <div style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.5, fontFamily: "var(--font-sans)", marginBottom: 12 }}>
            <span style={{ color: "var(--red)", fontWeight: 600 }}>{portfolio_pulse.triggers_count} trigger{portfolio_pulse.triggers_count !== 1 ? 's' : ''}:</span> {portfolio_pulse.triggers_text}
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-mono)", borderTop: "1px dashed var(--border)", paddingTop: 12 }}>
            <strong style={{ color: "var(--amber)", fontWeight: 600 }}>{portfolio_pulse.downgrades_count} downgrade{portfolio_pulse.downgrades_count !== 1 ? 's' : ''}:</strong> {portfolio_pulse.downgrades_text}
          </div>
        </div>

        {/* Card 3: Active strategy lens */}
        <div style={{ background: "var(--bg)", padding: 24, borderTop: "1px solid var(--border)", borderBottom: "1px solid var(--border)", borderLeft: "1px solid var(--border)" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Target size={14} color="var(--lavender)" />
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.18em", color: "var(--text-muted)", textTransform: "uppercase" }}>Active Strategy</span>
            </div>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--lavender)", background: "var(--purple-light)", padding: "2px 6px", borderRadius: 4 }}>{active_strategy.name}</span>
          </div>
          
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {active_strategy.top_picks.map((pick: any) => (
              <div key={pick.symbol} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700, color: "var(--text)" }}>
                  {pick.symbol}
                  {pick.is_new && <span style={{ fontSize: 9, color: "var(--amber)", marginLeft: 6, fontWeight: 500 }}>NEW</span>}
                </span>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--green)", fontWeight: 700 }}>{pick.score}</span>
              </div>
            ))}
          </div>
          <div style={{ fontSize: 11, color: "var(--text-light)", fontFamily: "var(--font-mono)", borderTop: "1px dashed var(--border)", paddingTop: 12, marginTop: 12 }}>
            Avg coverage: {active_strategy.avg_coverage}
          </div>
        </div>

        {/* Card 4: Surprising movers */}
        <div style={{ background: "var(--bg)", padding: 24, border: "1px solid var(--border)", borderRadius: "0 12px 12px 0", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
              <Zap size={14} color="var(--green)" />
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.18em", color: "var(--text-muted)", textTransform: "uppercase" }}>Surprising Movers</span>
            </div>
            
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {surprising_movers.map((mover: any, idx: number) => (
                <div key={idx}>
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700, color: "var(--text)", marginBottom: 2 }}>
                    {mover.symbol} {mover.delta && <span style={{ color: mover.neg ? "var(--red)" : "var(--green)", marginLeft: 6 }}>{mover.delta}</span>}
                    {mover.evStr && <span style={{ color: mover.evNeg ? "var(--red)" : "var(--green)", marginLeft: 6, fontWeight: 600 }}>{mover.evStr}</span>}
                  </div>
                  <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.4, fontFamily: "var(--font-sans)" }}>{mover.reason}</div>
                </div>
              ))}
            </div>
          </div>
          <div style={{ marginTop: 24 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-muted)", marginBottom: 8 }}>
              <RefreshCw size={12} /> Live tracking: <strong style={{ color: "var(--green)" }}>{system_pulse.live_mtd} MTD</strong> vs SPY {system_pulse.spy_mtd}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
              <BarChart2 size={12} /> Avg coverage: {system_pulse.avg_coverage}
            </div>
          </div>
        </div>
      </div>

      {/* ── IDEAS TESTING (Reasons to act/wait & Paper trade loss) ── */}
      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 24, marginTop: 32 }}>
        
        {/* Opposing One-Liners */}
        <div style={{ background: "var(--bg)", padding: 20, borderRadius: 8, border: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.18em", color: "var(--text-muted)", textTransform: "uppercase", marginBottom: 4 }}>System Debate</div>
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
        </div>

        {/* What the model got wrong */}
        <div style={{ background: "var(--bg)", padding: 20, borderRadius: 8, border: "1px solid var(--border)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.18em", color: "var(--text-muted)", textTransform: "uppercase" }}>System Miss</span>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--red)", background: "var(--red-light)", padding: "2px 6px", borderRadius: 4 }}>PAPER LOSS</span>
          </div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 700, color: "var(--text)", marginBottom: 4 }}>
            {miss.symbol} <span style={{ color: "var(--red)", marginLeft: 8 }}>{miss.loss_pct > 0 ? "+" : ""}{miss.loss_pct}%</span>
          </div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.5, fontFamily: "var(--font-sans)" }}>
            {miss.reason}
          </div>
        </div>

      </div>

    </div>
  );
}
