import "./globals.css";
import type { Metadata } from "next";
import { Navbar } from "@/components/navbar";
import { ToastProvider } from "@/components/ui/toast";

export const metadata: Metadata = {
  title: "Gate.io Capital Bot",
  description: "Low-risk Gate.io spot trading dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="tr">
      <body>
        <ToastProvider>
          <Navbar />
          <main className="min-h-screen lg:ml-56">{children}</main>
        </ToastProvider>
      </body>
    </html>
  );
}
