"use client";
import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { Search, Loader2 } from "lucide-react";
import { useSearch } from "../search-context";

interface Hit { symbol: string; name: string; exchange: string; currency: string }

// Top-nav typeahead. As the user types, a dropdown of matching symbols/companies
// surfaces below the box (FMP-backed via /api/search); selecting one opens the
// stock page. The query is also pushed into the shared search context so the
// screener table on "/" keeps filtering live for anyone already on that page.
export default function SymbolSearch() {
  const router = useRouter();
  const { setQuery } = useSearch();
  const [text, setText] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [active, setActive] = useState(0);
  const boxRef = useRef<HTMLDivElement>(null);
  const seqRef = useRef(0);

  // Debounced fetch. seqRef guards against out-of-order responses (a slow
  // earlier request resolving after a faster later one).
  useEffect(() => {
    const q = text.trim();
    if (q.length < 1) { setHits([]); setLoading(false); return; }
    setLoading(true);
    const id = setTimeout(async () => {
      const seq = ++seqRef.current;
      try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(q)}`);
        const data = await res.json();
        if (seq !== seqRef.current) return;
        setHits(Array.isArray(data?.results) ? data.results : []);
        setActive(0);
      } catch {
        if (seq === seqRef.current) setHits([]);
      } finally {
        if (seq === seqRef.current) setLoading(false);
      }
    }, 150);
    return () => clearTimeout(id);
  }, [text]);

  // Close the dropdown on any click outside the box.
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  const go = useCallback((sym: string) => {
    setOpen(false);
    setText("");
    setHits([]);
    setQuery("");
    router.push(`/stock/${encodeURIComponent(sym)}`);
  }, [router, setQuery]);

  const onChange = (v: string) => {
    setText(v);
    setQuery(v);          // keep the "/" screener table filtering in sync
    setOpen(true);
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setActive(a => Math.min(a + 1, hits.length - 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive(a => Math.max(a - 1, 0)); }
    else if (e.key === "Enter") { if (open && hits[active]) { e.preventDefault(); go(hits[active].symbol); } }
    else if (e.key === "Escape") { setOpen(false); }
  };

  const showPanel = open && text.trim().length >= 1;

  return (
    <div ref={boxRef} style={{ position: "relative", width: 280, maxWidth: "38vw" }}>
      <Search size={13} style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", color: "var(--text-light)", pointerEvents: "none" }} />
      <input
        value={text}
        onChange={e => onChange(e.target.value)}
        onKeyDown={onKey}
        onFocus={() => { if (text.trim()) setOpen(true); }}
        placeholder="Search symbol or company..."
        autoComplete="off" spellCheck={false} role="combobox" aria-expanded={showPanel} aria-autocomplete="list"
        style={{ width: "100%", padding: "7px 10px 7px 32px", fontSize: 12, fontFamily: "var(--font-mono)", border: "1px solid var(--border)", borderRadius: 6, background: "var(--bg)", color: "var(--text)", outline: "none" }} />
      {loading && <Loader2 size={13} className="animate-spin" style={{ position: "absolute", right: 10, top: "50%", transform: "translateY(-50%)", color: "var(--text-light)" }} />}

      {showPanel && (
        <div style={{ position: "absolute", top: "calc(100% + 6px)", left: 0, width: "min(360px, 92vw)", maxHeight: 340, overflowY: "auto", background: "var(--bg-surface, var(--bg))", border: "1px solid var(--border)", borderRadius: 8, boxShadow: "0 12px 32px rgba(0,0,0,0.35)", zIndex: 60, padding: 4 }}>
          {hits.length === 0 ? (
            <div style={{ padding: "12px 12px", fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--text-light)" }}>
              {loading ? "Searching…" : "No matches"}
            </div>
          ) : hits.map((h, i) => (
            <button
              key={h.symbol}
              onMouseDown={e => { e.preventDefault(); go(h.symbol); }}
              onMouseEnter={() => setActive(i)}
              style={{ display: "flex", alignItems: "center", gap: 10, width: "100%", textAlign: "left", padding: "8px 10px", border: "none", borderRadius: 6, cursor: "pointer", background: i === active ? "var(--green-light)" : "transparent", color: "var(--text)" }}>
              <span style={{ fontFamily: "var(--font-mono)", fontWeight: 700, fontSize: 12, minWidth: 56, color: i === active ? "var(--green)" : "var(--text)" }}>{h.symbol}</span>
              <span style={{ flex: 1, fontSize: 11, color: "var(--text-muted)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={h.name}>{h.name || "—"}</span>
              {h.exchange && <span style={{ fontSize: 9, fontFamily: "var(--font-mono)", color: "var(--text-light)", padding: "2px 6px", border: "1px solid var(--border)", borderRadius: 4, flexShrink: 0 }}>{h.exchange}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
