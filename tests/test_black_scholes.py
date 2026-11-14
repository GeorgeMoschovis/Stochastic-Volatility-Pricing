import numpy as np
import pytest

from pricing.black_scholes import bs_greeks, bs_price


def test_hull_example(hull):
    assert bs_price(**hull, kind="call") == pytest.approx(4.76, abs=0.01)
    assert bs_price(**hull, kind="put") == pytest.approx(0.81, abs=0.01)


def test_put_call_parity(hull):
    hull["q"] = 0.03
    S, K, T, r, q = hull["S"], hull["K"], hull["T"], hull["r"], hull["q"]
    call = bs_price(**hull, kind="call")
    put = bs_price(**hull, kind="put")
    assert call - put == pytest.approx(S * np.exp(-q * T) - K * np.exp(-r * T), abs=1e-12)


def test_vectorised_over_arrays(hull):
    spots = np.array([30.0, 42.0, 55.0])
    hull["S"] = spots
    prices = bs_price(**hull, kind="call")
    assert prices.shape == (3,)
    assert np.all(np.diff(prices) > 0)


def test_greek_signs(hull):
    call = bs_greeks(**hull, kind="call")
    put = bs_greeks(**hull, kind="put")
    assert 0 < call["delta"] < 1
    assert -1 < put["delta"] < 0
    assert call["gamma"] == pytest.approx(put["gamma"])
    assert call["vega"] == pytest.approx(put["vega"])
    assert call["rho"] > 0 > put["rho"]


def test_invalid_inputs_raise(hull):
    with pytest.raises(ValueError):
        bs_price(**{**hull, "sigma": -0.2})
    with pytest.raises(ValueError):
        bs_price(**hull, kind="straddle")
