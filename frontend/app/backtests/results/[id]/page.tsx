import { BacktestResult } from "@/components/backtest-result";

export default function Page({ params }: { params: { id: string } }) {
  return <BacktestResult id={params.id} />;
}
