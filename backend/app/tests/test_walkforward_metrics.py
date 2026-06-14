from app.walkforward.metrics import robustness_score, walk_forward_efficiency, wfe_label
from app.walkforward.validator import WalkForwardValidator


def test_wfe_labels() -> None:
    assert walk_forward_efficiency(10000, 7000) == 0.7
    assert wfe_label(0.8) == "Excellent"
    assert wfe_label(0.2) == "Overfit Risk"


def test_robustness_score_bounds() -> None:
    score = robustness_score(consistency=0.75, wfe=0.7, sharpe=1.8, drawdown=-0.1, profit_factor=1.6)
    assert 0 <= score <= 100


def test_deployment_rejects_overfit_warning() -> None:
    decision = WalkForwardValidator().deployment_decision(
        {
            "robustness_score": 90,
            "consistency_score": 0.8,
            "wfe": 0.8,
            "average_sharpe": 2,
            "worst_drawdown": -0.1,
        },
        overfit_warning=True,
    )
    assert decision["decision"] == "AUTO_DEPLOYMENT_REJECT"


def test_aggregate_results_wfe_uses_annualized_returns() -> None:
    from types import SimpleNamespace

    from app.walkforward.metrics import aggregate_results

    # Train windows are long (small annualized), test windows short. Raw net-profit
    # WFE would look terrible; annualized-return WFE compares like-for-like.
    windows = [
        SimpleNamespace(
            window_id=i,
            train_metrics={"net_profit": 1000.0, "annualized_return": 0.40},
            test_metrics={
                "net_profit": 200.0, "annualized_return": 0.32, "total_return": 0.05,
                "sharpe_ratio": 1.2, "sortino_ratio": 1.5, "max_drawdown": -0.08,
                "profit_factor": 1.6,
            },
        )
        for i in range(3)
    ]
    agg = aggregate_results(windows)
    # WFE = mean(test annualized) / mean(train annualized) = 0.32 / 0.40 = 0.8
    assert round(agg["wfe"], 4) == 0.8
    # total_return is the compounded OOS return (1.05^3 - 1), not a profit ratio.
    assert round(agg["total_return"], 6) == round(1.05**3 - 1, 6)
