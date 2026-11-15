/* 05 · Launch sequence. The countdown runs while the backend starts the MCAS mission
   (POST /simulation/missions); the animation only finishes once the mission exists. */
import { api } from "../api.js";
import { state, notify, nameOf, rec } from "../state.js";
import { el, actions, esc, sleep, toast } from "../ui.js";

const STAGES = ["Final checks", "Countdown", "Liftoff", "Deployment", "Orbit insertion"];
let root = null;
let alive = false;

export function render({ go }) {
  const ev = state.evaluation;
  const mass = ev?.resources?.total_spacecraft_mass_kg?.value;
  const orbit = rec("orbits", state.config.orbit_id);
  root = el(`<div class="page">
    <div class="head">
      <div><div class="eyebrow">Phase 03 · Launch operations</div><h1 class="title">Go for launch</h1></div>
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
          <div><span>Launcher</span><b>${esc(nameOf(state.config.launch_vehicle_id))}</b></div>
          <div><span>Spacecraft</span><b>${mass != null ? `${mass.toFixed(1)} kg` : "—"}</b></div>
          <div><span>Target orbit</span><b>${esc(orbit?.name || "—")}</b></div>
          <div><span>Status</span><b class="${ev?.feasibility?.status === "CONDITIONAL" ? "st-warn" : "st-ok"}">${esc(ev?.feasibility?.status || "—")}</b></div>
        </div>
        <div class="divider"></div>
        <div class="stages" id="l-stages">${STAGES.map((s) => `<div class="stage"><i></i>${s}</div>`).join("")}</div>
        <button class="btn orange lg block" style="margin-top:auto" data-action="ignite" id="l-go">INITIATE COUNTDOWN ↗</button>
        <button class="btn ghost block" data-action="back" id="l-back">← BACK TO REVIEW</button>
      </div>
    </div>
  </div>`);
  alive = true;
  actions(root, {
    back: () => go("review"),
    ignite: () => ignite(go),
  });
  return root;
}
export function leave() { alive = false; root = null; }

function stage(i, done = false) {
  if (!root) return;
  root.querySelectorAll(".stage").forEach((s, k) => {
    s.classList.toggle("on", k === i && !done);
    s.classList.toggle("done", k < i || (k === i && done));
  });
}

async function ignite(go) {
  const goBtn = root.querySelector("#l-go");
  goBtn.disabled = true;
  root.querySelector("#l-back").disabled = true;
  const t = root.querySelector("#l-t");
  const s = root.querySelector("#l-s");
  const pill = root.querySelector("#l-pill");
  pill.textContent = "SEQUENCE ACTIVE";
  stage(0);
  const name = `Earth Watch · ${nameOf(state.config.platform_id)}`;
  const started = api.startMission(state.config, name).then((m) => ({ m }), (err) => ({ err }));
  await sleep(700);
  stage(1);
  for (let n = 10; n >= 0 && alive; n--) {
    t.textContent = n === 0 ? "T−0" : `T−${n}`;
    s.textContent = n > 3 ? "AUTOMATED SEQUENCE" : n > 0 ? "MAIN ENGINE START" : "LIFTOFF";
    await sleep(320);
  }
  const { m, err } = await started;
  if (!alive) return;
  if (err) {
    t.textContent = "HOLD"; t.classList.remove("go");
    s.textContent = "LAUNCH SCRUBBED";
    pill.textContent = "SCRUB";
    toast(err.message, "error");
    root.querySelector("#l-back").disabled = false;
    return;
  }
  state.mission = m;
  state.shownPeriod = 0;
  state.reached.operations = true;
  notify("launched");
  stage(2);
  t.textContent = "LIFTOFF"; t.classList.add("go");
  s.textContent = nameOf(state.config.launch_vehicle_id).toUpperCase();
  root.querySelector("#l-trail").classList.add("fly");
  root.querySelector("#l-glow").classList.add("on");
  await sleep(1500); if (!alive) return;
  stage(3); s.textContent = "SPACECRAFT SEPARATION";
  await sleep(1000); if (!alive) return;
  stage(4); s.textContent = "ORBIT INSERTION";
  await sleep(900); if (!alive) return;
  stage(4, true);
  if (m.status === "NOT_LAUNCHED") {
    toast("The engine refused the launch: a hard constraint fails.", "error");
    go("review");
    return;
  }
  go("operations");
}
