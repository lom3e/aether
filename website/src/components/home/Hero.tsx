import type { Copy } from "@/content/home";
import { DMG_URL } from "@/lib/site";
import { PlatformText } from "./PlatformText";
import { HeroOrb } from "./HeroOrb";
import { HeroCta } from "./HeroCta";

export function Hero({ c }: { c: Copy }) {
  return (
    <section className="ae-hero" id="top">
      <div className="ae-hero-orb">
        <HeroOrb label={c.hero.orbLabel} />
      </div>
      <div className="ae-wrap ae-hero-copy">
        <h1 className="ae-h1">
          <span className="ae-line"><span>{c.hero.l1}</span></span>
          <span className="ae-line d1"><span><PlatformText mac={c.hero.l2} pc={c.hero.l2Pc} /></span></span>
        </h1>
        <p className="ae-hero-sub ae-in-load" style={{ ["--d" as string]: "420ms" }}>{c.hero.sub}</p>
        <div className="ae-hero-actions ae-in-load" style={{ ["--d" as string]: "560ms" }}>
          <HeroCta href={DMG_URL}>{c.hero.cta}</HeroCta>
          <a className="ae-link" href="#demo">{c.hero.secondary}</a>
        </div>
        <p className="ae-hero-note ae-in-load" style={{ ["--d" as string]: "700ms" }}><PlatformText mac={c.hero.note} pc={c.hero.notePc} /></p>
      </div>
    </section>
  );
}
