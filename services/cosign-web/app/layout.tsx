import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";
import "./globals.css";
import { Header } from "@/components/Header";

const plexSans = IBM_Plex_Sans({
  variable: "--font-plex-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});
const plexMono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: "Cosign — you cosign, not a bot",
  description: "AI drafts the work. An AI critic refines it. You cosign. Shipped under your name.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${plexSans.variable} ${plexMono.variable}`}>
      <body>
        <div className="bp-grid" aria-hidden />
        <div className="bp-glow" aria-hidden />
        <div className="bp-grain" aria-hidden />
        <Header />
        <main className="mx-auto max-w-5xl px-5 py-8">{children}</main>
      </body>
    </html>
  );
}
