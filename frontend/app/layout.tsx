import "./globals.css";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Gate.io Capital Bot",
  description: "Low-risk Gate.io spot trading dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="tr">
      <body>{children}</body>
    </html>
  );
}
