import type { Metadata, Viewport } from "next";
import { notFound } from "next/navigation";
import { Inter } from "next/font/google";
import "../globals.css";
import "../site.css";
import { LanguageProvider } from "@/lib/i18n/context";
import { ThemeProvider } from "@/lib/theme-context";
import { CookieConsent } from "@/components/CookieConsent";
import { copy, isLang, LANGS } from "@/content/home";
import { SITE_URL } from "@/lib/site";

const sans = Inter({ variable: "--font-sans-loaded", subsets: ["latin"], display: "swap" });

export const viewport: Viewport = {
  themeColor: [{ color: "#0b0b0e" }],
  width: "device-width",
  initialScale: 1,
};

export function generateStaticParams() {
  return LANGS.map((lang) => ({ lang }));
}

export async function generateMetadata({ params }: { params: Promise<{ lang: string }> }): Promise<Metadata> {
  const { lang } = await params;
  if (!isLang(lang)) return {};
  const c = copy[lang];
  return {
    metadataBase: new URL(SITE_URL),
    title: { default: c.meta.title, template: "%s · Aether" },
    description: c.meta.description,
    applicationName: "Aether",
    authors: [{ name: "Aether Community & LMLabs", url: "https://lmlabs.it" }],
    alternates: { canonical: `/${lang}`, languages: { it: "/it", en: "/en", "x-default": "/en" } },
    openGraph: {
      title: c.meta.ogTitle,
      description: c.meta.description,
      url: `/${lang}`,
      siteName: "Aether",
      type: "website",
      locale: lang === "it" ? "it_IT" : "en_US",
      alternateLocale: lang === "it" ? ["en_US"] : ["it_IT"],
    },
    twitter: { card: "summary_large_image", title: c.meta.ogTitle, description: c.meta.description },
  };
}

const themeScript = `(function(){try{var s=localStorage.getItem('aether_theme');var t=s==='light'||s==='dark'?s:(s==='system'?(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'):'dark');var d=document.documentElement;d.setAttribute('data-theme',t);d.classList.add(t,'js');}catch(e){document.documentElement.setAttribute('data-theme','dark');}})();`;

export default async function RootLayout({ children, params }: { children: React.ReactNode; params: Promise<{ lang: string }> }) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();
  return (
    <html lang={lang} suppressHydrationWarning className={sans.variable}>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>
        <ThemeProvider>
          <LanguageProvider lang={lang}>
            {children}
            <CookieConsent />
          </LanguageProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
