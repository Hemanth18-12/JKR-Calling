import "@jkr/ui/styles.css";
import "./globals.css";

import type { Metadata } from "next";
import { Inter, Outfit } from "next/font/google";

import { Providers } from "./providers";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const outfit = Outfit({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
});

export const metadata: Metadata = {
  title: "JKR AI Calling — India-first AI Voice Platform",
  description:
    "Multilingual AI revenue agent platform for India. Makes and receives calls in Telugu, Hindi, and English. Qualifies leads, books appointments, and proves it worked.",
  keywords: ["AI calling", "multilingual", "Telugu", "Hindi", "India", "lead qualification"],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${outfit.variable}`}>
      <body className="min-h-screen bg-background font-sans text-foreground antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
