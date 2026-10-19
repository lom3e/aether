import type { Copy } from "@/content/home";
import { Rise } from "./Rise";

export function Faq({ c }: { c: Copy }) {
  return (
    <section className="ae-section" id="faq">
      <div className="ae-wrap ae-faq-grid">
        <Rise as="h2" className="ae-h2 ae-faq-title">{c.faq.title}</Rise>
        <div className="ae-acc">
          {c.faq.items.map((it, i) => (
            <Rise key={it.q} i={Math.min(i, 3)}>
              <details name="faq">
                <summary>{it.q}</summary>
                <p className="ans">{it.a}</p>
              </details>
            </Rise>
          ))}
        </div>
      </div>
    </section>
  );
}
