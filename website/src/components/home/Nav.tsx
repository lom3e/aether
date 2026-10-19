"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Menu, Moon, Sun, X } from "lucide-react";
import { useLanguage } from "@/lib/i18n/context";
import { useTheme } from "@/lib/theme-context";

export function Nav() {
  const { lang, setLang, c } = useLanguage();
  const { resolvedTheme, toggleTheme } = useTheme();
  const [solid, setSolid] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const on = () => setSolid(window.scrollY > 24);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);

  const base = `/${lang}`;
  const links = [
    { href: `${base}#demo`, label: c.nav.demo },
    { href: `${base}#screen`, label: c.nav.screen },
    { href: `${base}#memory`, label: c.nav.memory },
    { href: `${base}#teams`, label: c.nav.teams },
    { href: `${base}#privacy`, label: c.nav.privacy },
    { href: `${base}#faq`, label: c.nav.faq },
  ];
  const mark = resolvedTheme === "dark" ? "/brand/logo_bianco.svg" : "/brand/logo_nero.svg";

  return (
    <header className={`ae-nav${solid || open ? " solid" : ""}`}>
      <a className="ae-skip" href="#main">{lang === "it" ? "Vai al contenuto" : "Skip to content"}</a>
      <div className="ae-wrap ae-nav-in">
        <Link href={base} className="ae-brand" aria-label="Aether">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={mark} alt="" width={34} height={34} />
          Aether
        </Link>
        <nav className="ae-nav-links" aria-label="Principale">
          {links.map((l) => (
            <a key={l.href} href={l.href}>{l.label}</a>
          ))}
        </nav>
        <div className="ae-nav-tools">
          <button className="ae-chip" onClick={() => setLang(lang === "it" ? "en" : "it")} aria-label={lang === "it" ? "Switch to English" : "Passa all'italiano"}>
            {lang === "it" ? "EN" : "IT"}
          </button>
          <button className="ae-chip" onClick={toggleTheme} aria-label={resolvedTheme === "dark" ? "Light theme" : "Dark theme"}>
            {resolvedTheme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
          </button>
          <a className="ae-btn ae-nav-cta" style={{ minHeight: 42, padding: "0 20px", fontSize: 15 }} href={`${base}#download`}>{c.nav.download}</a>
          <button className="ae-chip ae-burger" onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-label="Menu">
            {open ? <X size={19} /> : <Menu size={19} />}
          </button>
        </div>
      </div>
      {open && (
        <div className="ae-drawer" onClick={() => setOpen(false)}>
          {links.map((l) => (
            <a key={l.href} href={l.href}>{l.label}</a>
          ))}
          <a href={`${base}#download`}>{c.nav.download}</a>
        </div>
      )}
    </header>
  );
}
