import "@jkr/ui/styles.css";
import "./globals.css";

import type { Metadata } from "next";
import {
  Outfit,
  Plus_Jakarta_Sans,
  Noto_Sans_Telugu,
  Noto_Sans_Devanagari,
  JetBrains_Mono,
} from "next/font/google";

import { Providers } from "./providers";

const outfit = Outfit({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
});

const plusJakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const notoTelugu = Noto_Sans_Telugu({
  subsets: ["telugu"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-telugu",
  display: "swap",
});

const notoDevanagari = Noto_Sans_Devanagari({
  subsets: ["devanagari"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-devanagari",
  display: "swap",
});

const jetBrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "JKR AI Calling | India-first AI Voice Platform",
  description:
    "Multilingual AI revenue agent platform for India. Makes and receives calls in Telugu, Hindi, and English. Qualifies leads, books appointments, and proves it worked.",
  keywords: ["AI calling", "multilingual", "Telugu", "Hindi", "India", "lead qualification"],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${outfit.variable} ${plusJakarta.variable} ${notoTelugu.variable} ${notoDevanagari.variable} ${jetBrainsMono.variable}`}
    >
      <body className="min-h-screen bg-background font-sans text-foreground antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
