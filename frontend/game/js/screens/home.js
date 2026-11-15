/* 01 · Mission Control: choose a mission and start.
   Background video per mission: media/home/earth.mp4, moon.mp4, mars.mp4.
   If a video is missing the CSS planet stays visible instead. */
import { state, notify, emptyConfig, resetMission } from "../state.js";
import { el, actions, SVG, toast } from "../ui.js";
import { openProfile, openHistory } from "./account.js";
import { loadCatalog, resetSurface } from "./surface.js";
import * as sound from "../sound.js";

const MISSIONS = [
  { id: "earth", n: "01", name: "Earth Observation", meta: "LEO · SUN-SYNCHRONOUS", planet: "earth" },
  { id: "moon", n: "02", name: "Lunar Exploration", meta: "SOUTH POLE LANDER", planet: "moon" },
  { id: "mars", n: "03", name: "Mars Exploration", meta: "ROVER · JEZERO CRATER", planet: "" },
];

const videoSources = (id) => `<source src="media/home/${id}.mp4" type="video/mp4">`;

const SPEAKER_ON = '<svg viewBox="0 0 24 24"><path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M16 9a4 4 0 0 1 0 6M18.5 6.5a8 8 0 0 1 0 11"/></svg>';
const SPEAKER_OFF = '<svg viewBox="0 0 24 24"><path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M16 9l5 6M21 9l-5 6"/></svg>';

let offMute = null;

export function render({ go }) {
  const selected = MISSIONS.find((m) => m.id === state.missionType) || MISSIONS[0];
  const designed = selected.id === "earth"
    ? Boolean(state.config.platform_id || state.config.instrument_ids.length)
    : Boolean(state.surface.catalog?.mission.id === selected.id && Object.values(state.surface.selection).some((v) => (Array.isArray(v) ? v.length : v)));
  const inFlight = selected.id === "earth" && state.mission && state.mission.status === "AWAITING_DECISION";

  const node = el(`<div class="page home">
    <div class="stars"></div>
    <div class="planet ${selected.planet}" id="home-planet"></div>
    <video class="bg-video" id="home-video" autoplay muted loop playsinline preload="auto">${videoSources(selected.id)}</video>
    <div class="bg-shade"></div>
    <div class="home-content">
      <div class="home-top">
        <div class="home-brand">
          <img class="home-icon" src="brand/sq-icon.png" alt="">
          <img class="home-wordmark" src="brand/starquest-wordmark.png" alt="StarQuest — Earth observation simulation">
          <p>Design it. Launch it. Keep it alive.</p>
        </div>
        <div class="home-icons">
          <button class="icon-btn" data-action="sound" id="home-sound" title="Sound (M)" aria-label="Sound on or off">${sound.isMuted() ? SPEAKER_OFF : SPEAKER_ON}</button>
          <button class="icon-btn" data-action="profile" title="Player profile" aria-label="Player profile">${SVG.profile}</button>
          <button class="icon-btn" data-action="history" title="Saved missions" aria-label="Saved missions">${SVG.history}</button>
        </div>
      </div>
      <div class="mission-picker" role="radiogroup" aria-label="Mission">
        ${MISSIONS.map((m) => `
          <button class="mission-option ${m.id === selected.id ? "selected" : ""}" role="radio" aria-checked="${m.id === selected.id}" data-action="pick" data-id="${m.id}">
            <span class="num">${m.n}</span>
            <span><span>${m.name}</span><span class="meta">${m.meta}</span></span>
            <i></i>
          </button>`).join("")}
      </div>
      <div class="home-bottom">
        <span class="tiny">${state.user ? `Logged in as <b>${state.user.username}</b>` : "Playing as guest"} · M = sound</span>
        <div class="actions">
          ${inFlight ? '<button class="btn outline lg" data-action="resume">RESUME FLIGHT</button>'
            : designed ? '<button class="btn ghost lg" data-action="continue">CONTINUE DESIGN</button>' : ""}
          <button class="btn lg" data-action="start" id="home-start">START MISSION <span>↗</span></button>
        </div>
      </div>
    </div>
  </div>`);

  const video = node.querySelector("#home-video");
  const watch = () => {
    video.classList.remove("ready");
    video.addEventListener("playing", () => video.classList.add("ready"), { once: true });
  };
  watch();

  return actions(node, {
    pick: (b) => {
      if (b.dataset.id === state.missionType) return;
      state.missionType = b.dataset.id;
      sound.blip("select");
      notify("mission-type");
      node.querySelectorAll(".mission-option").forEach((x) => {
        const on = x === b;
        x.classList.toggle("selected", on);
        x.setAttribute("aria-checked", on);
      });
      const m = MISSIONS.find((x) => x.id === b.dataset.id);
      node.querySelector("#home-planet").className = `planet ${m.planet}`;
      video.classList.remove("ready");
      setTimeout(() => {
        video.innerHTML = videoSources(m.id);
        watch();
        video.load();
        video.play().catch(() => {});
      }, 350);
      node.querySelector(".home-bottom .actions [data-action=continue], .home-bottom .actions [data-action=resume]")?.remove();
    },
    start: async (b) => {
      resetMission();
      state.evaluation = null;
      state.debrief = null;
      state.reached = { briefing: true, designer: false, review: false, operations: false, results: false };
      if (state.missionType === "earth") {
        state.config = emptyConfig(state.scenario.id);
      } else {
        b.disabled = true;
        try { await loadCatalog(state.missionType); } catch (err) { toast(err.message, "error"); b.disabled = false; return; }
        resetSurface();
      }
      notify("new-mission");
      go("briefing");
    },
    continue: async () => {
      resetMission();
      if (state.missionType !== "earth") await loadCatalog(state.missionType);
      go(state.reached.designer ? "designer" : "briefing", { force: true });
    },
    resume: () => go("operations"),
    sound: () => sound.setMuted(!sound.isMuted()),
    profile: () => openProfile({ onChange: () => go("home", { force: true }) }),
    history: () => openHistory({ go }),
  });
}

export function mounted(node) {
  const btn = node.querySelector("#home-sound");
  offMute = sound.onMuteChange((m) => { btn.innerHTML = m ? SPEAKER_OFF : SPEAKER_ON; });
}
export function leave() { offMute?.(); offMute = null; }
