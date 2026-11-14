"""Download, clean and cache option chains for the Heston calibration.

    python -m data.fetch_options                 download a snapshot into data/cache/
    python -m data.fetch_options --save-sample   also overwrite data/sample_chain.csv

The app never depends on the network: if a download fails it uses the committed sample.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.special import ndtr

from pricing.implied_vol import implied_vol_vec

DATA_DIR = Path(__file__).resolve().parent
SAMPLE_PATH = DATA_DIR / "sample_chain.csv"
CACHE_DIR = DATA_DIR / "cache"

TICKER = "^SPX"
# one expiry is chosen near each of these maturities (calendar days)
TARGET_DAYS = (14, 30, 60, 90, 150, 210, 280, 365)


def is_monthly(date: pd.Timestamp) -> bool:
    """Standard monthly expiry: the third Friday of the month."""
    return date.weekday() == 4 and 15 <= date.day <= 21


def pick_expiries(expiries: list[str], today: pd.Timestamp) -> list[str]:
    """One listed expiry near each target maturity.

    From one month out only monthly expiries are used, because they are the most liquid.
    """
    dates = [pd.Timestamp(e) for e in expiries]
    chosen = []
    for target in TARGET_DAYS:
        pool = [d for d in dates if (d - today).days >= 10 and (target < 30 or is_monthly(d))]
        if not pool:
            continue
        best = min(pool, key=lambda d: abs((d - today).days - target))
        if best not in chosen:
            chosen.append(best)
    return [d.strftime("%Y-%m-%d") for d in chosen]


def keep_main_series(quotes: pd.DataFrame) -> pd.DataFrame:
    """Keep one option series per expiry.

    On monthly dates Yahoo mixes two SPX series (AM-settled "SPX" and PM-settled "SPXW").
    They expire a few hours apart, so only the larger one is kept.
    """
    root = quotes.contractSymbol.str.extract(r"^([A-Z]+)")[0]
    main_root = root.groupby(quotes.expiry).agg(lambda s: s.mode()[0])
    return quotes[root == quotes.expiry.map(main_root)]


def download_chain(ticker: str = TICKER) -> pd.DataFrame:
    """Bid/ask quotes for about eight expiries from Yahoo Finance (15 minutes delayed).

    Returns one row per option: ticker, snapshot_time, spot, expiry, kind, strike, bid, ask, open_interest.
    Raises RuntimeError when too few usable quotes come back, e.g. outside market hours.
    """
    source = yf.Ticker(ticker)
    now = pd.Timestamp.now(tz="UTC")
    frames = []
    for expiry in pick_expiries(list(source.options), now.tz_localize(None)):
        chain = source.option_chain(expiry)
        for kind, table in (("call", chain.calls), ("put", chain.puts)):
            frame = table[["contractSymbol", "strike", "bid", "ask", "openInterest"]].copy()
            frame["expiry"], frame["kind"] = expiry, kind
            frames.append(frame)
        spot = float(chain.underlying["regularMarketPrice"])
    if not frames:
        raise RuntimeError(f"no option expiries listed for {ticker}")

    quotes = keep_main_series(pd.concat(frames, ignore_index=True))
    quotes = quotes.rename(columns={"openInterest": "open_interest"})
    quotes = quotes[(quotes.bid > 0) & (quotes.ask > quotes.bid) & (quotes.open_interest > 0)]
    # deep in-the-money options are never used: keep OTM strikes plus a band around the money for parity
    is_call = quotes.kind == "call"
    quotes = quotes[(is_call & (quotes.strike > 0.9 * spot)) | (~is_call & (quotes.strike < 1.1 * spot))]
    # outside trading hours Yahoo reports bid = ask = 0 for nearly every option
    if len(quotes) < 100:
        raise RuntimeError(f"Yahoo returned only {len(quotes)} two-sided quotes, the option market is probably closed")

    quotes = quotes[["expiry", "kind", "strike", "bid", "ask", "open_interest"]].copy()
    quotes.insert(0, "spot", spot)
    quotes.insert(0, "snapshot_time", now.isoformat(timespec="seconds"))
    quotes.insert(0, "ticker", ticker)
    return quotes.reset_index(drop=True)


def years_to_expiry(expiry: str, snapshot: pd.Timestamp) -> float:
    """Calendar time in years from the snapshot to 16:00 New York time on the expiry date."""
    close = pd.Timestamp(f"{expiry} 16:00", tz="America/New_York")
    return (close - snapshot).total_seconds() / (365 * 24 * 3600)


def estimate_forward(quotes: pd.DataFrame, r: float, T: float, n_strikes: int = 5) -> float:
    r"""Forward price from put-call parity: $c - p = e^{-rT}(F - K)$, so $F = K + e^{rT}(c - p)$.

    Uses the strikes where the call and put prices are closest (near the money, where quotes
    are tightest) and returns the median of their implied forwards. No dividend yield is needed.
    """
    mids = quotes.pivot_table(index="strike", columns="kind", values="mid")
    if not {"call", "put"} <= set(mids.columns) or mids.dropna().empty:
        raise ValueError("no strike has both a call and a put quote")
    mids = mids.dropna()
    gap = mids.call - mids.put
    nearest = gap.abs().nsmallest(n_strikes).index
    return float(np.median(nearest + np.exp(r * T) * gap[nearest]))


def clean_chain(raw: pd.DataFrame, r: float, max_spread: float = 0.25, min_delta: float = 0.02,
                per_expiry: int = 30) -> pd.DataFrame:
    """Turn raw quotes into out-of-the-money implied volatilities.

    Steps: mid prices; drop wide spreads and zero open interest; forward from put-call parity;
    keep puts below the forward and calls above it; implied vols; drop the far wings
    (|delta| below min_delta, where a one-tick price change moves the vol a lot);
    thin to at most `per_expiry` strikes per maturity.
    """
    snapshot = pd.Timestamp(raw.snapshot_time.iloc[0])
    quotes = raw.copy()
    quotes["mid"] = 0.5 * (quotes.bid + quotes.ask)
    liquid = (quotes.bid > 0) & (quotes.open_interest > 0) & ((quotes.ask - quotes.bid) / quotes.mid < max_spread)
    quotes = quotes[liquid]

    blocks = []
    for expiry, group in quotes.groupby("expiry"):
        T = years_to_expiry(expiry, snapshot)
        forward = estimate_forward(group, r, T)
        is_put = group.kind == "put"
        otm = group[(is_put & (group.strike < forward)) | (~is_put & (group.strike >= forward))].copy()
        otm["T"], otm["forward"] = T, forward
        otm["log_moneyness"] = np.log(otm.strike / forward)
        # with q = r the Black-Scholes formula becomes Black's formula on the forward
        otm["iv"] = implied_vol_vec(otm.mid.to_numpy(), forward, otm.strike.to_numpy(), T, r, q=r, kind=otm.kind.to_numpy())
        otm = otm.dropna(subset="iv")
        otm = otm[forward_delta(otm) >= min_delta].sort_values("strike")
        keep = np.unique(np.linspace(0, len(otm) - 1, per_expiry).round().astype(int)) if len(otm) else []
        blocks.append(otm.iloc[keep])

    columns = ["expiry", "T", "kind", "strike", "forward", "log_moneyness", "mid", "bid", "ask", "open_interest", "iv"]
    clean = pd.concat(blocks, ignore_index=True)[columns]
    if clean.expiry.nunique() < 3 or len(clean) < 20:
        raise ValueError("too few liquid quotes left after cleaning")
    return clean


def forward_delta(otm: pd.DataFrame) -> pd.Series:
    r"""Absolute undiscounted Black delta, $N(-|d_1|)$ with $d_1 = \frac{-k}{\sigma\sqrt{T}} + \frac{\sigma\sqrt{T}}{2}$."""
    total_vol = otm.iv * np.sqrt(otm["T"])
    return ndtr(-np.abs(-otm.log_moneyness / total_vol + 0.5 * total_vol))


def save_snapshot(raw: pd.DataFrame, clean: pd.DataFrame) -> Path:
    """Write the raw and cleaned datasets to data/cache/ with the snapshot time in the file name."""
    CACHE_DIR.mkdir(exist_ok=True)
    stamp = pd.Timestamp(raw.snapshot_time.iloc[0]).strftime("%Y%m%d_%H%M")
    name = raw.ticker.iloc[0].strip("^")
    raw.to_csv(CACHE_DIR / f"raw_{name}_{stamp}.csv", index=False)
    clean.to_csv(CACHE_DIR / f"clean_{name}_{stamp}.csv", index=False)
    return CACHE_DIR / f"clean_{name}_{stamp}.csv"


def load_market_data(r: float, source: str = "live") -> tuple[pd.DataFrame, dict]:
    """Cleaned quotes and a description of where they came from.

    source="live" downloads from Yahoo Finance; on any failure it falls back to the
    committed sample and says why in meta["note"].
    """
    note = ""
    raw = clean = None
    if source == "live":
        try:
            raw = download_chain()
            clean = clean_chain(raw, r)
            save_snapshot(raw, clean)
        except Exception as error:  # network down, market closed, Yahoo format change: all end in the fallback
            note = f"Live download failed ({error}). Showing the offline sample instead."
            clean = None
    if clean is None:
        source = "sample"
        raw = pd.read_csv(SAMPLE_PATH)
        clean = clean_chain(raw, r)
    meta = {
        "source": source,
        "ticker": str(raw.ticker.iloc[0]),
        "snapshot_time": str(raw.snapshot_time.iloc[0]),
        "spot": float(raw.spot.iloc[0]),
        "r": r,
        "note": note,
    }
    return clean, meta


def main() -> None:
    """Download a snapshot, clean it, save both versions and print a summary per expiry."""
    raw = download_chain()
    clean = clean_chain(raw, r=0.05)
    path = save_snapshot(raw, clean)
    print(f"{len(raw)} raw quotes, {len(clean)} cleaned quotes, saved to {path.parent}")
    print(clean.groupby("expiry").agg(T=("T", "first"), forward=("forward", "first"), quotes=("iv", "size"),
                                      iv_min=("iv", "min"), iv_max=("iv", "max")).round(4))
    if "--save-sample" in sys.argv:
        raw.to_csv(SAMPLE_PATH, index=False)
        print(f"sample overwritten: {SAMPLE_PATH}")


if __name__ == "__main__":
    main()
