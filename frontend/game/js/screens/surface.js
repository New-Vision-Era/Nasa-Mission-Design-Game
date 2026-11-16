/* Mars rover and lunar lander: designer, pre-launch review and operations.
   Backend: /api/v1/surface/{mission}/... (backend/app/services/surface_mission.py).
   Same layout and rules as the Earth-observation screens; equipment values are illustrative. */
import { api } from "../api.js";
import { state, notify, emptySelection } from "../state.js";
import { el, actions, esc, STATUS_GLYPH, sleep, compareBars, fitChips, specTiles } from "../ui.js";
import { ICONS } from "../catalog.js";
import * as sound from "../sound.js";
import { decisionModal } from "./operations.js";

export const SLOTS = {
  launch: { label: "Launcher", multi: false, icon: "launcher", about: "Must lift the whole spacecraft. Bigger costs more." },
  power: { label: "Power", multi: false, icon: "eps", about: "Feeds the instruments and the base load." },
  comm: { label: "Comms", multi: false, icon: "comms", about: "Share of collected science that reaches Earth." },
  landing: { label: "Landing", multi: false, icon: "propulsion", about: "Reliability decides how you touch down." },
  instruments: { label: "Science", multi: true, icon: "instrument", about: "Each instrument adds science, mass and power." },
};
const ORDER = ["launch", "power", "comm", "landing", "instruments"];

export const surf = () => state.surface;
export const rec = (cat, id) => (id && surf().catalog?.categories[cat]?.[id]) ? { id, ...surf().catalog.categories[cat][id] } : null;
export const nameOf = (cat, id) => rec(cat, id)?.name || "—";

export async function loadCatalog(mission) {
  if (surf().catalog?.mission.id !== mission) {
    surf().catalog = await api.surfaceCatalog(mission);
    surf().evaluation = null;
  }
  return surf().catalog;
}

export function resetSurface() {
  surf().selection = emptySelection();
  surf().evaluation = null;
  surf().flight = null;
  surf().decisions = {};
  surf().slot = "launch";
  surf().page = 0;
  surf().inspect = null;
}

export function focusSurfaceSlot(step) {
  const map = { budget: "launch", mass: "landing", payload: "launch", link: "comm", night: "power", communications: "comm" };
  const slot = SLOTS[step] ? step : map[step] || "launch";
  surf().slot = slot; surf().page = 0; surf().inspect = null;
}

const filled = (k) => (k === "instruments" ? surf().selection.instruments.length > 0 : Boolean(surf().selection[k]));

let evalSeq = 0;
export function evaluateSurface() {
  const seq = ++evalSeq;
  return api.surfaceEvaluate(state.missionType, surf().selection).then((ev) => {
    if (seq === evalSeq) { surf().evaluation = ev; notify("evaluation"); }
  }).catch(() => {});
}

/* ---------------- shared bits ---------------- */
const fmt = (c) => (c.actual_value == null ? "" : c.limit_value == null ? `${+(+c.actual_value).toFixed(1)} ${c.unit || ""}`
  : `${c.unit === "M$" ? "$" : ""}${+(+c.actual_value).toFixed(1)}${c.unit === "M$" ? "M" : ""} / ${c.unit === "M$" ? "$" : ""}${c.limit_value}${c.unit === "M$" ? "M" : ` ${c.unit}`}`);

function cardMetric(cat, r) {
  switch (cat) {
    case "launch": return `${r.payloadKg} kg · $${r.cost}M`;
    case "power": return `${r.powerW} W · ${r.mass} kg · $${r.cost}M`;
    case "comm": return `${Math.round(r.efficiency * 100)}% link · $${r.cost}M`;
    case "landing": return `${Math.round(r.reliability * 100)}% reliable · $${r.cost}M`;
    default: return `${r.scienceValue} pts · ${r.powerW} W · $${r.cost}M`;
  }
}
function specs(cat, r) {
  const base = [["Cost", `$${r.cost}M`], ["Mass", `${r.mass} kg`]];
  switch (cat) {
    case "launch": return [["Payload capacity", `${r.payloadKg} kg`], ["Cost", `$${r.cost}M`]];
    case "power": return [["Power", `${r.powerW} W`], ...base, ["Works at night", (r.surfaceDuty ?? 1) < 1 ? "no" : "yes"]];
    case "comm": return [["Data reaching Earth", `${Math.round(r.efficiency * 100)}%`], ...base];
    case "landing": return [["Landing reliability", `${Math.round(r.reliability * 100)}%`], ...base];
    default: return [["Science value", `${r.scienceValue} pts`], ["Power", `${r.powerW} W`], ...base];
  }
}
const money = (v) => `$${v}M`;
const SURFACE_METRICS = {
  launch: [["Lift capacity", (x) => x.payloadKg, "high", (v) => `${v} kg`], ["Cost", (x) => x.cost, "low", money]],
  power: [["Power", (x) => x.powerW, "high", (v) => `${v} W`], ["Mass", (x) => x.mass, "low", (v) => `${v} kg`], ["Cost", (x) => x.cost, "low", money]],
  comm: [["Data home", (x) => x.efficiency, "high", (v) => `${Math.round(v * 100)}%`], ["Mass", (x) => x.mass, "low", (v) => `${v} kg`], ["Cost", (x) => x.cost, "low", money]],
  landing: [["Reliability", (x) => x.reliability, "high", (v) => `${Math.round(v * 100)}%`], ["Mass", (x) => x.mass, "low", (v) => `${v} kg`], ["Cost", (x) => x.cost, "low", money]],
  instruments: [["Science", (x) => x.scienceValue, "high", (v) => `${v} pts`], ["Power draw", (x) => x.powerW, "low", (v) => `${v} W`], ["Mass", (x) => x.mass, "low", (v) => `${v} kg`], ["Cost", (x) => x.cost, "low", money]],
};
const VERDICT = { GO: ["Ready to fly", "ok"], RISKY: ["Risky launch", "warn"], NO_GO: ["Launch blocked", "fail"] };

/* ================= DESIGNER ================= */
export const designer = (() => {
  let root = null;
  let timer = null;
  function render({ go }) {
    const m = surf().catalog.mission;
    root = el(`<div class="page">
      <div class="head">
        <div class="head-title"><div class="eyebrow">Phase 02 · ${esc(m.short)}</div><h1 class="title">Engineering workspace</h1></div>
        <span class="pill" id="s-pill"><i class="dot"></i> DRAFT</span>
      </div>
      <div class="designer">
        <div class="card info" id="s-info"></div>
        <div class="center">
          <div class="viewport3d" id="viewport-designer" data-view="${esc(m.id)}" aria-label="3D view"></div>
          <div class="subtabs" id="s-sub"></div>
          <div class="picker-head"><h3 id="s-ptitle"></h3><div class="pager" id="s-pager"></div></div>
          <div id="s-parts" class="parts-host"></div>
        </div>
        <div class="card resources" id="s-res"></div>
      </div>
      <div class="footer">
        <button class="btn ghost" data-action="back">← BRIEFING</button>
        <span class="tiny">${esc(m.value_note)}</span>
        <button class="btn" data-action="review" id="s-review">REVIEW DESIGN →</button>
      </div>
    </div>`);
    return actions(root, {
      back: () => go("briefing"),
      review: () => go("review"),
      slot: (b) => { surf().slot = b.dataset.slot; surf().page = 0; surf().inspect = null; paint(); notify("designer-tab"); },
      page: (b) => { surf().page += Number(b.dataset.dir); paintParts(); },
      pick: (b) => {
        const cat = surf().slot;
        const id = b.dataset.id;
        const sel = surf().selection;
        let on;
        if (cat === "instruments") {
          on = !sel.instruments.includes(id);
          sel.instruments = on ? [...sel.instruments, id] : sel.instruments.filter((x) => x !== id);
        } else {
          on = sel[cat] !== id;
          sel[cat] = on ? id : null;
        }
        sound.blip(on ? "select" : "deselect");
        surf().inspect = id;
        paint(); notify("design");
        clearTimeout(timer); timer = setTimeout(() => evaluateSurface().then(paintResources), 150);
      },
      jump: (b) => { focusSurfaceSlot(b.dataset.slot); paint(); notify("designer-tab"); },
    });
  }
  function paint() { if (!root) return; paintTabs(); paintParts(); paintInfo(); paintResources(); }
  function paintTabs() {
    root.querySelector("#s-sub").innerHTML = ORDER.map((k) => {
      const count = k === "instruments" ? surf().selection.instruments.length : 0;
      return `<button class="chip ${surf().slot === k ? "active" : ""}" data-action="slot" data-slot="${k}"><span class="need ${filled(k) ? "ok" : ""}"></span>${SLOTS[k].label}${count ? `<span class="count">${count}</span>` : ""}</button>`;
    }).join("");
    const ls = surf().evaluation?.launch_assessment?.status;
    const pill = root.querySelector("#s-pill");
    pill.className = `pill ${ls === "GO" ? "ok" : ls === "NO_GO" ? "bad" : ls === "RISKY" ? "warn" : ""}`;
    pill.innerHTML = `<i class="dot"></i> ${ls ? ls.replace("_", " ") : "DRAFT"}`;
  }
  function paintParts() {
    const cat = surf().slot;
    const items = Object.entries(surf().catalog.categories[cat]).map(([id, r]) => ({ id, ...r }));
    const per = 8;
    const pages = Math.max(1, Math.ceil(items.length / per));
    surf().page = Math.min(Math.max(0, surf().page), pages - 1);
    root.querySelector("#s-ptitle").textContent = { launch: "Select a launcher", power: "Select power", comm: "Select comms", landing: "Select a landing system", instruments: "Select instruments" }[cat];
    root.querySelector("#s-pager").innerHTML = pages > 1 ? `<button data-action="page" data-dir="-1" ${surf().page ? "" : "disabled"}>‹</button><span>${surf().page + 1}/${pages}</span><button data-action="page" data-dir="1" ${surf().page < pages - 1 ? "" : "disabled"}>›</button>` : "";
    const sel = surf().selection;
    root.querySelector("#s-parts").innerHTML = `<div class="parts">${items.slice(surf().page * per, surf().page * per + per).map((r) => {
      const on = cat === "instruments" ? sel.instruments.includes(r.id) : sel[cat] === r.id;
      return `<div role="button" tabindex="0" aria-pressed="${on}" class="part ${on ? "selected" : ""} ${surf().inspect === r.id ? "inspected" : ""}" data-action="pick" data-id="${esc(r.id)}" title="${esc(r.name)}">
        <div class="p-top"><span class="ico">${ICONS[SLOTS[cat].icon]}</span>${SLOTS[cat].multi ? `<span class="check">${on ? "✓" : ""}</span>` : ""}</div>
        <strong class="ellipsis">${esc(r.name)}</strong><small class="ellipsis">${esc(cardMetric(cat, r))}</small></div>`;
    }).join("")}</div>`;
  }
  function paintInfo() {
    const cat = surf().slot;
    const id = surf().inspect || (cat !== "instruments" ? surf().selection[cat] : null);
    const r = rec(cat, id);
    const box = root.querySelector("#s-info");
    if (!r) {
      box.innerHTML = `<div class="eyebrow">${SLOTS[cat].label}</div><h3>Required system</h3><p class="note">${SLOTS[cat].about}</p><div class="divider"></div><p class="tiny">Select a card to inspect it.</p>`;
      return;
    }
    const items = Object.entries(surf().catalog.categories[cat]).map(([k, x]) => ({ id: k, ...x }));
    box.innerHTML = `<div class="eyebrow">${SLOTS[cat].label}</div><h3>${esc(r.name)}</h3>
      <div class="maker"><span class="ico">${ICONS[SLOTS[cat].icon]}</span><span class="tiny">Game value *</span></div>
      ${fitChips(surfaceFits(cat, r))}
      ${specTiles(specs(cat, r).map(([k, v]) => [k, v, "assumption"]))}
      ${compareBars(items, r, SURFACE_METRICS[cat] || SURFACE_METRICS.instruments)}
      <p class="note clamp3">${SLOTS[cat].about}</p>`;
  }
  function surfaceFits(cat, r) {
    const mass = surf().evaluation?.resources?.mass_kg;
    switch (cat) {
      case "launch": return [mass != null && [mass <= r.payloadKg ? "ok" : "fail", mass <= r.payloadKg ? "Lifts your spacecraft" : "Spacecraft too heavy"]];
      case "power": return [[(r.surfaceDuty ?? 1) < 1 ? "warn" : "ok", (r.surfaceDuty ?? 1) < 1 ? "Sleeps at night" : "Works day and night"]];
      case "landing": return [[r.reliability >= 0.9 ? "ok" : r.reliability >= 0.75 ? "warn" : "fail", `${Math.round(r.reliability * 100)}% safe landing`]];
      case "comm": return [[r.efficiency >= 0.8 ? "ok" : "warn", `${Math.round(r.efficiency * 100)}% of data home`]];
      default: return [];
    }
  }
  function meter(label, c, money = false) {
    if (!c) return `<div class="meter"><div class="row"><span>${label}</span><b>—</b></div><div class="bar"><i style="width:0"></i></div></div>`;
    const ratio = c.limit_value ? c.actual_value / c.limit_value : 0;
    const cls = c.status === "FAIL" ? "fail" : ratio > 0.9 ? "warn" : "ok";
    const v = money ? `$${c.actual_value}M / $${c.limit_value}M` : `${c.actual_value} / ${c.limit_value} ${c.unit}`;
    return `<div class="meter" title="${esc(c.message)}"><div class="row"><span>${label}</span><b>${v}</b></div><div class="bar ${cls}"><i style="width:${Math.min(100, ratio * 100)}%"></i></div></div>`;
  }
  function paintResources() {
    if (!root) return;
    paintTabs();
    const ev = surf().evaluation;
    const box = root.querySelector("#s-res");
    const head = `<div class="row"><div><div class="eyebrow">Live resources</div><h3 style="margin-top:4px">Engineering check</h3></div></div>`;
    if (!ev) { box.innerHTML = `${head}<div class="todo">${ORDER.map((k) => `<button class="${filled(k) ? "ok" : ""}" data-action="jump" data-slot="${k}"><i></i>${SLOTS[k].label}</button>`).join("")}</div>`; return; }
    const by = Object.fromEntries(ev.constraints.map((c) => [c.id, c]));
    const issues = ev.constraints.filter((c) => c.status !== "PASS").sort((a) => (a.status === "FAIL" ? -1 : 1));
    const la = ev.launch_assessment;
    box.innerHTML = `${head}
      ${meter("Budget", by.budget, true)}
      ${meter("Mass cap", by.mass)}
      ${meter("Launcher payload", by.payload)}
      ${meter("Power", by.power)}
      <div class="row tiny"><span>Science planned</span><b class="mono" style="color:var(--white)">${ev.resources.science_planned} / ${ev.resources.science_max} pts</b></div>
      <div class="divider" style="margin:2px 0"></div>
      <div class="checks-mini">${issues.slice(0, 3).map((c) => `<button class="check-row" data-action="jump" data-slot="${c.related_step}" title="${esc(c.message)}"><span class="s ${c.status}">${STATUS_GLYPH[c.status]}</span><span class="ellipsis">${esc(c.title)}</span></button>`).join("") || (ev.complete ? '<p class="tiny st-ok">All checks pass.</p>' : "")}</div>
      ${ev.missing.length ? `<div class="todo">${ORDER.filter((k) => !filled(k)).map((k) => `<button data-action="jump" data-slot="${k}"><i></i>Add ${SLOTS[k].label.toLowerCase()}</button>`).join("")}</div>` : ""}
      <span class="tag ${VERDICT[la.status][1]}" style="align-self:flex-start;margin-top:auto">${VERDICT[la.status][0]}</span>`;
    root.querySelector("#s-review").disabled = false;
  }
  return {
    render,
    mounted: () => { paint(); evaluateSurface().then(paintResources); },
    leave: () => { clearTimeout(timer); root = null; },
  };
})();

/* ================= REVIEW ================= */
export const review = (() => {
  let root = null;
  let selected = null;
  function render({ go }) {
    selected = null;
    root = el(`<div class="page">
      <div class="head"><div class="head-title"><div class="eyebrow">Phase 03 · Validation</div><h1 class="title">Pre-launch review</h1></div><span class="pill" id="sr-pill"><i class="dot"></i> CHECKING</span></div>
      <div class="review">
        <div class="card stack"><div class="eyebrow">Configuration</div><div class="config-list" id="sr-config"></div></div>
        <div class="card stack"><div class="row"><div class="eyebrow">System checks</div><span class="tiny">Click a check for details</span></div><div class="check-list" id="sr-checks"></div></div>
        <div class="card verdict" id="sr-verdict"></div>
      </div>
      <div class="footer"><button class="btn ghost" data-action="edit">← EDIT DESIGN</button><button class="btn orange lg" data-action="launch" id="sr-launch" disabled>GO FOR LAUNCH ↗</button></div>
    </div>`);
    return actions(root, {
      edit: () => go("designer"),
      launch: () => go("launch"),
      sel: (b) => { selected = b.dataset.id; paint(); },
      fix: (b) => { focusSurfaceSlot(b.dataset.slot); go("designer"); },
    });
  }
  function paint() {
    if (!root) return;
    const s = surf().selection;
    root.querySelector("#sr-config").innerHTML = ORDER.map((k) => {
      const v = k === "instruments" ? s.instruments.map((i) => nameOf("instruments", i)).join(", ") || "—" : nameOf(k, s[k]);
      return `<button class="config-item" data-action="fix" data-slot="${k}"><span>${SLOTS[k].label}</span><b class="ellipsis">${esc(v)}</b></button>`;
    }).join("");
    const ev = surf().evaluation;
    if (!ev) return;
    const order = { FAIL: 0, WARNING: 1, PASS: 2 };
    const checks = [...ev.constraints].sort((a, b) => order[a.status] - order[b.status] || (a.severity === "hard" ? -1 : 1));
    if (!selected) selected = checks[0]?.id;
    root.querySelector("#sr-checks").innerHTML = checks.map((k) => `<button class="check-row ${k.id === selected ? "sel" : ""}" data-action="sel" data-id="${k.id}"><span class="s ${k.status}">${STATUS_GLYPH[k.status]}</span><span class="sev">${k.severity}</span><span class="t ellipsis">${esc(k.title)}</span><span class="v">${esc(fmt(k))}</span></button>`).join("")
      || '<p class="tiny">Add systems to run the checks.</p>';
    const la = ev.launch_assessment;
    const [title, cls] = VERDICT[la.status];
    const sel = ev.constraints.find((k) => k.id === selected);
    const risk = la.status === "RISKY" ? la.risks.find((r) => r.constraint_id === selected) : null;
    const counts = { PASS: 0, FAIL: 0, WARNING: 0 };
    ev.constraints.forEach((k) => { counts[k.status] = (counts[k.status] || 0) + 1; });
    const bottom = la.status === "NO_GO"
      ? `<div class="stack" style="gap:6px"><span class="label">Why it cannot fly</span><div class="consequences">${la.blocking.map((b) => `<div><b class="st-fail">×</b><span>${esc(b.reason)}</span></div>`).join("")}</div></div>`
      : la.status === "RISKY"
        ? `<div class="stack" style="gap:6px"><span class="label">If you launch now</span><div class="consequences">${la.risks.map((r) => `<div><b>!</b><span>${esc(r.consequence)}</span></div>`).join("")}</div></div>`
        : '<span class="tiny">Landing still depends on your landing system and your choice of site.</span>';
    root.querySelector("#sr-verdict").innerHTML = `<div class="eyebrow">Verdict</div><div class="big st-${cls}">${title}</div>
      <div class="counts"><div><span class="label">Pass</span><b class="st-ok">${counts.PASS}</b></div><div><span class="label">Fail</span><b class="st-fail">${counts.FAIL}</b></div><div><span class="label">Warn</span><b class="st-warn">${counts.WARNING}</b></div><div style="display:none"><span class="label">Science</span><b>${ev.resources.science_planned}</b></div></div>
      ${sel ? `<div class="detail"><h4>${esc(sel.title)}</h4><p>${esc(sel.message)}</p>${risk ? `<p class="st-warn" style="margin-top:6px">In flight: ${esc(risk.consequence)}</p>` : ""}${sel.status !== "PASS" ? `<button class="btn ghost" style="margin-top:10px;height:32px" data-action="fix" data-slot="${sel.related_step}">FIX IN WORKSPACE →</button>` : ""}</div>` : ""}
      ${bottom}`;
    const pill = root.querySelector("#sr-pill");
    pill.className = `pill ${cls === "ok" ? "ok" : cls === "warn" ? "warn" : "bad"}`;
    pill.innerHTML = `<i class="dot"></i> ${la.status.replace("_", " ")}`;
    const btn = root.querySelector("#sr-launch");
    btn.disabled = !ev.launchable;
    btn.textContent = la.status === "GO" ? "GO FOR LAUNCH ↗" : la.status === "RISKY" ? "LAUNCH ANYWAY ↗" : `FIX ${la.blocking.length} BLOCKER${la.blocking.length === 1 ? "" : "S"}`;
  }
  return { render, mounted: () => { paint(); evaluateSurface().then(paint); }, leave: () => { root = null; } };
})();

/* ================= OPERATIONS ================= */
export const operations = (() => {
  let root = null;
  let alive = false;
  let shown = 0;           // stages already played
  const STAGES = ["launch", "cruise", "landing", "surface"];
  function render({ go }) {
    const m = surf().catalog.mission;
    shown = 0;
    root = el(`<div class="page">
      <div class="head"><div class="head-title"><div class="eyebrow">Phase 04 · ${esc(m.short)}</div><h1 class="title">Mission control</h1></div><span class="status-big" id="so-status"><i></i> NOMINAL</span></div>
      <div class="ops">
        <div class="card stack" style="gap:12px">
          <div><span class="label">Mission day</span><div class="day" id="so-day">000</div><span class="tiny">${esc(m.duration)} mission</span></div>
          <div class="divider" style="margin:0"></div>
          <div class="meter"><div class="row"><span>Science to Earth</span><b id="so-sci">0 / ${m.science_max}</b></div><div class="bar"><i id="so-scibar" style="width:0"></i></div></div>
          <div class="kv">
            <div><span>Stage</span><b id="so-stage">Launch</b></div>
            <div><span>Landing</span><b id="so-land">—</b></div>
            <div><span>Launch</span><b class="${surf().evaluation?.launch_assessment?.status === "RISKY" ? "st-warn" : "st-ok"}">${surf().evaluation?.launch_assessment?.status === "RISKY" ? "Risky" : "Nominal"}</b></div>
          </div>
          <div class="divider" style="margin:0"></div>
          <div class="kv">
            <div><span>Lander</span><b>${esc(nameOf("landing", surf().selection.landing))}</b></div>
            <div><span>Power</span><b>${esc(nameOf("power", surf().selection.power))}</b></div>
          </div>
        </div>
        <div class="center">
          <div class="viewport3d" id="viewport-operations" data-view="${esc(m.id)}" aria-label="Mission 3D view"></div>
          <div class="timeline" id="so-tl" style="--n:4">${STAGES.map((s, i) => `<div class="tl-cell" data-s="${s}">${["LAUNCH", esc(m.cruise.title.split(" ")[0].toUpperCase()), "LANDING", "SURFACE"][i]}</div>`).join("")}</div>
        </div>
        <div class="card stack">
          <div class="row"><div class="eyebrow">Mission log</div><span class="tag ghost">live</span></div>
          <div class="log" id="so-log"></div>
          <button class="btn block" id="so-next" style="display:none" data-action="results">MISSION REPORT →</button>
        </div>
      </div>
    </div>`);
    alive = true;
    return actions(root, { results: () => { state.debrief = surf().flight.debrief; go("results", { force: true }); } });
  }
  function log(p, msg, kind = "") {
    const box = root?.querySelector("#so-log");
    if (!box) return;
    box.prepend(el(`<div class="log-item ${kind}"><span class="p">${esc(p)}</span><span>${esc(msg)}</span></div>`));
  }
  function setStatus(kind, text) {
    const s = root?.querySelector("#so-status");
    if (!s) return;
    s.className = `status-big ${kind}`;
    s.innerHTML = `<i></i> ${text}`;
  }
  async function playStages() {
    const f = surf().flight;
    const m = surf().catalog.mission;
    const days = { launch: 0, cruise: m.cruise.days, landing: m.cruise.days, surface: m.cruise.days + 30 };
    while (alive && shown < f.stages.length) {
      const st = f.stages[shown];
      const cell = root.querySelector(`.tl-cell[data-s="${st.id}"]`);
      cell?.classList.add("now");
      root.querySelector("#so-stage").textContent = st.title;
      root.querySelector("#so-day").textContent = String(days[st.id] ?? 0).padStart(3, "0");
      await sleep(900);
      if (!alive) return;
      cell?.classList.remove("now");
      cell?.classList.add(st.status === "completed" ? "done" : st.status === "degraded" ? "partial" : "lost");
      log(st.id.slice(0, 3).toUpperCase(), st.message, st.status === "completed" ? "science" : st.status === "degraded" ? "event" : "anomaly");
      if (st.id === "landing") root.querySelector("#so-land").textContent = { completed: "Clean", degraded: "Damaged", failed: "Lost" }[st.status];
      if (st.status === "failed") { sound.play("explosion", { volume: 0.8 }); setStatus("alert", "MISSION LOST"); }
      else sound.blip("tick");
      shown += 1;
    }
    if (!alive) return;
    if (f.status === "AWAITING_DECISION") {
      root.querySelector('.tl-cell[data-s="landing"]')?.classList.add("now");
      setStatus("alert", "DECISION");
      decisionModal(f.pending_decision, async (choice) => {
        surf().decisions = { ...surf().decisions, landing_site: choice };
        surf().flight = await api.surfaceFly(state.missionType, surf().selection, surf().decisions);
        notify("decision");
        setStatus("", "NOMINAL");
        playStages();
      });
      return;
    }
    if (f.status === "COMPLETED") {
      const d = f.debrief;
      const ret = d.objectives.find((o) => o.id === "return_data");
      const sci = d.score.categories.find((c) => c.id === "science");
      const pts = Math.round((sci.score_fraction || 0) * m.science_max);
      root.querySelector("#so-sci").textContent = `${pts} / ${m.science_max}`;
      root.querySelector("#so-scibar").style.width = `${(sci.score_fraction || 0) * 100}%`;
      STAGES.forEach((s) => { const c = root.querySelector(`.tl-cell[data-s="${s}"]`); if (c && !c.className.match(/done|partial|lost/)) c.classList.add("lost"); });
      if (d.outcome !== "FAILURE" || !d.launch_assessment?.total_loss) setStatus("done", "MISSION COMPLETE");
      log("END", `Outcome: ${d.outcome.replaceAll("_", " ")}. ${ret?.message || ""}`, "phase");
      sound.blip(d.outcome === "SUCCESS" ? "success" : "fail");
      state.debrief = d;
      state.reached.results = true;
      notify("completed");
      root.querySelector("#so-next").style.display = "";
    }
  }
  return {
    render,
    mounted: () => { log("—", `${surf().catalog.mission.name}: on course.`, "phase"); playStages(); },
    leave: () => { alive = false; root = null; },
  };
})();

/* For the debrief: differences between two selections, by slot. */
export function diffSelections(a, b) {
  const out = [];
  for (const k of ORDER) {
    const x = k === "instruments" ? a[k].map((i) => nameOf(k, i)).join(", ") : nameOf(k, a[k]);
    const y = k === "instruments" ? b[k].map((i) => nameOf(k, i)).join(", ") : nameOf(k, b[k]);
    if (x !== y) out.push([SLOTS[k].label, x || "none", y || "none"]);
  }
  return out;
}
