from decimal import Decimal

from app.models.enums import MarketRegimeType
from app.market_regime.features import FeatureEngineer
from app.market_regime.trend import TrendClassifier
from app.market_regime.volatility import VolatilityClassifier
from app.market_regime.signals import RegimeSignalFilter


def test_feature_engineer_output() -> None:
    # Build synthetic candles
    candles = [
        {"open": 100.0, "high": 105.0, "low": 98.0, "close": 102.0, "volume": 1000.0, "timestamp": "2026-06-01T00:00:00Z"}
        for _ in range(50)
    ]
    df = FeatureEngineer.compute_features(candles)
    
    assert not df.empty
    assert len(df) == 50
    assert "ema_20" in df.columns
    assert "adx" in df.columns
    assert "realized_vol" in df.columns
    assert "rsi" in df.columns
    assert "obv" in df.columns
    # Verify no NaN values remain
    assert not df.isnull().any().any()


def test_trend_classifier() -> None:
    # 1. Trending Bull Row
    bull_row = {
        "close": 150.0,
        "ema_20": 140.0,
        "ema_50": 130.0,
        "ema_200": 120.0,
        "ema_200_slope": 0.002,
        "adx": 35.0
    }
    assert TrendClassifier.classify_trend(bull_row) == MarketRegimeType.trending_bull

    # 2. Trending Bear Row
    bear_row = {
        "close": 90.0,
        "ema_20": 100.0,
        "ema_50": 110.0,
        "ema_200": 120.0,
        "ema_200_slope": -0.002,
        "adx": 35.0
    }
    assert TrendClassifier.classify_trend(bear_row) == MarketRegimeType.trending_bear

    # 3. Sideways Row
    sideways_row = {
        "close": 120.0,
        "ema_20": 121.0,
        "ema_50": 119.0,
        "ema_200": 120.0,
        "ema_200_slope": 0.0,
        "adx": 15.0
    }
    assert TrendClassifier.classify_trend(sideways_row) == MarketRegimeType.sideways


def test_volatility_classifier() -> None:
    # 1. High Volatility Row
    high_vol_row = {
        "bb_width": 0.25,
        "realized_vol": 0.50,
        "close": 100.0,
        "open": 98.0
    }
    assert VolatilityClassifier.classify_volatility(high_vol_row, historical_mean_bbw=0.05) == MarketRegimeType.high_volatility

    # 2. Low Volatility Row
    low_vol_row = {
        "bb_width": 0.01,
        "realized_vol": 0.05,
        "close": 100.0,
        "open": 99.9
    }
    assert VolatilityClassifier.classify_volatility(low_vol_row, historical_mean_bbw=0.05) == MarketRegimeType.low_volatility


def test_regime_signal_filter() -> None:
    # 1. Low confidence block
    allowed, reason, mult = RegimeSignalFilter.should_allow_trade(
        "CapitalPreservationStrategy", MarketRegimeType.trending_bull, 0.45
    )
    assert not allowed
    assert reason == "low_confidence_block"
    assert mult == Decimal("0")

    # 2. Sideways filters out breakout strategies
    allowed, reason, mult = RegimeSignalFilter.should_allow_trade(
        "BreakoutStrategy", MarketRegimeType.sideways, 0.80
    )
    assert not allowed
    assert reason == "breakout_and_trend_disabled_in_range"

    # 3. High Volatility cuts risk multiplier
    allowed, reason, mult = RegimeSignalFilter.should_allow_trade(
        "CapitalPreservationStrategy", MarketRegimeType.high_volatility, 0.85
    )
    assert allowed
    # High Vol has default 0.5 risk multiplier
    assert mult == Decimal("0.5")
