/* Procedural launch vehicles and launch effects (flame, smoke, fireball) for the 3D views.
   Shapes are simplified but keep each vehicle's character: published height and diameter,
   number of stages, strap-on boosters, colours. Built in metres, scaled by the caller. */
import * as THREE from "three";

const WHITE = 0xf2efe9, BLACK = 0x1b1a19, GREY = 0x9a958f, CHAR = 0x34312e;

/* id -> look. h/d in metres. s1/s2 are stage lengths as a fraction of the height. */
const LOOKS = {
  spacex_falcon9_dedicated: { h: 70, d: 3.7, s1: 0.6, inter: 0.07, s2: 0.17, fd: 5.2, body: WHITE, inter_c: BLACK, engines: 9, legs: true, fins: true },
  spacex_transporter_rideshare: { h: 70, d: 3.7, s1: 0.6, inter: 0.07, s2: 0.17, fd: 5.2, body: WHITE, inter_c: BLACK, engines: 9, legs: true, fins: true },
  rocket_lab_electron: { h: 18, d: 1.2, s1: 0.62, inter: 0.05, s2: 0.15, fd: 1.25, body: BLACK, inter_c: CHAR, engines: 9, accent: true },
  firefly_alpha: { h: 29.5, d: 2, s1: 0.6, inter: 0.06, s2: 0.17, fd: 2.3, body: CHAR, inter_c: BLACK, engines: 4, accent: true },
  isro_sslv: { h: 34, d: 2, s1: 0.5, inter: 0.08, s2: 0.24, fd: 2.1, body: WHITE, inter_c: GREY, engines: 1, bands: 3 },
  vega_c: { h: 35, d: 3.4, s1: 0.42, inter: 0.06, s2: 0.26, s2d: 2.4, fd: 3.3, body: WHITE, inter_c: GREY, engines: 1, bands: 2 },
  isro_pslv_xl: { h: 44, d: 2.8, s1: 0.48, inter: 0.06, s2: 0.27, fd: 3.2, body: 0xe7e1d6, inter_c: GREY, engines: 1, boosters: 6, bd: 1, bl: 0.33 },
  "lv-medium": { h: 45, d: 3, s1: 0.58, inter: 0.06, s2: 0.18, fd: 4, body: WHITE, inter_c: GREY, engines: 2 },
  "lv-standard": { h: 58, d: 3.8, s1: 0.6, inter: 0.06, s2: 0.16, fd: 4.2, body: 0xeee6da, inter_c: GREY, engines: 2, boosters: 2, bd: 1.6, bl: 0.32 },
  "lv-heavy": { h: 70, d: 3.7, s1: 0.6, inter: 0.07, s2: 0.17, fd: 5.2, body: WHITE, inter_c: BLACK, engines: 9, boosters: 2, bd: 3.7, bl: 0.6, cores: true, legs: true },
};
const FALLBACK = LOOKS["lv-medium"];
export const lookFor = (id) => LOOKS[id] || FALLBACK;

const mat = (color, rough = 0.5, metal = 0.15) => new THREE.MeshStandardMaterial({ color, roughness: rough, metalness: metal });
function cyl(rTop, rBot, len, m, seg = 40) {
  const mesh = new THREE.Mesh(new THREE.CylinderGeometry(rTop, rBot, len, seg), m);
  mesh.castShadow = true; mesh.receiveShadow = true;
  return mesh;
}
function bell(r, m) {
  const g = new THREE.LatheGeometry([new THREE.Vector2(r * 0.35, 0), new THREE.Vector2(r * 0.5, -r * 0.5), new THREE.Vector2(r * 0.85, -r * 1.2), new THREE.Vector2(r, -r * 1.6)], 24);
  const mesh = new THREE.Mesh(g, m); mesh.castShadow = true;
  return mesh;
}
function ogive(r, len, segments = 32, phiStart = 0, phiLength = Math.PI * 2) {
  const pts = [];
  for (let i = 0; i <= 16; i++) {
    const t = i / 16;
    pts.push(new THREE.Vector2(Math.max(0.001, r * Math.sqrt(1 - Math.pow(t, 1.8))), t * len));
  }
  return new THREE.LatheGeometry([new THREE.Vector2(0.001, 0), new THREE.Vector2(r, 0), ...pts.slice(1)], segments, phiStart, phiLength);
}
function booster(d, len, m) {
  const g = new THREE.Group();
  const body = cyl(d / 2, d / 2, len, m, 24); body.position.y = len / 2; g.add(body);
  const nose = new THREE.Mesh(ogive(d / 2, d * 2.2, 24), m); nose.position.y = len; nose.castShadow = true; g.add(nose);
  const b = bell(d * 0.32, mat(0x2b2724, 0.4, 0.8)); g.add(b);
  return g;
}

/* Returns { group, stage1, stage2, fairing: [left, right], payload, height, nozzle1, nozzle2, radius } (metres). */
export function buildRocket(id) {
  const L = lookFor(id);
  const r = L.d / 2;
  const body = mat(L.body, 0.45, 0.1);
  const interM = mat(L.inter_c, 0.6, 0.2);
  const metal = mat(0x2b2724, 0.35, 0.85);
  const accent = mat(0xd97706, 0.5, 0.2);
  const group = new THREE.Group();

  const l1 = L.h * L.s1, li = L.h * L.inter, l2 = L.h * L.s2;
  const fd = L.fd || L.d, lf = Math.max(L.h - l1 - li - l2, fd * 1.6);

  // first stage (with interstage, engines, legs, fins and strap-ons)
  const stage1 = new THREE.Group();
  const s1 = cyl(r, r, l1, body); s1.position.y = l1 / 2; stage1.add(s1);
  const inter = cyl(r, r, li, interM); inter.position.y = l1 + li / 2; stage1.add(inter);
  if (L.bands) for (let i = 1; i <= L.bands; i++) { const b = cyl(r * 1.01, r * 1.01, L.h * 0.008, interM); b.position.y = (l1 * i) / (L.bands + 1); stage1.add(b); }
  if (L.accent) { const a = cyl(r * 1.012, r * 1.012, L.h * 0.012, accent); a.position.y = l1 * 0.9; stage1.add(a); }
  const n = L.engines;
  const er = n === 1 ? r * 0.55 : n <= 2 ? r * 0.38 : n <= 4 ? r * 0.3 : r * 0.2;
  for (let i = 0; i < n; i++) {
    const e = bell(er, metal);
    if (n === 9 && i === 8) e.position.set(0, 0, 0);
    else if (n > 1) { const a = (i / Math.min(n, 8)) * Math.PI * 2; const k = n === 9 ? 0.62 : 0.5; e.position.set(Math.cos(a) * r * k, 0, Math.sin(a) * r * k); }
    stage1.add(e);
  }
  if (L.legs) for (let i = 0; i < 4; i++) {
    const leg = new THREE.Mesh(new THREE.BoxGeometry(r * 0.12, l1 * 0.22, r * 0.06), interM);
    const a = i * Math.PI / 2 + Math.PI / 4;
    leg.position.set(Math.cos(a) * r * 1.02, l1 * 0.12, Math.sin(a) * r * 1.02); leg.rotation.y = -a; leg.castShadow = true;
    stage1.add(leg);
  }
  if (L.fins) for (let i = 0; i < 4; i++) {
    const fin = new THREE.Mesh(new THREE.BoxGeometry(r * 0.5, r * 0.06, r * 0.45), metal);
    const a = i * Math.PI / 2 + Math.PI / 4;
    fin.position.set(Math.cos(a) * r * 1.2, l1 + li * 0.75, Math.sin(a) * r * 1.2); fin.rotation.y = -a;
    stage1.add(fin);
  }
  stage1.userData.boosters = [];
  if (L.boosters) {
    const bl = L.h * L.bl, bd = L.bd;
    for (let i = 0; i < L.boosters; i++) {
      const a = (i / L.boosters) * Math.PI * 2 + (L.boosters === 2 ? 0 : Math.PI / L.boosters);
      const b = L.cores ? (() => {        // heavy: two full side cores
        const g = new THREE.Group(); const c = cyl(bd / 2, bd / 2, bl, body); c.position.y = bl / 2; g.add(c);
        const nose = new THREE.Mesh(ogive(bd / 2, bd * 1.6, 24), interM); nose.position.y = bl; g.add(nose);
        for (let k = 0; k < 9; k++) { const e = bell(bd * 0.1, metal); if (k < 8) { const q = (k / 8) * Math.PI * 2; e.position.set(Math.cos(q) * bd * 0.31, 0, Math.sin(q) * bd * 0.31); } g.add(e); }
        return g; })() : booster(bd, bl, body);
      b.position.set(Math.cos(a) * (r + bd / 2 + 0.05), 0, Math.sin(a) * (r + bd / 2 + 0.05));
      stage1.add(b);
      stage1.userData.boosters.push({ x: b.position.x, z: b.position.z, r: L.cores ? bd * 0.4 : bd * 0.32 });
    }
  }
  group.add(stage1);

  // second stage: hidden engine bell inside the interstage
  const stage2 = new THREE.Group();
  const r2 = (L.s2d || L.d) / 2;
  const s2 = cyl(r2, r2, l2, body); s2.position.y = l2 / 2; stage2.add(s2);
  const vac = bell(r2 * 0.45, metal); vac.scale.setScalar(1); stage2.add(vac);
  if (r2 < r) { const adapter = cyl(r2, r, li * 0.4, interM); adapter.position.y = -li * 0.2; stage2.add(adapter); }
  stage2.position.y = l1 + li;
  group.add(stage2);

  // fairing halves (open sideways at fairing separation) and the payload inside
  const rf = fd / 2;
  const fm = mat(L.body === BLACK ? BLACK : WHITE, 0.4, 0.1);
  fm.side = THREE.DoubleSide;
  const fairing = [0, 1].map((k) => {
    const half = new THREE.Group();
    const cylLen = lf * 0.45;
    const c = new THREE.Mesh(new THREE.CylinderGeometry(rf, rf, cylLen, 32, 1, true, k * Math.PI, Math.PI), fm); c.position.y = cylLen / 2; c.castShadow = true;
    const nose = new THREE.Mesh(ogive(rf, lf - cylLen, 32, k * Math.PI, Math.PI), fm); nose.position.y = cylLen; nose.castShadow = true;
    half.add(c, nose);
    if (rf > r2 + 0.05) { const boat = new THREE.Mesh(new THREE.CylinderGeometry(rf, r2, rf * 0.35, 32, 1, true, k * Math.PI, Math.PI), fm); boat.position.y = -rf * 0.175; half.add(boat); }
    half.position.y = l1 + li + l2;
    group.add(half);
    return half;
  });
  const payload = new THREE.Group();
  payload.position.y = l1 + li + l2 + rf * 0.15;
  payload.userData.room = { r: rf * 0.8, h: lf * 0.6 };
  group.add(payload);

  return { group, stage1, stage2, fairing, payload, height: L.h, radius: r, look: L, nozzle1: -er * 1.6, nozzle2: -r2 * 0.45 * 1.6, engineR: n === 1 ? er : r * 0.75, engineR2: r2 * 0.45 };
}

/* ---------------------------------------------------------------- effects */

let puffTex = null;
function puffTexture() {
  if (puffTex) return puffTex;
  const c = document.createElement("canvas"); c.width = c.height = 64;
  const g = c.getContext("2d");
  const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grad.addColorStop(0, "rgba(255,255,255,1)"); grad.addColorStop(0.45, "rgba(255,255,255,.55)"); grad.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = grad; g.fillRect(0, 0, 64, 64);
  puffTex = new THREE.CanvasTexture(c);
  puffTex.colorSpace = THREE.SRGBColorSpace;
  return puffTex;
}

/* Engine plume: a glowing cone that flickers. length/width in metres. */
export function makeFlame(radius, length, vacuum = false) {
  const geo = new THREE.CylinderGeometry(radius * (vacuum ? 1.0 : 0.9), radius * (vacuum ? 3.2 : 1.7), length, 24, 1, true);
  geo.translate(0, -length / 2, 0);
  const material = new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide,
    uniforms: { uTime: { value: 0 }, uPower: { value: 0 }, uVac: { value: vacuum ? 1 : 0 } },
    vertexShader: `varying vec2 vUv; varying vec3 vN; void main(){ vUv = uv; vN = normalize(normalMatrix * normal); gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
    fragmentShader: `uniform float uTime; uniform float uPower; uniform float uVac; varying vec2 vUv; varying vec3 vN;
      void main(){
        float y = 1.0 - vUv.y;                       // 0 at the nozzle, 1 at the tip
        float rim = pow(abs(vN.z), 1.4);              // brighter where we look through more gas
        float flick = 0.85 + 0.15 * sin(uTime * 60.0 + vUv.x * 25.0) * sin(uTime * 37.0);
        float body = smoothstep(1.0, 0.05, y) * rim * flick;
        vec3 core = mix(vec3(1.0, 0.97, 0.85), vec3(1.0, 0.62, 0.18), smoothstep(0.0, 0.35, y));
        vec3 col = mix(core, vec3(0.85, 0.25, 0.05), smoothstep(0.35, 0.9, y));
        col = mix(col, vec3(0.75, 0.75, 1.0), uVac * 0.35 * smoothstep(0.2, 1.0, y));
        gl_FragColor = vec4(col * 1.6, body * uPower);
      }`,
  });
  const mesh = new THREE.Mesh(geo, material);
  const core = new THREE.Mesh(new THREE.ConeGeometry(radius * 0.7, length * 0.32, 18, 1, true).translate(0, -length * 0.16, 0).rotateX(Math.PI),
    new THREE.MeshBasicMaterial({ color: 0xfff3d6, transparent: true, opacity: 0, blending: THREE.AdditiveBlending, depthWrite: false }));
  const g = new THREE.Group(); g.add(mesh, core);
  g.userData = { material, core, length };
  g.renderOrder = 5;
  g.update = (t, power) => {
    material.uniforms.uTime.value = t; material.uniforms.uPower.value = power;
    core.material.opacity = Math.min(1, power) * (0.75 + Math.random() * 0.25);
    const s = 0.9 + Math.random() * 0.12;
    g.scale.set(1, Math.max(0.001, power) * s, 1);
    g.visible = power > 0.01;
  };
  g.update(0, 0);
  return g;
}

/* A pool of camera-facing puffs: smoke, exhaust trail, fireball, sparks. */
export class Puffs {
  constructor(scene, max = 260) {
    this.texture = puffTexture();
    this.items = [];
    this.free = [];
    for (let i = 0; i < max; i++) {
      const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: puffTexture(), transparent: true, depthWrite: false, opacity: 0 }));
      s.visible = false; scene.add(s);
      this.free.push(s);
    }
  }
  spawn(pos, vel, { life = 3, size = 1, grow = 2, color = 0xbdb6ad, hot = 0, opacity = 0.7, additive = false, drag = 0.6 } = {}) {
    const s = this.free.pop() || this.items.shift()?.s;
    if (!s) return;
    s.position.copy(pos); s.visible = true;
    s.material.blending = additive ? THREE.AdditiveBlending : THREE.NormalBlending;
    s.material.color.set(color); s.material.rotation = Math.random() * 6.28;
    this.items.push({ s, vel: vel.clone(), age: 0, life, size, grow, base: new THREE.Color(color), hot, opacity, drag });
  }
  update(dt) {
    const warm = new THREE.Color(0xffb067);
    for (let i = this.items.length - 1; i >= 0; i--) {
      const p = this.items[i];
      p.age += dt;
      const k = p.age / p.life;
      if (k >= 1) { p.s.visible = false; this.free.push(p.s); this.items.splice(i, 1); continue; }
      p.vel.multiplyScalar(Math.max(0, 1 - p.drag * dt));
      p.s.position.addScaledVector(p.vel, dt);
      const sz = p.size * (1 + p.grow * Math.sqrt(k));
      p.s.scale.set(sz, sz, 1);
      p.s.material.opacity = p.opacity * (k < 0.08 ? k / 0.08 : 1 - Math.pow(k, 1.4));
      if (p.hot) p.s.material.color.copy(p.base).lerp(warm, Math.max(0, p.hot * (1 - k * 3)));
    }
  }
  clear() { this.items.forEach((p) => { p.s.visible = false; this.free.push(p.s); }); this.items = []; }
}

/* Gradient sky that fades from a dusk horizon to black space as alt goes 0 -> 1. */
export function makeSky() {
  const m = new THREE.ShaderMaterial({
    side: THREE.BackSide, depthWrite: false,
    uniforms: { uAlt: { value: 0 } },
    vertexShader: `varying vec3 vDir; void main(){ vDir = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
    fragmentShader: `uniform float uAlt; varying vec3 vDir;
      void main(){
        float h = vDir.y;
        vec3 horizon = vec3(0.86, 0.42, 0.14);
        vec3 mid = vec3(0.20, 0.13, 0.12);
        vec3 top = vec3(0.04, 0.04, 0.06);
        vec3 col = mix(horizon, mid, smoothstep(-0.02, 0.18, h));
        col = mix(col, top, smoothstep(0.18, 0.7, h));
        col = mix(col, vec3(0.06,0.05,0.045), smoothstep(-0.02, -0.25, h));
        col = mix(col, vec3(0.0), smoothstep(0.0, 1.0, uAlt));
        gl_FragColor = vec4(col, 1.0);
      }`,
  });
  const sky = new THREE.Mesh(new THREE.SphereGeometry(900, 32, 16), m);
  sky.renderOrder = -10;
  return sky;
}

/* Launch tower: a lattice column with a few arms. */
export function makeTower(height, width) {
  const g = new THREE.Group();
  const m = mat(0x5b5550, 0.7, 0.5);
  const post = (x, z) => { const p = new THREE.Mesh(new THREE.BoxGeometry(width * 0.06, height, width * 0.06), m); p.position.set(x, height / 2, z); p.castShadow = true; g.add(p); };
  const w = width / 2;
  post(-w, -w); post(w, -w); post(-w, w); post(w, w);
  const levels = Math.round(height / width);
  for (let i = 0; i <= levels; i++) {
    const y = (i / levels) * height;
    for (const [sx, sz, rx] of [[w * 2, 0.05, 0], [0.05, w * 2, 1]]) {
      for (const off of [-w, w]) {
        const bar = new THREE.Mesh(new THREE.BoxGeometry(rx ? width * 0.04 : sx, width * 0.04, rx ? sz : width * 0.04), m);
        bar.position.set(rx ? off : 0, y, rx ? 0 : off); g.add(bar);
      }
    }
    if (i < levels) {
      const brace = new THREE.Mesh(new THREE.BoxGeometry(width * 0.03, Math.hypot(width, height / levels), width * 0.03), m);
      brace.position.set(0, y + height / levels / 2, w); brace.rotation.z = Math.atan2(width, height / levels); g.add(brace);
    }
  }
  return g;
}
