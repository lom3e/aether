import type { Copy } from "@/content/home";
import { Rise } from "./Rise";

export function MemoryBoard({ c }: { c: Copy }) {
  const m = c.memory;
  return (
    <section className="ae-section" id="memory">
      <div className="ae-wrap">
        <Rise as="h2" className="ae-h2" style={{ maxWidth: "20ch" }}>{m.title}</Rise>
        <Rise as="p" i={1} className="ae-lead">{m.sub}</Rise>
        <div className="ae-board">
          <Rise className="ae-tile s6 tall acc" i={0}>
            <span className="ae-bubble sm" style={{ background: "var(--ae-accent-ink)" }} />
            <div className="ae-big">{m.learn.title}</div>
            <div className="ae-flow">
              <div>{m.learn.before}</div>
              <div className="fix">{m.learn.correction}</div>
              <div className="ok">{m.learn.after}</div>
            </div>
            <p className="ae-p">{m.learn.text}</p>
          </Rise>
          <Rise className="ae-tile s6 tall" i={1}>
            <span className="ae-bubble" />
            <h3 className="ae-big" style={{ fontSize: "clamp(26px,2.6vw,40px)" }}>{m.knowledge.title}</h3>
            <p className="ae-p">{m.knowledge.text}</p>
          </Rise>
          {m.categories.map((cat, i) => (
            <Rise key={cat.name} className="ae-tile s3" i={i % 4}>
              <h3>{cat.name}</h3>
              <p className="ae-p">{cat.line}</p>
            </Rise>
          ))}
          <Rise className="ae-tile s6" i={0}>
            <h3>{m.remember.title}</h3>
            <p className="ae-p">{m.remember.text}</p>
          </Rise>
          <Rise className="ae-tile s6" i={1}>
            <h3>{m.versions.title}</h3>
            <p className="ae-p">{m.versions.text}</p>
          </Rise>
        </div>
      </div>
    </section>
  );
}
