/* Small DOM helpers shared by every screen. */

export const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export function el(html) {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
}

/* Delegate clicks on [data-action] inside root to handlers[action](target, event). */
export function actions(root, handlers) {
  root.addEventListener("click", (e) => {
    const t = e.target.closest("[data-action]");
    if (!t || !root.contains(t) || t.disabled) return;
    const fn = handlers[t.dataset.action];
    if (fn) { e.preventDefault(); fn(t, e); }
  });
  root.addEventListener("keydown", (e) => {
    if ((e.key === "Enter" || e.key === " ") && e.target.matches?.('[role="button"][data-action]')) {
      e.preventDefault();
      e.target.click();
    }
  });
  return root;
}

let toastTimer;
export function toast(message, kind = "") {
  const t = document.getElementById("toast");
  t.textContent = message;
  t.className = `toast show ${kind}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.className = "toast"; }, 3600);
}

export function openModal(content, { wide = false, dismissible = true, onClose } = {}) {
  const root = document.getElementById("modal-root");
  const back = el(`<div class="backdrop"><div class="modal ${wide ? "wide" : ""}" role="dialog" aria-modal="true">${dismissible ? '<button class="close" data-close aria-label="Close">×</button>' : ""}</div></div>`);
  const modal = back.firstElementChild;
  if (typeof content === "string") modal.insertAdjacentHTML("beforeend", content);
  else modal.append(content);
  const close = () => { back.remove(); document.removeEventListener("keydown", onKey); onClose?.(); };
  const onKey = (e) => { if (e.key === "Escape" && dismissible) close(); };
  if (dismissible) {
    back.addEventListener("click", (e) => { if (e.target === back || e.target.closest("[data-close]")) close(); });
    document.addEventListener("keydown", onKey);
  }
  root.append(back);
  return { modal, close };
}

export function closeModals() { document.getElementById("modal-root").innerHTML = ""; }

export const STATUS_GLYPH = { PASS: "✓", WARNING: "!", FAIL: "×", NOT_EVALUATED: "?" };
export const LEVEL_CLASS = { LOW: "ok", MEDIUM: "warn", HIGH: "fail", UNKNOWN: "unknown" };
export const FEAS_CLASS = { FEASIBLE: "ok", CONDITIONAL: "warn", INFEASIBLE: "fail" };

export const SVG = {
  profile: '<svg viewBox="0 0 24 24"><circle cx="12" cy="8" r="3.5"/><path d="M4.8 20c.5-4 3.1-6 7.2-6s6.7 2 7.2 6"/></svg>',
  history: '<svg viewBox="0 0 24 24"><path d="M5 3.8h11l3 3V20H5z"/><path d="M8 4v6h8V4M8 20v-6h8v6"/></svg>',
};

export function pct(v) { return v == null ? "—" : `${Math.round(v * 100)}%`; }

export function fitPage(n) { return Math.max(1, n); }

export function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }
