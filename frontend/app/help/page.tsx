"use client";

import Link from "next/link";
import { ExternalLink } from "lucide-react";

import { Card } from "@/components/ui/card";
import { GLOSSARY, HELP_MODULES } from "@/lib/help-content";

const KIND_BADGE: Record<string, string> = {
  "Buton": "bg-primary/10 text-primary",
  "Liste": "bg-amber-100 text-amber-700",
  "Alan": "bg-blue-100 text-blue-700",
  "Onay kutusu": "bg-purple-100 text-purple-700",
  "Gösterge": "bg-gray-100 text-gray-600",
  "Sekme": "bg-teal-100 text-teal-700",
};

export default function HelpPage() {
  return (
    <main className="mx-auto max-w-5xl px-6 py-8">
      <header className="mb-6">
        <h1 className="text-2xl font-bold">Yardım & Kılavuz</h1>
        <p className="mt-1 text-sm text-muted">
          Her ekranın ne işe yaradığını, üzerindeki her butonun/listenin/alanın ne yaptığını ve
          hangi ayarı değiştirince neyin değişeceğini sade bir dille anlatır. Finans terimleri en
          altta <a href="#sozluk" className="text-primary underline">Sözlük</a> bölümünde açıklanır.
        </p>
        <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-800">
          Yeni başlıyorsan önce <strong>Paper Trading</strong> (sahte parayla) ekranını kullan. Gerçek
          para riske atmadan, her şeyin nasıl çalıştığını burada güvenle öğrenirsin.
        </div>
      </header>

      {/* İçindekiler */}
      <Card className="mb-6">
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">İçindekiler</h2>
        <ul className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
          {HELP_MODULES.map((m) => (
            <li key={m.id}>
              <a href={`#${m.id}`} className="flex items-center gap-2 rounded px-2 py-1 text-sm hover:bg-border/50">
                <m.icon size={15} className="text-primary" aria-hidden="true" />
                {m.title}
              </a>
            </li>
          ))}
          <li>
            <a href="#sozluk" className="flex items-center gap-2 rounded px-2 py-1 text-sm font-medium hover:bg-border/50">
              📖 Finansal Terimler Sözlüğü
            </a>
          </li>
        </ul>
      </Card>

      {/* Modüller */}
      <div className="space-y-6">
        {HELP_MODULES.map((m) => (
          <Card key={m.id} id={m.id} className="scroll-mt-20">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div className="flex items-center gap-2.5">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <m.icon size={18} aria-hidden="true" />
                </span>
                <div>
                  <h2 className="text-lg font-semibold">{m.title}</h2>
                  <code className="text-xs text-muted">{m.route}</code>
                </div>
              </div>
              <Link
                href={m.route}
                className="inline-flex items-center gap-1 rounded-md border border-border px-2.5 py-1 text-xs text-muted hover:text-foreground"
              >
                Ekrana git <ExternalLink size={12} />
              </Link>
            </div>

            <p className="text-sm text-foreground">{m.summary}</p>
            <p className="mt-2 rounded-md bg-gray-50 px-3 py-2 text-sm text-muted">
              <strong className="text-foreground">Sade anlatım: </strong>{m.forBeginner}
            </p>

            <h3 className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wide text-muted">
              Ekrandaki kontroller
            </h3>
            <ul className="divide-y divide-border">
              {m.items.map((it) => (
                <li key={it.name} className="flex flex-col gap-1 py-2 sm:flex-row sm:gap-3">
                  <div className="flex shrink-0 items-start gap-2 sm:w-64">
                    <span className={`mt-0.5 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${KIND_BADGE[it.kind] ?? "bg-gray-100 text-gray-600"}`}>
                      {it.kind}
                    </span>
                    <span className="text-sm font-medium">{it.name}</span>
                  </div>
                  <p className="text-sm text-muted">{it.desc}</p>
                </li>
              ))}
            </ul>

            {m.tips && m.tips.length > 0 && (
              <div className="mt-4 rounded-md border border-blue-100 bg-blue-50 px-3 py-2">
                <h3 className="text-xs font-semibold text-blue-800">💡 İpuçları</h3>
                <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-blue-900">
                  {m.tips.map((t) => (
                    <li key={t}>{t}</li>
                  ))}
                </ul>
              </div>
            )}
          </Card>
        ))}
      </div>

      {/* Sözlük */}
      <Card id="sozluk" className="mt-6 scroll-mt-20">
        <h2 className="mb-1 text-lg font-semibold">📖 Finansal Terimler Sözlüğü</h2>
        <p className="mb-4 text-sm text-muted">
          Ekranlarda geçen terimlerin gündelik dille açıklamaları.
        </p>
        <dl className="space-y-3">
          {GLOSSARY.map((g) => (
            <div key={g.term} className="border-b border-border pb-3">
              <dt className="text-sm font-semibold">{g.term}</dt>
              <dd className="mt-0.5 text-sm text-muted">{g.def}</dd>
            </div>
          ))}
        </dl>
      </Card>

      <p className="mt-6 text-center text-xs text-muted">
        Bir terim veya buton burada eksik/yanlışsa söyle, güncelleyelim.
      </p>
    </main>
  );
}
