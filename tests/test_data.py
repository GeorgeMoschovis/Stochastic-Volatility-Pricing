import numpy as np
import pandas as pd
import pytest

from data.fetch_options import SAMPLE_PATH, clean_chain, estimate_forward, load_market_data, pick_expiries
from pricing.black_scholes import bs_price

SNAPSHOT = "2026-11-13T15:00:00+00:00"


def synthetic_chain(forward: float = 5000.0, sigma: float = 0.2, r: float = 0.04) -> pd.DataFrame:
    """Raw quotes for three expiries priced with Black's formula at a flat vol, with a 2% bid-ask spread."""
    rows = []
    for expiry, T in (("2027-02-19", 0.2694), ("2027-05-21", 0.5187), ("2027-11-19", 1.0174)):
        for strike in np.arange(4000.0, 6001.0, 100.0):
            for kind in ("call", "put"):
                mid = float(bs_price(forward, strike, T, r, sigma, q=r, kind=kind))
                rows.append(dict(ticker="TEST", snapshot_time=SNAPSHOT, spot=forward, expiry=expiry, kind=kind,
                                 strike=strike, bid=0.99 * mid, ask=1.01 * mid, open_interest=10))
    return pd.DataFrame(rows)


def test_pick_expiries_prefers_monthly_dates():
    listed = ["2026-11-20", "2026-11-27", "2026-12-04", "2026-12-18", "2027-01-15", "2027-03-19", "2027-06-18", "2027-11-19"]
    chosen = pick_expiries(listed, pd.Timestamp("2026-11-13"))
    assert chosen[0] == "2026-11-27"
    assert chosen == sorted(set(chosen))
    assert "2026-12-04" not in chosen


def test_forward_from_put_call_parity():
    raw = synthetic_chain(forward=5000.0)
    raw["mid"] = 0.5 * (raw.bid + raw.ask)
    quotes = raw[raw.expiry == "2027-11-19"]
    assert estimate_forward(quotes, r=0.04, T=1.0174) == pytest.approx(5000.0, rel=1e-4)


def test_clean_chain_keeps_otm_options_and_recovers_the_vol():
    clean = clean_chain(synthetic_chain(sigma=0.2), r=0.04, min_delta=0.0)
    puts, calls = clean[clean.kind == "put"], clean[clean.kind == "call"]
    assert (puts.strike < puts.forward).all()
    assert (calls.strike >= calls.forward).all()
    assert clean.iv.to_numpy() == pytest.approx(0.2, abs=2e-3)


def test_wide_spreads_are_dropped():
    raw = synthetic_chain()
    wide = raw.strike == 4500.0
    raw.loc[wide, "ask"] = 2.0 * raw.loc[wide, "bid"]
    clean = clean_chain(raw, r=0.04, min_delta=0.0)
    assert 4500.0 not in clean.strike.to_numpy()


def test_committed_sample_is_usable():
    assert SAMPLE_PATH.exists()
    quotes, meta = load_market_data(r=0.05, source="sample")
    assert meta["source"] == "sample"
    assert quotes.expiry.nunique() >= 6
    assert quotes.iv.between(0.03, 1.5).all()
    assert quotes["T"].between(0.02, 1.2).all()


def test_forward_needs_both_calls_and_puts():
    raw = synthetic_chain()
    raw["mid"] = 0.5 * (raw.bid + raw.ask)
    with pytest.raises(ValueError):
        estimate_forward(raw[raw.kind == "call"], r=0.04, T=1.0)


def test_failed_download_falls_back_to_the_sample(monkeypatch):
    def no_network():
        raise RuntimeError("network down")

    monkeypatch.setattr("data.fetch_options.download_chain", no_network)
    quotes, meta = load_market_data(r=0.05, source="live")
    assert meta["source"] == "sample"
    assert "network down" in meta["note"]
    assert len(quotes) > 50
