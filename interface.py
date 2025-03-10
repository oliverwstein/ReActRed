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
                if node_x == x and node_y == y:
                    tile_code = '@'
                else:
                    tile_code = data.get('tile_code', '?')
                explored_tiles[(node_x, node_y)] = tile_code
        
        if not explored_tiles:
            logger.info("No map data available for this area yet.")
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
        logger.info(f"Map coordinates: Player @ ({x},{y}) in explored area from ({min_x},{min_y}) to ({max_x},{max_y})")
        logger.info(f"Legend: @ = Player position, ? = Unexplored, 0 = Walkable, W = Water, T = Tree, G = Grass, v/</>= Ledges")
        
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
                    
    async def _show_state(self, blackboard):
        """Show detailed information about the current game state in the same format as wrapper.__str__"""
        game_state = blackboard.game_state
        
        # Format the state information similar to wrapper.__str__
        print(f"\n{'-' * 20} Frame: {game_state['frame']} {'-' * 20}")
        print(f"State: {game_state['state']} | In Battle: {game_state['is_in_battle']} | Last Button: {game_state['last_button']}")
        
        # Map information
        print(f"\n=== MAP INFO ===")
        print(f"Current Map: {game_state['map']['name']}")
        print(f"Tileset: {game_state['map']['tileset']['name']}")
        print(f"Dimensions: {game_state['map']['dimensions']}")
        
        # Player information
        print(f"\n=== PLAYER INFO ===")
        player_x, player_y, facing = game_state['player']['position']
        print(f"Position: ({player_x}, {player_y}) Facing: {facing}")
        print(f"Money: {game_state['player']['money']} ₽")
        print(f"Badges: {', '.join(game_state['player']['badges']) if game_state['player']['badges'] else 'None'}")
        print(f"Pokédex: {game_state['player']['pokedex']['owned']} owned, {game_state['player']['pokedex']['seen']} seen")
        
        # Bag items
        print(f"\n=== BAG ITEMS ===")
        if game_state['player']['bag']:
            for item_name, quantity in game_state['player']['bag']:
                print(f"  • {item_name} x{quantity}")
        else:
            print("  • Empty bag")
        
        # Team information
        print(f"\n=== TEAM POKÉMON ===")
        if game_state['player']['team'] and game_state['player']['team'].get('pokemon'):
            for pokemon in game_state['player']['team']['pokemon']:
                print(f"  • {pokemon.get('nickname', 'Unknown')} ({pokemon.get('species_id', 'Unknown')}) Lv.{pokemon.get('level', '?')}")
                print(f"    HP: {pokemon.get('current_hp', '?')}/{pokemon.get('max_hp', '?')} | Status: {pokemon.get('status', 'Unknown')}")
                print(f"    Types: {', '.join(filter(None, pokemon.get('types', ['Unknown'])))}")
                print(f"    Moves: {', '.join(pokemon.get('moves', ['None']))}")
                
                # Print stats in a compact format
                if 'stats' in pokemon:
                    stats = pokemon['stats']
                    stats_str = " | ".join([f"{k}: {v}" for k, v in stats.items()])
                    print(f"    Stats: {stats_str}")
        else:
            print("  • No Pokémon in team")
        
        # Map entities (NPCs, etc.)
        print(f"\n=== MAP ENTITIES ===")
        if game_state['viewport']['entities']:
            for entity in game_state['viewport']['entities']:
                print(f"  • {entity.get('name', 'Unknown')} @ ({entity['position']['x']}, {entity['position']['y']}) - {entity.get('state', 'Unknown')}")
        else:
            print("  • No visible entities")
        
        # Map warps
        if game_state['map']['warps']:
            print(f"\n=== MAP WARPS ===")
            for coords, destination in game_state['map']['warps'].items():
                print(f"  • Warp @ {coords} → {destination}")
        
        # Battle information
        if game_state['is_in_battle']:
            print(f"\n{'=' * 20} BATTLE {'=' * 20}")
            battle = game_state['battle']
            
            # Battle type
            battle_type = "Trainer Battle" if battle.get("is_trainer_battle", False) else "Wild Encounter"
            print(f"Type: {battle_type}")
            
            # Player's active Pokémon
            if game_state['player']['team'] and len(game_state['player']['team']['pokemon']) > 0:
                active_pokemon = game_state['player']['team']['pokemon'][0]
                print(f"\nPLAYER POKÉMON:")
                print(f"  • {active_pokemon.get('nickname', 'Unknown')} ({active_pokemon.get('species_id', 'Unknown')}) Lv.{active_pokemon.get('level', '?')}")
                print(f"    HP: {active_pokemon.get('current_hp', '?')}/{active_pokemon.get('max_hp', '?')} | Status: {active_pokemon.get('status', 'Unknown')}")
            
            # Enemy Pokémon
            if 'enemy_pokemon' in battle:
                enemy = battle['enemy_pokemon']
                print(f"\nENEMY POKÉMON:")
                print(f"  • {enemy.get('nickname', enemy.get('species_name', 'Unknown'))} ({enemy.get('species_name', 'Unknown')}) Lv.{enemy.get('level', '?')}")
                print(f"    HP: {enemy.get('hp_percent', '?')}% | Status: {enemy.get('status', 'Unknown')}")
                print(f"    Types: {', '.join(filter(None, enemy.get('types', ['Unknown'])))}")
            
            # Turn counter
            if 'turn_counter' in battle:
                print(f"\nTurn: {battle['turn_counter'] + 1}")
        
        # Menu information
        menu_state = game_state['text'].get('menu_state', {})
        if menu_state.get('cursor_pos') is not None:
            print(f"\n=== VISIBLE TEXT ===")
            for line in game_state['text'].get("lines"):
                print(f"  {line}")
            print(f"\n=== MENU INFO ===")
            cursor_pos = menu_state.get('cursor_pos', ('?', '?'))
            print(f"  Cursor Position: {cursor_pos}")
            if menu_state.get('cursor_text'):
                print(f"  Selected Text: '{menu_state['cursor_text']}'")
        
        # Text and dialog information
        if game_state['text']['dialog'] and game_state['state'] != 'menu':
            print(f"\n=== DIALOG ===")
            for line in game_state['text']['dialog']:
                print(f"  {line}")
                    
        # Tilemap visualization
        if game_state['state'] == 'default' and not game_state['is_in_battle'] and game_state['viewport'].get('tiles'):
            print(f"\n=== MAP VIEW ===")
            map_with_player = game_state['viewport']['tiles']
            map_with_player[4][4] = '@'
            for row in map_with_player:
                print('  ' + ' '.join(row))
                
        # Also show last button press for context
        if self.last_button:
            print(f"Last button press: {self.last_button}")
            print(f"Frames since last button: {game_state.get('frame', 0) - blackboard.last_button_frame}")
    
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