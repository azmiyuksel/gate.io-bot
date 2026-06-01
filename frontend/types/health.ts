export type StrategyHealthStatus = {
  health_score: string | number;
  drift_score: string | number;
  state: "ACTIVE" | "WARNING" | "CRITICAL" | "PAUSED" | string;
  failure_mode: string;
  anomaly: "NORMAL" | "ANOMALOUS" | string;
};

export type StrategyBaseline = {
  id: number;
  strategy_name: string;
  expected_sharpe: string | number;
  expected_win_rate: string | number;
  expected_profit_factor: string | number;
  expected_drawdown: string | number;
  expected_trade_frequency: string | number;
  created_at: string;
  updated_at: string;
};

export type StrategyHealthLog = {
  id: number;
  strategy_name: string;
  rolling_sharpe: string | number;
  rolling_win_rate: string | number;
  rolling_profit_factor: string | number;
  rolling_drawdown: string | number;
  expectancy: string | number;
  health_score: string | number;
  created_at: string;
};

export type StrategyAlert = {
  id: number;
  strategy_name: string;
  alert_level: "GREEN" | "YELLOW" | "ORANGE" | "RED" | string;
  message: string;
  action_taken: string;
  created_at: string;
};

export type StrategyStateTransition = {
  id: number;
  strategy_name: string;
  old_state: string;
  new_state: string;
  trigger_reason: string;
  created_at: string;
};
