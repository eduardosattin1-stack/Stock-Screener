"use client";

import React, { useState, useEffect, useRef } from "react";
import { Loader2 } from "lucide-react";

// Dynamically import the heavy chart component so it only runs on the client
import dynamic from "next/dynamic";
const ChartImpl = dynamic(() => import("./ChartImpl"), { ssr: false });

import AutoSizer from "react-virtualized-auto-sizer";

export function ReactFinancialChartTab({ symbol }: { symbol: string }) {
  const [data, setData] = useState<any[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([
      fetch(`/api/fmp?e=historical-price-eod/full&symbol=${symbol}`).then(res => res.json()),
      fetch(`/api/fmp?e=earnings-surprises&symbol=${symbol}`).then(res => res.json()).catch(() => [])
    ])
      .then(([json, earningsJson]) => {
        if (!json || !Array.isArray(json) || json.length === 0) {
          setError("No historical data found.");
          return;
        }

        const earningsMap: Record<string, any> = {};
        if (Array.isArray(earningsJson)) {
          earningsJson.forEach((e: any) => {
            if (e.date) earningsMap[e.date] = e;
          });
        }
        
        // FMP returns descending order (newest first).
        // react-financial-charts requires ascending order (oldest first).
        // Take the last 600 days to keep performance reasonable.
        const parsed = json.slice(0, 600).reverse().map((d: any) => ({
          date: new Date(d.date),
          open: d.open,
          high: d.high,
          low: d.low,
          close: d.close,
          volume: d.volume,
          earnings: earningsMap[d.date] || null
        }));
        
        setData(parsed);
      })
      .catch(err => {
        setError(err.message);
      });
  }, [symbol]);

  if (error) return <div style={{padding: 40, textAlign: "center", color: "#ef4444"}}>{error}</div>;
  if (!data) return <div style={{padding: 40, textAlign: "center"}}><Loader2 className="animate-spin" size={24} style={{margin:"0 auto", color:"#10b981"}}/></div>;

  return (
    <div style={{ width: "100%", height: "1200px", background: "#fff", border: "1px solid #e5e7eb", borderRadius: 8, overflow: "hidden" }}>
      <AutoSizer>
        {({ width, height }) => (
          <ChartImpl data={data} symbol={symbol} width={width} height={height} ratio={typeof window !== "undefined" ? window.devicePixelRatio : 1} />
        )}
      </AutoSizer>
    </div>
  );
}
