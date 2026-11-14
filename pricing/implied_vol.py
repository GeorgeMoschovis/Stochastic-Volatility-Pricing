"""Implied volatility: the sigma that makes the Black-Scholes price equal to a given price."""

import numpy as np
from numpy.typing import ArrayLike
from scipy.optimize import brentq

from pricing.black_scholes import bs_price

SIGMA_MIN, SIGMA_MAX = 1e-4, 5.0


def no_arbitrage_bounds(S: float, K: float, T: float, r: float, q: float = 0.0, kind: str = "call") -> tuple[float, float]:
    r"""Model-free price bounds.

    Call: $\max(S e^{-qT} - K e^{-rT}, 0) \le c \le S e^{-qT}$.
    Put:  $\max(K e^{-rT} - S e^{-qT}, 0) \le p \le K e^{-rT}$.
    """
    spot_pv, strike_pv = S * np.exp(-q * T), K * np.exp(-r * T)
    if kind == "call":
        return max(spot_pv - strike_pv, 0.0), spot_pv
    return max(strike_pv - spot_pv, 0.0), strike_pv


def implied_vol(price: float, S: float, K: float, T: float, r: float, q: float = 0.0, kind: str = "call") -> tuple[float, str]:
    r"""Solve $\text{BS}(\sigma) = \text{price}$ for $\sigma \in [10^{-4}, 5]$ with Brent's method.

    Returns (sigma, "") on success and (nan, reason) when no volatility reproduces the price.
    """
    low, high = no_arbitrage_bounds(S, K, T, r, q, kind)
    if not low <= price <= high:
        return np.nan, f"price {price:.6g} is outside the no-arbitrage bounds [{low:.6g}, {high:.6g}]"

    def error(sigma: float) -> float:
        return bs_price(S, K, T, r, sigma, q, kind) - price

    # the BS price is increasing in sigma, so a root exists only if the errors at the ends have opposite signs
    if error(SIGMA_MIN) > 0:
        return np.nan, f"implied volatility is below {SIGMA_MIN}: the price has no time value"
    if error(SIGMA_MAX) < 0:
        return np.nan, f"implied volatility is above {SIGMA_MAX}"
    return float(brentq(error, SIGMA_MIN, SIGMA_MAX, xtol=1e-12)), ""


def implied_vol_vec(prices: ArrayLike, S: ArrayLike, K: ArrayLike, T: ArrayLike, r: ArrayLike,
                    q: ArrayLike = 0.0, kind: ArrayLike = "call", n_iter: int = 50) -> np.ndarray:
    """Implied volatility for arrays, by bisection on all elements at once (inputs are broadcast).

    `kind` may be one string or an array of "call"/"put". NaN where no sigma in [1e-4, 5] fits.
    Bisection replaces a Python loop over `implied_vol` because a calibration needs
    tens of thousands of inversions; 50 halvings shrink the bracket below 1e-14.
    """
    prices, S, K, T, r, q, kind = np.broadcast_arrays(prices, S, K, T, r, q, kind)
    is_call = kind == "call"

    def price(sigma: np.ndarray) -> np.ndarray:
        return np.where(is_call, bs_price(S, K, T, r, sigma, q, "call"), bs_price(S, K, T, r, sigma, q, "put"))

    low = np.full(prices.shape, SIGMA_MIN)
    high = np.full(prices.shape, SIGMA_MAX)
    solvable = (price(low) <= prices) & (prices <= price(high))
    for _ in range(n_iter):
        mid = 0.5 * (low + high)
        too_low = price(mid) < prices
        low = np.where(too_low, mid, low)
        high = np.where(too_low, high, mid)
    return np.where(solvable, 0.5 * (low + high), np.nan)
