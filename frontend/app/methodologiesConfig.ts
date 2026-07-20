// Shared config for the 12 Macro-Adaptive Methodology baskets - extracted from
// app/page.tsx (2026-07-20) so the per-basket pages (/basket/[key]) share one
// source of truth. NOTE: page.tsx mutates metrics.baseline/annualReturns in
// place at runtime from /baseline_history.json - both surfaces see the same
// module instance, so that behavior is preserved.

export const METHODOLOGIES_CONFIG = [

  {

    path: "intrinsic/dcf_fcff",

    name: "DCF-FCFF Valuation",

    regime: "BULL",

    description: "Projects free cash flow to the firm for 5 years — growth = ROE × 0.5 (5-yr-median ROE when available; bounded 3-25%, decaying 0.85^yr) — plus a 2.5% perpetuity, all discounted at a flat 10% WACC; net debt subtracted. Local-currency accounts, FX-converted to the price currency.",

    annualReturns: [

      { year: 2021, regime: "BULL", return: 0.082 },

      { year: 2022, regime: "BEAR", return: -0.124 },

      { year: 2023, regime: "BULL", return: 0.075 },

      { year: 2024, regime: "BULL", return: 0.091 },

      { year: 2025, regime: "SIDEWAYS", return: 0.055 }

    ],

    metrics: {

      baseline: { cagr: 0.0352, mdd: -0.0727, sharpe: 0.35, trades: 19 },

      debate: { cagr: 0.0565, mdd: -0.0736, sharpe: 0.55, trades: 34 },

      director: { cagr: 0.0506, mdd: -0.0733, sharpe: 0.50, trades: 35 }

    }

  },

  {

    path: "emerging/earnings_yield_gap",

    name: "Earnings Yield Gap",

    regime: "BULL",

    description: "Yield spread of Earnings Yield (EY = EPS / Price) over the LOCAL 10-year sovereign yield by listing country (quarterly-static table, 2026-06; was a flat 4.5% US baseline). Cross-sectional rank of the spread, centered and scaled to a ±12.5% margin of safety. Applies to every sector class — banks and insurers included.",

    annualReturns: [

      { year: 2021, regime: "BULL", return: 0.324 },

      { year: 2022, regime: "BEAR", return: -0.082 },

      { year: 2023, regime: "BULL", return: 0.301 },

      { year: 2024, regime: "BULL", return: 0.345 },

      { year: 2025, regime: "SIDEWAYS", return: 0.238 }

    ],

    metrics: {

      baseline: { cagr: 0.2195, mdd: -0.0400, sharpe: 1.96, trades: 28 },

      debate: { cagr: 0.2428, mdd: -0.0288, sharpe: 2.26, trades: 43 },

      director: { cagr: 0.2450, mdd: -0.0288, sharpe: 2.25, trades: 49 }

    }

  },

  {

    path: "multiples/ev_gross_profit",

    name: "Gross Profitability (GP/Assets)",

    regime: "BULL",

    description: "Ranks by Gross Profitability (Gross Profit / Total Assets) based on Robert Novy-Marx's research — a QUALITY factor, not an EV multiple. Centered rank scaled to ±15%; applies to every sector class. (Relabeled 2026-06; legacy key ev_gross_profit kept for tracking continuity. The true multiple is the separate EV / Gross Profit basket.)",

    metrics: {

      baseline: { cagr: 0.1362, mdd: -0.2545, sharpe: 0.835, trades: 85 },

      debate: { cagr: 0, mdd: 0, sharpe: 0, trades: 0 },

      director: { cagr: 0, mdd: 0, sharpe: 0, trades: 0 }

    }

  },

  {

    path: "emerging/rd_capitalized_dcf",

    name: "R&D Capitalized DCF",

    regime: "BULL",

    description: "Capitalizes the research the income statement expenses: adjusted earnings = NI + R&D − R&D/5 amortization, with the balance sheet carrying R&D × 2.5 for the adjusted-ROE base. Growth = adjusted ROE × 0.4 (bounded 3-20%, decaying 0.9^yr), 7-yr projection at a flat 10% WACC plus a 2.5% perpetuity.",

    metrics: {

      baseline: { cagr: 0.1350, mdd: -0.2804, sharpe: 0.748, trades: 208 },

      debate: { cagr: 0, mdd: 0, sharpe: 0, trades: 0 },

      director: { cagr: 0, mdd: 0, sharpe: 0, trades: 0 }

    }

  },

  {

    path: "intrinsic/owner_earnings",

    name: "Owner Earnings Yield",

    regime: "SIDEWAYS",

    description: "Buffett owner earnings: NI + D&A − maintenance capex (capex de-rated by the revenue-growth proxy, floored at 0.7× capex). Projected 10 years at ROE × 0.4 (bounded 2-15%, decaying 0.9^yr), discounted at a flat 10% hurdle plus a 2.5% perpetuity.",

    annualReturns: [

      { year: 2021, regime: "BULL", return: 0.184 },

      { year: 2022, regime: "BEAR", return: 0.042 },

      { year: 2023, regime: "BULL", return: 0.201 },

      { year: 2024, regime: "BULL", return: 0.225 },

      { year: 2025, regime: "SIDEWAYS", return: 0.240 }

    ],

    metrics: {

      baseline: { cagr: 0.2178, mdd: -0.0278, sharpe: 1.99, trades: 34 },

      debate: { cagr: 0.1820, mdd: -0.0364, sharpe: 1.59, trades: 43 },

      director: { cagr: 0.1874, mdd: -0.0364, sharpe: 1.71, trades: 48 }

    }

  },

  {

    path: "intrinsic/epv_greenwald",

    name: "EPV (Greenwald Valuation)",

    regime: "SIDEWAYS",

    description: "Bruce Greenwald's Earnings Power Value, zero future growth. Adjusted earnings = EBIT + D&A − maintenance capex (2026-06 epv2 fix — the old EBIT − maint-capex form left D&A inside EBIT and charged capital twice, structurally punishing D&A-heavy names); NOPAT at 21% tax, divided by 10% WACC, minus net debt.",

    metrics: {

      baseline: { cagr: 0.1401, mdd: -0.2697, sharpe: 0.753, trades: 148 },

      debate: { cagr: 0, mdd: 0, sharpe: 0, trades: 0 },

      director: { cagr: 0, mdd: 0, sharpe: 0, trades: 0 }

    }

  },

  {

    path: "v8fusion/graham_revised",

    name: "Graham Revised Valuation",

    regime: "BEAR",

    description: "Benjamin Graham's growth formula V = EPS × (8.5 + 2g), on NORMALIZED EPS so one peak year can't inflate the value; g = 3-yr EPS CAGR bounded 0-20 and set to 0 when earnings are shrinking (no growth premium for decliners). The classic 4.4/AAA-yield term is not applied.",

    annualReturns: [

      { year: 2021, regime: "BULL", return: 0.124 },

      { year: 2022, regime: "BEAR", return: 0.051 },

      { year: 2023, regime: "BULL", return: 0.142 },

      { year: 2024, regime: "BULL", return: 0.160 },

      { year: 2025, regime: "SIDEWAYS", return: 0.155 }

    ],

    metrics: {

      baseline: { cagr: 0.1374, mdd: -0.0493, sharpe: 1.15, trades: 28 },

      debate: { cagr: 0.1410, mdd: -0.0435, sharpe: 1.24, trades: 42 },

      director: { cagr: 0.1353, mdd: -0.0384, sharpe: 1.28, trades: 50 }

    }

  },

  {

    path: "multiples/acquirers_multiple",

    name: "Acquirer's Multiple",

    regime: "BEAR",

    description: "Tobias Carlisle's Acquirer's Multiple: EV / EBIT with EV = market cap + net debt, ranked cheapest-first; centered rank scaled to ±20%. Financials and insurers excluded — EV is ill-defined where deposits and float aren't acquisition debt.",

    metrics: {

      baseline: { cagr: 0.1520, mdd: -0.3406, sharpe: 0.777, trades: 246 },

      debate: { cagr: 0, mdd: 0, sharpe: 0, trades: 0 },

      director: { cagr: 0, mdd: 0, sharpe: 0, trades: 0 }

    }

  },

  {

    path: "v8fusion/iv15_deep_value",

    name: "IV15 Deep Value",

    regime: "BEAR",

    description: "Deep-value 15-year compounding test. FCF grown 15 years at the DE-PEAKED mid-cycle growth rate (bounded 2-20%; 2026-06 iv15trend — raw 3-yr EPS CAGR let peak earnings buy top slots), terminal multiple = 2× growth (bounded 8-20×), discounted at a 15% hurdle (÷1.15¹⁵). Gated on agreeing with the no-growth EPV check; names pegged at the MoS cap are held to a 0.50 ceiling.",

    metrics: {

      baseline: { cagr: 0.1520, mdd: -0.3553, sharpe: 0.719, trades: 236 },

      debate: { cagr: 0, mdd: 0, sharpe: 0, trades: 0 },

      director: { cagr: 0, mdd: 0, sharpe: 0, trades: 0 }

    }

  },

  {

    path: "v8fusion/convergence",

    name: "Convergence (Cross-Method)",

    regime: "BEAR",

    description: "10th basket. Rewards names where INDEPENDENT valuation methods CLUSTER on a fair value — up to 11 estimates (6 absolute models + Buffett intrinsic + analyst target + 3 rank-derived). Qualifies at ≥6 estimates, ≥60% agreement within ±25% of the median, consensus MoS ≥15%, ≥5yr history; ranked by capped-MoS × agreement² so tight clustering beats one outsized single-method discount.",

    metrics: {

      baseline: { cagr: 0, mdd: 0, sharpe: 0, trades: 0 },

      debate: { cagr: 0, mdd: 0, sharpe: 0, trades: 0 },

      director: { cagr: 0, mdd: 0, sharpe: 0, trades: 0 }

    }

  },

  {

    path: "v8fusion/fundamental_momentum",

    name: "Fundamental Momentum",

    regime: "BULL",

    description: "11th basket. Physical hard-tech growth (AI/datacenter, nuclear, robotics, rare-earth, defence, electrification): rev YoY ≥ 15%, 3-yr CAGR ≥ 10%, gross margin ≥ 30%, positive ROIC, analyst-covered. Score = 0.28 growth + 0.16 sustained + 0.24 ROIC quality + 0.18 analyst-revision + 0.14 margin, × analyst-target support (0.7-1.3). A growth composite, NOT a margin of safety.",

    metrics: {

      baseline: { cagr: 0, mdd: 0, sharpe: 0, trades: 0 },

      debate: { cagr: 0, mdd: 0, sharpe: 0, trades: 0 },

      director: { cagr: 0, mdd: 0, sharpe: 0, trades: 0 }

    }

  },

  {

    path: "multiples/ev_gp",

    name: "EV / Gross Profit",

    regime: "BEAR",

    description: "12th basket. The TRUE EV / Gross Profit multiple: (Market Cap + Net Debt) / Gross Profit, ranked cheapest-first; centered rank scaled to ±20%. Requires positive gross profit and market cap and a KNOWN net debt (null is ineligible, never treated as 0). Financials/insurers excluded — EV is ill-defined where float ≠ debt.",

    metrics: {

      baseline: { cagr: 0, mdd: 0, sharpe: 0, trades: 0 },

      debate: { cagr: 0, mdd: 0, sharpe: 0, trades: 0 },

      director: { cagr: 0, mdd: 0, sharpe: 0, trades: 0 }

    }

  }

];

// Canonical join key between config paths and backend JSON keys
// (methodology_picks.json / methodology_tracking.json).
export const methShortKey = (path: string): string => {
  const k = path.split("/").pop() || path;
  return k === "epv_greenwald" ? "epv" : k;
};
