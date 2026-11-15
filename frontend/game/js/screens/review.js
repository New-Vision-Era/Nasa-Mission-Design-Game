/* 04 · Engineering review + pre-launch validation, from the engine's constraint results. */
import { state, nameOf, rec } from "../state.js";
import { el, actions, esc, STATUS_GLYPH, LEVEL_CLASS } from "../ui.js";
import { evaluateNow, focusSlot } from "./designer.js";
import { STEP_TO_SLOT, usd } from "../catalog.js";
import { prettyIds } from "./operations.js";

const ORDER = { FAIL: 0, WARNING: 1, NOT_EVALUATED: 2, PASS: 3 };
let root = null;
let selected = null;

function fmt(c) {
  if (c.actual_value == null) return "";
  if (c.unit === "bits/day") return `${(c.actual_value / 8e9).toFixed(1)} GB/day`;
  if (c.unit === "mm3") return `${(c.actual_value / 1e6).toFixed(1)} / ${(c.limit_value / 1e6).toFixed(0)} L`;
  const f = (v) => (c.unit === "USD" ? usd(v) : typeof v === "number" ? (Math.abs(v) >= 100 ? Math.round(v).toLocaleString() : +v.toFixed(2)) : v);
  const u = c.unit && c.unit !== "USD" ? ` ${c.unit}` : "";
  return c.limit_value != null ? `${f(c.actual_value)} / ${f(c.limit_value)}${u}` : `${f(c.actual_value)}${u}`;
}

export function render({ go }) {
  selected = null;
  root = el(`<div class="page">
    <div class="head">
      <div><div class="eyebrow">Phase 03 · Validation</div><h1 class="title">Pre-launch review</h1></div>
      <span class="pill" id="r-pill"><i class="dot"></i> CHECKING</span>
    </div>
    <div class="review">
      <div class="card stack"><div class="eyebrow">Configuration</div><div class="config-list" id="r-config"></div></div>
      <div class="card stack"><div class="row"><div class="eyebrow">System checks</div><span class="tiny">Click a check for details</span></div><div class="check-list" id="r-checks"><div class="row"><span class="spinner"></span><span class="muted">Running checks…</span></div></div></div>
      <div class="card verdict" id="r-verdict"></div>
    </div>
    <div class="footer">
      <button class="btn ghost" data-action="edit">← EDIT DESIGN</button>
      <button class="btn orange lg" data-action="launch" id="r-launch" disabled>GO FOR LAUNCH ↗</button>
    </div>
  </div>`);
  actions(root, {
    edit: () => go("designer"),
    launch: () => go("launch"),
    sel: (b) => { selected = b.dataset.id; paint(); },
    fix: (b) => { focusSlot(b.dataset.slot); go("designer"); },
  });
  return root;
}

export function mounted() {
  paint();
  evaluateNow().then(paint);
}
export function leave() { root = null; }

function paint() {
  if (!root) return;
  const c = state.config;
  const p = c.power;
  const rows = [
    ["Platform", nameOf(c.platform_id), "platform"],
    ["Science", c.instrument_ids.map(nameOf).join(", ") || "—", "science"],
    ["Power", p.mode === "platform_payload_budget" ? "Platform supplied" : `${p.solar_array_ids.length} array · ${p.battery_ids.length} batt.`, "power"],
    ["Comms", c.communication_system_ids.map(nameOf).join(", ") || "—", "comms"],
    ["Attitude", nameOf(c.adcs_system_id), "adcs"],
    ["Propulsion", c.propulsion_system_id ? nameOf(c.propulsion_system_id) : "None", "propulsion"],
    ["Orbit", rec("orbits", c.orbit_id)?.name || "—", "orbit"],
    ["Launcher", nameOf(c.launch_vehicle_id), "launcher"],
  ];
  root.querySelector("#r-config").innerHTML = rows.map(([k, v, slot]) =>
    `<button class="config-item" data-action="fix" data-slot="${slot}" title="Edit ${k.toLowerCase()}"><span>${k}</span><b class="ellipsis">${esc(v)}</b></button>`).join("");

  const ev = state.evaluation;
  if (!ev) {
    if (state.evalError) root.querySelector("#r-checks").innerHTML = `<p class="st-fail">${esc(state.evalError)}</p>`;
    return;
  }
  const checks = [...ev.constraints].sort((a, b) => ORDER[a.status] - ORDER[b.status] || (a.severity === "hard" ? -1 : 1));
  if (!selected) selected = checks[0]?.id;
  root.querySelector("#r-checks").innerHTML = checks.map((k) =>
    `<button class="check-row ${k.id === selected ? "sel" : ""}" data-action="sel" data-id="${k.id}">
      <span class="s ${k.status}">${STATUS_GLYPH[k.status]}</span><span class="sev">${k.severity}</span>
      <span class="t ellipsis">${esc(k.title)}</span><span class="v">${esc(fmt(k))}</span></button>`).join("");

  const counts = { PASS: 0, WARNING: 0, FAIL: 0, NOT_EVALUATED: 0 };
  ev.constraints.forEach((k) => counts[k.status]++);
  const la = ev.launch_assessment;
  const status = la.status;
  const sel = ev.constraints.find((k) => k.id === selected);
  const selRisk = status === "RISKY" ? la.risks.find((r) => r.constraint_id === selected) : null;
  const selBlock = la.blocking.find((b) => b.constraint_id === selected);
  const pill = root.querySelector("#r-pill");
  pill.className = `pill ${status === "GO" ? "ok" : status === "RISKY" ? "warn" : "bad"}`;
  pill.innerHTML = `<i class="dot"></i> ${status.replace("_", " ")}`;

  const title = { GO: "Ready to fly", RISKY: "Risky launch", NO_GO: "Launch blocked" }[status];
  const cls = { GO: "ok", RISKY: "warn", NO_GO: "fail" }[status];
  let bottom;
  if (status === "NO_GO") {
    bottom = `<div class="stack" style="gap:6px"><span class="label">Why it cannot fly</span>
      <div class="consequences">${la.blocking.map((b) => `<div><b class="st-fail">×</b><span>${esc(b.reason)}</span></div>`).join("")}</div></div>`;
  } else if (status === "RISKY") {
    bottom = `<div class="stack" style="gap:6px"><span class="label">If you launch now</span>
      <div class="consequences">${la.risks.map((r) => `<div><b>!</b><span>${esc(r.consequence)}</span></div>`).join("")}</div></div>`;
  } else {
    const risks = ev.risk_assessment.risks.filter((r) => r.level === "HIGH" || r.level === "MEDIUM").slice(0, 3);
    bottom = `<div class="stack" style="gap:6px">
      <div class="row"><span class="label">Flight risks</span><span class="tag ${LEVEL_CLASS[ev.risk_assessment.overall_level]}">${ev.risk_assessment.overall_level}</span></div>
      ${risks.map((r) => `<div class="row tiny" title="${esc(r.reason)}"><span class="ellipsis">${esc(r.title)}</span><span class="tag ${LEVEL_CLASS[r.level]}">${r.level}</span></div>`).join("") || '<span class="tiny">No medium or high risk.</span>'}</div>`;
  }

  root.querySelector("#r-verdict").innerHTML = `
    <div class="eyebrow">Verdict</div>
    <div class="big st-${cls}">${title}</div>
    <div class="counts">
      <div><span class="label">Pass</span><b class="st-ok">${counts.PASS}</b></div>
      <div><span class="label">Review</span><b class="st-warn">${counts.WARNING + counts.NOT_EVALUATED}</b></div>
      <div><span class="label">Fail</span><b class="st-fail">${counts.FAIL}</b></div>
    </div>
    ${sel ? `<div class="detail">
      <h4>${esc(sel.title)}</h4>
      <p title="${esc(sel.message)}">${esc(prettyIds(sel.message))}</p>
      ${selBlock ? `<p class="st-fail" style="margin-top:6px">Blocks the launch.</p>` : selRisk ? `<p class="st-warn" style="margin-top:6px">In flight: ${esc(selRisk.consequence)}</p>` : ""}
      ${sel.status !== "PASS" ? `<button class="btn ghost" style="margin-top:10px;height:32px" data-action="fix" data-slot="${STEP_TO_SLOT[sel.related_step] || "platform"}">FIX IN WORKSPACE →</button>` : ""}
    </div>` : ""}
    ${bottom}`;

  const btn = root.querySelector("#r-launch");
  btn.disabled = !ev.launchable;
  btn.textContent = status === "GO" ? "GO FOR LAUNCH ↗" : status === "RISKY" ? "LAUNCH ANYWAY ↗" : `FIX ${la.blocking.length} BLOCKER${la.blocking.length === 1 ? "" : "S"}`;
}
