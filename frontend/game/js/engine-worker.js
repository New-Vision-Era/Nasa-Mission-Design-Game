/* The game's backend, running in the browser (used when no server is reachable, e.g. GitHub Pages).

   Python (Pyodide, vendor/pyodide) runs the same backend code as the server: py/bundle.zip holds
   backend/app, simulation and data, built by scripts/build_pages.sh. Requests from js/api.js arrive
   as {id, method, path, body, token}; backend/app/browser_api.py answers them like FastAPI would.
   The SQLite database is kept in IndexedDB, so accounts and saved missions survive a reload. */
/* global importScripts, loadPyodide */
importScripts("../vendor/pyodide/pyodide.js");

const base = new URL("../", self.location.href);
let api = null;
let pyodide = null;
let saveTimer = null;

function progress(text) { self.postMessage({ type: "progress", text }); }

function persist() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => pyodide.FS.syncfs(false, () => {}), 300);
}

const ready = (async () => {
  progress("Starting the mission computer…");
  pyodide = await loadPyodide({ indexURL: new URL("vendor/pyodide/", base).href });
  progress("Loading engineering libraries…");
  await pyodide.loadPackage(["pydantic", "sqlite3"]);
  const FS = pyodide.FS;
  try {
    FS.mkdir("/data");
    FS.mount(pyodide.FS.filesystems.IDBFS, {}, "/data");
    await new Promise((resolve) => FS.syncfs(true, () => resolve()));
  } catch { /* no IndexedDB (private mode): data lasts for this visit only */ }
  progress("Loading the simulation engine…");
  const bundle = await fetch(new URL("py/bundle.zip", base));
  if (!bundle.ok) throw new Error(`py/bundle.zip missing (${bundle.status}). Run scripts/build_pages.sh.`);
  pyodide.unpackArchive(new Uint8Array(await bundle.arrayBuffer()), "zip", { extractDir: "/app" });
  pyodide.runPython(`
import sys
sys.path.insert(0, "/app")
from backend.app.browser_api import BrowserApi
api = BrowserApi("/data/space_mission.db")
`);
  api = pyodide.globals.get("api");
  persist();
  progress("ready");
})();

self.onmessage = async (event) => {
  const { id, method, path, body, token } = event.data;
  try {
    await ready;
    const out = JSON.parse(api.handle(method, path, body === undefined ? null : JSON.stringify(body), token || null));
    if (method !== "GET") persist();
    self.postMessage({ id, status: out.status, body: out.body });
  } catch (err) {
    self.postMessage({ id, status: 0, body: { error: { code: "engine_error", message: String(err?.message || err).split("\n").slice(-2).join(" ") } } });
  }
};
