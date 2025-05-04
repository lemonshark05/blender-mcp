import shutil
from pathlib import Path
import importlib
import socket
import json
import asyncio
import logging
import re
from dataclasses import dataclass
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Any, List
import os

# ─── Auto-clean Python bytecode cache ───
_PROJECT_ROOT = Path(__file__).parent
for cache_dir in _PROJECT_ROOT.rglob("__pycache__"):
    shutil.rmtree(cache_dir, ignore_errors=True)
for pyc_file in _PROJECT_ROOT.rglob("*.pyc"):
    try:
        pyc_file.unlink()
    except OSError:
        pass
importlib.invalidate_caches()
# ─────────────────────────────────────────

from mcp.server.fastmcp import FastMCP, Context, Image

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("BlenderMCPServer")

@dataclass
class BlenderConnection:
    host: str
    port: int
    sock: socket.socket = None

    def connect(self) -> bool:
        if self.sock:
            return True
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            logger.info(f"Connected to Blender at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Blender: {e}")
            self.sock = None
            return False

    def disconnect(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception as e:
                logger.error(f"Error disconnecting: {e}")
            finally:
                self.sock = None

    def receive_full_response(self, sock, buffer_size=8192):
        chunks = []
        sock.settimeout(15.0)
        try:
            while True:
                chunk = sock.recv(buffer_size)
                if not chunk:
                    break
                chunks.append(chunk)
                try:
                    data = b''.join(chunks)
                    json.loads(data.decode('utf-8'))
                    return data
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            logger.warning(f"Receive warning: {e}")
        if chunks:
            data = b''.join(chunks)
            try:
                json.loads(data.decode('utf-8'))
                return data
            except Exception:
                raise Exception("Incomplete JSON response received")
        raise Exception("No data received")

    def send_command(self, command_type: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        if not self.sock and not self.connect():
            raise ConnectionError("Not connected to Blender")
        command = {"type": command_type, "params": params or {}}
        try:
            logger.info(f"Sending command: {command_type} with params: {params}")
            self.sock.sendall(json.dumps(command).encode('utf-8'))
            data = self.receive_full_response(self.sock)
            resp = json.loads(data.decode('utf-8'))
            if resp.get('status') == 'error':
                raise Exception(resp.get('message', 'Unknown error from Blender'))
            return resp.get('result', {})
        except Exception as e:
            self.sock = None
            raise

# Global persistent connection
_blender_connection: BlenderConnection = None

def get_blender_connection() -> BlenderConnection:
    global _blender_connection
    if _blender_connection:
        try:
            _blender_connection.send_command('get_scene_info')
            return _blender_connection
        except Exception:
            _blender_connection.disconnect()
            _blender_connection = None
    _blender_connection = BlenderConnection(host='localhost', port=9876)
    if not _blender_connection.connect():
        raise Exception("Could not connect to Blender. Ensure the addon is running.")
    return _blender_connection

@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, Any]]:
    try:
        logger.info("BlenderMCP server starting up")
        startup_check_nodecity()
        yield {}
    finally:
        global _blender_connection
        if _blender_connection:
            _blender_connection.disconnect()
            _blender_connection = None
        logger.info("BlenderMCP server shut down")

# Initialize MCP server
data_files = [ 
    (".bl_info.json", None)
]
mcp = FastMCP(
    "BlenderMCP",
    description="Blender integration through the Model Context Protocol",
    lifespan=server_lifespan
)

# Startup check for NodeCity node group
def startup_check_nodecity():
    try:
        blender = get_blender_connection()
        exists = blender.send_command('has_node_group', {'group_name': 'NodeCity'})
        found = exists.get('result', False) if isinstance(exists, dict) else bool(exists)
        if found:
            logger.info("✅ Found 'NodeCity' node group")
        else:
            logger.warning("⚠️ 'NodeCity' node group not found in project")
    except Exception as e:
        logger.error(f"Error checking NodeCity: {e}")

# === MCP Tools ===

@mcp.tool()
def get_scene_info(ctx: Context) -> str:
    """Get detailed information about the current Blender scene."""
    try:
        blender = get_blender_connection()
        result = blender.send_command('get_scene_info')
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting scene info: {e}")
        return f"Error getting scene info: {e}"

@mcp.tool()
def get_object_info(ctx: Context, object_name: str) -> str:
    """Get detailed information about a specific object."""
    try:
        blender = get_blender_connection()
        result = blender.send_command('get_object_info', {'name': object_name})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting object info: {e}")
        return f"Error getting object info: {e}"

@mcp.tool()
def execute_blender_code(ctx: Context, code: str) -> str:
    """Execute arbitrary Python code in Blender."""
    try:
        blender = get_blender_connection()
        result = blender.send_command('execute_code', {'code': code})
        return f"Code executed successfully: {result.get('result', '')}"
    except Exception as e:
        logger.error(f"Error executing code: {e}")
        return f"Error executing code: {e}"

@mcp.tool()
def has_node_group(ctx: Context, group_name: str) -> str:
    """Check if a Geometry Node Group exists."""
    try:
        blender = get_blender_connection()
    except Exception:
        return "Error: Could not connect to Blender."
    result = blender.send_command('has_node_group', {'group_name': group_name})
    exists = result.get('result', False) if isinstance(result, dict) else bool(result)
    return f"Node group '{group_name}' exists: {exists}"

@mcp.tool()
def get_node_group_inputs(ctx: Context, group_name: str) -> str:
    """List interface inputs of a node group."""
    blender = get_blender_connection()
    result = blender.send_command('get_node_group_inputs', {'group_name': group_name})
    inputs = result.get('result', [])
    if not inputs:
        return f"No inputs found for '{group_name}'."
    lines = [f"- {i['name']} ({i['type']}), default={i['default']}" for i in inputs]
    return f"Inputs for '{group_name}':\n" + "\n".join(lines)

@mcp.tool()
def set_node_group_input(
    ctx: Context,
    group_name: str,
    input_name: str,
    value: Any
) -> str:
    """Set a node group input interface value."""
    blender = get_blender_connection()
    params = {'group_name': group_name, 'input_name': input_name, 'value': value}
    result = blender.send_command('set_node_group_input', params)
    if 'modified_modifiers' in result:
        return f"Set '{input_name}'={value} on {result['modified_modifiers']} modifier(s)."
    return f"Error: {result.get('message', 'unknown')}"

@mcp.tool()
def set_texture(
    ctx: Context,
    object_name: str,
    texture_id: str
) -> str:
    """Apply a Polyhaven texture to an object."""
    try:
        blender = get_blender_connection()
        result = blender.send_command('set_texture', {'object_name': object_name, 'texture_id': texture_id})
        if 'error' in result:
            return f"Error: {result['error']}"
        material_info = result.get('material_info', {})
        info = [f"Material='{result.get('material')}'; maps={result.get('maps')}" ]
        info.append(f"Nodes={material_info.get('node_count')}, has_nodes={material_info.get('has_nodes')}" )
        return "Successfully applied texture. " + "; ".join(info)
    except Exception as e:
        logger.error(f"Error applying texture: {e}")
        return f"Error applying texture: {e}"

# === NodeCity Automation Tools ===

@mcp.tool()
def scan_nodecity_inputs(ctx: Context) -> str:
    """Scan and return all input sockets of the 'NodeCity' node group."""
    blender = get_blender_connection()
    result = blender.send_command('get_node_group_inputs', {'group_name': 'NodeCity'})
    inputs = result.get('result', [])
    if not inputs:
        return "⚠️ 'NodeCity' found but has no inputs."
    return "\n".join([f"- {inp['name']} ({inp['type']}), default={inp['default']}" for inp in inputs])

@mcp.tool()
def create_nodecity(ctx: Context, params: Dict[str, Any]) -> str:
    """Create an empty object, add NodeCity modifier, and apply params."""
    blender = get_blender_connection()
    params_json = json.dumps(params)
    code = f'''import bpy, json
# Create new empty
obj = bpy.data.objects.new("NodeCityInstance", None)
bpy.context.collection.objects.link(obj)
# Add geometry nodes modifier
mod = obj.modifiers.new(name="NodeCity", type="NODES")
mod.node_group = bpy.data.node_groups.get("NodeCity")
# Apply params
dict_params = json.loads(r"""{params_json}"""')
for name, value in dict_params.items():
    try: setattr(mod, name, value)
    except: pass
# Select and activate
bpy.context.view_layer.objects.active = obj
obj.select_set(True)
print("Created NodeCityInstance", dict_params)'''  # noqa
    blender.send_command('execute_code', {'code': code})
    return f"✅ Created NodeCityInstance with params: {params}"

@mcp.prompt()
def nodecity_autocreate(ctx: Context, user_input: str) -> str:
    """Auto workflow: scan inputs, ask LLM for values, create instance."""
    # Ensure Blender is connected
    try:
        get_blender_connection()
    except Exception:
        return None  # skip autocreate if not connected

    if not re.search(r"\bNodeCity\b", user_input, re.IGNORECASE):
        return None

    # Step 1: scan
    scan = scan_nodecity_inputs(ctx)
    # Step 2: LLM picks values
    llm_prompt = f"""
The NodeCity input sockets are:
{scan}
Choose values for a modern high-density city and respond with only a JSON dict mapping input names to values.
"""
    llm_resp = ctx.llm({"role":"user","content":llm_prompt})
    try:
        params = json.loads(llm_resp.content)
    except Exception:
        return "❌ Failed parsing JSON: " + llm_resp.content

    # Step 3: create
    try:
        return create_nodecity(ctx, params)
    except Exception as e:
        return f"❌ Creation error: {e}"

# Start server
def main():
    tools = asyncio.run(mcp.list_tools())
    names = list(tools.keys()) if isinstance(tools, dict) else list(tools)
    logger.info(f"Registered MCP tools: {names}")
    mcp.run()

if __name__ == '__main__':
    main()