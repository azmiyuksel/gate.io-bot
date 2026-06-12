from app.walkforward.metrics import walk_forward_efficiency


class WalkForwardValidator:
    def detect_overfit(self, train_metrics: dict, test_metrics: dict) -> tuple[bool, list[str]]:
        warnings: list[str] = []
        train_sharpe = float(train_metrics.get("sharpe_ratio", 0))
        test_sharpe = float(test_metrics.get("sharpe_ratio", 0))
        train_profit = float(train_metrics.get("net_profit", 0))
        test_profit = float(test_metrics.get("net_profit", 0))
        train_dd = abs(float(train_metrics.get("max_drawdown", 0)))
        test_dd = abs(float(test_metrics.get("max_drawdown", 0)))
        if train_sharpe > 1 and test_sharpe < train_sharpe * 0.5:
            warnings.append("Train Sharpe materially exceeds test Sharpe")
        if train_profit > 0 and test_profit < train_profit * 0.3:
            warnings.append("Train profit does not transfer to out-of-sample data")
        if train_dd > 0 and test_dd > train_dd * 2:
            warnings.append("Out-of-sample drawdown is more than double train drawdown")
        if walk_forward_efficiency(train_profit, test_profit) < 0.3:
            warnings.append("WFE below 30%, overfit risk")
        return bool(warnings), warnings

    def deployment_decision(self, aggregated: dict, overfit_warning: bool) -> dict:
        checks = {
            "robustness_score_gt_70": aggregated.get("robustness_score", 0) > 70,
            "consistency_gt_60": aggregated.get("consistency_score", 0) > 0.60,
            "wfe_gt_50": aggregated.get("wfe", 0) > 0.50,
            "sharpe_gt_1_5": aggregated.get("average_sharpe", 0) > 1.5,
            "max_drawdown_lt_15": abs(aggregated.get("worst_drawdown", 0)) < 0.15,
            "overfit_warning_false": not overfit_warning,
        }
        approved = all(checks.values())
        return {
            "decision": "REQUIRES_HUMAN_REVIEW" if approved else "AUTO_DEPLOYMENT_REJECT",
            "approved": approved,
            "checks": checks,
            "note": "Human approval is required before production deployment",
        }
