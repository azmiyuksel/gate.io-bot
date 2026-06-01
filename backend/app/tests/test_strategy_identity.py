"""Guards the single canonical strategy identifier.

The live engine, StrategySettings, the paper adapter and the health/regime
records must all agree on one name, otherwise auto-pause / risk-reduction
lookups silently miss.
"""
from app.models.entities import StrategySettings
from app.services.strategy.signals import STRATEGY_NAME, CapitalPreservationStrategy


def test_strategy_exposes_canonical_name() -> None:
    assert CapitalPreservationStrategy().name == STRATEGY_NAME
    assert STRATEGY_NAME == "capital_preservation_v1"


def test_strategy_name_matches_settings_default() -> None:
    # StrategySettings.name default must equal the strategy's canonical name so
    # health-engine auto-disable (filter by name) actually finds the row.
    default_name = StrategySettings.__table__.c.name.default.arg
    assert default_name == STRATEGY_NAME
