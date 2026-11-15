/* 02 · Briefing + requirements on one screen. */
import { state, isSurface } from "../state.js";
import { el, actions, esc } from "../ui.js";
import { usd } from "../catalog.js";

function renderSurface({ go }) {
  const m = state.surface.catalog.mission;
  const node = el(`<div class="page">
    <div class="head">
      <div class="head-title"><div class="eyebrow">Phase 01 · Mission setup</div><h1 class="title">Mission briefing</h1></div>
      <span class="pill cyan">${esc(m.short)}</span>
    </div>
    <div class="briefing-grid">
      <div class="card brief-hero">
        <div class="planet-mini ${m.id}"></div>
        <span class="tag">${m.id === "mars" ? "Planetary science" : "Lunar science"}</span>
        <h2>${esc(m.name)}</h2>
        <p>${esc(m.briefing)}</p>
        <div class="objectives">
          ${m.goals.map((g, i) => `<div class="objective"><span class="label">Goal ${i + 1}</span><b style="font-size:14px">${esc(g)}</b></div>`).join("")}
          <div class="objective"><span class="label">Cruise</span><b style="font-size:14px">${m.cruise.days} days</b></div>
        </div>
      </div>
      <div class="card stack" style="gap:12px">
        <div class="eyebrow">Requirements</div>
        <div class="req-grid">
          <div class="req"><span class="label">Budget</span><b>$${m.budget_m}M</b></div>
          <div class="req"><span class="label">Duration</span><b>${esc(m.duration)}</b></div>
          <div class="req"><span class="label">Mass cap</span><b>${m.mass_cap_kg} kg</b></div>
          <div class="req"><span class="label">Base load</span><b>${m.base_load_w} W</b></div>
        </div>
        <div class="rules">
          <div class="rule"><span class="tag fail">Hard</span><span>Budget, mass, launcher payload and power.</span></div>
          <div class="rule"><span class="tag warn">Landing</span><span>Your lander and your choice of site decide how you touch down.</span></div>
          <div class="rule"><span class="tag ghost">Values</span><span>${esc(m.value_note)}</span></div>
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

export function render(ctx) {
  if (isSurface()) return renderSurface(ctx);
  const { go } = ctx;
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
