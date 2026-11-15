/* Entry point: loads reference data, restores the session and routes between screens. */
import { api, hasToken, onEngineProgress, engineMode } from "./api.js";
import { state, restore, notify, apiReady, subscribe, isSurface } from "./state.js";
import "./sound.js";
import * as surface from "./screens/surface.js";
import { el, toast, esc } from "./ui.js";
import { loadMission } from "./screens/account.js";
import * as home from "./screens/home.js";
import * as briefing from "./screens/briefing.js";
import * as designer from "./screens/designer.js";
import * as review from "./screens/review.js";
import * as launch from "./screens/launch.js";
import * as operations from "./screens/operations.js";
import * as results from "./screens/results.js";
import * as debrief from "./screens/debrief.js";

const SCREENS = { home, briefing, designer, review, launch, operations, results, debrief };
const SURFACE_SCREENS = { designer: surface.designer, review: surface.review, operations: surface.operations };
const screenFor = (name) => (isSurface() && SURFACE_SCREENS[name]) || SCREENS[name];


function canEnter(screen) {
  if (isSurface()) {
    const s = state.surface;
    switch (screen) {
      case "home": case "briefing": return true;
      case "designer": return state.reached.briefing && Boolean(s.catalog);
      case "review": return Boolean(s.catalog && s.evaluation);
      case "launch": return Boolean(s.evaluation?.launchable) && !s.flight;
      case "operations": return Boolean(s.flight) && s.flight.status !== "NOT_LAUNCHED";
      case "results": case "debrief": return Boolean(state.debrief) && s.flight?.status === "COMPLETED";
      default: return false;
    }
  }
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
  document.getElementById("app").dataset.screen = screen;
  const host = document.getElementById("screen");
  host.innerHTML = "";
  current = screenFor(screen);
  const node = current.render({ go });
  host.append(node);
  current.mounted?.(node);
  notify("screen");
}


async function boot() {
  subscribe((reason) => { if (reason === "auth" && state.screen === "home") go("home", { force: true }); });
  const saved = restore();
  const host = document.getElementById("screen");
  host.append(el('<div class="page" style="display:grid;place-items:center"><div class="stack" style="align-items:center;gap:10px"><div class="row"><span class="spinner"></span><span class="muted" id="boot-msg">Contacting mission control…</span></div><p class="tiny" id="boot-note" style="text-align:center"></p></div></div>'));
  const stopProgress = onEngineProgress((text) => {
    const m = document.getElementById("boot-msg");
    const n = document.getElementById("boot-note");
    if (m && text !== "ready") m.textContent = text;
    if (n) n.textContent = "The engine runs in your browser. The first visit downloads about 15 MB.";
  });
  try {
    const [catalog, scenarios] = await Promise.all([api.catalog(), api.scenarios()]);
    stopProgress();
    state.catalog = catalog;
    state.scenario = scenarios.scenarios.find((s) => s.id === state.config.scenario_id) || scenarios.scenarios[0];
  } catch (err) {
    host.innerHTML = "";
    host.append(el(`<div class="page" style="display:grid;place-items:center;text-align:center"><div class="stack" style="align-items:center;max-width:440px">
      <div class="eyebrow">Link lost</div><h1 class="title">Mission control is offline</h1>
      <p class="muted">${esc(err.message)}</p>
      <p class="tiny mono">${engineMode() === "browser" ? "In-browser engine failed to start. Try another browser or reload." : "uvicorn backend.app.main:create_app --factory --port 8000"}</p>
      <button class="btn" onclick="location.reload()">RETRY</button></div></div>`));
    return;
  }
  if (hasToken()) {
    try { state.user = await api.me(); } catch { state.user = null; }
  }

  if (isSurface()) {
    try { await surface.loadCatalog(state.missionType); } catch { state.missionType = "earth"; }
  }
  // Resume an unfinished mission if there was one.
  if (saved?.missionId && !isSurface()) {
    try { await loadMission(saved.missionId, { go, silent: true }); return; } catch { /* fall through */ }
  }
  const start = saved?.screen && !["launch", "operations", "results", "debrief"].includes(saved.screen) ? saved.screen : "home";
  go(canEnter(start) ? start : "home", { force: true });
  if ((start === "designer" || start === "review") && !isSurface()) designer.evaluateNow();
}

// 3D views load on their own: if WebGL or the files are missing, the game still runs.
import("./viewer3d.js").catch((err) => console.warn("3D view disabled:", err));

window.addEventListener("unhandledrejection", (e) => toast(e.reason?.message || "Unexpected error", "error"));
boot();
