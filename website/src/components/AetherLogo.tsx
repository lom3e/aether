"use client";

import React from "react";
import Image from "next/image";
import { useTheme } from "@/lib/theme-context";

export type LogoVariant = "mark" | "horizontal" | "wordmark" | "full" | "favicon";
export type LogoColorMode = "auto" | "light" | "dark" | "purple" | "full";
export type LogoId = "auto" | "light" | "dark" | "purple" | "full" | "logo1" | "logo2" | "logo3" | "logo4";

interface AetherLogoProps {
  id?: LogoId;
  variant?: LogoVariant;
  colorMode?: LogoColorMode;
  size?: number;
  wordmarkHeight?: number;
  interactive?: boolean;
  className?: string;
  style?: React.CSSProperties;
  priority?: boolean;
}

export function AetherLogo({
  id = "auto",
  variant = "horizontal",
  colorMode = "auto",
  size = 28,
  wordmarkHeight,
  interactive = true,
  className = "",
  style = {},
  priority = false,
}: AetherLogoProps) {
  const { resolvedTheme } = useTheme();
  const isDark = resolvedTheme === "dark";

  // Resolve color mode preference — standard purple brand identity
  let effectiveMode: "light" | "dark" | "purple" | "full" = "purple";

  if (colorMode === "full" || id === "full" || variant === "full") {
    effectiveMode = "full";
  } else if (colorMode === "dark" || id === "dark") {
    effectiveMode = "dark";
  } else if (colorMode === "light" || id === "light") {
    effectiveMode = "light";
  } else {
    // Default to official purple logo
    effectiveMode = "purple";
  }

  const containerClass = `${interactive ? "aether-brand-lockup" : ""} ${className}`.trim();

  // 1. Full Composition (Logo Viola con Scritta)
  if (variant === "full" || effectiveMode === "full") {
    const fullHeight = size * 1.4;
    const fullWidth = Math.round(fullHeight * (425.18 / 477.62));

    return (
      <div
        className={containerClass}
        style={{
          display: "inline-flex",
          alignItems: "center",
          textDecoration: "none",
          ...style,
        }}
      >
        <div className="aether-logo-mark">
          <Image
            src="/brand/logo_viola_con_scritta.svg"
            alt="Aether"
            width={fullWidth}
            height={fullHeight}
            style={{ height: `${fullHeight}px`, width: "auto", display: "block" }}
            priority={priority}
            unoptimized
          />
        </div>
      </div>
    );
  }

  // 2. Favicon / Icon only
  if (variant === "favicon") {
    const favHeight = size;
    const favWidth = Math.round(favHeight * (460.89 / 425.88));

    return (
      <div className={containerClass} style={{ display: "inline-flex", alignItems: "center", ...style }}>
        <div className="aether-logo-mark">
          <Image
            src="/brand/favicon.svg"
            alt="Aether"
            width={favWidth}
            height={favHeight}
            style={{ height: `${favHeight}px`, width: "auto", display: "block" }}
            priority={priority}
            unoptimized
          />
        </div>
      </div>
    );
  }

  // 3. Wordmark SVG Helper (scritta_AETHER.svg)
  const wmH = wordmarkHeight || Math.max(14, Math.round(size * 0.58));
  const wmW = Math.round(wmH * (424.47183 / 68.15432));

  const wordmarkElement = (
    <div className="aether-logo-wordmark" style={{ display: "inline-flex", alignItems: "center" }}>
      <Image
        src="/brand/scritta_AETHER.svg"
        alt="AETHER"
        width={wmW}
        height={wmH}
        style={{
          height: `${wmH}px`,
          width: "auto",
          display: "block",
          filter: isDark ? "brightness(0) invert(1)" : "none",
          transition: "filter 200ms ease",
          flexShrink: 0,
        }}
        priority={priority}
        unoptimized
      />
    </div>
  );

  // If wordmark-only variant requested:
  if (variant === "wordmark") {
    return (
      <div className={containerClass} style={{ display: "inline-flex", alignItems: "center", ...style }}>
        {wordmarkElement}
      </div>
    );
  }

  // 4. Mark Glyph Source selection based on mapping:
  // Official Purple Brand Mark (Fixed for both Light and Dark themes)
  let markSrc = "/brand/logo_viola.svg";
  let markAspect = 382.73 / 353.66; // ~1.082

  if (effectiveMode === "dark" && colorMode === "dark") {
    markSrc = "/brand/logo_bianco.svg";
    markAspect = 255.72 / 235.05;
  } else if (effectiveMode === "light" && colorMode === "light") {
    markSrc = "/brand/logo_nero.svg";
    markAspect = 255.72 / 235.05;
  } else {
    markSrc = "/brand/logo_viola.svg";
    markAspect = 382.73 / 353.66;
  }

  const markHeight = size;
  const markWidth = Math.round(markHeight * markAspect);

  const markElement = (
    <div className="aether-logo-mark" style={{ display: "inline-flex", alignItems: "center", flexShrink: 0 }}>
      <Image
        src={markSrc}
        alt="Aether"
        width={markWidth}
        height={markHeight}
        style={{
          height: `${markHeight}px`,
          width: "auto",
          display: "block",
          flexShrink: 0,
        }}
        priority={priority}
        unoptimized
      />
    </div>
  );

  // If mark-only variant requested:
  if (variant === "mark") {
    return (
      <div className={containerClass} style={{ display: "inline-flex", alignItems: "center", ...style }}>
        {markElement}
      </div>
    );
  }

  // 5. Horizontal Variant (Mark + Wordmark SVG)
  return (
    <div
      className={containerClass}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: Math.max(8, Math.round(size * 0.32)),
        textDecoration: "none",
        ...style,
      }}
    >
      {markElement}
      {wordmarkElement}
    </div>
  );
}
