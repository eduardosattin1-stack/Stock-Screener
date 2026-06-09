// Catalyst Watch — verified investigation board (2026-06-05)
// Authored from the multi-agent research + adversarial-verify passes, NOT the legacy backend scanner.
// Scores are v4 methodology: base (Bloom-gate catalyst quality) x convergence x confirmation, clamped 0-10.
// See CATALYST_SCORING_REBUILD.md (methodology) + CATALYST_WATCH_BOARD.md (the board).
// Served locally by /api/catalysts/{candidates,scan}; unknown symbols still proxy Cloud Run.

const NO_OPTIONS = (note: string) => ({
  iv_current: null,
  skew_25d: null,
  term_structure: "N/A",
  pc_oi_ratio: null,
  total_oi: null,
  implied_earnings_move_pct: null,
  market_sentiment_flag: "N/A",
  overall_interpretation: note,
});

const STAMP = "2026-06-05T12:00:00Z";

// Full per-symbol dossiers (rendered on the detail pane).
export const CATALYST_BOARD: Record<string, any> = {
  MBGL: {
    symbol: "MBGL", company_name: "Mobility Global (S&P Global spin-off)", price: null, market_cap: 9000000000,
    catalyst_density_score: 7.5, adjusted_loeb_score: 7.5, final_adjusted_loeb: 7.5, upside_downside_ratio: 2.0,
    recommendation: "WATCH", catalyst_nature: "mechanical_execution", re_rate_status: "pending",
    tier: "ACTIVE", lane: "Spin-off", gate_status: "PASS", bloom_gates_passed: ["G2_concrete_commitment", "G3_unpriced_figure"],
    edge: "High", verify_verdict: "CONFIRMED-w/-corrections", instrument: "SpinCo equity (cash-equity at launch; options likely not day-1)",
    resolution_driver: "Spin distribution + forced index reflow (idiosyncratic)",
    analysis_summary: "ACTIVE [verified]. S&P Global cuts its Mobility/CARFAX unit ($1.75B rev, 40.6% adj-EBITDA margin, 81% subscription) loose, loaded with ~$2.0B new senior notes funding a cash dividend up to parent. Record Jun 15 -> when-issued 'MBGL WI' Jun 26 -> distribution Jul 1, 2026 (dates verbatim from the May 21 SPGI PR). The edge: a sub-$10B, brand-name orphan force-sold by index funds that hold SPGI for the ratings franchise, not auto-data. Bloom gates: G2 (board-approved, Form-10-filed, dated distribution) + G3 (orphan standalone economics + SoP dislocation); no G1 counterparty (structural separation). Caveat: listed MBGL options unlikely at launch -> cash-equity expression first.",
    bloom_catalysts: {
      catalyst_1: { title: "Separation Approved & Dated", detected: true, description: "Board-approved, Form-10 effective pending; 1-for-1 tax-free distribution Jul 1, 2026.", evidence: "S&P Global PR, May 21 2026: record Jun 15, WI 'MBGL WI' Jun 26, distribution effective 12:01am Jul 1; lists NYSE 'MBGL'." },
      catalyst_2: { title: "Forced Index Reflow", detected: true, description: "SPGI index/active holders dump the orphan into no natural buyer base at distribution.", evidence: "$2.0B SpinCo notes priced May 19 2026 ($650M+$650M+$700M) to fund a cash payment to parent." },
      catalyst_3: { title: "Orphan Re-rate", detected: false, description: "CARFAX-anchored, 81%-subscription standalone re-rates to a data-comp multiple once the forced selling clears.", evidence: "Pending post-distribution; the asymmetric leg." },
    },
    loeb_criteria: {
      catalyst_density: { rating: "High", analysis: "Single hard dated event (Jul 1 distribution) with a mechanical forced-flow tail." },
      sum_of_parts: { detected: true, analysis: "CARFAX + B2B mobility data trades inside SPGI at the ratings-franchise multiple; standalone deserves a data-comp re-rate." },
      activism_potential: { detected: false, analysis: "N/A — structural separation, no activist." },
      risk_reward: { ratio: "2.0:1", analysis: "Upside on the orphan re-rate vs. limited downside (quality subscription base, defensible cash flows)." },
    },
    options_signals: NO_OPTIONS("No listed MBGL options at launch (SpinCo not yet trading; SPGI options get adjusted to include the stub). Cash-equity expression."),
    recent_events: [
      { date: "2026-05-21", type: "filing", title: "S&P Global approves separation of Mobility Global (record Jun 15, distribution Jul 1)", link: "https://press.spglobal.com/2026-05-21" },
      { date: "2026-05-19", type: "news", title: "Mobility Global prices $2.0B senior notes to fund cash payment to parent", link: "https://www.prnewswire.com/news-releases/302776849" },
      { date: "2026-05-07", type: "filing", title: "Form 10 registration statement filed for Mobility Global separation", link: "https://press.spglobal.com/2026-05-07" },
    ],
    cache_timestamp: STAMP,
  },

  "PRX.AS": {
    symbol: "PRX.AS", company_name: "Prosus N.V. (forced seller of Delivery Hero)", price: 40.33, market_cap: 88000000000,
    catalyst_density_score: 4.5, adjusted_loeb_score: 4.5, final_adjusted_loeb: 4.5, upside_downside_ratio: 1.4,
    recommendation: "WATCH", catalyst_nature: "pricing_dislocation", re_rate_status: "pending",
    tier: "WATCH", lane: "Forced-seller overhang (corrected)", gate_status: "WEAK (no clean catalyst)", bloom_gates_passed: ["G1_named_counterparty"],
    edge: "Low", verify_verdict: "DEMOTED — forced-seller framing was wrong (the holdco is NOT the beneficiary)",
    instrument: "Weak — holdco-discount is perennial, not a catalyst; the re-rate is on the underlying (DHER), already fired",
    resolution_driver: "EC waiver ruling affects DHER's overhang, not PRX's value",
    analysis_summary: "WATCH -> DEMOTED [forced-seller framing corrected]. The DHER playbook is about the OVERHANG on the UNDERLYING (DHER) clearing and re-rating the stock — NOT the holdco/seller benefiting. So 'long Prosus the compelled seller' was the wrong read: Prosus being forced to sell doesn't re-rate Prosus; it pressures DHER (which already re-rated EUR14.8->38.8 on the Uber bid = the underlying trade is FIRED). PRX's holdco discount is a perennial structural discount, not a dated catalyst. Demoted to a low WATCH. (See BLCO for the one name that actually fits the corrected forced-seller-overhang playbook.)",
    bloom_catalysts: {
      catalyst_1: { title: "Binding Forced Sale", detected: true, description: "EU merger-remedy condition compels Prosus to divest its DHER stake by Oct 11, 2026.", evidence: "EC extension to Oct 11 confirmed Jun 2 2026; condition from the Aug-2025 Just Eat Takeaway clearance." },
      catalyst_2: { title: "Waiver Decision (the trigger)", detected: false, description: "Prosus asked the EC to scrap the requirement (May 25 2026); grant lifts the overhang off PRX.", evidence: "Waiver request reported May 25 2026; binary political decision." },
      catalyst_3: { title: "Overhang Removal / Re-rate", detected: false, description: "Holdco discount + forced-seller overhang compress once the path resolves.", evidence: "PRX EUR40.33, near 1-yr low EUR37.37." },
    },
    loeb_criteria: {
      catalyst_density: { rating: "High", analysis: "Hard dated deadline + a binary waiver decision; multiple paths to overhang removal." },
      sum_of_parts: { detected: true, analysis: "PRX trades at a wide discount to its listed/unlisted holdings incl. the appreciated DHER stake it cannot vote." },
      activism_potential: { detected: true, analysis: "Regulator-forced action; Uber as strategic counterparty/buyer of the blocks." },
      risk_reward: { ratio: null, analysis: "Upside if the condition is dropped/eased vs. a forced fire-sale + DHER de-rate downside." },
    },
    options_signals: NO_OPTIONS("Options not pulled for this Amsterdam line (verified-investigation board; no ThetaData run)."),
    recent_events: [
      { date: "2026-06-02", type: "news", title: "Prosus granted until Oct 11 for the Delivery Hero stake sale", link: "https://www.moneyweb.co.za/" },
      { date: "2026-05-25", type: "news", title: "Prosus asks EU to scrap the Delivery Hero stake-sale requirement", link: "https://www.pymnts.com/" },
    ],
    cache_timestamp: STAMP,
  },

  MGNI: {
    symbol: "MGNI", company_name: "Magnite, Inc. (Google AdX divestiture beneficiary)", price: 14.83, market_cap: 2100000000,
    catalyst_density_score: 7.2, adjusted_loeb_score: 7.2, final_adjusted_loeb: 7.2, upside_downside_ratio: 2.6,
    recommendation: "WATCH", catalyst_nature: "pricing_dislocation", re_rate_status: "pending",
    tier: "WATCH", lane: "Forced Seller (beneficiary)", gate_status: "PASS", bloom_gates_passed: ["G1_named_counterparty", "G3_unpriced_figure"],
    edge: "High", verify_verdict: "CONFIRMED (wave-1)", instrument: "MGNI equity / Dec-2026 calls",
    resolution_driver: "Judge Brinkema's structural-vs-conduct remedy ruling (US v. Google)",
    analysis_summary: "WATCH [beneficiary]. A DOJ structural remedy in US v. Google could force divestiture of Google's AdX exchange — handing the largest independent SSP a structural share gift. Two independent regulatory tracks point at the same tiny set of SSPs: the US DOJ remedy ruling (overdue, H1-26) and the EU structural decision. Bloom: G1 (court/DOJ vs Google) + G3 (the unpriced share-shift); G2 pending (the remedy ORDER isn't written yet — that's the hardening trigger). MGNI is the cleaner risk/reward; PUBM has already run. NOTE: MGNI + PUBM resolve on the SAME ruling — size as ONE position, not two.",
    bloom_catalysts: {
      catalyst_1: { title: "Liability Established", detected: true, description: "Court found Google liable on AdX+DFP tying (Apr-2025); remedy phase underway.", evidence: "Brinkema (EDVA) liability finding; closing arguments Nov 2025." },
      catalyst_2: { title: "Structural Remedy Order (trigger)", detected: false, description: "A written order specifying AdX divestiture + timeline flips this WATCH->ACTIVE.", evidence: "Ruling overdue vs the court's ~Mar-2026 target; H1-2026." },
      catalyst_3: { title: "EU Structural Track", detected: true, description: "EU Commission moving toward an ad-tech divestiture order (EUR2.95B fine already landed).", evidence: "EC decision AT.40670; structural remedies signaled by EVP Ribera." },
    },
    loeb_criteria: {
      catalyst_density: { rating: "High", analysis: "Two independent regulatory tracks (US + EU) converging on the same beneficiary." },
      sum_of_parts: { detected: false, analysis: "N/A — beneficiary thesis, not a break-up of MGNI." },
      activism_potential: { detected: true, analysis: "Government-forced structural remedy against the dominant competitor." },
      risk_reward: { ratio: "2.6:1", analysis: "Upside on a structural AdX sale + share shift; downside if the remedy is conduct-only." },
    },
    options_signals: NO_OPTIONS("Options chain exists but Greeks not pulled (no ThetaData run). Confirm liquidity before an options expression."),
    recent_events: [
      { date: "2025-11-21", type: "news", title: "Closing arguments conclude in US v. Google ad-tech remedy phase", link: "https://www.adexchanger.com/" },
      { date: "2026-01-16", type: "filing", title: "EU Commission publishes 363-page Google ad-tech decision; structural remedies loom", link: "https://ppc.land/" },
    ],
    cache_timestamp: STAMP,
  },

  HONA: {
    symbol: "HONA", company_name: "Honeywell Aerospace (Honeywell spin-off)", price: null, market_cap: 90000000000,
    catalyst_density_score: 6.8, adjusted_loeb_score: 6.8, final_adjusted_loeb: 6.8, upside_downside_ratio: 1.9,
    recommendation: "WATCH", catalyst_nature: "mechanical_execution", re_rate_status: "pending",
    tier: "ACTIVE", lane: "Spin-off", gate_status: "PASS", bloom_gates_passed: ["G2_concrete_commitment", "G3_unpriced_figure"],
    edge: "Med", verify_verdict: "CONFIRMED-w/-corrections (debt $24B->$16B)", instrument: "HON options now (deep); HONA post-distribution; SOTP pair",
    resolution_driver: "Which side is mis-levered (cash-flow cover); rating outcome",
    analysis_summary: "ACTIVE [verified, corrected]. Final leg of Honeywell's 3-way split: Aerospace (~$17.4B rev) spun on/around Jun 29, 2026. VERIFY-PASS CORRECTION: the '$24B gross debt' was garbled — real funded SpinCo debt is ~$16B notes ($10B new-money funds the dividend-up that de-levers RemainCo; ~$6B exchange refinances existing parent debt). The undrawn $4B revolver + $4B CP were triple-counted. The cleaner re-rate may be the de-levered RemainCo ('Honeywell Technologies'), not the SpinCo. Record date not yet declared -> Jun 29 could slip. Bloom: G2 (Form-10-filed, dated) + G3 (the mis-leverage/SoP read).",
    bloom_catalysts: {
      catalyst_1: { title: "Spin Dated", detected: true, description: "Aerospace distribution expected Jun 29, 2026 (record date pending board declaration).", evidence: "Honeywell Aerospace Investor Day PR; Form 10-12B/A on file." },
      catalyst_2: { title: "Leverage Placement", detected: true, description: "~$16B funded notes; ~$10B new-money dividends up to de-lever RemainCo.", evidence: "Cleary Gottlieb deal-counsel summary; $16B priced ~Mar 10 2026 (9 tranches)." },
      catalyst_3: { title: "SOTP Re-rate", detected: false, description: "Pure-play A&D SpinCo vs de-levered RemainCo; the mis-leverage read is underpriced.", evidence: "Pending first standalone prints." },
    },
    loeb_criteria: {
      catalyst_density: { rating: "Medium-High", analysis: "Hard dated spin; the value is in the which-side-mis-levered read, not the headline." },
      sum_of_parts: { detected: true, analysis: "Aerospace pure-play vs RemainCo Technologies; deliberate leverage skew creates a SOTP pair." },
      activism_potential: { detected: false, analysis: "N/A — structural separation." },
      risk_reward: { ratio: "1.9:1", analysis: "SOTP unlock if both re-rate; downside if HONA cash flow misses the load." },
    },
    options_signals: NO_OPTIONS("HON listed options are deep (express the pair via HON now); HONA options only post-distribution."),
    recent_events: [
      { date: "2026-06-03", type: "news", title: "Honeywell Aerospace to host inaugural Investor Day; Jun 29 spin, Nasdaq 'HONA'", link: "https://www.prnewswire.com/news-releases/302789411" },
      { date: "2026-03-10", type: "news", title: "Honeywell Aerospace prices $16B debt offering for the spin-off", link: "https://www.investing.com/" },
    ],
    cache_timestamp: STAMP,
  },

  PUBM: {
    symbol: "PUBM", company_name: "PubMatic, Inc. (Google AdX divestiture beneficiary)", price: 11.81, market_cap: 550000000,
    catalyst_density_score: 6.3, adjusted_loeb_score: 6.3, final_adjusted_loeb: 6.3, upside_downside_ratio: 2.4,
    recommendation: "WATCH", catalyst_nature: "pricing_dislocation", re_rate_status: "partial",
    tier: "WATCH", lane: "Forced Seller (beneficiary)", gate_status: "PASS", bloom_gates_passed: ["G1_named_counterparty", "G3_unpriced_figure"],
    edge: "Med", verify_verdict: "CONFIRMED-w/-caution (already run)", instrument: "PUBM equity / Dec-2026 calls (entry-sensitive)",
    resolution_driver: "Same Brinkema ruling as MGNI — ONE bet across both",
    analysis_summary: "WATCH [beneficiary, already run]. Same US AdX divestiture catalyst as MGNI, with the highest beta to a forced break-up of Google's exchange — but the stock has already run ($6.15->$11.81, near its 52-wk high), so it's partly priced and entry-sensitive. SIZE AS ONE with MGNI (same resolution driver). MGNI is the cleaner expression of the identical thesis.",
    bloom_catalysts: {
      catalyst_1: { title: "Liability Established", detected: true, description: "Same US v. Google remedy phase as MGNI.", evidence: "Brinkema liability finding 2025." },
      catalyst_2: { title: "Structural Remedy Order (trigger)", detected: false, description: "Written AdX divestiture order flips WATCH->ACTIVE.", evidence: "Ruling overdue, H1-2026." },
      catalyst_3: { title: "Run-up Risk", detected: true, description: "Already +37% over 200d toward the 52-wk high — much of the move may be done.", evidence: "FMP quote 2026-06-05." },
    },
    loeb_criteria: {
      catalyst_density: { rating: "High", analysis: "Same two-track regulatory convergence as MGNI." },
      sum_of_parts: { detected: false, analysis: "N/A — beneficiary thesis." },
      activism_potential: { detected: true, analysis: "Government-forced structural remedy." },
      risk_reward: { ratio: "2.4:1", analysis: "Torque if structural; but the run-up has compressed the entry edge." },
    },
    options_signals: NO_OPTIONS("Options chain exists; Greeks not pulled. Thinnest SSP — confirm liquidity."),
    recent_events: [
      { date: "2026-03-01", type: "filing", title: "PubMatic amended antitrust complaint vs Google", link: "https://pubmatic.com/" },
    ],
    cache_timestamp: STAMP,
  },

  SPCX: {
    symbol: "SPCX", company_name: "SpaceX (Nasdaq-100 fast-entry)", price: null, market_cap: 1770000000000,
    catalyst_density_score: 5.8, adjusted_loeb_score: 5.8, final_adjusted_loeb: 5.8, upside_downside_ratio: 1.7,
    recommendation: "WATCH", catalyst_nature: "mechanical_execution", re_rate_status: "pending",
    tier: "CONTINGENT", lane: "Index Flow", gate_status: "PASS (contingent)", bloom_gates_passed: ["G2_concrete_commitment"],
    edge: "Low-Med", verify_verdict: "CONFIRMED-w/-corrections (contingent on IPO pricing)", instrument: "SPCX long-gamma post-IPO; or relative-underperform top-NDX",
    resolution_driver: "The Jun 11/12 IPO actually pricing (single kill-risk)",
    analysis_summary: "CONTINGENT. SpaceX IPO Jun 12 -> Nasdaq-100 fast-entry ~Jul 6 (~$6.7B forced QQQ buy on a ~3% float = squeeze; every NDX member trimmed ~0.5%). S&P leg is confirmed OFF (S&P DJI rejected fast-entry Jun 4; $4.94B 2025 GAAP loss). SINGLE KILL-RISK: the IPO slipping past Jun 11/12 voids every leg — not yet priced, tape hostile. Magnitudes (~$6.7B, ~3% float) are soft analyst estimates that move with the unfixed float. Real asymmetry is the SPCX low-float squeeze, not the well-telegraphed QQQ dilution.",
    bloom_catalysts: {
      catalyst_1: { title: "Fast-Entry Rule Live", detected: true, description: "Nasdaq-100 fast-entry rule effective May 1 2026; SpaceX trivially clears the top-40 bar.", evidence: "Nasdaq methodology update; Ashurst/Lexology summaries." },
      catalyst_2: { title: "IPO Pricing (the gate)", detected: false, description: "Pricing set for Jun 11, debut Jun 12 — NOT yet priced. Everything downstream hinges on it.", evidence: "CNBC/Fortune Jun 3 2026: $135 fixed, 555.6M sh." },
      catalyst_3: { title: "Inclusion Buy / Squeeze", detected: false, description: "~$6.7B forced QQQ buy on a thin float ~Jul 6.", evidence: "Analyst-estimated; float-sensitive." },
    },
    loeb_criteria: {
      catalyst_density: { rating: "Medium", analysis: "Mechanical + dated, but the whole structure is contingent on an unpriced IPO." },
      sum_of_parts: { detected: false, analysis: "N/A." },
      activism_potential: { detected: false, analysis: "N/A — index mechanics." },
      risk_reward: { ratio: "1.7:1", analysis: "Squeeze upside vs IPO-slip / soft-float downside." },
    },
    options_signals: NO_OPTIONS("SPCX not yet trading; no options. Contingent on the IPO pricing."),
    recent_events: [
      { date: "2026-06-04", type: "news", title: "S&P Dow Jones keeps megacap IPO rules — SpaceX S&P fast-entry rejected", link: "https://www.cnbc.com/2026/06/05/" },
      { date: "2026-06-03", type: "news", title: "SpaceX IPO roadshow: $135 fixed, 555.6M shares, ~$1.77T", link: "https://www.cnbc.com/2026/06/03/" },
    ],
    cache_timestamp: STAMP,
  },

  VERI: {
    symbol: "VERI", company_name: "Veritone, Inc.", price: 2.10, market_cap: 88000000,
    catalyst_density_score: 5.1, adjusted_loeb_score: 5.1, final_adjusted_loeb: 5.1, upside_downside_ratio: 2.2,
    recommendation: "WATCH", catalyst_nature: "pricing_dislocation", re_rate_status: "pending",
    tier: "WATCH", lane: "Distressed", gate_status: "PASS", bloom_gates_passed: ["G3_unpriced_figure"],
    edge: "High", verify_verdict: "UNVERIFIED — pending adversarial pass", instrument: "Own the 2026 CONVERTS (equity is short/avoid — dilution base case)",
    resolution_driver: "Whether mgmt signs an exchange before Nov-15 vs equitizes",
    analysis_summary: "WATCH [distressed]. $45.6M 1.75% converts due Nov-15-2026 vs $15.1M cash + a $45.8M working-cap deficit; going-concern; refi only 'in discussions,' nothing signed. The instrument is the CONVERTS (par-vs-recovery), not the equity — dilutive equitization is the base case. Bloom: G3 (cash << face, the unpriced gap); G1/G2 pending (no signed deal — that's why it's WATCH). Hardens on a signed exchange/RSA, a dilutive raise, or a missed/PIK'd coupon. NOTE: not yet through the adversarial-verify pass.",
    bloom_catalysts: {
      catalyst_1: { title: "Convert Maturity Wall", detected: true, description: "$45.6M converts mature Nov-15-2026; cannot cash-settle.", evidence: "Veritone 10-Q (3/31/26), filed May 14 2026." },
      catalyst_2: { title: "Exchange / Equitization (trigger)", detected: false, description: "A signed exchange or RSA hardens this; equitization dilutes the common.", evidence: "Refi 'in discussions,' nothing signed." },
      catalyst_3: { title: "Going-Concern Clock", detected: true, description: "Liquidity runs to ~late-2026.", evidence: "10-Q going-concern language." },
    },
    loeb_criteria: {
      catalyst_density: { rating: "Medium", analysis: "One hard dated forcing event (Nov-15) but no signed path yet." },
      sum_of_parts: { detected: false, analysis: "N/A." },
      activism_potential: { detected: false, analysis: "N/A — credit/restructuring." },
      risk_reward: { ratio: "2.2:1", analysis: "Converts par-ish on a deal; equity heavily diluted in the base case, ~0 in Ch11." },
    },
    options_signals: NO_OPTIONS("Micro-cap; the play is the converts, not listed equity options."),
    recent_events: [
      { date: "2026-05-14", type: "filing", title: "Veritone 10-Q (3/31/26): going-concern; $45.6M converts due Nov-15-2026", link: "https://www.sec.gov/Archives/edgar/data/0001615165/000162828026035074/veri-20260331.htm" },
    ],
    cache_timestamp: STAMP,
  },

  AHT: {
    symbol: "AHT", company_name: "Ashford Hospitality Trust", price: 5.00, market_cap: 25000000,
    catalyst_density_score: 4.6, adjusted_loeb_score: 4.6, final_adjusted_loeb: 4.6, upside_downside_ratio: 2.5,
    recommendation: "WATCH", catalyst_nature: "pricing_dislocation", re_rate_status: "pending",
    tier: "WATCH", lane: "Distressed", gate_status: "PASS", bloom_gates_passed: ["G3_unpriced_figure"],
    edge: "Med", verify_verdict: "UNVERIFIED — pending adversarial pass", instrument: "Own the SUSPENDED PREFERRED (arrears optionality); avoid common",
    resolution_driver: "Resolution of the Jul-9 Highland maturity (refi/extend vs surrender keys)",
    analysis_summary: "WATCH [distressed]. $1.9B non-recourse maturing within 12 months; going-concern; Highland loan ($723.6M, 18 hotels) FINAL maturity Jul-9-2026; preferred dividends suspended (accruing) since Jan-2026. The instrument is the SUSPENDED PREFERRED (Series D-M; accruing arrears = the asymmetric payoff if a deal pays them) — the common is a ~$20M lottery stub. Bloom: G3 (preferred arrears, unpriced). Hardens on a Highland default/hand-back, a strategic-transaction announcement, or further preferred deferral. NOTE: not yet adversarially verified.",
    bloom_catalysts: {
      catalyst_1: { title: "Highland Final Maturity", detected: true, description: "$723.6M (18 hotels) final maturity Jul-9-2026, no further extensions disclosed.", evidence: "AHT 8-K Jan-13-2026; 10-Q (3/31/26) filed May 14 2026." },
      catalyst_2: { title: "Preferred Arrears", detected: true, description: "Series D-M suspended since Jan-2026 and accruing — paid in a strategic transaction.", evidence: "10-Q (3/31/26)." },
      catalyst_3: { title: "Strategic Transaction (trigger)", detected: false, description: "A sale/strategic deal that pays preferred arrears re-rates the pref hard.", evidence: "Pending." },
    },
    loeb_criteria: {
      catalyst_density: { rating: "Medium", analysis: "Hard date (Jul-9) but deeply levered; outcome distribution wide." },
      sum_of_parts: { detected: true, analysis: "Hotel-level non-recourse structure; asset-by-asset hand-back vs sale optionality." },
      activism_potential: { detected: false, analysis: "N/A." },
      risk_reward: { ratio: "2.5:1", analysis: "Preferred re-rates if arrears paid; impaired if cascading hand-backs." },
    },
    options_signals: NO_OPTIONS("The instrument is the preferred, not the common/options."),
    recent_events: [
      { date: "2026-05-14", type: "filing", title: "AHT 10-Q (3/31/26): going-concern; $1.9B maturing within 12 months", link: "https://www.sec.gov/Archives/edgar/data/0001232582/" },
    ],
    cache_timestamp: STAMP,
  },

  SNBR: {
    symbol: "SNBR", company_name: "Sleep Number Corp", price: 0.58, market_cap: 13000000,
    catalyst_density_score: 4.5, adjusted_loeb_score: 4.5, final_adjusted_loeb: 4.5, upside_downside_ratio: 3.0,
    recommendation: "WATCH", catalyst_nature: "pricing_dislocation", re_rate_status: "pending",
    tier: "WATCH", lane: "Distressed", gate_status: "PASS", bloom_gates_passed: ["G3_unpriced_figure"],
    edge: "High (extreme-risk)", verify_verdict: "UNVERIFIED — move live today, deal NOT confirmed", instrument: "Equity is a dated coin-flip option only; debt is the value",
    resolution_driver: "Whether a sale 'in full to lenders' closes by Jun-30/Jul-1",
    analysis_summary: "WATCH [distressed, live today]. Forbearance + $25M bridge term loan maturing Jun-30-2026; $30M min-liquidity covenant waived only until ~Jul-1; lender-mandated milestones to consummate a sale 'in full' (Guggenheim engaged). Stock +66% on 228M shares TODAY (Jun 5) — the market is pricing a sale/recap at the deadline, but NO signed deal is confirmed (no 8-K found). Equity is a 3-week binary coin-flip ($13M cap); the revolver/term debt is the value instrument. Extreme risk; NOT a core line. NOTE: unverified — the move is real, the deal is not confirmed.",
    bloom_catalysts: {
      catalyst_1: { title: "Bridge Maturity Wall", detected: true, description: "$25M bridge matures Jun-30-2026; covenant snaps back ~Jul-1.", evidence: "Sleep Number 8-K amendment, Apr-28-2026." },
      catalyst_2: { title: "Sale Mandate (trigger)", detected: false, description: "Lender-mandated sale 'in full'; no signed deal yet.", evidence: "8-K milestones; Guggenheim engaged." },
      catalyst_3: { title: "Market Pricing a Deal", detected: true, description: "+66% on 228M shares today vs no confirming 8-K.", evidence: "FMP tape 2026-06-05 (verify before acting)." },
    },
    loeb_criteria: {
      catalyst_density: { rating: "Medium", analysis: "Imminent hard wall (Jun-30/Jul-1) with a sale mandate attached." },
      sum_of_parts: { detected: false, analysis: "N/A." },
      activism_potential: { detected: false, analysis: "N/A — lender-led." },
      risk_reward: { ratio: "3.0:1", analysis: "Equity-positive sale multiples the stub; lender recap or Ch11 wipes it. Binary." },
    },
    options_signals: NO_OPTIONS("Micro-cap binary; treat equity as a dated option only."),
    recent_events: [
      { date: "2026-04-28", type: "filing", title: "Sleep Number 8-K: forbearance + $25M bridge (Jun-30 maturity), sale mandate", link: "https://www.sec.gov/Archives/edgar/data/0000827187/" },
    ],
    cache_timestamp: STAMP,
  },

  GPC: {
    symbol: "GPC", company_name: "Genuine Parts Company", price: 98.00, market_cap: 13700000000,
    catalyst_density_score: 4.5, adjusted_loeb_score: 4.5, final_adjusted_loeb: 4.5, upside_downside_ratio: 1.7,
    recommendation: "WATCH", catalyst_nature: "mechanical_execution", re_rate_status: "pending",
    tier: "WATCH", lane: "Spin-off (soft)", gate_status: "FAIL-for-now", bloom_gates_passed: ["G2_partial"],
    edge: "Med", verify_verdict: "wave-1 WATCH", instrument: "Equity; the post-announce selloff is the tell",
    resolution_driver: "Form 10 filing + which side gets the premium multiple",
    analysis_summary: "WATCH [soft spin]. GPC to split into Automotive (NAPA) and Industrial (Motion); stock sold off hard (~$98 vs $151 52-wk high) post-announcement. NO Form 10 filed yet -> not ACTIVE. The selloff itself is the tell, but there's no dated forced-flow catalyst until the filing. Hardens on a Form 10 + 2H-2026 investor day with terms; completion targeted Q1-2027. Likely Motion (industrial) is the higher-quality orphan.",
    bloom_catalysts: {
      catalyst_1: { title: "Separation Announced", detected: true, description: "Plan to split NAPA (auto) from Motion (industrial).", evidence: "GPC PR Feb-17-2026." },
      catalyst_2: { title: "Form 10 (trigger)", detected: false, description: "No filing/date yet -> WATCH until the Form 10 + investor day.", evidence: "Investor days 2H-2026; completion Q1-2027." },
      catalyst_3: { title: "Re-rate", detected: false, description: "Higher-multiple side (likely Motion) re-rates post-separation.", evidence: "Pending." },
    },
    loeb_criteria: {
      catalyst_density: { rating: "Low-Medium", analysis: "Real separation but soft timing; no dated forced flow yet." },
      sum_of_parts: { detected: true, analysis: "Auto vs Industrial; the post-announce selloff may be mispricing the cleaner industrial side." },
      activism_potential: { detected: false, analysis: "N/A." },
      risk_reward: { ratio: "1.7:1", analysis: "SOTP unlock vs the dead-money risk of a 2027 completion." },
    },
    options_signals: NO_OPTIONS("Optionable large-cap; Greeks not pulled."),
    recent_events: [
      { date: "2026-02-17", type: "news", title: "Genuine Parts plans to separate Automotive and Industrial", link: "https://www.genpt.com/2026-02-17" },
    ],
    cache_timestamp: STAMP,
  },

  JNJ: {
    symbol: "JNJ", company_name: "Johnson & Johnson (DePuy ortho separation)", price: 165.00, market_cap: 400000000000,
    catalyst_density_score: 4.2, adjusted_loeb_score: 4.2, final_adjusted_loeb: 4.2, upside_downside_ratio: 1.5,
    recommendation: "WATCH", catalyst_nature: "mechanical_execution", re_rate_status: "pending",
    tier: "WATCH", lane: "Spin-off (soft)", gate_status: "FAIL-for-now", bloom_gates_passed: ["G2_partial"],
    edge: "Low", verify_verdict: "wave-1 WATCH", instrument: "Equity (far-dated)",
    resolution_driver: "Form 10 + structure (spin vs IPO/sale)",
    analysis_summary: "WATCH [soft spin, far-dated]. J&J to separate its ~$9.2B-sales orthopaedics business (DePuy Synthes). Announced Oct-14-2025; 18-24 month window (-> 2027). No Form 10, no forced-flow event yet -> low score until it hardens. Mega-cap, well-covered = thin edge.",
    bloom_catalysts: {
      catalyst_1: { title: "Intent Announced", detected: true, description: "Intent to separate orthopaedics as standalone DePuy Synthes.", evidence: "J&J PR Oct-14-2025." },
      catalyst_2: { title: "Form 10 + Structure (trigger)", detected: false, description: "Spin vs partial-IPO/sale undecided; no filing.", evidence: "18-24 month window." },
      catalyst_3: { title: "Re-rate", detected: false, description: "Standalone ortho multiple.", evidence: "Pending 2027." },
    },
    loeb_criteria: {
      catalyst_density: { rating: "Low", analysis: "Far-dated, no filing, no forced flow." },
      sum_of_parts: { detected: true, analysis: "Ortho carve-out from the med-tech/pharma conglomerate." },
      activism_potential: { detected: false, analysis: "N/A." },
      risk_reward: { ratio: "1.5:1", analysis: "Modest; long-dated optionality." },
    },
    options_signals: NO_OPTIONS("Optionable mega-cap; Greeks not pulled. Far-dated."),
    recent_events: [
      { date: "2025-10-14", type: "news", title: "J&J announces intent to separate its orthopaedics business", link: "https://www.jnj.com/media-center/press-releases" },
    ],
    cache_timestamp: STAMP,
  },

  ETN: {
    symbol: "ETN", company_name: "Eaton Corp (Mobility Group spin)", price: 290.00, market_cap: 115000000000,
    catalyst_density_score: 4.2, adjusted_loeb_score: 4.2, final_adjusted_loeb: 4.2, upside_downside_ratio: 1.5,
    recommendation: "WATCH", catalyst_nature: "mechanical_execution", re_rate_status: "pending",
    tier: "WATCH", lane: "Spin-off (soft)", gate_status: "FAIL-for-now", bloom_gates_passed: ["G2_partial"],
    edge: "Low-Med", verify_verdict: "wave-1 WATCH", instrument: "Equity (far-dated)",
    resolution_driver: "Form 10 + record date",
    analysis_summary: "WATCH [soft spin, far-dated]. Eaton to spin Vehicle + eMobility (~$3B sales, ~13% margin) into a standalone. Announced Jan-26-2026; targeted end-Q1-2027; Form 10 NOT yet filed. The SpinCo will be the orphan once filed. Low score until it hardens.",
    bloom_catalysts: {
      catalyst_1: { title: "Spin Planned", detected: true, description: "Vehicle + eMobility spin announced.", evidence: "Eaton PR Jan-26-2026." },
      catalyst_2: { title: "Form 10 (trigger)", detected: false, description: "No filing/date.", evidence: "Targeted end-Q1-2027." },
      catalyst_3: { title: "Orphan Re-rate", detected: false, description: "SpinCo dislocation once filed.", evidence: "Pending." },
    },
    loeb_criteria: {
      catalyst_density: { rating: "Low", analysis: "Far-dated, no Form 10." },
      sum_of_parts: { detected: true, analysis: "Vehicle/eMobility carve-out from the electrical pure-play." },
      activism_potential: { detected: false, analysis: "N/A." },
      risk_reward: { ratio: "1.5:1", analysis: "Modest; long-dated." },
    },
    options_signals: NO_OPTIONS("Optionable large-cap; Greeks not pulled. Far-dated."),
    recent_events: [
      { date: "2026-01-26", type: "news", title: "Eaton plans to spin off its Mobility Group", link: "https://www.eaton.com/us/en-us/company/news-insights/news-releases/2026" },
    ],
    cache_timestamp: STAMP,
  },

  GOCO: {
    symbol: "GOCO", company_name: "GoHealth, Inc.", price: 0.90, market_cap: 21000000,
    catalyst_density_score: 4.0, adjusted_loeb_score: 4.0, final_adjusted_loeb: 4.0, upside_downside_ratio: 2.0,
    recommendation: "WATCH", catalyst_nature: "pricing_dislocation", re_rate_status: "pending",
    tier: "WATCH", lane: "Distressed", gate_status: "PASS", bloom_gates_passed: ["G3_unpriced_figure"],
    edge: "Med", verify_verdict: "UNVERIFIED — pending adversarial pass", instrument: "Equity is a binary option; the 2029 super-priority term loan is cleaner",
    resolution_driver: "Whether the Sept-2026 covenant step is met without a dilutive raise",
    analysis_summary: "WATCH [distressed]. Mgmt projects a probable breach of an escalating minimum-liquidity covenant within 12 months; $39.9M cash vs $701.8M term loans; covenant steps to $30M by Sept-2026. In compliance NOW (breach projected, not fired). The play is the term loan or a tiny defined-risk equity option. Bloom: G3 (the covenant gap). Hardens on a missed weekly covenant, a new super-priority tranche, or a going-concern amendment. NOTE: not yet adversarially verified.",
    bloom_catalysts: {
      catalyst_1: { title: "Escalating Liquidity Covenant", detected: true, description: "Weekly min-liquidity covenant rises to $30M in Sept-2026.", evidence: "GoHealth 10-Q (3/31/26)." },
      catalyst_2: { title: "Covenant Step (trigger)", detected: false, description: "The Sept-2026 step is the dated forcing event.", evidence: "10-Q." },
      catalyst_3: { title: "Refi / Amend", detected: false, description: "New money on soft terms vs dilutive amend.", evidence: "Already amended once (Aug-2025)." },
    },
    loeb_criteria: {
      catalyst_density: { rating: "Low-Medium", analysis: "Dated covenant step but in compliance now; market knows the story." },
      sum_of_parts: { detected: false, analysis: "N/A." },
      activism_potential: { detected: false, analysis: "N/A." },
      risk_reward: { ratio: "2.0:1", analysis: "Bounce on stabilization; ~0 on a covenant trip." },
    },
    options_signals: NO_OPTIONS("Micro-cap; the cleaner instrument is the term loan."),
    recent_events: [
      { date: "2026-05-15", type: "filing", title: "GoHealth 10-Q (3/31/26): projected liquidity-covenant breach within 12 months", link: "https://www.sec.gov/Archives/edgar/data/0001808220/" },
    ],
    cache_timestamp: STAMP,
  },

  TXT: {
    symbol: "TXT", company_name: "Textron Inc. (Industrial separation)", price: 80.00, market_cap: 14500000000,
    catalyst_density_score: 3.8, adjusted_loeb_score: 3.8, final_adjusted_loeb: 3.8, upside_downside_ratio: 1.4,
    recommendation: "WATCH", catalyst_nature: "mechanical_execution", re_rate_status: "pending",
    tier: "WATCH", lane: "Spin-off (soft)", gate_status: "FAIL (path undecided)", bloom_gates_passed: [],
    edge: "Low", verify_verdict: "wave-1 WATCH", instrument: "Equity (path undecided)",
    resolution_driver: "Board commits spin vs sale, then Form 10",
    analysis_summary: "WATCH [soft, undecided]. Textron to separate its Industrial segment (Kautex + Specialized Vehicles), leaving a pure-play A&D. Announced Apr-30-2026; path explicitly UNDECIDED (sale OR tax-free spin); 12-18 month target. No spin mechanism in motion -> lowest score on the board. Revisit only if a spin (not a sale) is chosen.",
    bloom_catalysts: {
      catalyst_1: { title: "Separation Announced", detected: true, description: "Industrial segment to be separated.", evidence: "Textron 8-K/PR Apr-30-2026." },
      catalyst_2: { title: "Structure Decision (trigger)", detected: false, description: "Sale vs spin undecided.", evidence: "12-18 month target." },
      catalyst_3: { title: "Re-rate", detected: false, description: "Pure-play A&D RemainCo if a spin.", evidence: "Pending." },
    },
    loeb_criteria: {
      catalyst_density: { rating: "Low", analysis: "Path undecided; no concrete spin commitment." },
      sum_of_parts: { detected: true, analysis: "Industrial vs A&D; but a sale would resolve it differently." },
      activism_potential: { detected: false, analysis: "N/A." },
      risk_reward: { ratio: "1.4:1", analysis: "Weak until the structure is committed." },
    },
    options_signals: NO_OPTIONS("Optionable; Greeks not pulled. Path undecided."),
    recent_events: [
      { date: "2026-04-30", type: "filing", title: "Textron to separate its Industrial segment (spin or sale undecided)", link: "https://www.sec.gov/Archives/edgar/data/0000217346/" },
    ],
    cache_timestamp: STAMP,
  },

  QVC: {
    symbol: "QVC", company_name: "Reorganized QVC, Inc. (post-reorg equity)", price: null, market_cap: null,
    catalyst_density_score: 7.3, adjusted_loeb_score: 7.3, final_adjusted_loeb: 7.3, upside_downside_ratio: 2.5,
    recommendation: "WATCH", catalyst_nature: "mechanical_execution", re_rate_status: "pending",
    tier: "ACTIVE", lane: "Distressed (in-court)", gate_status: "PASS", bloom_gates_passed: ["G1_named_counterparty", "G2_concrete_commitment", "G3_unpriced_figure"],
    edge: "High", verify_verdict: "CONFIRMED-w/-corrections (contested; very short shelf life)", instrument: "NEW post-reorg equity (when-issued / first listing — not yet tradeable); takeback debt for seniority",
    resolution_driver: "Plan confirmation + the pursued NYSE/Nasdaq listing of new equity",
    analysis_summary: "ACTIVE [verified, in-court]. QVC prepack: the fulcrum (sr secured notes + revolver) equitizes >$5B funded debt into ~100% of new equity + $1.275B takeback debt; debt cut $6.6B->$1.3B; old QVCGA/QVCC WIPED. THE RARITY: the plan commits to PURSUE an NYSE/Nasdaq listing of the new equity (OTCID fallback) — the one buyable public instrument in a lane where everything else goes private. 3 Bloom gates. CAVEATS (verify): confirmation hearing is IN-FLIGHT (Jun 4-9) and CONTESTED — preferred holders (Cygnus/Sona) filed an 862-page objection + a competing-plan push; emergence ~June (could slip to mid-July); new equity NOT yet tradeable (when-issued pending). VERY SHORT SHELF LIFE — if confirmation is entered this week and it emerges, the catalyst FIRES. Re-check daily.",
    bloom_catalysts: {
      catalyst_1: { title: "Prepack Filed + RSA", detected: true, description: "Fulcrum noteholders signed the RSA; prepack plan filed; debt $6.6B->$1.3B.", evidence: "QVC PR Apr 16 2026; Kroll docket; ad hoc sr secured noteholder group RSA." },
      catalyst_2: { title: "Confirmation In-Flight (CONTESTED)", detected: true, description: "Combined disclosure/confirmation hearing Jun 4-9 2026; preferred objection live.", evidence: "Judge Perez, S.D. Tex.; Cygnus/Sona 862-page objection (petition11 Jun 3)." },
      catalyst_3: { title: "Listed Post-Reorg Equity (trigger)", detected: false, description: "Plan to pursue NYSE/Nasdaq listing of new equity; when-issued is the entry.", evidence: "Plan/DS language verbatim (ppc.land/Debtwire Apr 26); OTCID fallback." },
    },
    loeb_criteria: {
      catalyst_density: { rating: "High", analysis: "Hardened prepack (RSA + filed plan + dated confirmation) with a quantified de-lever and a rare listed post-reorg equity." },
      sum_of_parts: { detected: true, analysis: "Fulcrum takes ~100% of new equity at the de-levered $1.3B cap structure; retail/streaming-commerce turnaround optionality." },
      activism_potential: { detected: true, analysis: "Preferred holders (Cygnus/Sona) contesting the plan / pushing a competing plan — confirmation risk." },
      risk_reward: { ratio: "2.5:1", analysis: "New equity re-rates on de-levered FCF vs confirmation slip / retail erosion. Old common = 0 (wiped)." },
    },
    options_signals: NO_OPTIONS("Post-reorg equity not yet listed; no options. Entry is when-issued / first listing."),
    recent_events: [
      { date: "2026-06-03", type: "news", title: "QVC confirmation contested — preferred holders file 862-page objection + competing plan", link: "https://www.petition11.com/p/qvc-c-for-confirmation" },
      { date: "2026-04-16", type: "filing", title: "QVC files prepack Ch11; $6.6B->$1.3B debt cut; plan to pursue NYSE/Nasdaq listing of new equity", link: "https://restructuring.ra.kroll.com/QVC/" },
    ],
    cache_timestamp: STAMP,
  },

  NFE: {
    symbol: "NFE", company_name: "New Fortress Energy (UK Restructuring Plan + Ch15)", price: null, market_cap: null,
    catalyst_density_score: 6.5, adjusted_loeb_score: 6.5, final_adjusted_loeb: 6.5, upside_downside_ratio: 1.6,
    recommendation: "WATCH", catalyst_nature: "mechanical_execution", re_rate_status: "pending",
    tier: "ACTIVE", lane: "Distressed (LME)", gate_status: "PASS", bloom_gates_passed: ["G1_named_counterparty", "G2_concrete_commitment", "G3_unpriced_figure"],
    edge: "Med", verify_verdict: "CONFIRMED-w/-corrections (vote Jun 17 / UK sanction Jun 18 / Ch15 Jun 23; dilution is as-converted)", instrument: "PUBLIC NFE common = DILUTION SHORT / avoid; the long edge is the PRIVATE creditor package (new equity / conv pref)",
    resolution_driver: "UK High Court sanction + Ch15 recognition (process, not macro)",
    analysis_summary: "ACTIVE [LME, VERIFIED]. Signed RSA (97%+ of $5.8B debt; terms confirmed verbatim in the DEFR14A): $5.8B -> ~$571M new term loans + $2.46B convertible preferred + creditors take 65% of pro-forma common. Sequence: voting deadline Jun 9 -> plan meetings Jun 15 -> stockholder vote Jun 17 -> UK High Court sanction Jun 18 -> US Ch15 recognition Jun 23; outside date Sept 15. 3 Bloom gates, hardened. KEY: the public NFE common is the WRONG side -- ~87% dilution AS-CONVERTED (existing holders 35% at close -> ~13% fully-diluted after the conv-pref converts + 10% MIP); the long edge is the PRIVATE creditor package, NOT addressable on a long-equity board. Boarded for the catalyst + the short read.",
    bloom_catalysts: {
      catalyst_1: { title: "Signed RSA (97%)", detected: true, description: "Supporting creditors >97% of $5.8B; definitive equitization terms.", evidence: "NFE PRE-14A proxy; RSA support 97% as of Apr 30 2026." },
      catalyst_2: { title: "Vote + Court Sanction (trigger)", detected: true, description: "Stockholder vote Jun 17; UK sanction Jun 18; US Ch15 recognition Jun 23.", evidence: "DEFR14A (May 27 2026); meeting Jun 17 2026." },
      catalyst_3: { title: "Common Dilution", detected: true, description: "Creditors take 65% of common; old holders ~85-90% diluted -> short/avoid.", evidence: "RSA terms: 65% equity to creditors, $2.46B pref, $571M debt." },
    },
    loeb_criteria: {
      catalyst_density: { rating: "Medium-High", analysis: "One of 2026's largest LMEs, hardened and dated — but the public instrument is the wrong side." },
      sum_of_parts: { detected: false, analysis: "N/A." },
      activism_potential: { detected: true, analysis: "Creditor-led restructuring; the creditor package is the value." },
      risk_reward: { ratio: "1.6:1", analysis: "Long the creditor package (private) vs short the diluted common; execution/regulatory (FLNG) risk." },
    },
    options_signals: NO_OPTIONS("NFE common is optionable but the catalyst plays through the private creditor package; public common = dilution short."),
    recent_events: [
      { date: "2026-04-30", type: "filing", title: "NFE RSA support reaches 97% of $5.8B debt; UK Restructuring Plan + Ch15", link: "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=NFE" },
    ],
    cache_timestamp: STAMP,
  },

  SAKS: {
    symbol: "SAKS", company_name: "Saks Global Enterprises (Ch11, private)", price: null, market_cap: null,
    catalyst_density_score: 6.3, adjusted_loeb_score: 6.3, final_adjusted_loeb: 6.3, upside_downside_ratio: 1.7,
    recommendation: "WATCH", catalyst_nature: "mechanical_execution", re_rate_status: "pending",
    tier: "ACTIVE", lane: "Distressed (in-court)", gate_status: "PASS", bloom_gates_passed: ["G1_named_counterparty", "G2_concrete_commitment", "G3_unpriced_figure"],
    edge: "Med", verify_verdict: "CONFIRMED-w/-corrections (Baker objection narrow; 'equity private' high-likelihood but unverified)", instrument: "Second-out ($1,439M) / third-out ($441M) 11% 2029 notes (fulcrum BONDS); equity stays PRIVATE — no public-equity expression",
    resolution_driver: "Recovery/coverage on the post-reorg cap structure (luxury-retail GMV execution)",
    analysis_summary: "ACTIVE [in-court, bonds-only]. VERIFIED forward (not yet confirmed/emerged as of Jun 5). Confirmation hearing Jun 5 (today, Judge Perez); emergence ~Jun 22. $1.75B committed capital + $500M court-approved exit financing (note: post-emergence exit DEBT ~$1.2B is a separate layer). THE INSTRUMENT IS BONDS: the 2nd-out ($1,439M) / 3rd-out ($441M) 11% 2029 notes — equity stays PRIVATE (high-likelihood but not explicitly confirmed by a primary doc), so NO public-equity expression. Confirmation risk = a Richard Baker objection, but it is NARROW (a D&O-indemnification / third-party-release fight, not a plan-value challenge). No fresh June bond mark available. Re-poll the docket before relying on 'forward'.",
    bloom_catalysts: {
      catalyst_1: { title: "DS Approved + RSA", detected: true, description: "Disclosure statement approved May 1; RSA + UCC deal; $500M exit financing committed.", evidence: "Saks PR May 1 2026; Stretto docket." },
      catalyst_2: { title: "Confirmation Today (trigger)", detected: true, description: "Confirmation hearing Jun 5 2026 (Judge Perez); emergence ~Jun 22.", evidence: "Stretto docket; DS approval PR." },
      catalyst_3: { title: "Fulcrum Notes", detected: true, description: "Second-out/third-out 2029 notes are the addressable security; equity private.", evidence: "$1.44B 2nd-out + $441M 3rd-out 2029 notes (Aug-2025 exchange)." },
    },
    loeb_criteria: {
      catalyst_density: { rating: "Medium-High", analysis: "Hardened, dated (confirming today) — but bonds-only, no public equity." },
      sum_of_parts: { detected: false, analysis: "N/A." },
      activism_potential: { detected: false, analysis: "N/A — creditor-led." },
      risk_reward: { ratio: "1.7:1", analysis: "2029 notes pull to par on clean emergence vs turnaround miss (S&P negative)." },
    },
    options_signals: NO_OPTIONS("Private equity; the play is the second-out 2029 notes (bond market), not listed equity."),
    recent_events: [
      { date: "2026-05-01", type: "filing", title: "Saks Global disclosure statement approved; advancing to confirmation + emergence", link: "https://www.prnewswire.com/news-releases/302760555.html" },
    ],
    cache_timestamp: STAMP,
  },

  SATS: {
    symbol: "SATS", company_name: "EchoStar Corp (DISH DBS grace clock)", price: null, market_cap: null,
    catalyst_density_score: 4.5, adjusted_loeb_score: 4.5, final_adjusted_loeb: 4.5, upside_downside_ratio: 1.5,
    recommendation: "WATCH", catalyst_nature: "pricing_dislocation", re_rate_status: "pending",
    tier: "WATCH", lane: "Distressed (LME)", gate_status: "PASS (weak)", bloom_gates_passed: ["G1_named_counterparty", "G2_concrete_commitment", "G3_unpriced_figure"],
    edge: "Low", verify_verdict: "CONFIRMED-w/-corrections -> DOWNGRADED (can-kick)", instrument: "DISH DBS notes (grace-clock); SATS common is CONTAMINATED by an unrelated SpaceX-IPO narrative (+543%/12mo) -> not a clean read",
    resolution_driver: "AT&T spectrum close (net $20.25B / gross ~$23B) — but cure likely from balance-sheet cash",
    analysis_summary: "WATCH [LME, downgraded by verify]. EchoStar skipped ~$183M DISH DBS coupon Jun 1, 30-day grace -> ~Jul 1 EoD. VERIFY DOWNGRADE: this is a PERPETUAL CAN-KICK, not a clean binary — EchoStar ran the identical skip-then-cure twice in 2025; base-rate outcome = quiet cure within grace (a non-event), likely funded from balance-sheet cash (decoupled from the AT&T close). The AT&T figure is NET $20.25B (gross ~$23B). The SATS common is contaminated by an unrelated SpaceX-IPO-backdoor narrative (+543%/12mo) -> NOT a clean read on the grace clock. Real event, weak edge — scored low.",
    bloom_catalysts: {
      catalyst_1: { title: "Skipped Coupon + Grace", detected: true, description: "Skipped ~$183M DISH DBS coupon Jun 1; 30-day grace to ~Jul 1.", evidence: "EchoStar 8-K Jun 1 2026 (3 DBS tranches: $72.2M/$71.9M/$38.4M)." },
      catalyst_2: { title: "Can-Kick Base Rate", detected: true, description: "Identical 2025 skip-then-cure (cured within grace twice) -> likely a non-event.", evidence: "SDxCentral Jun 5 2026; 2025 precedent (cured Jun 27 / Jul 30 2025)." },
      catalyst_3: { title: "AT&T Cure (decoupled)", detected: false, description: "AT&T net $20.25B pending (FCC+DOJ approved); but cure likely from cash, not the deal close.", evidence: "10-Q ~$22.65B gross; AT&T H1-2026." },
    },
    loeb_criteria: {
      catalyst_density: { rating: "Low", analysis: "Dated grace clock but the base-rate outcome is a quiet cure (non-event); a can-kick, not a binary." },
      sum_of_parts: { detected: false, analysis: "N/A." },
      activism_potential: { detected: false, analysis: "N/A." },
      risk_reward: { ratio: "1.5:1", analysis: "DBS notes snap to par-recovery only on a real default/cure event; SATS equity contaminated by the SpaceX narrative." },
    },
    options_signals: NO_OPTIONS("SATS optionable but contaminated by the SpaceX-backdoor narrative; the catalyst is in the DBS notes."),
    recent_events: [
      { date: "2026-06-05", type: "news", title: "EchoStar still in 30-day grace on DISH DBS coupon (echoes the 2025 skip-then-cure)", link: "https://www.sdxcentral.com/" },
      { date: "2026-06-01", type: "filing", title: "EchoStar 8-K: skipped ~$183M DISH DBS interest, 30-day grace -> ~Jul 1", link: "https://www.sec.gov/Archives/edgar/data/0001415404/000141540426000020/sats-20260601x8k.htm" },
    ],
    cache_timestamp: STAMP,
  },

  TPTA: {
    symbol: "TPTA", company_name: "Terra Property Trust 6.00% Notes 2026 (NYSE baby bond)", price: 20.09, market_cap: null,
    catalyst_density_score: 6.0, adjusted_loeb_score: 6.0, final_adjusted_loeb: 6.0, upside_downside_ratio: 1.8,
    recommendation: "WATCH", catalyst_nature: "pricing_dislocation", re_rate_status: "pending",
    tier: "ACTIVE", lane: "Distressed (LME)", gate_status: "PASS", bloom_gates_passed: ["G2_concrete_commitment", "G3_unpriced_figure"],
    edge: "Med", verify_verdict: "CONFIRMED-w/-corrections (going-concern PASS; 5-day shelf life)", instrument: "The NYSE-listed TPTA baby bond directly (the cleanest public distressed instrument on the board)",
    resolution_driver: "Refinance-or-haircut at the hard Jun-30 maturity wall (idiosyncratic)",
    analysis_summary: "ACTIVE [LME, cleanest public instrument]. Going-concern CRE-debt REIT (10-Q: $5M cash vs ~$69.6M debt due, substantial doubt) swaps its Jun-30-2026 maturity wall: 6.00% notes -> 8.00% secured notes due Dec-31-2028 at a ~20% haircut ($20 new + $5 cash per $25). Registered exchange, expiry extended to Jun 10. ~$56.4M stack. The instrument is the NYSE-listed TPTA baby bond itself — directly tradeable, the cleanest public distressed line on the board. 2 Bloom gates (G1 unmet — no formed ad-hoc group). CAVEATS (verify): 5-DAY SHELF LIFE (Jun-10 expiry); soft demand (the prior 7% offer got only ~30% uptake). Distressed test PASSES (going-concern confirmed).",
    bloom_catalysts: {
      catalyst_1: { title: "Going-Concern Maturity Wall", detected: true, description: "6.00% notes mature Jun-30-2026; $5M cash vs ~$69.6M due; substantial doubt.", evidence: "Terra Property Trust Q1-2026 10-Q; Egan-Jones downgrade to B." },
      catalyst_2: { title: "Registered Exchange (trigger)", detected: true, description: "6%->8% sec notes due Dec-31-2028 at 20% haircut; expiry Jun 10 2026.", evidence: "GlobeNewswire May 7 2026; S-4/A Amendment No. 1." },
      catalyst_3: { title: "Listed, Tradeable", detected: true, description: "TPTA is a $25 NYSE baby bond a public investor can trade directly.", evidence: "NYSE: TPTA; the exchange-listed note." },
    },
    loeb_criteria: {
      catalyst_density: { rating: "Medium", analysis: "Genuine going-concern distress + a dated, directly-tradeable listed exchange (rare on this board)." },
      sum_of_parts: { detected: false, analysis: "N/A." },
      activism_potential: { detected: false, analysis: "No formed ad-hoc group (Arena only 'considering') -> G1 unmet." },
      risk_reward: { ratio: null, analysis: "New 8% secured 2028 holds at/above exchange value vs low-participation default risk on the un-tendered Jun-30 stub." },
    },
    options_signals: NO_OPTIONS("Baby bond, not optioned. Trade the note directly on NYSE; avoid the un-tendered Jun-30 stub."),
    recent_events: [
      { date: "2026-05-07", type: "filing", title: "Terra Property Trust commences registered exchange offer (6%->8% sec 2028, 20% haircut)", link: "https://www.globenewswire.com/" },
    ],
    cache_timestamp: STAMP,
  },
};

// Sidebar candidate list (the page re-sorts by score).
export const CATALYST_CANDIDATES: any[] = Object.values(CATALYST_BOARD).map((d: any) => ({
  symbol: d.symbol,
  name: d.company_name,
  price: d.price ?? null,
  market_cap: d.market_cap ?? null,
  catalyst_score: d.catalyst_density_score,
  adjusted_loeb_score: d.adjusted_loeb_score,
  flags: [d.tier, d.lane].filter(Boolean),
  has_special_flag: d.tier === "ACTIVE",
  categories: [d.lane],
  rr_ratio: d.upside_downside_ratio ?? null,
  is_scanned: true,
  convergence_score: null,
}));
