import { NextResponse, type NextRequest } from "next/server";

const LOCALES = ["it", "en"] as const;

function pick(request: NextRequest): (typeof LOCALES)[number] {
  const header = request.headers.get("accept-language") || "";
  for (const part of header.split(",")) {
    const code = part.trim().slice(0, 2).toLowerCase();
    if (code === "it" || code === "en") return code;
  }
  return "en";
}

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (LOCALES.some((l) => pathname === `/${l}` || pathname.startsWith(`/${l}/`))) return;
  request.nextUrl.pathname = `/${pick(request)}${pathname === "/" ? "" : pathname}`;
  return NextResponse.redirect(request.nextUrl);
}

export const config = {
  // Everything except Next internals, API and files with an extension (icons, images, sitemap, robots, ...).
  matcher: ["/((?!_next|api|.*\\..*).*)"],
};
