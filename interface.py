#!/usr/bin/env python3
"""
Text-Adventure Style Game Interface for Agents Playing Pokemon Red.
"""

import asyncio
import aioconsole
import logging

# Configure logger
logger = logging.getLogger("PokemonAI")
logger.setLevel(logging.INFO)

# Create file handler
import os
os.makedirs('logs', exist_ok=True)
fh = logging.FileHandler('logs/pokemon_ai.log', mode='w')
fh.setLevel(logging.INFO)

# Create formatter
formatter = logging.Formatter('%(message)s')
fh.setFormatter(formatter)

# Add handler to logger if not already present
if not logger.handlers:
    logger.addHandler(fh)

class InteractiveMode:
    """
    Minimal interactive mode for controlling the game from the command line.
    """
    
    def __init__(self, agent=None):
        """Initialize the interactive mode with an optional agent"""
        self.agent = agent
        self.valid_buttons = ["up", "down", "left", "right", "a", "b", "start", "select"]
        self.button_sequence = []
        self.last_button = None
    
    async def get_menu_action(self, client):
        """Handle user input during menu state"""
        # Check if we have a pending button sequence
        if self.button_sequence:
            button = self.button_sequence.pop(0)
            self.last_button = button
            return button
        
        # Start with default menu context
        recent_dialog = await self._get_recent_dialog(client)
        context = recent_dialog['context'] + self._show_menu_state(client) + self._show_battle_state(client)
        
        # Keep processing until we get a button
        while True:
            # Get command
            command = await self._get_command(context)
            
            # Process command
            result = await self._process_command(command, client)
            
            # If we got a button, return it
            if "button" in result:
                return result["button"]
            
            # If we got new context, show it
            if "context" in result:
                context = result["context"]
            else:
                # Default back to menu state context
                recent_dialog = await self._get_recent_dialog(client)
                context = recent_dialog['context'] + self._show_menu_state(client) + self._show_battle_state(client)
    
    async def get_default_action(self, client):
        """Handle user input during default (overworld) state"""
        # Check if we have a pending button sequence
        if self.button_sequence:
            button = self.button_sequence.pop(0)
            self.last_button = button
            return button
        
        # Start with default context
        recent_dialog = await self._get_recent_dialog(client)
        move_options = await self._show_move_options(client)
        context = recent_dialog['context'] + move_options
        
        # Keep processing until we get a button
        while True:
            # Get command
            command = await self._get_command(context)
            
            # Process command
            result = await self._process_command(command, client)
            
            # If we got a button, return it
            if "button" in result:
                return result["button"]
            
            # If we got new context, show it
            if "context" in result:
                context = result["context"]
            else:
                recent_dialog = await self._get_recent_dialog(client)
                context = recent_dialog['context'] + self._show_move_options(client)
    
    async def get_dialog_action(self, client):
        self._show_dialog_state(client)
        return "a"  # Auto-advance
    
    async def _get_command(self, context):
        """Get command from user or agent"""
        if self.agent is not None:
            return await self.agent.get_command(context)
        else:
            prompt = f"{context}\n Command:"
            try:
                # this prints the prompt to the console
                return await aioconsole.ainput(prompt)
            except asyncio.CancelledError:
                return ""
    
    def _create_visual_map(self, client):
        """Create a visual map representation with entities, warps, and player"""
        state = client.game_state.get("state", {})
        
        # Get the viewport tiles
        viewport_tiles = state.get("viewport", {}).get("tiles", [])
        if not viewport_tiles:
            return ""
        
        # Get player position for reference
        position = state.get("player", {}).get("position", (0, 0, "Unknown"))
        player_x, player_y, facing = position
        
        # Get entities
        entities = state.get("viewport", {}).get("entities", [])
        entity_positions = {}
        entity_info = []  # To store entity names and relative positions
        
        for entity in entities:
            entity_x = entity['position']['x']
            entity_y = entity['position']['y']
            entity_name = entity.get('name', 'Unknown Entity')
            
            # Calculate relative position to player
            rel_x = entity_x - player_x
            rel_y = entity_y - player_y
            
            # Determine direction description (e.g., "2 up", "3 left")
            x_desc = ""
            if rel_x != 0:
                x_desc = f"{abs(rel_x)} {'right' if rel_x > 0 else 'left'}"
                
            y_desc = ""
            if rel_y != 0:
                y_desc = f"{abs(rel_y)} {'down' if rel_y > 0 else 'up'}"
                
            rel_desc = ""
            if x_desc and y_desc:
                rel_desc = f"{y_desc}, {x_desc}"
            elif x_desc:
                rel_desc = x_desc
            elif y_desc:
                rel_desc = y_desc
            else:
                rel_desc = "Standing on it"
                
            # Store entity information
            entity_info.append(f"{entity_name}: {rel_desc}")
            
            # Mark position on map
            entity_positions[(entity_x, entity_y)] = 'E'  # Mark entity positions
        
        # Get warps
        warps = {}
        warp_info = []  # To store warp destinations and relative positions
        
        if 'map' in state and 'warps' in state['map']:
            for coords_str, destination in state['map']['warps'].items():
                coords_parts = coords_str.split(',')
                if len(coords_parts) == 2:
                    warp_x, warp_y = int(coords_parts[0]), int(coords_parts[1])
                    
                    # Calculate relative position to player
                    rel_x = warp_x - player_x
                    rel_y = warp_y - player_y
                    
                    # Determine direction description
                    x_desc = ""
                    if rel_x != 0:
                        x_desc = f"{abs(rel_x)} {'right' if rel_x > 0 else 'left'}"
                        
                    y_desc = ""
                    if rel_y != 0:
                        y_desc = f"{abs(rel_y)} {'down' if rel_y > 0 else 'up'}"
                        
                    rel_desc = ""
                    if x_desc and y_desc:
                        rel_desc = f"{y_desc}, {x_desc}"
                    elif x_desc:
                        rel_desc = x_desc
                    elif y_desc:
                        rel_desc = y_desc
                    else:
                        rel_desc = "same position"
                    
                    # Store warp information
                    warp_info.append(f"Warp to {destination}: {rel_desc}")
                    
                    # Mark position on map
                    warps[(warp_x, warp_y)] = 'D'  # Mark warp/door positions
        
        # Create map representation
        map_display = []
        
        # Create the map rows with symbols
        for y_idx, row in enumerate(viewport_tiles):
            display_row = []
            for x_idx, tile in enumerate(row):
                # Calculate absolute map coordinates from viewport position
                map_x = player_x + (x_idx - 4)
                map_y = player_y + (y_idx - 4)
                
                # Default display character based on tile type
                display_char = tile
                
                # Check if this is the player position
                if map_x == player_x and map_y == player_y:
                    display_char = '@'
                # Check if this is an entity position
                elif (map_x, map_y) in entity_positions:
                    display_char = 'E'
                # Check if this is a warp position
                elif (map_x, map_y) in warps:
                    display_char = 'D'
                # Replace tile codes with more semantic characters
                elif tile in ['v', '<', '>']:
                    display_char = tile  # Keep ledges as they are
                elif tile == 'W':
                    display_char = 'W'  # Water
                elif tile == 'T':
                    display_char = 'T'  # Tree
                elif tile == 'G':
                    display_char = 'G'  # Grass
                elif tile == '1':
                    display_char = '.'  # Walkable path
                elif tile == '0':
                    display_char = 'X'  # Wall/object (something solid in-game)
                elif tile == '#':
                    display_char = '#'  # Off-map area (black space)
                
                display_row.append(display_char)
            
            # Only add the row if it has content (not all off-map)
            if any(char != '#' for char in display_row):
                map_display.append(' '.join(display_row))
        
        # Add entity information
        if entity_info:
            map_display.append("")
            map_display.append("Entities:")
            for info in entity_info:
                map_display.append(f"  - {info}")
        
        # Add warp information
        if warp_info:
            map_display.append("")
            map_display.append("Warps:")
            for info in warp_info:
                map_display.append(f"  - {info}")
        
        # Note: We're removing the legend from here as it will be 
        # generated contextually in the _show_move_options function
        
        return "\n".join(map_display)
    
    async def _show_move_options(self, client):
        """Display movement options in text adventure format with improved presentation"""
        state = client.game_state.get("state", {})
        
        # Build output string
        output = []
        
        # Add clear game state header
        output.append("=== GAME STATE: EXPLORATION ===")
        
        # Show position, map, and direction
        position = state.get("player", {}).get("position", (0, 0, "Unknown"))
        map_name = state.get("map", {}).get("name", "Unknown")
        x, y, facing = position
        
        # More natural phrasing for location
        output.append(f"\nYou are in {map_name} facing {facing}")
        
        # Create and add visual map display
        output.append("\nMAP VIEW:")
        
        # Get the viewport tiles (for creating contextual legend later)
        viewport_tiles = state.get("viewport", {}).get("tiles", [])
        
        # Create visual map but don't add legend yet
        visual_map_lines = self._create_visual_map(client).split('\n')
        
        # Extract the actual map part and entity/warp information
        actual_map_lines = []
        entities_warps_info = []
        for line in visual_map_lines:
            if line.startswith("Legend:"):
                # Stop when we reach the legend section
                break
            elif line.strip() == "Entities:" or line.strip() == "Warps:":
                # Start collecting entity/warp info
                entities_warps_info.append(line)
            elif entities_warps_info:
                # Continue collecting entity/warp info
                entities_warps_info.append(line)
            else:
                # Collect the actual map display
                actual_map_lines.append(line)
        
        # Add the map and entity/warp info to output
        output.extend(actual_map_lines)
        if entities_warps_info:
            output.extend(entities_warps_info)
        
        # Create a contextual legend based on what's actually in the viewport
        # Collect tile types present in the current viewport
        present_tiles = set()
        for row in viewport_tiles:
            for tile in row:
                present_tiles.add(tile)
        
        # Always include player, walkable path, and wall
        present_tiles.add('@')
        present_tiles.add('.')
        present_tiles.add('#')
        
        # Check if entities are present
        if any("Entities:" in line for line in entities_warps_info):
            present_tiles.add('E')
        
        # Check if warps are present
        if any("Warps:" in line for line in entities_warps_info):
            present_tiles.add('D')
        
        # Create contextual legend
        output.append("\nLegend:")
        if '@' in present_tiles:
            output.append("@ - Player")
        if 'E' in present_tiles:
            output.append("E - Entity/NPC")
        if 'D' in present_tiles:
            output.append("D - Door/Warp")
        if '.' in present_tiles or '1' in present_tiles:
            output.append(". - Walkable path")
        if '0' in present_tiles:
            output.append("X - Wall or object")
        if '#' in present_tiles:
            output.append("# - Off-map area (outside the accessible area)")
        if 'G' in present_tiles:
            output.append("G - Grass (may contain wild Pokémon)")
        if 'W' in present_tiles:
            output.append("W - Water (requires Surf)")
        if 'T' in present_tiles:
            output.append("T - Tree (requires Cut)")
        if 'v' in present_tiles or '<' in present_tiles or '>' in present_tiles:
            output.append("v,<,> - Ledges (one-way paths)")

        # Define directions and their relative coordinates
        directions = {
            "Up": (0, -1),
            "Down": (0, 1),
            "Left": (-1, 0),
            "Right": (1, 0)
        }
        
        # Get player's current tile
        current_tile = "?"
        if viewport_tiles and len(viewport_tiles) > 4 and len(viewport_tiles[4]) > 4:
            current_tile = viewport_tiles[4][4]
        
        # Check if player is on water (surfing)
        is_surfing = current_tile == "W"
        
        # Get warps
        warps = {}
        if 'map' in state and 'warps' in state['map']:
            for coords_str, destination in state['map']['warps'].items():
                coords_parts = coords_str.split(',')
                if len(coords_parts) == 2:
                    warp_x, warp_y = int(coords_parts[0]), int(coords_parts[1])
                    warps[(warp_x, warp_y)] = destination
        
        # Check if player is standing on a warp
        player_on_warp = (x, y) in warps
        player_warp_dest = warps.get((x, y), "")
        
        # Get recent movement history to determine warp context
        recent_movements = []
        try:
            recent_movements = await client.get_recent_entries(entry_type="movement", count=3)
        except Exception:
            pass
        
        # Determine if we just warped (different maps in movement history)
        just_warped = False
        on_door = False
        if len(recent_movements) >= 2:
            last_map = recent_movements[-2]["data"]["map"]
            current_map = recent_movements[-1]["data"]["map"]
            if last_map != current_map:
                just_warped = True
            elif player_on_warp:
                # We're on a warp but didn't just warp = we're on a door
                on_door = True
                
        # Get entities
        entities = state.get("viewport", {}).get("entities", [])
        
        # Current player state description
        status_desc = []
        if is_surfing:
            status_desc.append("You are surfing on water")
        
        if player_on_warp:
            if just_warped:
                status_desc.append(f"You just arrived here through a warp from another map")
            elif on_door:
                status_desc.append(f"You are standing at the entrance to {player_warp_dest}")
            else:
                status_desc.append(f"You are standing on a warp point to {player_warp_dest}")
        
        # Show player state
        if status_desc:
            output.append("\nSTATUS: " + " ".join(status_desc))
        
        # Get surrounding information in each direction for text adventure format
        output.append("\nAROUND YOU:")
        
        # Track available actions
        movement_actions = []
        interaction_actions = []
        
        # First check what's in each direction
        direction_info = {}
        
        # [Direction checking code - kept the same]
        for direction, (dx, dy) in directions.items():
            # Calculate adjacent position in absolute map coordinates
            adj_x, adj_y = x + dx, y + dy
            
            # Calculate the viewport index for the adjacent tile
            view_y = 4 + dy
            view_x = 4 + dx
            
            # Default values
            tile_code = "#"
            can_move = False
            has_entity = False
            entity_name = ""
            is_warp = False
            warp_dest = ""
            interesting_object = False
            
            # Get tile information
            if viewport_tiles and 0 <= view_y < len(viewport_tiles) and 0 <= view_x < len(viewport_tiles[0]):
                tile_code = viewport_tiles[view_y][view_x]
            
            # Check for entities at the adjacent position
            for entity in entities:
                entity_x = entity['position']['x']
                entity_y = entity['position']['y']
                if entity_x == adj_x and entity_y == adj_y:
                    has_entity = True
                    entity_name = entity.get('name', 'Unknown Entity')
                    break
            
            # Check for warps at the adjacent position
            if (adj_x, adj_y) in warps:
                is_warp = True
                warp_dest = warps[(adj_x, adj_y)]
            
            # Door handling logic
            if on_door:
                if tile_code == "#":
                    can_move = True
                    is_warp = True
                    warp_dest = player_warp_dest
                elif tile_code in ["1", ".", "G"]:
                    can_move = True
                    tile_code = '.'
            else:
                # Regular movement logic
                if tile_code in ["1", ".", "G"]:
                    can_move = True
                    if (adj_x, adj_y) in warps:
                        is_warp = True
                        warp_dest = warps[(adj_x, adj_y)]
                elif tile_code == "W":
                    can_move = is_surfing
                    if not is_surfing:
                        interesting_object = True
                elif tile_code == "T":
                    can_move = False
                    interesting_object = True
                elif tile_code == "<" and direction.lower() == "left":
                    can_move = True
                elif tile_code == ">" and direction.lower() == "right":
                    can_move = True
                elif tile_code == "v" and direction.lower() == "down":
                    can_move = True
                elif tile_code == "0":
                    interesting_object = True  # Real in-game object
            
            # Store information for the direction
            direction_info[direction] = {
                "tile": tile_code,
                "can_move": can_move,
                "entity": entity_name if has_entity else None,
                "is_warp": is_warp,
                "warp_dest": warp_dest,
                "interesting_object": interesting_object or has_entity
            }
            
            # Format information for text adventure style
            desc = ""
            if has_entity:
                desc = f"{direction.lower()}: {entity_name}"
                if direction.lower() == facing.lower():
                    interaction_actions.append(f"A: interact with {entity_name}")
                elif direction.lower() != facing.lower():
                    movement_actions.append(f"{direction.lower()}: Turn to face {entity_name}")
            elif is_warp:
                if tile_code == "#" and on_door:
                    desc = f"{direction.lower()}: Doorway leading to {warp_dest}"
                elif tile_code in ["1", ".", "G"] and on_door:
                    desc = f"{direction.lower()}: Another doorway to {warp_dest}"
                else:
                    desc = f"{direction.lower()}: Path to {warp_dest}"
                    
                if can_move:
                    if on_door and tile_code == "#":
                        movement_actions.append(f"{direction.lower()}: Enter {warp_dest}")
                    else:
                        movement_actions.append(f"{direction.lower()}: Go toward {warp_dest}")
                elif direction.lower() != facing.lower():
                    movement_actions.append(f"{direction.lower()}: Turn to face the path to {warp_dest}")
            else:
                # Format different tile types
                if tile_code == "1" or tile_code == ".":
                    desc = f"{direction.lower()}: Clear path"
                elif tile_code == "G":
                    desc = f"{direction.lower()}: Grass (may encounter wild Pokémon)"
                elif tile_code == "W":
                    desc = f"{direction.lower()}: Water (requires Surf)"
                elif tile_code == "T":
                    desc = f"{direction.lower()}: Small tree (requires Cut)"
                elif tile_code in ["<", ">", "v"]:
                    desc = f"{direction.lower()}: Ledge"
                elif tile_code == "0":
                    desc = f"{direction.lower()}: Object or wall"
                elif tile_code == "#":
                    desc = f"{direction.lower()}: Off-map"
                else:
                    desc = f"{direction.lower()}: {tile_code} tile"
                
                if can_move:
                    movement_actions.append(f"{direction.lower()}: move {direction.lower()}")
                # Add facing action for interesting but not walkable tiles
                elif interesting_object and direction.lower() != facing.lower():
                    if tile_code == "W":
                        movement_actions.append(f"{direction.lower()}: Turn to face the water")
                    elif tile_code == "T":
                        movement_actions.append(f"{direction.lower()}: Turn to face the tree")
                    elif tile_code == "0":
                        movement_actions.append(f"{direction.lower()}: Turn to face the object")
                    else:
                        movement_actions.append(f"{direction.lower()}: Turn to face {direction.lower()}")
            
            # Add the description to the output
            if desc:
                output.append(f"  {desc}")
        
        # Show available actions with better grouping
        output.append("\nAVAILABLE ACTIONS:")
        
        # Movement actions
        if movement_actions:
            output.append("  MOVEMENT:")
            for action in movement_actions:
                output.append(f"  • {action}")
        

        # Check what the player is facing to provide contextual interaction options
        facing_direction = facing.lower()
        facing_coord = None
        
        # Map facing direction to directional offset
        if facing_direction == "up":
            facing_coord = "Up"
        elif facing_direction == "down":
            facing_coord = "Down"
        elif facing_direction == "left":
            facing_coord = "Left"
        elif facing_direction == "right":
            facing_coord = "Right"
        
        # Get info about what we're facing
        facing_info = direction_info.get(facing_coord, {})
        facing_tile = facing_info.get("tile", "")
        facing_entity = facing_info.get("entity")
        
        # Simple check for interactable objects
        can_interact = facing_entity or facing_tile in ["X", "T", "W"]
        
        if can_interact:
            output.append("  INTERACTION:")
            if facing_entity:
                output.append(f"  • A: Talk to {facing_entity}")
            else:
                output.append("  • A: Interact with what's in front of you")

        
        # Menu actions
        output.append("  MENU:")
        output.append("  • START: Open POKEMON menu")
        
        # Client commands
        output.append("  CLIENT:")
        output.append("  • state - Show detailed game state")
        output.append("  • help - Display help information")
        
        # Return the complete output
        return "\n".join(output)
    
    def _show_menu_state(self, client):
        """Show current menu state in text adventure format with neutral presentation"""
        state = client.game_state.get("state", {})
        menu_state = state.get("text", {}).get("menu_state", {})
        
        # Build output string
        output = []
        
        # Clearly identify this as a menu context
        output.append("=== GAME STATE: MENU ===")
        
        # Show current selection
        cursor_text = menu_state.get("cursor_text", "Unknown")
        cursor_pos = menu_state.get("cursor_pos", (0, 0))
        
        # Show raw OCR text - preserving the exact menu layout
        ocr_lines = state.get("text", {}).get("OCR", [])
        if ocr_lines:
            output.append("\nCURRENT MENU:")
            for line in ocr_lines:
                output.append(f"  {line}")
            
            # Add explicit cursor position explanation
            if cursor_text:
                output.append(f"\nCursor (▶) is currently on: {cursor_text}")
        
        # Display all available actions equally without preference
        output.append("\nAVAILABLE ACTIONS:")
        output.append(f"  • A: Select the current cursor option ({cursor_text})")
        output.append("  • B: Cancel/Go back")
        output.append("  • UP/DOWN: Move cursor between options")
        output.append("  • LEFT/RIGHT: Move cursor between columns (if available)")
        output.append("  • START: Confirm (used primarily when naming characters)")
        
        # Add client commands
        output.append("\nCLIENT COMMANDS:")
        output.append("  • state - Show detailed game state")
        output.append("  • journal [type] [count] - Show recent journal entries")
        output.append("  • help - Display help information")
        
        # Return the complete output
        result = "\n".join(output)
        return result
    
    def _show_dialog_state(self, client):
        """Show dialog state in text adventure format"""
        dialog_lines = client.game_state.get("state", {}).get("text", {}).get("dialog", [])
        output = ["CONVERSATION"]
        
        # Get current map and entities for context
        state = client.game_state.get("state", {})
        map_name = state.get("map", {}).get("name", "Unknown")
        entities = state.get("viewport", {}).get("entities", [])
        
        # Try to identify who might be speaking
        speaker = "Someone"
        # Find the entity directly in front of the player
        player_pos = state.get("player", {}).get("position", (0, 0, "Unknown"))
        if player_pos:
            x, y, facing = player_pos
            # Calculate position in front of player
            if facing == "Up":
                front_x, front_y = x, y - 1
            elif facing == "Down":
                front_x, front_y = x, y + 1
            elif facing == "Left":
                front_x, front_y = x - 1, y
            elif facing == "Right":
                front_x, front_y = x + 1, y
            else:
                front_x, front_y = x, y
            
            # Check if any entity is at this position
            for entity in entities:
                entity_x = entity['position']['x']
                entity_y = entity['position']['y']
                if entity_x == front_x and entity_y == front_y:
                    speaker = entity.get('name', 'Someone')
                    break
        
        # Format dialog as a conversation
        if dialog_lines:
            dialog_text = " ".join(dialog_lines)
            output.append(f"\n{speaker} says:")
            output.append(f'  "{dialog_text}"')
        
        # Show available actions
        output.append("\nAVAILABLE ACTIONS:")
        output.append("  • Continue (press A)")
        
        # Add client commands
        output.append("\nCLIENT COMMANDS:")
        output.append("  • state - Show detailed game state")
        output.append("  • help - Display help information")
        
        result = "\n".join(output)
        return result
    
    def _show_help(self):
        """Show help text"""
        output = [
            "\nAvailable queries:",
            "  state - Show detailed game state",
            "  journal [type] [count] - Show recent journal entries",
            "    Types: movement, dialog, menu, action, state_transition, all",
            "    Examples: 'journal dialog 5', 'journal all 10'",
            "  help - Show this help message\n"
        ]
        
        # Log the complete output
        result = "\n".join(output)
        return result
    
    async def _get_recent_dialog(self, client):
        """
        Get all dialog entries since the most recent non-dialog action.
        This allows us to capture complete conversations that occurred
        after the player made a deliberate non-dialog action.
        """
        # Get a reasonable number of recent actions to examine
        action_entries = await client.get_recent_entries(count=30, entry_type="action")
        if not action_entries:
            return {"context": ""}
        
        # Find the most recent non-dialog action
        non_dialog_action = None
        for action in action_entries[::-1]:
            state = action.get("data", {}).get("state", "")
            if state != "dialog":
                non_dialog_action = action
                break
        
        # If we didn't find a non-dialog action, use the oldest action we have
        if not non_dialog_action and action_entries:
            non_dialog_action = action_entries[-1]
        
        # Get reference frame
        reference_frame = non_dialog_action.get("frame", 0)
        
        # Get all dialog entries since that frame
        dialog_entries = await client.get_entries_since_frame(reference_frame, entry_type="dialog")
        
        # Format entries
        if dialog_entries:
            context = self._format_journal_entries(dialog_entries, "dialog", 
                                                title=f"DIALOG:")
        else:
            context = ""
        
        return {"context": context}
    
    def _format_journal_entries(self, entries, entry_type=None, title=None):
        """Format journal entries for display"""
        if not entries:
            return ""
        
        output = []
        if title:
            output.append(f"\n=== {title.upper()} ===")
        else:
            output.append(f"\n=== {entry_type.upper() if entry_type else 'JOURNAL'} ENTRIES ===")
        
        # Format based on entry type
        for entry in entries:
            entry_time = entry.get("frame", 0)
            entry_type = entry.get("type", "unknown")
            entry_data = entry.get("data", {})
            
            if entry_type == "dialog":
                dialog_text = " ".join(entry_data) if isinstance(entry_data, list) else str(entry_data)
                output.append(f"\"{dialog_text}\"")
            
            elif entry_type == "movement":
                position = entry_data.get("position", (0, 0, "Unknown"))
                map_name = entry_data.get("map", "Unknown")
                x, y, facing = position
                output.append(f"Moved to {map_name} ({x}, {y}) facing {facing}")
            
            elif entry_type == "menu":
                cursor_text = entry_data.get("cursor_text", "Unknown")
                cursor_pos = entry_data.get("cursor_pos", (0, 0))
                output.append(f"Menu selection - '{cursor_text}' at position {cursor_pos}")
            
            elif entry_type == "action":
                button = entry_data.get("button", "Unknown")
                state = entry_data.get("state", "Unknown")
                output.append(f"Button {button} pressed in {state} state")
            
            elif entry_type == "state_transition":
                from_state = entry_data.get("from", "Unknown")
                to_state = entry_data.get("to", "Unknown")
                duration = entry_data.get("duration", 0)
                output.append(f"State changed from {from_state} to {to_state} (duration: {duration} frames)")
            
            else:
                # Generic handling for other entry types
                output.append(f"{entry_type} - {entry_data}")
        
        return "\n".join(output) + '\n\n'

    def _show_state(self, client):
        """Show detailed information about the current game state"""
        game_state = client.game_state.get("state", {})
        
        # Build output string
        output = []
        output.append(f"\n=== GAME STATE: {client.game_state.get('current_state_type', 'unknown')} ===")
        output.append(f"Last Button: {game_state.get('last_button', 'None')}")
        
        # Map data
        if game_state.get('map', {}).get('dimensions') != [0, 0]:
            output.append("\n=== MAP DATA ===")
            output.append(f"Current Map: {game_state.get('map', {}).get('name', 'Unknown')}")
            player_position = game_state.get('player', {}).get('position', (0, 0, 'Unknown'))
            player_x, player_y, facing = player_position
            if facing == 'Null':
                facing = 'Up'
            output.append(f"You are facing: {facing}")
            badges = game_state.get('player', {}).get('badges', [])
            output.append(f"Badges: {', '.join(badges) if badges else 'None'}")
        
        # Battle data
        if game_state.get('is_in_battle', False):
            output.append("\n=== BATTLE DATA ===")
            battle = game_state.get('battle', {})
            battle_type = "Trainer" if battle.get("is_trainer_battle", False) else "Wild"
            output.append(f"On turn {battle.get('turn_counter', 0)} of {battle_type} battle")
            
            # Player's active Pokémon
            player_team = game_state.get('player', {}).get('team', {})
            if player_team and player_team.get('pokemon', []):
                active_pokemon = player_team['pokemon'][0]
                output.append("\nPLAYER POKÉMON:")
                output.append(f"  • {active_pokemon.get('nickname', 'Unknown')} ({active_pokemon.get('species_id', 'Unknown')}) Lv.{active_pokemon.get('level', '?')}")
                output.append(f"    HP: {active_pokemon.get('current_hp', '?')}/{active_pokemon.get('max_hp', '?')} | Status: {active_pokemon.get('status', 'Unknown')}")
            
            # Enemy Pokémon
            if 'enemy_pokemon' in battle:
                enemy = battle['enemy_pokemon']
                output.append("\nENEMY POKÉMON:")
                output.append(f"  • {enemy.get('nickname', enemy.get('species_name', 'Unknown'))} ({enemy.get('species_name', 'Unknown')}) Lv.{enemy.get('level', '?')}")
                output.append(f"    HP: {enemy.get('hp_percent', '?')}% | Status: {enemy.get('status', 'Unknown')}")
                output.append(f"    Types: {', '.join(filter(None, enemy.get('types', ['Unknown'])))}")
        
        # Item bag
        player_bag = game_state.get('player', {}).get('bag', [])
        if player_bag:
            output.append("\n=== ITEM BAG DATA ===")
            for item_name, quantity in player_bag:
                output.append(f"  • {item_name} x{quantity}")
        
        # Team data
        player_team = game_state.get('player', {}).get('team', {})
        if player_team and player_team.get('pokemon', []):
            output.append("\n=== TEAM DATA ===")
            for pokemon in player_team['pokemon']:
                output.append(f"  • {pokemon.get('nickname', 'Unknown')} ({pokemon.get('species_id', 'Unknown')}) Lv.{pokemon.get('level', '?')}")
                output.append(f"    HP: {pokemon.get('current_hp', '?')}/{pokemon.get('max_hp', '?')} | Status: {pokemon.get('status', 'Unknown')}")
                output.append(f"    Types: {', '.join(filter(None, pokemon.get('types', ['Unknown'])))}")
                output.append(f"    Moves: {', '.join(pokemon.get('moves', ['None']))}")
                
                # Show stats in a compact format
                if 'stats' in pokemon:
                    stats = pokemon['stats']
                    stats_str = " | ".join([f"{k}: {v}" for k, v in stats.items()])
                    output.append(f"    Stats: {stats_str}")
        
        # Menu information
        menu_state = game_state.get('text', {}).get('menu_state', {})
        if menu_state.get('cursor_pos') is not None:
            output.append("\n=== OCR ===")
            for line in game_state.get('text', {}).get("OCR", []):
                output.append(f"  {line}")
            output.append("\n=== MENU INFO ===")
            if menu_state.get('cursor_text'):
                output.append(f"  Current Menu Option: '{menu_state['cursor_text']}'")
        
        return "\n".join(output)

    def _show_battle_state(self, client):
        game_state = client.game_state.get("state", {})
        # Build output string
        output = []
        # Battle data
        if game_state.get('is_in_battle', False):
            output.append("\n=== BATTLE DATA ===")
            battle = game_state.get('battle', {})
            battle_type = "Trainer" if battle.get("is_trainer_battle", False) else "Wild"
            output.append(f"{battle_type} battle")
            
            # Player's active Pokémon
            player_team = game_state.get('player', {}).get('team', {})
            if player_team and player_team.get('pokemon', []):
                active_pokemon = player_team['pokemon'][0]
                output.append("\nPLAYER POKÉMON:")
                output.append(f"  • {active_pokemon.get('nickname', 'Unknown')} ({active_pokemon.get('species_id', 'Unknown')}) Lv.{active_pokemon.get('level', '?')}")
                output.append(f"    HP: {active_pokemon.get('current_hp', '?')}/{active_pokemon.get('max_hp', '?')} | Status: {active_pokemon.get('status', 'Unknown')}")
            
            # Enemy Pokémon
            if 'enemy_pokemon' in battle:
                enemy = battle['enemy_pokemon']
                output.append("\nENEMY POKÉMON:")
                output.append(f"  • {enemy.get('nickname', enemy.get('species_name', 'Unknown'))} ({enemy.get('species_name', 'Unknown')}) Lv.{enemy.get('level', '?')}")
                output.append(f"    HP: {enemy.get('hp_percent', '?')}% | Status: {enemy.get('status', 'Unknown')}")
                output.append(f"    Types: {', '.join(filter(None, enemy.get('types', ['Unknown'])))}")
        
        # Item bag
        player_bag = game_state.get('player', {}).get('bag', [])
        if player_bag:
            output.append("\n=== ITEM BAG DATA ===")
            for item_name, quantity in player_bag:
                output.append(f"  • {item_name} x{quantity}")
        
        # Team data
        player_team = game_state.get('player', {}).get('team', {})
        if player_team and player_team.get('pokemon', []):
            output.append("\n=== TEAM DATA ===")
            for pokemon in player_team['pokemon']:
                output.append(f"  • {pokemon.get('nickname', 'Unknown')} ({pokemon.get('species_id', 'Unknown')}) Lv.{pokemon.get('level', '?')}")
                output.append(f"    HP: {pokemon.get('current_hp', '?')}/{pokemon.get('max_hp', '?')} | Status: {pokemon.get('status', 'Unknown')}")
                output.append(f"    Types: {', '.join(filter(None, pokemon.get('types', ['Unknown'])))}")
                output.append(f"    Moves: {', '.join(pokemon.get('moves', ['None']))}")
                
                # Show stats in a compact format
                if 'stats' in pokemon:
                    stats = pokemon['stats']
                    stats_str = " | ".join([f"{k}: {v}" for k, v in stats.items()])
                    output.append(f"    Stats: {stats_str}")

        return "\n".join(output)
    
    async def _process_command(self, command, client):
        """Process a command and return a button if applicable"""
        command = command.strip().lower() if command else ""
        
        # Empty command
        if not command:
            return {}
        
        # Direct button press
        if command in self.valid_buttons:
            print(f"button: {command}")
            return {"button": command}
        
        # Check for button sequence (comma-separated)
        if "," in command:
            buttons = [btn.strip() for btn in command.split(",")]
            valid_sequence = all(btn in self.valid_buttons for btn in buttons)
            if valid_sequence and buttons:
                self.button_sequence = buttons[1:]  # Queue all but first
                return {"button": buttons[0]}  # Return first immediately
        
        # Help command
        if command == "help":
            context = self._show_help()
            return {"context": context}
        
        # State command
        if command == "state":
            context = self._show_state(client)
            return {"context": context}
        
        # Unknown command - assume it's a button if short
        if len(command) <= 6:
            logger.info(f"Trying to press button: {command}")
            return {"button": command}
        
        logger.info(f"Unknown command: {command}")
        return {}