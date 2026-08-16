"use client";

import React from "react";
import Link from "next/link";
import { ArrowLeft, Users, ShieldCheck, Laptop } from "lucide-react";
import { Navbar } from "@/components/Navbar";
import { Footer } from "@/components/Footer";
import { useLanguage } from "@/lib/i18n/context";

export default function AboutPage() {
  const { lang } = useLanguage();

  return (
    <main style={{ minHeight: "100vh", position: "relative", background: "var(--bg-page)" }}>
      <Navbar />

      <section style={{ padding: "140px 0 100px" }}>
        <div className="container-narrow">
          {/* Back link */}
          <div style={{ marginBottom: 32 }}>
            <Link
              href="/"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                color: "var(--text-secondary)",
                textDecoration: "none",
                fontSize: "0.875rem",
                fontWeight: 500,
              }}
            >
              <ArrowLeft size={16} />
              <span>{lang === "it" ? "Torna alla Home" : "Back to Home"}</span>
            </Link>
          </div>

          <span className="section-tag">{lang === "it" ? "INFORMAZIONI" : "ABOUT AETHER"}</span>
          <h1 className="section-title" style={{ marginBottom: 24 }}>
            {lang === "it" ? "La nostra visione." : "Our vision."}
          </h1>

          <div style={{ display: "flex", flexDirection: "column", gap: 24, fontSize: "1.125rem", color: "var(--text-secondary)", lineHeight: 1.7 }}>
            <p>
              {lang === "it"
                ? "Aether nasce dalla convinzione che il futuro dell'intelligenza artificiale per le aziende e i professionisti non risieda in un singolo chatbot generico che cerca di fare tutto da solo, ma in una squadra di collaboratori specializzati che lavorano in modo coordinato."
                : "Aether is built on the conviction that the future of applied AI for businesses and professionals does not belong to a single generic chatbot trying to do everything alone, but to a specialized workforce of AI workers collaborating systematically."}
            </p>

            <p>
              {lang === "it"
                ? "Progettiamo Aether come una piattaforma aperta, rispettosa della privacy e incentrata sul controllo umano. Crediamo che i tuoi dati debbano restare tuoi e che ogni decisione critica debba sempre essere approvata da te."
                : "We design Aether as an open, privacy-first platform centered on human oversight. We believe your data must remain yours and that critical actions should always require your explicit confirmation."}
            </p>
          </div>

          {/* 3 Values */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 20, marginTop: 48 }}>
            {[
              {
                icon: Users,
                title: lang === "it" ? "Lavoro di Squadra" : "Workforce Collaboration",
                desc: lang === "it"
                  ? "Scomporre i compiti complessi tra più collaboratori dedicati garantisce precisione e verificabilità."
                  : "Decomposing complex goals across specialized workers delivers reliability and zero hallucination drift.",
              },
              {
                icon: Laptop,
                title: lang === "it" ? "Privacy & Sovranità" : "Privacy & Sovereignty",
                desc: lang === "it"
                  ? "I tuoi documenti aziendali possono essere elaborati localmente con Ollama senza dipendenze cloud obbligatorie."
                  : "Your company knowledge can be processed 100% locally with Ollama without forced cloud lock-in.",
              },
              {
                icon: ShieldCheck,
                title: lang === "it" ? "Controllo Umano" : "Human Oversight",
                desc: lang === "it"
                  ? "L'intelligenza artificiale accelera il lavoro; tu mantieni sempre l'ultima parola."
                  : "AI workers accelerate the execution; you always maintain the final decision.",
              },
            ].map((v, i) => {
              const Icon = v.icon;
              return (
                <div key={i} className="glass-card" style={{ padding: "26px 24px", display: "flex", gap: 18, alignItems: "flex-start" }}>
                  <div
                    style={{
                      width: 44,
                      height: 44,
                      borderRadius: "var(--radius-sm)",
                      background: "rgba(var(--accent-violet-rgb), 0.1)",
                      border: "1px solid rgba(var(--accent-violet-rgb), 0.25)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      flexShrink: 0,
                    }}
                  >
                    <Icon size={20} style={{ color: "var(--accent-violet)" }} />
                  </div>
                  <div>
                    <h3 style={{ fontSize: "1.15rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: 6 }}>
                      {v.title}
                    </h3>
                    <p style={{ fontSize: "0.95rem", color: "var(--text-secondary)", lineHeight: 1.55, margin: 0 }}>
                      {v.desc}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      <Footer />
    </main>
  );
}
