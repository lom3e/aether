"use client";

import React from "react";
import Link from "next/link";
import { ArrowLeft, Cookie, Settings2, ShieldCheck, Database, CheckCircle2 } from "lucide-react";
import { Navbar } from "@/components/Navbar";
import { Footer } from "@/components/Footer";
import { useLanguage } from "@/lib/i18n/context";

export default function CookiesPage() {
  const { lang } = useLanguage();
  const isIt = lang === "it";

  const handleOpenConsentModal = () => {
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("aether-open-cookie-preferences"));
    }
  };

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
                transition: "color 150ms ease",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.color = "var(--text-primary)")}
              onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-secondary)")}
            >
              <ArrowLeft size={16} />
              <span>{isIt ? "Torna alla Home" : "Back to Home"}</span>
            </Link>
          </div>

          {/* Page Tag & Title */}
          <span className="section-tag">{isIt ? "GESTIONE COOKIE & STORAGE" : "COOKIE MANAGEMENT & STORAGE"}</span>
          <h1 className="section-title" style={{ marginBottom: 16 }}>
            {isIt ? "Informativa Estesa sui Cookie" : "Cookie Policy"}
          </h1>
          <p style={{ fontSize: "1.0625rem", color: "var(--text-muted)", marginBottom: 36, lineHeight: 1.6 }}>
            {isIt
              ? "Ultimo aggiornamento: 30 Agosto 2026 • Conforme alla Direttiva ePrivacy e alle Linee Guida del Garante Privacy"
              : "Last updated: August 30, 2026 • Compliant with ePrivacy Directive and European Privacy Guidelines"}
          </p>

          {/* Quick Action Box: Manage Preferences */}
          <div
            className="glass-card"
            style={{
              padding: "24px 26px",
              background: "var(--bg-surface-elevated)",
              border: "1px solid var(--border-highlight)",
              borderRadius: "var(--radius-lg)",
              marginBottom: 44,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              flexWrap: "wrap",
              gap: 18,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
              <div
                style={{
                  width: 40,
                  height: 40,
                  borderRadius: "var(--radius-sm)",
                  background: "rgba(var(--accent-violet-rgb), 0.12)",
                  border: "1px solid rgba(var(--accent-violet-rgb), 0.3)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "var(--accent-violet)",
                  flexShrink: 0,
                }}
              >
                <Cookie size={20} />
              </div>
              <div>
                <h2 style={{ fontSize: "1.05rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
                  {isIt ? "Vuoi modificare le tue scelte?" : "Want to change your preferences?"}
                </h2>
                <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", margin: 0, marginTop: 2 }}>
                  {isIt
                    ? "Puoi aggiornare o revocare il tuo consenso in qualsiasi momento con un click."
                    : "You can update or withdraw your consent at any time in one click."}
                </p>
              </div>
            </div>

            <button
              onClick={handleOpenConsentModal}
              className="btn-primary"
              style={{
                padding: "10px 20px",
                fontSize: "0.875rem",
                borderRadius: "var(--radius-sm)",
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              <Settings2 size={16} />
              <span>{isIt ? "Gestisci Preferenze Cookie" : "Manage Cookie Preferences"}</span>
            </button>
          </div>

          {/* Main Content */}
          <div style={{ display: "flex", flexDirection: "column", gap: 36, color: "var(--text-secondary)", fontSize: "1.025rem", lineHeight: 1.7 }}>
            {/* Section 1 */}
            <div>
              <h2 style={{ fontSize: "1.35rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: 12, letterSpacing: "-0.02em" }}>
                {isIt ? "1. Cosa Sono i Cookie e il LocalStorage" : "1. What are Cookies and LocalStorage"}
              </h2>
              <p>
                {isIt
                  ? "I cookie sono piccoli file di testo che i siti web visitati inviano al terminale dell'utente, dove vengono memorizzati per essere poi ritrasmessi agli stessi siti alla visita successiva. Oltre ai cookie tradizionali, le moderne applicazioni web utilizzano la tecnologia di archiviazione locale (LocalStorage), che permette di salvare informazioni essenziali direttamente nel browser in modo sicuro, performante e senza sovraccaricare le richieste di rete."
                  : "Cookies are small text files placed on your device by websites you visit. In addition to traditional HTTP cookies, modern web platforms utilize LocalStorage, an advanced web standard that securely saves essential settings locally within your browser without sending unnecessary network overhead on every request."}
              </p>
            </div>

            {/* Section 2: Detailed Table */}
            <div>
              <h2 style={{ fontSize: "1.35rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: 12, letterSpacing: "-0.02em" }}>
                {isIt ? "2. Tecnologie e Dati Memorizzati su Questo Sito" : "2. Technologies and Keys Stored on this Website"}
              </h2>
              <p style={{ marginBottom: 16 }}>
                {isIt
                  ? "Questo sito web utilizza esclusivamente tecnologie tecniche e funzionali strettamente necessarie per offrirti l'esperienza desiderata:"
                  : "This website uses strictly necessary technical and functional technologies to provide you with the intended service experience:"}
              </p>

              {/* Responsive Table */}
              <div style={{ overflowX: "auto", border: "1px solid var(--border-medium)", borderRadius: "var(--radius-md)", background: "var(--bg-surface)" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "0.9rem" }}>
                  <thead>
                    <tr style={{ background: "var(--bg-surface-elevated)", borderBottom: "1px solid var(--border-medium)", color: "var(--text-primary)" }}>
                      <th style={{ padding: "12px 16px", fontWeight: 600 }}>{isIt ? "Nome Chiave" : "Key Name"}</th>
                      <th style={{ padding: "12px 16px", fontWeight: 600 }}>{isIt ? "Tipologia" : "Type"}</th>
                      <th style={{ padding: "12px 16px", fontWeight: 600 }}>{isIt ? "Finalità" : "Purpose"}</th>
                      <th style={{ padding: "12px 16px", fontWeight: 600 }}>{isIt ? "Durata" : "Duration"}</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                      <td style={{ padding: "12px 16px", fontFamily: "var(--font-mono)", color: "var(--accent-violet)", fontWeight: 600 }}>aether_theme</td>
                      <td style={{ padding: "12px 16px" }}>{isIt ? "LocalStorage (Tecnico)" : "LocalStorage (Technical)"}</td>
                      <td style={{ padding: "12px 16px" }}>{isIt ? "Memorizza la preferenza del tema visivo (Chiaro o Scuro)" : "Remembers visual theme selection (Light or Dark)"}</td>
                      <td style={{ padding: "12px 16px" }}>{isIt ? "Persistente" : "Persistent"}</td>
                    </tr>
                    <tr style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                      <td style={{ padding: "12px 16px", fontFamily: "var(--font-mono)", color: "var(--accent-violet)", fontWeight: 600 }}>aether_lang</td>
                      <td style={{ padding: "12px 16px" }}>{isIt ? "LocalStorage (Tecnico)" : "LocalStorage (Technical)"}</td>
                      <td style={{ padding: "12px 16px" }}>{isIt ? "Memorizza la lingua scelta dell'interfaccia (Italiano o Inglese)" : "Remembers selected interface language (Italian or English)"}</td>
                      <td style={{ padding: "12px 16px" }}>{isIt ? "Persistente" : "Persistent"}</td>
                    </tr>
                    <tr>
                      <td style={{ padding: "12px 16px", fontFamily: "var(--font-mono)", color: "var(--accent-violet)", fontWeight: 600 }}>aether_cookie_consent</td>
                      <td style={{ padding: "12px 16px" }}>{isIt ? "LocalStorage (Tecnico)" : "LocalStorage (Technical)"}</td>
                      <td style={{ padding: "12px 16px" }}>{isIt ? "Salva le preferenze di consenso privacy dell'utente" : "Stores user privacy consent choices and timestamp"}</td>
                      <td style={{ padding: "12px 16px" }}>{isIt ? "12 mesi" : "12 months"}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* Section 3 */}
            <div>
              <h2 style={{ fontSize: "1.35rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: 12, letterSpacing: "-0.02em" }}>
                {isIt ? "3. Nessun Cookie di Profilazione Pubblicitaria" : "3. No Advertising or Tracking Cookies"}
              </h2>
              <p>
                {isIt
                  ? "Non installiamo cookie di profilazione, cookie pubblicitari o tracciatori comportamentali di terze parti. Non cediamo né condividiamo le informazioni di navigazione con broker di dati pubblicitari."
                  : "We do not deploy profiling cookies, ad-network beacons, or third-party behavioral trackers. We do not sell or monetize browsing data with data brokers."}
              </p>
            </div>

            {/* Section 4 */}
            <div>
              <h2 style={{ fontSize: "1.35rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: 12, letterSpacing: "-0.02em" }}>
                {isIt ? "4. Come Gestire o Cancellare i Cookie nel Browser" : "4. How to Manage or Clear Cookies in Your Browser"}
              </h2>
              <p>
                {isIt
                  ? "Puoi gestire o cancellare in qualsiasi momento i dati memorizzati direttamente attraverso le impostazioni del tuo browser:"
                  : "You can also manage, inspect, or delete cookies and local storage directly through your browser settings:"}
              </p>
              <ul style={{ paddingLeft: 24, marginTop: 8, display: "flex", flexDirection: "column", gap: 6 }}>
                <li><strong>Apple Safari:</strong> {isIt ? "Impostazioni → Privacy → Gestisci dati siti web." : "Settings → Privacy → Manage Website Data."}</li>
                <li><strong>Google Chrome:</strong> {isIt ? "Impostazioni → Privacy e sicurezza → Cookie e altri dati dei siti." : "Settings → Privacy and security → Third-party cookies."}</li>
                <li><strong>Mozilla Firefox:</strong> {isIt ? "Opzioni → Privacy e sicurezza → Cookie e dati dei siti web." : "Settings → Privacy & Security → Cookies and Site Data."}</li>
                <li><strong>Microsoft Edge:</strong> {isIt ? "Impostazioni → Cookie e autorizzazioni sito." : "Settings → Cookies and site permissions."}</li>
              </ul>
            </div>

            {/* Section 5 */}
            <div style={{ borderTop: "1px solid var(--border-subtle)", paddingTop: 24, marginTop: 12 }}>
              <p style={{ fontSize: "0.95rem", color: "var(--text-muted)", margin: 0 }}>
                {isIt
                  ? "Per l'informativa completa sul trattamento dei dati personali e sui diritti dell'interessato ai sensi del GDPR, consulta la nostra "
                  : "For comprehensive details regarding personal data processing and data subject rights under GDPR, please review our "}
                <Link href="/privacy" style={{ color: "var(--accent-violet)", textDecoration: "underline", fontWeight: 600 }}>
                  {isIt ? "Informativa sulla Privacy" : "Privacy Policy"}
                </Link>.
              </p>
            </div>
          </div>
        </div>
      </section>

      <Footer />
    </main>
  );
}
