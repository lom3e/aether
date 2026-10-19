import type { Copy } from "@/content/home";
import { Heading, Rise } from "./Rise";

export function Teams({ c }: { c: Copy }) {
  const t = c.teams;
  return (
    <section className="ae-section" id="teams" style={{ paddingTop: 0 }}>
      <div className="ae-wrap">
        <Heading style={{ maxWidth: "20ch" }}>{t.title}</Heading>
        <Rise as="p" i={1} className="ae-lead">{t.sub}</Rise>
        <div className="ae-teams-grid">
          {t.presets.map((p, i) => (
            <Rise key={p.name} className="ae-team" i={i}>
              <h3>{p.name}</h3>
              <p className="ae-p">{p.line}</p>
            </Rise>
          ))}
          <Rise className="ae-teams-wide" i={0}>
            <h3 style={{ fontSize: 28, letterSpacing: "-0.03em" }}>{t.architect.title}</h3>
            <p className="ae-p" style={{ marginTop: 10, maxWidth: "46ch" }}>{t.architect.text}</p>
          </Rise>
          <Rise className="ae-teams-wide" i={1}>
            <h3 style={{ fontSize: 28, letterSpacing: "-0.03em" }}>{t.community.title}</h3>
            <p className="ae-p" style={{ marginTop: 10, maxWidth: "46ch" }}>{t.community.text}</p>
          </Rise>
        </div>
      </div>
    </section>
  );
}
