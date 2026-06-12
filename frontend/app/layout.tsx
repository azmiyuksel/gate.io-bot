import "./globals.css";
import type { Metadata } from "next";
import { Navbar } from "@/components/navbar";

export const metadata: Metadata = {
  title: "Gate.io Capital Bot",
  description: "Low-risk Gate.io spot trading dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="tr">
      <body>
        <Navbar />
        <main className="ml-56 min-h-screen">{children}</main>
      </body>
    </html>
  );
}
