// Static SVG visuals for the /welcome landing page. Pure server-safe JSX:
// no hooks, no props, no client state. Authored against the brand palette
// (deep-sea #0a1817 surface; ink #f3ede4; green/lavender/amber accents).
// All data shapes are invented and illustrative.


export function HeroGapChart() {
  return (
    <svg
      viewBox="0 0 1040 300"
      width="100%"
      style={{ display: "block", height: "auto" }}
      role="img"
      aria-label="A stock price trading well below a fair value range estimated by twelve valuation methods, then closing the gap after a catalyst event"
    >
      {/* horizontal grid */}
      <line x1={40} y1={60} x2={1010} y2={60} stroke="#16302b" strokeWidth={1} />
      <line x1={40} y1={130} x2={1010} y2={130} stroke="#16302b" strokeWidth={1} />
      <line x1={40} y1={200} x2={1010} y2={200} stroke="#16302b" strokeWidth={1} />

      {/* time axis baseline with quarterly ticks, no labels */}
      <line x1={40} y1={270} x2={1010} y2={270} stroke="#1f3a35" strokeWidth={1} />
      <line x1={40} y1={270} x2={40} y2={274} stroke="#1f3a35" strokeWidth={1} />
      <line x1={201.7} y1={270} x2={201.7} y2={274} stroke="#1f3a35" strokeWidth={1} />
      <line x1={363.3} y1={270} x2={363.3} y2={274} stroke="#1f3a35" strokeWidth={1} />
      <line x1={525} y1={270} x2={525} y2={274} stroke="#1f3a35" strokeWidth={1} />
      <line x1={686.7} y1={270} x2={686.7} y2={274} stroke="#1f3a35" strokeWidth={1} />
      <line x1={848.3} y1={270} x2={848.3} y2={274} stroke="#1f3a35" strokeWidth={1} />
      <line x1={1010} y1={270} x2={1010} y2={274} stroke="#1f3a35" strokeWidth={1} />

      {/* faint gap shading between price and band lower edge, up to the catalyst */}
      <path
        d="M 40 118
           C 200 115, 340 116, 500 112
           C 600 109.5, 660 108.6, 728 108
           L 728 221
           C 720 223, 710 225, 698 228
           C 676 233, 654 237, 632 233
           C 610 229, 588 225, 566 229
           C 544 233, 522 239, 500 240
           C 478 241, 456 237, 434 232
           C 412 227, 390 223, 368 228
           C 346 233, 324 238, 302 235
           C 280 232, 258 226, 236 220
           C 214 214, 192 209, 170 213
           C 148 217, 126 222, 104 219
           C 82 216, 62 210, 40 206
           Z"
        fill="#14b87a"
        fillOpacity={0.04}
        stroke="none"
      />

      {/* fair value band area */}
      <path
        d="M 40 80
           C 200 77, 340 78, 500 74
           C 660 70, 840 68, 1010 63
           L 1010 104
           C 920 105.6, 830 107, 728 108
           C 660 108.6, 600 109.5, 500 112
           C 340 116, 200 115, 40 118
           Z"
        fill="#14b87a"
        fillOpacity={0.12}
        stroke="none"
      />

      {/* band edges */}
      <path
        d="M 40 80 C 200 77, 340 78, 500 74 C 660 70, 840 68, 1010 63"
        fill="none"
        stroke="#14b87a"
        strokeOpacity={0.5}
        strokeWidth={1}
      />
      <path
        d="M 40 118 C 200 115, 340 116, 500 112 C 600 109.5, 660 108.6, 728 108 C 830 107, 920 105.6, 1010 104"
        fill="none"
        stroke="#14b87a"
        strokeOpacity={0.5}
        strokeWidth={1}
      />

      {/* gap measurement line, early on */}
      <line
        x1={210}
        y1={122}
        x2={210}
        y2={204}
        stroke="#6b7d7a"
        strokeOpacity={0.8}
        strokeWidth={1}
        strokeDasharray="2 4"
      />

      {/* price line */}
      <path
        d="M 40 206
           C 62 210, 82 216, 104 219
           C 126 222, 148 217, 170 213
           C 192 209, 214 214, 236 220
           C 258 226, 280 232, 302 235
           C 324 238, 346 233, 368 228
           C 390 223, 412 227, 434 232
           C 456 237, 478 241, 500 240
           C 522 239, 544 233, 566 229
           C 588 225, 610 229, 632 233
           C 654 237, 676 233, 698 228
           C 710 225, 720 223, 728 221
           C 748 216, 768 206, 788 193
           C 808 180, 828 170, 848 161
           C 868 152, 888 147, 908 142
           C 928 137, 948 133, 968 128
           C 986 124, 998 120, 1010 116"
        fill="none"
        stroke="#f3ede4"
        strokeWidth={2}
        strokeLinecap="round"
      />

      {/* catalyst marker */}
      <circle cx={728} cy={221} r={11} fill="#f5b942" fillOpacity={0.12} />
      <path d="M 728 214.5 L 734.5 221 L 728 227.5 L 721.5 221 Z" fill="#f5b942" />

      {/* catalyst leader line */}
      <line x1={728} y1={232} x2={728} y2={249} stroke="#6b7d7a" strokeWidth={1} />

      {/* labels */}
      <text
        x={40}
        y={52}
        fill="#b4c1be"
        fontFamily="JetBrains Mono, monospace"
        fontSize={12}
        letterSpacing="0.14em"
      >
        FAIR VALUE RANGE
      </text>
      <text
        x={40}
        y={68}
        fill="#6b7d7a"
        fontFamily="JetBrains Mono, monospace"
        fontSize={11}
        letterSpacing="0.14em"
      >
        12 METHODS
      </text>
      <text
        x={40}
        y={238}
        fill="#b4c1be"
        fontFamily="JetBrains Mono, monospace"
        fontSize={11}
        letterSpacing="0.14em"
      >
        PRICE
      </text>
      <text
        x={218}
        y={167}
        fill="#f3ede4"
        fontFamily="JetBrains Mono, monospace"
        fontSize={12}
      >
        +62%
      </text>
      <text
        x={728}
        y={260}
        fill="#b4c1be"
        fontFamily="JetBrains Mono, monospace"
        fontSize={11}
        letterSpacing="0.14em"
        textAnchor="middle"
      >
        CATALYST
      </text>
    </svg>
  );
}

export function ConvergenceStrip() {
  return (
    <svg
      viewBox="0 0 1040 150"
      width="100%"
      style={{ display: "block", height: "auto" }}
      role="img"
      aria-label="Twelve fair value estimates clustering on a value axis well above the current price"
    >
      {/* soft band behind the estimate cluster */}
      <rect x="548" y="45" width="344" height="60" rx="4" fill="#14b87a" fillOpacity="0.10" />

      {/* value axis baseline */}
      <line x1="40" y1="75" x2="1000" y2="75" stroke="#1f3a35" strokeWidth="1" />

      {/* current price marker */}
      <line x1="300" y1="62" x2="300" y2="88" stroke="#f3ede4" strokeWidth="2" strokeLinecap="round" />

      {/* discount bracket between price and cluster */}
      <line x1="312" y1="58" x2="540" y2="58" stroke="#6b7d7a" strokeWidth="1" />
      <line x1="312" y1="58" x2="312" y2="64" stroke="#6b7d7a" strokeWidth="1" />
      <line x1="540" y1="58" x2="540" y2="64" stroke="#6b7d7a" strokeWidth="1" />

      {/* twelve estimates, jittered so overlaps read separately */}
      <circle cx="566" cy="75" r="5" fill="#14b87a" fillOpacity="0.85" />
      <circle cx="600" cy="72" r="5" fill="#14b87a" fillOpacity="0.85" />
      <circle cx="634" cy="78" r="5" fill="#14b87a" fillOpacity="0.85" />
      <circle cx="660" cy="71" r="5" fill="#14b87a" fillOpacity="0.85" />
      <circle cx="678" cy="80" r="5" fill="#14b87a" fillOpacity="0.85" />
      <circle cx="694" cy="69" r="5" fill="#14b87a" fillOpacity="0.85" />
      <circle cx="722" cy="70" r="5" fill="#14b87a" fillOpacity="0.85" />
      <circle cx="738" cy="79" r="5" fill="#14b87a" fillOpacity="0.85" />
      <circle cx="756" cy="72" r="5" fill="#14b87a" fillOpacity="0.85" />
      <circle cx="792" cy="76" r="5" fill="#14b87a" fillOpacity="0.85" />
      <circle cx="848" cy="74" r="5" fill="#14b87a" fillOpacity="0.85" />

      {/* median estimate */}
      <circle cx="708" cy="77" r="5" fill="#c4b5fd" fillOpacity="0.85" />

      {/* leader from median label to the lavender dot */}
      <line x1="708" y1="86" x2="708" y2="114" stroke="#6b7d7a" strokeWidth="1" strokeOpacity="0.8" />

      <text
        x="300"
        y="108"
        textAnchor="middle"
        fill="#b4c1be"
        fontFamily="JetBrains Mono, monospace"
        fontSize="11"
        letterSpacing="0.14em"
      >
        PRICE
      </text>

      <text
        x="426"
        y="48"
        textAnchor="middle"
        fill="#f3ede4"
        fontFamily="JetBrains Mono, monospace"
        fontSize="11"
        letterSpacing="0.14em"
      >
        DISCOUNT 41%
      </text>

      <text
        x="720"
        y="34"
        textAnchor="middle"
        fill="#b4c1be"
        fontFamily="JetBrains Mono, monospace"
        fontSize="11"
        letterSpacing="0.14em"
      >
        12 ESTIMATES
      </text>

      <text
        x="708"
        y="128"
        textAnchor="middle"
        fill="#6b7d7a"
        fontFamily="JetBrains Mono, monospace"
        fontSize="11"
        letterSpacing="0.14em"
      >
        MEDIAN
      </text>
    </svg>
  );
}

export function CatalystTimeline() {
  return (
    <svg
      viewBox="0 0 1040 140"
      width="100%"
      style={{ display: "block", height: "auto" }}
      role="img"
      aria-label="Event-driven position timeline: entry marker, a defined window in which the catalyst is expected, the expected event, and preset exit rules, marked nightly"
    >
      {/* main timeline */}
      <line x1="48" y1="78" x2="1000" y2="78" stroke="#1f3a35" strokeWidth="1" />

      {/* nightly marks: three near-invisible ticks above the line */}
      <line x1="260" y1="69" x2="260" y2="75" stroke="#6b7d7a" strokeWidth="1" strokeOpacity="0.5" />
      <line x1="330" y1="69" x2="330" y2="75" stroke="#6b7d7a" strokeWidth="1" strokeOpacity="0.5" />
      <line x1="400" y1="69" x2="400" y2="75" stroke="#6b7d7a" strokeWidth="1" strokeOpacity="0.5" />

      {/* defined window band */}
      <rect x="480" y="58" width="340" height="40" fill="#f5b942" fillOpacity="0.12" />
      <line x1="480" y1="58" x2="480" y2="98" stroke="#f5b942" strokeWidth="1" strokeOpacity="0.45" />
      <line x1="820" y1="58" x2="820" y2="98" stroke="#f5b942" strokeWidth="1" strokeOpacity="0.45" />

      {/* thin amber underline beneath the band, gapped for the event leader */}
      <line x1="480" y1="104" x2="632" y2="104" stroke="#f5b942" strokeWidth="1" strokeOpacity="0.45" />
      <line x1="648" y1="104" x2="820" y2="104" stroke="#f5b942" strokeWidth="1" strokeOpacity="0.45" />

      {/* entry marker */}
      <circle cx="140" cy="78" r="4" fill="#f3ede4" />

      {/* expected event: amber diamond */}
      <path d="M 640 72 L 646 78 L 640 84 L 634 78 Z" fill="#f5b942" />

      {/* leader from diamond down to its label */}
      <line x1="640" y1="90" x2="640" y2="116" stroke="#6b7d7a" strokeWidth="1" strokeOpacity="0.7" />

      {/* latest-exit tick */}
      <line x1="940" y1="71" x2="940" y2="85" stroke="#6b7d7a" strokeWidth="1" />

      {/* labels */}
      <text
        x="48"
        y="60"
        fill="#6b7d7a"
        fontFamily="JetBrains Mono, monospace"
        fontSize="11"
        letterSpacing="0.14em"
      >
        MARKED NIGHTLY
      </text>
      <text
        x="140"
        y="102"
        textAnchor="middle"
        fill="#b4c1be"
        fontFamily="JetBrains Mono, monospace"
        fontSize="11"
        letterSpacing="0.14em"
      >
        ENTRY
      </text>
      <text
        x="650"
        y="46"
        textAnchor="middle"
        fill="#b4c1be"
        fontFamily="JetBrains Mono, monospace"
        fontSize="11"
        letterSpacing="0.14em"
      >
        DEFINED WINDOW
      </text>
      <text
        x="640"
        y="131"
        textAnchor="middle"
        fill="#6b7d7a"
        fontFamily="JetBrains Mono, monospace"
        fontSize="11"
        letterSpacing="0.14em"
      >
        EXPECTED EVENT
      </text>
      <text
        x="940"
        y="104"
        textAnchor="middle"
        fill="#6b7d7a"
        fontFamily="JetBrains Mono, monospace"
        fontSize="11"
        letterSpacing="0.14em"
      >
        EXIT RULES SET
      </text>
    </svg>
  );
}

export function ReviewFlow() {
  return (
    <svg
      viewBox="0 0 1040 170"
      width="100%"
      style={{ display: "block", height: "auto" }}
      role="img"
      aria-label="Publication pipeline: ideas move from screen to analysis to adversarial review and only then to the board; failures are dropped"
    >
      {/* connectors between stations */}
      <line x1="190" y1="70" x2="310" y2="70" stroke="#1f3a35" strokeWidth="1" />
      <line x1="460" y1="70" x2="580" y2="70" stroke="#1f3a35" strokeWidth="1" />
      <line x1="730" y1="70" x2="850" y2="70" stroke="#1f3a35" strokeWidth="1" />

      {/* drop branch from REVIEW: down, then softly right to the ghost outcome */}
      <path
        d="M 655 92 L 655 114 L 716 138"
        fill="none"
        stroke="#6b7d7a"
        strokeWidth="1"
        strokeDasharray="2 4"
        strokeLinecap="round"
      />

      {/* station rects */}
      <rect x="40" y="48" width="150" height="44" rx="6" fill="none" stroke="#1f3a35" strokeWidth="1" />
      <rect x="310" y="48" width="150" height="44" rx="6" fill="none" stroke="#1f3a35" strokeWidth="1" />
      <rect x="580" y="48" width="150" height="44" rx="6" fill="none" stroke="#1f3a35" strokeWidth="1" />
      <rect x="850" y="48" width="150" height="44" rx="6" fill="#14b87a" fillOpacity="0.08" stroke="#14b87a" strokeWidth="1" />

      {/* junction dots where connectors meet rects */}
      <circle cx="190" cy="70" r="3" fill="#b4c1be" />
      <circle cx="310" cy="70" r="3" fill="#b4c1be" />
      <circle cx="460" cy="70" r="3" fill="#b4c1be" />
      <circle cx="580" cy="70" r="3" fill="#b4c1be" />
      <circle cx="730" cy="70" r="3" fill="#b4c1be" />
      <circle cx="850" cy="70" r="3" fill="#b4c1be" />
      <circle cx="655" cy="92" r="3" fill="#b4c1be" />

      {/* tiny tick from the ADVERSARIAL note down to the REVIEW station */}
      <line x1="655" y1="40" x2="655" y2="48" stroke="#1f3a35" strokeWidth="1" />

      {/* red tick before the DROPPED ghost label */}
      <line x1="724" y1="138" x2="736" y2="138" stroke="#ef5a5a" strokeWidth="2" strokeLinecap="round" />

      {/* labels */}
      <text
        x="115"
        y="74"
        textAnchor="middle"
        fill="#b4c1be"
        fontFamily="JetBrains Mono, monospace"
        fontSize="12"
        letterSpacing="0.14em"
      >
        SCREEN
      </text>
      <text
        x="385"
        y="74"
        textAnchor="middle"
        fill="#b4c1be"
        fontFamily="JetBrains Mono, monospace"
        fontSize="12"
        letterSpacing="0.14em"
      >
        ANALYSIS
      </text>
      <text
        x="655"
        y="74"
        textAnchor="middle"
        fill="#b4c1be"
        fontFamily="JetBrains Mono, monospace"
        fontSize="12"
        letterSpacing="0.14em"
      >
        REVIEW
      </text>
      <text
        x="925"
        y="74"
        textAnchor="middle"
        fill="#f3ede4"
        fontFamily="JetBrains Mono, monospace"
        fontSize="12"
        letterSpacing="0.14em"
      >
        BOARD
      </text>
      <text
        x="655"
        y="34"
        textAnchor="middle"
        fill="#6b7d7a"
        fontFamily="JetBrains Mono, monospace"
        fontSize="11"
        letterSpacing="0.14em"
      >
        ADVERSARIAL
      </text>
      <text
        x="744"
        y="142"
        fill="#6b7d7a"
        fontFamily="JetBrains Mono, monospace"
        fontSize="11"
        letterSpacing="0.14em"
      >
        DROPPED
      </text>
    </svg>
  );
}
