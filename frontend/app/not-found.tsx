import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center px-6 text-center">
      <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-border">
        <span className="text-2xl font-bold text-muted">404</span>
      </div>
      <h2 className="mb-2 text-xl font-semibold">Sayfa bulunamadı</h2>
      <p className="mb-6 max-w-md text-sm text-muted">
        Aradığınız sayfa mevcut değil veya taşınmış olabilir.
      </p>
      <Link href="/">
        <Button>Ana Sayfaya Dön</Button>
      </Link>
    </div>
  );
}
