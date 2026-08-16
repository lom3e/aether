"use client";

import React, { createContext, useContext, useState } from "react";
import { translations } from "./translations";

export type Language = "it" | "en";

interface LanguageContextType {
  lang: Language;
  setLang: (lang: Language) => void;
  t: typeof translations.it;
}

const LanguageContext = createContext<LanguageContextType | undefined>(undefined);

function getInitialLanguage(): Language {
  if (typeof window === "undefined") return "it";
  try {
    const urlParams = new URLSearchParams(window.location.search);
    const urlLang = urlParams.get("lang") as Language | null;
    if (urlLang && (urlLang === "it" || urlLang === "en")) {
      return urlLang;
    }

    const saved = localStorage.getItem("aether_lang") as Language | null;
    if (saved && (saved === "it" || saved === "en")) {
      return saved;
    }

    return navigator.language.startsWith("it") ? "it" : "en";
  } catch {
    // ignore
  }
  return "it";
}

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Language>(getInitialLanguage);

  const setLang = (newLang: Language) => {
    setLangState(newLang);
    try {
      localStorage.setItem("aether_lang", newLang);
      const url = new URL(window.location.href);
      url.searchParams.set("lang", newLang);
      window.history.replaceState({}, "", url.toString());
    } catch {
      // ignore
    }
  };

  const t = translations[lang] || translations.it;

  return (
    <LanguageContext.Provider value={{ lang, setLang, t }}>
      {children}
    </LanguageContext.Provider>
  );
}

export function useLanguage(): LanguageContextType {
  const context = useContext(LanguageContext);
  if (!context) {
    return {
      lang: "it",
      setLang: () => {},
      t: translations.it,
    };
  }
  return context;
}
