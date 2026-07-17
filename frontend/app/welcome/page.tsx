// Public marketing landing page for Speculair. Deliberately outside the app shell:
// nav.tsx and AuthGate.tsx both special-case "/welcome", and middleware.ts rewrites
// the marketing domain's root here. No GCS reads, no auth, no client state — this
// page must render even when every backend is down.
import type { Metadata } from "next";
import {
  Crosshair, Zap, ShieldCheck, Activity, Mail, ArrowRight, Layers, Bot,
} from "lucide-react";

export const metadata: Metadata = {
  title: "Speculair — AI-run equity research",
  description:
    "Twelve valuation methodologies, cross-checked on every company. Re-rating catalysts, hunted and tracked live. An AI-operated research platform launching as a subscription.",
};

const CONTACT_EMAIL = "carbonbridge.tech@gmail.com";
const MAILTO = `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent("Speculair — early access")}`;

const METHODOLOGIES: { name: string; blurb: string }[] = [
  { name: "DCF — Free Cash Flow to Firm", blurb: "What the discounted cash flows say the whole enterprise is worth." },
  { name: "R&D-Capitalized DCF", blurb: "Values the research the income statement expenses away." },
  { name: "Owner Earnings", blurb: "Buffett's measure of the cash an owner could actually take out." },
  { name: "Earnings Power Value", blurb: "Greenwald's discipline: what the business earns assuming zero growth." },
  { name: "Graham Revised", blurb: "The father of value investing's formula, restated for modern data." },
  { name: "IV15 Deep Value", blurb: "A fifteen-year view of intrinsic worth, deliberately conservative." },
  { name: "Earnings-Yield Gap", blurb: "Earnings yield measured against each market's own sovereign bond." },
  { name: "Gross Profitability", blurb: "Novy-Marx quality — earning power read before accounting noise." },
  { name: "Acquirer's Multiple", blurb: "What a buyer of the entire company would be paying." },
  { name: "EV / Gross Profit", blurb: "Enterprise value against raw earning capacity, ranked worldwide." },
  { name: "Convergence", blurb: "One verdict, formed only where independent estimates agree." },
  { name: "Fundamental Momentum", blurb: "Operating improvement the market has not yet priced." },
];

const mono = "var(--font-mono)";
const serif = "var(--font-serif)";

function Kicker({ children, color = "var(--lavender)" }: { children: React.ReactNode; color?: string }) {
  return (
    <div style={{ fontFamily: mono, fontSize: 11, fontWeight: 500, letterSpacing: "0.22em", textTransform: "uppercase", color, marginBottom: 16 }}>
      {children}
    </div>
  );
}

function H2({ children }: { children: React.ReactNode }) {
  return (
    <h2 style={{ fontFamily: serif, fontWeight: 400, fontSize: "clamp(28px, 4vw, 40px)", lineHeight: 1.15, color: "var(--text)", margin: 0, letterSpacing: "-0.01em" }}>
      {children}
    </h2>
  );
}

function Wordmark({ size = 18 }: { size?: number }) {
  return (
    <span style={{ fontFamily: mono, fontWeight: 800, fontSize: size, letterSpacing: "-0.04em", color: "var(--text)" }}>
      specul<span style={{ color: "var(--lavender)" }}>AI</span>r
    </span>
  );
}

export default function Welcome() {
  return (
    <div id="top" style={{ background: "var(--bg)", color: "var(--text)", minHeight: "100vh", overflowX: "hidden" }}>
      <style>{`
        .sp-container { max-width: 1060px; margin: 0 auto; padding: 0 28px; }
        .sp-section { padding: 110px 0; border-top: 1px solid var(--border-subtle); }
        .sp-btn-primary {
          display: inline-flex; align-items: center; gap: 8px;
          background: var(--green); color: #08201b; border: 1px solid var(--green);
          font-family: var(--font-mono); font-size: 13px; font-weight: 700;
          padding: 12px 22px; border-radius: 7px; cursor: pointer;
          transition: filter .15s ease, transform .15s ease;
        }
        .sp-btn-primary:hover { filter: brightness(1.12); transform: translateY(-1px); }
        .sp-btn-ghost {
          display: inline-flex; align-items: center; gap: 8px;
          background: transparent; color: var(--text-secondary); border: 1px solid var(--border);
          font-family: var(--font-mono); font-size: 13px; font-weight: 500;
          padding: 12px 22px; border-radius: 7px; cursor: pointer;
          transition: border-color .15s ease, color .15s ease;
        }
        .sp-btn-ghost:hover { border-color: var(--text-light); color: var(--text); }
        .sp-card {
          background: var(--bg-surface); border: 1px solid var(--border);
          border-radius: 10px; padding: 22px;
          transition: border-color .2s ease;
        }
        .sp-card:hover { border-color: var(--green-border); }
        .sp-grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
        .sp-grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
        .sp-stats { display: grid; grid-template-columns: repeat(4, 1fr); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; }
        .sp-stat { padding: 26px 20px; background: var(--bg-surface); }
        .sp-stat + .sp-stat { border-left: 1px solid var(--border); }
        @media (max-width: 900px) {
          .sp-grid-4 { grid-template-columns: repeat(2, 1fr); }
          .sp-grid-3 { grid-template-columns: 1fr; }
          .sp-stats { grid-template-columns: repeat(2, 1fr); }
          .sp-stat:nth-child(3) { border-left: none; }
          .sp-stat:nth-child(n+3) { border-top: 1px solid var(--border); }
          .sp-section { padding: 72px 0; }
        }
        @media (max-width: 560px) {
          .sp-grid-4 { grid-template-columns: 1fr; }
          .sp-stats { grid-template-columns: 1fr; }
          .sp-stat + .sp-stat { border-left: none; border-top: 1px solid var(--border); }
        }
        @keyframes sp-pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.35; } }
      `}</style>

      {/* ── Header ─────────────────────────────────────────────── */}
      <header style={{ position: "sticky", top: 0, zIndex: 40, background: "rgba(10,24,23,0.85)", backdropFilter: "blur(10px)", borderBottom: "1px solid var(--border-subtle)" }}>
        <div className="sp-container" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", height: 62 }}>
          <a href="#top" style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{ width: 30, height: 30, borderRadius: 7, background: "var(--green)", color: "#08201b", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 800, fontFamily: mono, letterSpacing: "-0.04em", boxShadow: "0 0 32px rgba(20,184,122,0.22)" }}>SA</span>
            <Wordmark />
          </a>
          <a href={MAILTO} className="sp-btn-primary" style={{ padding: "9px 18px", fontSize: 12 }}>
            <Mail size={13} /> Get in touch
          </a>
        </div>
      </header>

      {/* ── Hero ───────────────────────────────────────────────── */}
      <section style={{ position: "relative", padding: "130px 0 90px" }}>
        <div aria-hidden style={{ position: "absolute", inset: 0, pointerEvents: "none", background: "radial-gradient(600px 320px at 20% 0%, rgba(20,184,122,0.09), transparent 70%), radial-gradient(700px 380px at 85% 10%, rgba(196,181,253,0.07), transparent 70%)" }} />
        <div className="sp-container" style={{ position: "relative" }}>
          <Kicker>AI-run equity research</Kicker>
          <h1 style={{ fontFamily: serif, fontWeight: 300, fontSize: "clamp(40px, 6.5vw, 68px)", lineHeight: 1.08, letterSpacing: "-0.015em", margin: "0 0 26px", maxWidth: 780 }}>
            Fair value, cross-checked twelve ways.<br />
            <span style={{ fontStyle: "italic", color: "var(--lavender)" }}>Catalysts, tracked in the open.</span>
          </h1>
          <p style={{ fontSize: 17, lineHeight: 1.65, color: "var(--text-secondary)", maxWidth: 620, margin: "0 0 38px" }}>
            Speculair is an AI-operated research platform that screens thousands of listed
            companies for genuine mispricing — and for the events that force the market
            to correct it. Every conclusion is published with a time-stamp and tracked live,
            winners and losers alike.
          </p>
          <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginBottom: 72 }}>
            <a href={MAILTO} className="sp-btn-primary"><Mail size={14} /> Get in touch</a>
            <a href="#how" className="sp-btn-ghost">How it works <ArrowRight size={14} /></a>
          </div>

          <div className="sp-stats">
            {[
              { n: "12", l: "valuation methodologies", c: "var(--green)" },
              { n: "+1", l: "catalyst basket, tracked live", c: "var(--lavender)" },
              { n: "2,500+", l: "companies screened, globally", c: "var(--text)" },
              { n: "Nightly", l: "marks on every open position", c: "var(--amber)", pulse: true },
            ].map((s) => (
              <div key={s.l} className="sp-stat">
                <div style={{ fontFamily: mono, fontSize: 26, fontWeight: 700, color: s.c, display: "flex", alignItems: "center", gap: 8 }}>
                  {s.pulse && <span style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--amber)", animation: "sp-pulse 2.4s ease-in-out infinite" }} />}
                  {s.n}
                </div>
                <div style={{ fontFamily: mono, fontSize: 11, color: "var(--text-light)", marginTop: 7, letterSpacing: "0.04em" }}>{s.l}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── How it works ───────────────────────────────────────── */}
      <section id="how" className="sp-section">
        <div className="sp-container">
          <Kicker color="var(--green)">The screener</Kicker>
          <H2>Cheap is a fact. A reason to re-rate is a thesis.</H2>
          <p style={{ fontSize: 15, lineHeight: 1.7, color: "var(--text-secondary)", maxWidth: 640, margin: "20px 0 44px" }}>
            Most screens stop at &ldquo;statistically cheap.&rdquo; Speculair goes two steps further:
            it demands that independent valuation methods agree on the discount, and then
            looks for the catalyst that turns the discount into a return.
          </p>
          <div className="sp-grid-3">
            {[
              { icon: <Crosshair size={16} />, t: "Find the discount", d: "Every company is priced under twelve independent valuation methodologies — intrinsic models, cross-sectional ranks, and composites. A name qualifies only when methods that share no assumptions converge on the same conclusion." },
              { icon: <Zap size={16} />, t: "Find the trigger", d: "Undervaluation alone can stay undervalued for a decade. The screener hunts re-rating catalysts — datable, observable events with a defined window — so a position has a reason to work, not just room to." },
              { icon: <ShieldCheck size={16} />, t: "Survive the skeptic", d: "Nothing is published on a single opinion. Every thesis is argued by AI analysts and then attacked by an adversarial skeptic whose only job is to kill it. What survives, ships. What doesn't, doesn't." },
            ].map((f) => (
              <div key={f.t} className="sp-card">
                <div style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: 34, height: 34, borderRadius: 8, background: "var(--green-light)", color: "var(--green)", marginBottom: 16 }}>{f.icon}</div>
                <div style={{ fontFamily: mono, fontSize: 14, fontWeight: 700, marginBottom: 10 }}>{f.t}</div>
                <div style={{ fontSize: 13.5, lineHeight: 1.65, color: "var(--text-secondary)" }}>{f.d}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Twelve methodologies ───────────────────────────────── */}
      <section className="sp-section">
        <div className="sp-container">
          <Kicker>Twelve methodologies, one verdict</Kicker>
          <H2>No single model is trusted. That&rsquo;s the point.</H2>
          <p style={{ fontSize: 15, lineHeight: 1.7, color: "var(--text-secondary)", maxWidth: 640, margin: "20px 0 44px" }}>
            Each methodology values the same company from a different direction — discounted
            cash flows, earning power, replacement logic, cross-sectional rank. Where they
            disagree, we assume the models are wrong. Where they converge, we start paying attention.
          </p>
          <div className="sp-grid-4">
            {METHODOLOGIES.map((m, i) => (
              <div key={m.name} className="sp-card" style={{ padding: 18 }}>
                <div style={{ fontFamily: mono, fontSize: 10, color: "var(--text-light)", marginBottom: 8 }}>{String(i + 1).padStart(2, "0")}</div>
                <div style={{ fontFamily: mono, fontSize: 12.5, fontWeight: 700, marginBottom: 8, color: "var(--text)" }}>{m.name}</div>
                <div style={{ fontSize: 12, lineHeight: 1.55, color: "var(--text-muted)" }}>{m.blurb}</div>
              </div>
            ))}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 26, fontFamily: mono, fontSize: 12, color: "var(--text-light)" }}>
            <Layers size={13} style={{ flexShrink: 0 }} />
            Each methodology runs as its own tracked basket — twelve live portfolios, each accountable to its own record.
          </div>
        </div>
      </section>

      {/* ── The thirteenth basket ──────────────────────────────── */}
      <section className="sp-section">
        <div className="sp-container" style={{ display: "grid", gridTemplateColumns: "1fr", gap: 36 }}>
          <div style={{ maxWidth: 680 }}>
            <Kicker color="var(--amber)">The thirteenth basket</Kicker>
            <H2>Twelve baskets own the mispricing.<br />The thirteenth owns the moment.</H2>
            <p style={{ fontSize: 15, lineHeight: 1.7, color: "var(--text-secondary)", margin: "20px 0 0" }}>
              Alongside the twelve methodology baskets runs a separate, event-driven sleeve:
              positions taken because a specific, datable catalyst — a ruling, a readout, a
              refinancing, a strategic decision — is expected to re-rate the stock inside a
              defined window. Each entry carries its thesis, its clock, and its exit
              conditions in writing before the position exists. It is tracked with the same
              nightly discipline as everything else.
            </p>
          </div>
          <div style={{ display: "flex", gap: 6, alignItems: "flex-end", height: 68 }} aria-hidden>
            {Array.from({ length: 12 }).map((_, i) => (
              <div key={i} style={{ flex: 1, height: `${34 + ((i * 17) % 30)}%`, background: "var(--green-light)", border: "1px solid var(--green-border)", borderRadius: 3 }} />
            ))}
            <div style={{ flex: 1, height: "100%", background: "rgba(245,185,66,0.16)", border: "1px solid rgba(245,185,66,0.45)", borderRadius: 3 }} />
          </div>
        </div>
      </section>

      {/* ── Built by AI ────────────────────────────────────────── */}
      <section className="sp-section">
        <div className="sp-container">
          <Kicker>The AI-built story</Kicker>
          <H2>Designed, written, and operated by AI.<br />Held to a human standard of proof.</H2>
          <div className="sp-grid-3" style={{ marginTop: 44 }}>
            {[
              { icon: <Bot size={16} />, t: "AI end to end", d: "The screening engine, the valuation work, the research notes, the debate that decides every basket — and this page — were built and are run by AI. Human judgment sets the rules and the risk limits; the machine executes them without fatigue, ego, or attachment to yesterday's opinion." },
              { icon: <ShieldCheck size={16} />, t: "Adversarial by design", d: "AI's known failure mode is confident agreement. Speculair is built against it: independent agents argue each thesis, and a dedicated skeptic is rewarded for refuting, not confirming. A conviction that cannot survive its own devil's advocate never reaches you." },
              { icon: <Activity size={16} />, t: "Accountable in public", d: "Every pick is time-stamped the day it is published and marked every night thereafter. Track records include the exits, the losers, and the theses that were refuted. If the process stops working, the numbers will say so before we do." },
            ].map((f) => (
              <div key={f.t} className="sp-card">
                <div style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", width: 34, height: 34, borderRadius: 8, background: "var(--purple-light)", color: "var(--lavender)", marginBottom: 16 }}>{f.icon}</div>
                <div style={{ fontFamily: mono, fontSize: 14, fontWeight: 700, marginBottom: 10 }}>{f.t}</div>
                <div style={{ fontSize: 13.5, lineHeight: 1.65, color: "var(--text-secondary)" }}>{f.d}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Subscription CTA ───────────────────────────────────── */}
      <section className="sp-section">
        <div className="sp-container">
          <div style={{ border: "1px solid var(--border)", borderRadius: 14, padding: "clamp(36px, 6vw, 64px)", textAlign: "center", background: "linear-gradient(180deg, var(--bg-surface), var(--bg))", position: "relative", overflow: "hidden" }}>
            <div aria-hidden style={{ position: "absolute", inset: 0, background: "radial-gradient(420px 200px at 50% 0%, rgba(20,184,122,0.10), transparent 70%)", pointerEvents: "none" }} />
            <div style={{ position: "relative" }}>
              <Kicker color="var(--green)">Launching as a subscription</Kicker>
              <H2>The research desk is warming up.</H2>
              <p style={{ fontSize: 15, lineHeight: 1.7, color: "var(--text-secondary)", maxWidth: 520, margin: "18px auto 34px" }}>
                Speculair opens as a subscription service. Early access will be limited while
                the desk scales — tell us who you are and what you invest in, and we&rsquo;ll be in touch.
              </p>
              <a href={MAILTO} className="sp-btn-primary" style={{ fontSize: 14, padding: "14px 28px" }}>
                <Mail size={15} /> Get in touch
              </a>
              <div style={{ fontFamily: mono, fontSize: 11, color: "var(--text-light)", marginTop: 18 }}>{CONTACT_EMAIL}</div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Footer ─────────────────────────────────────────────── */}
      <footer style={{ borderTop: "1px solid var(--border-subtle)", padding: "44px 0 56px" }}>
        <div className="sp-container" style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
            <Wordmark size={15} />
            <a href={MAILTO} style={{ fontFamily: mono, fontSize: 12, color: "var(--text-muted)" }}>{CONTACT_EMAIL}</a>
          </div>
          <p style={{ fontFamily: mono, fontSize: 10.5, lineHeight: 1.7, color: "var(--text-light)", maxWidth: 760, margin: 0 }}>
            © 2026 Speculair. Research and analytics, not investment advice. Nothing on this
            site is an offer, a solicitation, or a recommendation to buy or sell any security.
            Tracked baskets are model portfolios, not managed accounts; past or simulated
            performance does not predict future results. Do your own diligence.
          </p>
        </div>
      </footer>
    </div>
  );
}
