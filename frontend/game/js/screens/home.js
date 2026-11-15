/* 01 · Mission Control: choose a mission and start. */
import { state, notify, emptyConfig, resetMission } from "../state.js";
import { el, actions, SVG, toast } from "../ui.js";
import { openProfile, openHistory } from "./account.js";

const MISSIONS = [
  { id: "earth", n: "01", name: "Earth Observation", meta: "LEO · SUN-SYNCHRONOUS", planet: "earth", available: true },
  { id: "moon", n: "02", name: "Lunar Exploration", meta: "CIS-LUNAR", planet: "moon", available: false },
  { id: "mars", n: "03", name: "Mars Exploration", meta: "INTERPLANETARY", planet: "", available: false },
];

export function render({ go }) {
  const selected = MISSIONS.find((m) => m.id === state.missionType) || MISSIONS[0];
  const hasDesign = Boolean(state.config.platform_id || state.config.instrument_ids.length);
  const inFlight = state.mission && state.mission.status === "AWAITING_DECISION";

  const node = el(`<div class="page home">
    <div class="stars"></div>
    <div class="planet ${selected.planet}" id="home-planet"></div>
    <div class="home-content">
      <div class="home-top">
        <div class="home-brand">
          <div class="eyebrow">Space Mission Design Game</div>
          <h1>Mission<br><span>Control</span></h1>
          <p>Design it. Launch it. Keep it alive.</p>
        </div>
        <div class="home-icons">
          <button class="icon-btn" data-action="profile" title="Player profile" aria-label="Player profile">${SVG.profile}</button>
          <button class="icon-btn" data-action="history" title="Mission history" aria-label="Mission history">${SVG.history}</button>
        </div>
      </div>
      <div class="mission-picker" role="radiogroup" aria-label="Mission">
        ${MISSIONS.map((m) => `
          <button class="mission-option ${m.id === selected.id ? "selected" : ""}" role="radio" aria-checked="${m.id === selected.id}"
            data-action="pick" data-id="${m.id}" ${m.available ? "" : "disabled"}>
            <span class="num">${m.n}</span>
            <span><span>${m.name}</span><span class="meta">${m.meta}</span></span>
            ${m.available ? "<i></i>" : '<span class="tag ghost soon">Soon</span>'}
          </button>`).join("")}
      </div>
      <div class="home-bottom">
        <span class="tiny">${state.user ? `Logged in as <b>${state.user.username}</b>` : "Playing as guest"}</span>
        <div class="actions">
          ${inFlight ? '<button class="btn outline lg" data-action="resume">RESUME FLIGHT</button>'
            : hasDesign ? '<button class="btn ghost lg" data-action="continue">CONTINUE DESIGN</button>' : ""}
          <button class="btn lg" data-action="start">START MISSION <span>↗</span></button>
        </div>
      </div>
    </div>
  </div>`);

  return actions(node, {
    pick: (b) => {
      state.missionType = b.dataset.id;
      node.querySelectorAll(".mission-option").forEach((x) => {
        const on = x === b;
        x.classList.toggle("selected", on);
        x.setAttribute("aria-checked", on);
      });
      const m = MISSIONS.find((x) => x.id === b.dataset.id);
      node.querySelector("#home-planet").className = `planet ${m.planet}`;
    },
    start: () => {
      const m = MISSIONS.find((x) => x.id === state.missionType);
      if (!m?.available) { toast("This mission is not available yet."); return; }
      resetMission();
      state.config = emptyConfig(state.scenario.id);
      state.evaluation = null;
      state.reached = { briefing: true, designer: false, review: false, operations: false, results: false };
      notify("new-mission");
      go("briefing");
    },
    continue: () => { resetMission(); go(state.reached.designer ? "designer" : "briefing", { force: true }); },
    resume: () => go("operations"),
    profile: () => openProfile({ onChange: () => go("home", { force: true }) }),
    history: () => openHistory({ go }),
  });
}
