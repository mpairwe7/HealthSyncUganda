import type { Metadata, Viewport } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";

import { Header } from "@/components/layout/header";
import { Providers } from "@/components/layout/providers";
import { APP_NAME } from "@/lib/utils/env";

import "./globals.css";

/*
 * Inter and JetBrains Mono are downloaded at build time and served from the
 * Next.js asset pipeline — no runtime Google Fonts call, so the platform
 * works behind firewalls and on the rural offline scenario.
 */
const inter = Inter({
  subsets: ["latin", "latin-ext"],
  variable: "--font-inter",
  display: "swap",
  weight: ["400", "500", "600", "700"],
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  display: "swap",
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: {
    default: APP_NAME,
    template: `%s · ${APP_NAME}`,
  },
  description:
    "Interoperable National Digital Health Platform — patient records, supply chain visibility, FHIR R4 exchange.",
  applicationName: APP_NAME,
  manifest: "/manifest.webmanifest",
  icons: { icon: "/favicon.ico" },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#0F5132",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${inter.variable} ${jetbrainsMono.variable}`}
    >
      <body>
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground"
        >
          Skip to main content
        </a>
        <Providers>
          <Header />
          <main id="main-content" className="container py-6">
            {children}
          </main>
        </Providers>
      </body>
    </html>
  );
}
