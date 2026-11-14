import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)
HULL = dict(S=42, K=40, T=0.5, r=0.10, q=0.0, sigma=0.20, kind="call")


def test_price_endpoint():
    data = client.post("/api/price", json={**HULL, "n_steps": 200, "n_paths": 20_000}).json()
    assert data["bs"] == pytest.approx(4.76, abs=0.01)
    assert data["tree"] == pytest.approx(data["bs"], abs=0.01)
    assert [row["method"] for row in data["mc"]] == ["plain", "antithetic", "control_variate"]


def test_greeks_endpoint():
    data = client.post("/api/greeks", json={**HULL, "pricer": "bs"}).json()
    delta = next(row for row in data["rows"] if row["greek"] == "delta")
    assert delta["analytic"] == pytest.approx(0.779, abs=1e-3)
    assert delta["abs_error"] < 1e-3


def test_greeks_surface_shape():
    body = dict(K=40, r=0.1, q=0, sigma=0.2, kind="call", S_min=20, S_max=60, n_S=5, T_values=[0.25, 0.5, 1.0])
    data = client.post("/api/greeks-surface", json=body).json()
    assert len(data["S"]) == 5
    assert len(data["delta"]) == 3 and len(data["delta"][0]) == 5


def test_implied_vol_endpoint():
    ok = client.post("/api/implied-vol", json=dict(price=4.7594, S=42, K=40, T=0.5, r=0.1)).json()
    assert ok["implied_vol"] == pytest.approx(0.20, abs=1e-4)
    bad = client.post("/api/implied-vol", json=dict(price=1.0, S=42, K=40, T=0.5, r=0.1)).json()
    assert bad["implied_vol"] is None and "no-arbitrage" in bad["reason"]


def test_invalid_input_is_rejected():
    response = client.post("/api/price", json={**HULL, "sigma": -1})
    assert response.status_code == 422


def test_static_pages_are_served():
    assert client.get("/").status_code == 200
    assert client.get("/docs-site/").status_code == 200


def test_market_data_calibration_and_surface():
    market = client.get("/api/market-data", params=dict(source="sample")).json()
    assert market["meta"]["source"] == "sample"
    assert len(market["expiries"]) >= 6
    quotes = [{k: q[k] for k in ("T", "strike", "forward", "iv")} for q in market["quotes"]]

    fit = client.post("/api/heston/calibrate", json=dict(r=0.05, quotes=quotes)).json()
    assert fit["rmse"] < fit["rmse_flat_bs"] / 3
    assert len(fit["by_maturity"]) == len(market["expiries"])

    surface = client.post("/api/heston/surface", json=dict(params=fit["params"], quotes=quotes, n_k=21, n_T=11)).json()
    assert len(surface["market"]) == 11 and len(surface["market"][0]) == 21
    assert len(surface["smiles"]) == len(market["expiries"])
    # both surfaces are filled everywhere on the grid, which follows the quoted region
    assert all(v is not None for row in surface["market"] + surface["heston"] for v in row)
    assert len(surface["k"]) == 11 and len(surface["k"][0]) == 21

    market_only = client.post("/api/heston/surface", json=dict(quotes=quotes)).json()
    assert market_only["smiles"] == [] and market_only["heston"][0][0] is None
