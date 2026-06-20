from app.core.config import get_settings
from app.models import ApiKey, Order, Position, StrategySettings, SystemLog, Trade, WorkerHeartbeat, User, RefreshToken, AuditLog, Portfolio, PortfolioAsset, Allocation, RebalanceEvent, PortfolioMetric, RiskSnapshot, MarketRegimeRecord, RegimeTransition, RegimeFeatures, RegimeConfidence, RegimePerformance, StrategyBaseline, StrategyHealthLog, StrategyDriftScore, StrategyAlert, StrategyStateHistory, AccountSnapshot, ReconciliationLog, CircuitBreakerEvent, ExecutionOrder, ExecutionFill, ExecutionMetric, SlippageLog, LatencyLog, ExecutionReport, MarketDataRaw, MarketDataClean, MarketDataAnomaly, MarketDataHealthLog, DataQualityReport, ResearchStrategy, StrategyVersion, ResearchExperiment, HypothesisTest, FeatureRecord, ABTestResult, LearningCycle, KnowledgeEntry, DiscoveredFeature, StrategyRanking, PromotionRequest, LearningReport, PaperAccount, PaperEquityCurve, PaperLog, PaperOrder, PaperPosition, PaperTrade

_ = (ApiKey, Order, Position, StrategySettings, SystemLog, Trade, WorkerHeartbeat, User, RefreshToken, AuditLog, Portfolio, PortfolioAsset, Allocation, RebalanceEvent, PortfolioMetric, RiskSnapshot, MarketRegimeRecord, RegimeTransition, RegimeFeatures, RegimeConfidence, RegimePerformance, StrategyBaseline, StrategyHealthLog, StrategyDriftScore, StrategyAlert, StrategyStateHistory, AccountSnapshot, ReconciliationLog, CircuitBreakerEvent, ExecutionOrder, ExecutionFill, ExecutionMetric, SlippageLog, LatencyLog, ExecutionReport, MarketDataRaw, MarketDataClean, MarketDataAnomaly, MarketDataHealthLog, DataQualityReport, ResearchStrategy, StrategyVersion, ResearchExperiment, HypothesisTest, FeatureRecord, ABTestResult, LearningCycle, KnowledgeEntry, DiscoveredFeature, StrategyRanking, PromotionRequest, LearningReport, PaperAccount, PaperEquityCurve, PaperLog, PaperOrder, PaperPosition, PaperTrade)


# Arbitrary, stable key for the Postgres advisory lock that serializes schema
# migrations across the API + worker services (Railway boots them concurrently).
_MIGRATION_LOCK_KEY = 871042


def init_db() -> None:
    from alembic import command
    from alembic.config import Config

    settings = get_settings()
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)

    from app.db.session import engine

    # Serialize migrations cluster-wide: Railway starts the API + paper-worker +
    # scheduler concurrently, and each runs `upgrade head` at boot. With a pending
    # migration, two concurrent runs race and one fails ("column already exists").
    # A Postgres advisory lock makes the first runner migrate while the others
    # block, then see head and no-op. SQLite (local/tests) has no advisory locks
    # and no concurrency, so it runs unguarded.
    if engine.dialect.name == "postgresql":
        with engine.connect() as conn:
            conn.exec_driver_sql(f"SELECT pg_advisory_lock({_MIGRATION_LOCK_KEY})")
            try:
                _run_schema_sync(alembic_cfg, command)
            finally:
                conn.exec_driver_sql(f"SELECT pg_advisory_unlock({_MIGRATION_LOCK_KEY})")
    else:
        _run_schema_sync(alembic_cfg, command)


def _run_schema_sync(alembic_cfg, command) -> None:
    from sqlalchemy import inspect

    from app.db.session import engine

    inspector = inspect(engine)
    if not inspector.has_table("alembic_version"):
        # No alembic tracking yet — distinguish two cases instead of always
        # stamping (stamp only writes the version row, it does NOT create tables):
        #   * FRESH/EMPTY DB (e.g. a brand-new Railway Postgres): no domain tables
        #     exist, so RUN the migrations to actually create the schema. Stamping
        #     here would leave the DB empty AND the cleanup below would crash on
        #     `DELETE FROM paper_logs` (missing table).
        #   * LEGACY DB created via create_all before alembic was adopted: the
        #     tables already exist; stamp head to adopt them without re-creating.
        if inspector.has_table("users"):
            command.stamp(alembic_cfg, "head")
        else:
            command.upgrade(alembic_cfg, "head")
        _cleanup_paper_data()
        _mark_cleanup_done()
    else:
        command.upgrade(alembic_cfg, "head")
        _cleanup_if_needed()


def _cleanup_if_needed() -> None:
    from sqlalchemy import text
    from app.db.session import engine

    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT EXISTS (SELECT 1 FROM strategy_settings WHERE name = 'paper_cleanup_done')"
        )).fetchone()
        if not row or not row[0]:
            _cleanup_paper_data()
            _mark_cleanup_done()


def _cleanup_paper_data() -> None:
    """Clear stale paper trading data left over from create_all deployments."""
    from sqlalchemy import text
    from app.db.session import engine

    with engine.connect() as conn:
        tables = ("paper_logs", "paper_equity_curve", "paper_orders",
                   "paper_trades", "paper_positions")
        for t in tables:
            conn.execute(text(f"DELETE FROM {t}"))
        conn.execute(text(
            "UPDATE paper_accounts SET cash_balance = initial_balance, "
            "realized_pnl = 0, updated_at = NOW()"
        ))
        conn.commit()


def _mark_cleanup_done() -> None:
    from sqlalchemy import text
    from app.db.session import engine

    with engine.connect() as conn:
        # The marker is a sentinel row in strategy_settings. The numeric columns
        # are NOT NULL with no DB-level default (the model defaults are Python-side
        # only), so an INSERT that omits them raises NotNullViolation — which made
        # this marker NEVER persist, so _cleanup_if_needed re-ran _cleanup_paper_data
        # on EVERY boot/redeploy, wiping all paper logs/trades/positions each time.
        # Supply the full set of required columns (values chosen to satisfy the
        # table CheckConstraints) so the marker is written exactly once.
        conn.execute(text(
            "INSERT INTO strategy_settings "
            "(name, is_enabled, max_capital_per_trade_pct, daily_max_loss_pct, "
            " weekly_max_loss_pct, max_open_positions, min_reward_risk, "
            " atr_multiplier, trailing_stop_pct) "
            "VALUES ('paper_cleanup_done', false, 0.08, 0.05, 0.18, 10, 1.5, 2.0, 0.015) "
            "ON CONFLICT (name) DO NOTHING"
        ))
        conn.commit()
