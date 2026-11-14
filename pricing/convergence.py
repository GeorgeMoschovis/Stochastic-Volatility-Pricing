"""Convergence study: binomial tree and Monte Carlo against the Black-Scholes price.

Run `python -m pricing.convergence` to regenerate the PNGs in figures/.
"""

import time
from pathlib import Path
from typing import Callable

import numpy as np

from pricing.binomial import crr_price
from pricing.black_scholes import bs_price
from pricing.monte_carlo import METHODS, mc_price

FIGURES = Path(__file__).resolve().parent.parent / "figures"
HULL = dict(S=42.0, K=40.0, T=0.5, r=0.10, sigma=0.20, q=0.0)


def tree_convergence(S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0,
                     kind: str = "call", n_max: int = 1000) -> dict:
    """Tree price and signed error (tree minus Black-Scholes) for step counts from 10 to n_max.

    Every n up to 100 is included, then pairs (n, n+1) on a log grid,
    so odd and even step counts both appear and the oscillation is visible.
    """
    exact = float(bs_price(S, K, T, r, sigma, q, kind))
    coarse = np.geomspace(100, n_max, 30).astype(int)
    steps = np.unique(np.concatenate([np.arange(10, 101), coarse, coarse + 1]))
    steps = steps[steps <= n_max]
    prices = np.array([crr_price(S, K, T, r, sigma, q, kind, n=int(n)) for n in steps])
    return {"n": steps, "price": prices, "error": prices - exact, "bs_price": exact}


def timed(run: Callable, repeats: int = 3) -> tuple:
    """Run a function a few times and return (result, fastest time): the minimum is the least noisy timing."""
    fastest = float("inf")
    for _ in range(repeats):
        start = time.perf_counter()
        result = run()
        fastest = min(fastest, time.perf_counter() - start)
    return result, fastest


def mc_convergence(S: float, K: float, T: float, r: float, sigma: float, q: float = 0.0,
                   kind: str = "call", n_grid: np.ndarray | None = None, seed: int = 0) -> dict:
    """Absolute error, standard error and runtime of the three estimators for N = 10^2 ... 10^6."""
    exact = float(bs_price(S, K, T, r, sigma, q, kind))
    if n_grid is None:
        n_grid = np.logspace(2, 6, 13).astype(int)
    study = {"N": n_grid, "bs_price": exact}
    for method in METHODS:
        errors, std_errors, runtimes = [], [], []
        for n_paths in n_grid:
            result, runtime = timed(lambda: mc_price(S, K, T, r, sigma, q, kind, int(n_paths), seed, method))
            runtimes.append(runtime)
            errors.append(abs(result.price - exact))
            std_errors.append(result.std_error)
        study[method] = {"error": np.array(errors), "std_error": np.array(std_errors), "runtime": np.array(runtimes)}
    return study


def variance_reduction_summary(study: dict) -> list[dict]:
    """Compare the estimators at the largest N.

    vr_factor  = (SE_plain / SE)^2, the variance reduction at equal N.
    efficiency = SE^2 * runtime (lower is better); efficiency_gain is relative to plain MC,
    so it also charges each estimator for its extra computing time.
    """
    plain_se = study["plain"]["std_error"][-1]
    plain_time = study["plain"]["runtime"][-1]
    rows = []
    for method in METHODS:
        se, runtime = study[method]["std_error"][-1], study[method]["runtime"][-1]
        # a zero standard error (payoff exactly linear in S_T) means an infinite reduction
        vr_factor = (plain_se / se) ** 2 if se > 0 else float("inf")
        rows.append({
            "method": method,
            "n_paths": int(study["N"][-1]),
            "std_error": float(se),
            "vr_factor": float(vr_factor),
            "runtime": float(runtime),
            "efficiency": float(se**2 * runtime),
            "efficiency_gain": float(vr_factor * plain_time / runtime),
        })
    return rows


def plot_tree(study: dict, path: Path) -> None:
    """Two panels: the tree price for n up to 100, and the absolute error on a log-log scale."""
    import matplotlib.pyplot as plt

    n, price, error = study["n"], study["price"], np.abs(study["error"])
    odd = n % 2 == 1
    fig, (left, right) = plt.subplots(1, 2, figsize=(11, 4))

    small = n <= 100
    left.plot(n[small], price[small], lw=1.2, marker="o", ms=3, label="CRR tree")
    left.axhline(study["bs_price"], color="#e6ebf5", lw=1, ls="--", label="Black-Scholes")
    left.set(title="Tree price oscillates around Black-Scholes", xlabel="steps n", ylabel="call price")
    left.legend()

    right.loglog(n[~odd], error[~odd], "o", ms=3.5, label="even n")
    right.loglog(n[odd], error[odd], "o", ms=3.5, label="odd n")
    right.loglog(n, error[0] * n[0] / n, color="#8b97b0", lw=1, ls="--", label="slope -1")
    right.set(title="Absolute error decays like 1/n", xlabel="steps n", ylabel="|tree - BS|")
    right.legend()
    fig.savefig(path)
    plt.close(fig)


def plot_mc(study: dict, path: Path) -> None:
    """Standard errors (lines) and realised errors (dots) of the three estimators on a log-log scale."""
    import matplotlib.pyplot as plt

    N = study["N"]
    labels = {"plain": "plain", "antithetic": "antithetic", "control_variate": "control variate"}
    fig, ax = plt.subplots(figsize=(7, 4.5))
    for i, method in enumerate(METHODS):
        ax.loglog(N, study[method]["std_error"], color=f"C{i}", label=f"{labels[method]}: standard error")
        ax.loglog(N, study[method]["error"], "o", color=f"C{i}", ms=4, alpha=0.75)
    reference = study["plain"]["std_error"][0] * np.sqrt(N[0] / N)
    ax.loglog(N, 2.5 * reference, color="#8b97b0", lw=1, ls="--", label="slope -1/2")
    ax.plot([], [], "o", color="#8b97b0", ms=4, label="dots: |MC - BS|")
    ax.set(title=r"Monte Carlo error falls like $N^{-1/2}$", xlabel="paths N", ylabel="error")
    ax.legend(fontsize=8)
    fig.savefig(path)
    plt.close(fig)


def main() -> None:
    """Run the study on Hull's example, save both figures and print the variance-reduction table."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.style.use(FIGURES / "style.mplstyle")
    tree = tree_convergence(**HULL)
    mc = mc_convergence(**HULL)
    plot_tree(tree, FIGURES / "tree_convergence.png")
    plot_mc(mc, FIGURES / "mc_convergence.png")

    print(f"Black-Scholes price {tree['bs_price']:.6f}")
    print(f"tree error at n = {tree['n'][-1]}: {tree['error'][-1]:+.2e}")
    print(f"{'estimator':<16}{'std error':>11}{'VR factor':>11}{'time (s)':>10}{'efficiency gain':>17}")
    for row in variance_reduction_summary(mc):
        print(f"{row['method']:<16}{row['std_error']:>11.6f}{row['vr_factor']:>11.2f}"
              f"{row['runtime']:>10.3f}{row['efficiency_gain']:>17.2f}")
    print(f"figures saved to {FIGURES}")


if __name__ == "__main__":
    main()
