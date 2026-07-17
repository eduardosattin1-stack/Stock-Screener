// Public marketing landing page for Speculair. Deliberately outside the app shell:
// nav.tsx and AuthGate.tsx both special-case "/welcome", and middleware.ts rewrites
// the marketing domain's root here. No GCS reads, no auth, no client state. This
// page must render even when every backend is down.
//
// Design reference: hebbia.com. Warm ivory on near-black, huge uppercase display
// serif, hairline dividers, small letterspaced uppercase labels, almost no color.
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Speculair | AI equity research",
  description:
    "Speculair values 2,500 listed companies twelve different ways, flags the ones trading well below fair value, and tracks every pick in public from the day it is published.",
};

const CONTACT_EMAIL = "carbonbridge.tech@gmail.com";
const MAILTO = `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent("Speculair access")}`;

const METHODOLOGIES: { name: string; blurb: string }[] = [
  { name: "DCF, Free Cash Flow to Firm", blurb: "Projected free cash flow, discounted back to today." },
  { name: "R&D-Capitalized DCF", blurb: "The same model, with research spending treated as investment." },
  { name: "Owner Earnings", blurb: "The cash an owner could take out without weakening the business." },
  { name: "Earnings Power Value", blurb: "What the business earns today, assuming no growth at all." },
  { name: "Graham Revised", blurb: "Benjamin Graham's formula, applied to current data." },
  { name: "IV15 Deep Value", blurb: "A deliberately conservative fifteen-year estimate of intrinsic value." },
  { name: "Earnings-Yield Gap", blurb: "Earnings yield measured against each country's own government bond." },
  { name: "Gross Profitability", blurb: "Profit quality read high up the income statement, before accounting noise." },
  { name: "Acquirer's Multiple", blurb: "The price a buyer of the entire company would be paying." },
  { name: "EV / Gross Profit", blurb: "Enterprise value set against gross profit, ranked across the whole universe." },
  { name: "Convergence", blurb: "A single estimate, formed only where independent methods agree." },
  { name: "Fundamental Momentum", blurb: "Businesses improving faster than the market has noticed." },
];

// Illustrative screen output. Anonymized on purpose: no real tickers or claims.
const SCREEN_ROWS = [
  { name: "Industrials, EU", price: "24.10", fv: "38.60", agree: "9 / 12", catalyst: "Strategic review, H2" },
  { name: "Healthcare, US", price: "11.72", fv: "19.40", agree: "8 / 12", catalyst: "Phase 3 readout, Oct" },
  { name: "Media, EU", price: "6.85", fv: "10.10", agree: "10 / 12", catalyst: "Refinancing, Q4" },
  { name: "Consumer, US", price: "42.30", fv: "61.90", agree: "7 / 12", catalyst: "Spin-off record date" },
];

function Kicker({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ fontFamily: "var(--font-sans)", fontSize: 12, fontWeight: 600, letterSpacing: "0.24em", textTransform: "uppercase", color: "var(--lp-muted)", marginBottom: 20 }}>
      {children}
    </div>
  );
}

function Wordmark({ size = 15 }: { size?: number }) {
  return (
    <span style={{ fontFamily: "var(--font-mono)", fontWeight: 700, fontSize: size, letterSpacing: "0.02em", color: "var(--lp-ink)" }}>
      specul<span style={{ color: "var(--lavender)" }}>AI</span>r
    </span>
  );
}

export default function Welcome() {
  return (
    <div id="top" className="lp" style={{ background: "var(--lp-bg)", color: "var(--lp-ink)", minHeight: "100vh", overflowX: "hidden", fontFamily: "var(--font-sans)" }}>
      <style>{`
        .lp {
          --lp-bg: #111211;
          --lp-ink: #f4f1ea;
          --lp-muted: rgba(244, 241, 234, 0.58);
          --lp-faint: rgba(244, 241, 234, 0.38);
          --lp-line: rgba(244, 241, 234, 0.14);
          --lp-line-soft: rgba(244, 241, 234, 0.08);
          --lp-panel: #171817;
        }
        .lp ::selection { background: rgba(244,241,234,0.2); }
        .lp-container { max-width: 1120px; margin: 0 auto; padding: 0 32px; }
        .lp-section { padding: 104px 0; border-top: 1px solid var(--lp-line-soft); }
        .lp-display {
          font-family: var(--font-serif); font-weight: 340; text-transform: uppercase;
          letter-spacing: 0.025em; line-height: 0.98; color: var(--lp-ink); margin: 0;
        }
        .lp-h2 { font-size: clamp(30px, 4.2vw, 46px); }
        .lp-body { font-size: 16px; line-height: 1.7; color: var(--lp-muted); }
        .lp-btn {
          display: inline-flex; align-items: center; gap: 10px;
          font-family: var(--font-sans); font-size: 12px; font-weight: 700;
          letter-spacing: 0.18em; text-transform: uppercase;
          padding: 14px 26px; border-radius: 6px; cursor: pointer;
          transition: opacity .15s ease, border-color .15s ease;
        }
        .lp-btn-solid { background: var(--lp-ink); color: #141514; border: 1px solid var(--lp-ink); }
        .lp-btn-solid:hover { opacity: 0.85; }
        .lp-btn-line { background: transparent; color: var(--lp-ink); border: 1px solid var(--lp-line); }
        .lp-btn-line:hover { border-color: var(--lp-muted); }
        .lp-stats { display: grid; grid-template-columns: repeat(4, 1fr); border-top: 1px solid var(--lp-line); }
        .lp-stat { padding: 34px 28px 6px 0; border-right: 1px solid transparent; }
        .lp-stat-n { font-family: var(--font-serif); font-weight: 340; font-size: clamp(34px, 4.5vw, 54px); line-height: 1; }
        .lp-stat-l { font-size: 11px; font-weight: 600; letter-spacing: 0.2em; text-transform: uppercase; color: var(--lp-faint); margin-top: 14px; line-height: 1.6; }
        .lp-cols3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 48px; }
        .lp-feature { border-top: 1px solid var(--lp-line); padding-top: 26px; }
        .lp-feature-n { font-family: var(--font-mono); font-size: 11px; color: var(--lp-faint); margin-bottom: 18px; }
        .lp-feature-t { font-size: 17px; font-weight: 700; letter-spacing: 0.01em; margin-bottom: 12px; color: var(--lp-ink); }
        .lp-feature-d { font-size: 14px; line-height: 1.7; color: var(--lp-muted); }
        .lp-methods { display: grid; grid-template-columns: 1fr 1fr; column-gap: 72px; }
        .lp-method { display: grid; grid-template-columns: 44px 1fr; gap: 14px; padding: 20px 0; border-top: 1px solid var(--lp-line-soft); }
        .lp-method-n { font-family: var(--font-mono); font-size: 11px; color: var(--lp-faint); padding-top: 3px; }
        .lp-method-name { font-size: 14.5px; font-weight: 700; color: var(--lp-ink); margin-bottom: 5px; }
        .lp-method-blurb { font-size: 13px; line-height: 1.6; color: var(--lp-muted); }
        .lp-table { width: 100%; border-collapse: collapse; font-family: var(--font-mono); font-size: 12.5px; }
        .lp-table th {
          text-align: left; font-weight: 500; font-size: 10px; letter-spacing: 0.18em; text-transform: uppercase;
          color: var(--lp-faint); padding: 12px 16px; border-bottom: 1px solid var(--lp-line);
        }
        .lp-table td { padding: 13px 16px; border-bottom: 1px solid var(--lp-line-soft); color: var(--lp-ink); white-space: nowrap; }
        .lp-table td.muted { color: var(--lp-muted); }
        @media (max-width: 900px) {
          .lp-section { padding: 72px 0; }
          .lp-cols3 { grid-template-columns: 1fr; gap: 36px; }
          .lp-methods { grid-template-columns: 1fr; }
          .lp-stats { grid-template-columns: repeat(2, 1fr); }
        }
        @media (max-width: 560px) {
          .lp-stats { grid-template-columns: 1fr; }
        }
      `}</style>

      {/* ── Header ─────────────────────────────────────────────── */}
      <header style={{ position: "sticky", top: 0, zIndex: 40, background: "rgba(17,18,17,0.86)", backdropFilter: "blur(12px)", borderBottom: "1px solid var(--lp-line-soft)" }}>
        <div className="lp-container" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", height: 64 }}>
          <a href="#top"><Wordmark /></a>
          <a href={MAILTO} className="lp-btn lp-btn-line" style={{ padding: "10px 18px", fontSize: 11 }}>Contact</a>
        </div>
      </header>

      {/* ── Hero ───────────────────────────────────────────────── */}
      <section style={{ padding: "120px 0 96px" }}>
        <div className="lp-container">
          <Kicker>AI research for public equities</Kicker>
          <h1 className="lp-display" style={{ fontSize: "clamp(52px, 9vw, 118px)", maxWidth: 980 }}>
            Fair value,<br />verified.
          </h1>
          <p className="lp-body" style={{ maxWidth: 560, margin: "36px 0 44px" }}>
            Speculair values 2,500 listed companies twelve different ways, flags the ones
            trading well below fair value, and looks for the event that could close the gap.
            Every pick is published with a date and tracked from that day on, losers included.
          </p>
          <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
            <a href={MAILTO} className="lp-btn lp-btn-solid">Request access</a>
            <a href="#how" className="lp-btn lp-btn-line">How it works</a>
          </div>

          <div className="lp-stats" style={{ marginTop: 100 }}>
            {[
              { n: "12", l: "Valuation methods on every company" },
              { n: "13", l: "Baskets tracked live" },
              { n: "2,500+", l: "Companies screened" },
              { n: "Nightly", l: "Every position marked" },
            ].map((s) => (
              <div key={s.l} className="lp-stat">
                <div className="lp-stat-n">{s.n}</div>
                <div className="lp-stat-l">{s.l}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── The screen ─────────────────────────────────────────── */}
      <section id="how" className="lp-section">
        <div className="lp-container">
          <Kicker>The screen</Kicker>
          <h2 className="lp-display lp-h2" style={{ maxWidth: 720 }}>Cheap is not enough</h2>
          <p className="lp-body" style={{ maxWidth: 600, margin: "28px 0 56px" }}>
            Plenty of stocks look cheap on one metric, and most deserve to. Speculair flags a
            company only when several unrelated valuation methods put fair value well above
            the price, and when there is a concrete event that could force the market to
            look again.
          </p>

          <div style={{ border: "1px solid var(--lp-line)", borderRadius: 10, background: "var(--lp-panel)", overflow: "hidden", marginBottom: 64 }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 16px", borderBottom: "1px solid var(--lp-line)" }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--lp-muted)" }}>screen output</span>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: "0.16em", textTransform: "uppercase", color: "var(--lp-faint)" }}>Illustrative</span>
            </div>
            <div style={{ overflowX: "auto" }}>
              <table className="lp-table">
                <thead>
                  <tr>
                    <th>Company</th><th>Price</th><th>Median fair value</th><th>Methods above price</th><th>Catalyst</th>
                  </tr>
                </thead>
                <tbody>
                  {SCREEN_ROWS.map((r) => (
                    <tr key={r.name}>
                      <td>{r.name}</td>
                      <td className="muted">{r.price}</td>
                      <td>{r.fv}</td>
                      <td>{r.agree}</td>
                      <td className="muted">{r.catalyst}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="lp-cols3">
            {[
              { n: "01", t: "Find the discount", d: "Every company is valued twelve different ways: cash flow models, earning power, classic value formulas, market-wide ranks. A stock makes the list when methods that share no assumptions point to the same discount." },
              { n: "02", t: "Find the trigger", d: "A discount can sit untouched for years. So the screen also looks for the event that could end it: a results date, a ruling, a refinancing, a spin-off, a strategic review. Each catalyst has a date and a defined window." },
              { n: "03", t: "Test the thesis", d: "Before anything is published, each idea goes through a structured review in which one reviewer's only job is to find what is wrong with it. Ideas that fail that review are dropped. The rest go on the board." },
            ].map((f) => (
              <div key={f.n} className="lp-feature">
                <div className="lp-feature-n">{f.n}</div>
                <div className="lp-feature-t">{f.t}</div>
                <div className="lp-feature-d">{f.d}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Twelve methodologies ───────────────────────────────── */}
      <section className="lp-section">
        <div className="lp-container">
          <Kicker>Valuation</Kicker>
          <h2 className="lp-display lp-h2" style={{ maxWidth: 760 }}>Twelve ways to value the same company</h2>
          <p className="lp-body" style={{ maxWidth: 600, margin: "28px 0 48px" }}>
            Discounted cash flow, earning power, Graham, profitability ranks. Each method
            approaches the business from a different angle, and no single one is trusted on
            its own. When they disagree, we move on. When they agree, we look closer.
          </p>
          <div className="lp-methods">
            {METHODOLOGIES.map((m, i) => (
              <div key={m.name} className="lp-method">
                <div className="lp-method-n">{String(i + 1).padStart(2, "0")}</div>
                <div>
                  <div className="lp-method-name">{m.name}</div>
                  <div className="lp-method-blurb">{m.blurb}</div>
                </div>
              </div>
            ))}
          </div>
          <p style={{ fontSize: 13, color: "var(--lp-faint)", marginTop: 36, maxWidth: 600, lineHeight: 1.7 }}>
            Each method also runs as its own tracked basket, so you can see how every one of
            the twelve performs on its own record.
          </p>
        </div>
      </section>

      {/* ── The thirteenth basket ──────────────────────────────── */}
      <section className="lp-section">
        <div className="lp-container">
          <Kicker>Catalysts</Kicker>
          <h2 className="lp-display lp-h2" style={{ maxWidth: 760 }}>The thirteenth basket</h2>
          <p className="lp-body" style={{ maxWidth: 600, margin: "28px 0 0" }}>
            Twelve baskets hold undervalued companies. The thirteenth holds situations with a
            clock: positions taken because a specific event is expected to move the stock
            inside a set window. The thesis, the deadline and the exit rules are written down
            before the position opens, and the basket is marked every night like the rest.
          </p>
        </div>
      </section>

      {/* ── Built by AI ────────────────────────────────────────── */}
      <section className="lp-section">
        <div className="lp-container">
          <Kicker>How it is built</Kicker>
          <h2 className="lp-display lp-h2" style={{ maxWidth: 820 }}>Built by AI, judged on results</h2>
          <div className="lp-cols3" style={{ marginTop: 56 }}>
            {[
              { n: "01", t: "Run by AI, ruled by people", d: "The screening, the valuation work and the research notes are produced by AI, working to rules and risk limits set by people. It reads filings and prices companies the same way every day, at a scale no analyst team can." },
              { n: "02", t: "Reviewed before published", d: "AI tends to agree with itself, so the system is built to push back. Independent agents review every thesis, and one of them exists purely to break it. An idea that fails the review never reaches the site." },
              { n: "03", t: "Tracked in public", d: "Every pick carries its publication date and is marked against the market every night. The record keeps the losers and the ideas that were closed early. If the process stops working, the numbers will show it." },
            ].map((f) => (
              <div key={f.n} className="lp-feature">
                <div className="lp-feature-n">{f.n}</div>
                <div className="lp-feature-t">{f.t}</div>
                <div className="lp-feature-d">{f.d}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Access ─────────────────────────────────────────────── */}
      <section className="lp-section">
        <div className="lp-container" style={{ textAlign: "center" }}>
          <Kicker>Access</Kicker>
          <h2 className="lp-display" style={{ fontSize: "clamp(36px, 6vw, 72px)" }}>Opening as a<br />subscription</h2>
          <p className="lp-body" style={{ maxWidth: 480, margin: "30px auto 40px" }}>
            Speculair is opening to a limited group of subscribers. If you would like access,
            send us a note and tell us a little about how you invest.
          </p>
          <a href={MAILTO} className="lp-btn lp-btn-solid" style={{ padding: "16px 34px" }}>Get in touch</a>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--lp-faint)", marginTop: 22 }}>{CONTACT_EMAIL}</div>
        </div>
      </section>

      {/* ── Footer ─────────────────────────────────────────────── */}
      <footer style={{ borderTop: "1px solid var(--lp-line-soft)", padding: "48px 0 60px" }}>
        <div className="lp-container" style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
            <Wordmark size={13} />
            <a href={MAILTO} style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--lp-muted)" }}>{CONTACT_EMAIL}</a>
          </div>
          <p style={{ fontSize: 11.5, lineHeight: 1.8, color: "var(--lp-faint)", maxWidth: 780, margin: 0 }}>
            © 2026 Speculair. Research and analytics, not investment advice. Nothing on this
            site is an offer, a solicitation, or a recommendation to buy or sell any security.
            Tracked baskets are model portfolios, not managed accounts. Past or simulated
            performance does not predict future results. Do your own diligence.
          </p>
        </div>
      </footer>
    </div>
  );
}
