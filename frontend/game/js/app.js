/* Entry point: loads reference data, restores the session and routes between screens. */
import { api, hasToken } from "./api.js";
import { state, restore, notify, apiReady, subscribe } from "./state.js";
import { el, toast, SVG, esc } from "./ui.js";
import { openProfile, openHistory, loadMission } from "./screens/account.js";
import * as home from "./screens/home.js";
import * as briefing from "./screens/briefing.js";
import * as designer from "./screens/designer.js";
import * as review from "./screens/review.js";
import * as launch from "./screens/launch.js";
import * as operations from "./screens/operations.js";
import * as results from "./screens/results.js";
import * as debrief from "./screens/debrief.js";

const SCREENS = { home, briefing, designer, review, launch, operations, results, debrief };

const JOURNEY = [
  ["home", "Mission Control"],
  ["briefing", "Briefing"],
  ["designer", "Engineering"],
  ["review", "Validation"],
  ["launch", "Launch"],
  ["operations", "Operations"],
  ["results", "Results"],
  ["debrief", "Debrief"],
];

const CRUMB = {
  home: "CONTROL", briefing: "BRIEFING", designer: "ENGINEERING WORKSPACE", review: "PRE-LAUNCH VALIDATION",
  launch: "LAUNCH SEQUENCE", operations: "MISSION OPERATIONS", results: "MISSION REPORT", debrief: "ENGINEERING DEBRIEF",
};

function canEnter(screen) {
  const done = state.mission?.status === "COMPLETED" || state.mission?.status === "NOT_LAUNCHED";
  switch (screen) {
    case "home": case "briefing": return true;
    case "designer": return state.reached.briefing;
    case "review": return state.reached.designer && apiReady();
    case "launch": return Boolean(state.evaluation?.launchable) && !state.mission;
    case "operations": return Boolean(state.mission) && state.mission.status !== "NOT_LAUNCHED";
    case "results": case "debrief": return done && Boolean(state.debrief);
    default: return false;
  }
}

let current = null;

export function go(screen, opts = {}) {
  if (!SCREENS[screen]) return;
  if (!opts.force && !canEnter(screen)) return;
  current?.leave?.();
  state.screen = screen;
  if (state.reached[screen] === false) state.reached[screen] = true;
  const app = document.getElementById("app");
  app.classList.toggle("no-chrome", screen === "home");
  const host = document.getElementById("screen");
  host.innerHTML = "";
  current = SCREENS[screen];
  const node = current.render({ go });
  host.append(node);
  current.mounted?.(node);
  document.getElementById("crumb").textContent = CRUMB[screen];
  renderJourney();
  notify("screen");
}

function renderJourney() {
  const nav = document.getElementById("journey");
  const idx = JOURNEY.findIndex(([k]) => k === state.screen);
  nav.innerHTML = '<div class="label">Mission journey</div>' + JOURNEY.map(([key, label], i) => {
    const cls = [key === state.screen ? "active" : "", i < idx ? "done" : ""].join(" ");
    return `<button class="${cls}" data-go="${key}" ${canEnter(key) ? "" : "disabled"}><span class="n">${String(i + 1).padStart(2, "0")}</span><span class="txt">${label}</span></button>`;
  }).join("");
  const m = state.mission;
  document.getElementById("side-mission").textContent = state.scenario ? "EARTH WATCH / 001" : "—";
  document.getElementById("side-status").textContent = m
    ? (m.status === "COMPLETED" ? `COMPLETE · ${Math.round(m.score_total ?? 0)} PTS` : m.status === "AWAITING_DECISION" ? "IN FLIGHT · DECISION" : m.status.replaceAll("_", " "))
    : "DESIGN PHASE · NOT LAUNCHED";
}

export function refreshChrome() {
  renderJourney();
  const av = document.getElementById("top-profile");
  av.textContent = state.user ? state.user.username[0].toUpperCase() : "G";
  av.title = state.user ? `Logged in as ${state.user.username}` : "Guest — log in to keep a mission history";
}

async function boot() {
  document.getElementById("journey").addEventListener("click", (e) => {
    const b = e.target.closest("[data-go]");
    if (b && !b.disabled) go(b.dataset.go);
  });
  const hist = document.getElementById("top-history");
  hist.innerHTML = SVG.history;
  hist.addEventListener("click", () => openHistory({ go }));
  document.getElementById("top-profile").addEventListener("click", () => openProfile({ onChange: refreshChrome }));

  subscribe((reason) => { if (reason !== "screen") refreshChrome(); });
  const saved = restore();
  const pill = document.getElementById("api-pill");
  const host = document.getElementById("screen");
  host.append(el('<div class="page" style="display:grid;place-items:center"><div class="row"><span class="spinner"></span><span class="muted">Contacting mission control…</span></div></div>'));
  try {
    const [catalog, scenarios] = await Promise.all([api.catalog(), api.scenarios()]);
    state.catalog = catalog;
    state.scenario = scenarios.scenarios.find((s) => s.id === state.config.scenario_id) || scenarios.scenarios[0];
    pill.className = "pill ok";
    pill.innerHTML = '<i class="dot"></i> SYSTEM ONLINE';
  } catch (err) {
    pill.className = "pill bad";
    pill.innerHTML = '<i class="dot"></i> OFFLINE';
    host.innerHTML = "";
    host.append(el(`<div class="page" style="display:grid;place-items:center;text-align:center"><div class="stack" style="align-items:center;max-width:440px">
      <div class="eyebrow">Link lost</div><h1 class="title">Mission control is offline</h1>
      <p class="muted">${esc(err.message)}</p>
      <p class="tiny mono">uvicorn backend.app.main:create_app --factory --port 8000</p>
      <button class="btn" onclick="location.reload()">RETRY</button></div></div>`));
    return;
  }
  if (hasToken()) {
    try { state.user = await api.me(); } catch { state.user = null; }
  }
  refreshChrome();

  // Resume an unfinished mission if there was one.
  if (saved?.missionId) {
    try { await loadMission(saved.missionId, { go, silent: true }); return; } catch { /* fall through */ }
  }
  const start = saved?.screen && !["launch", "operations", "results", "debrief"].includes(saved.screen) ? saved.screen : "home";
  go(canEnter(start) ? start : "home", { force: true });
  if (start === "designer" || start === "review") designer.evaluateNow();
}

window.addEventListener("unhandledrejection", (e) => toast(e.reason?.message || "Unexpected error", "error"));
boot();
