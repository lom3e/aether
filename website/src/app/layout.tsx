import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { LanguageProvider } from "@/lib/i18n/context";
import { LogoProvider } from "@/lib/logo-context";
import { ThemeProvider } from "@/lib/theme-context";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
  display: "swap",
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  display: "swap",
});

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://aether-workforce.org";

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: dark)", color: "#0a0a0a" },
    { media: "(prefers-color-scheme: light)", color: "#fafafa" },
  ],
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
};

export const metadata: Metadata = {
  title: "Aether — Costruisci la tua squadra di AI | Build your AI team",
  description:
    "Aether è una piattaforma aperta per creare e gestire squadre di collaboratori AI per il tuo lavoro.",
  keywords: [
    "AI Workforce",
    "Squadra AI",
    "Collaboratori AI",
    "Multi-Agent System",
    "Autonomous Agents",
    "Aether",
    "Local AI",
    "Ollama",
    "Human in the Loop",
  ],
  authors: [{ name: "Aether Community & LMLabs", url: "https://lmlabs.it" }],
  creator: "Aether",
  publisher: "LMLabs",
  metadataBase: new URL(siteUrl),
  icons: {
    icon: [
      { url: "/brand/favicon.svg", type: "image/svg+xml" },
      { url: "/icon.svg", type: "image/svg+xml" },
    ],
    shortcut: ["/brand/favicon.svg"],
    apple: ["/brand/favicon.svg"],
  },
  alternates: {
    canonical: "/",
    languages: {
      "it": "/?lang=it",
      "en": "/?lang=en",
    },
  },
  openGraph: {
    title: "Aether — Costruisci la tua squadra di AI",
    description:
      "Crea collaboratori AI specializzati, dai loro i tuoi documenti e lascia che lavorino insieme per te.",
    url: siteUrl,
    siteName: "Aether",
    type: "website",
    locale: "it_IT",
    alternateLocale: ["en_US"],
  },
  twitter: {
    card: "summary_large_image",
    title: "Aether — Costruisci la tua squadra di AI",
    description:
      "Crea collaboratori AI specializzati, dai loro i tuoi documenti e lascia che lavorino insieme per te.",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="it" suppressHydrationWarning>
      <head>
        <link rel="icon" href="/brand/favicon.svg" type="image/svg+xml" />
        <script
          dangerouslySetInnerHTML={{
            __html: `
              (function() {
                try {
                  var saved = localStorage.getItem('aether_theme');
                  var theme = saved || 'light';
                  document.documentElement.setAttribute('data-theme', theme);
                  if (theme === 'dark') {
                    document.documentElement.classList.add('dark');
                    document.documentElement.classList.remove('light');
                  } else {
                    document.documentElement.classList.add('light');
                    document.documentElement.classList.remove('dark');
                  }
                } catch(e) {}
              })();
            `,
          }}
        />
      </head>
      <body className={`${geistSans.className} ${geistSans.variable} ${geistMono.variable}`}>
        <ThemeProvider>
          <LanguageProvider>
            <LogoProvider>{children}</LogoProvider>
          </LanguageProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
