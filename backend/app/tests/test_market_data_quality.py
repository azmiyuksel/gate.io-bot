from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.market_data_quality.anomaly_detector import AnomalyDetector
from app.market_data_quality.backtest_support import BacktestDataQuality
from app.market_data_quality.cross_exchange_validator import CrossExchangeValidator
from app.market_data_quality.data_health_score import DataHealthScorer
from app.market_data_quality.engine import MarketDataQualityEngine
from app.market_data_quality.gap_detector import GapDetector
from app.market_data_quality.models import (
    AnomalyType,
    CandleData,
    DataQualityCategory,
    DataTradeStatus,
    ValidationCode,
)
from app.market_data_quality.normalization import (
    DataNormalizer,
    normalize_symbol,
    normalize_timestamp,
)
from app.market_data_quality.spike_detector import SpikeDetector
from app.market_data_quality.validator import CandleValidator
from app.market_data_quality.volume_analyzer import VolumeAnalyzer
from app.models.entities import MarketDataAnomaly, MarketDataClean, MarketDataHealthLog

BASE_TS = int(datetime(2024, 1, 1, tzinfo=UTC).timestamp())


def make_candle(i: int, price: float, volume: float = 100.0, interval: int = 3600) -> CandleData:
    p = Decimal(str(price))
    return CandleData(
        symbol="BTC_USDT",
        timeframe="1h",
        timestamp=datetime.fromtimestamp(BASE_TS + i * interval, UTC),
        open=p,
        high=p * Decimal("1.005"),
        low=p * Decimal("0.995"),
        close=p,
        volume=Decimal(str(volume)),
        source="gateio",
    )


def make_dicts(n: int, base: float = 100.0, step: float = 0.1, interval: int = 3600) -> list[dict]:
    out = []
    for i in range(n):
        price = base + i * step
        out.append(
            {
                "timestamp": BASE_TS + i * interval,
                "open": price,
                "high": price * 1.005,
                "low": price * 0.995,
                "close": price,
                "volume": 100.0,
            }
        )
    return out


# --------------------------------------------------------------------------
# Validator
# --------------------------------------------------------------------------
def test_validator_ohlc_consistency() -> None:
    v = CandleValidator()
    bad = make_candle(1, 100.0)
    bad.high = Decimal("99")  # high below open/close
    result = v.validate(bad, None)
    assert not result.is_valid
    assert ValidationCode.high_below_components in result.codes


def test_validator_rejects_non_positive_and_negative_volume() -> None:
    v = CandleValidator()
    c = make_candle(1, 100.0)
    c.close = Decimal("0")
    c.volume = Decimal("-5")
    result = v.validate(c, None)
    assert not result.is_valid
    assert ValidationCode.non_positive_price in result.codes
    assert ValidationCode.negative_volume in result.codes


def test_validator_duplicate_timestamp_and_excessive_move() -> None:
    v = CandleValidator(spike_threshold_pct=0.10)
    prev = make_candle(1, 100.0)
    dup = make_candle(1, 150.0)  # same timestamp, +50% move
    result = v.validate(dup, prev)
    assert ValidationCode.duplicate_timestamp in result.codes
    assert ValidationCode.excessive_move in result.codes


# --------------------------------------------------------------------------
# Normalization
# --------------------------------------------------------------------------
def test_normalize_symbol_variants() -> None:
    assert normalize_symbol("btc-usdt") == "BTC_USDT"
    assert normalize_symbol("BTC/USDT") == "BTC_USDT"
    assert normalize_symbol("BTCUSDT") == "BTC_USDT"


def test_normalize_timestamp_handles_ms_and_seconds() -> None:
    sec = normalize_timestamp(BASE_TS)
    ms = normalize_timestamp(BASE_TS * 1000)
    assert sec == ms
    assert sec.tzinfo is not None


def test_normalizer_rounds_and_canonicalizes() -> None:
    norm = DataNormalizer()
    c = make_candle(1, 100.123456789987, volume=10.0)
    c.symbol = "btcusdt"
    out = norm.normalize_candle(c)
    assert out.symbol == "BTC_USDT"
    assert out.close.as_tuple().exponent == -10  # 10 dp precision


# --------------------------------------------------------------------------
# Gap detector
# --------------------------------------------------------------------------
def test_gap_detector_missing_and_disconnect() -> None:
    candles = [make_candle(i, 100.0) for i in range(10)]
    del candles[5]  # one missing hour
    del candles[6]  # creates a larger hole too
    report = GapDetector("1h").analyze(candles, now=candles[-1].timestamp)
    assert report.missing_count >= 1


def test_gap_detector_feed_delay() -> None:
    candles = [make_candle(i, 100.0) for i in range(5)]
    now = candles[-1].timestamp + timedelta(hours=10)
    report = GapDetector("1h").analyze(candles, now=now)
    assert report.feed_delayed is True


# --------------------------------------------------------------------------
# Spike detector
# --------------------------------------------------------------------------
def test_spike_detector_flag_mode() -> None:
    det = SpikeDetector(threshold_pct=0.10, mode="flag")
    prev = make_candle(0, 100.0)
    spike = make_candle(1, 130.0)  # +30%
    res = det.detect(spike, prev)
    assert res.is_spike
    assert res.finding.anomaly_type == AnomalyType.flash_pump
    assert res.repaired is spike  # flag keeps candle


def test_spike_detector_ignore_and_smooth() -> None:
    prev = make_candle(0, 100.0)
    spike = make_candle(1, 130.0)

    ignored = SpikeDetector(threshold_pct=0.10, mode="ignore").detect(spike, prev)
    assert ignored.repaired is None

    smoothed = SpikeDetector(threshold_pct=0.10, mode="smooth").detect(spike, prev)
    assert smoothed.repaired is not None
    # Clamped to within +10% of previous close.
    assert smoothed.repaired.close <= Decimal("110.0001")


# --------------------------------------------------------------------------
# Volume analyzer
# --------------------------------------------------------------------------
def test_volume_spike_and_liquidity_drop() -> None:
    history = [make_candle(i, 100.0, volume=100.0) for i in range(40)]
    analyzer = VolumeAnalyzer(spike_multiple=8.0, liquidity_drop_pct=0.10)

    spike = make_candle(41, 100.0, volume=2000.0)
    findings = analyzer.analyze(spike, history)
    assert any(f.anomaly_type == AnomalyType.volume_spike for f in findings)

    drop = make_candle(42, 100.0, volume=1.0)
    findings2 = analyzer.analyze(drop, history)
    assert any(f.anomaly_type == AnomalyType.liquidity_drop for f in findings2)


# --------------------------------------------------------------------------
# Anomaly detector (z-score)
# --------------------------------------------------------------------------
def test_anomaly_detector_zscore_flags_spike() -> None:
    history = [make_candle(i, 100.0 + i * 0.01) for i in range(60)]
    detector = AnomalyDetector(zscore_threshold=4.0, enable_ml=False)
    spike = make_candle(60, 140.0)  # large jump vs tiny historical vol
    findings = detector.detect(spike, history)
    assert len(findings) >= 1


# --------------------------------------------------------------------------
# Health score
# --------------------------------------------------------------------------
def test_health_score_weighting_and_categories() -> None:
    scorer = DataHealthScorer()
    perfect = scorer.compute(
        total_candles=100, invalid_candles=0, expected_candles=100, missing_candles=0,
        anomalies=0, feed_lag_seconds=0, interval_seconds=3600,
    )
    assert perfect.score == 100.0
    assert perfect.category == DataQualityCategory.excellent
    assert perfect.trade_status == DataTradeStatus.clean

    bad = scorer.compute(
        total_candles=100, invalid_candles=60, expected_candles=100, missing_candles=40,
        anomalies=50, feed_lag_seconds=36000, interval_seconds=3600,
    )
    assert bad.score < 50
    assert bad.trade_status == DataTradeStatus.invalid


# --------------------------------------------------------------------------
# Cross exchange
# --------------------------------------------------------------------------
def test_cross_exchange_divergence_detected() -> None:
    validator = CrossExchangeValidator(
        sources={"binance": lambda s: Decimal("100")}, threshold_pct=0.01
    )
    result = validator.validate("BTC_USDT", Decimal("105"))  # 5% off
    assert result.diverged
    assert result.finding.anomaly_type == AnomalyType.cross_exchange_divergence


# --------------------------------------------------------------------------
# Backtest support
# --------------------------------------------------------------------------
def test_backtest_clean_drops_structural() -> None:
    candles = [make_candle(i, 100.0) for i in range(10)]
    candles[4].high = Decimal("1")  # structural break
    res = BacktestDataQuality(spike_mode="flag").clean(candles)
    assert res.dropped >= 1
    assert res.total == 10


def test_backtest_inject_spikes_changes_series() -> None:
    candles = [make_candle(i, 100.0) for i in range(50)]
    spiked = BacktestDataQuality.inject_spikes(candles, probability=1.0, magnitude=0.3)
    assert any(c.source.endswith("spiked") for c in spiked)


# --------------------------------------------------------------------------
# Engine pipeline (DB)
# --------------------------------------------------------------------------
def test_engine_clean_series_high_health(db_session) -> None:
    engine = MarketDataQualityEngine(db_session)
    dicts = make_dicts(60)
    now = datetime.fromtimestamp(BASE_TS + 59 * 3600, UTC)
    result = engine.ingest(dicts, "BTC_USDT", "1h", now=now)

    assert result.total == 60
    assert result.clean_emitted == 60
    assert result.anomalies == 0
    assert result.health.score >= 90
    assert db_session.query(MarketDataClean).count() == 60
    assert db_session.query(MarketDataHealthLog).count() == 1
    assert engine.trade_status("BTC_USDT", "1h") == DataTradeStatus.clean


def test_engine_detects_injected_spike(db_session) -> None:
    engine = MarketDataQualityEngine(db_session)
    dicts = make_dicts(60)
    # Inject a 40% spike on the last candle.
    dicts[-1]["close"] = dicts[-1]["close"] * 1.40
    dicts[-1]["high"] = dicts[-1]["close"]
    now = datetime.fromtimestamp(BASE_TS + 59 * 3600, UTC)
    result = engine.ingest(dicts, "BTC_USDT", "1h", now=now)

    assert result.anomalies >= 1
    assert db_session.query(MarketDataAnomaly).count() >= 1


def test_engine_missing_candle_lowers_completeness(db_session) -> None:
    engine = MarketDataQualityEngine(db_session)
    dicts = make_dicts(60)
    del dicts[30]  # create a gap
    now = datetime.fromtimestamp(BASE_TS + 59 * 3600, UTC)
    result = engine.ingest(dicts, "BTC_USDT", "1h", now=now)

    assert result.missing_candles >= 1
    assert result.health.completeness_score < 100
