import React from 'react';
import { Activity, Clock, TrendingUp, AlertTriangle, ArrowRight, Zap, RefreshCw, BarChart2, Shield } from 'lucide-react';

export function DailyBriefing() {
  return (
    <div style={{ marginBottom: 48, background: "var(--bg-surface)", borderBottom: "1px solid var(--border)", padding: "32px 48px", borderRadius: "0 0 16px 16px" }}>
      {/* ── HEADLINE STRIP ── */}
      <div style={{ display: "flex", alignItems: "baseline", gap: 16, marginBottom: 32 }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, letterSpacing: "0.18em", color: "var(--green)", textTransform: "uppercase", fontWeight: 700 }}>
          Daily Briefing
        </div>
        <div style={{ fontFamily: "var(--font-serif)", fontSize: 22, fontWeight: 300, fontStyle: "italic", color: "var(--text)" }}>
          Regime cooled to CAUTIOUS, Compounder added two new names, portfolio steady.
        </div>
      </div>

      {/* ── 4-CARD GRID ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 1 }}>
        
        {/* Card 1: Regime pulse */}
        <div style={{ background: "var(--bg)", padding: 24, border: "1px solid var(--border)", borderRadius: "12px 0 0 12px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
            <Activity size={14} color="var(--amber)" />
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.18em", color: "var(--text-muted)", textTransform: "uppercase" }}>Regime Pulse</span>
          </div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 14, fontWeight: 700, color: "var(--amber)", marginBottom: 8 }}>
            CAUTIOUS <span style={{ color: "var(--text-light)", fontWeight: 400 }}>0.48 → 0.44</span>
          </div>
          <div style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.5, fontFamily: "var(--font-sans)", marginBottom: 12 }}>
            Sentiment cooled. Yield curve inverted further.
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-mono)", borderTop: "1px dashed var(--border)", paddingTop: 12 }}>
            <strong style={{ color: "var(--text)", fontWeight: 600 }}>Action:</strong> Composite floor raised to 0.75 for new momentum entries.
          </div>
        </div>

        {/* Card 2: Portfolio pulse */}
        <div style={{ background: "var(--bg)", padding: 24, borderTop: "1px solid var(--border)", borderBottom: "1px solid var(--border)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
            <Shield size={14} color="var(--text-muted)" />
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.18em", color: "var(--text-muted)", textTransform: "uppercase" }}>Portfolio Pulse</span>
          </div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 8 }}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 14, fontWeight: 700, color: "var(--green)" }}>+0.4%</div>
            <div style={{ fontSize: 11, color: "var(--text-light)", fontFamily: "var(--font-mono)" }}>vs yesterday</div>
          </div>
          <div style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.5, fontFamily: "var(--font-sans)", marginBottom: 12 }}>
            <span style={{ color: "var(--red)", fontWeight: 600 }}>1 trigger:</span> AVGO at -8.1% from entry, hard stop fires at -12%.
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-mono)", borderTop: "1px dashed var(--border)", paddingTop: 12 }}>
            <strong style={{ color: "var(--amber)", fontWeight: 600 }}>1 downgrade:</strong> NVDA momentum signal slipped from BUY to HOLD.
          </div>
        </div>

        {/* Card 3: Active strategy lens */}
        <div style={{ background: "var(--bg)", padding: 24, borderTop: "1px solid var(--border)", borderBottom: "1px solid var(--border)", borderLeft: "1px solid var(--border)" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Target size={14} color="var(--lavender)" />
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.18em", color: "var(--text-muted)", textTransform: "uppercase" }}>Active Strategy</span>
            </div>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--lavender)", background: "var(--purple-light)", padding: "2px 6px", borderRadius: 4 }}>COMPOUNDER</span>
          </div>
          
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700, color: "var(--text)" }}>DEC</span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--green)", fontWeight: 700 }}>0.93</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700, color: "var(--text)" }}>FBIN <span style={{ fontSize: 9, color: "var(--amber)", marginLeft: 6, fontWeight: 500 }}>NEW</span></span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--green)", fontWeight: 700 }}>0.88</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700, color: "var(--text)" }}>CALM</span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--green)", fontWeight: 700 }}>0.85</span>
            </div>
          </div>
          <div style={{ fontSize: 11, color: "var(--text-light)", fontFamily: "var(--font-mono)", borderTop: "1px dashed var(--border)", paddingTop: 12, marginTop: 12 }}>
            Avg coverage: 5/5 factors.
          </div>
        </div>

        {/* Card 4: Surprising movers */}
        <div style={{ background: "var(--bg)", padding: 24, border: "1px solid var(--border)", borderRadius: "0 12px 12px 0" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
            <Zap size={14} color="var(--green)" />
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.18em", color: "var(--text-muted)", textTransform: "uppercase" }}>Surprising Movers</span>
          </div>
          
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700, color: "var(--text)", marginBottom: 2 }}>UBER <span style={{ color: "var(--green)", marginLeft: 6 }}>+0.12</span></div>
              <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.4, fontFamily: "var(--font-sans)" }}>Crossed into STRONG BUY. Fresh catalyst from Q1 earnings beat.</div>
            </div>
            <div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700, color: "var(--text)", marginBottom: 2 }}>PLTR</div>
              <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.4, fontFamily: "var(--font-sans)" }}>Factor coverage improved to 5/5. Score is now trustworthy at 0.81.</div>
            </div>
          </div>
        </div>
      </div>

      {/* ── SYSTEM PULSE (FOOTER) ── */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 24, paddingTop: 16, borderTop: "1px solid var(--border-subtle)" }}>
        <div style={{ display: "flex", gap: 32 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
            <Clock size={12} /> Scan completed in 4m 12s (2,425 symbols)
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
            <RefreshCw size={12} /> Live tracking: <strong style={{ color: "var(--green)" }}>+2.4% MTD</strong> vs SPY +1.1%
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
            <BarChart2 size={12} /> Avg coverage: 82%
          </div>
        </div>
      </div>

      {/* ── IDEAS TESTING (Reasons to act/wait & Paper trade loss) ── */}
      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 24, marginTop: 32 }}>
        
        {/* Opposing One-Liners */}
        <div style={{ background: "var(--bg)", padding: 20, borderRadius: 8, border: "1px solid var(--border)", display: "flex", flexDirection: "column", gap: 12 }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.18em", color: "var(--text-muted)", textTransform: "uppercase", marginBottom: 4 }}>System Debate</div>
          <div style={{ display: "flex", gap: 12 }}>
            <div style={{ flex: 1, paddingRight: 16, borderRight: "1px solid var(--border-subtle)" }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700, color: "var(--green)", marginRight: 8 }}>ACT</span>
              <span style={{ fontSize: 13, color: "var(--text-secondary)", fontFamily: "var(--font-sans)" }}>3 names cleared Momentum + Quality + Smart Money simultaneously today.</span>
            </div>
            <div style={{ flex: 1, paddingLeft: 4 }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700, color: "var(--amber)", marginRight: 8 }}>WAIT</span>
              <span style={{ fontSize: 13, color: "var(--text-secondary)", fontFamily: "var(--font-sans)" }}>Only 8 names cleared the 0.83 floor across the entire universe, lowest since March.</span>
            </div>
          </div>
        </div>

        {/* What the model got wrong */}
        <div style={{ background: "var(--bg)", padding: 20, borderRadius: 8, border: "1px solid var(--border)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.18em", color: "var(--text-muted)", textTransform: "uppercase" }}>System Miss</span>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--red)", background: "var(--red-light)", padding: "2px 6px", borderRadius: 4 }}>PAPER LOSS</span>
          </div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 700, color: "var(--text)", marginBottom: 4 }}>
            LULU <span style={{ color: "var(--red)", marginLeft: 8 }}>-14.2%</span>
          </div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.5, fontFamily: "var(--font-sans)" }}>
            High Quality + Value score misled the model into a value trap. Momentum sub-factor failed to catch the trend deterioration fast enough.
          </div>
        </div>

      </div>

    </div>
  );
}
