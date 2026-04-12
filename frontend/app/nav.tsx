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
      padding: "10px 20px", borderBottom: "1px solid #e5e7eb", background: "#ffffff",
      position: "sticky", top: 0, zIndex: 50,
      boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: "#2d7a4f", fontFamily: "var(--font-mono)", letterSpacing: "0.12em" }}>
          CB
        </span>
        <div style={{ width: 1, height: 16, background: "#e5e7eb" }} />
        <div style={{ display: "flex", gap: 2 }}>
          {links.map(l => {
            const active = l.href === "/" ? pathname === "/" : pathname.startsWith(l.href);
            return (
              <button key={l.href} onClick={() => router.push(l.href)} style={{
                display: "flex", alignItems: "center", gap: 5,
                padding: "6px 12px", fontSize: 11, fontFamily: "var(--font-mono)", fontWeight: 600,
                border: "none", borderRadius: 6, cursor: "pointer",
                background: active ? "#e8f5ee" : "transparent",
                color: active ? "#2d7a4f" : "#6b7280",
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
