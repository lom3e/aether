import type { Copy } from "@/content/home";
import { Heading, Rise } from "./Rise";

export function Models({ c }: { c: Copy }) {
  const m = c.models;
  return (
    <section className="ae-section" id="models">
      <div className="ae-wrap">
        <Heading>{m.title}</Heading>
        <Rise as="p" i={1} className="ae-lead">{m.sub}</Rise>
      </div>
      <div className="ae-marquee" aria-label={m.providers.join(", ")}>
        <div className="ae-marquee-track">
          {[0, 1].map((k) => (
            <div className="ae-marquee-set" key={k} aria-hidden={k === 1}>
              {m.providers.map((p) => <span className="ae-provider" key={p + k}>{p}</span>)}
            </div>
          ))}
        </div>
      </div>
      <div className="ae-wrap">
        <Rise as="p" i={2} className="ae-p" style={{ marginTop: 28, maxWidth: "56ch" }}>{m.note}</Rise>
      </div>
    </section>
  );
}
