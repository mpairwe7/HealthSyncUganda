import type { Metadata, Viewport } from "next";

import { Header } from "@/components/layout/header";
import { Providers } from "@/components/layout/providers";
import { APP_NAME } from "@/lib/utils/env";

import "./globals.css";

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
  themeColor: "#1f8a4c",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <Providers>
          <Header />
          <main className="container py-6">{children}</main>
        </Providers>
      </body>
    </html>
  );
}
