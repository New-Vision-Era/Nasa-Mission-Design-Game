/* Frontend bridge for the additive real-data simulation API (equipment_v4).
   Same pattern as mars-api.js. No UI here: any page can call window.EngineV4API. */
(() => {
  "use strict";
  const BASE = window.ENGINE_V4_API_BASE || "http://127.0.0.1:8000/api/v1/simulation";

  async function request(path, body) {
    let response;
    try {
      response = await fetch(BASE + path, body === undefined ? {} : {
        method: "POST",
        headers: {"Content-Type": "application/json"},
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
      request("/recommend", {configuration, scenario_parameters: scenarioParameters || null})
  };
})();
