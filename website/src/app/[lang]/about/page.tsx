"use client";

import React from "react";
import Link from "next/link";
import { ArrowLeft, Users, ShieldCheck, Laptop } from "lucide-react";
import { Nav } from "@/components/home/Nav";
import { SiteFooter } from "@/components/home/SiteFooter";
import { useLanguage } from "@/lib/i18n/context";

export default function AboutPage() {
  const { lang } = useLanguage();

  return (
    <main style={{ minHeight: "100vh", position: "relative", background: "var(--bg-page)" }}>
      <Nav />

      <section style={{ padding: "140px 0 100px" }}>
        <div className="container-narrow">
          {/* Back link */}
          <div style={{ marginBottom: 32 }}>
            <Link
              href={`/${lang}`}
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

          <span className="section-tag">{lang === "it" ? "CHI SIAMO" : "ABOUT"}</span>
          <h1 className="section-title" style={{ marginBottom: 24 }}>
            {lang === "it" ? "Un assistente tuo." : "An assistant that is yours."}
          </h1>

          <div style={{ display: "flex", flexDirection: "column", gap: 24, fontSize: "1.125rem", color: "var(--text-secondary)", lineHeight: 1.7 }}>
            <p>
              {lang === "it"
                ? "Aether è un assistente personale che vive sul tuo computer. Non è una chat che dimentica tutto: ricorda quello che gli dici, impara quando lo correggi, guarda lo schermo solo quando glielo chiedi e, per i lavori grandi, coordina squadre di agenti specializzati che puoi personalizzare."
                : "Aether is a personal assistant that lives on your computer. It is not a chat that forgets everything: it remembers what you tell it, learns when you correct it, looks at your screen only when you ask, and for bigger jobs coordinates teams of specialised agents you can customise."}
            </p>

            <p>
              {lang === "it"
                ? "Lo costruiamo come software aperto (licenza MIT), rispettoso della privacy e centrato sul controllo umano: i tuoi dati restano tuoi, sei tu a scegliere il modello, e le azioni sensibili aspettano la tua approvazione. Aether dice quello che ha verificato davvero, e niente di più."
                : "We build it as open source software (MIT license), privacy-first and centred on human oversight: your data stays yours, you choose the model, and sensitive actions wait for your approval. Aether reports what it actually verified, and nothing more."}
            </p>
          </div>

          {/* 3 Values */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 20, marginTop: 48 }}>
            {[
              {
                icon: Users,
                title: lang === "it" ? "Squadre su misura" : "Teams built for you",
                desc: lang === "it"
                  ? "Per i lavori complessi più agenti specializzati, ognuno con ruolo e strumenti, che tu puoi personalizzare."
                  : "For complex jobs, several specialised agents, each with its own role and tools, that you can customise.",
              },
              {
                icon: Laptop,
                title: lang === "it" ? "Privacy e scelta" : "Privacy and choice",
                desc: lang === "it"
                  ? "Memoria e documenti restano sul tuo computer. Con un modello locale (Ollama) nulla esce; con un provider cloud, il testo va solo a quel provider."
                  : "Memory and documents stay on your computer. With a local model (Ollama) nothing leaves; with a cloud provider, the text goes only to that provider.",
              },
              {
                icon: ShieldCheck,
                title: lang === "it" ? "Controllo Umano" : "Human Oversight",
                desc: lang === "it"
                  ? "L'AI accelera il lavoro; tu mantieni l'ultima parola."
                  : "AI speeds the work up; you keep the final word.",
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

      <SiteFooter />
    </main>
  );
}
