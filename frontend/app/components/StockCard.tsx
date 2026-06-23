import React from "react";
import { ChevronRight } from "lucide-react";

export interface StockCardProps {
  symbol: string;
  companyName?: string;
  strategy: string; // e.g., "BORING", "Momentum"
  thesis: string; // 2 sentence AI thesis
  action: "BUY" | "HOLD" | "TRIM" | "SELL" | "WATCH" | "STRONG BUY";
  p20?: number;
  upside?: number;
  smartMoney?: number;
  score?: number;
  price: number;
  currency?: string;
  onClick?: (e: React.MouseEvent) => void;
}

const ACTION_COLORS: Record<string, { bg: string, text: string, border: string }> = {
  "STRONG BUY": { bg: "var(--purple-light)", text: "var(--purple)", border: "var(--purple-light)" },
  "BUY": { bg: "var(--green-light)", text: "var(--green)", border: "var(--green-light)" },
  "WATCH": { bg: "var(--amber-light)", text: "var(--amber)", border: "var(--amber-light)" },
  "HOLD": { bg: "var(--bg-elevated)", text: "var(--text-muted)", border: "var(--border)" },
  "TRIM": { bg: "var(--amber-light)", text: "var(--amber)", border: "var(--amber-light)" },
  "SELL": { bg: "var(--red-light)", text: "var(--red)", border: "var(--red-light)" },
};

const CURRENCY_SYMBOL: Record<string, string> = {
  USD: "$", EUR: "€", GBP: "£", JPY: "¥", CNY: "¥", HKD: "HK$",
};

const fmtPrice = (n: number | null | undefined, c?: string) => {
  if (n == null || n === 0) return "—";
  const sym = CURRENCY_SYMBOL[c ?? ""] ?? "$";
  return n >= 1000
    ? `${sym}${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
    : `${sym}${n.toFixed(2)}`;
};

export function StockCard({
  symbol,
  companyName,
  strategy,
  thesis,
  action,
  p20,
  upside,
  smartMoney,
  score,
  price,
  currency,
  onClick
}: StockCardProps) {
  const badgeStyle = ACTION_COLORS[action] || ACTION_COLORS["HOLD"];
  const scoreColor = score !== undefined ? (score > 0.7 ? "#10b981" : score > 0.5 ? "var(--text)" : score > 0.3 ? "var(--text-muted)" : "#ef4444") : "var(--text-muted)";

  return (
    <div 
      onClick={onClick}
      style={{
        background: "var(--bg-surface)",
        borderRadius: 12,
        border: "1px solid var(--border)",
        padding: "16px",
        marginBottom: "12px",
        cursor: onClick ? "pointer" : "default",
        boxShadow: "0 2px 8px rgba(0,0,0,0.04)",
        transition: "transform 0.15s, box-shadow 0.15s",
        position: "relative",
        overflow: "hidden"
      }}
      onMouseEnter={(e) => {
        if (onClick) {
          e.currentTarget.style.transform = "translateY(-2px)";
          e.currentTarget.style.boxShadow = "0 6px 16px rgba(0,0,0,0.08)";
        }
      }}
      onMouseLeave={(e) => {
        if (onClick) {
          e.currentTarget.style.transform = "none";
          e.currentTarget.style.boxShadow = "0 2px 8px rgba(0,0,0,0.04)";
        }
      }}
    >
      {/* Top Header Row */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 40, height: 40, borderRadius: 8, background: "var(--bg-elevated)", display: "flex", alignItems: "center", justifyContent: "center", border: "1px solid var(--border-subtle)" }}>
            <span style={{ fontWeight: 700, fontSize: 14, fontFamily: "var(--font-mono)", color: "var(--text)" }}>{symbol.substring(0, 2)}</span>
          </div>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ fontWeight: 800, fontSize: 16, fontFamily: "var(--font-mono)", letterSpacing: "0.02em", color: "var(--text)" }}>{symbol}</span>
              <span style={{ 
                fontSize: 9, 
                fontWeight: 700, 
                padding: "2px 6px", 
                borderRadius: 4, 
                fontFamily: "var(--font-mono)", 
                background: badgeStyle.bg, 
                color: badgeStyle.text,
                border: `1px solid ${badgeStyle.border}`
              }}>
                {action}
              </span>
            </div>
            {companyName && (
              <div style={{ fontSize: 11, color: "var(--text-light)", fontFamily: "var(--font-mono)", marginTop: 2, maxWidth: 180, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {companyName}
              </div>
            )}
          </div>
        </div>
        
        <div style={{ textAlign: "right" }}>
          <div style={{ fontSize: 15, fontWeight: 700, fontFamily: "var(--font-mono)", color: "var(--text)" }}>
            {fmtPrice(price, currency)}
          </div>
          <div style={{ fontSize: 10, fontWeight: 600, color: "var(--text-muted)", fontFamily: "var(--font-mono)", marginTop: 2, letterSpacing: "0.04em", textTransform: "uppercase" }}>
            {strategy}
          </div>
        </div>
      </div>

      {/* Thesis Body */}
      <div style={{ fontSize: 13, lineHeight: 1.5, color: "var(--text-secondary)", marginBottom: 16, fontFamily: "var(--font-sans)" }}>
        {thesis || "No thesis generated for this position."}
      </div>

      {/* Footer Metrics */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingTop: 12, borderTop: "1px solid var(--border-subtle)" }}>
        <div style={{ display: "flex", gap: 16 }}>
          {score !== undefined && (
            <div>
              <div style={{ fontSize: 9, color: "var(--text-light)", fontFamily: "var(--font-mono)", fontWeight: 600, marginBottom: 2 }}>p(10)</div>
              <div style={{ fontSize: 14, fontWeight: 800, fontFamily: "var(--font-mono)", color: scoreColor }}>{score.toFixed(2)}</div>
            </div>
          )}
          
          {p20 != null && (
            <div>
              <div style={{ fontSize: 9, color: "var(--text-light)", fontFamily: "var(--font-mono)", fontWeight: 600, marginBottom: 2 }}>P(20)</div>
              <div style={{ fontSize: 14, fontWeight: 700, fontFamily: "var(--font-mono)", color: p20 > 60 ? "var(--green)" : "var(--text-muted)" }}>{p20}%</div>
            </div>
          )}
          {upside != null && (
            <div>
              <div style={{ fontSize: 9, color: "var(--text-light)", fontFamily: "var(--font-mono)", fontWeight: 600, marginBottom: 2 }}>UPSIDE</div>
              <div style={{ fontSize: 14, fontWeight: 700, fontFamily: "var(--font-mono)", color: upside > 20 ? "var(--green)" : upside > 0 ? "var(--text)" : "var(--red)" }}>{upside > 0 ? "+" : ""}{upside.toFixed(0)}%</div>
            </div>
          )}
          {smartMoney != null && (
            <div>
              <div style={{ fontSize: 9, color: "var(--text-light)", fontFamily: "var(--font-mono)", fontWeight: 600, marginBottom: 2 }}>BASKET</div>
              <div style={{ fontSize: 14, fontWeight: 700, fontFamily: "var(--font-mono)", color: smartMoney > 0.6 ? "var(--green)" : "var(--text)" }}>{(smartMoney * 100).toFixed(0)}</div>
            </div>
          )}
        </div>

        {onClick && (
          <div style={{ display: "flex", alignItems: "center", gap: 4, color: "var(--green, #2d7a4f)", fontSize: 12, fontWeight: 600, fontFamily: "var(--font-mono)" }}>
            Details <ChevronRight size={14} />
          </div>
        )}
      </div>
    </div>
  );
}
