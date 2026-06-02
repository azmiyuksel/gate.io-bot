import { BacktestResult } from "@/components/backtest-result";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <BacktestResult id={id} />;
}
