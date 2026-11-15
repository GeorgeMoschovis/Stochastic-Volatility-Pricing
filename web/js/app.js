// Entry point: tab switching, the shared inputs form, and refreshing the active tab.

import * as convergence from "./convergence.js";
import * as greeks from "./greeks.js";
import * as pricer from "./pricer.js";
import * as surface from "./surface.js";
import { $, bindDisclosure, bindResetButtons, clearError, currentTheme, renderMath, segmented, setTheme } from "./ui.js";

const TABS = { pricer, greeks, convergence, surface };
const HULL = { S: 42, K: 40, T: 0.5, sigma: 0.2, r: 0.1, q: 0, n_steps: 500, n_paths: 100000, seed: 42 };

let active = "pricer";
// bumped whenever the inputs change; a tab recomputes only if it has not shown this version yet
let version = 0;
const shownVersion = {};

const kind = segmented("kind", inputsChanged);

function readInputs() {
  const form = $("inputs");
  const values = { kind: kind.value };
  for (const name of Object.keys(HULL)) values[name] = Number(form.elements[name].value);
  return values;
}

async function refreshActive() {
  if (shownVersion[active] === version) return;
  shownVersion[active] = version;
  clearError();
  await TABS[active].refresh(readInputs());
}

// pressing Enter fires both "change" and "submit": the short delay merges them into one refresh
let timer;
function inputsChanged() {
  clearTimeout(timer);
  timer = setTimeout(() => {
    version += 1;
    refreshActive();
  }, 50);
}

function showTab(name) {
  active = name;
  document.querySelectorAll(".tab").forEach((tab) => tab.classList.toggle("is-active", tab.dataset.tab === name));
  document.querySelectorAll(".panel").forEach((panel) => panel.classList.toggle("is-active", panel.id === `tab-${name}`));
  // the volatility tab has its own controls and uses the full width
  $("layout").classList.toggle("no-sidebar", name === "surface");
  refreshActive();
  // charts drawn while their tab was hidden need to pick up the real size
  window.dispatchEvent(new Event("resize"));
}

// The button names the theme it switches to.
function applyTheme(name) {
  setTheme(name);
  $("theme-toggle").textContent = name === "dark" ? "Light theme" : "Dark theme";
  Object.values(TABS).forEach((tab) => tab.redraw());
}

function init() {
  applyTheme(currentTheme());
  $("theme-toggle").addEventListener("click", () => applyTheme(currentTheme() === "dark" ? "light" : "dark"));
  renderMath(document.body);
  bindResetButtons();
  bindDisclosure();
  Object.values(TABS).forEach((tab) => tab.init());

  document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => showTab(tab.dataset.tab)));
  $("error-close").addEventListener("click", clearError);
  $("inputs").addEventListener("change", inputsChanged);
  $("inputs").addEventListener("submit", (event) => {
    event.preventDefault();
    inputsChanged();
  });
  $("reset-inputs").addEventListener("click", () => {
    for (const [name, value] of Object.entries(HULL)) $("inputs").elements[name].value = value;
    kind.value = "call";
    inputsChanged();
  });

  refreshActive();
}

init();
