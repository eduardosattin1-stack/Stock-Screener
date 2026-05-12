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

    const prompt = `You are an elite financial analyst AI. Write a dynamic, natural-sounding narrative report for ${symbol} based on the provided quantitative data.

    The report MUST translate these dry numbers into what is actually happening in the company and its broader industry (e.g., if it's NVDA, relate the numbers to the AI boom and hyperscaler deployment; if it's an oil company, relate to energy markets).

    Here is the quantitative data from our backend model:
    - Overall Composite Score (0-1): ${composite}
    - Factor Scores (0-1): Momentum: ${momentum}, Quality: ${quality}, Growth: ${growth}, Value: ${value}, Smart Money: ${smartMoney}
    - Fundamentals: ROE: ${roe}, FCF Margin: ${fcfMargin}, Price to FCF: ${pFcf}
    - Options/Volatility: Probability of +10% move (Hit Prob): ${hitProb}, Implied Volatility Rank (0-100): ${ivRank}

    Format your response in Markdown with the following specific sections (do not use other top-level headers):
    
    ### The Bottom Line
    A concise 2-3 sentence executive summary of the stock's current setup.
    
    ### Narrative & Industry Context
    Connect the stock's performance and numbers to the real-world narrative. What macroeconomic or industry trends are driving these metrics? 
    
    ### Fundamental Assessment
    Analyze the quality, growth, value factors, and margins. Is it a cash-generating machine? Is it burning cash? Is it overvalued?
    
    ### Options & Volatility Landscape
    Analyze the momentum, smart money flows, hit probability, and IV rank. Suggest what kind of options strategy (e.g., credit spreads, debit spreads, covered calls) makes sense in this volatility environment.
    
    Write in a sophisticated, objective, and analytical tone. Do not use generic filler.`;

    const response = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-pro-preview:generateContent?key=${apiKey}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contents: [{ parts: [{ text: prompt }] }],
        generationConfig: {
          temperature: 0.4,
          maxOutputTokens: 1024,
        }
      })
    });

    if (!response.ok) {
      const errText = await response.text();
      throw new Error(`Gemini API error: ${response.status} - ${errText}`);
    }

    const geminiData = await response.json();
    const generatedText = geminiData.candidates?.[0]?.content?.parts?.[0]?.text;

    if (!generatedText) {
      throw new Error("No text returned from Gemini API");
    }

    return NextResponse.json({ story: generatedText });

  } catch (error: any) {
    console.error("Story Generation Error:", error);
    return NextResponse.json({ error: error.message || "Failed to generate story" }, { status: 500 });
  }
}
