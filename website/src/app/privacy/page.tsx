"use client";

import React from "react";
import Link from "next/link";
import { ArrowLeft, ShieldCheck, Lock, FileText, Server, EyeOff, UserCheck, HelpCircle } from "lucide-react";
import { Navbar } from "@/components/Navbar";
import { Footer } from "@/components/Footer";
import { useLanguage } from "@/lib/i18n/context";

export default function PrivacyPage() {
  const { lang } = useLanguage();
  const isIt = lang === "it";

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
          <span className="section-tag">{isIt ? "CONFORMITÀ & TRASPARENZA" : "COMPLIANCE & TRANSPARENCY"}</span>
          <h1 className="section-title" style={{ marginBottom: 16 }}>
            {isIt ? "Informativa sulla Privacy" : "Privacy Policy"}
          </h1>
          <p style={{ fontSize: "1.0625rem", color: "var(--text-muted)", marginBottom: 40, lineHeight: 1.6 }}>
            {isIt
              ? "Ultimo aggiornamento: 30 Agosto 2026 • Conforme al Regolamento Generale sulla Protezione dei Dati (GDPR - Reg. UE 2016/679)"
              : "Last updated: August 30, 2026 • Compliant with General Data Protection Regulation (GDPR - EU Reg. 2016/679)"}
          </p>

          {/* Highlight Box: Privacy-by-Design Philosophy */}
          <div
            className="glass-card"
            style={{
              padding: "28px 26px",
              background: "var(--bg-surface-elevated)",
              border: "1px solid var(--border-highlight)",
              borderRadius: "var(--radius-lg)",
              marginBottom: 44,
              display: "flex",
              gap: 18,
              alignItems: "flex-start",
            }}
          >
            <div
              style={{
                width: 44,
                height: 44,
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
              <ShieldCheck size={22} />
            </div>
            <div>
              <h2 style={{ fontSize: "1.15rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: 8, letterSpacing: "-0.01em" }}>
                {isIt ? "Principio Fondamentale: Sovranità Locale dei Dati" : "Core Principle: Local Data Sovereignty"}
              </h2>
              <p style={{ fontSize: "0.95rem", color: "var(--text-secondary)", lineHeight: 1.6, margin: 0 }}>
                {isIt
                  ? "Aether è progettato secondo i principi di Privacy by Design e Privacy by Default. Quando utilizzi l'applicazione desktop Aether con modelli di intelligenza artificiale eseguiti in locale (come Ollama), tutti i documenti, i prompt e i dati rimangono esclusivamente sul tuo computer. Nessun dato personale o documento aziendale viene inviato ai nostri server o a terze parti."
                  : "Aether is built upon the principles of Privacy by Design and Privacy by Default. When using the Aether desktop application with locally running AI models (such as Ollama), all documents, prompts, and corporate files remain strictly on your local machine. No personal data or business documents are transmitted to our servers or third parties."}
              </p>
            </div>
          </div>

          {/* Detailed Policy Sections */}
          <div style={{ display: "flex", flexDirection: "column", gap: 36, color: "var(--text-secondary)", fontSize: "1.025rem", lineHeight: 1.7 }}>
            {/* Section 1 */}
            <div>
              <h2 style={{ fontSize: "1.35rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: 12, letterSpacing: "-0.02em" }}>
                {isIt ? "1. Titolare del Trattamento dei Dati" : "1. Data Controller"}
              </h2>
              <p>
                {isIt
                  ? "Il Titolare del trattamento dei dati raccolti tramite questo sito web (aether-workforce.org / aether-website-mu.vercel.app) è il progetto Aether promosso da LMLabs (con sede in Italia). Per qualsiasi richiesta o per l'esercizio dei diritti previsti dal GDPR, puoi contattarci all'indirizzo email dedicato:"
                  : "The Data Controller for information processed through this website (aether-workforce.org / aether-website-mu.vercel.app) is the Aether Project sponsored by LMLabs (based in Italy). For any privacy inquiries or to exercise your GDPR rights, you can reach out via email at:"}
              </p>
              <div style={{ marginTop: 10, padding: "12px 18px", background: "var(--bg-surface)", border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-sm)", display: "inline-block" }}>
                <a
                  href="mailto:privacy@aethermate.com"
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.9rem",
                    color: "var(--accent-violet)",
                    fontWeight: 600,
                    textDecoration: "none",
                  }}
                >
                  privacy@aethermate.com
                </a>
              </div>
            </div>

            {/* Section 2 */}
            <div>
              <h2 style={{ fontSize: "1.35rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: 12, letterSpacing: "-0.02em" }}>
                {isIt ? "2. Dati Personali Trattati Tramite il Sito Web" : "2. Personal Data Processed on the Website"}
              </h2>
              <p>
                {isIt
                  ? "Attraverso la navigazione su questo sito web, trattiamo esclusivamente le seguenti tipologie di dati:"
                  : "Through your navigation on this website, we only process the following categories of data:"}
              </p>
              <ul style={{ paddingLeft: 24, marginTop: 8, display: "flex", flexDirection: "column", gap: 8 }}>
                <li>
                  <strong style={{ color: "var(--text-primary)" }}>{isIt ? "Dati Tecnici di Navigazione:" : "Technical Navigation Data:"}</strong>{" "}
                  {isIt
                    ? "Indirizzo IP (anonimizzato nei log standard del provider di hosting), tipo di browser, sistema operativo, orario della richiesta e pagine visitate, raccolti al solo fine di garantire la sicurezza e il corretto funzionamento dell'infrastruttura web."
                    : "IP address (anonymized in standard hosting provider logs), browser user-agent, operating system, timestamp of request, and requested pages, collected strictly for security, traffic routing, and system integrity."}
                </li>
                <li>
                  <strong style={{ color: "var(--text-primary)" }}>{isIt ? "Preferenze di Navigazione Locali (LocalStorage):" : "Local Browsing Preferences (LocalStorage):"}</strong>{" "}
                  {isIt
                    ? "Scelta della lingua (IT/EN), tema grafico (chiaro/scuro) e stato del consenso ai cookie. Questi dati sono conservati unicamente nel tuo browser e non vengono trasmessi a server esterni."
                    : "Selection of language (IT/EN), visual theme (light/dark), and privacy consent status. This information is stored solely within your local browser storage and is never transferred to remote servers."}
                </li>
              </ul>
            </div>

            {/* Section 3 */}
            <div>
              <h2 style={{ fontSize: "1.35rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: 12, letterSpacing: "-0.02em" }}>
                {isIt ? "3. Finalità e Basi Giuridiche del Trattamento" : "3. Purposes and Legal Basis for Processing"}
              </h2>
              <p>
                {isIt
                  ? "I dati vengono trattati nel rispetto dei principi di liceità, correttezza e trasparenza previsti dall'Art. 6 del GDPR:"
                  : "Data is processed in compliance with the principles of lawfulness, fairness, and transparency pursuant to Article 6 of GDPR:"}
              </p>
              <ul style={{ paddingLeft: 24, marginTop: 8, display: "flex", flexDirection: "column", gap: 8 }}>
                <li>
                  <strong style={{ color: "var(--text-primary)" }}>{isIt ? "Erogazione del Servizio Web:" : "Service Delivery:"}</strong>{" "}
                  {isIt
                    ? "Permettere la visualizzazione delle pagine e il download diretto del software (.dmg per macOS). Base giuridica: esecuzione di misure precontrattuali o contrattuali (Art. 6.1.b GDPR)."
                    : "Enabling page rendering and direct software binary download (.dmg for macOS). Legal basis: performance of pre-contractual or contractual steps (Art. 6.1.b GDPR)."}
                </li>
                <li>
                  <strong style={{ color: "var(--text-primary)" }}>{isIt ? "Sicurezza e Prevenzione Abusi:" : "Security & Fraud Prevention:"}</strong>{" "}
                  {isIt
                    ? "Monitoraggio tecnico per prevenire attacchi informatici e malfunzionamenti. Base giuridica: legittimo interesse del Titolare (Art. 6.1.f GDPR)."
                    : "Technical monitoring to prevent cyber attacks, spam, or service degradation. Legal basis: legitimate interest of the Controller (Art. 6.1.f GDPR)."}
                </li>
              </ul>
            </div>

            {/* Section 4 */}
            <div>
              <h2 style={{ fontSize: "1.35rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: 12, letterSpacing: "-0.02em" }}>
                {isIt ? "4. Nessun Tracciamento Invasivo o Profilazione" : "4. Zero Invasive Tracking or Profiling"}
              </h2>
              <p>
                {isIt
                  ? "Non effettuiamo alcun tipo di profilazione commerciale, non vendiamo dati a terzi e non utilizziamo cookie pubblicitari di tracciamento invasivo. Il nostro modello di business e di sviluppo è interamente incentrato sul software open source e sul rispetto dell'utente."
                  : "We do not engage in behavioral advertising profiling, we do not sell personal data to third parties, and we do not deploy invasive tracking cookies. Our development philosophy is rooted in transparent open-source software and total respect for user privacy."}
              </p>
            </div>

            {/* Section 5 */}
            <div>
              <h2 style={{ fontSize: "1.35rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: 12, letterSpacing: "-0.02em" }}>
                {isIt ? "5. Conservazione e Destinatari dei Dati" : "5. Data Retention and Third-Party Processors"}
              </h2>
              <p>
                {isIt
                  ? "Il sito è ospitato sull'infrastruttura globale di Vercel Inc. e il codice sorgente è ospitato su GitHub (Microsoft Corp.). I log tecnici di connessione vengono cancellati automaticamente secondo le policy standard di sicurezza del provider (normalmente entro 30 giorni)."
                  : "The website is hosted on the global CDN infrastructure of Vercel Inc. and source code releases are hosted on GitHub (Microsoft Corp.). Technical connection logs are purged automatically in accordance with standard provider retention schedules (typically within 30 days)."}
              </p>
            </div>

            {/* Section 6 */}
            <div>
              <h2 style={{ fontSize: "1.35rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: 12, letterSpacing: "-0.02em" }}>
                {isIt ? "6. I Tuoi Diritti (Artt. 15-22 del GDPR)" : "6. Your Rights under GDPR (Articles 15-22)"}
              </h2>
              <p>
                {isIt
                  ? "In qualità di interessato, hai il diritto in qualunque momento di esercitare i tuoi diritti ai sensi del Regolamento UE 2016/679:"
                  : "As a data subject, you are entitled under EU Regulation 2016/679 to exercise the following rights at any time:"}
              </p>
              <ul style={{ paddingLeft: 24, marginTop: 8, display: "flex", flexDirection: "column", gap: 6 }}>
                <li><strong>{isIt ? "Diritto di Accesso:" : "Right of Access:"}</strong> {isIt ? "ottenere conferma dell'esistenza o meno di dati personali che ti riguardano." : "obtain confirmation as to whether your personal data is being processed."}</li>
                <li><strong>{isIt ? "Diritto di Rettifica e Cancellazione (Oblio):" : "Right to Rectification and Erasure:"}</strong> {isIt ? "richiedere l'aggiornamento o la cancellazione dei dati trattati." : "request correction of inaccurate data or deletion of personal data."}</li>
                <li><strong>{isIt ? "Diritto di Limitazione e Opposizione:" : "Right to Restriction and Object:"}</strong> {isIt ? "opporsi in tutto o in parte al trattamento per motivi legittimi." : "restrict or object to data processing on legitimate grounds."}</li>
                <li><strong>{isIt ? "Diritto di Reclamo:" : "Right to Lodge a Complaint:"}</strong> {isIt ? "proporre reclamo all'Autorità Garante per la Protezione dei Dati Personali (www.garanteprivacy.it) qualora ritieni che il trattamento violi la normativa vigente." : "lodge a formal complaint with your relevant Data Protection Authority (such as the Italian Garante Privacy at www.garanteprivacy.it)."}</li>
              </ul>
            </div>

            {/* Section 7 */}
            <div style={{ borderTop: "1px solid var(--border-subtle)", paddingTop: 24, marginTop: 12 }}>
              <p style={{ fontSize: "0.95rem", color: "var(--text-muted)", margin: 0 }}>
                {isIt
                  ? "Per maggiori informazioni sulla gestione dei cookie e dello storage locale, consulta la nostra "
                  : "For detailed information regarding cookies and local storage management, please review our "}
                <Link href="/cookies" style={{ color: "var(--accent-violet)", textDecoration: "underline", fontWeight: 600 }}>
                  {isIt ? "Cookie Policy dedicata" : "dedicated Cookie Policy"}
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
