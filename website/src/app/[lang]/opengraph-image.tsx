import { ImageResponse } from "next/og";
import { copy, isLang } from "@/content/home";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const alt = "Aether";

export default async function Image({ params }: { params: Promise<{ lang: string }> }) {
  const { lang } = await params;
  const c = copy[isLang(lang) ? lang : "en"];
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", background: "#0a0a0a", position: "relative", color: "#f5f5f5", fontFamily: "sans-serif" }}>
        <div style={{ position: "absolute", right: -260, top: -120, width: 900, height: 900, borderRadius: 450, background: "#8b5cf6", display: "flex" }} />
        <div style={{ display: "flex", flexDirection: "column", justifyContent: "center", padding: "0 72px", width: 760 }}>
          <div style={{ fontSize: 34, fontWeight: 700, marginBottom: 40, display: "flex" }}>Aether</div>
          <div style={{ fontSize: 92, fontWeight: 800, lineHeight: 1, letterSpacing: -3, display: "flex", flexDirection: "column" }}>
            <span>{c.hero.l1}</span>
            <span>{c.hero.l2}</span>
          </div>
        </div>
      </div>
    ),
    size,
  );
}
