"use client";

import React, { useState } from "react";
import {
  Bot,
  Search,
  CheckCircle2,
  XCircle,
  ShieldCheck,
} from "lucide-react";
import { useLanguage } from "@/lib/i18n/context";

export function ProductDemo() {
  const { t, lang } = useLanguage();
  const [approved, setApproved] = useState<boolean | null>(null);

  return (
    <section
      id="product"
      style={{
        position: "relative",
        padding: "120px 0 100px",
        background: "var(--bg-surface-elevated)",
        borderBottom: "1px solid var(--border-subtle)",
      }}
    >
      <div className="container-wide">
        {/* Section Header */}
        <div style={{ maxWidth: 780, margin: "0 auto 50px", textAlign: "center" }}>
          <span className="section-tag">{t.productDemo.tag}</span>
          <h2 className="section-title" style={{ margin: "0 auto 16px" }}>
            {t.productDemo.title}
          </h2>
          <p className="section-desc" style={{ margin: "0 auto" }}>
            {t.productDemo.subtitle}
          </p>
        </div>

        {/* Real Product Window */}
        <div
          style={{
            background: "var(--bg-surface)",
            border: "1px solid var(--border-medium)",
            borderRadius: "var(--radius-xl)",
            overflow: "hidden",
            boxShadow: "var(--window-shadow)",
            maxWidth: 1140,
            margin: "0 auto",
          }}
        >
          {/* Top Window Bar */}
          <div
            style={{
              background: "var(--bg-surface-elevated)",
              borderBottom: "1px solid var(--border-subtle)",
              padding: "14px 20px",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 12,
              flexWrap: "wrap",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
              <div style={{ display: "flex", gap: 6, flexShrink: 0 }}>
                <span style={{ width: 10, height: 10, borderRadius: "50%", background: "#ef4444" }} />
                <span style={{ width: 10, height: 10, borderRadius: "50%", background: "#f59e0b" }} />
                <span style={{ width: 10, height: 10, borderRadius: "50%", background: "#10b981" }} />
              </div>
              <div
                style={{
                  fontSize: "0.8125rem",
                  color: "var(--text-secondary)",
                  background: "var(--bg-surface)",
                  padding: "4px 12px",
                  borderRadius: "var(--radius-sm)",
                  border: "1px solid var(--border-subtle)",
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                <span style={{ color: "var(--accent-violet)", fontWeight: 600 }}>Aether Workspace</span>
                <span style={{ color: "var(--text-muted)" }}>•</span>
                <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{t.productDemo.windowTitle}</span>
              </div>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "0.8125rem", color: "var(--text-secondary)", fontWeight: 500, flexShrink: 0 }}>
              <span className="pulse-dot" style={{ width: 6, height: 6 }} />
              <span>{t.productDemo.activeBadge}</span>
            </div>
          </div>

          {/* Main Workspace Screen Content */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1.1fr 0.9fr",
              padding: "36px 30px",
              gap: 32,
              background: "var(--bg-surface)",
            }}
            className="demo-split-grid"
          >
            {/* Left: Stream of Delegation */}
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div style={{ fontSize: "0.8125rem", fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
                {lang === "it" ? "SQUADRA AL LAVORO" : "TEAM AT WORK"}
              </div>

              {/* User Goal */}
              <div
                style={{
                  background: "var(--bg-surface-elevated)",
                  borderRadius: "var(--radius-md)",
                  padding: "16px 18px",
                  border: "1px solid var(--border-subtle)",
                }}
              >
                <span style={{ fontSize: "0.8125rem", color: "var(--accent-violet)", fontWeight: 600, display: "block", marginBottom: 4 }}>
                  {t.productDemo.userGoalTitle}
                </span>
                <div style={{ fontSize: "0.95rem", color: "var(--text-primary)", fontWeight: 500, lineHeight: 1.5 }}>
                  &ldquo;{t.productDemo.userGoalText}&rdquo;
                </div>
              </div>

              {/* Manager Step */}
              <div
                style={{
                  background: "var(--bg-surface-subtle)",
                  border: "1px solid var(--border-medium)",
                  borderRadius: "var(--radius-md)",
                  padding: "16px 18px",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                  <Bot size={18} style={{ color: "var(--accent-violet)" }} />
                  <span style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "0.9375rem" }}>
                    {t.productDemo.managerLabel}
                  </span>
                  <span style={{ fontSize: "0.8125rem", color: "var(--text-muted)", marginLeft: "auto" }}>09:41</span>
                </div>
                <p style={{ fontSize: "0.9375rem", color: "var(--text-secondary)", margin: 0, lineHeight: 1.5 }}>
                  {t.productDemo.managerText}
                </p>
              </div>

              {/* Researcher Step */}
              <div
                style={{
                  background: "var(--bg-surface-subtle)",
                  border: "1px solid var(--border-medium)",
                  borderRadius: "var(--radius-md)",
                  padding: "16px 18px",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                  <Search size={18} style={{ color: "var(--accent-emerald)" }} />
                  <span style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "0.9375rem" }}>
                    {t.productDemo.researcherLabel}
                  </span>
                  <span style={{ fontSize: "0.8125rem", color: "var(--text-muted)", marginLeft: "auto" }}>09:42</span>
                </div>
                <p style={{ fontSize: "0.9375rem", color: "var(--text-secondary)", margin: 0, lineHeight: 1.5 }}>
                  {t.productDemo.researcherText}
                </p>
              </div>
            </div>

            {/* Right: Deliverable & Sign-off */}
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <div style={{ fontSize: "0.8125rem", fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
                {lang === "it" ? "RISULTATO & APPROVAZIONE" : "DELIVERABLE & APPROVAL"}
              </div>

              <div
                style={{
                  background: "var(--bg-surface-elevated)",
                  border: "1px solid var(--border-medium)",
                  borderRadius: "var(--radius-md)",
                  padding: "24px 22px",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between",
                  height: "100%",
                }}
              >
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12, flexWrap: "wrap", gap: 8 }}>
                    <span style={{ fontWeight: 700, fontSize: "1.15rem", color: "var(--text-primary)" }}>
                      {t.productDemo.deliverableTitle}
                    </span>
                    <span className="badge-pill active" style={{ fontSize: "0.75rem" }}>
                      {t.productDemo.deliverableStatus}
                    </span>
                  </div>

                  <p style={{ fontSize: "0.9375rem", color: "var(--text-secondary)", lineHeight: 1.6, marginBottom: 20 }}>
                    {t.productDemo.deliverableDesc}
                  </p>
                </div>

                {/* Sign-off Checkpoint */}
                <div
                  style={{
                    borderTop: "1px solid var(--border-subtle)",
                    paddingTop: 16,
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "0.875rem", color: "var(--accent-amber)", fontWeight: 600, marginBottom: 12 }}>
                    <ShieldCheck size={18} />
                    <span>{t.productDemo.approvalNotice}</span>
                  </div>

                  {approved === null ? (
                    <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                      <button
                        onClick={() => setApproved(true)}
                        className="btn-primary"
                        style={{
                          background: "var(--accent-emerald)",
                          borderColor: "var(--accent-emerald)",
                          color: "#ffffff",
                          padding: "10px 20px",
                          fontSize: "0.875rem",
                          minHeight: 44,
                          flex: 1,
                        }}
                      >
                        <CheckCircle2 size={16} />
                        <span>{t.productDemo.approveBtn}</span>
                      </button>
                      <button
                        onClick={() => setApproved(false)}
                        className="btn-secondary"
                        style={{ padding: "10px 16px", fontSize: "0.875rem", minHeight: 44 }}
                      >
                        <XCircle size={16} />
                        <span>{lang === "it" ? "Modifica" : "Revise"}</span>
                      </button>
                    </div>
                  ) : approved ? (
                    <div style={{ color: "var(--accent-emerald)", fontSize: "0.9375rem", fontWeight: 600 }}>
                      {t.productDemo.approvedMsg}
                    </div>
                  ) : (
                    <div style={{ color: "var(--accent-amber)", fontSize: "0.9375rem", fontWeight: 500 }}>
                      {lang === "it" ? "La squadra sta modificando la bozza." : "Team is revising the draft."}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <style jsx>{`
        @media (max-width: 860px) {
          .demo-split-grid {
            grid-template-columns: 1fr !important;
            padding: 24px 18px !important;
            gap: 24px !important;
          }
        }
      `}</style>
    </section>
  );
}
