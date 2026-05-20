import React from "react";
import { ChevronRight, TrendingUp, Zap, Target, Activity } from "lucide-react";
import { StockCard } from "./StockCard";
import { useRouter } from "next/navigation";

interface ThemeCardProps {
  themeName: string;
  stockCount: number;
  performance1Y: number; // calculated from price / sma200
  avgScore: number;
  topPicks: any[]; // The StockData for the top 3 picks
  expanded: boolean;
  onClick: () => void;
}

export function ThemeCard({
  themeName,
  stockCount,
  performance1Y,
  avgScore,
  topPicks,
  expanded,
  onClick,
}: ThemeCardProps) {
  const router = useRouter();
  
  const isPositive = performance1Y >= 0;
  const perfColor = isPositive ? "var(--green)" : "var(--red)";
  
  // High score themes get a special highlight
  const isHot = avgScore > 0.65;

  return (
    <div 
      style={{
        background: "var(--bg-surface)",
        borderRadius: 12,
        border: `1px solid ${expanded ? "var(--green)" : "var(--border)"}`,
        boxShadow: expanded ? "0 4px 12px rgba(45,122,79,0.15)" : "0 2px 4px rgba(0,0,0,0.04)",
        overflow: "hidden",
        transition: "all 0.2s ease",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Header / Trigger */}
      <div 
        onClick={onClick}
        style={{
          padding: "16px 20px",
          cursor: "pointer",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          background: expanded ? "var(--bg)" : "transparent",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          <div style={{
            width: 44, height: 44, borderRadius: 10,
            background: isHot ? "var(--green-light)" : "var(--bg-elevated)",
            display: "flex", alignItems: "center", justifyContent: "center",
            color: isHot ? "var(--green)" : "var(--text-muted)"
          }}>
            {isHot ? <Zap size={22} /> : <Target size={22} />}
          </div>
          <div>
            <h3 style={{ margin: 0, fontSize: 16, fontFamily: "var(--font-sans)", fontWeight: 700, color: "var(--text)" }}>
              {themeName}
            </h3>
            <p style={{ margin: 0, marginTop: 4, fontSize: 12, fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
              {stockCount} Companies • Avg Score {(avgScore * 100).toFixed(0)}
            </p>
          </div>
        </div>
        
        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <div style={{ textAlign: "right" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 4, color: perfColor, fontWeight: 700, fontSize: 16, fontFamily: "var(--font-mono)" }}>
              <TrendingUp size={16} />
              {isPositive ? "+" : ""}{(performance1Y * 100).toFixed(1)}%
            </div>
            <div style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--text-light)", marginTop: 2 }}>
              1Y Est. Performance
            </div>
          </div>
          <ChevronRight 
            size={20} 
            color="var(--text-light)" 
            style={{ 
              transform: expanded ? "rotate(90deg)" : "none", 
              transition: "transform 0.2s ease" 
            }} 
          />
        </div>
      </div>

      {/* Expanded Content: Top Picks */}
      {expanded && (
        <div style={{ 
          padding: "0 20px 24px 20px", 
          background: "var(--bg)",
          borderTop: "1px solid var(--border-subtle)"
        }}>
          <div style={{ 
            fontSize: 11, 
            fontWeight: 700, 
            letterSpacing: "0.08em", 
            color: "var(--text-muted)", 
            fontFamily: "var(--font-mono)", 
            textTransform: "uppercase", 
            margin: "20px 0 16px 0",
            display: "flex",
            alignItems: "center",
            gap: 8
          }}>
            <Activity size={14} /> SpeculAIr Top Conviction Picks
          </div>
          
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 16 }}>
            {topPicks.map(s => {
              let action: any = "HOLD";
              if (s.composite > 0.8) action = "STRONG BUY";
              else if (s.composite > 0.65) action = "BUY";
              else if (s.composite > 0.5) action = "HOLD";
              else if (s.composite > 0.3) action = "TRIM";
              else action = "SELL";

              return (
                <StockCard 
                  key={s.symbol}
                  symbol={s.symbol}
                  companyName={s.company_name}
                  strategy={s.theme?.toUpperCase() || "THEMATIC"}
                  thesis={s.transcript_summary || s.reasons?.join(". ") || "Data-driven conviction pick based on high composite scoring and sector momentum."}
                  action={action}
                  p20={s.hit_prob ? Math.round(s.hit_prob * 100) : undefined}
                  upside={s.intrinsic_upside ?? undefined}
                  smartMoney={s.smart_money_score ?? undefined}
                  score={s.composite ?? 0}
                  price={s.price}
                  currency={s.currency}
                  onClick={() => router.push(`/stock/${s.symbol}`)}
                />
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
