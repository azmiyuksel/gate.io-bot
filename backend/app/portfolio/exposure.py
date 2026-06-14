from decimal import Decimal
from typing import Dict, List, Any


class ExposureManager:
    @staticmethod
    def calculate_asset_exposures(positions: List[Any], total_equity: Decimal) -> Dict[str, float]:
        """
        Calculates exposure percentage per asset.
        Positions can be database entities (Position or PaperPosition) or dicts.
        """
        if total_equity <= 0:
            return {}

        exposures = {}
        for pos in positions:
            symbol = getattr(pos, "symbol", None) or pos.get("symbol")
            if not symbol:
                continue
            
            # Exposure = quantity * current_price
            qty = Decimal(str(getattr(pos, "quantity", 0) or pos.get("quantity", 0)))
            price = Decimal(
                str(
                    getattr(pos, "current_price", None)
                    or getattr(pos, "last_price", None)
                    or pos.get("current_price", None)
                    or pos.get("last_price", 0)
                )
            )
            
            value = qty * price
            exposure_pct = float(value / total_equity)
            exposures[symbol] = exposures.get(symbol, 0.0) + exposure_pct

        return exposures

    @staticmethod
    def calculate_strategy_exposures(allocations: List[Any], asset_exposures: Dict[str, float]) -> Dict[str, float]:
        """
        Estimates exposure per strategy based on strategy weights and overall asset exposures.
        """
        strategy_exposures = {}
        
        # Filter for strategy allocations
        strategy_allocs = [a for a in allocations if getattr(a, "target_type", "") == "strategy" or a.get("target_type") == "strategy"]
        total_strategy_weight = sum(float(getattr(a, "weight", 0.0) or a.get("weight", 0.0)) for a in strategy_allocs)
        
        if total_strategy_weight <= 0:
            return {}

        total_asset_exposure = sum(asset_exposures.values())

        for alloc in strategy_allocs:
            name = getattr(alloc, "target_name", "") or alloc.get("target_name")
            weight = float(getattr(alloc, "weight", 0.0) or alloc.get("weight", 0.0))
            
            # Distribute total asset exposure based on strategy weights
            exposure_share = (weight / total_strategy_weight) * total_asset_exposure
            strategy_exposures[name] = exposure_share

        return strategy_exposures
