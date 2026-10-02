import { SerwistProvider } from "@serwist/turbopack/react";
import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import { siteUrl } from "@/lib/site";

export const metadata: Metadata = {
  // Makes link-preview image URLs absolute (P1-07).
  metadataBase: siteUrl(),
  title: "Cornerpin",
  description: "Subdivision lots: status, price, maps, photos and documents.",
  applicationName: "Cornerpin",
  appleWebApp: { capable: true, title: "Cornerpin" },
  icons: { apple: "/icons/apple-touch-icon.png" },
};

export const viewport: Viewport = {
  themeColor: "#1c1917",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-dvh antialiased">
        {/*
          One service worker at the root scope (ADR-005). Caching rules arrive in P1-10;
          cacheOnNavigation would cache every visited page, including /app, so it stays off.
        */}
        <SerwistProvider
          swUrl="/serwist/sw.js"
          disable={process.env.NODE_ENV === "development"}
          cacheOnNavigation={false}
          reloadOnOnline={false}
        >
          {children}
        </SerwistProvider>
      </body>
    </html>
  );
}
