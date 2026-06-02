"use client";
// Client auth context: current user, allowlist status, and sign-in/out.
// Allowlist = a Firestore doc `allowlist/{lowercased-email}`; existence === allowed.
// (Enforced for real at the DB layer by firestore.rules; this is the UX check.)
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { onAuthStateChanged, signInWithPopup, signOut, type User } from "firebase/auth";
import { doc, getDoc } from "firebase/firestore";
import { auth, db, googleProvider, firebaseEnabled } from "./firebase";

interface AuthCtx {
  user: User | null;
  loading: boolean;
  allowed: boolean | null; // null = no user yet / not checked
  signIn: () => Promise<void>;
  logout: () => Promise<void>;
}

const Ctx = createContext<AuthCtx>({
  user: null, loading: true, allowed: null,
  signIn: async () => {}, logout: async () => {},
});

export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [allowed, setAllowed] = useState<boolean | null>(null);

  useEffect(() => {
    if (!firebaseEnabled || !auth) { setLoading(false); return; }
    const unsub = onAuthStateChanged(auth, async (u) => {
      setUser(u);
      if (u?.email && db) {
        try {
          const snap = await getDoc(doc(db, "allowlist", u.email.toLowerCase()));
          setAllowed(snap.exists());
        } catch {
          setAllowed(false);
        }
      } else {
        setAllowed(null);
      }
      setLoading(false);
    });
    return () => unsub();
  }, []);

  const signIn = async () => { if (auth) await signInWithPopup(auth, googleProvider); };
  const logout = async () => { if (auth) await signOut(auth); };

  return <Ctx.Provider value={{ user, loading, allowed, signIn, logout }}>{children}</Ctx.Provider>;
}
