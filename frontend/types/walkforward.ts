export type WalkForwardListItem = {
  id: number;
  created_at: string;
  strategy_name: string;
  symbol: string;
  timeframe: string;
  mode: string;
  status: string;
  robustness_score: number;
  wfe: number;
  consistency_score: number;
  average_sharpe: number;
  average_drawdown: number;
  deployment_decision: string;
};

export type WalkForwardDetail = {
  id: number;
  strategy_name: string;
  symbol: string;
  timeframe: string;
  mode: string;
  status: string;
  parameters: Record<string, unknown>;
  aggregated_metrics: Record<string, number | string>;
  combined_equity_curve: Array<{ timestamp: string; equity: number }>;
  monte_carlo_results: Record<string, number>;
  deployment_decision: { decision?: string; approved?: boolean; checks?: Record<string, boolean> };
  overfit_warnings: Array<Record<string, unknown>>;
  report: { charts?: Record<string, string> };
  windows: Array<{
    id: number;
    window_id: number;
    train_start: string;
    train_end: string;
    test_start: string;
    test_end: string;
    best_params: Record<string, unknown>;
    train_metrics: Record<string, number>;
    test_metrics: Record<string, number>;
    equity_curve: Array<{ timestamp: string; equity: number }>;
    trades: Array<Record<string, number | string>>;
    wfe: number;
    overfit_warning: boolean;
  }>;
};
