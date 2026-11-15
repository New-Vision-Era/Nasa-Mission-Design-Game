/* Player profile (register / log in / log out) and mission history. */
import { api, setToken } from "../api.js";
import { state, notify } from "../state.js";
import { el, esc, openModal, toast } from "../ui.js";

export function openProfile({ onChange } = {}) {
  if (state.user) return openProfileCard(onChange);
  let mode = "login";
  const box = el(`<div class="stack" style="gap:14px">
    <div class="eyebrow">Player profile</div>
    <h2 class="title" style="font-size:24px" id="pf-title">Log in</h2>
    <p class="tiny">Guests can play. An account keeps your mission history.</p>
    <form class="form" id="pf-form" autocomplete="on">
      <input name="username" placeholder="Username" autocomplete="username" required minlength="3" maxlength="32" pattern="[A-Za-z0-9_]+">
      <input name="password" type="password" placeholder="Password (8+ characters)" autocomplete="current-password" required minlength="8">
      <div class="err" id="pf-err"></div>
      <button class="btn block" type="submit" id="pf-submit">LOG IN</button>
    </form>
    <button class="btn ghost block" id="pf-switch">CREATE AN ACCOUNT</button>
  </div>`);
  const { close } = openModal(box);
  const form = box.querySelector("#pf-form");
  box.querySelector("#pf-switch").addEventListener("click", () => {
    mode = mode === "login" ? "register" : "login";
    box.querySelector("#pf-title").textContent = mode === "login" ? "Log in" : "Create account";
    box.querySelector("#pf-submit").textContent = mode === "login" ? "LOG IN" : "CREATE ACCOUNT";
    box.querySelector("#pf-switch").textContent = mode === "login" ? "CREATE AN ACCOUNT" : "I ALREADY HAVE AN ACCOUNT";
    form.password.autocomplete = mode === "login" ? "current-password" : "new-password";
  });
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const err = box.querySelector("#pf-err");
    err.textContent = "";
    try {
      const res = await (mode === "login" ? api.login : api.register)(form.username.value.trim(), form.password.value);
      setToken(res.token);
      state.user = res.user;
      close();
      notify("auth");
      toast(`Welcome, ${res.user.username}.`);
      onChange?.();
    } catch (ex) {
      err.textContent = ex.status === 409 ? "That username is taken." : ex.status === 401 ? "Wrong username or password." : ex.message;
    }
  });
}

async function openProfileCard(onChange) {
  const box = el(`<div class="stack" style="gap:14px">
    <div class="eyebrow">Player profile</div>
    <h2 class="title" style="font-size:24px">${esc(state.user.username)}</h2>
    <div class="stat-row"><div><span class="label">Missions flown</span><b id="pf-n">…</b></div><div><span class="label">Best score</span><b id="pf-best">…</b></div></div>
    <button class="btn ghost block" id="pf-out">LOG OUT</button>
  </div>`);
  const { close } = openModal(box);
  box.querySelector("#pf-out").addEventListener("click", async () => {
    try { await api.logout(); } catch { /* token may already be gone */ }
    setToken(null);
    state.user = null;
    close();
    notify("auth");
    onChange?.();
  });
  try {
    const list = await api.history();
    const done = list.filter((m) => m.status === "COMPLETED");
    box.querySelector("#pf-n").textContent = done.length;
    const best = Math.max(...done.map((m) => m.score_total ?? 0));
    box.querySelector("#pf-best").textContent = done.length ? Math.round(best) : "—";
  } catch {
    box.querySelector("#pf-n").textContent = "—";
    box.querySelector("#pf-best").textContent = "—";
  }
}

const PAGE = 6;

export async function openHistory({ go }) {
  if (!state.user) {
    toast("Log in to see your mission history.");
    openProfile({ onChange: () => openHistory({ go }) });
    return;
  }
  const box = el(`<div class="stack" style="gap:12px">
    <div class="eyebrow">Mission history</div>
    <h2 class="title" style="font-size:24px">Past missions</h2>
    <div class="hist-list" id="h-list"><div class="row"><span class="spinner"></span><span class="muted">Loading…</span></div></div>
    <div class="row"><span class="tiny" id="h-count"></span><div class="pager" id="h-pager"></div></div>
  </div>`);
  const { close } = openModal(box, { wide: false });
  let list = [];
  let page = 0;
  const paint = () => {
    const shown = list.slice(page * PAGE, page * PAGE + PAGE);
    box.querySelector("#h-list").innerHTML = shown.map((m) => `
      <button class="hist-item" data-id="${esc(m.mission_id)}">
        <span><span class="ellipsis" style="display:block">${esc(m.name || "Mission")}</span><span class="tiny">${new Date(m.created_at).toLocaleString()}</span></span>
        <span class="tag ${m.status === "COMPLETED" ? (m.outcome === "SUCCESS" ? "ok" : m.outcome === "FAILURE" ? "fail" : "warn") : "ghost"}">${esc((m.status === "COMPLETED" ? m.outcome : "in flight").replaceAll("_", " "))}</span>
        <b>${m.score_total == null ? "—" : Math.round(m.score_total)}</b>
      </button>`).join("") || '<p class="tiny">No missions yet. Launch one!</p>';
    const pages = Math.max(1, Math.ceil(list.length / PAGE));
    box.querySelector("#h-count").textContent = list.length ? `${list.length} mission${list.length === 1 ? "" : "s"}` : "";
    box.querySelector("#h-pager").innerHTML = pages > 1 ? `<button data-dir="-1" ${page ? "" : "disabled"}>‹</button><span>${page + 1}/${pages}</span><button data-dir="1" ${page < pages - 1 ? "" : "disabled"}>›</button>` : "";
  };
  box.addEventListener("click", async (e) => {
    const pg = e.target.closest("[data-dir]");
    if (pg) { page += Number(pg.dataset.dir); paint(); return; }
    const item = e.target.closest(".hist-item");
    if (!item) return;
    try { await loadMission(item.dataset.id, { go }); close(); } catch (ex) { toast(ex.message, "error"); }
  });
  try { list = await api.history(); paint(); } catch (ex) { box.querySelector("#h-list").innerHTML = `<p class="err">${esc(ex.message)}</p>`; }
}

/* Open a stored mission: completed -> report, in flight -> operations. */
export async function loadMission(id, { go, silent = false } = {}) {
  const view = await api.getMission(id);
  state.mission = view;
  state.config = JSON.parse(JSON.stringify(view.state.configuration));
  state.reached = { briefing: true, designer: true, review: true, operations: true, results: view.status === "COMPLETED" };
  if (view.status === "COMPLETED" && view.debrief) {
    state.debrief = view.debrief;
    state.shownPeriod = view.state.total_periods;
    notify("load");
    go(silent ? "results" : "results", { force: true });
  } else if (view.status === "AWAITING_DECISION") {
    state.debrief = null;
    state.shownPeriod = view.state.timeline.length ? Math.max(...view.state.timeline.map((t) => t.period)) : 0;
    notify("load");
    go("operations", { force: true });
  } else {
    throw new Error("This mission did not launch.");
  }
}
