"use client";

import React, { useState } from "react";
import { useActiveLogo } from "@/lib/logo-context";
import { useLanguage } from "@/lib/i18n/context";
import { useTheme } from "@/lib/theme-context";
import { Sparkles, X, Layers, Sun, Moon } from "lucide-react";
import { AetherLogo, LogoId } from "./AetherLogo";

export function VersionPreviewSwitch() {
  const { activeLogo, setActiveLogo } = useActiveLogo();
  const { lang, setLang } = useLanguage();
  const { resolvedTheme, toggleTheme } = useTheme();
  const [minimized, setMinimized] = useState(false);

  const logoOptions: { id: LogoId; name: string }[] = [
    { id: "auto", name: "Auto" },
    { id: "purple", name: "Viola" },
    { id: "full", name: "Completo" },
    { id: "light", name: "Nero" },
  ];

  if (minimized) {
    return (
      <button
        onClick={() => setMinimized(false)}
        style={{
          position: "fixed",
          bottom: 20,
          right: 20,
          zIndex: 9999,
          background: "var(--bg-surface)",
          border: "1px solid var(--border-medium)",
          borderRadius: "var(--radius-full)",
          padding: "8px 16px",
          color: "var(--text-primary)",
          fontSize: "0.75rem",
          fontWeight: 600,
          cursor: "pointer",
          boxShadow: "var(--card-shadow)",
          display: "flex",
          alignItems: "center",
          gap: 8,
          backdropFilter: "blur(16px)",
        }}
        title="Open Logo & Studio Controls"
      >
        <Layers size={14} style={{ color: "var(--accent-violet)" }} />
        <span>Aether Studio</span>
      </button>
    );
  }

  return (
    <div
      style={{
        position: "fixed",
        bottom: 20,
        right: 20,
        zIndex: 9999,
        background: "var(--bg-surface)",
        border: "1px solid var(--border-medium)",
        borderRadius: "var(--radius-lg)",
        padding: "14px 18px",
        boxShadow: "var(--window-shadow)",
        backdropFilter: "blur(20px)",
        display: "flex",
        flexDirection: "column",
        gap: 12,
        maxWidth: 330,
        fontSize: "0.75rem",
      }}
    >
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, fontWeight: 700, color: "var(--text-primary)" }}>
          <Sparkles size={14} style={{ color: "var(--accent-violet)" }} />
          <span>Aether Live Studio</span>
        </div>
        <button
          onClick={() => setMinimized(true)}
          style={{
            background: "transparent",
            border: "none",
            color: "var(--text-muted)",
            cursor: "pointer",
            padding: 2,
          }}
          aria-label="Minimize Studio"
        >
          <X size={14} />
        </button>
      </div>

      {/* Official Logo Selector */}
      <div>
        <div style={{ color: "var(--text-secondary)", marginBottom: 6, fontSize: "0.6875rem", textTransform: "uppercase", letterSpacing: "0.06em" }}>
          Asset Logo Ufficiale:
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 6 }}>
          {logoOptions.map((item) => {
            const isSelected = activeLogo === item.id || (item.id === "auto" && activeLogo === "logo1");
            return (
              <button
                key={item.id}
                onClick={() => setActiveLogo(item.id)}
                style={{
                  background: isSelected ? "rgba(var(--accent-violet-rgb), 0.15)" : "var(--bg-surface-subtle)",
                  border: `1px solid ${isSelected ? "var(--accent-violet)" : "var(--border-subtle)"}`,
                  borderRadius: "var(--radius-xs)",
                  padding: "8px 4px",
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: 4,
                  cursor: "pointer",
                  transition: "all 150ms ease",
                }}
              >
                <AetherLogo id={item.id} variant="mark" size={18} />
                <span style={{ fontSize: "0.625rem", color: isSelected ? "var(--text-primary)" : "var(--text-secondary)", fontWeight: isSelected ? 700 : 400 }}>
                  {item.name}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Quick Controls Line: Theme & Language */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", borderTop: "1px solid var(--border-subtle)", paddingTop: 10 }}>
        {/* Theme quick button */}
        <button
          onClick={toggleTheme}
          style={{
            background: "var(--bg-surface-subtle)",
            border: "1px solid var(--border-subtle)",
            color: "var(--text-secondary)",
            borderRadius: "var(--radius-xs)",
            padding: "4px 8px",
            fontSize: "0.6875rem",
            fontWeight: 600,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            gap: 4,
          }}
        >
          {resolvedTheme === "dark" ? <Sun size={12} /> : <Moon size={12} />}
          <span>{resolvedTheme === "dark" ? "Light" : "Dark"}</span>
        </button>

        {/* Language quick switcher */}
        <div style={{ display: "flex", gap: 4 }}>
          <button
            onClick={() => setLang("it")}
            style={{
              background: lang === "it" ? "var(--accent-violet)" : "transparent",
              color: lang === "it" ? "#ffffff" : "var(--text-secondary)",
              border: "none",
              borderRadius: "var(--radius-xs)",
              padding: "3px 8px",
              fontSize: "0.6875rem",
              fontWeight: 700,
              cursor: "pointer",
            }}
          >
            IT
          </button>
          <button
            onClick={() => setLang("en")}
            style={{
              background: lang === "en" ? "var(--accent-violet)" : "transparent",
              color: lang === "en" ? "#ffffff" : "var(--text-secondary)",
              border: "none",
              borderRadius: "var(--radius-xs)",
              padding: "3px 8px",
              fontSize: "0.6875rem",
              fontWeight: 700,
              cursor: "pointer",
            }}
          >
            EN
          </button>
        </div>
      </div>
    </div>
  );
}
