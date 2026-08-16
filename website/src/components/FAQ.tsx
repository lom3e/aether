"use client";

import React, { useState } from "react";
import { ChevronDown } from "lucide-react";
import { useLanguage } from "@/lib/i18n/context";

export function FAQ() {
  const { t } = useLanguage();
  const [openIndex, setOpenIndex] = useState<number | null>(0);

  const toggle = (index: number) => {
    setOpenIndex(openIndex === index ? null : index);
  };

  return (
    <section
      id="faq"
      style={{
        position: "relative",
        padding: "120px 0 100px",
        background: "var(--bg-page)",
        borderBottom: "1px solid var(--border-subtle)",
      }}
    >
      <div className="container-narrow">
        {/* Section Header */}
        <div style={{ textAlign: "center", maxWidth: 680, margin: "0 auto 50px" }}>
          <span className="section-tag">{t.faq.tag}</span>
          <h2 className="section-title">{t.faq.title}</h2>
          <p className="section-desc" style={{ margin: "0 auto" }}>
            {t.faq.subtitle}
          </p>
        </div>

        {/* Accordion List */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {t.faq.items.map((item, idx) => {
            const isOpen = openIndex === idx;
            return (
              <div
                key={idx}
                style={{
                  background: "var(--bg-surface)",
                  border: `1px solid ${isOpen ? "var(--border-highlight)" : "var(--border-subtle)"}`,
                  borderRadius: "var(--radius-md)",
                  overflow: "hidden",
                  boxShadow: "var(--card-shadow)",
                  transition: "all 150ms ease",
                }}
              >
                <button
                  onClick={() => toggle(idx)}
                  style={{
                    width: "100%",
                    padding: "22px 26px",
                    background: "transparent",
                    border: "none",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 16,
                    cursor: "pointer",
                    textAlign: "left",
                    color: "var(--text-primary)",
                  }}
                  aria-expanded={isOpen}
                >
                  <span style={{ fontSize: "1.08rem", fontWeight: 600 }}>{item.q}</span>
                  <ChevronDown
                    size={18}
                    style={{
                      color: isOpen ? "var(--accent-violet)" : "var(--text-muted)",
                      transform: isOpen ? "rotate(180deg)" : "rotate(0)",
                      transition: "transform 200ms ease",
                      flexShrink: 0,
                    }}
                  />
                </button>

                {isOpen && (
                  <div
                    style={{
                      padding: "0 26px 24px",
                      color: "var(--text-secondary)",
                      fontSize: "1rem",
                      lineHeight: 1.65,
                      borderTop: "1px solid var(--border-subtle)",
                      paddingTop: 16,
                    }}
                  >
                    {item.a}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
