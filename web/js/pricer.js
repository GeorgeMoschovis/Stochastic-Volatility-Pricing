// Tab 1: prices from the three methods, Monte Carlo intervals, the Greeks table and implied volatility.

import { postJSON } from "./api.js";
import { $, COLORS, ESTIMATORS, axis, fmt, fmtPct, fmtSci, fmtTimes, info, layout2d, plot, renderMath, withLoading } from "./ui.js";

let lastInputs = null;

const GREEKS = {
  delta: { symbol: "Delta \\(\\Delta\\)", digits: 4 },
  gamma: { symbol: "Gamma \\(\\Gamma\\)", digits: 4 },
  vega: { symbol: "Vega \\(\\nu\\)", digits: 4 },
  theta: { symbol: "Theta \\(\\Theta\\)", digits: 4 },
  rho: { symbol: "Rho \\(\\rho\\)", digits: 4 },
};

const money = (x, digits = 2) => `$${Math.abs(x).toFixed(digits)}`;
const gainOrLose = (x) => (x >= 0 ? "gains" : "loses");

// One plain-English sentence per Greek, built from the analytic value. Shown on hover.
const MEANING = {
  delta: (v) => `Δ = ${v.toFixed(2)}: the option ${gainOrLose(v)} ≈ ${money(v)} for a $1 rise in the stock.`,
  gamma: (v) => `Γ = ${v.toFixed(3)}: delta rises by ≈ ${v.toFixed(3)} for a $1 rise in the stock.`,
  vega: (v) => `ν = ${v.toFixed(2)}: the option gains ≈ ${money(v / 100, 3)} if volatility rises by one point (20% → 21%).`,
  theta: (v) => `Θ = ${v.toFixed(2)} per year: the option ${gainOrLose(v)} ≈ ${money(v / 365, 4)} per calendar day as time passes.`,
  rho: (v) => `ρ = ${v.toFixed(2)}: the option ${gainOrLose(v)} ≈ ${money(v / 100, 3)} if the interest rate rises by one point.`,
};

export function init() {
  const reloadGreeks = () => lastInputs && loadGreeks(lastInputs);
  $("fd-pricer").addEventListener("change", reloadGreeks);
  $("fd-bump").addEventListener("change", reloadGreeks);
  $("iv-form").addEventListener("submit", (event) => {
    event.preventDefault();
    solveImpliedVol();
  });
}

export async function refresh(inputs) {
  lastInputs = inputs;
  $("iv-result").textContent = "";
  await Promise.all([loadPrices(inputs), loadGreeks(inputs)]);
}

async function loadPrices(inputs) {
  const cards = ["card-bs", "card-tree", "card-mc", "card-mc-detail"];
  const data = await withLoading(cards, "Could not price the option", () => postJSON("/api/price", inputs));
  if (!data) return;

  $("bs-price").textContent = fmt(data.bs);
  $("tree-steps").textContent = `${inputs.n_steps} steps`;
  $("tree-price").textContent = fmt(data.tree);
  $("tree-note").textContent = `Tree minus Black–Scholes: ${fmtSci(data.tree - data.bs)}`;
  $("tree-tip").textContent =
    `With American exercise the tree gives ${fmt(data.tree_american)}, ` +
    `an early-exercise premium of ${fmtSci(data.tree_american - data.tree)}.`;

  const best = data.mc.find((row) => row.method === "control_variate");
  const inside = best.ci_low <= data.bs && data.bs <= best.ci_high;
  $("mc-paths").textContent = `${inputs.n_paths.toLocaleString("en-US")} paths`;
  $("mc-price").textContent = fmt(best.price);
  $("mc-note").textContent = `± ${fmt(1.96 * best.std_error)} at 95% confidence`;
  $("mc-tip").textContent =
    `Control variate estimator. Its 95% interval [${fmt(best.ci_low)}, ${fmt(best.ci_high)}] ` +
    `${inside ? "contains" : "does not contain"} the Black–Scholes price.`;

  $("mc-rows").innerHTML = data.mc.map((row) => `
    <tr>
      <td><span class="dot" style="background:${ESTIMATORS[row.method].color}"></span>${ESTIMATORS[row.method].label}</td>
      <td>${fmt(row.price)}</td>
      <td>${fmt(1.96 * row.std_error)}</td>
      <td>${fmtTimes(row.vr_factor)}</td>
    </tr>`).join("");

  drawIntervals(data);
}

// Each estimate with its 95% interval, against the exact price.
function drawIntervals(data) {
  const traces = data.mc.map((row) => ({
    x: [row.price],
    y: [ESTIMATORS[row.method].label],
    error_x: { type: "data", array: [1.96 * row.std_error], color: ESTIMATORS[row.method].color, thickness: 2, width: 7 },
    mode: "markers",
    marker: { color: ESTIMATORS[row.method].color, size: 9 },
    showlegend: false,
    hovertemplate: `${ESTIMATORS[row.method].label}<br>price %{x:.4f}<br>95% interval [${fmt(row.ci_low)}, ${fmt(row.ci_high)}]<extra></extra>`,
  }));
  plot("mc-chart", traces, layout2d({
    margin: { l: 110, r: 16, t: 28, b: 40 },
    xaxis: axis("option price"),
    yaxis: axis("", { autorange: "reversed" }),
    shapes: [{ type: "line", x0: data.bs, x1: data.bs, yref: "paper", y0: 0, y1: 1, line: { color: COLORS.text, width: 1, dash: "dash" } }],
    annotations: [{ x: data.bs, yref: "paper", y: 1.12, text: "Black–Scholes", showarrow: false, font: { color: COLORS.text2, size: 11 } }],
  }));
}

function differencePill(row) {
  return `<span class="pill">${fmtSci(row.finite_diff - row.analytic)} (${fmtPct(row.rel_error, 3)})</span>`;
}

async function loadGreeks(inputs) {
  const body = { ...inputs, pricer: $("fd-pricer").value, bump_S: Number($("fd-bump").value) };
  const data = await withLoading(["card-greeks"], "Could not compute the Greeks", () => postJSON("/api/greeks", body));
  if (!data) return;
  $("greek-rows").innerHTML = data.rows.map((row) => `
    <tr>
      <td>${GREEKS[row.greek].symbol} ${info(MEANING[row.greek](row.analytic))}</td>
      <td>${fmt(row.analytic, GREEKS[row.greek].digits)}</td>
      <td>${fmt(row.finite_diff, GREEKS[row.greek].digits)}</td>
      <td>${differencePill(row)}</td>
    </tr>`).join("");
  renderMath($("greek-rows"));
}

async function solveImpliedVol() {
  if (!lastInputs) return;
  const { S, K, T, r, q, kind } = lastInputs;
  const body = { price: Number($("iv-price").value), S, K, T, r, q, kind };
  const data = await withLoading(["card-iv"], "Could not solve for implied volatility", () => postJSON("/api/implied-vol", body));
  if (!data) return;
  $("iv-result").innerHTML = data.implied_vol === null
    ? `<span class="pill">No solution</span> ${data.reason}.`
    : `Implied volatility <b>${fmtPct(data.implied_vol)}</b> reproduces a ${kind} price of ${fmt(body.price, 2)}.`;
}
