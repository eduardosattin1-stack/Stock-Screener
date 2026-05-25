"use client";
import { useState, useEffect, useMemo, useRef } from "react";
import { 
  Compass, Search, Zap, Target, Award, Calendar, 
  ExternalLink, TrendingUp, AlertCircle, RefreshCw, 
  HelpCircle, ChevronRight, CheckCircle2, AlertTriangle, PlayCircle,
  Star, Trash2
} from "lucide-react";


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
}

interface Candidate {
  symbol: string;
  name: string;
  price: number | null;
  market_cap: number | null;
  catalyst_score: number;
  flags: string[];
  has_special_flag: boolean;
  categories?: string[];
  priority?: number;
  upside?: number;
  rr_ratio?: number | null;
  is_scanned?: boolean;
}

export default function CatalystWatch() {
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [loadingCandidates, setLoadingCandidates] = useState(true);
  const [selectedSymbol, setSelectedSymbol] = useState<string>("CVS");
  const [report, setReport] = useState<CatalystScanReport | null>(null);
  const [loadingScan, setLoadingScan] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const [customSymbol, setCustomSymbol] = useState("");
  
  // Filtering and sorting state
  const [categoryFilter, setCategoryFilter] = useState<string>("All");
  const [sortField, setSortField] = useState<"score" | "asymmetry" | "mcap">("score");
  
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
      prev.map((c) => c.symbol === sym ? { ...c, catalyst_score: newScore, is_scanned: true } : c)
    );
    setWatchlist((prev) => {
      const updated = prev.map((w) => w.symbol === sym ? { ...w, catalyst_score: newScore, is_scanned: true } : w);
      localStorage.setItem("catalyst_watchlist", JSON.stringify(updated));
      return updated;
    });
    setRecentScans((prev) => 
      prev.map((r) => r.symbol === sym ? { ...r, catalyst_score: newScore, is_scanned: true } : r)
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

  const toggleWatchlist = (symbol: string, name: string, score: number, price?: number | null, market_cap?: number | null) => {
    const sym = symbol.toUpperCase().trim();
    const exists = watchlist.some((item) => item.symbol === sym);
    let updated: Candidate[];
    if (exists) {
      updated = watchlist.filter((item) => item.symbol !== sym);
    } else {
      updated = [
        ...watchlist,
        {
          symbol: sym,
          name: name || "Unknown Company",
          catalyst_score: score,
          price: price ?? null,
          market_cap: market_cap ?? null,
          flags: ["Watchlist"],
          has_special_flag: true
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
          is_scanned: true
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
          is_scanned: true
        },
        ...prev
      ];
    });
  };

  // Filter recent scans to exclude items currently on the watchlist
  const filteredRecentScans = useMemo(() => {
    return recentScans.filter(r => !watchlist.some(w => w.symbol === r.symbol));
  }, [recentScans, watchlist]);

  // Filter and sort candidates list based on active filters and sorting selection
  const processedCandidates = useMemo(() => {
    let result = candidates.filter(cand => 
      !watchlist.some(w => w.symbol === cand.symbol) &&
      !recentScans.some(r => r.symbol === cand.symbol)
    );
    
    if (categoryFilter !== "All") {
      result = result.filter(cand => 
        cand.categories && cand.categories.includes(categoryFilter)
      );
    }
    
    result.sort((a, b) => {
      if (sortField === "asymmetry") {
        const asymA = a.rr_ratio ?? (a.upside ? a.upside * 10 : 0);
        const asymB = b.rr_ratio ?? (b.upside ? b.upside * 10 : 0);
        return asymB - asymA;
      } else if (sortField === "mcap") {
        return (b.market_cap || 0) - (a.market_cap || 0);
      } else {
        // Default: score (Loeb Score)
        return (b.catalyst_score || 0) - (a.catalyst_score || 0);
      }
    });
    
    return result;
  }, [candidates, watchlist, recentScans, categoryFilter, sortField]);

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
        onClick={() => setSelectedSymbol(cand.symbol)}
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
          </span>
          <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
            {sortField === "mcap" ? (
              <span style={{ fontSize: 10, fontFamily: T.mono, padding: "1px 5px", borderRadius: 4, background: "rgba(59,130,246,0.18)", color: T.blue }} title="Market Cap">
                {formatMarketCap(cand.market_cap || undefined)}
              </span>
            ) : sortField === "asymmetry" ? (
              <span style={{ fontSize: 10, fontFamily: T.mono, padding: "1px 5px", borderRadius: 4, background: (cand.rr_ratio || (cand.upside && cand.upside > 0.15)) ? "rgba(20,184,122,0.18)" : "rgba(255,255,255,0.05)", color: (cand.rr_ratio || (cand.upside && cand.upside > 0.15)) ? T.green : T.muted }} title="Asymmetry (R/R or Upside)">
                {cand.rr_ratio ? `R/R: ${cand.rr_ratio.toFixed(1)}:1` : cand.upside ? `Upside: +${(cand.upside * 100).toFixed(0)}%` : "R/R: —"}
              </span>
            ) : (
              <span 
                style={{ 
                  fontSize: 10, 
                  fontFamily: T.mono, 
                  padding: "1px 5px", 
                  borderRadius: 4, 
                  background: cand.is_scanned 
                    ? (cand.catalyst_score >= 7.5 ? "rgba(168,85,247,0.18)" : "rgba(255,255,255,0.05)")
                    : "rgba(255,255,255,0.03)", 
                  color: cand.is_scanned 
                    ? (cand.catalyst_score >= 7.5 ? T.purple : T.light) 
                    : T.muted 
                }} 
                title={cand.is_scanned ? "Loeb Score (Deep Scanned)" : "Loeb Score (Heuristic Estimate)"}
              >
                Loeb: {cand.catalyst_score.toFixed(1)}{cand.is_scanned ? "" : "*"}
              </span>
            )}
            {listType === "watchlist" && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  toggleWatchlist(cand.symbol, cand.name, cand.catalyst_score);
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
              <span key={idx} style={{ fontSize: 8, padding: "1px 4px", borderRadius: 3, background: "rgba(255,255,255,0.06)", color: T.muted, border: `1px solid rgba(255,255,255,0.03)` }}>
                {fl}
              </span>
            ))}
          </div>
        )}
      </div>
    );
  };

  return (
    <div style={{ minHeight: "100vh", background: T.bg, color: T.text, fontFamily: T.mono }}>

      
      {/* Sub-header detailing strategy details */}
      <div style={{ padding: "16px 24px", borderBottom: `1px solid ${T.border}`, background: "rgba(10, 10, 10, 0.4)", display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Zap size={16} color={T.green} />
          <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: "0.05em", color: T.green, textTransform: "uppercase" }}>
            Opportunistic AI Layer: Loeb / Third Point + Bloom Framework
          </span>
        </div>
        <div style={{ fontSize: 11, color: T.light, maxWidth: 650, textAlign: "right" }}>
          Filters a wide universe by catalyst density & Sum-of-Parts dislocation. High asymmetric 2:1 R/R entries verified by option Greeks and multi-quarter transcript tracking.
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "320px 1fr", minHeight: "calc(100vh - 120px)", background: T.bg }}>
        
        {/* LEFT SIDEBAR: Candidate List */}
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
          </div>

          <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 14, maxHeight: "calc(100vh - 280px)", paddingRight: 4 }}>
            {loadingCandidates ? (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", padding: 40, gap: 8, fontSize: 12, color: T.muted }}>
                <RefreshCw size={14} className="animate-spin" /> Loading candidates...
              </div>
            ) : (
              <>
                {/* 1. WATCHLIST */}
                {watchlist.length > 0 && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    <div style={{ fontSize: 9, fontWeight: 800, textTransform: "uppercase", color: "var(--amber, #f59e0b)", letterSpacing: "0.08em", display: "flex", alignItems: "center", gap: 4, borderBottom: `1px solid rgba(245,158,11,0.2)`, paddingBottom: 4 }}>
                      <Star size={10} fill="var(--amber, #f59e0b)" color="var(--amber, #f59e0b)" /> Watchlist ({watchlist.length})
                    </div>
                    {watchlist.map(cand => renderCandidate(cand, "watchlist"))}
                  </div>
                )}

                {/* 2. RECENT SCANS */}
                {filteredRecentScans.length > 0 && (
                  <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    <div style={{ fontSize: 9, fontWeight: 800, textTransform: "uppercase", color: T.green, letterSpacing: "0.08em", display: "flex", alignItems: "center", gap: 4, borderBottom: `1px solid rgba(20,184,122,0.2)`, paddingBottom: 4 }}>
                      <PlayCircle size={10} color={T.green} /> Recent Scans ({filteredRecentScans.length})
                    </div>
                    {filteredRecentScans.map(cand => renderCandidate(cand, "recent"))}
                  </div>
                )}

                {/* 3. DEFAULT CANDIDATES */}
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <div style={{ fontSize: 9, fontWeight: 800, textTransform: "uppercase", color: T.muted, letterSpacing: "0.08em", borderBottom: `1px solid ${T.border}`, paddingBottom: 4 }}>
                    Scanning Candidates ({processedCandidates.length})
                  </div>
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

        {/* MAIN PANEL: AI Event-Driven Scan Result */}
        <div style={{ padding: 24, overflowY: "auto", maxHeight: "calc(100vh - 120px)" }}>
          
          {loadingScan ? (
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
                      
                      <button
                        onClick={() => toggleWatchlist(
                          report.symbol, 
                          report.company_name, 
                          report.catalyst_density_score,
                          report.price,
                          report.market_cap
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
                      <span>Price: <strong style={{ color: T.text }}>${report.price?.toFixed(2) || "N/A"}</strong></span>
                      <span>Market Cap: <strong style={{ color: T.text }}>{formatMarketCap(report.market_cap)}</strong></span>
                      {report.cache_timestamp && (
                        <span>Last Scan: <strong style={{ color: T.text }}>{formatCacheDate(report.cache_timestamp)}</strong></span>
                      )}
                    </div>
                  </div>

                  {/* SCORE GAUGES */}
                  <div style={{ display: "flex", gap: 16 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 16px", background: "rgba(168,85,247,0.06)", borderRadius: 6, border: `1px solid ${T.purple}` }}>
                      <div style={{ textAlign: "right" }}>
                        <div style={{ fontSize: 8, fontWeight: 700, color: T.muted, letterSpacing: "0.05em", textTransform: "uppercase" }}>Loeb Score</div>
                        <div style={{ fontSize: 9, color: T.light }}>Catalyst Density</div>
                      </div>
                      <div style={{ fontSize: 24, fontWeight: 800, color: T.purple, fontFamily: T.mono }}>
                        {report.catalyst_density_score?.toFixed(1) || "N/A"}
                      </div>
                    </div>
                    
                    <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "8px 16px", background: "rgba(20,184,122,0.06)", borderRadius: 6, border: `1px solid ${T.green}` }}>
                      <div style={{ textAlign: "right" }}>
                        <div style={{ fontSize: 8, fontWeight: 700, color: T.muted, letterSpacing: "0.05em", textTransform: "uppercase" }}>Risk / Reward</div>
                        <div style={{ fontSize: 9, color: T.light }}>Target Ratio</div>
                      </div>
                      <div style={{ fontSize: 24, fontWeight: 800, color: T.green, fontFamily: T.mono }}>
                        {report.upside_downside_ratio ? `${report.upside_downside_ratio.toFixed(1)}:1` : "N/A"}
                      </div>
                    </div>
                  </div>
                </div>

                <div style={{ borderTop: `1px solid ${T.border}`, paddingTop: 16 }}>
                  <div style={{ fontSize: 9, fontWeight: 700, textTransform: "uppercase", color: T.muted, letterSpacing: "0.08em", marginBottom: 6 }}>
                    Opportunistic AI Thesis Summary
                  </div>
                  <p style={{ fontSize: 12, color: T.text, lineHeight: 1.6, margin: 0 }}>
                    {report.analysis_summary}
                  </p>
                </div>
              </div>

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
                        {report.bloom_catalysts.catalyst_1.title}
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
                        {report.bloom_catalysts.catalyst_2.title}
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
                        {report.bloom_catalysts.catalyst_3.title}
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

                  {report.loeb_criteria?.sum_of_parts && (
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
                  
                  {report.loeb_criteria?.activism_potential && (
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

                  {report.loeb_criteria?.risk_reward && (
                    <div style={{ borderTop: `1px solid ${T.border}`, paddingTop: 14 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                        <span style={{ fontSize: 9, fontWeight: 700, color: T.muted, textTransform: "uppercase" }}>Asymmetric Risk/Reward Analysis</span>
                        <span style={{ fontSize: 9, fontWeight: 700, color: T.green }}>
                          Ratio: {report.loeb_criteria.risk_reward.ratio}
                        </span>
                      </div>
                      <div style={{ fontSize: 11, color: T.text, lineHeight: 1.5 }}>
                        {report.loeb_criteria.risk_reward.analysis}
                      </div>
                    </div>
                  )}

                </div>

              </div>

              {/* OPTIONS / DERIVATIVES METRICS & ANALYSIS */}
              {report.options_signals && (
                <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 8, padding: 20 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", color: T.green, textTransform: "uppercase", marginBottom: 16, paddingBottom: 6, borderBottom: `2px solid ${T.greenLight}` }}>
                    <TrendingUp size={12} /> Options market catalyst signals (ThetaData Pipeline)
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
                      <div style={{ fontSize: 8, color: T.muted, textTransform: "uppercase" }}>P/C OI Ratio</div>
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
