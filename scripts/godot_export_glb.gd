# Re-export the visualization pair's Godot models (branch `game`, game/index.pck) as .glb for the web UI.
#
# The Godot web export only contains imported scenes, not the original .glb files. This script loads
# each model from the pack and writes it back to glTF, keeping node names (the *_mount points) and
# animations (solar-wing deployment). Output: frontend/game/models/*.glb
#
#   git show origin/game:game/index.pck > /tmp/index.pck
#   godot --headless --main-pack /tmp/index.pck --script scripts/godot_export_glb.gd
#
# Needs Godot 4.7.x (the version the pack was exported with). Prints each model's node tree.
extends SceneTree

var OUT: String = OS.get_environment("GLB_OUT") if OS.get_environment("GLB_OUT") != "" else "/tmp/glb/"  # set GLB_OUT=/abs/path/frontend/game/models/

func _walk(n: Node, depth: int, out: Array) -> void:
	var line := "  ".repeat(depth) + n.name + " [" + n.get_class() + "]"
	if n is Node3D:
		line += " pos=" + str((n as Node3D).position) + " rot=" + str((n as Node3D).rotation_degrees) + " scale=" + str((n as Node3D).scale)
	out.append(line)
	for c in n.get_children():
		_walk(c, depth + 1, out)

func _init() -> void:
	var dirs := ["platforms", "power", "instruments", "communications", "propulsion", "adcs"]
	for d: String in dirs:
		var da := DirAccess.open("res://assets/models/" + d)
		if da == null:
			print("no dir ", d)
			continue
		for f: String in da.get_files():
			if not f.ends_with(".glb.import"):
				continue
			var path: String = "res://assets/models/" + d + "/" + f.replace(".import", "")
			var ps: PackedScene = load(path)
			if ps == null:
				print("FAIL load ", path)
				continue
			var inst := ps.instantiate()
			var tree: Array = []
			_walk(inst, 0, tree)
			print("=== ", d, "/", f.replace(".glb.import", ""))
			print("\n".join(tree))
			var doc := GLTFDocument.new()
			var st := GLTFState.new()
			var err := doc.append_from_scene(inst, st)
			if err != OK:
				print("FAIL append ", err)
				continue
			var outp: String = OUT + f.replace(".glb.import", ".glb")
			err = doc.write_to_filesystem(st, outp)
			print("wrote ", outp, " err=", err)
			inst.free()
	quit()
