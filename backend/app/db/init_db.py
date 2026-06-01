from app.db.session import Base, engine
from app.models import ApiKey, Order, Position, StrategySettings, SystemLog, Trade, User, Portfolio, PortfolioAsset, Allocation, RebalanceEvent, PortfolioMetric, RiskSnapshot, MarketRegimeRecord, RegimeTransition, RegimeFeatures, RegimeConfidence, RegimePerformance, StrategyBaseline, StrategyHealthLog, StrategyDriftScore, StrategyAlert, StrategyStateHistory, AccountSnapshot, ReconciliationLog, CircuitBreakerEvent

_ = (ApiKey, Order, Position, StrategySettings, SystemLog, Trade, User, Portfolio, PortfolioAsset, Allocation, RebalanceEvent, PortfolioMetric, RiskSnapshot, MarketRegimeRecord, RegimeTransition, RegimeFeatures, RegimeConfidence, RegimePerformance, StrategyBaseline, StrategyHealthLog, StrategyDriftScore, StrategyAlert, StrategyStateHistory, AccountSnapshot, ReconciliationLog, CircuitBreakerEvent)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
