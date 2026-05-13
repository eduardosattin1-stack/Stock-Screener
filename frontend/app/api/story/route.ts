import { NextRequest, NextResponse } from "next/server";

export const maxDuration = 300; // 5 minutes for deep 6-step multi-agent debate

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

async function callClaude(prompt: string, apiKey: string) {
  const response = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-api-key": apiKey,
      "anthropic-version": "2023-06-01"
    },
    body: JSON.stringify({
      model: "claude-sonnet-4-20250514",
      max_tokens: 1024,
      messages: [{ role: "user", content: prompt }]
    })
  });

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`Claude API error: ${response.status} - ${errText}`);
  }

  const data = await response.json();
  return data.content[0].text;
}

export async function POST(req: NextRequest) {
  try {
    const data = await req.json();
    const { symbol, stockData } = data;

    if (!symbol || !stockData) {
      return NextResponse.json({ error: "symbol and stockData are required" }, { status: 400 });
    }

    const geminiApiKey = process.env.GEMINI_API_KEY;
    const anthropicApiKey = process.env.ANTHROPIC_API_KEY;
    
    if (!geminiApiKey || !anthropicApiKey) {
      return NextResponse.json({ error: "GEMINI_API_KEY or ANTHROPIC_API_KEY is not set in environment variables." }, { status: 500 });
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

    const baseData = `
    Symbol: ${symbol} @ $${price}
    - Composite Score: ${composite}
    - Momentum: ${momentum}, Quality: ${quality}, Growth: ${growth}, Value: ${value}, Smart Money: ${smartMoney}
    - Fundamentals: ROE: ${roe}, FCF Margin: ${fcfMargin}, Price to FCF: ${pFcf}
    - Options: Hit Prob: ${hitProb}, IV Rank: ${ivRank}
    `;

    // Step 1: Claude (Bull 1)
    const claudeBull1 = await callClaude(`You are a highly aggressive Bull Analyst. Make the initial Bull Case for ${symbol}. Data: ${baseData}\nKeep it to 2-3 sentences.`, anthropicApiKey);

    // Step 2: Gemini (Bear 1)
    const geminiBear1 = await callGemini(`You are a highly skeptical Bear Analyst. Rebut this Bull Case:\n\n${claudeBull1}\n\nData: ${baseData}\nKeep it to 2-3 sentences.`, geminiApiKey);

    // Step 3: Claude (Bull 2)
    const claudeBull2 = await callClaude(`You are the Bull Analyst. The Bear just said this:\n\n${geminiBear1}\n\nDefend your thesis and refine it. Data: ${baseData}\nKeep it to 2-3 sentences.`, anthropicApiKey);

    // Step 4: Gemini (Bear 2)
    const geminiBear2 = await callGemini(`You are the Bear Analyst. The Bull replied:\n\n${claudeBull2}\n\nMake your final bearish conclusion with a specific short-term downside PRICE TARGET based on the indicators. Limit to 3 sentences.`, geminiApiKey);

    // Step 5: Claude (Bull 3)
    const claudeBull3 = await callClaude(`You are the Bull Analyst. Make your final bullish conclusion with a specific short-term upside PRICE TARGET. Bear's final point was:\n\n${geminiBear2}\n\nData: ${baseData}\nLimit to 3 sentences.`, anthropicApiKey);

    // Step 6: Gemini CIO (Synthesis)
    const synthPrompt = `You are an elite, objective Chief Investment Officer. Synthesize the raw data, the Bull's final case, and the Bear's final case into a structured JSON report.
    
    Raw Data: ${baseData}
    Bull's Final Stand: ${claudeBull3}
    Bear's Final Stand: ${geminiBear2}

    You must output a JSON object with exactly these keys:
    1. "bottomLine": A dynamic, 3-sentence executive summary declaring the actual verdict based on the data.
    2. "balanceSheet": A "Health Grade" (A, B, C, D, or F) followed by a dash and a plain-English explanation of cash generation and debt capacity.
    3. "macroContext": A 2-sentence assessment of whether the stock's sector is fighting or riding the current macro regime.
    4. "optionsTrade": A suggested options trade narrative based on the Hit Prob and IV Rank.
    5. "catalysts": Approaching catalysts or major macro overhangs.
    6. "bullBear": Condense the analysts' points into exactly "Bull says: [1 sentence with price target]. Bear says: [1 sentence with price target]."
    7. "confidenceScore": A number from 0 to 100 representing your confidence in your verdict.

    Output pure JSON, no markdown formatting blocks.`;

    const finalJsonText = await callGemini(synthPrompt, geminiApiKey, true);

    return NextResponse.json({ story: JSON.parse(finalJsonText) });

  } catch (error: any) {
    console.error("Story Generation Error:", error);
    return NextResponse.json({ error: error.message || "Failed to generate story" }, { status: 500 });
  }
}
