"use client";

import React, { createContext, useContext } from "react";
import { usePathname, useRouter } from "next/navigation";
import { translations } from "./translations";
import { copy, type Copy, type Lang } from "@/content/home";

export type Language = Lang;

interface LanguageContextType {
  lang: Language;
  setLang: (lang: Language) => void;
  /** Cookie-banner strings. */
  t: (typeof translations)["it"];
  /** Site copy for the active language. */
  c: Copy;
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

/** The language comes from the route (/it, /en): crawlers and people see the same thing. */
export function LanguageProvider({ lang, children }: { lang: Language; children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();

  const setLang = (next: Language) => {
    if (next === lang) return;
    try {
      localStorage.setItem("aether_lang", next);
    } catch {
      // ignore
    }
    const rest = pathname.replace(/^\/(it|en)(?=\/|$)/, "");
    router.push(`/${next}${rest || ""}`);
  };

  return (
    <LanguageContext.Provider value={{ lang, setLang, t: translations[lang], c: copy[lang] }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage(): LanguageContextType {
  const context = useContext(LanguageContext);
  if (!context) return { lang: "it", setLang: () => {}, t: translations.it, c: copy.it };
  return context;
}
