// Public reference page: the Speculair method, in plain words. Sibling of /welcome and
// built the same way — a hook-free server component with no client state and no backend
// reads. Every number here is a static, dated snapshot, so the page renders even when
// every backend is down.
//
// Styling follows the /welcome idiom exactly: one scoped `.sp-*` <style> block for the
// local design system plus inline style objects for one-offs. Dark-only, like the rest
// of the app — the global :root in globals.css defines no light theme, so this page
// must not introduce one.
//
// Audience: someone with no software or finance background. Jargon is either avoided or
// explained in the sentence that uses it. Anything shipped since the previous weekly run
// carries a NEW badge so a returning reader can see what changed.
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "The method | Speculair",
  description:
    "How about 2,520 companies become a handful worth owning: the nightly scan, the twelve valuation screens, the AI committee, the debt-cycle phases and the Director's rulebook — in plain words.",
};

const CONTACT_EMAIL = "carbonbridge.tech@gmail.com";
const MAILTO = `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent("Speculair access")}`;

const AS_OF = "27 July 2026";

/* ── Data ─────────────────────────────────────────────────────── */

type Stage = {
  name: string;
  count?: string;
  isNew?: boolean;
  badge?: string;
  body: React.ReactNode;
  plus?: React.ReactNode;
};

const STAGES: Stage[] = [
  {
    name: "The nightly read",
    count: "2,520 companies",
    body: (
      <p>
        A scanner collects each company’s sales, profits, cash, debts and price history, and computes
        the raw material everything else uses. If a company is not in this scan, nothing downstream
        can ever buy it — this is the one gate nothing can reach around.
      </p>
    ),
  },
  {
    name: "Twelve ways of asking “is it cheap?”",
    count: "184 names surfaced",
    isNew: true,
    badge: "WIDER",
    body: (
      <p>
        Twelve different valuation questions each rank the whole universe and keep their own
        shortlist — one asks what all future cash profits are worth today, one what a buyer of the
        entire company would pay, one values the business as if it never grew again, and so on. A
        name only moves forward if at least one question says “cheap”.
      </p>
    ),
    plus: (
      <>
        <strong>New:</strong> each question now keeps its{" "}
        <strong>30 best answers instead of 20</strong> — the pool grew from 141 companies to 184. And
        the one screen that lost money was <strong>retired</strong>, with its record frozen for
        honesty (details below).
      </>
    ),
  },
  {
    name: "The sorting desk",
    count: "~60 deep reviews, the rest carried",
    isNew: true,
    body: (
      <p>
        Re-analysing every name every week would be wasteful — most weeks, most companies have not
        changed. So last week’s analysis carries forward with a fresh price unless something real
        happened: new quarterly results, a price move over 10%, a pending dated event, or the company
        is new here. Holdings always get a fresh look.
      </p>
    ),
    plus: (
      <>
        <strong>New:</strong> capacity for deep reviews rose from 40 to{" "}
        <strong>60 a week</strong>, and a <strong>waiting list</strong> guarantees every newcomer
        gets its first review within a few weeks — previously, overflow names could be skipped
        indefinitely purely by alphabet.
      </>
    ),
  },
  {
    name: "The committee argues",
    count: "one committee per company",
    body: (
      <p>
        Each name that earns a deep review gets a full argument — investigator, advocate, judge, then
        an independent sceptic. That is section 03 below.
      </p>
    ),
  },
  {
    name: "The calculator checks",
    body: (
      <p>
        Before any opinion counts, code verifies the numbers: the pessimistic price must sit below
        the optimistic one, quoted prices must match the live market, and a claimed safety cushion
        must be deep enough to be believable. A record that fails arithmetic cannot be bought,
        however good the story. This catches real errors — one target was published as 21 when the
        analysis said 358.
      </p>
    ),
  },
  {
    name: "The Director picks the books",
    isNew: true,
    badge: "NEW RULES",
    body: (
      <p>
        A portfolio-manager AI reads everything — the arguments, the sceptic’s verdicts, the checked
        numbers, the economic weather — and assembles the portfolios under rules it cannot bend. The
        new rulebook is section 05.
      </p>
    ),
  },
];

type QCell = { q: string; ret: string; cls?: "pos" | "neg"; retired?: boolean };

const QUESTIONS: [QCell, QCell][] = [
  [
    { q: "Deepest bargains among out-of-favour names", ret: "+16.3%", cls: "pos" },
    { q: "Classic Graham value arithmetic, updated", ret: "+3.0%" },
  ],
  [
    { q: "Price versus gross profit", ret: "+12.1%", cls: "pos" },
    { q: "Does it out-earn a safe bond?", ret: "+3.6%" },
  ],
  [
    { q: "What would a buyer of the whole firm pay?", ret: "+10.3%", cls: "pos" },
    { q: "All future cash profits, priced today", ret: "+3.5%" },
  ],
  [
    { q: "Price versus gross profit (stricter variant)", ret: "+6.6%", cls: "pos" },
    { q: "Worth if it never grows again", ret: "+2.9%" },
  ],
  [
    { q: "Several methods agree it is cheap", ret: "+2.0%" },
    { q: "The owner’s yearly take-home (Buffett’s lens)", ret: "+2.8%" },
  ],
  [
    { q: "Research spending counted as investment", ret: "+1.6%" },
    { q: "Business results accelerating", ret: "−14.1%", cls: "neg", retired: true },
  ],
];

const SEATS: { who: string; sub: string; body: React.ReactNode }[] = [
  {
    who: "The Investigator",
    sub: "digs first",
    body: (
      <>
        Reads five quarters of management’s own words and the accounts behind them, hunting for
        things that do not add up. Scores the company’s credibility 1–5. A score of 2 or less bars
        the name from every portfolio — no story overrides it. This has correctly kept out companies
        that later faced fraud investigations, including ones whose shares rose anyway.
      </>
    ),
  },
  {
    who: "The Peer checker",
    sub: "knows the neighbours",
    body: (
      <>
        Names the company’s real competitors and checks whether “cheap” survives the comparison —
        cheap against the wrong peer group is how value traps get bought.
      </>
    ),
  },
  {
    who: "The Advocate",
    sub: "argues both sides",
    body: (
      <>
        Writes the strongest honest case <em>for</em> and the strongest honest case <em>against</em>,
        and values the business piece by piece — producing three prices: pessimistic, fair,
        optimistic.
      </>
    ),
  },
  {
    who: "The Judge",
    sub: "settles it",
    body: (
      <>
        Weighs both cases into one verdict and one fair price. <span className="sp-new">NEW</span> —
        the Judge no longer marks a company down just because its big news already happened or no
        event is on the calendar. The evidence showed that habit was backwards: the “old news” names
        it rejected went on to beat the “exciting event” names by a wide margin. Events with dates
        belong to their own basket; here, only the value case matters.
      </>
    ),
  },
  {
    who: "The Sceptic",
    sub: "can veto",
    body: (
      <>
        Sees <em>only</em> the case against, and tries to kill the idea using primary sources —
        filings, regulators, the company’s own site. “Refuted” is a hard no: the Director cannot seat
        that name, whatever anyone else said.
      </>
    ),
  },
];

const DIALS: { name: string; role: string; body: React.ReactNode; isNew?: boolean }[] = [
  {
    name: "Growth & inflation",
    role: "dial one",
    body: (
      <>
        Is the economy speeding up or slowing, and are prices heating or cooling? Sets the overall
        posture: reach when conditions are friendly, defend when they are not.
      </>
    ),
  },
  {
    name: "Market mood",
    role: "dial two",
    body: (
      <>
        Interest-rate spreads, volatility, credit conditions — a temperature reading on how nervous
        or relaxed markets are right now.
      </>
    ),
  },
  {
    name: "The debt cycle",
    role: "dial three · reads DISCIPLINE today",
    isNew: true,
    body: (
      <>
        Where does the government-borrowing cycle sit? Built from six measured gauges (real long-term
        rates, bond-auction demand, debt service, credit stress and more). Deliberately{" "}
        <strong>advice, not orders</strong>: it colours the Director’s stance and stretches the time
        horizon, but moves no money until a ledger of evidence proves it should.
      </>
    ),
  },
];

const PHASES: { phase: string; today?: boolean; means: string; works: string }[] = [
  {
    phase: "EXPANSION",
    means: "Money is easy: borrowing is cheap, lenders are relaxed, governments spend freely.",
    works: "Almost everything — growth and story stocks most of all.",
  },
  {
    phase: "DISCIPLINE",
    today: true,
    means:
      "Lenders start demanding real compensation. Interest rates stay genuinely above inflation, and borrowers get squeezed.",
    works:
      "Businesses producing real cash now. Promises of profits far in the future get punished.",
  },
  {
    phase: "FORCING",
    means:
      "Something breaks: a failed government-bond auction, a funding panic. The authorities must choose between defending the value of money and rescuing the system.",
    works: "Almost nothing — defence, quality, dry powder.",
  },
  {
    phase: "MONETIZATION",
    means:
      "The rescue: money is printed, rates are pushed below inflation, and savers quietly pay the bill.",
    works: "Real assets — gold, commodities, resource producers — and long-duration stories.",
  },
];

const BUCKETS: { name: string; role: string; body: string }[] = [
  {
    name: "CASH-NOW",
    role: "earns today",
    body:
      "Profits arrive as cash this year, every year. The DISCIPLINE phase rewards these — they do not need to borrow and do not need to wait.",
  },
  {
    name: "PAYBACK",
    role: "earns soon",
    body:
      "Real cash, but the bulk of it a few years out. Fine in most weather; squeezed when waiting gets expensive.",
  },
  {
    name: "STORY",
    role: "earns someday",
    body:
      "The value lives far in the future — pre-profit growth, exploration, moonshots. These soar in MONETIZATION and suffocate in DISCIPLINE, however good the story is. Buying one today means the thesis must survive the wait.",
  },
];

const RULES: React.ReactNode[] = [
  <>
    <strong>Every position gets an equal slice.</strong> <span className="sp-new">NEW</span> The
    AI’s confidence scores were tested against results and showed no predictive power — its most
    confident calls were actually its worst. Until confidence earns its keep, no position is sized
    bigger than another.
  </>,
  <>
    <strong>No fixed number of seats.</strong> <span className="sp-new">NEW</span> The book is as big
    as the genuine opportunity set — six seats or eighteen. The discipline is dilution: every
    addition shrinks every existing slice, so a new name must be at least as good as the current
    middle of the book.
  </>,
  <>
    <strong>A real discount, or no entry.</strong> <span className="sp-new">NEW</span> New positions
    need at least 20% estimated upside in friendly weather — 25 to 30% when conditions worsen. You
    should be paid more to take risk when the tape is against you. Thin bargains do not get bought.
  </>,
  <>
    <strong>Every holding has an exit plan.</strong> <span className="sp-new">NEW</span> A floor
    below (the price at which the idea is declared broken) and a ceiling above (at 85% of fair value,
    start banking the win). Before this, a stock could quietly rise to fully valued and nothing would
    ever say “sell” — one holding rode its discount from 44% down to 9% unnoticed.
  </>,
  <>
    <strong>Every change is written down.</strong> <span className="sp-new">NEW</span> The weekly
    memo now opens with a diary: what was added and why, what was dropped and why, what was kept. No
    silent rotations.
  </>,
  <>
    <strong>Standing vetoes.</strong> Credibility of 2 or less bars the name. A refuted sceptic
    verdict bars the name. Failed arithmetic bars the name. At most 3 names per sector, at most 2
    riding the same hidden theme — a bigger book must be a more diversified one, never a more
    concentrated one.
  </>,
];

const BOOKS: { name: string; role: string; blurb: string; isNew?: boolean }[] = [
  {
    name: "Apex",
    role: "the flagship · 9 seats",
    blurb:
      "Solid businesses at a discount. The economic weather sets how big a discount is demanded at the door and how defensive the stance is — but every seat, once in, gets the same equal slice.",
  },
  {
    name: "Value lens",
    role: "second opinion · 10 seats",
    blurb:
      "The same research re-scored ignoring news and the economy entirely: just “is it cheap and financially sound?”",
  },
  {
    name: "Basket 13",
    role: "dated events · 21 seats",
    blurb:
      "Situations with a date attached — a takeover closing, a ruling, a spin-off. The only book allowed to bet on an event.",
  },
  {
    name: "Recovery sleeve",
    role: "experiment on paper · 10 seats",
    isNew: true,
    blurb:
      "Buys quality names whose big news already happened and the crowd left — the profile the old rules kept rejecting that kept going up (one such rejection rose 55%). Paper money only, racing a fixed benchmark for a quarter to earn a real allocation.",
  },
  {
    name: "Future resources",
    role: "long-term theme",
    blurb:
      "Mining, power and materials for the build-out decade — its own universe, its own rules, run beside the others.",
  },
];

/* ── Small components ─────────────────────────────────────────── */

function Wordmark({ size = 15 }: { size?: number }) {
  return (
    <span style={{ fontFamily: "var(--font-mono)", fontWeight: 700, fontSize: size, letterSpacing: "0.02em", color: "var(--sp-ink)" }}>
      specul<span style={{ color: "var(--lavender)" }}>AI</span>r
    </span>
  );
}

function SectionHead({ n, title, children }: { n: string; title: string; children?: React.ReactNode }) {
  return (
    <>
      <h2 className="sp-h2">
        <span className="sp-h2-n">{n}</span>
        {title}
      </h2>
      {children ? <p className="sp-sectnote">{children}</p> : null}
    </>
  );
}

function retClass(cls?: "pos" | "neg") {
  return cls === "pos" ? "num sp-pos" : cls === "neg" ? "num sp-neg" : "num";
}

/* ── Page ─────────────────────────────────────────────────────── */

export default function Pipeline() {
  return (
    <div id="top" className="sp" style={{ background: "var(--sp-bg)", color: "var(--sp-ink)", minHeight: "100vh", overflowX: "hidden", fontFamily: "var(--font-sans)" }}>
      <style>{`
        .sp {
          --sp-bg: #0a1817;
          --sp-ink: #f3ede4;
          --sp-muted: #b4c1be;
          --sp-faint: #6b7d7a;
          --sp-line: #1f3a35;
          --sp-line-soft: #16302b;
          --sp-panel: #101f1d;
          --sp-panel-2: #18302c;
        }
        .sp ::selection { background: rgba(20,184,122,0.28); }
        .sp-container { max-width: 1120px; margin: 0 auto; padding: 0 clamp(18px, 4vw, 40px); }

        .sp-eyebrow {
          font-family: var(--font-mono); font-size: 11px; letter-spacing: 0.16em;
          text-transform: uppercase; color: var(--amber); margin: 0 0 14px;
        }
        .sp-h1 {
          font-family: var(--font-serif); font-weight: 340; text-transform: uppercase;
          font-size: clamp(28px, 5vw, 54px); line-height: 1.02; letter-spacing: 0.02em;
          color: var(--sp-ink); margin: 0 0 20px;
        }
        .sp-standfirst { font-size: clamp(15px, 1.7vw, 18px); line-height: 1.65; color: var(--sp-muted); max-width: 66ch; margin: 0 0 24px; }
        .sp-standfirst strong { color: var(--sp-ink); font-weight: 700; }

        .sp-new {
          display: inline-block; font-family: var(--font-mono); font-size: 9.5px; font-weight: 700;
          letter-spacing: 0.12em; padding: 2px 7px; border-radius: 3px;
          background: var(--green); color: #06120f; vertical-align: middle;
        }
        .sp-retired {
          display: inline-block; font-family: var(--font-mono); font-size: 9.5px; font-weight: 700;
          letter-spacing: 0.12em; padding: 2px 7px; border-radius: 3px;
          background: var(--red); color: #1a0c0c; vertical-align: middle;
        }
        .sp-legend {
          display: inline-flex; align-items: center; gap: 11px; border: 1px solid rgba(20,184,122,0.45);
          background: rgba(20,184,122,0.09); border-radius: 6px; padding: 10px 15px;
          margin: 0; font-size: 13.5px; line-height: 1.6; color: var(--sp-muted);
        }

        .sp-section { padding: 56px 0 0; }
        .sp-h2 {
          font-family: var(--font-mono); font-size: 12px; letter-spacing: 0.15em; text-transform: uppercase;
          color: var(--sp-ink); font-weight: 600; margin: 0 0 8px;
        }
        .sp-h2-n { color: var(--amber); margin-right: 12px; }
        .sp-sectnote { font-size: 14.5px; line-height: 1.65; color: var(--sp-muted); margin: 0 0 24px; max-width: 68ch; }
        .sp-sectnote strong { color: var(--sp-ink); font-weight: 700; }
        .sp-sectnote em { color: var(--sp-ink); font-style: italic; }

        /* spine */
        .sp-stage {
          position: relative; border-left: 2px solid var(--sp-line);
          padding: 0 0 28px 26px; margin-left: 10px;
        }
        .sp-stage:last-child { border-left-color: transparent; padding-bottom: 0; }
        .sp-stage::before {
          content: ""; position: absolute; left: -7px; top: 6px; width: 12px; height: 12px;
          background: var(--amber); border: 2px solid var(--sp-bg); border-radius: 50%;
        }
        .sp-stage-new::before { background: var(--green); }
        .sp-stage-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px; margin: 0 0 10px; }
        .sp-stage-name { font-weight: 700; font-size: 16.5px; letter-spacing: -0.012em; color: var(--sp-ink); }
        .sp-count { font-family: var(--font-mono); font-size: 12.5px; color: var(--sp-faint); font-variant-numeric: tabular-nums; }
        .sp-stage p { margin: 0 0 10px; font-size: 14.5px; line-height: 1.65; color: var(--sp-muted); max-width: 70ch; }
        .sp-stage p strong { color: var(--sp-ink); font-weight: 700; }
        .sp-stage p em { color: var(--sp-ink); font-style: italic; }

        .sp-plus {
          border-left: 3px solid var(--green); background: var(--sp-panel); border-radius: 0 6px 6px 0;
          padding: 11px 15px; margin: 10px 0 0; font-size: 13.5px; line-height: 1.6;
          color: var(--sp-muted); max-width: 68ch;
        }
        .sp-plus strong { color: var(--sp-ink); font-weight: 700; }
        .sp-plus em { color: var(--sp-ink); font-style: italic; }

        /* tables */
        .sp-scroller { overflow-x: auto; border: 1px solid var(--sp-line); border-radius: 8px; background: var(--sp-panel); }
        .sp-table { border-collapse: collapse; width: 100%; font-size: 13.5px; min-width: 560px; }
        .sp-table th, .sp-table td {
          text-align: left; padding: 11px 15px; border-bottom: 1px solid var(--sp-line-soft);
          vertical-align: top; line-height: 1.55; color: var(--sp-muted);
        }
        .sp-table thead th {
          font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase;
          color: var(--sp-faint); font-weight: 500; background: var(--sp-panel-2);
          border-bottom: 1px solid var(--sp-line); white-space: nowrap;
        }
        .sp-table tbody td:first-child { color: var(--sp-ink); }
        .sp-table tbody tr:last-child td { border-bottom: none; }
        .sp-table .num { text-align: right; font-family: var(--font-mono); font-variant-numeric: tabular-nums; white-space: nowrap; }
        .sp-pos { color: var(--green); font-weight: 600; }
        .sp-neg { color: var(--red); font-weight: 600; }

        /* committee */
        .sp-panel-box { border: 1px solid var(--sp-line); border-radius: 8px; background: var(--sp-panel); padding: 4px 21px 8px; }
        .sp-seat { display: grid; grid-template-columns: 138px 1fr; gap: 16px; border-bottom: 1px solid var(--sp-line-soft); padding: 15px 0; }
        .sp-seat:last-child { border-bottom: none; }
        .sp-seat-who { font-weight: 700; font-size: 14.5px; color: var(--sp-ink); }
        .sp-seat-who small {
          display: block; font-family: var(--font-mono); font-size: 9.5px; color: var(--sp-faint);
          letter-spacing: 0.1em; text-transform: uppercase; margin-top: 4px; font-weight: 400;
        }
        .sp-seat p { margin: 0; font-size: 14px; line-height: 1.65; color: var(--sp-muted); max-width: 66ch; }
        .sp-seat p em { color: var(--sp-ink); font-style: italic; }

        /* cards */
        .sp-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 14px; }
        .sp-card { border: 1px solid var(--sp-line); border-top: 3px solid var(--amber); border-radius: 6px; background: var(--sp-panel); padding: 17px 19px; }
        .sp-card-new { border: 1px dashed rgba(20,184,122,0.55); border-top: 3px solid var(--green); }
        .sp-card h3 { font-size: 15px; margin: 0 0 4px; letter-spacing: -0.01em; color: var(--sp-ink); font-weight: 700; }
        .sp-card .role { font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.1em; text-transform: uppercase; color: var(--sp-faint); margin: 0 0 11px; }
        .sp-card p { font-size: 13px; line-height: 1.6; color: var(--sp-muted); margin: 0; }
        .sp-card p strong { color: var(--sp-ink); font-weight: 700; }

        /* rulebook */
        .sp-rulebox { border: 1px solid var(--sp-line); border-radius: 8px; background: var(--sp-panel); }
        .sp-rule {
          display: grid; grid-template-columns: 20px 1fr; gap: 13px; padding: 14px 20px;
          border-bottom: 1px solid var(--sp-line-soft); font-size: 14px; line-height: 1.65; color: var(--sp-muted);
        }
        .sp-rule:last-child { border-bottom: none; }
        .sp-rule-tick { color: var(--amber); font-weight: 700; }
        .sp-rule strong { color: var(--sp-ink); font-weight: 700; }

        .sp-foot {
          border-top: 1px solid var(--sp-line); margin-top: 56px; padding: 20px 0 0;
          font-family: var(--font-mono); font-size: 11.5px; line-height: 1.8; color: var(--sp-faint);
        }
        .sp-link { color: var(--green); border-bottom: 1px solid var(--sp-line); }
        .sp-link:hover { border-bottom-color: var(--green); }

        .sp-btn {
          display: inline-flex; align-items: center; font-family: var(--font-sans); font-size: 11px;
          font-weight: 700; letter-spacing: 0.18em; text-transform: uppercase; padding: 10px 18px;
          border-radius: 6px; background: transparent; color: var(--sp-ink); border: 1px solid var(--sp-line);
          transition: border-color .15s ease, color .15s ease;
        }
        .sp-btn:hover { border-color: var(--green); color: var(--green); }

        @media (max-width: 640px) {
          .sp-stage { margin-left: 2px; padding-left: 20px; }
          .sp-seat { grid-template-columns: 1fr; gap: 5px; }
        }
      `}</style>

      {/* ── Header (mirrors the /welcome marketing header) ─────── */}
      <header style={{ position: "sticky", top: 0, zIndex: 40, background: "rgba(17,18,17,0.86)", backdropFilter: "blur(12px)", borderBottom: "1px solid var(--sp-line-soft)" }}>
        <div className="sp-container" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", height: 64 }}>
          <a href="/welcome"><Wordmark /></a>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <a href="/welcome" className="sp-btn">Overview</a>
            <a href={MAILTO} className="sp-btn">Contact</a>
          </div>
        </div>
      </header>

      <div className="sp-container" style={{ padding: "clamp(40px, 6vw, 72px) clamp(18px, 4vw, 40px) 80px" }}>
        {/* ── Masthead ─────────────────────────────────────────── */}
        <p className="sp-eyebrow">Speculair · the method, in plain words</p>
        <h1 className="sp-h1">From 2,520 companies to a handful worth owning</h1>
        <p className="sp-standfirst">
          Every night a computer reads the accounts of about 2,520 companies around the world. Once a
          week, the most interesting ones are argued over by a committee of AIs, checked by a
          calculator and a professional sceptic, and a Director assembles the portfolios.{" "}
          <strong>Machines propose; arithmetic and rules decide.</strong>
        </p>

        <div className="sp-legend">
          <span className="sp-new">NEW</span>
          <span>
            marks everything added since the previous full run. This week’s run is the first outing
            for all of it.
          </span>
        </div>

        {/* ── 01 The assembly line ─────────────────────────────── */}
        <section className="sp-section">
          <SectionHead n="01" title="The assembly line" />
          {STAGES.map((s) => (
            <div key={s.name} className={s.isNew ? "sp-stage sp-stage-new" : "sp-stage"}>
              <div className="sp-stage-head">
                <span className="sp-stage-name">{s.name}</span>
                {s.count ? <span className="sp-count">{s.count}</span> : null}
                {s.badge ? <span className="sp-new">{s.badge}</span> : null}
              </div>
              {s.body}
              {s.plus ? <div className="sp-plus">{s.plus}</div> : null}
            </div>
          ))}
        </section>

        {/* ── 02 The twelve questions ──────────────────────────── */}
        <section className="sp-section">
          <SectionHead n="02" title="The twelve questions, and how each has done">
            Each screen runs as its own tracked basket, so the method’s parts are judged separately —
            this year the “cheap on cash profits” family is carrying the results.
          </SectionHead>
          <div className="sp-scroller">
            <table className="sp-table">
              <thead>
                <tr>
                  <th>The question, plainly</th>
                  <th className="num">This year</th>
                  <th>The question, plainly</th>
                  <th className="num">This year</th>
                </tr>
              </thead>
              <tbody>
                {QUESTIONS.map((pair) => (
                  <tr key={pair[0].q}>
                    <td>{pair[0].q}</td>
                    <td className={retClass(pair[0].cls)}>{pair[0].ret}</td>
                    <td>
                      {pair[1].q}
                      {pair[1].retired ? (
                        <>
                          {" "}
                          <span className="sp-retired">RETIRED</span>
                        </>
                      ) : null}
                    </td>
                    <td className={retClass(pair[1].cls)}>{pair[1].ret}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="sp-sectnote" style={{ marginTop: 16, marginBottom: 0 }}>
            The retired screen is frozen with its loss on display, not deleted — the record stays
            honest. <span className="sp-new">NEW</span> The four winning questions now get priority
            when review slots run short.
          </p>
        </section>

        {/* ── 03 The committee ─────────────────────────────────── */}
        <section className="sp-section">
          <SectionHead n="03" title="The committee — who argues, and who can say no" />
          <div className="sp-panel-box">
            {SEATS.map((s) => (
              <div key={s.who} className="sp-seat">
                <div className="sp-seat-who">
                  {s.who}
                  <small>{s.sub}</small>
                </div>
                <p>{s.body}</p>
              </div>
            ))}
          </div>
          <p className="sp-sectnote" style={{ marginTop: 16, marginBottom: 0 }}>
            All seats now run on the newest models — upgraded this week.
          </p>
        </section>

        {/* ── 04 The economic weather ──────────────────────────── */}
        <section className="sp-section">
          <SectionHead n="04" title="The economic weather — now on three dials">
            The Director does not pick in a vacuum; it reads the weather first. Until this week there
            were two dials. A third was just added.
          </SectionHead>
          <div className="sp-cards">
            {DIALS.map((d) => (
              <div key={d.name} className={d.isNew ? "sp-card sp-card-new" : "sp-card"}>
                <h3>
                  {d.name} {d.isNew ? <span className="sp-new">NEW</span> : null}
                </h3>
                <p className="role">{d.role}</p>
                <p>{d.body}</p>
              </div>
            ))}
          </div>

          {/* 04a — the phases */}
          <div style={{ marginTop: 40 }}>
            <SectionHead n="04a" title="The four phases, plainly">
              The debt-cycle dial can only ever read one of four phases. It moves one step at a time
              and needs two consecutive weekly readings to change — a single hot data print cannot
              jump it across the map.
            </SectionHead>
            <div className="sp-scroller">
              <table className="sp-table">
                <thead>
                  <tr>
                    <th style={{ width: 168 }}>Phase</th>
                    <th>What it means</th>
                    <th>What tends to work</th>
                  </tr>
                </thead>
                <tbody>
                  {PHASES.map((p) => (
                    <tr key={p.phase}>
                      <td>
                        <strong>{p.phase}</strong>
                        {p.today ? (
                          <>
                            {" "}
                            <span className="sp-new">TODAY</span>
                          </>
                        ) : null}
                      </td>
                      <td>{p.means}</td>
                      <td>{p.works}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* 04b — the buckets */}
          <div style={{ marginTop: 40 }}>
            <SectionHead n="04b" title="What each stock is to the cycle: cash-now, payback or story">
              Every reviewed stock is also stamped — from its own accounts, not opinion — by{" "}
              <em>when</em> its money arrives. That is what decides how the cycle treats it.
            </SectionHead>
            <div className="sp-cards">
              {BUCKETS.map((b) => (
                <div key={b.name} className="sp-card">
                  <h3>{b.name}</h3>
                  <p className="role">{b.role}</p>
                  <p>{b.body}</p>
                </div>
              ))}
            </div>
            <div className="sp-plus" style={{ marginTop: 20, maxWidth: "none" }}>
              <strong>Coming next — the Cycle Fit card:</strong> each reviewed stock’s page will
              state, in one card, where the dial sits, what the stock is to the cycle,{" "}
              <em>which phase its payoff actually needs</em>, and the dated evidence that would prove
              the phase is turning — so a “phase-three trade being bought in phase one” is named out
              loud before it is bought.
            </div>
          </div>
        </section>

        {/* ── 05 The rulebook ──────────────────────────────────── */}
        <section className="sp-section">
          <SectionHead n="05" title="The Director’s rulebook">
            The Director has judgment, but the rules below are not up for debate — most were added
            this week after studying what the system had been getting wrong.
          </SectionHead>
          <div className="sp-rulebox">
            {RULES.map((r, i) => (
              <div key={i} className="sp-rule">
                <span className="sp-rule-tick">✓</span>
                <div>{r}</div>
              </div>
            ))}
          </div>
        </section>

        {/* ── 06 The books ─────────────────────────────────────── */}
        <section className="sp-section">
          <SectionHead n="06" title="Where the money lands — five books" />
          <div className="sp-cards">
            {BOOKS.map((b) => (
              <div key={b.name} className={b.isNew ? "sp-card sp-card-new" : "sp-card"}>
                <h3>
                  {b.name} {b.isNew ? <span className="sp-new">NEW</span> : null}
                </h3>
                <p className="role">{b.role}</p>
                <p>{b.blurb}</p>
              </div>
            ))}
          </div>
          <p className="sp-sectnote" style={{ marginTop: 18, marginBottom: 0 }}>
            Every book is paper-tracked with its own audited record — real prices, no trades. The
            honest caveat: the screens have proven themselves; the committee-and-Director layer has
            not yet, and this week’s run is designed to test exactly that.
          </p>
        </section>

        <p className="sp-foot">
          Counts as of {AS_OF} — 184 unique names across twelve screens at 30 picks each. Basket
          returns are calendar-year-to-date on tracked paper baskets, not traded performance. NEW
          marks what shipped since the previous run: the wider universe (20 to 30 picks), deep-review
          capacity from 40 to 60, the first-look waiting list, the judge’s old-news penalty removed,
          the momentum screen retired, winning-family priority, the recovery sleeve, equal slices, a
          floating seat count, the weather-scaled entry floor, exit floors and ceilings, the rotation
          diary, the debt-cycle dial, and the newest models in every seat.
        </p>

        <p style={{ fontFamily: "var(--font-mono)", fontSize: 11.5, color: "var(--sp-faint)", marginTop: 26 }}>
          <a href="/welcome" className="sp-link">
            Back to the overview
          </a>
        </p>
      </div>
    </div>
  );
}
