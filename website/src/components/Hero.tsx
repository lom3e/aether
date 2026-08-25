"use client";

import React, { useEffect, useRef } from "react";
import { ArrowDown, ArrowRight, Sparkles } from "lucide-react";
import { useLanguage } from "@/lib/i18n/context";
import { useTheme } from "@/lib/theme-context";

export function Hero() {
  const { t, lang } = useLanguage();
  const { resolvedTheme } = useTheme();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  const isDark = resolvedTheme === "dark";
  const isDarkRef = useRef(isDark);
  const langRef = useRef(lang);

  useEffect(() => {
    isDarkRef.current = isDark;
  }, [isDark]);

  useEffect(() => {
    langRef.current = lang;
  }, [lang]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animationFrameId: number;
    let dpr = Math.min(window.devicePixelRatio || 1, 2);
    let width = window.innerWidth;
    let height = window.innerHeight;

    const resize = () => {
      if (!canvas) return;
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.scale(dpr, dpr);
    };

    resize();
    window.addEventListener("resize", resize);

    // Background floating ambient particles
    const bgParticles = Array.from({ length: width < 768 ? 22 : 45 }, () => ({
      x: Math.random() * width,
      y: Math.random() * height,
      vx: (Math.random() - 0.5) * 0.18,
      vy: (Math.random() - 0.5) * 0.18,
      size: 1 + Math.random() * 1.5,
      alpha: 0.15 + Math.random() * 0.35,
    }));

    // Active workflow packets between perimeter agents
    interface Packet {
      fromIdx: number;
      toIdx: number;
      progress: number;
      speed: number;
      color: string;
    }
    let packets: Packet[] = [];

    const spawnPacket = () => {
      const flows = [
        { from: 0, to: 1, color: "#8b5cf6" }, // Coordinator -> Researcher
        { from: 1, to: 2, color: "#38bdf8" }, // Researcher -> Writer
        { from: 2, to: 3, color: "#c084fc" }, // Writer -> Reviewer
        { from: 3, to: 0, color: "#10b981" }, // Reviewer -> Coordinator (Feedback Loop)
      ];
      const chosen = flows[Math.floor(Math.random() * flows.length)];
      packets.push({
        fromIdx: chosen.from,
        toIdx: chosen.to,
        progress: 0,
        speed: 0.008 + Math.random() * 0.006,
        color: chosen.color,
      });
    };

    const packetTimer = setInterval(spawnPacket, 750);

    let tick = 0;

    const render = () => {
      tick++;
      ctx.clearRect(0, 0, width, height);

      const dark = isDarkRef.current;
      const isMob = width < 768;
      const isIt = langRef.current === "it";

      // 1. Ambient Background Particle Dust
      bgParticles.forEach((p) => {
        p.x += p.vx;
        p.y += p.vy;
        if (p.x < 0) p.x = width;
        if (p.x > width) p.x = 0;
        if (p.y < 0) p.y = height;
        if (p.y > height) p.y = 0;

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
        ctx.fillStyle = dark
          ? `rgba(139, 92, 246, ${p.alpha * 0.3})`
          : `rgba(124, 58, 237, ${p.alpha * 0.2})`;
        ctx.fill();
      });

      // 2. Expansive Perimeter Constellation (Safe-Area free from text obstruction)
      const topY = isMob ? Math.max(70, height * 0.11) : Math.max(90, height * 0.13);
      const bottomY = isMob ? Math.min(height - 70, height * 0.90) : Math.min(height - 80, height * 0.89);
      const leftX = isMob ? width * 0.12 : Math.max(90, width * 0.12);
      const rightX = isMob ? width * 0.88 : Math.min(width - 90, width * 0.88);
      const flankY = height * 0.50;

      const swayX = Math.sin(tick * 0.02) * (isMob ? 4 : 8);
      const swayY = Math.cos(tick * 0.018) * (isMob ? 4 : 7);

      const perimeterNodes = [
        {
          id: "coordinator",
          name: isIt ? "Coordinatore" : "Coordinator",
          x: width * 0.5 + swayX * 0.5,
          y: topY + swayY * 0.5,
          color: dark ? "#8b5cf6" : "#7c3aed",
          radius: isMob ? 18 : 24,
          isManager: true,
        },
        {
          id: "researcher",
          name: isIt ? "Ricercatore" : "Researcher",
          x: leftX + swayX,
          y: flankY + swayY * 0.7,
          color: dark ? "#38bdf8" : "#0284c7",
          radius: isMob ? 16 : 20,
          isManager: false,
        },
        {
          id: "writer",
          name: isIt ? "Redattore" : "Writer",
          x: rightX - swayX,
          y: flankY - swayY * 0.7,
          color: dark ? "#c084fc" : "#9333ea",
          radius: isMob ? 16 : 20,
          isManager: false,
        },
        {
          id: "reviewer",
          name: isIt ? "Revisore" : "Reviewer",
          x: width * 0.5 - swayX * 0.5,
          y: bottomY - swayY * 0.5,
          color: dark ? "#f59e0b" : "#d97706",
          radius: isMob ? 16 : 20,
          isManager: false,
        },
      ];

      // 3. Perimeter Connecting Arcs around the center safe-area
      const links = [
        [0, 1], // Coordinator -> Researcher
        [0, 2], // Coordinator -> Writer
        [1, 3], // Researcher -> Reviewer
        [2, 3], // Writer -> Reviewer
      ];

      links.forEach(([i1, i2], linkIdx) => {
        const n1 = perimeterNodes[i1];
        const n2 = perimeterNodes[i2];
        const pulse = (Math.sin(tick * 0.035 + linkIdx * 1.5) + 1) * 0.5;

        const grad = ctx.createLinearGradient(n1.x, n1.y, n2.x, n2.y);
        grad.addColorStop(0, n1.color);
        grad.addColorStop(1, n2.color);

        ctx.beginPath();
        ctx.moveTo(n1.x, n1.y);
        ctx.lineTo(n2.x, n2.y);
        ctx.strokeStyle = dark
          ? `rgba(139, 92, 246, ${0.14 + pulse * 0.12})`
          : `rgba(124, 58, 237, ${0.12 + pulse * 0.10})`;
        ctx.lineWidth = isMob ? 1.2 : 1.8;
        ctx.stroke();
      });

      // 4. Traveling Active Task Packets
      for (let pIdx = packets.length - 1; pIdx >= 0; pIdx--) {
        const p = packets[pIdx];
        p.progress += p.speed;

        if (p.progress >= 1) {
          packets.splice(pIdx, 1);
          continue;
        }

        const nFrom = perimeterNodes[p.fromIdx];
        const nTo = perimeterNodes[p.toIdx];

        const curX = nFrom.x + (nTo.x - nFrom.x) * p.progress;
        const curY = nFrom.y + (nTo.y - nFrom.y) * p.progress;
        const tailX = nFrom.x + (nTo.x - nFrom.x) * Math.max(0, p.progress - 0.08);
        const tailY = nFrom.y + (nTo.y - nFrom.y) * Math.max(0, p.progress - 0.08);

        // Comet tail trail
        ctx.beginPath();
        ctx.moveTo(tailX, tailY);
        ctx.lineTo(curX, curY);
        ctx.strokeStyle = p.color;
        ctx.lineWidth = isMob ? 1.8 : 2.5;
        ctx.lineCap = "round";
        ctx.stroke();

        // Packet halo & core
        ctx.beginPath();
        ctx.arc(curX, curY, isMob ? 5 : 7, 0, Math.PI * 2);
        ctx.fillStyle = dark ? "rgba(139, 92, 246, 0.3)" : "rgba(124, 58, 237, 0.2)";
        ctx.fill();

        ctx.beginPath();
        ctx.arc(curX, curY, isMob ? 2.5 : 3.5, 0, Math.PI * 2);
        ctx.fillStyle = p.color;
        ctx.fill();
      }

      // 5. Draw Perimeter Agent Nodes
      perimeterNodes.forEach((node) => {
        const pulse = Math.sin(tick * 0.04 + (node.isManager ? 0 : 2)) * 3;

        // Outer ambient aura
        ctx.beginPath();
        ctx.arc(node.x, node.y, node.radius + 6 + pulse, 0, Math.PI * 2);
        ctx.fillStyle = dark ? "rgba(139, 92, 246, 0.12)" : "rgba(124, 58, 237, 0.08)";
        ctx.fill();

        // Double ring for Coordinator
        if (node.isManager) {
          ctx.beginPath();
          ctx.arc(node.x, node.y, node.radius + 3, 0, Math.PI * 2);
          ctx.strokeStyle = dark ? "rgba(139, 92, 246, 0.45)" : "rgba(124, 58, 237, 0.35)";
          ctx.lineWidth = 1.2;
          ctx.stroke();
        }

        // Node disc body
        ctx.beginPath();
        ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
        ctx.fillStyle = dark ? "#111116" : "#ffffff";
        ctx.strokeStyle = node.color;
        ctx.lineWidth = node.isManager ? 2 : 1.5;
        ctx.fill();
        ctx.stroke();

        // Node center core
        ctx.beginPath();
        ctx.arc(node.x, node.y, node.radius * 0.42, 0, Math.PI * 2);
        ctx.fillStyle = node.color;
        ctx.fill();

        // Node label
        ctx.font = `${node.isManager ? "700" : "600"} ${isMob ? "10.5px" : "12px"} -apple-system, BlinkMacSystemFont, sans-serif`;
        ctx.fillStyle = dark ? "rgba(255, 255, 255, 0.85)" : "rgba(9, 9, 11, 0.85)";
        ctx.textAlign = "center";
        ctx.fillText(node.name, node.x, node.y + node.radius + (isMob ? 13 : 16));
      });

      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      window.removeEventListener("resize", resize);
      clearInterval(packetTimer);
      cancelAnimationFrame(animationFrameId);
    };
  }, [t, lang]);

  return (
    <section
      style={{
        position: "relative",
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        alignItems: "center",
        padding: "130px 24px 70px",
        overflow: "hidden",
      }}
    >
      {/* High-DPI Spatial Background Canvas */}
      <canvas
        ref={canvasRef}
        style={{
          position: "absolute",
          inset: 0,
          width: "100%",
          height: "100%",
          pointerEvents: "none",
          zIndex: 1,
        }}
      />

      {/* Main Foreground Hero Content (100% Free Safe-Area) */}
      <div
        className="container"
        style={{
          position: "relative",
          zIndex: 10,
          textAlign: "center",
          maxWidth: 880,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          pointerEvents: "none",
        }}
      >
        {/* Minimal Platform Badge */}
        <div style={{ display: "inline-flex", alignItems: "center", gap: 8, marginBottom: 20 }}>
          <span className="badge-pill active" style={{ padding: "4px 14px", fontSize: "0.8125rem" }}>
            <Sparkles size={13} style={{ color: "var(--accent-violet)" }} />
            <span>{t.hero.badge}</span>
          </span>
        </div>

        {/* Giant Punchy Headline */}
        <h1
          style={{
            fontSize: "clamp(2.5rem, 6vw, 5.25rem)",
            fontWeight: 700,
            lineHeight: 1.08,
            letterSpacing: "-0.04em",
            color: "var(--text-primary)",
            marginBottom: 20,
          }}
        >
          {t.hero.title}
        </h1>

        {/* Clean Subtitle */}
        <p
          style={{
            fontSize: "clamp(1.15rem, 2.2vw, 1.4rem)",
            fontWeight: 400,
            lineHeight: 1.55,
            color: "var(--text-secondary)",
            maxWidth: 680,
            marginBottom: 40,
            letterSpacing: "-0.01em",
          }}
        >
          {t.hero.subtitle}
        </p>

        {/* Focused CTA Button Group */}
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            alignItems: "center",
            justifyContent: "center",
            gap: 14,
            marginBottom: 20,
            pointerEvents: "auto",
            width: "100%",
          }}
        >
          {/* Primary CTA: Direct Download */}
          <a
            href="#try"
            className="btn-primary"
            style={{
              padding: "14px 34px",
              fontSize: "1.025rem",
              borderRadius: "var(--radius-sm)",
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
            }}
          >
            <span>{t.hero.ctaPrimary}</span>
            <ArrowRight size={16} />
          </a>

          {/* Secondary CTA: Smooth Scroll to Interactive Story */}
          <a
            href="#story"
            className="btn-secondary"
            style={{
              padding: "14px 28px",
              fontSize: "1.025rem",
              borderRadius: "var(--radius-sm)",
              display: "inline-flex",
              alignItems: "center",
              gap: "8px",
            }}
          >
            <span>{t.hero.ctaSecondary}</span>
            <ArrowDown size={16} />
          </a>
        </div>
      </div>
    </section>
  );
}