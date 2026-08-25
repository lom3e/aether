"use client";

import React, { useState, useEffect, useRef } from "react";
import {
  Sparkles,
  Users,
  Search,
  PenTool,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  Cpu,
  FileText,
  Lock,
  ArrowRight,
  RefreshCw,
  Layers,
  ChevronDown,
} from "lucide-react";
import { useLanguage } from "@/lib/i18n/context";
import { useTheme } from "@/lib/theme-context";

export function ParallaxStoryV2() {
  const { t, lang } = useLanguage();
  const { resolvedTheme } = useTheme();
  const [activeIdx, setActiveIdx] = useState(0);
  const [approvedState, setApprovedState] = useState<boolean | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const isDark = resolvedTheme === "dark";
  const moments = t.storyV2?.moments || [];
  const current = moments[activeIdx] || moments[0];

  useEffect(() => {
    const handleScroll = () => {
      if (!containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const totalHeight = containerRef.current.scrollHeight - window.innerHeight;
      if (totalHeight <= 0) return;

      const progress = Math.max(0, Math.min(1, -rect.top / totalHeight));
      const newIndex = Math.min(moments.length - 1, Math.floor(progress * moments.length));
      setActiveIdx(newIndex);
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
        minHeight: "350vh",
      }}
    >
      {/* Sticky Parallax Container */}
      <div
        style={{
          position: "sticky",
          top: 0,
          minHeight: "100vh",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          overflow: "hidden",
          padding: "80px 0 40px",
        }}
      >
        <div className="container-wide" style={{ height: "100%", display: "flex", flexDirection: "column" }}>
          {/* Header Bar with Progress Indicator */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: 24,
              paddingBottom: 12,
              borderBottom: "1px solid var(--border-subtle)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span className="section-tag" style={{ margin: 0 }}>
                {t.storyV2.tag}
              </span>
            </div>

            {/* Step Pills */}
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {moments.map((m: any, idx: number) => {
                const active = idx === activeIdx;
                return (
                  <button
                    key={m.id}
                    onClick={() => setActiveIdx(idx)}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 6,
                      padding: "4px 12px",
                      borderRadius: "var(--radius-full)",
                      background: active ? "var(--accent-violet)" : "var(--bg-surface-elevated)",
                      color: active ? "#ffffff" : "var(--text-secondary)",
                      border: active ? "1px solid var(--accent-violet)" : "1px solid var(--border-subtle)",
                      fontSize: "0.75rem",
                      fontWeight: active ? 700 : 500,
                      cursor: "pointer",
                      transition: "all 150ms ease",
                    }}
                  >
                    <span>{idx + 1}</span>
                    <span className="hide-mobile" style={{ fontSize: "0.6875rem" }}>
                      {idx === 0 ? "Limite" : idx === 1 ? "Auto-Architect" : idx === 2 ? "Knowledge" : "Controllo"}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Main 2-Column Split */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1.1fr 0.9fr",
              gap: 40,
              flex: 1,
              alignItems: "center",
            }}
            className="story-grid"
          >
            {/* Visual Stage Card (Rich interactive graphic) */}
            <div
              style={{
                width: "100%",
                minHeight: 400,
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
            >
              {/* MOMENT 1: Single Chatbot vs Distributed Workforce */}
              {activeIdx === 0 && (
                <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: 16, zIndex: 2 }}>
                  <div
                    style={{
                      background: "rgba(244, 63, 94, 0.06)",
                      border: "1px solid rgba(244, 63, 94, 0.25)",
                      borderRadius: "var(--radius-md)",
                      padding: "16px 18px",
                      display: "flex",
                      flexDirection: "column",
                      gap: 8,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 6, color: "#e11d48", fontWeight: 700, fontSize: "0.8125rem" }}>
                        <AlertTriangle size={15} />
                        <span>Chatbot Singolo Tradizionale</span>
                      </div>
                      <span style={{ fontSize: "0.6875rem", color: "#e11d48", fontWeight: 600 }}>Contesto Saturo (98%)</span>
                    </div>
                    <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: 0, lineHeight: 1.4 }}>
                      &ldquo;Fai ricerca su 10 competitor, scrivi l&apos;architettura e prepara il codice con i test.&rdquo; → Risposta generica e allucinazioni.
                    </p>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", justifyContent: "center", color: "var(--accent-violet)", fontWeight: 700, fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                    <span>↓ Con Aether: Squadra Distribuita ↓</span>
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
                    {[
                      { role: "Strategy Lead", tool: "Claude 3.7", icon: "👑" },
                      { role: "Market Analyst", tool: "DeepSeek-R1", icon: "🔍" },
                      { role: "Full-Stack Dev", tool: "Qwen 2.5 Coder", icon: "⚙️" },
                      { role: "QA Engineer", tool: "Local Ollama", icon: "🛡️" },
                    ].map((sp, i) => (
                      <div
                        key={i}
                        style={{
                          background: "var(--bg-surface-elevated)",
                          border: "1px solid var(--border-medium)",
                          borderRadius: "var(--radius-sm)",
                          padding: "10px 12px",
                          display: "flex",
                          alignItems: "center",
                          gap: 8,
                        }}
                      >
                        <span style={{ fontSize: "1rem" }}>{sp.icon}</span>
                        <div>
                          <div style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)" }}>{sp.role}</div>
                          <div style={{ fontSize: "0.6875rem", color: "var(--accent-violet)", fontFamily: "var(--font-mono)" }}>{sp.tool}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* MOMENT 2: AI Workforce Auto-Architect */}
              {activeIdx === 1 && (
                <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: 16, zIndex: 2 }}>
                  <div
                    style={{
                      background: "var(--bg-surface-elevated)",
                      border: "1px solid var(--border-medium)",
                      borderRadius: "var(--radius-md)",
                      padding: "16px 18px",
                    }}
                  >
                    <div style={{ fontSize: "0.6875rem", color: "var(--text-muted)", fontWeight: 700, textTransform: "uppercase", marginBottom: 4 }}>
                      Input Utente
                    </div>
                    <div style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)" }}>
                      &ldquo;Voglio un audit di sicurezza sui contratti dei fornitori con calcolo delle penali.&rdquo;
                    </div>
                  </div>

                  <div
                    style={{
                      background: "linear-gradient(135deg, rgba(124, 58, 237, 0.12) 0%, rgba(59, 130, 246, 0.06) 100%)",
                      border: "1px solid rgba(124, 58, 237, 0.3)",
                      borderRadius: "var(--radius-md)",
                      padding: "18px 20px",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 6, color: "var(--accent-violet)", fontWeight: 700, fontSize: "0.8125rem" }}>
                        <Sparkles size={15} />
                        <span>Auto-Architect Blueprint</span>
                      </div>
                      <span style={{ fontSize: "0.6875rem", color: "var(--accent-emerald)", fontWeight: 600 }}>Sintesi in 1.1s ✓</span>
                    </div>

                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", display: "flex", alignItems: "center", gap: 6 }}>
                        <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--accent-violet)" }} />
                        <span>Creato team con 3 agenti specializzati e isolamento memoria</span>
                      </div>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", display: "flex", alignItems: "center", gap: 6 }}>
                        <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--accent-violet)" }} />
                        <span>Assegnato parser PDF e calcolatore penali deterministico</span>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* MOMENT 3: Private Knowledge Base */}
              {activeIdx === 2 && (
                <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: 16, zIndex: 2 }}>
                  <div
                    style={{
                      background: "var(--bg-surface-elevated)",
                      border: "1px solid var(--border-medium)",
                      borderRadius: "var(--radius-md)",
                      padding: "18px 20px",
                      display: "flex",
                      flexDirection: "column",
                      gap: 12,
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <Lock size={16} style={{ color: "var(--accent-emerald)" }} />
                        <span style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-primary)" }}>Local Knowledge Vault</span>
                      </div>
                      <span style={{ fontSize: "0.6875rem", padding: "2px 8px", borderRadius: 4, background: "rgba(16, 185, 129, 0.1)", color: "var(--accent-emerald)", fontWeight: 600 }}>
                        100% Offline
                      </span>
                    </div>

                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      {["contratto_fornitura_2026.pdf (14 pagine)", "bilancio_consolidato_q4.xlsx", "policy_sicurezza_aziendale.md"].map((doc, i) => (
                        <div
                          key={i}
                          style={{
                            background: "var(--bg-surface)",
                            border: "1px solid var(--border-subtle)",
                            borderRadius: "var(--radius-xs)",
                            padding: "8px 12px",
                            fontSize: "0.75rem",
                            color: "var(--text-primary)",
                            display: "flex",
                            alignItems: "center",
                            gap: 8,
                          }}
                        >
                          <FileText size={13} style={{ color: "var(--text-muted)" }} />
                          <span>{doc}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div
                    style={{
                      background: "rgba(16, 185, 129, 0.08)",
                      border: "1px solid rgba(16, 185, 129, 0.2)",
                      borderRadius: "var(--radius-sm)",
                      padding: "10px 14px",
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      fontSize: "0.75rem",
                      color: "var(--accent-emerald)",
                      fontWeight: 600,
                    }}
                  >
                    <CheckCircle2 size={15} />
                    <span>Nessun dato o documento inviato a server esterni.</span>
                  </div>
                </div>
              )}

              {/* MOMENT 4: Sovereign Human in the Loop */}
              {activeIdx === 3 && (
                <div style={{ width: "100%", display: "flex", flexDirection: "column", gap: 16, zIndex: 2 }}>
                  <div
                    style={{
                      background: "var(--bg-surface-elevated)",
                      border: "1px solid var(--border-medium)",
                      borderRadius: "var(--radius-md)",
                      padding: "18px 20px",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                      <ShieldCheck size={18} style={{ color: "var(--accent-amber)" }} />
                      <span style={{ fontSize: "0.875rem", fontWeight: 700, color: "var(--text-primary)" }}>Checkpoint di Controllo Richiesto</span>
                    </div>
                    <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: 0, marginBottom: 14 }}>
                      Il team ha completato l&apos;analisi e redatto il documento finale. Confermi la pubblicazione?
                    </p>

                    <div style={{ display: "flex", gap: 10 }}>
                      <button
                        onClick={() => setApprovedState(true)}
                        style={{
                          background: approvedState === true ? "var(--accent-emerald)" : "var(--bg-surface)",
                          color: approvedState === true ? "#ffffff" : "var(--text-primary)",
                          border: approvedState === true ? "1px solid var(--accent-emerald)" : "1px solid var(--border-medium)",
                          padding: "8px 16px",
                          borderRadius: "var(--radius-sm)",
                          fontSize: "0.8125rem",
                          fontWeight: 600,
                          cursor: "pointer",
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 6,
                        }}
                      >
                        <CheckCircle2 size={14} />
                        <span>Approva Deliverable</span>
                      </button>

                      <button
                        onClick={() => setApprovedState(false)}
                        style={{
                          background: approvedState === false ? "rgba(245, 158, 11, 0.1)" : "var(--bg-surface)",
                          color: approvedState === false ? "var(--accent-amber)" : "var(--text-secondary)",
                          border: approvedState === false ? "1px solid var(--accent-amber)" : "1px solid var(--border-subtle)",
                          padding: "8px 14px",
                          borderRadius: "var(--radius-sm)",
                          fontSize: "0.8125rem",
                          fontWeight: 500,
                          cursor: "pointer",
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 6,
                        }}
                      >
                        <RefreshCw size={13} />
                        <span>Chiedi Modifiche</span>
                      </button>
                    </div>

                    {approvedState !== null && (
                      <div style={{ marginTop: 10, fontSize: "0.75rem", fontWeight: 600, color: approvedState ? "var(--accent-emerald)" : "var(--accent-amber)" }}>
                        {approvedState ? "✓ Documento approvato ed esportato con successo!" : "ℹ️ Feedback inviato alla squadra per la revisione."}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Narrative Explanation Column */}
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div
                style={{
                  fontSize: "0.75rem",
                  fontWeight: 700,
                  color: "var(--accent-violet)",
                  letterSpacing: "0.06em",
                  textTransform: "uppercase",
                }}
              >
                {current.tag}
              </div>

              <h2
                style={{
                  fontSize: "clamp(1.75rem, 3.2vw, 2.4rem)",
                  fontWeight: 800,
                  color: "var(--text-primary)",
                  letterSpacing: "-0.02em",
                  lineHeight: 1.2,
                  margin: 0,
                  whiteSpace: "pre-line",
                }}
              >
                {current.headline}
              </h2>

              <p
                style={{
                  fontSize: "1.05rem",
                  fontWeight: 600,
                  color: "var(--text-primary)",
                  lineHeight: 1.5,
                  margin: 0,
                }}
              >
                {current.subheadline}
              </p>

              <p
                style={{
                  fontSize: "0.9375rem",
                  color: "var(--text-secondary)",
                  lineHeight: 1.6,
                  margin: 0,
                }}
              >
                {current.description}
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
