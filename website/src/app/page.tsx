import React from "react";
import { Navbar } from "@/components/Navbar";
import { Hero } from "@/components/Hero";
import { WhatIsAether } from "@/components/WhatIsAether";
import { ParallaxStory } from "@/components/ParallaxStory";
import { HowAetherWorks } from "@/components/HowAetherWorks";
import { ProductDemo } from "@/components/ProductDemo";
import { AdaptableWork } from "@/components/AdaptableWork";
import { FAQ } from "@/components/FAQ";
import { AlphaCTA } from "@/components/AlphaCTA";
import { Footer } from "@/components/Footer";

export const metadata = {
  title: "Aether — Costruisci la tua squadra di AI | Build your AI team",
  description:
    "Crea collaboratori AI specializzati, dai loro i tuoi documenti e lascia che lavorino insieme per te.",
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

      {/* 6. Product Demo: Ecco Cosa Vedi */}
      <ProductDemo />

      {/* 7. Si Adatta al Tuo Lavoro: 8 Interactive Workflows */}
      <AdaptableWork />

      {/* 8. Plain-Language FAQ */}
      <FAQ />

      {/* 9. High-Impact Clean Alpha CTA */}
      <AlphaCTA />

      {/* 10. Minimal Footer with LMLabs Attribution */}
      <Footer />
    </main>
  );
}
