"use client";

import React from "react";
import { MessageSquare, Users, FileText, CheckCircle2 } from "lucide-react";
import { useLanguage } from "@/lib/i18n/context";

export function HowAetherWorks() {
  const { t } = useLanguage();

  const stepIcons = [MessageSquare, Users, FileText, CheckCircle2];

  return (
    <section
      id="how-it-works"
      style={{
        position: "relative",
        padding: "120px 0 100px",
        background: "var(--bg-page)",
        borderBottom: "1px solid var(--border-subtle)",
      }}
    >
      <div className="container">
        {/* Section Header */}
        <div style={{ maxWidth: 780, margin: "0 auto 60px", textAlign: "center" }}>
          <span className="section-tag">{t.howItWorks.tag}</span>
          <h2 className="section-title" style={{ margin: "0 auto 16px" }}>
            {t.howItWorks.title}
          </h2>
          <p className="section-desc" style={{ margin: "0 auto" }}>
            {t.howItWorks.subtitle}
          </p>
        </div>

        {/* 4 Clean Steps Grid */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
            gap: 24,
            maxWidth: 1140,
            margin: "0 auto",
          }}
        >
          {t.howItWorks.steps.map((step, idx) => {
            const Icon = stepIcons[idx] || MessageSquare;
            return (
              <div
                key={idx}
                className="glass-card"
                style={{
                  padding: "34px 26px",
                  display: "flex",
                  flexDirection: "column",
                  gap: 16,
                  position: "relative",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div
                    style={{
                      width: 42,
                      height: 42,
                      borderRadius: "var(--radius-sm)",
                      background: "rgba(var(--accent-violet-rgb), 0.1)",
                      border: "1px solid rgba(var(--accent-violet-rgb), 0.25)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    <Icon size={19} style={{ color: "var(--accent-violet)" }} />
                  </div>
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.8125rem",
                      fontWeight: 700,
                      color: "var(--accent-violet)",
                      background: "rgba(var(--accent-violet-rgb), 0.08)",
                      padding: "2px 8px",
                      borderRadius: "var(--radius-xs)",
                    }}
                  >
                    {step.number}
                  </span>
                </div>

                <h3
                  style={{
                    fontSize: "1.2rem",
                    fontWeight: 600,
                    color: "var(--text-primary)",
                    letterSpacing: "-0.01em",
                  }}
                >
                  {step.title}
                </h3>

                <p
                  style={{
                    fontSize: "0.95rem",
                    color: "var(--text-secondary)",
                    lineHeight: 1.6,
                    margin: 0,
                  }}
                >
                  {step.desc}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
