"""Mars rover mission rules, separate from the Earth-observation engine.

Values are educational game-balancing assumptions, not NASA specifications.
"""
from __future__ import annotations
from typing import Any

BUDGET_LIMIT_M, MASS_LIMIT_KG, BASE_LOAD_W, SCIENCE_MAX = 100, 2000, 200, 100
EQUIPMENT: dict[str, dict[str, dict[str, Any]]] = {
 "launch": {
  "lv-standard":{"name":"Standard Launch Vehicle","cost":25,"mass":0,"payloadKg":1800},
  "lv-heavy":{"name":"Heavy Launch Vehicle","cost":40,"mass":0,"payloadKg":3000}},
 "power": {
  "pw-solar":{"name":"Solar Panels","cost":10,"mass":150,"powerW":500},
  "pw-nuclear":{"name":"Advanced Nuclear Power System","cost":20,"mass":250,"powerW":900}},
 "comm": {
  "cm-basic":{"name":"Basic Antenna","cost":5,"mass":30,"efficiency":.70},
  "cm-advanced":{"name":"Advanced Antenna","cost":12,"mass":60,"efficiency":.95}},
 "instruments": {
  "ins-camera":{"name":"High-Resolution Camera","cost":5,"mass":50,"scienceValue":20,"powerW":50},
  "ins-spectro":{"name":"Spectrometer","cost":8,"mass":100,"scienceValue":35,"powerW":100},
  "ins-drill":{"name":"Sample Collection Drill","cost":12,"mass":200,"scienceValue":45,"powerW":200}},
 "landing": {
  "ld-standard":{"name":"Standard Landing System","cost":8,"mass":250,"reliability":.75},
  "ld-advanced":{"name":"Advanced Landing System","cost":15,"mass":350,"reliability":.95}}
}

def _normalise(raw: dict[str, Any]) -> dict[str, Any]:
    s={k:raw.get(k) for k in ("launch","power","comm","landing")}
    instruments=raw.get("instruments",[])
    if not isinstance(instruments,list): raise ValueError("instruments must be a list")
    if len(instruments)!=len(set(instruments)): raise ValueError("An instrument can only be selected once")
    s["instruments"]=instruments
    for category in ("launch","power","comm","landing"):
        value=s[category]
        if value is not None and value not in EQUIPMENT[category]:
            raise ValueError(f"Unknown {category} option: {value}")
    for value in instruments:
        if value not in EQUIPMENT["instruments"]: raise ValueError(f"Unknown instrument option: {value}")
    return s

def calculate(selection: dict[str, Any]) -> dict[str, Any]:
    s=_normalise(selection)
    chosen=[EQUIPMENT[c][s[c]] for c in ("launch","power","comm","landing") if s[c]]
    instruments=[EQUIPMENT["instruments"][i] for i in s["instruments"]]
    chosen += instruments
    cost=sum(x["cost"] for x in chosen); mass=sum(x["mass"] for x in chosen)
    launch=EQUIPMENT["launch"].get(s["launch"]); power=EQUIPMENT["power"].get(s["power"])
    comm=EQUIPMENT["comm"].get(s["comm"]); landing=EQUIPMENT["landing"].get(s["landing"])
    payload=launch["payloadKg"] if launch else 0
    mass_limit=min(payload,MASS_LIMIT_KG) if payload else MASS_LIMIT_KG
    available=power["powerW"] if power else 0
    required=BASE_LOAD_W+sum(i["powerW"] for i in instruments)
    science=sum(i["scienceValue"] for i in instruments)
    missing=[label for key,label in (("launch","Launch Vehicle"),("power","Power System"),
      ("comm","Communication System"),("instruments","Scientific Instruments"),("landing","Landing System"))
      if not (s[key] if key!="instruments" else s[key])]
    checks=[
     {"id":"complete","hard":False,"pass":not missing,"label":"Every system configured",
      "detail":"All five categories have a choice." if not missing else "Still needed: "+", ".join(missing)+".","fail":""},
     {"id":"budget","hard":True,"pass":cost<=BUDGET_LIMIT_M,"label":"Within budget",
      "detail":f"${cost}M of ${BUDGET_LIMIT_M}M used.","fail":f"Over budget: ${cost}M against ${BUDGET_LIMIT_M}M."},
     {"id":"mass","hard":True,"pass":mass<=mass_limit,"label":"Within mass limit",
      "detail":f"{mass} kg of {mass_limit} kg allowed.","fail":f"Too heavy: {mass} kg exceeds {mass_limit} kg."},
     {"id":"payload","hard":True,"pass":not payload or mass<=payload,"label":"Fits launch payload",
      "detail":f"{mass} kg of {payload} kg vehicle capacity." if payload else "Choose a launch vehicle.",
      "fail":f"Too heavy for launch vehicle: {mass} kg against {payload} kg."},
     {"id":"power","hard":True,"pass":not power or required<=available,"label":"Power covers the load",
      "detail":f"{required} W required, {available} W available." if power else "Choose a power system.",
      "fail":f"Not enough power: {required} W required, {available} W available."}]
    resources={"cost":cost,"budgetLimit":100,"budgetRemaining":100-cost,"budgetRatio":cost/100,
      "mass":mass,"massLimit":mass_limit,"massRatio":mass/mass_limit if mass_limit else 0,
      "payload":payload,"power":available,"required":required,"powerRatio":required/available if available else 0,
      "science":science,"scienceMax":SCIENCE_MAX}
    return {"selection":s,"valid":all(c["pass"] for c in checks),"hardOk":all(c["pass"] for c in checks if c["hard"]),
      "complete":not missing,"missing":missing,"checks":checks,"resources":resources,
      "derived":{"commEfficiency":comm["efficiency"] if comm else 0,
                 "landingReliability":landing["reliability"] if landing else 0}}

def simulate(selection: dict[str, Any]) -> dict[str, Any]:
    v=calculate(selection)
    if not v["valid"]: raise ValueError("Mission design is incomplete or violates a hard constraint")
    s,r,d=v["selection"],v["resources"],v["derived"]
    mass_ratio=r["mass"]/r["massLimit"] if r["massLimit"] else 0
    launch_status="failure" if r["mass"]>r["payload"] else ("warning" if r["mass"]/r["payload"]>=.9 else "success")
    power_factor=min(1.0,r["power"]/r["required"]) if r["required"] else 1.0
    cruise_status="success" if r["required"]<=r["power"] and d["commEfficiency"]>=.9 else "warning"
    landing_status="success" if d["landingReliability"]>=.9 else ("warning" if d["landingReliability"]>=.7 else "failure")
    if landing_status=="success" and mass_ratio>=.9: landing_status="warning"
    landing_factor={"success":1.0,"warning":.8,"failure":0.0}[landing_status]
    returns=[]
    for iid in s["instruments"]:
        item=EQUIPMENT["instruments"][iid]
        returns.append({"id":iid,"name":item["name"],"planned":item["scienceValue"],
                        "collected":round(item["scienceValue"]*power_factor*landing_factor,1)})
    collected=round(sum(x["collected"] for x in returns),1)
    transmitted=round(collected*d["commEfficiency"],1); lost=round(collected-transmitted,1)
    metrics={"score":transmitted,"collected":collected,"transmitted":transmitted,"dataLost":lost,
      "instrumentReturns":returns,"powerFactor":power_factor,"landingFactor":landing_factor,
      "commEfficiency":d["commEfficiency"],"landingReliability":d["landingReliability"],
      "landingStatus":landing_status,"budgetUsed":r["cost"],"massUsed":r["mass"],"massLimit":r["massLimit"],
      "scienceMax":SCIENCE_MAX,"resourceEfficiency":round(transmitted/(r["cost"]/10),1) if r["cost"] else 0}
    day=86400
    launch_events=[
      {"t":0,"text":"Ignition and liftoff. Launch vehicle reports go for ascent.","level":"info"},
      {"t":45,"text":f"Payload check: {r['mass']} kg against {r['payload']} kg vehicle capacity ({r['mass']/r['payload']*100:.0f}% used).","level":"success" if launch_status=="success" else "warning"},
      {"t":120,"text":"Spacecraft separated and deployed." if launch_status!="failure" else "Launch failed: payload exceeds vehicle capacity.","level":"success" if launch_status!="failure" else "danger"}]
    cruise_events=[
      {"t":14*day,"text":"Trajectory correction burn executed on schedule.","level":"success"},
      {"t":120*day,"text":f"Power: {r['power']} W available for a {r['required']} W load.","level":"success" if r["required"]<=r["power"] else "warning"},
      {"t":240*day,"text":f"Comm link at {d['commEfficiency']*100:.0f}% efficiency.","level":"success" if d["commEfficiency"]>=.9 else "warning"}]
    landing_events=[
      {"t":260*day,"text":"Entry, descent and landing sequence begins.","level":"info"},
      {"t":260*day+420,"text":f"Landing reliability {d['landingReliability']*100:.0f}%. Estimated touchdown risk {(1-d['landingReliability'])*100:.0f}%.","level":landing_status if landing_status!="failure" else "danger"},
      {"t":260*day+900,"text":{"success":"Touchdown confirmed. Rover is on the surface.","warning":"Touchdown achieved with elevated risk.","failure":"Touchdown failed. Surface operations cannot begin."}[landing_status],"level":landing_status if landing_status!="failure" else "danger"}]
    if landing_status=="failure":
      surface_events=[{"t":262*day,"text":"No rover on the surface. Surface operations cancelled.","level":"danger"}]; surface_status="failure"
    else:
      surface_events=[{"t":262*day+i*2*day,"text":f"{x['name']}: {x['collected']} of {x['planned']} pts collected.","level":"success" if x["collected"]>=x["planned"] else "warning"} for i,x in enumerate(returns)]
      surface_events.append({"t":330*day,"text":f"Data delivered to Earth: {transmitted} of {SCIENCE_MAX} pts."+ (f" {lost} pts lost on the comm link." if lost else " No losses on the link."),"level":"success" if transmitted>=80 else "warning"})
      surface_status="success" if transmitted>=80 else ("warning" if transmitted>=50 else "failure")
    stages=[
      {"id":"launch","status":launch_status,"headline":{"success":"Spacecraft delivered to transfer orbit","warning":"Launch succeeded with a thin payload margin","failure":"Launch failed: payload over vehicle capacity"}[launch_status],"events":launch_events},
      {"id":"cruise","status":cruise_status,"headline":"Cruise nominal: power and link healthy" if cruise_status=="success" else "Cruise complete with power or link limits","events":cruise_events},
      {"id":"landing","status":landing_status,"headline":{"success":"Touchdown confirmed","warning":"Touchdown achieved with elevated risk","failure":"Landing failed"}[landing_status],"events":landing_events},
      {"id":"surface","status":surface_status,"headline":{"success":"Surface science complete","warning":"Partial science return","failure":"Little or no science returned"}[surface_status],"events":surface_events}]
    statuses=[x["status"] for x in stages]
    outcome="FAILURE" if "failure" in statuses else ("PARTIAL SUCCESS" if "warning" in statuses else "SUCCESS")
    return {"outcome":outcome,"stages":stages,"metrics":metrics,"resources":r,"selectionSnapshot":s,"validation":v}
