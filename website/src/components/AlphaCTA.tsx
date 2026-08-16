"use client";

import React from "react";
import { ArrowRight } from "lucide-react";
import { GithubIcon } from "@/components/icons/GithubIcon";
import { useLanguage } from "@/lib/i18n/context";

export function AlphaCTA() {
  const { t } = useLanguage();

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
        <div style={{ maxWidth: 760, margin: "0 auto" }}>
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
              maxWidth: 580,
              margin: "0 auto 36px",
              lineHeight: 1.5,
            }}
          >
            {t.alpha.subtitle}
          </p>

          <div
            style={{
              display: "flex",
              justifyContent: "center",
              gap: 14,
              flexWrap: "wrap",
            }}
          >
            <a
              href="https://github.com/lom3e/aether/releases/tag/v1.3.0-alpha-workforce"
              target="_blank"
              rel="noopener noreferrer"
              className="btn-primary"
              style={{
                padding: "15px 36px",
                fontSize: "1.05rem",
                borderRadius: "var(--radius-sm)",
              }}
            >
              <span>{t.alpha.tryBtn}</span>
              <ArrowRight size={17} />
            </a>

            <a
              href="https://github.com/lom3e/aether"
              target="_blank"
              rel="noopener noreferrer"
              className="btn-secondary"
              style={{
                padding: "15px 28px",
                fontSize: "1.05rem",
                borderRadius: "var(--radius-sm)",
              }}
            >
              <GithubIcon size={18} />
              <span>{t.alpha.githubBtn}</span>
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}
