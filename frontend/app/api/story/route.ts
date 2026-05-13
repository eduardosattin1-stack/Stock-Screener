import { NextRequest, NextResponse } from "next/server";

export const maxDuration = 120; // 2 minutes for multi-step debate

async function callGemini(prompt: string, apiKey: string, isJson: boolean = false) {
  const config: any = { temperature: 0.5, maxOutputTokens: 2048 };
  if (isJson) config.responseMimeType = "application/json";

  const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-pro-preview:generateContent?key=${apiKey}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      contents: [{ parts: [{ text: prompt }] }],
      generationConfig: config
    })
  });

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`Gemini API error: ${response.status} - ${errText}`);
  }

  const data = await response.json();
  const text = data.candidates?.[0]?.content?.parts?.[0]?.text;
  if (!text) throw new Error("No text returned from Gemini API");
  return text;
}

export async function POST(req: NextRequest) {
  try {
    const data = await req.json();
    const { symbol, stockData, persona, incomes, ratios } = data;

    if (!symbol || !stockData) {
      return NextResponse.json({ error: "symbol and stockData are required" }, { status: 400 });
    }

    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey) {
      return NextResponse.json({ error: "GEMINI_API_KEY is not set in environment variables." }, { status: 500 });
    }

    const s = stockData;
    const composite = s.composite?.toFixed(2) || "N/A";
    const momentum = s.momentum?.toFixed(2) || "N/A";
    const quality = s.quality?.toFixed(2) || "N/A";
    const growth = s.growth?.toFixed(2) || "N/A";
    const value = s.value?.toFixed(2) || "N/A";
    const smartMoney = s.smart_money?.toFixed(2) || "N/A";
    const roe = s.roe_avg ? (s.roe_avg * 100).toFixed(1) + "%" : "N/A";
    const fcfMargin = s.fcf_margin ? (s.fcf_margin * 100).toFixed(1) + "%" : "N/A";
    const pFcf = s.p_fcf ? s.p_fcf.toFixed(1) + "x" : "N/A";
    const hitProb = s.hit_prob ? (s.hit_prob * 100).toFixed(1) + "%" : "N/A";
    const ivRank = s.tradier_iv_rank !== undefined ? s.tradier_iv_rank : "N/A";
    const price = s.price || "N/A";
    const mcap = s.market_cap ? (s.market_cap / 1e9).toFixed(2) + "B" : "N/A";
    const sma50 = s.sma50?.toFixed(2) || "N/A";
    const sma200 = s.sma200?.toFixed(2) || "N/A";
    const revCagr = s.revenue_cagr_3y ? (s.revenue_cagr_3y * 100).toFixed(1) + "%" : "N/A";
    const epsCagr = s.eps_cagr_3y ? (s.eps_cagr_3y * 100).toFixed(1) + "%" : "N/A";
    const grossMargin = s.gross_margin ? (s.gross_margin * 100).toFixed(1) + "%" : "N/A";
    const piotroski = s.piotroski ?? "N/A";
    const altmanZ = s.altman_z?.toFixed(2) ?? "N/A";
    const dcf = s.dcf_value?.toFixed(2) ?? "N/A";
    const ownerYield = s.owner_earnings_yield ? (s.owner_earnings_yield * 100).toFixed(1) + "%" : "N/A";

    // Build Track Record / 5-Year History
    let historyStr = "";
    if (incomes && incomes.length > 0) {
      historyStr += "\n    - 5-Year Income & Growth:\n";
      incomes.forEach((inc: any) => {
        historyStr += `      [${inc.calendarYear}] Rev: $${(inc.revenue/1e9).toFixed(2)}B, Gross: $${(inc.grossProfit/1e9).toFixed(2)}B, OpInc: $${(inc.operatingIncome/1e9).toFixed(2)}B, Net: $${(inc.netIncome/1e9).toFixed(2)}B, EPS: $${inc.epsdiluted?.toFixed(2)}, EBITDA: $${(inc.ebitda/1e9).toFixed(2)}B\n`;
      });
    }
    if (s.buffett_history?.rows && s.buffett_history.rows.length > 0) {
      historyStr += "\n    - Buffett Track Record (Per Share Value & Equity):\n";
      s.buffett_history.rows.slice(-5).forEach((r: any) => {
        historyStr += `      [${r.year}] BVPS: $${r.bvps?.toFixed(2)}, EPS: $${r.eps?.toFixed(2)}, DPS: $${r.dps?.toFixed(2)}, ROE: ${(r.roe*100).toFixed(1)}%, P/E: ${r.pe?.toFixed(1)}x\n`;
      });
      if (s.buffett_history.cagrs) {
        historyStr += `      5Y CAGR: BVPS ${(s.buffett_history.cagrs.bvps_5y! * 100).toFixed(1)}%, EPS ${(s.buffett_history.cagrs.eps_5y! * 100).toFixed(1)}%\n`;
      }
    }

    const baseData = `
    Symbol: ${symbol} @ $${price} (Market Cap: $${mcap})
    - Composite Score: ${composite}
    - Factor Scores: Momentum: ${momentum}, Quality: ${quality}, Growth: ${growth}, Value: ${value}, Smart Money: ${smartMoney}
    - Technicals: SMA50: $${sma50}, SMA200: $${sma200}
    - Fundamentals & Margins: ROE: ${roe}, FCF Margin: ${fcfMargin}, Gross Margin: ${grossMargin}, Price to FCF: ${pFcf}
    - Growth (3y CAGR): Revenue: ${revCagr}, EPS: ${epsCagr}
    - Financial Health: Piotroski F-Score: ${piotroski}, Altman Z-Score: ${altmanZ}
    - Valuation: DCF Value: $${dcf}, Owner Earnings Yield: ${ownerYield}
    - Options & Flow: Hit Prob: ${hitProb}, IV Rank: ${ivRank}
    ${historyStr}
    `;

    // Persona mapping
    let personaInstruction = "an elite, objective Chief Investment Officer";
    let bullPersona = "a highly aggressive, optimistic portfolio manager";
    let bearPersona = "a highly skeptical, aggressive short-seller";

    if (persona === "Warren Buffett") {
      personaInstruction = "Warren Buffett, the legendary value investor";
      bullPersona = "Charlie Munger, focusing on wide moats and excellent businesses at fair prices";
      bearPersona = "a strict Benjamin Graham disciple, demanding a massive margin of safety and hating any premium valuation";
    } else if (persona === "Cathie Wood") {
      personaInstruction = "Cathie Wood, the visionary growth investor focused on disruptive innovation";
      bullPersona = "an ARK Invest analyst, obsessed with exponential growth trajectories and technological disruption";
      bearPersona = "a traditional value investor who thinks the growth assumptions are completely delusional";
    } else if (persona === "Ray Dalio") {
      personaInstruction = "Ray Dalio, the master of macro-economics and regime-based investing";
      bullPersona = "a Bridgewater macro analyst seeing perfect alignment between the company and the current economic machine";
      bearPersona = "a Bridgewater risk manager warning about the impending debt cycle and macro headwinds";
    } else if (persona === "Stanley Druckenmiller") {
      personaInstruction = "Stanley Druckenmiller, the legendary macro trader known for aggressive momentum and flow-based bets";
      bullPersona = "a top-tier hedge fund trader seeing massive institutional accumulation and perfect chart setups";
      bearPersona = "a contrarian macro trader seeing exhausted momentum and a crowded trade ready to reverse";
    }

    // Step 1: Bull Case Generation
    const bullPrompt = `You are ${bullPersona}. Build the absolute best, highly detailed BULL case for ${symbol} based on this data:
    ${baseData}
    Argue why the stock will go much higher. Provide a detailed analysis of the fundamentals, growth, and technicals. Limit to 5-7 sentences.`;
    const bullCase = await callGemini(bullPrompt, apiKey);

    // Step 2: Bear Case Generation
    const bearPrompt = `You are ${bearPersona}. Build the absolute best, highly detailed BEAR case for ${symbol} based on this data:
    ${baseData}
    Tear apart the bull thesis, highlight fundamental weaknesses, valuation risks, or macro headwinds. Limit to 5-7 sentences.`;
    const bearCase = await callGemini(bearPrompt, apiKey);

    // Step 3: Synthesis
    const synthPrompt = `You are ${personaInstruction}. Synthesize the raw data, the Bull Case, and the Bear Case into a final JSON report.
    Write in the distinct voice, style, and philosophy of ${persona || "an objective CIO"}. Use rich, descriptive language.
    
    Raw Data: ${baseData}
    Bull Analyst: ${bullCase}
    Bear Analyst: ${bearCase}

    You must output a JSON object with exactly these keys:
    1. "bottomLine": A dynamic, highly detailed 4-to-5 sentence executive summary declaring the actual verdict based on the data and your specific investment philosophy.
    2. "balanceSheet": A "Health Grade" (A, B, C, D, or F) followed by a dash and a detailed, plain-English explanation of cash generation, debt capacity, Piotroski score, and Altman Z.
    3. "macroContext": A 3-to-4 sentence assessment of whether the stock's sector is fighting or riding the current macro regime, and how it fits into the broader economic picture.
    4. "optionsTrade": A suggested options trade or technical setup narrative based on the Hit Prob, IV Rank, and moving averages.
    5. "catalysts": Approaching catalysts or major macro overhangs.
    6. "bullBear": Condense the analysts' points into exactly "Bull says: [2 detailed sentences]. Bear says: [2 detailed sentences]."
    7. "confidenceScore": A number from 0 to 100 representing your confidence in your verdict.

    Output pure JSON, no markdown formatting blocks.`;

    const finalJsonText = await callGemini(synthPrompt, apiKey, true);

    return NextResponse.json({ story: JSON.parse(finalJsonText) });

  } catch (error: any) {
    console.error("Story Generation Error:", error);
    return NextResponse.json({ error: error.message || "Failed to generate story" }, { status: 500 });
  }
}
