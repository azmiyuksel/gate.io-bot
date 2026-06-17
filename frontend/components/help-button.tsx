"use client";

import { HelpCircle } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { helpAnchorForPath } from "@/lib/help-content";

/**
 * Floating, context-aware help button shown on every screen. It links to the
 * /help section for the CURRENT screen (deep-link via #anchor), so the user
 * lands directly on the explanation for whatever they're looking at.
 */
export function HelpButton() {
  const pathname = usePathname();

  // The /help page itself doesn't need the floating button.
  if (pathname.startsWith("/help")) return null;

  const anchor = helpAnchorForPath(pathname);
  const href = anchor ? `/help#${anchor}` : "/help";

  return (
    <Link
      href={href}
      aria-label="Bu ekran için yardım"
      title="Bu ekran için yardım"
      className="fixed bottom-5 right-5 z-40 flex items-center gap-2 rounded-full border border-border bg-primary px-4 py-2.5 text-sm font-medium text-white shadow-lg transition hover:brightness-95 focus:outline-none focus:ring-2 focus:ring-primary/40"
    >
      <HelpCircle size={18} aria-hidden="true" />
      <span className="hidden sm:inline">Yardım</span>
    </Link>
  );
}
