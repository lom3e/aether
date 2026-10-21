import type { Copy } from "@/content/home";
import { Heading, Rise } from "./Rise";

export function Faq({ c }: { c: Copy }) {
  return (
    <section className="ae-section" id="faq">
      <div className="ae-wrap ae-faq-grid">
        <Heading className="ae-h2 ae-faq-title">{c.faq.title}</Heading>
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
