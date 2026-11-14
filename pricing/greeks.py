"""Finite-difference Greeks that work with any pricer, and a comparison with the analytic Greeks.

A pricer is any function pricer(S, K, T, r, sigma, q, kind) -> float.
"""

from typing import Callable

from pricing.black_scholes import bs_greeks

Pricer = Callable[..., float]


def fd_greeks(
    pricer: Pricer,
    S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0, kind: str = "call",
    bump_S: float = 0.01,
    bump_sigma: float = 0.001,
    bump_r: float = 0.001,
    bump_T: float = 1 / 365,
) -> dict[str, float]:
    r"""Central finite-difference Greeks.

    $\Delta \approx \frac{V(S+h) - V(S-h)}{2h}$,
    $\Gamma \approx \frac{V(S+h) - 2V(S) + V(S-h)}{h^2}$,
    and the same central difference in $\sigma$, $r$ and $T$ for vega, rho and theta
    ($\Theta = -\partial V / \partial T$).

    bump_S is relative to S; the other bumps are absolute.
    The default 1% spot bump suits tree and Monte Carlo prices, which are piecewise linear in S:
    a tiny bump would give a meaningless gamma. For a smooth pricer a smaller bump is more accurate.
    For a Monte Carlo pricer use a fixed seed, so every bumped price uses the same random numbers.
    """
    h = bump_S * S
    # keep T - h_T positive for very short maturities
    h_T = min(bump_T, 0.5 * T)

    def V(S=S, T=T, r=r, sigma=sigma) -> float:
        return pricer(S, K, T, r, sigma, q, kind)

    base, up, down = V(), V(S=S + h), V(S=S - h)
    return {
        "delta": (up - down) / (2 * h),
        "gamma": (up - 2 * base + down) / h**2,
        "vega": (V(sigma=sigma + bump_sigma) - V(sigma=sigma - bump_sigma)) / (2 * bump_sigma),
        "theta": -(V(T=T + h_T) - V(T=T - h_T)) / (2 * h_T),
        "rho": (V(r=r + bump_r) - V(r=r - bump_r)) / (2 * bump_r),
    }


def compare_greeks(
    pricer: Pricer,
    S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0, kind: str = "call",
    **bumps: float,
) -> list[dict]:
    """Analytic Black-Scholes Greeks next to finite-difference Greeks of `pricer`, with errors."""
    analytic = bs_greeks(S, K, T, r, sigma, q, kind)
    numeric = fd_greeks(pricer, S, K, T, r, sigma, q, kind, **bumps)
    rows = []
    for name, exact in analytic.items():
        error = abs(numeric[name] - exact)
        rows.append({
            "greek": name,
            "analytic": float(exact),
            "finite_diff": float(numeric[name]),
            "abs_error": float(error),
            "rel_error": float(error / abs(exact)) if exact != 0 else float("nan"),
        })
    return rows
