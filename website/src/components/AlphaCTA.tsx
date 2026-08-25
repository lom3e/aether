"use client";

import React from "react";
import { Download, Apple, Clock } from "lucide-react";
import { GithubIcon } from "@/components/icons/GithubIcon";
import { useLanguage } from "@/lib/i18n/context";
import { useGithubLatestRelease } from "@/lib/useGithubRelease";

export function AlphaCTA() {
  const { t } = useLanguage();
  const { releaseTag, releaseUrl } = useGithubLatestRelease();

  return (
    <section
      id="try"
      style={{
        position: "relative",
        padding: "130px 0 110px",
        background: "var(--bg-page)",
        borderBottom: "1px solid var(--border-subtle)",
        textAlign: "center",
      }}
    >
      <div className="container">
        <div style={{ maxWidth: 780, margin: "0 auto" }}>
          {/* Release Tag Pill */}
          <div style={{ display: "inline-flex", alignItems: "center", gap: 8, marginBottom: 16 }}>
            <a
              href={releaseUrl}
              target="_blank"
              rel="noreferrer"
              style={{ textDecoration: "none" }}
            >
              <span
                className="badge-pill active"
                style={{
                  padding: "4px 12px",
                  fontSize: "0.8125rem",
                  fontFamily: "var(--font-mono)",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                {releaseTag || t.alpha.releaseTag || "Release v1.5.0"}
              </span>
            </a>
          </div>

          <h2
            style={{
              fontSize: "clamp(2.5rem, 5.5vw, 4.25rem)",
              fontWeight: 700,
              letterSpacing: "-0.04em",
              color: "var(--text-primary)",
              lineHeight: 1.1,
              marginBottom: 18,
            }}
          >
            {t.alpha.title}
          </h2>

          <p
            style={{
              fontSize: "clamp(1.15rem, 2.2vw, 1.4rem)",
              color: "var(--text-secondary)",
              maxWidth: 620,
              margin: "0 auto 36px",
              lineHeight: 1.5,
            }}
          >
            {t.alpha.subtitle}
          </p>

          {/* Primary Action Buttons */}
          <div
            style={{
              display: "flex",
              justifyContent: "center",
              gap: 14,
              flexWrap: "wrap",
              marginBottom: 28,
            }}
          >
            {/* Direct macOS DMG Download */}
            <a
              href="https://github.com/lom3e/aether/releases/latest/download/Aether.dmg"
              target="_blank"
              rel="noopener noreferrer"
              className="btn-primary"
              style={{
                padding: "15px 32px",
                fontSize: "1.05rem",
                borderRadius: "var(--radius-sm)",
                display: "inline-flex",
                alignItems: "center",
                gap: "10px",
              }}
            >
              <Download size={18} />
              <span>{t.alpha.tryBtn}</span>
            </a>

            {/* GitHub Source Link */}
            <a
              href="https://github.com/lom3e/aether"
              target="_blank"
              rel="noopener noreferrer"
              className="btn-secondary"
              style={{
                padding: "15px 28px",
                fontSize: "1.05rem",
                borderRadius: "var(--radius-sm)",
                display: "inline-flex",
                alignItems: "center",
                gap: "10px",
              }}
            >
              <GithubIcon size={18} />
              <span>{t.alpha.githubBtn}</span>
            </a>
          </div>

          {/* Platform Status & Compatibility Strip */}
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              gap: 20,
              flexWrap: "wrap",
              padding: "10px 18px",
              background: "var(--bg-surface)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "var(--radius-md)",
              fontSize: "0.8125rem",
              color: "var(--text-secondary)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <Apple size={14} style={{ color: "var(--accent-violet)" }} />
              <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>macOS:</span>
              <span>{t.alpha.macBadge}</span>
            </div>

            <div style={{ width: 1, height: 14, background: "var(--border-subtle)" }} />

            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <Clock size={14} style={{ color: "var(--text-muted)" }} />
              <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>Windows:</span>
              <span style={{ color: "var(--text-muted)" }}>{t.alpha.windowsNotice}</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
