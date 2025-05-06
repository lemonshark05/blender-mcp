import bpy
import os
import bmesh
import json
import threading
import socket
import time
import traceback
from bpy.props import StringProperty, IntProperty, BoolProperty, EnumProperty
import io
from contextlib import redirect_stdout
import re
from typing import Any

bl_info = {
    "name": "Blender MCP",
    "author": "BlenderMCP",
    "version": (0, 1),
    "blender": (3, 0, 0),
    "location": "View3D > Sidebar > BlenderMCP",
    "description": "Connect Blender to Claude via MCP",
    "category": "Interface",
}

class BlenderMCPServer:
    def __init__(self, host='localhost', port=9876):
        self.host = host
        self.port = port
        self.running = False
        self.socket = None
        self.server_thread = None
    
    def start(self):
        if self.running:
            print("Server is already running")
            return
            
        self.running = True
        
        try:
            # Create socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((self.host, self.port))
            self.socket.listen(1)
            
            # Start server thread
            self.server_thread = threading.Thread(target=self._server_loop)
            self.server_thread.daemon = True
            self.server_thread.start()
            
            print(f"BlenderMCP server started on {self.host}:{self.port}")
        except Exception as e:
            print(f"Failed to start server: {str(e)}")
            self.stop()
            
    def stop(self):
        self.running = False
        
        # Close socket
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        
        # Wait for thread to finish
        if self.server_thread:
            try:
                if self.server_thread.is_alive():
                    self.server_thread.join(timeout=1.0)
            except:
                pass
            self.server_thread = None
        
        print("BlenderMCP server stopped")
    
    def _server_loop(self):
        """Main server loop in a separate thread"""
        print("Server thread started")
        self.socket.settimeout(1.0)  # Timeout to allow for stopping
        
        while self.running:
            try:
                # Accept new connection
                try:
                    client, address = self.socket.accept()
                    print(f"Connected to client: {address}")
                    
                    # Handle client in a separate thread
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client,)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                except socket.timeout:
                    # Just check running condition
                    continue
                except Exception as e:
                    print(f"Error accepting connection: {str(e)}")
                    time.sleep(0.5)
            except Exception as e:
                print(f"Error in server loop: {str(e)}")
                if not self.running:
                    break
                time.sleep(0.5)
        
        print("Server thread stopped")
    
    def _handle_client(self, client):
        """Handle connected client"""
        print("Client handler started")
        client.settimeout(None)  # No timeout
        buffer = b''
        
        try:
            while self.running:
                # Receive data
                try:
                    data = client.recv(8192)
                    if not data:
                        print("Client disconnected")
                        break
                    
                    buffer += data
                    try:
                        # Try to parse command
                        command = json.loads(buffer.decode('utf-8'))
                        buffer = b''
                        
                        # Execute command in Blender's main thread
                        def execute_wrapper():
                            try:
                                response = self.execute_command(command)
                                response_json = json.dumps(response)
                                try:
                                    client.sendall(response_json.encode('utf-8'))
                                except:
                                    print("Failed to send response - client disconnected")
                            except Exception as e:
                                print(f"Error executing command: {str(e)}")
                                traceback.print_exc()
                                try:
                                    error_response = {
                                        "status": "error",
                                        "message": str(e)
                                    }
                                    client.sendall(json.dumps(error_response).encode('utf-8'))
                                except:
                                    pass
                            return None
                        
                        # Schedule execution in main thread
                        bpy.app.timers.register(execute_wrapper, first_interval=0.0)
                    except json.JSONDecodeError:
                        # Incomplete data, wait for more
                        pass
                except Exception as e:
                    print(f"Error receiving data: {str(e)}")
                    break
        except Exception as e:
            print(f"Error in client handler: {str(e)}")
        finally:
            try:
                client.close()
            except:
                pass
            print("Client handler stopped")

    def execute_command(self, command):
        """Execute a command in the main Blender thread"""
        try:            
            return self._execute_command_internal(command)
                
        except Exception as e:
            print(f"Error executing command: {str(e)}")
            traceback.print_exc()
            return {"status": "error", "message": str(e)}

    def _execute_command_internal(self, command):
        """Internal command execution with proper context"""
        cmd_type = command.get("type")
        params = command.get("params", {})

        # Base handlers that are always available
        handlers = {
            "get_scene_info": self.get_scene_info,
            "get_object_info": self.get_object_info,
            "execute_code": self.execute_code,
            "has_node_group":        self.has_node_group,
            "get_node_group_inputs": self.get_node_group_inputs,
            "set_node_group_input":  self.set_node_group_input,
            "list_parts":        self.list_parts,
            "replace_part":      self.replace_part,
            "init_model": self.init_model,
        }

        handler = handlers.get(cmd_type)
        if handler:
            try:
                print(f"Executing handler for {cmd_type}")
                result = handler(**params)
                print(f"Handler execution complete")
                return {"status": "success", "result": result}
            except Exception as e:
                print(f"Error in handler: {str(e)}")
                traceback.print_exc()
                return {"status": "error", "message": str(e)}
        else:
            return {"status": "error", "message": f"Unknown command type: {cmd_type}"}
        
    def list_parts(self):
        """Return a dict of all available part-objects grouped by type."""
        if not bpy.context.scene.blendermcp_use_roles:
            return {"status":"error", "message":"Role Models disabled in UI"}
        
        out = {"Head": [], "Waist": [], "Leg": [], "Arm": []}
        pat = re.compile(r"^(Head|Waist|Leg|Arm)(?:[\._].*)?$")
        for obj in bpy.data.objects:
            m = pat.match(obj.name)
            if m:
                out[m.group(1)].append(obj.name)
        return out
    
    def init_model(self):
        """Load the base mesh plus all Marker_ objects into the scene."""
        if not bpy.context.scene.blendermcp_use_roles:
            return {"status":"error", "message":"Role Models disabled in UI"}
        
        asset_dir  = "/Users/hula/Documents/Female"
        blend_file = "CustomizeFemaleBaseMesh_AnimeStyle_v1_3_AssetBrowser.blend"
        blend_path = os.path.join(asset_dir, blend_file)

        # 1. Load base + markers
        with bpy.data.libraries.load(blend_path, link=False) as (src, dst):
            dst.objects = [name for name in src.objects
                            if name == "AnimeStyle_Female_Base" or name.startswith("Marker_")]
            dst.meshes  = list(src.meshes)

        # 2. Link into scene & zero the base
        for obj in dst.objects:
            if obj is None: continue
            if obj.name not in bpy.context.scene.collection.objects:
                bpy.context.scene.collection.objects.link(obj)
            if obj.name.startswith("AnimeStyle_Female_Base"):
                obj.location = (0,0,0)

        return {"status":"success", "message":"Base character initialized"}

    def replace_part(self, part_type: str, new_name: str):
        """
        Delete the old faces/material slots for a given part_type,
        append+align+join the new asset named new_name under Marker_<part_type>.
        """
        if not bpy.context.scene.blendermcp_use_roles:
            return {"status":"error", "message":"Role Models disabled in UI"}
        
        # 1) find base mesh
        base = max(
            (o for o in bpy.data.objects if o.type=='MESH' and o.name.startswith("AnimeStyle_Female_Base")),
            key=lambda o: len(o.data.vertices),
            default=None
        )
        if not base:
            raise RuntimeError("Base mesh not found")

        # 2) delete old faces + slots
        import bmesh
        bm = bmesh.new(); bm.from_mesh(base.data)
        # collect slot indices whose root == part_type
        to_remove = [
            i for i,slot in enumerate(base.material_slots)
            if slot.material and slot.material.name.split('.',1)[0] == part_type
        ]
        for face in [f for f in bm.faces if f.material_index in to_remove]:
            bm.faces.remove(face)
        # remove orphan verts
        for v in [v for v in bm.verts if not v.link_faces]:
            bm.verts.remove(v)
        bm.to_mesh(base.data); base.data.update()
        for idx in sorted(to_remove, reverse=True):
            base.data.materials.pop(index=idx)
        bm.free()

        # 3) append new object
        blend_path = os.path.join("/Users/hula/Documents/Female",
                                  "CustomizeFemaleBaseMesh_AnimeStyle_v1_3_AssetBrowser.blend")
        with bpy.data.libraries.load(blend_path, link=False) as (src, dst):
            if new_name not in src.objects:
                raise RuntimeError(f"{new_name} not found")
            dst.objects = [new_name]
        new_obj = bpy.data.objects[new_name]
        # link if needed
        coll = bpy.context.scene.collection
        if new_obj.name not in coll.objects:
            coll.objects.link(new_obj)

        # 4) align
        marker = bpy.data.objects.get(f"Marker_{part_type}")
        if not marker:
            raise RuntimeError(f"Marker_{part_type} not found")
        new_obj.matrix_world = marker.matrix_world.copy()

        # 5) join
        for o in bpy.context.view_layer.objects:
            o.select_set(False)
        base.select_set(True)
        new_obj.select_set(True)
        bpy.context.view_layer.objects.active = base
        bpy.ops.object.join()

        return {"status":"success", "message": f"{part_type} replaced with {new_name}"}
    
    def has_node_group(self, group_name):
        return group_name in bpy.data.node_groups

    def get_node_group_inputs(self, group_name):
        ng = bpy.data.node_groups.get(group_name)
        if not ng:
            raise ValueError(f"Node group not found: {group_name}")
        out = []
        for item in ng.interface.items_tree:
            # only sockets, not frames/etc.
            if getattr(item, "item_type", "") == "SOCKET" and item.in_out == "INPUT":
                out.append({
                    "name": item.name,
                    "type": item.socket_type,
                    "default": getattr(item, "default_value", None),
                    "identifier": item.identifier,
                })
        return out

    def set_node_group_input(self, group_name: str, input_name: str, value: Any):
        import re, bpy
        def normalize(s: str) -> str:
            return re.sub(r"[\s_]+", "", s).lower()

        ng = bpy.data.node_groups.get(group_name)
        if not ng:
            return {"status":"error","message":f"Node group '{group_name}' not found"}

        # find the interface socket
        key = normalize(input_name)
        target = None
        for item in ng.interface.items_tree:
            if item.in_out=="INPUT" and normalize(item.name)==key:
                target = item
                break
        if not target:
            return {"status":"error","message":f"Input '{input_name}' not found"}

        try:
            target.default_value = value
        except Exception as e:
            return {"status":"error","message":f"Failed to set default: {e}"}

        # refresh  
        bpy.context.view_layer.update()
        for w in bpy.context.window_manager.windows:
            for area in w.screen.areas:
                area.tag_redraw()

        return {
            "status":"success",
            "group":group_name,
            "input":target.name,
            "new_value":value
        }


    def get_scene_info(self):
        """Get information about the current Blender scene"""
        try:
            print("Getting scene info...")
            # Simplify the scene info to reduce data size
            scene_info = {
                "name": bpy.context.scene.name,
                "object_count": len(bpy.context.scene.objects),
                "objects": [],
                "materials_count": len(bpy.data.materials),
            }
            
            # Collect minimal object information (limit to first 10 objects)
            for i, obj in enumerate(bpy.context.scene.objects):
                if i >= 10:  # Reduced from 20 to 10
                    break
                    
                obj_info = {
                    "name": obj.name,
                    "type": obj.type,
                    # Only include basic location data
                    "location": [round(float(obj.location.x), 2), 
                                round(float(obj.location.y), 2), 
                                round(float(obj.location.z), 2)],
                }
                scene_info["objects"].append(obj_info)
            
            print(f"Scene info collected: {len(scene_info['objects'])} objects")
            return scene_info
        except Exception as e:
            print(f"Error in get_scene_info: {str(e)}")
            traceback.print_exc()
            return {"error": str(e)}
    
    @staticmethod
    def _get_aabb(obj):
        """ Returns the world-space axis-aligned bounding box (AABB) of an object. """
        if obj.type != 'MESH':
            raise TypeError("Object must be a mesh")

        # Get the bounding box corners in local space
        local_bbox_corners = [mathutils.Vector(corner) for corner in obj.bound_box]

        # Convert to world coordinates
        world_bbox_corners = [obj.matrix_world @ corner for corner in local_bbox_corners]

        # Compute axis-aligned min/max coordinates
        min_corner = mathutils.Vector(map(min, zip(*world_bbox_corners)))
        max_corner = mathutils.Vector(map(max, zip(*world_bbox_corners)))

        return [
            [*min_corner], [*max_corner]
        ]
    
    def get_object_info(self, name):
        """Get detailed information about a specific object"""
        obj = bpy.data.objects.get(name)
        if not obj:
            raise ValueError(f"Object not found: {name}")
        
        # Basic object info
        obj_info = {
            "name": obj.name,
            "type": obj.type,
            "location": [obj.location.x, obj.location.y, obj.location.z],
            "rotation": [obj.rotation_euler.x, obj.rotation_euler.y, obj.rotation_euler.z],
            "scale": [obj.scale.x, obj.scale.y, obj.scale.z],
            "visible": obj.visible_get(),
            "materials": [],
        }

        if obj.type == "MESH":
            bounding_box = self._get_aabb(obj)
            obj_info["world_bounding_box"] = bounding_box
        
        # Add material slots
        for slot in obj.material_slots:
            if slot.material:
                obj_info["materials"].append(slot.material.name)
        
        # Add mesh data if applicable
        if obj.type == 'MESH' and obj.data:
            mesh = obj.data
            obj_info["mesh"] = {
                "vertices": len(mesh.vertices),
                "edges": len(mesh.edges),
                "polygons": len(mesh.polygons),
            }
        
        return obj_info
    
    def execute_code(self, code):
        """Execute arbitrary Blender Python code"""
        # This is powerful but potentially dangerous - use with caution
        try:
            # Create a local namespace for execution
            namespace = {"bpy": bpy}

            # Capture stdout during execution, and return it as result
            capture_buffer = io.StringIO()
            with redirect_stdout(capture_buffer):
                exec(code, namespace)
            
            captured_output = capture_buffer.getvalue()
            return {"executed": True, "result": captured_output}
        except Exception as e:
            raise Exception(f"Code execution error: {str(e)}")

# Blender UI Panel
class BLENDERMCP_PT_Panel(bpy.types.Panel):
    bl_label = "Blender MCP"
    bl_idname = "BLENDERMCP_PT_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'BlenderMCP'
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        layout.prop(scene, "blendermcp_port")
        layout.prop(scene, "blendermcp_use_roles", text="Use assets from Role Models")

        if not scene.blendermcp_server_running:
            layout.operator("blendermcp.start_server", text="Connect to MCP server")
        else:
            layout.operator("blendermcp.stop_server", text="Disconnect from MCP server")
            layout.label(text=f"Running on port {scene.blendermcp_port}")

# Operator to start the server
class BLENDERMCP_OT_StartServer(bpy.types.Operator):
    bl_idname = "blendermcp.start_server"
    bl_label = "Connect to Claude"
    bl_description = "Start the BlenderMCP server to connect with Claude"
    
    def execute(self, context):
        scene = context.scene
        
        # Create a new server instance
        if not hasattr(bpy.types, "blendermcp_server") or not bpy.types.blendermcp_server:
            bpy.types.blendermcp_server = BlenderMCPServer(port=scene.blendermcp_port)
        
        # Start the server
        bpy.types.blendermcp_server.start()
        scene.blendermcp_server_running = True
        
        return {'FINISHED'}

# Operator to stop the server
class BLENDERMCP_OT_StopServer(bpy.types.Operator):
    bl_idname = "blendermcp.stop_server"
    bl_label = "Stop the connection to Claude"
    bl_description = "Stop the connection to Claude"
    
    def execute(self, context):
        scene = context.scene
        
        # Stop the server if it exists
        if hasattr(bpy.types, "blendermcp_server") and bpy.types.blendermcp_server:
            bpy.types.blendermcp_server.stop()
            del bpy.types.blendermcp_server
        
        scene.blendermcp_server_running = False
        
        return {'FINISHED'}

def on_use_roles_update(self, context):
    enabled = context.scene.blendermcp_use_roles
    msg = "Role Models ENABLED" if enabled else "Role Models DISABLED"
    # 1) Print to the system console
    print(f"[BlenderMCP] {msg}")
    # 2) Show a quick popup in the UI
    def draw(self, context):
        self.layout.label(text=msg)
    context.window_manager.popup_menu(draw, title="BlenderMCP", icon='INFO')

def register():
    # 1) Define scene-level properties (does not access any Scene instance)
    bpy.types.Scene.blendermcp_port = bpy.props.IntProperty(
        name="Port",
        default=9876,
        min=1024,
        max=65535
    )
    bpy.types.Scene.blendermcp_server_running = bpy.props.BoolProperty(
        name="Server Running",
        default=False
    )
    bpy.types.Scene.blendermcp_use_roles = bpy.props.BoolProperty(
      name="Use assets from Role Models",
       default=False,
       update=on_use_roles_update
   )

    # 2) Register the sidebar panel and connect/disconnect operators
    bpy.utils.register_class(BLENDERMCP_PT_Panel)
    bpy.utils.register_class(BLENDERMCP_OT_StartServer)
    bpy.utils.register_class(BLENDERMCP_OT_StopServer)

    print("BlenderMCP addon registered")


def unregister():
    # 1) If the server was started, stop it
    if hasattr(bpy.types, "blendermcp_server") and bpy.types.blendermcp_server:
        bpy.types.blendermcp_server.stop()
        del bpy.types.blendermcp_server

    # 2) Unregister UI classes
    bpy.utils.unregister_class(BLENDERMCP_PT_Panel)
    bpy.utils.unregister_class(BLENDERMCP_OT_StartServer)
    bpy.utils.unregister_class(BLENDERMCP_OT_StopServer)

    # 3) Remove the properties from the Scene type
    del bpy.types.Scene.blendermcp_port
    del bpy.types.Scene.blendermcp_server_running
    del bpy.types.Scene.blendermcp_use_roles

    print("BlenderMCP addon unregistered")

if __name__ == "__main__":
    register()