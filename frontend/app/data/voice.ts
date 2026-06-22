// ── House Voice — the single source of truth for user-facing copy ──────────────
// Every code-derived token that can reach the screen (status enums, verdicts,
// regime labels, valuation-method keys, lanes, factors…) maps here to ONE plain
// phrasing, so the same token reads identically everywhere — stock page, table,
// briefing, catalyst board. Voice = approachable-hybrid: Morningstar-grade
// clarity, a touch warmer, no slang, no emoji.
//
// label = short on-screen text · tip = plain-English definition (hover card via
// <Term>/<Tip>) · tone = optional badge color. Maintained by the `house-voice`
// skill; new UI copy goes through this file, never raw tokens.

export type Tone = "good" | "mid" | "bad" | "muted";
export type Term = { label: string; tip?: string; tone?: Tone };

export const VOICE: Record<string, Term> = {
  // ── Social Arb (consumer-behavior signals) ──
  SA_DEMAND: { label: "Demand index", tip: "Blended z-score of consumer demand against the entity's own 30-day baseline — weighted mention volume plus purchase-intent share. High = chatter accelerating, not just loud." },
  SA_AWARENESS: { label: "Awareness index", tip: "How much the financial world has caught on: finance-media article count + StockTwits trader volume, capped. The other half of the gap trade." },
  SA_GAP: { label: "Gap score", tip: "Demand − Awareness. The edge: consumers moving while the market hasn't noticed. The gap closes (and the trade ends) when finance media and traders pile in." },
  SA_VELOCITY: { label: "Velocity z", tip: "Today's weighted mentions vs the trailing 30-day mean/σ. Only recorded when z ≥ 2.5 — the step-change detector, not the absolute level." },
  SA_CORROBORATION: { label: "Corroboration", tip: "How many platforms spiked in the same 48h window. ≥2 filters out platform-native memes; single-platform spikes are usually noise. A hard multiplier on the score." },
  SA_MATERIALITY: { label: "Materiality", tip: "How much a viral product actually moves the mapped ticker. Mono-brand / small-cap → near 1.0; buried inside a megacap → near 0. Revenue-share when known, else from market cap." },
  SA_INTENT: { label: "Purchase-intent share", tip: "Fraction of mentions expressing buying behavior — 'just bought', 'switching to', 'sold out everywhere'. Volume with intent beats volume alone." },
  SA_SCORE: { label: "Signal score", tip: "Composite rank: gap × materiality × corroboration, intent-weighted. A relative ranking across live signals — not a probability or a return estimate." },
  SA_DIRECTION: { label: "Direction", tip: "Long when the demand/awareness gap is positive (rising behavior, low awareness). Watch when it's borderline or awareness is already catching up." },

  // ── Catalyst tiers ──
  ACTIVE:     { label: "Active", tone: "good", tip: "Real, dated, forward catalyst that passed the skeptic check. The actionable tier — but still check the edge before sizing." },
  CONTINGENT: { label: "Waiting on a trigger", tone: "mid", tip: "The catalyst depends on a prior event resolving first. Watch the upstream trigger." },
  NONE:       { label: "Dropped", tone: "muted", tip: "Failed the gate or lost its edge (catalyst fired, no upside left, or deal trading through terms). Off the board — shown only so you can see why it was dropped." },

  // ── Catalyst / Loeb score ──
  CATALYST_SCORE: { label: "Catalyst score (0–10)", tip: "How real, clean, and imminent the CATALYST is — not how cheap the stock is, and not the edge. A signed deal scores high even at a 0.3% spread. 5–6 = one real dated catalyst; 7–8 = strong, ≥2 Bloom gates; 9–10 = multiple imminent hard catalysts converging (rare)." },

  // ── Edge grades ──
  EDGE: { label: "Edge", tip: "How much mispricing is left to capture — the perishable part, re-checked at entry. A catalyst can be completely real (high score) yet have no edge (Low) once the market has priced it." },
  H: { label: "High", tone: "good", tip: "Edge: High — ≥ 2.5 : 1 reward-to-risk against the live price. Meaningful mispricing left." },
  M: { label: "Medium", tone: "mid", tip: "Edge: Medium — 1.5–2.5 : 1, a modest edge. Also where a high ratio gets capped when it rests on a thin floor." },
  L: { label: "Low", tone: "bad", tip: "Edge: Low — under 1.5 : 1, or a blocking flag (priced out, through terms, broken inputs). Not actionable now, but can re-open if the price pulls back." },

  // ── Risk / reward + binary metrics ──
  RR: { label: "Risk / reward", tip: "Reward-to-risk vs the live price. Sum-of-parts / recovery / capital-return: (fair value − price) ÷ (price − downside floor). Merger-arb: (deal price − price) ÷ (price − pre-bid price). Binaries get expected value instead of a single ratio." },
  EV: { label: "Expected value", tip: "P(win) × upside + P(loss) × downside, as % of price. Binaries show this instead of one ratio — a coin-flip shown as a single risk/reward is misleading." },
  PAYOFF: { label: "Payoff odds", tip: "The raw odds if it works: upside ÷ downside. Read it alongside the win probability, never on its own." },
  WIN_PROB: { label: "Win probability", tip: "Estimated chance the binary outcome (approval, ruling) goes the right way. Calibrated, cited in the basis." },

  // ── Floor flags ──
  THIN_FLOOR: { label: "Thin floor", tone: "mid", tip: "The downside cushion is under 15% of the price, so the risk/reward rests on a small denominator and reads higher than it really is. The grade is capped at Medium and the raw ratio is hidden — trust the grade, not the number." },
  TINY_FLOOR: { label: "Tiny floor", tone: "mid", tip: "Downside under 5% of price — an even thinner cushion. Same handling: grade capped, raw ratio hidden." },

  // ── Blocking / status flags ──
  NO_UPSIDE:             { label: "Priced out", tone: "bad", tip: "The stock already sits at or above fair value — the catalyst has played out. Kept on the board (it can re-open on a pullback) but graded Low." },
  FLOOR_GE_LIVE:         { label: "No downside estimate", tone: "muted", tip: "The estimated floor is at or above the current price, so downside can't be measured and no ratio is shown." },
  TRADING_THROUGH_TERMS: { label: "Trading through terms", tone: "bad", tip: "A merger-arb name trading ABOVE the deal price — the spread is negative, no arb left. Dropped." },
  NO_BREAK_DOWNSIDE:     { label: "No break downside", tone: "muted", tip: "Merger-arb where the pre-bid price is at/above the current price — the break risk can't be sized." },
  QUARANTINED:           { label: "Quarantined", tone: "muted", tip: "The valuation build had broken inputs (bad units or per-row arithmetic), so no risk/reward is shown — the number can't be trusted until the build is fixed." },
  SOP_TARGET_MISMATCH:   { label: "Build mismatch", tone: "muted", tip: "The sum-of-parts build doesn't reconcile to the stated target; the computed build value is used for the risk/reward instead of the asserted target." },
  RR_STALE:              { label: "Stale price", tone: "muted", tip: "The live price for the risk/reward was stale or unavailable, so it falls back to the dossier-time price. Refresh to update." },
  RE_DOSSIER:            { label: "Needs refresh", tone: "mid", tip: "The price has moved more than 15% since the valuation was built — the catalyst may be repricing or the thesis may have broken. The fair-value estimate needs a refresh." },
  ROW_EV_MISMATCH:       { label: "Build warning", tone: "muted", tip: "A segment's value doesn't match its inputs (value × multiple). The name is quarantined until the build is corrected." },
  MULTIPLE_OUT_OF_BAND:  { label: "Build warning", tone: "muted", tip: "A valuation multiple is outside the plausible band (EBITDA 4–25×, sales 0.5–12×) with no cited comp." },
  UNITS_UNDECLARED:      { label: "Build warning", tone: "muted", tip: "The valuation build didn't declare its units, so the math can't be trusted — quarantined." },

  // ── Lanes (the hunting grounds) ──
  forced_seller:   { label: "Forced-seller overhang", tip: "A forced or large seller is suppressing the stock; you own the suppressed shares and time the overhang clearing, which re-rates it. The highest-priority lane." },
  spinoff:         { label: "Spin-off", tip: "Post-spin orphan selling, sum-of-parts unlock, and RemainCo re-rating. The 'actually read the Form 10' edge." },
  distressed:      { label: "Distressed / restructuring", tip: "A dated balance-sheet milestone — refinancing, asset sale, deleveraging trigger, or bankruptcy emergence." },
  index_flow:      { label: "Index flow", tip: "Forced index rebalancing — buys/sells that must happen on a known date." },
  activist:        { label: "Activist + structural", tip: "An activist hardening a trigger toward a sale, split, or board change." },
  merger_arb:      { label: "Merger-arb", tip: "A deal where the spread reflects real, analyzable risk (antitrust, cross-border, contested vote) — not a clean 1% cash arb that's already priced." },
  capital_return:  { label: "Capital return", tip: "A tender, special dividend, or dated debt paydown." },
  supply_timing:   { label: "Supply shortage + timing", tip: "A structural shortage the company is uniquely positioned to fill on a timeline." },
  bio_convergence: { label: "Dated binary", tip: "A PDUFA or trial readout with mispriced asymmetry — not a 50/50 coin-flip. Shown as a barbell (expected value / payoff / win-prob), never a single ratio." },

  // ── Resolution drivers (Basket 13) ──
  Forced_divest_flow:   { label: "Forced divestiture", tip: "A regulator is forcing a sale of assets — the divestiture flow is a dated, mechanical catalyst." },
  FDA_clinical_readout: { label: "Trial readout", tip: "A clinical-trial result on a known date — a dated binary outcome." },
  FDA_approval_decision:{ label: "FDA decision", tip: "An FDA approval/rejection decision (PDUFA date) — a dated binary outcome." },
  FDA_pathway_feedback: { label: "FDA pathway feedback", tip: "Guidance from the FDA on the regulatory path — softer-dated than a decision, but it can harden the thesis." },
  US_antitrust:         { label: "Antitrust ruling", tip: "A US antitrust review or ruling that gates a deal — a dated, binary risk." },
  Refi_restructuring:   { label: "Refinancing / restructuring", tip: "A dated balance-sheet milestone — refinancing or restructuring step." },
  Deal_close_generic:   { label: "Deal close", tip: "A merger or acquisition closing on its expected date." },

  // ── Structural columns ──
  BOARD_PRIORITY:    { label: "Board priority", tip: "The sort key: the catalyst score, nudged by lane priority so forced-sellers and spins surface above merger-arb and binaries at an equal score. The score itself is untouched — this only affects ordering within a tier." },
  RESOLUTION_DRIVER: { label: "Resolution driver", tip: "The single event that actually resolves this position (FDA decision, antitrust approval, deal close, spin distribution, refi…). Used to judge concentration — many names resolving on the same driver is one bet in disguise, not a diversified book." },
  DRIFT:             { label: "Drift", tip: "How far the live price has moved from the price used when the valuation was built. Large drift flags a refresh." },

  // ── Bloom timeline stages ──
  STAGE_CATALYST:  { label: "Stage 1 — Catalyst", tip: "The event itself: detected and described, with the primary-source evidence." },
  STAGE_MILESTONE: { label: "Stage 2 — Milestone", tip: "The dated checkpoint that hardens the catalyst, plus the next date to watch." },
  STAGE_VERIFY:    { label: "Stage 3 — Verify", tip: "An adversarial skeptic check against primary sources. Verified means the line survived a deliberate attempt to kill it." },

  // ── Verify status ──
  CONFIRMED:                 { label: "Verified", tone: "good", tip: "Passed the adversarial skeptic check against primary sources." },
  CONFIRMED_WITH_CORRECTIONS:{ label: "Verified (with edits)", tone: "good", tip: "Survived the skeptic check, with some facts adjusted." },
  SCAN_ONLY:                 { label: "Quick-scan only", tone: "muted", tip: "On the board from the fast triage pass but not yet skeptic-checked — held in Watch until verified." },
  UNVERIFIED:                { label: "Unverified", tone: "muted", tip: "Flagged, but the adversarial check is still pending. Held in Watch." },
  REFUTED:                   { label: "Knocked down", tone: "bad", tip: "The skeptic disproved the thesis against a primary source. Dropped." },

  // ── Catalyst outcomes (resolved paper positions) ──
  OPEN:          { label: "Live", tone: "good", tip: "The position is open and the catalyst hasn't resolved yet." },
  CLOSED:        { label: "Closed", tone: "muted", tip: "The position has been closed out." },
  FIRED_WIN:     { label: "Played out — win", tone: "good", tip: "The catalyst happened and the thesis worked; the upside was captured." },
  FIRED_LOSS:    { label: "Played out — loss", tone: "bad", tip: "The catalyst happened but the thesis didn't work." },
  SLIPPED:       { label: "Delayed", tone: "mid", tip: "The catalyst's timing slipped. The thesis can still be intact — the clock just reset." },
  THESIS_BROKEN: { label: "Thesis broke", tone: "bad", tip: "The reason to own it no longer holds, so the position was dropped." },
  EDGE_GONE:     { label: "Edge priced in", tone: "muted", tip: "The market repriced the name before the catalyst, leaving no edge left to capture." },
  EXPIRED:       { label: "Window closed", tone: "muted", tip: "The catalyst window passed without a clean resolution." },

  // ── Order / limit status ──
  PENDING:       { label: "Order placed", tone: "mid", tip: "An order is placed but not yet filled." },
  PENDING_LIMIT: { label: "Waiting to buy (limit)", tone: "mid", tip: "A limit order is resting below the market — we only buy at our price, so the position isn't held yet." },
  PENDING_HARD:  { label: "Order placed", tone: "mid", tip: "A firm order is placed and waiting to fill." },

  // ── Performance barrier outcomes ──
  TOUCHED:  { label: "Hit target", tone: "good", tip: "The stock reached the target gain (the barrier) within the window." },
  NO_TOUCH: { label: "Missed target", tone: "bad", tip: "The window closed before the stock reached the target gain." },

  // ── Macro regime ──
  RISK_ON:  { label: "Risk-on", tone: "good", tip: "A favorable macro backdrop — conditions support leaning into growth and momentum." },
  RISK_OFF: { label: "Risk-off", tone: "bad", tip: "A defensive backdrop — prioritize quality and downside protection." },
  CAUTIOUS: { label: "Cautious", tone: "mid", tip: "Rising risks — stick to high-conviction, debate-backed names." },
  NEUTRAL:  { label: "Neutral", tone: "muted", tip: "A balanced, sideways backdrop with no clear directional edge." },

  // ── Composite classification ──
  DEEP_VALUE:     { label: "Deep value", tip: "Trading well below intrinsic value on multiple measures." },
  VALUE:          { label: "Value", tip: "A valuation-driven pick — cheaper than its fundamentals justify." },
  QUALITY_GROWTH: { label: "Quality growth", tip: "A high-quality compounder — strong returns on capital and durable growth." },
  GROWTH:         { label: "Growth", tip: "Growth-led, typically at a premium valuation." },
  SPECULATIVE:    { label: "Speculative", tone: "mid", tip: "A binary or turnaround play — higher risk, wider range of outcomes." },

  // ── Action / signal badges (screener, portfolio, stock card) ──
  STRONG_BUY: { label: "Strong buy", tone: "good" },
  BUY:        { label: "Buy", tone: "good" },
  WATCH:      { label: "Watch", tone: "mid", tip: "Worth monitoring, but not actionable yet — waiting on a better price, a date, or a confirmation." },
  HOLD:       { label: "Hold", tone: "muted" },
  ADD:        { label: "Add", tone: "good" },
  TRIM:       { label: "Trim", tone: "mid" },
  SELL:       { label: "Sell", tone: "bad" },

  // ── Technical signal direction ──
  BULLISH: { label: "Bullish", tone: "good" },
  BEARISH: { label: "Bearish", tone: "bad" },

  // ── 5-factor names (stock detail radar) ──
  momentum:    { label: "Momentum", tip: "Price and earnings acceleration." },
  quality:     { label: "Quality", tip: "Returns on capital, margins, and balance-sheet strength." },
  growth:      { label: "Growth", tip: "Revenue and earnings growth rate." },
  value:       { label: "Value", tip: "Valuation multiples vs peers and history." },
  smart_money: { label: "Smart money", tip: "Institutional accumulation — what big, informed holders are doing." },

  // ── Valuation methodologies (one name per lens) ──
  dcf_fcff:           { label: "DCF (free cash flow)", tip: "Discounted cash flow on free cash flow to the firm — value from the cash the business throws off." },
  dcf_fcff_mos:       { label: "Margin of safety", tip: "How far below the DCF fair value the stock trades — the cushion if you're wrong." },
  rd_capitalized_dcf: { label: "DCF (R&D capitalized)", tip: "DCF that treats R&D as an investment rather than an expense — fairer for research-heavy companies." },
  owner_earnings:     { label: "Owner earnings", tip: "Buffett-style cash a long-term owner could pull out: earnings + depreciation − maintenance capex." },
  epv:                { label: "Earnings power value", tip: "What the business is worth on today's earnings with no growth assumed — a conservative floor." },
  epv_to_ev:          { label: "Earnings power vs price", tip: "Earnings power value against enterprise value — how much you pay for the no-growth earnings." },
  graham_revised:     { label: "Graham (revised)", tip: "A modernized Benjamin Graham fair-value formula." },
  graham_revised_mos: { label: "Graham margin of safety", tip: "Discount to the revised-Graham fair value." },
  iv15_deep_value:    { label: "15-yr intrinsic value", tip: "A long-horizon intrinsic-value estimate — the deep-value lens." },
  acquirers_multiple: { label: "Acquirer's multiple", tip: "Enterprise value ÷ operating earnings — how an acquirer would price the whole business." },
  ev_gp:              { label: "EV / gross profit", tip: "Enterprise value against gross profit — a quality-aware cheapness measure." },
  ev_gross_profit:    { label: "Gross profitability", tip: "Gross profit relative to assets (Novy-Marx) — a quality factor, not a cheapness multiple." },
  consensus_mos:      { label: "Blended margin of safety", tip: "The blended discount to fair value across the valuation methods." },

  // ── Speculair books ──
  apex_basket:           { label: "Apex basket", tip: "The highest-conviction names that cleared the full multi-agent debate." },
  capitulation_watchlist:{ label: "Beaten-Down Watchlist", tip: "Oversold names being watched for a reversal — not yet bought." },
  conviction:            { label: "Conviction", tip: "How strongly the system backs the name, 0–100, after the debate." },
};

// Back-compat: the old catalyst-glossary shape {title, body}, derived from every
// VOICE entry that carries a definition. Tip.tsx reads this; do not hand-edit —
// add to VOICE above instead.
export const GLOSSARY: Record<string, { title: string; body: string }> = Object.fromEntries(
  Object.entries(VOICE)
    .filter(([, v]) => v.tip)
    .map(([k, v]) => [k, { title: v.label, body: v.tip as string }]),
);

// Turn an un-mapped token into something readable so a raw code token never shows.
// PENDING_LIMIT -> "Pending Limit"; capitulation_watchlist -> "Capitulation Watchlist".
// Short all-caps acronyms (DCF, EPV, RSI) are preserved.
export function prettify(token: string): string {
  if (!token) return "";
  if (/^[A-Z0-9]{2,5}$/.test(token)) return token;
  return token
    .replace(/[_-]+/g, " ")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .trim()
    .split(/\s+/)
    .map((w) => (/^[A-Z0-9]{2,5}$/.test(w) ? w : w.charAt(0).toUpperCase() + w.slice(1).toLowerCase()))
    .join(" ");
}

export function termLabel(token?: string | null): string {
  if (token == null || token === "") return "";
  return VOICE[token]?.label ?? prettify(String(token));
}
export function termTip(token?: string | null): string | undefined {
  return token == null ? undefined : VOICE[token]?.tip;
}
export function termTone(token?: string | null): Tone | undefined {
  return token == null ? undefined : VOICE[token]?.tone;
}
