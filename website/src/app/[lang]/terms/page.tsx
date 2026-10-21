"use client";

import React from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { Nav } from "@/components/home/Nav";
import { SiteFooter } from "@/components/home/SiteFooter";
import { useLanguage } from "@/lib/i18n/context";

type Block = { h: string; p: string[] };

const IT: Block[] = [
  { h: "1. Cos'è Aether", p: ["Aether è un assistente personale open source (licenza MIT) che gira sul tuo computer. Questo sito (aethermate.com) serve a presentarlo e a distribuirne il download. Usando il sito o l'applicazione accetti questi termini."] },
  { h: "2. Licenza e assenza di garanzia", p: ["Il software è fornito \"così com'è\", senza garanzie di alcun tipo, come previsto dalla licenza MIT. Le risposte dei modelli di intelligenza artificiale possono essere inesatte: verificale prima di prendere decisioni importanti, soprattutto in ambito legale, medico o finanziario."] },
  { h: "3. I tuoi dati e i servizi collegati", p: ["I tuoi dati restano sul tuo computer. Se scegli di collegare un modello esterno o un servizio (per esempio Google Calendar o GitHub), Aether invia a quel servizio solo ciò che serve alla tua richiesta e solo dopo che lo hai autorizzato; puoi scollegarlo in qualsiasi momento da Collegamenti. L'uso di quei servizi è regolato dai loro termini."] },
  { h: "4. Uso corretto", p: ["Ti impegni a non usare Aether per attività illecite, per violare diritti di terzi o per aggirare le misure di sicurezza di altri servizi. Sei responsabile delle azioni che autorizzi Aether a compiere sui tuoi account e file."] },
  { h: "5. Responsabilità", p: ["Nei limiti consentiti dalla legge, gli autori non rispondono di danni indiretti o di perdita di dati derivanti dall'uso del software. Ti consigliamo di tenere copie dei file importanti. Restano ferme le tutele inderogabili previste per i consumatori."] },
  { h: "6. Modifiche", p: ["Possiamo aggiornare questi termini; la data in alto indica l'ultima revisione. Continuando a usare Aether dopo un aggiornamento accetti la nuova versione."] },
  { h: "7. Legge applicabile e contatti", p: ["Si applica la legge italiana. Per domande scrivi a privacy@aethermate.com."] },
];
const EN: Block[] = [
  { h: "1. What Aether is", p: ["Aether is an open-source (MIT licence) personal assistant that runs on your computer. This website (aethermate.com) presents it and hosts the download. By using the site or the app you accept these terms."] },
  { h: "2. Licence and no warranty", p: ["The software is provided \"as is\", without warranty of any kind, as set out in the MIT licence. AI model answers can be wrong: check them before making important decisions, especially legal, medical or financial ones."] },
  { h: "3. Your data and connected services", p: ["Your data stays on your computer. If you choose to connect an external model or service (for example Google Calendar or GitHub), Aether sends that service only what your request needs and only after you authorised it; you can disconnect it at any time from Connections. Those services are governed by their own terms."] },
  { h: "4. Acceptable use", p: ["You agree not to use Aether for unlawful activity, to infringe third-party rights or to bypass the security measures of other services. You are responsible for the actions you authorise Aether to take on your accounts and files."] },
  { h: "5. Liability", p: ["To the extent permitted by law, the authors are not liable for indirect damages or data loss arising from use of the software. Keep copies of important files. Mandatory consumer protections remain unaffected."] },
  { h: "6. Changes", p: ["We may update these terms; the date above shows the latest revision. Continuing to use Aether after an update means you accept the new version."] },
  { h: "7. Governing law and contact", p: ["Italian law applies. For questions write to privacy@aethermate.com."] },
];

export default function TermsPage() {
  const { lang } = useLanguage();
  const isIt = lang === "it";
  const blocks = isIt ? IT : EN;
  return (
    <main style={{ minHeight: "100vh", position: "relative", background: "var(--bg-page)" }}>
      <Nav />
      <section style={{ padding: "140px 0 100px" }}>
        <div className="container-narrow">
          <div style={{ marginBottom: 32 }}>
            <Link href={`/${lang}`} style={{ display: "inline-flex", alignItems: "center", gap: 8, color: "var(--text-secondary)", textDecoration: "none", fontSize: "0.875rem", fontWeight: 500 }}>
              <ArrowLeft size={16} />
              <span>{isIt ? "Torna alla Home" : "Back to Home"}</span>
            </Link>
          </div>
          <span className="section-tag">{isIt ? "TERMINI" : "TERMS"}</span>
          <h1 className="section-title" style={{ marginBottom: 16 }}>{isIt ? "Termini di servizio" : "Terms of Service"}</h1>
          <p style={{ fontSize: "1.0625rem", color: "var(--text-muted)", marginBottom: 40, lineHeight: 1.6 }}>
            {isIt ? "Ultimo aggiornamento: 21 ottobre 2026" : "Last updated: October 21, 2026"}
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 32, color: "var(--text-secondary)", fontSize: "1.025rem", lineHeight: 1.7 }}>
            {blocks.map((b) => (
              <div key={b.h}>
                <h2 style={{ fontSize: "1.35rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: 12, letterSpacing: "-0.02em" }}>{b.h}</h2>
                {b.p.map((t) => <p key={t}>{t}</p>)}
              </div>
            ))}
          </div>
        </div>
      </section>
      <SiteFooter />
    </main>
  );
}
