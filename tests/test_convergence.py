import numpy as np

from pricing.convergence import HULL, mc_convergence, tree_convergence, variance_reduction_summary


def test_tree_error_shrinks_and_oscillates():
    study = tree_convergence(**HULL, n_max=400)
    error = np.abs(study["error"])
    assert error[study["n"] >= 300].max() < error[study["n"] <= 20].max() / 5
    # consecutive step counts land on opposite sides of the exact price
    small = study["error"][study["n"] <= 30]
    assert np.any(np.sign(small[1:]) != np.sign(small[:-1]))


def test_mc_standard_error_has_slope_minus_half():
    study = mc_convergence(**HULL, n_grid=np.array([1_000, 10_000, 100_000]))
    se = study["plain"]["std_error"]
    slope = np.polyfit(np.log(study["N"]), np.log(se), 1)[0]
    assert abs(slope + 0.5) < 0.05


def test_summary_ranks_variance_reduction():
    study = mc_convergence(**HULL, n_grid=np.array([50_000]))
    rows = {row["method"]: row for row in variance_reduction_summary(study)}
    assert rows["plain"]["vr_factor"] == 1.0
    assert rows["antithetic"]["vr_factor"] > 1
    assert rows["control_variate"]["vr_factor"] > 1
