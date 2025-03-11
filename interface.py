#!/usr/bin/env python3
"""
Interactive mode handler for Pokémon AI Client

This module provides the InteractiveMode class to handle user input
for manual control and journal/graph queries in the phase-based architecture.
"""

import asyncio
import base64
import os
import aioconsole
import logging
import networkx as nx

os.makedirs('logs', exist_ok=True)

# Configure logger
logger = logging.getLogger("PokemonAI") 
logger.setLevel(logging.INFO)

# Clear and create file handler
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
    Handles interactive user input during different game states,
    allowing for journal queries, path finding, and manual button control.
    """
    
    def __init__(self, agent=None):
        self.agent = agent
        self.valid_buttons = ["up", "down", "left", "right", "a", "b", "start", "select"]
        
        self.last_button = None
        self.screenshots_dir = "screenshots"
        self.last_prompt_frame = 0
        
        # Add button sequence support
        self.button_sequence = []
        
        # Create screenshots directory if it doesn't exist
        if not os.path.exists(self.screenshots_dir):
            os.makedirs(self.screenshots_dir)
    
    async def get_menu_action(self, blackboard):
        """Handle user input during menu state"""
        # Check if we have a pending button sequence
        if self.button_sequence:
            button = self.button_sequence.pop(0)
            self.last_button = button
            logger.info(f"Executing sequence button: {button} ({len(self.button_sequence)} remaining)")
            return button
            
        await self.show_journal_since_last_prompt(blackboard)
        await self._show_menu_text(blackboard)
        menu_state = blackboard.game_state.get("text", {}).get("menu_state", {})
        cursor_text = menu_state.get("cursor_text", "")
        current_item = menu_state.get("current_item", -1)
        max_item = menu_state.get("max_item", -1)
        
        prompt_msg = f"INTERACTIVE MENU"
        if cursor_text:
            prompt_msg += f" on '{cursor_text}' (item {current_item+1}/{max_item+1})"
            
        # Add last button info if available
        if self.last_button:
            prompt_msg += f" [Last: {self.last_button}]"
            
        logger.info(f"{prompt_msg} - Enter command or button:")
        self.last_prompt_frame = blackboard.game_state.get("frame", 0)
        # Get user input until a valid action is determined
        while True:
            command = await self._get_command()
            result = await self._process_command(command, blackboard)
            
            # Return button if one was selected
            if "button" in result:
                self.last_button = result["button"]
                return result["button"]
                
            # Otherwise, refresh prompt and try again
            logger.info(f"{prompt_msg} - Enter command or button:")
    
    async def get_default_action(self, blackboard):
        """Handle user input during default (overworld) state"""
        # Check if we have a pending button sequence
        if self.button_sequence:
            button = self.button_sequence.pop(0)
            self.last_button = button
            logger.info(f"Executing sequence button: {button} ({len(self.button_sequence)} remaining)")
            return button
            
        await self.show_journal_since_last_prompt(blackboard)
        await self._show_surroundings(blackboard)
        position = blackboard.game_state.get("player", {}).get("position", (0, 0, "Null"))
        map_name = blackboard.game_state.get("map", {}).get("name", "Unknown")
        if position[2] != 'Null':
            prompt_msg = f"INTERACTIVE MAP: {map_name} at {position}"
        else:
            prompt_msg = f"INTERACTIVE MAP:"
        if self.last_button:
            prompt_msg += f" [Last: {self.last_button}]"
        self.last_prompt_frame = blackboard.game_state.get("frame", 0)
        logger.info(f"{prompt_msg} - Enter command or button:")
        
        # Get user input until a valid action is determined
        while True:
            command = await self._get_command()
            result = await self._process_command(command, blackboard)
            
            # Return button if one was selected
            if "button" in result:
                self.last_button = result["button"]
                return result["button"]
                
            # Otherwise, refresh prompt and try again
            logger.info(f"{prompt_msg} - Enter command or button:")
    
    async def _get_command(self):
        """Get command either from agent or console"""
        if self.agent is not None:
            return await self.agent.get_command()
        else:
            prompt = "> "
            try:
                return await aioconsole.ainput(prompt)
            except asyncio.CancelledError:
                return ""
    
    async def _show_help_text(self, blackboard):
        """Show enhanced help text with contextual information about available data"""
        # Get current map name for map command context
        current_map = blackboard.game_state.get("map", {}).get("name", "Unknown")
        
        # Get dialog history count
        dialog_count = len([e for e in blackboard.journal if e["type"] == "dialog"])
        
        # Get movement history count
        movement_count = len([e for e in blackboard.journal if e["type"] == "movement"])
        
        # Get total journal entry count
        journal_count = len(blackboard.journal)
        
        # Get list of visited maps
        visited_maps = set()
        for node_id, data in blackboard.world_graph.nodes(data=True):
            if data.get('visited', False):
                map_name, _, _ = node_id
                visited_maps.add(map_name)
        
        # Get goals information
        goal_count = len(getattr(blackboard, "goals", []))
        open_goals = sum(1 for g in getattr(blackboard, "goals", []) if not g.get("completed", False))
        
        # Create and display the enhanced help text
        help_text = f"""
    Available commands:
    up, down, left, right, a, b, start, select - Press the specified button

    dialog [n]         - Show last n dialog entries (default: 25)
                        ({dialog_count} dialog entries available)

    movements [n]      - Show last n movement entries (default: 25)
                        ({movement_count} movement entries available)

    query [n] [text]   - Search journal for entries containing text
                    - If only a number is provided, shows last n entries
                    - If no arguments, shows last 10 entries
                    ({journal_count} total journal entries)

    map [mapname]      - Show map view (current map: {current_map} or specify from {len(visited_maps)} visited maps)

    explore [options]  - Automatically explore the current map
                - Options:
                  * see-only: Only reveal all tiles (don't traverse all)
                  * interact-entities: Interact with all entities
                  * interact-tiles: Interact with all walls and objects


    atlas              - List all visited maps with summary information
                        ({len(visited_maps)} maps visited)

    state              - Show detailed current game state

    screen             - Access the screen image data

    note [text]        - Add a note to the journal

    goal [add|list|complete] [text] - Manage goals/todos
                                    ({goal_count} goals, {open_goals} open)

    help               - Show this help message
    """
        
        await asyncio.sleep(0.1)
        logger.info(help_text)
        return True

    async def _process_screen(self, command, blackboard):
        """Process screen-related commands to access and manipulate screen data"""
        if not blackboard.game_state.get("screen"):
            logger.info("No screen data available")
            return {}
            
        # Parse command
        parts = command.split()
        action = parts[1] if len(parts) > 1 else "info"
        
        # Get screen data as base64
        screen_b64 = blackboard.game_state.get("screen", "")
        
        if not screen_b64:
            logger.info("Screen data is empty")
            return {}
            
        # Decode screen data
        try:
            screen_bytes = base64.b64decode(screen_b64)
            
            return screen_bytes
                
        except Exception as e:
            logger.error(f"Error processing screen data: {e}")
            return 
    
    async def _process_note(self, command, blackboard):
        """Process note command to add a note to the journal"""
        # Extract the note text (everything after "note ")
        note_text = command[5:].strip()
        
        if not note_text:
            logger.info("Note cannot be empty")
            return {}
            
        # Add note to journal
        current_frame = blackboard.game_state.get("frame", 0)
        position = blackboard.game_state.get("player", {}).get("position", (0, 0, "Unknown"))
        map_name = blackboard.game_state.get("map", {}).get("name", "Unknown")
        
        # Create note entry
        note_entry = {
            "type": "note",
            "frame": current_frame,
            "data": {
                "text": note_text,
                "position": position,
                "map": map_name,
            }
        }
        
        # Add to blackboard journal
        blackboard.journal.append(note_entry)
        
        logger.info(f"Note added to journal: {note_text}")
        return {}
    
    async def _process_goal(self, command, blackboard):
        """Process goal command to manage goals/todos in the journal"""
        parts = command.split(maxsplit=2)
        
        if len(parts) < 2:
            logger.info("Usage: goal [add|list|complete|remove] [text|number]")
            return {}
            
        action = parts[1].lower()
        
        # Initialize goals list if it doesn't exist
        if not hasattr(blackboard, "goals"):
            blackboard.goals = []
            
        # Handle list action
        if action == "list":
            if not blackboard.goals:
                logger.info("No goals in the list")
            else:
                logger.info("Current goals:")
                for i, goal in enumerate(blackboard.goals):
                    status = "✓" if goal.get("completed", False) else "□"
                    logger.info(f"{i+1}. [{status}] {goal['text']}")
            return {}
            
        # Handle add action
        elif action == "add" and len(parts) >= 3:
            goal_text = parts[2].strip()
            if not goal_text:
                logger.info("Goal text cannot be empty")
                return {}
                
            current_frame = blackboard.game_state.get("frame", 0)
            # Add goal
            blackboard.goals.append({
                "text": goal_text,
                "created": current_frame,
                "completed": False
            })
            
            # Add to journal
            note_entry = {
                "type": "goal",
                "frame": current_frame,
                "data": {
                    "action": "add",
                    "text": goal_text,
                }
            }
            blackboard.journal.append(note_entry)
            
            logger.info(f"Goal added: {goal_text}")
            return {}
            
        # Handle complete action
        elif action == "complete" and len(parts) >= 3:
            try:
                # Check if it's a number (index)
                goal_index = int(parts[2]) - 1
                if 0 <= goal_index < len(blackboard.goals):
                    blackboard.goals[goal_index]["completed"] = True
                    
                    # Add to journal
                    current_frame = blackboard.game_state.get("frame", 0)
                    note_entry = {
                        "type": "goal",
                        "frame": current_frame,
                        "data": {
                            "action": "complete",
                            "text": blackboard.goals[goal_index]["text"],
                        }
                    }
                    blackboard.journal.append(note_entry)
                    
                    logger.info(f"Marked goal as completed: {blackboard.goals[goal_index]['text']}")
                else:
                    logger.info(f"Invalid goal index: {goal_index+1}")
            except ValueError:
                # If not a number, assume it's a text search
                goal_text = parts[2].strip().lower()
                found = False
                
                for goal in blackboard.goals:
                    if goal_text in goal["text"].lower() and not goal["completed"]:
                        goal["completed"] = True
                        found = True
                        
                        # Add to journal
                        current_frame = blackboard.game_state.get("frame", 0)
                        note_entry = {
                            "type": "goal",
                            "frame": current_frame,
                            "data": {
                                "action": "complete",
                                "text": goal["text"],
                            }
                        }
                        blackboard.journal.append(note_entry)
                        
                        logger.info(f"Marked goal as completed: {goal['text']}")
                        break
                        
                if not found:
                    logger.info(f"No matching incomplete goal found for: {goal_text}")
            
            return {}
            
        # Handle remove action
        elif action == "remove" and len(parts) >= 3:
            try:
                # Check if it's a number (index)
                goal_index = int(parts[2]) - 1
                if 0 <= goal_index < len(blackboard.goals):
                    removed_goal = blackboard.goals.pop(goal_index)
                    
                    # Add to journal
                    current_frame = blackboard.game_state.get("frame", 0)
                    note_entry = {
                        "type": "goal",
                        "frame": current_frame,
                        "data": {
                            "action": "remove",
                            "text": removed_goal["text"],
                        }
                    }
                    blackboard.journal.append(note_entry)
                    
                    logger.info(f"Removed goal: {removed_goal['text']}")
                else:
                    logger.info(f"Invalid goal index: {goal_index+1}")
            except ValueError:
                # If not a number, assume it's a text search
                goal_text = parts[2].strip().lower()
                found = False
                
                for i, goal in enumerate(blackboard.goals):
                    if goal_text in goal["text"].lower():
                        removed_goal = blackboard.goals.pop(i)
                        found = True
                        
                        # Add to journal
                        current_frame = blackboard.game_state.get("frame", 0)
                        note_entry = {
                            "type": "goal",
                            "frame": current_frame,
                            "data": {
                                "action": "remove",
                                "text": removed_goal["text"],
                            }
                        }
                        blackboard.journal.append(note_entry)
                        
                        logger.info(f"Removed goal: {removed_goal['text']}")
                        break
                        
                if not found:
                    logger.info(f"No matching goal found for: {goal_text}")
            
            return {}
        
        else:
            logger.info("Usage: goal [add|list|complete|remove] [text|number]")
            return {}
    
    async def _show_dialog(self, count, blackboard):
        """Show recent dialog entries"""
        dialog_entries = []
        
        # Extract dialog entries from journal
        for entry in reversed(blackboard.journal):
            if entry["type"] == "dialog":
                dialog_entries.append(entry)
                if len(dialog_entries) >= count:
                    break
        
        if dialog_entries:
            logger.info(f"Last {len(dialog_entries)} dialog entries:")
            for entry in reversed(dialog_entries):
                frame = entry["frame"]
                dialog_text = " ".join(entry["data"])
                logger.info(f"[{frame}] {dialog_text}")
        else:
            logger.info("No dialog entries found")
    
    async def _search_journal(self, query_text, blackboard):
        """
        Search the journal for entries matching the query or return the last N entries.
        
        Args:
            query_text (str): Query text. If it starts with a number, it will return the last N entries.
                            If empty, it will return the last 10 entries.
            blackboard (Blackboard): The blackboard object containing the journal.
        """
        # Parse query to check if it starts with a number
        parts = query_text.strip().split(maxsplit=1)
        
        # Default number of entries to show
        count = 10
        search_text = query_text
        
        # Check if first part is a number (for last N entries)
        if parts and parts[0].isdigit():
            count = int(parts[0])
            # If there's text after the number, use it as search text
            search_text = parts[1] if len(parts) > 1 else None
        
        # If no search text, just return last N entries
        if not search_text or search_text.strip() == "":
            entries = blackboard.journal[-count:] if count <= len(blackboard.journal) else blackboard.journal
            logger.info(f"Last {len(entries)} journal entries:")
            
            for entry in entries:
                frame = entry["frame"]
                type_name = entry["type"]
                
                if type_name == "dialog":
                    data_str = " ".join(entry["data"])
                elif type_name == "menu":
                    menu_state = entry["data"]
                    cursor_text = menu_state.get("cursor_text", "Unknown")
                    data_str = f"Menu selection: {cursor_text}"
                elif type_name == "action":
                    data_str = f"Button: {entry['data']['button']} in {entry['data']['state']} state"
                elif type_name == "movement":
                    pos = entry["data"]["position"]
                    map_name = entry["data"]["map"]
                    data_str = f"Map: {map_name}, Position: {pos}"
                else:
                    data_str = str(entry["data"])
                
                # Truncate long data strings
                if len(data_str) > 100:
                    data_str = data_str[:97] + "..."
                
                logger.info(f"[{frame}] {type_name.upper()}: {data_str}")
            
            return
        
        # Otherwise, perform a search with the text
        results = []
        for entry in blackboard.journal:
            if search_text.lower() in str(entry["data"]).lower():
                results.append(entry)
        
        if results:
            # Limit results to the requested count
            results_to_show = results[-count:] if count < len(results) else results
            
            logger.info(f"Found {len(results)} matching entries, showing last {len(results_to_show)}:")
            for entry in results_to_show:
                frame = entry["frame"]
                type_name = entry["type"]
                
                if type_name == "dialog":
                    data_str = " ".join(entry["data"])
                elif type_name == "menu":
                    menu_state = entry["data"]
                    cursor_text = menu_state.get("cursor_text", "Unknown")
                    data_str = f"Menu selection: {cursor_text}"
                elif type_name == "action":
                    data_str = f"Button: {entry['data']['button']} in {entry['data']['state']} state"
                elif type_name == "movement":
                    pos = entry["data"]["position"]
                    map_name = entry["data"]["map"]
                    data_str = f"Map: {map_name}, Position: {pos}"
                else:
                    data_str = str(entry["data"])
                
                # Truncate long data strings
                if len(data_str) > 100:
                    data_str = data_str[:97] + "..."
                
                logger.info(f"[{frame}] {type_name.upper()}: {data_str}")
        else:
            logger.info(f"No entries found for query: {search_text}")
    
    async def _show_atlas(self, blackboard):
        """List all visited maps with detailed information including map connections with coordinates"""
        # Dictionary to store map data
        map_data = {}
        
        # Collect map statistics
        for node_id, data in blackboard.world_graph.nodes(data=True):
            if data.get('visited', False):
                map_name, x, y = node_id
                
                if map_name not in map_data:
                    map_data[map_name] = {
                        'positions': [],
                        'dialogs': 0,
                        'warps': set(),
                        'min_x': float('inf'),
                        'max_x': float('-inf'),
                        'min_y': float('inf'),
                        'max_y': float('-inf'),
                        'special_tiles': set(),
                        'connections': {}  # Store connected maps with coordinates
                    }
                
                # Add position
                map_data[map_name]['positions'].append((x, y))
                
                # Update min/max coordinates
                map_data[map_name]['min_x'] = min(map_data[map_name]['min_x'], x)
                map_data[map_name]['max_x'] = max(map_data[map_name]['max_x'], x)
                map_data[map_name]['min_y'] = min(map_data[map_name]['min_y'], y)
                map_data[map_name]['max_y'] = max(map_data[map_name]['max_y'], y)
                
                # Count dialogs
                if 'dialogs' in data and len(data['dialogs']) > 0:
                    map_data[map_name]['dialogs'] += len(data['dialogs'])
        
        # Find map connections by analyzing movement history
        # We're looking for consecutive entries with different maps
        for i in range(1, len(blackboard.movement_history)):
            prev_entry = blackboard.movement_history[i-1]
            curr_entry = blackboard.movement_history[i]
            
            prev_map = prev_entry["map"]
            curr_map = curr_entry["map"]
            
            # If maps are different, this indicates a connection
            if prev_map != curr_map:
                # Get exit and entry coordinates
                prev_x, prev_y, _ = prev_entry["position"]
                curr_x, curr_y, _ = curr_entry["position"]
                
                # Add connection from previous map to current map
                if prev_map in map_data:
                    if curr_map not in map_data[prev_map]['connections']:
                        map_data[prev_map]['connections'][curr_map] = []
                    
                    connection_info = {
                        'exit': (prev_x, prev_y),
                        'entry': (curr_x, curr_y)
                    }
                    
                    # Check if this specific connection already exists
                    if not any(c['exit'] == (prev_x, prev_y) and c['entry'] == (curr_x, curr_y) 
                            for c in map_data[prev_map]['connections'][curr_map]):
                        map_data[prev_map]['connections'][curr_map].append(connection_info)
                
                # Add reverse connection from current map to previous map
                if curr_map in map_data:
                    if prev_map not in map_data[curr_map]['connections']:
                        map_data[curr_map]['connections'][prev_map] = []
                    
                    connection_info = {
                        'exit': (curr_x, curr_y),
                        'entry': (prev_x, prev_y)
                    }
                    
                    # Check if this specific connection already exists
                    if not any(c['exit'] == (curr_x, curr_y) and c['entry'] == (prev_x, prev_y) 
                            for c in map_data[curr_map]['connections'][prev_map]):
                        map_data[curr_map]['connections'][prev_map].append(connection_info)
        
        # Sort maps by name
        sorted_maps = sorted(map_data.keys())
        
        if not sorted_maps:
            logger.info("No maps have been visited yet.")
            return
        
        # Display map information
        logger.info(f"Visited Maps ({len(sorted_maps)} total):")
        logger.info("=" * 80)
        
        for map_name in sorted_maps:
            data = map_data[map_name]
            
            # Build display string
            logger.info(f"MAP: {map_name}")
            logger.info(f"  Explored: {len(data['positions'])} tiles")
            
            # Show dialog count
            if data['dialogs'] > 0:
                logger.info(f"  Dialogs: {data['dialogs']} recorded")
            
            # Show connections to other maps with coordinates
            if data['connections']:
                logger.info(f"  Connections:")
                for connected_map, connections in sorted(data['connections'].items()):
                    for i, conn in enumerate(connections):
                        exit_coords = conn['exit']
                        entry_coords = conn['entry']
                        logger.info(f"    • To {connected_map}: Exit at {exit_coords} → Enter at {entry_coords}")
                
            logger.info("-" * 80)
            
    async def _show_position(self, blackboard):
        """Show current player position and map based on explored areas"""
        position = blackboard.game_state.get("player", {}).get("position", (0, 0, "Unknown"))
        map_name = blackboard.game_state.get("map", {}).get("name", "Unknown")
        
        x, y, facing = position
        logger.info(f"Current position: ({x}, {y}) facing {facing} in {map_name}")
        
        # Collect all explored tiles for the current map
        explored_tiles = {}
        
        for node_id, data in blackboard.world_graph.nodes(data=True):
            node_map, node_x, node_y = node_id
            if node_map == map_name:
                tile_code = data.get('tile_code', '?')
                explored_tiles[(node_x, node_y)] = tile_code
        
        if not explored_tiles:
            logger.info("No map data available for this area yet.")
            return
        
        # Extract entity positions
        entity_positions = {}
        if 'viewport' in blackboard.game_state and 'entities' in blackboard.game_state['viewport']:
            entities = blackboard.game_state['viewport']['entities']
            for entity in entities:
                entity_x = entity['position']['x']
                entity_y = entity['position']['y']
                entity_positions[(entity_x, entity_y)] = 'E'  # Mark entity positions
        
        # Extract warp positions
        warp_positions = {}
        if 'map' in blackboard.game_state and 'warps' in blackboard.game_state['map']:
            warps = blackboard.game_state['map']['warps']
            for coords_str, destination in warps.items():
                # Parse coordinates like "5,8" into a tuple (5,8)
                x_str, y_str = coords_str.split(',')
                warp_x, warp_y = int(x_str), int(y_str)
                warp_positions[(warp_x, warp_y)] = 'D'  # Mark warp positions
        
        # Calculate the bounds of what we've seen
        tile_coords = list(explored_tiles.keys())
        min_x = min(tx for tx, _ in tile_coords)
        max_x = max(tx for tx, _ in tile_coords)
        min_y = min(ty for _, ty in tile_coords)
        max_y = max(ty for _, ty in tile_coords)
        
        # Create a grid representing the area we've seen
        map_grid = []
        for y_pos in range(min_y, max_y + 1):
            row = []
            for x_pos in range(min_x, max_x + 1):
                coord = (x_pos, y_pos)
                
                # Player position gets highest priority
                if x_pos == x and y_pos == y:
                    row.append('@')
                # Entity positions get next priority
                elif coord in entity_positions:
                    row.append('E')
                # Warp positions get next priority
                elif coord in warp_positions:
                    row.append('D')
                # Otherwise show the normal terrain
                elif coord in explored_tiles:
                    row.append(explored_tiles[coord])
                else:
                    row.append('?')  # Use '?' for tiles we haven't seen
            map_grid.append(row)
            
        # Display the map
        logger.info(f"Map of {map_name} (explored areas):")
        for row in map_grid:
            logger.info("  " + " ".join(row))
        
        # Add information about the map coordinates
        logger.info(f"Map coordinates: Player @ ({x},{y}) in explored area from ({min_x},{min_y}) to ({max_x},{max_y})")
        logger.info(f"Legend: @ = Player position, E = Entity, W = Warp, ? = Unexplored, 0 = Walkable, W = Water, T = Tree, G = Grass, v/</>= Ledges")
        
        # Add nearby entities information
        if 'viewport' in blackboard.game_state and 'entities' in blackboard.game_state['viewport']:
            entities = blackboard.game_state['viewport']['entities']
            if entities:
                logger.info("Nearby entities:")
                for entity in entities:
                    entity_name = entity.get('name', 'Unknown')
                    entity_x = entity['position']['x']
                    entity_y = entity['position']['y']
                    logger.info(f"  • {entity_name} at ({entity_x}, {entity_y})")
        
        # Add nearby warps information
        warps = blackboard.game_state.get('map', {}).get('warps', {})
        if warps:
            logger.info("Nearby warps:")
            for coords, destination in warps.items():
                logger.info(f"  • {coords} → {destination}")

    async def _show_movements(self, count, blackboard):
        """Show recent movement entries"""
        movement_entries = []
        
        # Extract movement entries from journal
        for entry in reversed(blackboard.journal):
            if entry["type"] == "movement":
                movement_entries.append(entry)
                if len(movement_entries) >= count:
                    break
        
        if movement_entries:
            logger.info(f"Last {len(movement_entries)} movement entries:")
            for entry in reversed(movement_entries):
                frame = entry["frame"]
                position = entry["data"]["position"]
                map_name = entry["data"]["map"]
                logger.info(f"[{frame}] Map: {map_name}, Position: {position}")
        else:
            logger.info("No movement entries found")

    async def _show_surroundings(self, blackboard):
        """Show what's immediately surrounding the player (adjacent tiles)"""
        position = blackboard.game_state.get("player", {}).get("position", (0, 0, "Unknown"))
        map_name = blackboard.game_state.get("map", {}).get("name", "Unknown")
        
        x, y, facing = position
        logger.info(f"Current position: ({x}, {y}) facing {facing} in {map_name}")
        
        # Define directions and their relative coordinates
        directions = {
            "Up": (0, -1),
            "Down": (0, 1),
            "Left": (-1, 0),
            "Right": (1, 0)
        }
        
        # Get what tile we're standing on
        current_node_id = (map_name, x, y)
        current_tile = "?"
        if blackboard.world_graph.has_node(current_node_id):
            current_tile = blackboard.world_graph.nodes[current_node_id].get('tile_code', '?')
        
        # Check if we're standing on a warp
        current_warp = None
        if 'map' in blackboard.game_state and 'warps' in blackboard.game_state['map']:
            current_coords = f"{x},{y}"
            if current_coords in blackboard.game_state['map']['warps']:
                current_warp = blackboard.game_state['map']['warps'][current_coords]
        
        # Report what we're standing on
        warp_info = f" - Warp to: {current_warp}" if current_warp else ""
        logger.info(f"Standing on: {current_tile}{warp_info}")
        
        # Keep track of warp positions for checking adjacent # tiles
        warp_positions = []
        warp_destinations = {}
        if 'map' in blackboard.game_state and 'warps' in blackboard.game_state['map']:
            for coords_str, destination in blackboard.game_state['map']['warps'].items():
                coords_parts = coords_str.split(',')
                if len(coords_parts) == 2:
                    warp_x, warp_y = int(coords_parts[0]), int(coords_parts[1])
                    warp_positions.append((warp_x, warp_y))
                    warp_destinations[(warp_x, warp_y)] = destination
        
        # Check each adjacent tile
        logger.info("Surrounding tiles:")
        for direction, (dx, dy) in directions.items():
            adj_x, adj_y = x + dx, y + dy
            adj_node_id = (map_name, adj_x, adj_y)
            
            # Default tile information
            tile_info = "Unknown"
            
            # Check if this node exists in our graph
            if blackboard.world_graph.has_node(adj_node_id):
                tile_code = blackboard.world_graph.nodes[adj_node_id].get('tile_code', '?')
                
                # Check if this is a # tile adjacent to a warp - mark as ? instead
                if tile_code == '#':
                    # Check if any warp position is adjacent to this tile
                    for warp_x, warp_y in warp_positions:
                        # Calculate Manhattan distance to the warp
                        if abs(adj_x - warp_x) + abs(adj_y - warp_y) <= 1:
                            tile_code = '?'  # This # tile is adjacent to a warp, so mark as ?
                            break
                
                tile_info = tile_code
                
                # Highlight if this is the direction we're facing
                if direction == facing:
                    tile_info = f"{tile_info} ◄"
            
            # Check for entities at this position
            entities = []
            if 'viewport' in blackboard.game_state and 'entities' in blackboard.game_state['viewport']:
                for entity in blackboard.game_state['viewport']['entities']:
                    entity_x = entity['position']['x']
                    entity_y = entity['position']['y']
                    if entity_x == adj_x and entity_y == adj_y:
                        entities.append(entity.get('name', 'Unknown Entity'))
            
            # Check for warps at this position
            warps = []
            if 'map' in blackboard.game_state and 'warps' in blackboard.game_state['map']:
                for coords_str, destination in blackboard.game_state['map']['warps'].items():
                    # Parse coordinates like "5,8" into a tuple (5,8)
                    coords_parts = coords_str.split(',')
                    if len(coords_parts) == 2:
                        warp_x, warp_y = int(coords_parts[0]), int(coords_parts[1])
                        if warp_x == adj_x and warp_y == adj_y:
                            warps.append(destination)
            
            # Combine information
            direction_info = f"  {direction}: {tile_info}"
            if entities:
                direction_info += f" - Entity: {', '.join(entities)}"
            if warps:
                direction_info += f" - Warp to: {', '.join(warps)}"
            
            logger.info(direction_info)
        
        # Track special obstacle positions
        boulder_positions = []
        tree_positions = []
        water_positions = []
        
        # Create a walkability graph for standard pathfinding (no HMs required)
        walkability_graph = nx.Graph()
        
        # Create graphs for different HM abilities
        cut_graph = nx.Graph()  # Can use Cut
        surf_graph = nx.Graph()  # Can use Surf
        strength_graph = nx.Graph()  # Can use Strength
        
        # Add all walkable nodes from the world graph that are on the current map
        for node_id, data in blackboard.world_graph.nodes(data=True):
            node_map, node_x, node_y = node_id
            if node_map == map_name:
                # Get the tile code to determine walkability
                tile_code = data.get('tile_code', '#')
                pos = (node_x, node_y)
                
                # Track special obstacles for HM checks
                if tile_code == 'T':  # Tree
                    tree_positions.append(pos)
                elif tile_code == 'W':  # Water
                    water_positions.append(pos)
                
                # Basic walkable tiles (no HMs needed)
                is_walkable = (
                    tile_code == '1' or
                    tile_code == 'G' or
                    (tile_code == 'D') or  # Doors are walkable
                    pos in warp_positions  # Warp positions are walkable
                )
                
                if is_walkable:
                    walkability_graph.add_node(pos)
                    cut_graph.add_node(pos)
                    surf_graph.add_node(pos)
                    strength_graph.add_node(pos)
                
                # Add tree nodes to cut graph
                if tile_code == 'T':
                    cut_graph.add_node(pos)
                    
                # Add water nodes to surf graph
                if tile_code == 'W':
                    surf_graph.add_node(pos)
        
        # Check for entities and handle appropriately
        if 'viewport' in blackboard.game_state and 'entities' in blackboard.game_state['viewport']:
            for entity in blackboard.game_state['viewport']['entities']:
                entity_x = entity['position']['x']
                entity_y = entity['position']['y']
                entity_name = entity.get('name', 'Unknown Entity')
                pos = (entity_x, entity_y)
                
                # Check if the entity is a boulder
                is_boulder = 'Boulder' in entity_name
                
                # If it's a boulder, mark its position
                if is_boulder:
                    boulder_positions.append(pos)
                    strength_graph.add_node(pos)  # Boulders are walkable with Strength
                # Otherwise, remove the node if it's a stationary entity
                elif entity.get('movement', {}).get('type', '') == 'stationary':
                    if pos in walkability_graph:
                        walkability_graph.remove_node(pos)
                    if pos in cut_graph:
                        cut_graph.remove_node(pos)
                    if pos in surf_graph:
                        surf_graph.remove_node(pos)
                    if pos in strength_graph:
                        strength_graph.remove_node(pos)
        
        # Add edges between adjacent walkable tiles for all graphs
        for graph in [walkability_graph, cut_graph, surf_graph, strength_graph]:
            for node_x, node_y in list(graph.nodes()):
                # Check each adjacent position
                for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                    adj_x, adj_y = node_x + dx, node_y + dy
                    adj_pos = (adj_x, adj_y)
                    if adj_pos in graph:
                        graph.add_edge((node_x, node_y), adj_pos)
        
        # Calculate shortest paths to warps
        if warp_positions and (x, y) in walkability_graph:
            logger.info("\nAccessible warps:")
            
            for warp_x, warp_y in warp_positions:
                # Skip the warp we're already on
                if warp_x == x and warp_y == y:
                    continue
                
                warp_pos = (warp_x, warp_y)
                destination = warp_destinations.get(warp_pos, "Unknown")
                
                # Try to find a standard path first (no HMs required)
                standard_path = None
                try:
                    if warp_pos in walkability_graph:
                        standard_path = nx.shortest_path(walkability_graph, (x, y), warp_pos)
                except nx.NetworkXNoPath:
                    pass
                
                # If standard path found, use it
                if standard_path:
                    # Convert path to directions
                    directions_to_warp = []
                    for i in range(len(standard_path) - 1):
                        x1, y1 = standard_path[i]
                        x2, y2 = standard_path[i + 1]
                        
                        if x2 > x1:
                            directions_to_warp.append("right")
                        elif x2 < x1:
                            directions_to_warp.append("left")
                        elif y2 > y1:
                            directions_to_warp.append("down")
                        elif y2 < y1:
                            directions_to_warp.append("up")
                    
                    # Display the path - show first 5 steps with "..." if longer
                    path_str = ",".join(directions_to_warp[:5])
                    if len(directions_to_warp) > 5:
                        path_str += "..."
                    
                    logger.info(f"  • Warp to {destination} at ({warp_x}, {warp_y}): {len(standard_path)-1} steps")
                    logger.info(f"    Path: {path_str}")
                
                # If no standard path, try HM paths in order: Cut, Surf, Strength
                else:
                    # Try Cut path
                    cut_path = None
                    try:
                        if warp_pos in cut_graph:
                            cut_path = nx.shortest_path(cut_graph, (x, y), warp_pos)
                    except nx.NetworkXNoPath:
                        pass
                    
                    # Try Surf path
                    surf_path = None
                    try:
                        if warp_pos in surf_graph:
                            surf_path = nx.shortest_path(surf_graph, (x, y), warp_pos)
                    except nx.NetworkXNoPath:
                        pass
                    
                    # Try Strength path
                    strength_path = None
                    try:
                        if warp_pos in strength_graph:
                            strength_path = nx.shortest_path(strength_graph, (x, y), warp_pos)
                    except nx.NetworkXNoPath:
                        pass
                    
                    # Use the first available HM path
                    if cut_path:
                        logger.info(f"  • Warp to {destination} at ({warp_x}, {warp_y}): Requires Cut ability")
                        # Count how many trees are in the path
                        trees_in_path = sum(1 for pos in cut_path if pos in tree_positions)
                        logger.info(f"    Path requires cutting {trees_in_path} tree(s)")
                    elif surf_path:
                        logger.info(f"  • Warp to {destination} at ({warp_x}, {warp_y}): Requires Surf ability")
                        # Count water tiles
                        water_tiles = sum(1 for pos in surf_path if pos in water_positions)
                        logger.info(f"    Path requires surfing across {water_tiles} water tile(s)")
                    elif strength_path:
                        logger.info(f"  • Warp to {destination} at ({warp_x}, {warp_y}): Requires Strength ability")
                        # Count boulders
                        boulders = sum(1 for pos in strength_path if pos in boulder_positions)
                        logger.info(f"    Path requires moving {boulders} boulder(s)")
                    else:
                        logger.info(f"  • Warp to {destination} at ({warp_x}, {warp_y}): No path found")
        
        # Get all entities on the current map
        all_entities = []
        if 'viewport' in blackboard.game_state and 'entities' in blackboard.game_state['viewport']:
            for entity in blackboard.game_state['viewport']['entities']:
                entity_x = entity['position']['x']
                entity_y = entity['position']['y']
                name = entity.get('name', 'Unknown Entity')
                # Skip entities we're right next to (already shown above)
                if abs(entity_x - x) <= 1 and abs(entity_y - y) <= 1:
                    continue
                all_entities.append((entity_x, entity_y, name))
        
        # Calculate shortest paths to entities
        if all_entities and (x, y) in walkability_graph:
            logger.info("\nAccessible entities:")
            
            for entity_x, entity_y, name in all_entities:
                entity_pos = (entity_x, entity_y)
                
                # Check if we need an adjacent tile to interact with entity
                interaction_pos = entity_pos
                if entity_pos not in walkability_graph:
                    # Find an adjacent walkable tile to interact from
                    adjacent_tiles = []
                    for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                        adj_x, adj_y = entity_x + dx, entity_y + dy
                        adj_pos = (adj_x, adj_y)
                        if adj_pos in walkability_graph:
                            adjacent_tiles.append(adj_pos)
                    
                    # If no adjacent walkable tiles, try with HM abilities
                    if not adjacent_tiles:
                        logger.info(f"  • {name} at ({entity_x}, {entity_y}): No standard path found")
                        continue
                        
                    # Use the first adjacent tile
                    interaction_pos = adjacent_tiles[0]
                
                # Try to find a standard path first (no HMs required)
                standard_path = None
                try:
                    standard_path = nx.shortest_path(walkability_graph, (x, y), interaction_pos)
                except nx.NetworkXNoPath:
                    pass
                
                # If standard path found, use it
                if standard_path:
                    # Convert path to directions
                    directions_to_entity = []
                    for i in range(len(standard_path) - 1):
                        x1, y1 = standard_path[i]
                        x2, y2 = standard_path[i + 1]
                        
                        if x2 > x1:
                            directions_to_entity.append("right")
                        elif x2 < x1:
                            directions_to_entity.append("left")
                        elif y2 > y1:
                            directions_to_entity.append("down")
                        elif y2 < y1:
                            directions_to_entity.append("up")
                    
                    # If ending at an adjacent tile, add facing direction
                    if interaction_pos != entity_pos:
                        # Add direction to face the entity
                        if entity_x > interaction_pos[0]:
                            directions_to_entity.append("right (face)")
                        elif entity_x < interaction_pos[0]:
                            directions_to_entity.append("left (face)")
                        elif entity_y > interaction_pos[1]:
                            directions_to_entity.append("down (face)")
                        elif entity_y < interaction_pos[1]:
                            directions_to_entity.append("up (face)")
                    
                    # Display the path - show first 5 steps with "..." if longer
                    path_str = ",".join(directions_to_entity[:5])
                    if len(directions_to_entity) > 5:
                        path_str += "..."
                    
                    logger.info(f"  • {name} at ({entity_x}, {entity_y}): {len(standard_path)-1} steps")
                    logger.info(f"    Path: {path_str}")
                
                # If no standard path, try HM paths in order: Cut, Surf, Strength
                else:
                    # Try Cut path
                    cut_path = None
                    try:
                        # Find reachable adjacent tile in cut graph
                        for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                            adj_x, adj_y = entity_x + dx, entity_y + dy
                            adj_pos = (adj_x, adj_y)
                            if adj_pos in cut_graph:
                                cut_path = nx.shortest_path(cut_graph, (x, y), adj_pos)
                                interaction_pos = adj_pos
                                break
                    except nx.NetworkXNoPath:
                        pass
                    
                    # Try Surf path if Cut failed
                    surf_path = None
                    try:
                        if not cut_path:
                            # Find reachable adjacent tile in surf graph
                            for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                                adj_x, adj_y = entity_x + dx, entity_y + dy
                                adj_pos = (adj_x, adj_y)
                                if adj_pos in surf_graph:
                                    surf_path = nx.shortest_path(surf_graph, (x, y), adj_pos)
                                    interaction_pos = adj_pos
                                    break
                    except nx.NetworkXNoPath:
                        pass
                    
                    # Try Strength path if Surf failed
                    strength_path = None
                    try:
                        if not cut_path and not surf_path:
                            # Find reachable adjacent tile in strength graph
                            for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                                adj_x, adj_y = entity_x + dx, entity_y + dy
                                adj_pos = (adj_x, adj_y)
                                if adj_pos in strength_graph:
                                    strength_path = nx.shortest_path(strength_graph, (x, y), adj_pos)
                                    interaction_pos = adj_pos
                                    break
                    except nx.NetworkXNoPath:
                        pass
                    
                    # Use the first available HM path
                    if cut_path:
                        logger.info(f"  • {name} at ({entity_x}, {entity_y}): Requires Cut ability")
                        # Count how many trees are in the path
                        trees_in_path = sum(1 for pos in cut_path if pos in tree_positions)
                        logger.info(f"    Path requires cutting {trees_in_path} tree(s)")
                    elif surf_path:
                        logger.info(f"  • {name} at ({entity_x}, {entity_y}): Requires Surf ability")
                        # Count water tiles
                        water_tiles = sum(1 for pos in surf_path if pos in water_positions)
                        logger.info(f"    Path requires surfing across {water_tiles} water tile(s)")
                    elif strength_path:
                        logger.info(f"  • {name} at ({entity_x}, {entity_y}): Requires Strength ability")
                        # Count boulders
                        boulders = sum(1 for pos in strength_path if pos in boulder_positions)
                        logger.info(f"    Path requires moving {boulders} boulder(s)")
                    else:
                        logger.info(f"  • {name} at ({entity_x}, {entity_y}): No path found")

    async def _explore_map(self, blackboard, options=None):
        """
        Systematically explore the current map using a frontier-based algorithm.
        
        Args:
            options (dict): Configuration options for exploration
                - 'see_only' (bool): If True, only attempt to see all tiles; if False, attempt to walk on all tiles
                - 'interact_entities' (bool): If True, interact with all entities encountered
                - 'interact_tiles' (bool): If True, interact with all tiles (including walls)
                - 'max_steps' (int): Maximum number of steps to take (None for unlimited)
                
        Returns:
            list: Sequence of buttons to press for exploration
        """
        # Set default options
        if options is None:
            options = {
                'see_only': False,
                'interact_entities': False,
                'interact_tiles': False,
                'max_steps': None
            }
        
        position = blackboard.game_state.get("player", {}).get("position", (0, 0, "Unknown"))
        map_name = blackboard.game_state.get("map", {}).get("name", "Unknown")
        
        x, y, facing = position
        logger.info(f"Planning exploration of {map_name} from position ({x}, {y})")
        logger.info(f"Exploration settings: {options}")
        
        # Get current map dimensions and exploration stats
        explored_tiles = set()
        seen_tiles = set()
        walkable_tiles = set()
        interaction_tiles = set()
        
        # Define visibility range (how far the player can see)
        visibility_range = 4
        
        # Process map data from world graph
        for node_id, data in blackboard.world_graph.nodes(data=True):
            node_map, node_x, node_y = node_id
            if node_map == map_name:
                seen_tiles.add((node_x, node_y))
                
                if data.get('visited', False):
                    explored_tiles.add((node_x, node_y))
                
                # Get the tile code to determine walkability
                tile_code = data.get('tile_code', '#')
                if tile_code in ['1', 'G']:
                    walkable_tiles.add((node_x, node_y))
                
                # Identify tiles to interact with
                if options['interact_tiles'] and tile_code in ['0', '#', 'W', 'T']:
                    interaction_tiles.add((node_x, node_y))
        
        # Create walkability graph from known information
        walkability_graph = nx.Graph()
        for tile_x, tile_y in walkable_tiles:
            walkability_graph.add_node((tile_x, tile_y))
        
        # Process entities for both walkability and interaction
        entity_positions = []
        stationary_entity_positions = set()
        
        if 'viewport' in blackboard.game_state and 'entities' in blackboard.game_state['viewport']:
            for entity in blackboard.game_state['viewport']['entities']:
                entity_x = entity['position']['x']
                entity_y = entity['position']['y']
                entity_name = entity.get('name', 'Unknown Entity')
                pos = (entity_x, entity_y)
                
                # Check if entity is stationary
                is_stationary = entity.get('movement', {}).get('type', '') == 'stationary'
                
                # Check if entity is a boulder (special case)
                is_boulder = 'Boulder' in entity_name
                
                # Mark as stationary for walkability exclusion
                if is_stationary and not is_boulder:
                    stationary_entity_positions.add(pos)
                    
                    # If it's a stationary entity (not a boulder) and we're interacting with entities
                    if options['interact_entities']:
                        # Find adjacent walkable tiles for interaction
                        for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                            adj_x, adj_y = entity_x + dx, entity_y + dy
                            adj_pos = (adj_x, adj_y)
                            if adj_pos in walkable_tiles:
                                entity_positions.append({
                                    'position': pos,
                                    'interaction_tile': adj_pos,
                                    'name': entity_name
                                })
                                break
        
        # Remove stationary entities from walkability graph
        for pos in stationary_entity_positions:
            if pos in walkability_graph:
                walkability_graph.remove_node(pos)
        
        # Add edges between adjacent walkable tiles
        for node_x, node_y in list(walkability_graph.nodes()):
            for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                adj_x, adj_y = node_x + dx, node_y + dy
                adj_pos = (adj_x, adj_y)
                if adj_pos in walkability_graph:
                    walkability_graph.add_edge((node_x, node_y), adj_pos)
        
        # Calculate frontier tiles (unexplored tiles adjacent to explored ones)
        frontier_tiles = {}  # Dictionary mapping positions to value
        
        # For each walkable tile, calculate information gain
        for wx, wy in walkable_tiles:
            # Skip tiles that aren't in the walkability graph (e.g., occupied by entities)
            if (wx, wy) not in walkability_graph:
                continue
                
            # Skip already visited tiles if we're not in see-only mode
            if not options['see_only'] and (wx, wy) in explored_tiles:
                continue
            
            # Calculate potential information gain (unseen tiles that would be revealed)
            unseen_tiles = set()
            for dx in range(-visibility_range, visibility_range + 1):
                for dy in range(-visibility_range, visibility_range + 1):
                    # Skip tiles outside visibility range (Manhattan distance)
                    if abs(dx) + abs(dy) > visibility_range:
                        continue
                    
                    # Calculate the potentially visible tile
                    new_x, new_y = wx + dx, wy + dy
                                        
                    # If this tile hasn't been seen yet, it would be newly revealed
                    if (new_x, new_y) not in seen_tiles:
                        unseen_tiles.add((new_x, new_y))
            
            # If this position reveals unseen tiles, add it to frontier with its value
            if unseen_tiles:
                # Value is the number of unseen tiles that would be revealed
                frontier_tiles[(wx, wy)] = len(unseen_tiles)
        
        logger.info(f"Found {len(frontier_tiles)} frontier tiles for exploration")
        
        # Generate target queue
        target_queue = []
        
        # 1. First priority: Unvisited walkable tiles if not in see-only mode
        if not options['see_only']:
            unvisited_walkable = set()
            for pos in walkable_tiles:
                if pos not in explored_tiles and pos in walkability_graph:
                    unvisited_walkable.add(pos)
            
            logger.info(f"Found {len(unvisited_walkable)} unvisited walkable tiles")
            
            # Add unvisited tiles to target queue
            for tile_x, tile_y in unvisited_walkable:
                # Get exploration value from frontier_tiles if available
                exploration_value = frontier_tiles.get((tile_x, tile_y), 0)
                
                target_queue.append({
                    'position': (tile_x, tile_y),
                    'type': 'walkable',
                    'action': 'walk',
                    'value': exploration_value
                })
        
        # 2. Second priority: High-value frontier tiles for seeing all tiles
        for (tile_x, tile_y), value in frontier_tiles.items():
            # Skip tiles already in the queue from previous step
            if any(t['position'] == (tile_x, tile_y) for t in target_queue):
                continue
                
            target_queue.append({
                'position': (tile_x, tile_y),
                'type': 'frontier',
                'action': 'walk',
                'value': value
            })
        
        # 3. Third priority: Entities to interact with
        if options['interact_entities']:
            logger.info(f"Found {len(entity_positions)} entities to interact with")
            
            for entity in entity_positions:
                target_queue.append({
                    'position': entity['interaction_tile'],
                    'type': 'entity',
                    'facing_position': entity['position'],
                    'name': entity['name'],
                    'action': 'interact',
                    'value': 0  # Lower priority than exploration
                })
        
        # 4. Fourth priority: Tiles to interact with
        if options['interact_tiles']:
            interaction_targets = []
            
            for tile_x, tile_y in interaction_tiles:
                # Find adjacent walkable tiles to interact from
                for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                    adj_x, adj_y = tile_x + dx, tile_y + dy
                    adj_pos = (adj_x, adj_y)
                    if adj_pos in walkability_graph:
                        interaction_targets.append({
                            'position': adj_pos,
                            'facing_position': (tile_x, tile_y),
                            'action': 'interact'
                        })
                        break
            
            logger.info(f"Found {len(interaction_targets)} tiles to interact with")
            
            for target in interaction_targets:
                target_queue.append({
                    'position': target['position'],
                    'type': 'tile_interaction',
                    'facing_position': target['facing_position'],
                    'action': 'interact',
                    'value': 0  # Lower priority than exploration
                })
        
        # If no targets found, exploration is complete
        if not target_queue:
            logger.info("Exploration complete! No more exploration targets.")
            return []
        
        # Plan exploration path using frontier-based algorithm
        full_button_sequence = []
        current_pos = (x, y)
        remaining_targets = target_queue.copy()
        visited_positions = set(explored_tiles)
        
        # Get maximum steps if specified
        max_steps = options.get('max_steps', None)
        
        # While we still have targets and haven't reached the step limit
        while remaining_targets and (max_steps is None or len(full_button_sequence) < max_steps):
            # Find the best next target
            best_target = None
            best_path = None
            best_score = -float('inf')
            
            # Calculate scores for each remaining target
            for target in remaining_targets:
                try:
                    # Calculate path to this target
                    path = nx.shortest_path(walkability_graph, current_pos, target['position'])
                    path_length = len(path) - 1
                    
                    # Skip if path would exceed max steps
                    if max_steps is not None and len(full_button_sequence) + path_length > max_steps:
                        continue
                    
                    # Calculate score based on value and distance
                    # For frontier/exploration targets, prioritize value per step
                    if target['type'] in ['walkable', 'frontier']:
                        value = target['value']
                        # Avoid division by zero
                        if path_length == 0:
                            path_length = 1
                        score = value / path_length
                    # For interaction targets, just use inverse of distance
                    else:
                        score = 1.0 / (path_length + 1)
                    
                    # If this is better than our current best, update
                    if score > best_score:
                        best_target = target
                        best_path = path
                        best_score = score
                except nx.NetworkXNoPath:
                    # Skip targets we can't reach
                    continue
            
            # If we found a good target, add its path to our sequence
            if best_target and best_path:
                # Convert path to buttons
                path_buttons = []
                for i in range(len(best_path) - 1):
                    x1, y1 = best_path[i]
                    x2, y2 = best_path[i + 1]
                    
                    if x2 > x1:
                        path_buttons.append("right")
                    elif x2 < x1:
                        path_buttons.append("left")
                    elif y2 > y1:
                        path_buttons.append("down")
                    elif y2 < y1:
                        path_buttons.append("up")
                
                # Add interaction if needed
                if best_target['action'] == 'interact':
                    if 'facing_position' in best_target:
                        # Add facing direction
                        tx, ty = best_target['position']
                        fx, fy = best_target['facing_position']
                        
                        if fx > tx:
                            path_buttons.append("right")
                        elif fx < tx:
                            path_buttons.append("left")
                        elif fy > ty:
                            path_buttons.append("down")
                        elif fy < ty:
                            path_buttons.append("up")
                    
                    # Add 'a' button for interaction
                    path_buttons.append("a")
                
                # Add buttons to the full sequence
                full_button_sequence.extend(path_buttons)
                
                # Update current position and mark target as visited
                current_pos = best_target['position']
                remaining_targets.remove(best_target)
                visited_positions.add(current_pos)
                
                # If this was a frontier tile, remove other targets that would be too similar
                if best_target['type'] in ['walkable', 'frontier']:
                    # Remove targets within a close distance that would be redundant
                    redundant_distance = 2
                    redundant_targets = []
                    
                    for target in remaining_targets:
                        if target['type'] in ['walkable', 'frontier']:
                            tx, ty = target['position']
                            if abs(tx - current_pos[0]) + abs(ty - current_pos[1]) <= redundant_distance:
                                redundant_targets.append(target)
                    
                    for target in redundant_targets:
                        if target in remaining_targets:
                            remaining_targets.remove(target)
            else:
                # No reachable targets left
                break
        
        # Log exploration plan
        if full_button_sequence:
            logger.info(f"Planned exploration with {len(full_button_sequence)} steps")
            
            # If sequence is long, show abbreviated version
            if len(full_button_sequence) > 20:
                abbreviated = ", ".join(full_button_sequence[:10]) + "... " + ", ".join(full_button_sequence[-10:])
                logger.info(f"Button sequence: {abbreviated} ({len(full_button_sequence)} total steps)")
            else:
                logger.info(f"Button sequence: {', '.join(full_button_sequence)}")
                
            return full_button_sequence
        else:
            logger.info("No exploration targets found.")
            return []
                    
    async def _show_map(self, map_name, blackboard):
        """Show map info for the specified map or current map if unspecified"""
        if not map_name:
            # Use current map
            map_name = blackboard.game_state.get("map", {}).get("name", "Unknown")
            
        position = blackboard.game_state.get("player", {}).get("position", (0, 0, "Unknown"))
        x, y, facing = position
        
        # Get current player position and map for context
        current_map = blackboard.game_state.get("map", {}).get("name", "Unknown")
        logger.info(f"Current position: ({x}, {y}) facing {facing} in {current_map}")
        
        # Only show detailed map info if we're viewing the current map or map is specified
        is_current_map = map_name == current_map
        
        # Collect all explored tiles for the requested map
        explored_tiles = {}
        
        for node_id, data in blackboard.world_graph.nodes(data=True):
            node_map, node_x, node_y = node_id
            if node_map == map_name:
                if is_current_map and node_x == x and node_y == y:
                    tile_code = '@'  # Mark player position only if showing current map
                else:
                    tile_code = data.get('tile_code', '?')
                explored_tiles[(node_x, node_y)] = tile_code
        
        if not explored_tiles:
            logger.info(f"No map data available for {map_name}.")
            return
        
        # Calculate the bounds of what we've seen
        tile_coords = list(explored_tiles.keys())
        min_x = min(tx for tx, _ in tile_coords)
        max_x = max(tx for tx, _ in tile_coords)
        min_y = min(ty for _, ty in tile_coords)
        max_y = max(ty for _, ty in tile_coords)
        
        # Create a grid representing the area we've seen
        map_grid = []
        for y_pos in range(min_y, max_y + 1):
            row = []
            for x_pos in range(min_x, max_x + 1):
                coord = (x_pos, y_pos)
                if coord in explored_tiles:
                    row.append(explored_tiles[coord])
                else:
                    row.append('?')  # Use '?' for tiles we haven't seen
            map_grid.append(row)
            
        # Display the map
        logger.info(f"Map of {map_name} (explored areas):")
        for row in map_grid:
            logger.info("  " + " ".join(row))
        
        # Add information about the map coordinates
        logger.info(f"Map coordinates: From ({min_x},{min_y}) to ({max_x},{max_y})")
        logger.info(f"Legend: @ = Player position, ? = Unexplored, 0 = Walkable, W = Water, T = Tree, G = Grass, v/</>= Ledges")
        
        # If we're viewing the current map, show additional information
        if is_current_map:
            # Add nearby entities information
            if 'viewport' in blackboard.game_state and 'entities' in blackboard.game_state['viewport']:
                entities = blackboard.game_state['viewport']['entities']
                if entities:
                    logger.info("Nearby entities:")
                    for entity in entities:
                        entity_name = entity.get('name', 'Unknown')
                        entity_x = entity['position']['x']
                        entity_y = entity['position']['y']
                        logger.info(f"  • {entity_name} at ({entity_x}, {entity_y})")
            
            # Add nearby warps information
            warps = blackboard.game_state.get('map', {}).get('warps', {})
            if warps:
                logger.info("Nearby warps:")
                for coords, destination in warps.items():
                    logger.info(f"  • {coords} → {destination}")

    async def _show_menu_text(self, blackboard):
        game_state = blackboard.game_state
        menu_state = game_state['text'].get('menu_state', {})
        if menu_state.get('cursor_pos') is not None:
            logger.info(f"\n=== VISIBLE TEXT ===")
            for line in game_state['text'].get("lines"):
                logger.info(f"  {line}")
            logger.info(f"\n=== MENU INFO ===")
            cursor_pos = menu_state.get('cursor_pos', ('?', '?'))
            logger.info(f"  Cursor Position: {cursor_pos}")
            if menu_state.get('cursor_text'):
                logger.info(f"  Current Menu Option: '{menu_state['cursor_text']}'")

    async def _show_state(self, blackboard):
        """Show detailed information about the current game state in the same format as wrapper.__str__"""
        game_state = blackboard.game_state
        
        # Format the state information similar to wrapper.__str__
        logger.info(f"Frame: {game_state['frame']}")
        logger.info(f"State: {game_state['state']} | In Battle: {game_state['is_in_battle']} | Last Button: {game_state['last_button']}")
        
        # Map information
        logger.info(f"\n=== MAP INFO ===")
        logger.info(f"Current Map: {game_state['map']['name']}")
        logger.info(f"Tileset: {game_state['map']['tileset']['name']}")
        logger.info(f"Dimensions: {game_state['map']['dimensions']}")
        
        # Player information
        logger.info(f"\n=== PLAYER INFO ===")
        player_x, player_y, facing = game_state['player']['position']
        logger.info(f"Position: ({player_x}, {player_y}) Facing: {facing}")
        logger.info(f"Money: {game_state['player']['money']} ₽")
        logger.info(f"Badges: {', '.join(game_state['player']['badges']) if game_state['player']['badges'] else 'None'}")
        logger.info(f"Pokédex: {game_state['player']['pokedex']['owned']} owned, {game_state['player']['pokedex']['seen']} seen")
        
        # Bag items
        logger.info(f"\n=== BAG ITEMS ===")
        if game_state['player']['bag']:
            for item_name, quantity in game_state['player']['bag']:
                logger.info(f"  • {item_name} x{quantity}")
        else:
            logger.info("  • Empty bag")
        
        # Team information
        logger.info(f"\n=== TEAM POKÉMON ===")
        if game_state['player']['team'] and game_state['player']['team'].get('pokemon'):
            for pokemon in game_state['player']['team']['pokemon']:
                logger.info(f"  • {pokemon.get('nickname', 'Unknown')} ({pokemon.get('species_id', 'Unknown')}) Lv.{pokemon.get('level', '?')}")
                logger.info(f"    HP: {pokemon.get('current_hp', '?')}/{pokemon.get('max_hp', '?')} | Status: {pokemon.get('status', 'Unknown')}")
                logger.info(f"    Types: {', '.join(filter(None, pokemon.get('types', ['Unknown'])))}")
                logger.info(f"    Moves: {', '.join(pokemon.get('moves', ['None']))}")
                
                # logger.info stats in a compact format
                if 'stats' in pokemon:
                    stats = pokemon['stats']
                    stats_str = " | ".join([f"{k}: {v}" for k, v in stats.items()])
                    logger.info(f"    Stats: {stats_str}")
        else:
            logger.info("  • No Pokémon in team")
        
        # Map entities (NPCs, etc.)
        logger.info(f"\n=== MAP ENTITIES ===")
        if game_state['viewport']['entities']:
            for entity in game_state['viewport']['entities']:
                logger.info(f"  • {entity.get('name', 'Unknown')} @ ({entity['position']['x']}, {entity['position']['y']}) - {entity.get('state', 'Unknown')}")
        else:
            logger.info("  • No visible entities")
        
        # Map warps
        if game_state['map']['warps']:
            logger.info(f"\n=== MAP WARPS ===")
            for coords, destination in game_state['map']['warps'].items():
                logger.info(f"  • Warp @ {coords} → {destination}")
        
        # Battle information
        if game_state['is_in_battle']:
            logger.info(f"\n{'=' * 20} BATTLE {'=' * 20}")
            battle = game_state['battle']
            
            # Battle type
            battle_type = "Trainer Battle" if battle.get("is_trainer_battle", False) else "Wild Encounter"
            logger.info(f"Type: {battle_type}")
            
            # Player's active Pokémon
            if game_state['player']['team'] and len(game_state['player']['team']['pokemon']) > 0:
                active_pokemon = game_state['player']['team']['pokemon'][0]
                logger.info(f"\nPLAYER POKÉMON:")
                logger.info(f"  • {active_pokemon.get('nickname', 'Unknown')} ({active_pokemon.get('species_id', 'Unknown')}) Lv.{active_pokemon.get('level', '?')}")
                logger.info(f"    HP: {active_pokemon.get('current_hp', '?')}/{active_pokemon.get('max_hp', '?')} | Status: {active_pokemon.get('status', 'Unknown')}")
            
            # Enemy Pokémon
            if 'enemy_pokemon' in battle:
                enemy = battle['enemy_pokemon']
                logger.info(f"\nENEMY POKÉMON:")
                logger.info(f"  • {enemy.get('nickname', enemy.get('species_name', 'Unknown'))} ({enemy.get('species_name', 'Unknown')}) Lv.{enemy.get('level', '?')}")
                logger.info(f"    HP: {enemy.get('hp_percent', '?')}% | Status: {enemy.get('status', 'Unknown')}")
                logger.info(f"    Types: {', '.join(filter(None, enemy.get('types', ['Unknown'])))}")
            
            # Turn counter
            if 'turn_counter' in battle:
                logger.info(f"\nTurn: {battle['turn_counter'] + 1}")
        
        # Menu information
        menu_state = game_state['text'].get('menu_state', {})
        if menu_state.get('cursor_pos') is not None:
            logger.info(f"\n=== VISIBLE TEXT ===")
            for line in game_state['text'].get("lines"):
                logger.info(f"  {line}")
            logger.info(f"\n=== MENU INFO ===")
            cursor_pos = menu_state.get('cursor_pos', ('?', '?'))
            logger.info(f"  Cursor Position: {cursor_pos}")
            if menu_state.get('cursor_text'):
                logger.info(f"  Current Menu Option: '{menu_state['cursor_text']}'")
        
        # Text and dialog information
        if game_state['text']['dialog'] and game_state['state'] != 'menu':
            logger.info(f"\n=== DIALOG ===")
            for line in game_state['text']['dialog']:
                logger.info(f"  {line}")
                    
        # Tilemap visualization
        if game_state['state'] == 'default' and not game_state['is_in_battle'] and game_state['viewport'].get('tiles'):
            logger.info(f"\n=== MAP VIEW ===")
            map_with_player = game_state['viewport']['tiles']
            map_with_player[4][4] = '@'
            for row in map_with_player:
                logger.info('  ' + ' '.join(row))
                
        # Also show last button press for context
        if self.last_button:
            logger.info(f"Last button press: {self.last_button}")
            logger.info(f"Frames since last button: {game_state.get('frame', 0) - blackboard.last_button_frame}")
    
    async def show_journal_since_last_prompt(self, blackboard):
        """Show journal entries that occurred since the last time the user was prompted for input"""
        
        # Find entries that occurred after the last prompt frame
        new_entries = [entry for entry in blackboard.journal if entry["frame"] > self.last_prompt_frame]
        
        if not new_entries:
            return
        
        logger.info(f"=== UPDATES SINCE LAST PROMPT ===")
        
        for entry in new_entries:
            type_name = entry["type"]
            
            # Format entry based on type
            if type_name == "dialog":
                logger.info(f"DIALOG: {' '.join(entry['data'])}")
            elif type_name == "movement":
                if entry['data']['position'][2] != 'Null':
                    logger.info(f"MOVED: {entry['data']['map']} at {entry['data']['position']}")

    async def _process_command(self, command, blackboard):
        """Process user command and take appropriate action"""
        command = command.strip()
        logger.info(f"Command: {command}")
        
        # Check if command is a button sequence
        if "," in command:
            # Split the sequence and find the first 'a'
            buttons = [btn.strip() for btn in command.split(",")]
            
            valid_sequence = all(btn in self.valid_buttons for btn in buttons)

            if valid_sequence and buttons:
                self.button_sequence = buttons[1:]
                logger.info(f"Parsed button sequence: {buttons[0]} + {len(self.button_sequence)} more")
                return {"button": buttons[0]}
            else:
                logger.info(f"Invalid button sequence: {command}")
                return {}
                
        # Empty command - default to 'a'
        if not command:
            return {"button": "a"}
        
        # Direct button press
        if command in self.valid_buttons:
            return {"button": command}
            
        # Help command
        if command == "help":
            await self._show_help_text(blackboard)
            return {}

        # State command - show current state
        if command == "state":
            await self._show_state(blackboard)
            return {}
            
        # Dialog command
        if command.startswith("dialog"):
            parts = command.split()
            count = int(parts[1]) if len(parts) > 1 else 25
            await self._show_dialog(count, blackboard)
            return {}
            
        # Movements command
        if command.startswith("movements"):
            parts = command.split()
            count = int(parts[1]) if len(parts) > 1 else 25
            await self._show_movements(count, blackboard)
            return {}
            
        # Query command - now supports just "query" or "query N" to show last N entries
        if command.startswith("query"):
            query_text = command[5:].strip()  # Remove "query" prefix
            await self._search_journal(query_text, blackboard)
            return {}
            
        # Map command (formerly 'pos')
        if command.startswith("map"):
            parts = command.split()
            map_name = parts[1] if len(parts) > 1 else None
            await self._show_map(map_name, blackboard)
            if command == 'map':
                await self._show_surroundings(blackboard)
            return {}
        
        if command.startswith("explore"):
            parts = command.split()
            
            # Parse options
            options = {
                'see_only': 'see-only' in parts or 'see' in parts,
                'interact_entities': 'interact-entities' in parts or 'entities' in parts,
                'interact_tiles': 'interact-tiles' in parts or 'tiles' in parts
            }
            
            # Check for step limit
            max_steps = None
            for part in parts:
                if part.isdigit():
                    max_steps = int(part)
                    options['max_steps'] = max_steps
                    break
            
            # Print exploration mode
            mode_description = []
            if options['see_only']:
                mode_description.append("seeing all tiles")
            else:
                mode_description.append("traversing all tiles")
            
            if options['interact_entities']:
                mode_description.append("interacting with entities")
            
            if options['interact_tiles']:
                mode_description.append("interacting with tiles")
            
            if max_steps is not None:
                mode_description.append(f"maximum {max_steps} steps")
            
            logger.info(f"Planning exploration: {', '.join(mode_description)}")
            
            # Get exploration button sequence
            button_sequence = await self._explore_map(blackboard, options)
            
            if button_sequence:
                # Set the button sequence and return the first button
                self.button_sequence = button_sequence[1:] if len(button_sequence) > 1 else []
                first_button = button_sequence[0] if button_sequence else None
                
                if first_button:
                    logger.info(f"Starting exploration: {first_button} ({len(self.button_sequence)} moves queued)")
                    return {"button": first_button}
            
            logger.info("No exploration path found.")
            return {}
            
        # Atlas command - list all visited maps
        if command == "atlas":
            await self._show_atlas(blackboard)
            return {}
            
        # Support old 'pos' command for backward compatibility
        if command == "pos":
            await self._show_position(blackboard)
            return {}
        
        # Screen command
        if command.startswith("screen"):
            await self._process_screen(command, blackboard)
            return {}
        
        # Note command
        if command.startswith("note "):
            await self._process_note(command, blackboard)
            return {}
        
        # Goal command
        if command.startswith("goal "):
            await self._process_goal(command, blackboard)
            return {}
            
        # Unknown command - assume it's a button if it's a single word
        if " " not in command and len(command) <= 6:
            logger.info(f"Trying to press button: {command}")
            return {"button": command}
            
        logger.info(f"Unknown command: {command}. Type 'help' for available commands.")
        return {}