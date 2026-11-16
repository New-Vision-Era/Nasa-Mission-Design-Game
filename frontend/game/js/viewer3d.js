/* 3D views: the designer window (spacecraft, orbit or launcher), the launch pad
   (#viewport-launch) and the operations window (#viewport-operations).

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
import { buildRocket, makeFlame, Puffs, makeSky, makeTower } from "./rocket3d.js";

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
const launcherId = () => (isSurface() ? state.surface.selection.launch : state.config.launch_vehicle_id);

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
      this.extra = new THREE.Group();
      scene.add(this.extra);
      this.holderScale = 1;
      this.viewKey = null;
      this.applyView(true);
    } else if (this.mode === "launch") {
      this.setupLaunch();
      return;
    } else {
      this.setupOperations();
    }
    this.rebuild(true);
  }

  /* ---------- designer: which picture fits the open slot ---------- */
  designerKey() {
    if (isSurface()) {
      const s = state.surface;
      if (s.slot !== "launch") return { view: "craft" };
      const inspected = s.inspect && s.catalog?.categories?.launch?.[s.inspect] ? s.inspect : null;
      return { view: "launcher", id: inspected || s.selection.launch || null };
    }
    const d = state.designer;
    if (d.slot === "orbit") return { view: "orbit", id: (d.inspect?.slot === "orbit" && d.inspect.id) || state.config.orbit_id || null };
    if (d.slot === "launcher") return { view: "launcher", id: (d.inspect?.slot === "launcher" && d.inspect.id) || state.config.launch_vehicle_id || null };
    return { view: "craft" };
  }

  applyView(force = false) {
    const k = this.designerKey();
    const key = JSON.stringify(k);
    if (!force && key === this.viewKey) return false;
    const viewChanged = !this.viewKey || JSON.parse(this.viewKey).view !== k.view;
    this.viewKey = key;
    this.view = k.view;
    this.extra.clear();
    this.orbitPaths = [];
    this.pad.visible = k.view === "craft" || (k.view === "launcher" && Boolean(k.id));
    this.craftHolder.visible = k.view !== "launcher";
    this.controls.autoRotate = true;
    const target = new THREE.Vector3();
    if (k.view === "orbit") {
      const R = 1.2;
      this.earth = planet("earth", R);
      this.extra.add(this.earth);
      const eq = new THREE.Mesh(new THREE.TorusGeometry(R * 1.04, 0.004, 6, 160), new THREE.MeshBasicMaterial({ color: 0xf7f4ef, transparent: true, opacity: 0.18 }));
      eq.rotation.x = Math.PI / 2;
      this.extra.add(eq);
      const orbits = state.catalog?.categories?.orbits || [];
      const shown = k.id ? orbits.filter((o) => o.id === k.id) : orbits;
      this.orbitPaths = shown.map((o) => {
        const radius = R * (1 + (o.altitude_km / 6371) * 5);      // altitude exaggerated x5 so 400 and 700 km look different
        const ring = new THREE.Mesh(new THREE.TorusGeometry(radius, k.id ? 0.011 : 0.006, 8, 240),
          new THREE.MeshBasicMaterial({ color: ACCENT, transparent: true, opacity: k.id ? 0.95 : 0.35 }));
        ring.rotation.x = Math.PI / 2;
        const tilt = new THREE.Group();
        tilt.add(ring);
        tilt.rotation.set(0, 0.5, THREE.MathUtils.degToRad(o.inclination_deg));
        this.extra.add(tilt);
        return { tilt, radius };
      });
      this.holderScale = k.id ? 0.16 : 0;
      this.fit = { dist: 6.8 };
    } else if (k.view === "launcher") {
      const ids = k.id ? [k.id] : (isSurface() ? Object.keys(state.surface.catalog?.categories?.launch || {}) : (state.catalog?.categories?.launch_vehicles || []).map((r) => r.id));
      const rockets = ids.map((id) => ({ id, R: buildRocket(id) }));
      const tallest = Math.max(...rockets.map((x) => x.R.height));
      let x = 0;
      const gap = 0.55;
      rockets.forEach(({ R }, i) => {
        const sc = k.id ? 3.3 / R.height : 3.3 / tallest;          // line-up keeps the real height ratio
        R.group.scale.setScalar(sc);
        R.group.position.y = -1.25 - R.nozzle1 * sc;
        const w = Math.max(R.radius * 2, 1) * sc * (R.look.boosters ? 2.2 : 1);
        if (i) x += gap + w / 2;
        R.group.position.x = x;
        x += w / 2;
        this.extra.add(R.group);
      });
      this.extra.children.forEach((g) => { g.position.x -= x / 2; });
      target.set(0, 0.45, 0);
      this.controls.autoRotate = Boolean(k.id);
      this.fit = { dist: k.id ? 7 : 8.5 };
      if (!k.id) this.camera.position.set(0, 1.2, 8.5);
      this.holderScale = 1;
    } else {
      this.holderScale = 1;
      this.fit = { dist: 5.6 };
    }
    this.controls.target.copy(target);
    this.craftHolder.position.set(0, 0, 0);
    this.craftHolder.rotation.set(0, 0, 0);
    this.craftHolder.scale.setScalar(this.holderScale);
    this.orbitAngle = 0;
    if (viewChanged) this.pop = 0;
    return true;
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

  /* ---------- launch pad: rocket, tower, smoke; driven by cue() from the launch screen ---------- */
  setupLaunch() {
    const scene = this.scene;
    const cam = this.camera;
    this.controls.enabled = false;
    this.controls.autoRotate = false;
    cam.near = 0.1; cam.far = 4000; cam.fov = 42; cam.updateProjectionMatrix();
    this.key.position.set(-40, 22, 30);
    this.key.intensity = 1.5;
    this.key.color.set(0xffc58f);
    Object.assign(this.key.shadow.camera, { left: -22, right: 22, top: 22, bottom: -22, far: 160 });
    this.key.shadow.camera.updateProjectionMatrix();
    this.sky = makeSky();
    scene.add(this.sky);
    this.starField = stars(1800, 800);
    this.starField.material.opacity = 0;
    scene.add(this.starField);
    scene.fog = new THREE.Fog(0x3a2316, 90, 700);

    const ground = new THREE.Mesh(new THREE.CircleGeometry(2000, 64), new THREE.MeshStandardMaterial({ color: 0x241e19, roughness: 1, metalness: 0 }));
    ground.rotation.x = -Math.PI / 2; ground.receiveShadow = true;
    scene.add(ground);
    const pad = new THREE.Mesh(new THREE.CylinderGeometry(9, 10, 0.8, 48), new THREE.MeshStandardMaterial({ color: 0x38332e, roughness: 0.95 }));
    pad.position.y = 0.4; pad.receiveShadow = true;
    scene.add(pad);
    const trench = new THREE.Mesh(new THREE.BoxGeometry(26, 0.05, 3.2), new THREE.MeshStandardMaterial({ color: 0x0d0b0a, roughness: 1 }));
    trench.position.y = 0.82;
    scene.add(trench);

    const R = buildRocket(launcherId());
    const S = 10 / R.height;                               // every vehicle drawn 10 units tall
    R.group.scale.setScalar(S);
    R.group.rotation.order = "ZYX";
    R.group.position.y = 0.8 - R.nozzle1 * S + 0.25;
    scene.add(R.group);
    this.R = R;
    const tower = makeTower(11.5, 1.7);
    const tx = -(R.radius * S * (R.look.boosters ? 2.4 : 1) + 2.4);
    tower.position.set(tx, 0.8, -0.6);
    scene.add(tower);
    this.arm = new THREE.Mesh(new THREE.BoxGeometry(Math.abs(tx) - R.radius * S, 0.25, 0.5), new THREE.MeshStandardMaterial({ color: 0x5b5550, roughness: 0.7, metalness: 0.5 }));
    this.arm.position.set(tx / 2 - R.radius * S / 2 + 0.2, 0.8 + 8.6, -0.3);
    scene.add(this.arm);
    [[-7, 6], [7, -6], [6, 8]].forEach(([x, z]) => {      // pad lights
      const l = new THREE.PointLight(0xffe7c2, 5, 22, 1.8); l.position.set(x, 3, z); scene.add(l);
    });

    // engine plumes: core stage, strap-ons, upper stage
    this.flames1 = [];
    const f1 = makeFlame(R.engineR, R.height * 0.45);
    f1.position.y = R.nozzle1;
    R.stage1.add(f1); this.flames1.push(f1);
    (R.stage1.userData.boosters || []).forEach((b) => {
      const f = makeFlame(b.r, R.height * 0.4); f.position.set(b.x, R.nozzle1 * 0.6, b.z); R.stage1.add(f); this.flames1.push(f);
    });
    this.flame2 = makeFlame(R.engineR2, R.height * 0.55, true);
    this.flame2.position.y = R.nozzle2;
    R.stage2.add(this.flame2);
    this.nozzleGlow = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.puffs?.tex, color: 0xffb060, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, opacity: 0 }));
    this.nozzleGlow.position.y = R.nozzle1 - R.radius;
    R.stage1.add(this.nozzleGlow);
    this.flameLight = new THREE.PointLight(0xff9a40, 0, 90, 1.4);
    this.flameLight.position.y = R.nozzle1 - 4 / S;
    R.stage1.add(this.flameLight);

    this.puffs = new Puffs(scene, 360);
    this.nozzleGlow.material.map = this.puffs.texture;
    this.loose = [];
    this.ls = { phase: "idle", tau: 0, p1: 0, p1T: 0, p2: 0, p2T: 0, speed: 0, pitch: 0, roll: 0, shake: 0, alt: 0, zoom: 1, coast: false, veer: false, staged: false, deployed: false, exploded: false, lost: false, t: 0 };
    this.focus = new THREE.Vector3(0, 5.5, 0);
    this.look = this.focus.clone();
    cam.position.set(12, 3.4, 19);
    cam.lookAt(this.look);
    this.camOffset = null;

    // the player's spacecraft rides in the fairing
    this.payloadMixers = [];
    assemble(currentSpec()).then((res) => {
      if (!res || this.R !== R) return;
      const { craft, mixers } = res;
      const box = new THREE.Box3().setFromObject(craft);
      if (box.isEmpty()) return;
      const size = box.getSize(new THREE.Vector3());
      const room = R.payload.userData.room;
      const k = Math.min((room.r * 1.5) / Math.max(size.x, size.z, 1e-3), (room.h * 0.8) / Math.max(size.y, 1e-3));
      craft.scale.setScalar(k);
      craft.position.copy(box.getCenter(new THREE.Vector3())).multiplyScalar(-k);
      craft.position.y += (size.y * k) / 2;
      R.payload.add(craft);
      this.payloadMixers = mixers;
    });
  }

  cue(name) {
    const L = this.ls;
    if (!L || !this.R) return;
    const R = this.R;
    const dirOf = () => new THREE.Vector3(Math.sin(L.pitch), Math.cos(L.pitch), 0);
    const sideOf = () => new THREE.Vector3(Math.cos(L.pitch), -Math.sin(L.pitch), 0);
    const release = (obj, vel, spin, gravity = 0) => { this.scene.attach(obj); this.loose.push({ obj, vel, spin, gravity }); };
    switch (name) {
      case "ignition": L.phase = "ignition"; L.p1T = 0.55; L.shake = 0.05; this.arm.visible = false; break;
      case "liftoff": L.phase = "flight"; L.tau = 0; L.p1T = 1; L.shake = 0.35; break;
      case "staging": {
        if (L.staged) return;
        L.staged = true;
        L.p1T = 0; L.p1 = 0;
        this.flames1.forEach((f) => f.update(0, 0));
        this.flameLight.intensity = 0;
        release(R.stage1, dirOf().multiplyScalar(L.speed * 0.82), new THREE.Vector3(0.15, 0, 0.35), 9);
        const at = R.stage2.getWorldPosition(new THREE.Vector3());
        for (let i = 0; i < 14; i++) this.puffs.spawn(at, new THREE.Vector3().randomDirection().multiplyScalar(4).addScaledVector(dirOf(), L.speed * 0.9),
          { life: 1.4, size: 0.9, grow: 3, color: 0xe8e2da, opacity: 0.55, drag: 1.2 });
        setTimeout(() => { if (this.ls === L && !L.exploded) L.p2T = 1; }, 450);
        break;
      }
      case "fairing": {
        if (L.fairingGone) return;
        L.fairingGone = true;
        R.fairing.forEach((half, k) => {
          const side = sideOf().multiplyScalar(k === 0 ? 1 : -1);   // half 0 is the +x half
          release(half, dirOf().multiplyScalar(L.speed).addScaledVector(side, 6), new THREE.Vector3(0, 0, k === 0 ? -1.6 : 1.6), 3);
        });
        L.zoom = 0.45;
        break;
      }
      case "deploy": {
        if (L.deployed) return;
        L.deployed = true;
        L.coast = true;
        setTimeout(() => { if (this.ls === L) L.p2T = 0; }, 350);
        this.payload = R.payload;
        release(R.payload, dirOf().multiplyScalar(L.speed + 3), new THREE.Vector3(0.05, 0.25, 0.03), 0);
        L.zoom = 0.14;
        break;
      }
      case "explode": this.explode(); break;
      case "veer": L.veer = true; L.shake = 0.3; break;
      case "nosignal": {
        if (!this.payload) return;
        const beacon = new THREE.PointLight(0xdc2626, 6, 6);
        const dot = new THREE.Mesh(new THREE.SphereGeometry(0.08, 12, 8), new THREE.MeshBasicMaterial({ color: 0xff3b3b }));
        dot.add(beacon);
        this.payload.add(dot);
        this.beacon = { dot, t: 0 };
        const p = this.loose.find((x) => x.obj === this.payload);
        if (p) p.spin.set(1.1, 1.7, 0.6);
        break;
      }
      default: break;
    }
  }

  explode() {
    const L = this.ls, R = this.R;
    if (L.exploded) return;
    L.exploded = true; L.lost = true;
    L.p1T = L.p2T = 0;
    const at = R.group.localToWorld(new THREE.Vector3(0, R.height * 0.45, 0));
    R.group.visible = false;
    this.loose.forEach((x) => { if (x.obj !== this.payload) x.obj.visible = false; });
    const vel = new THREE.Vector3(Math.sin(L.pitch), Math.cos(L.pitch), 0).multiplyScalar(L.speed * 0.25);
    for (let i = 0; i < 46; i++) this.puffs.spawn(at.clone().add(new THREE.Vector3().randomDirection().multiplyScalar(Math.random() * 1.5)),
      new THREE.Vector3().randomDirection().multiplyScalar(5 + Math.random() * 11).add(vel),
      { life: 0.8 + Math.random(), size: 0.9 + Math.random() * 1.2, grow: 3, color: i % 3 ? 0xff9a3a : 0xfff0c0, opacity: 0.9, additive: true, drag: 1.8 });
    for (let i = 0; i < 40; i++) this.puffs.spawn(at.clone().add(new THREE.Vector3().randomDirection().multiplyScalar(2)),
      new THREE.Vector3().randomDirection().multiplyScalar(2 + Math.random() * 5).add(vel),
      { life: 4 + Math.random() * 3, size: 1.6 + Math.random() * 1.5, grow: 3.2, color: 0x3d3532, opacity: 0.75, drag: 0.7, hot: 0.6 });
    const dm = new THREE.MeshStandardMaterial({ color: 0x2a2522, emissive: 0xff7a1a, emissiveIntensity: 1.4, roughness: 0.6 });
    for (let i = 0; i < 26; i++) {
      const piece = new THREE.Mesh(new THREE.BoxGeometry(0.1 + Math.random() * 0.4, 0.1 + Math.random() * 0.5, 0.08 + Math.random() * 0.2), dm);
      piece.position.copy(at);
      this.scene.add(piece);
      this.loose.push({ obj: piece, vel: new THREE.Vector3().randomDirection().multiplyScalar(6 + Math.random() * 14).add(vel), spin: new THREE.Vector3(Math.random() * 6, Math.random() * 6, Math.random() * 6), gravity: 9 });
    }
    this.flash = new THREE.PointLight(0xff8a3a, 1500, 200, 1.4);
    this.flash.position.copy(at);
    this.scene.add(this.flash);
    this.focus.copy(at);
    L.shake = 0.9;
    L.zoom = 1.7;
  }

  frameLaunch(_dt, t) {
    const L = this.ls, R = this.R, cam = this.camera;
    // real elapsed time, so a slow computer shows the same flight, just with fewer frames
    const now = performance.now();
    const dt = Math.min(0.25, Math.max(0.001, ((now - (this.lastLaunchFrame || now)) / 1000) || 0.016));
    this.lastLaunchFrame = now;
    L.t += dt;
    L.p1 += (L.p1T - L.p1) * Math.min(1, dt * (L.p1T > L.p1 ? 3 : 8));
    L.p2 += (L.p2T - L.p2) * Math.min(1, dt * 5);
    const dir = new THREE.Vector3(Math.sin(L.pitch), Math.cos(L.pitch), 0);

    if (L.phase === "flight" && !L.exploded) {
      L.tau += dt;
      if (L.veer) { L.pitch += dt * 1.1; L.roll += dt * 3; }
      else { const want = L.tau > 2 ? Math.min(0.8, (L.tau - 2) * 0.17) : 0; L.pitch += (want - L.pitch) * Math.min(1, dt * 1.5); }
      const thrust = L.coast ? 0 : (L.p1 + L.p2 > 0.2 ? 1 : 0.15);
      L.speed += (6 + 6 * L.tau) * thrust * dt;
      R.group.position.addScaledVector(dir, L.speed * dt);
      R.group.rotation.set(0, L.roll, -L.pitch);
      L.alt = THREE.MathUtils.smoothstep(L.tau, 1.2, 6.5);
    }
    // smoke from the pad while the engines are near the ground
    const nearPad = R.group.position.y < 30;
    if (L.p1 > 0.08 && nearPad && !L.staged && !L.exploded) {
      const n = Math.ceil(dt * 260 * L.p1);
      for (let i = 0; i < n; i++) {
        const side = Math.random() < 0.5 ? -1 : 1;
        this.puffs.spawn(new THREE.Vector3((Math.random() - 0.5) * 3, 1.2, (Math.random() - 0.5) * 2.5),
          new THREE.Vector3(side * (10 + Math.random() * 14), 1 + Math.random() * 4, (Math.random() - 0.5) * 6),
          { life: 4 + Math.random() * 3, size: 2 + Math.random() * 1.5, grow: 3.6, color: 0xcbc2b6, opacity: 0.55 * L.p1, drag: 0.55, hot: 1 });
      }
    }
    // exhaust trail behind the first stage
    if (L.phase === "flight" && !L.staged && !L.exploded && L.p1 > 0.3 && R.group.position.y > 2) {
      const noz = R.stage1.localToWorld(new THREE.Vector3(0, R.nozzle1 - R.height * 0.12, 0));
      const n = Math.ceil(dt * 120);
      for (let i = 0; i < n; i++) this.puffs.spawn(noz.clone().addScaledVector(dir, -Math.random() * L.speed * dt),
        dir.clone().multiplyScalar(-L.speed * 0.12).add(new THREE.Vector3().randomDirection().multiplyScalar(1.2)),
        { life: 3.5, size: 1.1, grow: 5, color: 0xdcd3c8, opacity: 0.45 * (1 - L.alt * 0.85), drag: 0.25, hot: 0.7 });
    }
    // plumes and their light
    const sputter = L.veer ? (Math.random() < 0.35 ? 0.2 : 1) : 1;
    this.flames1.forEach((f) => f.update(t, L.staged ? 0 : L.p1 * (1 + L.alt * 0.6)));
    this.flame2.update(t, L.p2 * sputter * (L.exploded ? 0 : 1));
    if (!L.staged) this.flameLight.intensity = L.p1 * (240 + Math.random() * 80);
    const glow = L.staged || L.exploded ? 0 : L.p1;
    this.nozzleGlow.material.opacity = glow * (0.75 + Math.random() * 0.25);
    this.nozzleGlow.scale.setScalar((R.engineR * 7 + R.radius * 4) * (0.9 + Math.random() * 0.2));
    // free-flying pieces
    this.loose.forEach((x) => {
      x.vel.y -= x.gravity * dt;
      x.obj.position.addScaledVector(x.vel, dt);
      x.obj.rotation.x += x.spin.x * dt; x.obj.rotation.y += x.spin.y * dt; x.obj.rotation.z += x.spin.z * dt;
    });
    if (L.deployed) this.payloadMixers.forEach((m) => m.update(dt));
    if (this.beacon) {
      this.beacon.t += dt;
      const on = this.beacon.t < 1.8 && Math.sin(this.beacon.t * 14) > 0;
      this.beacon.dot.visible = on;
    }
    if (this.flash) { this.flash.intensity *= Math.exp(-dt * 3.5); if (this.flash.intensity < 1) { this.scene.remove(this.flash); this.flash = null; } }
    this.puffs.update(dt);

    // sky: dusk to space
    this.sky.material.uniforms.uAlt.value = L.alt;
    this.sky.position.copy(cam.position);
    this.starField.position.copy(cam.position);
    this.starField.material.opacity = L.alt * 0.95;
    this.scene.fog.color.setRGB(0.227 * (1 - L.alt), 0.137 * (1 - L.alt), 0.086 * (1 - L.alt));

    // camera: wide pad shot, then look up, then chase the vehicle (or what is left of it)
    if (!L.exploded) {
      const target = this.payload && L.deployed ? this.payload.getWorldPosition(new THREE.Vector3())
        : R.group.localToWorld(new THREE.Vector3(0, R.height * (L.fairingGone ? 0.85 : L.staged ? 0.75 : 0.5), 0));
      this.focus.copy(target);
    }
    if (L.phase !== "flight" || L.tau < 1.6) {
      if (L.phase !== "flight") cam.position.lerp(new THREE.Vector3(10, 2.8, 16), dt * 0.12);
      this.look.lerp(L.phase === "flight" ? this.focus : new THREE.Vector3(0, 5.5, 0), Math.min(1, dt * 3));
    } else {
      if (!this.camOffset) this.camOffset = cam.position.clone().sub(this.focus);
      const want = new THREE.Vector3(10, -4.5, 17).multiplyScalar(L.zoom);
      this.camOffset.lerp(want, Math.min(1, dt * (L.exploded ? 0.8 : 1.4)));
      cam.position.copy(this.focus).add(this.camOffset);
      this.look.lerp(this.focus, Math.min(1, dt * 6));
    }
    const base = L.phase === "flight" && !L.staged ? 0.1 * L.p1 * (1 - L.alt) : L.phase === "ignition" ? 0.04 : 0;
    L.shake = Math.max(base, L.shake * Math.exp(-dt * 1.6));
    cam.lookAt(this.look);
    if (L.shake > 0.001) cam.position.add(new THREE.Vector3((Math.random() - 0.5) * L.shake, (Math.random() - 0.5) * L.shake, 0));
    this.renderer.render(this.scene, cam);
  }


  frame(ts) {
    if (!this.running || !this.scene) return;
    this.clock.update(ts);
    const dt = Math.min(this.clock.getDelta(), 0.05);
    const t = this.clock.getElapsed();
    this.mixers.forEach((m) => m.update(dt));
    if (this.mode === "launch") { this.frameLaunch(dt, t); return; }
    if (this.mode === "designer") {
      if (this.pop !== undefined && this.pop < 1) {
        this.pop = Math.min(1, this.pop + dt * 2.2);
        const e = 1 - Math.pow(1 - this.pop, 3);
        this.craftHolder.scale.setScalar((0.85 + 0.15 * e) * this.holderScale);
        this.extra.scale.setScalar(0.92 + 0.08 * e);
      }
      if (this.view === "orbit") {
        this.earth.rotation.y += dt * 0.08;
        const path = this.orbitPaths.length === 1 ? this.orbitPaths[0] : null;
        if (path) {
          this.orbitAngle += dt * 0.6;
          const pos = new THREE.Vector3(Math.cos(this.orbitAngle) * path.radius, 0, Math.sin(this.orbitAngle) * path.radius).applyEuler(path.tilt.rotation);
          this.craftHolder.position.copy(pos);
          this.craftHolder.lookAt(0, 0, 0);
        }
      } else if (this.view === "craft") this.craftHolder.position.y = Math.sin(t * 1.2) * 0.05;
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
  const l = document.getElementById("viewport-launch");
  if (!d && !o && !l) { viewer?.detach(); return; }
  const v = ensure();
  if (!v) return;
  v.attach(d || l || o, d ? "designer" : l ? "launch" : "operations");
}

/* The launch screen drives the pad scene: ignition, liftoff, staging, fairing, deploy, explode, veer, nosignal. */
export function launchCue(name) {
  if (viewer?.mode === "launch") viewer.cue(name);
}
export const has3D = () => Boolean(ensure());

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
  if (reason === "design" || reason === "replay" || reason === "evaluation" || reason === "designer-tab") {
    if (viewer.mode === "designer") {
      clearTimeout(rebuildTimer);
      rebuildTimer = setTimeout(() => { if (viewer?.mode === "designer" && viewer.scene) { viewer.applyView(); viewer.rebuild(); } }, 60);
    }
    return;
  }
  if (viewer.mode === "launch") return;
  onOperations(reason);
});
