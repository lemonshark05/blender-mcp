import bpy
import os

def scan_geometry_node_groups_to_desktop():
    # Determine the path to the user's Desktop
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    filepath = os.path.join(desktop, "GeoNode_Scan_Output.txt")

    # Open (or create) the output file on the Desktop
    with open(filepath, "w", encoding="utf-8") as f:
        def writeln(line=""):
            f.write(line + "\n")

        # Iterate over all node groups in the .blend
        for ng in bpy.data.node_groups:
            # Only process Geometry Nodes groups
            if ng.bl_idname != 'GeometryNodeTree':
                continue

            writeln(f"\n=== Geometry Node Group: '{ng.name}' ===")

            # Find the Group Input and Group Output nodes
            group_in  = next((n for n in ng.nodes if n.bl_idname == 'NodeGroupInput'), None)
            group_out = next((n for n in ng.nodes if n.bl_idname == 'NodeGroupOutput'), None)

            # List interface inputs (sockets on the Group Input node)
            if group_in:
                writeln(">> Interface Inputs:")
                for sock in group_in.outputs:
                    default = getattr(sock, "default_value", None)
                    writeln(f"   • '{sock.name}' — type: {sock.type}, default: {default}")
            else:
                writeln(">> WARNING: Group Input node not found")

            # List interface outputs (sockets on the Group Output node)
            if group_out:
                writeln(">> Interface Outputs:")
                for sock in group_out.inputs:
                    writeln(f"   • '{sock.name}' — type: {sock.type}")
            else:
                writeln(">> WARNING: Group Output node not found")

            # List every node inside the group and its sockets
            writeln(">> Inside Nodes:")
            for node in ng.nodes:
                writeln(f"   • Node: '{node.name}' (bl_idname: {node.bl_idname})")
                # Node inputs
                for sock in node.inputs:
                    default = getattr(sock, "default_value", None)
                    writeln(f"       - IN:  '{sock.name}' — type: {sock.type}, default: {default}")
                # Node outputs
                for sock in node.outputs:
                    writeln(f"       - OUT: '{sock.name}' — type: {sock.type}")

        # Final status message
        writeln("\nScan complete. Output file:")
        writeln(filepath)

    # Print confirmation to the console (visible if Blender was launched from Terminal)
    print(f"[GeoNode Scan] Output written to: {filepath}")

# Execute the scan
scan_geometry_node_groups_to_desktop()