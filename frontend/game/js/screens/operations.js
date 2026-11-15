/* 06 · Mission operations. Plays back the engine's period-by-period timeline and stops on
   each anomaly that needs a player decision (MCAS). Decisions are sent to
   POST /simulation/missions/{id}/decisions; the engine replays the mission and returns
   the next state. Nothing here invents a consequence. */
import { api } from "../api.js";
import { state, notify, nameOf, anyRec } from "../state.js";
import { el, actions, esc, openModal, sleep, toast } from "../ui.js";

let root = null;
let alive = false;
let speed = 1;
let playing = false;

const SYSTEM_LABEL = { communications: "Communications", power: "Power", payload: "Payload", data: "Data handling", adcs: "Attitude control", pointing: "Pointing" };

export function render({ go }) {
  const st = state.mission.state;
  root = el(`<div class="page">
    <div class="head">
      <div><div class="eyebrow">Phase 04 · Mission operations</div><h1 class="title">Mission control</h1></div>
      <div class="row" style="gap:14px">
        <div class="speed" id="o-speed">${[1, 2, 4].map((s) => `<button data-action="speed" data-s="${s}" class="${s === speed ? "active" : ""}">${s}×</button>`).join("")}</div>
        <span class="status-big" id="o-status"><i></i> NOMINAL</span>
      </div>
    </div>
    <div class="ops">
      <div class="card stack" style="gap:12px">
        <div><span class="label">Mission day</span><div class="day" id="o-day">000</div><span class="tiny" id="o-dayof">of ${Math.round(state.scenario.parameters.mission_duration_days)}</span></div>
        <div class="divider" style="margin:0"></div>
        <div class="meter"><div class="row"><span>Observations</span><b id="o-obs">0 / ${st.total_periods}</b></div><div class="bar"><i id="o-obsbar" style="width:0"></i></div></div>
        <div class="kv">
          <div><span>Period</span><b id="o-period">—</b></div>
          <div><span>Phase</span><b id="o-phase">Commissioning</b></div>
          <div><span>Data backlog</span><b id="o-backlog">—</b></div>
          <div><span>Anomalies</span><b id="o-anoms">0</b></div>
          <div><span>Decisions</span><b id="o-dec">0</b></div>
        </div>
        <div class="divider" style="margin:0"></div>
        <div class="kv">
          <div><span>Main radio</span><b class="ellipsis" style="max-width:60%">${esc(nameOf(state.config.communication_system_ids.at(-1)))}</b></div>
          <div><span>Payload</span><b class="ellipsis" style="max-width:60%">${esc(state.config.instrument_ids.map(nameOf).join(", "))}</b></div>
        </div>
      </div>
      <div class="center">
        <div class="viewport3d" id="viewport-operations" data-view="mission" aria-label="Mission 3D view"></div>
        <div class="phases"><span id="ph-l">Launch</span><span id="ph-c">Commissioning</span><span id="ph-s">Science operations</span><span id="ph-d">Complete</span></div>
        <div class="timeline" id="o-tl" style="--n:${st.total_periods}">${Array.from({ length: st.total_periods }, (_, i) => `<div class="tl-cell" data-p="${i + 1}">${String(i + 1).padStart(2, "0")}</div>`).join("")}</div>
      </div>
      <div class="card stack">
        <div class="row"><div class="eyebrow">Mission log</div><span class="tag ghost">live</span></div>
        <div class="log" id="o-log"></div>
        <button class="btn block" id="o-next" style="display:none" data-action="results">MISSION REPORT →</button>
      </div>
    </div>
  </div>`);
  alive = true;
  actions(root, {
    speed: (b) => {
      speed = Number(b.dataset.s);
      root.querySelectorAll("#o-speed button").forEach((x) => x.classList.toggle("active", x === b));
    },
    results: () => { state.debrief = state.mission.debrief; go("results", { force: true }); },
  });
  return root;
}

export function mounted() {
  const st = state.mission.state;
  // Static history first (launch, deployment, commissioning), then replay what was already shown.
  st.mission_history.filter((h) => h.period == null && h.phase !== "mission_completion").forEach((h) => log("—", h.message, "phase"));
  for (let p = 1; p <= state.shownPeriod; p++) paintPeriod(p, false);
  play();
}
export function leave() { alive = false; root = null; }

function log(p, message, kind = "") {
  if (!root) return;
  const box = root.querySelector("#o-log");
  box.prepend(el(`<div class="log-item ${kind}"><span class="p">${esc(p)}</span><span>${esc(message)}</span></div>`));
  while (box.children.length > 30) box.lastElementChild.remove();
}

function anomalyName(st, id) {
  const all = [...(st.resolved_anomalies || []), ...(st.active_anomalies || [])];
  return all.find((a) => a.anomaly_id === id)?.name || id.replace(/-p\d+$/, "").replaceAll("_", " ");
}

function paintPeriod(p, withLog = true) {
  const st = state.mission.state;
  const t = st.timeline.find((x) => x.period === p);
  if (!t || !root) return;
  const cell = root.querySelector(`.tl-cell[data-p="${p}"]`);
  cell.classList.remove("now", "lost", "done", "partial");
  cell.classList.add(t.science_credit >= 0.999 ? "done" : t.science_credit > 0 ? "partial" : "lost");
  if (t.event_types.length || t.anomaly_ids.length) {
    cell.insertAdjacentHTML("beforeend", `<span class="ev ${t.anomaly_ids.length ? "anom" : ""}"></span>`);
  }
  const next = root.querySelector(`.tl-cell[data-p="${p + 1}"]`);
  if (next) next.classList.add("now");

  const done = st.timeline.filter((x) => x.period <= p);
  const credit = done.reduce((s, x) => s + (x.science_credit || 0), 0);
  root.querySelector("#o-day").textContent = String(Math.round(t.elapsed_days)).padStart(3, "0");
  root.querySelector("#o-period").textContent = `${p} / ${st.total_periods}`;
  root.querySelector("#o-phase").textContent = "Science ops";
  root.querySelector("#o-obs").textContent = `${+credit.toFixed(1)} / ${st.total_periods}`;
  root.querySelector("#o-obsbar").style.width = `${(credit / st.total_periods) * 100}%`;
  root.querySelector("#o-backlog").textContent = t.backlog_bits == null ? "n/a" : `${(t.backlog_bits / 8e9).toFixed(1)} GB`;
  const anoms = st.timeline.filter((x) => x.period <= p).reduce((s, x) => s + x.anomaly_ids.length, 0);
  root.querySelector("#o-anoms").textContent = anoms;
  root.querySelector("#o-dec").textContent = (st.decision_history || []).filter((d) => d.period <= p).length;
  phase("s");

  if (!withLog) return;
  const pp = `P${String(p).padStart(2, "0")}`;
  const consequences = st.mission_history.filter((h) => h.period === p);
  if (t.anomaly_ids.length) {
    t.anomaly_ids.forEach((id) => log(pp, `Anomaly · ${anomalyName(st, id)}`, "anomaly"));
    consequences.forEach((h) => log(pp, h.message.split(". ").slice(0, 2).join(". "), "event"));
  } else if (t.event_types.length) {
    log(pp, `${t.event_types.map((e) => e.replaceAll("_", " ")).join(", ")} — no effect on this design`, "event");
  } else {
    log(pp, t.science_observed ? "Observations nominal" : "No observation this period", t.science_observed ? "science" : "anomaly");
  }
}

function phase(k) {
  if (!root) return;
  ["l", "c", "s", "d"].forEach((x) => root.querySelector(`#ph-${x}`).classList.toggle("on", x === k));
}

function setStatus(kind) {
  if (!root) return;
  const s = root.querySelector("#o-status");
  s.className = `status-big ${kind === "alert" ? "alert" : kind === "done" ? "done" : ""}`;
  s.innerHTML = `<i></i> ${kind === "alert" ? "ANOMALY" : kind === "done" ? "MISSION COMPLETE" : "NOMINAL"}`;
}

async function play() {
  if (playing) return;
  playing = true;
  try {
    const st = state.mission.state;
    if (state.shownPeriod === 0) {
      phase("c");
      root?.querySelector(".tl-cell[data-p='1']")?.classList.add("now");
      await sleep(700 / speed);
    }
    const target = st.timeline.length ? Math.max(...st.timeline.map((t) => t.period)) : 0;
    while (alive && state.shownPeriod < target) {
      state.shownPeriod += 1;
      paintPeriod(state.shownPeriod);
      notify("period");
      await sleep(900 / speed);
    }
    if (!alive) return;
    if (st.status === "AWAITING_DECISION" && st.pending_decision) {
      setStatus("alert");
      root.querySelector(".tl-cell.now")?.classList.add("lost");
      await sleep(350);
      if (alive) openDecision(st.pending_decision);
    } else if (st.status === "COMPLETED") {
      state.debrief = state.mission.debrief;
      state.reached.results = true;
      notify("completed");
      phase("d");
      setStatus("done");
      st.mission_history.filter((h) => h.phase === "mission_completion").forEach((h) => log("END", h.message.split(". ").slice(0, 1).join(". "), "phase"));
      root.querySelector("#o-next").style.display = "";
      root.querySelector("#o-dayof").textContent = `outcome ${st.outcome?.replaceAll("_", " ").toLowerCase() || ""}`;
    }
  } finally { playing = false; }
}

function openDecision(pd) {
  let choice = (pd.responses.find((r) => r.is_default && r.available) || pd.responses.find((r) => r.available))?.id;
  const letters = "ABCDEF";
  const content = el(`<div class="stack" style="gap:14px">
    <div class="alert-head"><span class="tag fail">⚠ ${esc(pd.category === "engineering" ? "Engineering anomaly" : "External event")} · ${esc(SYSTEM_LABEL[pd.affected_system] || pd.affected_system)}</span>
      <span class="tiny mono">DAY ${String(Math.round(pd.elapsed_days)).padStart(3, "0")} · P${String(pd.period).padStart(2, "0")}</span></div>
    <h2 class="event-title">${esc(pd.name)}</h2>
    <div class="event-grid">
      <div class="stack">
        <p class="muted">${esc(pd.what_happened)}</p>
        <div class="label" style="margin-top:4px">Choose your response</div>
        <div class="choices">${pd.responses.map((r, i) => `
          <button class="choice ${r.id === choice ? "selected" : ""}" data-id="${esc(r.id)}" ${r.available ? "" : "disabled"}>
            <div class="row"><b>${letters[i]} · ${esc(r.label)}</b>${r.is_default ? '<span class="tag ghost">default</span>' : ""}</div>
            <p>${esc(r.available ? r.trade_off : r.unavailable_reason)}</p>
          </button>`).join("")}</div>
      </div>
      <div class="why">
        <div><div class="label">Symptom</div><span>${esc(pd.symptom)}</span></div>
        <div><div class="label">Your design</div><span class="clamp3" title="${esc(pd.contributing_design_decision)}">${esc(prettyIds(pd.contributing_design_decision))}</span></div>
        <div><div class="label">Recovery</div><span>${esc(pd.recovery || "—")}</span></div>
      </div>
    </div>
    <button class="btn lg block" id="ev-confirm">CONFIRM DECISION</button>
  </div>`);
  const { close } = openModal(content, { wide: true, dismissible: false });
  content.querySelectorAll(".choice").forEach((b) => b.addEventListener("click", () => {
    choice = b.dataset.id;
    content.querySelectorAll(".choice").forEach((x) => x.classList.toggle("selected", x === b));
  }));
  const confirm = content.querySelector("#ev-confirm");
  confirm.addEventListener("click", async () => {
    if (!choice) return;
    confirm.disabled = true;
    confirm.innerHTML = '<span class="spinner"></span> TRANSMITTING';
    try {
      const view = await api.decide(state.mission.mission_id, pd.anomaly_id, choice);
      close();
      state.mission = view;
      // The decided period is now part of the timeline; replay from where we stopped.
      setStatus("ok");
      notify("decision");
      play();
    } catch (err) {
      confirm.disabled = false;
      confirm.textContent = "CONFIRM DECISION";
      toast(err.message, "error");
    }
  });
}

/* Replace component ids in engine text with their names. */
export function prettyIds(text) {
  return String(text || "").replace(/\b[a-z][a-z0-9_]*[0-9_][a-z0-9_]*\b/g, (m) => {
    const r = anyRec(m);
    return r ? r.name : m;
  });
}

