#!/usr/bin/env python3
"""
Pokemon Game Logger

This module provides a Logger class for recording and tracking game state,
including dialog, movement, menu interactions, and world graph construction.
"""

import logging
import networkx as nx
from enum import Enum

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger("PokemonLogger")

# Define game states
class GameState(Enum):
    DIALOG = "dialog"
    MENU = "menu"
    SCRIPTED = "scripted"
    DEFAULT = "default"
    UNKNOWN = "unknown"

class Logger:
    """
    Records and tracks game state, dialog, movement, and builds a traversal graph
    of the game world.
    """
    
    def __init__(self, log_level=logging.INFO):
        """Initialize the logger with empty data structures"""
        # Configure logging
        self.logger = logging.getLogger("PokemonLogger")
        self.logger.setLevel(log_level)
        
        # Data recording structures
        self.journal = []  # Chronological record of observations and actions
        self.dialog_history = []  # All dialog seen
        self.movement_history = []  # Position history
        self.menu_history = []  # Menu interactions
        self.action_history = []  # Actions taken
        
        # Game state history
        self.state_transitions = []  # Record of state changes
        self.current_state_entered = 0
        self.current_state = None
        
        # World graph for navigation and world modeling
        self.world_graph = nx.Graph()
        
        self.logger.info("Logger initialized")
    
    def update_state_tracking(self, new_state, frame):
        """
        Track state transitions between different game states.
        
        Args:
            new_state (str): The current game state (dialog, menu, scripted, default)
            frame (int): The current frame number
        """
        if self.current_state != new_state:
            if self.current_state is not None:
                # Record the state exit
                duration = frame - self.current_state_entered
                self.state_transitions.append({
                    "state": self.current_state,
                    "entered_frame": self.current_state_entered,
                    "exited_frame": frame,
                    "duration": duration
                })
                self.logger.info(f"Exited {self.current_state} state after {duration} frames")
            
            # Record new state entry
            self.current_state = new_state
            self.current_state_entered = frame
            self.logger.info(f"Entered {new_state} state at frame {frame}")
    
    def record_movement(self, position, map_name, frame, viewport_data=None):
        """
        Record player movement and update the world graph.
        
        Args:
            position (tuple): (x, y, facing) tuple of player position
            map_name (str): Current map name
            frame (int): Current frame number
            viewport_data (dict): Optional viewport data for tile information
        """
        x, y, facing = position
        node_id = (map_name, x, y)
        
        # Create journal entry
        entry = {
            "frame": frame,
            "position": position,
            "map": map_name
        }
        self.movement_history.append(entry)
        self.journal.append({
            "type": "movement",
            "frame": frame,
            "data": entry
        })
        
        # Update graph - add or update node for current position
        if not self.world_graph.has_node(node_id):
            self.world_graph.add_node(node_id, 
                                    map=map_name,
                                    visited=True,
                                    first_visit_frame=frame)
        else:
            # Mark as visited and update last visit
            self.world_graph.nodes[node_id]['visited'] = True
            self.world_graph.nodes[node_id]['last_visit_frame'] = frame
        
        # Create edge between previous position and current position
        if len(self.movement_history) > 1:
            prev_entry = self.movement_history[-2]
            prev_map = prev_entry["map"]
            prev_x, prev_y, _ = prev_entry["position"]
            prev_node = (prev_map, prev_x, prev_y)
            
            # Create edge between previous and current position
            if prev_map == map_name:
                # Same map - check if adjacent (Manhattan distance of 1)
                dx = abs(x - prev_x)
                dy = abs(y - prev_y)
                if dx + dy == 1:
                    # Add edge if not already present
                    if not self.world_graph.has_edge(prev_node, node_id):
                        self.world_graph.add_edge(prev_node, node_id, traversal_count=1)
                    else:
                        # Increment traversal count if edge exists
                        self.world_graph[prev_node][node_id]['traversal_count'] += 1
            else:
                # Different maps - create edge regardless of position
                # This represents doors, cave entrances, etc.
                if not self.world_graph.has_edge(prev_node, node_id):
                    self.world_graph.add_edge(prev_node, node_id, 
                                             is_warp=True, 
                                             traversal_count=1)
                else:
                    self.world_graph[prev_node][node_id]['traversal_count'] += 1
        
        # Update surrounding tiles based on viewport data
        if viewport_data and 'tiles' in viewport_data:
            tiles = viewport_data['tiles']
            if tiles:
                # Player is typically in the center of the viewport
                center_y = len(tiles) // 2
                center_x = len(tiles[0]) // 2
                
                for dy in range(len(tiles)):
                    for dx in range(len(tiles[0])):
                        # Calculate map coordinates
                        map_x = x + (dx - center_x)
                        map_y = y + (dy - center_y)
                        tile_code = tiles[dy][dx]
                        
                        # Skip "#" tiles - they're not part of the map
                        if tile_code == "#":
                            continue
                        
                        tile_node = (map_name, map_x, map_y)
                        
                        # Add or update node with tile information
                        if not self.world_graph.has_node(tile_node):
                            # New node
                            self.world_graph.add_node(tile_node,
                                                    map=map_name,
                                                    tile_code=tile_code,
                                                    visited=(map_x==x and map_y==y),
                                                    first_visit_frame=frame if map_x==x and map_y==y else None)
                        else:
                            # Existing node - update tile code
                            self.world_graph.nodes[tile_node]['tile_code'] = tile_code
                            
                            # Only update visited status if we're standing on it and it wasn't visited before
                            if map_x==x and map_y==y and not self.world_graph.nodes[tile_node].get('visited', False):
                                self.world_graph.nodes[tile_node]['visited'] = True
                                self.world_graph.nodes[tile_node]['first_visit_frame'] = frame
        
        self.logger.debug(f"Recorded movement: {position} in {map_name}")
        
    def record_dialog(self, dialog_text, frame, position=None, map_name=None):
        """
        Record dialog text and associate it with the current location if provided.
        
        Args:
            dialog_text (list): List of dialog text lines
            frame (int): Current frame number
            position (tuple, optional): (x, y, facing) player position
            map_name (str, optional): Current map name
        """
        if not dialog_text:
            return
            
        # Avoid duplicates by checking if the last entry is identical
        if not self.dialog_history or self.dialog_history[-1]["text"] != dialog_text:
            entry = {
                "frame": frame,
                "text": dialog_text,
                "position": position,
                "map": map_name
            }
            self.dialog_history.append(entry)
            self.journal.append({
                "type": "dialog",
                "frame": frame,
                "data": dialog_text
            })
            
            # If position and map are provided, update the world graph
            if position and map_name:
                x, y, _ = position
                node_id = (map_name, x, y)
                
                if self.world_graph.has_node(node_id):
                    # Add dialog as node attribute
                    if 'dialogs' not in self.world_graph.nodes[node_id]:
                        self.world_graph.nodes[node_id]['dialogs'] = []
                    
                    self.world_graph.nodes[node_id]['dialogs'].append({
                        'frame': frame,
                        'text': dialog_text
                    })
                    
            self.logger.debug(f"Recorded dialog: {' '.join(dialog_text)}")
        
    def record_menu(self, menu_state, frame):
        """
        Record menu interaction.
        
        Args:
            menu_state (dict): Menu state information
            frame (int): Current frame number
        """
        entry = {
            "frame": frame,
            "menu_state": menu_state
        }
        self.menu_history.append(entry)
        self.journal.append({
            "type": "menu",
            "frame": frame,
            "data": menu_state
        })
        self.logger.debug(f"Recorded menu state: {menu_state}")
    
    def record_action(self, action, frame, state=None):
        """
        Record action taken by the player or AI.
        
        Args:
            action (str): Button pressed
            frame (int): Current frame number
            state (str, optional): Current game state
        """
        entry = {
            "frame": frame,
            "action": action,
            "state": state or self.current_state
        }
        self.action_history.append(entry)
        self.journal.append({
            "type": "action",
            "frame": frame,
            "data": {
                "button": action,
                "state": state or self.current_state
            }
        })
        self.logger.debug(f"Recorded action: {action} in state {state or self.current_state}")
    
    def record_battle(self, battle_data, frame):
        """
        Record battle information.
        
        Args:
            battle_data (dict): Battle state information
            frame (int): Current frame number
        """
        self.journal.append({
            "type": "battle",
            "frame": frame,
            "data": battle_data
        })
        self.logger.debug(f"Recorded battle state at frame {frame}")
    
    def record_pokemon_interaction(self, interaction_type, pokemon_data, frame):
        """
        Record interactions with Pokemon like catches, evolutions, etc.
        
        Args:
            interaction_type (str): Type of interaction (catch, evolution, etc.)
            pokemon_data (dict): Pokemon information
            frame (int): Current frame number
        """
        self.journal.append({
            "type": "pokemon_interaction",
            "frame": frame,
            "interaction": interaction_type,
            "data": pokemon_data
        })
        self.logger.debug(f"Recorded {interaction_type} with {pokemon_data.get('species_id', 'Unknown')}")
    
    def record_item_interaction(self, interaction_type, item_data, frame):
        """
        Record interactions with items.
        
        Args:
            interaction_type (str): Type of interaction (pickup, use, buy, etc.)
            item_data (dict): Item information
            frame (int): Current frame number
        """
        self.journal.append({
            "type": "item_interaction",
            "frame": frame,
            "interaction": interaction_type,
            "data": item_data
        })
        self.logger.debug(f"Recorded {interaction_type} with {item_data.get('name', 'Unknown')}")
    
    def get_recent_journal(self, entries=10, entry_type=None):
        """
        Get the N most recent journal entries, optionally filtered by type.
        
        Args:
            entries (int): Number of entries to retrieve
            entry_type (str, optional): Filter by entry type
            
        Returns:
            list: Recent journal entries
        """
        if entry_type:
            filtered = [entry for entry in self.journal if entry["type"] == entry_type]
            return filtered[-entries:] if filtered else []
        return self.journal[-entries:] if self.journal else []
    
    def search_journal(self, query, max_results=15):
        """
        Search journal entries containing the query string.
        
        Args:
            query (str): Search query
            max_results (int): Maximum number of results to return
            
        Returns:
            list: Matching journal entries
        """
        results = []
        for entry in self.journal:
            if query.lower() in str(entry["data"]).lower():
                results.append(entry)
                
        return results[-max_results:] if results else []
    
    def get_visited_maps(self):
        """
        Get a list of all visited maps.
        
        Returns:
            dict: Map name -> count of visited positions
        """
        visited_maps = {}
        
        for node_id, data in self.world_graph.nodes(data=True):
            if data.get('visited', False):
                map_name = data.get('map', 'Unknown')
                
                if map_name not in visited_maps:
                    visited_maps[map_name] = 0
                    
                visited_maps[map_name] += 1
                
        return visited_maps
    
    def get_visited_locations(self, map_name=None):
        """
        Get a list of visited locations, optionally filtered by map.
        
        Args:
            map_name (str, optional): Filter by map name
            
        Returns:
            list: Visited locations as (map, x, y) tuples
        """
        visited = []
        
        for node_id, data in self.world_graph.nodes(data=True):
            if data.get('visited', False):
                node_map, x, y = node_id
                
                if map_name is None or node_map == map_name:
                    visited.append((node_map, x, y))
                    
        return visited
    
    def find_path(self, start_pos, end_pos):
        """
        Find the shortest path between two positions.
        
        Args:
            start_pos (tuple): (map_name, x, y) start position
            end_pos (tuple): (map_name, x, y) end position
            
        Returns:
            list: List of positions forming the shortest path, or None if no path exists
        """
        try:
            if not self.world_graph.has_node(start_pos):
                self.logger.warning(f"Start position {start_pos} not in world graph")
                return None
                
            if not self.world_graph.has_node(end_pos):
                self.logger.warning(f"End position {end_pos} not in world graph")
                return None
                
            path = nx.shortest_path(self.world_graph, start_pos, end_pos)
            return path
        except nx.NetworkXNoPath:
            self.logger.warning(f"No path found from {start_pos} to {end_pos}")
            return None
        except Exception as e:
            self.logger.error(f"Error finding path: {e}")
            return None
    
    def get_map_statistics(self, map_name=None):
        """
        Get statistics about map exploration.
        
        Args:
            map_name (str, optional): Filter by map name
            
        Returns:
            dict: Map statistics
        """
        stats = {
            "total_nodes": 0,
            "visited_nodes": 0,
            "total_edges": 0,
            "warps": 0,
            "dialogs": 0
        }
        
        # Count nodes
        for node_id, data in self.world_graph.nodes(data=True):
            node_map = node_id[0]
            
            if map_name is None or node_map == map_name:
                stats["total_nodes"] += 1
                
                if data.get('visited', False):
                    stats["visited_nodes"] += 1
                    
                if 'dialogs' in data:
                    stats["dialogs"] += len(data['dialogs'])
        
        # Count edges and warps
        for u, v, data in self.world_graph.edges(data=True):
            u_map = u[0]
            v_map = v[0]
            
            if map_name is None or u_map == map_name or v_map == map_name:
                stats["total_edges"] += 1
                
                if data.get('is_warp', False):
                    stats["warps"] += 1
                    
        return stats
    
    def save_graph(self, filename):
        """
        Save the world graph to a file.
        
        Args:
            filename (str): Output filename
        """
        try:
            import pickle
            with open(filename, 'wb') as f:
                pickle.dump(self.world_graph, f)
            self.logger.info(f"World graph saved to {filename}")
            return True
        except Exception as e:
            self.logger.error(f"Error saving world graph: {e}")
            return False
    
    def load_graph(self, filename):
        """
        Load the world graph from a file.
        
        Args:
            filename (str): Input filename
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            import pickle
            with open(filename, 'rb') as f:
                self.world_graph = pickle.load(f)
            self.logger.info(f"World graph loaded from {filename}")
            return True
        except Exception as e:
            self.logger.error(f"Error loading world graph: {e}")
            return False