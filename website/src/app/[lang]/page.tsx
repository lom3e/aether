import { notFound } from "next/navigation";
import { copy, isLang } from "@/content/home";
import { Nav } from "@/components/home/Nav";
import { Hero } from "@/components/home/Hero";
import { CompanionDemo } from "@/components/home/CompanionDemo";
import { RealApp } from "@/components/home/RealApp";
import { ScreenFlow } from "@/components/home/ScreenFlow";
import { MemoryBoard } from "@/components/home/MemoryBoard";
import { Teams } from "@/components/home/Teams";
import { Privacy } from "@/components/home/Privacy";
import { Models } from "@/components/home/Models";
import { Download } from "@/components/home/Download";
import { Faq } from "@/components/home/Faq";
import { SiteFooter } from "@/components/home/SiteFooter";
import { SITE_URL } from "@/lib/site";

export default async function HomePage({ params }: { params: Promise<{ lang: string }> }) {
  const { lang } = await params;
  if (!isLang(lang)) notFound();
  const c = copy[lang];
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: "Aether",
    applicationCategory: "ProductivityApplication",
    operatingSystem: "macOS",
    description: c.meta.description,
    url: `${SITE_URL}/${lang}`,
    offers: { "@type": "Offer", price: "0", priceCurrency: "EUR" },
    license: "https://opensource.org/licenses/MIT",
  };
  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
      <Nav />
      <main id="main">
        <Hero c={c} />
        <CompanionDemo c={c} />
        <ScreenFlow c={c} />
        <RealApp c={c} />
        <MemoryBoard c={c} />
        <Teams c={c} />
        <Privacy c={c} />
        <Models c={c} />
        <Download c={c} />
        <Faq c={c} />
      </main>
      <SiteFooter />
    </>
  );
}
