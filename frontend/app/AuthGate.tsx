"use client";
// Whole-app gate. States: not-configured (fail OPEN → render app, as pre-auth) ·
// loading · signed-out (Google button) · signed-in-but-not-allowlisted · allowed (render app).
import type { ReactNode } from "react";
import { useAuth } from "./AuthProvider";
import { firebaseEnabled } from "./firebase";

function Shell({ children }: { children: ReactNode }) {
  return (
    <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--bg)", padding: 24 }}>
      <div style={{ maxWidth: 380, width: "100%", textAlign: "center", background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: 12, padding: "40px 32px", boxShadow: "var(--shadow-md)" }}>
        {children}
      </div>
    </div>
  );
}

export function AuthGate({ children }: { children: ReactNode }) {
  const { user, loading, allowed, signIn, logout } = useAuth();

  // Not configured yet → stay public (no regression, no brick) until env vars land.
  if (!firebaseEnabled) return <>{children}</>;

  // Local dev is open by default so debugging / headless checks aren't blocked by the
  // sign-in gate. Set NEXT_PUBLIC_AUTH_FORCE=1 to exercise the real gate locally.
  // Production builds (Vercel) are NODE_ENV=production → always gated.
  if (process.env.NODE_ENV !== "production" && process.env.NEXT_PUBLIC_AUTH_FORCE !== "1") return <>{children}</>;

  if (loading) {
    return <Shell><div style={{ fontFamily: "var(--font-mono)", color: "var(--text-muted)", fontSize: 13 }}>Loading…</div></Shell>;
  }

  if (!user) {
    return (
      <Shell>
        <div style={{ fontWeight: 800, fontSize: 20, color: "var(--text)", marginBottom: 6 }}>CB Screener</div>
        <div style={{ fontFamily: "var(--font-mono)", color: "var(--text-muted)", fontSize: 12, marginBottom: 24 }}>Sign in to continue</div>
        <button onClick={() => void signIn()} style={{ width: "100%", padding: "12px 16px", borderRadius: 8, border: "1px solid var(--border)", background: "var(--bg)", color: "var(--text)", fontWeight: 700, fontSize: 14, cursor: "pointer", fontFamily: "var(--font-sans)" }}>
          Continue with Google
        </button>
      </Shell>
    );
  }

  if (allowed === false) {
    return (
      <Shell>
        <div style={{ fontWeight: 800, fontSize: 18, color: "var(--text)", marginBottom: 8 }}>Access pending</div>
        <div style={{ fontFamily: "var(--font-mono)", color: "var(--text-muted)", fontSize: 12, marginBottom: 4 }}>{user.email}</div>
        <div style={{ fontFamily: "var(--font-mono)", color: "var(--text-light)", fontSize: 11, marginBottom: 24 }}>This account isn&apos;t on the allowlist yet.</div>
        <button onClick={() => void logout()} style={{ padding: "8px 16px", borderRadius: 8, border: "1px solid var(--border)", background: "transparent", color: "var(--text-muted)", fontSize: 12, cursor: "pointer", fontFamily: "var(--font-mono)" }}>
          Sign out
        </button>
      </Shell>
    );
  }

  if (allowed === null) {
    return <Shell><div style={{ fontFamily: "var(--font-mono)", color: "var(--text-muted)", fontSize: 13 }}>Checking access…</div></Shell>;
  }

  return <>{children}</>;
}
