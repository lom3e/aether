import { describe, expect, it } from "vitest";
import { copy, it as itCopy, en as enCopy } from "../src/content/home";
import { translations } from "../src/lib/i18n/translations";

function shape(v: unknown): unknown {
  if (Array.isArray(v)) return v.map(shape);
  if (v && typeof v === "object") return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, shape(x)]));
  return typeof v;
}

describe("home copy", () => {
  it("IT and EN have exactly the same structure", () => {
    expect(shape(enCopy)).toEqual(shape(itCopy));
  });

  it("cookie banner strings have the same structure in both languages", () => {
    expect(shape(translations.en)).toEqual(shape(translations.it));
  });

  it("never claims what the product cannot back (claims ledger)", () => {
    const text = JSON.stringify(copy).toLowerCase();
    const banned = [
      "zero allucinazion", "nessuna allucinazione", "zero hallucination", "no hallucination",
      "in 1 secondo", "in 1 second", "mai inviat", "never sent", "nothing ever leaves",
      "sempre in ascolto", "always listening", "always watching", "ti osserva",
      "aggiornamenti automatici attivi", "notarizzat" + "a da apple e", // "is notarized" style claims
      "windows disponibile", "windows available", "download for windows", "scarica per windows",
    ];
    for (const b of banned) expect(text, `banned phrase: ${b}`).not.toContain(b);
  });

  it("states the honest limits in both languages", () => {
    for (const c of [itCopy, enCopy]) {
      const all = JSON.stringify(c).toLowerCase();
      expect(all).toMatch(/notariz/);
      expect(all).toMatch(/windows/);
      expect(all).toMatch(/groq/);
      expect(all).toMatch(/ollama/);
    }
  });

  it("headlines stay short enough for two lines", () => {
    for (const c of [itCopy, enCopy]) {
      for (const h of [c.hero.l1, c.hero.l2, c.demo.title, c.screen.title, c.memory.title, c.privacy.title, c.models.title, c.download.title]) {
        expect(h.length, h).toBeLessThanOrEqual(46);
      }
    }
  });
});
