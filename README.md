# Custom MCP Integration Summary

- **Modular Character Assembly**  
  - `init_model` + `execute_blender_code`: import base mesh and body-part assets (Head/Waist/Arms/Legs)  
  - `list_parts` + `replace_part`: dynamically list and swap character parts  
- **Low-Poly City Planning (NodeCity)**  
  - Geometry Nodes “CityGenerator” for street and block layout  
  - MCP tools to adjust node group parameters: `has_node_group`, `get_node_group_inputs`, `set_node_group_input`  
  - `execute_blender_code`: scatter assets (trees, benches, vehicles)  
- **Hybrid Workflow**  
  - Geometry Nodes for instant visual feedback and broad procedural layouts  
  - Python API for batch operations, custom logic, and fine control  
  - All commands orchestrated via a FastMCP TCP server  

---

# Geometry Nodes vs. Python API with MCP

|                    | Geometry Nodes                        | Python API                         |
|--------------------|---------------------------------------|------------------------------------|
| **Pros**           | - Visual workflow, no coding          | - Full access to all Blender subsystems<br>- Easy to batch-process large datasets<br>- Built-in performance optimizations<br>- Mature ecosystem of scripts and add-ons |
| **Cons**           | - Limited to geometry tasks           | - Steeper learning curve for non-developers<br>- Complex scripts are harder to debug<br>- Slower iteration cycle     |
| **Real-time UX**   | Instant feedback & real-time updates  | Script-driven, needs run/reload     |

---

## FastMCP Server & Tools

- **Scene Information**  
  - `get_scene_info`  
  - `list_parts`  
  - `get_object_info`  
  - `init_model`  
- **Asset Management**  
  - `execute_blender_code`  
  - `replace_part`  
- **Node Group Operations**  
  - `has_node_group`  
  - `get_node_group_inputs`  
  - `set_node_group_input`  

**Server Setup**  
1. Blender Add-on listens on TCP port 9876.  
2. FastMCP server dispatches JSON commands.  
3. Commands execute on Blender’s main thread via timers.

---

## Project Examples

### 1. Modular Character Assembly  
1. **Asset Import**  
   - `init_model` to spawn base character  
   - `execute_blender_code` to load head, waist, arms, legs assets  
2. **Part Replacement**  
   - `list_parts()` → identify “head”, “waist”, “arms”, “legs”  
   - `replace_part("head", asset_id)` (and similarly for other parts)  
3. **Final Touches**  
   - Material tweaks and posing via Python API or Geometry Nodes

### 2. Low-Poly City Planning (NodeCity)  
1. **Base Layout**  
   - Geometry Nodes “CityGenerator” for streets & blocks  
2. **MCP Parameter Tweaks**  
   - `has_node_group("NodeCity")`  etc.  
3. **A**

## Install the Claude MCP Server

1. **Install UV**  
   - **macOS**:  
     ```bash
     brew install uv
     ```  
   - **Windows**:  
     ```powershell
     powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
     set Path=C:\Users\<YourUsername>\.local\bin;%Path%
     ```

2. **Configure Claude Desktop**  
   Go to **Claude → Settings → Developer → Edit Config** (`claude_desktop_config.json`) and set your local MCP server path:
   ```json
   {
     "mcpServers": {
       "blender": {
         "command": "uvx",
         "args": ["/path/to/blender-mcp"]
       }
     }
   }
Enable MCP in Blender
Download addon.py from this repo.

Open Blender and go to Edit → Preferences → Add-ons.

Click Install... and select the downloaded addon.py.

Enable Interface: Blender MCP by checking its box.

In the 3D View sidebar (press N if hidden), open the BlenderMCP panel and click Connect to Claude.

## Geometry Nodes vs. Python API with MCP

|                    | Geometry Nodes                        | Python API                         |
|--------------------|---------------------------------------|------------------------------------|
| **Pros**           | - Visual workflow, no coding          | - Full access to all Blender subsystems<br>- Easy to batch-process large datasets<br>- Built-in performance optimizations<br>- Mature ecosystem of scripts and add-ons |
| **Cons**           | - Limited to geometry tasks           | - Steeper learning curve for non-developers<br>- Complex scripts are harder to debug<br>- Slower iteration cycle     |
| **Real-time UX**   | Instant feedback & real-time updates  | Script-driven, needs run/reload     |

---

## FastMCP Server & Tools

- **Scene Information**  
  - `get_scene_info`  
  - `list_parts`  
  - `get_object_info`  
  - `init_model`  
- **Asset Management**  
  - `execute_blender_code`  
  - `replace_part`  
- **Node Group Ops**  
  - `has_node_group`  
  - `get_node_group_inputs`  
  - `set_node_group_input`  

**Server Setup**  
1. Blender Add-on listens on TCP port 9876.  
2. FastMCP server dispatches JSON commands.  
3. Commands execute on Blender’s main thread via timers.

---

## Project Examples

### 1. Modular Character Assembly  
Using MCP tools to build and swap character parts:
1. **Asset Import**  
   - `init_model` to spawn a base character mesh  
   - `execute_blender_code` to pull in ready-made head, waist, arms, legs from a remote asset server  
2. **Part Replacement Workflow**  
   - `list_parts` → identify “head”, “waist”, “arms”, “legs”  
   - `replace_part("head", new_head_asset_id)`  
   - Likewise for waist, arms, legs  
3. **Final Touches**  
   - Tweak materials/colors via Python API  
   - Pose adjustments via Geometry Nodes “Pose” node group

### 2. Low-Poly City Planning with NodeCity  
Combining Geometry Nodes for base layout with MCP-driven parameter tweaks:
1. **Base Generation**  
   - In Blender: Geometry Nodes “CityGenerator” creates streets + blocks  
2. **MCP-driven Customization**  
   - `has_node_group("CityGenerator")`  
   - `get_node_group_inputs("CityGenerator")` → fetch “block_size”, “road_width”, “building_height”  
   - `set_node_group_input("CityGenerator", "block_size", 12.0)`  
   - `set_node_group_input("CityGenerator", "building_height", 8.0)`  
3. **Asset Placement**  
   - `execute_blender_code` to scatter trees, benches, vehicles at designated points  
   - Real-time parameter adjustments via Claude → instant scene preview

---

## Batch AI NPC Production

By combining both **Modular Character Assembly** and **NodeCity** workflows with MCP tools, you can:

- **Batch-import and swap** hundreds of character parts programmatically  
- **Fine-tune materials, poses, and parameters** across large asset libraries in one go  
- **Automate variant generation** via loops or LLM-driven prompts  
- **Export ready-to-use NPCs** at scale for games or simulations  

This end-to-end pipeline demonstrates the feasibility of **batch AI–powered NPC production**, leveraging automated asset composition and real-time parameter control.  

