import numpy as np
import pytest

from pricing.black_scholes import bs_price
from pricing.calibration import heston_implied_vols
from pricing.heston import HestonParams, heston_call_strikes, heston_cf, heston_mc, heston_price

PARAMS = HestonParams(v0=0.04, kappa=2.0, theta=0.05, sigma_v=0.5, rho=-0.7)
MARKET = dict(S=100.0, T=1.0, r=0.05, q=0.02)


@pytest.mark.parametrize("kind", ["call", "put"])
def test_reduces_to_black_scholes_when_vol_of_vol_vanishes(kind):
    sigma = 0.2
    flat = HestonParams(v0=sigma**2, kappa=2.0, theta=sigma**2, sigma_v=1e-3, rho=0.0)
    heston = heston_price(42, 40, 0.5, 0.10, 0.0, flat, kind)
    assert heston == pytest.approx(bs_price(42, 40, 0.5, 0.10, sigma, 0.0, kind), abs=1e-5)


def test_characteristic_function_basics():
    # phi(0) = 1 for any distribution; phi(-i) = E[S_T / F] = 1 is the martingale property behind parity
    assert heston_cf(0.0, 1.0, PARAMS) == pytest.approx(1.0)
    assert heston_cf(-1j, 1.0, PARAMS) == pytest.approx(1.0)


def test_put_call_parity():
    S, T, r, q = MARKET.values()
    for K in (80.0, 100.0, 120.0):
        call = heston_price(S, K, T, r, q, PARAMS, "call")
        put = heston_price(S, K, T, r, q, PARAMS, "put")
        assert call - put == pytest.approx(S * np.exp(-q * T) - K * np.exp(-r * T), abs=1e-10)


def test_price_respects_no_arbitrage_bounds():
    S, T, r, q = MARKET.values()
    for K in (60.0, 100.0, 150.0):
        call = heston_price(S, K, T, r, q, PARAMS)
        assert max(S * np.exp(-q * T) - K * np.exp(-r * T), 0) < call < S * np.exp(-q * T)


@pytest.mark.parametrize("T", [0.04, 0.5, 2.0])
def test_fast_grid_matches_adaptive_quadrature(T):
    S, _, r, q = MARKET.values()
    F = S * np.exp((r - q) * T)
    strikes = np.array([70.0, 90.0, 100.0, 110.0, 130.0])
    grid = heston_call_strikes(F, strikes, T, r, PARAMS)
    quad = [heston_price(S, K, T, r, q, PARAMS) for K in strikes]
    assert grid == pytest.approx(np.array(quad), abs=1e-7)


def test_semi_analytic_price_inside_monte_carlo_interval():
    # Feller holds for these parameters, so the Euler scheme has little bias
    p = HestonParams(v0=0.04, kappa=2.0, theta=0.04, sigma_v=0.3, rho=-0.7)
    S, T, r, q = MARKET.values()
    exact = heston_price(S, 100.0, T, r, q, p)
    mc = heston_mc(S, 100.0, T, r, q, p, n_paths=200_000, n_steps=100, seed=1)
    assert mc.ci_low < exact < mc.ci_high


def test_negative_correlation_gives_downward_skew():
    strikes = np.array([85.0, 100.0, 115.0])
    vols = heston_implied_vols(np.full(3, 100.0), strikes, np.full(3, 0.5), 0.0, PARAMS)
    assert vols[0] > vols[1] > vols[2]


def test_feller_flag():
    assert HestonParams(0.04, 2.0, 0.04, 0.3, -0.7).feller
    assert not HestonParams(0.04, 2.0, 0.04, 1.0, -0.7).feller
