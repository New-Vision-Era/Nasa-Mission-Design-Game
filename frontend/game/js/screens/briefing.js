/* 02 · Briefing + requirements on one screen. */
import { state } from "../state.js";
import { el, actions, esc } from "../ui.js";
import { usd } from "../catalog.js";

export function render({ go }) {
  const sc = state.scenario;
  const p = sc.parameters;
  const sci = p.science || {};
  const first = sc.briefing.split(/(?<=\.)\s/)[0];
  const families = (sci.required_instrument_families_any || []).map((f) => f.replace("optical_", "")).join(" / ");

  const node = el(`<div class="page">
    <div class="head">
      <div><div class="eyebrow">Phase 01 · Mission setup</div><h1 class="title">Mission briefing</h1></div>
      <span class="pill cyan">EARTH WATCH / 001</span>
    </div>
    <div class="briefing-grid">
      <div class="card brief-hero">
        <div class="planet-mini"></div>
        <span class="tag">Earth science</span>
        <h2>${esc(sc.name)}</h2>
        <p>${esc(first)}</p>
        <div class="objectives">
          <div class="objective"><span class="label">Resolution</span><b>≤ ${sci.max_gsd_m ?? "—"} m</b></div>
          <div class="objective"><span class="label">Swath</span><b>≥ ${sci.min_swath_km ?? "—"} km</b></div>
          <div class="objective"><span class="label">Imager</span><b style="font-size:14px">${esc(families || "—")}</b></div>
          <div class="objective"><span class="label">Orbit</span><b style="font-size:14px">${sci.prefer_sun_synchronous ? "Sun-synchronous" : "Any LEO"}</b></div>
        </div>
      </div>
      <div class="card stack" style="gap:12px">
        <div class="eyebrow">Requirements</div>
        <div class="req-grid">
          <div class="req"><span class="label">Budget</span><b>${usd(p.budget_usd)}</b></div>
          <div class="req"><span class="label">Duration</span><b>${Math.round(p.mission_duration_days)} days</b></div>
          <div class="req"><span class="label">Ground stations</span><b style="font-size:13px">${(p.ground_station_types || []).map((g) => g.replace("_", "-").toUpperCase()).join(" · ")}</b></div>
          <div class="req"><span class="label">Success at</span><b>${Math.round(p.success_threshold * 100)}% obs.</b></div>
        </div>
        <div class="rules">
          <div class="rule"><span class="tag fail">Hard</span><span>Must pass to launch: mass, power, uplink, orbit, launcher, budget.</span></div>
          <div class="rule"><span class="tag warn">Soft</span><span>Raises your score: better science, margins, data return.</span></div>
          <div class="rule"><span class="tag ghost">Events</span><span>Anomalies happen in flight. Your design decides your options.</span></div>
        </div>
      </div>
    </div>
    <div class="footer">
      <button class="btn ghost" data-action="back">← HOME</button>
      <button class="btn" data-action="accept">ACCEPT MISSION →</button>
    </div>
  </div>`);
  return actions(node, {
    back: () => go("home"),
    accept: () => { state.reached.designer = true; go("designer", { force: true }); },
  });
}
