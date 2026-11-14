// Tab 2: price and Greeks against spot for several maturities, and 3D surfaces over spot and maturity.

import { postJSON } from "./api.js";
import { $, CAMERAS, COLORS, SEQUENTIAL, axis, colorbar, layout2d, layout3d, plot, segmented, withLoading } from "./ui.js";

const MATURITIES = [
  { T: 1 / 12, label: "1 month" },
  { T: 0.25, label: "3 months" },
  { T: 0.5, label: "6 months" },
  { T: 1.0, label: "1 year" },
];

const PANELS = [
  { key: "price", title: "Price" },
  { key: "delta", title: "Delta Δ" },
  { key: "gamma", title: "Gamma Γ" },
  { key: "vega", title: "Vega ν (per 1.00 of σ)" },
  { key: "theta", title: "Theta Θ (per year)" },
  { key: "rho", title: "Rho ρ (per 1.00 of r)" },
];

const SURFACE_LABELS = { price: "Price", delta: "Delta Δ", gamma: "Gamma Γ", vega: "Vega ν" };

let curveData = null;
let surfaceData = null;
let lastInputs = null;
let picker = null;

export function init() {
  picker = segmented("curve-greek", drawCurves);
  $("surface-greek").addEventListener("change", drawSurface);
}

export async function refresh(inputs) {
  lastInputs = inputs;
  const { S, K, T, r, q, sigma, kind } = inputs;
  // the grid is centred on the spot, so with an odd number of points the spot is a grid node
  const base = { K, r, q, sigma, kind, S_min: 0.5 * S, S_max: 1.5 * S };
  const tMax = Math.max(1, 2 * T);
  const tGrid = Array.from({ length: 40 }, (_, i) => 0.02 + ((tMax - 0.02) * i) / 39);
  // add the option's own maturity so its marker sits exactly on the surface
  const tValues = [...new Set([...tGrid, T])].sort((a, b) => a - b);

  const data = await withLoading(["card-greek-curves", "card-greek-surface"], "Could not compute the Greeks", () =>
    Promise.all([
      postJSON("/api/greeks-surface", { ...base, n_S: 121, T_values: MATURITIES.map((m) => m.T) }),
      postJSON("/api/greeks-surface", { ...base, n_S: 61, T_values: tValues }),
    ]));
  if (!data) return;
  curveData = data[0];
  surfaceData = data[1];
  drawCurves();
  drawSurface();
}

// One line per maturity. Shows the chosen quantity, or all six as small charts sharing one legend.
function drawCurves() {
  if (!curveData) return;
  const all = picker.value === "all";
  const panels = all ? PANELS : PANELS.filter((panel) => panel.key === picker.value);
  const element = $("greek-curves");
  element.classList.toggle("tall", all);

  const traces = [];
  const layout = layout2d({ annotations: [], shapes: [] });
  if (all) {
    layout.grid = { rows: 2, columns: 3, pattern: "independent", xgap: 0.12, ygap: 0.22 };
    layout.margin = { l: 50, r: 16, t: 30, b: 40 };
    layout.legend = { orientation: "h", x: 0.5, xanchor: "center", y: -0.17, font: { color: COLORS.text2, size: 11 } };
  }

  panels.forEach((panel, i) => {
    const n = i === 0 ? "" : String(i + 1);
    MATURITIES.forEach((maturity, j) => {
      traces.push({
        x: curveData.S,
        y: curveData[panel.key][j],
        xaxis: `x${n}`,
        yaxis: `y${n}`,
        name: maturity.label,
        legendgroup: maturity.label,
        showlegend: i === 0,
        mode: "lines",
        line: { color: COLORS.ramp[j], width: 2 },
        hovertemplate: `${maturity.label}<br>S = %{x:.2f}<br>${panel.title.split(" (")[0]} = %{y:.4f}<extra></extra>`,
      });
    });
    layout[`xaxis${n}`] = axis(!all || i >= 3 ? "spot price S" : "");
    layout[`yaxis${n}`] = axis(all ? "" : panel.title);
    if (all) {
      layout.annotations.push({
        text: panel.title, xref: `x${n} domain`, yref: `y${n} domain`, x: 0, y: 1.14,
        showarrow: false, font: { color: COLORS.text, size: 12 },
      });
    }
    // thin vertical line at the strike
    layout.shapes.push({
      type: "line", xref: `x${n}`, yref: `y${n} domain`, x0: lastInputs.K, x1: lastInputs.K, y0: 0, y1: 1,
      line: { color: COLORS.muted, width: 1, dash: "dot" },
    });
  });
  // the chart is taller when it holds six panels, so fit it to its box after drawing
  plot("greek-curves", traces, layout).then(() => window.Plotly.Plots.resize(element));
}

function drawSurface() {
  if (!surfaceData) return;
  const key = $("surface-greek").value;
  const label = SURFACE_LABELS[key];
  const { S, T } = lastInputs;
  const row = surfaceData.T.indexOf(T);
  const col = (surfaceData.S.length - 1) / 2;

  const surface = {
    type: "surface",
    x: surfaceData.S,
    y: surfaceData.T,
    z: surfaceData[key],
    colorscale: SEQUENTIAL,
    colorbar: colorbar(label),
    contours: { z: { show: true, usecolormap: true, highlightcolor: COLORS.text, project: { z: false } } },
    hovertemplate: `S = %{x:.2f}<br>T = %{y:.2f} y<br>${label} = %{z:.4f}<extra></extra>`,
  };
  const marker = {
    type: "scatter3d",
    mode: "markers",
    x: [S],
    y: [T],
    z: [surfaceData[key][row][col]],
    marker: { color: COLORS.text, size: 6, line: { color: COLORS.surface, width: 2 } },
    name: "your option",
    showlegend: false,
    hovertemplate: `Your option<br>S = %{x:.2f}<br>T = %{y:.2f} y<br>${label} = %{z:.4f}<extra></extra>`,
  };
  plot("greek-surface", [surface, marker], layout3d("spot price S", "maturity T (years)", label, CAMERAS.greeks));
}
