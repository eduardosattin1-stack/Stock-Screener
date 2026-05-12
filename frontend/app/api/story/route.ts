import { NextRequest, NextResponse } from "next/server";

export const maxDuration = 60; // 60s max execution time for Vercel

export async function POST(req: NextRequest) {
  try {
    const data = await req.json();
    const { symbol, stockData } = data;

    if (!symbol || !stockData) {
      return NextResponse.json({ error: "symbol and stockData are required" }, { status: 400 });
    }

    const apiKey = process.env.GEMINI_API_KEY;
    if (!apiKey) {
      return NextResponse.json({ error: "GEMINI_API_KEY is not set in environment variables." }, { status: 500 });
    }

    // Extracting relevant metrics to build the prompt
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

    const prompt = `You are an elite financial analyst AI. Generate a narrative report for ${symbol} based on the provided quantitative data.

    Data:
    - Composite Score: ${composite}
    - Momentum: ${momentum}, Quality: ${quality}, Growth: ${growth}, Value: ${value}, Smart Money: ${smartMoney}
    - Fundamentals: ROE: ${roe}, FCF Margin: ${fcfMargin}, Price to FCF: ${pFcf}
    - Options: Hit Prob: ${hitProb}, IV Rank: ${ivRank}

    You must output a JSON object with exactly these keys:
    1. "bottomLine": A dynamic, 3-sentence executive summary. Read the composite score and generate a clear verdict. Relate the numbers to real-world industry narratives.
    2. "balanceSheet": A "Health Grade" (A, B, C, D, or F) followed by a dash and a plain-English explanation of cash generation and debt capacity.
    3. "macroContext": A 2-sentence assessment of whether the stock's sector is fighting or riding the current macro regime.
    4. "optionsTrade": A suggested options trade narrative (e.g. credit spread, debit spread, covered call) based on the Hit Prob and IV Rank.
    5. "catalysts": Approaching catalysts or major macro overhangs that could impact the stock near-term.
    6. "bullBear": A short "Bull says: X. Bear says: Y." debate summarizing the core arguments for both sides.
    7. "confidenceScore": A number from 0 to 100 representing how confident you are in this narrative based on the clarity and alignment of the fundamental and technical data.

    Output pure JSON, no markdown formatting blocks.`;

    const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-pro-preview:generateContent?key=${apiKey}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contents: [{ parts: [{ text: prompt }] }],
        generationConfig: {
          temperature: 0.4,
          maxOutputTokens: 1024,
          responseMimeType: "application/json",
        }
      })
    });

    if (!response.ok) {
      const errText = await response.text();
      throw new Error(`Gemini API error: ${response.status} - ${errText}`);
    }

    const geminiData = await response.json();
    let generatedText = geminiData.candidates?.[0]?.content?.parts?.[0]?.text;

    if (!generatedText) {
      throw new Error("No text returned from Gemini API");
    }

    return NextResponse.json({ story: JSON.parse(generatedText) });

  } catch (error: any) {
    console.error("Story Generation Error:", error);
    return NextResponse.json({ error: error.message || "Failed to generate story" }, { status: 500 });
  }
}
