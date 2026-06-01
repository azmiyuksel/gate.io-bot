"""Market Data Quality Engine.

Real-time pipeline that every candle flows through before it is trusted:

    raw_data -> normalize -> validate -> anomaly detection
             -> repair/flag -> emit clean -> (trading / backtest / paper)

The engine persists raw candles, clean candles, anomalies and a rolling health
score, and exposes a trading gate (``trade_status``) so live/paper engines can
pause or de-risk on degraded feeds. It is exchange-agnostic: cross-exchange
reference prices are injected as callables.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.market_data_quality.anomaly_detector import AnomalyDetector
from app.market_data_quality.cross_exchange_validator import (
    CrossExchangeValidator,
    PriceSource,
)
from app.market_data_quality.data_health_score import DataHealthScorer
from app.market_data_quality.gap_detector import GapDetector, timeframe_seconds
from app.market_data_quality.models import (
    AnomalyFinding,
    AnomalyType,
    CandleData,
    DataTradeStatus,
    HealthScore,
    RepairAction,
    ValidationCode,
    category_for_score,
    trade_status_for_score,
)
from app.market_data_quality.normalization import DataNormalizer
from app.market_data_quality.spike_detector import SpikeDetector
from app.market_data_quality.validator import CandleValidator
from app.market_data_quality.volume_analyzer import VolumeAnalyzer
from app.models.entities import (
    DataQualityReport,
    MarketDataAnomaly,
    MarketDataClean,
    MarketDataHealthLog,
    MarketDataRaw,
)

_VALIDATION_TO_ANOMALY = {
    ValidationCode.high_below_components: AnomalyType.ohlc_inconsistency,
    ValidationCode.low_above_components: AnomalyType.ohlc_inconsistency,
    ValidationCode.non_positive_price: AnomalyType.invalid_value,
    ValidationCode.negative_volume: AnomalyType.invalid_value,
    ValidationCode.duplicate_timestamp: AnomalyType.duplicate_timestamp,
    ValidationCode.excessive_move: AnomalyType.price_spike,
    ValidationCode.missing_field: AnomalyType.invalid_value,
}
# Validation codes that make a candle structurally untrustworthy -> drop.
_STRUCTURAL_CODES = {
    ValidationCode.non_positive_price,
    ValidationCode.negative_volume,
    ValidationCode.high_below_components,
    ValidationCode.low_above_components,
    ValidationCode.duplicate_timestamp,
    ValidationCode.missing_field,
}


@dataclass
class CandleOutcome:
    candle: CandleData
    is_valid: bool
    is_clean: bool
    repair_action: RepairAction
    anomalies: list[AnomalyFinding] = field(default_factory=list)
    cleaned: CandleData | None = None


@dataclass
class ProcessResult:
    symbol: str
    timeframe: str
    total: int
    valid: int
    clean_emitted: int
    anomalies: int
    missing_candles: int
    health: HealthScore
    outcomes: list[CandleOutcome] = field(default_factory=list)

    @property
    def trade_status(self) -> DataTradeStatus:
        return self.health.trade_status


class MarketDataQualityEngine:
    def __init__(
        self,
        db: Session,
        *,
        cross_exchange_sources: dict[str, PriceSource] | None = None,
    ) -> None:
        self.db = db
        s = get_settings()
        self.settings = s
        self.normalizer = DataNormalizer(quote_hint=s.default_quote_currency)
        self.validator = CandleValidator(spike_threshold_pct=s.mdq_spike_threshold_pct)
        self.spike = SpikeDetector(threshold_pct=s.mdq_spike_threshold_pct, mode=s.mdq_spike_mode)
        self.volume = VolumeAnalyzer(
            spike_multiple=s.mdq_volume_spike_multiple,
            liquidity_drop_pct=s.mdq_liquidity_drop_pct,
        )
        self.anomaly = AnomalyDetector(
            zscore_threshold=s.mdq_zscore_threshold, enable_ml=s.mdq_enable_ml
        )
        self.scorer = DataHealthScorer()
        self.cross_exchange = CrossExchangeValidator(
            sources=cross_exchange_sources,
            threshold_pct=s.mdq_cross_exchange_threshold_pct,
        )

    # ------------------------------------------------------------------
    # Spec API surface
    # ------------------------------------------------------------------
    def validate_candle(self, candle: CandleData, previous: CandleData | None):
        return self.validator.validate(candle, previous)

    def detect_anomalies(
        self, candle: CandleData, history: list[CandleData]
    ) -> list[AnomalyFinding]:
        findings: list[AnomalyFinding] = []
        previous = history[-1] if history else None
        spike = self.spike.detect(candle, previous)
        if spike.finding:
            findings.append(spike.finding)
        findings.extend(self.volume.analyze(candle, history))
        findings.extend(self.anomaly.detect(candle, history))
        if self.cross_exchange.sources:
            cross = self.cross_exchange.validate(candle.symbol, candle.close)
            if cross.finding:
                findings.append(cross.finding)
        return findings

    def repair_or_flag_data(
        self, candle: CandleData, validation, anomalies: list[AnomalyFinding]
    ) -> tuple[RepairAction, CandleData | None, bool]:
        """Decide what to emit. Returns (action, cleaned_candle_or_None, is_clean)."""
        # Structurally broken candles are dropped (safest).
        if any(code in _STRUCTURAL_CODES for code in validation.codes):
            return RepairAction.drop, None, False

        spike_present = any(
            a.anomaly_type in (AnomalyType.flash_crash, AnomalyType.flash_pump, AnomalyType.price_spike)
            for a in anomalies
        )
        if spike_present and self.settings.mdq_spike_mode == "ignore":
            return RepairAction.drop, None, False
        if spike_present and self.settings.mdq_spike_mode == "smooth":
            repaired = self._smoothed_candle(candle, anomalies)
            return RepairAction.interpolate, repaired or candle, True

        if anomalies:
            # Keep the data but mark it uncertain so downstream can de-risk.
            return RepairAction.flag_uncertain, candle, True

        return RepairAction.none, candle, True

    def compute_data_health_score(
        self,
        *,
        total_candles: int,
        invalid_candles: int,
        expected_candles: int,
        missing_candles: int,
        anomalies: int,
        feed_lag_seconds: float,
        interval_seconds: float,
    ) -> HealthScore:
        return self.scorer.compute(
            total_candles=total_candles,
            invalid_candles=invalid_candles,
            expected_candles=expected_candles,
            missing_candles=missing_candles,
            anomalies=anomalies,
            feed_lag_seconds=feed_lag_seconds,
            interval_seconds=interval_seconds,
        )

    # ------------------------------------------------------------------
    # Main pipeline
    # ------------------------------------------------------------------
    def ingest(
        self,
        raw_candles: list,
        symbol: str,
        timeframe: str,
        source: str = "gateio",
        now: datetime | None = None,
        persist: bool = True,
    ) -> ProcessResult:
        """Run a batch of raw candles through the full quality pipeline."""
        now = now or datetime.now(UTC)
        normalized = self._normalize_batch(raw_candles, symbol, timeframe, source)
        normalized.sort(key=lambda c: c.timestamp)

        # Seed history with recent clean candles for statistical context.
        history: list[CandleData] = self._recent_clean(symbol, timeframe, limit=self.anomaly.window)

        outcomes: list[CandleOutcome] = []
        invalid = 0
        anomaly_total = 0
        clean_emitted = 0

        for candle in normalized:
            previous = history[-1] if history else None
            validation = self.validator.validate(candle, previous)
            anomalies = self.detect_anomalies(candle, history)
            action, cleaned, is_clean = self.repair_or_flag_data(candle, validation, anomalies)

            if not validation.is_valid:
                invalid += 1
                anomalies = self._augment_validation_anomalies(validation, anomalies)
            anomaly_total += len(anomalies)

            outcome = CandleOutcome(
                candle=candle,
                is_valid=validation.is_valid,
                is_clean=is_clean,
                repair_action=action,
                anomalies=anomalies,
                cleaned=cleaned,
            )
            outcomes.append(outcome)

            if persist:
                self._persist_raw(candle)
                self._persist_anomalies(candle, anomalies, action)
            if is_clean and cleaned is not None:
                clean_emitted += 1
                if persist:
                    self._persist_clean(cleaned, action, bool(anomalies))
                history.append(cleaned)

        # Gap / completeness analysis over the batch.
        gap = GapDetector(timeframe).analyze(normalized, now=now)
        interval = timeframe_seconds(timeframe)
        expected = len(normalized) + gap.missing_count
        health = self.compute_data_health_score(
            total_candles=len(normalized),
            invalid_candles=invalid,
            expected_candles=max(expected, 1),
            missing_candles=gap.missing_count,
            anomalies=anomaly_total,
            feed_lag_seconds=gap.feed_lag_seconds,
            interval_seconds=interval,
        )

        if persist and normalized:
            self._persist_health(symbol, timeframe, health, len(normalized),
                                  anomaly_total, gap.missing_count, gap.feed_lag_seconds)
            self.db.commit()

        return ProcessResult(
            symbol=symbol,
            timeframe=timeframe,
            total=len(normalized),
            valid=len(normalized) - invalid,
            clean_emitted=clean_emitted,
            anomalies=anomaly_total,
            missing_candles=gap.missing_count,
            health=health,
            outcomes=outcomes,
        )

    def emit_clean_data(self, result: ProcessResult) -> list[CandleData]:
        """Clean candles ready for downstream consumers (trading/backtest)."""
        return [o.cleaned for o in result.outcomes if o.is_clean and o.cleaned is not None]

    # ------------------------------------------------------------------
    # Trading gate
    # ------------------------------------------------------------------
    def trade_status(self, symbol: str, timeframe: str = "1h") -> DataTradeStatus:
        log = (
            self.db.query(MarketDataHealthLog)
            .filter(MarketDataHealthLog.symbol == symbol)
            .filter(MarketDataHealthLog.timeframe == timeframe)
            .order_by(MarketDataHealthLog.created_at.desc())
            .first()
        )
        if log is None:
            return DataTradeStatus.clean  # no data yet -> don't block by default
        return trade_status_for_score(float(log.health_score))

    def latest_health(self, symbol: str, timeframe: str = "1h") -> MarketDataHealthLog | None:
        return (
            self.db.query(MarketDataHealthLog)
            .filter(MarketDataHealthLog.symbol == symbol)
            .filter(MarketDataHealthLog.timeframe == timeframe)
            .order_by(MarketDataHealthLog.created_at.desc())
            .first()
        )

    def generate_report(
        self, symbol: str, timeframe: str, start: datetime, end: datetime, persist: bool = True
    ) -> DataQualityReport:
        anomalies = (
            self.db.query(MarketDataAnomaly)
            .filter(MarketDataAnomaly.symbol == symbol)
            .filter(MarketDataAnomaly.timeframe == timeframe)
            .filter(MarketDataAnomaly.created_at >= start)
            .filter(MarketDataAnomaly.created_at <= end)
            .all()
        )
        health_logs = (
            self.db.query(MarketDataHealthLog)
            .filter(MarketDataHealthLog.symbol == symbol)
            .filter(MarketDataHealthLog.timeframe == timeframe)
            .filter(MarketDataHealthLog.created_at >= start)
            .filter(MarketDataHealthLog.created_at <= end)
            .all()
        )
        total = (
            self.db.query(MarketDataRaw)
            .filter(MarketDataRaw.symbol == symbol)
            .filter(MarketDataRaw.timeframe == timeframe)
            .filter(MarketDataRaw.created_at >= start)
            .filter(MarketDataRaw.created_at <= end)
            .count()
        )
        clean = (
            self.db.query(MarketDataClean)
            .filter(MarketDataClean.symbol == symbol)
            .filter(MarketDataClean.timeframe == timeframe)
            .filter(MarketDataClean.created_at >= start)
            .filter(MarketDataClean.created_at <= end)
            .count()
        )

        breakdown: dict[str, int] = {}
        for a in anomalies:
            breakdown[a.anomaly_type] = breakdown.get(a.anomaly_type, 0) + 1
        missing = sum(h.missing_candles for h in health_logs)
        avg_health = (
            sum(float(h.health_score) for h in health_logs) / len(health_logs)
            if health_logs
            else 0.0
        )

        report = DataQualityReport(
            symbol=symbol,
            timeframe=timeframe,
            start_time=start,
            end_time=end,
            total_candles=total,
            valid_candles=clean,
            anomalies_total=len(anomalies),
            missing_candles=missing,
            average_health_score=Decimal(str(round(avg_health, 2))),
            category=str(category_for_score(avg_health)),
            anomaly_breakdown=breakdown,
            report_data={"health_samples": len(health_logs)},
        )
        if persist:
            self.db.add(report)
            self.db.commit()
            self.db.refresh(report)
        return report

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _normalize_batch(
        self, raw_candles: list, symbol: str, timeframe: str, source: str
    ) -> list[CandleData]:
        out: list[CandleData] = []
        for raw in raw_candles:
            if isinstance(raw, CandleData):
                out.append(self.normalizer.normalize_candle(raw))
            else:
                out.append(self.normalizer.from_exchange_dict(raw, symbol, timeframe, source))
        return out

    def _smoothed_candle(
        self, candle: CandleData, anomalies: list[AnomalyFinding]
    ) -> CandleData | None:
        # The spike detector already produced a smoothed candle when in smooth mode;
        # recompute against the last clean candle if available.
        history = self._recent_clean(candle.symbol, candle.timeframe, limit=1)
        previous = history[-1] if history else None
        return self.spike.detect(candle, previous).repaired

    def _augment_validation_anomalies(
        self, validation, anomalies: list[AnomalyFinding]
    ) -> list[AnomalyFinding]:
        existing = {a.anomaly_type for a in anomalies}
        for code, detail in zip(validation.codes, validation.details):
            atype = _VALIDATION_TO_ANOMALY.get(code)
            if atype and atype not in existing:
                anomalies.append(
                    AnomalyFinding(
                        anomaly_type=atype,
                        severity="CRITICAL",
                        detail=detail,
                        detection_method="validation",
                    )
                )
                existing.add(atype)
        return anomalies

    def _recent_clean(self, symbol: str, timeframe: str, limit: int) -> list[CandleData]:
        rows = (
            self.db.query(MarketDataClean)
            .filter(MarketDataClean.symbol == symbol)
            .filter(MarketDataClean.timeframe == timeframe)
            .order_by(MarketDataClean.timestamp.desc())
            .limit(limit)
            .all()
        )
        rows.reverse()
        return [
            CandleData(
                symbol=r.symbol,
                timeframe=r.timeframe,
                timestamp=r.timestamp,
                open=r.open,
                high=r.high,
                low=r.low,
                close=r.close,
                volume=r.volume,
                source=r.source,
            )
            for r in rows
        ]

    def _persist_raw(self, candle: CandleData) -> None:
        exists = (
            self.db.query(MarketDataRaw.id)
            .filter(MarketDataRaw.symbol == candle.symbol)
            .filter(MarketDataRaw.timeframe == candle.timeframe)
            .filter(MarketDataRaw.timestamp == candle.timestamp)
            .filter(MarketDataRaw.source == candle.source)
            .first()
        )
        if exists:
            return
        self.db.add(
            MarketDataRaw(
                symbol=candle.symbol,
                timeframe=candle.timeframe,
                timestamp=candle.timestamp,
                open=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
                volume=candle.volume,
                source=candle.source,
            )
        )

    def _persist_clean(self, candle: CandleData, action: RepairAction, uncertain: bool) -> None:
        exists = (
            self.db.query(MarketDataClean.id)
            .filter(MarketDataClean.symbol == candle.symbol)
            .filter(MarketDataClean.timeframe == candle.timeframe)
            .filter(MarketDataClean.timestamp == candle.timestamp)
            .filter(MarketDataClean.source == candle.source)
            .first()
        )
        if exists:
            return
        self.db.add(
            MarketDataClean(
                symbol=candle.symbol,
                timeframe=candle.timeframe,
                timestamp=candle.timestamp,
                open=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
                volume=candle.volume,
                source=candle.source,
                repair_action=str(action),
                is_uncertain=uncertain,
            )
        )

    def _persist_anomalies(
        self, candle: CandleData, anomalies: list[AnomalyFinding], action: RepairAction
    ) -> None:
        for a in anomalies:
            self.db.add(
                MarketDataAnomaly(
                    symbol=candle.symbol,
                    timeframe=candle.timeframe,
                    timestamp=candle.timestamp,
                    anomaly_type=str(a.anomaly_type),
                    severity=a.severity,
                    detection_method=a.detection_method,
                    observed_value=(
                        Decimal(str(a.observed_value)) if a.observed_value is not None else None
                    ),
                    threshold_value=(
                        Decimal(str(a.threshold_value)) if a.threshold_value is not None else None
                    ),
                    repair_action=str(action),
                    detail=a.detail,
                    source=candle.source,
                )
            )

    def _persist_health(
        self,
        symbol: str,
        timeframe: str,
        health: HealthScore,
        evaluated: int,
        anomalies: int,
        missing: int,
        feed_lag: float,
    ) -> None:
        self.db.add(
            MarketDataHealthLog(
                symbol=symbol,
                timeframe=timeframe,
                health_score=Decimal(str(health.score)),
                consistency_score=Decimal(str(health.consistency_score)),
                completeness_score=Decimal(str(health.completeness_score)),
                anomaly_inverse_score=Decimal(str(health.anomaly_inverse_score)),
                latency_score=Decimal(str(health.latency_score)),
                category=str(health.category),
                trade_status=str(health.trade_status),
                candles_evaluated=evaluated,
                anomalies_found=anomalies,
                missing_candles=missing,
                feed_latency_ms=Decimal(str(round(feed_lag * 1000, 2))),
            )
        )
