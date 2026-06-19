from app.core.config import get_settings
from app.models import ApiKey, Order, Position, StrategySettings, SystemLog, Trade, WorkerHeartbeat, User, RefreshToken, AuditLog, Portfolio, PortfolioAsset, Allocation, RebalanceEvent, PortfolioMetric, RiskSnapshot, MarketRegimeRecord, RegimeTransition, RegimeFeatures, RegimeConfidence, RegimePerformance, StrategyBaseline, StrategyHealthLog, StrategyDriftScore, StrategyAlert, StrategyStateHistory, AccountSnapshot, ReconciliationLog, CircuitBreakerEvent, ExecutionOrder, ExecutionFill, ExecutionMetric, SlippageLog, LatencyLog, ExecutionReport, MarketDataRaw, MarketDataClean, MarketDataAnomaly, MarketDataHealthLog, DataQualityReport, ResearchStrategy, StrategyVersion, ResearchExperiment, HypothesisTest, FeatureRecord, ABTestResult, LearningCycle, KnowledgeEntry, DiscoveredFeature, StrategyRanking, PromotionRequest, LearningReport, PaperAccount, PaperEquityCurve, PaperLog, PaperOrder, PaperPosition, PaperTrade

_ = (ApiKey, Order, Position, StrategySettings, SystemLog, Trade, WorkerHeartbeat, User, RefreshToken, AuditLog, Portfolio, PortfolioAsset, Allocation, RebalanceEvent, PortfolioMetric, RiskSnapshot, MarketRegimeRecord, RegimeTransition, RegimeFeatures, RegimeConfidence, RegimePerformance, StrategyBaseline, StrategyHealthLog, StrategyDriftScore, StrategyAlert, StrategyStateHistory, AccountSnapshot, ReconciliationLog, CircuitBreakerEvent, ExecutionOrder, ExecutionFill, ExecutionMetric, SlippageLog, LatencyLog, ExecutionReport, MarketDataRaw, MarketDataClean, MarketDataAnomaly, MarketDataHealthLog, DataQualityReport, ResearchStrategy, StrategyVersion, ResearchExperiment, HypothesisTest, FeatureRecord, ABTestResult, LearningCycle, KnowledgeEntry, DiscoveredFeature, StrategyRanking, PromotionRequest, LearningReport, PaperAccount, PaperEquityCurve, PaperLog, PaperOrder, PaperPosition, PaperTrade)


def init_db() -> None:
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    settings = get_settings()
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)

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
        conn.execute(text(
            "INSERT INTO strategy_settings (name, is_enabled) "
            "VALUES ('paper_cleanup_done', true) "
            "ON CONFLICT (name) DO NOTHING"
        ))
        conn.commit()
