"use client";

import React, { useState } from "react";
import Link from "next/link";
import { Terminal, Copy, Check, ExternalLink, ArrowLeft } from "lucide-react";
import { GithubIcon } from "@/components/icons/GithubIcon";
import { Navbar } from "@/components/Navbar";
import { Footer } from "@/components/Footer";
import { useLanguage } from "@/lib/i18n/context";

type TabType = "python" | "yaml" | "cli";

export default function BuildersPage() {
  const { lang } = useLanguage();
  const [activeTab, setActiveTab] = useState<TabType>("python");
  const [copied, setCopied] = useState(false);

  const commandText = 'pip install "git+https://github.com/lom3e/aether.git" && aether ui';

  const copyCmd = () => {
    navigator.clipboard.writeText(commandText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <main style={{ minHeight: "100vh", position: "relative", background: "var(--bg-page)" }}>
      <Navbar />

      <section style={{ padding: "140px 0 100px" }}>
        <div className="container">
          {/* Breadcrumb / Back Link */}
          <div style={{ marginBottom: 32 }}>
            <Link
              href="/"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                color: "var(--text-secondary)",
                textDecoration: "none",
                fontSize: "0.875rem",
                fontWeight: 500,
              }}
            >
              <ArrowLeft size={16} />
              <span>{lang === "it" ? "Torna alla Home" : "Back to Home"}</span>
            </Link>
          </div>

          {/* Section Header */}
          <div style={{ maxWidth: 780, marginBottom: 50 }}>
            <span className="section-tag">{lang === "it" ? "PER SVILUPPATORI" : "FOR BUILDERS"}</span>
            <h1 className="section-title">
              {lang === "it" ? "Costruisci collaboratori e skill in Python." : "Build AI workers and skills in Python."}
            </h1>
            <p className="section-desc">
              {lang === "it"
                ? "Aether offre un'architettura modulare in Python con supporto nativo per specifiche YAML, integrazioni con Ollama e strumenti personalizzati."
                : "Aether provides a modular Python runtime with native YAML specs, local Ollama integration, and custom tool authoring."}
            </p>
          </div>

          {/* Quickstart Terminal Card */}
          <div
            style={{
              maxWidth: 780,
              background: "var(--bg-surface)",
              border: "1px solid var(--border-medium)",
              borderRadius: "var(--radius-md)",
              padding: "16px 22px",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 16,
              boxShadow: "var(--card-shadow)",
              marginBottom: 40,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 12, fontFamily: "var(--font-mono)", fontSize: "0.875rem", overflow: "hidden" }}>
              <Terminal size={18} style={{ color: "var(--accent-violet)", flexShrink: 0 }} />
              <span style={{ color: "var(--accent-violet)", userSelect: "none" }}>$</span>
              <span style={{ color: "var(--text-primary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {commandText}
              </span>
            </div>

            <button
              onClick={copyCmd}
              style={{
                background: copied ? "rgba(16, 185, 129, 0.15)" : "var(--bg-surface-subtle)",
                border: copied ? "1px solid var(--accent-emerald)" : "1px solid var(--border-subtle)",
                color: copied ? "var(--accent-emerald)" : "var(--text-secondary)",
                borderRadius: "var(--radius-xs)",
                padding: "6px 14px",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: 6,
                fontSize: "0.8125rem",
                fontFamily: "var(--font-mono)",
                flexShrink: 0,
              }}
            >
              {copied ? <Check size={14} /> : <Copy size={14} />}
              <span>{copied ? (lang === "it" ? "Copiato" : "Copied") : (lang === "it" ? "Copia" : "Copy")}</span>
            </button>
          </div>

          {/* Code Snippet Studio */}
          <div
            style={{
              background: "var(--bg-surface)",
              border: "1px solid var(--border-medium)",
              borderRadius: "var(--radius-lg)",
              overflow: "hidden",
              boxShadow: "var(--window-shadow)",
              marginBottom: 48,
              maxWidth: 900,
            }}
          >
            {/* Tabs */}
            <div
              style={{
                background: "var(--bg-surface-elevated)",
                borderBottom: "1px solid var(--border-subtle)",
                padding: "10px 18px",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <div style={{ display: "flex", gap: 8 }}>
                {[
                  { id: "python" as TabType, label: "Python SDK" },
                  { id: "yaml" as TabType, label: "YAML Manifest" },
                  { id: "cli" as TabType, label: "CLI Commands" },
                ].map((tab) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    style={{
                      background: activeTab === tab.id ? "var(--bg-surface)" : "transparent",
                      border: `1px solid ${activeTab === tab.id ? "var(--border-subtle)" : "transparent"}`,
                      borderRadius: "var(--radius-xs)",
                      padding: "6px 14px",
                      fontSize: "0.8125rem",
                      fontFamily: "var(--font-mono)",
                      color: activeTab === tab.id ? "var(--text-primary)" : "var(--text-secondary)",
                      cursor: "pointer",
                      fontWeight: activeTab === tab.id ? 600 : 400,
                    }}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                Python 3.11+
              </span>
            </div>

            {/* Code Content */}
            <div style={{ padding: 28, fontFamily: "var(--font-mono)", fontSize: "0.875rem", lineHeight: 1.65, overflowX: "auto" }}>
              {activeTab === "python" && (
                <pre style={{ color: "var(--text-primary)" }}>
                  {`from aether.team.config import TeamConfig, AgentConfig
from aether.team.team import Team

config = TeamConfig(
    name="enterprise-workforce",
    default_provider="ollama",
    default_model="qwen3.5:9b",
    agents=[
        AgentConfig(
            name="manager",
            role="Workforce Coordinator",
            instructions="Decompose project and delegate tasks.",
            delegates_to=["researcher", "writer"]
        ),
        AgentConfig(
            name="researcher",
            role="Knowledge Specialist",
            skills=["search_knowledge"]
        ),
        AgentConfig(
            name="writer",
            role="Proposal Author",
            skills=["format_markdown"]
        )
    ]
)

team = Team(config=config)
result = team.run("Analyze Q3_Report.pdf and draft summary.")
print(result.output)`}
                </pre>
              )}

              {activeTab === "yaml" && (
                <pre style={{ color: "var(--text-primary)" }}>
                  {`name: "enterprise-workforce"
version: "1.3.0"
default_provider: "ollama"
default_model: "qwen3.5:9b"

agents:
  - name: "manager"
    role: "Coordinator"
    delegates_to: ["researcher", "writer"]
  
  - name: "researcher"
    role: "Knowledge Specialist"
    skills: ["search_knowledge"]

  - name: "writer"
    role: "Author"
    skills: ["format_markdown"]`}
                </pre>
              )}

              {activeTab === "cli" && (
                <pre style={{ color: "var(--text-primary)" }}>
                  {`# 1. Launch local Web Workspace:
aether ui

# 2. Run tasks directly via CLI:
aether run "Audit Q3 numbers and prepare summary"

# 3. Check active team status:
aether team status`}
                </pre>
              )}
            </div>
          </div>

          {/* Builder CTAs */}
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
            <a
              href="https://github.com/lom3e/aether/blob/main/README.md"
              target="_blank"
              rel="noopener noreferrer"
              className="btn-secondary"
            >
              <span>{lang === "it" ? "Documentazione Completa" : "Full Documentation"}</span>
              <ExternalLink size={15} />
            </a>

            <a
              href="https://github.com/lom3e/aether"
              target="_blank"
              rel="noopener noreferrer"
              className="btn-secondary"
            >
              <GithubIcon size={16} />
              <span>{lang === "it" ? "Guarda su GitHub" : "View on GitHub"}</span>
            </a>
          </div>
        </div>
      </section>

      <Footer />
    </main>
  );
}
