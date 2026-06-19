"use client";
import { createContext, useContext, useState, ReactNode } from "react";

// App-wide symbol/company search query, lifted so the box can live in the shared
// top nav (nav.tsx) while the screener (page.tsx) reads it for table filtering.
type SearchCtx = { query: string; setQuery: (s: string) => void };
const Ctx = createContext<SearchCtx>({ query: "", setQuery: () => {} });

export function SearchProvider({ children }: { children: ReactNode }) {
  const [query, setQuery] = useState("");
  return <Ctx.Provider value={{ query, setQuery }}>{children}</Ctx.Provider>;
}

export const useSearch = () => useContext(Ctx);
