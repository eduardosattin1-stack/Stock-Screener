"use client";
import { usePathname, useRouter } from "next/navigation";
import { BarChart3, Briefcase } from "lucide-react";

export default function Nav() {
  const pathname = usePathname();
  const router = useRouter();

  const links = [
    { href: "/", label: "Screener", icon: <BarChart3 size={13} /> },
    { href: "/portfolio", label: "Portfolio", icon: <Briefcase size={13} /> },
  ];

  return (
    <nav style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "8px 20px", borderBottom: "1px solid #1e2433", background: "#08090e",
      position: "sticky", top: 0, zIndex: 50,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <span style={{ fontSize: 11, fontWeight: 700, color: "#4a5060", fontFamily: "var(--font-mono)", letterSpacing: "0.12em" }}>
          CB
        </span>
        <div style={{ display: "flex", gap: 2 }}>
          {links.map(l => {
            const active = l.href === "/" ? pathname === "/" : pathname.startsWith(l.href);
            return (
              <button key={l.href} onClick={() => router.push(l.href)} style={{
                display: "flex", alignItems: "center", gap: 5,
                padding: "5px 10px", fontSize: 11, fontFamily: "var(--font-mono)", fontWeight: 500,
                border: "none", borderRadius: 3, cursor: "pointer",
                background: active ? "#1a1f2e" : "transparent",
                color: active ? "#c9cdd6" : "#4a5060",
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
