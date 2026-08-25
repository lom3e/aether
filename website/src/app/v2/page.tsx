import React from "react";
import Link from "next/link";
import { Navbar } from "@/components/Navbar";
import { Hero } from "@/components/Hero";
import { ParallaxStoryV2 } from "@/components/ParallaxStoryV2";
import { WhatIsAether } from "@/components/WhatIsAether";
import { AdaptableWork } from "@/components/AdaptableWork";
import { FAQ } from "@/components/FAQ";
import { AlphaCTA } from "@/components/AlphaCTA";
import { Footer } from "@/components/Footer";
import { Sparkles, ArrowLeft } from "lucide-react";

export const metadata = {
  title: "Aether v1.6.0 — Redesign Preview | Build your AI team",
  description:
    "Riprogettazione completa di Aether con ParallaxStory interattivo, AI Auto-Architect, Gerarchia Modelli e Privacy Sovrana.",
};

export default function VersionTwoPage() {
  return (
    <main style={{ minHeight: "100vh", position: "relative", background: "var(--bg-page)" }}>
      {/* Version Comparison Bar */}
      <div
        style={{
          background: "linear-gradient(90deg, rgba(16, 185, 129, 0.12) 0%, rgba(124, 58, 237, 0.12) 100%)",
          borderBottom: "1px solid rgba(16, 185, 129, 0.25)",
          padding: "8px 16px",
          textAlign: "center",
          fontSize: "0.8125rem",
          fontWeight: 600,
          color: "var(--text-primary)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 10,
          position: "relative",
          zIndex: 101,
        }}
      >
        <span style={{ display: "inline-flex", alignItems: "center", gap: 5, color: "var(--accent-emerald)" }}>
          <Sparkles size={14} />
          <span>Versione B (Redesign v1.6.0 con Parallax Avanzato)</span>
        </span>
        <span style={{ color: "var(--text-muted)" }}>•</span>
        <Link
          href="/"
          style={{
            color: "var(--accent-violet)",
            textDecoration: "none",
            display: "inline-flex",
            alignItems: "center",
            gap: 4,
            fontWeight: 700,
          }}
        >
          <ArrowLeft size={13} />
          <span>Torna a Versione A (Classic)</span>
        </Link>
      </div>

      {/* 1. Global Navigation Bar with Theme & Language Controls */}
      <Navbar />

      {/* 2. Hero Cinematica: Interactive Agent Network */}
      <Hero />

      {/* 3. Cinematic Parallax Scroll Story v1.6.0: 4 Ricchi Momenti */}
      <ParallaxStoryV2 />

      {/* 4. Le Innovazioni v1.6.0: 3 Pilastri Tecnologici */}
      <WhatIsAether />

      {/* 5. Si Adatta al Tuo Lavoro: 4 Flussi Professionali */}
      <AdaptableWork />

      {/* 6. Plain-Language FAQ */}
      <FAQ />

      {/* 7. High-Impact Clean Download CTA */}
      <AlphaCTA />

      {/* 8. Minimal Footer with LMLabs Attribution */}
      <Footer />
    </main>
  );
}
