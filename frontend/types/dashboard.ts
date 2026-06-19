export type Position = {
  id: number;
  symbol: string;
  status: string;
  side: string;
  entry_price: string;
  quantity: string;
  stop_loss: string;
  take_profit: string;
  trailing_stop: string | null;
  breakeven_stop: boolean;
  realized_pnl: string;
  exchange_stop_order_id: string | null;
  stop_placed_at: string | null;
  opened_at: string | null;
};

export type Trade = {
  id: number;
  symbol: string;
  side: string;
  price: string;
  quantity: string;
  realized_pnl: string;
};

export type StrategySettings = {
  is_enabled: boolean;
  max_capital_per_trade_pct: string;
  daily_max_loss_pct: string;
  weekly_max_loss_pct: string;
  max_open_positions: number;
  min_reward_risk: string;
  atr_multiplier: string;
  trailing_stop_pct: string;
};

export type DashboardSummary = {
  total_balance: string;
  daily_pnl: string;
  weekly_pnl: string;
  bot_enabled: boolean;
  open_positions: Position[];
  recent_trades: Trade[];
  strategy: StrategySettings;
};
