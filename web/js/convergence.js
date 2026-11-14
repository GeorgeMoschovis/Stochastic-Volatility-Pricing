// Tab 3: how the tree and the Monte Carlo estimators converge to the Black-Scholes price.

import { getJSON } from "./api.js";
import { $, COLORS, ESTIMATORS, LOG_AXIS, axis, fmtSci, fmtTimes, layout2d, plot, segmented, withLoading } from "./ui.js";

const REFERENCE = { color: COLORS.muted, width: 1.2, dash: "dash" };

let study = null;
let treeView = null;

export function init() {
  treeView = segmented("tree-view", drawTree);
}

export async function refresh(inputs) {
  const { S, K, T, r, q, sigma, kind, seed } = inputs;
  const cards = ["card-tree-conv", "card-mc-conv", "card-vr"];
  const data = await withLoading(cards, "Could not run the convergence study", () =>
    getJSON("/api/convergence", { S, K, T, r, q, sigma, kind, seed }));
  if (!data) return;
  study = data;
  drawTree();
  drawMonteCarlo(data.mc);
  fillSummary(data.summary);
}

function drawTree() {
  if (!study) return;
  if (treeView.value === "price") drawTreePrice(study);
  else drawTreeError(study.tree);
}

// The first 100 step counts on a linear scale show the sawtooth around the exact price.
function drawTreePrice(data) {
  const keep = data.tree.n.map((n, i) => i).filter((i) => data.tree.n[i] <= 100);
  const n = keep.map((i) => data.tree.n[i]);
  const traces = [
    {
      x: n, y: keep.map((i) => data.tree.price[i]), name: "CRR tree", mode: "lines+markers",
      line: { color: COLORS.series[0], width: 1.5 }, marker: { size: 5 },
      hovertemplate: "n = %{x}<br>price %{y:.4f}<extra></extra>",
    },
    {
      x: [n[0], n[n.length - 1]], y: [data.bs_price, data.bs_price], name: "Black–Scholes", mode: "lines",
      line: { color: COLORS.text, width: 1.2, dash: "dash" }, hovertemplate: "Black–Scholes %{y:.4f}<extra></extra>",
    },
  ];
  plot("tree-chart", traces, layout2d({ xaxis: axis("steps n"), yaxis: axis("option price") }));
}

function drawTreeError(tree) {
  const error = tree.error.map(Math.abs);
  const pick = (parity) => tree.n.map((n, i) => i).filter((i) => tree.n[i] % 2 === parity);
  const points = (parity, name, color) => ({
    x: pick(parity).map((i) => tree.n[i]), y: pick(parity).map((i) => error[i]), name, mode: "markers",
    marker: { color, size: 6 }, hovertemplate: `${name}<br>n = %{x}<br>|error| %{y:.2e}<extra></extra>`,
  });
  const reference = {
    x: tree.n, y: tree.n.map((n) => (error[0] * tree.n[0]) / n), name: "slope −1", mode: "lines",
    line: REFERENCE, hoverinfo: "skip",
  };
  plot("tree-chart", [points(0, "even n", COLORS.series[0]), points(1, "odd n", COLORS.series[1]), reference],
    layout2d({ xaxis: axis("steps n", LOG_AXIS), yaxis: axis("|tree − Black–Scholes|", LOG_AXIS) }));
}

// Lines are standard errors, dots are the errors that were actually realised.
function drawMonteCarlo(mc) {
  const traces = [];
  for (const [method, { label, color }] of Object.entries(ESTIMATORS)) {
    traces.push({
      x: mc.N, y: mc[method].std_error, name: `${label}: standard error`, mode: "lines", line: { color, width: 2 },
      hovertemplate: `${label}<br>N = %{x}<br>standard error %{y:.2e}<extra></extra>`,
    });
    traces.push({
      x: mc.N, y: mc[method].error, name: `${label}: |MC − BS|`, mode: "markers", marker: { color, size: 6, opacity: 0.8 },
      showlegend: false, hovertemplate: `${label}<br>N = %{x}<br>|MC − BS| %{y:.2e}<extra></extra>`,
    });
  }
  const start = 2.5 * mc.plain.std_error[0];
  traces.push({
    x: mc.N, y: mc.N.map((n) => start * Math.sqrt(mc.N[0] / n)), name: "slope −½", mode: "lines",
    line: REFERENCE, hoverinfo: "skip",
  });
  traces.push({ x: [null], y: [null], name: "dots: realised |MC − BS|", mode: "markers", marker: { color: COLORS.muted, size: 6 } });
  plot("mc-conv-chart", traces, layout2d({ xaxis: axis("paths N", LOG_AXIS), yaxis: axis("error", LOG_AXIS) }));
}

function fillSummary(rows) {
  $("vr-rows").innerHTML = rows.map((row) => `
    <tr>
      <td><span class="dot" style="background:${ESTIMATORS[row.method].color}"></span>${ESTIMATORS[row.method].label}</td>
      <td>${fmtSci(row.std_error)}</td>
      <td>${fmtTimes(row.vr_factor)}</td>
      <td>${(1000 * row.runtime).toFixed(0)} ms</td>
      <td>${fmtTimes(row.efficiency_gain)}</td>
    </tr>`).join("");
  $("vr-hint").textContent = `Measured at N = ${rows[0].n_paths.toLocaleString("en-US")} paths.`;
}
