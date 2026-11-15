/* Game sound. Recorded effects come from the team's files on the main branch (trimmed into
   audio/); interface blips are synthesised with Web Audio so they need no files.
   Browsers allow sound only after the first click or key press: everything waits for that.
   M toggles mute anywhere; the choice is remembered. */

const FILES = {
  countdown: "audio/countdown.mp3",   // "10 ... 1" with echo; numbers ~1.28 s apart
  launch: "audio/launch.mp3",
  explosion: "audio/explosion.mp3",
  alarm: "audio/alarm.mp3",
  ambient: "audio/ambient.mp3",       // cockpit hum, looped quietly in the background
};
export const COUNTDOWN_STEP_MS = 1280;

const KEY = "smdg.muted";
let muted = (() => { try { return localStorage.getItem(KEY) === "1"; } catch { return false; } })();
let unlocked = false;
let ctx = null;
const clips = {};
const listeners = new Set();

function clip(name) {
  if (!clips[name]) {
    const a = new Audio(FILES[name]);
    a.preload = "auto";
    if (name === "ambient") { a.loop = true; a.volume = 0.18; }
    clips[name] = a;
  }
  return clips[name];
}

export function isMuted() { return muted; }
export function onMuteChange(fn) { listeners.add(fn); return () => listeners.delete(fn); }

export function setMuted(value) {
  muted = Boolean(value);
  try { localStorage.setItem(KEY, muted ? "1" : "0"); } catch { /* storage off */ }
  Object.values(clips).forEach((a) => { a.muted = muted; });
  if (!muted && unlocked) ambient(true);
  listeners.forEach((fn) => fn(muted));
}

export function play(name, { volume = 1, restart = true } = {}) {
  if (!unlocked) return null;
  const a = clip(name);
  a.muted = muted;
  a.volume = name === "ambient" ? a.volume : volume;
  if (restart) { try { a.currentTime = 0; } catch { /* not loaded yet */ } }
  a.play().catch(() => { /* blocked or missing: stay silent */ });
  return a;
}

export function stop(name, fadeMs = 0) {
  const a = clips[name];
  if (!a) return;
  if (!fadeMs) { a.pause(); return; }
  const v0 = a.volume;
  const t0 = performance.now();
  const step = (t) => {
    const k = Math.min(1, (t - t0) / fadeMs);
    a.volume = v0 * (1 - k);
    if (k < 1) requestAnimationFrame(step); else { a.pause(); a.volume = v0; }
  };
  requestAnimationFrame(step);
}

export function ambient(on) {
  if (on) { if (!muted) play("ambient", { restart: false }); }
  else stop("ambient", 600);
}

/* Synthesised interface sounds. kind: click | select | deselect | error | success | fail | tick */
export function blip(kind = "click") {
  if (!unlocked || muted) return;
  try {
    ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
    const notes = {
      click: [[880, 0.035, "square", 0.025]],
      select: [[660, 0.05, "sine", 0.08], [990, 0.07, "sine", 0.07]],
      deselect: [[700, 0.05, "sine", 0.06], [470, 0.07, "sine", 0.05]],
      error: [[160, 0.18, "sawtooth", 0.05]],
      success: [[523, 0.12, "sine", 0.09], [659, 0.12, "sine", 0.09], [784, 0.25, "sine", 0.09]],
      fail: [[330, 0.22, "triangle", 0.09], [247, 0.35, "triangle", 0.09]],
      tick: [[1200, 0.02, "square", 0.02]],
    }[kind] || [];
    let t = ctx.currentTime;
    for (const [freq, dur, type, gain] of notes) {
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.type = type; o.frequency.value = freq;
      g.gain.setValueAtTime(gain, t);
      g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
      o.connect(g).connect(ctx.destination);
      o.start(t); o.stop(t + dur + 0.02);
      t += dur * 0.85;
    }
  } catch { /* no Web Audio: stay silent */ }
}

function unlock() {
  if (unlocked) return;
  unlocked = true;
  Object.keys(FILES).forEach(clip);   // start loading
  ambient(true);
}

window.addEventListener("pointerdown", unlock, { once: true, capture: true });
window.addEventListener("keydown", (e) => {
  unlock();
  if ((e.key === "m" || e.key === "M") && !e.target.closest?.("input, textarea")) setMuted(!muted);
}, { capture: true });

/* Every button gives a short click. */
document.addEventListener("click", (e) => {
  const b = e.target.closest("button, [role='button']");
  if (!b || b.disabled) return;
  if (b.matches(".part, [data-action='pick']")) return; // cards play select / deselect themselves
  blip("click");
}, { capture: true });
