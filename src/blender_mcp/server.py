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
from typing import AsyncIterator, Dict, Any

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

# A manifest of every tool your MCP server exposes:
TOOL_MANIFEST = [
    {
        "name": "get_scene_info",
        "description": "Get basic info about the current Blender scene (objects, materials).",
        "params": {}
    },
    {
        "name": "get_object_info",
        "description": "Get detailed info about a named object.",
        "params": {"object_name": "string"}
    },
    {
        "name": "execute_blender_code",
        "description": "Run arbitrary Python code in Blender.",
        "params": {"code": "string"}
    },
    {
        "name": "list_parts",
        "description": "List all available Head/Waist/Leg/Arm asset names.",
        "params": {}
    },
    {
        "name": "init_model",
        "description": "Load the base female character mesh plus Marker_ objects.",
        "params": {}
    },
    {
        "name": "replace_part",
        "description": "Swap a body part. Params: part_type (Head/Arm/Leg/Waist), new_name (asset).",
        "params": {"part_type": "string", "new_name": "string"}
    },
    {
        "name": "has_node_group",
        "description": "Check if a Geometry Node Group exists.",
        "params": {"group_name": "string"}
    },
    {
        "name": "get_node_group_inputs",
        "description": "Get input sockets of a node group.",
        "params": {"group_name": "string"}
    },
    {
        "name": "set_node_group_input",
        "description": "Set a default value on a node group input.",
        "params": {"group_name": "string", "input_name": "string", "value": "any"}
    },
    {
        "name": "scan_nodecity_inputs",
        "description": "List inputs on the 'NodeCity' node group.",
        "params": {}
    },
    {
        "name": "create_nodecity",
        "description": "Configure the NodeCity node group with given params.",
        "params": {"params": "object"}
    }
]

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
    blender = get_blender_connection()
    result = blender.send_command('get_node_group_inputs', {'group_name': group_name})
    # result should now be a list of dicts with 'name','type','default'
    if not result:
        return f"No inputs for '{group_name}'"
    lines = [f"- {i['name']} ({i['type']}), default={i['default']}" for i in result]
    return f"Inputs for '{group_name}':\n" + "\n".join(lines)

@mcp.tool()
def set_node_group_input(ctx: Context, group_name: str, input_name: str, value: Any) -> str:
    blender = get_blender_connection()
    resp = blender.send_command('set_node_group_input', {
        'group_name': group_name,
        'input_name': input_name,
        'value': value
    })
    # resp is now the dict returned by the add-on handler
    if resp.get("status") == "success":
        return f"✅ {resp['input']} default set to {resp['new_value']}"
    else:
        return f"❌ {resp.get('message','unknown error')}"

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
    results = []
    for key, val in params.items():
        resp = set_node_group_input(ctx, "NodeCity", key, val)
        results.append(resp)
    return "\n".join([str(r) for r in results])

@mcp.tool()
def list_parts(ctx: Context) -> str:
    """Return JSON-string of available Head/Waist/Leg/Arm variants."""
    blender = get_blender_connection()
    result = blender.send_command("list_parts")
    return json.dumps(result, indent=2)

@mcp.tool()
def init_model(ctx) -> str:
    """Create a fresh character by loading the base+markers."""
    blender = get_blender_connection()
    result  = blender.send_command("init_model")
    if result.get("status")=="success":
        return result["message"]
    else:
        return f"Error: {result.get('message','init_model failed')}"

@mcp.tool()
def replace_part(ctx: Context, part_type: str, new_name: str) -> str:
    """Replace the given part_type with new_name in the Base model."""
    blender = get_blender_connection()
    resp = blender.send_command("replace_part", {
        "part_type": part_type,
        "new_name": new_name
    })
    # resp is a dict with status/message
    if resp.get("status")=="success":
        return resp["message"]
    else:
        return f"Error: {resp.get('message','unknown')}"

@mcp.prompt()
def init_model_prompt(ctx: Context, user_input: str) -> str:
    if re.search(r"(?i)\b(female|role|character|human)\b", user_input):
        return json.dumps({"type": "init_model", "params": {}})
    return None

@mcp.prompt()
def list_parts_prompt(ctx: Context, user_input: str) -> str:
    if ( re.search(r"(?i)\b(what|which|list|get)\b.*\b(arm|leg|head|waist)s?\b", user_input)
         and not re.search(r"[A-Za-z]+_[A-Za-z]+", user_input) ):
        return json.dumps({"type": "list_parts", "params": {}})
    return None

@mcp.prompt()
def replace_part_prompt(ctx: Context, user_input: str) -> str:
    m = re.search(r"\b(Head|Arm|Leg|Waist)_([A-Za-z0-9]+)\b", user_input)
    if m:
        return json.dumps({
            "type": "replace_part",
            "params": {
                "part_type": m.group(1),
                "new_name": f"{m.group(1)}_{m.group(2)}"
            }
        })
    return None

@mcp.prompt()
def dynamic_tool_router(ctx: Context, user_input: str) -> str:
    role_tools = [
        t for t in TOOL_MANIFEST
        if t["name"] in (
            "init_model",
            "list_parts",
            "replace_part",
            "get_scene_info",
            "get_object_info",
            "execute_blender_code"
        )
    ]
    system_msg = f"""
You are a bridge between natural language and Blender operations.  You have these ROLE-FOCUSED tools:

{json.dumps(role_tools, indent=2)}

Rules:
- init_model → create a new character.
- list_parts → list available body-part variants.
- replace_part → swap in a named variant.
- get_scene_info / get_object_info / execute_blender_code → general Blender queries.
- If none apply, reply NO_TOOL.

Respond *only* with the JSON or the literal string NO_TOOL.  No extra text.
"""
    llm_resp = ctx.llm([
        {"role": "system",  "content": system_msg},
        {"role": "user",    "content": user_input}
    ])
    reply = llm_resp.content.strip()
    if reply.upper() == "NO_TOOL":
        return None
    try:
        cmd = json.loads(reply)
        if any(t["name"] == cmd.get("type") for t in role_tools):
            return reply
    except:
        pass
    return None

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
    llm_resp = ctx.llm({"role":"city designer","content":llm_prompt})
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