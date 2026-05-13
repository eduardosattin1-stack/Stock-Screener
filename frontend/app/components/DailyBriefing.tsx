"use client";
import React, { useState, useEffect } from 'react';
import { Activity, Clock, AlertTriangle, Zap, RefreshCw, BarChart2, Shield, Target } from 'lucide-react';

export function DailyBriefing() {
  const [briefing, setBriefing] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/briefing')
      .then(res => res.json())
      .then(data => {
        setBriefing(data);
        setLoading(false);
      })
      .catch(err => {
        console.error("Failed to fetch daily briefing:", err);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div style={{ marginBottom: 48, background: "var(--bg-surface)", borderBottom: "1px solid var(--border)", padding: "32px 48px", borderRadius: "0 0 16px 16px", display: "flex", justifyContent: "center", alignItems: "center", height: "300px" }}>
        <RefreshCw size={24} color="var(--text-muted)" style={{ animation: "spin 2s linear infinite" }} />
      </div>
    );
  }

  if (!briefing || briefing.error) {
    return null;
  }

  const {
    headline,
    regime_pulse,
    portfolio_pulse,
    active_strategy,
    surprising_movers,
    system_pulse,
    debate,
    miss
  } = briefing;

  return (
    <div style={{ marginBottom: 48, background: "var(--bg-surface)", borderBottom: "1px solid var(--border)", padding: "32px 48px", borderRadius: "0 0 16px 16px" }}>
      {/* ── HEADLINE STRIP ── */}
      <div style={{ display: "flex", alignItems: "baseline", gap: 16, marginBottom: 32 }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, letterSpacing: "0.18em", color: "var(--green)", textTransform: "uppercase", fontWeight: 700 }}>
          Daily Briefing
        </div>
        <div style={{ fontFamily: "var(--font-serif)", fontSize: 22, fontWeight: 300, fontStyle: "italic", color: "var(--text)" }}>
          {headline}
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
            {regime_pulse.regime} <span style={{ color: "var(--text-light)", fontWeight: 400 }}>{regime_pulse.prev_score} → {regime_pulse.score}</span>
          </div>
          <div style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.5, fontFamily: "var(--font-sans)", marginBottom: 12 }}>
            {regime_pulse.summary}
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-mono)", borderTop: "1px dashed var(--border)", paddingTop: 12 }}>
            <strong style={{ color: "var(--text)", fontWeight: 600 }}>Action:</strong> {regime_pulse.action}
          </div>
        </div>

        {/* Card 2: Portfolio pulse */}
        <div style={{ background: "var(--bg)", padding: 24, borderTop: "1px solid var(--border)", borderBottom: "1px solid var(--border)" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
            <Shield size={14} color="var(--text-muted)" />
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.18em", color: "var(--text-muted)", textTransform: "uppercase" }}>Portfolio Pulse</span>
          </div>
          <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 8 }}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 14, fontWeight: 700, color: portfolio_pulse.pnl_delta_pct >= 0 ? "var(--green)" : "var(--red)" }}>
              {portfolio_pulse.pnl_delta_pct > 0 ? "+" : ""}{portfolio_pulse.pnl_delta_pct}%
            </div>
            <div style={{ fontSize: 11, color: "var(--text-light)", fontFamily: "var(--font-mono)" }}>vs yesterday</div>
          </div>
          <div style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.5, fontFamily: "var(--font-sans)", marginBottom: 12 }}>
            <span style={{ color: "var(--red)", fontWeight: 600 }}>{portfolio_pulse.triggers_count} trigger{portfolio_pulse.triggers_count !== 1 ? 's' : ''}:</span> {portfolio_pulse.triggers_text}
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)", fontFamily: "var(--font-mono)", borderTop: "1px dashed var(--border)", paddingTop: 12 }}>
            <strong style={{ color: "var(--amber)", fontWeight: 600 }}>{portfolio_pulse.downgrades_count} downgrade{portfolio_pulse.downgrades_count !== 1 ? 's' : ''}:</strong> {portfolio_pulse.downgrades_text}
          </div>
        </div>

        {/* Card 3: Active strategy lens */}
        <div style={{ background: "var(--bg)", padding: 24, borderTop: "1px solid var(--border)", borderBottom: "1px solid var(--border)", borderLeft: "1px solid var(--border)" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Target size={14} color="var(--lavender)" />
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.18em", color: "var(--text-muted)", textTransform: "uppercase" }}>Active Strategy</span>
            </div>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--lavender)", background: "var(--purple-light)", padding: "2px 6px", borderRadius: 4 }}>{active_strategy.name}</span>
          </div>
          
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {active_strategy.top_picks.map((pick: any) => (
              <div key={pick.symbol} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700, color: "var(--text)" }}>
                  {pick.symbol}
                  {pick.is_new && <span style={{ fontSize: 9, color: "var(--amber)", marginLeft: 6, fontWeight: 500 }}>NEW</span>}
                </span>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--green)", fontWeight: 700 }}>{pick.score}</span>
              </div>
            ))}
          </div>
          <div style={{ fontSize: 11, color: "var(--text-light)", fontFamily: "var(--font-mono)", borderTop: "1px dashed var(--border)", paddingTop: 12, marginTop: 12 }}>
            Avg coverage: {active_strategy.avg_coverage}
          </div>
        </div>

        {/* Card 4: Surprising movers */}
        <div style={{ background: "var(--bg)", padding: 24, border: "1px solid var(--border)", borderRadius: "0 12px 12px 0", display: "flex", flexDirection: "column", justifyContent: "space-between" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
              <Zap size={14} color="var(--green)" />
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.18em", color: "var(--text-muted)", textTransform: "uppercase" }}>Surprising Movers</span>
            </div>
            
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {surprising_movers.map((mover: any, idx: number) => (
                <div key={idx}>
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 700, color: "var(--text)", marginBottom: 2 }}>
                    {mover.symbol} {mover.delta && <span style={{ color: "var(--green)", marginLeft: 6 }}>{mover.delta}</span>}
                  </div>
                  <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.4, fontFamily: "var(--font-sans)" }}>{mover.reason}</div>
                </div>
              ))}
            </div>
          </div>
          <div style={{ marginTop: 24 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-muted)", marginBottom: 8 }}>
              <RefreshCw size={12} /> Live tracking: <strong style={{ color: "var(--green)" }}>{system_pulse.live_mtd} MTD</strong> vs SPY {system_pulse.spy_mtd}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
              <BarChart2 size={12} /> Avg coverage: {system_pulse.avg_coverage}
            </div>
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
              <span style={{ fontSize: 13, color: "var(--text-secondary)", fontFamily: "var(--font-sans)" }}>{debate.act}</span>
            </div>
            <div style={{ flex: 1, paddingLeft: 4 }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700, color: "var(--amber)", marginRight: 8 }}>WAIT</span>
              <span style={{ fontSize: 13, color: "var(--text-secondary)", fontFamily: "var(--font-sans)" }}>{debate.wait}</span>
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
            {miss.symbol} <span style={{ color: "var(--red)", marginLeft: 8 }}>{miss.loss_pct > 0 ? "+" : ""}{miss.loss_pct}%</span>
          </div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.5, fontFamily: "var(--font-sans)" }}>
            {miss.reason}
          </div>
        </div>

      </div>

    </div>
  );
}
