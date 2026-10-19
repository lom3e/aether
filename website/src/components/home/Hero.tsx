import type { Copy } from "@/content/home";
import { OrbCanvas } from "@/components/orb/OrbCanvas";
import { DMG_URL } from "@/lib/site";
import { PlatformText } from "./PlatformText";

export function Hero({ c }: { c: Copy }) {
  return (
    <section className="ae-hero" id="top">
      <div className="ae-hero-orb" aria-hidden={false}>
        <OrbCanvas scale label={c.hero.orbLabel} state="idle" />
      </div>
      <div className="ae-wrap ae-hero-copy">
        <h1 className="ae-h1">
          <span>{c.hero.l1}</span>
          <span><PlatformText mac={c.hero.l2} pc={c.hero.l2Pc} /></span>
        </h1>
        <p className="ae-hero-sub">{c.hero.sub}</p>
        <div className="ae-hero-actions">
          <a className="ae-btn" href={DMG_URL}>{c.hero.cta}</a>
          <a className="ae-link" href="#demo">{c.hero.secondary}</a>
        </div>
        <p className="ae-hero-note"><PlatformText mac={c.hero.note} pc={c.hero.notePc} /></p>
      </div>
    </section>
  );
}
