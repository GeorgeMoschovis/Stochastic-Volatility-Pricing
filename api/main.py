"""FastAPI backend: JSON endpoints under /api, the web app at / and the documentation at /docs-site.

Run with:  uvicorn api.main:app --reload
"""

from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Literal

import numpy as np
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from scipy.interpolate import griddata

from api.schemas import (
    CalibrationRequest, GreeksRequest, GreeksSurfaceRequest, HestonSurfaceRequest,
    ImpliedVolRequest, MarketQuote, OptionInputs, PriceRequest,
)
from data.fetch_options import load_market_data
from pricing.binomial import crr_price
from pricing.black_scholes import bs_greeks, bs_price
from pricing.calibration import (
    calibrate_heston, flat_bs_benchmark, heston_implied_vols, rmse_by_maturity, rmse_points, smile_curve,
)
from pricing.convergence import mc_convergence, tree_convergence, variance_reduction_summary
from pricing.greeks import Pricer, compare_greeks
from pricing.heston import HestonParams
from pricing.implied_vol import implied_vol
from pricing.monte_carlo import METHODS, mc_price, variance_reduction_factor

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="Stochastic-Volatility-Pricing API")


@app.exception_handler(ValueError)
def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """The pricing library raises ValueError for bad inputs: report it as a 400 with the message."""
    return JSONResponse(status_code=400, content={"detail": str(exc)})


def to_list(values: np.ndarray) -> list:
    """Numpy array to nested lists, with NaN and infinities replaced by None (they are not valid JSON)."""
    array = np.asarray(values, dtype=float)
    return np.where(np.isfinite(array), array.astype(object), None).tolist()


def finite(x: float) -> float | None:
    """A float for JSON: None when it is NaN or infinite."""
    return float(x) if np.isfinite(x) else None


@app.post("/api/price")
def price(req: PriceRequest) -> dict:
    """Black-Scholes, binomial tree and the three Monte Carlo estimators for one option."""
    args = (req.S, req.K, req.T, req.r, req.sigma, req.q, req.kind)
    results = {m: mc_price(*args, req.n_paths, req.seed, m) for m in METHODS}
    monte_carlo = [
        {
            "method": m,
            "price": res.price,
            "std_error": res.std_error,
            "ci_low": res.ci_low,
            "ci_high": res.ci_high,
            "vr_factor": finite(variance_reduction_factor(results["plain"], res)),
        }
        for m, res in results.items()
    ]
    return {
        "bs": float(bs_price(*args)),
        "tree": crr_price(*args, n=req.n_steps),
        "tree_american": crr_price(*args, n=req.n_steps, american=True),
        "mc": monte_carlo,
    }


def build_pricer(req: GreeksRequest) -> Pricer:
    """The function that finite differences are applied to."""
    if req.pricer == "bs":
        return bs_price
    if req.pricer == "tree":
        return lambda S, K, T, r, sigma, q, kind: crr_price(S, K, T, r, sigma, q, kind, n=req.n_steps)
    # the same seed for every bumped price: common random numbers
    return lambda S, K, T, r, sigma, q, kind: mc_price(S, K, T, r, sigma, q, kind, req.n_paths, req.seed).price


@app.post("/api/greeks")
def greeks(req: GreeksRequest) -> dict:
    """Analytic Greeks next to finite-difference Greeks of the chosen pricer."""
    rows = compare_greeks(build_pricer(req), req.S, req.K, req.T, req.r, req.sigma, req.q, req.kind, bump_S=req.bump_S)
    return {"pricer": req.pricer, "rows": [{**row, "rel_error": finite(row["rel_error"])} for row in rows]}


@app.post("/api/greeks-surface")
def greeks_surface(req: GreeksSurfaceRequest) -> dict:
    """Price and Greeks on a grid of spot prices (columns) and maturities (rows)."""
    if req.S_max <= req.S_min:
        raise ValueError("S_max must be greater than S_min")
    if min(req.T_values) <= 0:
        raise ValueError("maturities must be positive")
    S = np.linspace(req.S_min, req.S_max, req.n_S)
    T = np.array(req.T_values)
    S_grid, T_grid = np.meshgrid(S, T)
    args = (S_grid, req.K, T_grid, req.r, req.sigma, req.q, req.kind)
    surfaces = {"price": bs_price(*args), **bs_greeks(*args)}
    return {"S": S.tolist(), "T": T.tolist(), **{name: to_list(z) for name, z in surfaces.items()}}


@app.get("/api/convergence")
def convergence(inputs: Annotated[OptionInputs, Query()], seed: int = 0) -> dict:
    """Tree and Monte Carlo convergence towards the Black-Scholes price."""
    args = (inputs.S, inputs.K, inputs.T, inputs.r, inputs.sigma, inputs.q, inputs.kind)
    tree = tree_convergence(*args)
    mc = mc_convergence(*args, seed=seed)
    return {
        "bs_price": tree["bs_price"],
        "tree": {"n": tree["n"].tolist(), "price": to_list(tree["price"]), "error": to_list(tree["error"])},
        "mc": {"N": mc["N"].tolist(), **{m: {k: to_list(v) for k, v in mc[m].items()} for m in METHODS}},
        "summary": [{k: v if isinstance(v, (str, int)) else finite(v) for k, v in row.items()}
                    for row in variance_reduction_summary(mc)],
    }


@app.post("/api/implied-vol")
def implied_volatility(req: ImpliedVolRequest) -> dict:
    """Implied volatility of one option price, or the reason why none exists."""
    vol, reason = implied_vol(req.price, req.S, req.K, req.T, req.r, req.q, req.kind)
    return {"implied_vol": None if np.isnan(vol) else vol, "reason": reason}


@app.get("/api/market-data")
def market_data(r: Annotated[float, Query(ge=-0.5, le=1)] = 0.05, source: Literal["live", "sample"] = "live") -> dict:
    """Cleaned out-of-the-money quotes with implied vols.

    A failed live download falls back to the offline sample; meta["source"] and meta["note"] say so.
    """
    quotes, meta = load_market_data(r, source)
    expiries = [
        {"expiry": expiry, "T": float(group["T"].iloc[0]), "forward": float(group.forward.iloc[0]), "n_quotes": len(group)}
        for expiry, group in quotes.groupby("expiry")
    ]
    columns = ["expiry", "T", "kind", "strike", "forward", "log_moneyness", "mid", "iv"]
    return {"meta": meta, "expiries": expiries, "quotes": quotes[columns].to_dict("records")}


def quote_arrays(quotes: list[MarketQuote]) -> tuple[np.ndarray, ...]:
    """Forward, strike, maturity and implied vol as arrays with one entry per quote."""
    return tuple(np.array([getattr(quote, name) for quote in quotes]) for name in ("forward", "strike", "T", "iv"))


@app.post("/api/heston/calibrate")
def heston_calibrate(req: CalibrationRequest) -> dict:
    """Calibrate Heston to the quotes and compare it with one flat Black-Scholes vol per maturity."""
    F, K, T, iv = quote_arrays(req.quotes)
    fit = calibrate_heston(F, K, T, iv, req.r)
    flat = flat_bs_benchmark(T, iv)
    heston_rmse, flat_rmse = rmse_by_maturity(T, fit.model_iv - iv), rmse_by_maturity(T, flat - iv)
    return {
        "params": asdict(fit.params),
        "feller": fit.params.feller,
        "rmse": fit.rmse,
        "rmse_flat_bs": rmse_points(flat - iv),
        "runtime": fit.runtime,
        "n_evaluations": fit.n_evaluations,
        "converged": fit.converged,
        "model_iv": fit.model_iv.tolist(),
        "by_maturity": [
            {"T": t, "flat_sigma": float(flat[T == t][0]), "rmse_heston": heston_rmse[t], "rmse_flat_bs": flat_rmse[t]}
            for t in heston_rmse
        ],
    }


def smile_grid(k: np.ndarray, T: np.ndarray, n_k: int, n_T: int) -> tuple[np.ndarray, np.ndarray]:
    """A grid that follows the quoted region.

    At each maturity, log-moneyness runs from the lowest to the highest quoted value (interpolated
    between quoted maturities), because short maturities trade over a much narrower strike range.
    """
    maturities = np.unique(T)
    lowest = np.array([k[T == t].min() for t in maturities])
    highest = np.array([k[T == t].max() for t in maturities])
    T_axis = np.linspace(maturities[0], maturities[-1], n_T)
    low = np.interp(T_axis, maturities, lowest)[:, None]
    high = np.interp(T_axis, maturities, highest)[:, None]
    k_grid = low + np.linspace(0, 1, n_k) * (high - low)
    return k_grid, np.repeat(T_axis[:, None], n_k, axis=1)


@app.post("/api/heston/surface")
def heston_surface(req: HestonSurfaceRequest) -> dict:
    """Market and Heston implied vols on a (log-moneyness, maturity) grid, plus one Heston smile per maturity.

    The market surface is a linear interpolation of the quotes (scipy griddata).
    Without parameters (before calibration) only the market surface is filled in.
    """
    F, K, T, iv = quote_arrays(req.quotes)
    k = np.log(K / F)
    k_grid, T_grid = smile_grid(k, T, req.n_k, req.n_T)

    market = griddata((k, T), iv, (k_grid, T_grid), method="linear", rescale=True)
    # grid points on the edge of the quoted region can fall just outside the triangulation: use the nearest quote
    holes = np.isnan(market)
    market[holes] = griddata((k, T), iv, (k_grid[holes], T_grid[holes]), method="nearest", rescale=True)

    heston = np.full(k_grid.shape, np.nan)
    smiles = []
    if req.params is not None:
        params = HestonParams(**req.params.model_dump())
        # in terms of k the Heston smile does not depend on the forward or the rate, so F = 1 and r = 0 are used
        heston = heston_implied_vols(np.ones(k_grid.size), np.exp(k_grid.ravel()), T_grid.ravel(), 0.0, params)
        heston = heston.reshape(k_grid.shape)
        for maturity in np.unique(T):
            k_line, vols = smile_curve(maturity, k[T == maturity].min(), k[T == maturity].max(), params)
            smiles.append({"T": float(maturity), "k": k_line.tolist(), "heston": to_list(vols)})
    return {
        "k": k_grid.tolist(),
        "T": T_grid[:, 0].tolist(),
        "market": to_list(market),
        "heston": to_list(heston),
        "error": to_list(heston - market),
        "smiles": smiles,
    }


# static sites are mounted last so they never shadow the API routes
app.mount("/docs-site", StaticFiles(directory=ROOT / "docs", html=True), name="docs-site")
app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")
