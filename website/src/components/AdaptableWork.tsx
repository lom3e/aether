"use client";

import React, { useState } from "react";
import {
  FileText,
  Code,
  Calendar,
  Mail,
  Search,
  BarChart3,
  PenTool,
  Sliders,
  Users,
  CheckCircle2,
  ChevronRight,
  Sparkles,
} from "lucide-react";
import { useLanguage } from "@/lib/i18n/context";

export function AdaptableWork() {
  const { t } = useLanguage();
  const [selectedId, setSelectedId] = useState("docs");

  const iconMap: Record<string, React.ComponentType<{ size?: number; style?: React.CSSProperties; className?: string }>> = {
    FileText,
    Code,
    Calendar,
    Mail,
    Search,
    BarChart3,
    PenTool,
    Sliders,
  };

  const categories = t.forWork.categories;
  const activeCategory = categories.find((c) => c.id === selectedId) || categories[0];
  const ActiveIcon = iconMap[activeCategory.iconName] || FileText;

  return (
    <section
      id="solutions"
      style={{
        position: "relative",
        padding: "120px 0 100px",
        background: "var(--bg-page)",
        borderBottom: "1px solid var(--border-subtle)",
      }}
    >
      <div className="container">
        {/* Section Header */}
        <div style={{ maxWidth: 820, margin: "0 auto 60px", textAlign: "center" }}>
          <span className="section-tag">{t.forWork.tag}</span>
          <h2 className="section-title" style={{ margin: "0 auto 16px" }}>
            {t.forWork.title}
          </h2>
          <p className="section-desc" style={{ margin: "0 auto" }}>
            {t.forWork.subtitle}
          </p>
        </div>

        {/* Master-Detail Layout */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "320px 1fr",
            gap: 32,
            alignItems: "start",
          }}
          className="adaptable-grid"
        >
          {/* Left Column: Vertical Interactive Directory */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 8,
            }}
            className="adaptable-list"
          >
            {categories.map((cat) => {
              const Icon = iconMap[cat.iconName] || FileText;
              const isSelected = selectedId === cat.id;

              return (
                <button
                  key={cat.id}
                  onClick={() => setSelectedId(cat.id)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    width: "100%",
                    minHeight: 52,
                    padding: "12px 18px",
                    borderRadius: "var(--radius-md)",
                    background: isSelected ? "var(--bg-surface-elevated)" : "var(--bg-surface)",
                    border: `1px solid ${isSelected ? "var(--accent-violet)" : "var(--border-subtle)"}`,
                    color: isSelected ? "var(--text-primary)" : "var(--text-secondary)",
                    cursor: "pointer",
                    textAlign: "left",
                    transition: "transform 200ms cubic-bezier(0.16, 1, 0.3, 1), border-color 150ms ease, background-color 150ms ease",
                    boxShadow: isSelected ? "var(--card-shadow)" : "none",
                  }}
                  aria-pressed={isSelected}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <div
                      style={{
                        width: 32,
                        height: 32,
                        borderRadius: "var(--radius-xs)",
                        background: isSelected ? "rgba(var(--accent-violet-rgb), 0.15)" : "var(--bg-surface-subtle)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        color: isSelected ? "var(--accent-violet)" : "var(--text-muted)",
                        flexShrink: 0,
                      }}
                    >
                      <Icon size={17} />
                    </div>
                    <span style={{ fontSize: "0.95rem", fontWeight: isSelected ? 600 : 450 }}>
                      {cat.title}
                    </span>
                  </div>

                  <ChevronRight
                    size={16}
                    style={{
                      color: isSelected ? "var(--accent-violet)" : "var(--text-muted)",
                      transform: isSelected ? "translateX(2px)" : "translateX(0)",
                      transition: "transform 150ms ease",
                    }}
                  />
                </button>
              );
            })}
          </div>

          {/* Right Column: Dynamic Detail Panel */}
          <div
            className="glass-card"
            style={{
              padding: "44px 40px",
              border: "1px solid var(--border-medium)",
              display: "flex",
              flexDirection: "column",
              gap: 28,
              minHeight: 460,
            }}
          >
            {/* Top Category Badge & Headline */}
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 14, flexWrap: "wrap" }}>
                <span className="badge-pill active">
                  <ActiveIcon size={14} />
                  <span>{activeCategory.title}</span>
                </span>
                <span className="badge-pill" style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>
                  {activeCategory.badge}
                </span>
              </div>

              <h3
                style={{
                  fontSize: "clamp(1.4rem, 2.5vw, 1.85rem)",
                  fontWeight: 700,
                  color: "var(--text-primary)",
                  letterSpacing: "-0.03em",
                  lineHeight: 1.25,
                  marginBottom: 16,
                }}
              >
                {activeCategory.headline}
              </h3>

              <p
                style={{
                  fontSize: "1.0625rem",
                  color: "var(--text-secondary)",
                  lineHeight: 1.65,
                  margin: 0,
                }}
              >
                {activeCategory.desc}
              </p>
            </div>

            {/* Team Breakdown Box */}
            <div
              style={{
                background: "var(--bg-surface-elevated)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "var(--radius-md)",
                padding: "24px 22px",
                display: "flex",
                flexDirection: "column",
                gap: 14,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "0.8125rem", fontWeight: 700, color: "var(--accent-violet)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
                <Users size={16} />
                <span>{activeCategory.teamTitle}</span>
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {activeCategory.teamMembers.map((member: { name: string; role: string }, idx: number) => (
                  <div
                    key={idx}
                    style={{
                      display: "flex",
                      alignItems: "flex-start",
                      gap: 10,
                      fontSize: "0.9375rem",
                    }}
                  >
                    <CheckCircle2 size={16} style={{ color: "var(--accent-emerald)", marginTop: 3, flexShrink: 0 }} />
                    <div>
                      <strong style={{ color: "var(--text-primary)", fontWeight: 600 }}>{member.name}:</strong>{" "}
                      <span style={{ color: "var(--text-secondary)" }}>{member.role}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Transparent Framing Note */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                fontSize: "0.8125rem",
                color: "var(--text-muted)",
                fontFamily: "var(--font-sans)",
                borderTop: "1px solid var(--border-subtle)",
                paddingTop: 16,
              }}
            >
              <Sparkles size={14} style={{ color: "var(--accent-violet)" }} />
              <span>{activeCategory.framingNote}</span>
            </div>
          </div>
        </div>
      </div>

      <style jsx>{`
        @media (max-width: 860px) {
          .adaptable-grid {
            grid-template-columns: 1fr !important;
            gap: 20px !important;
          }
          .adaptable-list {
            display: grid !important;
            grid-template-columns: 1fr 1fr !important;
            gap: 8px !important;
          }
        }
        @media (max-width: 540px) {
          .adaptable-list {
            grid-template-columns: 1fr !important;
          }
        }
      `}</style>
    </section>
  );
}
