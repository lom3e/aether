"use client";

import React, { useState, useEffect, useRef } from "react";
import Image from "next/image";
import {
  ChevronLeft,
  ChevronRight,
  Download,
  ArrowDown,
  Sparkles,
  Play,
  Pause,
} from "lucide-react";
import { useLanguage } from "@/lib/i18n/context";

export function ProductDemo() {
  const { t, lang } = useLanguage();
  const [currentSlide, setCurrentSlide] = useState(0);
  const [isPlaying, setIsPlaying] = useState(true);
  const [touchStart, setTouchStart] = useState<number | null>(null);

  const slides = t.productDemo?.slides || [];
  const totalSlides = slides.length || 7;

  // Auto-advance carousel
  useEffect(() => {
    if (!isPlaying) return;
    const timer = setInterval(() => {
      setCurrentSlide((prev) => (prev + 1) % totalSlides);
    }, 5500);
    return () => clearInterval(timer);
  }, [isPlaying, totalSlides]);

  const handlePrev = () => {
    setIsPlaying(false);
    setCurrentSlide((prev) => (prev - 1 + totalSlides) % totalSlides);
  };

  const handleNext = () => {
    setIsPlaying(false);
    setCurrentSlide((prev) => (prev + 1) % totalSlides);
  };

  const handleTouchStart = (e: React.TouchEvent) => {
    setTouchStart(e.targetTouches[0].clientX);
  };

  const handleTouchEnd = (e: React.TouchEvent) => {
    if (touchStart === null) return;
    const touchEnd = e.changedTouches[0].clientX;
    const diff = touchStart - touchEnd;
    if (diff > 50) handleNext();
    else if (diff < -50) handlePrev();
    setTouchStart(null);
  };

  const slide = slides[currentSlide] || slides[0];

  return (
    <section
      id="concept"
      style={{
        position: "relative",
        padding: "100px 0 120px",
        background: "#08080a",
        borderTop: "1px solid rgba(255, 255, 255, 0.08)",
        borderBottom: "1px solid rgba(255, 255, 255, 0.08)",
        overflow: "hidden",
      }}
    >
      {/* Background Ambient Glow */}
      <div
        style={{
          position: "absolute",
          top: "30%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          width: "600px",
          height: "600px",
          background: "radial-gradient(circle, rgba(139, 92, 246, 0.15) 0%, rgba(139, 92, 246, 0) 70%)",
          pointerEvents: "none",
          zIndex: 0,
        }}
      />

      <div className="container" style={{ maxWidth: 860, position: "relative", zIndex: 1 }}>
        {/* Section Tag */}
        <div style={{ textAlign: "center", marginBottom: 32 }}>
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              padding: "4px 14px",
              borderRadius: "9999px",
              background: "rgba(139, 92, 246, 0.12)",
              border: "1px solid rgba(139, 92, 246, 0.3)",
              color: "#a78bfa",
              fontSize: "0.8125rem",
              fontWeight: 700,
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", sans-serif',
            }}
          >
            <Sparkles size={14} />
            <span>{t.productDemo.tag}</span>
          </div>
        </div>

        {/* Carousel Visual Frame */}
        <div
          onTouchStart={handleTouchStart}
          onTouchEnd={handleTouchEnd}
          style={{
            background: "#0f0f13",
            border: "1px solid rgba(255, 255, 255, 0.12)",
            borderRadius: "24px",
            padding: "48px 36px 40px",
            minHeight: "560px",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "space-between",
            boxShadow: "0 30px 80px -20px rgba(0, 0, 0, 0.8), 0 0 40px rgba(139, 92, 246, 0.1)",
            position: "relative",
            userSelect: "none",
          }}
        >
          {/* 3D Aether Emblem Top Center */}
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", marginBottom: 12 }}>
            <Image
              src="/brand/aether_emblem_3d.png"
              alt="Aether Emblem"
              width={64}
              height={64}
              priority
              style={{ objectFit: "contain", filter: "drop-shadow(0 8px 24px rgba(139, 92, 246, 0.4))" }}
            />
          </div>

          {/* Dynamic Slide Content */}
          <div
            style={{
              width: "100%",
              maxWidth: "680px",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              textAlign: "center",
              flex: 1,
              justifyContent: "center",
              margin: "16px 0 24px",
            }}
          >
            {/* SLIDE 1: Vision / Cover */}
            {currentSlide === 0 && (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 16 }}>
                <h3
                  style={{
                    fontSize: "clamp(2rem, 4.8vw, 3.1rem)",
                    fontWeight: 900,
                    lineHeight: 1.15,
                    color: "#ffffff",
                    letterSpacing: "-0.03em",
                    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", sans-serif',
                    textTransform: "uppercase",
                  }}
                >
                  <div>{slide.headlineTop}</div>
                  <div style={{ color: "#8b5cf6", textShadow: "0 0 30px rgba(139, 92, 246, 0.5)" }}>
                    {slide.headlineHighlight}
                  </div>
                </h3>
                <p
                  style={{
                    fontSize: "1.25rem",
                    fontWeight: 700,
                    color: "#e4e4e7",
                    marginTop: 8,
                    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", sans-serif',
                  }}
                >
                  {slide.caption}
                </p>
              </div>
            )}

            {/* SLIDE 2: Problem / Single AI */}
            {currentSlide === 1 && (
              <div style={{ width: "100%", display: "flex", flexDirection: "column", alignItems: "center", gap: 24 }}>
                <h3
                  style={{
                    fontSize: "clamp(1.75rem, 3.8vw, 2.5rem)",
                    fontWeight: 800,
                    color: "#ffffff",
                    letterSpacing: "-0.02em",
                    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", sans-serif',
                  }}
                >
                  {slide.headline}
                </h3>

                <div
                  style={{
                    width: "100%",
                    background: "rgba(255, 255, 255, 0.03)",
                    border: "1px solid rgba(255, 255, 255, 0.12)",
                    borderRadius: "16px",
                    padding: "24px 28px",
                    display: "flex",
                    flexDirection: "column",
                    gap: 16,
                    textAlign: "left",
                  }}
                >
                  <div style={{ textAlign: "right" }}>
                    <span
                      style={{
                        display: "inline-block",
                        background: "rgba(255, 255, 255, 0.08)",
                        border: "1px solid rgba(255, 255, 255, 0.15)",
                        borderRadius: "12px",
                        padding: "10px 16px",
                        fontSize: "0.9375rem",
                        fontWeight: 600,
                        color: "#ffffff",
                        maxWidth: "85%",
                        lineHeight: 1.5,
                      }}
                    >
                      {slide.prompt}
                    </span>
                  </div>

                  <div style={{ textAlign: "left" }}>
                    <span
                      style={{
                        display: "inline-block",
                        background: "rgba(244, 63, 94, 0.08)",
                        border: "1px solid rgba(244, 63, 94, 0.25)",
                        borderRadius: "12px",
                        padding: "10px 16px",
                        fontSize: "0.9375rem",
                        color: "#fda4af",
                        maxWidth: "85%",
                        lineHeight: 1.5,
                      }}
                    >
                      {slide.botResponse}
                    </span>
                  </div>
                </div>

                <div
                  style={{
                    fontSize: "1.1rem",
                    fontWeight: 700,
                    color: "#ffffff",
                    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", sans-serif',
                  }}
                >
                  {slide.footer}
                </div>
              </div>
            )}

            {/* SLIDE 3: The Team Shift */}
            {currentSlide === 2 && (
              <div style={{ width: "100%", display: "flex", flexDirection: "column", alignItems: "center", gap: 24 }}>
                <h3
                  style={{
                    fontSize: "clamp(1.75rem, 3.8vw, 2.5rem)",
                    fontWeight: 800,
                    color: "#ffffff",
                    letterSpacing: "-0.02em",
                    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", sans-serif',
                  }}
                >
                  {slide.headline}
                </h3>

                <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12, width: "100%" }}>
                  <div
                    style={{
                      background: "rgba(255, 255, 255, 0.05)",
                      border: "1px solid rgba(255, 255, 255, 0.2)",
                      borderRadius: "12px",
                      padding: "12px 32px",
                      fontSize: "1rem",
                      fontWeight: 700,
                      color: "#ffffff",
                    }}
                  >
                    {slide.requestLabel}
                  </div>

                  <div style={{ color: "#8b5cf6", display: "flex", alignItems: "center", justifyContent: "center" }}>
                    <ArrowDown size={22} />
                  </div>

                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "1fr 1fr",
                      gap: 12,
                      width: "100%",
                      maxWidth: "460px",
                    }}
                  >
                    {slide.roles?.map((role: string, idx: number) => (
                      <div
                        key={idx}
                        style={{
                          background: "rgba(139, 92, 246, 0.08)",
                          border: "2px solid #8b5cf6",
                          borderRadius: "12px",
                          padding: "16px 20px",
                          fontSize: "1.05rem",
                          fontWeight: 800,
                          color: "#ffffff",
                          boxShadow: "0 0 20px rgba(139, 92, 246, 0.2)",
                        }}
                      >
                        {role}
                      </div>
                    ))}
                  </div>
                </div>

                <div
                  style={{
                    fontSize: "1.05rem",
                    fontWeight: 700,
                    color: "#a1a1aa",
                    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", sans-serif',
                  }}
                >
                  {slide.footer}
                </div>
              </div>
            )}

            {/* SLIDE 4: One Goal, Multiple Specialists */}
            {currentSlide === 3 && (
              <div style={{ width: "100%", display: "flex", flexDirection: "column", alignItems: "center", gap: 24 }}>
                <h3
                  style={{
                    fontSize: "clamp(1.75rem, 3.8vw, 2.5rem)",
                    fontWeight: 800,
                    color: "#ffffff",
                    letterSpacing: "-0.02em",
                    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", sans-serif',
                  }}
                >
                  {(slide.headline || "").split(slide.highlightWord || "")[0]}
                  <span style={{ color: "#8b5cf6" }}>{slide.highlightWord}</span>
                </h3>

                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr",
                    gap: 14,
                    width: "100%",
                    maxWidth: "540px",
                  }}
                >
                  {slide.cards?.map((card: any, idx: number) => (
                    <div
                      key={idx}
                      style={{
                        background: "rgba(18, 18, 24, 0.95)",
                        border: "1.5px solid rgba(139, 92, 246, 0.6)",
                        borderRadius: "16px",
                        padding: "20px 22px",
                        textAlign: "left",
                        boxShadow: "0 8px 24px rgba(0, 0, 0, 0.5), inset 0 0 20px rgba(139, 92, 246, 0.05)",
                      }}
                    >
                      <div style={{ fontSize: "1.2rem", fontWeight: 800, color: "#ffffff", marginBottom: 4 }}>
                        {card.title}
                      </div>
                      <div style={{ fontSize: "0.875rem", color: "#a1a1aa", fontWeight: 500 }}>
                        {card.sub}
                      </div>
                    </div>
                  ))}
                </div>

                <div
                  style={{
                    fontSize: "1.05rem",
                    fontWeight: 700,
                    color: "#a1a1aa",
                    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", sans-serif',
                  }}
                >
                  {slide.footer}
                </div>
              </div>
            )}

            {/* SLIDE 5: True Collaboration */}
            {currentSlide === 4 && (
              <div style={{ width: "100%", display: "flex", flexDirection: "column", alignItems: "center", gap: 20 }}>
                <h3
                  style={{
                    fontSize: "clamp(1.75rem, 3.8vw, 2.5rem)",
                    fontWeight: 800,
                    color: "#ffffff",
                    letterSpacing: "-0.02em",
                    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", sans-serif',
                  }}
                >
                  {(slide.headline || "").split(slide.highlightWord || "")[0]}
                  <span style={{ color: "#8b5cf6" }}>{slide.highlightWord}</span>
                </h3>

                <div
                  style={{
                    width: "100%",
                    maxWidth: "520px",
                    display: "flex",
                    flexDirection: "column",
                    gap: 10,
                    position: "relative",
                    paddingLeft: "16px",
                    borderLeft: "2px solid rgba(139, 92, 246, 0.5)",
                    textAlign: "left",
                  }}
                >
                  {slide.thread?.map((item: any, idx: number) => (
                    <div
                      key={idx}
                      style={{
                        background: "rgba(255, 255, 255, 0.04)",
                        border: "1px solid rgba(255, 255, 255, 0.1)",
                        borderRadius: "12px",
                        padding: "12px 18px",
                      }}
                    >
                      <div style={{ fontSize: "0.9375rem", fontWeight: 800, color: "#ffffff", marginBottom: 2 }}>
                        {item.role}
                      </div>
                      <div style={{ fontSize: "0.8125rem", color: "#a1a1aa" }}>
                        {item.action}
                      </div>
                    </div>
                  ))}
                </div>

                <div
                  style={{
                    fontSize: "1rem",
                    fontWeight: 700,
                    color: "#a1a1aa",
                    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", sans-serif',
                  }}
                >
                  {slide.footer}
                </div>
              </div>
            )}

            {/* SLIDE 6: Human In The Loop */}
            {currentSlide === 5 && (
              <div style={{ width: "100%", display: "flex", flexDirection: "column", alignItems: "center", gap: 20 }}>
                <h3
                  style={{
                    fontSize: "clamp(1.75rem, 3.8vw, 2.5rem)",
                    fontWeight: 800,
                    color: "#ffffff",
                    letterSpacing: "-0.02em",
                    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", sans-serif',
                  }}
                >
                  {(slide.headline || "").split(slide.highlightWord || "")[0]}
                  <span style={{ color: "#8b5cf6" }}>{slide.highlightWord}</span>
                </h3>

                <div style={{ width: "100%", maxWidth: "520px", display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
                  {/* Engine Box */}
                  <div
                    style={{
                      width: "100%",
                      background: "rgba(18, 18, 24, 0.95)",
                      border: "2px solid #8b5cf6",
                      borderRadius: "16px",
                      padding: "18px 20px",
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      gap: 12,
                      boxShadow: "0 0 30px rgba(139, 92, 246, 0.25)",
                    }}
                  >
                    <div style={{ fontSize: "1.1rem", fontWeight: 800, color: "#ffffff" }}>
                      {slide.engineLabel}
                    </div>
                    <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "center" }}>
                      {slide.agents?.map((ag: string, i: number) => (
                        <span
                          key={i}
                          style={{
                            background: "rgba(255, 255, 255, 0.08)",
                            border: "1px solid rgba(255, 255, 255, 0.15)",
                            borderRadius: "9999px",
                            padding: "4px 12px",
                            fontSize: "0.75rem",
                            fontWeight: 700,
                            color: "#ffffff",
                          }}
                        >
                          {ag}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div style={{ color: "#10b981", display: "flex", alignItems: "center", justifyContent: "center" }}>
                    <ArrowDown size={22} />
                  </div>

                  {/* Delivered Asset Box */}
                  <div
                    style={{
                      width: "100%",
                      maxWidth: "380px",
                      background: "rgba(16, 185, 129, 0.08)",
                      border: "1.5px solid #10b981",
                      borderRadius: "14px",
                      padding: "14px 20px",
                      boxShadow: "0 0 25px rgba(16, 185, 129, 0.2)",
                    }}
                  >
                    <div style={{ fontSize: "0.9375rem", fontWeight: 800, color: "#34d399", marginBottom: 2 }}>
                      {slide.assetLabel}
                    </div>
                    <div style={{ fontSize: "0.8125rem", color: "#a7f3d0", fontWeight: 600 }}>
                      {slide.assetSub}
                    </div>
                  </div>
                </div>

                <div
                  style={{
                    fontSize: "1rem",
                    fontWeight: 700,
                    color: "#a1a1aa",
                    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", sans-serif',
                  }}
                >
                  {slide.footer}
                </div>
              </div>
            )}

            {/* SLIDE 7: Stop Prompting. Start Delegating (CTA) */}
            {currentSlide === 6 && (
              <div style={{ width: "100%", display: "flex", flexDirection: "column", alignItems: "center", gap: 24 }}>
                <h3
                  style={{
                    fontSize: "clamp(2rem, 4.5vw, 2.9rem)",
                    fontWeight: 900,
                    color: "#ffffff",
                    letterSpacing: "-0.03em",
                    lineHeight: 1.15,
                    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", sans-serif',
                  }}
                >
                  <div>Stop prompting.</div>
                  <div style={{ color: "#8b5cf6", textShadow: "0 0 30px rgba(139, 92, 246, 0.5)" }}>
                    Start delegating.
                  </div>
                </h3>

                <p style={{ fontSize: "1.1rem", color: "#a1a1aa", maxWidth: "480px", lineHeight: 1.5 }}>
                  {slide.subheadline}
                </p>

                <a
                  href="https://github.com/lom3e/aether/releases/latest/download/Aether.dmg"
                  target="_blank"
                  rel="noopener noreferrer"
                  style={{
                    background: "linear-gradient(135deg, #8b5cf6 0%, #6d28d9 100%)",
                    color: "#ffffff",
                    padding: "16px 36px",
                    borderRadius: "9999px",
                    fontWeight: 800,
                    fontSize: "1.05rem",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 10,
                    textDecoration: "none",
                    boxShadow: "0 0 35px rgba(139, 92, 246, 0.5)",
                    transition: "transform 150ms ease, box-shadow 150ms ease",
                    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", sans-serif',
                  }}
                >
                  <Download size={18} />
                  <span>{slide.ctaBtn}</span>
                </a>

                <div
                  style={{
                    fontSize: "0.875rem",
                    fontWeight: 600,
                    color: "#71717a",
                    fontFamily: '-apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", sans-serif',
                  }}
                >
                  {slide.footer}
                </div>
              </div>
            )}
          </div>

          {/* Navigation Controls Bar */}
          <div
            style={{
              width: "100%",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              borderTop: "1px solid rgba(255, 255, 255, 0.08)",
              paddingTop: "20px",
              marginTop: "auto",
            }}
          >
            {/* Prev Button */}
            <button
              onClick={handlePrev}
              style={{
                background: "rgba(255, 255, 255, 0.06)",
                border: "1px solid rgba(255, 255, 255, 0.12)",
                borderRadius: "9999px",
                padding: "8px 16px",
                color: "#ffffff",
                fontSize: "0.875rem",
                fontWeight: 600,
                cursor: "pointer",
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                transition: "all 150ms ease",
              }}
            >
              <ChevronLeft size={16} />
              <span>{t.productDemo.prev}</span>
            </button>

            {/* Dots Indicator */}
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              {slides.map((_: any, idx: number) => {
                const active = idx === currentSlide;
                return (
                  <button
                    key={idx}
                    onClick={() => {
                      setIsPlaying(false);
                      setCurrentSlide(idx);
                    }}
                    style={{
                      width: active ? 28 : 8,
                      height: 8,
                      borderRadius: "9999px",
                      background: active ? "#8b5cf6" : "rgba(255, 255, 255, 0.2)",
                      border: "none",
                      cursor: "pointer",
                      transition: "all 200ms ease",
                      padding: 0,
                    }}
                    aria-label={`Slide ${idx + 1}`}
                  />
                );
              })}
            </div>

            {/* Next Button & Autoplay Toggle */}
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <button
                onClick={() => setIsPlaying(!isPlaying)}
                style={{
                  background: "transparent",
                  border: "none",
                  color: isPlaying ? "#8b5cf6" : "#71717a",
                  cursor: "pointer",
                  padding: "6px",
                  display: "flex",
                  alignItems: "center",
                }}
                title={isPlaying ? "Pause autoplay" : "Resume autoplay"}
              >
                {isPlaying ? <Pause size={15} /> : <Play size={15} />}
              </button>

              <button
                onClick={handleNext}
                style={{
                  background: "rgba(255, 255, 255, 0.06)",
                  border: "1px solid rgba(255, 255, 255, 0.12)",
                  borderRadius: "9999px",
                  padding: "8px 16px",
                  color: "#ffffff",
                  fontSize: "0.875rem",
                  fontWeight: 600,
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  transition: "all 150ms ease",
                }}
              >
                <span>{t.productDemo.next}</span>
                <ChevronRight size={16} />
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
