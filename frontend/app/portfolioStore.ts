"use client";
// Per-user portfolio storage in Firestore: one doc `users/{uid}/portfolio/state`
// holding { positions, history } (mirrors the old global state.json shape).
// Client-direct writes, secured by firestore.rules (owner + allowlist). Current
// valuation is computed by the UI from the shared scan/live prices, so no backend
// monitor write is needed here.
import { doc, getDoc, setDoc, type DocumentReference } from "firebase/firestore";
import { db } from "./firebase";

export interface PortfolioPosition {
  symbol: string;
  entry_price: number;
  shares: number;
  entry_date: string;
  notes?: string;
  bucket?: "midcap" | "sp500" | null;
  asset_type?: "stock" | "option";
  strategy?: string;
  expiration?: string;
  strikes?: string;
  contracts?: number;
}
export interface PortfolioHistoryEntry {
  symbol: string;
  action: string;
  date: string;
  entry_price: number;
  exit_price: number;
  pnl_pct: number;
  reason: string;
  entry_date?: string;
  exit_date: string;
  days_held: number;
  asset_type?: "stock" | "option";
}
export interface PortfolioState {
  positions: PortfolioPosition[];
  history: PortfolioHistoryEntry[];
}

const EMPTY: PortfolioState = { positions: [], history: [] };

function ref(uid: string): DocumentReference {
  if (!db) throw new Error("Portfolio storage not configured");
  return doc(db, "users", uid, "portfolio", "state");
}

export async function getPortfolio(uid: string): Promise<PortfolioState> {
  if (!db) return EMPTY;
  const snap = await getDoc(ref(uid));
  const d = snap.data() as Partial<PortfolioState> | undefined;
  return { positions: d?.positions ?? [], history: d?.history ?? [] };
}

export async function addPosition(
  uid: string,
  p: { symbol: string; entry_price: number; shares: number; notes?: string; bucket?: "midcap" | "sp500" | null; asset_type?: "stock" | "option" },
): Promise<void> {
  if (!db) throw new Error("Portfolio storage not configured");
  const cur = await getPortfolio(uid);
  const pos: PortfolioPosition = {
    symbol: p.symbol,
    entry_price: p.entry_price,
    shares: p.shares,
    entry_date: new Date().toISOString(),
    notes: p.notes ?? "",
    bucket: p.bucket ?? null,
    asset_type: p.asset_type ?? "stock",
  };
  // Replace any existing same-symbol/same-type position (matches prior add semantics).
  const positions = [
    ...cur.positions.filter((x) => !(x.symbol === pos.symbol && (x.asset_type ?? "stock") === pos.asset_type)),
    pos,
  ];
  await setDoc(ref(uid), { positions, history: cur.history }, { merge: true });
}

export async function closePosition(
  uid: string,
  symbol: string,
  exitPrice: number,
  reason: string,
  asset_type?: string,
): Promise<void> {
  if (!db) throw new Error("Portfolio storage not configured");
  const cur = await getPortfolio(uid);
  const idx = cur.positions.findIndex(
    (x) => x.symbol === symbol && (asset_type ? (x.asset_type ?? "stock") === asset_type : true),
  );
  if (idx < 0) return;
  const pos = cur.positions[idx];
  const pnl_pct = pos.entry_price ? ((exitPrice - pos.entry_price) / pos.entry_price) * 100 : 0;
  const entryMs = Date.parse(pos.entry_date);
  const days_held = Number.isNaN(entryMs) ? 0 : Math.round((Date.now() - entryMs) / 86_400_000);
  const nowIso = new Date().toISOString();
  const hist: PortfolioHistoryEntry = {
    symbol,
    action: "SELL",
    date: nowIso,
    entry_price: pos.entry_price,
    exit_price: exitPrice,
    pnl_pct,
    reason: reason || "User close",
    entry_date: pos.entry_date,
    exit_date: nowIso,
    days_held,
    asset_type: pos.asset_type,
  };
  const positions = cur.positions.filter((_, i) => i !== idx);
  await setDoc(ref(uid), { positions, history: [hist, ...cur.history] }, { merge: true });
}

// ── Customizable header radar — per-user symbol list (users/{uid}/radar/config) ──
export const DEFAULT_RADAR = ["^GSPC", "^NDX", "^GDAXI", "^RUT", "BTCUSD", "EURUSD"];

export async function getRadar(uid: string): Promise<string[]> {
  if (!db) return DEFAULT_RADAR;
  const snap = await getDoc(doc(db, "users", uid, "radar", "config"));
  const d = snap.data() as { symbols?: string[] } | undefined;
  return Array.isArray(d?.symbols) && d!.symbols.length ? (d!.symbols as string[]) : DEFAULT_RADAR;
}

export async function setRadar(uid: string, symbols: string[]): Promise<void> {
  if (!db) return;
  await setDoc(doc(db, "users", uid, "radar", "config"), { symbols }, { merge: true });
}
