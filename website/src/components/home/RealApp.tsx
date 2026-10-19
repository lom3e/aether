import Image from "next/image";
import type { Copy } from "@/content/home";
import { Heading, Rise } from "./Rise";
import { AppVideo } from "./AppVideo";

const FILES = [
  { name: "app-home.png", w: 2400, h: 1600 },
  { name: "companion-panel.png", w: 816, h: 1208 },
  { name: "companion-choose.png", w: 816, h: 1208 },
  { name: "companion-review.png", w: 816, h: 1208 },
];

export function RealApp({ c, lang }: { c: Copy; lang: string }) {
  const r = c.real;
  return (
    <section className="ae-section ae-real" id="app" style={{ paddingTop: 0 }}>
      <div className="ae-wrap">
        <Heading style={{ maxWidth: "20ch" }}>{r.title}</Heading>
        <Rise as="p" i={1} className="ae-lead">{r.sub}</Rise>
        <Rise i={2} className="ae-video-wrap">
          <AppVideo src={`/video/companion-${lang}.mp4`} poster={`/video/companion-${lang}.jpg`} label={r.video.label} caption={r.video.caption} play={r.video.play} pause={r.video.pause} />
        </Rise>
        <div className="ae-shots">
          {r.shots.map((s, i) => (
            <Rise key={s.label} i={Math.min(i, 3)} className={`ae-shot-card${i === 0 ? " wide" : ""}`}>
              <div className="ae-shot-frame">
                <Image src={`/shots/${lang}/${FILES[i].name}`} width={FILES[i].w} height={FILES[i].h} alt={s.alt} sizes={i === 0 ? "(max-width: 920px) 100vw, 1200px" : "(max-width: 920px) 60vw, 380px"} loading="lazy" quality={92} />
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
