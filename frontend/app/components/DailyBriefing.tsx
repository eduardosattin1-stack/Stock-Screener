"use client";
import React, { useState, useEffect, useCallback } from 'react';
import { useRouter } from "next/navigation";
import { Activity, RefreshCw, BarChart2, Target, Radar, TrendingUp, TrendingDown, Award, Landmark } from 'lucide-react';

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
  const router = useRouter();
  const [briefing, setBriefing] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);

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

  const { headline, generated_at, regime_pulse, model_focus, radar_watch, basket_pulse, system_pulse, thermometer, debate, congress, target_watch } = briefing;

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

  const SOURCE: Record<string, { label: string; color: string; bg: string }> = {
    apex: { label: "APEX", color: "var(--green)", bg: "var(--green-light)" },
    value: { label: "VALUE", color: "var(--blue)", bg: "var(--blue-light)" },
  };
  const sourceChip = (source: string) => {
    const s = SOURCE[source] || { label: source.toUpperCase(), color: "var(--text-light)", bg: "var(--bg-elevated)" };
    return <span style={{ fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.08em", color: s.color, background: s.bg, padding: "1px 5px", borderRadius: 3, flexShrink: 0 }}>{s.label}</span>;
  };

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
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 14, fontWeight: 700, color: regime_pulse.regime === "RISK_ON" ? "var(--green)" : regime_pulse.regime === "RISK_OFF" ? "var(--red)" : "var(--amber)" }}>
              {regime_pulse.regime} <span style={{ color: "var(--text-light)", fontWeight: 400 }}>{regime_pulse.score}</span>
            </span>
            {/* Growth x inflation quadrant (JPM 2x2, weekly classifier snapshot) — the risk-axis
                label above can't tell stagflation from a disinflationary slowdown; this can. */}
            {regime_pulse.quadrant && (() => {
              const q = regime_pulse.quadrant;
              const qc = q === "GOLDILOCKS" ? "var(--green)" : q === "REFLATION" ? "var(--amber)" : q === "STAGFLATION" ? "#f97316" : "var(--red)";
              const tip = `Growth × inflation quadrant (${regime_pulse.quadrant_detail || "weekly classifier"}). GOLDILOCKS = growth up / inflation cooling · REFLATION = growth up / inflation hot · STAGFLATION = growth down / inflation hot · RISK_OFF = disinflationary slowdown.${regime_pulse.regime_read?.agent_view ? ` Agent regime read: ${regime_pulse.regime_read.agent_view}${regime_pulse.regime_read.stance_note ? " — " + regime_pulse.regime_read.stance_note : ""}` : ""}`;
              return (
                <span title={tip} style={{ fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 700, padding: "2px 7px", borderRadius: 4, color: qc, background: "color-mix(in srgb, currentColor 12%, transparent)", border: `1px solid color-mix(in srgb, ${qc} 40%, transparent)`, cursor: "help", letterSpacing: "0.06em" }}>
                  {q}{regime_pulse.regime_read?.agent_view === "CONTRADICT" ? " · agent disputes" : ""}
                </span>
              );
            })()}
            {/* Dalio debt-cycle chip (third axis, weekly state machine) — answers what the
                quadrant can't: are positive real rates chosen by a hot economy, or imposed
                by the bond market? DISCIPLINE = duration punished / real assets not yet. */}
            {regime_pulse.cycle?.phase && (() => {
              const c = regime_pulse.cycle;
              const pc = c.phase === "EXPANSION" ? "var(--green)" : c.phase === "DISCIPLINE" ? "var(--amber)" : c.phase === "FORCING" ? "var(--red)" : "#a855f7";
              const tip = `Debt-cycle phase (${c.confidence || "?"} confidence): ${c.phase_detail || ""}${c.phase_basis ? ` Basis: ${c.phase_basis}.` : ""}${c.transition_blocked ? ` State machine blocked a jump to ${c.transition_implied} (hysteresis).` : ""}${c.reserve_asset_note ? ` Reserve check: ${c.reserve_asset_note}` : ""}${c.phase_view === "CONTRADICT" ? " Agent regime read DISPUTES the phase dials." : ""}`;
              return (
                <span title={tip} style={{ fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 700, padding: "2px 7px", borderRadius: 4, color: pc, background: "color-mix(in srgb, currentColor 12%, transparent)", border: `1px solid color-mix(in srgb, ${pc} 40%, transparent)`, cursor: "help", letterSpacing: "0.06em" }}>
                  CYCLE · {c.phase}{typeof c.weeks_in_phase === "number" ? ` (${c.weeks_in_phase}w)` : ""}{c.phase_view === "CONTRADICT" ? " · agent disputes" : ""}
                </span>
              );
            })()}
          </div>
          {regime_pulse.quadrant_detail && (
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--text-light)", marginTop: -4, marginBottom: 8 }}>
              {regime_pulse.quadrant_detail}
            </div>
          )}
          {/* Cycle read + dated falsifiers — what would break the phase call, with check-by
              dates (at most 3, nearest first). The falsifiers are the ledger entries the
              next weekly run gets scored against. */}
          {regime_pulse.cycle?.phase && (
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--text-light)", marginTop: -2, marginBottom: 8 }}>
              {/* Plain-language phase line, same register as quadrant_detail above. Pure
                  display labeling off the published debt_cycle block — the implication
                  clause is a fixed gloss per phase, not a computed signal. Fails soft:
                  an unmapped or absent phase simply drops the clause / the whole line. */}
              {(() => {
                const PHASE_MEANS: Record<string, string> = {
                  EXPANSION: "credit is cheap and flowing, so borrowing to grow is still rewarded and profit-later promises still get funded",
                  DISCIPLINE: "lenders are demanding real compensation, so businesses producing cash now are favoured over promises of profit later",
                  FORCING: "the debt burden is being forced onto someone, so balance-sheet strength matters more than growth",
                  MONETIZATION: "the debt is being inflated away, so real assets and pricing power beat fixed cash streams",
                };
                const p = String(regime_pulse.cycle.phase);
                const w = regime_pulse.cycle.weeks_in_phase;
                const means = PHASE_MEANS[p];
                const head = `${p}${typeof w === "number" ? `, week ${w}` : ""}`;
                return <div style={{ marginBottom: 3 }}>{means ? `${head} — ${means}.` : `${head}.`}</div>;
              })()}
              {regime_pulse.cycle.phase_detail}
              {(regime_pulse.cycle.falsifiers || []).length > 0 && (
                <div style={{ marginTop: 4, paddingTop: 4, borderTop: "1px dotted var(--border)" }}>
                  {regime_pulse.cycle.falsifiers.map((f: any, i: number) => (
                    <div key={i} style={{ opacity: 0.85 }}>
                      ⚠ breaks if: {f.condition}{f.check_by ? ` (by ${f.check_by})` : ""}{f.implies ? ` → ${f.implies}` : ""}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
          {/* The Director's own phase narrative (spec.phase_read), relayed verbatim by the
              briefing route. Sits between the dials one-liners and the sentiment summary.
              Absent phase / absent block = nothing rendered, no placeholder. */}
          {regime_pulse.cycle?.phase_read && (
            <div style={{ fontSize: 11, color: "var(--text-secondary)", lineHeight: 1.55, fontFamily: "var(--font-sans)", marginBottom: 10, paddingTop: 8, borderTop: "1px dotted var(--border)" }}>
              {regime_pulse.cycle.phase_read}
            </div>
          )}
          <div style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.5, fontFamily: "var(--font-sans)", marginBottom: 12 }}>
            {regime_pulse.summary}
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-mono)", borderTop: "1px dashed var(--border)", paddingTop: 12 }}>
            <strong style={{ color: "var(--text)", fontWeight: 600 }}>Action:</strong> {regime_pulse.action}
          </div>
          <RegimePulseDetail macro={macro} />
        </div>

        {/* Card 2: On Your Radar — what's live in Apex / Value Lens */}
        <div style={{ background: "var(--bg)", padding: 24, borderTop: "1px solid var(--border)", borderBottom: "1px solid var(--border)", display: "flex", flexDirection: "column" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Radar size={14} color="var(--green)" />
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.18em", color: "var(--text-muted)", textTransform: "uppercase" }}>On Your Radar</span>
            </div>
            {radar_watch?.total > 0 && (
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--text-light)" }}>{radar_watch.total} across the system</span>
            )}
          </div>

          {radar_watch?.items?.length > 0 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 9 }}>
              {radar_watch.items.map((it: any, i: number) => (
                <div key={`${it.symbol}-${i}`} onClick={() => router.push(`/stock/${encodeURIComponent(it.symbol)}`)} style={{ cursor: "pointer" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700, color: "var(--text)" }}>{it.symbol}</span>
                    {sourceChip(it.source)}
                  </div>
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--text-muted)", marginTop: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{it.text}</div>
                </div>
              ))}
              {radar_watch.total > radar_watch.items.length && (
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--text-light)" }}>+{radar_watch.total - radar_watch.items.length} more across the system</div>
              )}
            </div>
          ) : (
            <div style={{ fontSize: 12, color: "var(--text-muted)", fontFamily: "var(--font-sans)", lineHeight: 1.5 }}>
              Nothing dated right now — no near-term catalysts in Apex, no thesis-break levels flagged in Value Lens.
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
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--text-muted)", marginTop: 1 }}>{p.probLabel} {Math.round(p.prob * 100)}%{p.peak > 0.5 ? ` · peaked +${p.peak}%` : ""}{p.enteredDaysAgo != null ? ` · entered ${p.enteredDaysAgo === 0 ? "today" : `${p.enteredDaysAgo}d ago`}` : ""}</div>
                </div>
              ))}
              {model_focus.picks_total > model_focus.picks.length && (
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--text-light)" }}>+{model_focus.picks_total - model_focus.picks.length} more this week</div>
              )}
            </div>
          ) : (
            <div style={{ fontSize: 12, color: "var(--text-muted)", fontFamily: "var(--font-sans)", lineHeight: 1.5 }}>
              No new D9/D10 signals entered this week.
            </div>
          )}

          {model_focus?.hot_sectors?.length > 0 && (
            <div style={{ borderTop: "1px dashed var(--border)", paddingTop: 12, marginTop: 12 }}>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, letterSpacing: "0.16em", color: "var(--text-light)", textTransform: "uppercase", marginBottom: 6 }}>
                Hot sectors{model_focus.hot_sectors[0].is_week ? " (1wk)" : ""}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                {model_focus.hot_sectors.map((s: any) => (
                  <div key={s.name} style={{ display: "flex", justifyContent: "space-between", fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-muted)" }}>
                    <b style={{ color: "var(--text)", fontWeight: 600 }}>{s.name}</b>
                    <span style={{ color: s.neg ? "var(--red)" : "var(--green)" }}>{s.neg ? "" : "+"}{s.week}%</span>
                  </div>
                ))}
              </div>
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
          {/* Bounded-risk setups — relayed from the publish-time risk_badge stamp (numeric-gate-
              checked bear floor + asymmetry, or a dated hard catalyst). Hidden until a weekly
              publish stamps the field. ·off-board = debated and eligible but not seated. */}
          {debate.bounded?.length > 0 && (
            <div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--text-light)", marginBottom: 6 }}>
                Bounded-risk setups — the debate's own bear case, gate-checked · tap to read why
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
                {debate.bounded.map((b: any) => {
                  const hard = b.kind === "dated_catalyst_floor";
                  const c = hard ? "#2563eb" : "var(--green)";
                  const tip = `${hard ? "Dated catalyst · checked floor" : "Bounded downside · modeled"}: bear −${Math.abs(b.floor ?? 0).toFixed(0)}% vs base +${(b.upside ?? 0).toFixed(0)}% = ${b.rr}:1, recomputed by the numeric gate at a verified price. The debate's MODEL of the adverse case — not a guarantee.${b.seated ? "" : " Debated and eligible, but not seated in the apex."}`;
                  return (
                    <button key={b.symbol} title={tip} onClick={() => router.push(`/stock/${encodeURIComponent(b.symbol)}?tab=debate`)}
                      style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700, color: c, background: hard ? "rgba(37,99,235,0.12)" : "var(--green-light)", border: `1px solid ${hard ? "rgba(37,99,235,0.35)" : "var(--green-border)"}`, borderRadius: 4, padding: "3px 8px", cursor: "pointer" }}>
                      {hard ? "◆" : "▣"} {b.symbol}{b.rr != null ? ` ${b.rr}:1` : ""}{b.seated ? "" : " · off-board"}
                    </button>
                  );
                })}
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
          {/* Live-tracking footer (system pulse) — each book's own MTD (trailing 30d) and
              since-inception return, each paired against SPY over that SAME window (not a
              mismatched MTD-vs-YTD comparison, and no fabricated YTD for books that only
              launched in June). */}
          <div style={{ display: "flex", flexDirection: "column", gap: 6, borderTop: "1px dashed var(--border)", paddingTop: 12, marginTop: 4 }}>
            {(system_pulse.live_tracking?.books || []).map((b: any) => (
              <div key={b.key} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-muted)", flexWrap: "wrap" }}>
                <RefreshCw size={12} style={{ flexShrink: 0 }} />
                <span style={{ color: "var(--text)", fontWeight: 700 }}>{b.label}:</span>
                {b.mtd_pct != null && (
                  <span>
                    MTD <strong style={{ color: b.mtd_pct >= 0 ? "var(--green)" : "var(--red)" }}>{b.mtd_pct >= 0 ? "+" : ""}{b.mtd_pct}%</strong>
                    {system_pulse.live_tracking.spy_mtd_pct != null && <> (SPY {system_pulse.live_tracking.spy_mtd_pct >= 0 ? "+" : ""}{system_pulse.live_tracking.spy_mtd_pct}%)</>}
                  </span>
                )}
                <span>·</span>
                <span>
                  Since {b.since_label} <strong style={{ color: b.since_inception_pct >= 0 ? "var(--green)" : "var(--red)" }}>{b.since_inception_pct >= 0 ? "+" : ""}{b.since_inception_pct}%</strong>
                  {b.spy_since_inception_pct != null && <> (SPY {b.spy_since_inception_pct >= 0 ? "+" : ""}{b.spy_since_inception_pct}%)</>}
                </span>
              </div>
            ))}
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
              {basket_pulse.mtd_winner && (
                <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8 }}>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-secondary)" }}><Activity size={11} style={{ verticalAlign: -1, marginRight: 4, color: "var(--green)" }} />MTD: <b style={{ color: "var(--text)" }}>{basket_pulse.mtd_winner.label}</b></span>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>
                    <span style={{ fontWeight: 700, color: basket_pulse.mtd_winner.mtd >= 0 ? "var(--green)" : "var(--red)" }}>{basket_pulse.mtd_winner.mtd >= 0 ? "+" : ""}{basket_pulse.mtd_winner.mtd}%</span>
                    {basket_pulse.mtd_winner.week != null && (
                      <span style={{ color: "var(--text-light)", fontSize: 10 }}> · wk {basket_pulse.mtd_winner.week >= 0 ? "+" : ""}{basket_pulse.mtd_winner.week}%</span>
                    )}
                  </span>
                </div>
              )}
              {basket_pulse.top_name && (
                <div onClick={() => router.push(`/stock/${encodeURIComponent(basket_pulse.top_name.sym)}`)} style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 8, cursor: "pointer" }}>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-secondary)" }}><Award size={11} style={{ verticalAlign: -1, marginRight: 4, color: "var(--amber)" }} />Top name: <b style={{ color: "var(--text)" }}>{basket_pulse.top_name.sym}</b></span>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700, color: basket_pulse.top_name.ret >= 0 ? "var(--green)" : "var(--red)" }}>{basket_pulse.top_name.ret >= 0 ? "+" : ""}{basket_pulse.top_name.ret}%</span>
                </div>
              )}
              <div style={{ borderTop: "1px dashed var(--border)", paddingTop: 10, marginTop: 2, fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-muted)" }}>
                {basket_pulse.green}/{basket_pulse.total} baskets green{basket_pulse.since_common ? ` · since ${basket_pulse.since_common}` : ""}{basket_pulse.top_name?.since ? ` · top name since ${basket_pulse.top_name.since}` : ""}
              </div>
            </div>
          ) : (
            <div style={{ fontSize: 12, color: "var(--text-muted)", fontFamily: "var(--font-sans)", lineHeight: 1.5 }}>Basket tracking not available yet.</div>
          )}
        </div>

      </div>

      {/* ── CONGRESS WATCH — big STOCK Act filings (Senate + House, last 30d) ──
          Server-aggregated in /api/briefing from the FMP senate-latest/house-latest
          feeds. Renders only when the pull produced data, so an FMP outage or an
          endpoint change degrades to "no card", never to a broken briefing. */}
      {congress && congress.top?.length > 0 && (
        <div style={{ marginTop: 24, background: "var(--bg)", padding: 20, borderRadius: 8, border: "1px solid var(--border)" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Landmark size={14} color="var(--amber)" />
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.18em", color: "var(--text-muted)", textTransform: "uppercase" }}>Congress Watch</span>
            </div>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--text-light)" }}>
              {congress.big_count} big of {congress.total} filings · since {congress.coverage_from}
            </span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "10px 28px" }}>
            {congress.top.map((t: any, i: number) => (
              <div key={`${t.symbol}-${t.who}-${i}`} onClick={() => router.push(`/stock/${encodeURIComponent(t.symbol)}`)} style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", minWidth: 0 }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700, color: "var(--text)", flexShrink: 0 }}>{t.symbol}</span>
                <span title={t.chamber === "S" ? "Senate" : "House"} style={{ fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.08em", color: "var(--text-muted)", background: "var(--bg-elevated)", padding: "1px 5px", borderRadius: 3, flexShrink: 0 }}>{t.chamber === "S" ? "SEN" : "HSE"}</span>
                {t.apex && <span style={{ fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.08em", color: "var(--lavender)", background: "var(--purple-light)", padding: "1px 5px", borderRadius: 3, flexShrink: 0 }}>APEX</span>}
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.who}</span>
                <span style={{ marginLeft: "auto", fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700, color: t.side === "BUY" ? "var(--green)" : "var(--red)", flexShrink: 0 }}>
                  {t.side} {t.range}
                </span>
                <span title={`traded ${t.tx || "—"} · filed ${t.filed}`} style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--text-light)", flexShrink: 0, cursor: "help" }}>
                  filed {t.filed?.slice(5)}
                </span>
              </div>
            ))}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap", borderTop: "1px dashed var(--border)", paddingTop: 12, marginTop: 14 }}>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-muted)" }}>
              ≥$100K skew: <b style={{ color: "var(--green)" }}>{congress.big_buys} buys</b> · <b style={{ color: "var(--red)" }}>{congress.big_sells} sells</b>
            </span>
            {congress.hot?.length > 0 && (
              <span style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap", fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-muted)" }}>
                Most filed:
                {congress.hot.map((h: any) => (
                  <button key={h.symbol} onClick={() => router.push(`/stock/${encodeURIComponent(h.symbol)}`)}
                    title={`${h.buys} buys · ${h.sells} sells in the last 30d${h.apex ? " · in the apex basket" : ""}`}
                    style={{ fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 700, color: h.buys >= h.sells ? "var(--green)" : "var(--red)", background: h.buys >= h.sells ? "var(--green-light)" : "rgba(239,68,68,0.1)", border: "none", borderRadius: 4, padding: "2px 7px", cursor: "pointer" }}>
                    {h.symbol} {h.buys}B/{h.sells}S
                  </button>
                ))}
              </span>
            )}
            <span style={{ marginLeft: "auto", fontFamily: "var(--font-mono)", fontSize: 8, color: "var(--text-light)", fontStyle: "italic" }}>
              STOCK Act disclosures lag trades by up to 45d — context, not signal
            </span>
          </div>
        </div>
      )}

      {/* ── TARGET WATCH — most substantial analyst price-target changes (30d) ──
          Server-aggregated in /api/briefing from FMP price-target-latest-news;
          deltas are real prior→new moves parsed from the analyst note titles.
          Hidden when the pull fails or parses nothing. */}
      {target_watch && (target_watch.raises?.length > 0 || target_watch.cuts?.length > 0) && (
        <div style={{ marginTop: 24, background: "var(--bg)", padding: 20, borderRadius: 8, border: "1px solid var(--border)" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Target size={14} color="var(--lavender)" />
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.18em", color: "var(--text-muted)", textTransform: "uppercase" }}>Target Watch</span>
            </div>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--text-light)" }}>
              {target_watch.raises_count} raises · {target_watch.cuts_count} cuts · since {target_watch.coverage_from}
            </span>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0 28px" }}>
            {([["BIGGEST RAISES", target_watch.raises, "var(--green)"], ["BIGGEST CUTS", target_watch.cuts, "var(--red)"]] as [string, any[], string][]).map(([label, rows, color]) => (
              <div key={label}>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, letterSpacing: "0.16em", color, marginBottom: 8 }}>{label}</div>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {rows.map((t: any) => (
                    <div key={`${t.symbol}-${t.date}`} onClick={() => router.push(`/stock/${encodeURIComponent(t.symbol)}`)} style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", minWidth: 0 }}>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700, color: "var(--text)", flexShrink: 0 }}>{t.symbol}</span>
                      {t.apex && <span style={{ fontFamily: "var(--font-mono)", fontSize: 8, letterSpacing: "0.08em", color: "var(--lavender)", background: "var(--purple-light)", padding: "1px 5px", borderRadius: 3, flexShrink: 0 }}>APEX</span>}
                      {t.n > 1 && <span title={`${t.n} same-direction target changes on ${t.symbol} in the window — showing the largest`} style={{ fontFamily: "var(--font-mono)", fontSize: 8, color: "var(--text-muted)", background: "var(--bg-elevated)", padding: "1px 5px", borderRadius: 3, flexShrink: 0, cursor: "help" }}>×{t.n}</span>}
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.firm}</span>
                      <span title={`$${t.prior} → $${t.target}${t.implied != null ? ` · implied ${t.implied >= 0 ? "+" : ""}${t.implied}% vs price at publication` : ""} · ${t.date}`} style={{ marginLeft: "auto", fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700, color, flexShrink: 0, cursor: "help" }}>
                        ${t.prior}→${t.target} ({t.delta >= 0 ? "+" : ""}{t.delta}%)
                      </span>
                    </div>
                  ))}
                  {!rows.length && <div style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-sans)" }}>None in the window.</div>}
                </div>
              </div>
            ))}
          </div>
          <div style={{ borderTop: "1px dashed var(--border)", paddingTop: 10, marginTop: 14, fontFamily: "var(--font-mono)", fontSize: 8, color: "var(--text-light)", fontStyle: "italic" }}>
            {target_watch.total_changes} parseable target changes in the window · deltas are each analyst&apos;s own prior → new target
          </div>
        </div>
      )}

    </div>
  );
}
