// Shared helpers: number formatting, loading and error states, and the Plotly theme.

export const COLORS = {
  text: "#e6ebf5",
  text2: "#a9b4c9",
  muted: "#7c89a3",
  grid: "#1e2a44",
  axis: "#2a3a5c",
  surface: "#111a2e",
  // categorical series, always used in this order
  series: ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181"],
  // one-hue ramp for ordered series such as maturities (short to long)
  ramp: ["#1c5cab", "#3987e5", "#86b6ef", "#cde2fb"],
};

// low values recede into the dark background, high values are bright
export const SEQUENTIAL = [[0, "#0d366b"], [0.5, "#3987e5"], [1, "#cde2fb"]];
// two opposite hues around a neutral midpoint, for signed errors
export const DIVERGING = [[0, "#3987e5"], [0.5, "#4a5468"], [1, "#e66767"]];

export const ESTIMATORS = {
  plain: { label: "Plain", color: COLORS.series[0] },
  antithetic: { label: "Antithetic", color: COLORS.series[1] },
  control_variate: { label: "Control variate", color: COLORS.series[2] },
};

export const $ = (id) => document.getElementById(id);

export function fmt(x, digits = 4) {
  return Number.isFinite(x) ? x.toFixed(digits) : "–";
}

export function fmtSci(x) {
  if (!Number.isFinite(x)) return "–";
  if (Math.abs(x) < 1e-12) return "0";
  return Math.abs(x) >= 1e-3 ? x.toFixed(4) : x.toExponential(1);
}

// a ratio such as "4.1×"; the API sends null when the ratio is infinite
export function fmtTimes(x) {
  if (!Number.isFinite(x)) return "∞";
  return x < 1e6 ? `${x.toFixed(1)}×` : "> 10⁶×";
}

export function fmtPct(x, digits = 2) {
  return Number.isFinite(x) ? `${(100 * x).toFixed(digits)}%` : "–";
}

export function renderMath(element) {
  if (window.renderMathInElement) {
    window.renderMathInElement(element, { delimiters: [{ left: "\\(", right: "\\)", display: false }] });
  }
}

// a small icon that shows the given explanation on hover or focus
export function info(html) {
  return `<span class="info" tabindex="0">ⓘ<span class="tip">${html}</span></span>`;
}

export function showError(context, error) {
  $("error-text").textContent = `${context}: ${error.message}`;
  $("error-banner").hidden = false;
}

export function clearError() {
  $("error-banner").hidden = true;
}

// Show a spinner on the given cards while the task runs; report failures in the banner.
export async function withLoading(cardIds, context, task) {
  const cards = cardIds.map($);
  cards.forEach((card) => card.classList.add("is-loading"));
  try {
    return await task();
  } catch (error) {
    showError(context, error);
    return null;
  } finally {
    cards.forEach((card) => card.classList.remove("is-loading"));
  }
}

// A segmented control: one active button, onChange receives its data-value.
export function segmented(id, onChange) {
  const root = $(id);
  root.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button || button.disabled) return;
    root.querySelectorAll("button").forEach((b) => b.classList.toggle("is-active", b === button));
    onChange(button.dataset.value);
  });
  return {
    get value() { return root.querySelector(".is-active").dataset.value; },
    set value(v) { root.querySelectorAll("button").forEach((b) => b.classList.toggle("is-active", b.dataset.value === v)); },
    setEnabled(v, enabled) { root.querySelector(`[data-value="${v}"]`).disabled = !enabled; },
  };
}

const AXIS = {
  gridcolor: COLORS.grid,
  linecolor: COLORS.axis,
  zerolinecolor: COLORS.axis,
  tickfont: { color: COLORS.muted, size: 11 },
  title: { font: { color: COLORS.text2, size: 12 } },
  automargin: true,
};

export function axis(title, extra = {}) {
  return { ...AXIS, title: { ...AXIS.title, text: title }, ...extra };
}

// log axis with ticks only at powers of ten
export const LOG_AXIS = { type: "log", dtick: 1, exponentformat: "power" };

export function layout2d(extra = {}) {
  return {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: COLORS.text, family: "'Plus Jakarta Sans', system-ui, -apple-system, 'Segoe UI', sans-serif", size: 12 },
    margin: { l: 58, r: 16, t: 36, b: 46 },
    // the legend sits above the plot so it never collides with the x-axis title
    legend: { orientation: "h", x: 0, y: 1.02, yanchor: "bottom", font: { color: COLORS.text2, size: 11 } },
    hoverlabel: { bgcolor: "#16213a", bordercolor: COLORS.axis, font: { color: COLORS.text } },
    ...extra,
  };
}

// starting viewpoints, chosen so each surface faces the viewer
export const CAMERAS = {
  greeks: { eye: { x: -1.35, y: -1.45, z: 0.7 }, center: { x: 0, y: 0, z: -0.14 } },
  volatility: { eye: { x: 1.5, y: -1.5, z: 0.7 }, center: { x: 0, y: 0, z: -0.14 } },
};

export function layout3d(xTitle, yTitle, zTitle, camera) {
  const axis3d = (title) => ({
    title: { text: title, font: { color: COLORS.text2, size: 12 } },
    gridcolor: COLORS.axis,
    zerolinecolor: COLORS.axis,
    backgroundcolor: COLORS.surface,
    showbackground: true,
    tickfont: { color: COLORS.muted, size: 10 },
  });
  return layout2d({
    margin: { l: 0, r: 0, t: 0, b: 0 },
    scene: {
      xaxis: axis3d(xTitle),
      yaxis: axis3d(yTitle),
      zaxis: axis3d(zTitle),
      camera,
      aspectmode: "manual",
      aspectratio: { x: 1.25, y: 1.25, z: 0.8 },
    },
    // keep the camera when the data changes, so switching views does not reset the rotation
    uirevision: "keep",
  });
}

export function colorbar(title) {
  return { title: { text: title, font: { color: COLORS.text2, size: 11 } }, tickfont: { color: COLORS.muted, size: 10 }, thickness: 12, len: 0.6 };
}

// the camera each 3D chart started with, so "Reset view" can restore it
const homeCameras = new Map();

export function plot(id, traces, layout) {
  if (layout.scene) homeCameras.set(id, layout.scene.camera);
  return window.Plotly.react($(id), traces, layout, { displaylogo: false, responsive: true });
}

// "Reset view" buttons: restore the default camera (3D) or autorange every axis (2D).
export function bindResetButtons() {
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-reset]");
    if (!button) return;
    const element = $(button.dataset.reset);
    if (!element.layout) return;
    if (element.layout.scene) {
      window.Plotly.relayout(element, { "scene.camera": homeCameras.get(element.id) });
      return;
    }
    const update = {};
    Object.keys(element.layout).filter((key) => /^[xy]axis\d*$/.test(key)).forEach((key) => { update[`${key}.autorange`] = true; });
    window.Plotly.relayout(element, update);
  });
}

// Collapsible sections and "data-toggle" buttons.
export function bindDisclosure() {
  // a chart drawn inside a closed section has no size yet, so fit it when the section opens
  document.addEventListener("toggle", (event) => {
    if (!event.target.open) return;
    event.target.querySelectorAll(".js-plotly-plot").forEach((chart) => window.Plotly.Plots.resize(chart));
  }, true);
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-toggle]");
    if (!button) return;
    const target = $(button.dataset.toggle);
    target.hidden = !target.hidden;
  });
}
