"use client";

import type { Copy } from "@/content/home";
import { DMG_URL, REPO_URL, RELEASES_URL } from "@/lib/site";
import { useGithubLatestRelease } from "@/lib/useGithubRelease";
import { Rise } from "./Rise";

export function Download({ c }: { c: Copy }) {
  const d = c.download;
  const { version } = useGithubLatestRelease();
  return (
    <section className="ae-section ae-download" id="download">
      <div className="ae-wrap ae-dl-grid">
        <div>
          <Rise as="h2" className="ae-h2">{d.title}</Rise>
          <Rise as="p" i={1} className="ae-lead">{d.sub}</Rise>
          <Rise i={2} className="ae-hero-actions">
            <a className="ae-btn" href={DMG_URL}>{d.button}</a>
            <a className="ae-link" href={RELEASES_URL}>{d.version}: {version}</a>
          </Rise>
          <Rise as="p" i={3} className="ae-p" style={{ marginTop: 18 }}>{d.requirements} {d.free}</Rise>
          <Rise i={3} className="ae-row" style={{ marginTop: 22, gap: 22 }}>
            <a className="ae-link" href={REPO_URL}>{d.github}</a>
            <a className="ae-link" href={`${REPO_URL}/blob/development/CHANGELOG.md`}>{d.changelog}</a>
          </Rise>
        </div>
        <div>
          <Rise as="h3" className="ae-step-title" style={{ marginTop: 0, maxWidth: "none" }}>{d.first.title}</Rise>
          <Rise as="ol" i={1} className="ae-steps">
            {d.first.steps.map((s) => <li key={s}>{s}</li>)}
          </Rise>
          <Rise as="p" i={2} className="ae-p" style={{ marginTop: 16 }}>{d.first.why}</Rise>
          <div className="ae-cols2">
            <Rise className="ae-small-tile" i={0}>
              <h3>{d.windows.title}</h3>
              <p className="ae-p">{d.windows.text}</p>
            </Rise>
            <Rise className="ae-small-tile" i={1}>
              <h3>{d.roadmap.title}</h3>
              <ul>{d.roadmap.items.map((it) => <li key={it} className="ae-p"><span className="ae-dot" />{it}</li>)}</ul>
            </Rise>
          </div>
        </div>
      </div>
    </section>
  );
}
