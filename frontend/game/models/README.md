# 3D models

Spacecraft parts made by the visualization pair in Godot (branch `game`, `game/index.pck`), converted
back to glTF with `scripts/godot_export_glb.gd` (Godot 4.7.2, headless). Node names are kept, so the
platform mount points (`payload_mount`, `solar_mount_left`, `solar_mount_right`, `communication_mount`,
`adcs_mount`, `propulsion_mount`) and the solar-wing deployment animations work as in the Godot workshop.

`js/viewer3d.js` places them the way `scripts/workshop/spacecraft_assembler.gd` did. Game component ->
model mapping is at the top of `viewer3d.js`. A part without a model is not drawn.

To update after the visualization pair changes their models:

```bash
git show origin/game:game/index.pck > /tmp/index.pck
GLB_OUT=$PWD/frontend/game/models/ godot --headless --main-pack /tmp/index.pck --script $PWD/scripts/godot_export_glb.gd
```

Rover wheels, lander legs and the radioisotope power unit are drawn in code (no model existed).
