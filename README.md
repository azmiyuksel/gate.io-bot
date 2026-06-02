# Gate.io Spot Capital Preservation Bot

Low-risk spot trading system scaffold for Gate.io. It is designed for slow, controlled execution, capital preservation, and auditable order state, not high-frequency trading.

## Stack

- Backend: Python 3.12, FastAPI, SQLAlchemy, PostgreSQL, Redis, APScheduler
- Exchange: Gate.io REST API with HMAC signing, rate limiting, retry/reconnect behavior, correct spot market-order semantics (BUY = quote amount, SELL = base amount, IOC), pair precision / min-notional rounding, and base/quote fee normalization
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

Get a token pair (short-lived access token + revocable refresh token):

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@example.com","password":"strong-password"}'
```

Auth endpoints (all under `/api/v1/auth`):

- `POST /auth/login` → `{access_token, refresh_token}` (rate-limited)
- `POST /auth/refresh` → rotates and returns a fresh token pair
- `POST /auth/logout` → revokes the supplied refresh token

Access tokens are short-lived (`ACCESS_TOKEN_EXPIRE_MINUTES`, default 15) so role
changes and revocation propagate quickly; refresh tokens are tracked server-side
(`refresh_tokens` table) and can be individually revoked.

Open the dashboard at `http://localhost:3000` and sign in with your email and
password — the session is persisted and access tokens are auto-refreshed.

> **API paths:** every endpoint is served under a single `/api/v1` prefix. The
> previous duplicate `/api/...` and unversioned bare paths have been removed.

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

For local development the FastAPI app creates SQLAlchemy tables on startup. For
any shared or production database, use the Alembic migrations instead:

```bash
cd backend
alembic upgrade head            # apply migrations
alembic revision --autogenerate -m "describe change"   # after editing models
```

The migration environment (`backend/migrations/env.py`) reads `DATABASE_URL`
from your settings. A reference `backend/schema.sql` is also kept for inspection.

## Tests & CI

```bash
cd backend
pip install -e '.[dev]'
ruff check app
pytest
```

GitHub Actions (`.github/workflows/ci.yml`) runs the backend lint + tests and a
frontend type-checking build on every push and pull request. Dependency updates
are automated via Dependabot (`.github/dependabot.yml`).

## Observability

- **Structured logging**: every process (API, scheduler, paper worker) emits
  JSON log lines via `app.core.logging`. API request logs carry a per-request
  `correlation_id`.
- **Correlation IDs**: the API accepts/echoes an `X-Request-ID` header and tags
  all logs produced while handling that request.
- **Health probes**: `GET /health` (liveness) and `GET /health/ready` (database
  readiness, returns 503 when the DB is unreachable).
- **Metrics**: `GET /metrics` exposes Prometheus counters and a latency
  histogram (`http_requests_total`, `http_request_duration_seconds`), labelled by
  method, route template and status.
- **Audit trail**: privileged actions (circuit-breaker trip/reset, strategy
  changes, manual position close) are written to `audit_logs` attributed to the
  acting user and mirrored to the structured log. Read them at
  `GET /api/v1/dashboard/audit` (admin only).
- **Error handling**: unhandled exceptions return `{"detail": "Internal server
  error", "request_id": ...}` and are logged with the correlation id, without
  leaking internals.
- **Trade economics**: `GET /api/v1/dashboard/economics` reports per-trade
  expected value, payoff ratio, the break-even win rate and the realized
  **edge** (win rate − break-even), plus the strategy's return vs simply
  buying and holding the primary asset (excess return / alpha).

## Backtest Engine

The backtest module lives in `backend/app/backtest`:

- `engine.py`: historical data loader and orchestration
- `broker.py`: virtual broker with market, limit, stop and stop-limit primitives and a **maker/taker cost model** — market entries and stop-loss exits pay the taker fee plus spread/slippage; resting limit entries and take-profit exits pay the lower maker fee with no slippage
- **Execution mode** (`execution_mode` parameter): `market` (taker, always fills next open) or `limit` (maker — posts a buy at the signal close and fills only if price trades to it, otherwise the signal is missed), so you can measure whether the edge survives net of realistic costs
- `portfolio.py`: cash, equity, realized/unrealized PnL and positions
- `strategy_runner.py`: `BaseStrategy` interface and EMA/RSI/ATR example strategy
- `engine.py`: signals are evaluated on a bar's close and **filled on the next bar's open** (no same-bar lookahead bias)
- `metrics.py`: total return, CAGR, drawdowns, Sharpe, Sortino, Calmar, win rate, profit factor, **compounding** Monte Carlo (bootstraps per-trade equity-fraction returns), **timeframe-aware annualization**, optional risk-free rate, and a **buy-and-hold benchmark** (`buy_hold_return`, `excess_return_vs_buy_hold`)
- `optimizer.py`: grid search and walk-forward analysis, with a **multiple-testing / selection-bias** assessment (expected maximum Sharpe under the null given N trials) that flags a best config as `likely_overfit` when it is no better than chance
- `reports.py`: Plotly JSON reports and PDF download adapter
- `models.py`: backtest dataclasses and supported timeframe metadata

API endpoints (under `/api/v1/backtests`):

- `POST /api/v1/backtests`
- `GET /api/v1/backtests`
- `GET /api/v1/backtests/{id}`
- `DELETE /api/v1/backtests/{id}`
- `POST /api/v1/backtests/{id}/optimize`
- `POST /api/v1/backtests/{id}/walk-forward`

Dashboard pages:

- `http://localhost:3000/backtests`
- `http://localhost:3000/backtests/create`
- `http://localhost:3000/backtests/results/{id}`

## Walk-Forward Analysis

The institutional WFA module lives in `backend/app/walkforward`:

- `engine.py`: training, Optuna optimization, out-of-sample test and result aggregation
- `splitter.py`: rolling and expanding time-series windows with a configurable **purge/embargo gap** between train and test (`embargo_days`, default 1) to prevent boundary leakage
- `optimizer.py`: Optuna search over EMA fast/slow, RSI period/entry, ATR multiplier and risk percent
- `validator.py`: overfit warnings and deployment gate checks
- `metrics.py`: WFE, consistency, robustness, aggregation and Monte Carlo on OOS trades
- `report.py`: Plotly report payload and PDF adapter
- `models.py`: WFA dataclasses

WFA API endpoints are exposed under `/api/v1/walkforward`:

- `POST /api/v1/walkforward/start`
- `GET /api/v1/walkforward`
- `GET /api/v1/walkforward/{id}`
- `GET /api/v1/walkforward/{id}/report`
- `DELETE /api/v1/walkforward/{id}`

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
`/api/v1/...`.

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

## Market Data Quality Engine (`backend/app/market_data_quality`)

Institutional data-integrity layer that every candle passes through before any
backtest, paper or live decision trusts it. Pipeline:

    raw -> normalize -> validate -> anomaly detection -> repair/flag -> emit clean

Modules:

- `validator.py`: OHLC consistency, zero/negative values, duplicate timestamps, excessive moves
- `normalization.py`: UTC timestamps, `BASE_QUOTE` symbol form, precision rounding, volume scaling
- `gap_detector.py`: missing candles, feed delay, websocket-disconnect gaps, interpolation
- `spike_detector.py`: configurable single-candle spike filter (`flag` / `smooth` / `ignore`)
- `volume_analyzer.py`: volume-spike and sudden-liquidity-drop detection
- `anomaly_detector.py`: z-score on returns + optional Isolation Forest (ML, corroborated)
- `cross_exchange_validator.py`: pluggable cross-exchange price divergence checks
- `data_health_score.py`: weighted 0-100 score (0.3 consistency + 0.3 completeness + 0.2 anomaly⁻¹ + 0.2 latency)
- `engine.py`: real-time orchestration, persistence and the trading gate

Health categories: Excellent (90-100), Good (75-89), Risky (50-74), Unreliable (<50).
Trading gate: `CLEAN` (normal), `DEGRADED` (50% risk), `INVALID` (pause, if `MDQ_PAUSE_ON_INVALID`).

Integration:

- **Ingestion**: `MarketDataIngestion` only promotes clean candles to `historical_candles`.
- **Live**: `TradingEngine.scan_symbol` runs the gate — invalid data pauses entries, degraded data halves size.
- **Backtest**: `backtest_support.BacktestDataQuality` applies the same rules and can inject spikes/gaps for robustness testing.
- **Alerts**: the scheduler notifies via Telegram when a feed turns degraded/invalid.

Tables: `market_data_raw`, `market_data_clean`, `market_data_anomalies`,
`market_data_health_logs`, `data_quality_reports`.

API (`/api/v1/data-quality`):

- `GET /data-quality/status?symbol=&timeframe=`
- `GET /data-quality/score?symbol=&timeframe=`
- `GET /data-quality/anomalies?symbol=&timeframe=&limit=`
- `GET /data-quality/health-logs?symbol=&timeframe=&limit=`
- `GET /data-quality/report?symbol=&timeframe=&hours=`
- `POST /data-quality/revalidate` (admin)

Dashboard page: `http://localhost:3000/data-quality` — health score, score breakdown,
health timeline, missing-data/anomaly trend, anomaly-type distribution and a live anomaly table.

## Strategy Research Lab (`backend/app/strategy_research`)

An R&D laboratory that discovers, evaluates and promotes trading strategies. A
*genome* is a parameter vector over a registered strategy template; the lab runs
an evolutionary loop and only lets robust strategies reach production.

Modules:

- `models.py`: templates, search space, genome, fitness function
- `generator.py`: indicator-combination, rule mutation, crossover, feature-driven generation
- `feature_store.py`: price/volume/volatility/trend/order-flow features scored by correlation-with-profit, importance and stability
- `hypothesis_builder.py`: generates and statistically tests market hypotheses (Welch t-test)
- `backtest_runner.py`: backtest + walk-forward + Monte Carlo + in/out-of-sample overfit check (reuses the production backtest engine)
- `evaluator.py`: fitness scoring, ranking and the production-promotion gate
- `ab_testing.py`: head-to-head comparison of two strategies on identical data
- `clustering.py`: K-Means family grouping and near-duplicate detection
- `repository.py`: signature-deduplicated persistence and versioning
- `engine.py`: the research-loop orchestrator

Fitness: `0.4*sharpe + 0.3*stability + 0.2*profit_factor - 0.1*drawdown`.

Promotion gate (all must pass, else `REJECTED`): Sharpe ≥ `RESEARCH_MIN_SHARPE`,
drawdown ≤ `RESEARCH_MAX_DRAWDOWN`, stability ≥ `RESEARCH_MIN_STABILITY`,
consistency ≥ `RESEARCH_MIN_CONSISTENCY`, trades ≥ `RESEARCH_MIN_TRADES`,
overfit = false.

The scheduler runs a research generation every 6 hours (in a worker thread) and
alerts on Telegram when strategies are promoted.

Tables: `research_strategies`, `strategy_versions`, `research_experiments`,
`hypothesis_tests`, `feature_store`, `ab_test_results`.

API (`/api/v1/research`):

- `POST /research/generate` (admin) — generate (and optionally evaluate) a strategy
- `POST /research/run` (admin) — run one evolutionary generation
- `GET /research/strategies` · `GET /research/leaderboard` · `GET /research/experiments`
- `GET /research/features` · `POST /research/features/recompute` (admin)
- `GET /research/hypotheses` · `POST /research/hypotheses/test` (admin)
- `GET /research/ab-tests`
- `POST /research/promote/{strategy_id}` (admin)

Dashboard page: `http://localhost:3000/strategy-research` — leaderboard, feature
importance, hypothesis results, experiment feed and one-click promotion.

## Auto Learning & Continuous Evolution (`backend/app/auto_learning`)

A continuous learning system that mines patterns, generates hypotheses, discovers
features, evolves strategies and ranks them — **but never deploys anything
automatically**. Every candidate must travel:

    Research → Validation → Paper Trading → Human Approval → Production

The engine only ever creates a `PromotionRequest` in `AWAITING_APPROVAL`; a human
must explicitly approve it. The layer never enables live trading, never changes
risk limits and never touches the circuit breaker (enforced structurally and by
`SafetyGuard`, with a test asserting state is unchanged across a cycle).

Modules:

- `knowledge_base.py`: long-term memory (strategies, trades, regime/feature performance, learned facts)
- `pattern_miner.py`: best/worst trade sets, regime-based and parameter-region patterns
- `hypothesis_generator.py`: generate + statistically test market hypotheses
- `feature_discovery.py`: derived features (ATR/Volume, RSI*ADX, volatility-regime score) auto-tested
- `strategy_evolution.py`: mutation/crossover/perturbation seeded from known-good parameters
- `meta_learning.py`: which family works in which regime, `strategy_family_score`, portfolio learning
- `validation_pipeline.py`: backtest → cross-validation → walk-forward → Monte Carlo → robustness → paper proxy
- `ranking_engine.py`: 30 robustness + 25 walk-forward + 20 stability + 15 sharpe + 10 drawdown (0-100)
- `safety.py`: hard safety locks + verifiable invariant snapshot
- `engine.py`: the learning loop + human-approval promotion workflow + weekly report

Promotion gate (then human approval): Sharpe > 1.5, Profit Factor > 1.3,
Consistency > 60%, Walk-Forward PASS, Monte Carlo PASS, overfit LOW, paper PASS.

The scheduler runs a learning cycle nightly and a weekly report (both in worker
threads), alerting on Telegram when strategies await approval.

Tables: `learning_cycles`, `knowledge_entries`, `discovered_features`,
`strategy_rankings`, `promotion_requests`, `learning_reports`.

API (`/api/v1/learning`):

- `POST /learning/start` (admin) — run one learning cycle
- `POST /learning/stop` (admin)
- `GET /learning/status` · `GET /learning/cycles`
- `GET /learning/hypotheses` · `GET /learning/features` · `GET /learning/rankings` · `GET /learning/knowledge`
- `GET /learning/promotion-requests`
- `POST /learning/promote-request/{strategy_id}` (admin) — **human approval gate**
- `POST /learning/promotion-requests/{request_id}/reject` (admin)
- `POST /learning/report` (admin)

Dashboard page: `http://localhost:3000/learning` — pending approvals with
approve/reject, strategy ranking, discovered features and the knowledge feed.

## Important Notes

This is an engineering scaffold, not financial advice. Start in read-only or tiny-size mode, verify Gate.io order minimums per symbol, and review every live permission before enabling the strategy.
