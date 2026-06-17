import "./globals.css";
import type { Metadata } from "next";
import { HelpButton } from "@/components/help-button";
import { Navbar } from "@/components/navbar";
import { ToastProvider } from "@/components/ui/toast";
import { AuthProvider } from "@/lib/auth-context";

export const metadata: Metadata = {
  title: "Gate.io Capital Bot",
  description: "Low-risk Gate.io spot trading dashboard",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="tr">
      <body>
        <a href="#main-content" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:rounded-md focus:bg-primary focus:px-4 focus:py-2 focus:text-white focus:shadow-lg">
          İçeriğe atla
        </a>
        <ToastProvider>
          <AuthProvider>
            <Navbar />
            <div id="main-content" className="min-h-screen lg:ml-56">{children}</div>
            <HelpButton />
          </AuthProvider>
        </ToastProvider>
      </body>
    </html>
  );
}
