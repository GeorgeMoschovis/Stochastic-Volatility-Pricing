"""Generate the static images used by docs/index.html.

    python -m docs.make_illustrations
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from data.fetch_options import load_market_data
from pricing.calibration import calibrate_heston, heston_implied_vols, plot_smiles, smile_curve
from pricing.convergence import FIGURES, HULL, mc_convergence, plot_mc, plot_tree, tree_convergence
from pricing.heston import HestonParams

IMG = Path(__file__).resolve().parent / "img"
# dark to light for low, middle and high values of the parameter being varied
SHADES = ["#1c5cab", "#3987e5", "#cde2fb"]
SIZE = (4.2, 3.0)


def atm_term_structure(p: HestonParams, maturities: np.ndarray) -> np.ndarray:
    """At-the-money implied vol (K = F) for each maturity, in percent."""
    n = len(maturities)
    return 100 * heston_implied_vols(np.ones(n), np.ones(n), maturities, 0.0, p)


def term_structure_figure(name: str, label: str, values: list[float], base: dict) -> None:
    """How one parameter changes the at-the-money vol across maturities."""
    maturities = np.linspace(0.05, 3.0, 40)
    fig, ax = plt.subplots(figsize=SIZE)
    for value, shade in zip(values, SHADES):
        ax.plot(maturities, atm_term_structure(HestonParams(**{**base, name: value}), maturities), color=shade, label=f"{label} = {value}")
    ax.set(xlabel="maturity T (years)", ylabel="at-the-money vol (%)")
    ax.legend(fontsize=8)
    fig.savefig(IMG / f"heston_{name}.png")
    plt.close(fig)


def smile_figure(name: str, label: str, values: list[float], base: dict) -> None:
    """How one parameter changes the six-month smile."""
    fig, ax = plt.subplots(figsize=SIZE)
    for value, shade in zip(values, SHADES):
        k, vols = smile_curve(0.5, -0.3, 0.3, HestonParams(**{**base, name: value}))
        ax.plot(k, 100 * vols, color=shade, label=f"{label} = {value}")
    ax.set(xlabel="log-moneyness ln(K/F)", ylabel="implied vol (%)")
    ax.legend(fontsize=8)
    fig.savefig(IMG / f"heston_{name}.png")
    plt.close(fig)


def market_smile_figure(quotes: pd.DataFrame, expiry: str) -> None:
    """One market smile against the flat line that Black-Scholes assumes."""
    group = quotes[quotes.expiry == expiry]
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    ax.plot(group.log_moneyness, 100 * group.iv, "o", ms=4, color="#e6ebf5", label=f"S&P 500 options expiring {expiry}")
    ax.axhline(100 * group.iv.mean(), color="C1", ls="--", lw=1.5, label="what Black-Scholes assumes: one volatility")
    ax.set(xlabel="log-moneyness ln(K/F)", ylabel="implied vol (%)")
    ax.legend(fontsize=8)
    fig.savefig(IMG / "market_smile.png")
    plt.close(fig)


def main() -> None:
    """Create every image in docs/img."""
    IMG.mkdir(exist_ok=True)
    plt.style.use(FIGURES / "style.mplstyle")

    # v0, theta and kappa shape the term structure; sigma_v and rho shape the smile
    level = dict(v0=0.04, kappa=2.0, theta=0.04, sigma_v=0.3, rho=-0.7)
    term_structure_figure("v0", "v0", [0.02, 0.04, 0.08], level)
    term_structure_figure("theta", "theta", [0.02, 0.04, 0.08], level)
    term_structure_figure("kappa", "kappa", [0.5, 2.0, 8.0], {**level, "v0": 0.09})
    smile_figure("sigma_v", "sigma_v", [0.2, 0.5, 1.0], {**level, "rho": 0.0})
    smile_figure("rho", "rho", [-0.7, 0.0, 0.7], {**level, "sigma_v": 0.5})

    plot_tree(tree_convergence(**HULL), IMG / "tree_convergence.png")
    plot_mc(mc_convergence(**HULL), IMG / "mc_convergence.png")

    quotes, meta = load_market_data(r=0.05, source="sample")
    F, K, T, iv = (quotes[c].to_numpy() for c in ("forward", "strike", "T", "iv"))
    plot_smiles(quotes, calibrate_heston(F, K, T, iv, meta["r"]), IMG / "fit_smiles.png")
    market_smile_figure(quotes, "2027-02-19")
    print(f"images saved to {IMG}")


if __name__ == "__main__":
    main()
