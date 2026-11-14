import numpy as np
import pytest

from pricing.binomial import crr_price
from pricing.black_scholes import bs_price


@pytest.mark.parametrize("kind", ["call", "put"])
def test_tree_converges_to_black_scholes(hull, kind):
    tree = crr_price(**hull, kind=kind, n=1000)
    assert abs(tree - bs_price(**hull, kind=kind)) < 1e-3


def test_put_call_parity(hull):
    S, K, T, r = hull["S"], hull["K"], hull["T"], hull["r"]
    call = crr_price(**hull, kind="call", n=200)
    put = crr_price(**hull, kind="put", n=200)
    assert call - put == pytest.approx(S - K * np.exp(-r * T), abs=1e-10)


def test_american_put_at_least_european(hull):
    european = crr_price(**hull, kind="put", n=500)
    american = crr_price(**hull, kind="put", n=500, american=True)
    assert american >= european
    # early exercise has real value for a put when r > 0
    assert american - european > 1e-3


def test_american_call_equals_european_without_dividends(hull):
    european = crr_price(**hull, kind="call", n=300)
    american = crr_price(**hull, kind="call", n=300, american=True)
    assert american == pytest.approx(european, abs=1e-10)


def test_one_step_tree_by_hand():
    # S=100, K=100, u=1.1052, d=0.9048, r=0: p* = 0.475, call = 0.475 * 10.52
    price = crr_price(100, 100, 1.0, 0.0, 0.10, n=1)
    u = np.exp(0.10)
    p = (1 - 1 / u) / (u - 1 / u)
    assert price == pytest.approx(p * (100 * u - 100))
