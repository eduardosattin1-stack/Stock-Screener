"use client";
import { usePathname, useRouter } from "next/navigation";
import { BarChart3, Briefcase, Radio } from "lucide-react";

export default function Nav() {
  const pathname = usePathname();
  const router = useRouter();

  const links = [
    { href: "/", label: "Screener", icon: <BarChart3 size={13} /> },
    { href: "/portfolio", label: "Portfolio", icon: <Briefcase size={13} /> },
    { href: "/signals", label: "Signals", icon: <Radio size={13} /> },
  ];

  return (
    <nav style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "10px 24px", borderBottom: "1px solid var(--border)",
      background: "var(--bg)", position: "sticky", top: 0, zIndex: 50,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }} onClick={() => router.push("/")}>
          <div style={{
            width: 22, height: 22, borderRadius: 5, background: "var(--green)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 10, fontWeight: 700, color: "#fff", fontFamily: "var(--font-mono)",
          }}>CB</div>
          <span style={{ fontSize: 12, fontWeight: 700, color: "var(--text)", fontFamily: "var(--font-mono)", letterSpacing: "0.04em" }}>
            SCREENER
          </span>
          <span style={{ fontSize: 9, fontWeight: 600, color: "var(--green)", fontFamily: "var(--font-mono)",
            padding: "1px 5px", borderRadius: 3, background: "var(--green-light)", border: "1px solid var(--green-border)" }}>
            v6
          </span>
        </div>
        <div style={{ display: "flex", gap: 2 }}>
          {links.map(l => {
            const active = l.href === "/" ? pathname === "/" : pathname.startsWith(l.href);
            return (
              <button key={l.href} onClick={() => router.push(l.href)} style={{
                display: "flex", alignItems: "center", gap: 5,
                padding: "6px 12px", fontSize: 12, fontFamily: "var(--font-mono)", fontWeight: 500,
                border: "none", borderRadius: 5, cursor: "pointer",
                background: active ? "var(--green-light)" : "transparent",
                color: active ? "var(--green)" : "var(--text-muted)",
                transition: "all 0.15s",
              }}>
                {l.icon} {l.label}
              </button>
            );
          })}
        </div>
      </div>
    </nav>
  );
}
