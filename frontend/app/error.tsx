"use client";

import { Button } from "@/components/ui/button";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center px-6 text-center">
      <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-red-100">
        <span className="text-2xl">&#9888;</span>
      </div>
      <h2 className="mb-2 text-xl font-semibold">Bir hata oluştu</h2>
      <p className="mb-6 max-w-md text-sm text-muted">
        {error.message || "Beklenmeyen bir hata oluştu. Lütfen tekrar deneyin."}
      </p>
      <Button onClick={reset}>Tekrar Dene</Button>
    </div>
  );
}
