"""Request bodies for the API. Pydantic checks types and ranges before any pricing code runs."""

from typing import Literal

from pydantic import BaseModel, Field

Kind = Literal["call", "put"]


class OptionInputs(BaseModel):
    """Contract and market inputs. The defaults are Hull's textbook example."""

    S: float = Field(42.0, gt=0, le=1e7)
    K: float = Field(40.0, gt=0, le=1e7)
    T: float = Field(0.5, gt=0, le=30)
    r: float = Field(0.10, ge=-0.5, le=1)
    q: float = Field(0.0, ge=-0.5, le=1)
    sigma: float = Field(0.20, gt=0, le=5)
    kind: Kind = "call"


class PriceRequest(OptionInputs):
    n_steps: int = Field(500, ge=1, le=5000)
    n_paths: int = Field(100_000, ge=100, le=2_000_000)
    seed: int = Field(42, ge=0)


class GreeksRequest(PriceRequest):
    # which pricer the finite differences are applied to
    pricer: Literal["bs", "tree", "mc"] = "bs"
    bump_S: float = Field(0.01, gt=0, le=0.2)


class GreeksSurfaceRequest(BaseModel):
    K: float = Field(40.0, gt=0)
    r: float = Field(0.10, ge=-0.5, le=1)
    q: float = Field(0.0, ge=-0.5, le=1)
    sigma: float = Field(0.20, gt=0, le=5)
    kind: Kind = "call"
    S_min: float = Field(gt=0)
    S_max: float = Field(gt=0)
    n_S: int = Field(60, ge=2, le=200)
    T_values: list[float] = Field(min_length=1, max_length=100)


class ImpliedVolRequest(BaseModel):
    price: float = Field(gt=0)
    S: float = Field(gt=0)
    K: float = Field(gt=0)
    T: float = Field(gt=0, le=30)
    r: float = Field(0.0, ge=-0.5, le=1)
    q: float = Field(0.0, ge=-0.5, le=1)
    kind: Kind = "call"


class HestonParamsIn(BaseModel):
    v0: float = Field(gt=0, le=4)
    kappa: float = Field(gt=0, le=50)
    theta: float = Field(gt=0, le=4)
    sigma_v: float = Field(gt=0, le=10)
    rho: float = Field(gt=-1, lt=1)


class MarketQuote(BaseModel):
    """One cleaned market option: maturity, strike, forward for that maturity and implied vol."""

    T: float = Field(gt=0, le=30)
    strike: float = Field(gt=0)
    forward: float = Field(gt=0)
    iv: float = Field(gt=0, le=5)


class CalibrationRequest(BaseModel):
    r: float = Field(0.05, ge=-0.5, le=1)
    quotes: list[MarketQuote] = Field(min_length=5, max_length=2000)


class HestonSurfaceRequest(BaseModel):
    # without parameters only the market surface is returned
    params: HestonParamsIn | None = None
    quotes: list[MarketQuote] = Field(min_length=5, max_length=2000)
    n_k: int = Field(41, ge=5, le=101)
    n_T: int = Field(25, ge=5, le=61)
