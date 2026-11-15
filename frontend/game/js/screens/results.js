/* 07 · Mission report: score and outcome straight from the engine's debrief. */
import { state } from "../state.js";
import { el, actions, esc, pct } from "../ui.js";

const OUTCOME_TEXT = { SUCCESS: "Mission successful", PARTIAL_SUCCESS: "Partial success", FAILURE: "Mission failed", NOT_LAUNCHED: "Not launched" };
const CAT_SHORT = { science: "Science", objectives: "Objectives", reliability: "Reliability", efficiency: "Efficiency" };

export function render({ go }) {
  const d = state.debrief;
  const score = d.score;
  const total = score.total ?? 0;
  const ref = d.reference_without_anomalies;
  const prev = state.previous;
  const C = 2 * Math.PI * 52;
  const node = el(`<div class="page">
    <div class="head">
      <div><div class="eyebrow">Phase 05 · Mission report</div><h1 class="title">${OUTCOME_TEXT[d.outcome] || d.outcome}</h1></div>
      ${prev ? `<span class="pill ${total >= prev.score ? "ok" : "bad"}"><i class="dot"></i> ${total >= prev.score ? "+" : ""}${(total - prev.score).toFixed(1)} VS LAST ATTEMPT</span>` : ""}
    </div>
    <div class="results">
      <div class="card score-card">
        <div class="ring">
          <svg viewBox="0 0 120 120"><circle class="bg" cx="60" cy="60" r="52"/><circle class="fg" id="ring" cx="60" cy="60" r="52" stroke-dasharray="${C}" stroke-dashoffset="${C}"/></svg>
          <div class="val"><b id="score-n">0</b><span>/ ${score.max}</span></div>
        </div>
        <div class="outcome ${d.outcome}">${(d.outcome || "").replaceAll("_", " ")}</div>
        <span class="tiny">${score.completeness < 1 ? `${pct(score.completeness)} of the score could be evaluated` : "Fully evaluated score"}</span>
      </div>
      <div class="res-right">
        <div class="cats">${score.categories.map((c) => `
          <div class="cat"><span class="label">${CAT_SHORT[c.id] || esc(c.title)}</span>
            <b>${c.points == null ? "—" : +c.points.toFixed(1)}<small> / ${c.weight}</small></b>
            <div class="bar ${!c.evaluable ? "unknown" : c.score_fraction >= .8 ? "ok" : c.score_fraction >= .5 ? "warn" : "fail"}"><i style="width:${(c.score_fraction || 0) * 100}%"></i></div></div>`).join("")}
        </div>
        <div class="facts">
          <div class="fact"><span class="label">Objectives</span><b>${pct(d.mission.objective_fraction)}</b></div>
          <div class="fact"><span class="label">Anomalies</span><b>${d.anomalies.length}</b></div>
          <div class="fact"><span class="label">Your decisions</span><b>${d.decisions.filter((x) => x.decided_by === "player").length}</b></div>
          <div class="fact" title="${esc(ref?.note || "")}"><span class="label">Without anomalies</span><b>${ref ? +ref.score_total.toFixed(1) : "—"}</b></div>
        </div>
        <div class="card stack">
          <div class="eyebrow">Objectives</div>
          <div class="obj-list">${d.objectives.map((o) => `
            <div class="meter" title="${esc(o.message)}"><div class="row"><span>${esc(o.title)}</span><b>${o.achieved_fraction == null ? "not evaluated" : pct(o.achieved_fraction)}</b></div>
              <div class="bar ${o.achieved_fraction == null ? "unknown" : o.achieved_fraction >= .8 ? "ok" : o.achieved_fraction >= .4 ? "warn" : "fail"}"><i style="width:${(o.achieved_fraction || 0) * 100}%"></i></div>
              <span class="tiny clamp2">${esc(o.message)}</span></div>`).join("")}
          </div>
        </div>
      </div>
    </div>
    <div class="footer">
      <button class="btn ghost" data-action="home">MISSION CONTROL</button>
      <button class="btn" data-action="debrief">ENGINEERING DEBRIEF →</button>
    </div>
  </div>`);
  return actions(node, { home: () => go("home"), debrief: () => go("debrief") });
}

export function mounted(node) {
  const total = state.debrief.score.total ?? 0;
  const C = 2 * Math.PI * 52;
  requestAnimationFrame(() => { node.querySelector("#ring").style.strokeDashoffset = C * (1 - total / 100); });
  const n = node.querySelector("#score-n");
  const t0 = performance.now();
  const tick = (t) => {
    const k = Math.min(1, (t - t0) / 1300);
    n.textContent = Math.round(total * (1 - Math.pow(1 - k, 3)));
    if (k < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}
