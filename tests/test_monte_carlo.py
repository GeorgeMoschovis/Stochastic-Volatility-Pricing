import pytest

from pricing.black_scholes import bs_price
from pricing.monte_carlo import METHODS, mc_price, variance_reduction_factor

N_PATHS = 200_000


@pytest.mark.parametrize("kind", ["call", "put"])
@pytest.mark.parametrize("method", METHODS)
def test_estimator_within_three_standard_errors(hull, method, kind):
    result = mc_price(**hull, kind=kind, n_paths=N_PATHS, seed=7, method=method)
    exact = bs_price(**hull, kind=kind)
    assert abs(result.price - exact) < 3 * result.std_error


@pytest.mark.parametrize("method", ["antithetic", "control_variate"])
def test_variance_reduction_beats_plain(hull, method):
    plain = mc_price(**hull, n_paths=N_PATHS, seed=7, method="plain")
    reduced = mc_price(**hull, n_paths=N_PATHS, seed=7, method=method)
    assert reduced.std_error < plain.std_error
    assert variance_reduction_factor(plain, reduced) > 1


def test_confidence_interval_is_symmetric(hull):
    result = mc_price(**hull, n_paths=10_000, seed=1)
    assert result.ci_high - result.price == pytest.approx(1.96 * result.std_error)
    assert result.price - result.ci_low == pytest.approx(1.96 * result.std_error)


def test_same_seed_gives_same_price(hull):
    first = mc_price(**hull, n_paths=10_000, seed=3)
    second = mc_price(**hull, n_paths=10_000, seed=3)
    assert first.price == second.price


def test_unknown_method_raises(hull):
    with pytest.raises(ValueError):
        mc_price(**hull, method="quasi")
