import type { Copy } from "@/content/home";
import { Rise } from "./Rise";

export function Models({ c }: { c: Copy }) {
  const m = c.models;
  return (
    <section className="ae-section" id="models">
      <div className="ae-wrap">
        <Rise as="h2" className="ae-h2">{m.title}</Rise>
        <Rise as="p" i={1} className="ae-lead">{m.sub}</Rise>
        <div className="ae-providers">
          {m.providers.map((p, i) => (
            <Rise key={p} className="ae-provider" i={i}>{p}</Rise>
          ))}
        </div>
        <Rise as="p" i={2} className="ae-p" style={{ marginTop: 28, maxWidth: "56ch" }}>{m.note}</Rise>
      </div>
    </section>
  );
}
