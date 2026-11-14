"""Heston calibration to market implied volatilities, across all maturities at once.

Run `python -m pricing.calibration` to calibrate to the sample chain and regenerate the smile figures.
"""

import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.typing import ArrayLike
from scipy.optimize import least_squares

from pricing.heston import HestonParams, heston_call_strikes
from pricing.implied_vol import implied_vol_vec

# bounds for (v0, kappa, theta, sigma_v, rho)
LOWER = [1e-4, 1e-2, 1e-4, 1e-2, -0.99]
UPPER = [1.0, 10.0, 1.0, 3.0, 0.99]


@dataclass
class CalibrationResult:
    params: HestonParams
    model_iv: np.ndarray
    rmse: float
    runtime: float
    n_evaluations: int
    converged: bool


def heston_implied_vols(F: ArrayLike, K: ArrayLike, T: ArrayLike, r: float, p: HestonParams) -> np.ndarray:
    """Black implied volatilities of Heston prices for arrays of options.

    F, K and T have one entry per option; options with the same maturity must share one forward.
    Where a model price has no implied vol (numerically below intrinsic value) the result is 0.
    """
    F, K, T = (np.asarray(x, dtype=float) for x in (F, K, T))
    is_put = K < F
    prices = np.empty(len(K))
    for maturity in np.unique(T):
        m = T == maturity
        calls = heston_call_strikes(F[m][0], K[m], maturity, r, p)
        # use the out-of-the-money option (put below the forward, by parity): its price is pure
        # time value, so the inversion to an implied vol is well conditioned
        prices[m] = np.where(is_put[m], calls - np.exp(-r * maturity) * (F[m] - K[m]), calls)
    # q = r turns Black-Scholes into Black's formula on the forward
    vols = implied_vol_vec(prices, F, K, T, r, q=r, kind=np.where(is_put, "put", "call"))
    return np.nan_to_num(vols, nan=0.0)


def rmse_points(errors: ArrayLike) -> float:
    """Root-mean-square error in volatility points (1 point = 0.01 of implied vol)."""
    return float(100 * np.sqrt(np.mean(np.square(errors))))


def rmse_by_maturity(T: ArrayLike, errors: ArrayLike) -> dict[float, float]:
    """RMSE in volatility points for each maturity separately."""
    T, errors = np.asarray(T), np.asarray(errors)
    return {float(t): rmse_points(errors[T == t]) for t in np.unique(T)}


def initial_guess(F: np.ndarray, K: np.ndarray, T: np.ndarray, market_iv: np.ndarray) -> list[float]:
    """Starting point of the optimiser.

    v0 and theta are the at-the-money variances of the shortest and longest maturity (what the
    model should roughly reproduce at both ends); kappa = 2, sigma_v = 0.5 and rho = -0.7 are
    typical values for equity indices.
    """
    def atm_variance(maturity: float) -> float:
        m = T == maturity
        return float(market_iv[m][np.argmin(np.abs(np.log(K[m] / F[m])))] ** 2)

    return [atm_variance(T.min()), 2.0, atm_variance(T.max()), 0.5, -0.7]


def calibrate_heston(F: ArrayLike, K: ArrayLike, T: ArrayLike, market_iv: ArrayLike, r: float,
                     weights: ArrayLike | None = None, x0: ArrayLike | None = None) -> CalibrationResult:
    r"""Fit the five Heston parameters to all maturities jointly.

    $\min_{v_0,\kappa,\theta,\sigma_v,\rho} \sum_i w_i \big(\sigma^{IV}_{Heston,i} - \sigma^{IV}_{mkt,i}\big)^2$

    solved with a bounded trust-region least-squares method. Weights default to 1.
    """
    F, K, T, market_iv = (np.asarray(x, dtype=float) for x in (F, K, T, market_iv))
    weights = np.ones(len(K)) if weights is None else np.asarray(weights, dtype=float)
    if x0 is None:
        x0 = initial_guess(F, K, T, market_iv)
    x0 = np.clip(x0, LOWER, UPPER)

    n_evaluations = 0

    def residuals(x: np.ndarray) -> np.ndarray:
        nonlocal n_evaluations
        n_evaluations += 1
        return np.sqrt(weights) * (heston_implied_vols(F, K, T, r, HestonParams(*x)) - market_iv)

    start = time.perf_counter()
    # diff_step: finite-difference steps well above the noise of the numerical integration
    fit = least_squares(residuals, x0, bounds=(LOWER, UPPER), x_scale="jac", diff_step=1e-4)
    runtime = time.perf_counter() - start

    params = HestonParams(*(float(x) for x in fit.x))
    model_iv = heston_implied_vols(F, K, T, r, params)
    return CalibrationResult(params, model_iv, rmse_points(model_iv - market_iv), runtime, n_evaluations, bool(fit.success))


def flat_bs_benchmark(T: ArrayLike, market_iv: ArrayLike) -> np.ndarray:
    """Black-Scholes benchmark: one constant volatility per maturity.

    The constant that minimises squared vol errors is the mean implied vol of that maturity.
    Returns the benchmark vol for each option.
    """
    T, market_iv = np.asarray(T, dtype=float), np.asarray(market_iv, dtype=float)
    flat = np.empty(len(T))
    for maturity in np.unique(T):
        flat[T == maturity] = market_iv[T == maturity].mean()
    return flat


def smile_curve(T: float, k_min: float, k_max: float, p: HestonParams, n: int = 60) -> tuple[np.ndarray, np.ndarray]:
    """Heston implied vols on a fine grid of log-moneyness k = ln(K/F), for plotting one smile.

    In terms of k the smile does not depend on the forward or the rate, so F = 1 and r = 0 are used.
    """
    k = np.linspace(k_min, k_max, n)
    return k, heston_implied_vols(np.ones(n), np.exp(k), np.full(n, T), 0.0, p)


def plot_smiles(quotes: pd.DataFrame, result: CalibrationResult, path: Path) -> None:
    """One panel per expiry: market dots, Heston line, flat Black-Scholes dashed line."""
    import matplotlib.pyplot as plt

    expiries = list(quotes.groupby("expiry"))
    fig, axes = plt.subplots(2, (len(expiries) + 1) // 2, figsize=(14, 6.5), sharey=True, constrained_layout=True)
    for ax, (expiry, group) in zip(axes.ravel(), expiries):
        T = group["T"].iloc[0]
        k, vols = smile_curve(T, group.log_moneyness.min(), group.log_moneyness.max(), result.params)
        ax.plot(group.log_moneyness, 100 * group.iv, "o", ms=3.5, color="#e6ebf5", label="market")
        ax.plot(k, 100 * vols, color="C0", label="Heston")
        ax.axhline(100 * group.iv.mean(), color="C1", lw=1.3, ls="--", label="flat Black-Scholes")
        ax.set_title(f"{expiry}  (T = {T:.2f})", fontsize=9)
    for ax in axes[-1]:
        ax.set_xlabel("log-moneyness ln(K/F)")
    for ax in axes[:, 0]:
        ax.set_ylabel("implied vol (%)")
    axes[0, 0].legend(fontsize=8)
    fig.savefig(path)
    plt.close(fig)


def plot_surface(quotes: pd.DataFrame, result: CalibrationResult, path: Path) -> None:
    """Heston implied-vol surface with the market quotes as points."""
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=(8, 6))
    ax = fig.add_subplot(projection="3d")
    for expiry, group in quotes.groupby("expiry"):
        T = group["T"].iloc[0]
        k, vols = smile_curve(T, group.log_moneyness.min(), group.log_moneyness.max(), result.params)
        ax.plot(k, np.full_like(k, T), 100 * vols, color="C0", lw=1.5)
        ax.scatter(group.log_moneyness, group["T"], 100 * group.iv, color="#e6ebf5", s=7, depthshade=False)
    ax.plot([], [], color="C0", label="Heston fit")
    ax.scatter([], [], color="#e6ebf5", s=7, label="market quotes")
    ax.set(xlabel="log-moneyness ln(K/F)", ylabel="maturity T (years)", zlabel="implied vol (%)")
    ax.view_init(elev=22, azim=-58)
    # shrink the box a little so the axis labels are not clipped
    ax.set_box_aspect(None, zoom=0.85)
    ax.legend(loc="upper left", fontsize=8)
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.set_pane_color("#111a2e")
    fig.savefig(path)
    plt.close(fig)


def main() -> None:
    """Calibrate to the sample chain, print the results and save the smile figures."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from data.fetch_options import load_market_data
    from pricing.convergence import FIGURES

    quotes, meta = load_market_data(r=0.05, source="sample")
    F, K, T, iv = (quotes[c].to_numpy() for c in ("forward", "strike", "T", "iv"))
    result = calibrate_heston(F, K, T, iv, meta["r"])
    flat = flat_bs_benchmark(T, iv)

    p = result.params
    print(f"{meta['ticker']} snapshot {meta['snapshot_time']}, {len(quotes)} quotes, {quotes.expiry.nunique()} expiries")
    print(f"v0={p.v0:.4f}  kappa={p.kappa:.3f}  theta={p.theta:.4f}  sigma_v={p.sigma_v:.3f}  rho={p.rho:.3f}")
    print(f"Feller condition holds: {p.feller}   runtime {result.runtime:.1f} s   evaluations {result.n_evaluations}")
    print(f"RMSE Heston {result.rmse:.2f} vol points, flat Black-Scholes {rmse_points(flat - iv):.2f} vol points")
    heston_rmse, flat_rmse = rmse_by_maturity(T, result.model_iv - iv), rmse_by_maturity(T, flat - iv)
    for maturity in heston_rmse:
        print(f"  T = {maturity:.3f}: Heston {heston_rmse[maturity]:.2f}, flat BS {flat_rmse[maturity]:.2f}")

    plt.style.use(FIGURES / "style.mplstyle")
    plot_smiles(quotes, result, FIGURES / "heston_smiles.png")
    plot_surface(quotes, result, FIGURES / "vol_surface.png")
    print(f"figures saved to {FIGURES}")


if __name__ == "__main__":
    main()
