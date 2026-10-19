import Image from "next/image";
import type { Copy } from "@/content/home";
import { Rise } from "./Rise";

const FILES = [
  { src: "/shots/app-home.jpg", w: 1800, h: 1200 },
  { src: "/shots/companion-panel.png", w: 700, h: 1037 },
  { src: "/shots/companion-choose.png", w: 700, h: 1037 },
  { src: "/shots/companion-review.png", w: 700, h: 1037 },
];

export function RealApp({ c }: { c: Copy }) {
  const r = c.real;
  return (
    <section className="ae-section ae-real" id="app" style={{ paddingTop: 0 }}>
      <div className="ae-wrap">
        <Rise as="h2" className="ae-h2" style={{ maxWidth: "20ch" }}>{r.title}</Rise>
        <Rise as="p" i={1} className="ae-lead">{r.sub}</Rise>
        <div className="ae-shots">
          {r.shots.map((s, i) => (
            <Rise key={s.label} i={Math.min(i, 3)} className={`ae-shot-card${i === 0 ? " wide" : ""}`}>
              <div className="ae-shot-frame">
                <Image src={FILES[i].src} width={FILES[i].w} height={FILES[i].h} alt={s.alt} sizes={i === 0 ? "(max-width: 920px) 100vw, 1200px" : "(max-width: 920px) 60vw, 380px"} loading="lazy" />
              </div>
              <p className="ae-p ae-shot-label"><span className="ae-dot" />{s.label}</p>
            </Rise>
          ))}
        </div>
        <Rise as="p" className="ae-demo-note">{r.caption}</Rise>
      </div>
    </section>
  );
}
