"use client";

import React, { useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowRight } from "lucide-react";
import { useLanguage } from "@/lib/i18n/context";
import { useActiveLogo } from "@/lib/logo-context";
import { useTheme } from "@/lib/theme-context";
import { AetherLogo } from "./AetherLogo";

interface AgentNode {
  id: string;
  name: string;
  role: string;
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  baseRadius: number;
  scale: number;
  targetScale: number;
  color: string;
  activity: string;
  connections: string[];
}

interface Packet {
  fromNode: AgentNode;
  toNode: AgentNode;
  progress: number;
  speed: number;
  color: string;
}

export function Hero() {
  const { t } = useLanguage();
  const { activeLogo } = useActiveLogo();
  const { resolvedTheme } = useTheme();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [activeTooltip, setActiveTooltip] = useState<{
    name: string;
    role: string;
    activity: string;
    color: string;
  } | null>(null);
  const [hasHeroVideo, setHasHeroVideo] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);

  // Persistent refs across re-renders
  const nodesRef = useRef<AgentNode[]>([]);
  const isDarkRef = useRef(resolvedTheme === "dark");

  useEffect(() => {
    isDarkRef.current = resolvedTheme === "dark";
  }, [resolvedTheme]);

  useEffect(() => {
    // Check if hero video asset is present
    const testVideo = document.createElement("video");
    testVideo.src = "/videos/hero.mp4";
    testVideo.onloadeddata = () => setHasHeroVideo(true);
    testVideo.onerror = () => setHasHeroVideo(false);

    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animationFrameId: number;
    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    const handleResize = () => {
      if (!canvas) return;
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    };

    window.addEventListener("resize", handleResize);

    const isDark = isDarkRef.current;

    // Initialize nodes once (or re-anchor them without snapping)
    if (nodesRef.current.length === 0) {
      nodesRef.current = [
        {
          id: "manager",
          name: t.hero.agents.manager.name,
          role: t.hero.agents.manager.role,
          x: width * 0.5,
          y: height * 0.38,
          vx: 0.18,
          vy: 0.12,
          radius: 24,
          baseRadius: 24,
          scale: 1,
          targetScale: 1,
          color: isDark ? "#8b5cf6" : "#7c3aed",
          activity: t.hero.agents.manager.status,
          connections: ["researcher", "writer", "oversight"],
        },
        {
          id: "researcher",
          name: t.hero.agents.researcher.name,
          role: t.hero.agents.researcher.role,
          x: width * 0.28,
          y: height * 0.58,
          vx: -0.15,
          vy: 0.1,
          radius: 20,
          baseRadius: 20,
          scale: 1,
          targetScale: 1,
          color: isDark ? "#a1a1aa" : "#475569",
          activity: t.hero.agents.researcher.status,
          connections: ["manager", "writer"],
        },
        {
          id: "writer",
          name: t.hero.agents.writer.name,
          role: t.hero.agents.writer.role,
          x: width * 0.72,
          y: height * 0.58,
          vx: 0.14,
          vy: -0.12,
          radius: 20,
          baseRadius: 20,
          scale: 1,
          targetScale: 1,
          color: isDark ? "#d4d4d8" : "#64748b",
          activity: t.hero.agents.writer.status,
          connections: ["manager", "oversight"],
        },
        {
          id: "oversight",
          name: t.hero.agents.oversight.name,
          role: t.hero.agents.oversight.role,
          x: width * 0.5,
          y: height * 0.78,
          vx: 0.11,
          vy: 0.15,
          radius: 20,
          baseRadius: 20,
          scale: 1,
          targetScale: 1,
          color: isDark ? "#f59e0b" : "#d97706",
          activity: t.hero.agents.oversight.status,
          connections: ["writer", "manager"],
        },
      ];
    } else {
      // Update text and colors smoothly without resetting coordinates
      nodesRef.current.forEach((n) => {
        if (n.id === "manager") {
          n.name = t.hero.agents.manager.name;
          n.role = t.hero.agents.manager.role;
          n.activity = t.hero.agents.manager.status;
          n.color = isDark ? "#8b5cf6" : "#7c3aed";
        } else if (n.id === "researcher") {
          n.name = t.hero.agents.researcher.name;
          n.role = t.hero.agents.researcher.role;
          n.activity = t.hero.agents.researcher.status;
          n.color = isDark ? "#a1a1aa" : "#475569";
        } else if (n.id === "writer") {
          n.name = t.hero.agents.writer.name;
          n.role = t.hero.agents.writer.role;
          n.activity = t.hero.agents.writer.status;
          n.color = isDark ? "#d4d4d8" : "#64748b";
        } else if (n.id === "oversight") {
          n.name = t.hero.agents.oversight.name;
          n.role = t.hero.agents.oversight.role;
          n.activity = t.hero.agents.oversight.status;
          n.color = isDark ? "#f59e0b" : "#d97706";
        }
      });
    }

    const nodes = nodesRef.current;
    const packets: Packet[] = [];

    const createPacket = () => {
      if (nodes.length === 0) return;
      const fromIdx = Math.floor(Math.random() * nodes.length);
      const fromNode = nodes[fromIdx];
      if (fromNode.connections.length === 0) return;

      const targetConnId =
        fromNode.connections[Math.floor(Math.random() * fromNode.connections.length)];
      const toNode = nodes.find((n) => n.id === targetConnId);
      if (!toNode) return;

      packets.push({
        fromNode,
        toNode,
        progress: 0,
        speed: 0.006 + Math.random() * 0.006,
        color: fromNode.color,
      });
    };

    const packetInterval = setInterval(createPacket, 1400);

    let mouseX = -2000;
    let mouseY = -2000;
    let hoveredNode: AgentNode | null = null;

    const handleMouseMove = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      mouseX = e.clientX - rect.left;
      mouseY = e.clientY - rect.top;

      let found: AgentNode | null = null;
      for (const node of nodes) {
        const dist = Math.hypot(mouseX - node.x, mouseY - node.y);
        if (dist < node.radius + 18) {
          found = node;
          break;
        }
      }

      if (found !== hoveredNode) {
        hoveredNode = found;
        if (found) {
          setActiveTooltip({
            name: found.name,
            role: found.role,
            activity: found.activity,
            color: found.color,
          });
        } else {
          setActiveTooltip(null);
        }
      }
    };

    const handleMouseLeave = () => {
      mouseX = -2000;
      mouseY = -2000;
      hoveredNode = null;
      setActiveTooltip(null);
    };

    window.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseleave", handleMouseLeave);

    let tick = 0;

    const render = () => {
      tick++;
      ctx.clearRect(0, 0, width, height);

      const dark = isDarkRef.current;

      // Update Node Positions & Scale Interpolation
      nodes.forEach((node) => {
        const isHovered = hoveredNode?.id === node.id;
        node.targetScale = isHovered ? 1.25 : 1;
        // Smooth easing towards target scale (10% per frame)
        node.scale += (node.targetScale - node.scale) * 0.12;
        node.radius = node.baseRadius * node.scale;

        // Continuous smooth soft drift
        node.x += node.vx;
        node.y += node.vy;

        const pad = node.baseRadius + 25;
        if (node.x < pad) {
          node.x = pad;
          node.vx = Math.abs(node.vx);
        } else if (node.x > width - pad) {
          node.x = width - pad;
          node.vx = -Math.abs(node.vx);
        }

        if (node.y < pad) {
          node.y = pad;
          node.vy = Math.abs(node.vy);
        } else if (node.y > height - pad) {
          node.y = height - pad;
          node.vy = -Math.abs(node.vy);
        }
      });

      // Draw Connection Lines
      ctx.lineWidth = 1;
      nodes.forEach((fromNode) => {
        fromNode.connections.forEach((targetId) => {
          const toNode = nodes.find((n) => n.id === targetId);
          if (!toNode) return;

          ctx.beginPath();
          ctx.moveTo(fromNode.x, fromNode.y);
          ctx.lineTo(toNode.x, toNode.y);
          ctx.strokeStyle = dark ? "rgba(255, 255, 255, 0.05)" : "rgba(0, 0, 0, 0.06)";
          ctx.stroke();
        });
      });

      // Draw & Update Packets
      for (let i = packets.length - 1; i >= 0; i--) {
        const p = packets[i];
        p.progress += p.speed;

        if (p.progress >= 1) {
          packets.splice(i, 1);
          continue;
        }

        const px = p.fromNode.x + (p.toNode.x - p.fromNode.x) * p.progress;
        const py = p.fromNode.y + (p.toNode.y - p.fromNode.y) * p.progress;

        ctx.beginPath();
        ctx.arc(px, py, 3, 0, Math.PI * 2);
        ctx.fillStyle = p.color;
        ctx.shadowColor = p.color;
        ctx.shadowBlur = 6;
        ctx.fill();
        ctx.shadowBlur = 0;
      }

      // Draw Nodes
      nodes.forEach((node) => {
        const isHovered = hoveredNode?.id === node.id;
        const pulse = Math.sin(tick * 0.035 + node.baseRadius) * 2;

        // Outer Glow Halo
        ctx.beginPath();
        ctx.arc(node.x, node.y, node.radius + 8 + pulse, 0, Math.PI * 2);
        ctx.fillStyle = isHovered
          ? dark ? "rgba(139, 92, 246, 0.22)" : "rgba(124, 58, 237, 0.16)"
          : dark ? "rgba(255, 255, 255, 0.02)" : "rgba(0, 0, 0, 0.02)";
        ctx.fill();

        // Node Surface Circle
        ctx.beginPath();
        ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
        ctx.fillStyle = dark ? "#121214" : "#ffffff";
        ctx.strokeStyle = isHovered
          ? node.color
          : dark ? "rgba(255, 255, 255, 0.15)" : "rgba(0, 0, 0, 0.14)";
        ctx.lineWidth = isHovered ? 2.5 : 1.5;
        ctx.fill();
        ctx.stroke();

        // Center Core Point
        ctx.beginPath();
        ctx.arc(node.x, node.y, node.radius * 0.45, 0, Math.PI * 2);
        ctx.fillStyle = node.color;
        ctx.fill();

        // Label Typography
        ctx.font = `600 13px system-ui, -apple-system, sans-serif`;
        ctx.fillStyle = isHovered
          ? dark ? "#f5f5f5" : "#0f172a"
          : dark ? "rgba(245, 245, 245, 0.85)" : "rgba(15, 23, 42, 0.85)";
        ctx.textAlign = "center";
        ctx.fillText(node.name, node.x, node.y + node.radius + 18);
      });

      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      window.removeEventListener("resize", handleResize);
      window.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseleave", handleMouseLeave);
      clearInterval(packetInterval);
      cancelAnimationFrame(animationFrameId);
    };
  }, [t]);

  return (
    <section
      style={{
        position: "relative",
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        alignItems: "center",
        padding: "140px 24px 70px",
        overflow: "hidden",
      }}
    >
      {/* Video or Canvas Background Stage */}
      {hasHeroVideo ? (
        <video
          ref={videoRef}
          src="/videos/hero.mp4"
          poster="/videos/hero-poster.jpg"
          autoPlay
          muted
          loop
          playsInline
          style={{
            position: "absolute",
            inset: 0,
            width: "100%",
            height: "100%",
            objectFit: "cover",
            zIndex: 1,
            opacity: resolvedTheme === "dark" ? 0.65 : 0.4,
          }}
        />
      ) : (
        <canvas
          ref={canvasRef}
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            width: "100%",
            height: "100%",
            pointerEvents: "auto",
            zIndex: 1,
            opacity: 0.95,
          }}
        />
      )}

      {/* Hero Content Container */}
      <div
        className="container"
        style={{
          position: "relative",
          zIndex: 2,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          textAlign: "center",
          maxWidth: 900,
          pointerEvents: "none",
        }}
      >
        {/* Brand Supertitle Lockup with Official Mark & Wordmark */}
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            marginBottom: 20,
          }}
        >
          <AetherLogo id={activeLogo} size={22} wordmarkHeight={13} priority />
        </div>

        {/* Primary Headline */}
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
          <a
            href="#story"
            className="btn-primary"
            style={{
              padding: "14px 34px",
              fontSize: "1.025rem",
              borderRadius: "var(--radius-sm)",
            }}
          >
            <span>{t.hero.ctaPrimary}</span>
            <ArrowDown size={16} />
          </a>

          <a
            href="#try"
            className="btn-secondary"
            style={{
              padding: "14px 28px",
              fontSize: "1.025rem",
              borderRadius: "var(--radius-sm)",
            }}
          >
            <span>{t.hero.ctaSecondary}</span>
            <ArrowRight size={16} />
          </a>
        </div>

        {/* Live Hover Node Inspection Overlay */}
        {activeTooltip && (
          <div
            style={{
              position: "fixed",
              bottom: 30,
              left: "50%",
              transform: "translateX(-50%)",
              background: "var(--bg-surface)",
              border: `1px solid ${activeTooltip.color}`,
              borderRadius: "var(--radius-md)",
              padding: "12px 22px",
              display: "flex",
              alignItems: "center",
              gap: 14,
              boxShadow: "var(--card-shadow)",
              backdropFilter: "blur(16px)",
              zIndex: 50,
              pointerEvents: "none",
            }}
          >
            <div
              style={{
                width: 10,
                height: 10,
                borderRadius: "50%",
                background: activeTooltip.color,
              }}
            />
            <div style={{ textAlign: "left" }}>
              <div style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-primary)" }}>
                {activeTooltip.name} • {activeTooltip.role}
              </div>
              <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                {activeTooltip.activity}
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
