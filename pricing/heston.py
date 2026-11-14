"""Heston stochastic-volatility model: characteristic function, semi-analytic prices and a Monte Carlo check.

Model under the risk-neutral measure:
    dS = (r - q) S dt + sqrt(v) S dW_S
    dv = kappa (theta - v) dt + sigma_v sqrt(v) dW_v,    corr(dW_S, dW_v) = rho
"""

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from numpy.typing import ArrayLike
from scipy.integrate import quad
from scipy.special import roots_legendre

from pricing.monte_carlo import MCResult, payoff, summarise


@dataclass
class HestonParams:
    r"""$v_0$ initial variance, $\kappa$ mean-reversion speed, $\theta$ long-run variance,
    $\sigma_v$ volatility of variance, $\rho$ correlation between price and variance shocks."""

    v0: float
    kappa: float
    theta: float
    sigma_v: float
    rho: float

    @property
    def feller(self) -> bool:
        r"""Feller condition $2\kappa\theta > \sigma_v^2$: if true the variance never touches zero."""
        return 2 * self.kappa * self.theta > self.sigma_v**2


def heston_cf(u: ArrayLike, T: float, p: HestonParams) -> ArrayLike:
    r"""Characteristic function $\varphi(u) = E[e^{iuX_T}]$ of $X_T = \ln(S_T / F)$, with $F = S_0 e^{(r-q)T}$.

    $\varphi(u) = \exp(C + D v_0)$ with $\beta = \kappa - \rho\sigma_v iu$,
    $d = \sqrt{\beta^2 + \sigma_v^2 (iu + u^2)}$, $g = \frac{\beta - d}{\beta + d}$,

    $C = \frac{\kappa\theta}{\sigma_v^2}\Big[(\beta - d)T - 2\ln\frac{1 - g e^{-dT}}{1 - g}\Big]$,
    $D = \frac{\beta - d}{\sigma_v^2} \cdot \frac{1 - e^{-dT}}{1 - g e^{-dT}}$.

    This is the "little Heston trap" form of Albrecher, Mayer, Schoutens and Tistaert (2007).
    It is algebraically equal to Heston's original formula but uses $e^{-dT}$ instead of $e^{+dT}$,
    which keeps the complex logarithm on its principal branch for long maturities.
    u may be complex and may be an array.
    """
    iu = 1j * u
    beta = p.kappa - p.rho * p.sigma_v * iu
    d = np.sqrt(beta**2 + p.sigma_v**2 * (iu + u**2))
    g = (beta - d) / (beta + d)
    decay = np.exp(-d * T)
    C = p.kappa * p.theta / p.sigma_v**2 * ((beta - d) * T - 2 * np.log((1 - g * decay) / (1 - g)))
    D = (beta - d) / p.sigma_v**2 * (1 - decay) / (1 - g * decay)
    return np.exp(C + D * p.v0)


def integration_cutoff(T: float, p: HestonParams, tol: float = 1e-10, cap: float = 6400.0) -> float:
    """Finite upper limit for the pricing integrals.

    The integrand is bounded by |phi(u)| / u, so the limit is doubled (25, 50, 100, ...) until
    that bound is below tol. Long maturities stop at 25 or 50; a two-week option with a large
    volatility of variance needs more than 1000, because its characteristic function decays slowly.
    """
    u_max = 25.0
    while abs(heston_cf(u_max, T, p)) / u_max > tol and u_max < cap:
        u_max *= 2
    return u_max


def heston_price(S: float, K: float, T: float, r: float, q: float, p: HestonParams, kind: str = "call") -> float:
    r"""European option price by numerical integration with scipy's adaptive `quad`.

    $c = e^{-rT}(F P_1 - K P_2)$ with $k = \ln(K/F)$ and the Gil-Pelaez inversions

    $P_2 = \frac12 + \frac1\pi \int_0^\infty \text{Re}\Big[\frac{e^{-iuk}\varphi(u)}{iu}\Big]du$,
    $P_1 = \frac12 + \frac1\pi \int_0^\infty \text{Re}\Big[\frac{e^{-iuk}\varphi(u - i)}{iu}\Big]du$.

    Puts follow from put-call parity. The integrals stop at `integration_cutoff`.
    """
    if kind not in ("call", "put"):
        raise ValueError("kind must be 'call' or 'put'")
    if min(S, K, T) <= 0:
        raise ValueError("S, K and T must be positive")
    F = S * np.exp((r - q) * T)
    k = np.log(K / F)
    u_max = integration_cutoff(T, p)

    def integrand(u: float, shift: complex) -> float:
        return (np.exp(-1j * u * k) * heston_cf(u + shift, T, p) / (1j * u)).real

    P1 = 0.5 + quad(integrand, 0, u_max, args=(-1j,), limit=500)[0] / np.pi
    P2 = 0.5 + quad(integrand, 0, u_max, args=(0,), limit=500)[0] / np.pi
    call = np.exp(-r * T) * (F * P1 - K * P2)
    if kind == "call":
        return float(call)
    return float(call - np.exp(-r * T) * (F - K))


@lru_cache(maxsize=None)
def gauss_legendre(n: int) -> tuple[np.ndarray, np.ndarray]:
    """Gauss-Legendre nodes and weights on [-1, 1]. Cached: they are slow to compute and reused all the time."""
    return roots_legendre(n)


def heston_call_strikes(F: float, strikes: ArrayLike, T: float, r: float, p: HestonParams) -> np.ndarray:
    """Call prices for many strikes at one maturity, given the forward F.

    Same integrals as `heston_price`, but on a fixed Gauss-Legendre grid: the characteristic
    function does not depend on the strike, so it is evaluated once and reused for every strike.
    This is what makes calibration fast.
    """
    strikes = np.asarray(strikes, dtype=float)
    u_max = integration_cutoff(T, p)
    # enough nodes to resolve the oscillation of exp(-iuk) over [0, u_max]
    x, w = gauss_legendre(max(128, int(0.4 * u_max)))
    u = 0.5 * u_max * (x + 1)
    w = 0.5 * u_max * w

    k = np.log(strikes / F)[:, None]
    kernel = np.exp(-1j * u * k) / (1j * u)
    P1 = 0.5 + (kernel * heston_cf(u - 1j, T, p)).real @ w / np.pi
    P2 = 0.5 + (kernel * heston_cf(u, T, p)).real @ w / np.pi
    return np.exp(-r * T) * (F * P1 - strikes * P2)


def heston_mc(
    S: float, K: float, T: float, r: float, q: float, p: HestonParams, kind: str = "call",
    n_paths: int = 100_000, n_steps: int = 200, seed: int | None = 0,
) -> MCResult:
    r"""Monte Carlo price with a full-truncation Euler scheme, used only as an independent check.

    With $v^+ = \max(v, 0)$:
    $\ln S \mathrel{+}= (r - q - v^+/2)\Delta t + \sqrt{v^+ \Delta t}\, Z_1$,
    $v \mathrel{+}= \kappa(\theta - v^+)\Delta t + \sigma_v \sqrt{v^+ \Delta t}\, Z_2$,
    $Z_2 = \rho Z_1 + \sqrt{1 - \rho^2}\, Z_\perp$.
    """
    rng = np.random.default_rng(seed)
    dt = T / n_steps
    log_S = np.full(n_paths, np.log(S))
    v = np.full(n_paths, p.v0)
    for _ in range(n_steps):
        Z1 = rng.standard_normal(n_paths)
        Z2 = p.rho * Z1 + np.sqrt(1 - p.rho**2) * rng.standard_normal(n_paths)
        # the variance can step below zero; it is floored only where it is used
        v_plus = np.maximum(v, 0.0)
        log_S += (r - q - 0.5 * v_plus) * dt + np.sqrt(v_plus * dt) * Z1
        v += p.kappa * (p.theta - v_plus) * dt + p.sigma_v * np.sqrt(v_plus * dt) * Z2
    samples = np.exp(-r * T) * payoff(np.exp(log_S), K, kind)
    return summarise(samples, "heston_euler", n_paths)
