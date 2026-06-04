"use client";
import { usePathname, useRouter } from "next/navigation";
import { BarChart3, Briefcase, TrendingUp, Compass } from "lucide-react";

export default function Nav() {
  const pathname = usePathname();
  const router = useRouter();
  const links = [
    { href: "/", label: "Discover", icon: <BarChart3 size={13} /> },
    { href: "/portfolio", label: "Live Track Record", icon: <Briefcase size={13} /> },
    { href: "/performance", label: "System Performance", icon: <TrendingUp size={13} /> },
    { href: "/catalysts", label: "Catalyst Watch", icon: <Compass size={13} /> },
  ];
  return (
    <nav style={{ display:"flex", alignItems:"center", justifyContent:"space-between", padding:"10px 24px", borderBottom:"1px solid var(--border)", background:"var(--bg)", position:"sticky", top:0, zIndex:50 }}>
      <div style={{ display:"flex", alignItems:"center", gap:20 }}>
        <div style={{ display:"flex", alignItems:"center", gap:14, cursor:"pointer" }} onClick={()=>router.push("/")}>
          <div style={{ 
            width:32, height:32, borderRadius:7, 
            background:"var(--green)", color:"var(--bg)", 
            display:"flex", alignItems:"center", justifyContent:"center", 
            fontSize:12, fontWeight:800, fontFamily:"var(--font-mono)", letterSpacing:"-0.04em",
            boxShadow: "0 0 40px rgba(20,184,122,0.18), inset 0 1px 0 rgba(255,255,255,0.2)"
          }}>SA</div>
          <div style={{ 
            fontSize:18, fontWeight:800, color:"var(--text)", 
            fontFamily:"var(--font-mono)", letterSpacing:"-0.04em", lineHeight:1,
            display:"inline-flex", alignItems:"baseline"
          }}>
            specul<span style={{color:"var(--lavender)"}}>AI</span>r
          </div>
          <span style={{ 
            fontSize:11, fontWeight:500, color:"var(--lavender)", 
            fontFamily:"var(--font-mono)", padding:"4px 9px", borderRadius:6, 
            background:"rgba(196,181,253,0.18)", textTransform:"lowercase", letterSpacing:"0.1em",
            marginLeft:4
          }}>beta</span>
        </div>
        <div style={{ display:"flex", gap:2 }}>
          {links.map(l=>{const active=l.href==="/"?pathname==="/":pathname.startsWith(l.href);return(
            <button key={l.href} onClick={()=>router.push(l.href)} style={{ display:"flex", alignItems:"center", gap:5, padding:"6px 12px", fontSize:12, fontFamily:"var(--font-mono)", fontWeight:500, border:"none", borderRadius:5, cursor:"pointer", background:active?"var(--green-light)":"transparent", color:active?"var(--green)":"var(--text-muted)", transition:"all 0.15s" }}>{l.icon} {l.label}</button>
          );})}
        </div>
      </div>
    </nav>
  );
}
