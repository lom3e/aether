import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { isLang } from "@/content/home";
import { Nav } from "@/components/home/Nav";
import { SiteFooter } from "@/components/home/SiteFooter";
import { inline, loadChangelog, type Inline } from "@/lib/changelog";

export async function generateMetadata({ params }: { params: Promise<{ lang: string }> }): Promise<Metadata> {
  const { lang } = await params;
  return { title: lang === "it" ? "Novità" : "What's new", alternates: { canonical: `/${lang}/changelog` } };
}

function Rich({ text }: { text: string }) {
  return (
    <>
      {inline(text).map((p: Inline, i) =>
        p.t === "b" ? <strong key={i}>{p.v}</strong>
        : p.t === "code" ? <code key={i}>{p.v}</code>
        : p.t === "a" ? <a key={i} className="ae-link" href={p.href}>{p.v}</a>
        : <span key={i}>{p.v}</span>,
      )}
    </>
  );
}

export default async function ChangelogPage({ params }: { params: Promise<{ lang: string }> }) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();
  const releases = loadChangelog().slice(0, 8);
  const it = lang === "it";
  return (
    <>
      <Nav />
      <main id="main" className="ae-section" style={{ paddingTop: 140 }}>
        <div className="ae-wrap ae-changelog">
          <h1 className="ae-h2" style={{ maxWidth: "none" }}>{it ? "Novità" : "What's new"}</h1>
          <p className="ae-lead">{it ? "Le ultime versioni di Aether. Il registro completo è su GitHub." : "The latest Aether versions. The full log is on GitHub."}</p>
          <div className="ae-acc" style={{ marginTop: 48 }}>
            {releases.map((r, idx) => (
              <details key={r.title} open={idx === 0} name="rel">
                <summary>{r.title}{r.date ? <small className="ae-rel-date">{r.date}</small> : null}</summary>
                <div className="ans ae-rel-body">
                  {r.sections.map((s, i) => (
                    <div key={i}>
                      {s.heading && <h3>{s.heading}</h3>}
                      {s.paragraphs.map((p, k) => <p key={k}><Rich text={p} /></p>)}
                      {s.items.length > 0 && <ul>{s.items.map((it2, k) => <li key={k}><Rich text={it2} /></li>)}</ul>}
                    </div>
                  ))}
                </div>
              </details>
            ))}
          </div>
          <p className="ae-p" style={{ marginTop: 32 }}>
            <a className="ae-link" href="https://github.com/lom3e/aether/blob/development/CHANGELOG.md">{it ? "Registro completo su GitHub" : "Full log on GitHub"}</a>
          </p>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
