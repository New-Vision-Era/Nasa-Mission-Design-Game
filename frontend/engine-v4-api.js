/* Frontend bridge for the additive real-data simulation API (equipment_v4).
   Same pattern as mars-api.js. No UI here: any page can call window.EngineV4API. */
(() => {
  "use strict";
  const BASE = window.ENGINE_V4_API_BASE || "http://127.0.0.1:8000/api/v1/simulation";

  async function request(path, body, token) {
    const auth = token ? {Authorization: `Bearer ${token}`} : {};
    let response;
    try {
      response = await fetch(BASE + path, body === undefined ? {headers: auth} : {
        method: "POST",
        headers: {"Content-Type": "application/json", ...auth},
        body: JSON.stringify(body)
      });
    } catch (_) {
      throw new Error("Cannot reach the backend. Start FastAPI at http://127.0.0.1:8000 and refresh.");
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.error?.message || `Simulation API request failed (${response.status}).`);
      error.code = data.error?.code;
      error.field = data.error?.field;
      error.details = data.error?.details || [];
      error.result = data.error?.result;  /* present on 409 not_launchable */
      throw error;
    }
    return data;
  }

  window.EngineV4API = {
    /* Real component catalog: {dataset_id, units, value_kinds, categories: {platforms: [...], ...}} */
    catalog: () => request("/catalog"),
    /* Scenario briefings and default parameters (gameplay assumptions) */
    scenarios: () => request("/scenarios"),
    /* configuration: component ids; scenarioParameters: optional overrides; seed: optional integer */
    run: (configuration, scenarioParameters, seed) =>
      request("/run", {configuration, scenario_parameters: scenarioParameters || null, seed: seed ?? 0}),
    recommend: (configuration, scenarioParameters) =>
      request("/recommend", {configuration, scenario_parameters: scenarioParameters || null}),
    /* Launch and store. token: bearer token from /auth/login, or omit for a guest run.
       options: {scenarioParameters, seed, name}. Rejects with code "not_launchable" if a hard constraint fails. */
    launch: (configuration, options = {}, token) =>
      request("/runs", {configuration, scenario_parameters: options.scenarioParameters || null,
                        seed: options.seed ?? null, name: options.name || null}, token),
    /* The logged-in player's stored runs, newest first */
    history: token => request("/runs", undefined, token),
    /* One stored run in full: {run_id, name, created_at, scenario_parameters, result} */
    getRun: (runId, token) => request("/runs/" + encodeURIComponent(runId), undefined, token)
  };
})();
