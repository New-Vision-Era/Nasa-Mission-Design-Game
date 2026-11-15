/* 08 · Engineering debrief: what worked, what to fix, and a concrete next design
   from the engine's optimizer (POST /simulation/recommend). */
import { api } from "../api.js";
import { state, notify, nameOf, resetMission } from "../state.js";
import { el, actions, esc } from "../ui.js";
import { STEP_TO_SLOT } from "../catalog.js";
import { focusSlot, evaluateNow } from "./designer.js";
import { prettyIds } from "./operations.js";

const CAT_SHORT = { science: "Science", objectives: "Objectives", reliability: "Reliability", efficiency: "Efficiency" };
const CAT_STEP = { science: "instruments", objectives: "instruments", efficiency: "launch_vehicle", reliability: "adcs" };
const SLOT_FIELDS = [
  ["platform_id", "Platform"], ["instrument_ids", "Science"], ["communication_system_ids", "Comms"],
  ["adcs_system_id", "Attitude"], ["propulsion_system_id", "Propulsion"], ["orbit_id", "Orbit"], ["launch_vehicle_id", "Launcher"],
];

let root = null;
let suggestion = null;

const firstSentence = (t) => prettyIds(String(t || "").split(/(?<=\.)\s/)[0]);

export function render({ go }) {
  const d = state.debrief;
  const good = [
    ...d.score.categories.filter((c) => c.evaluable && c.score_fraction >= 0.9).map((c) => ({ text: `${CAT_SHORT[c.id] || c.title}: ${+c.points.toFixed(1)} / ${c.weight}` })),
    ...d.explanations.filter((e) => e.kind === "strength").map((e) => ({ text: firstSentence(e.message) })),
    ...d.objectives.filter((o) => (o.achieved_fraction ?? 0) >= 0.8).map((o) => ({ text: firstSentence(o.message) })),
  ].slice(0, 5);

  const seen = new Set();
  const improve = [
    ...d.explanations.filter((e) => ["problem", "weakness", "warning"].includes(e.kind)),
    ...d.score.categories.filter((c) => c.evaluable && c.score_fraction < 0.75).map((c) => ({ message: `${CAT_SHORT[c.id]}: ${c.reasons.find((r) => !/100%/.test(r)) || c.reasons[0] || "below target"}`, related_step: CAT_STEP[c.id] || null })),
    ...(d.debrief.engineering_weaknesses || []).map((w) => ({ message: w, related_step: (d.risk_assessment?.risks || []).find((r) => w.startsWith(r.title))?.related_step || null })),
    ...d.explanations.filter((e) => e.kind === "unknown" && e.constraint_id),
  ].filter((e) => { const k = firstSentence(e.message); if (seen.has(k)) return false; seen.add(k); return true; }).slice(0, 5);

  const decisions = (d.debrief.player_decisions || []).map((p, i) => ({ p, c: (d.debrief.mission_consequences || [])[i] })).slice(0, 4);

  root = el(`<div class="page">
    <div class="head">
      <div><div class="eyebrow">Phase 05 · Learn &amp; improve</div><h1 class="title">Engineering debrief</h1></div>
      <span class="pill cyan">SCORE ${Math.round(d.score.total ?? 0)} · ${(d.outcome || "").replaceAll("_", " ")}</span>
    </div>
    <div class="debrief">
      <div class="card">
        <div class="eyebrow" style="color:var(--ok)">What went well</div>
        ${good.map((g) => `<div class="lesson"><span class="m st-ok">✓</span><span>${esc(g.text)}</span></div>`).join("") || '<p class="tiny">Nothing stood out this time.</p>'}
      </div>
      <div class="card">
        <div class="eyebrow" style="color:var(--orange)">What to improve</div>
        ${improve.map((e) => {
          const slot = STEP_TO_SLOT[e.related_step];
          return `<div class="lesson"><span class="m ${e.kind === "unknown" ? "st-unknown" : "st-warn"}">${e.kind === "unknown" ? "?" : "!"}</span><span><span class="clamp2" title="${esc(prettyIds(e.message))}">${esc(firstSentence(e.message))}</span>${slot ? `<button data-action="fix" data-slot="${slot}">FIX ${esc(slot.toUpperCase())} →</button>` : ""}</span></div>`;
        }).join("") || '<p class="tiny">No weakness found by the engine.</p>'}
      </div>
      <div class="card">
        <div class="eyebrow">In flight</div>
        ${decisions.map((x) => `<div class="lesson"><span class="m" style="color:var(--cyan)">›</span><span><b class="ellipsis" style="display:block">${esc(x.p)}</b><span class="tiny clamp2">${esc((x.c || "").split(": ").slice(1).join(": "))}</span></span></div>`).join("")
          || `<div class="lesson"><span class="m" style="color:var(--cyan)">›</span><span>${d.anomalies.length ? "Anomalies were handled automatically: your design left one option." : "No anomaly needed a decision."}</span></div>`}
        <div class="suggest" id="sug" style="margin-top:auto"><div class="row"><span class="label">Engineers suggest</span><span class="spinner"></span></div></div>
      </div>
    </div>
    <div class="footer">
      <button class="btn ghost" data-action="score">← SCORE</button>
      <div class="row">
        <button class="btn ghost" data-action="home">NEW MISSION</button>
        <button class="btn" data-action="improve">IMPROVE DESIGN ↗</button>
      </div>
    </div>
  </div>`);

  const toDesigner = (config) => {
    state.previous = { score: d.score.total ?? 0, outcome: d.outcome };
    if (config) state.config = JSON.parse(JSON.stringify(config));
    resetMission();
    state.evaluation = null;
    notify("replay");
    go("designer", { force: true });
    evaluateNow();
  };

  return actions(root, {
    score: () => go("results"),
    home: () => { resetMission(); go("home"); },
    improve: () => toDesigner(d.configuration),
    fix: (b) => { focusSlot(b.dataset.slot); toDesigner(d.configuration); },
    load: () => suggestion && toDesigner(suggestion.configuration),
  });
}

export async function mounted() {
  const d = state.debrief;
  const box = root?.querySelector("#sug");
  try {
    const rec = await api.recommend(d.configuration);
    if (!root) return;
    const alts = rec.alternatives || [];
    suggestion = alts.find((a) => diff(d.configuration, a.configuration).length) || null;
    if (!suggestion) {
      box.innerHTML = '<span class="label">Engineers suggest</span><span class="tiny">Your design is already on the best trade-off curve.</span>';
      return;
    }
    const changes = diff(d.configuration, suggestion.configuration).slice(0, 3);
    box.innerHTML = `<div class="row"><span class="label">Engineers suggest</span><span class="tag">${esc(suggestion.label || "alternative")}</span></div>
      <div class="diff">${changes.map(([k, a, b]) => `<div><span class="dim" style="width:64px">${k}</span><s class="ellipsis">${esc(a)}</s>→<b class="ellipsis">${esc(b)}</b></div>`).join("")}</div>
      <button class="btn outline" style="height:32px" data-action="load">TRY THIS DESIGN</button>`;
  } catch {
    if (box) box.innerHTML = '<span class="label">Engineers suggest</span><span class="tiny">No suggestion available.</span>';
  }
}
export function leave() { root = null; }

function diff(a, b) {
  const out = [];
  const show = (v) => (Array.isArray(v) ? v.map(nameOf).join(", ") || "none" : v ? nameOf(v) : "none");
  for (const [k, label] of SLOT_FIELDS) {
    if (JSON.stringify(a[k] ?? null) !== JSON.stringify(b[k] ?? null)) out.push([label, show(a[k]), show(b[k])]);
  }
  if (JSON.stringify(a.power) !== JSON.stringify(b.power)) out.push(["Power", a.power.mode === "platform_payload_budget" ? "platform" : "custom", b.power.mode === "platform_payload_budget" ? "platform" : "custom"]);
  return out;
}
