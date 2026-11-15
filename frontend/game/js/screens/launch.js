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
          <div><span>Launch review</span><b class="${{ GO: "st-ok", RISKY: "st-warn", NO_GO: "st-fail" }[ev?.launch_assessment?.status] || ""}">${esc((ev?.launch_assessment?.status || "—").replace("_", " "))}</b></div>
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
  actions(root, {
    back: () => go("review"),
    ignite: () => ignite(go),
    report: () => go("results", { force: true }),
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
  root.querySelector("#l-pill").textContent = "SEQUENCE ACTIVE";
  const pill = root.querySelector("#l-pill");
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
  if (m.status === "NOT_LAUNCHED") {
    toast("Launch refused: the design is catastrophically out of limits.", "error");
    state.mission = null;
    go("review");
    return;
  }
  const la = m.state.launch_assessment;
  const loss = la?.total_loss;
  const trail = root.querySelector("#l-trail");
  stage(2);
  t.textContent = "LIFTOFF"; t.classList.add("go");
  s.textContent = nameOf(state.config.launch_vehicle_id).toUpperCase();
  trail.classList.add("fly");
  root.querySelector("#l-glow").classList.add("on");

  if (loss) {
    const at = { launch: 2, orbit_insertion: 4, commissioning: 4 }[loss.stage];
    if (at > 2) { await sleep(1400); if (!alive) return; stage(3); s.textContent = "SPACECRAFT SEPARATION"; await sleep(900); if (!alive) return; stage(4); }
    if (loss.stage === "commissioning") { stage(4, true); s.textContent = "ACQUIRING SIGNAL…"; await sleep(1600); if (!alive) return; }
    else await sleep(900);
    if (!alive) return;
    trail.classList.add("lost");
    root.querySelectorAll(".stage")[at].classList.add("fail");
    t.classList.remove("go"); t.classList.add("lost");
    t.textContent = { launch: "VEHICLE LOST", orbit_insertion: "WRONG ORBIT", commissioning: "NO SIGNAL" }[loss.stage];
    s.textContent = "MISSION LOST";
    pill.textContent = "FAILURE";
    root.querySelector("#l-why").textContent = loss.reason;
    root.querySelector("#l-why").style.display = "";
    state.debrief = m.debrief;
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
  stage(4); s.textContent = "ORBIT INSERTION";
  await sleep(900); if (!alive) return;
  stage(4, true);
  if (la && la.status === "RISKY") {
    root.querySelectorAll(".stage")[4].classList.add("warn");
    pill.textContent = "DAMAGED";
    s.textContent = "IN ORBIT · DAMAGE REPORTED";
    root.querySelector("#l-why").textContent = la.risks.map((r) => r.consequence).join(" ");
    root.querySelector("#l-why").style.display = "";
    await sleep(2600); if (!alive) return;
  }
  go("operations");
}
