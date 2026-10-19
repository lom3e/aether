"use client";

import Link from "next/link";
import { useLanguage } from "@/lib/i18n/context";
import { REPO_URL } from "@/lib/site";
import { PlatformText } from "./PlatformText";
import { OrbCanvas } from "@/components/orb/OrbCanvas";

export function SiteFooter() {
  const { lang, c } = useLanguage();
  const f = c.footer;
  const base = `/${lang}`;
  return (
    <footer className="ae-footer">
      <div className="ae-wrap">
        <div className="ae-foot-cols">
          <div>
            <h4>{f.product}</h4>
            <a href={`${base}#demo`}>{c.nav.demo}</a>
            <a href={`${base}#memory`}>{c.nav.memory}</a>
            <a href={`${base}#download`}>{c.nav.download}</a>
          </div>
          <div>
            <h4>{f.project}</h4>
            <Link href={`${base}/builders`}>{f.builders}</Link>
            <Link href={`${base}/about`}>{f.about}</Link>
            <a href={REPO_URL}>{f.github}</a>
            <a href={`${REPO_URL}/blob/development/CHANGELOG.md`}>{f.changelog}</a>
          </div>
          <div>
            <h4>{f.legal}</h4>
            <Link href={`${base}/privacy`}>{f.privacy}</Link>
            <Link href={`${base}/cookies`}>{f.cookies}</Link>
            <button onClick={() => window.dispatchEvent(new CustomEvent("aether-open-cookie-preferences"))}>{f.cookieSettings}</button>
          </div>
          <div>
            <h4>Aether</h4>
            <p className="ae-p" style={{ fontSize: 16 }}><PlatformText mac={f.tagline} pc={f.taglinePc} /></p>
          </div>
        </div>
        <div className="ae-foot-base">
          <span>{f.copy}</span>
          <a href="https://lmlabs.it" style={{ color: "inherit" }}>{f.built}</a>
        </div>
      </div>
      <div className="ae-foot-orb" aria-hidden="true">
        <OrbCanvas scale label="Aether" state="idle" />
        <span className="ae-foot-word">Aether</span>
      </div>
    </footer>
  );
}
