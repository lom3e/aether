"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { ShieldCheck, Cookie, X, Settings2, Lock } from "lucide-react";
import { useLanguage } from "@/lib/i18n/context";

interface CookiePreferences {
  essential: boolean;
  functional: boolean;
  analytics: boolean;
  marketing: boolean;
  timestamp?: string;
  version?: string;
}

const STORAGE_KEY = "aether_cookie_consent";
const CURRENT_VERSION = "1.0";

export function CookieConsent() {
  const { t } = useLanguage();
  const [mounted, setMounted] = useState(false);
  const [bannerVisible, setBannerVisible] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);

  const [preferences, setPreferences] = useState<CookiePreferences>({
    essential: true,
    functional: false,
    analytics: false,
    marketing: false,
  });

  useEffect(() => {
    setMounted(true);
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsed = JSON.parse(saved) as CookiePreferences;
        setPreferences({
          essential: true,
          functional: !!parsed.functional,
          analytics: !!parsed.analytics,
          marketing: !!parsed.marketing,
        });
      } else {
        setBannerVisible(true);
      }
    } catch {
      setBannerVisible(true);
    }

    const handleOpenModal = () => {
      setModalVisible(true);
    };

    window.addEventListener("aether-open-cookie-preferences", handleOpenModal);

    return () => {
      window.removeEventListener("aether-open-cookie-preferences", handleOpenModal);
    };
  }, []);

  const saveConsent = (prefs: CookiePreferences) => {
    const payload: CookiePreferences = {
      ...prefs,
      essential: true,
      timestamp: new Date().toISOString(),
      version: CURRENT_VERSION,
    };
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
    } catch {
      // ignore
    }
    setPreferences(payload);
    setBannerVisible(false);
    setModalVisible(false);
  };

  const handleAcceptAll = () => {
    saveConsent({
      essential: true,
      functional: true,
      analytics: true,
      marketing: true,
    });
  };

  const handleRejectNonEssential = () => {
    saveConsent({
      essential: true,
      functional: false,
      analytics: false,
      marketing: false,
    });
  };

  const handleSaveCustom = () => {
    saveConsent(preferences);
  };

  if (!mounted) return null;

  return (
    <>
      {/* 1. FLOATING BOTTOM BANNER */}
      {bannerVisible && !modalVisible && (
        <div
          role="region"
          aria-label={t.cookieConsent.bannerTitle}
          style={{
            position: "fixed",
            bottom: 24,
            left: 20,
            right: 20,
            maxWidth: 620,
            margin: "0 auto",
            zIndex: 9990,
            background: "var(--bg-surface)",
            border: "1px solid var(--border-medium)",
            borderRadius: "var(--radius-lg)",
            boxShadow: "var(--window-shadow)",
            backdropFilter: "blur(20px)",
            WebkitBackdropFilter: "blur(20px)",
            padding: "24px",
            display: "flex",
            flexDirection: "column",
            gap: 16,
            animation: "aetherFadeUp 250ms cubic-bezier(0.16, 1, 0.3, 1)",
          }}
        >
          {/* Header */}
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div
              style={{
                width: 34,
                height: 34,
                borderRadius: "var(--radius-sm)",
                background: "rgba(var(--accent-violet-rgb), 0.12)",
                border: "1px solid rgba(var(--accent-violet-rgb), 0.25)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--accent-violet)",
                flexShrink: 0,
              }}
            >
              <Cookie size={18} />
            </div>
            <h3
              style={{
                fontSize: "1.05rem",
                fontWeight: 700,
                color: "var(--text-primary)",
                margin: 0,
                letterSpacing: "-0.02em",
              }}
            >
              {t.cookieConsent.bannerTitle}
            </h3>
          </div>

          {/* Description */}
          <p
            style={{
              fontSize: "0.875rem",
              color: "var(--text-secondary)",
              lineHeight: 1.55,
              margin: 0,
            }}
          >
            {t.cookieConsent.bannerText}{" "}
            <span>
              {t.cookieConsent.footerNotice}{" "}
              <Link
                href="/privacy"
                style={{
                  color: "var(--accent-violet)",
                  textDecoration: "underline",
                  fontWeight: 500,
                }}
              >
                {t.cookieConsent.privacyLink}
              </Link>{" "}
              e la{" "}
              <Link
                href="/cookies"
                style={{
                  color: "var(--accent-violet)",
                  textDecoration: "underline",
                  fontWeight: 500,
                }}
              >
                {t.cookieConsent.cookieLink}
              </Link>
              .
            </span>
          </p>

          {/* Action Buttons */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "flex-end",
              flexWrap: "wrap",
              gap: 10,
              paddingTop: 6,
            }}
          >
            <button
              onClick={() => setModalVisible(true)}
              style={{
                padding: "8px 14px",
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--border-subtle)",
                background: "var(--bg-surface-subtle)",
                color: "var(--text-secondary)",
                fontSize: "0.8125rem",
                fontWeight: 600,
                cursor: "pointer",
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                transition: "all 150ms ease",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.color = "var(--text-primary)")}
              onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-secondary)")}
            >
              <Settings2 size={14} />
              <span>{t.cookieConsent.customize}</span>
            </button>

            <button
              onClick={handleRejectNonEssential}
              style={{
                padding: "8px 16px",
                borderRadius: "var(--radius-sm)",
                border: "1px solid var(--border-medium)",
                background: "var(--bg-surface)",
                color: "var(--text-primary)",
                fontSize: "0.8125rem",
                fontWeight: 600,
                cursor: "pointer",
                transition: "all 150ms ease",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-surface-elevated)")}
              onMouseLeave={(e) => (e.currentTarget.style.background = "var(--bg-surface)")}
            >
              {t.cookieConsent.rejectNonEssential}
            </button>

            <button
              onClick={handleAcceptAll}
              className="btn-primary"
              style={{
                padding: "8px 18px",
                fontSize: "0.8125rem",
                borderRadius: "var(--radius-sm)",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              {t.cookieConsent.acceptAll}
            </button>
          </div>
        </div>
      )}

      {/* 2. DETAILED PREFERENCES MODAL */}
      {modalVisible && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="cookie-modal-title"
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 10000,
            background: "rgba(0, 0, 0, 0.65)",
            backdropFilter: "blur(12px)",
            WebkitBackdropFilter: "blur(12px)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "20px",
            animation: "aetherFade 200ms ease",
          }}
          onClick={(e) => {
            if (e.target === e.currentTarget) setModalVisible(false);
          }}
        >
          <div
            style={{
              width: "100%",
              maxWidth: 620,
              maxHeight: "88vh",
              overflowY: "auto",
              background: "var(--bg-surface)",
              border: "1px solid var(--border-medium)",
              borderRadius: "var(--radius-xl)",
              padding: "32px 28px",
              boxShadow: "var(--window-shadow)",
              display: "flex",
              flexDirection: "column",
              gap: 22,
              animation: "aetherScaleUp 220ms cubic-bezier(0.16, 1, 0.3, 1)",
            }}
          >
            {/* Modal Header */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 16 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                <div
                  style={{
                    width: 40,
                    height: 40,
                    borderRadius: "var(--radius-sm)",
                    background: "rgba(var(--accent-violet-rgb), 0.12)",
                    border: "1px solid rgba(var(--accent-violet-rgb), 0.25)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    color: "var(--accent-violet)",
                    flexShrink: 0,
                  }}
                >
                  <ShieldCheck size={22} />
                </div>
                <div>
                  <h2
                    id="cookie-modal-title"
                    style={{
                      fontSize: "1.25rem",
                      fontWeight: 700,
                      color: "var(--text-primary)",
                      letterSpacing: "-0.02em",
                      margin: 0,
                    }}
                  >
                    {t.cookieConsent.modalTitle}
                  </h2>
                </div>
              </div>

              <button
                onClick={() => setModalVisible(false)}
                style={{
                  background: "transparent",
                  border: "none",
                  color: "var(--text-muted)",
                  cursor: "pointer",
                  padding: 4,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  borderRadius: "var(--radius-xs)",
                  transition: "color 150ms ease",
                }}
                aria-label={t.cookieConsent.close}
                onMouseEnter={(e) => (e.currentTarget.style.color = "var(--text-primary)")}
                onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-muted)")}
              >
                <X size={20} />
              </button>
            </div>

            {/* Modal Intro */}
            <p
              style={{
                fontSize: "0.875rem",
                color: "var(--text-secondary)",
                lineHeight: 1.6,
                margin: 0,
              }}
            >
              {t.cookieConsent.modalDesc}
            </p>

            {/* Category Accordion / List */}
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {/* 1. Essential / Technical */}
              <div
                style={{
                  background: "var(--bg-surface-elevated)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-md)",
                  padding: "16px 18px",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <Lock size={15} style={{ color: "var(--accent-violet)" }} />
                    <strong style={{ fontSize: "0.95rem", color: "var(--text-primary)" }}>
                      {t.cookieConsent.categories.essential.name}
                    </strong>
                  </div>
                  <span
                    style={{
                      fontSize: "0.75rem",
                      fontWeight: 700,
                      color: "var(--accent-emerald)",
                      background: "rgba(16, 185, 129, 0.1)",
                      padding: "2px 8px",
                      borderRadius: "var(--radius-full)",
                    }}
                  >
                    {t.cookieConsent.categories.essential.badge}
                  </span>
                </div>
                <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", lineHeight: 1.5, margin: 0 }}>
                  {t.cookieConsent.categories.essential.desc}
                </p>
              </div>

              {/* 2. Functional */}
              <div
                style={{
                  background: "var(--bg-surface-elevated)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-md)",
                  padding: "16px 18px",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                  <strong style={{ fontSize: "0.95rem", color: "var(--text-primary)" }}>
                    {t.cookieConsent.categories.functional.name}
                  </strong>
                  <label style={{ display: "inline-flex", alignItems: "center", cursor: "pointer", position: "relative" }}>
                    <input
                      type="checkbox"
                      checked={preferences.functional}
                      onChange={(e) => setPreferences({ ...preferences, functional: e.target.checked })}
                      style={{
                        width: 38,
                        height: 20,
                        accentColor: "var(--accent-violet)",
                        cursor: "pointer",
                      }}
                    />
                  </label>
                </div>
                <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", lineHeight: 1.5, margin: 0 }}>
                  {t.cookieConsent.categories.functional.desc}
                </p>
              </div>

              {/* 3. Analytics */}
              <div
                style={{
                  background: "var(--bg-surface-elevated)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-md)",
                  padding: "16px 18px",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                  <strong style={{ fontSize: "0.95rem", color: "var(--text-primary)" }}>
                    {t.cookieConsent.categories.analytics.name}
                  </strong>
                  <label style={{ display: "inline-flex", alignItems: "center", cursor: "pointer", position: "relative" }}>
                    <input
                      type="checkbox"
                      checked={preferences.analytics}
                      onChange={(e) => setPreferences({ ...preferences, analytics: e.target.checked })}
                      style={{
                        width: 38,
                        height: 20,
                        accentColor: "var(--accent-violet)",
                        cursor: "pointer",
                      }}
                    />
                  </label>
                </div>
                <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", lineHeight: 1.5, margin: 0 }}>
                  {t.cookieConsent.categories.analytics.desc}
                </p>
              </div>

              {/* 4. Marketing */}
              <div
                style={{
                  background: "var(--bg-surface-elevated)",
                  border: "1px solid var(--border-subtle)",
                  borderRadius: "var(--radius-md)",
                  padding: "16px 18px",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                  <strong style={{ fontSize: "0.95rem", color: "var(--text-primary)" }}>
                    {t.cookieConsent.categories.marketing.name}
                  </strong>
                  <label style={{ display: "inline-flex", alignItems: "center", cursor: "pointer", position: "relative" }}>
                    <input
                      type="checkbox"
                      checked={preferences.marketing}
                      onChange={(e) => setPreferences({ ...preferences, marketing: e.target.checked })}
                      style={{
                        width: 38,
                        height: 20,
                        accentColor: "var(--accent-violet)",
                        cursor: "pointer",
                      }}
                    />
                  </label>
                </div>
                <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", lineHeight: 1.5, margin: 0 }}>
                  {t.cookieConsent.categories.marketing.desc}
                </p>
              </div>
            </div>

            {/* Modal Bottom Actions */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                flexWrap: "wrap",
                gap: 10,
                borderTop: "1px solid var(--border-subtle)",
                paddingTop: 16,
              }}
            >
              <button
                onClick={handleRejectNonEssential}
                style={{
                  padding: "10px 16px",
                  borderRadius: "var(--radius-sm)",
                  border: "1px solid var(--border-subtle)",
                  background: "var(--bg-surface)",
                  color: "var(--text-secondary)",
                  fontSize: "0.875rem",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                {t.cookieConsent.rejectNonEssential}
              </button>

              <div style={{ display: "flex", gap: 10 }}>
                <button
                  onClick={handleSaveCustom}
                  style={{
                    padding: "10px 18px",
                    borderRadius: "var(--radius-sm)",
                    border: "1px solid var(--border-medium)",
                    background: "var(--bg-surface-elevated)",
                    color: "var(--text-primary)",
                    fontSize: "0.875rem",
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                >
                  {t.cookieConsent.savePreferences}
                </button>

                <button
                  onClick={handleAcceptAll}
                  className="btn-primary"
                  style={{
                    padding: "10px 20px",
                    fontSize: "0.875rem",
                    borderRadius: "var(--radius-sm)",
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                >
                  {t.cookieConsent.acceptAll}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <style jsx global>{`
        @keyframes aetherFadeUp {
          from {
            opacity: 0;
            transform: translateY(16px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
        @keyframes aetherFade {
          from {
            opacity: 0;
          }
          to {
            opacity: 1;
          }
        }
        @keyframes aetherScaleUp {
          from {
            opacity: 0;
            transform: scale(0.96);
          }
          to {
            opacity: 1;
            transform: scale(1);
          }
        }
      `}</style>
    </>
  );
}
