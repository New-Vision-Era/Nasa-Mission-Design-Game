/* 05 · Launch sequence, for every mission type. The countdown follows the countdown recording
   (one number every COUNTDOWN_STEP_MS) while the backend starts the mission:
   Earth -> POST /simulation/missions, Mars/Moon -> POST /surface/{mission}/fly.
   A risky launch can end here (ascent or orbit-insertion failure) or report damage. */
import { api } from "../api.js";
import { state, notify, nameOf as earthName, rec as earthRec, isSurface } from "../state.js";
import { el, actions, esc, sleep, toast } from "../ui.js";
import { nameOf as surfName } from "./surface.js";
import * as sound from "../sound.js";

const STAGES = ["Final checks", "Countdown", "Liftoff", "Deployment", "Orbit insertion"];
let root = null;
let alive = false;

/* What the launch screen needs, whatever the mission. */
function view() {
  if (isSurface()) {
    const s = state.surface;
    const ev = s.evaluation;
    return {
      launcher: surfName("launch", s.selection.launch),
      mass: ev?.resources?.mass_kg,
      target: s.catalog.mission.cruise.title.replace(" cruise", "") + " transfer",
      verdict: ev?.launch_assessment?.status,
      risks: ev?.launch_assessment?.risks || [],
      start: () => api.surfaceFly(state.missionType, s.selection, {}),
      accept: (res) => { s.flight = res; return { status: res.status, loss: res.launch_assessment?.total_loss, debrief: res.debrief }; },
    };
  }
  const ev = state.evaluation;
  return {
    launcher: earthName(state.config.launch_vehicle_id),
    mass: ev?.resources?.total_spacecraft_mass_kg?.value,
    target: earthRec("orbits", state.config.orbit_id)?.name || "—",
    verdict: ev?.launch_assessment?.status,
    risks: ev?.launch_assessment?.risks || [],
    start: () => api.startMission(state.config, `Earth Watch · ${earthName(state.config.platform_id)}`),
    accept: (m) => {
      state.mission = m;
      state.shownPeriod = 0;
      return { status: m.status, loss: m.state.launch_assessment?.total_loss, debrief: m.debrief };
    },
  };
}

export function render({ go }) {
  const v = view();
  root = el(`<div class="page">
    <div class="head">
      <div class="head-title"><div class="eyebrow">Phase 03 · Launch operations</div><h1 class="title">Go for launch</h1></div>
      <span class="pill cyan" id="l-pill">AWAITING COMMAND</span>
    </div>
    <div class="launch">
      <div class="card pad">
        <div class="stars" style="opacity:.35"></div>
        <div class="glow" id="l-glow"></div><div class="trail" id="l-trail"></div>
        <div class="countdown"><div class="t" id="l-t">T−10</div><div class="s" id="l-s">SYSTEMS READY · STANDING BY</div></div>
      </div>
      <div class="card stack" style="gap:14px">
        <div class="kv">
          <div><span>Launcher</span><b>${esc(v.launcher)}</b></div>
          <div><span>Spacecraft</span><b>${v.mass != null ? `${(+v.mass).toFixed(1)} kg` : "—"}</b></div>
          <div><span>Target</span><b>${esc(v.target)}</b></div>
          <div><span>Launch review</span><b class="${{ GO: "st-ok", RISKY: "st-warn", NO_GO: "st-fail" }[v.verdict] || ""}">${esc((v.verdict || "—").replace("_", " "))}</b></div>
        </div>
        <div class="divider"></div>
        <p class="tiny st-warn" id="l-why" style="display:none"></p>
        <div class="stages" id="l-stages">${STAGES.map((s) => `<div class="stage"><i></i>${s}</div>`).join("")}</div>
        <button class="btn orange lg block" style="margin-top:auto" data-action="ignite" id="l-go">INITIATE COUNTDOWN ↗</button>
        <button class="btn ghost block" data-action="back" id="l-back">← BACK TO REVIEW</button>
      </div>
    </div>
  </div>`);
  alive = true;
  return actions(root, {
    back: () => go("review"),
    ignite: () => ignite(go),
    report: () => go("results", { force: true }),
  });
}
export function leave() {
  alive = false;
  root = null;
  sound.stop("countdown", 400);
  sound.stop("launch", 1500);
}

function stage(i, done = false) {
  if (!root) return;
  root.querySelectorAll(".stage").forEach((s, k) => {
    s.classList.toggle("on", k === i && !done);
    s.classList.toggle("done", k < i || (k === i && done));
  });
}

async function ignite(go) {
  const v = view();
  root.querySelector("#l-go").disabled = true;
  root.querySelector("#l-back").disabled = true;
  const t = root.querySelector("#l-t");
  const s = root.querySelector("#l-s");
  const pill = root.querySelector("#l-pill");
  const why = root.querySelector("#l-why");
  pill.textContent = "SEQUENCE ACTIVE";
  stage(0);
  const started = v.start().then((m) => ({ m }), (err) => ({ err }));
  await sleep(600);
  if (!alive) return;
  stage(1);
  sound.ambient(false);
  sound.play("countdown", { volume: 0.9 });
  for (let n = 10; n >= 1 && alive; n--) {
    t.textContent = `T−${n}`;
    s.textContent = n > 3 ? "AUTOMATED SEQUENCE" : "MAIN ENGINE START";
    await sleep(sound.COUNTDOWN_STEP_MS);
  }
  if (!alive) return;
  const { m, err } = await started;
  if (!alive) return;
  if (err) {
    sound.stop("countdown", 300);
    t.textContent = "HOLD";
    s.textContent = "LAUNCH SCRUBBED";
    pill.textContent = "SCRUB";
    sound.blip("error");
    toast(err.message, "error");
    root.querySelector("#l-back").disabled = false;
    sound.ambient(true);
    return;
  }
  const r = v.accept(m);
  state.reached.operations = true;
  notify("launched");
  if (r.status === "NOT_LAUNCHED") {
    sound.stop("countdown", 300);
    toast("Launch refused: the design is catastrophically out of limits.", "error");
    state.mission = null;
    state.surface.flight = null;
    go("review");
    return;
  }

  const trail = root.querySelector("#l-trail");
  t.textContent = "T−0";
  stage(2);
  sound.play("launch", { volume: 0.85 });
  await sleep(500);
  if (!alive) return;
  t.textContent = "LIFTOFF"; t.classList.add("go");
  s.textContent = v.launcher.toUpperCase();
  trail.classList.add("fly");
  root.querySelector("#l-glow").classList.add("on");

  const loss = r.loss;
  if (loss && ["launch", "orbit_insertion", "commissioning"].includes(loss.stage)) {
    const at = { launch: 2, orbit_insertion: 4, commissioning: 4 }[loss.stage];
    if (at > 2) { await sleep(1400); if (!alive) return; stage(3); s.textContent = "SPACECRAFT SEPARATION"; await sleep(900); if (!alive) return; stage(4); }
    if (loss.stage === "commissioning") { stage(4, true); s.textContent = "ACQUIRING SIGNAL…"; await sleep(1600); if (!alive) return; }
    else await sleep(900);
    if (!alive) return;
    sound.stop("launch", 300);
    sound.play(loss.stage === "commissioning" ? "alarm" : "explosion", { volume: 0.9 });
    trail.classList.add("lost");
    root.querySelectorAll(".stage")[at].classList.add("fail");
    t.classList.remove("go"); t.classList.add("lost");
    t.textContent = { launch: "VEHICLE LOST", orbit_insertion: "WRONG ORBIT", commissioning: "NO SIGNAL" }[loss.stage];
    s.textContent = "MISSION LOST";
    pill.textContent = "FAILURE";
    why.textContent = loss.reason;
    why.style.display = "";
    state.debrief = r.debrief;
    state.reached.results = true;
    notify("lost");
    const btn = root.querySelector("#l-go");
    btn.textContent = "MISSION REPORT →";
    btn.disabled = false;
    btn.dataset.action = "report";
    return;
  }

  await sleep(1500); if (!alive) return;
  stage(3); s.textContent = "SPACECRAFT SEPARATION";
  await sleep(1000); if (!alive) return;
  stage(4); s.textContent = isSurface() ? "TRANSFER BURN" : "ORBIT INSERTION";
  await sleep(900); if (!alive) return;
  stage(4, true);
  if (v.verdict === "RISKY") {
    root.querySelectorAll(".stage")[4].classList.add("warn");
    pill.textContent = "DAMAGED";
    s.textContent = "ON COURSE · DAMAGE REPORTED";
    why.textContent = v.risks.map((x) => x.consequence).join(" ");
    why.style.display = "";
    sound.blip("error");
    await sleep(2600); if (!alive) return;
  }
  sound.stop("launch", 2000);
  sound.ambient(true);
  go("operations");
}
