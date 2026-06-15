from app.core.config import get_settings
from app.models import ApiKey, Order, Position, StrategySettings, SystemLog, Trade, User, RefreshToken, AuditLog, Portfolio, PortfolioAsset, Allocation, RebalanceEvent, PortfolioMetric, RiskSnapshot, MarketRegimeRecord, RegimeTransition, RegimeFeatures, RegimeConfidence, RegimePerformance, StrategyBaseline, StrategyHealthLog, StrategyDriftScore, StrategyAlert, StrategyStateHistory, AccountSnapshot, ReconciliationLog, CircuitBreakerEvent, ExecutionOrder, ExecutionFill, ExecutionMetric, SlippageLog, LatencyLog, ExecutionReport, MarketDataRaw, MarketDataClean, MarketDataAnomaly, MarketDataHealthLog, DataQualityReport, ResearchStrategy, StrategyVersion, ResearchExperiment, HypothesisTest, FeatureRecord, ABTestResult, LearningCycle, KnowledgeEntry, DiscoveredFeature, StrategyRanking, PromotionRequest, LearningReport, PaperAccount, PaperEquityCurve, PaperLog, PaperOrder, PaperPosition, PaperTrade

_ = (ApiKey, Order, Position, StrategySettings, SystemLog, Trade, User, RefreshToken, AuditLog, Portfolio, PortfolioAsset, Allocation, RebalanceEvent, PortfolioMetric, RiskSnapshot, MarketRegimeRecord, RegimeTransition, RegimeFeatures, RegimeConfidence, RegimePerformance, StrategyBaseline, StrategyHealthLog, StrategyDriftScore, StrategyAlert, StrategyStateHistory, AccountSnapshot, ReconciliationLog, CircuitBreakerEvent, ExecutionOrder, ExecutionFill, ExecutionMetric, SlippageLog, LatencyLog, ExecutionReport, MarketDataRaw, MarketDataClean, MarketDataAnomaly, MarketDataHealthLog, DataQualityReport, ResearchStrategy, StrategyVersion, ResearchExperiment, HypothesisTest, FeatureRecord, ABTestResult, LearningCycle, KnowledgeEntry, DiscoveredFeature, StrategyRanking, PromotionRequest, LearningReport, PaperAccount, PaperEquityCurve, PaperLog, PaperOrder, PaperPosition, PaperTrade)


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
        # Tables exist from a previous create_all() but alembic_version doesn't.
        # Stamp the head revision so Alembic knows all tables are already present,
        # then future deploys only apply pending migrations.
        command.stamp(alembic_cfg, "head")
        # One-time cleanup of old paper trading data from the create_all era.
        _cleanup_paper_data()
    else:
        command.upgrade(alembic_cfg, "head")


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
