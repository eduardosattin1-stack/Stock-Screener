"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Signals() {
  const router = useRouter();
  useEffect(() => { router.replace("/performance"); }, [router]);
  return <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center" }}><span style={{ color: "#9ca3af", fontFamily: "var(--font-mono)", fontSize: 12 }}>Redirecting to Performance...</span></div>;
}
