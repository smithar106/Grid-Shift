import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { TopNav } from "@/components/TopNav";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "GridShift — Data Center Energy Optimization",
  description:
    "Integrating public energy data, mathematical programming, and interactive analytics to model cost and emissions trade-offs in flexible computing workloads.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full`}
    >
      <body className="flex min-h-full flex-col">
        <TopNav />
        <main className="mx-auto w-full max-w-[1440px] flex-1 px-6 py-6">{children}</main>
        <footer className="mx-auto w-full max-w-[1440px] px-6 pb-6 pt-2">
          <p className="text-[11px] text-ink-faint">
            GridShift models hypothetical workloads over a finite horizon. It does not
            control real data centers and does not guarantee electricity savings.
          </p>
        </footer>
      </body>
    </html>
  );
}
