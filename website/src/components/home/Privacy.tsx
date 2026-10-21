import type { Copy } from "@/content/home";
import { Heading, Rise } from "./Rise";

export function Privacy({ c }: { c: Copy }) {
  const p = c.privacy;
  const cols = [p.columns.stays, p.columns.goes, p.columns.asks];
  return (
    <Rise as="section" variant="wipe" className="ae-section ae-privacy" id="privacy">
      <div className="ae-wrap">
        <Heading>{p.title}</Heading>
        <Rise as="p" i={1} className="ae-lead">{p.sub}</Rise>
        <div className="ae-priv-cols">
          {cols.map((col, i) => (
            <Rise key={col.title} className="ae-priv-col" i={i}>
              <h3>{col.title}</h3>
              <ul>{col.items.map((it) => <li key={it}>{it}</li>)}</ul>
            </Rise>
          ))}
        </div>
        <Rise as="p" i={3} className="ae-foot-note">{p.footnote}</Rise>
      </div>
    </Rise>
  );
}
