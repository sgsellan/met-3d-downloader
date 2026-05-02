# glb_to_obj.py — run inside Blender: blender -b -P glb_to_obj.py -- in.glb out.obj
import bpy, sys

argv = sys.argv[sys.argv.index("--") + 1:]
glb_in, obj_out = argv[0], argv[1]

# Start clean
bpy.ops.wm.read_factory_settings(use_empty=True)

bpy.ops.import_scene.gltf(filepath=glb_in)

bpy.ops.wm.obj_export(
    filepath=obj_out,
    export_materials=True,
    export_uv=True,
    export_normals=True,
    export_triangulated_mesh=True,   # OBJ has no native quad/ngon guarantee anyway
    forward_axis='Y',
    up_axis='Z',
)