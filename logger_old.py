"""
A streamlined logging system for tracking player exploration in Pokémon Red/Blue.
Focuses on tracking entities, warps, and a detailed path with facing direction.
Removes the tile-based tracking to improve performance and reduce memory usage.
"""

import json
import copy

class PokemonGameLogger:
    """
    A streamlined logger for tracking the player's exploration in Pokémon Red/Blue.
    Focuses on entities, warps, and path tracking without tile-level data.
    """
    
    def __init__(self):
        """Initialize the logger with empty data structures."""
        self.log = {
            "maps": {},    # Map data (entities, warps)
            "path": []     # Player's path through the game
        }
        
        # Internal tracking state
        self._last_position = None
        self._last_map = None
        self._last_frame = 0
        self._last_facing = None
        
    def __str__(self):
        """Return a human-readable summary of the exploration log."""
        # Get statistics
        stats = self.get_stats()
        
        # Build summary string
        summary = []
        summary.append("\n===== EXPLORATION LOG SUMMARY =====")
        summary.append(f"Maps visited: {stats['maps_visited']}")
        summary.append(f"Warps discovered: {stats['warps_discovered']}")
        summary.append(f"Entities encountered: {stats['entities_encountered']}")
        summary.append(f"Path length: {stats['path_length']} steps")
        
        # Map details
        summary.append("\n=== Maps Explored ===")
        for map_name in sorted(self.log["maps"].keys()):
            map_data = self.log["maps"][map_name]
            
            # Only process maps with actual dimensions
            if map_data.get("dimensions", (0, 0)) == (0, 0):
                continue
                
            width, height = map_data["dimensions"]
            
            # Count entities and warps
            entity_count = len(map_data.get("entities", {}))
            warp_count = len(map_data.get("warps", {}))
            
            summary.append(f"  • {map_name} ({width}x{height}):")
            summary.append(f"    - Entities: {entity_count}")
            summary.append(f"    - Warps: {warp_count}")
            
            # Add a blank line after each map
            summary.append("")
        
        # Recent movement
        summary.append("\n=== Recent Movement ===")
        recent_path = self.log["path"][-10:] if len(self.log["path"]) > 10 else self.log["path"]
        for step in recent_path:
            frame, map_name, x, y, facing = step
            summary.append(f"  Frame {frame}: {map_name} at ({x}, {y}) facing {facing}")
        
        return "\n".join(summary)
    
    def update(self, frame, wrapper):
        """
        Update the log with the current game state.
        
        Args:
            frame (int): Current frame number
            wrapper (EnhancedPokemonWrapper): Reference to the game wrapper
        """
        # Skip if the game state isn't available
        if not wrapper.data:
            return
            
        # Extract current state information
        current_map = wrapper.data.get('map', {}).get('name')
        map_dimensions = wrapper.data.get('map', {}).get('dimensions', (0, 0))
        if not current_map or (map_dimensions[0] == 0 or map_dimensions[1] == 0):
            return        
            
        # Get player position and facing direction
        player_position = None
        player_facing = None
        if 'player' in wrapper.data and 'position' in wrapper.data['player']:
            position_data = wrapper.data['player']['position']
            if len(position_data) >= 3:
                player_position = (position_data[0], position_data[1])
                player_facing = position_data[2]
                
        # Skip update if essential data is missing
        if not player_position or not player_facing:
            return
        
        # Always track the player's path with facing information
        if (self._last_map != current_map or 
            self._last_position != player_position or 
            self._last_facing != player_facing):
            # Store as [frame, map_name, x, y, facing]
            self.log["path"].append([
                frame,
                current_map,
                player_position[0],
                player_position[1],
                player_facing
            ])
        
        # If map has valid dimensions, update its data
        if map_dimensions[0] > 0 and map_dimensions[1] > 0:
            # Initialize map data if needed
            if current_map not in self.log["maps"]:
                self._initialize_map(current_map, map_dimensions, frame)
            elif self.log["maps"][current_map].get("dimensions") != map_dimensions:
                # Update dimensions if they changed
                self.log["maps"][current_map]["dimensions"] = map_dimensions
            
            # Update entities and warps
            self._update_entities(current_map, frame, wrapper)
            self._update_warps(current_map, wrapper)
        
        # Store current state for next update
        self._last_position = player_position
        self._last_map = current_map
        self._last_frame = frame
        self._last_facing = player_facing
        
    def _initialize_map(self, map_name, dimensions, frame):
        """Initialize data for a new map."""
        # Create map entry
        self.log["maps"][map_name] = {
            "name": map_name,  # Store map name in the data for easier reference
            "dimensions": dimensions,
            "first_visit_frame": frame,
            "entities": {},
            "warps": {}
        }
    
    def _update_entities(self, current_map, frame, wrapper):
        """Update entity information for the current map."""
        # Get entities from current state
        entities = wrapper.data.get('viewport', {}).get('entities', [])
        if not entities:
            return
            
        map_entities = self.log["maps"][current_map]["entities"]
        
        for entity in entities:
            # Skip entities without name or position
            if 'name' not in entity or 'position' not in entity:
                continue
                
            entity_name = entity['name']
            entity_position = (entity['position'].get('x'), entity['position'].get('y'))
            
            # Skip invalid positions
            if None in entity_position:
                continue
                
            # Update entity in log
            if entity_name not in map_entities:
                map_entities[entity_name] = {
                    "first_seen_frame": frame,
                    "last_seen_frame": frame,
                    "positions": [entity_position]
                }
            else:
                # Update existing entity
                map_entities[entity_name]["last_seen_frame"] = frame
                
                # Add new position if not already seen
                if entity_position not in map_entities[entity_name]["positions"]:
                    map_entities[entity_name]["positions"].append(entity_position)
    
    def _update_warps(self, current_map, wrapper):
        """Update warp information for the current map."""
        # Get warps from game state
        warps = wrapper.data.get('map', {}).get('warps', {})
        if not warps:
            return
            
        map_warps = self.log["maps"][current_map]["warps"]
        
        # Add any new warps
        for warp_coords_str, destination in warps.items():
            # Convert string coords to tuple if needed
            warp_coords = None
            if isinstance(warp_coords_str, str):
                try:
                    warp_coords = eval(warp_coords_str)
                except:
                    continue
            else:
                warp_coords = warp_coords_str
            
            # Skip invalid coordinates
            if not isinstance(warp_coords, tuple) or len(warp_coords) != 2:
                continue
                
            # Add warp if not already in log
            if warp_coords not in map_warps:
                map_warps[warp_coords] = {
                    "destination": destination,
                    "discovered_frame": self._last_frame
                }
    
    def get_stats(self):
        """Return summary statistics about exploration."""
        maps_visited = len([m for m in self.log["maps"].values() 
                           if m.get("dimensions", (0, 0))[0] > 0])
        
        # Count entities and warps
        entities_encountered = sum(len(map_data.get("entities", {})) 
                                  for map_data in self.log["maps"].values())
        
        warps_discovered = sum(len(map_data.get("warps", {})) 
                              for map_data in self.log["maps"].values())
        
        return {
            "maps_visited": maps_visited,
            "entities_encountered": entities_encountered,
            "warps_discovered": warps_discovered,
            "path_length": len(self.log["path"])
        }
        
    def save_log(self, filename):
        """
        Save the current log to a JSON file.
        
        Args:
            filename (str): Path to the file to save
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Create a deep copy of the log to modify
            serializable_log = copy.deepcopy(self.log)
            
            # Convert tuple keys to strings for JSON serialization
            for map_name, map_data in serializable_log["maps"].items():
                # Convert warp coordinate tuples to strings
                if "warps" in map_data:
                    map_data["warps"] = {str(coords): data 
                                        for coords, data in map_data["warps"].items()}
                
                # Convert entity position tuples to strings in the positions list
                if "entities" in map_data:
                    for entity_name, entity_data in map_data["entities"].items():
                        if "positions" in entity_data:
                            entity_data["positions"] = [str(pos) for pos in entity_data["positions"]]
            
            with open(filename, 'w') as f:
                json.dump(serializable_log, f, indent=2)
            
            print(f"Log successfully saved to {filename}")
            return True
            
        except Exception as e:
            print(f"Error saving log: {e}")
            return False
    
    def load_log(self, filename):
        """
        Load a log from a JSON file.
        
        Args:
            filename (str): Path to the file to load
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            import ast
            
            with open(filename, 'r') as f:
                loaded_log = json.load(f)
            
            # Convert string representations to tuples
            for map_name, map_data in loaded_log["maps"].items():
                # Convert warp coordinate strings back to tuples
                if "warps" in map_data:
                    map_data["warps"] = {ast.literal_eval(coords_str): data 
                                        for coords_str, data in map_data["warps"].items()}
                
                # Convert entity position strings back to tuples
                if "entities" in map_data:
                    for entity_name, entity_data in map_data["entities"].items():
                        if "positions" in entity_data:
                            entity_data["positions"] = [ast.literal_eval(pos_str) 
                                                      for pos_str in entity_data["positions"]]
            
            # Update the log
            self.log = loaded_log
            
            # Restore internal state from the loaded log
            if self.log["path"]:
                last_entry = self.log["path"][-1]
                frame, map_name, x, y, facing = last_entry
                self._last_position = (x, y)
                self._last_map = map_name
                self._last_frame = frame
                self._last_facing = facing
            
            print(f"Log successfully loaded from {filename}")
            return True
            
        except Exception as e:
            print(f"Error loading log: {e}")
            return False