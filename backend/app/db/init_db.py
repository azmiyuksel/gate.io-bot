from app.core.config import get_settings
from app.db.session import Base, engine
from app.models import ApiKey, Order, Position, StrategySettings, SystemLog, Trade, User, RefreshToken, AuditLog, Portfolio, PortfolioAsset, Allocation, RebalanceEvent, PortfolioMetric, RiskSnapshot, MarketRegimeRecord, RegimeTransition, RegimeFeatures, RegimeConfidence, RegimePerformance, StrategyBaseline, StrategyHealthLog, StrategyDriftScore, StrategyAlert, StrategyStateHistory, AccountSnapshot, ReconciliationLog, CircuitBreakerEvent, ExecutionOrder, ExecutionFill, ExecutionMetric, SlippageLog, LatencyLog, ExecutionReport, MarketDataRaw, MarketDataClean, MarketDataAnomaly, MarketDataHealthLog, DataQualityReport, ResearchStrategy, StrategyVersion, ResearchExperiment, HypothesisTest, FeatureRecord, ABTestResult, LearningCycle, KnowledgeEntry, DiscoveredFeature, StrategyRanking, PromotionRequest, LearningReport, PaperAccount, PaperEquityCurve, PaperLog, PaperOrder, PaperPosition, PaperTrade

_ = (ApiKey, Order, Position, StrategySettings, SystemLog, Trade, User, RefreshToken, AuditLog, Portfolio, PortfolioAsset, Allocation, RebalanceEvent, PortfolioMetric, RiskSnapshot, MarketRegimeRecord, RegimeTransition, RegimeFeatures, RegimeConfidence, RegimePerformance, StrategyBaseline, StrategyHealthLog, StrategyDriftScore, StrategyAlert, StrategyStateHistory, AccountSnapshot, ReconciliationLog, CircuitBreakerEvent, ExecutionOrder, ExecutionFill, ExecutionMetric, SlippageLog, LatencyLog, ExecutionReport, MarketDataRaw, MarketDataClean, MarketDataAnomaly, MarketDataHealthLog, DataQualityReport, ResearchStrategy, StrategyVersion, ResearchExperiment, HypothesisTest, FeatureRecord, ABTestResult, LearningCycle, KnowledgeEntry, DiscoveredFeature, StrategyRanking, PromotionRequest, LearningReport, PaperAccount, PaperEquityCurve, PaperLog, PaperOrder, PaperPosition, PaperTrade)


def init_db() -> None:
    settings = get_settings()
    if settings.environment == "local":
        Base.metadata.create_all(bind=engine)
    else:
        from alembic import command
        from alembic.config import Config

        alembic_cfg = Config("alembic.ini")
        alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)
        command.upgrade(alembic_cfg, "head")
