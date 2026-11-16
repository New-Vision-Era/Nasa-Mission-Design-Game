/* Catalog helpers: which slot uses which catalog category, and how a component is
   summarised on a card (two numbers) and in the inspector (a few specs).
   Every number comes from the backend catalog; null stays "n/p" (not published). */

export const ICONS = {
  platform: '<svg viewBox="0 0 24 24"><rect x="8" y="8" width="8" height="8" rx="1"/><path d="M2 10h6M2 14h6M16 10h6M16 14h6M12 4v4M12 16v4"/></svg>',
  instrument: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><circle cx="12" cy="12" r="8"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2"/></svg>',
  solar: '<svg viewBox="0 0 24 24"><rect x="3" y="6" width="18" height="12" rx="1"/><path d="M9 6v12M15 6v12M3 12h18"/></svg>',
  battery: '<svg viewBox="0 0 24 24"><rect x="3" y="7" width="16" height="10" rx="2"/><path d="M21 10v4M7 10v4M11 10v4"/></svg>',
  eps: '<svg viewBox="0 0 24 24"><path d="M13 2 5 14h6l-1 8 8-12h-6z"/></svg>',
  comms: '<svg viewBox="0 0 24 24"><path d="M5 19a10 10 0 0 1 0-14M19 5a10 10 0 0 1 0 14M8 16a6 6 0 0 1 0-8M16 8a6 6 0 0 1 0 8"/><circle cx="12" cy="12" r="1.5"/></svg>',
  adcs: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 3v4M12 17v4M3 12h4M17 12h4"/><circle cx="12" cy="12" r="2"/></svg>',
  propulsion: '<svg viewBox="0 0 24 24"><path d="M12 2c3 3 4 7 4 11H8c0-4 1-8 4-11z"/><path d="M9 17l-1 5M15 17l1 5M12 17v5"/></svg>',
  orbit: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><ellipse cx="12" cy="12" rx="10" ry="4.5" transform="rotate(-20 12 12)"/></svg>',
  launcher: '<svg viewBox="0 0 24 24"><path d="M12 2c2.5 2.5 3.5 6 3.5 10v5h-7v-5C8.5 8 9.5 4.5 12 2z"/><path d="M8.5 13 6 17v2h2.5M15.5 13 18 17v2h-2.5M10 21h4"/></svg>',
  none: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/><path d="M6.5 17.5l11-11"/></svg>',
};

const n = (v, digits = 1) => (v === null || v === undefined || Number.isNaN(v) ? null : Number(v).toFixed(digits).replace(/\.0+$/, ""));

export function usd(v) {
  if (v === null || v === undefined) return "n/p";
  if (Math.abs(v) >= 1e6) return `$${n(v / 1e6, 2)}M`;
  if (Math.abs(v) >= 1e3) return `$${n(v / 1e3, 0)}k`;
  return `$${n(v, 0)}`;
}
export const unit = (v, u, d = 1) => (n(v, d) === null ? "n/p" : `${n(v, d)} ${u}`);

export function gbPerDay(bits) { return bits == null ? null : bits / 8e9; }

/* Slots shown in the designer. `category` is the catalog key. */
export const SLOTS = {
  platform:   { tab: "spacecraft", label: "Platform",   category: "platforms",             multi: false, required: true,  icon: "platform" },
  science:    { tab: "spacecraft", label: "Science",    category: "instruments",           multi: true,  required: true,  icon: "instrument" },
  power:      { tab: "spacecraft", label: "Power",      category: "power_systems",         multi: true,  required: false, icon: "solar" },
  comms:      { tab: "spacecraft", label: "Comms",      category: "communication_systems", multi: true,  required: true,  icon: "comms" },
  adcs:       { tab: "spacecraft", label: "Attitude",   category: "adcs_systems",          multi: false, required: true,  icon: "adcs" },
  propulsion: { tab: "spacecraft", label: "Propulsion", category: "propulsion_systems",    multi: false, required: false, icon: "propulsion", allowNone: true },
  orbit:      { tab: "orbit",      label: "Orbit",      category: "orbits",                multi: false, required: true,  icon: "orbit" },
  launcher:   { tab: "launcher",   label: "Launcher",   category: "launch_vehicles",       multi: false, required: true,  icon: "launcher" },
};

/* Engine related_step -> designer slot */
export const STEP_TO_SLOT = {
  platform: "platform", instruments: "science", power: "power", communications: "comms",
  adcs: "adcs", propulsion: "propulsion", orbit: "orbit", launch_vehicle: "launcher", budget: "platform",
  volume: "science", mass: "science", pointing: "adcs",
};

export function iconFor(slot, rec) {
  if (slot === "power" && rec) return ICONS[{ solar_array: "solar", battery: "battery", power_conditioning: "eps" }[rec.family] || "solar"];
  return ICONS[SLOTS[slot]?.icon || "none"];
}

/* Two short metrics for a card. */
export function cardMetrics(slot, r) {
  switch (slot) {
    case "platform": return `${unit(r.payload_mass_capacity_kg, "kg", 0)} · ${unit(r.payload_average_power_w, "W", 0)} · ${usd(r.price_usd)}`;
    case "science": return r.gsd_m != null ? `${unit(r.gsd_m, "m")} · ${unit(r.swath_km, "km")} swath` : `${unit(r.mass_kg, "kg", 2)} · ${unit(r.power_operating_w, "W")}`;
    case "power":
      if (r.family === "solar_array") return `${unit(r.peak_power_w, "W")} peak · ${unit(r.mass_kg, "kg", 2)}`;
      if (r.family === "battery") return `${unit(r.energy_wh, "Wh")} · ${unit(r.mass_kg, "kg", 2)}`;
      return `EPS · ${unit(r.mass_kg, "kg", 2)}`;
    case "comms": return `${r.band} · ${rate(r.downlink_kbps)}`;
    case "adcs": return `${unit(r.pointing_accuracy_deg, "°", 3)} · ${unit(r.mass_kg, "kg", 2)}`;
    case "propulsion": return `${r.family.replace("_", " ")} · ${unit(r.total_impulse_ns, "Ns", 0)}`;
    case "orbit": return `${unit(r.altitude_km, "km", 0)} · ${r.sun_synchronous ? "SSO" : `${n(r.inclination_deg)}°`}`;
    case "launcher": return `${usd(r.price_usd)} · ${maxCapacity(r)}`;
    default: return "";
  }
}

function rate(kbps) {
  if (kbps == null) return "n/p";
  if (kbps >= 1000) return `${n(kbps / 1000, 1)} Mbps`;
  return `${n(kbps, 1)} kbps`;
}

function maxCapacity(r) {
  const pts = r.capacity_points || [];
  if (!pts.length) return "rideshare";
  return `${unit(Math.max(...pts.map((p) => p.mass_kg)), "kg", 0)}`;
}

/* Inspector specs: [label, value, kind?] — at most 5. */
export function inspectorSpecs(slot, r) {
  const kind = (v) => (v === "estimate" ? "estimate" : v === "gameplay_assumption" ? "assumption" : "");
  switch (slot) {
    case "platform": return [
      ["Payload capacity", unit(r.payload_mass_capacity_kg, "kg", 0)],
      ["Payload power", unit(r.payload_average_power_w, "W", 0)],
      ["Bus mass", unit(r.bus_mass_kg, "kg", 0), kind(r.bus_mass_basis)],
      ["Payload bay", r.payload_volume_mm ? r.payload_volume_mm.join("×") + " mm" : "n/p"],
      ["Price", usd(r.price_usd)],
    ];
    case "science": return [
      ["Type", (r.family || "").replaceAll("_", " ")],
      ["Resolution (500 km)", unit(r.gsd_m, "m")],
      ["Swath", unit(r.swath_km, "km")],
      ["Mass · Power", `${unit(r.mass_kg, "kg", 2)} · ${unit(r.power_operating_w, "W")}`],
      ["TRL", r.trl ?? "n/p"],
    ];
    case "power":
      if (r.family === "solar_array") return [["Peak power", unit(r.peak_power_w, "W")], ["Type", (r.type || "").replaceAll("_", " ")], ["Mass", unit(r.mass_kg, "kg", 3)]];
      if (r.family === "battery") return [["Energy", unit(r.energy_wh, "Wh")], ["Mass", unit(r.mass_kg, "kg", 3)]];
      return [["Role", "Power conditioning"], ["Mass", unit(r.mass_kg, "kg", 3)]];
    case "comms": return [
      ["Band", `${r.band} · ${(r.ground_station_type || "").replace("_", "-")}`],
      ["Downlink", rate(r.downlink_kbps)],
      ["Receives commands", r.can_receive_commands ? "yes" : "no"],
      ["Transmit power", unit(r.power_tx_w, "W")],
      ["Mass", unit(r.mass_kg, "kg", 2)],
    ];
    case "adcs": return [
      ["Pointing accuracy", unit(r.pointing_accuracy_deg, "°", 3)],
      ["Star tracker", r.has_star_tracker ? "yes" : "no"],
      ["Mass", unit(r.mass_kg, "kg", 3)],
      ["TRL", r.trl ?? "n/p"],
    ];
    case "propulsion": return [
      ["Family", (r.family || "").replace("_", " ")],
      ["Total impulse", unit(r.total_impulse_ns, "Ns", 0)],
      ["Thrust", unit(r.thrust_n, "N", 3)],
      ["Wet mass", unit(r.wet_mass_kg, "kg", 2)],
    ];
    case "orbit": return [
      ["Altitude", unit(r.altitude_km, "km", 0)],
      ["Inclination", unit(r.inclination_deg, "°")],
      ["Sun-synchronous", r.sun_synchronous ? "yes" : "no"],
      ["Period", unit(r.period_min, "min")],
      ["Orbits / day", n(r.orbits_per_day, 1) ?? "n/p"],
    ];
    case "launcher": return [
      ["Price", r.price_usd != null ? usd(r.price_usd) : launcherPrice(r) != null ? `~${usd(launcherPrice(r))}` : "n/p", r.price_usd == null || r.price_type === "publicly_stated_estimate" ? "estimate" : ""],
      ["Capacity", maxCapacity(r)],
      ["Height", LAUNCHER_SIZE[r.id] ? `${LAUNCHER_SIZE[r.id].h} m` : "n/p"],
      ["Reaches", (r.orbit_ids_supported || []).length + " orbits"],
    ];
    default: return [];
  }
}

export const NONE_CARD = { id: null, name: "No propulsion", none: true };

/* Published vehicle sizes (m), used for the 3D rockets and the inspector. */
export const LAUNCHER_SIZE = {
  rocket_lab_electron: { h: 18, d: 1.2 }, firefly_alpha: { h: 29.5, d: 2 }, isro_sslv: { h: 34, d: 2 },
  vega_c: { h: 35, d: 3.4 }, isro_pslv_xl: { h: 44, d: 2.8 }, spacex_falcon9_dedicated: { h: 70, d: 3.7 },
  spacex_transporter_rideshare: { h: 70, d: 3.7 },
};
export const launcherCapacityKg = (r) => { const p = r.capacity_points || []; return p.length ? Math.max(...p.map((x) => x.mass_kg)) : null; };
export const launcherPrice = (r) => r.price_usd ?? (r.price_estimate ? (r.price_estimate.min_usd + r.price_estimate.max_usd) / 2 : null);
const kgf = (v) => `${n(v, v < 10 ? 2 : 0)} kg`;
const wf = (v) => `${n(v, v < 10 ? 1 : 0)} W`;

/* Inspector comparison bars: [label, get, better, fmt] */
export function compareMetrics(slot, r) {
  switch (slot) {
    case "platform": return [["Payload room", (x) => x.payload_mass_capacity_kg, "high", kgf], ["Payload power", (x) => x.payload_average_power_w, "high", wf], ["Price", (x) => x.price_usd, "low", usd]];
    case "science": return [["Sharpness", (x) => x.gsd_m, "low", (v) => `${n(v, 1)} m`], ["Swath", (x) => x.swath_km, "high", (v) => `${n(v, 0)} km`], ["Mass", (x) => x.mass_kg, "low", kgf], ["Power draw", (x) => x.power_operating_w, "low", wf]];
    case "power":
      if (r.family === "solar_array") return [["Power", (x) => (x.family === r.family ? x.peak_power_w : null), "high", wf], ["Mass", (x) => (x.family === r.family ? x.mass_kg : null), "low", kgf]];
      if (r.family === "battery") return [["Energy", (x) => (x.family === r.family ? x.energy_wh : null), "high", (v) => `${n(v, 0)} Wh`], ["Mass", (x) => (x.family === r.family ? x.mass_kg : null), "low", kgf]];
      return [["Mass", (x) => (x.family === r.family ? x.mass_kg : null), "low", kgf]];
    case "comms": return [["Data rate", (x) => x.downlink_kbps, "high", rate], ["Transmit power", (x) => x.power_tx_w, "low", wf], ["Mass", (x) => x.mass_kg, "low", kgf]];
    case "adcs": return [["Pointing", (x) => x.pointing_accuracy_deg, "low", (v) => `${n(v, 3)}°`], ["Mass", (x) => x.mass_kg, "low", kgf]];
    case "propulsion": return [["Total impulse", (x) => x.total_impulse_ns, "high", (v) => `${n(v, 0)} Ns`], ["Thrust", (x) => x.thrust_n, "high", (v) => `${n(v, 3)} N`], ["Mass", (x) => x.wet_mass_kg, "low", kgf]];
    case "orbit": return [["Image sharpness", (x) => x.resolution_scale_vs_500km, "low", (v) => `×${n(v, 2)}`], ["Pass length", (x) => x.max_pass_duration_min_10deg, "high", (v) => `${n(v, 1)} min`], ["Time in shadow", (x) => x.max_eclipse_min, "low", (v) => `${n(v, 0)} min`]];
    case "launcher": return [["Lift capacity", launcherCapacityKg, "high", kgf], ["Price", launcherPrice, "low", usd], ["Orbits reached", (x) => (x.orbit_ids_supported || []).length, "high", (v) => `${v}`]];
    default: return [];
  }
}

/* Category glyph used in summaries */
export function slotOfCategory(category) {
  return Object.keys(SLOTS).find((k) => SLOTS[k].category === category);
}
