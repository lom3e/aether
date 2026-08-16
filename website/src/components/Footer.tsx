"use client";

import React from "react";
import Link from "next/link";
import { GithubIcon } from "@/components/icons/GithubIcon";
import { useLanguage } from "@/lib/i18n/context";
import { useActiveLogo } from "@/lib/logo-context";
import { AetherLogo } from "./AetherLogo";

export function Footer() {
  const { t } = useLanguage();
  const { activeLogo } = useActiveLogo();

  return (
    <footer
      style={{
        background: "var(--bg-surface)",
        borderTop: "1px solid var(--border-subtle)",
        padding: "70px 0 40px",
        color: "var(--text-secondary)",
        fontSize: "0.9375rem",
      }}
    >
      <div className="container">
        {/* Top Brand & Navigation Line */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            flexWrap: "wrap",
            gap: 36,
            marginBottom: 44,
          }}
        >
          {/* Brand Info */}
          <div>
            <div style={{ marginBottom: 14 }}>
              <AetherLogo id={activeLogo} size={26} wordmarkHeight={15} />
            </div>
            <p
              style={{
                color: "var(--text-secondary)",
                lineHeight: 1.6,
                maxWidth: 360,
                marginBottom: 16,
                fontSize: "0.9375rem",
              }}
            >
              {t.footer.desc}
            </p>
            <div style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>
              {t.footer.mit}
            </div>
          </div>

          {/* Links */}
          <div
            style={{
              display: "flex",
              gap: 28,
              flexWrap: "wrap",
              alignItems: "center",
            }}
          >
            <Link
              href="/#product"
              style={{ color: "var(--text-secondary)", textDecoration: "none", transition: "color 150ms ease" }}
              onMouseEnter={(e) => (e.currentTarget.style.color = "var(--text-primary)")}
              onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-secondary)")}
            >
              {t.footer.links.product}
            </Link>
            <Link
              href="/#how-it-works"
              style={{ color: "var(--text-secondary)", textDecoration: "none", transition: "color 150ms ease" }}
              onMouseEnter={(e) => (e.currentTarget.style.color = "var(--text-primary)")}
              onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-secondary)")}
            >
              {t.footer.links.howItWorks}
            </Link>
            <Link
              href="/#solutions"
              style={{ color: "var(--text-secondary)", textDecoration: "none", transition: "color 150ms ease" }}
              onMouseEnter={(e) => (e.currentTarget.style.color = "var(--text-primary)")}
              onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-secondary)")}
            >
              {t.footer.links.solutions}
            </Link>
            <Link
              href="/#faq"
              style={{ color: "var(--text-secondary)", textDecoration: "none", transition: "color 150ms ease" }}
              onMouseEnter={(e) => (e.currentTarget.style.color = "var(--text-primary)")}
              onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-secondary)")}
            >
              {t.footer.links.faq}
            </Link>
            <Link
              href="/builders"
              style={{ color: "var(--text-secondary)", textDecoration: "none", transition: "color 150ms ease" }}
              onMouseEnter={(e) => (e.currentTarget.style.color = "var(--text-primary)")}
              onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-secondary)")}
            >
              {t.footer.links.builders}
            </Link>
            <Link
              href="/about"
              style={{ color: "var(--text-secondary)", textDecoration: "none", transition: "color 150ms ease" }}
              onMouseEnter={(e) => (e.currentTarget.style.color = "var(--text-primary)")}
              onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-secondary)")}
            >
              {t.footer.links.about}
            </Link>
            <a
              href="https://github.com/lom3e/aether"
              target="_blank"
              rel="noopener noreferrer"
              style={{
                color: "var(--text-secondary)",
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                textDecoration: "none",
                transition: "color 150ms ease",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.color = "var(--text-primary)")}
              onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-secondary)")}
            >
              <GithubIcon size={15} />
              <span>GitHub</span>
            </a>
          </div>
        </div>

        {/* Bottom Attribution Line with LMLabs */}
        <div
          style={{
            borderTop: "1px solid var(--border-subtle)",
            paddingTop: 24,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: 16,
            fontSize: "0.875rem",
            color: "var(--text-muted)",
          }}
        >
          <div>
            {t.footer.copy}
          </div>

          <div>
            <a
              href={t.footer.lmlabsUrl}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                color: "var(--accent-violet)",
                textDecoration: "none",
                fontWeight: 600,
                transition: "opacity 150ms ease",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.opacity = "0.8")}
              onMouseLeave={(e) => (e.currentTarget.style.opacity = "1")}
            >
              {t.footer.builtBy}
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
}
