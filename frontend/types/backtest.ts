export type BacktestListItem = {
  id: number;
  created_at: string;
  strategy_name: string;
  symbol: string;
  timeframe: string;
  status: string;
  net_profit: number;
  sharpe_ratio: number;
  max_drawdown: number;
};

export type BacktestDetail = {
  id: number;
  strategy_name: string;
  symbol: string;
  timeframe: string;
  status: string;
  parameters: Record<string, unknown>;
  metrics: Record<string, number>;
  charts: Record<string, string>;
  optimization_results: Array<Record<string, unknown>>;
  walk_forward_results: Array<Record<string, unknown>>;
  monte_carlo_results: Record<string, number>;
  trades: Array<{
    id: number;
    entry_time: string;
    exit_time: string | null;
    entry_price: number;
    exit_price: number;
    quantity: number;
    pnl: number;
    pnl_pct: number;
    exit_reason: string;
  }>;
};
