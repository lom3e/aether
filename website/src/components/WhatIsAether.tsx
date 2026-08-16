"use client";

import React from "react";
import { Users, FileText, ShieldCheck } from "lucide-react";
import { useLanguage } from "@/lib/i18n/context";

export function WhatIsAether() {
  const { t } = useLanguage();

  const icons = [Users, FileText, ShieldCheck];

  return (
    <section
      id="what-is-aether"
      style={{
        position: "relative",
        padding: "120px 0 100px",
        background: "var(--bg-page)",
        borderBottom: "1px solid var(--border-subtle)",
      }}
    >
      <div className="container">
        {/* Section Header */}
        <div style={{ maxWidth: 800, margin: "0 auto 60px", textAlign: "center" }}>
          <span className="section-tag">{t.whatIsAether.tag}</span>
          <h2 className="section-title" style={{ margin: "0 auto 16px" }}>
            {t.whatIsAether.title}
          </h2>
          <p className="section-desc" style={{ margin: "0 auto" }}>
            {t.whatIsAether.subtitle}
          </p>
        </div>

        {/* 3 Core Pillars */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
            gap: 28,
            maxWidth: 1060,
            margin: "0 auto",
          }}
        >
          {t.whatIsAether.pillars.map((pillar, idx) => {
            const Icon = icons[idx] || Users;
            return (
              <div
                key={idx}
                className="glass-card"
                style={{
                  padding: "36px 28px",
                  display: "flex",
                  flexDirection: "column",
                  gap: 16,
                }}
              >
                <div
                  style={{
                    width: 46,
                    height: 46,
                    borderRadius: "var(--radius-sm)",
                    background: "rgba(var(--accent-violet-rgb), 0.1)",
                    border: "1px solid rgba(var(--accent-violet-rgb), 0.25)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <Icon size={22} style={{ color: "var(--accent-violet)" }} />
                </div>

                <h3
                  style={{
                    fontSize: "1.3rem",
                    fontWeight: 600,
                    color: "var(--text-primary)",
                    letterSpacing: "-0.02em",
                  }}
                >
                  {pillar.title}
                </h3>

                <p
                  style={{
                    fontSize: "0.9875rem",
                    color: "var(--text-secondary)",
                    lineHeight: 1.6,
                    margin: 0,
                  }}
                >
                  {pillar.desc}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
