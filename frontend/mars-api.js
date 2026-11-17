/* Frontend bridge for the additive Mars rover API. */
(() => {
  "use strict";
  const BASE = window.MARS_API_BASE || "http://127.0.0.1:8000/api/v1/mars";
  async function post(path, selection) {
    let response;
    try {
      response = await fetch(BASE + path, {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify(selection)
      });
    } catch (_) {
      throw new Error("Cannot reach the Mars backend. Start FastAPI at http://127.0.0.1:8000 and refresh.");
    }
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || body.error?.message || `Mars API request failed (${response.status}).`);
    return body;
  }
  window.MarsAPI = {
    evaluate: selection => post("/evaluate", selection),
    simulate: selection => post("/simulate", selection)
  };
})();
