"use client";
import React, { useState, useEffect } from "react";
import { ChevronDown, Plus, Trash2, RefreshCw, GripVertical } from "lucide-react";
import Link from "next/link";

export interface WatchlistBasket {
  id: string;
  name: string;
  symbols: string[];
}

export function Watchlist({ embedded = false }: { embedded?: boolean } = {}) {
  const [baskets, setBaskets] = useState<WatchlistBasket[]>([]);
  const [activeBasketId, setActiveBasketId] = useState<string | null>(null);
  const [quotes, setQuotes] = useState<Record<string, { price: number; change: number; changesPercentage: number }>>({});
  const [newSymbol, setNewSymbol] = useState("");
  const [loading, setLoading] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [editingBasket, setEditingBasket] = useState(false);
  const [newBasketName, setNewBasketName] = useState("");

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
      const syms = activeBasket.symbols.join(",");
      const res = await fetch(`/api/fmp?e=quote&symbol=${syms}`);
      const data = await res.json();
      if (Array.isArray(data)) {
        const qMap: any = {};
        data.forEach((q: any) => {
          qMap[q.symbol] = { price: q.price, change: q.change, changesPercentage: q.changesPercentage };
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
      {/* Header */}
      <div style={{ padding: "16px", borderBottom: "1px solid var(--border-subtle)", display: "flex", justifyContent: "space-between", alignItems: "center", position: "relative" }}>
        <button onClick={() => setMenuOpen(!menuOpen)} style={{ display: "flex", alignItems: "center", gap: 6, background: "none", border: "none", cursor: "pointer", fontSize: 16, fontWeight: 700, color: "var(--text)" }}>
          {activeBasket.name} <ChevronDown size={16} />
        </button>

        <div style={{ display: "flex", gap: 12, alignItems: "center", color: "var(--text-light)" }}>
          <button onClick={fetchQuotes} title="Refresh Quotes" style={{ background: "none", border: "none", cursor: "pointer", color: "inherit", padding: 4 }}>
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          </button>
        </div>

        {/* Basket Dropdown */}
        {menuOpen && (
          <div style={{ position: "absolute", top: "100%", left: 16, width: 240, background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: 6, boxShadow: "0 4px 12px rgba(0,0,0,0.1)", zIndex: 50, padding: 8 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", padding: "4px 8px", marginBottom: 4 }}>MY LISTS</div>
            {baskets.map(b => (
              <div key={b.id} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 8px", borderRadius: 4, background: b.id === activeBasketId ? "var(--bg-hover)" : "transparent" }}>
                <button onClick={() => { setActiveBasketId(b.id); setMenuOpen(false); }} style={{ background: "none", border: "none", cursor: "pointer", flex: 1, textAlign: "left", fontSize: 13, fontWeight: 500 }}>{b.name}</button>
                {baskets.length > 1 && (
                  <button onClick={() => handleDeleteBasket(b.id)} title="Delete List" style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-light)", padding: 4 }}><Trash2 size={12} /></button>
                )}
              </div>
            ))}
            <div style={{ borderTop: "1px solid var(--border-subtle)", margin: "8px 0" }} />
            {editingBasket ? (
              <form onSubmit={handleCreateBasket} style={{ display: "flex", gap: 4, padding: "0 8px" }}>
                <input autoFocus value={newBasketName} onChange={e => setNewBasketName(e.target.value)} placeholder="List name..." style={{ flex: 1, padding: "4px 8px", fontSize: 12, border: "1px solid var(--border)", borderRadius: 4, background: "var(--bg)", color: "var(--text)" }} />
                <button type="submit" style={{ padding: "4px 8px", background: "var(--green)", color: "#fff", border: "none", borderRadius: 4, fontSize: 12, fontWeight: 600, cursor: "pointer" }}>Add</button>
              </form>
            ) : (
              <button onClick={() => setEditingBasket(true)} style={{ width: "100%", textAlign: "left", padding: "6px 8px", background: "none", border: "none", cursor: "pointer", fontSize: 13, fontWeight: 500, color: "var(--text-muted)", display: "flex", alignItems: "center", gap: 6 }}>
                <Plus size={14} /> Create new list
              </button>
            )}
          </div>
        )}
      </div>

      {/* Add Symbol */}
      <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border-subtle)" }}>
        <form onSubmit={handleAddSymbol} style={{ display: "flex", position: "relative" }}>
          <button type="submit" title="Add symbol" disabled={!newSymbol.trim()} style={{ position: "absolute", left: 4, top: "50%", transform: "translateY(-50%)", display: "flex", alignItems: "center", justifyContent: "center", width: 22, height: 22, background: "none", border: "none", padding: 0, color: newSymbol.trim() ? "var(--text)" : "var(--text-light)", cursor: newSymbol.trim() ? "pointer" : "default" }}>
            <Plus size={14} />
          </button>
          <input value={newSymbol} onChange={e => setNewSymbol(e.target.value)} placeholder="Add symbol" style={{ width: "100%", padding: "6px 10px 6px 28px", fontSize: 12, border: "1px solid var(--border)", borderRadius: 4, outline: "none", fontFamily: "var(--font-mono)", background: "var(--bg)", color: "var(--text)" }} />
        </form>
      </div>

      {/* Columns Header */}
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.2fr) 1fr 1fr 1fr 24px", gap: 8, padding: "8px 16px", fontSize: 10, fontWeight: 600, color: "var(--text-light)", textTransform: "uppercase", borderBottom: "1px solid var(--border-subtle)", fontFamily: "var(--font-mono)" }}>
        <div>Symbol</div>
        <div style={{ textAlign: "right" }}>Last</div>
        <div style={{ textAlign: "right" }}>Chg</div>
        <div style={{ textAlign: "right" }}>Chg%</div>
        <div></div>
      </div>

      {/* Symbols List */}
      <div style={embedded ? undefined : { flex: 1, overflowY: "auto" }}>
        {activeBasket.symbols.length === 0 ? (
          <div style={{ padding: 32, textAlign: "center", color: "var(--text-muted)", fontSize: 12 }}>
            This list is empty. Add symbols above.
          </div>
        ) : (
          activeBasket.symbols.map(sym => {
            const q = quotes[sym];
            const p = q?.price;
            const c = q?.change ?? 0;
            const cp = q?.changesPercentage ?? 0;
            const color = c > 0 ? "var(--green)" : c < 0 ? "var(--red)" : "var(--text-muted)";
            return (
              <div key={sym} className="group" style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.2fr) 1fr 1fr 1fr 24px", gap: 8, padding: "10px 16px", borderBottom: "1px solid var(--border-subtle)", alignItems: "center", fontSize: 12, fontFamily: "var(--font-mono)", cursor: "pointer", transition: "background 0.1s" }}
                   onMouseEnter={e => (e.currentTarget.style.background = "var(--bg-hover)")} onMouseLeave={e => (e.currentTarget.style.background = "transparent")}>
                <div style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: 700 }}>
                  <Link href={`/stock/${sym}`} style={{ textDecoration: "none", color: "var(--text)" }}>{sym}</Link>
                </div>
                <div style={{ textAlign: "right" }}>{p ? p.toFixed(2) : "—"}</div>
                <div style={{ textAlign: "right", color }}>{c > 0 ? `+${c.toFixed(2)}` : c.toFixed(2)}</div>
                <div style={{ textAlign: "right", color }}>{cp > 0 ? `+${cp.toFixed(2)}%` : `${cp.toFixed(2)}%`}</div>
                <button onClick={(e) => { e.stopPropagation(); removeSymbol(sym); }} title="Remove" style={{ background: "none", border: "none", cursor: "pointer", color: "var(--text-light)", padding: 4, display: "flex", alignItems: "center", justifyContent: "center" }}>
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
