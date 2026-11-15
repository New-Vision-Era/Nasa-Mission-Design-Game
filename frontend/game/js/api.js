/* API client for the game. Two ways to reach the same backend code:

   - server: the FastAPI backend under /api/v1 (uvicorn). Used when it answers.
   - browser: the same Python backend running in the page (Pyodide in a Web Worker,
     js/engine-worker.js). Used on GitHub Pages and whenever no server answers.

   Force one with ?engine=server or ?engine=browser, or set window.GAME_API_BASE. */

const BASE = window.GAME_API_BASE
  || (location.protocol.startsWith("http") && location.port !== "5500" && location.port !== "5173"
    ? `${location.origin}/api/v1`
    : "http://127.0.0.1:8000/api/v1");

const forced = new URLSearchParams(location.search).get("engine");
let mode = forced === "browser" || forced === "server" ? forced
  : location.hostname.endsWith("github.io") ? "browser" : null;
let modePromise = null;
const progressListeners = new Set();
export function onEngineProgress(fn) { progressListeners.add(fn); return () => progressListeners.delete(fn); }
export const engineMode = () => mode;

function resolveMode() {
  if (mode) return Promise.resolve(mode);
  if (!modePromise) {
    modePromise = (async () => {
      try {
        const ctrl = new AbortController();
        const timer = setTimeout(() => ctrl.abort(), 1500);
        const res = await fetch(`${BASE}/health`, { signal: ctrl.signal });
        clearTimeout(timer);
        mode = res.ok ? "server" : "browser";
      } catch { mode = "browser"; }
      return mode;
    })();
  }
  return modePromise;
}

/* ---- in-browser backend (Web Worker) ---- */
let worker = null;
let nextId = 1;
const pending = new Map();
function engine() {
  if (!worker) {
    worker = new Worker(new URL("./engine-worker.js", import.meta.url));
    worker.onmessage = (e) => {
      const msg = e.data;
      if (msg.type === "progress") { progressListeners.forEach((fn) => fn(msg.text)); return; }
      const p = pending.get(msg.id);
      if (p) { pending.delete(msg.id); p(msg); }
    };
    worker.onerror = (e) => {
      for (const [id, p] of pending) { pending.delete(id); p({ status: 0, body: { error: { code: "engine_error", message: e.message || "The in-browser engine failed to start." } } }); }
    };
  }
  return worker;
}
function browserRequest(method, path, body, tok) {
  return new Promise((resolve) => {
    const id = nextId++;
    pending.set(id, resolve);
    engine().postMessage({ id, method, path: `/api/v1${path}`, body, token: tok });
  });
}

const TOKEN_KEY = "smdg.token";

function readToken() {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}

let token = readToken();

export function setToken(value) {
  token = value || null;
  try { value ? localStorage.setItem(TOKEN_KEY, value) : localStorage.removeItem(TOKEN_KEY); } catch { /* storage off */ }
}

export function hasToken() { return Boolean(token); }

export class ApiError extends Error {
  constructor(status, body) {
    const err = body?.error || {};
    super(err.message || `Request failed (${status}).`);
    this.status = status;
    this.code = err.code;
    this.field = err.field;
    this.details = err.details || [];
    this.result = err.result;
  }
}

async function request(method, path, body) {
  if ((await resolveMode()) === "browser") {
    const out = await browserRequest(method, path, body, token);
    if (out.status === 204) return null;
    if (out.status < 200 || out.status >= 300) {
      if (out.status === 401 && token) setToken(null);
      throw new ApiError(out.status, out.body);
    }
    return out.body;
  }
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let response;
  try {
    response = await fetch(BASE + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError(0, { error: { code: "offline", message: "Cannot reach mission control. Is the backend running on port 8000?" } });
  }
  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && token) setToken(null);
    throw new ApiError(response.status, data);
  }
  return data;
}

const sim = "/simulation";

export const api = {
  base: BASE,
  // reference data
  catalog: () => request("GET", `${sim}/catalog`),
  scenarios: () => request("GET", `${sim}/scenarios`),
  // design
  evaluate: (configuration) => request("POST", `${sim}/evaluate`, { configuration }),
  recommend: (configuration) => request("POST", `${sim}/recommend`, { configuration }),
  // MCAS interactive missions
  startMission: (configuration, name, seed) =>
    request("POST", `${sim}/missions`, { configuration, name: name || null, seed: seed ?? null }),
  getMission: (id) => request("GET", `${sim}/missions/${encodeURIComponent(id)}`),
  decide: (id, anomalyId, responseId) =>
    request("POST", `${sim}/missions/${encodeURIComponent(id)}/decisions`, { anomaly_id: anomalyId, response_id: responseId }),
  debrief: (id) => request("GET", `${sim}/missions/${encodeURIComponent(id)}/debrief`),
  history: () => request("GET", `${sim}/missions?limit=50`),
  // surface missions (Mars rover, lunar lander)
  surfaceCatalog: (mission) => request("GET", `/surface/${mission}/catalog`),
  surfaceEvaluate: (mission, selection) => request("POST", `/surface/${mission}/evaluate`, { selection }),
  surfaceFly: (mission, selection, decisions) => request("POST", `/surface/${mission}/fly`, { selection, decisions: decisions || {} }),
  surfaceRecommend: (mission, selection) => request("POST", `/surface/${mission}/recommend`, { selection }),
  // accounts
  register: (username, password) => request("POST", "/auth/register", { username, password }),
  login: (username, password) => request("POST", "/auth/login", { username, password }),
  logout: () => request("POST", "/auth/logout"),
  me: () => request("GET", "/auth/me"),
};
