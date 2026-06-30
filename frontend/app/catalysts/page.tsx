"use client";
import { useState, useEffect, useMemo, useRef } from "react";
import { 
  Compass, Search, Zap, Target, Award, Calendar, 
  ExternalLink, TrendingUp, AlertCircle, RefreshCw, 
  HelpCircle, ChevronRight, CheckCircle2, AlertTriangle, PlayCircle,
  Star, Trash2
} from "lucide-react";
import { Tip, Term, rrDisplay, toneColor } from "../components/Tip";
import { termLabel } from "../data/voice";
import { BASKET13 } from "../data/basket13";

// ── Basket 13 (catalyst sleeve, paper) — open seats keyed by symbol for chips ──
const B13: any = BASKET13 || {};
const B13_SEATS: Record<string, any> = {};   // held seats only — resting limits are not positions
(B13.entries || []).forEach((e: any) => { if (!e.resolution && e.status !== "PENDING_LIMIT") B13_SEATS[e.symbol] = e; });
const fmtB13Expr = (e: any) => {
  const x = e?.expression || {};
  const t = String(x.type || "equity").replace(/_/g, " ");
  return x.expiry ? `${t} ${String(x.expiry).slice(2)}` : t;
};
const fmtB13RR = (e: any) =>
  e?.expected_rr != null ? `${Number(e.expected_rr).toFixed(2)}:1`
  : e?.expected_ev != null ? `EV ${(Number(e.expected_ev) * 100).toFixed(0)}%` : "—";


// ── Theme definitions matching speculair system ─────────────────────────────
const T = {
  bg: "var(--bg)",
  card: "var(--bg-surface)",
  border: "var(--border)",
  text: "var(--text)",
  muted: "var(--text-muted)",
  light: "var(--text-light)",
  green: "var(--green)",
  greenLight: "var(--green-light)",
  greenBorder: "var(--green-border)",
  red: "var(--red)",
  redLight: "var(--red-light)",
  amber: "var(--amber)",
  amberLight: "var(--amber-light)",
  purple: "var(--purple)",
  purpleLight: "var(--purple-light)",
  blue: "var(--blue)",
  mono: "var(--font-mono, 'JetBrains Mono', monospace)"
};

interface BloomCatalyst {
  title: string;
  detected: boolean;
  description: string;
  evidence: string;
}

interface LoebCriterion {
  rating?: string;
  ratio?: string;
  detected?: boolean;
  analysis: string;
}

interface OptionsSignals {
  iv_current: number | null;
  skew_25d: number | null;
  term_structure: string;
  pc_oi_ratio: number | null;
  total_oi: number | null;
  implied_earnings_move_pct: number | null;
  market_sentiment_flag: string;
  overall_interpretation: string;
}

interface RecentEvent {
  date: string;
  type: "filing" | "news" | "transcript";
  title: string;
  link: string;
}

interface CatalystScanReport {
  symbol: string;
  company_name: string;
  price: number;
  market_cap: number;
  catalyst_density_score: number;
  upside_downside_ratio: number;
  analysis_summary: string;
  recommendation: "BUY" | "WATCH" | "HOLD" | "SELL";
  bloom_catalysts: {
    catalyst_1: BloomCatalyst;
    catalyst_2: BloomCatalyst;
    catalyst_3: BloomCatalyst;
  };
  loeb_criteria: {
    catalyst_density: LoebCriterion;
    sum_of_parts: LoebCriterion;
    activism_potential: LoebCriterion;
    risk_reward: LoebCriterion;
  };
  options_signals: OptionsSignals;
  recent_events: RecentEvent[];
  cache_timestamp?: string;
  is_merger_arb?: boolean;
  catalyst_nature?: "mechanical_execution" | "pricing_dislocation";
  catalyst_nature_rationale?: string;
  re_rate_status?: "pending" | "partial" | "complete";
  merger_arb_data?: {
    acquirer_symbol?: string;
    acquirer_name?: string;
    acquirer_price?: number;
    cash_component?: number;
    stock_component_ratio?: number;
    implied_deal_value?: number;
    gross_spread_val?: number;
    gross_spread_pct?: number;
    expected_close?: string;
    unhedged_downside?: number;
    unhedged_rr_asymmetry?: string;
    pre_announce_price?: number;
    deal_status?: string;
  } | null;
  convergence_score?: number;
  independent_track_count?: number;
  unfired_independent_track_count?: number;
  is_dher_pattern?: boolean;
  tracks?: Array<{
    track_type: string;
    evidence: string;
    counterparty: string | null;
    dated_event: boolean;
    event_date: string | null;
    fired: boolean;
    independence_score?: number;
  }>;
  options_confirmation_score?: number;
  credit_health?: {
    grade?: string;
    net_debt_ebitda?: number;
    distress_flags?: string[];
  };
  adjusted_loeb_score?: number;
  final_adjusted_loeb?: number;
  score_adjustments?: ScoreAdjustment[];
  distressed_setup_flag?: boolean;
  credit_event_risk_flag?: boolean;
  credit_health_layer3_adjustment_applied?: boolean;
}

interface ScoreAdjustment {
  factor: string;
  adjustment: number;
  reason: string;
}

interface Candidate {
  symbol: string;
  name: string;
  price: number | null;
  market_cap: number | null;
  catalyst_score: number;
  adjusted_loeb_score?: number;
  score_adjustments?: ScoreAdjustment[];
  flags: string[];
  has_special_flag: boolean;
  categories?: string[];
  priority?: number;
  upside?: number;
  rr_ratio?: number | null;
  is_scanned?: boolean;
  is_merger_arb?: boolean;
  is_dher_pattern?: boolean;
  convergence_score?: number | null;
  resolution_driver?: string;   // §3 conviction tag (post-board pass)
  board_priority?: number;      // §3 lane-tilt sort key (score - tilt*(lane_priority-1))
  edge_grade?: string;          // phase-2 computed edge (H/M/L) vs live price
  computed_rr?: number | null;  // phase-2 lane-aware R:R (ratio lanes)
  ev_pct?: number | null;       // phase-2 binary EV%
  win_prob?: number | null;
  payoff?: number | null;
  valuation_method?: string;
  edge_flags?: string[];
  lane_canon?: string;
}

export default function CatalystWatch() {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loadingCandidates, setLoadingCandidates] = useState(true);
  const [selectedSymbol, setSelectedSymbol] = useState<string>("MBGL");
  const [report, setReport] = useState<CatalystScanReport | null>(null);
  const [loadingScan, setLoadingScan] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const [customSymbol, setCustomSymbol] = useState("");
  
  // Filtering and sorting state
  const [categoryFilter, setCategoryFilter] = useState<string>("All");
  const [sortField, setSortField] = useState<"score" | "asymmetry" | "mcap">("score");
  const [showMergerArbs, setShowMergerArbs] = useState<boolean>(true);
  const [showActionable, setShowActionable] = useState<boolean>(false);  // phase-2 edge filter
  const [b13Open, setB13Open] = useState<boolean>(true);                 // Basket 13 sleeve panel
  const [view, setView] = useState<"basket" | "detail">("basket");       // basket = the default landing view
  const [sidebarOpen, setSidebarOpen] = useState<boolean>(false);        // scanning-candidates rail (off by default — let the basket breathe)
  const [liveQuotes, setLiveQuotes] = useState<Record<string, any>>({}); // live ticker for the basket seats

  // Live ticker for the Basket 13 seats + the on-deck watchlist (reuses /api/quotes — FMP batch-quote proxy; 60s refresh)
  useEffect(() => {
    const syms = Array.from(new Set([...Object.keys(B13_SEATS), ...((B13.watchlist || []).map((w: any) => w.symbol))]));
    if (!syms.length) return;
    let stop = false;
    const pull = () =>
      fetch(`/api/quotes?symbols=${encodeURIComponent(syms.join(","))}&light=1`)
        .then(r => r.json())
        .then(d => {
          if (stop || !Array.isArray(d?.quotes)) return;
          const m: Record<string, any> = {};
          d.quotes.forEach((q: any) => { m[q.symbol] = q; });
          setLiveQuotes(m);
        })
        .catch(() => {});
    pull();
    const iv = setInterval(pull, 60000);
    return () => { stop = true; clearInterval(iv); };
  }, []);
  const [customAcquirerPrice, setCustomAcquirerPrice] = useState<number | "">("");
  const [scanProgress, setScanProgress] = useState<{ status: string, total_symbols: number, completed_count: number, current_symbol: string, speed_stats: string, estimated_remaining_seconds: number } | null>(null);
  
  // Cache of scans to prevent double fetching during session
  const scanCacheRef = useRef<Record<string, CatalystScanReport>>({});

  const [watchlist, setWatchlist] = useState<Candidate[]>([]);
  const [recentScans, setRecentScans] = useState<Candidate[]>([]);

  // Format cache revision dates
  const formatCacheDate = (isoString?: string) => {
    if (!isoString) return "Never";
    try {
      const d = new Date(isoString);
      return d.toLocaleString();
    } catch (e) {
      return isoString;
    }
  };

  // Propagate updated catalyst scores across all active lists
  const propagateScoreUpdate = (symbol: string, newScore: number) => {
    const sym = symbol.toUpperCase().trim();
    setCandidates((prev) => 
      prev.map((c) => c.symbol === sym ? { ...c, catalyst_score: newScore, adjusted_loeb_score: newScore, is_scanned: true } : c)
    );
    setWatchlist((prev) => {
      const updated = prev.map((w) => w.symbol === sym ? { ...w, catalyst_score: newScore, adjusted_loeb_score: newScore, is_scanned: true } : w);
      localStorage.setItem("catalyst_watchlist", JSON.stringify(updated));
      return updated;
    });
    setRecentScans((prev) => 
      prev.map((r) => r.symbol === sym ? { ...r, catalyst_score: newScore, adjusted_loeb_score: newScore, is_scanned: true } : r)
    );
  };

  // Force a fresh scan on-demand bypassing the cache
  const handleForceRefresh = (symbol: string) => {
    if (!symbol) return;
    setLoadingScan(true);
    setScanError(null);
    fetch(`/api/catalysts/scan?symbol=${symbol}&refresh=true`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP error ${r.status}`);
        return r.json();
      })
      .then((data: CatalystScanReport) => {
        setReport(data);
        setCustomAcquirerPrice(data.merger_arb_data?.acquirer_price ?? "");
        scanCacheRef.current[symbol] = data;
        setLoadingScan(false);
        addRecentScan(data);
        propagateScoreUpdate(data.symbol, data.catalyst_density_score);
      })
      .catch((err) => {
        console.error(`Failed to refresh scan for ${symbol}`, err);
        setScanError(`Failed to refresh event-driven scan for ${symbol}. Please try again.`);
        setLoadingScan(false);
      });
  };

  // Load watchlist on mount
  useEffect(() => {
    if (typeof window !== "undefined") {
      const saved = localStorage.getItem("catalyst_watchlist");
      if (saved) {
        try {
          setWatchlist(JSON.parse(saved));
        } catch (e) {
          console.error("Failed to parse watchlist", e);
        }
      }
    }
  }, []);

  // Poll universe scan progress
  useEffect(() => {
    const checkProgress = () => {
      fetch("/api/catalysts/progress")
        .then((r) => r.ok ? r.json() : null)
        .then((data) => {
          if (data) {
            setScanProgress(data);
          }
        })
        .catch((err) => console.error("Failed to fetch scan progress", err));
    };
    checkProgress();
    const interval = setInterval(checkProgress, 3000);
    return () => clearInterval(interval);
  }, []);

  const toggleWatchlist = (symbol: string, name: string, score: number, price?: number | null, market_cap?: number | null, is_merger_arb?: boolean) => {
    const sym = symbol.toUpperCase().trim();
    const exists = watchlist.some((item) => item.symbol === sym);
    let updated: Candidate[];
    if (exists) {
      updated = watchlist.filter((item) => item.symbol !== sym);
    } else {
      const cachedCand = candidates.find(c => c.symbol === sym);
      const isArb = is_merger_arb !== undefined ? is_merger_arb : (cachedCand?.is_merger_arb ?? false);
      updated = [
        ...watchlist,
        {
          symbol: sym,
          name: name || "Unknown Company",
          catalyst_score: score,
          price: price ?? null,
          market_cap: market_cap ?? null,
          flags: ["Watchlist"],
          has_special_flag: true,
          is_merger_arb: isArb
        }
      ];
      // Remove from recentScans since it's now watched
      setRecentScans((prev) => prev.filter((item) => item.symbol !== sym));
    }
    setWatchlist(updated);
    localStorage.setItem("catalyst_watchlist", JSON.stringify(updated));
  };

  const addRecentScan = (data: CatalystScanReport) => {
    const sym = data.symbol.toUpperCase().trim();
    if (!sym) return;
    
    setRecentScans((prev) => {
      const exists = prev.some((item) => item.symbol === sym);
      if (exists) {
        return prev.map((item) => item.symbol === sym ? {
          ...item,
          catalyst_score: data.catalyst_density_score,
          price: data.price,
          market_cap: data.market_cap,
          flags: data.recommendation ? [data.recommendation] : ["Scanned"],
          is_scanned: true,
          is_merger_arb: data.is_merger_arb,
          is_dher_pattern: data.is_dher_pattern,
          convergence_score: data.convergence_score
        } : item);
      }
      return [
        {
          symbol: sym,
          name: data.company_name,
          catalyst_score: data.catalyst_density_score,
          price: data.price,
          market_cap: data.market_cap,
          flags: data.recommendation ? [data.recommendation] : ["Scanned"],
          has_special_flag: false,
          is_scanned: true,
          is_merger_arb: data.is_merger_arb,
          is_dher_pattern: data.is_dher_pattern,
          convergence_score: data.convergence_score
        },
        ...prev
      ];
    });
  };

  // Filter recent scans to exclude items currently on the watchlist and apply merger arb filter if unchecked
  const filteredRecentScans = useMemo(() => {
    let result = recentScans.filter(r => !watchlist.some(w => w.symbol === r.symbol));
    if (!showMergerArbs) {
      result = result.filter(r => !r.is_merger_arb);
    }
    return result;
  }, [recentScans, watchlist, showMergerArbs]);

  // Filter watchlist to include or exclude merger arbs based on toggle
  const filteredWatchlist = useMemo(() => {
    if (showMergerArbs) {
      return watchlist;
    } else {
      return watchlist.filter(w => !w.is_merger_arb);
    }
  }, [watchlist, showMergerArbs]);

  // Filter and sort candidates list based on active filters and sorting selection
  const processedCandidates = useMemo(() => {
    let result = candidates.filter(cand => 
      !watchlist.some(w => w.symbol === cand.symbol)
    );
    
    if (categoryFilter !== "All") {
      result = result.filter(cand => 
        cand.categories && cand.categories.includes(categoryFilter)
      );
    }
    
    // Merger Arb Filter: Include all (if true) or Exclude (if false)
    if (!showMergerArbs) {
      result = result.filter(cand => !cand.is_merger_arb);
    }

    // Phase-2 "Actionable" edge filter: hide names whose COMPUTED edge is Low
    // (poor ratio or non-positive binary EV). Un-valued names always show — edge is an
    // overlay (Option A), never the primary sort, so board_priority order is untouched.
    if (showActionable) {
      result = result.filter(cand =>
        !((cand.computed_rr != null && cand.computed_rr < 1.5) || (cand.ev_pct != null && cand.ev_pct <= 0)));
    }

    result.sort((a, b) => {
      if (sortField === "asymmetry") {
        const asymA = a.rr_ratio ?? (a.upside ? a.upside * 10 : 0);
        const asymB = b.rr_ratio ?? (b.upside ? b.upside * 10 : 0);
        return asymB - asymA;
      } else if (sortField === "mcap") {
        return (b.market_cap || 0) - (a.market_cap || 0);
      } else {
        // Default: board_priority within tier (manual §5 ACTIVE-first + §3 lane tilt).
        const tr: Record<string, number> = { ACTIVE: 0, CONTINGENT: 1, WATCH: 2, NONE: 9 };
        const ta = tr[a.flags?.[0]] ?? 3, tb = tr[b.flags?.[0]] ?? 3;
        if (ta !== tb) return ta - tb;
        return (b.board_priority ?? b.adjusted_loeb_score ?? b.catalyst_score ?? 0)
             - (a.board_priority ?? a.adjusted_loeb_score ?? a.catalyst_score ?? 0);
      }
    });
    
    return result;
  }, [candidates, watchlist, recentScans, categoryFilter, sortField, showMergerArbs, showActionable]);

  // §3 #5 "hidden common factor" view: resolution-driver concentration across ACTIVE names.
  const driverConcentration = useMemo(() => {
    const SUPER: Record<string, string> = {
      FDA_approval_decision: "FDA/biotech", FDA_clinical_readout: "FDA/biotech",
      US_antitrust: "Deal-completion", US_sector_regulator: "Deal-completion",
      CFIUS_FDI: "Deal-completion", Foreign_regulator: "Deal-completion",
      Deal_close_generic: "Deal-completion", Shareholder_vote: "Deal-completion",
    };
    const act = candidates.filter(c => c.flags?.[0] === "ACTIVE" && c.resolution_driver);
    if (!act.length) return [] as { label: string; pct: number }[];
    const cnt: Record<string, number> = {};
    act.forEach(c => { const s = SUPER[c.resolution_driver as string] || "Idiosyncratic"; cnt[s] = (cnt[s] || 0) + 1; });
    return Object.entries(cnt).sort((a, b) => b[1] - a[1]).map(([label, v]) => ({ label, pct: Math.round((100 * v) / act.length) }));
  }, [candidates]);

  // 1. Fetch Candidates List
  useEffect(() => {
    fetch("/api/catalysts/candidates")
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP error ${r.status}`);
        return r.json();
      })
      .then((data: Candidate[]) => {
        setCandidates(data || []);
        setLoadingCandidates(false);
        
        // Select the first watched symbol from localStorage on mount if it exists
        if (typeof window !== "undefined") {
          const saved = localStorage.getItem("catalyst_watchlist");
          if (saved) {
            try {
              const parsed = JSON.parse(saved);
              if (parsed && parsed.length > 0) {
                setSelectedSymbol(parsed[0].symbol);
                return; // skip setting from default data
              }
            } catch (e) {}
          }
        }
        
        if (data && data.length > 0) {
          setSelectedSymbol(data[0].symbol);
        }
      })
      .catch((err) => {
        console.error("Failed to load candidates", err);
        setLoadingCandidates(false);
        // Fallback placeholder candidate
        const fallbacks: Candidate[] = [
          { symbol: "CVS", name: "CVS Health Corp", price: 54.20, market_cap: 67800000000, catalyst_score: 8.5, flags: ["Starboard activist stake", "8-K Management change"], has_special_flag: true },
          { symbol: "DIS", name: "Walt Disney Co", price: 114.50, market_cap: 208000000000, catalyst_score: 8.0, flags: ["Proxy fight resolution", "Asset review"], has_special_flag: true },
          { symbol: "SONY", name: "Sony Group Corp", price: 89.15, market_cap: 112000000000, catalyst_score: 7.8, flags: ["Sum of parts dislocation"], has_special_flag: true }
        ];
        setCandidates(fallbacks);
        
        // Fallback watch logic on mount
        if (typeof window !== "undefined") {
          const saved = localStorage.getItem("catalyst_watchlist");
          if (saved) {
            try {
              const parsed = JSON.parse(saved);
              if (parsed && parsed.length > 0) {
                setSelectedSymbol(parsed[0].symbol);
                return;
              }
            } catch (e) {}
          }
        }
        setSelectedSymbol(fallbacks[0].symbol);
      });
  }, []);

  // 2. Fetch Deep Scan for Symbol
  useEffect(() => {
    if (!selectedSymbol) return;
    
    // Check cache first
    const cached = scanCacheRef.current[selectedSymbol];
    if (cached) {
      setReport(cached);
      setCustomAcquirerPrice(cached.merger_arb_data?.acquirer_price ?? "");
      setScanError(null);
      addRecentScan(cached);
      return;
    }

    setLoadingScan(true);
    setScanError(null);
    
    fetch(`/api/catalysts/scan?symbol=${selectedSymbol}`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP error ${r.status}`);
        return r.json();
      })
      .then((data: CatalystScanReport) => {
        setReport(data);
        setCustomAcquirerPrice(data.merger_arb_data?.acquirer_price ?? "");
        scanCacheRef.current[selectedSymbol] = data;
        setLoadingScan(false);
        addRecentScan(data);
        propagateScoreUpdate(data.symbol, data.catalyst_density_score);
      })
      .catch((err) => {
        console.error(`Failed to scan ${selectedSymbol}`, err);
        setScanError(`Failed to load event-driven scan for ${selectedSymbol}. Please try again.`);
        setLoadingScan(false);
        setReport(null);
      });
  }, [selectedSymbol]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const sym = customSymbol.toUpperCase().trim();
    if (sym) {
      setSelectedSymbol(sym);
      setCustomSymbol("");
    }
  };

  const getRecommendationStyle = (rec?: string) => {
    switch (rec) {
      case "BUY":
        return { color: T.green, backgroundColor: T.greenLight, borderColor: T.greenBorder };
      case "WATCH":
        return { color: T.amber, backgroundColor: T.amberLight, borderColor: T.amber };
      case "HOLD":
        return { color: T.muted, backgroundColor: T.card, borderColor: T.border };
      case "SELL":
        return { color: T.red, backgroundColor: T.redLight, borderColor: T.red };
      default:
        return { color: T.text, backgroundColor: T.card, borderColor: T.border };
    }
  };

  const formatMarketCap = (num?: number) => {
    if (!num) return "N/A";
    if (num >= 1e12) return `$${(num / 1e12).toFixed(2)}T`;
    if (num >= 1e9) return `$${(num / 1e9).toFixed(1)}B`;
    if (num >= 1e6) return `$${(num / 1e6).toFixed(1)}M`;
    return `$${num.toLocaleString()}`;
  };

  const renderCandidate = (cand: Candidate, listType: "watchlist" | "recent" | "candidate") => {
    const active = cand.symbol === selectedSymbol;
    const isWatched = watchlist.some(w => w.symbol === cand.symbol);
    return (
      <div 
        key={`${listType}-${cand.symbol}`} 
        onClick={() => { setSelectedSymbol(cand.symbol); setView("detail"); }}
        style={{ 
          background: active ? "var(--green-light)" : T.card, 
          border: `1px solid ${active ? T.green : T.border}`,
          borderRadius: 6,
          padding: "10px 12px",
          cursor: "pointer",
          transition: "all 0.15s",
          boxShadow: active ? "0 0 15px rgba(20,184,122,0.08)" : "none",
          position: "relative"
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
          <span style={{ fontSize: 13, fontWeight: 700, color: active ? T.green : T.text, display: "flex", alignItems: "center", gap: 5 }}>
            {cand.symbol}
            {isWatched && <Star size={11} fill="var(--amber, #f59e0b)" color="var(--amber, #f59e0b)" />}
            {cand.is_merger_arb && <span style={{ fontSize: 7, padding: "1px 4px", borderRadius: 3, background: "rgba(59,130,246,0.15)", color: T.blue, border: `1px solid rgba(59,130,246,0.3)` }}>M&A ARB</span>}
            {cand.is_dher_pattern && <span style={{ fontSize: 7, padding: "1px 4px", borderRadius: 3, background: "rgba(168,85,247,0.15)", color: T.purple, border: `1px solid rgba(168,85,247,0.3)` }}>DHER</span>}
          </span>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            {sortField === "mcap" ? (
              <span style={{ fontSize: 10, fontFamily: T.mono, padding: "1px 5px", borderRadius: 4, background: "rgba(59,130,246,0.18)", color: T.blue }} title="Market Cap">
                {formatMarketCap(cand.market_cap || undefined)}
              </span>
            ) : sortField === "asymmetry" ? (() => {
              const rr = rrDisplay(cand);
              return (
              <Tip k="RR" extra={rr.rawForTooltip}><span style={{ fontSize: 10, fontFamily: T.mono, padding: "1px 5px", borderRadius: 4, background: "rgba(255,255,255,0.06)", color: toneColor(rr.tone) }}>{rr.text}</span></Tip>
              );
            })() : (() => {
                const displayScore = cand.adjusted_loeb_score ?? cand.catalyst_score;
                const hasDivergence = cand.adjusted_loeb_score != null && Math.abs(cand.adjusted_loeb_score - cand.catalyst_score) >= 1.0;
                const adjustmentTooltip = cand.score_adjustments?.map(a => `${a.factor}: ${a.adjustment > 0 ? '+' : ''}${a.adjustment.toFixed(1)} (${a.reason})`).join('\n') || '';
                return (
                  <span 
                    style={{ 
                      fontSize: 10, 
                      fontFamily: T.mono, 
                      padding: "1px 5px", 
                      borderRadius: 4, 
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 3,
                      background: cand.is_scanned 
                        ? (displayScore >= 7.5 ? "rgba(168,85,247,0.18)" : "rgba(255,255,255,0.05)")
                        : "rgba(255,255,255,0.03)", 
                      color: cand.is_scanned 
                        ? (displayScore >= 7.5 ? T.purple : T.light) 
                        : T.muted 
                    }} 
                    title={adjustmentTooltip ? `Score Adjustments:\n${adjustmentTooltip}` : (cand.is_scanned ? "Loeb Score (Deep Scanned)" : "Loeb Score (Heuristic Estimate)")}
                  >
                    {hasDivergence ? (
                      <>
                        <span style={{ textDecoration: "line-through", opacity: 0.5 }}>{cand.catalyst_score.toFixed(1)}</span>
                        <span>→</span>
                        <span style={{ fontWeight: 600 }}>{displayScore.toFixed(1)}</span>
                        <AlertTriangle size={10} style={{ color: T.amber, flexShrink: 0 }} />
                      </>
                    ) : (
                      <>{displayScore.toFixed(1)}{cand.is_scanned ? "" : "*"}</>
                    )}
                  </span>
                );
              })()}
            {listType === "watchlist" && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  toggleWatchlist(cand.symbol, cand.name, cand.catalyst_score, cand.price, cand.market_cap, cand.is_merger_arb);
                }}
                style={{ background: "none", border: "none", cursor: "pointer", padding: "2px 0 0 2px", color: T.muted }}
                title="Remove from Watchlist"
              >
                <Trash2 size={12} style={{ opacity: 0.7 }} />
              </button>
            )}
          </div>
        </div>
        <div style={{ fontSize: 10, color: T.light, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", marginBottom: 6 }}>
          {cand.name || "Unknown Company"}
        </div>
        {cand.flags && cand.flags.length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
            {cand.flags.slice(0, 2).map((fl, idx) => (
              <Tip key={idx} k={idx === 0 ? fl : cand.lane_canon}><span style={{ fontSize: 8, padding: "1px 4px", borderRadius: 3, background: "rgba(255,255,255,0.06)", color: T.muted, border: `1px solid rgba(255,255,255,0.03)` }}>
                {fl}
              </span></Tip>
            ))}
          </div>
        )}
        {cand.valuation_method && cand.edge_grade && cand.edge_grade !== "?" && (() => {
          const rr = rrDisplay(cand);
          const PRIMARY = new Set(["QUARANTINED", "TRADING_THROUGH_TERMS", "NO_UPSIDE", "FLOOR_GE_LIVE", "NO_BREAK_DOWNSIDE", "THIN_FLOOR", "TINY_FLOOR"]);
          const chips = (cand.edge_flags || []).map((f: string) => f.split(":")[0]).filter((f: string) => !PRIMARY.has(f));
          return (
          <div style={{ marginTop: 4, display: "flex", gap: 4, alignItems: "center", flexWrap: "wrap" }}>
            <Tip k={cand.edge_grade}><span style={{ fontSize: 8, fontWeight: 800, padding: "1px 5px", borderRadius: 3, background: cand.edge_grade === "H" ? "rgba(20,184,122,0.18)" : cand.edge_grade === "M" ? "rgba(217,151,6,0.18)" : "rgba(239,68,68,0.16)", color: cand.edge_grade === "H" ? T.green : cand.edge_grade === "M" ? "#d97706" : "#ef4444" }}>EDGE {cand.edge_grade}</span></Tip>
            <Tip k="RR" extra={rr.rawForTooltip}><span style={{ fontSize: 8, fontFamily: T.mono, color: toneColor(rr.tone) }}>{rr.text}</span></Tip>
            {chips.slice(0, 3).map((f: string) => (
              <Tip key={f} k={f}><span style={{ fontSize: 7.5, fontFamily: T.mono, color: "#d97706", border: "1px solid rgba(217,151,6,0.3)", borderRadius: 3, padding: "0 3px" }}>{f === "RE_DOSSIER" ? "⟳" : f.replace(/_/g, " ").toLowerCase()}</span></Tip>
            ))}
          </div>
          );
        })()}
        {cand.resolution_driver && (
          <div style={{ marginTop: 4 }}>
            <Tip k="RESOLUTION_DRIVER"><span style={{ fontSize: 8, padding: "1px 5px", borderRadius: 3, background: "rgba(196,181,253,0.14)", color: T.purple, border: "1px solid rgba(196,181,253,0.20)" }}>
              ⛓ {String(cand.resolution_driver).replace(/_/g, " ")}
            </span></Tip>
          </div>
        )}
        {B13_SEATS[cand.symbol] && (
          <div style={{ marginTop: 4 }}>
            <span title={`Basket 13 seat — ${B13_SEATS[cand.symbol].weight_pct}% · ${fmtB13Expr(B13_SEATS[cand.symbol])}${B13_SEATS[cand.symbol].staging ? " · staging (half-weight, equity-only)" : ""} · review: ${B13_SEATS[cand.symbol].review_trigger || "—"}`}
              style={{ fontSize: 8, fontWeight: 800, fontFamily: T.mono, padding: "1px 5px", borderRadius: 3, background: "rgba(59,130,246,0.14)", color: T.blue, border: "1px solid rgba(59,130,246,0.25)" }}>
              ⬡ B13 {B13_SEATS[cand.symbol].weight_pct}% {fmtB13Expr(B13_SEATS[cand.symbol])}{B13_SEATS[cand.symbol].staging ? " *" : ""}
            </span>
          </div>
        )}
      </div>
    );
  };

  // Dynamic merger arb math calculation based on customAcquirerPrice input
  const mergerArbComputed = useMemo(() => {
    if (!report || (!report.is_merger_arb && !report.merger_arb_data) || !report.merger_arb_data) return null;
    
    const data = report.merger_arb_data;
    const isPE = !data.acquirer_symbol || data.acquirer_symbol === "CASH" || data.acquirer_symbol === "NONE";
    
    const acquirerPriceToUse = customAcquirerPrice !== "" ? customAcquirerPrice : (data.acquirer_price || 0);
    const cashComponent = data.cash_component || 0;
    const stockComponentRatio = data.stock_component_ratio || 0;
    const targetPrice = report.price || 0;
    const preAnnouncePrice = data.pre_announce_price || (targetPrice * 0.85);

    const impliedDealValue = cashComponent + (stockComponentRatio * acquirerPriceToUse);
    const grossSpreadVal = impliedDealValue - targetPrice;
    const grossSpreadPct = targetPrice > 0 ? (grossSpreadVal / targetPrice) * 100 : 0;
    const unhedgedDownside = targetPrice - preAnnouncePrice;
    const unhedgedRRVal = grossSpreadVal > 0 ? -(unhedgedDownside / grossSpreadVal) : -99.9;
    const unhedgedRRString = grossSpreadVal > 0 ? `${unhedgedRRVal.toFixed(1)}:1` : "N/A (Negative Spread)";
    
    // Dynamic rounded strikes for options suggestion builder
    const roundStrike = (val: number, step = 2.5) => Math.round(val / step) * step;
    
    const longPutStrike = roundStrike(targetPrice, targetPrice < 50 ? 2.5 : 5.0);
    let shortPutStrike = roundStrike(preAnnouncePrice, preAnnouncePrice < 50 ? 2.5 : 5.0);
    if (longPutStrike <= shortPutStrike) {
      shortPutStrike = longPutStrike - (targetPrice < 50 ? 2.5 : 5.0);
    }
    
    const dealValStrike = roundStrike(impliedDealValue, impliedDealValue < 50 ? 2.5 : 5.0);
    
    const targetHedges = [
      {
        strategy: "Bear Put Spread (Downside Protection)",
        description: `Buy ${longPutStrike} Put / Sell ${shortPutStrike} Put on ${report.symbol} to hedge drop to pre-announce reference ($${preAnnouncePrice.toFixed(2)}).`,
        legs: `Buy $${longPutStrike} P / Sell $${shortPutStrike} P`
      },
      {
        strategy: "Covered Call (Yield Enhancement)",
        description: `Buy ${report.symbol} stock and Sell ${dealValStrike} Call to collect premium and buffer downside, capping upside at deal price.`,
        legs: `Buy Stock / Sell $${dealValStrike} C`
      }
    ];
    
    const acquirerHedges = [];
    if (stockComponentRatio > 0 && data.acquirer_symbol && data.acquirer_symbol !== "CASH") {
      const acqSpot = acquirerPriceToUse;
      if (acqSpot > 0) {
        const acqShortStrike = roundStrike(acqSpot, acqSpot < 50 ? 2.5 : 5.0);
        const acqLongStrike = roundStrike(acqSpot * 1.10, acqSpot < 50 ? 2.5 : 5.0);
        acquirerHedges.push({
          strategy: "Bear Call Spread (Short Protection)",
          description: `Sell $${acqShortStrike} Call / Buy $${acqLongStrike} Call on ${data.acquirer_symbol} to hedge long target exposure if acquirer shares plummet.`,
          legs: `Sell $${acqShortStrike} Call / Buy $${acqLongStrike} Call`
        });
        
        const acqLongPut = roundStrike(acqSpot, acqSpot < 50 ? 2.5 : 5.0);
        const acqShortPut = roundStrike(acqSpot * 0.85, acqSpot < 50 ? 2.5 : 5.0);
        acquirerHedges.push({
          strategy: "Bear Put Spread (Synthetic Short)",
          description: `Buy $${acqLongPut} Put / Sell $${acqShortPut} Put on ${data.acquirer_symbol} to gain short exposure to the acquirer component without borrow cost.`,
          legs: `Buy $${acqLongPut} Put / Sell $${acqShortPut} Put`
        });
      }
    }

    return {
      impliedDealValue,
      grossSpreadVal,
      grossSpreadPct,
      unhedgedDownside,
      unhedgedRRString,
      acquirerPriceToUse,
      isPE,
      targetHedges,
      acquirerHedges
    };
  }, [report, customAcquirerPrice]);

  return (
    <div style={{ minHeight: "100vh", background: T.bg, color: T.text, fontFamily: T.mono }}>

      {/* Universe Scan Progress Indicator */}
      {scanProgress && scanProgress.status === "scanning" && (
        <div style={{
          background: "linear-gradient(90deg, rgba(20,184,122,0.15) 0%, rgba(59,130,246,0.15) 100%)",
          borderBottom: `1px solid rgba(20,184,122,0.3)`,
          padding: "10px 24px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 16,
          boxShadow: "0 4px 20px rgba(0,0,0,0.15)",
          backdropFilter: "blur(8px)",
          position: "sticky",
          top: 0,
          zIndex: 1000
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <RefreshCw size={14} color={T.green} style={{ animation: "spin 2s linear infinite" }} />
            <span style={{ fontSize: 11, fontWeight: 700, color: T.text }}>
              UNIVERSE SCAN IN PROGRESS
            </span>
            <span style={{ fontSize: 10, color: T.light, background: "rgba(255,255,255,0.05)", padding: "2px 6px", borderRadius: 4, border: `1px solid ${T.border}` }}>
              Scanning: <strong style={{ color: T.text }}>{scanProgress.current_symbol}</strong>
            </span>
          </div>
          
          <div style={{ flex: 1, maxWidth: 400, display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{ flex: 1, height: 6, background: "rgba(255,255,255,0.1)", borderRadius: 3, overflow: "hidden", position: "relative" }}>
              <div style={{
                height: "100%",
                background: `linear-gradient(90deg, ${T.green} 0%, ${T.blue} 100%)`,
                width: `${(scanProgress.completed_count / (scanProgress.total_symbols || 1)) * 100}%`,
                transition: "width 0.5s ease-out-in"
              }} />
            </div>
            <span style={{ fontSize: 10, fontFamily: T.mono, color: T.text, fontWeight: 700, minWidth: 65 }}>
              {scanProgress.completed_count}/{scanProgress.total_symbols}
            </span>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 16, fontSize: 10, color: T.light }}>
            <div>
              Speed: <strong style={{ color: T.green }}>{scanProgress.speed_stats}</strong>
            </div>
            {scanProgress.estimated_remaining_seconds > 0 && (
              <div>
                ETA: <strong style={{ color: T.text }}>{Math.round(scanProgress.estimated_remaining_seconds)}s</strong>
              </div>
            )}
          </div>
        </div>
      )}

      
      {/* Sub-header detailing strategy details */}
      <div style={{ padding: "16px 24px", borderBottom: `1px solid ${T.border}`, background: "rgba(10, 10, 10, 0.4)", display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
          <Zap size={16} color={T.green} />
          <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: "0.05em", color: T.green, textTransform: "uppercase" }}>
            Opportunistic AI Layer: Loeb / Third Point + Bloom Framework
          </span>
          <span style={{ width: 10 }} />
          <span onClick={() => setView("basket")}
            style={{ fontSize: 10, fontWeight: 800, fontFamily: T.mono, padding: "3px 10px", borderRadius: 4, cursor: "pointer", userSelect: "none",
              color: view === "basket" ? T.blue : T.muted, border: `1px solid ${view === "basket" ? "rgba(59,130,246,0.45)" : T.border}`,
              background: view === "basket" ? "rgba(59,130,246,0.10)" : "transparent" }}>
            ⬡ BASKET 13
          </span>
          <span onClick={() => setView("detail")}
            style={{ fontSize: 10, fontWeight: 800, fontFamily: T.mono, padding: "3px 10px", borderRadius: 4, cursor: "pointer", userSelect: "none",
              color: view === "detail" ? T.green : T.muted, border: `1px solid ${view === "detail" ? "rgba(20,184,122,0.45)" : T.border}`,
              background: view === "detail" ? "rgba(20,184,122,0.08)" : "transparent" }}>
            ⌕ DEPTH: {selectedSymbol}
          </span>
          <span onClick={() => setSidebarOpen(!sidebarOpen)}
            style={{ fontSize: 10, fontWeight: 700, fontFamily: T.mono, padding: "3px 10px", borderRadius: 4, cursor: "pointer", userSelect: "none",
              color: sidebarOpen ? T.text : T.muted, border: `1px solid ${T.border}`, background: sidebarOpen ? "rgba(255,255,255,0.04)" : "transparent" }}>
            ◧ CANDIDATES {sidebarOpen ? "ON" : "OFF"}
          </span>
        </div>
        <div style={{ fontSize: 11, color: T.light, maxWidth: 650, textAlign: "right" }}>
          Filters a wide universe by catalyst density & Sum-of-Parts dislocation. High asymmetric 2:1 R/R entries verified by option Greeks and multi-quarter transcript tracking.
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: sidebarOpen ? "320px 1fr" : "1fr", minHeight: "calc(100vh - 120px)", background: T.bg }}>

        {/* LEFT SIDEBAR: Candidate List (toggleable — off by default so Basket 13 breathes) */}
        {sidebarOpen && (
        <div style={{ borderRight: `1px solid ${T.border}`, padding: "20px 16px", display: "flex", flexDirection: "column", gap: 16, background: "rgba(5, 5, 5, 0.2)" }}>
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase", color: T.muted, letterSpacing: "0.1em", marginBottom: 12 }}>
              Catalyst Scanning candidates
            </div>
            <form onSubmit={handleSearchSubmit} style={{ position: "relative", marginBottom: 12 }}>
              <input 
                type="text" 
                placeholder="Search symbol (e.g. SONY, CVS, DIS)..." 
                value={customSymbol}
                onChange={(e) => setCustomSymbol(e.target.value)}
                style={{ width: "100%", background: T.card, border: `1px solid ${T.border}`, borderRadius: 6, padding: "8px 32px 8px 12px", fontSize: 12, color: T.text, outline: "none", fontFamily: T.mono }}
              />
              <button type="submit" style={{ position: "absolute", right: 8, top: 8, background: "none", border: "none", cursor: "pointer", color: T.muted }}>
                <Search size={14} />
              </button>
            </form>

            <div style={{ display: "flex", gap: 8, marginBottom: 4 }}>
              <div style={{ flex: 1 }}>
                <label style={{ fontSize: 8, color: T.muted, textTransform: "uppercase", display: "block", marginBottom: 4 }}>Category</label>
                <select
                  value={categoryFilter}
                  onChange={(e) => setCategoryFilter(e.target.value)}
                  style={{ width: "100%", background: T.card, border: `1px solid ${T.border}`, borderRadius: 4, padding: "4px 6px", fontSize: 10, color: T.text, fontFamily: T.mono, outline: "none", cursor: "pointer" }}
                >
                  <option value="All">All Events</option>
                  <option value="Governance">Governance / Activist</option>
                  <option value="M&A">M&A / Buyout</option>
                  <option value="Spinoff">Spinoff / Splits</option>
                  <option value="Options">Options Inversion</option>
                </select>
              </div>
              <div style={{ flex: 1 }}>
                <label style={{ fontSize: 8, color: T.muted, textTransform: "uppercase", display: "block", marginBottom: 4 }}>Sort By</label>
                <select
                  value={sortField}
                  onChange={(e) => setSortField(e.target.value as any)}
                  style={{ width: "100%", background: T.card, border: `1px solid ${T.border}`, borderRadius: 4, padding: "4px 6px", fontSize: 10, color: T.text, fontFamily: T.mono, outline: "none", cursor: "pointer" }}
                >
                  <option value="score">Loeb Score</option>
                  <option value="asymmetry">Asymmetry (R/R)</option>
                  <option value="mcap">Market Cap</option>
                </select>
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: "rgba(255,255,255,0.02)", border: `1px solid ${T.border}`, borderRadius: 6, padding: "6px 10px", marginTop: 10 }}>
              <span style={{ fontSize: 10, fontWeight: 600, color: T.text }}>Show Merger Arbs</span>
              <button
                type="button"
                onClick={() => setShowMergerArbs(!showMergerArbs)}
                style={{
                  background: showMergerArbs ? T.green : "rgba(255,255,255,0.1)",
                  border: "none",
                  borderRadius: 12,
                  width: 34,
                  height: 20,
                  position: "relative",
                  cursor: "pointer",
                  transition: "background 0.2s"
                }}
              >
                <div
                  style={{
                    background: "#fff",
                    borderRadius: "50%",
                    width: 14,
                    height: 14,
                    position: "absolute",
                    top: 3,
                    left: showMergerArbs ? 17 : 3,
                    transition: "left 0.2s"
                  }}
                />
              </button>
            </div>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", background: "rgba(255,255,255,0.02)", border: `1px solid ${T.border}`, borderRadius: 6, padding: "6px 10px", marginTop: 8 }}>
              <span style={{ fontSize: 10, fontWeight: 600, color: T.text }} title="Edge overlay (phase-2): hide names whose computed R:R / binary EV is Low. Does NOT change the board_priority sort.">Actionable only <span style={{ color: T.muted, fontWeight: 400 }}>· edge ≥ M</span></span>
              <button type="button" onClick={() => setShowActionable(!showActionable)} style={{ background: showActionable ? T.green : "rgba(255,255,255,0.1)", border: "none", borderRadius: 12, width: 34, height: 20, position: "relative", cursor: "pointer", transition: "background 0.2s" }}>
                <div style={{ background: "#fff", borderRadius: "50%", width: 14, height: 14, position: "absolute", top: 3, left: showActionable ? 17 : 3, transition: "left 0.2s" }} />
              </button>
            </div>
          </div>

          <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 14, maxHeight: "calc(100vh - 280px)", paddingRight: 4 }}>
            {loadingCandidates ? (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: 40, gap: 8, fontSize: 12, color: T.muted }}>
                <RefreshCw size={14} className="animate-spin" /> Loading candidates...
              </div>
            ) : (
              <>
                {/* 1. WATCHLIST */}
                {filteredWatchlist.length > 0 && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    <div style={{ fontSize: 9, fontWeight: 800, textTransform: "uppercase", color: "var(--amber, #f59e0b)", letterSpacing: "0.08em", display: "flex", alignItems: "center", gap: 4, borderBottom: `1px solid rgba(245,158,11,0.2)`, paddingBottom: 4 }}>
                      <Star size={10} fill="var(--amber, #f59e0b)" color="var(--amber, #f59e0b)" /> Watchlist ({filteredWatchlist.length})
                    </div>
                    {filteredWatchlist.map(cand => renderCandidate(cand, "watchlist"))}
                  </div>
                )}



                {/* 3. DEFAULT CANDIDATES */}
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <div style={{ fontSize: 9, fontWeight: 800, textTransform: "uppercase", color: T.muted, letterSpacing: "0.08em", borderBottom: `1px solid ${T.border}`, paddingBottom: 4 }}>
                    Scanning Candidates ({processedCandidates.length})
                  </div>
                  {driverConcentration.length > 0 && (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center", fontSize: 9, fontFamily: T.mono, color: T.light, padding: "1px 0 2px" }} title="ACTIVE resolution-driver concentration — what the live catalysts actually resolve on (manual §3 #5)">
                      <Tip k="RESOLUTION_DRIVER"><span style={{ color: T.muted, fontWeight: 700 }}>ACTIVE drivers:</span></Tip>
                      {driverConcentration.map((d, i) => (
                        <span key={d.label}>
                          <span style={{ color: T.green, fontWeight: 700 }}>{d.pct}%</span> {d.label}{i < driverConcentration.length - 1 ? " ·" : ""}
                        </span>
                      ))}
                    </div>
                  )}
                  {processedCandidates.length === 0 ? (
                    <div style={{ fontSize: 10, color: T.light, padding: "8px 0" }}>No matching candidates</div>
                  ) : (
                    processedCandidates.map(cand => renderCandidate(cand, "candidate"))
                  )}
                </div>
              </>
            )}
          </div>
        </div>
        )}

        {/* MAIN PANEL: AI Event-Driven Scan Result */}
        <div style={{ padding: 24, overflowY: "auto", maxHeight: "calc(100vh - 120px)" }}>

          {/* BASKET 13 — catalyst sleeve (paper, event-resolution tracker) — the DEFAULT view; depth analysis is a separate view */}
          {view === "basket" ? (B13.entries || []).length > 0 ? (() => {
            const open = (B13.entries || []).filter((e: any) => !e.resolution);
            const resolved = (B13.entries || []).filter((e: any) => e.resolution);
            const atDrvCap = (n: number) => n >= (B13.caps?.max_per_driver ?? 2);
            return (
              <>
              <div style={{ background: T.card, border: "1px solid rgba(59,130,246,0.30)", borderRadius: 8, padding: "13px 18px", marginBottom: 24, boxShadow: "var(--shadow-md)" }}>
                <div onClick={() => setB13Open(!b13Open)} style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", cursor: "pointer", userSelect: "none" }}>
                  <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.08em", color: T.blue }}>⬡ BASKET 13 — CATALYST SLEEVE</span>
                  <span style={{ fontSize: 8, fontWeight: 700, padding: "1px 6px", borderRadius: 3, background: "rgba(217,151,6,0.14)", color: "#d97706", border: "1px solid rgba(217,151,6,0.3)", textTransform: "uppercase" }}>paper · calibration</span>
                  <span style={{ fontSize: 10, fontFamily: T.mono, color: T.light }}>
                    {open.filter((e: any) => e.status !== "PENDING_LIMIT").length} seats · {B13.invested_pct}% invested{B13.pending_pct ? ` · ${B13.pending_pct}% resting-limit` : ""} · {B13.cash_pct}% cash · {resolved.length} resolved
                  </span>
                  <span style={{ fontSize: 9, fontFamily: T.mono, color: T.muted, marginLeft: "auto" }}>run {B13.generated} {b13Open ? "▾" : "▸"}</span>
                </div>
                {b13Open && (
                  <>
                    <div style={{ overflowX: "auto", marginTop: 10 }}>
                      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 10.5, fontFamily: T.mono }}>
                        <thead>
                          <tr style={{ color: T.muted, fontSize: 8.5, textTransform: "uppercase", letterSpacing: "0.05em", textAlign: "left" }}>
                            <th style={{ padding: "3px 8px 3px 0" }}>Seat</th>
                            <th style={{ padding: "3px 8px" }}>Wt</th>
                            <th style={{ padding: "3px 8px" }}>Expression</th>
                            <th style={{ padding: "3px 8px" }}>Lane</th>
                            <th style={{ padding: "3px 8px" }}>Driver</th>
                            <th style={{ padding: "3px 8px" }}>Exp R:R / EV</th>
                            <th style={{ padding: "3px 8px" }}>Entry</th>
                            <th style={{ padding: "3px 8px" }}>Review trigger</th>
                            <th style={{ padding: "3px 8px" }}>CRO</th>
                            <th style={{ padding: "3px 0" }}>Live</th>
                          </tr>
                        </thead>
                        <tbody>
                          {open.map((e: any) => (
                            <tr key={e.symbol} style={{ borderTop: `1px solid ${T.border}` }}>
                              <td style={{ padding: "5px 8px 5px 0" }}>
                                <span onClick={(ev) => { ev.stopPropagation(); setSelectedSymbol(e.symbol); setView("detail"); }} style={{ color: T.blue, fontWeight: 800, cursor: "pointer" }}>{e.symbol}</span>
                                {e.staging && <span title="Staging pick — soft-dated catalyst: equity-only, half-weight cap" style={{ marginLeft: 5, fontSize: 7.5, fontWeight: 700, padding: "0 4px", borderRadius: 3, background: "rgba(217,151,6,0.14)", color: "#d97706" }}>STG</span>}
                              </td>
                              <td style={{ padding: "5px 8px", color: T.text, fontWeight: 700 }}>{e.weight_pct}%</td>
                              <td style={{ padding: "5px 8px", color: T.light }}>{fmtB13Expr(e)}</td>
                              <td style={{ padding: "5px 8px", color: T.light }}>{termLabel(e.lane_canon)}</td>
                              <td style={{ padding: "5px 8px", color: T.purple }}>{termLabel(e.resolution_driver)}</td>
                              <td style={{ padding: "5px 8px", color: T.green }}>{fmtB13RR(e)}</td>
                              <td style={{ padding: "5px 8px", color: e.status === "PENDING_LIMIT" ? "#d97706" : T.light }} title={e.status === "PENDING_LIMIT" ? `Resting limit since ${e.order_date} — live price at stamp exceeded the CRO entry limit; fills when the close trades ≤ ${e.limit_price}. Not held; no NAV impact.` : `edge ${e.edge_grade} · score ${e.score} · floor ${e.downside_floor ?? "—"} · risk-to-floor ${e.risk_to_floor_pct ?? "—"}%${e.hedge ? ` · hedge ${e.hedge.ratio} ${e.hedge.symbol}` : ""}`}>{e.status === "PENDING_LIMIT" ? `⏳ RESTING ≤ ${e.limit_price}` : `${e.entry_date} @ ${e.entry_price != null ? Number(e.entry_price).toFixed(2) : "n/a"}`}{e.hedge ? <span style={{ marginLeft: 4, fontSize: 8, color: T.muted }}>hedged</span> : null}</td>
                              <td style={{ padding: "5px 8px", color: T.light, maxWidth: 230, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={e.review_trigger || ""}>{e.review_trigger || "—"}</td>
                              <td style={{ padding: "5px 8px" }}>
                                {(e.cro_conditions || []).length > 0
                                  ? <span title={e.cro_conditions.join("\n• ").replace(/^/, "• ")} style={{ fontSize: 8.5, color: "#d97706", border: "1px solid rgba(217,151,6,0.3)", borderRadius: 3, padding: "0 4px", cursor: "help" }}>⚠ {e.cro_conditions.length} cond</span>
                                  : <span style={{ fontSize: 8.5, color: T.muted }}>clean</span>}
                              </td>
                              <td style={{ padding: "5px 0" }}>
                                {(() => {
                                  const q = liveQuotes[e.symbol];
                                  if (!q || q.price == null) return <span style={{ fontSize: 9, color: T.muted }}>—</span>;
                                  const pnl = e.entry_price ? (q.price / e.entry_price - 1) * 100 : null;
                                  return (
                                    <span title={`live ${q.price.toFixed(2)} · day ${q.day != null ? `${q.day >= 0 ? "+" : ""}${q.day.toFixed(2)}%` : "—"} · vs entry ${pnl != null ? `${pnl >= 0 ? "+" : ""}${pnl.toFixed(1)}%` : "—"}`}
                                      style={{ display: "inline-flex", flexDirection: "column", lineHeight: 1.3 }}>
                                      <span style={{ color: T.text, fontWeight: 700 }}>
                                        {q.price.toFixed(2)}
                                        {q.day != null && <span style={{ marginLeft: 5, fontSize: 8.5, color: q.day >= 0 ? T.green : T.red }}>{q.day >= 0 ? "+" : ""}{q.day.toFixed(1)}%</span>}
                                      </span>
                                      {pnl != null && <span style={{ fontSize: 8.5, color: pnl >= 0 ? T.green : T.red }}>pos {pnl >= 0 ? "+" : ""}{pnl.toFixed(1)}%</span>}
                                    </span>
                                  );
                                })()}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", marginTop: 10, paddingTop: 8, borderTop: `1px solid ${T.border}` }}>
                      <span style={{ fontSize: 8.5, fontWeight: 700, textTransform: "uppercase", color: T.muted, letterSpacing: "0.05em" }}>Caps</span>
                      {Object.entries(B13.driver_utilization || {}).map(([d, n]: any) => (
                        <span key={d} title={`max ${B13.caps?.max_per_driver ?? 2} names per resolution driver`} style={{ fontSize: 8.5, fontFamily: T.mono, padding: "1px 6px", borderRadius: 3, border: `1px solid ${atDrvCap(n) ? "rgba(217,151,6,0.4)" : T.border}`, color: atDrvCap(n) ? "#d97706" : T.light }}>
                          {termLabel(d)} {n}/{B13.caps?.max_per_driver ?? 2}
                        </span>
                      ))}
                      <span style={{ width: 6 }} />
                      {Object.entries(B13.cluster_utilization || {}).map(([c, w]: any) => (
                        <span key={c} title={`max ${B13.caps?.max_super_pct ?? 40} weight-points per super-cluster`} style={{ fontSize: 8.5, fontFamily: T.mono, padding: "1px 6px", borderRadius: 3, background: "rgba(196,181,253,0.08)", border: "1px solid rgba(196,181,253,0.2)", color: T.purple }}>
                          {c} {w}/{B13.caps?.max_super_pct ?? 40}
                        </span>
                      ))}
                      {(() => {
                        const cap = (B13.caps?.max_per_lane || {}).bio_convergence;
                        const n = (B13.lane_utilization || {}).bio_convergence;
                        if (cap == null || n == null) return null;
                        const atCap = n >= cap;
                        return <span title="max names in the bio_convergence lane (held + new)" style={{ fontSize: 8.5, fontFamily: T.mono, padding: "1px 6px", borderRadius: 3, border: `1px solid ${atCap ? "rgba(217,151,6,0.4)" : T.border}`, color: atCap ? "#d97706" : T.light }}>bio {n}/{cap}</span>;
                      })()}
                    </div>
                    {resolved.length > 0 && (
                      <div style={{ marginTop: 10 }}>
                        <div style={{ fontSize: 8.5, fontWeight: 700, textTransform: "uppercase", color: T.muted, letterSpacing: "0.05em", marginBottom: 4 }}>Resolution history</div>
                        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 10, fontFamily: T.mono }}>
                          <tbody>
                            {resolved.map((e: any, i: number) => (
                              <tr key={`${e.symbol}-${i}`} style={{ borderTop: `1px solid ${T.border}` }}>
                                <td style={{ padding: "4px 8px 4px 0", color: T.text, fontWeight: 700 }}>{e.symbol}</td>
                                <td style={{ padding: "4px 8px", color: e.resolution.resolution_type === "FIRED_WIN" ? T.green : e.resolution.resolution_type === "FIRED_LOSS" ? T.red : "#d97706" }}><Term k={e.resolution.resolution_type} /></td>
                                <td style={{ padding: "4px 8px", color: T.light }}>{e.entry_date} → {e.resolution.resolution_date} ({e.resolution.days_held}d)</td>
                                <td style={{ padding: "4px 8px", color: T.light }}>{e.entry_price != null ? Number(e.entry_price).toFixed(2) : "?"} → {e.resolution.exit_price != null ? Number(e.resolution.exit_price).toFixed(2) : "?"}</td>
                                <td style={{ padding: "4px 8px", color: (e.resolution.realized_return_pct ?? 0) >= 0 ? T.green : T.red }}>{e.resolution.realized_return_pct != null ? `${(e.resolution.realized_return_pct * 100).toFixed(1)}%` : "—"}</td>
                                <td style={{ padding: "4px 8px", color: T.light }}>rr {e.resolution.realized_rr ?? "—"} (exp {fmtB13RR(e)})</td>
                                <td style={{ padding: "4px 0", color: T.muted, maxWidth: 260, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={e.resolution.notes || ""}>{e.resolution.notes || ""}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                    {B13.memo && (
                      <details style={{ marginTop: 8 }}>
                        <summary style={{ fontSize: 9, color: T.muted, cursor: "pointer" }}>Director memo · {(B13.non_selections || []).length} non-selections recorded (counterfactuals)</summary>
                        <p style={{ fontSize: 10.5, color: T.light, lineHeight: 1.55, margin: "6px 0 0" }}>{B13.memo}</p>
                        {(B13.non_selections || []).length > 0 && (
                          <div style={{ marginTop: 6, fontSize: 9.5, fontFamily: T.mono, color: T.muted, lineHeight: 1.6 }}>
                            {(B13.non_selections || []).map((p: any, i: number) => (
                              <div key={`${p.symbol}-${i}`}><span style={{ color: T.light, fontWeight: 700 }}>{p.symbol}</span> — {p.passed_because}</div>
                            ))}
                          </div>
                        )}
                      </details>
                    )}
                    <div style={{ marginTop: 8, fontSize: 8.5, color: T.muted }}>
                      Paper basket — nothing is actually traded. Each idea ends one way and stays there (no rebalancing): it plays out as a win or a loss, gets delayed, the thesis breaks, the edge gets priced in, or the window closes. Real outcomes re-tune the edge bar, lane mix and caps each quarter.
                    </div>
                  </>
                )}
              </div>

              {/* TRACK RECORD — the proof ledger: NAV curve + expected vs actual per seat */}
              {(() => {
                const all = [...open.filter((e: any) => e.status !== "PENDING_LIMIT"), ...resolved];
                // per-seat actual % on the underlying: resolved = frozen realized; open = live quote vs entry
                const actualOf = (e: any): number | null => {
                  if (e.resolution) return e.resolution.realized_return_pct != null ? e.resolution.realized_return_pct * 100 : null;
                  const q = liveQuotes[e.symbol];
                  return q?.price != null && e.entry_price ? (q.price / e.entry_price - 1) * 100 : null;
                };
                const wInv = all.reduce((s, e) => s + (e.weight_pct || 0), 0);
                let liveRet = 0; let haveLive = false;
                all.forEach(e => { const a = actualOf(e); if (a != null) { liveRet += (e.weight_pct || 0) / 100 * a / 100; haveLive = true; } });
                const navLive = haveLive ? 100 * (1 + liveRet) : null;
                const expWtd = wInv > 0 ? all.reduce((s, e) => s + (e.weight_pct || 0) * (e.expected_return_pct || 0), 0) / wInv : 0;
                const actWtd = wInv > 0 ? all.reduce((s, e) => { const a = actualOf(e); return s + (e.weight_pct || 0) * (a ?? 0); }, 0) / wInv : 0;
                const wins = resolved.filter((e: any) => e.resolution?.resolution_type === "FIRED_WIN").length;
                const decided = resolved.filter((e: any) => ["FIRED_WIN", "FIRED_LOSS"].includes(e.resolution?.resolution_type)).length;
                // NAV series: server marks + today's live point
                const marks: any[] = [...(B13.marks || [])];
                if (navLive != null) {
                  const last = marks[marks.length - 1];
                  const todayIso = new Date().toISOString().slice(0, 10);
                  if (last && last.date === todayIso) marks[marks.length - 1] = { ...last, nav: navLive };
                  else marks.push({ date: todayIso, nav: navLive });
                }
                const navs = marks.map(m => m.nav);
                const yMin = Math.min(100, ...navs) - 0.5, yMax = Math.max(100, ...navs) + 0.5;
                const W = 600, H = 110, PX = 6, PY = 8;
                const xOf = (i: number) => marks.length > 1 ? PX + (W - 2 * PX) * (i / (marks.length - 1)) : W / 2;
                const yOf = (v: number) => PY + (H - 2 * PY) * (1 - (v - yMin) / (yMax - yMin || 1));
                const pts = marks.map((m, i) => `${xOf(i).toFixed(1)},${yOf(m.nav).toFixed(1)}`).join(" ");
                const lastNav = navs.length ? navs[navs.length - 1] : 100;
                const maxAbs = Math.max(5, ...all.map(e => Math.abs(e.expected_return_pct || 0)), ...all.map(e => Math.abs(actualOf(e) ?? 0)));
                const barW = (v: number) => Math.min(70, Math.abs(v) / maxAbs * 70);
                const KPI = ({ label, value, tone }: any) => (
                  <div style={{ padding: "6px 12px", border: `1px solid ${T.border}`, borderRadius: 6, minWidth: 96 }}>
                    <div style={{ fontSize: 8, textTransform: "uppercase", letterSpacing: "0.06em", color: T.muted }}>{label}</div>
                    <div style={{ fontSize: 15, fontWeight: 800, fontFamily: T.mono, color: tone || T.text }}>{value}</div>
                  </div>
                );
                return (
                  <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 8, padding: "13px 18px", marginBottom: 24 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 10 }}>
                      <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.08em", color: T.text }}>📈 TRACK RECORD</span>
                      <span style={{ fontSize: 9, color: T.muted }}>NAV indexed 100 at inception · marked daily on underlying prices · expected vs realized is the calibration proof</span>
                    </div>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
                      <KPI label="NAV (live)" value={navLive != null ? navLive.toFixed(2) : lastNav.toFixed(2)} tone={(navLive ?? lastNav) >= 100 ? T.green : T.red} />
                      <KPI label="Basket P&L" value={`${((navLive ?? lastNav) - 100) >= 0 ? "+" : ""}${(((navLive ?? lastNav) - 100)).toFixed(2)}%`} tone={(navLive ?? lastNav) >= 100 ? T.green : T.red} />
                      <KPI label="Invested-only P&L" value={`${actWtd >= 0 ? "+" : ""}${actWtd.toFixed(2)}%`} tone={actWtd >= 0 ? T.green : T.red} />
                      <KPI label="Expected (wtd)" value={`+${expWtd.toFixed(1)}%`} tone={T.blue} />
                      <KPI label="Capture vs expected" value={expWtd ? `${(actWtd / expWtd * 100).toFixed(0)}%` : "—"} />
                      <KPI label="Hit rate" value={decided ? `${wins}/${decided}` : "0/0"} />
                      <KPI label="Marks" value={String(marks.length)} />
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "minmax(280px, 1.1fr) minmax(300px, 1fr)", gap: 18, alignItems: "start" }}>
                      <div>
                        <div style={{ fontSize: 8.5, fontWeight: 700, textTransform: "uppercase", color: T.muted, letterSpacing: "0.05em", marginBottom: 4 }}>NAV history</div>
                        <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
                          <line x1={PX} x2={W - PX} y1={yOf(100)} y2={yOf(100)} stroke="rgba(255,255,255,0.15)" strokeDasharray="3 3" />
                          <text x={W - PX} y={yOf(100) - 3} textAnchor="end" fontSize="8" fill="rgba(255,255,255,0.35)" fontFamily="monospace">100</text>
                          {marks.length > 1
                            ? <polyline points={pts} fill="none" stroke={lastNav >= 100 ? "var(--green)" : "var(--red)"} strokeWidth="1.6" />
                            : null}
                          {marks.map((m, i) => (
                            <circle key={m.date} cx={xOf(i)} cy={yOf(m.nav)} r="2.6" fill={m.nav >= 100 ? "var(--green)" : "var(--red)"}>
                              <title>{m.date} · NAV {Number(m.nav).toFixed(2)}</title>
                            </circle>
                          ))}
                          {marks.length > 0 && (
                            <text x={xOf(marks.length - 1)} y={yOf(lastNav) - 6} textAnchor="end" fontSize="9" fontWeight="700" fill={lastNav >= 100 ? "var(--green)" : "var(--red)"} fontFamily="monospace">{lastNav.toFixed(2)}</text>
                          )}
                        </svg>
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 8, fontFamily: T.mono, color: T.muted }}>
                          <span>{marks[0]?.date || ""}</span><span>{marks[marks.length - 1]?.date || ""}</span>
                        </div>
                      </div>
                      <div>
                        <div style={{ fontSize: 8.5, fontWeight: 700, textTransform: "uppercase", color: T.muted, letterSpacing: "0.05em", marginBottom: 4 }}>Expected vs actual (per seat, underlying %)</div>
                        {all.map((e: any) => {
                          const exp = e.expected_return_pct, act = actualOf(e);
                          return (
                            <div key={e.symbol} style={{ display: "grid", gridTemplateColumns: "52px 76px 1fr", alignItems: "center", gap: 6, padding: "2px 0", fontFamily: T.mono }}>
                              <span style={{ fontSize: 9.5, fontWeight: 800, color: e.resolution ? T.muted : T.text }}>{e.symbol}{e.staging ? "*" : ""}</span>
                              <span style={{ fontSize: 9 }}>
                                <span style={{ color: act != null ? (act >= 0 ? T.green : T.red) : T.muted }}>{act != null ? `${act >= 0 ? "+" : ""}${act.toFixed(1)}%` : "—"}</span>
                                <span style={{ color: T.muted }}> / +{(exp ?? 0).toFixed(0)}%</span>
                              </span>
                              <span style={{ position: "relative", height: 10 }}>
                                <span title={`expected +${(exp ?? 0).toFixed(1)}%`} style={{ position: "absolute", left: 0, top: 1, height: 8, width: barW(exp ?? 0), border: "1px solid rgba(59,130,246,0.55)", borderRadius: 2, background: "rgba(59,130,246,0.10)" }} />
                                {act != null && <span title={`actual ${act >= 0 ? "+" : ""}${act.toFixed(1)}%`} style={{ position: "absolute", left: 0, top: 3, height: 4, width: barW(act), borderRadius: 2, background: act >= 0 ? "var(--green)" : "var(--red)" }} />}
                              </span>
                            </div>
                          );
                        })}
                        <div style={{ fontSize: 8, color: T.muted, marginTop: 4 }}>outline = Director expectation · solid = live/realized · * staging · resolved seats freeze at exit</div>
                      </div>
                    </div>
                  </div>
                );
              })()}

              {/* WATCHLIST — on-deck: CRO survivors the Director cleared but couldn't seat (a combined cap is full) */}
              {(B13.watchlist || []).length > 0 && (
                <div style={{ background: T.card, border: "1px dashed rgba(59,130,246,0.35)", borderRadius: 8, padding: "13px 18px", marginBottom: 24 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap", marginBottom: 8 }}>
                    <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.08em", color: T.blue }}>⬡ WATCHLIST — ON-DECK</span>
                    <span style={{ fontSize: 9, color: T.muted }}>{B13.watchlist.length} on-deck names, carried to resolution. Cleared by the CRO but not seated (a driver/cluster cap is full); first to enter when a held seat resolves. A name leaves only when its catalyst resolves or it graduates into the basket — a re-debate never silently drops it; one the Director cools on is flagged <span style={{ color: "#d97706" }}>↓ deprio</span> (with his reason), not erased.</span>
                  </div>
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 10.5, fontFamily: T.mono }}>
                      <thead>
                        <tr style={{ color: T.muted, fontSize: 8.5, textTransform: "uppercase", letterSpacing: "0.05em", textAlign: "left" }}>
                          <th style={{ padding: "3px 8px 3px 0" }}>Seat</th>
                          <th style={{ padding: "3px 8px" }}>Wt</th>
                          <th style={{ padding: "3px 8px" }}>Expression</th>
                          <th style={{ padding: "3px 8px" }}>Lane</th>
                          <th style={{ padding: "3px 8px" }}>Driver</th>
                          <th style={{ padding: "3px 8px" }}>Exp R:R / EV</th>
                          <th style={{ padding: "3px 8px" }}>Entry</th>
                          <th style={{ padding: "3px 8px" }}>Review trigger</th>
                          <th style={{ padding: "3px 8px" }}>CRO</th>
                          <th style={{ padding: "3px 8px" }}>Status</th>
                          <th style={{ padding: "3px 0" }}>Live</th>
                        </tr>
                      </thead>
                      <tbody>
                        {B13.watchlist.map((w: any) => (
                          <tr key={w.symbol} style={{ borderTop: `1px solid ${T.border}`, opacity: w.de_prioritized ? 0.6 : 1 }}>
                            <td style={{ padding: "5px 8px 5px 0" }}>
                              <span onClick={() => { setSelectedSymbol(w.symbol); setView("detail"); }} style={{ color: T.blue, fontWeight: 800, cursor: "pointer" }}>{w.symbol}</span>
                            </td>
                            <td style={{ padding: "5px 8px", color: T.light }} title="intended weight if seated">{w.intended_weight_pct != null ? `${w.intended_weight_pct}%` : "—"}</td>
                            <td style={{ padding: "5px 8px", color: T.light }} title={w.expression_intended ? "intended instrument if seated (Director's expression rule)" : ""}>{fmtB13Expr(w)}{w.expression_intended ? <span style={{ marginLeft: 4, fontSize: 7.5, color: T.muted }}>int</span> : null}</td>
                            <td style={{ padding: "5px 8px", color: T.light }}>{termLabel(w.lane_canon)}</td>
                            <td style={{ padding: "5px 8px", color: T.purple }}>{termLabel(w.resolution_driver)}</td>
                            <td style={{ padding: "5px 8px", color: T.green }}>{w.ev_pct != null ? `EV ${(w.ev_pct * 100).toFixed(0)}%` : w.computed_rr != null ? `${Number(w.computed_rr).toFixed(2)}:1` : "—"}</td>
                            <td style={{ padding: "5px 8px", color: T.light }} title={`edge ${w.edge_grade ?? "—"} · score ${w.score ?? "—"}`}>{w.entry_date ? `${w.entry_date} @ ${w.entry_price != null ? Number(w.entry_price).toFixed(2) : "n/a"}` : "—"}</td>
                            <td style={{ padding: "5px 8px", color: T.light, maxWidth: 230, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={`enters when: ${w.would_enter_if || w.blocked_by || "—"}${w.note ? "\n" + w.note : ""}`}>{w.dated_milestone || "—"}</td>
                            <td style={{ padding: "5px 8px" }}>
                              {(w.cro_conditions || []).length > 0
                                ? <span title={w.cro_conditions.join("\n• ").replace(/^/, "• ")} style={{ fontSize: 8.5, color: "#d97706", border: "1px solid rgba(217,151,6,0.3)", borderRadius: 3, padding: "0 4px", cursor: "help" }}>⚠ {w.cro_conditions.length} cond</span>
                                : <span style={{ fontSize: 8.5, color: T.muted }}>clean</span>}
                            </td>
                            <td style={{ padding: "5px 8px" }}>
                              {w.de_prioritized
                                ? <span title={`Director de-prioritized: ${w.deprioritization_rationale || w.stance_change_rationale || "no reason given"}`} style={{ fontSize: 8.5, color: "#d97706", border: "1px solid rgba(217,151,6,0.3)", borderRadius: 3, padding: "0 4px", cursor: "help" }}>↓ deprio</span>
                                : <span style={{ fontSize: 8.5, color: T.green }}>active</span>}
                            </td>
                            <td style={{ padding: "5px 0" }}>
                              {(() => {
                                const q = liveQuotes[w.symbol];
                                if (!q || q.price == null) return <span style={{ fontSize: 9, color: T.muted }}>—</span>;
                                const pnl = w.entry_price ? (q.price / w.entry_price - 1) * 100 : null;
                                return (
                                  <span title={`live ${q.price.toFixed(2)} · day ${q.day != null ? `${q.day >= 0 ? "+" : ""}${q.day.toFixed(2)}%` : "—"} · vs entry ${pnl != null ? `${pnl >= 0 ? "+" : ""}${pnl.toFixed(1)}%` : "—"}`}
                                    style={{ display: "inline-flex", flexDirection: "column", lineHeight: 1.3 }}>
                                    <span style={{ color: T.text, fontWeight: 700 }}>
                                      {q.price.toFixed(2)}
                                      {q.day != null && <span style={{ marginLeft: 5, fontSize: 8.5, color: q.day >= 0 ? T.green : T.red }}>{q.day >= 0 ? "+" : ""}{q.day.toFixed(1)}%</span>}
                                    </span>
                                    {pnl != null && <span style={{ fontSize: 8.5, color: pnl >= 0 ? T.green : T.red }}>pos {pnl >= 0 ? "+" : ""}{pnl.toFixed(1)}%</span>}
                                  </span>
                                );
                              })()}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* WATCHLIST TRACK RECORD — its own card (the 4th card), parallel to the basket's.
                  The watchlist tracked as a SEPARATE equal-weight cohort: did the queue move as the
                  Director expected? */}
              {(B13.watchlist || []).length > 0 && (() => {
                    const wl = B13.watchlist || [];
                    const lastWlMark: any = (B13.watchlist_marks || [])[(B13.watchlist_marks || []).length - 1];
                    const wActual = (w: any): number | null => {
                      const q = liveQuotes[w.symbol];
                      if (q?.price != null && w.entry_price) return (q.price / w.entry_price - 1) * 100;
                      const ms = lastWlMark?.seats?.[w.symbol];   // fall back to the latest daily mark
                      return ms?.ret_pct != null ? ms.ret_pct : null;
                    };
                    let liveRet = 0, nLive = 0;
                    wl.forEach((w: any) => { const a = wActual(w); if (a != null) { liveRet += a; nLive++; } });
                    const navLive = nLive ? 100 + liveRet / nLive : null;
                    const actAvg = nLive ? liveRet / nLive : 0;
                    const exps = wl.map((w: any) => w.expected_pct).filter((v: any) => v != null);
                    const expAvg = exps.length ? exps.reduce((s: number, v: number) => s + v, 0) / exps.length : 0;
                    const marks: any[] = [...(B13.watchlist_marks || [])];
                    if (navLive != null) {
                      const last = marks[marks.length - 1];
                      const todayIso = new Date().toISOString().slice(0, 10);
                      if (last && last.date === todayIso) marks[marks.length - 1] = { ...last, nav: navLive };
                      else marks.push({ date: todayIso, nav: navLive });
                    }
                    const navs = marks.map(m => m.nav);
                    const yMin = Math.min(100, ...navs) - 0.5, yMax = Math.max(100, ...navs) + 0.5;
                    const W = 600, H = 90, PX = 6, PY = 8;
                    const xOf = (i: number) => marks.length > 1 ? PX + (W - 2 * PX) * (i / (marks.length - 1)) : W / 2;
                    const yOf = (v: number) => PY + (H - 2 * PY) * (1 - (v - yMin) / (yMax - yMin || 1));
                    const pts = marks.map((m, i) => `${xOf(i).toFixed(1)},${yOf(m.nav).toFixed(1)}`).join(" ");
                    const lastNav = navs.length ? navs[navs.length - 1] : 100;
                    const maxAbs = Math.max(5, ...wl.map((w: any) => Math.abs(w.expected_pct || 0)), ...wl.map((w: any) => Math.abs(wActual(w) ?? 0)));
                    const barW = (v: number) => Math.min(70, Math.abs(v) / maxAbs * 70);
                    const KPI = ({ label, value, tone }: any) => (
                      <div style={{ padding: "5px 10px", border: `1px solid ${T.border}`, borderRadius: 6, minWidth: 84 }}>
                        <div style={{ fontSize: 7.5, textTransform: "uppercase", letterSpacing: "0.06em", color: T.muted }}>{label}</div>
                        <div style={{ fontSize: 13, fontWeight: 800, fontFamily: T.mono, color: tone || T.text }}>{value}</div>
                      </div>
                    );
                    return (
                      <div style={{ background: T.card, border: "1px dashed rgba(59,130,246,0.35)", borderRadius: 8, padding: "13px 18px", marginBottom: 24 }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
                          <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.08em", color: T.blue }}>⬡ WATCHLIST — ON-DECK TRACK RECORD</span>
                          <span style={{ fontSize: 8.5, color: T.muted }}>equal-weight cohort · NAV 100 at each name&apos;s watchlist entry · separate from the basket — does the queue move as the Director expects?</span>
                        </div>
                        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 10 }}>
                          <KPI label="NAV (live)" value={navLive != null ? navLive.toFixed(2) : lastNav.toFixed(2)} tone={(navLive ?? lastNav) >= 100 ? T.green : T.red} />
                          <KPI label="Cohort P&L" value={`${actAvg >= 0 ? "+" : ""}${actAvg.toFixed(2)}%`} tone={actAvg >= 0 ? T.green : T.red} />
                          <KPI label="Expected (avg)" value={`+${expAvg.toFixed(1)}%`} tone={T.blue} />
                          <KPI label="Capture" value={expAvg ? `${(actAvg / expAvg * 100).toFixed(0)}%` : "—"} />
                          <KPI label="Names" value={String(nLive || wl.length)} />
                          <KPI label="Marks" value={String((B13.watchlist_marks || []).length)} />
                        </div>
                        <div style={{ display: "grid", gridTemplateColumns: "minmax(280px, 1.1fr) minmax(300px, 1fr)", gap: 18, alignItems: "start" }}>
                          <div>
                            <div style={{ fontSize: 8, fontWeight: 700, textTransform: "uppercase", color: T.muted, letterSpacing: "0.05em", marginBottom: 4 }}>NAV history</div>
                            <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
                              <line x1={PX} x2={W - PX} y1={yOf(100)} y2={yOf(100)} stroke="rgba(255,255,255,0.15)" strokeDasharray="3 3" />
                              <text x={W - PX} y={yOf(100) - 3} textAnchor="end" fontSize="8" fill="rgba(255,255,255,0.35)" fontFamily="monospace">100</text>
                              {marks.length > 1 ? <polyline points={pts} fill="none" stroke={lastNav >= 100 ? "var(--green)" : "var(--red)"} strokeWidth="1.6" /> : null}
                              {marks.map((m, i) => (
                                <circle key={m.date} cx={xOf(i)} cy={yOf(m.nav)} r="2.6" fill={m.nav >= 100 ? "var(--green)" : "var(--red)"}>
                                  <title>{m.date} · NAV {Number(m.nav).toFixed(2)}</title>
                                </circle>
                              ))}
                              {marks.length > 0 && (
                                <text x={xOf(marks.length - 1)} y={yOf(lastNav) - 6} textAnchor="end" fontSize="9" fontWeight="700" fill={lastNav >= 100 ? "var(--green)" : "var(--red)"} fontFamily="monospace">{lastNav.toFixed(2)}</text>
                              )}
                            </svg>
                            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 8, fontFamily: T.mono, color: T.muted }}>
                              <span>{marks[0]?.date || ""}</span><span>{marks[marks.length - 1]?.date || ""}</span>
                            </div>
                          </div>
                          <div>
                            <div style={{ fontSize: 8, fontWeight: 700, textTransform: "uppercase", color: T.muted, letterSpacing: "0.05em", marginBottom: 4 }}>Expected vs actual (per name, underlying %)</div>
                            {wl.map((w: any) => {
                              const exp = w.expected_pct, act = wActual(w);
                              return (
                                <div key={w.symbol} style={{ display: "grid", gridTemplateColumns: "52px 76px 1fr", alignItems: "center", gap: 6, padding: "2px 0", fontFamily: T.mono }}>
                                  <span style={{ fontSize: 9.5, fontWeight: 800, color: T.text }}>{w.symbol}</span>
                                  <span style={{ fontSize: 9 }}>
                                    <span style={{ color: act != null ? (act >= 0 ? T.green : T.red) : T.muted }}>{act != null ? `${act >= 0 ? "+" : ""}${act.toFixed(1)}%` : "—"}</span>
                                    <span style={{ color: T.muted }}> / {exp != null ? `+${exp.toFixed(0)}%` : "—"}</span>
                                  </span>
                                  <span style={{ position: "relative", height: 10 }}>
                                    {exp != null && <span title={`expected +${exp.toFixed(1)}%`} style={{ position: "absolute", left: 0, top: 1, height: 8, width: barW(exp), border: "1px solid rgba(59,130,246,0.55)", borderRadius: 2, background: "rgba(59,130,246,0.10)" }} />}
                                    {act != null && <span title={`actual ${act >= 0 ? "+" : ""}${act.toFixed(1)}%`} style={{ position: "absolute", left: 0, top: 3, height: 4, width: barW(act), borderRadius: 2, background: act >= 0 ? "var(--green)" : "var(--red)" }} />}
                                  </span>
                                </div>
                              );
                            })}
                            <div style={{ fontSize: 8, color: T.muted, marginTop: 4 }}>outline = Director expectation · solid = live move since watchlist entry</div>
                          </div>
                        </div>
                      </div>
                    );
                  })()}
              </>
            );
          })() : (
            <div style={{ minHeight: "40vh", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 12, color: T.muted, textAlign: "center" }}>
              No Basket 13 entries yet — run the catalyst debate (backend/_basket13_README.md), then _basket13_export.py.
            </div>
          ) : loadingScan ? (
            <div style={{ minHeight: "60vh", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 16 }}>
              <RefreshCw size={36} color={T.green} className="animate-spin" />
              <div style={{ fontSize: 13, color: T.muted, textAlign: "center" }}>
                Running multi-strategy cognitive extraction pipeline for <strong style={{ color: T.text }}>{selectedSymbol}</strong>...
                <br />
                <span style={{ fontSize: 11, color: T.light }}>Scanning SEC 8-Ks, news networks, 6-quarter earnings transcripts & option chain snapshots.</span>
              </div>
            </div>
          ) : scanError ? (
            <div style={{ minHeight: "50vh", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12, color: T.red, textAlign: "center" }}>
              <AlertCircle size={36} />
              <div style={{ fontWeight: 700 }}>Scan Failed</div>
              <div style={{ fontSize: 12, color: T.light }}>{scanError}</div>
              <button 
                onClick={() => setSelectedSymbol(selectedSymbol)} 
                style={{ background: T.card, border: `1px solid ${T.border}`, padding: "8px 16px", borderRadius: 6, color: T.text, fontSize: 11, cursor: "pointer", display: "flex", alignItems: "center", gap: 6, marginTop: 12 }}
              >
                <RefreshCw size={12} /> Retry Scan
              </button>
            </div>
          ) : report ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span onClick={() => setView("basket")} style={{ fontSize: 10, fontWeight: 800, fontFamily: T.mono, color: T.blue, border: "1px solid rgba(59,130,246,0.3)", borderRadius: 4, padding: "3px 10px", cursor: "pointer", userSelect: "none" }}>← BASKET 13</span>
                <span style={{ fontSize: 9, color: T.muted, textTransform: "uppercase", letterSpacing: "0.06em" }}>Stock depth analysis</span>
              </div>

              {/* TOP HEADER SUMMARY CARD */}
              <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 8, padding: 20, boxShadow: "var(--shadow-md)" }}>
                <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "flex-start", gap: 16, marginBottom: 16 }}>
                  <div>
                    <div style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: 10, marginBottom: 4 }}>
                      <h1 style={{ fontSize: 24, fontWeight: 800, margin: 0 }}>
                        {report.company_name}
                      </h1>
                      <span style={{ fontSize: 14, fontWeight: 700, color: T.muted }}>
                        ({report.symbol})
                      </span>
                      {report.recommendation && (
                        <span style={{ 
                          fontSize: 10, fontWeight: 800, padding: "3px 9px", borderRadius: 6,
                          borderWidth: 1, borderStyle: "solid",
                          ...getRecommendationStyle(report.recommendation)
                        }}>
                          {report.recommendation}
                        </span>
                      )}
                      {(report as any).tier && (() => {
                        const tu = String((report as any).tier).toUpperCase();
                        const c = tu === "ACTIVE" ? "#14b87a" : tu === "CONTINGENT" ? "#a855f7" : "#d97706";
                        return (
                          <span style={{ fontSize: 10, fontWeight: 800, padding: "3px 9px", borderRadius: 6, border: `1px solid ${c}`, color: c, letterSpacing: "0.04em" }} title="Catalyst tier (gate hardness): Active = sized · Watch = tracking to harden · Waiting on a trigger = gated on a pending event">
                            {termLabel((report as any).tier)}
                          </span>
                        );
                      })()}

                      <button
                        onClick={() => toggleWatchlist(
                          report.symbol, 
                          report.company_name, 
                          report.catalyst_density_score,
                          report.price,
                          report.market_cap,
                          report.is_merger_arb
                        )}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 6,
                          background: watchlist.some(w => w.symbol === report.symbol.toUpperCase().trim()) ? "rgba(245,158,11,0.12)" : "transparent",
                          border: `1px solid ${watchlist.some(w => w.symbol === report.symbol.toUpperCase().trim()) ? "var(--amber, #f59e0b)" : T.border}`,
                          borderRadius: 6,
                          padding: "3px 8px",
                          fontSize: 10,
                          fontWeight: 700,
                          color: watchlist.some(w => w.symbol === report.symbol.toUpperCase().trim()) ? "var(--amber, #f59e0b)" : T.muted,
                          cursor: "pointer",
                          transition: "all 0.15s",
                          fontFamily: T.mono,
                          marginLeft: 8
                        }}
                      >
                        <Star size={11} fill={watchlist.some(w => w.symbol === report.symbol.toUpperCase().trim()) ? "var(--amber, #f59e0b)" : "none"} color={watchlist.some(w => w.symbol === report.symbol.toUpperCase().trim()) ? "var(--amber, #f59e0b)" : T.muted} />
                        {watchlist.some(w => w.symbol === report.symbol.toUpperCase().trim()) ? "WATCHED" : "ADD TO WATCHLIST"}
                      </button>

                      <button
                        onClick={() => handleForceRefresh(report.symbol)}
                        disabled={loadingScan}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: 6,
                          background: "transparent",
                          border: `1px solid ${T.border}`,
                          borderRadius: 6,
                          padding: "3px 8px",
                          fontSize: 10,
                          fontWeight: 700,
                          color: T.green,
                          cursor: "pointer",
                          transition: "all 0.15s",
                          fontFamily: T.mono,
                          marginLeft: 8
                        }}
                      >
                        <RefreshCw size={11} className={loadingScan ? "animate-spin" : ""} style={{ animation: loadingScan ? "spin 1s linear infinite" : "none" }} />
                        RE-SCAN
                      </button>
                    </div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 16, fontSize: 11, color: T.light, marginTop: 4 }}>
                      <span>Price: <strong style={{ color: T.text }}>${(((report as any).live_price ?? report.price))?.toFixed(2) || "N/A"}</strong>{(report as any).live_price != null ? <span style={{ color: T.muted, fontSize: 9 }}> live</span> : null}</span>
                      <span>Market Cap: <strong style={{ color: T.text }}>{formatMarketCap(report.market_cap)}</strong></span>
                      {report.cache_timestamp && (
                        <span title="Date of the full AI Loeb deep-scan; price is live. Use RE-SCAN to refresh the analysis.">Deep-scanned: <strong style={{ color: T.text }}>{formatCacheDate(report.cache_timestamp)}</strong></span>
                      )}
                    </div>
                  </div>

                  {/* SCORE GAUGES */}
                  <div style={{ display: "flex", gap: 16 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 16px", background: "rgba(168,85,247,0.06)", borderRadius: 6, border: `1px solid ${T.purple}` }}>
                      <div style={{ textAlign: "right" }}>
                        <Tip k="CATALYST_SCORE"><div style={{ fontSize: 8, fontWeight: 700, color: T.muted, letterSpacing: "0.05em", textTransform: "uppercase" }}>Loeb Score</div></Tip>
                        <div style={{ fontSize: 9, color: T.light }}>Catalyst Density</div>
                      </div>
                      <div style={{ fontSize: 24, fontWeight: 800, color: T.purple, fontFamily: T.mono }}>
                        {(report.adjusted_loeb_score ?? report.catalyst_density_score)?.toFixed(1) || "N/A"}
                      </div>
                    </div>
                    
                    {(() => { const rr = rrDisplay(report as any); return (
                    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 16px", background: "rgba(255,255,255,0.03)", borderRadius: 6, border: `1px solid ${toneColor(rr.tone)}` }}>
                      <div style={{ textAlign: "right" }}>
                        <Tip k="RR" extra={rr.rawForTooltip}><div style={{ fontSize: 8, fontWeight: 700, color: T.muted, letterSpacing: "0.05em", textTransform: "uppercase" }}>Risk / Reward</div></Tip>
                        <div style={{ fontSize: 9, color: T.light }}>vs live price</div>
                      </div>
                      <div style={{ fontSize: 16, fontWeight: 800, color: toneColor(rr.tone), fontFamily: T.mono }}>
                        {rr.text}
                      </div>
                    </div>
                    ); })()}

                    {report.convergence_score !== undefined && (
                      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 16px", background: "rgba(59,130,246,0.06)", borderRadius: 6, border: `1px solid ${T.blue}` }}>
                        <div style={{ textAlign: "right" }}>
                          <div style={{ fontSize: 8, fontWeight: 700, color: T.muted, letterSpacing: "0.05em", textTransform: "uppercase" }}>Convergence</div>
                          <div style={{ fontSize: 9, color: T.light }}>Catalyst Tracks</div>
                        </div>
                        <div style={{ fontSize: 24, fontWeight: 800, color: T.blue, fontFamily: T.mono }}>
                          {report.convergence_score.toFixed(1)}
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                <div style={{ borderTop: `1px solid ${T.border}`, paddingTop: 16 }}>
                  <div style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", color: T.muted, letterSpacing: "0.08em", marginBottom: 6 }}>
                    Opportunistic AI Thesis Summary
                  </div>
                  <p style={{ fontSize: 12, color: T.text, lineHeight: 1.6, margin: 0 }}>
                    {report.analysis_summary}
                  </p>

                  {/* Skeptic correction — reconciles a thesis whose prose argues a higher score than the skeptic's final */}
                  {(report as any).verify_verdict === "CONFIRMED_WITH_CORRECTIONS" && report.bloom_catalysts?.catalyst_3?.evidence && (
                    <div style={{ marginTop: 10, padding: "9px 12px", background: "rgba(217,151,6,0.06)", border: "1px solid rgba(217,151,6,0.25)", borderRadius: 6 }}>
                      <Tip k="CONFIRMED_WITH_CORRECTIONS"><span style={{ fontSize: 9, fontWeight: 800, textTransform: "uppercase", color: "#d97706", letterSpacing: "0.05em" }}>⚠ Skeptic correction</span></Tip>
                      <div style={{ fontSize: 10.5, color: T.light, lineHeight: 1.5, marginTop: 4 }}>{report.bloom_catalysts.catalyst_3.evidence}</div>
                    </div>
                  )}

                  {/* Post-board enforcement audit (manual §6/§9): driver tag + corrections trail */}
                  {((report as any).resolution_driver || ((report as any).corrections?.length > 0)) && (
                    <div style={{ marginTop: 12, padding: "10px 14px", background: "rgba(196,181,253,0.05)", border: `1px solid rgba(196,181,253,0.18)`, borderRadius: 6 }}>
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", marginBottom: (report as any).corrections?.length ? 6 : 0 }}>
                        <span style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", color: T.purple, letterSpacing: "0.06em" }}>Post-board pass</span>
                        {(report as any).resolution_driver && (
                          <span style={{ fontSize: 9, fontFamily: T.mono, padding: "1px 6px", borderRadius: 3, background: "rgba(196,181,253,0.14)", color: T.purple, border: "1px solid rgba(196,181,253,0.20)" }}>
                            ⛓ driver: {termLabel((report as any).resolution_driver)}
                          </span>
                        )}
                        {(report as any).lane_canon && (
                          <span style={{ fontSize: 9, fontFamily: T.mono, color: T.light }}>lane: {termLabel((report as any).lane_canon)}</span>
                        )}
                        {B13_SEATS[report.symbol] && (
                          <span title={`Basket 13 (paper catalyst sleeve) — entered ${B13_SEATS[report.symbol].entry_date} @ ${B13_SEATS[report.symbol].entry_price ?? "n/a"}${(B13_SEATS[report.symbol].cro_conditions || []).length ? `\nCRO conditions:\n- ${B13_SEATS[report.symbol].cro_conditions.join("\n- ")}` : ""}`}
                            style={{ fontSize: 9, fontWeight: 800, fontFamily: T.mono, padding: "1px 6px", borderRadius: 3, background: "rgba(59,130,246,0.14)", color: T.blue, border: "1px solid rgba(59,130,246,0.25)" }}>
                            ⬡ B13 seat: {B13_SEATS[report.symbol].weight_pct}% {fmtB13Expr(B13_SEATS[report.symbol])}{B13_SEATS[report.symbol].staging ? " · staging" : ""}
                          </span>
                        )}
                      </div>
                      {(report as any).corrections?.length > 0 && (
                        <div style={{ fontSize: 10, color: T.light, lineHeight: 1.5 }}>
                          <span style={{ color: T.muted, fontWeight: 700 }}>Corrections applied: </span>
                          {(report as any).corrections.join(" · ")}
                          {(report as any).adjusted_loeb_score_orig != null && (report as any).adjusted_loeb_score_orig !== report.adjusted_loeb_score && (
                            <span> · score {(report as any).adjusted_loeb_score_orig} → {report.adjusted_loeb_score}</span>
                          )}
                          {(report as any).tier_orig && (report as any).tier_orig !== (report as any).tier && (
                            <span> · tier {(report as any).tier_orig} → {(report as any).tier}</span>
                          )}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Phase-2 computed edge / valuation build (the EDGE axis, with the work shown) */}
                  {(report as any).valuation_method && (
                    <div style={{ marginTop: 12, padding: "12px 14px", background: "rgba(20,184,122,0.04)", border: `1px solid ${T.border}`, borderRadius: 6 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 8 }}>
                        <span style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", color: T.green, letterSpacing: "0.06em" }}>Edge · computed R:R</span>
                        <span style={{ fontSize: 9, fontFamily: T.mono, color: T.muted }}>({(report as any).valuation_method})</span>
                        {(report as any).edge_grade && (report as any).edge_grade !== "?" && (
                          <span style={{ fontSize: 9, fontWeight: 800, padding: "1px 6px", borderRadius: 3, background: (report as any).edge_grade === "H" ? "rgba(20,184,122,0.18)" : (report as any).edge_grade === "M" ? "rgba(217,151,6,0.18)" : "rgba(239,68,68,0.16)", color: (report as any).edge_grade === "H" ? T.green : (report as any).edge_grade === "M" ? "#d97706" : "#ef4444" }}>EDGE {(report as any).edge_grade}</span>
                        )}
                        {((report as any).edge_flags || []).map((f: string) => (<Tip key={f} k={f.split(":")[0]}><span style={{ fontSize: 8, fontFamily: T.mono, color: "#d97706", border: "1px solid rgba(217,151,6,0.3)", borderRadius: 3, padding: "1px 4px" }}>{f}</span></Tip>))}
                      </div>
                      {(report as any).valuation_method === "binary_prob" ? (
                        <div style={{ display: "flex", gap: 14, flexWrap: "wrap", fontSize: 11, fontFamily: T.mono, color: T.text }}>
                          <span>P(win) <b>{(((report as any).win_prob || 0) * 100).toFixed(0)}%</b></span>
                          <span style={{ color: T.green }}>up-leg <b>+${((report as any).up_leg || 0).toFixed(2)}</b></span>
                          <span style={{ color: "#ef4444" }}>down-leg <b>−${((report as any).down_leg || 0).toFixed(2)}</b></span>
                          <span>payoff <b>{((report as any).payoff || 0).toFixed(2)}×</b></span>
                          <span>EV <b style={{ color: ((report as any).ev_pct || 0) >= 0 ? T.green : "#ef4444" }}>{((report as any).ev_pct || 0) >= 0 ? "+" : ""}{(((report as any).ev_pct || 0) * 100).toFixed(1)}%</b></span>
                          <span style={{ color: T.muted }}>(barbell — not a single R:R)</span>
                        </div>
                      ) : (
                        <div style={{ display: "flex", gap: 14, flexWrap: "wrap", fontSize: 11, fontFamily: T.mono, color: T.text }}>
                          <Tip k="RR" extra={rrDisplay(report as any).rawForTooltip}><span>R:R <b style={{ color: toneColor(rrDisplay(report as any).tone) }}>{rrDisplay(report as any).text}</b></span></Tip>
                          <span style={{ color: T.green }}>target <b>${(((report as any).sop_built ?? (report as any).fair_value_target) || 0).toFixed(2)}</b>{(report as any).sop_built != null ? <span style={{ color: T.muted, fontWeight: 400 }}> (build)</span> : null}</span>
                          <span>live <b>${((report as any).live_price || report.price || 0).toFixed(2)}</b></span>
                          <span style={{ color: "#ef4444" }}>floor <b>${((report as any).downside_floor || 0).toFixed(2)}</b></span>
                          {(report as any).drift != null && (<span style={{ color: T.muted }}>drift {((report as any).drift * 100).toFixed(1)}%</span>)}
                        </div>
                      )}
                      {((report as any).edge_flags || []).includes("SOP_TARGET_MISMATCH") && (
                        <div style={{ fontSize: 9, color: "#d97706", marginTop: 4 }}>⚠ asserted target ${((report as any).fair_value_target || 0).toFixed(2)} ≠ reconciled build ${((report as any).sop_built || 0).toFixed(2)} — R:R uses the build (premium/advocacy stripped)</div>
                      )}
                      {(report as any).valuation?.advocacy_target != null && (
                        <div style={{ fontSize: 9, color: T.muted, marginTop: 2 }}>advocacy ceiling ${Number((report as any).valuation.advocacy_target).toFixed(2)} — activist target, displayed only (never in the R:R)</div>
                      )}
                      {(report as any).valuation?.valuation_basis && (
                        <div style={{ fontSize: 10, color: T.light, marginTop: 6, lineHeight: 1.5 }}><span style={{ color: T.muted, fontWeight: 700 }}>Basis: </span>{(report as any).valuation.valuation_basis}</div>
                      )}
                      {(report as any).valuation?.sop_components?.length > 0 && (
                        <div style={{ marginTop: 8 }}>
                          <div style={{ fontSize: 8, fontWeight: 700, textTransform: "uppercase", color: T.muted, marginBottom: 4 }}>Sum-of-parts build</div>
                          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 10, fontFamily: T.mono }}>
                            <thead><tr style={{ color: T.muted }}><th style={{ textAlign: "left", padding: "2px 4px" }}>Segment</th><th style={{ textAlign: "right" }}>Metric</th><th style={{ textAlign: "right" }}>×</th><th style={{ textAlign: "right", padding: "2px 4px" }}>EV</th></tr></thead>
                            <tbody>
                              {(report as any).valuation.sop_components.map((s: any, idx: number) => (
                                <tr key={idx} style={{ borderTop: `1px solid ${T.border}` }}>
                                  <td style={{ padding: "2px 4px", color: T.text }} title={s.basis}>{s.segment}</td>
                                  <td style={{ textAlign: "right", color: T.light }}>{s.metric_value != null ? `${s.metric_value} ${s.driver_metric || ""}` : "—"}</td>
                                  <td style={{ textAlign: "right", color: T.light }}>{s.multiple != null ? `${s.multiple}×` : "—"}</td>
                                  <td style={{ textAlign: "right", padding: "2px 4px", color: T.text }}>{s.ev_contribution != null ? `$${Number(s.ev_contribution).toLocaleString()}` : "—"}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          <div style={{ fontSize: 9, color: T.muted, marginTop: 4 }}>− net debt ${Number((report as any).valuation.net_debt || 0).toLocaleString()} − adj ${Number((report as any).valuation.adjustments || 0).toLocaleString()} ÷ {Number((report as any).valuation.shares_out || 0).toLocaleString()} sh = <b style={{ color: T.green }}>${((report as any).fair_value_target || 0).toFixed(2)}</b></div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Catalyst Nature Timing & Re-rate Distinction */}
                  {(report.catalyst_nature || report.re_rate_status) && (
                    <div style={{ marginTop: 12, padding: "10px 14px", background: "rgba(255,255,255,0.02)", border: `1px solid ${T.border}`, borderRadius: 6 }}>
                      <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 6 }}>
                        {report.catalyst_nature && (
                          <span style={{
                            fontSize: 9,
                            fontWeight: 700,
                            padding: "2px 6px",
                            borderRadius: 4,
                            background: report.catalyst_nature === "pricing_dislocation" ? "rgba(20, 184, 122, 0.12)" : "rgba(59, 130, 246, 0.12)",
                            color: report.catalyst_nature === "pricing_dislocation" ? T.green : T.blue,
                            border: `1px solid ${report.catalyst_nature === "pricing_dislocation" ? T.greenBorder || T.green : T.blue}`
                          }}>
                            {report.catalyst_nature === "pricing_dislocation" ? "ALPHA-BEARING DISLOCATION" : "MECHANICAL EXECUTION"}
                          </span>
                        )}
                        {report.re_rate_status && (
                          <span style={{
                            fontSize: 9,
                            fontWeight: 700,
                            padding: "2px 6px",
                            borderRadius: 4,
                            background: report.re_rate_status === "complete" ? "rgba(239, 68, 68, 0.12)" : (report.re_rate_status === "partial" ? "rgba(245, 158, 11, 0.12)" : "rgba(20, 184, 122, 0.12)"),
                            color: report.re_rate_status === "complete" ? T.red : (report.re_rate_status === "partial" ? T.amber : T.green),
                            border: `1px solid ${report.re_rate_status === "complete" ? T.red : (report.re_rate_status === "partial" ? T.amber : T.green)}`
                          }}>
                            RE-RATE: {report.re_rate_status.toUpperCase()}
                          </span>
                        )}
                        {report.is_dher_pattern && (
                          <span style={{
                            fontSize: 9,
                            fontWeight: 700,
                            padding: "2px 6px",
                            borderRadius: 4,
                            background: "rgba(168, 85, 247, 0.12)",
                            color: T.purple,
                            border: `1px solid ${T.purple}`
                          }}>
                            DHER CONVERGENCE
                          </span>
                        )}
                      </div>
                      {report.catalyst_nature_rationale && (
                        <div style={{ fontSize: 11, color: T.light, lineHeight: 1.4 }}>
                          <strong style={{ color: T.text }}>Trade Timing Insight:</strong> {report.catalyst_nature_rationale}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              </div>

              {/* MERGER ARBITRAGE CARD (DYNAMIC MATH & RISK) */}
              {report.merger_arb_data && mergerArbComputed && (
                <div style={{ 
                  background: "linear-gradient(135deg, rgba(20,184,122,0.04) 0%, rgba(59,130,246,0.04) 100%)", 
                  border: `1px solid ${T.border}`, 
                  borderRadius: 8, 
                  padding: 20,
                  boxShadow: "var(--shadow-md)"
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: T.blue, textTransform: "uppercase", marginBottom: 16, paddingBottom: 6, borderBottom: `2px solid ${T.blue}` }}>
                    <TrendingUp size={12} /> Active Merger Arbitrage Deal & Spread Analysis
                  </div>
                  
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1.5fr 1.5fr", gap: 20, marginBottom: 16 }}>
                    
                    {/* Deal Terms column */}
                    <div>
                      <div style={{ fontSize: 9, fontWeight: 700, color: T.muted, textTransform: "uppercase", marginBottom: 8 }}>Deal Terms</div>
                      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                        <div style={{ fontSize: 11 }}>
                          Acquirer: <strong style={{ color: T.text }}>{report.merger_arb_data.acquirer_name || "Private Equity"}</strong> {report.merger_arb_data.acquirer_symbol && report.merger_arb_data.acquirer_symbol !== "CASH" && <span style={{ color: T.muted }}>({report.merger_arb_data.acquirer_symbol})</span>}
                        </div>
                        <div style={{ fontSize: 11 }}>
                          Cash Component: <strong style={{ color: T.text }}>${report.merger_arb_data.cash_component?.toFixed(2) || "0.00"}</strong>
                        </div>
                        <div style={{ fontSize: 11 }}>
                          Stock Component: <strong style={{ color: T.text }}>{report.merger_arb_data.stock_component_ratio ? `${report.merger_arb_data.stock_component_ratio.toFixed(4)} shares` : "None (All-Cash)"}</strong>
                        </div>
                        
                        {report.merger_arb_data.acquirer_symbol && report.merger_arb_data.acquirer_symbol !== "CASH" && (
                          <div style={{ marginTop: 6 }}>
                            <label style={{ fontSize: 8, color: T.muted, textTransform: "uppercase", display: "block", marginBottom: 2 }}>
                              Acquirer Price Input
                            </label>
                            <input
                              type="number"
                              step="0.01"
                              value={customAcquirerPrice}
                              onChange={(e) => setCustomAcquirerPrice(e.target.value === "" ? "" : parseFloat(e.target.value))}
                              style={{
                                background: "rgba(0,0,0,0.2)",
                                border: `1px solid ${T.border}`,
                                borderRadius: 4,
                                padding: "4px 8px",
                                fontSize: 11,
                                color: T.text,
                                fontFamily: T.mono,
                                width: "100%",
                                outline: "none"
                              }}
                            />
                            {customAcquirerPrice !== "" && (
                              <button
                                type="button"
                                onClick={() => setCustomAcquirerPrice("")}
                                style={{
                                  background: "none",
                                  border: "none",
                                  color: T.muted,
                                  fontSize: 8,
                                  textTransform: "uppercase",
                                  cursor: "pointer",
                                  padding: 0,
                                  marginTop: 4,
                                  display: "block"
                                }}
                              >
                                Reset to Live (${report.merger_arb_data.acquirer_price?.toFixed(2)})
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Spread Valuation column */}
                    <div style={{ borderLeft: `1px solid ${T.border}`, paddingLeft: 20 }}>
                      <div style={{ fontSize: 9, fontWeight: 700, color: T.muted, textTransform: "uppercase", marginBottom: 8 }}>Live Spread Math</div>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                        <div>
                          <div style={{ fontSize: 9, color: T.light }}>Implied Deal Value</div>
                          <div style={{ fontSize: 16, fontWeight: 800, color: T.text, marginTop: 2, fontFamily: T.mono }}>
                            ${mergerArbComputed.impliedDealValue.toFixed(2)}
                          </div>
                        </div>
                        <div>
                          <div style={{ fontSize: 9, color: T.light }}>Gross Deal Spread</div>
                          <div style={{ 
                            fontSize: 16, 
                            fontWeight: 800, 
                            color: mergerArbComputed.grossSpreadVal >= 0 ? T.green : T.red, 
                            marginTop: 2, 
                            fontFamily: T.mono 
                          }}>
                            {mergerArbComputed.grossSpreadVal >= 0 ? "+" : ""}${mergerArbComputed.grossSpreadVal.toFixed(2)} ({mergerArbComputed.grossSpreadPct.toFixed(1)}%)
                          </div>
                        </div>
                      </div>
                      <div style={{ fontSize: 10, color: T.light, marginTop: 8 }}>
                        Expected Close: <strong style={{ color: T.text }}>{report.merger_arb_data.expected_close || "N/A"}</strong>
                      </div>
                    </div>

                    {/* Risk & Hedging column */}
                    <div style={{ borderLeft: `1px solid ${T.border}`, paddingLeft: 20 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                        <span style={{ fontSize: 9, fontWeight: 700, color: T.muted, textTransform: "uppercase" }}>Unhedged Risk Profile</span>
                        <span style={{ fontSize: 8, padding: "1px 5px", borderRadius: 3, background: T.redLight, color: T.red, fontWeight: 700 }}>NEGATIVE ASYMMETRY</span>
                      </div>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1.2fr", gap: 12 }}>
                        <div>
                          <div style={{ fontSize: 9, color: T.light }}>Downside if Break</div>
                          <div style={{ fontSize: 14, fontWeight: 700, color: T.red, marginTop: 2, fontFamily: T.mono }}>
                            -${mergerArbComputed.unhedgedDownside.toFixed(2)}
                          </div>
                        </div>
                        <div>
                          <div style={{ fontSize: 9, color: T.light }}>Unhedged R/R</div>
                          <div style={{ fontSize: 14, fontWeight: 700, color: T.red, marginTop: 2, fontFamily: T.mono }}>
                            {mergerArbComputed.unhedgedRRString}
                          </div>
                        </div>
                      </div>
                      <div style={{ fontSize: 10, color: T.light, marginTop: 8 }}>
                        Pre-Announce Reference: <span style={{ color: T.text }}>${report.merger_arb_data.pre_announce_price?.toFixed(2) || "N/A"}</span>
                      </div>
                    </div>

                  </div>

                  <div style={{ display: "flex", gap: 8, background: "rgba(239, 68, 68, 0.05)", border: `1px solid rgba(239, 68, 68, 0.2)`, borderRadius: 6, padding: "10px 12px", fontSize: 11, color: T.light, lineHeight: 1.5, marginBottom: 16 }}>
                    <AlertTriangle size={16} color={T.red} style={{ flexShrink: 0, marginTop: 1 }} />
                    <div>
                      <strong style={{ color: T.red }}>Risk Warning:</strong> Entering an unhedged long position in {report.symbol} at current levels has a negative unhedged risk/reward of {mergerArbComputed.unhedgedRRString}. To execute a standard risk-arbitrage trade, investors typically buy the target ({report.symbol}) and short the acquirer ({report.merger_arb_data.acquirer_symbol && report.merger_arb_data.acquirer_symbol !== "CASH" ? report.merger_arb_data.acquirer_symbol : "PE"}) at the exchange ratio of {report.merger_arb_data.stock_component_ratio || 0} to lock in the spread.
                    </div>
                  </div>

                  {/* Hedged Option Builder Suggestions */}
                  <div style={{ borderTop: `1px dashed ${T.border}`, paddingTop: 16 }}>
                    <div style={{ fontSize: 10, fontWeight: 700, color: T.green, textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 12 }}>
                      Hedged Option Builder Suggestions
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                      <div>
                        <div style={{ fontSize: 9, color: T.muted, textTransform: "uppercase", marginBottom: 6 }}>Target Hedges ({report.symbol})</div>
                        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                          {mergerArbComputed.targetHedges.map((hedge, idx) => (
                            <div key={idx} style={{ background: "rgba(255,255,255,0.01)", border: `1px solid ${T.border}`, borderRadius: 6, padding: "8px 10px" }}>
                              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                                <span style={{ fontSize: 10, fontWeight: 700, color: T.text }}>{hedge.strategy}</span>
                                <span style={{ fontSize: 8, padding: "1px 4px", borderRadius: 3, background: "rgba(20,184,122,0.1)", color: T.green, fontFamily: T.mono }}>{hedge.legs}</span>
                              </div>
                              <div style={{ fontSize: 9, color: T.light, lineHeight: 1.3 }}>{hedge.description}</div>
                            </div>
                          ))}
                        </div>
                      </div>
                      
                      <div>
                        <div style={{ fontSize: 9, color: T.muted, textTransform: "uppercase", marginBottom: 6 }}>
                          Acquirer Hedges {report.merger_arb_data.acquirer_symbol ? `(${report.merger_arb_data.acquirer_symbol})` : ""}
                        </div>
                        {mergerArbComputed.acquirerHedges.length > 0 ? (
                          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                            {mergerArbComputed.acquirerHedges.map((hedge, idx) => (
                              <div key={idx} style={{ background: "rgba(255,255,255,0.01)", border: `1px solid ${T.border}`, borderRadius: 6, padding: "8px 10px" }}>
                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
                                  <span style={{ fontSize: 10, fontWeight: 700, color: T.text }}>{hedge.strategy}</span>
                                  <span style={{ fontSize: 8, padding: "1px 4px", borderRadius: 3, background: "rgba(59,130,246,0.15)", color: T.blue, fontFamily: T.mono }}>{hedge.legs}</span>
                                </div>
                                <div style={{ fontSize: 9, color: T.light, lineHeight: 1.3 }}>{hedge.description}</div>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div style={{ height: "100%", display: "flex", alignItems: "center", justifyContent: "center", border: `1px dashed ${T.border}`, borderRadius: 6, padding: 16, fontSize: 10, color: T.muted, minHeight: 90 }}>
                            No stock component (All-Cash transaction) - no acquirer hedge required.
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* BLOOM STAGES TIMELINE */}
              <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 8, padding: 20 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: T.green, textTransform: "uppercase", marginBottom: 16, paddingBottom: 6, borderBottom: `2px solid ${T.greenLight}` }}>
                  <Compass size={12} /> Bloom Catalyst Timeline Stages
                </div>
                
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 16 }}>
                  
                  {/* Catalyst 1 */}
                  {report.bloom_catalysts?.catalyst_1 && (
                    <div style={{ 
                      background: "rgba(0,0,0,0.15)", borderRadius: 6, padding: 14, 
                      border: `1px solid ${report.bloom_catalysts.catalyst_1.detected ? T.purple : T.border}`,
                      opacity: report.bloom_catalysts.catalyst_1.detected ? 1 : 0.45
                    }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                        <span style={{ fontSize: 9, color: T.muted, textTransform: "uppercase" }}>Stage 1</span>
                        <span style={{ fontSize: 8, padding: "1px 5px", borderRadius: 3, background: report.bloom_catalysts.catalyst_1.detected ? T.purpleLight : "rgba(255,255,255,0.03)", color: report.bloom_catalysts.catalyst_1.detected ? T.purple : T.muted }}>
                          {report.bloom_catalysts.catalyst_1.detected ? "DETECTED" : "INACTIVE"}
                        </span>
                      </div>
                      <div style={{ fontSize: 12, fontWeight: 700, color: report.bloom_catalysts.catalyst_1.detected ? T.text : T.light, marginBottom: 6 }}>
                        <Tip k="STAGE_CATALYST">{report.bloom_catalysts.catalyst_1.title}</Tip>
                      </div>
                      <div style={{ fontSize: 11, color: T.light, lineHeight: 1.5, marginBottom: 8 }}>
                        {report.bloom_catalysts.catalyst_1.description}
                      </div>
                      {report.bloom_catalysts.catalyst_1.detected && (
                        <div style={{ fontSize: 9, color: T.purple, background: "rgba(168,85,247,0.06)", padding: "6px 8px", borderRadius: 4 }}>
                          <strong>Evidence:</strong> {report.bloom_catalysts.catalyst_1.evidence}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Catalyst 2 */}
                  {report.bloom_catalysts?.catalyst_2 && (
                    <div style={{ 
                      background: "rgba(0,0,0,0.15)", borderRadius: 6, padding: 14, 
                      border: `1px solid ${report.bloom_catalysts.catalyst_2.detected ? T.green : T.border}`,
                      opacity: report.bloom_catalysts.catalyst_2.detected ? 1 : 0.45
                    }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                        <span style={{ fontSize: 9, color: T.muted, textTransform: "uppercase" }}>Stage 2</span>
                        <span style={{ fontSize: 8, padding: "1px 5px", borderRadius: 3, background: report.bloom_catalysts.catalyst_2.detected ? T.greenLight : "rgba(255,255,255,0.03)", color: report.bloom_catalysts.catalyst_2.detected ? T.green : T.muted }}>
                          {report.bloom_catalysts.catalyst_2.detected ? "ACTIVE" : "INACTIVE"}
                        </span>
                      </div>
                      <div style={{ fontSize: 12, fontWeight: 700, color: report.bloom_catalysts.catalyst_2.detected ? T.text : T.light, marginBottom: 6 }}>
                        <Tip k="STAGE_MILESTONE">{report.bloom_catalysts.catalyst_2.title}</Tip>
                      </div>
                      <div style={{ fontSize: 11, color: T.light, lineHeight: 1.5, marginBottom: 8 }}>
                        {report.bloom_catalysts.catalyst_2.description}
                      </div>
                      {report.bloom_catalysts.catalyst_2.detected && (
                        <div style={{ fontSize: 9, color: T.green, background: "rgba(20,184,122,0.06)", padding: "6px 8px", borderRadius: 4 }}>
                          <strong>Evidence:</strong> {report.bloom_catalysts.catalyst_2.evidence}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Catalyst 3 */}
                  {report.bloom_catalysts?.catalyst_3 && (
                    <div style={{ 
                      background: "rgba(0,0,0,0.15)", borderRadius: 6, padding: 14, 
                      border: `1px solid ${report.bloom_catalysts.catalyst_3.detected ? T.blue : T.border}`,
                      opacity: report.bloom_catalysts.catalyst_3.detected ? 1 : 0.45
                    }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
                        <span style={{ fontSize: 9, color: T.muted, textTransform: "uppercase" }}>Stage 3</span>
                        <span style={{ fontSize: 8, padding: "1px 5px", borderRadius: 3, background: report.bloom_catalysts.catalyst_3.detected ? "rgba(59,130,246,0.18)" : "rgba(255,255,255,0.03)", color: report.bloom_catalysts.catalyst_3.detected ? T.blue : T.muted }}>
                          {report.bloom_catalysts.catalyst_3.detected ? "TRIGGERED" : "INACTIVE"}
                        </span>
                      </div>
                      <div style={{ fontSize: 12, fontWeight: 700, color: report.bloom_catalysts.catalyst_3.detected ? T.text : T.light, marginBottom: 6 }}>
                        <Tip k="STAGE_VERIFY">{report.bloom_catalysts.catalyst_3.title}</Tip>
                      </div>
                      <div style={{ fontSize: 11, color: T.light, lineHeight: 1.5, marginBottom: 8 }}>
                        {report.bloom_catalysts.catalyst_3.description}
                      </div>
                      {report.bloom_catalysts.catalyst_3.detected && (
                        <div style={{ fontSize: 9, color: T.blue, background: "rgba(59,130,246,0.06)", padding: "6px 8px", borderRadius: 4 }}>
                          <strong>Evidence:</strong> {report.bloom_catalysts.catalyst_3.evidence}
                        </div>
                      )}
                    </div>
                  )}

                </div>
              </div>

              {/* LOEB CRITERIA DETAILS */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
                
                {/* Loeb Catalyst Density & Sum of Parts */}
                <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 8, padding: 20, display: "flex", flexDirection: "column", gap: 16 }}>
                  
                  {report.loeb_criteria?.catalyst_density && (
                    <div>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                        <span style={{ fontSize: 9, fontWeight: 700, color: T.muted, textTransform: "uppercase" }}>Catalyst Density (12-24M)</span>
                        <span style={{ fontSize: 9, fontWeight: 700, color: T.purple }}>
                          {report.loeb_criteria.catalyst_density.rating} Density
                        </span>
                      </div>
                      <div style={{ fontSize: 11, color: T.text, lineHeight: 1.5 }}>
                        {report.loeb_criteria.catalyst_density.analysis}
                      </div>
                    </div>
                  )}

                  {report.loeb_criteria?.sum_of_parts?.analysis && !["N/A.", "N/A", "-"].includes(report.loeb_criteria.sum_of_parts.analysis) && (
                    <div style={{ borderTop: `1px solid ${T.border}`, paddingTop: 14 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                        <span style={{ fontSize: 9, fontWeight: 700, color: T.muted, textTransform: "uppercase" }}>Sum-of-Parts Discount</span>
                        <span style={{ 
                          fontSize: 9, fontWeight: 700, 
                          color: report.loeb_criteria.sum_of_parts.detected ? T.green : T.muted
                        }}>
                          {report.loeb_criteria.sum_of_parts.detected ? "SoP Dislocation Detected" : "No Dislocation"}
                        </span>
                      </div>
                      <div style={{ fontSize: 11, color: T.text, lineHeight: 1.5 }}>
                        {report.loeb_criteria.sum_of_parts.analysis}
                      </div>
                    </div>
                  )}

                </div>

                {/* Activism potential and Risk/Reward details */}
                <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 8, padding: 20, display: "flex", flexDirection: "column", gap: 16 }}>
                  
                  {report.loeb_criteria?.activism_potential?.analysis && !["-", "N/A.", "N/A"].includes(report.loeb_criteria.activism_potential.analysis) && (
                    <div>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                        <span style={{ fontSize: 9, fontWeight: 700, color: T.muted, textTransform: "uppercase" }}>Activism footprint / Leverage</span>
                        <span style={{ fontSize: 9, fontWeight: 700, color: T.purple }}>
                          {report.loeb_criteria.activism_potential.rating}
                        </span>
                      </div>
                      <div style={{ fontSize: 11, color: T.text, lineHeight: 1.5 }}>
                        {report.loeb_criteria.activism_potential.analysis}
                      </div>
                    </div>
                  )}

                  {report.loeb_criteria?.risk_reward?.analysis && (
                    <div style={{ borderTop: `1px solid ${T.border}`, paddingTop: 14 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                        <span style={{ fontSize: 9, fontWeight: 700, color: T.muted, textTransform: "uppercase" }}>Asymmetric Risk/Reward Analysis</span>
                      </div>
                      <div style={{ fontSize: 11, color: T.text, lineHeight: 1.5 }}>
                        {report.loeb_criteria.risk_reward.analysis}
                      </div>
                    </div>
                  )}

                </div>

              </div>

              {/* CATALYST CONVERGENCE & EVENT TRACKS */}
              {report.tracks && report.tracks.length > 0 && (
                <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 8, padding: 20, display: "flex", flexDirection: "column", gap: 16 }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderBottom: `2px solid rgba(59,130,246,0.15)`, paddingBottom: 6, marginBottom: 4 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: T.blue, textTransform: "uppercase" }}>
                      <Compass size={12} /> Catalyst Convergence & Event Tracks
                    </div>
                    {report.is_dher_pattern && (
                      <span style={{ fontSize: 9, fontWeight: 700, padding: "2px 6px", borderRadius: 4, background: "rgba(168,85,247,0.12)", color: T.purple, border: `1px solid ${T.purple}` }}>
                        DHER CONVERGENCE PATTERN
                      </span>
                    )}
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
                    <div style={{ background: "rgba(0,0,0,0.15)", padding: "10px 12px", borderRadius: 6, border: `1px solid ${T.border}` }}>
                      <div style={{ fontSize: 8, color: T.muted, textTransform: "uppercase" }}>Convergence Score</div>
                      <div style={{ fontSize: 18, fontWeight: 800, marginTop: 4, fontFamily: T.mono, color: T.blue }}>
                        {report.convergence_score != null ? report.convergence_score.toFixed(1) : "N/A"}/10.0
                      </div>
                    </div>
                    <div style={{ background: "rgba(0,0,0,0.15)", padding: "10px 12px", borderRadius: 6, border: `1px solid ${T.border}` }}>
                      <div style={{ fontSize: 8, color: T.muted, textTransform: "uppercase" }}>Independent Tracks</div>
                      <div style={{ fontSize: 18, fontWeight: 800, marginTop: 4, fontFamily: T.mono, color: T.text }}>
                        {report.independent_track_count != null ? report.independent_track_count : "0"}
                      </div>
                    </div>
                    <div style={{ background: "rgba(0,0,0,0.15)", padding: "10px 12px", borderRadius: 6, border: `1px solid ${T.border}` }}>
                      <div style={{ fontSize: 8, color: T.muted, textTransform: "uppercase" }}>Unfired (Pending) Tracks</div>
                      <div style={{ fontSize: 18, fontWeight: 800, marginTop: 4, fontFamily: T.mono, color: T.green }}>
                        {report.unfired_independent_track_count != null ? report.unfired_independent_track_count : "0"}
                      </div>
                    </div>
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {report.tracks.map((track, idx) => (
                      <div key={idx} style={{ padding: 12, background: "rgba(0,0,0,0.1)", borderRadius: 6, border: `1px solid ${T.border}`, display: "flex", flexDirection: "column", gap: 6 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <span style={{ fontSize: 10, fontWeight: 700, color: T.blue, textTransform: "uppercase" }}>
                            {track.track_type.replace(/_/g, " ")}
                          </span>
                          <div style={{ display: "flex", gap: 6 }}>
                            {track.independence_score !== undefined && (
                              <span style={{ fontSize: 8, padding: "1px 4px", borderRadius: 3, background: "rgba(255,255,255,0.05)", color: T.muted }}>
                                Ind. Wt: {track.independence_score.toFixed(1)}
                              </span>
                            )}
                            <span style={{ fontSize: 8, padding: "1px 4px", borderRadius: 3, background: track.fired ? "rgba(239, 68, 68, 0.12)" : "rgba(20, 184, 122, 0.12)", color: track.fired ? T.red : T.green }}>
                              {track.fired ? "FIRED / COMPLETED" : "PENDING / UPCOMING"}
                            </span>
                          </div>
                        </div>
                        <div style={{ fontSize: 11, color: T.text, lineHeight: 1.4 }}>
                          {track.evidence}
                        </div>
                        {(track.counterparty || track.event_date) && (
                          <div style={{ display: "flex", gap: 12, fontSize: 9, color: T.muted }}>
                            {track.counterparty && (
                              <span>Counterparty: <strong style={{ color: T.light }}>{track.counterparty}</strong></span>
                            )}
                            {track.event_date && (
                              <span>Target Date: <strong style={{ color: T.light }}>{track.event_date}</strong></span>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* CREDIT HEALTH STATUS */}
              {report.credit_health && (
                <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 8, padding: 20 }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderBottom: `2px solid rgba(239, 68, 68, 0.15)`, paddingBottom: 6, marginBottom: 12 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: T.red, textTransform: "uppercase" }}>
                      <AlertCircle size={12} /> Balance Sheet & Credit Health Audit
                    </div>
                    {report.credit_health.grade && (
                      <span style={{
                        fontSize: 10,
                        fontWeight: 800,
                        padding: "2px 8px",
                        borderRadius: 4,
                        background: report.credit_health.grade === "A" || report.credit_health.grade === "B"
                          ? "rgba(20, 184, 122, 0.12)"
                          : report.credit_health.grade === "C"
                            ? "rgba(245, 158, 11, 0.12)"
                            : "rgba(239, 68, 68, 0.12)",
                        color: report.credit_health.grade === "A" || report.credit_health.grade === "B"
                          ? T.green
                          : report.credit_health.grade === "C"
                            ? T.amber
                            : T.red,
                        border: `1px solid ${report.credit_health.grade === "A" || report.credit_health.grade === "B"
                          ? T.green
                          : report.credit_health.grade === "C"
                            ? T.amber
                            : T.red}`
                      }}>
                        GRADE {report.credit_health.grade}
                      </span>
                    )}
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    <div style={{ fontSize: 11, color: T.light }}>
                      Net Debt / EBITDA Ratio: <strong style={{ color: T.text }}>{report.credit_health.net_debt_ebitda != null ? `${report.credit_health.net_debt_ebitda.toFixed(2)}x` : "N/A"}</strong>
                    </div>
                    {report.credit_health.distress_flags && report.credit_health.distress_flags.length > 0 ? (
                      <div style={{ marginTop: 4 }}>
                        <div style={{ fontSize: 9, fontWeight: 700, color: T.red, textTransform: "uppercase", marginBottom: 4 }}>Distress Flags Flagged:</div>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                          {report.credit_health.distress_flags.map((flag, idx) => (
                            <span key={idx} style={{ fontSize: 9, padding: "2px 6px", borderRadius: 4, background: "rgba(239, 68, 68, 0.08)", color: T.red, border: `1px solid rgba(239, 68, 68, 0.2)` }}>
                              {flag}
                            </span>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <div style={{ fontSize: 11, color: T.green, display: "flex", alignItems: "center", gap: 4, marginTop: 4 }}>
                        <CheckCircle2 size={12} /> No solvency or balance sheet distress triggers detected.
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* OPTIONS / DERIVATIVES METRICS & ANALYSIS — render ONLY when real options data exists.
                  Sweep/enriched dossiers carry a NO_OPTIONS sentinel (all-null + "N/A"); the ThetaData
                  feed that used to fill these is retired, so a dead all-N/A panel is just noise. */}
              {report.options_signals && (
                report.options_signals.iv_current != null ||
                report.options_signals.skew_25d != null ||
                report.options_signals.pc_oi_ratio != null ||
                report.options_signals.total_oi != null ||
                report.options_signals.implied_earnings_move_pct != null ||
                (!!report.options_signals.term_structure && report.options_signals.term_structure !== "N/A")
              ) && (
                <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 8, padding: 20 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: T.green, textTransform: "uppercase", marginBottom: 16, paddingBottom: 6, borderBottom: `2px solid ${T.greenLight}` }}>
                    <TrendingUp size={12} /> Options market catalyst signals
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "repeat(6, 1fr)", gap: 12, marginBottom: 16 }}>
                    <div style={{ background: "rgba(0,0,0,0.15)", padding: "10px 12px", borderRadius: 6, border: `1px solid ${T.border}` }}>
                      <div style={{ fontSize: 8, color: T.muted, textTransform: "uppercase" }}>ATM IV</div>
                      <div style={{ fontSize: 14, fontWeight: 700, marginTop: 4, fontFamily: T.mono }}>
                        {report.options_signals.iv_current != null ? `${(report.options_signals.iv_current * 100).toFixed(1)}%` : "N/A"}
                      </div>
                    </div>
                    <div style={{ background: "rgba(0,0,0,0.15)", padding: "10px 12px", borderRadius: 6, border: `1px solid ${T.border}` }}>
                      <div style={{ fontSize: 8, color: T.muted, textTransform: "uppercase" }}>Skew (25d)</div>
                      <div style={{ fontSize: 14, fontWeight: 700, marginTop: 4, fontFamily: T.mono, color: report.options_signals.skew_25d && report.options_signals.skew_25d < 0 ? T.green : T.text }}>
                        {report.options_signals.skew_25d != null ? `${report.options_signals.skew_25d.toFixed(2)}` : "N/A"}
                      </div>
                    </div>
                    <div style={{ background: "rgba(0,0,0,0.15)", padding: "10px 12px", borderRadius: 6, border: `1px solid ${T.border}` }}>
                      <div style={{ fontSize: 8, color: T.muted, textTransform: "uppercase" }}>Structure</div>
                      <div style={{ fontSize: 14, fontWeight: 700, marginTop: 4, fontFamily: T.mono, color: report.options_signals.term_structure === "backwardation" ? T.purple : T.text }}>
                        {report.options_signals.term_structure || "N/A"}
                      </div>
                    </div>
                    <div style={{ background: "rgba(0,0,0,0.15)", padding: "10px 12px", borderRadius: 6, border: `1px solid ${T.border}` }}>
                      <div style={{ fontSize: 8, color: T.muted, textTransform: "uppercase" }}>P/C Ratio</div>
                      <div style={{ fontSize: 14, fontWeight: 700, marginTop: 4, fontFamily: T.mono }}>
                        {report.options_signals.pc_oi_ratio != null ? report.options_signals.pc_oi_ratio.toFixed(2) : "N/A"}
                      </div>
                    </div>
                    <div style={{ background: "rgba(0,0,0,0.15)", padding: "10px 12px", borderRadius: 6, border: `1px solid ${T.border}` }}>
                      <div style={{ fontSize: 8, color: T.muted, textTransform: "uppercase" }}>Total OI</div>
                      <div style={{ fontSize: 14, fontWeight: 700, marginTop: 4, fontFamily: T.mono }}>
                        {report.options_signals.total_oi != null ? report.options_signals.total_oi.toLocaleString() : "N/A"}
                      </div>
                    </div>
                    <div style={{ background: "rgba(0,0,0,0.15)", padding: "10px 12px", borderRadius: 6, border: `1px solid ${T.border}` }}>
                      <div style={{ fontSize: 8, color: T.muted, textTransform: "uppercase" }}>Implied Move</div>
                      <div style={{ fontSize: 14, fontWeight: 700, marginTop: 4, fontFamily: T.mono, color: T.purple }}>
                        {report.options_signals.implied_earnings_move_pct != null ? `±${report.options_signals.implied_earnings_move_pct.toFixed(1)}%` : "N/A"}
                      </div>
                    </div>
                  </div>

                  <div style={{ display: "flex", gap: 10, background: "rgba(0, 0, 0, 0.12)", border: `1px solid ${T.border}`, borderRadius: 6, padding: "12px 14px" }}>
                    <div style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", background: "rgba(20,184,122,0.18)", color: T.green, padding: "2px 6px", borderRadius: 4, height: "fit-content", whiteSpace: "nowrap" }}>
                      {report.options_signals.market_sentiment_flag}
                    </div>
                    <div style={{ fontSize: 11, color: T.light, lineHeight: 1.5 }}>
                      {report.options_signals.overall_interpretation}
                    </div>
                  </div>

                </div>
              )}

              {/* ANTECEDENT EVIDENCE FEED (FILINGS & NEWS) */}
              {report.recent_events && report.recent_events.length > 0 && (
                <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 8, padding: 20 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: T.green, textTransform: "uppercase", marginBottom: 16, paddingBottom: 6, borderBottom: `2px solid ${T.greenLight}` }}>
                    <Calendar size={12} /> Catalyst Evidence Feed (Filings & News Context)
                  </div>
                  
                  <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                    {report.recent_events.map((ev, idx) => (
                      <div 
                        key={idx} 
                        style={{ 
                          display: "flex", 
                          alignItems: "center", 
                          justifyContent: "space-between", 
                          padding: "8px 12px", 
                          background: "rgba(0,0,0,0.1)", 
                          borderRadius: 6, 
                          border: `1px solid ${T.border}` 
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: 10, overflow: "hidden" }}>
                          <span style={{ fontSize: 9, color: T.muted, whiteSpace: "nowrap" }}>
                            [{ev.date}]
                          </span>
                          <span style={{ 
                            fontSize: 8, padding: "1px 4px", borderRadius: 3, 
                            background: ev.type === "filing" ? "rgba(168,85,247,0.18)" : (ev.type === "news" ? "rgba(59,130,246,0.18)" : "rgba(20,184,122,0.18)"), 
                            color: ev.type === "filing" ? T.purple : (ev.type === "news" ? T.blue : T.green),
                            textTransform: "uppercase",
                            fontWeight: 700
                          }}>
                            {ev.type}
                          </span>
                          <span style={{ fontSize: 11, color: T.text, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                            {ev.title}
                          </span>
                        </div>
                        {ev.link && (
                          <a href={ev.link} target="_blank" rel="noreferrer" style={{ color: T.green, display: "flex", alignItems: "center", gap: 4, textDecoration: "none", fontSize: 10, paddingLeft: 12 }}>
                            Source <ExternalLink size={10} />
                          </a>
                        )}
                      </div>
                    ))}
                  </div>

                </div>
              )}

            </div>
          ) : (
            <div style={{ minHeight: "65vh", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12, color: T.muted }}>
              <Compass size={48} style={{ opacity: 0.3 }} />
              <div style={{ fontWeight: 700 }}>Select a candidate to run Catalyst Scan</div>
              <div style={{ fontSize: 11, maxWidth: 380, textAlign: "center", lineHeight: 1.5 }}>
                Click on any of the highly-rated catalyst candidates on the left panel or type in a ticker to trigger the event-driven scan.
              </div>
            </div>
          )}

        </div>

      </div>
    </div>
  );
}
