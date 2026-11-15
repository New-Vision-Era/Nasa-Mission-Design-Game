/* Game state. One plain object, persisted to localStorage so a refresh keeps the
   design and the active mission. Every change is broadcast on window as
   `smdg:state` so other systems (the 3D views) can follow along without
   touching the UI code:

     window.addEventListener("smdg:state", (e) => { const { screen, configuration, mission } = e.detail; });
*/

const SESSION_KEY = "smdg.session";
const SCENARIO_ID = "earth_observation_v4";

export function emptyConfig(scenarioId = SCENARIO_ID) {
  return {
    scenario_id: scenarioId,
    platform_id: null,
    instrument_ids: [],
    power: { mode: "platform_payload_budget", solar_array_ids: [], battery_ids: [], eps_id: null },
    communication_system_ids: [],
    adcs_system_id: null,
    propulsion_system_id: null,
    orbit_id: null,
    launch_vehicle_id: null,
  };
}

export const state = {
  screen: "home",
  catalog: null,          // GET /simulation/catalog
  scenario: null,         // the active scenario briefing
  user: null,             // {id, username} when logged in
  missionType: "earth",
  config: emptyConfig(),
  evaluation: null,       // POST /simulation/evaluate
  evalError: null,
  evaluating: false,
  mission: null,          // stored MCAS view {mission_id, status, state, debrief, ...}
  shownPeriod: 0,         // how far the operations animation has played
  debrief: null,
  previous: null,         // last finished debrief, for compare & replay
  designer: { tab: "spacecraft", slot: "platform", page: 0, inspect: null },
  reached: { briefing: false, designer: false, review: false, operations: false, results: false },
};

const listeners = new Set();
export function subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); }

export function save() {
  try {
    localStorage.setItem(SESSION_KEY, JSON.stringify({
      screen: state.screen, config: state.config, missionId: state.mission?.mission_id || null,
      reached: state.reached, missionType: state.missionType, previous: state.previous,
    }));
  } catch { /* storage unavailable: the game still works for this visit */ }
}

export function restore() {
  try {
    const raw = JSON.parse(localStorage.getItem(SESSION_KEY) || "null");
    if (!raw) return null;
    if (raw.config) state.config = { ...emptyConfig(), ...raw.config, power: { ...emptyConfig().power, ...(raw.config.power || {}) } };
    if (raw.reached) state.reached = { ...state.reached, ...raw.reached };
    if (raw.previous) state.previous = raw.previous;
    return raw;
  } catch { return null; }
}

export function notify(reason) {
  save();
  for (const fn of listeners) fn(reason);
  window.dispatchEvent(new CustomEvent("smdg:state", {
    detail: {
      reason,
      screen: state.screen,
      configuration: state.config,
      evaluation: state.evaluation,
      mission: state.mission?.state || null,
      shownPeriod: state.shownPeriod,
    },
  }));
}

/* --- catalog lookups --- */
export function rec(category, id) {
  if (!id || !state.catalog) return null;
  return state.catalog.categories[category]?.find((r) => r.id === id) || null;
}
export function anyRec(id) {
  if (!id || !state.catalog) return null;
  for (const list of Object.values(state.catalog.categories)) {
    const hit = list.find((r) => r.id === id);
    if (hit) return hit;
  }
  return null;
}
export const nameOf = (id) => anyRec(id)?.name || id;

/* --- design helpers --- */
export function apiReady(cfg = state.config) {
  return Boolean(cfg.platform_id && cfg.adcs_system_id && cfg.orbit_id && cfg.launch_vehicle_id)
    && (cfg.power.mode === "platform_payload_budget" || cfg.power.solar_array_ids.length > 0);
}

export function slotFilled(slot, cfg = state.config) {
  switch (slot) {
    case "platform": return Boolean(cfg.platform_id);
    case "science": return cfg.instrument_ids.length > 0;
    case "comms": return cfg.communication_system_ids.length > 0;
    case "adcs": return Boolean(cfg.adcs_system_id);
    case "orbit": return Boolean(cfg.orbit_id);
    case "launcher": return Boolean(cfg.launch_vehicle_id);
    case "power": return cfg.power.mode === "platform_payload_budget" || cfg.power.solar_array_ids.length > 0;
    case "propulsion": return true;
    default: return false;
  }
}

export function selectedIds(slot, cfg = state.config) {
  switch (slot) {
    case "platform": return cfg.platform_id ? [cfg.platform_id] : [];
    case "science": return cfg.instrument_ids;
    case "comms": return cfg.communication_system_ids;
    case "adcs": return cfg.adcs_system_id ? [cfg.adcs_system_id] : [];
    case "propulsion": return [cfg.propulsion_system_id];
    case "orbit": return cfg.orbit_id ? [cfg.orbit_id] : [];
    case "launcher": return cfg.launch_vehicle_id ? [cfg.launch_vehicle_id] : [];
    case "power": return [...cfg.power.solar_array_ids, ...cfg.power.battery_ids, cfg.power.eps_id].filter(Boolean);
    default: return [];
  }
}

export function toggleComponent(slot, id, r) {
  const c = state.config;
  const toggle = (list) => (list.includes(id) ? list.filter((x) => x !== id) : [...list, id]);
  switch (slot) {
    case "platform": c.platform_id = id; break;
    case "science": c.instrument_ids = toggle(c.instrument_ids); break;
    case "comms": c.communication_system_ids = toggle(c.communication_system_ids); break;
    case "adcs": c.adcs_system_id = id; break;
    case "propulsion": c.propulsion_system_id = c.propulsion_system_id === id ? null : id; break;
    case "orbit": c.orbit_id = id; break;
    case "launcher": c.launch_vehicle_id = id; break;
    case "power":
      if (r.family === "power_conditioning") c.power.eps_id = c.power.eps_id === id ? null : id;
      else if (r.family === "solar_array") c.power.solar_array_ids = c.power.solar_array_ids.includes(id) ? c.power.solar_array_ids.filter((x) => x !== id) : [...c.power.solar_array_ids, id];
      else c.power.battery_ids = c.power.battery_ids.includes(id) ? c.power.battery_ids.filter((x) => x !== id) : [...c.power.battery_ids, id];
      break;
  }
}

/* Power arrays and batteries may repeat: the count is the quantity. */
export function powerQty(id) {
  const p = state.config.power;
  return [...p.solar_array_ids, ...p.battery_ids].filter((x) => x === id).length;
}
export function changeQty(r, delta) {
  const p = state.config.power;
  const key = r.family === "solar_array" ? "solar_array_ids" : "battery_ids";
  if (delta > 0) p[key] = [...p[key], r.id];
  else {
    const i = p[key].lastIndexOf(r.id);
    if (i >= 0) p[key] = [...p[key].slice(0, i), ...p[key].slice(i + 1)];
  }
}

export function resetMission() {
  state.mission = null;
  state.debrief = null;
  state.shownPeriod = 0;
  state.reached.operations = false;
  state.reached.results = false;
}
