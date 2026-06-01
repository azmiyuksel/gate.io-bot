# Gate.io Spot Capital Preservation Bot

Low-risk spot trading system scaffold for Gate.io. It is designed for slow, controlled execution, capital preservation, and auditable order state, not high-frequency trading.

## Stack

- Backend: Python 3.12, FastAPI, SQLAlchemy, PostgreSQL, Redis, APScheduler
- Exchange: Gate.io REST API with HMAC signing, rate limiting, retry/reconnect behavior
- Frontend: Next.js, TypeScript, TailwindCSS, shadcn-style local components
- Security: JWT auth, password hashing, optional Fernet API key encryption, RBAC
- Notifications: Telegram for opens, closes, stop-loss events and daily report

## Strategy V1

- Trend filter: only allow long entries above 200 EMA
- Entry filter: RSI(14) below 35, close to 20 EMA, no excessive 24h volatility
- Position sizing: max 1% of equity per trade
- Risk limits: 2% daily max loss, 5% weekly max loss, max 3 open positions
- Exit: ATR stop-loss, minimum 1:2 reward/risk take profit, trailing stop, manual close

## Quick Start

```bash
cp .env.example .env
docker compose up --build
```

Create an admin user:

```bash
docker compose exec backend python app/scripts_create_admin.py --email admin@example.com --password strong-password
```

Get a JWT token:

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"strong-password"}'
```

Open the dashboard at `http://localhost:3000` and paste the JWT token into the token field.

## Environment

Set these in `.env` before live use:

- `GATEIO_API_KEY`
- `GATEIO_API_SECRET`
- `SECRET_KEY`
- `FERNET_KEY` from `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Keep `BOT_ENABLED=false` until you have verified API permissions, symbols, order minimums and account balances.

## Database

The SQL schema is in `backend/schema.sql`. The FastAPI app also creates SQLAlchemy tables on startup for local development.

## Tests

```bash
cd backend
pip install -e '.[dev]'
pytest
```

## Backtest Engine

The backtest module lives in `backend/app/backtest`:

- `engine.py`: historical data loader and orchestration
- `broker.py`: virtual broker with market, limit, stop and stop-limit trigger simulation primitives
- `portfolio.py`: cash, equity, realized/unrealized PnL and positions
- `strategy_runner.py`: `BaseStrategy` interface and EMA/RSI/ATR example strategy
- `metrics.py`: total return, CAGR, drawdowns, Sharpe, Sortino, Calmar, win rate, profit factor and Monte Carlo
- `optimizer.py`: grid search and walk-forward analysis
- `reports.py`: Plotly JSON reports and PDF download adapter
- `models.py`: backtest dataclasses and supported timeframe metadata

API endpoints are available under both `/api/v1/backtests` and `/api/backtests`:

- `POST /api/backtests`
- `GET /api/backtests`
- `GET /api/backtests/{id}`
- `DELETE /api/backtests/{id}`
- `POST /api/backtests/{id}/optimize`
- `POST /api/backtests/{id}/walk-forward`

Dashboard pages:

- `http://localhost:3000/backtests`
- `http://localhost:3000/backtests/create`
- `http://localhost:3000/backtests/results/{id}`

## Walk-Forward Analysis

The institutional WFA module lives in `backend/app/walkforward`:

- `engine.py`: training, Optuna optimization, out-of-sample test and result aggregation
- `splitter.py`: rolling and expanding time-series windows
- `optimizer.py`: Optuna search over EMA fast/slow, RSI period/entry, ATR multiplier and risk percent
- `validator.py`: overfit warnings and deployment gate checks
- `metrics.py`: WFE, consistency, robustness, aggregation and Monte Carlo on OOS trades
- `report.py`: Plotly report payload and PDF adapter
- `models.py`: WFA dataclasses

WFA API endpoints are exposed under `/walkforward`, `/api/walkforward`, and `/api/v1/walkforward`:

- `POST /walkforward/start`
- `GET /walkforward`
- `GET /walkforward/{id}`
- `GET /walkforward/{id}/report`
- `DELETE /walkforward/{id}`

Deployment gate:

- Robustness Score > 70
- Consistency > 60%
- WFE > 50%
- Average Sharpe > 1.5
- Worst Max Drawdown < 15%
- Overfit Warning = False

If any condition fails, the result is stored as `AUTO_DEPLOYMENT_REJECT`.

Dashboard pages:

- `http://localhost:3000/walk-forward`
- `http://localhost:3000/walk-forward/{id}`

## Live Safety Modules

These modules harden the bot for live operation. They run automatically from the
scheduler (`backend/app/workers/scheduler.py`) and are exposed via the API under
`/api/v1/...`, `/api/...` and bare paths.

### Account & Equity (`backend/app/account`)

Replaces the previously hard-coded equity with real Gate.io balances. `AccountManager`
fetches spot balances, marks open positions to market, persists an `AccountSnapshot`
and degrades to the last snapshot (or `FALLBACK_EQUITY`) when the exchange is
unreachable. Risk checks, the dashboard and the circuit breaker all read equity here.

- `GET /account/equity` — total equity, peak equity, drawdown %
- `GET /account/snapshot` — latest snapshot
- `GET /account/history` — snapshot history
- `POST /account/refresh` (admin) — pull a fresh live snapshot

### Reconciliation (`backend/app/reconciliation`)

Orders were stored as `open` on submission and never updated. `ReconciliationEngine`
pulls authoritative order state from Gate.io, updates local statuses, aligns position
entry prices with real average deal prices and writes an audit trail. Runs every cycle
and once on startup (`recover_on_startup`) for crash recovery.

- `POST /reconciliation/run` (admin) — reconcile open orders now
- `GET /reconciliation/logs` — reconciliation audit log

### Circuit Breaker (`backend/app/services/risk/circuit_breaker.py`)

Global kill-switch. Trips automatically on a breached daily/weekly realized-loss limit
or `MAX_ACCOUNT_DRAWDOWN_PCT` drawdown, and can be tripped/reset manually. Tripping
disables the strategy so no new entries are opened; `TradingEngine.scan_symbol` refuses
to trade while tripped.

- `GET /circuit-breaker` — current state
- `POST /circuit-breaker/trip` (admin) — manual halt
- `POST /circuit-breaker/reset` (admin) — re-arm

### Market Data (`backend/app/market_data`)

A `GateIOWebSocketClient` streams `spot.tickers` into a shared in-memory `price_cache`
(read by the account/reconciliation layers), and `MarketDataIngestion` upserts OHLCV
into `historical_candles` on a schedule so backtests, walk-forward and the regime engine
stay fed.

- `GET /market-data/latest` — latest cached prices
- `GET /market-data/candles?symbol=&interval=&limit=` — stored candles
- `POST /market-data/ingest` (admin) — ingest candles now

## Important Notes

This is an engineering scaffold, not financial advice. Start in read-only or tiny-size mode, verify Gate.io order minimums per symbol, and review every live permission before enabling the strategy.
