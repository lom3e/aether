"use client";

import { useEffect, useState } from "react";
import { AETHER_VERSION } from "./version";
import { RELEASES_URL } from "./site";

/** The latest published release. Falls back to the build-time constant and the generic /releases/latest page (no guessed tags). */
export function useGithubLatestRelease(): { version: string; releaseUrl: string } {
  const [release, setRelease] = useState({ version: AETHER_VERSION, releaseUrl: RELEASES_URL });

  useEffect(() => {
    let cancelled = false;
    fetch("https://api.github.com/repos/lom3e/aether/releases/latest")
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error("release unavailable"))))
      .then((data) => {
        if (cancelled || !data?.tag_name) return;
        const clean = String(data.tag_name).split("-")[0] || String(data.tag_name);
        setRelease({ version: clean, releaseUrl: data.html_url || RELEASES_URL });
      })
      .catch(() => {
        /* keep the fallback */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return release;
}
