import numpy as np
import pytest

from pricing.black_scholes import bs_price
from pricing.implied_vol import implied_vol, implied_vol_vec


@pytest.mark.parametrize("kind", ["call", "put"])
@pytest.mark.parametrize("sigma", [0.05, 0.20, 0.80])
def test_round_trip(hull, kind, sigma):
    hull["sigma"] = sigma
    price = bs_price(**hull, kind=kind)
    vol, reason = implied_vol(price, hull["S"], hull["K"], hull["T"], hull["r"], hull["q"], kind)
    assert reason == ""
    assert vol == pytest.approx(sigma, abs=1e-8)
    assert bs_price(**{**hull, "sigma": vol}, kind=kind) == pytest.approx(price, abs=1e-10)


def test_price_below_intrinsic_returns_nan(hull):
    # the call is worth at least S - K e^{-rT} = 3.95
    vol, reason = implied_vol(3.0, hull["S"], hull["K"], hull["T"], hull["r"])
    assert np.isnan(vol)
    assert "no-arbitrage" in reason


def test_price_above_spot_returns_nan(hull):
    vol, reason = implied_vol(50.0, hull["S"], hull["K"], hull["T"], hull["r"])
    assert np.isnan(vol)
    assert "no-arbitrage" in reason


def test_vectorised_solver_matches_brent(hull):
    strikes = np.linspace(30.0, 55.0, 11)
    kinds = np.where(strikes < hull["S"], "put", "call")
    prices = np.array([bs_price(hull["S"], k, hull["T"], hull["r"], 0.3, kind=kd) for k, kd in zip(strikes, kinds)])
    vec = implied_vol_vec(prices, hull["S"], strikes, hull["T"], hull["r"], kind=kinds)
    brent = [implied_vol(p, hull["S"], k, hull["T"], hull["r"], kind=kd)[0] for p, k, kd in zip(prices, strikes, kinds)]
    assert vec == pytest.approx(np.array(brent), abs=1e-9)
    assert vec == pytest.approx(0.3, abs=1e-9)


def test_vectorised_wrapper(hull):
    strikes = np.array([35.0, 40.0, 45.0])
    prices = bs_price(hull["S"], strikes, hull["T"], hull["r"], 0.25)
    prices[1] = 0.5  # below intrinsic value
    vols = implied_vol_vec(prices, hull["S"], strikes, hull["T"], hull["r"])
    assert vols[0] == pytest.approx(0.25, abs=1e-8)
    assert np.isnan(vols[1])
    assert vols[2] == pytest.approx(0.25, abs=1e-8)
