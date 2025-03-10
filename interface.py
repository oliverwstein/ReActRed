#!/usr/bin/env python3
"""
Interactive mode handler for Pokémon AI Client

This module provides the InteractiveMode class to handle user input
for manual control and journal/graph queries in the phase-based architecture.
"""

import asyncio
import aioconsole
import logging
import networkx as nx

logger = logging.getLogger("PokemonAI")

class InteractiveMode:
    """
    Handles interactive user input during different game states,
    allowing for journal queries, path finding, and manual button control.
    """
    
    def __init__(self):
        self.valid_buttons = ["up", "down", "left", "right", "a", "b", "start", "select"]
        self.help_text = """
Available commands:
  up, down, left, right, a, b, start, select - Press the specified button
  dialog [n]         - Show last n dialog entries (default: 5)
  query [text]       - Search journal for entries containing text
  path [map] [x] [y] - Find path to destination
  loc [map]          - List visited locations (optionally filtered by map)
  pos                - Show current position and map info
  state              - Show detailed current game state (useful after actions)
  help               - Show this help message
"""
        self.last_button = None
    
    async def get_menu_action(self, blackboard):
        """Handle user input during menu state"""
        menu_state = blackboard.game_state.get("text", {}).get("menu_state", {})
        cursor_text = menu_state.get("cursor_text", "")
        current_item = menu_state.get("current_item", -1)
        max_item = menu_state.get("max_item", -1)
        
        prompt_msg = f"INTERACTIVE: Menu"
        if cursor_text:
            prompt_msg += f" selecting '{cursor_text}' (item {current_item+1}/{max_item+1})"
            
        # Add last button info if available
        if self.last_button:
            prompt_msg += f" [Last: {self.last_button}]"
            
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
    
    async def get_default_action(self, blackboard):
        """Handle user input during default (overworld) state"""
        position = blackboard.game_state.get("player", {}).get("position", (0, 0, "Unknown"))
        map_name = blackboard.game_state.get("map", {}).get("name", "Unknown")
        
        prompt_msg = f"INTERACTIVE: {map_name} at {position}"
        if self.last_button:
            prompt_msg += f" [Last: {self.last_button}]"
            
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
        """Get user input from console"""
        prompt = "> "
        try:
            return await aioconsole.ainput(prompt)
        except asyncio.CancelledError:
            return ""
    
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
    
    async def _search_journal(self, query, blackboard):
        """Search the journal for entries matching the query"""
        results = []
        for entry in blackboard.journal:
            if query.lower() in str(entry["data"]).lower():
                results.append(entry)
        
        if results:
            logger.info(f"Found {len(results)} matching entries:")
            for i, entry in enumerate(results[-10:]):  # Show last 10 matches
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
            logger.info(f"No entries found for query: {query}")
    
    async def _find_path(self, map_name, dest_x, dest_y, blackboard):
        """Find a path to the specified location and return first step button if available"""
        # Get current position
        position = blackboard.game_state.get("player", {}).get("position", (0, 0, "Unknown"))
        current_map = blackboard.game_state.get("map", {}).get("name", "Unknown")
        current_x, current_y, _ = position
        
        # Create source and destination nodes
        source_node = (current_map, current_x, current_y)
        dest_node = (map_name, dest_x, dest_y)
        
        # Check if nodes exist
        if not blackboard.world_graph.has_node(source_node):
            logger.info(f"Current position not found in world graph: {source_node}")
            return None
        
        if not blackboard.world_graph.has_node(dest_node):
            logger.info(f"Destination not found in world graph: {dest_node}")
            return None
        
        # Try to find a path
        try:
            path = nx.shortest_path(blackboard.world_graph, source_node, dest_node)
            
            logger.info(f"Found path from {source_node} to {dest_node} with {len(path)} steps:")
            for i, (map_name, x, y) in enumerate(path):
                logger.info(f"  {i+1}. {map_name} ({x}, {y})")
                
            # Show first few steps as directions
            if len(path) > 1:
                logger.info("Directions:")
                next_button = None
                
                for i in range(1, min(4, len(path))):
                    prev_map, prev_x, prev_y = path[i-1]
                    curr_map, curr_x, curr_y = path[i]
                    
                    if prev_map != curr_map:
                        logger.info(f"  Take warp from {prev_map} ({prev_x}, {prev_y}) to {curr_map}")
                        next_button = "a" if i == 1 else None
                    else:
                        dx = curr_x - prev_x
                        dy = curr_y - prev_y
                        
                        direction = ""
                        if dx > 0:
                            direction = "right"
                        elif dx < 0:
                            direction = "left"
                        elif dy > 0:
                            direction = "down"
                        elif dy < 0:
                            direction = "up"
                        
                        logger.info(f"  Move {direction} from ({prev_x}, {prev_y}) to ({curr_x}, {curr_y})")
                        
                        # Set the next button for the first step only
                        if i == 1:
                            next_button = direction
                
                if next_button:
                    logger.info(f"Next movement: '{next_button}'")
                    return next_button
            
        except nx.NetworkXNoPath:
            logger.info(f"No path found from {source_node} to {dest_node}")
        except Exception as e:
            logger.info(f"Error finding path: {e}")
            
        return None
    
    async def _show_locations(self, map_filter, blackboard):
        """Show visited locations, optionally filtered by map"""
        visited_maps = {}
        
        # Collect visited locations by map
        for node_id, data in blackboard.world_graph.nodes(data=True):
            if data.get('visited', False):
                map_name, x, y = node_id
                
                if map_name not in visited_maps:
                    visited_maps[map_name] = []
                
                visited_maps[map_name].append((x, y))
        
        if map_filter:
            # Show details for a specific map
            if map_filter in visited_maps:
                positions = visited_maps[map_filter]
                logger.info(f"Visited locations in {map_filter} ({len(positions)} positions):")
                
                # Sort positions for easier reading
                positions.sort(key=lambda pos: (pos[1], pos[0]))  # Sort by y, then x
                
                for x, y in positions[:20]:  # Limit to 20 positions
                    # Check if there are dialogs at this position
                    node_id = (map_filter, x, y)
                    dialogs = blackboard.world_graph.nodes[node_id].get('dialogs', [])
                    
                    if dialogs:
                        dialog_count = len(dialogs)
                        logger.info(f"  ({x}, {y}) - {dialog_count} dialog entries")
                    else:
                        logger.info(f"  ({x}, {y})")
                
                if len(positions) > 20:
                    logger.info(f"  ... and {len(positions) - 20} more positions")
            else:
                logger.info(f"No visited locations in map: {map_filter}")
        else:
            # Show summary of all maps
            logger.info(f"Visited maps ({len(visited_maps)} total):")
            for map_name, positions in sorted(visited_maps.items()):
                logger.info(f"  {map_name}: {len(positions)} positions")
    
    async def _show_position(self, blackboard):
        """Show current player position and map"""
        position = blackboard.game_state.get("player", {}).get("position", (0, 0, "Unknown"))
        map_name = blackboard.game_state.get("map", {}).get("name", "Unknown")
        
        x, y, facing = position
        logger.info(f"Current position: ({x}, {y}) facing {facing} in {map_name}")
        
        # Show surrounding tiles if available
        if 'viewport' in blackboard.game_state and 'tiles' in blackboard.game_state['viewport']:
            tiles = blackboard.game_state['viewport']['tiles']
            if tiles:
                logger.info("Surrounding tiles:")
                for row in tiles:
                    logger.info("  " + " ".join(row))
            
    async def _show_state(self, blackboard):
        """Show detailed information about the current game state"""
        game_state = blackboard.game_state
        current_state = game_state.get('state', 'unknown')
        
        logger.info(f"Current game state: {current_state}")
        logger.info(f"Current phase: {blackboard.controller.current_phase.name if hasattr(blackboard, 'controller') else 'Unknown'}")
        
        # Show different details based on the state
        if current_state == "menu":
            menu_state = game_state.get("text", {}).get("menu_state", {})
            cursor_pos = menu_state.get("cursor_pos", (None, None))
            cursor_text = menu_state.get("cursor_text", "None")
            current_item = menu_state.get("current_item", -1)
            max_item = menu_state.get("max_item", -1)
            
            logger.info(f"Menu details:")
            logger.info(f"  Cursor position: {cursor_pos}")
            logger.info(f"  Selected text: '{cursor_text}'")
            logger.info(f"  Current item: {current_item+1} of {max_item+1}")
            
            # Show all visible text lines
            text_lines = game_state.get("text", {}).get("lines", [])
            if text_lines:
                logger.info("Visible text:")
                for line in text_lines:
                    logger.info(f"  {line}")
            
        elif current_state == "dialog":
            dialog_text = game_state.get("text", {}).get("dialog", [])
            
            logger.info(f"Dialog text:")
            for line in dialog_text:
                logger.info(f"  {line}")
                
        elif current_state == "default":
            # Show player position and map
            position = game_state.get("player", {}).get("position", (0, 0, "Unknown"))
            map_name = game_state.get("map", {}).get("name", "Unknown")
            
            x, y, facing = position
            logger.info(f"Position: ({x}, {y}) facing {facing} in {map_name}")
            
            # Show entities if available
            entities = game_state.get("viewport", {}).get("entities", [])
            if entities:
                logger.info(f"Visible entities ({len(entities)}):")
                for entity in entities[:5]:  # Limit to 5 entities
                    entity_pos = entity.get('position', {'x': '?', 'y': '?'})
                    logger.info(f"  {entity.get('name', 'Unknown')} at ({entity_pos.get('x', '?')}, {entity_pos.get('y', '?')})")
                
                if len(entities) > 5:
                    logger.info(f"  ... and {len(entities) - 5} more entities")
                    
        # Show game stability info
        logger.info(f"Game state stable: {blackboard.stable_state}")
        logger.info(f"Stability counter: {blackboard.stability_counter}/{blackboard.required_stability_frames}")
                    
        # Also show last button press for context
        if self.last_button:
            logger.info(f"Last button press: {self.last_button}")
            logger.info(f"Frames since last button: {game_state.get('frame', 0) - blackboard.last_button_frame}")
    
    async def _process_command(self, command, blackboard):
        """Process user command and take appropriate action"""
        command = command.strip().lower()
        
        # Empty command - default to 'a'
        if not command:
            return {"button": "a"}
        
        # Direct button press
        if command in self.valid_buttons:
            return {"button": command}
            
        # Help command
        if command == "help":
            logger.info(self.help_text)
            return {}

        # State command - show current state
        if command == "state":
            await self._show_state(blackboard)
            return {}
            
        # Dialog command
        if command.startswith("dialog"):
            parts = command.split()
            print(parts)
            count = int(parts[1]) if len(parts) > 1 else 5
            await self._show_dialog(count, blackboard)
            return {}
            
        # Query command
        if command.startswith("query "):
            query = command[6:]
            await self._search_journal(query, blackboard)
            return {}
            
        # Path finding command
        if command.startswith("path "):
            parts = command.split()
            if len(parts) >= 4:
                try:
                    map_name = parts[1]
                    x = int(parts[2])
                    y = int(parts[3])
                    button = await self._find_path(map_name, x, y, blackboard)
                    if button:
                        return {"button": button}
                except ValueError:
                    logger.info("Invalid coordinates. Use: path [map] [x] [y]")
            else:
                logger.info("Incomplete path command. Use: path [map] [x] [y]")
            return {}
            
        # Locations command
        if command.startswith("loc"):
            parts = command.split()
            map_filter = parts[1] if len(parts) > 1 else None
            await self._show_locations(map_filter, blackboard)
            return {}
            
        # Position command
        if command == "pos":
            await self._show_position(blackboard)
            return {}
            
        # Unknown command - assume it's a button if it's a single word
        if " " not in command and len(command) <= 6:
            logger.info(f"Trying to press button: {command}")
            return {"button": command}
            
        logger.info(f"Unknown command: {command}. Type 'help' for available commands.")
        return {}