export type PortfolioAsset = {
  id: number;
  symbol: string;
  position_size: string;
  average_entry_price: string;
  current_price: string;
  unrealized_pnl: string;
  risk_contribution: string;
  updated_at: string;
};

export type Allocation = {
  id: number;
  target_type: string;
  target_name: string;
  weight: string;
  allocated_amount: string;
  performance_score: string;
  risk_adjusted_return: string;
  correlation_penalty: string;
  stability_score: string;
  drawdown_adjustment: string;
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
  total_equity: string;
  sharpe_ratio: string;
  drawdown: string;
  correlation_risk_score: string;
  exposure_per_asset: Record<string, number>;
  exposure_per_strategy: Record<string, number>;
  volatility_adjusted_return: string;
};

export type RiskSnapshot = {
  id: number;
  timestamp: string;
  scenario_name: string;
  simulated_loss: string;
  limit_status: string;
  metrics_snapshot: Record<string, any>;
};

export type Portfolio = {
  id: number;
  name: string;
  description: string | null;
  is_active: boolean;
  total_equity: string;
  cash_balance: string;
  daily_max_risk_pct: string;
  weekly_max_risk_pct: string;
  monthly_max_risk_pct: string;
  created_at: string;
  updated_at: string;
  assets: PortfolioAsset[];
  allocations: Allocation[];
};
