import type { MetadataRoute } from "next";
import { SITE_URL } from "@/lib/site";

const PAGES = ["", "/changelog", "/builders", "/about", "/privacy", "/cookies"];

export default function sitemap(): MetadataRoute.Sitemap {
  return PAGES.flatMap((p) =>
    (["it", "en"] as const).map((l) => ({
      url: `${SITE_URL}/${l}${p}`,
      changeFrequency: p === "" ? "weekly" : "monthly",
      priority: p === "" ? 1 : 0.5,
      alternates: { languages: { it: `${SITE_URL}/it${p}`, en: `${SITE_URL}/en${p}` } },
    })),
  );
}
