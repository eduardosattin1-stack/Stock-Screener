// Public reference page: the Speculair pipeline system map. Sibling of /welcome and
// built the same way — an async-free server component with no hooks, no client state,
// no backend reads. Every number here is a static, dated snapshot (2026-07-24), so the
// page renders even when every backend is down.
//
// Styling follows the /welcome idiom exactly: one scoped `.sp-*` <style> block for the
// local design system plus inline style objects for one-offs. Dark-only, like the rest
// of the app — the global :root in globals.css defines no light theme, so this page
// must not introduce one.
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "System map | Speculair",
  description:
    "How 2,520 screened names become 9 apex seats: the nine-stage Speculair pipeline, the gates that remove material at each step, the five books, and what the evidence says actually predicts returns.",
};

const CONTACT_EMAIL = "carbonbridge.tech@gmail.com";
const MAILTO = `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent("Speculair access")}`;

const AS_OF = "2026-07-24";

/* ── Data ─────────────────────────────────────────────────────── */

const LEDGER: { label: string; value: string; sub: string }[] = [
  { label: "Scan universe", value: "2,520", sub: "global, nightly" },
  { label: "Screened", value: "141", sub: "11 methodologies" },
  { label: "Underwritten", value: "40", sub: "Tier-U hard cap" },
  { label: "Apex seats", value: "9", sub: "+ 6 runners" },
  { label: "Value seats", value: "10", sub: "+ 6 runners" },
  { label: "Basket 13", value: "21", sub: "open events" },
];

type Chip = { kind: "hard" | "size"; label: string };

type Stage = {
  name: string;
  engine: string;
  engineKind: "det" | "opus";
  bar?: number;
  flow?: React.ReactNode;
  body: React.ReactNode;
  chips?: Chip[];
};

const STAGES: Stage[] = [
  {
    name: "Universe",
    engine: "Cloud Run · nightly",
    engineKind: "det",
    bar: 100,
    flow: <>2,520 names scored on fundamentals, valuation, quality, technicals</>,
    body: (
      <p>
        The only source of candidates. A name absent here cannot enter any book — the single
        largest constraint in the system, and invisible from inside the debate.
      </p>
    ),
  },
  {
    name: "Methodology screens",
    engine: "deterministic",
    engineKind: "det",
    bar: 31,
    flow: (
      <>
        2,520 <span className="sp-arrow">→</span> 141 unique names <span className="sp-drop">(−94%)</span>
      </>
    ),
    body: (
      <p>
        Eleven valuation screens rank the universe; each publishes its own tracked basket. Four
        bypass lanes inject names the rankings structurally miss, with hard weekly caps in code:
        deep-drawdown quality (20), neglect orphans (3), quality-at-a-discount (3), fresh crashes (2).
      </p>
    ),
    chips: [
      { kind: "hard", label: "margin of safety ≤ 0 → invisible" },
      { kind: "hard", label: "structural break → dropped" },
    ],
  },
  {
    name: "Change detection",
    engine: "deterministic",
    engineKind: "det",
    body: (
      <p>
        Most names carry last week&apos;s record forward, restamped with a live price. A name is
        re-debated only on a real trigger: new transcript, price move over 10%, a dated catalyst
        pending, a held seat, a record over 21 days old, or first appearance. Cuts roughly 149
        debates to 45–70.
      </p>
    ),
  },
  {
    name: "Tier partition",
    engine: "deterministic",
    engineKind: "det",
    bar: 18,
    flow: (
      <>
        141 <span className="sp-arrow">→</span> 40 underwritten <span className="sp-drop">(hard cap)</span>
      </>
    ),
    body: (
      <p>
        Tier-U gets the full Opus treatment: held seats in delta mode, triggered seats, and ranked
        new intake. Everything above the cap drops to a cheap coverage refresh that <em>inherits</em>{" "}
        its old grade, or goes uncovered. Event-driven names are excluded here and routed to Basket 13.
      </p>
    ),
    chips: [
      { kind: "hard", label: "Basket-13 names excluded from this lane" },
      { kind: "size", label: "over cap → grade inherited, not re-judged" },
    ],
  },
  {
    name: "Debate",
    engine: "Opus · Sonnet",
    engineKind: "opus",
    body: (
      <p>
        Peer clustering (Sonnet) feeds a three-role underwrite per name: <strong>Interrogator</strong>{" "}
        builds a forensic dossier and scores credibility, <strong>Architect</strong> writes bull and
        bear plus a sum-of-parts valuation, <strong>CRO</strong> reconciles them into a fair value, a
        risk/reward, and two separate scores — a regime-aware conviction and a catalyst-blind value
        conviction.
      </p>
    ),
    chips: [
      { kind: "hard", label: "credibility ≤ 2 → forensic exclude" },
      { kind: "size", label: "eroding moat → value conviction capped at 3" },
    ],
  },
  {
    name: "Numeric gates",
    engine: "deterministic · enforced",
    engineKind: "det",
    body: (
      <p>
        Code checks the model&apos;s arithmetic: that bear ≤ base ≤ bull, that quoted prices match
        the live tape, that a claimed floor is real. Prose ratios are overwritten by computed ones.
        Enforcing since 2026-07-11.
      </p>
    ),
    chips: [
      { kind: "hard", label: "reject / exclude → demoted from seat" },
      { kind: "hard", label: "thin floor: downside < 15% of price" },
    ],
  },
  {
    name: "Skeptic kill-tier",
    engine: "Opus · adversarial",
    engineKind: "opus",
    body: (
      <p>
        An independent agent that sees only the bear case and is told to kill the thesis — refuted by
        default unless primary sources confirm the load-bearing facts. Runs <em>before</em> the
        Director, so kills inform seating rather than vaporising seats afterwards.
      </p>
    ),
    chips: [
      { kind: "hard", label: "refuted → cannot be seated" },
      { kind: "size", label: "material correction → size × 0.75" },
      { kind: "size", label: "no shard → half size" },
    ],
  },
  {
    name: "Directors",
    engine: "Opus · per book",
    engineKind: "opus",
    bar: 9,
    flow: (
      <>
        40 <span className="sp-arrow">→</span> 9 apex seats <span className="sp-drop">(−78%)</span>
      </>
    ),
    body: (
      <p>
        Two independent graders read the same records. The apex Director applies the macro regime and
        rotation discipline; the value Director strips catalyst and regime entirely and grades on
        margin of safety, solvency and forensic quality. A held seat is kept unless its thesis
        actually broke.
      </p>
    ),
    chips: [
      { kind: "hard", label: "conviction < 3 → ineligible" },
      { kind: "hard", label: "no equity special-sits (Basket 13 owns those)" },
      { kind: "size", label: "max 3 per sector" },
    ],
  },
  {
    name: "Post layers",
    engine: "deterministic",
    engineKind: "det",
    body: (
      <p>
        The last word belongs to code, not the model. Skeptic verdicts are applied, moat and
        secular-theme concentration capped, a measured correlation matrix caps any pair above 0.7,
        and unjustified conviction moves are clamped back to ±10 of last week&apos;s.
      </p>
    ),
    chips: [
      { kind: "size", label: "theme ≥ 2 names → combined cap" },
      { kind: "size", label: "correlated pair → ≤ 16% weight" },
      { kind: "size", label: "undated conviction move → clamped" },
    ],
  },
];

const BOOKS: { name: string; role: string; stat: string; statSub: string; blurb: string; paper?: boolean }[] = [
  {
    name: "Apex",
    role: "compounders · regime-sized",
    stat: "109.0",
    statSub: "NAV · equal weight",
    blurb: "9 seats. Durable franchises and value re-rates. Weighted NAV 105.3.",
  },
  {
    name: "Value lens",
    role: "catalyst-blind re-grade",
    stat: "108.0",
    statSub: "NAV",
    blurb: "10 seats from the same debates, graded purely on discount, solvency and forensics.",
  },
  {
    name: "Basket 13",
    role: "dated events",
    stat: "21",
    statSub: "open seats",
    blurb: "Merger spreads, forced sellers, breakups, binaries — the only book allowed to own an event.",
  },
  {
    name: "Recovery sleeve",
    role: "paper · new this week",
    stat: "10",
    statSub: "seats",
    blurb: "Treats a fired catalyst as an entry signal rather than a penalty. Benchmark pinned at inception.",
    paper: true,
  },
  {
    name: "Future resources",
    role: "thematic chain",
    stat: "—",
    statSub: "separate lane",
    blurb: "Its own universe, mapping and Director, published beside the others.",
    paper: true,
  },
];

const SIGNAL_ROWS: { signal: string; buckets: string; ret: React.ReactNode; retClass?: string; reads: string }[] = [
  {
    signal: "Debate conviction",
    buckets: "1 → 5",
    ret: <>+1.4 / +1.5 / +1.9 / +1.2 / +1.7%</>,
    retClass: "sp-flat",
    reads: "no ordering",
  },
  {
    signal: "Debate verdict",
    buckets: "A vs B vs C",
    ret: (
      <>
        <span className="sp-neg">−1.9%</span> / +2.1% / +1.4%
      </>
    ),
    reads: "top grade was worst",
  },
  {
    signal: "Implied upside (fair value)",
    buckets: "Q1 vs Q2–Q5",
    ret: (
      <>
        <span className="sp-neg">−2.3%</span> vs +1.3 … +3.0%
      </>
    ),
    reads: "floor detector, not a ranker",
  },
  {
    signal: "Catalyst status",
    buckets: "fired/soft vs dated",
    ret: (
      <>
        <span className="sp-pos">+2.5%</span> vs <span className="sp-neg">−4.2%</span>
      </>
    ),
    reads: "penalty was backwards",
  },
  {
    signal: "Screen family",
    buckets: "cheap-on-cash-earnings",
    ret: <>+10.0 … +17.6%</>,
    retClass: "sp-pos",
    reads: "the real signal",
  },
  {
    signal: "Screen family",
    buckets: "momentum (retired)",
    ret: <>−14.1%</>,
    retClass: "sp-neg",
    reads: "never held momentum",
  },
];

type BasketCell = { name: string; ytd: string; tone?: "pos" | "neg" };

const BASKET_ROWS: [BasketCell, BasketCell][] = [
  [
    { name: "iv15 deep value", ytd: "+17.6%", tone: "pos" },
    { name: "dcf fcff", ytd: "+4.3%" },
  ],
  [
    { name: "ev / gross profit", ytd: "+14.6%", tone: "pos" },
    { name: "epv", ytd: "+3.6%" },
  ],
  [
    { name: "acquirer's multiple", ytd: "+10.0%", tone: "pos" },
    { name: "earnings yield gap", ytd: "+2.7%" },
  ],
  [
    { name: "ev / gp", ytd: "+10.0%", tone: "pos" },
    { name: "owner earnings", ytd: "+2.3%" },
  ],
  [
    { name: "graham revised", ytd: "+2.3%" },
    { name: "convergence", ytd: "+1.0%" },
  ],
  [
    { name: "r&d capitalised dcf", ytd: "+0.6%" },
    { name: "fundamental momentum", ytd: "−14.1%", tone: "neg" },
  ],
];

const CHANGES: { change: string; what: string; status: string }[] = [
  {
    change: "Catalyst neutrality",
    what:
      "A spent or undated catalyst no longer cuts conviction in the apex. Events live in Basket 13, so the lever could only ever demote here.",
    status: "live",
  },
  {
    change: "Momentum retired",
    what:
      "Screen frozen with its record intact. Its holdings sat mid-range at RSI 49 — it was never holding momentum.",
    status: "live",
  },
  {
    change: "Intake tilt",
    what: "The four cash-earnings families get priority into the underwriting tier. Sized as one factor bet, not four.",
    status: "live",
  },
  {
    change: "Recovery sleeve",
    what: "Paper book that buys the fired-catalyst profile the old rubric discarded.",
    status: "paper",
  },
  {
    change: "Washout exception",
    what: "A deep-drawdown entry on a stable moat is sized at three-quarters rather than half.",
    status: "live",
  },
  {
    change: "Schema hardening",
    what:
      "Catalyst status is now a bare token with its evidence in a separate field — the cause of 31 malformed records.",
    status: "live",
  },
];

/* ── Pieces ───────────────────────────────────────────────────── */

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
          font-size: clamp(30px, 5.2vw, 56px); line-height: 1.0; letter-spacing: 0.02em;
          color: var(--sp-ink); margin: 0 0 20px;
        }
        .sp-standfirst { font-size: clamp(15px, 1.7vw, 18px); line-height: 1.65; color: var(--sp-muted); max-width: 64ch; margin: 0 0 30px; }
        .sp-standfirst strong { color: var(--sp-ink); font-weight: 700; }

        .sp-ledger {
          display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
          gap: 1px; background: var(--sp-line); border: 1px solid var(--sp-line); margin: 0 0 10px;
        }
        .sp-ledger > div { background: var(--sp-panel); padding: 15px 17px; }
        .sp-ledger dt {
          font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.13em;
          text-transform: uppercase; color: var(--sp-faint); margin: 0 0 7px;
        }
        .sp-ledger dd {
          font-family: var(--font-mono); font-size: 23px; font-weight: 600; margin: 0;
          font-variant-numeric: tabular-nums; letter-spacing: -0.02em; color: var(--sp-ink);
        }
        .sp-ledger dd .sub { display: block; font-size: 11px; color: var(--sp-muted); font-weight: 400; letter-spacing: 0; margin-top: 4px; }
        .sp-asof { font-family: var(--font-mono); font-size: 11px; color: var(--sp-faint); margin: 0; }

        .sp-section { padding: 56px 0 0; }
        .sp-h2 {
          font-family: var(--font-mono); font-size: 12px; letter-spacing: 0.15em; text-transform: uppercase;
          color: var(--sp-ink); font-weight: 600; margin: 0 0 8px;
        }
        .sp-h2-n { color: var(--amber); margin-right: 12px; }
        .sp-sectnote { font-size: 14.5px; line-height: 1.65; color: var(--sp-muted); margin: 0 0 24px; max-width: 68ch; }

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
        .sp-stage-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 10px; margin: 0 0 10px; }
        .sp-stage-name { font-weight: 700; font-size: 16.5px; letter-spacing: -0.012em; color: var(--sp-ink); }
        .sp-engine {
          font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.1em; text-transform: uppercase;
          padding: 3px 8px; border: 1px solid var(--sp-line); border-radius: 3px;
          color: var(--sp-faint); background: var(--sp-panel-2);
        }
        .sp-engine-det { color: var(--lavender); border-color: rgba(196,181,253,0.45); }
        .sp-engine-opus { color: var(--amber); border-color: rgba(245,185,66,0.45); }
        .sp-stage p { margin: 0 0 10px; font-size: 14.5px; line-height: 1.65; color: var(--sp-muted); max-width: 70ch; }
        .sp-stage p strong { color: var(--sp-ink); font-weight: 700; }
        .sp-stage p em { color: var(--sp-ink); font-style: italic; }
        .sp-flow {
          font-family: var(--font-mono); font-size: 13px; font-variant-numeric: tabular-nums;
          color: var(--sp-ink); margin: 0 0 12px;
        }
        .sp-arrow { color: var(--amber); padding: 0 8px; }
        .sp-drop { color: var(--red); }
        .sp-bar { height: 9px; background: var(--amber); margin: 0 0 12px; border-radius: 2px; max-width: 100%; }

        .sp-chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 2px 0 0; }
        .sp-chip { font-family: var(--font-mono); font-size: 11px; line-height: 1.5; padding: 3px 8px; border: 1px solid; border-radius: 3px; }
        .sp-chip-hard { color: var(--red); border-color: rgba(239,90,90,0.55); background: rgba(239,90,90,0.10); }
        .sp-chip-size { color: var(--lavender); border-color: rgba(196,181,253,0.55); background: rgba(196,181,253,0.10); }

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
        .sp-table .mono { font-family: var(--font-mono); font-size: 12.5px; }
        .sp-pos { color: var(--green); font-weight: 600; }
        .sp-neg { color: var(--red); font-weight: 600; }
        .sp-flat { color: var(--sp-faint); }

        /* books */
        .sp-books { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 14px; }
        .sp-book { border: 1px solid var(--sp-line); border-top: 3px solid var(--amber); border-radius: 6px; background: var(--sp-panel); padding: 17px 19px; }
        .sp-book-paper { border-top-color: var(--lavender); }
        .sp-book h3 { font-size: 15px; margin: 0 0 4px; letter-spacing: -0.01em; color: var(--sp-ink); font-weight: 700; }
        .sp-book .role { font-family: var(--font-mono); font-size: 10px; letter-spacing: 0.1em; text-transform: uppercase; color: var(--sp-faint); margin: 0 0 13px; }
        .sp-book .stat { font-family: var(--font-mono); font-size: 19px; font-variant-numeric: tabular-nums; margin: 0; color: var(--sp-ink); }
        .sp-book .stat span { font-size: 11.5px; color: var(--sp-faint); }
        .sp-book .blurb { font-size: 13px; line-height: 1.6; color: var(--sp-muted); margin: 11px 0 0; }

        /* verdict */
        .sp-verdict {
          border: 1px solid var(--sp-line); border-left: 3px solid var(--amber); border-radius: 6px;
          background: var(--sp-panel); padding: 19px 21px; margin: 0 0 22px;
        }
        .sp-verdict p { margin: 0; font-size: 14.5px; line-height: 1.65; color: var(--sp-muted); max-width: 72ch; }
        .sp-verdict p + p { margin-top: 11px; }
        .sp-verdict strong { color: var(--sp-ink); font-weight: 700; }

        .sp-foot {
          border-top: 1px solid var(--sp-line); margin-top: 56px; padding: 20px 0 0;
          font-family: var(--font-mono); font-size: 11.5px; line-height: 1.8; color: var(--sp-faint);
        }
        .sp-foot code { background: var(--sp-panel-2); padding: 1px 5px; border: 1px solid var(--sp-line); border-radius: 3px; color: var(--sp-muted); }

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
          .sp-ledger dd { font-size: 19px; }
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
        <p className="sp-eyebrow">Speculair · system map</p>
        <h1 className="sp-h1">How 2,520 names become 9 seats</h1>
        <p className="sp-standfirst">
          The pipeline is a <strong>subtractive refinery</strong>: mechanical screens select
          candidates, a multi-agent debate underwrites a capped subset, and a stack of deterministic
          gates removes material at every stage. Nothing downstream can add a name the screens never
          surfaced — which is why the gates, not the models, decide what you own.
        </p>

        <dl className="sp-ledger">
          {LEDGER.map((c) => (
            <div key={c.label}>
              <dt>{c.label}</dt>
              <dd>
                {c.value}
                <span className="sub">{c.sub}</span>
              </dd>
            </div>
          ))}
        </dl>
        <p className="sp-asof">as of {AS_OF} · 181 debate records in the current pass</p>

        {/* ── 01 The refinery ──────────────────────────────────── */}
        <section className="sp-section">
          <SectionHead n="01" title="The refinery">
            Each stage names its engine — deterministic code, or which model seat runs it. The chips
            show what that stage can remove: <span style={{ color: "var(--red)" }}>hard block</span>{" "}
            ends a seat, <span style={{ color: "var(--lavender)" }}>size cut</span> shrinks it.
          </SectionHead>

          {STAGES.map((s) => (
            <div key={s.name} className="sp-stage">
              <div className="sp-stage-head">
                <span className="sp-stage-name">{s.name}</span>
                <span className={`sp-engine ${s.engineKind === "opus" ? "sp-engine-opus" : "sp-engine-det"}`}>{s.engine}</span>
              </div>
              {s.bar !== undefined && <div className="sp-bar" style={{ width: `${s.bar}%` }} />}
              {s.flow && <div className="sp-flow">{s.flow}</div>}
              {s.body}
              {s.chips && (
                <div className="sp-chips">
                  {s.chips.map((c) => (
                    <span key={c.label} className={`sp-chip ${c.kind === "hard" ? "sp-chip-hard" : "sp-chip-size"}`}>
                      {c.label}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </section>

        {/* ── 02 Where the capital lands ───────────────────────── */}
        <section className="sp-section">
          <SectionHead n="02" title="Where the capital lands">
            Five books, each with its own funnel, sizing and tracked NAV. They do not compete for the
            same names — the separation is enforced in code, not by convention.
          </SectionHead>
          <div className="sp-books">
            {BOOKS.map((b) => (
              <div key={b.name} className={`sp-book${b.paper ? " sp-book-paper" : ""}`}>
                <h3>{b.name}</h3>
                <p className="role">{b.role}</p>
                <p className="stat">
                  {b.stat} <span>{b.statSub}</span>
                </p>
                <p className="blurb">{b.blurb}</p>
              </div>
            ))}
          </div>
        </section>

        {/* ── 03 What actually predicts returns ────────────────── */}
        <section className="sp-section">
          <SectionHead n="03" title="What actually predicts returns">
            Measured on 2,151 dated debate records across 422 names and 18 weekly runs, joined to
            realised prices. Confidence intervals cluster on the name, because weekly carry-forwards
            repeat the same call. One regime, roughly seven weeks — read it as a first read, not a law.
          </SectionHead>

          <div className="sp-verdict">
            <p>
              <strong>The mechanical screens earn the return; the debate layer mostly subtracts.</strong>{" "}
              The screens&apos; own baskets range from +17.6% to −14.1% and separate cleanly by family.
              The debate&apos;s grades do not separate at all.
            </p>
            <p>
              Its one demonstrated strength is <strong>vetoing</strong>: the forensic and skeptic layers
              correctly quarantined names with live fraud and DOJ actions, including several that rose
              anyway. That is a risk function working as designed.
            </p>
          </div>

          <div className="sp-scroller" style={{ marginBottom: 18 }}>
            <table className="sp-table">
              <thead>
                <tr>
                  <th>Signal</th>
                  <th>Buckets</th>
                  <th className="num">Forward return</th>
                  <th>Reads as</th>
                </tr>
              </thead>
              <tbody>
                {SIGNAL_ROWS.map((r) => (
                  <tr key={`${r.signal}-${r.buckets}`}>
                    <td>{r.signal}</td>
                    <td className="mono">{r.buckets}</td>
                    <td className={`num${r.retClass ? ` ${r.retClass}` : ""}`}>{r.ret}</td>
                    <td>{r.reads}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="sp-scroller">
            <table className="sp-table">
              <thead>
                <tr>
                  <th>Basket</th>
                  <th className="num">YTD</th>
                  <th>Basket</th>
                  <th className="num">YTD</th>
                </tr>
              </thead>
              <tbody>
                {BASKET_ROWS.map(([a, b]) => (
                  <tr key={a.name}>
                    <td className="mono">{a.name}</td>
                    <td className={`num${a.tone ? ` sp-${a.tone}` : ""}`}>{a.ytd}</td>
                    <td className="mono">{b.name}</td>
                    <td className={`num${b.tone ? ` sp-${b.tone}` : ""}`}>{b.ytd}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* ── 04 The blind spot ────────────────────────────────── */}
        <section className="sp-section">
          <SectionHead n="04" title="The blind spot" />
          <p className="sp-sectnote">
            Of 275 names in the scan that rose 50%+ off their low and sit near their high, the whole
            system captured 13 — a 5% capture rate. Of the 262 missed,{" "}
            <strong style={{ color: "var(--sp-ink)", fontWeight: 700 }}>
              249 carry a margin of safety at or below zero
            </strong>
            : they are mechanically invisible to every value screen precisely <em style={{ color: "var(--sp-ink)" }}>because</em> they already rose.
          </p>
          <p className="sp-sectnote" style={{ marginBottom: 0 }}>
            This is not fixable at the debate or Director layer, and chasing it would mean abandoning
            the value anchor the platform is built on. It is a universe-construction question —
            including spin-offs that never re-enter after separation, and price anchors that need a
            sanity check.
          </p>
        </section>

        {/* ── 05 Changed this week ─────────────────────────────── */}
        <section className="sp-section">
          <SectionHead n="05" title="Changed this week" />
          <div className="sp-scroller">
            <table className="sp-table">
              <thead>
                <tr>
                  <th>Change</th>
                  <th>What it does</th>
                  <th className="mono">Status</th>
                </tr>
              </thead>
              <tbody>
                {CHANGES.map((c) => (
                  <tr key={c.change}>
                    <td>{c.change}</td>
                    <td>{c.what}</td>
                    <td className="mono">{c.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* ── Sources ──────────────────────────────────────────── */}
        <p className="sp-foot">
          Sources — pipeline: <code>backend/weekly_opus_refresh.py</code>, <code>_regime_post.py</code>,{" "}
          <code>_value_post.py</code>, <code>_numeric_core.py</code>. Evidence:{" "}
          <code>backend/_opus_debate/cohort_joins.py</code> over <code>speculair_debate_history/</code>.
          Decision rule and baseline: <code>APEX_DECISION_RULE.md</code>, <code>_prefork_snapshot/</code>.
          <br />
          Counts are live as of {AS_OF}. Returns are realised forward returns on paper-tracked books,
          not traded performance.
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
