"use client";
import React, { useState, useEffect } from "react";
import { ChevronDown, Plus, Trash2, RefreshCw } from "lucide-react";
import Link from "next/link";

export interface WatchlistBasket {
  id: string;
  name: string;
  symbols: string[];
}

// ── Terminal Ledger Rail — shared module grammar ────────────────────────────
// One grid template + type scale shared by every rail module (Watchlist /
// SpeculairTracker / TrackedBaskets) so numbers right-align at identical
// x-positions down the whole 340px rail. Column 5 is a 20px action gutter
// present in every row so the numeric stack never shifts.
const GRID = "minmax(0, 1fr) 52px 52px 52px 20px";
const fmtPrice = (p: number | null | undefined) => (p == null ? null : p >= 10000 ? `${(p / 1000).toFixed(1)}k` : p.toFixed(2));
const fmtChange = (c: number | null | undefined) => (c == null ? null : `${c > 0 ? "+" : ""}${Math.abs(c) >= 1000 ? c.toFixed(0) : c.toFixed(2)}`);
const fmtPct = (pct: number | null | undefined) => (pct == null ? null : `${pct > 0 ? "+" : ""}${Math.abs(pct) >= 100 ? pct.toFixed(0) : pct.toFixed(2)}%`);
const PENDING = <span style={{ color: "var(--text-light)" }}>–.––</span>;

export function Watchlist({ embedded = false }: { embedded?: boolean } = {}) {
  const [baskets, setBaskets] = useState<WatchlistBasket[]>([]);
  const [activeBasketId, setActiveBasketId] = useState<string | null>(null);
  const [quotes, setQuotes] = useState<Record<string, { price: number; change: number; changesPercentage: number }>>({});
  const [newSymbol, setNewSymbol] = useState("");
  const [loading, setLoading] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [editingBasket, setEditingBasket] = useState(false);
  const [newBasketName, setNewBasketName] = useState("");
  const [hoveredSym, setHoveredSym] = useState<string | null>(null);
  const [hoveredListId, setHoveredListId] = useState<string | null>(null);
  const [inputFocused, setInputFocused] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("cb_watchlist_baskets");
    if (stored) {
      try {
        const parsed = JSON.parse(stored);
        setBaskets(parsed);
        if (parsed.length > 0) setActiveBasketId(parsed[0].id);
      } catch (e) {}
    } else {
      const defaultBasket = { id: "default", name: "Watchlist", symbols: ["SPY", "QQQ", "AAPL", "MSFT"] };
      setBaskets([defaultBasket]);
      setActiveBasketId(defaultBasket.id);
    }
  }, []);

  const activeBasket = baskets.find(b => b.id === activeBasketId) || baskets[0];

  useEffect(() => {
    if (baskets.length > 0) {
      localStorage.setItem("cb_watchlist_baskets", JSON.stringify(baskets));
    }
  }, [baskets]);

  const fetchQuotes = async () => {
    if (!activeBasket || activeBasket.symbols.length === 0) return;
    setLoading(true);
    try {
      // batch-quote (not quote) — FMP's quote endpoint is single-symbol; a comma list returns []
      const syms = activeBasket.symbols.join(",");
      const res = await fetch(`/api/fmp?e=batch-quote&symbols=${encodeURIComponent(syms)}`);
      const data = await res.json();
      if (Array.isArray(data)) {
        const qMap: any = {};
        data.forEach((q: any) => {
          const pct = q.changesPercentage ?? q.changePercentage;
          const chg = q.change ?? (q.price != null && pct != null ? q.price - q.price / (1 + pct / 100) : null);
          qMap[q.symbol] = { price: q.price, change: chg, changesPercentage: pct };
        });
        setQuotes(prev => ({ ...prev, ...qMap }));
      }
    } catch (e) {
      console.error("Watchlist fetch error:", e);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchQuotes();
    const interval = setInterval(fetchQuotes, 30000); // 30s updates
    return () => clearInterval(interval);
  }, [activeBasketId, activeBasket?.symbols.join(",")]);

  const handleAddSymbol = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSymbol.trim() || !activeBasket) return;
    const sym = newSymbol.trim().toUpperCase();
    if (!activeBasket.symbols.includes(sym)) {
      setBaskets(baskets.map(b => b.id === activeBasket.id ? { ...b, symbols: [...b.symbols, sym] } : b));
    }
    setNewSymbol("");
  };

  const removeSymbol = (sym: string) => {
    if (!activeBasket) return;
    setBaskets(baskets.map(b => b.id === activeBasket.id ? { ...b, symbols: b.symbols.filter(s => s !== sym) } : b));
  };

  const handleCreateBasket = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newBasketName.trim()) return;
    const nb: WatchlistBasket = { id: Date.now().toString(), name: newBasketName.trim(), symbols: [] };
    setBaskets([...baskets, nb]);
    setActiveBasketId(nb.id);
    setEditingBasket(false);
    setNewBasketName("");
    setMenuOpen(false);
  };

  const handleDeleteBasket = (id: string) => {
    const updated = baskets.filter(b => b.id !== id);
    if (updated.length === 0) {
      updated.push({ id: "default", name: "Watchlist", symbols: [] });
    }
    setBaskets(updated);
    setActiveBasketId(updated[0].id);
  };

  if (!activeBasket) return null;

  return (
    <div style={{ ...(embedded ? {} : { width: 340, borderLeft: "1px solid var(--border)", height: "100vh", position: "sticky", top: 0, zIndex: 40 }), background: "var(--bg-surface)", display: "flex", flexDirection: "column", fontFamily: "var(--font-sans)" }}>
      {/* Level-1 module band */}
      <div style={{ height: 28, boxSizing: "border-box", display: "flex", alignItems: "center", gap: 8, padding: "0 12px", background: "var(--bg)", borderTop: "1px solid var(--border)", borderBottom: "1px solid var(--border)", position: "relative" }}>
        <span style={{ width: 2, height: 10, borderRadius: 1, background: "var(--lavender)", flexShrink: 0 }} />
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-secondary)" }}>Watchlist</span>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text-light)" }}>{activeBasket.symbols.length}</span>

        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 2 }}>
          <button onClick={() => setMenuOpen(!menuOpen)} title="Switch list"
            style={{ display: "flex", alignItems: "center", gap: 4, background: "none", border: "none", cursor: "pointer", padding: "0 4px", height: 20, borderRadius: 4, color: "var(--text)" }}
            onMouseEnter={e => (e.currentTarget.style.background = "var(--bg-hover)")} onMouseLeave={e => (e.currentTarget.style.background = "transparent")}>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", maxWidth: 110, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", textTransform: "uppercase" }}>{activeBasket.name}</span>
            <ChevronDown size={10} color="var(--text-light)" style={{ flexShrink: 0, transform: menuOpen ? "rotate(180deg)" : "rotate(0deg)", transition: "transform 120ms ease" }} />
          </button>
          <button onClick={fetchQuotes} title="Refresh quotes"
            style={{ width: 20, height: 20, display: "flex", alignItems: "center", justifyContent: "center", background: "none", border: "none", cursor: "pointer", borderRadius: 4, color: "var(--text-light)" }}
            onMouseEnter={e => { e.currentTarget.style.background = "var(--bg-hover)"; e.currentTarget.style.color = "var(--text)"; }}
            onMouseLeave={e => { e.currentTarget.style.background = "transparent"; e.currentTarget.style.color = "var(--text-light)"; }}>
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />
          </button>
        </div>

        {/* List-switcher dropdown */}
        {menuOpen && (
          <>
            <div onClick={() => setMenuOpen(false)} style={{ position: "fixed", inset: 0, zIndex: 49 }} />
            <div style={{ position: "absolute", top: "calc(100% + 4px)", right: 8, width: 216, background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 6, boxShadow: "var(--shadow-md)", zIndex: 50, padding: 4, animation: "fadeIn 120ms ease" }}>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 600, letterSpacing: "0.08em", color: "var(--text-light)", padding: "4px 8px", textTransform: "uppercase" }}>My lists</div>
              {baskets.map(b => (
                <div key={b.id} onMouseEnter={() => setHoveredListId(b.id)} onMouseLeave={() => setHoveredListId(null)}
                  style={{ display: "flex", alignItems: "center", padding: "0 4px 0 0", borderRadius: 4, borderLeft: b.id === activeBasketId ? "2px solid var(--lavender)" : "2px solid transparent", background: b.id === activeBasketId || hoveredListId === b.id ? "var(--bg-hover)" : "transparent" }}>
                  <button onClick={() => { setActiveBasketId(b.id); setMenuOpen(false); }} style={{ background: "none", border: "none", cursor: "pointer", flex: 1, textAlign: "left", fontSize: 11, fontFamily: "var(--font-mono)", fontWeight: 500, color: "var(--text)", padding: "6px 8px", minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{b.name}</button>
                  {baskets.length > 1 && (
                    <button onClick={() => handleDeleteBasket(b.id)} title={`Delete ${b.name}`} aria-label={`Delete ${b.name}`}
                      style={{ width: 20, height: 20, display: "flex", alignItems: "center", justifyContent: "center", background: "none", border: "none", borderRadius: 4, cursor: "pointer", color: "var(--text-light)", opacity: hoveredListId === b.id ? 1 : 0, pointerEvents: hoveredListId === b.id ? "auto" : "none", transition: "opacity 120ms ease", flexShrink: 0 }}
                      onMouseEnter={e => { e.currentTarget.style.color = "var(--red)"; e.currentTarget.style.background = "var(--red-light)"; }}
                      onMouseLeave={e => { e.currentTarget.style.color = "var(--text-light)"; e.currentTarget.style.background = "transparent"; }}>
                      <Trash2 size={12} />
                    </button>
                  )}
                </div>
              ))}
              <div style={{ borderTop: "1px solid var(--border-subtle)", margin: "4px 0" }} />
              {editingBasket ? (
                <form onSubmit={handleCreateBasket} style={{ display: "flex", gap: 4, padding: "0 4px 4px" }}>
                  <input autoFocus value={newBasketName} onChange={e => setNewBasketName(e.target.value)} placeholder="List name..." style={{ flex: 1, minWidth: 0, padding: "4px 8px", fontSize: 11, fontFamily: "var(--font-mono)", border: "1px solid var(--border)", borderRadius: 4, background: "var(--bg)", color: "var(--text)", outline: "none" }} />
                  <button type="submit" style={{ padding: "4px 8px", background: "var(--green)", color: "#fff", border: "none", borderRadius: 4, fontSize: 11, fontFamily: "var(--font-mono)", fontWeight: 600, cursor: "pointer" }}>Add</button>
                </form>
              ) : (
                <button onClick={() => setEditingBasket(true)} style={{ width: "100%", textAlign: "left", padding: "6px 8px", background: "none", border: "none", cursor: "pointer", fontSize: 11, fontFamily: "var(--font-mono)", fontWeight: 500, color: "var(--text-light)", display: "flex", alignItems: "center", gap: 6, borderRadius: 4 }}
                  onMouseEnter={e => (e.currentTarget.style.background = "var(--bg-hover)")} onMouseLeave={e => (e.currentTarget.style.background = "transparent")}>
                  <Plus size={12} /> Create new list
                </button>
              )}
            </div>
          </>
        )}
      </div>

      {/* Add-symbol strip */}
      <div style={{ padding: "8px 12px", borderBottom: "1px solid var(--border-subtle)" }}>
        <form onSubmit={handleAddSymbol} style={{ display: "flex", position: "relative" }}>
          <button type="submit" title="Add symbol" disabled={!newSymbol.trim()} style={{ position: "absolute", left: 4, top: "50%", transform: "translateY(-50%)", display: "flex", alignItems: "center", justifyContent: "center", width: 20, height: 20, background: "none", border: "none", padding: 0, color: newSymbol.trim() ? "var(--lavender)" : "var(--text-light)", cursor: newSymbol.trim() ? "pointer" : "default" }}>
            <Plus size={14} />
          </button>
          <input value={newSymbol} onChange={e => setNewSymbol(e.target.value)} placeholder="Add symbol ↵"
            onFocus={() => setInputFocused(true)} onBlur={() => setInputFocused(false)}
            style={{ width: "100%", height: 26, boxSizing: "border-box", padding: "0 8px 0 26px", fontSize: 11, border: `1px solid ${inputFocused ? "var(--lavender-deep)" : "var(--border-subtle)"}`, borderRadius: 4, outline: "none", fontFamily: "var(--font-mono)", textTransform: "uppercase", background: "var(--bg)", color: "var(--text)" }} />
        </form>
      </div>

      {/* Column sub-header */}
      <div style={{ display: "grid", gridTemplateColumns: GRID, gap: 6, height: 20, alignItems: "center", padding: "0 12px", background: "var(--bg)", fontSize: 9, fontWeight: 600, color: "var(--text-light)", textTransform: "uppercase", letterSpacing: "0.08em", borderBottom: "1px solid var(--border-subtle)", fontFamily: "var(--font-mono)" }}>
        <div>Symbol</div>
        <div style={{ textAlign: "right" }}>Last</div>
        <div style={{ textAlign: "right" }}>Chg</div>
        <div style={{ textAlign: "right" }}>Chg%</div>
        <div></div>
      </div>

      {/* Symbols List */}
      <div style={embedded ? undefined : { flex: 1, overflowY: "auto" }}>
        {activeBasket.symbols.length === 0 ? (
          <div style={{ padding: "14px 12px", fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-light)", lineHeight: 1.5 }}>
            No symbols in this list.
            <div style={{ fontSize: 9, marginTop: 2 }}>Type a ticker above and press ↵</div>
          </div>
        ) : (
          activeBasket.symbols.map(sym => {
            const q = quotes[sym];
            const c = q?.change ?? 0;
            const cp = q?.changesPercentage ?? 0;
            const color = c > 0 ? "var(--green)" : c < 0 ? "var(--red)" : "var(--text-light)";
            return (
              <div key={sym} onMouseEnter={e => { e.currentTarget.style.background = "var(--bg-hover)"; setHoveredSym(sym); }} onMouseLeave={e => { e.currentTarget.style.background = "transparent"; setHoveredSym(null); }}
                style={{ display: "grid", gridTemplateColumns: GRID, gap: 6, height: 28, alignItems: "center", padding: "0 12px", borderBottom: "1px solid var(--border-subtle)", fontSize: 11, fontFamily: "var(--font-mono)", fontVariantNumeric: "tabular-nums", cursor: "pointer", transition: "background 0.1s" }}>
                <div style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  <Link href={`/stock/${sym}`} style={{ textDecoration: "none", color: "var(--text)", fontWeight: 700 }}>{sym}</Link>
                </div>
                <div style={{ textAlign: "right", color: "var(--text-secondary)" }}>{q?.price != null ? fmtPrice(q.price) : PENDING}</div>
                <div style={{ textAlign: "right", color }}>{q?.price != null ? fmtChange(c) : PENDING}</div>
                <div style={{ textAlign: "right", color, fontWeight: 700 }}>{q?.price != null ? fmtPct(cp) : PENDING}</div>
                <button onClick={(e) => { e.stopPropagation(); removeSymbol(sym); }} title={`Remove ${sym}`} aria-label={`Remove ${sym}`}
                  style={{ width: 20, height: 20, display: "flex", alignItems: "center", justifyContent: "center", background: "none", border: "none", borderRadius: 4, cursor: "pointer", color: "var(--text-light)", padding: 0, opacity: hoveredSym === sym ? 1 : 0, pointerEvents: hoveredSym === sym ? "auto" : "none", transition: "opacity 120ms ease" }}
                  onMouseEnter={e => { e.currentTarget.style.color = "var(--red)"; e.currentTarget.style.background = "var(--red-light)"; }}
                  onMouseLeave={e => { e.currentTarget.style.color = "var(--text-light)"; e.currentTarget.style.background = "transparent"; }}>
                  <Trash2 size={12} />
                </button>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
