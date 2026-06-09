// Plain-English glossary for the Catalyst Watch UI. Keyed by the exact token used in the data
// (edge_flags strings, lane_canon values, tier, edge_grade) plus UI labels. Used by <Tip>.
export const GLOSSARY: Record<string, { title: string; body: string }> = {
  // ---- tiers ----
  ACTIVE:     { title: "Active", body: "Real, dated, forward catalyst that passed the skeptic check. The actionable tier — but still check the edge before sizing." },
  WATCH:      { title: "Watch", body: "Real catalyst, but soft-dated, partly priced, or waiting on a trigger to harden. Monitor; it escalates to Active as the date or figure firms up." },
  CONTINGENT: { title: "Contingent", body: "The catalyst depends on a prior event resolving first. Watch the upstream trigger." },
  NONE:       { title: "Dropped", body: "Failed the gate or lost its edge (catalyst fired, no upside left, or deal trading through terms). Off the board — shown only so you can see why it was dropped." },

  // ---- catalyst / Loeb score ----
  CATALYST_SCORE: { title: "Catalyst score (0–10)", body: "How real, clean, and imminent the CATALYST is — not how cheap the stock is, and not the edge. A signed deal scores high even at a 0.3% spread. 5–6 = one real dated catalyst; 7–8 = strong, ≥2 Bloom gates; 9–10 = multiple imminent hard catalysts converging (rare)." },

  // ---- edge grades ----
  EDGE:  { title: "Edge", body: "How much mispricing is left to capture — the perishable part, re-checked at entry. A catalyst can be completely real (high score) yet have no edge (Low) once the market has priced it." },
  H:     { title: "Edge: High", body: "≥ 2.5 : 1 reward-to-risk against the live price — meaningful mispricing left." },
  M:     { title: "Edge: Medium", body: "1.5–2.5 : 1 — modest edge. Also where a high ratio gets capped when it rests on a thin floor." },
  L:     { title: "Edge: Low", body: "Under 1.5 : 1, or a blocking flag (priced out, through terms, broken inputs). Not actionable now — but a Low-edge name with a live catalyst can re-open if the price pulls back." },

  // ---- R:R ----
  RR: { title: "Risk / reward", body: "Reward-to-risk vs the live price. Sum-of-parts / recovery / capital-return: (fair value − price) ÷ (price − downside floor). Merger-arb: (deal price − price) ÷ (price − pre-bid price). Binaries get EV instead of a single ratio." },

  // ---- binary metrics ----
  EV:       { title: "Expected value", body: "P(win) × upside + P(loss) × downside, as % of price. Binaries show this instead of one ratio — a coin-flip shown as a single R:R is misleading." },
  PAYOFF:   { title: "Payoff odds", body: "The raw odds if it works: upside ÷ downside. Read it alongside the win probability, never on its own." },
  WIN_PROB: { title: "Win probability", body: "Estimated chance the binary outcome (approval, ruling) goes the right way. Calibrated, cited in the basis." },

  // ---- floor flags (the display-fix ones) ----
  THIN_FLOOR: { title: "Thin floor", body: "The downside cushion is under 15% of the price, so the R:R rests on a small denominator and reads higher than it really is. The grade is capped at M and the raw ratio is hidden — trust the grade, not the number." },
  TINY_FLOOR: { title: "Tiny floor", body: "Downside under 5% of price — an even thinner cushion. Same handling: grade capped, raw ratio hidden." },

  // ---- blocking / status flags ----
  NO_UPSIDE:            { title: "Priced out", body: "The stock already sits at or above fair value — the catalyst has played out. Kept on the board (it can re-open on a pullback) but graded Low." },
  FLOOR_GE_LIVE:        { title: "No downside estimate", body: "The estimated floor is at or above the current price, so downside can't be measured and no ratio is shown." },
  TRADING_THROUGH_TERMS:{ title: "Trading through terms", body: "A merger-arb name trading ABOVE the deal price — the spread is negative, no arb left. Dropped." },
  NO_BREAK_DOWNSIDE:    { title: "No break downside", body: "Merger-arb where the pre-bid price is at/above the current price — the break risk can't be sized." },
  QUARANTINED:          { title: "Quarantined", body: "The valuation build had broken inputs (bad units or per-row arithmetic), so no R:R is shown — the number can't be trusted until the build is fixed." },
  SOP_TARGET_MISMATCH:  { title: "Build mismatch", body: "The sum-of-parts build doesn't reconcile to the stated target; the computed build value is used for the R:R instead of the asserted target." },
  RR_STALE:             { title: "Stale price", body: "The live price for the R:R was stale or unavailable, so it falls back to the dossier-time price. Refresh to update." },
  RE_DOSSIER:           { title: "Needs re-dossier", body: "The price has moved more than 15% since the valuation was built — the catalyst may be repricing or the thesis may have broken. The fair-value estimate needs a refresh." },
  ROW_EV_MISMATCH:      { title: "Build integrity warning", body: "A segment's value doesn't match its inputs (value × multiple). The name is quarantined until the build is corrected." },
  MULTIPLE_OUT_OF_BAND: { title: "Build integrity warning", body: "A valuation multiple is outside the plausible band (EBITDA 4–25×, sales 0.5–12×) with no cited comp." },
  UNITS_UNDECLARED:     { title: "Build integrity warning", body: "The valuation build didn't declare its units, so the math can't be trusted — quarantined." },

  // ---- lanes (the 9 hunting grounds, in priority order) ----
  forced_seller:   { title: "Forced-seller overhang", body: "A forced or large seller is suppressing the stock; you own the suppressed shares and time the overhang clearing, which re-rates it. The DHER playbook — highest-priority lane." },
  spinoff:         { title: "Spin-off", body: "Post-spin orphan selling, sum-of-parts unlock, and RemainCo re-rating. The 'actually read the Form 10' edge." },
  distressed:      { title: "Distressed / restructuring", body: "A dated balance-sheet milestone — refinancing, asset sale, deleveraging trigger, or bankruptcy emergence." },
  index_flow:      { title: "Index flow", body: "Forced index rebalancing — buys/sells that must happen on a known date." },
  activist:        { title: "Activist + structural", body: "An activist hardening a trigger toward a sale, split, or board change." },
  merger_arb:      { title: "Merger-arb", body: "A deal where the spread reflects real, analyzable risk (antitrust, cross-border, contested vote) — not a clean 1% cash arb that's already priced." },
  capital_return:  { title: "Capital return", body: "A tender, special dividend, or dated debt paydown." },
  supply_timing:   { title: "Supply shortage + timing", body: "A structural shortage the company is uniquely positioned to fill on a timeline (the Bloom Energy playbook)." },
  bio_convergence: { title: "Dated binary", body: "A PDUFA or trial readout with MISPRICED asymmetry — not a 50/50 coin-flip. Shown as a barbell (EV / payoff / win-prob), never a single ratio." },

  // ---- structural columns ----
  BOARD_PRIORITY:    { title: "Board priority", body: "The sort key: the catalyst score, nudged by lane priority so forced-sellers and spins surface above merger-arb and binaries at an equal score. The score itself is untouched — this only affects ordering within a tier." },
  RESOLUTION_DRIVER: { title: "Resolution driver", body: "The single event that actually resolves this position (FDA decision, antitrust approval, deal close, spin distribution, refi…). Used to judge concentration — many names resolving on the same driver is one bet in disguise, not a diversified book." },
  DRIFT:             { title: "Drift", body: "How far the live price has moved from the price used when the valuation was built. Large drift flags a re-dossier." },

  // ---- Bloom timeline stages ----
  STAGE_CATALYST:  { title: "Stage 1 — Catalyst", body: "The event itself: detected and described, with the primary-source evidence." },
  STAGE_MILESTONE: { title: "Stage 2 — Milestone", body: "The dated checkpoint that hardens the catalyst, plus the next date to watch." },
  STAGE_VERIFY:    { title: "Stage 3 — Verify", body: "An adversarial skeptic check against primary sources. CONFIRMED means the line survived a deliberate attempt to kill it." },

  // ---- verify status ----
  CONFIRMED:                { title: "Confirmed", body: "Passed the adversarial skeptic tier against primary sources." },
  CONFIRMED_WITH_CORRECTIONS:{ title: "Confirmed (with corrections)", body: "Survived the skeptic, with some facts adjusted." },
  SCAN_ONLY:                { title: "Scan-only", body: "On the board from the fast triage pass but not yet skeptic-checked — held in Watch until verified." },
  UNVERIFIED:               { title: "Unverified", body: "Flagged but the adversarial pass is still pending. Held in Watch." },
  REFUTED:                  { title: "Refuted", body: "The skeptic killed the thesis against a primary source. Dropped." },
};
