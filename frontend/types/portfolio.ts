export type PortfolioAsset = {
  id: number;
  symbol: string;
  position_size: number;
  average_entry_price: number;
  current_price: number;
  unrealized_pnl: number;
  risk_contribution: number;
  updated_at: string;
};

export type Allocation = {
  id: number;
  target_type: string;
  target_name: string;
  weight: number;
  allocated_amount: number;
  performance_score: number;
  risk_adjusted_return: number;
  correlation_penalty: number;
  stability_score: number;
  drawdown_adjustment: number;
};

export type RebalanceEvent = {
  id: number;
  trigger_reason: string;
  previous_weights: Record<string, number>;
  new_weights: Record<string, number>;
  execution_log: string;
  status: string;
  created_at: string;
};

export type PortfolioMetric = {
  id: number;
  timestamp: string;
  total_equity: number;
  sharpe_ratio: number;
  drawdown: number;
  correlation_risk_score: number;
  exposure_per_asset: Record<string, number>;
  exposure_per_strategy: Record<string, number>;
  volatility_adjusted_return: number;
};

export type RiskSnapshot = {
  id: number;
  timestamp: string;
  scenario_name: string;
  simulated_loss: number;
  limit_status: string;
  metrics_snapshot: Record<string, any>;
};

export type PortfolioCorrelations = {
  symbols: string[];
  matrix: Record<string, Record<string, number>>;
  high_correlation_pairs: [string, string, number][];
  risk_score: number;
  timeframe: string;
  data_available: boolean;
};

export type Portfolio = {
  id: number;
  name: string;
  description: string | null;
  is_active: boolean;
  total_equity: number;
  cash_balance: number;
  peak_equity: number;
  daily_max_risk_pct: number;
  weekly_max_risk_pct: number;
  monthly_max_risk_pct: number;
  created_at: string;
  updated_at: string;
  assets: PortfolioAsset[];
  allocations: Allocation[];
};

export type StrategyPerformance = {
  name: string;
  sharpe_ratio: number;
  win_rate: number;
  profit_factor: number;
  max_drawdown: number;
  stability_score: number;
};
