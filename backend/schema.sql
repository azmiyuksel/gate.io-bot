CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  email VARCHAR(255) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  role VARCHAR(32) NOT NULL DEFAULT 'viewer',
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS api_keys (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  exchange VARCHAR(32) NOT NULL DEFAULT 'gateio',
  api_key_encrypted TEXT NOT NULL,
  api_secret_encrypted TEXT NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS positions (
  id SERIAL PRIMARY KEY,
  symbol VARCHAR(32) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'open',
  entry_price NUMERIC(24, 10) NOT NULL,
  quantity NUMERIC(24, 10) NOT NULL,
  stop_loss NUMERIC(24, 10) NOT NULL,
  take_profit NUMERIC(24, 10) NOT NULL,
  trailing_stop NUMERIC(24, 10),
  realized_pnl NUMERIC(24, 10) NOT NULL DEFAULT 0,
  exchange_stop_order_id VARCHAR(128),
  stop_placed_at TIMESTAMPTZ,
  opened_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  closed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_positions_exchange_stop_order_id ON positions(exchange_stop_order_id);

CREATE TABLE IF NOT EXISTS orders (
  id SERIAL PRIMARY KEY,
  exchange_order_id VARCHAR(128),
  position_id INTEGER REFERENCES positions(id),
  symbol VARCHAR(32) NOT NULL,
  side VARCHAR(16) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'open',
  price NUMERIC(24, 10),
  quantity NUMERIC(24, 10) NOT NULL,
  raw_response TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS trades (
  id SERIAL PRIMARY KEY,
  order_id INTEGER REFERENCES orders(id),
  symbol VARCHAR(32) NOT NULL,
  side VARCHAR(16) NOT NULL,
  price NUMERIC(24, 10) NOT NULL,
  quantity NUMERIC(24, 10) NOT NULL,
  fee NUMERIC(24, 10) NOT NULL DEFAULT 0,
  realized_pnl NUMERIC(24, 10) NOT NULL DEFAULT 0,
  traded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS strategy_settings (
  id SERIAL PRIMARY KEY,
  name VARCHAR(64) UNIQUE NOT NULL DEFAULT 'capital_preservation_v1',
  is_enabled BOOLEAN NOT NULL DEFAULT FALSE,
  max_capital_per_trade_pct NUMERIC(6, 4) NOT NULL DEFAULT 0.01,
  daily_max_loss_pct NUMERIC(6, 4) NOT NULL DEFAULT 0.02,
  weekly_max_loss_pct NUMERIC(6, 4) NOT NULL DEFAULT 0.05,
  max_open_positions INTEGER NOT NULL DEFAULT 3,
  min_reward_risk NUMERIC(6, 2) NOT NULL DEFAULT 2,
  atr_multiplier NUMERIC(6, 2) NOT NULL DEFAULT 1.5,
  trailing_stop_pct NUMERIC(6, 4) NOT NULL DEFAULT 0.01,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS system_logs (
  id SERIAL PRIMARY KEY,
  level VARCHAR(16) NOT NULL DEFAULT 'info',
  source VARCHAR(64) NOT NULL,
  message TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS historical_candles (
  id SERIAL PRIMARY KEY,
  symbol VARCHAR(32) NOT NULL,
  timeframe VARCHAR(8) NOT NULL,
  timestamp TIMESTAMPTZ NOT NULL,
  open NUMERIC(24, 10) NOT NULL,
  high NUMERIC(24, 10) NOT NULL,
  low NUMERIC(24, 10) NOT NULL,
  close NUMERIC(24, 10) NOT NULL,
  volume NUMERIC(24, 10) NOT NULL DEFAULT 0,
  source VARCHAR(32) NOT NULL DEFAULT 'gateio',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_candle_symbol_tf_ts UNIQUE (symbol, timeframe, timestamp)
);

CREATE INDEX IF NOT EXISTS ix_historical_candles_symbol ON historical_candles(symbol);
CREATE INDEX IF NOT EXISTS ix_historical_candles_timeframe ON historical_candles(timeframe);
CREATE INDEX IF NOT EXISTS ix_historical_candles_timestamp ON historical_candles(timestamp);

CREATE TABLE IF NOT EXISTS backtest_runs (
  id SERIAL PRIMARY KEY,
  strategy_name VARCHAR(128) NOT NULL DEFAULT 'ema_rsi_atr_v1',
  symbol VARCHAR(32) NOT NULL,
  timeframe VARCHAR(8) NOT NULL DEFAULT '1h',
  start_at TIMESTAMPTZ NOT NULL,
  end_at TIMESTAMPTZ NOT NULL,
  initial_cash NUMERIC(24, 10) NOT NULL DEFAULT 10000,
  status VARCHAR(32) NOT NULL DEFAULT 'pending',
  parameters JSONB NOT NULL DEFAULT '{}',
  metrics JSONB NOT NULL DEFAULT '{}',
  charts JSONB NOT NULL DEFAULT '{}',
  optimization_results JSONB NOT NULL DEFAULT '[]',
  walk_forward_results JSONB NOT NULL DEFAULT '[]',
  monte_carlo_results JSONB NOT NULL DEFAULT '{}',
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_backtest_runs_symbol ON backtest_runs(symbol);

CREATE TABLE IF NOT EXISTS backtest_trades (
  id SERIAL PRIMARY KEY,
  run_id INTEGER NOT NULL REFERENCES backtest_runs(id) ON DELETE CASCADE,
  symbol VARCHAR(32) NOT NULL,
  side VARCHAR(16) NOT NULL,
  entry_time TIMESTAMPTZ NOT NULL,
  exit_time TIMESTAMPTZ,
  entry_price NUMERIC(24, 10) NOT NULL,
  exit_price NUMERIC(24, 10),
  quantity NUMERIC(24, 10) NOT NULL,
  fee NUMERIC(24, 10) NOT NULL DEFAULT 0,
  pnl NUMERIC(24, 10) NOT NULL DEFAULT 0,
  pnl_pct NUMERIC(12, 6) NOT NULL DEFAULT 0,
  exit_reason VARCHAR(64)
);

CREATE INDEX IF NOT EXISTS ix_backtest_trades_symbol ON backtest_trades(symbol);

CREATE TABLE IF NOT EXISTS walkforward_runs (
  id SERIAL PRIMARY KEY,
  strategy_name VARCHAR(128) NOT NULL DEFAULT 'ema_rsi_atr_v1',
  symbol VARCHAR(32) NOT NULL,
  timeframe VARCHAR(8) NOT NULL DEFAULT '1h',
  mode VARCHAR(32) NOT NULL DEFAULT 'rolling',
  start_at TIMESTAMPTZ NOT NULL,
  end_at TIMESTAMPTZ NOT NULL,
  train_period_days INTEGER NOT NULL DEFAULT 365,
  test_period_days INTEGER NOT NULL DEFAULT 90,
  step_days INTEGER NOT NULL DEFAULT 90,
  n_trials INTEGER NOT NULL DEFAULT 30,
  initial_cash NUMERIC(24, 10) NOT NULL DEFAULT 10000,
  status VARCHAR(32) NOT NULL DEFAULT 'pending',
  parameters JSONB NOT NULL DEFAULT '{}',
  aggregated_metrics JSONB NOT NULL DEFAULT '{}',
  combined_equity_curve JSONB NOT NULL DEFAULT '[]',
  monte_carlo_results JSONB NOT NULL DEFAULT '{}',
  deployment_decision JSONB NOT NULL DEFAULT '{}',
  overfit_warnings JSONB NOT NULL DEFAULT '[]',
  report JSONB NOT NULL DEFAULT '{}',
  error TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_walkforward_runs_symbol ON walkforward_runs(symbol);

CREATE TABLE IF NOT EXISTS walkforward_windows (
  id SERIAL PRIMARY KEY,
  run_id INTEGER NOT NULL REFERENCES walkforward_runs(id) ON DELETE CASCADE,
  window_id INTEGER NOT NULL,
  train_start TIMESTAMPTZ NOT NULL,
  train_end TIMESTAMPTZ NOT NULL,
  test_start TIMESTAMPTZ NOT NULL,
  test_end TIMESTAMPTZ NOT NULL,
  best_params JSONB NOT NULL DEFAULT '{}',
  train_metrics JSONB NOT NULL DEFAULT '{}',
  test_metrics JSONB NOT NULL DEFAULT '{}',
  equity_curve JSONB NOT NULL DEFAULT '[]',
  trades JSONB NOT NULL DEFAULT '[]',
  wfe NUMERIC(12, 6) NOT NULL DEFAULT 0,
  overfit_warning BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS ix_walkforward_windows_window_id ON walkforward_windows(window_id);
