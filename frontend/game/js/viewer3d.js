/* 3D views for the two reserved windows (#viewport-designer, #viewport-operations).

   Models: the visualization pair's spacecraft parts from the `game` branch (Godot project),
   converted back to glTF (models/*.glb). Their mount points (payload_mount, solar_mount_left, ...)
   and the solar-wing deployment animations are kept, and parts are placed the way the Godot
   assembler (scripts/workshop/spacecraft_assembler.gd) placed them.

   It is a visual aid, not a scale model: a part without a model is simply not drawn.
   Nothing here touches the game logic; it reads the state and follows `smdg:state` events. */
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { RoomEnvironment } from "three/addons/environments/RoomEnvironment.js";
import { clone as cloneSkinned } from "three/addons/utils/SkeletonUtils.js";
import { state, rec, isSurface } from "./state.js";

const M = (name) => `models/${name}.glb`;
const ACCENT = 0xd97706;
const GROUND_Y = -1.3;

/* ---------------------------------------------------------------- model choice (game data -> model) */

const PLATFORM_MODEL = { gsat_20: "cubesat_platform", gsat_50: "GSAT50_platform", gsat_200: "heavy_platform" };
const INSTRUMENT_MODEL = {
  optical_rgb: "optical_camera", optical_multispectral: "multispectral_imager",
  optical_hyperspectral: "hyperspectral_imager", infrared: "infrared_instrument",
  microwave_radiometer: "microwave_radiometer", radar: "radar_instrument",
};
const RADIO_MODEL = { uhf: "deployable_antenna", s_band: "patch_antenna", x_band: "high_gain_antenna", optical: "high_gain_antenna" };

function solarModel(r) {
  const t = `${r.id} ${r.name} ${r.type || ""}`.toLowerCase();
  if (t.includes("double") || t.includes("2d") || t.includes("quintuple")) return "solar_deployable_double";
  if (t.includes("deploy") || t.includes("wing") || t.includes("origami")) return "solar_deployable_single";
  return "solar_fixed";
}

/* What to draw for the current design: {platform, solar, instruments[], radios[], adcs[], propulsion[], kind}. */
function earthSpec() {
  const c = state.config;
  if (!c.platform_id) return null;
  const spec = { kind: "satellite", platform: PLATFORM_MODEL[c.platform_id] || "medium_platform", solar: null,
                 instruments: [], radios: [], adcs: [], propulsion: [] };
  if (c.power.mode === "platform_payload_budget") spec.solar = "solar_fixed";
  else {
    const arrays = c.power.solar_array_ids.map((id) => rec("power_systems", id)).filter(Boolean);
    const order = ["solar_fixed", "solar_deployable_single", "solar_deployable_double"];
    spec.solar = arrays.map(solarModel).sort((a, b) => order.indexOf(b) - order.indexOf(a))[0] || null;
  }
  spec.instruments = c.instrument_ids.map((id) => ({ id, model: INSTRUMENT_MODEL[rec("instruments", id)?.family] || "optical_camera" }));
  spec.radios = c.communication_system_ids.map((id) => ({ id, model: RADIO_MODEL[rec("communication_systems", id)?.ground_station_type] || "patch_antenna" }));
  if (c.adcs_system_id) {
    const a = rec("adcs_systems", c.adcs_system_id);
    spec.adcs.push({ id: c.adcs_system_id, model: "reaction_wheel" });
    if (a?.has_star_tracker || /star|xact|arcus/i.test(a?.name || "")) spec.adcs.push({ id: c.adcs_system_id, model: "star_tracker" });
  }
  if (c.propulsion_system_id) {
    const p = rec("propulsion_systems", c.propulsion_system_id);
    if (p?.family === "electric") spec.propulsion.push({ id: c.propulsion_system_id, model: "ion_thruster" });
    else spec.propulsion.push({ id: c.propulsion_system_id, model: "monoprop_thruster" }, { id: c.propulsion_system_id, model: "propellant_tank" });
  }
  return spec;
}

const SURFACE_INSTRUMENT = { "ins-camera": "optical_camera", "ins-spectro": "hyperspectral_imager", "ins-xrf": "multispectral_imager", "ins-drill": "radar_instrument" };
function surfaceSpec() {
  const s = state.surface.selection;
  if (!state.surface.catalog) return null;
  const any = s.launch || s.power || s.comm || s.landing || s.instruments.length;
  if (!any) return null;
  const mission = state.missionType;
  return {
    kind: mission === "mars" ? "rover" : "lander",
    platform: "medium_platform",
    solar: s.power && /solar/.test(s.power) ? "solar_deployable_single" : null,
    rtg: s.power && !/solar/.test(s.power),
    instruments: s.instruments.map((id) => ({ id, model: SURFACE_INSTRUMENT[id] || "optical_camera" })),
    radios: s.comm ? [{ id: s.comm, model: /advanced|relay/.test(s.comm) ? "high_gain_antenna" : "patch_antenna" }] : [],
    adcs: [],
    propulsion: s.landing ? [{ id: s.landing, model: "monoprop_thruster" }] : [],
    precision: Boolean(s.landing && /advanced|precision/.test(s.landing)),
  };
}

const currentSpec = () => (isSurface() ? surfaceSpec() : earthSpec());

/* ---------------------------------------------------------------- loading */

const loader = new GLTFLoader();
const cache = new Map();
function load(name) {
  if (!cache.has(name)) {
    cache.set(name, new Promise((resolve) => {
      loader.load(M(name), (g) => resolve(g), undefined, () => resolve(null)); // missing model: draw nothing
    }));
  }
  return cache.get(name);
}
async function instance(name) {
  const g = await load(name);
  if (!g) return null;
  const obj = cloneSkinned(g.scene);
  obj.name = name;
  obj.userData.animations = g.animations;
  obj.traverse((o) => {
    if (o.isMesh) {
      o.castShadow = true; o.receiveShadow = true;
      if (o.material) { o.material = o.material.clone(); o.material.envMapIntensity = 1.1; }
    }
  });
  return obj;
}
const findNode = (root, name) => {
  let hit = null;
  root.traverse((o) => { if (!hit && o.name === name) hit = o; });
  return hit;
};

/* ---------------------------------------------------------------- procedural parts (no model) */

function metal(color, rough = 0.45, metalness = 0.75) { return new THREE.MeshStandardMaterial({ color, roughness: rough, metalness }); }

function wheels(size) {
  const g = new THREE.Group();
  const geo = new THREE.CylinderGeometry(0.16 * size, 0.16 * size, 0.12 * size, 24);
  const tire = metal(0x2b2622, 0.85, 0.3);
  const hub = metal(0xb8b0a6, 0.3, 0.9);
  for (const x of [-0.62, 0, 0.62]) {
    for (const z of [-0.55, 0.55]) {
      const w = new THREE.Mesh(geo, tire);
      w.rotation.x = Math.PI / 2;
      w.position.set(x * size, -0.62 * size, z * size);
      w.castShadow = true;
      const h = new THREE.Mesh(new THREE.CylinderGeometry(0.06 * size, 0.06 * size, 0.13 * size, 12), hub);
      h.rotation.x = Math.PI / 2; h.position.copy(w.position);
      const strut = new THREE.Mesh(new THREE.BoxGeometry(0.05 * size, 0.3 * size, 0.05 * size), hub);
      strut.position.set(x * size, -0.45 * size, z * 0.82 * size);
      g.add(w, h, strut);
    }
  }
  return g;
}

function legs(size, precision) {
  const g = new THREE.Group();
  const gold = new THREE.MeshStandardMaterial({ color: 0xc9a227, roughness: 0.35, metalness: 1 });
  const pad = metal(0x8a8179, 0.6, 0.6);
  for (let i = 0; i < 4; i++) {
    const a = Math.PI / 4 + (i * Math.PI) / 2;
    const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.035 * size, 0.035 * size, 0.9 * size, 10), gold);
    leg.position.set(Math.cos(a) * 0.62 * size, -0.62 * size, Math.sin(a) * 0.62 * size);
    leg.lookAt(Math.cos(a) * 1.2 * size, -1.3 * size, Math.sin(a) * 1.2 * size);
    leg.rotateX(Math.PI / 2);
    const foot = new THREE.Mesh(new THREE.CylinderGeometry(0.13 * size, 0.15 * size, 0.04 * size, 20), pad);
    foot.position.set(Math.cos(a) * 0.92 * size, -1.0 * size, Math.sin(a) * 0.92 * size);
    g.add(leg, foot);
  }
  if (precision) {
    const lidar = new THREE.Mesh(new THREE.SphereGeometry(0.09 * size, 16, 12), new THREE.MeshStandardMaterial({ color: 0x111111, emissive: ACCENT, emissiveIntensity: 0.8 }));
    lidar.position.set(0, -0.55 * size, 0.5 * size);
    g.add(lidar);
  }
  g.traverse((o) => { if (o.isMesh) o.castShadow = true; });
  return g;
}

function rtg(size) {
  const g = new THREE.Group();
  const body = new THREE.Mesh(new THREE.CylinderGeometry(0.11 * size, 0.11 * size, 0.5 * size, 20), metal(0x4a4540, 0.5, 0.8));
  g.add(body);
  for (let i = 0; i < 8; i++) {
    const fin = new THREE.Mesh(new THREE.BoxGeometry(0.02 * size, 0.46 * size, 0.18 * size), metal(0x6f6760, 0.5, 0.8));
    fin.rotation.y = (i * Math.PI) / 4;
    fin.position.set(Math.cos((i * Math.PI) / 4) * 0.12 * size, 0, Math.sin((i * Math.PI) / 4) * 0.12 * size);
    g.add(fin);
  }
  const glow = new THREE.PointLight(ACCENT, 0.6, 1.5 * size);
  g.add(glow);
  g.rotation.z = Math.PI / 2.6;
  g.position.set(-0.7 * size, 0.2 * size, -0.4 * size);
  return g;
}

/* ---------------------------------------------------------------- assembly */

let buildSeq = 0;

async function assemble(spec) {
  const seq = ++buildSeq;
  const craft = new THREE.Group();
  craft.name = "spacecraft";
  const mixers = [];
  if (!spec) return { craft, mixers, seq };
  const platform = await instance(spec.platform);
  if (seq !== buildSeq) return null;
  if (!platform) return { craft, mixers, seq };
  craft.add(platform);
  platform.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(platform);
  const size = box.getSize(new THREE.Vector3()).length() / 1.6;

  const mount = (name) => findNode(platform, name) || platform;
  const place = async (model, parent, pos, rotY = 0) => {
    const o = await instance(model);
    if (!o) return null;
    o.position.copy(pos);
    o.rotation.y = rotY;
    parent.add(o);
    if (o.userData.animations?.length) {
      const mixer = new THREE.AnimationMixer(o);
      o.userData.animations.forEach((clip) => {
        const a = mixer.clipAction(clip);
        a.setLoop(THREE.LoopOnce, 1); a.clampWhenFinished = true; a.play();
      });
      mixers.push(mixer);
    }
    return o;
  };

  const jobs = [];
  // power: as the Godot assembler did (double wings on the platform root, others on both side mounts)
  if (spec.solar === "solar_deployable_double") jobs.push(place(spec.solar, platform, new THREE.Vector3()));
  else if (spec.solar) {
    jobs.push(place(spec.solar, mount("solar_mount_left"), new THREE.Vector3(), Math.PI));
    jobs.push(place(spec.solar, mount("solar_mount_right"), new THREE.Vector3()));
  }
  const step = Math.max(0.25, size * 0.28);
  const slots = [[0, 0], [1, 0], [-1, 0], [0, 1], [0, -1], [1, 1], [-1, -1]];
  spec.instruments.slice(0, slots.length).forEach((it, i) =>
    jobs.push(place(it.model, mount("payload_mount"), new THREE.Vector3(slots[i][0] * step, 0, slots[i][1] * step))));
  const row = (list, mountName) => list.slice(0, 3).forEach((it, i) =>
    jobs.push(place(it.model, mount(mountName), new THREE.Vector3([0, 0.3, -0.3][i] * Math.max(1, size * 0.8), 0, 0))));
  row(spec.radios, "communication_mount");
  row(spec.adcs, "adcs_mount");
  row(spec.propulsion, "propulsion_mount");
  if (spec.kind === "rover") craft.add(wheels(size));
  if (spec.kind === "lander") craft.add(legs(size, spec.precision));
  if (spec.rtg) craft.add(rtg(size));
  await Promise.all(jobs);
  if (seq !== buildSeq) return null;
  craft.traverse((o) => { if (o.isMesh) o.castShadow = true; });
  return { craft, mixers, seq };
}

/* ---------------------------------------------------------------- procedural planets */

const PLANET = {
  earth: { a: 0x123a5c, b: 0x2f6f5a, c: 0xc9b98f, atm: 0x6fb7ff, land: 0.52 },
  moon: { a: 0x56524d, b: 0x7d7872, c: 0xb5afa8, atm: 0x000000, land: 0.0 },
  mars: { a: 0x6e2a12, b: 0xb4532a, c: 0xe0a070, atm: 0xffa070, land: 0.0 },
};
const NOISE = `
  vec3 h3(vec3 p){ p=vec3(dot(p,vec3(127.1,311.7,74.7)),dot(p,vec3(269.5,183.3,246.1)),dot(p,vec3(113.5,271.9,124.6))); return -1.0+2.0*fract(sin(p)*43758.5453123); }
  float n3(vec3 p){ vec3 i=floor(p); vec3 f=fract(p); vec3 u=f*f*(3.0-2.0*f);
    return mix(mix(mix(dot(h3(i),f),dot(h3(i+vec3(1,0,0)),f-vec3(1,0,0)),u.x),mix(dot(h3(i+vec3(0,1,0)),f-vec3(0,1,0)),dot(h3(i+vec3(1,1,0)),f-vec3(1,1,0)),u.x),u.y),
               mix(mix(dot(h3(i+vec3(0,0,1)),f-vec3(0,0,1)),dot(h3(i+vec3(1,0,1)),f-vec3(1,0,1)),u.x),mix(dot(h3(i+vec3(0,1,1)),f-vec3(0,1,1)),dot(h3(i+vec3(1,1,1)),f-vec3(1,1,1)),u.x),u.y),u.z); }
  float fbm(vec3 p){ float v=0.0,a=0.5; for(int i=0;i<5;i++){ v+=a*n3(p); p*=2.03; a*=0.5; } return v; }`;

function planet(kind, radius) {
  const p = PLANET[kind] || PLANET.earth;
  const mat = new THREE.ShaderMaterial({
    uniforms: { A: { value: new THREE.Color(p.a) }, B: { value: new THREE.Color(p.b) }, C: { value: new THREE.Color(p.c) },
                land: { value: p.land }, sun: { value: new THREE.Vector3(1, 0.4, 0.6).normalize() }, kind: { value: kind === "earth" ? 0 : kind === "moon" ? 1 : 2 } },
    vertexShader: `varying vec3 vP; varying vec3 vN; void main(){ vP=normalize(position); vN=normalize(normalMatrix*normal); gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);} `,
    fragmentShader: `uniform vec3 A,B,C,sun; uniform float land; uniform int kind; varying vec3 vP; varying vec3 vN; ${NOISE}
      void main(){
        float n=fbm(vP*2.4)*0.5+0.5;
        vec3 col;
        if(kind==0){ col = n>land ? mix(B,C,smoothstep(land,land+0.25,n)) : mix(A*0.7,A,n/land);
                     float cl=smoothstep(0.55,0.75,fbm(vP*3.1+7.0)*0.5+0.5); col=mix(col,vec3(0.95),cl*0.7);
                     col=mix(col,vec3(0.92),smoothstep(0.82,0.9,abs(vP.y))); }
        else if(kind==1){ float cr=smoothstep(0.62,0.66,fbm(vP*6.0+3.0)*0.5+0.5); col=mix(mix(A,C,n),B*0.8,cr); }
        else { col=mix(A,C,n); col=mix(col,B,smoothstep(0.4,0.7,fbm(vP*4.0+1.0)*0.5+0.5)); col=mix(col,vec3(0.95,0.9,0.85),smoothstep(0.88,0.94,abs(vP.y))); }
        float d=max(dot(normalize(vN),normalize((viewMatrix*vec4(sun,0.0)).xyz)),0.0);
        gl_FragColor=vec4(col*(0.12+1.05*d),1.0);
      }`,
  });
  const g = new THREE.Group();
  const sphere = new THREE.Mesh(new THREE.SphereGeometry(radius, 96, 64), mat);
  g.add(sphere);
  if (p.atm) {
    const atm = new THREE.Mesh(new THREE.SphereGeometry(radius * 1.06, 64, 48), new THREE.ShaderMaterial({
      uniforms: { c: { value: new THREE.Color(p.atm) } }, transparent: true, side: THREE.BackSide, blending: THREE.AdditiveBlending, depthWrite: false,
      vertexShader: "varying vec3 vN; void main(){ vN=normalize(normalMatrix*normal); gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);} ",
      fragmentShader: "uniform vec3 c; varying vec3 vN; void main(){ float i=pow(0.72-dot(vN,vec3(0,0,1.0)),3.0); gl_FragColor=vec4(c,1.0)*i*1.6; }",
    }));
    g.add(atm);
  }
  g.userData.sphere = sphere;
  return g;
}

function terrain(kind) {
  const geo = new THREE.CircleGeometry(30, 160, 0, Math.PI * 2);
  geo.rotateX(-Math.PI / 2);
  const pos = geo.attributes.position;
  const col = [];
  const base = new THREE.Color(kind === "mars" ? 0x5e2410 : 0x3d3a37);
  const hi = new THREE.Color(kind === "mars" ? 0x9a4a24 : 0x77726c);
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i), z = pos.getZ(i);
    const r = Math.hypot(x, z);
    const h = (Math.sin(x * 0.7) * Math.cos(z * 0.6) * 0.25 + Math.sin(x * 2.3 + z * 1.7) * 0.06) * Math.min(1, r / 4)
      + (kind === "moon" ? -0.35 * Math.exp(-((x - 6) ** 2 + (z + 4) ** 2) / 6) : 0);
    pos.setY(i, h);
    const k = Math.min(1, Math.max(0, 0.5 + h * 1.4 + (Math.random() - 0.5) * 0.08));
    const c = base.clone().lerp(hi, k);
    col.push(c.r, c.g, c.b);
  }
  geo.setAttribute("color", new THREE.Float32BufferAttribute(col, 3));
  geo.computeVertexNormals();
  const mesh = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 1, metalness: 0, envMapIntensity: 0.15 }));
  mesh.receiveShadow = true;
  const rocks = new THREE.Group();
  const rockMat = new THREE.MeshStandardMaterial({ color: base.clone().multiplyScalar(0.8), roughness: 1, flatShading: true });
  for (let i = 0; i < 70; i++) {
    const r = new THREE.Mesh(new THREE.DodecahedronGeometry(0.08 + Math.random() * 0.3, 0), rockMat);
    const a = Math.random() * Math.PI * 2, d = 2.5 + Math.random() * 20;
    r.position.set(Math.cos(a) * d, 0, Math.sin(a) * d);
    r.rotation.set(Math.random() * 3, Math.random() * 3, Math.random() * 3);
    r.castShadow = true; r.receiveShadow = true;
    rocks.add(r);
  }
  const g = new THREE.Group();
  g.add(mesh, rocks);
  return g;
}

function stars(n = 1400, r = 90) {
  const geo = new THREE.BufferGeometry();
  const p = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) {
    const v = new THREE.Vector3().randomDirection().multiplyScalar(r * (0.6 + Math.random() * 0.4));
    p.set([v.x, v.y, v.z], i * 3);
  }
  geo.setAttribute("position", new THREE.BufferAttribute(p, 3));
  return new THREE.Points(geo, new THREE.PointsMaterial({ color: 0xf7f4ef, size: 0.18, sizeAttenuation: true, transparent: true, opacity: 0.8, depthWrite: false }));
}

/* ---------------------------------------------------------------- viewer */

export function debugViewer() { return viewer; }

class Viewer {
  constructor() {
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.05;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFShadowMap;
    this.renderer.domElement.className = "viewer-canvas";
    const pmrem = new THREE.PMREMGenerator(this.renderer);
    this.env = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    this.clock = new THREE.Timer();
    this.mixers = [];
    this.container = null;
    this.mode = null;
    this.running = false;
    this.ro = new ResizeObserver(() => this.resize());
  }

  attach(container, mode) {
    this.detach();
    this.container = container;
    this.mode = mode;
    container.prepend(this.renderer.domElement);
    this.ro.observe(container);
    this.buildScene();
    this.resize();
    this.running = true;
    this.clock.reset?.();
    this.renderer.setAnimationLoop((ts) => this.frame(ts));
  }

  detach() {
    this.running = false;
    this.renderer.setAnimationLoop(null);
    if (this.container) this.ro.unobserve(this.container);
    this.renderer.domElement.remove();
    this.container = null;
    this.scene?.traverse((o) => { o.geometry?.dispose?.(); });
    this.scene = null;
  }

  resize() {
    if (!this.container) return;
    const w = this.container.clientWidth, h = this.container.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  lights(scene) {
    scene.add(new THREE.HemisphereLight(0xfff1dc, 0x241c16, 0.55));
    const key = new THREE.DirectionalLight(0xffe2b8, 2.4);
    key.position.set(6, 9, 7);
    key.castShadow = true;
    key.shadow.mapSize.set(1024, 1024);
    key.shadow.camera.left = key.shadow.camera.bottom = -6;
    key.shadow.camera.right = key.shadow.camera.top = 6;
    scene.add(key);
    const rim = new THREE.DirectionalLight(ACCENT, 1.6);
    rim.position.set(-7, 3, -6);
    scene.add(rim);
    this.key = key;
  }

  buildScene() {
    const scene = new THREE.Scene();
    scene.environment = this.env;
    this.scene = scene;
    this.camera = new THREE.PerspectiveCamera(38, 1, 0.05, 400);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.08;
    this.controls.enablePan = false;
    this.lights(scene);
    scene.add(stars());
    this.craftHolder = new THREE.Group();
    scene.add(this.craftHolder);
    this.fit = null;

    if (this.mode === "designer") {
      this.camera.position.set(3.2, 2.2, 4.2);
      this.controls.autoRotate = true;
      this.controls.autoRotateSpeed = 0.9;
      this.controls.minDistance = 1;
      this.controls.maxDistance = 20;
      const ring = new THREE.Mesh(new THREE.RingGeometry(1.6, 1.64, 128), new THREE.MeshBasicMaterial({ color: ACCENT, transparent: true, opacity: 0.45, side: THREE.DoubleSide }));
      ring.rotation.x = -Math.PI / 2; ring.position.y = -1.25;
      const disc = new THREE.Mesh(new THREE.CircleGeometry(1.6, 64), new THREE.ShadowMaterial({ opacity: 0.35 }));
      disc.rotation.x = -Math.PI / 2; disc.position.y = -1.26; disc.receiveShadow = true;
      this.pad = new THREE.Group(); this.pad.add(ring, disc);
      scene.add(this.pad);
    } else {
      this.setupOperations();
    }
    this.rebuild(true);
  }

  /* operations: the craft in orbit around its body, then (Mars/Moon) on the ground */
  setupOperations() {
    const kind = isSurface() ? state.missionType : "earth";
    this.body = planet(kind, 3);
    this.scene.add(this.body);
    this.orbit = new THREE.Mesh(new THREE.TorusGeometry(4.3, 0.008, 6, 200), new THREE.MeshBasicMaterial({ color: ACCENT, transparent: true, opacity: 0.55 }));
    this.orbit.rotation.x = Math.PI / 2.25;
    this.scene.add(this.orbit);
    this.orbitAngle = 0;
    this.camera.position.set(0, 3.2, 11.5);
    this.controls.minDistance = 5;
    this.controls.maxDistance = 30;
    this.controls.autoRotate = false;
    this.landed = false;
    this.alert = new THREE.PointLight(0xdc2626, 0, 3);
    this.scene.add(this.alert);
  }

  land() {
    if (this.landed || !this.scene) return;
    this.landed = true;
    const kind = state.missionType;
    this.scene.remove(this.body, this.orbit);
    this.ground = terrain(kind);
    this.ground.position.y = GROUND_Y;
    this.scene.add(this.ground);
    this.scene.fog = new THREE.Fog(kind === "mars" ? 0x2a140a : 0x141210, 9, 34);
    this.craftHolder.position.set(0, GROUND_Y + 5, 0);
    this.craftHolder.rotation.set(0, 0, 0);
    this.craftHolder.scale.setScalar(1);
    this.alert.intensity = 0;
    this.descent = 0;
    this.camera.position.set(5, 1.2, 6.5);
    this.controls.target.set(0, GROUND_Y + 1, 0);
    this.controls.minDistance = 2.5;
    this.controls.maxDistance = 14;
    this.controls.autoRotate = true;
    this.controls.autoRotateSpeed = 0.5;
  }

  crash() {
    this.crashed = true;
    const flash = new THREE.PointLight(0xff6a2a, 40, 12);
    flash.position.copy(this.craftHolder.position);
    this.scene.add(flash);
    this.flash = flash;
  }

  async rebuild(initial = false) {
    const spec = currentSpec();
    const key = JSON.stringify(spec) + (this.landed ? "L" : "");
    if (!initial && key === this.specKey) return;
    this.specKey = key;
    const result = await assemble(spec);
    if (!result || !this.scene) return;
    const { craft, mixers } = result;
    this.craftHolder.clear();
    this.mixers = mixers;
    this.craftHolder.add(craft);
    const box = new THREE.Box3().setFromObject(craft);
    if (box.isEmpty()) return;
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    const radius = Math.max(size.x, size.y, size.z) || 1;
    // normalise every craft: turntable, small in orbit, bigger on the ground
    const k = (this.mode === "designer" ? 2.6 : this.landed ? 2.2 : 0.9) / radius;
    craft.scale.setScalar(k);
    craft.position.copy(center).multiplyScalar(-k);
    if (this.landed) craft.position.y += (size.y * k) / 2 - 0.15;   // stand on the ground
    if (this.mode === "designer") {
      this.pop = initial ? 1 : 0;              // grow in when a part changes
      this.fit = { dist: 5.6 };
    }
  }

  setProgress(info) { this.progress = info; }

  frame(ts) {
    if (!this.running || !this.scene) return;
    this.clock.update(ts);
    const dt = Math.min(this.clock.getDelta(), 0.05);
    const t = this.clock.getElapsed();
    this.mixers.forEach((m) => m.update(dt));
    if (this.mode === "designer") {
      if (this.pop !== undefined && this.pop < 1) {
        this.pop = Math.min(1, this.pop + dt * 2.2);
        const e = 1 - Math.pow(1 - this.pop, 3);
        this.craftHolder.scale.setScalar(0.85 + 0.15 * e);
      }
      this.craftHolder.position.y = Math.sin(t * 1.2) * 0.05;
      if (this.fit) {
        const dir = this.camera.position.clone().sub(this.controls.target).normalize();
        const want = this.controls.target.clone().add(dir.multiplyScalar(this.fit.dist));
        this.camera.position.lerp(want, 0.06);
        if (this.camera.position.distanceTo(want) < 0.01) this.fit = null;
      }
    } else if (!this.landed) {
      const p = this.progress || {};
      this.body.rotation.y += dt * 0.05;
      this.orbitAngle += dt * (p.paused ? 0.05 : 0.35);
      const a = this.orbitAngle;
      const pos = new THREE.Vector3(Math.cos(a) * 4.3, 0, Math.sin(a) * 4.3).applyEuler(this.orbit.rotation);
      this.craftHolder.position.copy(pos);
      this.craftHolder.lookAt(0, 0, 0);
      this.alert.position.copy(pos);
      this.alert.intensity = p.alert ? 6 + Math.sin(t * 10) * 5 : 0;
    } else {
      if (this.descent < 1 && !this.crashed) {
        this.descent = Math.min(1, this.descent + dt * 0.45);
        const e = 1 - Math.pow(1 - this.descent, 2);
        this.craftHolder.position.y = GROUND_Y + 5 * (1 - e) + (this.progress?.lost ? -0.6 * e : 0);
        if (this.descent === 1 && this.progress?.lost) this.crash();
      }
      if (this.flash) { this.flash.intensity *= 0.94; if (this.flash.intensity < 0.1) { this.scene.remove(this.flash); this.flash = null; } }
    }
    this.controls.update();
    this.renderer.render(this.scene, this.camera);
  }
}

/* ---------------------------------------------------------------- wiring to the game */

let viewer = null;
let failed = false;
let rebuildTimer = null;

function ensure() {
  if (viewer || failed) return viewer;
  try { viewer = new Viewer(); } catch (err) {
    failed = true;
    console.warn("3D view unavailable (WebGL):", err);
  }
  return viewer;
}

function onScreen() {
  const d = document.getElementById("viewport-designer");
  const o = document.getElementById("viewport-operations");
  if (!d && !o) { viewer?.detach(); return; }
  const v = ensure();
  if (!v) return;
  v.attach(d || o, d ? "designer" : "operations");
}

function onOperations(reason) {
  if (!viewer || viewer.mode !== "operations") return;
  if (isSurface()) {
    const f = state.surface.flight;
    const landing = f?.stages?.find((s) => s.id === "landing");
    if (landing && !viewer.landed) {
      viewer.setProgress({ lost: landing.status === "failed" });
      setTimeout(() => { viewer?.land(); viewer?.rebuild(); }, 1200);
    }
    viewer.setProgress({ ...(viewer.progress || {}), alert: f?.status === "AWAITING_DECISION", lost: landing?.status === "failed" });
    return;
  }
  const st = state.mission?.state;
  const reachedDecision = st?.status === "AWAITING_DECISION"
    && state.shownPeriod >= Math.max(0, ...(st.timeline || []).map((x) => x.period));
  viewer.setProgress({ alert: reachedDecision, paused: st?.status === "COMPLETED" });
}

requestAnimationFrame(onScreen);   // the first screen may already be on display

window.addEventListener("smdg:state", (e) => {
  const { reason } = e.detail;
  if (reason === "screen") { requestAnimationFrame(onScreen); return; }
  if (!viewer?.scene) return;
  if (reason === "design" || reason === "replay" || reason === "evaluation") {
    if (viewer.mode === "designer") { clearTimeout(rebuildTimer); rebuildTimer = setTimeout(() => viewer.rebuild(), 80); }
    return;
  }
  onOperations(reason);
});
