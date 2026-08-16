"use client";

import React, { createContext, useContext, useState } from "react";
import { LogoId } from "@/components/AetherLogo";

interface LogoContextType {
  activeLogo: LogoId;
  setActiveLogo: (id: LogoId) => void;
}

const LogoContext = createContext<LogoContextType | undefined>(undefined);

function getInitialLogo(): LogoId {
  if (typeof window === "undefined") return "auto";
  try {
    const saved = localStorage.getItem("aether_active_logo") as LogoId | null;
    if (saved) return saved;
  } catch {
    // ignore
  }
  return "auto";
}

export function LogoProvider({ children }: { children: React.ReactNode }) {
  const [activeLogo, setActiveLogoState] = useState<LogoId>(getInitialLogo);

  const setActiveLogo = (id: LogoId) => {
    setActiveLogoState(id);
    try {
      localStorage.setItem("aether_active_logo", id);
    } catch {
      // ignore
    }
  };

  return (
    <LogoContext.Provider value={{ activeLogo, setActiveLogo }}>
      {children}
    </LogoContext.Provider>
  );
}

export function useActiveLogo(): LogoContextType {
  const context = useContext(LogoContext);
  if (!context) {
    return {
      activeLogo: "auto",
      setActiveLogo: () => {},
    };
  }
  return context;
}
