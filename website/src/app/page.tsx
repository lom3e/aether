import React from "react";
import { Navbar } from "@/components/Navbar";
import { Hero } from "@/components/Hero";
import { WhatIsAether } from "@/components/WhatIsAether";
import { ParallaxStory } from "@/components/ParallaxStory";
import { HowAetherWorks } from "@/components/HowAetherWorks";
import { AdaptableWork } from "@/components/AdaptableWork";
import { FAQ } from "@/components/FAQ";
import { AlphaCTA } from "@/components/AlphaCTA";
import { Footer } from "@/components/Footer";

export const metadata = {
  title: "Aether — Costruisci la tua squadra di AI | Build your AI team",
  description:
    "Crea collaboratori AI specializzati, dai loro i tuoi documenti e lascia che lavorino insieme per te sul tuo computer in totale sicurezza.",
};

export default function HomePage() {
  return (
    <main style={{ minHeight: "100vh", position: "relative", background: "var(--bg-page)" }}>
      {/* 1. Global Navigation Bar with Theme & Language Controls */}
      <Navbar />

      {/* 2. Hero Cinematica: Interactive Agent Network */}
      <Hero />

      {/* 3. Cos'è Aether: 3 Clean Pillars */}
      <WhatIsAether />

      {/* 4. Cinematic Parallax Scroll Story: 3 Iconic Moments */}
      <ParallaxStory />

      {/* 5. Come Funziona: 4 Simple Steps */}
      <HowAetherWorks />

      {/* 6. Si Adatta al Tuo Lavoro: 4 Flussi Professionali */}
      <AdaptableWork />

      {/* 7. Plain-Language FAQ */}
      <FAQ />

      {/* 8. High-Impact Clean Download CTA */}
      <AlphaCTA />

      {/* 9. Minimal Footer with LMLabs Attribution */}
      <Footer />
    </main>
  );
}
