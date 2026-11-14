import pytest

from pricing.binomial import crr_price
from pricing.black_scholes import bs_greeks, bs_price
from pricing.greeks import compare_greeks, fd_greeks
from pricing.monte_carlo import mc_price


@pytest.mark.parametrize("kind", ["call", "put"])
def test_fd_greeks_of_bs_match_analytic(hull, kind):
    # the BS price is smooth, so a small spot bump gives a tiny truncation error
    for row in compare_greeks(bs_price, **hull, kind=kind, bump_S=1e-3):
        assert row["rel_error"] < 1e-4, row


@pytest.mark.parametrize("kind", ["call", "put"])
def test_fd_greeks_with_default_bumps(hull, kind):
    for row in compare_greeks(bs_price, **hull, kind=kind):
        assert row["abs_error"] < 1e-3, row


def test_fd_greeks_of_tree_are_close(hull):
    def tree(S, K, T, r, sigma, q, kind):
        return crr_price(S, K, T, r, sigma, q, kind, n=400)

    # a wider spot bump averages over the kinks of the piecewise-linear tree price
    numeric = fd_greeks(tree, **hull, bump_S=0.05)
    exact = bs_greeks(**hull)
    for name in ("delta", "vega", "rho", "theta"):
        assert numeric[name] == pytest.approx(exact[name], rel=0.02)
    assert numeric["gamma"] == pytest.approx(exact["gamma"], rel=0.10)


def test_fd_delta_of_mc_with_common_random_numbers(hull):
    def mc(S, K, T, r, sigma, q, kind):
        return mc_price(S, K, T, r, sigma, q, kind, n_paths=100_000, seed=11).price

    numeric = fd_greeks(mc, **hull)
    exact = bs_greeks(**hull)
    assert numeric["delta"] == pytest.approx(exact["delta"], abs=0.01)
    assert numeric["vega"] == pytest.approx(exact["vega"], rel=0.03)
