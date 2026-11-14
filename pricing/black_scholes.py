"""Black-Scholes-Merton prices and analytic Greeks for European options.

Conventions used in the whole project: S spot, K strike, T maturity in years,
r continuously compounded risk-free rate, q continuous dividend yield,
sigma volatility. All functions accept floats or numpy arrays.
"""

import numpy as np
from scipy.special import ndtr  # standard normal CDF, fast on arrays

Num = float | np.ndarray


def check_inputs(S: Num, K: Num, T: Num, sigma: Num, kind: str) -> None:
    """Raise a clear error if an input is outside the model's domain."""
    if kind not in ("call", "put"):
        raise ValueError("kind must be 'call' or 'put'")
    for name, value in (("S", S), ("K", K), ("T", T), ("sigma", sigma)):
        if np.any(np.asarray(value) <= 0):
            raise ValueError(f"{name} must be positive")


def norm_pdf(x: Num) -> Num:
    r"""Standard normal density $\varphi(x) = e^{-x^2/2} / \sqrt{2\pi}$."""
    return np.exp(-0.5 * x**2) / np.sqrt(2 * np.pi)


def d1_d2(S: Num, K: Num, T: Num, r: Num, sigma: Num, q: Num = 0.0) -> tuple[Num, Num]:
    r"""$d_1 = \frac{\ln(S/K) + (r - q + \sigma^2/2)T}{\sigma\sqrt{T}}$, $d_2 = d_1 - \sigma\sqrt{T}$."""
    vol_sqrt_T = sigma * np.sqrt(T)
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / vol_sqrt_T
    return d1, d1 - vol_sqrt_T


def bs_price(S: Num, K: Num, T: Num, r: Num, sigma: Num, q: Num = 0.0, kind: str = "call") -> Num:
    r"""European option price.

    $c = S e^{-qT} N(d_1) - K e^{-rT} N(d_2)$,
    $p = K e^{-rT} N(-d_2) - S e^{-qT} N(-d_1)$.
    """
    check_inputs(S, K, T, sigma, kind)
    d1, d2 = d1_d2(S, K, T, r, sigma, q)
    if kind == "call":
        return S * np.exp(-q * T) * ndtr(d1) - K * np.exp(-r * T) * ndtr(d2)
    return K * np.exp(-r * T) * ndtr(-d2) - S * np.exp(-q * T) * ndtr(-d1)


def bs_delta(S: Num, K: Num, T: Num, r: Num, sigma: Num, q: Num = 0.0, kind: str = "call") -> Num:
    r"""$\Delta = \partial V / \partial S$: $e^{-qT} N(d_1)$ for a call, $-e^{-qT} N(-d_1)$ for a put."""
    check_inputs(S, K, T, sigma, kind)
    d1, _ = d1_d2(S, K, T, r, sigma, q)
    if kind == "call":
        return np.exp(-q * T) * ndtr(d1)
    return -np.exp(-q * T) * ndtr(-d1)


def bs_gamma(S: Num, K: Num, T: Num, r: Num, sigma: Num, q: Num = 0.0, kind: str = "call") -> Num:
    r"""$\Gamma = \partial^2 V / \partial S^2 = \frac{e^{-qT}\varphi(d_1)}{S\sigma\sqrt{T}}$ (same for calls and puts)."""
    check_inputs(S, K, T, sigma, kind)
    d1, _ = d1_d2(S, K, T, r, sigma, q)
    return np.exp(-q * T) * norm_pdf(d1) / (S * sigma * np.sqrt(T))


def bs_vega(S: Num, K: Num, T: Num, r: Num, sigma: Num, q: Num = 0.0, kind: str = "call") -> Num:
    r"""$\nu = \partial V / \partial \sigma = S e^{-qT} \varphi(d_1) \sqrt{T}$, per unit of volatility (1.00 = 100 vol points)."""
    check_inputs(S, K, T, sigma, kind)
    d1, _ = d1_d2(S, K, T, r, sigma, q)
    return S * np.exp(-q * T) * norm_pdf(d1) * np.sqrt(T)


def bs_theta(S: Num, K: Num, T: Num, r: Num, sigma: Num, q: Num = 0.0, kind: str = "call") -> Num:
    r"""$\Theta = -\partial V / \partial T$, per year.

    Call: $-\frac{S e^{-qT}\varphi(d_1)\sigma}{2\sqrt{T}} - rKe^{-rT}N(d_2) + qSe^{-qT}N(d_1)$.
    Put:  $-\frac{S e^{-qT}\varphi(d_1)\sigma}{2\sqrt{T}} + rKe^{-rT}N(-d_2) - qSe^{-qT}N(-d_1)$.
    """
    check_inputs(S, K, T, sigma, kind)
    d1, d2 = d1_d2(S, K, T, r, sigma, q)
    decay = -S * np.exp(-q * T) * norm_pdf(d1) * sigma / (2 * np.sqrt(T))
    if kind == "call":
        return decay - r * K * np.exp(-r * T) * ndtr(d2) + q * S * np.exp(-q * T) * ndtr(d1)
    return decay + r * K * np.exp(-r * T) * ndtr(-d2) - q * S * np.exp(-q * T) * ndtr(-d1)


def bs_rho(S: Num, K: Num, T: Num, r: Num, sigma: Num, q: Num = 0.0, kind: str = "call") -> Num:
    r"""$\rho = \partial V / \partial r$: $KTe^{-rT}N(d_2)$ for a call, $-KTe^{-rT}N(-d_2)$ for a put."""
    check_inputs(S, K, T, sigma, kind)
    _, d2 = d1_d2(S, K, T, r, sigma, q)
    if kind == "call":
        return K * T * np.exp(-r * T) * ndtr(d2)
    return -K * T * np.exp(-r * T) * ndtr(-d2)


def bs_greeks(S: Num, K: Num, T: Num, r: Num, sigma: Num, q: Num = 0.0, kind: str = "call") -> dict[str, Num]:
    """All five analytic Greeks in one dictionary."""
    args = (S, K, T, r, sigma, q, kind)
    return {
        "delta": bs_delta(*args),
        "gamma": bs_gamma(*args),
        "vega": bs_vega(*args),
        "theta": bs_theta(*args),
        "rho": bs_rho(*args),
    }
