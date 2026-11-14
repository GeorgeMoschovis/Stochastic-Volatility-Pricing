// Tab 4: market implied-volatility surface, Heston calibration, smiles and fitted parameters.

import { getJSON, postJSON } from "./api.js";
import {
  $, CAMERAS, COLORS, DIVERGING, SEQUENTIAL, axis, colorbar, fmt, fmtPct, info, layout2d, layout3d, plot, renderMath,
  segmented, withLoading,
} from "./ui.js";

const CARDS = ["card-vol-surface", "card-smile", "card-params", "card-fit"];

// responses of /api/market-data, /api/heston/calibrate and /api/heston/surface
let market = null;
let fit = null;
let grid = null;
let view = null;
let zMode = null;

export function init() {
  view = segmented("surface-view", drawSurface);
  zMode = segmented("surface-z", drawSurface);
  $("overlay-points").addEventListener("change", drawSurface);
  $("smile-expiry").addEventListener("change", drawSmile);
  $("load-market").addEventListener("click", () => loadMarket($("market-source").value));
  $("calibrate").addEventListener("click", calibrate);
}

export async function refresh() {
  // first visit: show the offline sample straight away, no network needed
  if (!market) await loadMarket("sample");
}

function quotesBody() {
  return market.quotes.map(({ T, strike, forward, iv }) => ({ T, strike, forward, iv }));
}

async function loadMarket(source) {
  const r = Number($("market-rate").value);
  $("market-status").textContent = source === "live" ? "Downloading option chains…" : "Loading the offline sample…";
  const loaded = await withLoading(CARDS, "Could not load market data", async () => {
    const data = await getJSON("/api/market-data", { r, source });
    const quotes = data.quotes.map(({ T, strike, forward, iv }) => ({ T, strike, forward, iv }));
    return { data, surface: await postJSON("/api/heston/surface", { quotes }) };
  });
  if (!loaded) {
    $("market-status").textContent = "Loading failed.";
    return;
  }
  market = loaded.data;
  grid = loaded.surface;
  fit = null;

  const { meta } = market;
  const when = meta.snapshot_time.slice(0, 16).replace("T", " ");
  const badge = $("market-badge");
  badge.hidden = false;
  badge.textContent = meta.source === "live"
    ? `Live data · ${meta.ticker} · ${when} UTC`
    : `Offline sample data, dated ${when} UTC · ${meta.ticker}`;
  $("market-info").hidden = false;
  $("market-tip").textContent =
    `${market.quotes.length} quotes across ${market.expiries.length} expiries, spot ${meta.spot.toFixed(2)}, r = ${fmtPct(meta.r)}.`;
  // a note means the live download failed and the sample was used instead, so it stays visible
  $("market-status").textContent = meta.note || "";

  $("smile-expiry").innerHTML = market.expiries
    .map((e) => `<option value="${e.expiry}">${e.expiry} (T = ${e.T.toFixed(2)})</option>`).join("");
  $("calibrate").disabled = false;
  view.value = "market";
  view.setEnabled("heston", false);
  view.setEnabled("error", false);
  drawAll();
}

async function calibrate() {
  const button = $("calibrate");
  button.disabled = true;
  button.textContent = "Calibrating…";
  $("market-status").textContent =
    `Fitting 5 parameters to ${market.quotes.length} implied volatilities across ${market.expiries.length} maturities…`;
  const result = await withLoading(CARDS, "Calibration failed", async () => {
    const calibration = await postJSON("/api/heston/calibrate", { r: market.meta.r, quotes: quotesBody() });
    const surface = await postJSON("/api/heston/surface", { params: calibration.params, quotes: quotesBody() });
    return { calibration, surface };
  });
  button.disabled = false;
  button.textContent = "Calibrate Heston";
  if (!result) {
    $("market-status").textContent = "Calibration failed.";
    return;
  }
  fit = result.calibration;
  grid = result.surface;
  $("market-status").textContent =
    `RMSE ${fit.rmse.toFixed(2)} volatility points (flat Black–Scholes: ${fit.rmse_flat_bs.toFixed(2)}).` +
    `${fit.converged ? "" : " The optimiser stopped before converging."}`;
  view.setEnabled("heston", true);
  view.setEnabled("error", true);
  view.value = "heston";
  drawAll();
}

function drawAll() {
  drawSurface();
  drawSmile();
  fillParams();
  fillFitTable();
}

// the plotted quantity: implied vol in percent, or total variance w = sigma^2 T
function toZ(iv, T) {
  if (iv === null) return null;
  return zMode.value === "iv" ? 100 * iv : iv * iv * T;
}

function drawSurface() {
  if (!grid) return;
  const isError = view.value === "error";
  const isVol = zMode.value === "iv";
  const digits = isVol ? 2 : 4;
  const model = view.value === "market" ? grid.market : grid.heston;

  // grid.k has one row of log-moneyness values per maturity, so x and y are both 2D
  const y = grid.T.map((T, i) => grid.k[i].map(() => T));
  const z = grid.T.map((T, i) => grid.k[i].map((_, j) => {
    if (!isError) return toZ(model[i][j], T);
    return toZ(grid.heston[i][j], T) - toZ(grid.market[i][j], T);
  }));

  let label = isVol ? "implied vol (%)" : "total variance w";
  if (isError) label = isVol ? "Heston − market (vol points)" : "Heston − market (w)";

  const traces = [{
    type: "surface",
    x: grid.k,
    y,
    z,
    colorscale: isError ? DIVERGING : SEQUENTIAL,
    // centre the diverging scale on zero so the neutral colour means "no error"
    ...(isError ? { cmid: 0 } : {}),
    colorbar: colorbar(label),
    opacity: 0.95,
    hovertemplate: `ln(K/F) = %{x:.3f}<br>T = %{y:.2f} y<br>${label} = %{z:.${digits}f}<extra></extra>`,
  }];

  if ($("overlay-points").checked) {
    const quotes = market.quotes;
    // on the error view the points are the exact fitting errors at the quotes
    const height = (q, i) => (isError ? toZ(fit.model_iv[i], q.T) - toZ(q.iv, q.T) : toZ(q.iv, q.T));
    traces.push({
      type: "scatter3d",
      mode: "markers",
      x: quotes.map((q) => q.log_moneyness),
      y: quotes.map((q) => q.T),
      z: quotes.map(height),
      customdata: quotes.map((q) => [q.expiry, q.strike, 100 * q.iv]),
      marker: { color: COLORS.text, size: 2.6, opacity: 0.9 },
      name: "market quotes",
      showlegend: false,
      hovertemplate: `%{customdata[0]}, K = %{customdata[1]}<br>market vol %{customdata[2]:.2f}%<br>${label} = %{z:.${digits}f}<extra></extra>`,
    });
  }
  plot("vol-surface", traces, layout3d("log-moneyness ln(K/F)", "maturity T (years)", label, CAMERAS.volatility));
}

function drawSmile() {
  if (!market) return;
  const expiry = $("smile-expiry").value;
  const quotes = market.quotes.filter((q) => q.expiry === expiry);
  const k = quotes.map((q) => q.log_moneyness);
  const flat = (100 * quotes.reduce((sum, q) => sum + q.iv, 0)) / quotes.length;

  const traces = [{
    x: k, y: quotes.map((q) => 100 * q.iv), customdata: quotes.map((q) => q.strike),
    name: "market", mode: "markers", marker: { color: COLORS.text, size: 7 },
    hovertemplate: "K = %{customdata}<br>ln(K/F) = %{x:.3f}<br>market vol %{y:.2f}%<extra></extra>",
  }];
  const smile = grid.smiles.find((s) => Math.abs(s.T - quotes[0].T) < 1e-9);
  if (smile) {
    traces.push({
      x: smile.k, y: smile.heston.map((v) => 100 * v), name: "Heston fit", mode: "lines",
      line: { color: COLORS.series[0], width: 2.5 },
      hovertemplate: "ln(K/F) = %{x:.3f}<br>Heston vol %{y:.2f}%<extra></extra>",
    });
  }
  traces.push({
    x: [Math.min(...k), Math.max(...k)], y: [flat, flat], name: "flat Black–Scholes", mode: "lines",
    line: { color: COLORS.series[1], width: 1.8, dash: "dash" },
    hovertemplate: "flat Black–Scholes vol %{y:.2f}%<extra></extra>",
  });
  plot("smile-chart", traces, layout2d({ xaxis: axis("log-moneyness ln(K/F)"), yaxis: axis("implied vol (%)") }));
}

function rhoMeaning(rho) {
  if (rho < -0.1) return "Falls in the index come with rising volatility, which creates the downward skew.";
  if (rho > 0.1) return "Rises in the index come with rising volatility, which tilts the smile upwards.";
  return "Price and variance shocks are almost unrelated, so the smile is close to symmetric.";
}

function fillParams() {
  const body = $("params-body");
  if (!fit) {
    $("params-note").textContent = "";
    body.innerHTML = '<p class="hint">Not calibrated yet.</p>';
    return;
  }
  const p = fit.params;
  const halfLife = Math.log(2) / p.kappa;
  const halfLifeText = halfLife < 0.25 ? `${Math.round(365 * halfLife)} days` : `${halfLife.toFixed(2)} years`;
  // label, value, explanation shown on hover
  const tiles = [
    ["RMSE Heston", fit.rmse.toFixed(2), "Typical fitting error of the Heston model across all quotes, in volatility points."],
    ["RMSE flat Black–Scholes", fit.rmse_flat_bs.toFixed(2), "The same error when each maturity gets one constant volatility. This is the benchmark Heston has to beat."],
    ["\\(v_0\\)", fmt(p.v0, 4), `Variance today: \\(\\sqrt{v_0}\\) = ${fmtPct(Math.sqrt(p.v0), 1)} is the volatility the model starts from.`],
    ["\\(\\kappa\\)", fmt(p.kappa, 2), `Speed of mean reversion: a gap between today's and the long-run variance halves every ${halfLifeText}.`],
    ["\\(\\theta\\)", fmt(p.theta, 4), `Long-run variance: \\(\\sqrt{\\theta}\\) = ${fmtPct(Math.sqrt(p.theta), 1)} is the volatility the model drifts towards.`],
    ["\\(\\sigma_v\\)", fmt(p.sigma_v, 2), "Volatility of variance: how randomly variance itself moves. Larger values fatten the tails and bend the smile more."],
    ["\\(\\rho\\)", fmt(p.rho, 2), rhoMeaning(p.rho)],
  ];
  const fellerText =
    `\\(2\\kappa\\theta = ${(2 * p.kappa * p.theta).toFixed(2)}\\) against \\(\\sigma_v^2 = ${(p.sigma_v ** 2).toFixed(2)}\\). ` +
    (fit.feller ? "The variance stays strictly positive." : "The variance can touch zero. This is usual for index calibrations and the pricing formula stays valid.");

  $("params-note").textContent =
    `v₀ ${fmt(p.v0, 4)} · κ ${fmt(p.kappa, 2)} · θ ${fmt(p.theta, 4)} · σᵥ ${fmt(p.sigma_v, 2)} · ρ ${fmt(p.rho, 2)}`;
  body.innerHTML = `
    <div class="metrics">
      ${tiles.map(([label, value, text]) => `<div class="metric"><b>${value}</b><span>${label}</span> ${info(text)}</div>`).join("")}
    </div>
    <p class="feller">Feller condition \\(2\\kappa\\theta > \\sigma_v^2\\)
      <span class="pill">${fit.feller ? "holds" : "violated"}</span> ${info(fellerText)}</p>
    <p class="hint">Calibrated in ${fit.runtime.toFixed(1)} s with ${fit.n_evaluations} model evaluations.</p>`;
  renderMath(body);
}

function fillFitTable() {
  $("fit-rows").innerHTML = market.expiries.map((e, i) => {
    const row = fit ? fit.by_maturity[i] : null;
    return `
      <tr>
        <td>${e.expiry}</td>
        <td>${e.T.toFixed(3)}</td>
        <td>${e.n_quotes}</td>
        <td>${e.forward.toFixed(1)}</td>
        <td>${row ? fmtPct(row.flat_sigma, 1) : "–"}</td>
        <td>${row ? row.rmse_flat_bs.toFixed(2) : "–"}</td>
        <td>${row ? row.rmse_heston.toFixed(2) : "–"}</td>
      </tr>`;
  }).join("");
}
