"use client";
// COMMODITIES & MINING — the Mining book plus its macro layer.
//
// Replaces the Social Arb board (retired 2026-07-27; the Cloud Run social engine is untouched).
// Two GCS reads, no client-side computation of anything that scores:
//   scans/commodity_macro.json   <- `mining-macro --gcs`  (Dalio phase/quadrant + tilt tables,
//                                   the Tavi dial set, and the per-chain winner scoreboard)
//   scans/speculair_mining.json  <- `mining-publish --gcs` (the Lane A basket, NAV, stress, memo)
// Both fall back to a bundled /public copy, matching the sibling Speculair cards.
//
// THE PAGE'S ARGUMENT, top to bottom: what regime are we in (Dalio) -> what does the tape say
// (Tavi dials) -> which commodity setups win on that evidence (scoreboard) -> and WHO are the best
// players inside the winning ones (the basket, grouped under its chain). That ordering is the whole
// point; do not reshuffle the blocks.
//
// DISPLAY-ONLY DISCIPLINE (mirrors the backend seam): the tilt tables are rendered from data the
// backend generated (_commodity_tilt.py) — there is deliberately NO tilt table hardcoded here, so
// the page and the Mining Director can never drift. Gold dials are shown because they are worth
// looking at; nothing computed from them scores anything, here or upstream.
import { useEffect, useState } from "react";
import { Pickaxe } from "lucide-react";

const GCS = "/api/gcs/scans";

const T = {
  bg: "var(--bg)", card: "var(--bg-surface)", border: "var(--border)",
  text: "var(--text)", light: "var(--text-light)", muted: "var(--text-muted)",
  green: "var(--green)", red: "var(--red)", amber: "var(--amber)", blue: "var(--blue)",
  mono: "var(--font-mono)", sans: "var(--font-sans)",
};

const TILT_COLOR: Record<string, string> = {
  tailwind: T.green, headwind: T.red, mixed: "#eab308", neutral: T.muted,
};
const num = (v: any, d = 2) => (typeof v === "number" && isFinite(v) ? v.toFixed(d) : "—");
const pct = (v: any, d = 1) => (typeof v === "number" && isFinite(v) ? `${v >= 0 ? "+" : ""}${v.toFixed(d)}%` : "—");
const cap = (s: any) => String(s || "").replace(/_/g, " ");

/** Fetch GCS-first with the bundled-file fallback the sibling cards use. */
function useGcs<T4 = any>(name: string): [T4 | null, boolean] {
  const [d, setD] = useState<T4 | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let dead = false;
    fetch(`${GCS}/${name}?t=${Date.now()}`)
      .then((r) => { if (r.ok) return r.json(); throw new Error("gcs"); })
      .catch(() => fetch(`/${name}`).then((r) => (r.ok ? r.json() : null)).catch(() => null))
      .then((j) => { if (!dead) { setD(j || null); setLoading(false); } });
    return () => { dead = true; };
  }, [name]);
  return [d, loading];
}

/** Hand-rolled sparkline over [[date, close], ...] — no chart lib, matching the rest of the app. */
function Spark({ series, w = 104, h = 26 }: { series?: any[]; w?: number; h?: number }) {
  const pts = (series || []).map((r: any) => (Array.isArray(r) ? r[1] : r)).filter((v: any) => typeof v === "number");
  if (pts.length < 3) return <div style={{ width: w, height: h }} />;
  const mn = Math.min(...pts), mx = Math.max(...pts), rng = mx - mn || 1;
  const d = pts.map((v: number, i: number) => `${(i / (pts.length - 1)) * w},${h - ((v - mn) / rng) * h}`).join(" ");
  const up = pts[pts.length - 1] >= pts[0];
  return (
    <svg width={w} height={h} style={{ display: "block" }}>
      <polyline points={d} fill="none" stroke={up ? T.green : T.red} strokeWidth={1.4} />
    </svg>
  );
}

function SourceChip({ source }: { source?: string }) {
  if (!source || source === "live") return null;
  const missing = source === "missing";
  return (
    <span title={missing ? "no data for this input on the last run" : "riding cached data"}
          style={{ fontSize: 8, padding: "1px 4px", borderRadius: 3, fontFamily: T.mono, fontWeight: 700,
                   background: missing ? "rgba(239,68,68,0.14)" : "var(--amber-light)",
                   color: missing ? T.red : T.amber }}>
      {missing ? "no data" : "cached"}
    </span>
  );
}

export default function CommoditiesPage() {
  const [macro] = useGcs<any>("commodity_macro.json");
  const [book] = useGcs<any>("speculair_mining.json");
  const [openChain, setOpenChain] = useState<string | null>(null);
  const [openWhy, setOpenWhy] = useState<string | null>(null);

  const dials = macro?.dials || {};
  const tilt = macro?.tilt || {};
  const resolved: Record<string, string> = tilt.resolved || {};
  const dc = macro?.debt_cycle || {};
  const board: any[] = macro?.scoreboard || [];
  const picks: any[] = book?.apex_basket || [];
  const track = book?.mining_tracking_weighted?.history?.length >= 4
    ? book.mining_tracking_weighted : book?.mining_tracking;
  const weighted = book?.mining_tracking_weighted?.history?.length >= 4;

  const picksByChain: Record<string, any[]> = {};
  picks.forEach((p) => {
    const c = p.chain || (Array.isArray(p.chains) ? p.chains[0] : "") || "unassigned";
    (picksByChain[c] = picksByChain[c] || []).push(p);
  });

  const phase = macro?.debt_cycle_phase || "UNKNOWN";
  const quadrant = macro?.quadrant || "UNKNOWN";
  const degraded = !!macro?.degraded;
  const staleDays = (() => {
    if (!macro?.generated_at) return null;
    const d = (Date.now() - new Date(macro.generated_at).getTime()) / 86400000;
    return isFinite(d) ? Math.floor(d) : null;
  })();

  return (
    <div style={{ padding: "20px 24px 60px", maxWidth: 1500, margin: "0 auto", background: T.bg }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
        <Pickaxe size={18} color={T.amber} />
        <h1 style={{ margin: 0, fontSize: 21, fontWeight: 800, color: T.text, fontFamily: T.sans }}>
          Commodities &amp; Mining
        </h1>
      </div>
      <div style={{ fontSize: 11, color: T.muted, fontFamily: T.mono, marginBottom: 18, lineHeight: 1.6, maxWidth: 1000 }}>
        The macro read first, then the players. Where we are in the debt cycle and the growth/inflation
        quadrant sets the commodity playbook; the dials say what the tape is actually doing; the
        scoreboard ranks which chains have the better setup on that evidence; and the basket below
        holds the names the debate pipeline picked inside them. Paper book, own NAV, never blended.
      </div>

      {!macro && (
        <div style={{ padding: "14px 16px", borderRadius: 8, border: `1px dashed ${T.border}`, background: T.card,
                      fontSize: 11.5, color: T.muted, fontFamily: T.mono, marginBottom: 18 }}>
          Macro layer not published yet. It appears after <code>mining-macro --gcs</code> runs on the
          operator box (weekly, before the Mining debates).
        </div>
      )}

      {(degraded || (staleDays != null && staleDays > 10)) && (
        <div style={{ padding: "10px 14px", borderRadius: 8, marginBottom: 18, fontSize: 10.5, lineHeight: 1.55,
                      fontFamily: T.mono, color: T.amber, background: "var(--amber-light)", border: `1px solid ${T.amber}` }}>
          {macro?.stale_banner || `Macro read is ${staleDays} days old — refresh mining-macro.`}
          {dc.seeded && " · Phase is a SEEDED prior, not yet earned by the state machine."}
          {dc.confidence === "low" && " · Phase confidence LOW (few live gauges)."}
        </div>
      )}

      {/* ══ 1. MACRO HEADER — the Dalio read + the tilt tables (rendered from backend data) ══ */}
      {macro && (
        <section style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, padding: "18px 20px", marginBottom: 16 }}>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", marginBottom: 12 }}>
            {[["Debt-cycle phase", phase, T.amber], ["Growth × inflation", quadrant, T.blue],
              ["Risk regime", macro.risk_regime || "—", T.green]].map(([label, val, col]) => (
              <div key={String(label)} style={{ padding: "8px 12px", borderRadius: 8, background: T.bg, border: `1px solid ${T.border}` }}>
                <div style={{ fontSize: 8.5, color: T.muted, fontFamily: T.mono, textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</div>
                <div style={{ fontSize: 14, fontWeight: 800, color: col as string, fontFamily: T.mono }}>{val}</div>
              </div>
            ))}
            {typeof dc.weeks_in_phase === "number" && (
              <div style={{ fontSize: 9.5, color: T.muted, fontFamily: T.mono, lineHeight: 1.5 }}>
                {dc.weeks_in_phase}w in phase{dc.prior_phase ? ` · from ${dc.prior_phase}` : ""}
                {dc.transition_blocked && dc.transition_implied
                  ? <div style={{ color: T.amber }}>hysteresis holding a step toward {dc.transition_implied}</div> : null}
              </div>
            )}
          </div>
          {(macro.quadrant_basis || dc.phase_basis) && (
            <div style={{ fontSize: 9.5, color: T.light, fontFamily: T.mono, marginBottom: 12, lineHeight: 1.5 }}>
              {dc.phase_basis ? <>phase: {dc.phase_basis}</> : null}
              {dc.phase_basis && macro.quadrant_basis ? " · " : ""}
              {macro.quadrant_basis ? <>quadrant: {macro.quadrant_basis}</> : null}
            </div>
          )}

          {/* the six debt-cycle gauges — inverted convention, stated */}
          {Object.keys(dc.sub_scores || {}).length > 0 && (
            <div style={{ marginBottom: 14 }}>
              <div style={{ fontSize: 8.5, color: T.muted, fontFamily: T.mono, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>
                Cycle gauges · higher = later in the cycle / more stress
              </div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {Object.entries(dc.sub_scores).map(([k, v]: [string, any]) => {
                  const src = (dc.sub_sources || {})[k];
                  const val = typeof v === "number" ? v : null;
                  return (
                    <div key={k} title={src === "missing" ? "gauge missing on the last run" : undefined}
                         style={{ padding: "5px 8px", borderRadius: 6, background: T.bg, border: `1px solid ${T.border}`, minWidth: 96, opacity: src === "missing" ? 0.5 : 1 }}>
                      <div style={{ fontSize: 8, color: T.muted, fontFamily: T.mono }}>{cap(k)}</div>
                      <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
                        <span style={{ fontSize: 12, fontWeight: 700, fontFamily: T.mono, color: val == null ? T.muted : val >= 0.66 ? T.red : val >= 0.33 ? "#eab308" : T.green }}>
                          {val == null ? "—" : val.toFixed(2)}
                        </span>
                        <SourceChip source={src} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* gold falsification chip — a check, never a scored input */}
          {dc.reserve_asset_check && Object.keys(dc.reserve_asset_check).length > 0 && (() => {
            const rc = dc.reserve_asset_check;
            const ok = rc.consistent_with_phase;
            return (
              <div style={{ fontSize: 9.5, fontFamily: T.mono, marginBottom: 14, padding: "7px 11px", borderRadius: 6,
                            background: T.bg, border: `1px solid ${ok === false ? T.amber : T.border}`,
                            color: ok === false ? T.amber : T.muted, lineHeight: 1.5 }}>
                <strong>{ok === true ? "✓ gold check consistent" : ok === false ? "⚠ gold check INCONSISTENT" : "— gold check skipped"}</strong>
                {rc.note ? ` — ${rc.note}` : ""}
                <div style={{ color: T.light, marginTop: 2 }}>
                  Falsification only: gold never scores the cycle read, it only tests it. An inconsistency
                  raises a falsifier — the phase call may be early or late — it does not refute it.
                </div>
              </div>
            );
          })()}

          {/* the tilt matrix — BOTH axes, both rows highlighted, rendered from backend tables */}
          {tilt.phase_table && (
            <div style={{ overflowX: "auto" }}>
              <div style={{ fontSize: 8.5, color: T.muted, fontFamily: T.mono, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 6 }}>
                Dalio commodity playbook · the live rows are highlighted on both axes
              </div>
              <table style={{ borderCollapse: "collapse", fontSize: 10, fontFamily: T.mono, width: "100%", minWidth: 720 }}>
                <tbody>
                  {[["PHASE", tilt.phase_table, phase], ["QUADRANT", tilt.quadrant_table, quadrant]].map(([axis, table, live]: any) => (
                    <>
                      <tr key={axis}><td colSpan={3} style={{ padding: "8px 6px 3px", color: T.muted, fontSize: 8.5, letterSpacing: "0.05em" }}>{axis}</td></tr>
                      {Object.entries(table || {}).map(([k, row]: [string, any]) => {
                        const isLive = k === live;
                        return (
                          <tr key={axis + k} style={{ background: isLive ? "rgba(217,119,6,0.09)" : "transparent" }}>
                            <td style={{ padding: "4px 8px", whiteSpace: "nowrap", fontWeight: isLive ? 800 : 500,
                                         color: isLive ? T.amber : T.light, borderLeft: `2px solid ${isLive ? T.amber : "transparent"}` }}>{k}</td>
                            <td style={{ padding: "4px 8px", color: T.green }}>{(row.favored || []).map(cap).join(", ") || "—"}</td>
                            <td style={{ padding: "4px 8px", color: T.red }}>{(row.disfavored || []).map(cap).join(", ") || "—"}</td>
                          </tr>
                        );
                      })}
                    </>
                  ))}
                </tbody>
              </table>
              {(tilt.phase_table?.[phase]?.gold_role || tilt.phase_table?.[phase]?.dalio_note) && (
                <div style={{ fontSize: 9.5, color: T.light, fontFamily: T.mono, marginTop: 8, lineHeight: 1.55, maxWidth: 900 }}>
                  {tilt.phase_table[phase].dalio_note && <div>{tilt.phase_table[phase].dalio_note}</div>}
                  {tilt.phase_table[phase].gold_role && <div style={{ marginTop: 3, color: T.muted }}><strong>Gold:</strong> {tilt.phase_table[phase].gold_role}</div>}
                </div>
              )}
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 10 }}>
                {Object.entries(resolved).map(([fam, label]) => (
                  <span key={fam} style={{ fontSize: 9, padding: "3px 7px", borderRadius: 4, fontFamily: T.mono, fontWeight: 700,
                                           background: "rgba(148,163,184,0.1)", color: TILT_COLOR[label] || T.muted }}>
                    {cap(fam)} · {label}
                  </span>
                ))}
              </div>
              {tilt.display_only_note && (
                <div style={{ fontSize: 8.5, color: T.light, fontFamily: T.mono, fontStyle: "italic", marginTop: 8, lineHeight: 1.5 }}>
                  {tilt.display_only_note}
                </div>
              )}
            </div>
          )}
        </section>
      )}

      {/* ══ 2. THE DIALS ══ */}
      {macro && Object.keys(dials).length > 0 && (
        <section style={{ marginBottom: 16 }}>
          <h2 style={{ margin: "0 0 8px", fontSize: 13, fontWeight: 700, color: T.text, fontFamily: T.sans }}>Commodity dials</h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(250px, 1fr))", gap: 10 }}>
            {["commodities_vs_equities", "copper_gold", "silver_gold", "dxy", "gold_vs_real_rates", "miners_vs_metal", "curve"]
              .filter((k) => dials[k]).map((k) => {
              const d = dials[k];
              const isGold = k === "gold_vs_real_rates";
              const isMiners = k === "miners_vs_metal";
              const isCurve = k === "curve";
              return (
                <div key={k} style={{ background: T.card, border: `1px solid ${isGold ? T.amber : T.border}`, borderRadius: 10, padding: "12px 14px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6, marginBottom: 6 }}>
                    <span style={{ fontSize: 10.5, fontWeight: 700, color: T.text, fontFamily: T.mono }}>{d.label}</span>
                    <SourceChip source={d.source} />
                  </div>
                  {isCurve ? (
                    <div style={{ fontSize: 10, fontFamily: T.mono, color: T.light, lineHeight: 1.6 }}>
                      <div>2s10s <strong style={{ color: T.text }}>{d.spread_2s10s_bp ?? "—"}bp</strong> · {d.shape_2s10s}</div>
                      <div>3m10y <strong style={{ color: T.text }}>{d.spread_3m10y_bp ?? "—"}bp</strong> · {d.shape_3m10y}</div>
                      <div style={{ color: T.muted }}>{d.motion}</div>
                    </div>
                  ) : isMiners ? (
                    <div style={{ fontSize: 10, fontFamily: T.mono, color: T.light, lineHeight: 1.6 }}>
                      {[["GDX/GLD", d.gdx_gld], ["XME/copper", d.xme_copper]].map(([lbl, leg]: any) => (
                        <div key={lbl} style={{ display: "flex", justifyContent: "space-between", gap: 6 }}>
                          <span>{lbl}</span>
                          <span style={{ color: leg?.confirmation === "confirming" ? T.green : leg?.confirmation === "diverging" ? T.red : T.muted, fontWeight: 600 }}>
                            {pct(leg?.chg_3m_pct)} · {leg?.confirmation || "—"}
                          </span>
                        </div>
                      ))}
                      <div style={{ fontSize: 8.5, color: T.muted, marginTop: 2 }}>{d.window_label} window</div>
                    </div>
                  ) : isGold ? (
                    <div style={{ fontSize: 10, fontFamily: T.mono, color: T.light, lineHeight: 1.6 }}>
                      <div style={{ fontSize: 13, fontWeight: 800, color: d.classification === "debasement_divergence" ? T.amber : T.text }}>
                        {cap(d.classification)}
                      </div>
                      <div>gold YoY {pct(d.gold_yoy_pct)} · real 10y {num(d.real_10y_now_pct)}% ({pct(d.real_10y_change_pp)}pp)</div>
                      <Spark series={d.series} />
                      <div style={{ fontSize: 8, color: T.amber, marginTop: 3, fontWeight: 700 }}>DISPLAY ONLY — scores nothing</div>
                    </div>
                  ) : (
                    <>
                      <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 3 }}>
                        <span style={{ fontSize: 16, fontWeight: 800, color: T.text, fontFamily: T.mono }}>{num(d.level, 3)}</span>
                        <span style={{ fontSize: 10, fontFamily: T.mono, color: (d.chg_3m_pct || 0) >= 0 ? T.green : T.red }}>{pct(d.chg_3m_pct)} 3m</span>
                      </div>
                      <Spark series={d.series} />
                      <div style={{ fontSize: 9, color: T.muted, fontFamily: T.mono, marginTop: 3 }}>
                        {d.pctile != null ? `${d.pctile}th pctile · ${d.pctile_window || ""}` : "percentile: insufficient history"}
                        {d.trend ? ` · ${d.trend}` : d.direction ? ` · ${d.direction}` : ""}
                      </div>
                    </>
                  )}
                  <div style={{ fontSize: 8.5, color: T.light, fontFamily: T.mono, marginTop: 6, lineHeight: 1.5 }}>{d.read}</div>
                </div>
              );
            })}
          </div>

          {/* per-commodity momentum table */}
          {dials.momentum_table?.rows?.length > 0 && (
            <div style={{ marginTop: 12, background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, padding: "12px 14px", overflowX: "auto" }}>
              <div style={{ fontSize: 10.5, fontWeight: 700, color: T.text, fontFamily: T.mono, marginBottom: 8 }}>{dials.momentum_table.label}</div>
              <table style={{ borderCollapse: "collapse", width: "100%", minWidth: 560, fontSize: 10, fontFamily: T.mono }}>
                <thead>
                  <tr style={{ color: T.muted, textAlign: "right" }}>
                    <th style={{ textAlign: "left", padding: "3px 6px", fontWeight: 500 }}>Commodity</th>
                    <th style={{ padding: "3px 6px", fontWeight: 500 }}>12m</th>
                    <th style={{ padding: "3px 6px", fontWeight: 500 }}>3m</th>
                    <th style={{ padding: "3px 6px", fontWeight: 500 }}>5y pctile</th>
                    <th style={{ padding: "3px 6px", fontWeight: 500 }}>off 52w high</th>
                    <th style={{ padding: "3px 6px", fontWeight: 500 }}>trend</th>
                  </tr>
                </thead>
                <tbody>
                  {dials.momentum_table.rows.map((r: any) => (
                    <tr key={r.symbol} style={{ borderTop: `1px solid ${T.border}`, textAlign: "right" }}>
                      <td style={{ textAlign: "left", padding: "4px 6px", color: T.text }}>
                        {r.label}{r.is_proxy && <span title={r.proxy_note} style={{ fontSize: 8, color: T.amber, marginLeft: 4 }}>proxy</span>}
                      </td>
                      <td style={{ padding: "4px 6px", color: (r.mom_12m_pct || 0) >= 0 ? T.green : T.red }}>{pct(r.mom_12m_pct)}</td>
                      <td style={{ padding: "4px 6px", color: (r.mom_3m_pct || 0) >= 0 ? T.green : T.red }}>{pct(r.mom_3m_pct)}</td>
                      <td style={{ padding: "4px 6px", color: T.light }}>{r.pctile_5y != null ? r.pctile_5y : "—"}</td>
                      <td style={{ padding: "4px 6px", color: T.light }}>{pct(r.off_52wk_high_pct)}</td>
                      <td style={{ padding: "4px 6px" }}><Spark series={r.series} w={60} h={16} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}

      {/* ══ 3. WINNER SCOREBOARD ══ */}
      {board.length > 0 && (
        <section style={{ marginBottom: 16 }}>
          <h2 style={{ margin: "0 0 4px", fontSize: 13, fontWeight: 700, color: T.text, fontFamily: T.sans }}>Which commodity setup wins</h2>
          <div style={{ fontSize: 9.5, color: T.muted, fontFamily: T.mono, marginBottom: 8, lineHeight: 1.5, maxWidth: 900 }}>
            {macro?.scoreboard_authority}
          </div>
          <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 10, overflow: "hidden" }}>
            {board.map((r: any) => {
              const open = openWhy === r.chain_id;
              const seats = (picksByChain[r.chain_id] || []).length;
              return (
                <div key={r.chain_id} style={{ borderTop: `1px solid ${T.border}` }}>
                  <div onClick={() => setOpenWhy(open ? null : r.chain_id)}
                       style={{ display: "flex", alignItems: "center", gap: 12, padding: "11px 14px", cursor: "pointer", flexWrap: "wrap" }}>
                    <span style={{ fontSize: 11, fontWeight: 800, color: T.muted, fontFamily: T.mono, width: 20 }}>#{r.rank}</span>
                    <span style={{ fontSize: 12, fontWeight: 700, color: T.text, fontFamily: T.mono, minWidth: 190 }}>{r.chain_name}</span>
                    <span style={{ fontSize: 15, fontWeight: 800, fontFamily: T.mono,
                                   color: r.score >= 65 ? T.green : r.score >= 50 ? "#eab308" : T.muted }}>{num(r.score, 1)}</span>
                    <span style={{ fontSize: 8.5, color: T.muted, fontFamily: T.mono }}>/100</span>
                    {resolved[r.chain_id] && (
                      <span style={{ fontSize: 8.5, padding: "2px 6px", borderRadius: 4, fontFamily: T.mono, fontWeight: 700,
                                     background: "rgba(148,163,184,0.1)", color: TILT_COLOR[resolved[r.chain_id]] }}>
                        {resolved[r.chain_id]}
                      </span>
                    )}
                    {r.regime_state && (
                      <span style={{ fontSize: 8.5, padding: "2px 6px", borderRadius: 4, fontFamily: T.mono, fontWeight: 700,
                                     background: "rgba(148,163,184,0.1)",
                                     color: r.regime_state === "TAILWIND" ? T.green : r.regime_state === "HEADWIND" ? T.red : T.muted }}>
                        {r.regime_state}
                      </span>
                    )}
                    {r.monetary_metal && (
                      <span title="monetary metal — price momentum is excluded from this score by design (the gold momentum-loop guard)"
                            style={{ fontSize: 8, padding: "1px 5px", borderRadius: 3, background: "var(--amber-light)", color: T.amber, fontFamily: T.mono, fontWeight: 700 }}>
                        momentum excluded
                      </span>
                    )}
                    <span style={{ marginLeft: "auto", fontSize: 9, color: T.muted, fontFamily: T.mono }}>
                      {seats > 0 ? `${seats} seat${seats === 1 ? "" : "s"} held` : "no seats"} · conf {r.confidence} · {open ? "▴" : "▾"} why
                    </span>
                  </div>
                  {open && (
                    <div style={{ padding: "0 14px 12px 54px", display: "flex", gap: 8, flexWrap: "wrap" }}>
                      {["setup", "momentum", "confirmation", "tilt"].map((leg) => {
                        const L = r.legs?.[leg] || {};
                        const excluded = String(L.source || "").includes("excluded");
                        const missing = String(L.source || "").includes("missing") || String(L.source || "").includes("n/a");
                        return (
                          <div key={leg} style={{ padding: "7px 10px", borderRadius: 6, background: T.bg, border: `1px solid ${T.border}`, minWidth: 150 }}>
                            <div style={{ fontSize: 8.5, color: T.muted, fontFamily: T.mono, textTransform: "uppercase" }}>{leg}</div>
                            <div style={{ fontSize: 12, fontWeight: 700, fontFamily: T.mono, color: excluded || missing ? T.muted : T.text }}>
                              {num(L.points, 1)}<span style={{ fontSize: 9, color: T.muted }}>/{L.max}</span>
                            </div>
                            <div style={{ fontSize: 8, color: excluded ? T.amber : T.light, fontFamily: T.mono, lineHeight: 1.4 }}>
                              {cap(L.source)}
                              {leg === "setup" && L.vs_incentive_pct != null ? ` · ${pct(L.vs_incentive_pct)} vs incentive` : ""}
                              {leg === "momentum" && L.mom_pctile != null ? ` · ${L.mom_pctile}th pctile` : ""}
                              {leg === "tilt" && L.phase ? ` · ${L.phase}` : ""}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          {macro?.gold_note && (
            <div style={{ fontSize: 8.5, color: T.light, fontFamily: T.mono, fontStyle: "italic", marginTop: 8, lineHeight: 1.5, maxWidth: 950 }}>
              {macro.gold_note}
            </div>
          )}
        </section>
      )}

      {/* ══ 4. THE BASKET — best players inside the winning chains ══ */}
      <section>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8, marginBottom: 6 }}>
          <h2 style={{ margin: 0, fontSize: 13, fontWeight: 700, color: T.text, fontFamily: T.sans }}>The Mining book</h2>
          <span style={{ fontSize: 9.5, color: T.amber, fontFamily: T.mono, fontWeight: 600 }}>
            {picks.length} Lane A seats · producers, royalties &amp; majors · physical-anchor rule
          </span>
        </div>

        {picks.length === 0 && (
          <div style={{ padding: "14px 16px", borderRadius: 8, border: `1px dashed ${T.border}`, background: T.card,
                        fontSize: 11.5, color: T.muted, fontFamily: T.mono, lineHeight: 1.6 }}>
            Awaiting the maiden publish. The chain runs on the operator box
            (mining-universe → chain map → debates → Director → mining-publish --gcs); this fills in
            the moment the payload lands.
          </div>
        )}

        {track && (
          <div style={{ display: "flex", alignItems: "center", gap: 18, padding: "10px 14px", marginBottom: 12, borderRadius: 8,
                        background: T.card, border: `1px solid ${T.border}`, flexWrap: "wrap" }}>
            <div>
              <div style={{ fontSize: 8.5, color: T.muted, fontFamily: T.mono, textTransform: "uppercase", letterSpacing: "0.04em" }}>Live track record</div>
              <div style={{ fontSize: 18, fontWeight: 800, fontFamily: T.mono, color: (track.since_inception_pct || 0) >= 0 ? T.green : T.red }}>
                {pct(track.since_inception_pct, 2)}
              </div>
              <div style={{ fontSize: 8.5, color: T.light, fontFamily: T.mono }}>since {track.inception_date}</div>
            </div>
            {(track.history || []).length > 1 && <Spark series={(track.history || []).map((h: any) => [h.date, h.nav])} w={130} h={34} />}
            <div style={{ fontSize: 9.5, color: T.muted, fontFamily: T.mono, lineHeight: 1.5 }}>
              NAV {track.nav} · {track.n_open} held · {track.n_closed} closed
              <div style={{ fontSize: 8, color: T.light }}>{weighted ? "Director-weighted" : "equal-weight"} · live-forward, never back-filled</div>
            </div>
            {book?.benchmark?.benchmark_return_pct != null && (
              <div style={{ fontSize: 9.5, color: T.muted, fontFamily: T.mono, lineHeight: 1.5 }}>
                {book.benchmark.blend}: <span style={{ color: (book.benchmark.benchmark_return_pct || 0) >= 0 ? T.green : T.red }}>{pct(book.benchmark.benchmark_return_pct, 2)}</span>
                {book.benchmark.active_return_pct != null && (
                  <div>active <strong style={{ color: book.benchmark.active_return_pct >= 0 ? T.green : T.red }}>{pct(book.benchmark.active_return_pct, 2)}</strong></div>
                )}
              </div>
            )}
            {book?.stress_test && (
              <div style={{ fontSize: 9.5, color: T.muted, fontFamily: T.mono, lineHeight: 1.5 }}>
                stress <span style={{ color: T.red, fontWeight: 600 }}>{pct(book.stress_test.published_downside_pct)}</span> recession
                <div style={{ fontSize: 8 }}>{pct(book.stress_test.basket_to_52w_lows_pct)} to 52w lows</div>
              </div>
            )}
          </div>
        )}

        {book?.pool_stats?.banner && (
          <div style={{ fontSize: 9, color: T.light, fontFamily: T.mono, fontStyle: "italic", marginBottom: 12, lineHeight: 1.5 }}>
            {book.pool_stats.banner}
          </div>
        )}

        {/* picks grouped under their chain, ordered by the scoreboard — the page's whole argument */}
        {(board.length ? board.map((b: any) => b.chain_id) : Object.keys(picksByChain))
          .filter((cid) => (picksByChain[cid] || []).length)
          .map((cid) => {
            const rows = picksByChain[cid] || [];
            const sb = board.find((b: any) => b.chain_id === cid);
            const collapsed = openChain && openChain !== cid;
            return (
              <div key={cid} style={{ marginBottom: 14 }}>
                <div onClick={() => setOpenChain(openChain === cid ? null : cid)}
                     style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6, cursor: "pointer", flexWrap: "wrap" }}>
                  <span style={{ fontSize: 11, fontWeight: 700, color: T.amber, fontFamily: T.mono }}>{cap(cid)}</span>
                  {sb && <span style={{ fontSize: 9, color: T.muted, fontFamily: T.mono }}>setup #{sb.rank} · {num(sb.score, 1)}/100</span>}
                  {resolved[cid] && (
                    <span style={{ fontSize: 8.5, padding: "1px 5px", borderRadius: 3, fontFamily: T.mono, fontWeight: 700,
                                   background: "rgba(148,163,184,0.1)", color: TILT_COLOR[resolved[cid]] }}>{resolved[cid]}</span>
                  )}
                  <span style={{ fontSize: 9, color: T.muted, fontFamily: T.mono }}>{rows.length} seat{rows.length === 1 ? "" : "s"}</span>
                </div>
                {!collapsed && (
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(400px, 1fr))", gap: 12 }}>
                    {rows.map((p: any) => (
                      <div key={p.symbol} style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 8, padding: 13 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6, marginBottom: 7, flexWrap: "wrap" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 7, flexWrap: "wrap" }}>
                            <a href={`/stock/${p.symbol}?tab=debate`} style={{ fontSize: 14, fontWeight: 800, color: T.text, fontFamily: T.mono, textDecoration: "none" }}>{p.symbol}</a>
                            <span style={{ fontSize: 8.5, padding: "2px 5px", borderRadius: 4, fontFamily: T.mono, fontWeight: 700,
                                           background: p.fr_score >= 80 ? "rgba(20,184,122,0.2)" : "rgba(148,163,184,0.18)",
                                           color: p.fr_score >= 80 ? T.green : T.muted }}>{p.fr_score}<span style={{ opacity: 0.55 }}>/100</span></span>
                            {p.weight_pct != null && <span style={{ fontSize: 8.5, color: T.muted, fontFamily: T.mono }}>wt {p.weight_pct}%</span>}
                            {p.business_model && <span style={{ fontSize: 8, padding: "1px 4px", borderRadius: 3, background: "rgba(217,119,6,0.14)", color: T.amber, fontFamily: T.mono }}>{cap(p.business_model)}</span>}
                            {p.growth_capex_fcf_negative && <span title="build-cycle producer — size capped 0.75" style={{ fontSize: 8, padding: "1px 4px", borderRadius: 3, background: "var(--amber-light)", color: T.amber, fontFamily: T.mono, fontWeight: 700 }}>capex ¾</span>}
                            {p.torque_leverage_quadrant && <span title="high torque on a levered balance sheet — size capped 0.75" style={{ fontSize: 8, padding: "1px 4px", borderRadius: 3, background: "var(--amber-light)", color: T.amber, fontFamily: T.mono, fontWeight: 700 }}>torque×lev ¾</span>}
                            {p.headwind_unjustified && <span title="HEADWIND chain, no written justification — clamped 0.5" style={{ fontSize: 8, padding: "1px 4px", borderRadius: 3, background: "rgba(239,68,68,0.14)", color: T.red, fontFamily: T.mono, fontWeight: 700 }}>headwind ½</span>}
                          </div>
                          {typeof p.sop_mos_pct === "number" && (
                            <span style={{ fontSize: 12, fontWeight: 700, fontFamily: T.mono, color: p.sop_mos_pct >= 0 ? T.green : T.red }}>{pct(p.sop_mos_pct, 0)} MoS</span>
                          )}
                        </div>
                        {p.physical_anchor && (
                          <div title="the physical thing this seat makes, moves or extracts — the anti-Visa rule"
                               style={{ fontSize: 9, color: T.muted, fontFamily: T.mono, fontStyle: "italic", marginBottom: 5 }}>⚓ {p.physical_anchor}</div>
                        )}
                        <div style={{ fontSize: 9.5, color: T.light, fontFamily: T.mono, lineHeight: 1.55, marginBottom: 5 }}>{p.thesis}</div>
                        {p.cost_curve && <div style={{ fontSize: 9, color: T.muted, fontFamily: T.mono, lineHeight: 1.5 }}><strong style={{ color: T.light }}>Cost/torque: </strong>{p.cost_curve}</div>}
                        {p.contracting_reserve && <div style={{ fontSize: 9, color: T.muted, fontFamily: T.mono, lineHeight: 1.5 }}><strong style={{ color: T.light }}>Contract/reserve: </strong>{p.contracting_reserve}</div>}
                        {p.phase_fit && <div style={{ fontSize: 9, color: T.muted, fontFamily: T.mono, lineHeight: 1.5 }}><strong style={{ color: T.light }}>Phase fit: </strong>{p.phase_fit}</div>}
                        <div style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 9, color: T.muted, fontFamily: T.mono, marginTop: 6 }}>
                          <span>{p.funded_solvency || "—"}{p.ndebt_ebitda != null ? ` · ${p.ndebt_ebitda}x nd/EBITDA` : ""}</span>
                          {p.thesis_break_px != null && <span>break {p.thesis_break_px}</span>}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}

        {book?.mining_memo && (
          <details style={{ background: T.card, border: `1px solid ${T.amber}`, borderRadius: 10, padding: "16px 20px", marginTop: 14 }}>
            <summary style={{ fontSize: 13, fontWeight: 700, color: T.text, fontFamily: T.sans, cursor: "pointer", outline: "none" }}>Mining Director memo</summary>
            <pre style={{ whiteSpace: "pre-wrap", fontSize: 10.5, fontFamily: T.mono, color: T.light, marginTop: 12, lineHeight: 1.6 }}>
              {typeof book.mining_memo === "string" ? book.mining_memo : JSON.stringify(book.mining_memo, null, 2)}
            </pre>
          </details>
        )}

        <div style={{ fontSize: 8.5, color: T.light, fontFamily: T.mono, marginTop: 14, lineHeight: 1.6, maxWidth: 950 }}>
          Paper book — no broker connection, no orders. US-listed names only; much developer alpha
          lists on TSX/ASX and is out of scope. Lane B (pre-revenue developers) is a separate event
          tracker and is not part of this NAV. Never blended with the Apex, Value or Future
          Disruptive Tech books.
          {macro?.generated_at ? ` · macro ${macro.generated_at}` : ""}
          {book?.generated_at ? ` · book ${book.generated_at}` : ""}
          {book?.engine ? ` · ${book.engine}` : ""}
        </div>
      </section>
    </div>
  );
}
