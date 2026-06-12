import logging
from datetime import UTC, datetime
from decimal import Decimal
from typing import List, Tuple
from sqlalchemy.orm import Session

from app.models.entities import MarketRegimeRecord, RegimeConfidence, RegimeFeatures, RegimeTransition
from app.models.enums import MarketRegimeType
from app.market_regime.detector import MarketRegimeDetector
from app.market_regime.features import FeatureEngineer
from app.market_regime.signals import RegimeSignalFilter
from app.services.notifications.telegram import TelegramNotifier

logger = logging.getLogger(__name__)


class MarketRegimeEngine:
    _REGIME_COOLDOWN_BAR_COUNT = 3

    def __init__(self, db: Session) -> None:
        self.db = db
        self.detector = MarketRegimeDetector()
        self.notifier = TelegramNotifier()
        self._consecutive_different_regime: dict[str, int] = {}
        self._load_cooldown_state()

    def _load_cooldown_state(self) -> None:
        """Reconstruct in-memory cooldown counters from the last regime records.

        This ensures that a process restart does not reset an in-progress
        cooldown window, preventing premature regime transitions.
        """
        symbols = (
            self.db.query(MarketRegimeRecord.symbol)
            .group_by(MarketRegimeRecord.symbol)
            .all()
        )
        for (symbol,) in symbols:
            recent = (
                self.db.query(MarketRegimeRecord)
                .filter(MarketRegimeRecord.symbol == symbol)
                .order_by(MarketRegimeRecord.created_at.desc())
                .limit(self._REGIME_COOLDOWN_BAR_COUNT + 1)
                .all()
            )
            if len(recent) < 2:
                continue
            # Walk backwards: count consecutive records where the regime differs
            # from the *oldest* record in the window (which represents the
            # "current" regime before any transition was confirmed).
            current_regime = recent[-1].regime_type
            consecutive = 0
            for rec in reversed(recent[:-1]):
                if rec.regime_type != current_regime:
                    consecutive += 1
                else:
                    break
            if consecutive > 0:
                self._consecutive_different_regime[symbol] = consecutive

    def update_regime(self, symbol: str, timeframe: str, candles: List[dict]) -> MarketRegimeRecord:
        """
        Computes features on the latest candles, fits/trains if needed, detects current regime,
        detects and logs transitions, and saves metrics.
        """
        if len(candles) < 210:
            # Fallback to simple sideways if not enough history
            record = MarketRegimeRecord(
                symbol=symbol,
                timeframe=timeframe,
                regime_type=MarketRegimeType.sideways,
                confidence=Decimal("1.0"),
                rule_based_vote=MarketRegimeType.sideways.value,
                clustering_vote=MarketRegimeType.sideways.value,
                ml_vote=MarketRegimeType.sideways.value,
            )
            self.db.add(record)
            self.db.commit()
            return record

        df = FeatureEngineer.compute_features(candles)
        
        # Fit detectors on this history if not already trained
        if not self.detector.classifier.is_trained:
            self.detector.fit_detectors(df)

        # Predict latest row
        latest_row = df.iloc[-1]
        timestamp = latest_row.name if isinstance(latest_row.name, datetime) else datetime.now(UTC)

        regime, confidence, votes = self.detector.detect(latest_row)

        # 1. Log Features
        feat_record = RegimeFeatures(
            symbol=symbol,
            timestamp=timestamp,
            features_json=latest_row.to_dict()
        )
        self.db.add(feat_record)

        # 2. Log Confidence
        conf_record = RegimeConfidence(
            symbol=symbol,
            timestamp=timestamp,
            confidence_score=Decimal(str(confidence)),
            vote_weights=votes
        )
        self.db.add(conf_record)

        # 3. Check for transitions
        last_record = (
            self.db.query(MarketRegimeRecord)
            .filter(MarketRegimeRecord.symbol == symbol, MarketRegimeRecord.timeframe == timeframe)
            .order_by(MarketRegimeRecord.created_at.desc())
            .first()
        )

        if last_record and last_record.regime_type != regime:
            # --- Regime transition cooldown ---
            # Require N consecutive same-regime detections before confirming a
            # switch. This prevents whipsaw from flickering ensemble votes.
            consecutive = self._consecutive_different_regime.get(symbol, 0) + 1
            self._consecutive_different_regime[symbol] = consecutive
            if consecutive < self._REGIME_COOLDOWN_BAR_COUNT:
                # Not enough consecutive detections; keep the old regime
                record = MarketRegimeRecord(
                    symbol=symbol,
                    timeframe=timeframe,
                    regime_type=last_record.regime_type,
                    confidence=Decimal(str(confidence)),
                    rule_based_vote=votes["rule_based"],
                    clustering_vote=votes["clustering"],
                    ml_vote=votes["ml_model"],
                    created_at=datetime.now(UTC),
                )
                self.db.add(record)
                self.db.commit()
                return record
            # Cooldown satisfied: confirm transition
            self._consecutive_different_regime[symbol] = 0
            transition = RegimeTransition(
                symbol=symbol,
                old_regime=last_record.regime_type,
                new_regime=regime,
                confidence=Decimal(str(confidence)),
                trigger_event=f"Ensemble vote switch to {regime.value}"
            )
            self.db.add(transition)
            
            # Send Telegram Alert asynchronously
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.notifier.send_regime_transition(
                    symbol,
                    str(last_record.regime_type.value),
                    str(regime.value),
                    float(confidence),
                ))
            except RuntimeError:
                logger.warning("Regime-transition alert skipped (no running event loop)", exc_info=True)

        # 4. Save Current Regime Record
        # Reset consecutive counter when regime matches the last recorded one
        if last_record and last_record.regime_type == regime:
            self._consecutive_different_regime[symbol] = 0
        record = MarketRegimeRecord(
            symbol=symbol,
            timeframe=timeframe,
            regime_type=regime,
            confidence=Decimal(str(confidence)),
            rule_based_vote=votes["rule_based"],
            clustering_vote=votes["clustering"],
            ml_vote=votes["ml_model"],
            created_at=datetime.now(UTC)
        )
        self.db.add(record)
        self.db.commit()
        return record

    def get_current_regime(self, symbol: str, timeframe: str = "1h") -> MarketRegimeRecord:
        """
        Gets the latest regime record from database, creating default if not found.
        """
        record = (
            self.db.query(MarketRegimeRecord)
            .filter(MarketRegimeRecord.symbol == symbol, MarketRegimeRecord.timeframe == timeframe)
            .order_by(MarketRegimeRecord.created_at.desc())
            .first()
        )
        if not record:
            record = MarketRegimeRecord(
                symbol=symbol,
                timeframe=timeframe,
                regime_type=MarketRegimeType.sideways,
                confidence=Decimal("1.0"),
                rule_based_vote=MarketRegimeType.sideways.value,
                clustering_vote=MarketRegimeType.sideways.value,
                ml_vote=MarketRegimeType.sideways.value,
            )
            self.db.add(record)
            self.db.commit()
            self.db.refresh(record)
        return record

    def should_trade(self, strategy_name: str, symbol: str, timeframe: str = "1h") -> Tuple[bool, str, Decimal]:
        """
        Determines whether a strategy is allowed to trade based on the current regime.
        Returns: (allowed, reason, risk_multiplier)
        """
        record = self.get_current_regime(symbol, timeframe)
        return RegimeSignalFilter.should_allow_trade(
            strategy_name,
            MarketRegimeType(record.regime_type),
            float(record.confidence)
        )

    def recalculate_history(self, symbol: str, timeframe: str, candles: List[dict]) -> int:
        """
        Recalculates the historical regime data and trains classifiers.
        """
        if len(candles) < 50:
            return 0

        df = FeatureEngineer.compute_features(candles)
        self.detector.fit_detectors(df)

        # Process history and save regime records
        count = 0
        for i in range(50, len(df)):
            row = df.iloc[i]
            timestamp = row.name if isinstance(row.name, datetime) else datetime.now(UTC)
            
            # Predict
            regime, confidence, votes = self.detector.detect(row)
            
            record = MarketRegimeRecord(
                symbol=symbol,
                timeframe=timeframe,
                regime_type=regime,
                confidence=Decimal(str(confidence)),
                rule_based_vote=votes["rule_based"],
                clustering_vote=votes["clustering"],
                ml_vote=votes["ml_model"],
                created_at=timestamp
            )
            self.db.add(record)
            count += 1

        self.db.commit()
        return count
