import type { Metadata, Viewport } from "next";

import { Header } from "@/components/layout/header";
import { Providers } from "@/components/layout/providers";
import { APP_NAME } from "@/lib/utils/env";

import "./globals.css";

// System font stack (see globals.css `--font-sans` / `--font-mono`) — no
// external font fetch, so the platform builds + runs behind firewalls and on
// rural offline workstations. Visually equivalent to Inter on Windows /
// Android / iOS where Segoe UI / Roboto / SF Pro ship system-wide.

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
  // viewport-fit=cover lets us paint under the iOS notch / Android cutout
  // and use env(safe-area-inset-*) to keep content out of the unsafe areas.
  viewportFit: "cover",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground"
        >
          Skip to main content
        </a>
        <Providers>
          <Header />
          <main id="main-content" className="container py-4 sm:py-6">
            {children}
          </main>
        </Providers>
      </body>
    </html>
  );
}
