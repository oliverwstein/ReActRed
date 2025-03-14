import logging
import networkx as nx
logger = logging.getLogger("PokemonManager")
logger.setLevel(logging.INFO)

# Create file handler
import os
os.makedirs('logs', exist_ok=True)
fh = logging.FileHandler('logs/pokemon_manager.log', mode='w')
fh.setLevel(logging.INFO)

# Create formatter
formatter = logging.Formatter('%(message)s')
fh.setFormatter(formatter)

# Add handler to logger if not already present
if not logger.handlers:
    logger.addHandler(fh)
    
class GameStateManager:
    """
    Manages game state stability detection, flow control, and event recording.
    Determines when the game should pause for client input.
    """
    
    def __init__(self, pyboy, wrapper):
        """Initialize the GameStateManager with references to PyBoy and wrapper"""
        self.pyboy = pyboy
        self.wrapper = wrapper
        
        # State tracking
        self.prev_game_state = {}
        self.current_state_type = None
        self.state_entered_frame = 0
        self.last_button = None
        self.last_button_frame = 0
        
        # Stability detection
        self.stable_state = False
        self.stability_counter = 0
        self.required_stability_frames = 120
        
        # Game flow control
        self.paused = False
        self.waiting_for_input = False
        
        # Event recording
        self.journal = []
        self.world_graph = WorldGraph()
    
    def update(self, frame):
        """
        Update state tracking and check for stability.
        Returns a boolean indicating if a stable state was just reached.
        """
        current_state = self.wrapper.data
        state_type = current_state.get("state", "unknown")
        
        # Check if content has changed
        content_changed = self._has_content_changed(state_type)
        
        # Track state transitions
        if self.current_state_type != state_type:
            self._track_state_transition(frame)
            self.stability_counter = 0
            self.stable_state = False
        elif content_changed:
            self.stability_counter = 0
            self.stable_state = False
        
        # Update current state type
        self.current_state_type = state_type
        
        # Check for stability
        stable_change = False
        if self._is_state_stable(state_type):
            self.stability_counter += 1
            if self.stability_counter >= self.required_stability_frames:
                if not self.stable_state:
                    self.stable_state = True
                    stable_change = True
        else:
            self.stability_counter = 0
            self.stable_state = False
        
        # Record data from state
        self._record_from_state(current_state, frame)
        
        # Update previous state
        self.prev_game_state = current_state
        
        return stable_change
    
    def should_pause_for_input(self):
        """
        Determine if the game should pause for client input based on state type.
        Returns True for stable menu and default states, False for dialog and scripted.
        """
        if not self.stable_state:
            return False
        
        if self.current_state_type == "dialog":
            # Auto-press A for dialog
            return False
        elif self.current_state_type == "scripted":
            # Let scripted scenes play out
            return False
        elif self.current_state_type in ["menu", "default"]:
            # Pause for client input
            return True
        
        return False
    
    def auto_handle_state(self):
        """
        Automatically handle states that don't require client input.
        Auto-advances dialog by pressing A.
        Returns the button that was auto-pressed, if any.
        """
        if not self.stable_state:
            return None
        
        if self.current_state_type == "dialog":
            # Auto-press A for dialog
            return "a"
        
        return None
    
    def process_button(self, button, frame):
        """Record button press and update last button information"""
        self._record_action(button, frame)
        self.last_button = button
        self.last_button_frame = frame
        
        # Reset stability tracking after sending input
        self.stability_counter = 0
        self.stable_state = False
    
    def _has_content_changed(self, state_type):
        """
        Check if content has changed within the same state type.
        Compares relevant aspects based on state type.
        """
        if not self.prev_game_state:
            return True
        
        if state_type == "menu":
            # Check if menu cursor or content changed
            prev_menu = self.prev_game_state.get("text", {}).get("menu_state", {})
            curr_menu = self.wrapper.data.get("text", {}).get("menu_state", {})
            return prev_menu != curr_menu
        
        elif state_type == "dialog":
            # Check if dialog content changed
            prev_dialog = self.prev_game_state.get("text", {}).get("dialog", [])
            curr_dialog = self.wrapper.data.get("text", {}).get("dialog", [])
            return prev_dialog != curr_dialog
        
        elif state_type == "default":
            # Check if player position changed
            prev_pos = self.prev_game_state.get("player", {}).get("position")
            curr_pos = self.wrapper.data.get("player", {}).get("position")
            return prev_pos != curr_pos
        
        # For other states or if we can't determine, assume content changed
        return True
    
    def _is_state_stable(self, state_type):
        """
        Determine if current state is stable based on state type.
        Different criteria for dialog, menu, default, and scripted states.
        """
        if not self.prev_game_state:
            return False
        
        if state_type == "dialog":
            # Dialog is stable when text has stopped rendering
            prev_dialog = self.prev_game_state.get("text", {}).get("dialog", [])
            curr_dialog = self.wrapper.data.get("text", {}).get("dialog", [])
            
            # Check if dialog content is the same
            if prev_dialog != curr_dialog:
                return False
            
            # Check if dialog length has changed (still rendering)
            prev_len = sum(len(line) for line in prev_dialog) if prev_dialog else 0
            curr_len = sum(len(line) for line in curr_dialog) if curr_dialog else 0
            return prev_len == curr_len and curr_len > 0
        
        elif state_type == "menu":
            # Menu is stable when cursor position and items stay the same
            prev_menu = self.prev_game_state.get("text", {}).get("menu_state", {})
            curr_menu = self.wrapper.data.get("text", {}).get("menu_state", {})
            
            prev_cursor = prev_menu.get("cursor_pos")
            curr_cursor = curr_menu.get("cursor_pos")
            
            prev_text = prev_menu.get("cursor_text")
            curr_text = curr_menu.get("cursor_text")
            
            return prev_cursor == curr_cursor and prev_text == curr_text and curr_cursor is not None
        
        elif state_type == "default":
            # Default state is stable when no movement or animation is occurring
            prev_pos = self.prev_game_state.get("player", {}).get("position")
            curr_pos = self.wrapper.data.get("player", {}).get("position")
            return prev_pos == curr_pos
        
        elif state_type == "scripted":
            # Scripted state is considered unstable by default
            return False
        
        return False
    
    def _track_state_transition(self, frame):
        """Record when state transitions occur"""
        if self.current_state_type is not None:
            # Record the transition in the journal
            self.journal.append({
                "type": "state_transition",
                "frame": frame,
                "data": {
                    "from": self.current_state_type,
                    "to": self.wrapper.data.get("state", "unknown"),
                    "duration": frame - self.state_entered_frame
                }
            })
        
        # Update state entry frame
        self.state_entered_frame = frame
    
    def _record_from_state(self, state, frame):
        """Record data from the current game state"""
        # Record player position if available
        if "player" in state and "position" in state["player"]:
            position = state["player"]["position"]
            map_name = state.get("map", {}).get("name", "Unknown")
            if position[0] != 0 or position[1] != 0:  # Avoid recording (0,0) positions
                self._record_movement(position, map_name, frame)
        
        # Record dialog if available
        if "text" in state and "dialog" in state["text"] and state["text"]["dialog"]:
            self._record_dialog(state["text"]["dialog"], frame)
        # Record menu state if available
        if "text" in state and "menu_state" in state["text"] and state["text"]["menu_state"].get("cursor_pos"):
            self._record_menu(state["text"]["menu_state"], frame)
    
    def _record_movement(self, position, map_name, frame):
        """Record player movement to the journal in a streamlined format"""
        x, y, facing = position
        
        # Get the last recorded movement, if any
        recent_movements = self.get_entries_by_type("movement", 1)
        
        # Check if position has actually changed (not just facing direction)
        if recent_movements:
            last_x, last_y, _ = recent_movements[0]["data"]["position"]
            last_map = recent_movements[0]["data"]["map"]
            
            # Skip if only direction changed
            if x == last_x and y == last_y and map_name == last_map:
                return
            
            # Get current tile type from the viewport data if available
            current_tile_type = None
            prev_tile_type = None
            viewport_tiles = self.wrapper.data.get("viewport", {}).get("tiles")
            if viewport_tiles and len(viewport_tiles) > 4 and len(viewport_tiles[4]) > 4:
                # Current position is at center of viewport (4,4)
                current_tile_type = viewport_tiles[4][4]
            
            # Record the movement in the world graph
            self.world_graph.record_movement(
                (last_map, last_x, last_y), 
                (map_name, x, y),
                prev_tile_type=prev_tile_type,
                new_tile_type=current_tile_type
            )
        else:
            # First movement recorded, just add the location to the graph
            self.world_graph.add_location(map_name, x, y)
        
        # Add to journal since coordinates changed
        self.journal.append({
            "type": "movement",
            "frame": frame,
            "data": {
                "position": position,
                "map": map_name
            }
        })
        
        # Log the new position with facing direction
        logger.info(f"MOVEMENT | Position: ({x},{y}) facing {facing} in {map_name}")

    def _record_dialog(self, dialog_text, frame):
        """Record dialog text with intelligent handling of continuations"""
        if not dialog_text or not self.stable_state:
            return
        
        # Skip exact duplicates
        recent_dialogs = self.get_entries_by_type("dialog", 1)
        if recent_dialogs and recent_dialogs[0]["data"] == dialog_text:
            return
        
        # Initialize variables to track if this is a continuation and the final dialog
        is_continuation = False
        
        # Check for continuations if we have previous dialog
        if recent_dialogs:
            last_entry = recent_dialogs[0]
            prev_dialog = last_entry["data"]
            
            # Check for overlap
            prev_lines_set = set(prev_dialog)
            current_lines_set = set(dialog_text)
            
            # Case 1: Direct overlap in lines
            if prev_lines_set.intersection(current_lines_set):
                is_continuation = True
            
            # # Case 2: Previous dialog doesn't end with sentence-ending punctuation
            # elif prev_dialog and prev_dialog[-1] and not prev_dialog[-1].endswith((".", "!", "?")):
            #     is_continuation = True
            
            if is_continuation:
                # Combine entries by taking all lines from both but avoiding duplicates
                combined_lines = prev_dialog.copy()
                
                # Add new lines that aren't in the previous dialog
                for line in dialog_text:
                    if line not in prev_lines_set:
                        combined_lines.append(line)
                
                # Update the previous entry with combined content
                for i in range(len(self.journal) - 1, -1, -1):
                    if self.journal[i]["type"] == "dialog" and self.journal[i]["data"] == prev_dialog:
                        self.journal[i]["data"] = combined_lines
                        self.journal[i]["frame"] = frame
                        break
                
                # Don't log yet, let's wait to see if there are more continuations
                return
        
        # If we get here, this is a completely new dialog
        # This means any previous dialog is complete, so let's log the latest dialog
        if not is_continuation and recent_dialogs:
            # Log the previous (now complete) dialog
            complete_dialog = recent_dialogs[0]["data"]
            logger.info(f"DIALOG: {' '.join(complete_dialog)}")
        
        # Add the new dialog to the journal (but don't log it yet)
        self.journal.append({
            "type": "dialog",
            "frame": frame,
            "data": dialog_text
        })
    
    def _record_menu(self, menu_state, frame):
        """Record menu interaction to the journal"""
        # Skip if the exact same menu state was just recorded (check the last journal entry)
        last_menu = self.get_entries_by_type("menu", 1)
        if last_menu and last_menu[-1]["data"]['cursor_text'] == menu_state['cursor_text']:
            return 
        self.journal.append({
            "type": "menu",
            "frame": frame,
            "data": menu_state,
        })
        logger.info(f"MENU OPTION: {menu_state['cursor_text']}")
    
    def _record_action(self, action, frame):
        """Record action taken to the journal"""
        self.journal.append({
            "type": "action",
            "frame": frame,
            "data": {
                "button": action,
                "state": self.current_state_type
            }
        })
        if self.current_state_type != 'dialog':
            logger.info(f"ACTION: {action}")
    
    def get_entries_by_type(self, entry_type, count=10):
        """Return the most recent entries of a specific type"""
        entries = [e for e in self.journal if e["type"] == entry_type]
        return entries[-count:] if entries else None
    
    def get_entries_since_frame(self, frame, entry_type=None):
        """Return all entries since a specific frame, optionally filtered by type"""
        if entry_type:
            return [e for e in self.journal if e["frame"] > frame and e["type"] == entry_type]
        else:
            return [e for e in self.journal if e["frame"] > frame]
    
    def get_recent_dialogs(self, count=10):
        """Convenience method to get recent dialog entries"""
        return self.get_entries_by_type("dialog", count)
    
    def get_recent_movements(self, count=10):
        """Convenience method to get recent movement entries"""
        return self.get_entries_by_type("movement", count)
    
    def get_last_position(self):
        """Return the most recent player position"""
        movements = self.get_entries_by_type("movement", 1)
        if movements:
            return movements[0]["data"]["position"]
        return None
    
    def get_visited_maps(self):
        """Return a list of all maps the player has visited"""
        return self.world_graph.get_visited_maps()

    def get_map_distances(self):
        """
        Get distances to all visited maps from the current position
        
        Returns:
            dict: Map of map names to distance information
        """
        current_position = self.get_last_position()
        if not current_position:
            return {}
        
        # Convert from (x, y, facing) to (map, x, y)
        recent_movements = self.get_entries_by_type("movement", 1)
        if not recent_movements:
            return {}
        
        current_map = recent_movements[0]["data"]["map"]
        x, y, _ = current_position
        
        # Get distances to all maps
        return self.world_graph.get_map_distances((current_map, x, y))

    def find_path_to_map(self, dest_map):
        """
        Find a path from the current position to the specified map
        
        Args:
            dest_map (str): Name of the destination map
            
        Returns:
            list: Path to the destination map or None if no path exists
        """
        current_position = self.get_last_position()
        if not current_position:
            return None
        
        # Convert from (x, y, facing) to (map, x, y)
        recent_movements = self.get_entries_by_type("movement", 1)
        if not recent_movements:
            return None
        
        current_map = recent_movements[0]["data"]["map"]
        x, y, _ = current_position
        
        # Find path to the map
        return self.world_graph.find_path_to_map((current_map, x, y), dest_map)
    
class WorldGraph:
    """
    A simple graph representation of the Pokémon world based on player movement.
    
    Each node is a (map_name, x, y) tuple representing a location.
    Edges represent possible movements between locations.
    """
    
    def __init__(self):
        # Main graph for pathfinding
        self.graph = nx.DiGraph()
        
        # Store set of visited maps
        self.visited_maps = set()
    
    def add_location(self, map_name, x, y, tile_type=None):
        """Add a location to the graph"""
        if not map_name or x is None or y is None:
            return
        
        node = (map_name, x, y)
        if not self.graph.has_node(node):
            self.graph.add_node(node, 
                                map=map_name, 
                                position=(x, y),
                                tile_type=tile_type or 'unknown')
            
            self.visited_maps.add(map_name)
    
    def record_movement(self, prev_position, new_position, prev_tile_type=None, new_tile_type=None):
        """
        Record a movement between two positions
        
        Args:
            prev_position (tuple): (map_name, x, y) of previous position
            new_position (tuple): (map_name, x, y) of new position
            prev_tile_type (str, optional): Tile type at previous position
            new_tile_type (str, optional): Tile type at new position
        
        Returns:
            bool: True if a new edge was added, False otherwise
        """
        if not prev_position or not new_position:
            return False
        
        # Unpack positions
        prev_map, prev_x, prev_y = prev_position
        new_map, new_x, new_y = new_position
        
        # Add both locations with their tile types if provided
        self.add_location(prev_map, prev_x, prev_y, prev_tile_type)
        self.add_location(new_map, new_x, new_y, new_tile_type)
        
        # Determine direction for same-map movement
        direction = None
        reverse_direction = None
        
        if prev_map == new_map:
            dx, dy = new_x - prev_x, new_y - prev_y
            if dx == 1 and dy == 0:
                direction = 'right'
                reverse_direction = 'left'
            elif dx == -1 and dy == 0:
                direction = 'left'
                reverse_direction = 'right'
            elif dx == 0 and dy == 1:
                direction = 'down'
                reverse_direction = 'up'
            elif dx == 0 and dy == -1:
                direction = 'up'
                reverse_direction = 'down'
        
        # Check if this is a ledge (one-way) based on tile types
        is_ledge = False
        if prev_tile_type in ['<', '>', 'v']:
            is_ledge = True
            # Only create one-way edges for ledges in the appropriate direction
            if (prev_tile_type == '<' and direction == 'left') or \
               (prev_tile_type == '>' and direction == 'right') or \
               (prev_tile_type == 'v' and direction == 'down'):
                is_ledge = True
            else:
                # If we're moving in a direction not matching the ledge direction,
                # it's probably a regular step
                is_ledge = False
        
        # Determine edge type (map transition or regular movement)
        edge_type = 'transition' if prev_map != new_map else 'walk'
        
        # Add the forward edge
        self.graph.add_edge(prev_position, new_position, 
                            type=edge_type,
                            direction=direction,
                            weight=5 if edge_type == 'transition' else 1)
        
        # For movements that aren't one-way ledges, add the reverse edge too
        if not is_ledge:
            # For map transitions, the reverse direction would be null
            transition_reverse = None if edge_type == 'transition' else reverse_direction
            
            self.graph.add_edge(new_position, prev_position,
                               type=edge_type,
                               direction=transition_reverse,
                               weight=5 if edge_type == 'transition' else 1)
        
        return True
    
    def get_visited_maps(self):
        """Get a list of all visited maps"""
        return list(self.visited_maps)
    
    def get_map_coords(self, map_name):
        """Get all visited coordinates for a specific map"""
        return [(x, y) for m, x, y in self.graph.nodes() if m == map_name]
    
    def find_path(self, start_pos, end_pos):
        """Find the shortest path between two positions"""
        if not self.graph.has_node(start_pos) or not self.graph.has_node(end_pos):
            return None
        
        try:
            path = nx.shortest_path(self.graph, start_pos, end_pos, weight='weight')
            return path
        except nx.NetworkXNoPath:
            return None
        
    def find_path_to_map(self, start_pos, dest_map):
        """
        Find the shortest path from a position to any point in the destination map.
        
        Args:
            start_pos (tuple): (map_name, x, y) of starting position
            dest_map (str): Name of the destination map
            
        Returns:
            list: Shortest path to the destination map or None if no path exists
        """
        if not self.graph.has_node(start_pos) or dest_map not in self.visited_maps:
            return None
            
        # Get all nodes in the destination map
        dest_nodes = [node for node in self.graph.nodes() if node[0] == dest_map]
        if not dest_nodes:
            return None
            
        # Find the shortest path to any node in the destination map
        shortest_path = None
        shortest_length = float('inf')
        
        for dest_node in dest_nodes:
            try:
                path = nx.shortest_path(self.graph, start_pos, dest_node, weight='weight')
                
                # Check if this path is shorter than the previous best
                if len(path) < shortest_length:
                    shortest_path = path
                    shortest_length = len(path)
            except nx.NetworkXNoPath:
                # No path to this specific node, try another
                continue
                
        return shortest_path

    def get_map_distances(self, current_pos):
        """
        Get distances to all visited maps from the current position.
        
        Args:
            current_pos (tuple): (map_name, x, y) of current position
            
        Returns:
            dict: Map of map names to (distance, next_step) tuples
                  where distance is the number of steps to reach the map
                  and next_step is the immediate next position to take
        """
        if not self.graph.has_node(current_pos):
            return {}
            
        result = {}
        
        # For each visited map, find the shortest path
        for map_name in self.visited_maps:
            # Skip the current map
            if map_name == current_pos[0]:
                continue
                
            path = self.find_path_to_map(current_pos, map_name)
            if path:
                # Store the distance and the next position to move to
                next_step = path[1] if len(path) > 1 else None
                result[map_name] = {
                    'distance': len(path) - 1,  # Subtract 1 since we're already at the first position
                    'next_step': next_step
                }
                
        return result
    
    def get_movement_directions(self, path):
        """Convert a path to a list of movement directions"""
        if not path or len(path) < 2:
            return []
        
        directions = []
        for i in range(len(path) - 1):
            from_pos = path[i]
            to_pos = path[i + 1]
            
            # Get edge data
            edge_data = self.graph.get_edge_data(from_pos, to_pos)
            
            if edge_data and 'direction' in edge_data:
                directions.append(edge_data['direction'] or 'transition')
            else:
                # Map transition
                if from_pos[0] != to_pos[0]:
                    directions.append('transition')
                else:
                    # Calculate direction based on coordinates
                    dx, dy = to_pos[1] - from_pos[1], to_pos[2] - from_pos[2]
                    if dx == 1 and dy == 0:
                        directions.append('right')
                    elif dx == -1 and dy == 0:
                        directions.append('left')
                    elif dx == 0 and dy == 1:
                        directions.append('down')
                    elif dx == 0 and dy == -1:
                        directions.append('up')
                    else:
                        directions.append('unknown')
        
        return directions
    
    def __str__(self):
        """String representation of the world graph"""
        return f"WorldGraph: {len(self.visited_maps)} maps, {len(self.graph.nodes())} locations, {len(self.graph.edges())} connections"
    