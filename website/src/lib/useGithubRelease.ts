"use client";

import { useState, useEffect } from "react";
import { AETHER_VERSION } from "./version";

export function useGithubLatestRelease(): { version: string; releaseTag: string; releaseUrl: string } {
  const [release, setRelease] = useState({
    version: AETHER_VERSION,
    releaseTag: `Release ${AETHER_VERSION}`,
    releaseUrl: `https://github.com/lom3e/aether/releases/tag/${AETHER_VERSION}-workforce-platform`,
  });

  useEffect(() => {
    // Check cached release
    const cached = sessionStorage.getItem("aether_latest_release");
    if (cached) {
      try {
        const parsed = JSON.parse(cached);
        if (parsed.version) {
          setRelease(parsed);
          return;
        }
      } catch {
        // ignore
      }
    }

    fetch("https://api.github.com/repos/lom3e/aether/releases/latest")
      .then((res) => {
        if (!res.ok) throw new Error("Unable to fetch latest release");
        return res.json();
      })
      .then((data) => {
        if (data && data.tag_name) {
          const rawTag = data.tag_name;
          const cleanVersion = rawTag.split("-")[0] || rawTag;
          const newRel = {
            version: cleanVersion,
            releaseTag: `Release ${cleanVersion}`,
            releaseUrl: data.html_url || `https://github.com/lom3e/aether/releases/tag/${rawTag}`,
          };
          setRelease(newRel);
          sessionStorage.setItem("aether_latest_release", JSON.stringify(newRel));
        }
      })
      .catch(() => {
        // fallback silently to hardcoded constant
      });
  }, []);

  return release;
}
