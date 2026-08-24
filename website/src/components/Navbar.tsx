"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { Menu, X, ArrowRight, Sun, Moon } from "lucide-react";
import { useLanguage } from "@/lib/i18n/context";
import { useActiveLogo } from "@/lib/logo-context";
import { useTheme } from "@/lib/theme-context";
import { AetherLogo } from "./AetherLogo";

export function Navbar() {
  const { lang, setLang, t } = useLanguage();
  const { activeLogo } = useActiveLogo();
  const { theme, resolvedTheme, setTheme, toggleTheme } = useTheme();
  const [scrolled, setScrolled] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const navLinks = [
    { name: t.nav.product, href: "/#product" },
    { name: t.nav.howItWorks, href: "/#how-it-works" },
    { name: t.nav.solutions, href: "/#solutions" },
    { name: t.nav.faq, href: "/#faq" },
  ];

  return (
    <header
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        zIndex: 100,
        padding: scrolled ? "12px 0" : "18px 0",
        transition: "all 200ms ease",
        background: scrolled
          ? resolvedTheme === "dark"
            ? "rgba(10, 10, 10, 0.92)"
            : "rgba(250, 250, 250, 0.92)"
          : "transparent",
        backdropFilter: scrolled ? "blur(16px)" : "none",
        WebkitBackdropFilter: scrolled ? "blur(16px)" : "none",
        borderBottom: scrolled ? "1px solid var(--border-subtle)" : "1px solid transparent",
      }}
    >
      <div className="container" style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        {/* Brand Logo */}
        <Link
          href="/"
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            textDecoration: "none",
          }}
        >
          <AetherLogo id={activeLogo} size={28} wordmarkHeight={16} priority />
          <span
            className="badge-pill active"
            style={{
              padding: "2px 7px",
              fontSize: "0.6875rem",
              fontFamily: "var(--font-mono)",
            }}
          >
            {t.nav.alphaLabel}
          </span>
        </Link>

        {/* Minimal Navigation Links for Desktop */}
        <nav
          style={{
            display: "none",
            alignItems: "center",
            gap: "28px",
          }}
          className="desktop-nav"
        >
          {navLinks.map((link) => (
            <a
              key={link.name}
              href={link.href}
              style={{
                fontSize: "0.9375rem",
                color: "var(--text-secondary)",
                fontWeight: 500,
                textDecoration: "none",
                transition: "color 150ms ease",
                whiteSpace: "nowrap",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.color = "var(--text-primary)")}
              onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-secondary)")}
            >
              {link.name}
            </a>
          ))}
        </nav>

        {/* Right Actions: Theme Toggle, Language Switcher & Primary CTA */}
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          {/* Theme Toggle Button */}
          <button
            onClick={toggleTheme}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              width: 36,
              height: 36,
              borderRadius: "var(--radius-sm)",
              background: "var(--bg-surface-subtle)",
              border: "1px solid var(--border-subtle)",
              color: "var(--text-secondary)",
              cursor: "pointer",
              transition: "all 150ms ease",
            }}
            title={resolvedTheme === "dark" ? "Switch to Light Mode" : "Switch to Dark Mode"}
            aria-label="Toggle theme"
          >
            {resolvedTheme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
          </button>

          {/* Language Switcher */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              background: "var(--bg-surface-subtle)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "var(--radius-sm)",
              padding: "2px",
              gap: 2,
            }}
          >
            <button
              onClick={() => setLang("it")}
              style={{
                background: lang === "it" ? "var(--bg-surface)" : "transparent",
                border: lang === "it" ? "1px solid var(--border-medium)" : "1px solid transparent",
                color: lang === "it" ? "var(--text-primary)" : "var(--text-secondary)",
                borderRadius: "var(--radius-xs)",
                padding: "4px 8px",
                fontSize: "0.75rem",
                fontWeight: 700,
                cursor: "pointer",
                transition: "all 150ms ease",
              }}
              title="Italiano"
            >
              IT
            </button>
            <button
              onClick={() => setLang("en")}
              style={{
                background: lang === "en" ? "var(--bg-surface)" : "transparent",
                border: lang === "en" ? "1px solid var(--border-medium)" : "1px solid transparent",
                color: lang === "en" ? "var(--text-primary)" : "var(--text-secondary)",
                borderRadius: "var(--radius-xs)",
                padding: "4px 8px",
                fontSize: "0.75rem",
                fontWeight: 700,
                cursor: "pointer",
                transition: "all 150ms ease",
              }}
              title="English"
            >
              EN
            </button>
          </div>

          <a
            href="#try"
            className="btn-primary desktop-cta"
            style={{
              padding: "8px 16px",
              fontSize: "0.875rem",
              minHeight: 36,
              borderRadius: "var(--radius-sm)",
              display: "inline-flex",
              alignItems: "center",
              gap: "6px",
            }}
          >
            <span>{t.nav.tryAether}</span>
            <ArrowRight size={14} />
          </a>

          {/* Mobile Menu Trigger */}
          <button
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            style={{
              display: "none",
              background: "transparent",
              border: "none",
              color: "var(--text-primary)",
              cursor: "pointer",
              padding: "6px",
            }}
            className="mobile-menu-btn"
            aria-label="Toggle navigation menu"
          >
            {mobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
          </button>
        </div>
      </div>

      {/* Mobile Drawer */}
      {mobileMenuOpen && (
        <div
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            right: 0,
            background: "var(--bg-page)",
            borderBottom: "1px solid var(--border-subtle)",
            boxShadow: "var(--card-shadow)",
            padding: "20px 24px",
            display: "flex",
            flexDirection: "column",
            gap: "14px",
          }}
        >
          {navLinks.map((link) => (
            <a
              key={link.name}
              href={link.href}
              onClick={() => setMobileMenuOpen(false)}
              style={{
                fontSize: "1.05rem",
                color: "var(--text-primary)",
                fontWeight: 500,
                textDecoration: "none",
                padding: "8px 0",
                borderBottom: "1px solid var(--border-subtle)",
              }}
            >
              {link.name}
            </a>
          ))}

          {/* Mobile Controls Line */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 0" }}>
            <span style={{ fontSize: "0.9375rem", color: "var(--text-secondary)" }}>Tema / Theme</span>
            <div style={{ display: "flex", gap: 6 }}>
              <button
                onClick={() => setTheme("light")}
                style={{
                  background: theme === "light" ? "var(--accent-violet)" : "var(--bg-surface-subtle)",
                  color: theme === "light" ? "#ffffff" : "var(--text-secondary)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-xs)",
                  padding: "6px 12px",
                  fontSize: "0.75rem",
                  fontWeight: 600,
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: 4,
                  minHeight: 36,
                }}
              >
                <Sun size={13} />
                <span>Light</span>
              </button>
              <button
                onClick={() => setTheme("dark")}
                style={{
                  background: theme === "dark" ? "var(--accent-violet)" : "var(--bg-surface-subtle)",
                  color: theme === "dark" ? "#ffffff" : "var(--text-secondary)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-xs)",
                  padding: "6px 12px",
                  fontSize: "0.75rem",
                  fontWeight: 600,
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: 4,
                  minHeight: 36,
                }}
              >
                <Moon size={13} />
                <span>Dark</span>
              </button>
            </div>
          </div>

          <a
            href="#try"
            onClick={() => setMobileMenuOpen(false)}
            className="btn-primary"
            style={{ width: "100%", justifyContent: "center", marginTop: 6 }}
          >
            <span>{t.nav.tryAether}</span>
            <ArrowRight size={15} />
          </a>
        </div>
      )}

      <style jsx>{`
        @media (min-width: 960px) {
          .desktop-nav {
            display: flex !important;
          }
          .desktop-cta {
            display: inline-flex !important;
          }
          .mobile-menu-btn {
            display: none !important;
          }
        }
        @media (max-width: 959px) {
          .desktop-nav {
            display: none !important;
          }
          .desktop-cta {
            display: none !important;
          }
          .mobile-menu-btn {
            display: block !important;
          }
        }
      `}</style>
    </header>
  );
}
