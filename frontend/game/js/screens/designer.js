/* 03 · Engineering workspace. Pick components; the engine re-evaluates the design live
   (POST /simulation/evaluate) and the dashboard shows the real constraint results. */
import { api } from "../api.js";
import {
  state, notify, rec, apiReady, slotFilled, selectedIds, toggleComponent, powerQty, changeQty,
} from "../state.js";
import { el, actions, esc, STATUS_GLYPH, LEVEL_CLASS } from "../ui.js";
import { SLOTS, NONE_CARD, cardMetrics, inspectorSpecs, iconFor, usd, unit, STEP_TO_SLOT, gbPerDay } from "../catalog.js";

const TABS = [["spacecraft", "Spacecraft"], ["orbit", "Orbit"], ["launcher", "Launcher"]];
const SPACECRAFT_SLOTS = ["platform", "science", "power", "comms", "adcs", "propulsion"];
const CHECKLIST = ["platform", "science", "power", "comms", "adcs", "orbit", "launcher"];

const ABOUT = {
  platform: "The bus: structure, payload room and power for your instruments.",
  science: "Instruments do the science. Match the imager to the mission.",
  power: "Use the platform's payload power, or build your own arrays and batteries.",
  comms: "Radios send data down and take commands up. You need an uplink.",
  adcs: "Attitude control points the camera. Better pointing, fewer missed targets.",
  propulsion: "Optional. Thrusters for orbit changes and keeping.",
  orbit: "Altitude sets resolution. Sun-synchronous keeps lighting constant.",
  launcher: "Must reach your orbit and lift your mass — within budget.",
};

let root = null;
let evalSeq = 0;
let evalTimer = null;
let perPage = 8;

/* ---------------- evaluation ---------------- */
export function evaluateNow() {
  clearTimeout(evalTimer);
  if (!apiReady()) { state.evaluation = null; state.evalError = null; paintResources(); return Promise.resolve(); }
  const seq = ++evalSeq;
  state.evaluating = true;
  paintResources();
  return api.evaluate(state.config).then((ev) => {
    if (seq !== evalSeq) return;
    state.evaluation = ev; state.evalError = null;
  }).catch((err) => {
    if (seq !== evalSeq) return;
    state.evaluation = null; state.evalError = err.message;
  }).finally(() => {
    if (seq !== evalSeq) return;
    state.evaluating = false;
    paintResources(); paintTabs(); notify("evaluation");
  });
}
function scheduleEvaluate() { clearTimeout(evalTimer); evalTimer = setTimeout(evaluateNow, 220); }

/* ---------------- render ---------------- */
export function render({ go }) {
  const d = state.designer;
  root = el(`<div class="page">
    <div class="head">
      <div><div class="eyebrow">Phase 02 · Mission engineering</div><h1 class="title">Engineering workspace</h1></div>
      <div class="tabs" id="d-tabs"></div>
      <span class="pill" id="d-feas"><i class="dot"></i> DRAFT</span>
    </div>
    <div class="designer">
      <div class="card info" id="d-info"></div>
      <div class="center">
        <div class="viewport3d" id="viewport-designer" data-view="spacecraft" aria-label="3D view"></div>
        <div class="subtabs" id="d-sub"></div>
        <div class="picker-head">
          <h3 id="d-ptitle"></h3>
          <div class="pager" id="d-pager"></div>
        </div>
        <div id="d-parts" style="display:flex;flex-direction:column"></div>
      </div>
      <div class="card resources" id="d-res"></div>
    </div>
    <div class="footer">
      <button class="btn ghost" data-action="back">← BRIEFING</button>
      <span class="tiny">* estimate or game assumption · n/p = not published</span>
      <button class="btn" data-action="review" id="d-review">REVIEW DESIGN →</button>
    </div>
  </div>`);
  if (!SLOTS[d.slot]) d.slot = "platform";

  actions(root, {
    back: () => go("briefing"),
    review: () => go("review"),
    tab: (b) => {
      d.tab = b.dataset.tab;
      d.slot = d.tab === "spacecraft" ? (SPACECRAFT_SLOTS.includes(d.slot) ? d.slot : "platform") : d.tab === "orbit" ? "orbit" : "launcher";
      d.page = 0; d.inspect = null; paintAll(); notify("designer-tab");
    },
    slot: (b) => { d.slot = b.dataset.slot; d.page = 0; d.inspect = null; paintAll(); notify("designer-tab"); },
    page: (b) => { d.page += Number(b.dataset.dir); paintParts(); },
    pick: (b) => {
      const slot = d.slot;
      const id = b.dataset.id || null;
      const r = id ? rec(SLOTS[slot].category, id) : null;
      d.inspect = id ? { slot, id } : null;
      if (slot === "power" && r && r.family !== "power_conditioning" && powerQty(id) > 0) { paintInfo(); paintParts(); return; }
      toggleComponent(slot, id, r);
      changed();
    },
    qty: (b, e) => {
      e.stopPropagation();
      const r = rec("power_systems", b.dataset.id);
      changeQty(r, Number(b.dataset.dir));
      d.inspect = { slot: "power", id: r.id };
      changed();
    },
    powermode: (b) => {
      state.config.power.mode = b.dataset.mode;
      changed();
    },
    jump: (b) => focusSlot(b.dataset.slot),
  });
  return root;
}

export function mounted() { paintAll(); if (apiReady() && !state.evaluation) evaluateNow(); }
export function leave() { clearTimeout(evalTimer); root = null; }

export function focusSlot(slot) {
  const d = state.designer;
  if (!SLOTS[slot]) return;
  d.slot = slot; d.tab = SLOTS[slot].tab; d.page = 0; d.inspect = null;
  if (root) paintAll();
}

function changed() {
  state.evaluation = state.evaluation && apiReady() ? state.evaluation : null;
  paintAll();
  notify("design");
  scheduleEvaluate();
}

function paintAll() { if (!root) return; paintTabs(); paintParts(); paintInfo(); paintResources(); }

/* ---------------- tabs ---------------- */
function paintTabs() {
  if (!root) return;
  const d = state.designer;
  const tabDone = { spacecraft: SPACECRAFT_SLOTS.every((s) => !SLOTS[s].required || slotFilled(s)), orbit: slotFilled("orbit"), launcher: slotFilled("launcher") };
  root.querySelector("#d-tabs").innerHTML = TABS.map(([k, l]) =>
    `<button class="${d.tab === k ? "active" : ""} ${tabDone[k] ? "complete" : ""}" data-action="tab" data-tab="${k}">${l}<span class="tdot"></span></button>`).join("");
  const sub = root.querySelector("#d-sub");
  if (d.tab === "spacecraft") {
    sub.style.display = "";
    sub.innerHTML = SPACECRAFT_SLOTS.map((s) => {
      const count = s === "science" ? state.config.instrument_ids.length : s === "comms" ? state.config.communication_system_ids.length : 0;
      const need = SLOTS[s].required ? `<span class="need ${slotFilled(s) ? "ok" : ""}"></span>` : "";
      return `<button class="chip ${d.slot === s ? "active" : ""}" data-action="slot" data-slot="${s}">${need}${SLOTS[s].label}${count ? `<span class="count">${count}</span>` : ""}</button>`;
    }).join("");
  } else { sub.style.display = "none"; sub.innerHTML = ""; }
  const ls = state.evaluation?.launch_assessment?.status;
  const pill = root.querySelector("#d-feas");
  pill.className = `pill ${ls === "GO" ? "ok" : ls === "NO_GO" ? "bad" : ls === "RISKY" ? "warn" : ""}`;
  pill.innerHTML = `<i class="dot"></i> ${ls ? ls.replace("_", " ") : "DRAFT"}`;
  root.querySelector("#d-review").disabled = !apiReady();
}

/* ---------------- parts grid ---------------- */
function itemsFor(slot) {
  const list = state.catalog.categories[SLOTS[slot].category] || [];
  if (slot === "propulsion") return [NONE_CARD, ...list];
  return list;
}

function badgeFor(slot, r) {
  const sci = state.scenario.parameters.science || {};
  if (slot === "science" && (sci.required_instrument_families_any || []).includes(r.family)) return '<span class="tag ok">match</span>';
  if (slot === "orbit" && r.sun_synchronous) return '<span class="tag">SSO</span>';
  if (slot === "launcher" && state.config.orbit_id) {
    return (r.orbit_ids_supported || []).includes(state.config.orbit_id) ? '<span class="tag ok">reaches</span>' : '<span class="tag fail">orbit ✗</span>';
  }
  if (slot === "comms" && r.can_receive_commands) return '<span class="tag">uplink</span>';
  return "";
}

function paintParts() {
  if (!root) return;
  const d = state.designer;
  const slot = d.slot;
  const host = root.querySelector("#d-parts");
  const title = root.querySelector("#d-ptitle");
  const pager = root.querySelector("#d-pager");
  const cols = root.querySelector(".center").clientWidth < 620 ? 3 : 4;
  perPage = cols * 2;
  host.style.setProperty("--cols", cols);

  title.textContent = { platform: "Select a platform", science: "Select instruments", power: "Power system", comms: "Select radios", adcs: "Attitude control", propulsion: "Propulsion", orbit: "Select an orbit", launcher: "Select a launcher" }[slot];

  if (slot === "power") {
    const mode = state.config.power.mode;
    const toggle = `<div class="power-mode">
      <button class="chip ${mode === "platform_payload_budget" ? "active" : ""}" data-action="powermode" data-mode="platform_payload_budget">Platform supplied</button>
      <button class="chip ${mode === "player_built_power_system" ? "active" : ""}" data-action="powermode" data-mode="player_built_power_system">Build my own</button></div>`;
    if (mode === "platform_payload_budget") {
      const pf = rec("platforms", state.config.platform_id);
      pager.innerHTML = "";
      host.innerHTML = `${toggle}<div class="parts" style="--parts-h:${partsHeight()}px;grid-template-columns:1fr;grid-template-rows:minmax(132px,auto);margin-top:8px">
        <div class="empty-note"><div><b>${pf ? unit(pf.payload_average_power_w, "W", 0) : "—"}</b>${pf ? `supplied to the payload by ${esc(pf.name)}` : "Pick a platform first"}</div></div></div>`;
      return;
    }
    host.innerHTML = toggle;
  } else host.innerHTML = "";

  const items = itemsFor(slot);
  const pages = Math.max(1, Math.ceil(items.length / perPage));
  d.page = Math.min(Math.max(0, d.page), pages - 1);
  const shown = items.slice(d.page * perPage, d.page * perPage + perPage);
  const sel = selectedIds(slot);
  const multi = SLOTS[slot].multi;

  pager.innerHTML = pages > 1
    ? `<button data-action="page" data-dir="-1" ${d.page === 0 ? "disabled" : ""} aria-label="Previous">‹</button><span>${d.page + 1}/${pages}</span><button data-action="page" data-dir="1" ${d.page >= pages - 1 ? "disabled" : ""} aria-label="Next">›</button>`
    : "";

  const grid = el(`<div class="parts" style="--parts-h:${partsHeight()}px;${slot === "power" ? "margin-top:8px" : ""}"></div>`);
  grid.innerHTML = shown.map((r) => {
    const isSel = r.none ? !state.config.propulsion_system_id : sel.includes(r.id);
    const qty = slot === "power" && r.family !== "power_conditioning" ? powerQty(r.id) : 0;
    const inspected = d.inspect?.id === r.id;
    return `<div role="button" tabindex="0" aria-pressed="${isSel}" class="part ${isSel ? "selected" : ""} ${inspected ? "inspected" : ""} ${r.none ? "none" : ""}" data-action="pick" ${r.id ? `data-id="${esc(r.id)}"` : ""} title="${esc(r.name)}">
      <div class="p-top"><span class="ico">${r.none ? iconFor("none") : iconFor(slot, r)}</span>${r.none ? "" : badgeFor(slot, r)}${multi && slot !== "power" ? `<span class="check">${isSel ? "✓" : ""}</span>` : ""}${qty ? `<span class="qty"><button data-action="qty" data-id="${esc(r.id)}" data-dir="-1" aria-label="Remove one">−</button><b>${qty}</b><button data-action="qty" data-id="${esc(r.id)}" data-dir="1" aria-label="Add one">+</button></span>` : ""}</div>
      <strong class="ellipsis">${esc(r.name)}</strong>
      <small class="ellipsis">${r.none ? "Not needed for this orbit" : esc(cardMetrics(slot, r))}</small>
    </div>`;
  }).join("");
  host.append(grid);
}

function partsHeight() {
  const h = window.innerHeight;
  return h < 720 ? 132 : h < 860 ? 150 : 172;
}

/* ---------------- inspector ---------------- */
function paintInfo() {
  if (!root) return;
  const d = state.designer;
  const box = root.querySelector("#d-info");
  const slot = d.inspect?.slot || d.slot;
  let r = d.inspect ? rec(SLOTS[slot].category, d.inspect.id) : null;
  if (!r && !SLOTS[slot].multi) {
    const id = selectedIds(slot)[0];
    r = id ? rec(SLOTS[slot].category, id) : null;
  }
  if (!r) {
    box.innerHTML = `<div class="eyebrow">${SLOTS[slot].label}</div>
      <h3>${SLOTS[slot].required ? "Required system" : "Optional system"}</h3>
      <p class="note">${ABOUT[slot]}</p>
      <div class="divider"></div>
      <p class="tiny">Select a card to inspect it.</p>`;
    return;
  }
  const specs = inspectorSpecs(slot, r);
  const note = r.value_notes || r.ownership_note || "";
  const src = (r.source_urls || [])[0];
  box.innerHTML = `<div class="eyebrow">${SLOTS[slot].label}</div>
    <h3>${esc(r.name)}</h3>
    <span class="tiny">${esc(r.manufacturer || r.provider || "")}</span>
    <div class="specs">${specs.map(([k, v, kind]) => `<div class="spec ${kind ? `kind-${kind}` : ""}"><span>${k}</span><b>${esc(v)}</b></div>`).join("")}</div>
    ${note ? `<p class="note clamp3" title="${esc(note)}">${esc(note)}</p>` : ""}
    ${src ? `<a class="src eyebrow" href="${esc(src)}" target="_blank" rel="noopener">Source ↗</a>` : ""}`;
}

/* ---------------- resources dashboard ---------------- */
function meter(label, c, fmt = (v) => v) {
  if (!c) return "";
  const known = c.actual_value != null && c.limit_value != null;
  const ratio = known ? c.actual_value / c.limit_value : 0;
  const cls = c.status === "FAIL" ? "fail" : c.status === "WARNING" ? "warn" : c.status === "NOT_EVALUATED" || !known ? "unknown" : "ok";
  const value = known ? `${fmt(c.actual_value)} / ${fmt(c.limit_value)}${c.unit && c.unit !== "USD" ? " " + c.unit : ""}` : "unknown";
  return `<div class="meter" title="${esc(c.message)}"><div class="row"><span>${label}</span><b>${esc(value)}</b></div><div class="bar ${cls}"><i style="width:${Math.min(100, ratio * 100)}%"></i></div></div>`;
}

function paintResources() {
  if (!root) return;
  const box = root.querySelector("#d-res");
  const ev = state.evaluation;
  const todo = CHECKLIST.filter((s) => !slotFilled(s));
  const head = `<div class="row"><div><div class="eyebrow">Live resources</div><h3 style="margin-top:4px">Engineering check</h3></div>
    ${state.evaluating ? '<span class="spinner" title="Evaluating"></span>' : ev ? `<span class="tag ${LEVEL_CLASS[ev.risk_assessment.overall_level]}">risk ${ev.risk_assessment.overall_level}</span>` : '<span class="tag ghost">draft</span>'}</div>`;

  if (!apiReady() || !ev) {
    box.innerHTML = `${head}
      <p class="tiny">${state.evalError ? `<span class="st-fail">${esc(state.evalError)}</span>` : apiReady() ? "Evaluating…" : "Fill the required systems to run the engine."}</p>
      <div class="todo">${CHECKLIST.map((s) => `<button class="${slotFilled(s) ? "ok" : ""}" data-action="jump" data-slot="${s}"><i></i>${SLOTS[s].label}</button>`).join("")}</div>`;
    return;
  }
  const byId = Object.fromEntries(ev.constraints.map((c) => [c.id, c]));
  const counts = { PASS: 0, WARNING: 0, FAIL: 0, NOT_EVALUATED: 0 };
  ev.constraints.forEach((c) => { counts[c.status] = (counts[c.status] || 0) + 1; });
  const issues = ev.constraints.filter((c) => c.status === "FAIL" || c.status === "WARNING")
    .sort((a, b) => (a.status === "FAIL" ? -1 : 1) - (b.status === "FAIL" ? -1 : 1) || (a.severity === "hard" ? -1 : 1));
  const dl = gbPerDay(ev.resources.downlink_bits_per_day?.value);
  const kg = (v) => Number(v).toFixed(v < 10 ? 2 : 1);
  const w = (v) => Number(v).toFixed(v < 10 ? 1 : 0);

  box.innerHTML = `${head}
    ${meter("Payload mass", byId.payload_mass, kg)}
    ${meter("Power", byId.power_budget || ev.constraints.find((c) => c.category === "power" && c.actual_value != null), w)}
    ${meter("Launch mass", byId.launch_mass, (v) => Math.round(v))}
    ${meter("Budget", byId.budget, (v) => usd(v))}
    <div class="row tiny"><span>Downlink</span><b class="mono" style="color:var(--white)">${dl == null ? "—" : `${dl.toFixed(dl < 1 ? 3 : 1)} GB/day`}</b></div>
    <div class="divider" style="margin:2px 0"></div>
    <div class="counts">
      <div><span class="label">Pass</span><b class="st-ok">${counts.PASS}</b></div>
      <div><span class="label">Warn</span><b class="st-warn">${counts.WARNING}</b></div>
      <div><span class="label">Fail</span><b class="st-fail">${counts.FAIL}</b></div>
    </div>
    <div class="checks-mini">
      ${issues.slice(0, todo.length ? 2 : 4).map((c) => `<button class="check-row" data-action="jump" data-slot="${STEP_TO_SLOT[c.related_step] || "platform"}" title="${esc(c.message)}">
        <span class="s ${c.status}">${STATUS_GLYPH[c.status]}</span><span class="ellipsis">${esc(c.title)}</span></button>`).join("")
        || '<p class="tiny st-ok">All evaluated checks pass.</p>'}
    </div>
    ${todo.length ? `<div class="todo">${todo.map((s) => `<button data-action="jump" data-slot="${s}"><i></i>Add ${SLOTS[s].label.toLowerCase()}</button>`).join("")}</div>` : ""}
    <span class="tag ${{ GO: "ok", RISKY: "warn", NO_GO: "fail" }[ev.launch_assessment.status]}" style="align-self:flex-start;margin-top:auto">${{ GO: "Go for launch", RISKY: "Risky launch", NO_GO: "Launch blocked" }[ev.launch_assessment.status]}</span>`;
}

window.addEventListener("resize", () => { if (root && state.screen === "designer") paintParts(); });
