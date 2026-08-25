"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  Users,
  Search,
  PenTool,
  ShieldCheck,
  CheckCircle2,
  LayoutDashboard,
  ArrowRight,
} from "lucide-react";
import { useLanguage } from "@/lib/i18n/context";
import { useTheme } from "@/lib/theme-context";

export function ParallaxStory() {
  const { t } = useLanguage();
  const { resolvedTheme } = useTheme();
  const [activeMomentIndex, setActiveMomentIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const isDark = resolvedTheme === "dark";
  const moments = t.story.moments;
  const activeMoment = moments[activeMomentIndex] || moments[0];

  useEffect(() => {
    const handleScroll = () => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const totalHeight = containerRef.current.scrollHeight - window.innerHeight;
      if (totalHeight <= 0) return;

      const progress = Math.max(0, Math.min(1, -rect.top / totalHeight));
      const newIndex = Math.min(moments.length - 1, Math.floor(progress * moments.length));
      setActiveMomentIndex(newIndex);
    };

    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, [moments.length]);

  return (
    <section
      id="story"
      ref={containerRef}
      style={{
        position: "relative",
        background: "var(--bg-page)",
        borderTop: "1px solid var(--border-subtle)",
        borderBottom: "1px solid var(--border-subtle)",
      }}
    >
      {/* Sticky Parallax Viewport */}
      <div
        style={{
          position: "sticky",
          top: 0,
          minHeight: "100vh",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          overflow: "hidden",
          padding: "70px 0 40px",
        }}
      >
        <div className="container-wide" style={{ height: "100%", display: "flex", flexDirection: "column" }}>
          {/* Header Bar */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: 20,
              paddingBottom: 12,
              borderBottom: "1px solid var(--border-subtle)",
            }}
          >
            <span className="section-tag" style={{ margin: 0 }}>
              {t.story.tag}
            </span>

            {/* Moment Indicator */}
            <div
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.8125rem",
                color: "var(--accent-violet)",
                background: "rgba(var(--accent-violet-rgb), 0.08)",
                padding: "4px 12px",
                borderRadius: "var(--radius-full)",
                border: "1px solid rgba(var(--accent-violet-rgb), 0.2)",
              }}
            >
              {t.story.counter} {activeMomentIndex + 1} {t.story.of} {moments.length}
            </div>
          </div>

          {/* Main 2-Column Split */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1.05fr 0.95fr",
              gap: 36,
              flex: 1,
              alignItems: "center",
            }}
            className="story-grid"
          >
            {/* Visual Stage */}
            <div
              style={{
                width: "100%",
                minHeight: 340,
                maxHeight: 520,
                background: "var(--bg-surface)",
                border: "1px solid var(--border-medium)",
                borderRadius: "var(--radius-xl)",
                position: "relative",
                overflow: "hidden",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                boxShadow: "var(--window-shadow)",
                padding: "28px 24px",
              }}
              className="visual-stage-card"
            >
              {/* Background Ambient Radial Glow */}
              <div
                style={{
                  position: "absolute",
                  inset: 0,
                  background: isDark
                    ? "radial-gradient(circle at center, rgba(139, 92, 246, 0.12) 0%, transparent 70%)"
                    : "radial-gradient(circle at center, rgba(124, 58, 237, 0.08) 0%, transparent 70%)",
                  pointerEvents: "none",
                }}
              />

              {/* MOMENT 1: Workforce Parallel Execution */}
              {activeMoment.id === 1 && (
                <div style={{ width: "100%", display: "flex", flexDirection: "column", alignItems: "center", gap: 20, zIndex: 2 }}>
                  <div style={{ display: "flex", gap: 12, alignItems: "center", justifyContent: "center", flexWrap: "wrap" }}>
                    {[
                      { name: t.hero.agents.manager.name, color: isDark ? "#8b5cf6" : "#7c3aed", icon: Users },
                      { name: t.hero.agents.researcher.name, color: isDark ? "#94a3b8" : "#475569", icon: Search },
                      { name: t.hero.agents.writer.name, color: isDark ? "#cbd5e1" : "#64748b", icon: PenTool },
                      { name: t.hero.agents.oversight.name, color: isDark ? "#f59e0b" : "#d97706", icon: ShieldCheck },
                    ].map((agent, i) => (
                      <div
                        key={agent.name}
                        style={{
                          background: "var(--bg-surface-elevated)",
                          border: `1px solid var(--border-medium)`,
                          borderRadius: "var(--radius-md)",
                          padding: "14px 10px",
                          textAlign: "center",
                          width: 105,
                          boxShadow: "var(--card-shadow)",
                          transform: `translateY(${i % 2 === 0 ? "-4px" : "4px"})`,
                          transition: "all 300ms ease",
                        }}
                      >
                        <div
                          style={{
                            width: 36,
                            height: 36,
                            borderRadius: "50%",
                            background: "var(--bg-surface)",
                            border: `1px solid ${agent.color}`,
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            margin: "0 auto 8px",
                          }}
                        >
                          <agent.icon size={18} style={{ color: agent.color }} />
                        </div>
                        <div style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)" }}>{agent.name}</div>
                      </div>
                    ))}
                  </div>

                  <div
                    style={{
                      background: "rgba(var(--accent-violet-rgb), 0.08)",
                      border: "1px solid rgba(var(--accent-violet-rgb), 0.25)",
                      borderRadius: "var(--radius-full)",
                      padding: "6px 16px",
                      fontSize: "0.8125rem",
                      color: "var(--accent-violet)",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 6,
                    }}
                  >
                    <CheckCircle2 size={15} />
                    <span>{activeMoment.summaryPill}</span>
                  </div>
                </div>
              )}

              {/* MOMENT 2: Task Delegation Flow */}
              {activeMoment.id === 2 && (
                <div style={{ width: "100%", display: "flex", flexDirection: "column", alignItems: "center", gap: 20, zIndex: 2 }}>
                  <div
                    style={{
                      background: "rgba(var(--accent-violet-rgb), 0.08)",
                      border: "1px solid rgba(var(--accent-violet-rgb), 0.25)",
                      borderRadius: "var(--radius-md)",
                      padding: "10px 16px",
                      fontSize: "0.875rem",
                      color: "var(--accent-violet)",
                      fontWeight: 600,
                      textAlign: "center",
                    }}
                  >
                    {activeMoment.flow}
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", justifyContent: "center" }}>
                    <div style={{ background: "var(--bg-surface-elevated)", border: "1px solid var(--border-medium)", borderRadius: "var(--radius-md)", padding: "12px 16px", textAlign: "center" }}>
                      <div style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "0.9375rem" }}>{t.hero.agents.researcher.name}</div>
                      <div style={{ fontSize: "0.75rem", color: "var(--accent-violet)", marginTop: 2 }}>
                        {t.hero.agents.researcher.status}
                      </div>
                    </div>

                    <ArrowRight size={18} style={{ color: "var(--accent-emerald)" }} />

                    <div style={{ background: "var(--bg-surface-elevated)", border: "1px solid var(--border-medium)", borderRadius: "var(--radius-md)", padding: "12px 16px", textAlign: "center" }}>
                      <div style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "0.9375rem" }}>{t.hero.agents.writer.name}</div>
                      <div style={{ fontSize: "0.75rem", color: "var(--accent-emerald)", marginTop: 2 }}>
                        {t.hero.agents.writer.status}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* MOMENT 3: Sovereign Control & Human Sign-off */}
              {activeMoment.id === 3 && (
                <div style={{ textAlign: "center", zIndex: 2, maxWidth: 420 }}>
                  <div
                    style={{
                      width: 64,
                      height: 64,
                      borderRadius: "16px",
                      background: "var(--bg-surface-elevated)",
                      border: "1px solid rgba(var(--accent-violet-rgb), 0.35)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      margin: "0 auto 16px",
                      boxShadow: "var(--card-shadow)",
                    }}
                  >
                    <LayoutDashboard size={32} style={{ color: "var(--accent-violet)" }} />
                  </div>
                  <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: 6 }}>
                    {activeMoment.flow}
                  </div>
                  <div style={{ fontSize: "0.9rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                    {activeMoment.subheadline}
                  </div>
                </div>
              )}
            </div>

            {/* Narrative Story Copy Card */}
            <div style={{ display: "flex", flexDirection: "column", justifyContent: "center" }}>
              <div
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.8125rem",
                  color: "var(--accent-violet)",
                  fontWeight: 700,
                  letterSpacing: "0.1em",
                  marginBottom: 10,
                }}
              >
                {activeMoment.tag}
              </div>

              <h2
                style={{
                  fontSize: "clamp(1.85rem, 3.8vw, 3rem)",
                  fontWeight: 700,
                  color: "var(--text-primary)",
                  lineHeight: 1.15,
                  letterSpacing: "-0.03em",
                  marginBottom: 14,
                  whiteSpace: "pre-line",
                }}
              >
                {activeMoment.headline}
              </h2>

              <div
                style={{
                  fontSize: "1.15rem",
                  fontWeight: 500,
                  color: "var(--accent-amber)",
                  marginBottom: 16,
                  lineHeight: 1.4,
                }}
              >
                {activeMoment.subheadline}
              </div>

              <p
                style={{
                  fontSize: "1rem",
                  color: "var(--text-secondary)",
                  lineHeight: 1.6,
                  marginBottom: 24,
                }}
              >
                {activeMoment.description}
              </p>

              {/* Moment Navigation Pills */}
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                {moments.map((m, idx) => (
                  <button
                    key={m.id}
                    onClick={() => setActiveMomentIndex(idx)}
                    style={{
                      width: activeMomentIndex === idx ? 36 : 10,
                      height: 8,
                      borderRadius: "var(--radius-full)",
                      background: activeMomentIndex === idx ? "var(--accent-violet)" : "var(--border-medium)",
                      border: "none",
                      cursor: "pointer",
                      transition: "all 300ms cubic-bezier(0.16, 1, 0.3, 1)",
                    }}
                    title={`Momento ${idx + 1}`}
                    aria-label={`Jump to moment ${idx + 1}`}
                  />
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Scroll Track */}
      <div style={{ height: "200vh" }} className="parallax-track" />

      <style jsx>{`
        @media (max-width: 860px) {
          .story-grid {
            grid-template-columns: 1fr !important;
            gap: 20px !important;
          }
          .visual-stage-card {
            min-height: 240px !important;
            max-height: 360px !important;
            padding: 16px !important;
          }
          .parallax-track {
            height: 140vh !important;
          }
        }
      `}</style>
    </section>
  );
}
