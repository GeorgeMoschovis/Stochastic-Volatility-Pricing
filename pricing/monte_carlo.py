"""Monte Carlo pricing of European options: plain, antithetic and control-variate estimators.

All three use the same budget: n_paths is the number of simulated terminal prices.
"""

from dataclasses import dataclass

import numpy as np

from pricing.black_scholes import check_inputs

METHODS = ("plain", "antithetic", "control_variate")


@dataclass
class MCResult:
    """A Monte Carlo estimate with its standard error and 95% confidence interval."""

    price: float
    std_error: float
    ci_low: float
    ci_high: float
    method: str
    n_paths: int


def summarise(samples: np.ndarray, method: str, n_paths: int) -> MCResult:
    r"""Mean of i.i.d. samples, $\text{SE} = s/\sqrt{m}$ and the interval $\text{mean} \pm 1.96\,\text{SE}$."""
    price = float(samples.mean())
    std_error = float(samples.std(ddof=1) / np.sqrt(len(samples)))
    return MCResult(price, std_error, price - 1.96 * std_error, price + 1.96 * std_error, method, n_paths)


def terminal_prices(S: float, T: float, r: float, sigma: float, q: float, Z: np.ndarray) -> np.ndarray:
    r"""Exact simulation: $S_T = S \exp\big((r - q - \sigma^2/2)T + \sigma\sqrt{T}\,Z\big)$."""
    return S * np.exp((r - q - 0.5 * sigma**2) * T + sigma * np.sqrt(T) * Z)


def payoff(ST: np.ndarray, K: float, kind: str) -> np.ndarray:
    """Call payoff max(S_T - K, 0) or put payoff max(K - S_T, 0)."""
    if kind == "call":
        return np.maximum(ST - K, 0.0)
    return np.maximum(K - ST, 0.0)


def mc_plain(
    S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0,
    kind: str = "call", n_paths: int = 100_000, seed: int | None = 0,
) -> MCResult:
    r"""Plain estimator $\hat V = e^{-rT} \frac{1}{N} \sum_i \text{payoff}(S_T^{(i)})$."""
    check_inputs(S, K, T, sigma, kind)
    Z = np.random.default_rng(seed).standard_normal(n_paths)
    samples = np.exp(-r * T) * payoff(terminal_prices(S, T, r, sigma, q, Z), K, kind)
    return summarise(samples, "plain", n_paths)


def mc_antithetic(
    S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0,
    kind: str = "call", n_paths: int = 100_000, seed: int | None = 0,
) -> MCResult:
    r"""Antithetic estimator: each $Z_i$ is paired with $-Z_i$ and the two discounted payoffs are averaged.

    The pair averages are i.i.d., so the standard error is computed from the N/2 pairs.
    """
    check_inputs(S, K, T, sigma, kind)
    Z = np.random.default_rng(seed).standard_normal(n_paths // 2)
    up = payoff(terminal_prices(S, T, r, sigma, q, Z), K, kind)
    down = payoff(terminal_prices(S, T, r, sigma, q, -Z), K, kind)
    samples = np.exp(-r * T) * 0.5 * (up + down)
    return summarise(samples, "antithetic", n_paths)


def mc_control_variate(
    S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0,
    kind: str = "call", n_paths: int = 100_000, seed: int | None = 0,
) -> MCResult:
    r"""Control-variate estimator using $S_T$, whose mean $S e^{(r-q)T}$ is known.

    $\hat V_{CV} = \hat V - b^* \big(\overline{S_T} - S e^{(r-q)T}\big) e^{-rT}$,
    $b^* = \widehat{\text{Cov}}(Y, S_T) / \widehat{\text{Var}}(S_T)$, with $Y$ the payoff.
    """
    check_inputs(S, K, T, sigma, kind)
    Z = np.random.default_rng(seed).standard_normal(n_paths)
    ST = terminal_prices(S, T, r, sigma, q, Z)
    Y = payoff(ST, K, kind)
    b = np.cov(Y, ST)[0, 1] / ST.var(ddof=1)
    # subtract the part of the payoff noise that is explained by S_T
    samples = np.exp(-r * T) * (Y - b * (ST - S * np.exp((r - q) * T)))
    return summarise(samples, "control_variate", n_paths)


def mc_price(
    S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0,
    kind: str = "call", n_paths: int = 100_000, seed: int | None = 0, method: str = "plain",
) -> MCResult:
    """Dispatch to one of the three estimators by name."""
    if n_paths < 2:
        raise ValueError("n_paths must be at least 2")
    estimators = {"plain": mc_plain, "antithetic": mc_antithetic, "control_variate": mc_control_variate}
    if method not in estimators:
        raise ValueError(f"method must be one of {METHODS}")
    return estimators[method](S, K, T, r, sigma, q, kind, n_paths, seed)


def variance_reduction_factor(plain: MCResult, other: MCResult) -> float:
    r"""$(\text{SE}_{plain} / \text{SE}_{other})^2$: how many times more plain paths give the same accuracy."""
    if other.std_error == 0:
        # happens when the payoff is exactly linear in S_T, e.g. a deep in-the-money call with tiny volatility
        return float("inf")
    return (plain.std_error / other.std_error) ** 2
