import { readFileSync } from "node:fs";
import { join } from "node:path";

export interface ChangelogRelease {
  title: string; // e.g. "v1.7.1"
  date: string;
  sections: { heading: string; items: string[]; paragraphs: string[] }[];
}

/** Parses the repository CHANGELOG (Keep a Changelog style) into releases. Unreleased and empty releases are dropped. */
export function parseChangelog(md: string): ChangelogRelease[] {
  const releases: ChangelogRelease[] = [];
  let rel: ChangelogRelease | null = null;
  let sec: ChangelogRelease["sections"][number] | null = null;
  let item: string | null = null;
  const flush = () => { if (item !== null && sec) sec.items.push(item); item = null; };
  for (const raw of md.split("\n")) {
    const line = raw.trimEnd();
    const h2 = line.match(/^## \[([^\]]+)\](?: - (.+))?$/);
    if (h2) {
      flush();
      rel = { title: h2[1], date: (h2[2] || "").trim(), sections: [] };
      sec = null;
      if (!/unreleased/i.test(rel.title)) releases.push(rel);
      continue;
    }
    if (!rel) continue;
    const h3 = line.match(/^###\s+(.+)$/);
    if (h3) { flush(); sec = { heading: h3[1], items: [], paragraphs: [] }; rel.sections.push(sec); continue; }
    if (/^---+$/.test(line) || line === "") { flush(); continue; }
    if (!sec) { sec = { heading: "", items: [], paragraphs: [] }; rel.sections.push(sec); }
    if (/^[-*] /.test(line)) { flush(); item = line.replace(/^[-*] /, ""); }
    else if (/^\s+/.test(raw) && item !== null) item += " " + line.trim();
    else { flush(); sec.paragraphs.push(line); }
  }
  flush();
  return releases.filter((r) => r.sections.some((s) => s.items.length || s.paragraphs.length));
}

export function loadChangelog(): ChangelogRelease[] {
  try {
    return parseChangelog(readFileSync(join(process.cwd(), "content", "changelog.md"), "utf8"));
  } catch {
    return [];
  }
}

/** **bold**, `code` and [text](url) only; everything else is text. Returns plain tokens for React to render. */
export type Inline = { t: "text" | "b" | "code" | "a"; v: string; href?: string };
export function inline(text: string): Inline[] {
  const out: Inline[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g;
  let last = 0;
  for (const m of text.matchAll(re)) {
    if (m.index! > last) out.push({ t: "text", v: text.slice(last, m.index) });
    const tok = m[0];
    if (tok.startsWith("**")) out.push({ t: "b", v: tok.slice(2, -2) });
    else if (tok.startsWith("`")) out.push({ t: "code", v: tok.slice(1, -1) });
    else { const mm = tok.match(/^\[([^\]]+)\]\(([^)]+)\)$/)!; out.push({ t: "a", v: mm[1], href: mm[2] }); }
    last = m.index! + tok.length;
  }
  if (last < text.length) out.push({ t: "text", v: text.slice(last) });
  return out;
}
