export type PaperStatus = {
  account_id: number;
  status: "RUNNING" | "PAUSED" | "STOPPED";
  cash_balance: string;
  equity: string;
  initial_balance: string;
  realized_pnl: string;
  unrealized_pnl: string;
  exposure: string;
  metrics: PaperMetrics;
};

export type PaperPosition = {
  id: number;
  symbol: string;
  quantity: string;
  average_entry_price: string;
  last_price: string;
  unrealized_pnl: string;
  realized_pnl: string;
  stop_loss: string | null;
  take_profit: string | null;
  is_open: boolean;
};

export type PaperTrade = {
  id: number;
  symbol: string;
  side: string;
  price: string;
  quantity: string;
  fee: string;
  realized_pnl: string;
  traded_at: string;
};

export type PaperOrder = {
  id: number;
  symbol: string;
  side: string;
  order_type: string;
  status: string;
  requested_quantity: string;
  filled_quantity: string;
  average_fill_price: string | null;
  fee_paid: string;
  latency_ms: number;
  signal: Record<string, unknown>;
  created_at: string;
  filled_at: string | null;
};

export type PaperMetrics = {
  realized_pnl: number;
  win_rate_rolling_100: number;
  rolling_sharpe: number;
  drawdown: number;
};

export type PaperRiskStatus = {
  max_daily_loss_pct: number;
  current_daily_loss_pct: number;
  max_drawdown_pct: number;
  current_drawdown: number;
  max_exposure_pct: number;
  current_exposure: number;
  max_open_positions: number;
  current_open_positions: number;
  status: string;
};

export type PaperEquityPoint = {
  timestamp: string;
  equity: number;
  drawdown: number;
  exposure: number;
};

export type PaperLog = {
  id: number;
  level: string;
  event: string;
  message: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type PaperEconomics = {
  edge: {
    trades: number;
    win_rate: number;
    payoff_ratio: number;
    expectancy: number;
    expectancy_r: number;
    break_even_win_rate: number;
    edge: number;
    has_edge: boolean;
  };
  cost_bridge: {
    gross_pnl: number;
    total_fees: number;
    net_pnl: number;
    fee_pct_of_gross: number;
  };
};

export type PaperSignalDiagnostics = {
  window_hours: number;
  evaluations: number;
  last_evaluation_at: string | null;
  reason_counts: Record<string, number>;
  latest_by_symbol: Record<string, { reason: string; at: string | null }>;
};
