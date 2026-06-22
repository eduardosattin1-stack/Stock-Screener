"use client";
import React, { useState, useRef } from "react";
import { GLOSSARY } from "../data/catalystGlossary";
import { termLabel } from "../data/voice";

const TONE: Record<string, string> = { good: "#14b87a", mid: "#d97706", bad: "#ef4444", muted: "var(--text-muted)" };
export function toneColor(tone: string) { return TONE[tone] || "var(--text)"; }

// What to show in the R:R slot. Raw ratio is kept for the tooltip, not shown when flagged.
export function rrDisplay(rep: any): { text: string; tone: "good" | "mid" | "bad" | "muted"; rawForTooltip?: string } {
  const f: string[] = (rep && rep.edge_flags) || [];
  const g = (rep && rep.edge_grade) || "?";
  // hard-blocking flags -> show the reason, never a number
  if (f.includes("QUARANTINED"))           return { text: "— · broken inputs",   tone: "muted" };
  if (f.includes("TRADING_THROUGH_TERMS")) return { text: "— · through terms",   tone: "bad" };
  if (f.includes("NO_UPSIDE"))             return { text: "— · priced out",      tone: "bad" };
  if (f.includes("FLOOR_GE_LIVE") || f.includes("NO_BREAK_DOWNSIDE"))
                                           return { text: "— · no downside est.", tone: "muted" };
  // binaries: a barbell, never a single ratio
  if (rep.valuation_method === "binary_prob" && rep.ev_pct != null)
    return { text: `EV ${(rep.ev_pct * 100).toFixed(0)}% · ${rep.payoff != null ? rep.payoff.toFixed(1) : "?"}x @ ${Math.round((rep.win_prob || 0) * 100)}%`,
             tone: rep.ev_pct > 0 ? "mid" : "bad" };
  // thin/tiny floor: grade only; hide the inflated ratio, keep it in the tooltip
  if (f.includes("THIN_FLOOR") || f.includes("TINY_FLOOR"))
    return { text: `${g} · thin floor`, tone: g === "H" ? "good" : g === "M" ? "mid" : "bad",
             rawForTooltip: rep.computed_rr != null ? `Raw ratio ${rep.computed_rr}:1 — hidden: rests on a <15% downside floor, so it overstates. Trust the grade.` : undefined };
  // clean ratio
  if (rep.computed_rr != null)
    return { text: `${rep.computed_rr}:1 · ${g}`, tone: g === "H" ? "good" : g === "M" ? "mid" : "bad" };
  return { text: g, tone: "muted" };
}

// Hover glossary chip. <Tip k="THIN_FLOOR">child</Tip> -> dotted-underline child + a positioned card
// (title bold + body) on hover, with a native title= fallback for touch/a11y. Unknown k -> plain child.
export function Tip({ k, children, extra }: { k?: string; children: React.ReactNode; extra?: string }) {
  const g = k ? GLOSSARY[k] : undefined;
  const [show, setShow] = useState(false);
  const [pos, setPos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const ref = useRef<HTMLSpanElement>(null);
  if (!g) return <>{children}</>;
  const onEnter = () => {
    const r = ref.current?.getBoundingClientRect();
    if (r) setPos({ x: Math.min(r.left, window.innerWidth - 300), y: r.bottom + 6 });
    setShow(true);
  };
  return (
    <span
      ref={ref}
      onMouseEnter={onEnter}
      onMouseLeave={() => setShow(false)}
      title={`${g.title} — ${g.body}${extra ? " — " + extra : ""}`}
      style={{ borderBottom: "1px dotted rgba(255,255,255,0.3)", cursor: "help" }}
    >
      {children}
      {show && (
        <span
          style={{
            position: "fixed", left: pos.x, top: pos.y, zIndex: 9999, width: 280,
            background: "#0d1117", border: "1px solid #2a3340", borderRadius: 6, padding: "9px 11px",
            boxShadow: "0 8px 28px rgba(0,0,0,0.55)", fontFamily: "var(--font-sans)",
            whiteSpace: "normal", pointerEvents: "none", textTransform: "none", letterSpacing: 0,
          }}
        >
          <span style={{ display: "block", fontSize: 11, fontWeight: 800, color: "#e6edf3", marginBottom: 3 }}>{g.title}</span>
          <span style={{ display: "block", fontSize: 10.5, lineHeight: 1.5, color: "#9da7b3" }}>{g.body}</span>
          {extra && <span style={{ display: "block", marginTop: 5, fontSize: 10, fontStyle: "italic", color: "#7d8590" }}>{extra}</span>}
        </span>
      )}
    </span>
  );
}

// House-voice term. <Term k="FIRED_WIN"/> renders the plain on-screen label for a
// token (from voice.ts) with the hover definition when one exists. Unknown tokens
// fall back to a prettified label, so a raw code token never reaches the screen.
// This is the one helper every surface should use instead of printing a raw enum.
export function Term({ k, extra }: { k?: string | null; extra?: string }) {
  const label = termLabel(k);
  if (!k || !GLOSSARY[k]) return <>{label}</>;
  return <Tip k={k} extra={extra}>{label}</Tip>;
}
