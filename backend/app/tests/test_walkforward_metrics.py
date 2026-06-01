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
