#!/usr/bin/env python3
"""
Redesigned Pokémon AI Client with Stability-Based Architecture

A redesigned client that focuses on finding stable states, making decisions at those points,
and waiting for the next stable state after an action, rather than trying to process every frame.

Usage:
    python client.py [--host HOST] [--port PORT] [--interactive] [--debug]
"""

import asyncio
import json
import argparse
import logging
import time
import random
import websockets
from enum import Enum, auto
import networkx as nx
from interface import InteractiveMode

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger("PokemonAI")

# Define game states
class GameState(Enum):
    DIALOG = "dialog"
    MENU = "menu"
    SCRIPTED = "scripted"
    DEFAULT = "default"
    UNKNOWN = "unknown"

# Blackboard for sharing data
class Blackboard:
    """Stores shared data and records game state history"""
    
    def __init__(self, ws):
        self.ws = ws
        self.game_state = {}
        self.prev_game_state = {}
        self.current_state_type = None
        self.last_button = None
        self.last_button_frame = 0
        self.stable_state = False
        self.stability_counter = 0
        self.required_stability_frames = 6  # Frames required for stability
        
        # Data recording structures
        self.journal = []  # Chronological record of observations and actions
        self.dialog_history = []  # All dialog seen
        self.movement_history = []  # Position history
        self.menu_history = []  # Menu interactions
        self.action_history = []  # Actions taken
        
        # World graph for navigation
        self.world_graph = nx.Graph()
        
        # State tracking
        self.state_entered_frame = 0
        self.state_transitions = []
    
    async def send_input(self, button):
        """Send input command to the server"""
        if button not in ["up", "down", "left", "right", "a", "b", "start", "select"]:
            logger.warning(f"Invalid button: {button}")
            return False
            
        current_frame = self.game_state.get("frame", 0)
        
        # Send the button command
        await self.ws.send(json.dumps({"button": button}))
        self.last_button = button
        self.last_button_frame = current_frame
        
        # Record the action
        self.record_action(button)
        
        # logger.info(f"Sent {button}, waiting for state to stabilize")
        
        # Reset stability tracking after sending input
        self.stability_counter = 0
        self.stable_state = False
        
        try:
            while True:
                # Non-blocking check for messages
                message = await asyncio.wait_for(self.ws.recv(), timeout=0.01)
        except asyncio.TimeoutError:
            # No more messages, which is expected
            pass
        
        # Reset stability tracking after sending input
        self.stability_counter = 0
        self.stable_state = False
        
        return True
    
    def update_game_state(self, new_state):
        """Update game state and check for stability"""
        current_frame = new_state.get("frame", 0)
        state_type = new_state.get("state", "unknown")
        
        # Save previous state for comparison
        self.prev_game_state = self.game_state
        self.game_state = new_state
        
        # Check if content has changed, even if state type remains the same
        content_changed = self.has_content_changed(state_type)
        
        # Track state transitions
        if self.current_state_type != state_type:
            self.track_state_transition(state_type, current_frame)
            
            # Always reset stability on state type change
            self.stability_counter = 0
            self.stable_state = False
        elif content_changed:
            # Content changed within the same state type
            # Reset stability counter
            self.stability_counter = 0
            self.stable_state = False
            logger.debug(f"Content changed within {state_type} state, reset stability")
        
        # Update current state type
        self.current_state_type = state_type
        
        # Check for stability based on state type
        if self.is_state_stable(state_type):
            self.stability_counter += 1
            if self.stability_counter >= self.required_stability_frames:
                if not self.stable_state:
                    # logger.info(f"Entered stable {state_type} state")
                    # logger.info(f"State {state_type} is now stable after {self.stability_counter} frames")
                    self.stable_state = True
        else:
            # Reset stability counter if state is not stable
            self.stability_counter = 0
            self.stable_state = False
            
        # Record data from the state
        self.record_from_state(new_state)
        
        return self.stable_state
    
    def has_content_changed(self, state_type):
        """Check if content has changed within the same state type"""
        if not self.prev_game_state:
            return True
            
        if state_type == "menu":
            # Check if menu cursor or content changed
            prev_menu = self.prev_game_state.get("text", {}).get("menu_state", {})
            curr_menu = self.game_state.get("text", {}).get("menu_state", {})
            return prev_menu != curr_menu
            
        elif state_type == "dialog":
            # Check if dialog content changed
            prev_dialog = self.prev_game_state.get("text", {}).get("dialog", [])
            curr_dialog = self.game_state.get("text", {}).get("dialog", [])
            return prev_dialog != curr_dialog
            
        elif state_type == "default":
            # Check if player position changed
            prev_pos = self.prev_game_state.get("player", {}).get("position")
            curr_pos = self.game_state.get("player", {}).get("position")
            return prev_pos != curr_pos
            
        # For other states or if we can't determine, assume content changed
        return True
    
    def track_state_transition(self, new_state_type, frame):
        """Record a state transition"""
        if self.current_state_type is not None:
            # Record the state exit
            duration = frame - self.state_entered_frame
            self.state_transitions.append({
                "state": self.current_state_type,
                "entered_frame": self.state_entered_frame,
                "exited_frame": frame,
                "duration": duration
            })
            # logger.info(f"Exited {self.current_state_type} state after {duration} frames")
        
        # Record new state entry
        self.state_entered_frame = frame
        # logger.info(f"Entered {new_state_type} state at frame {frame}")
    
    def is_state_stable(self, state_type):
        """
        Determine if the current state is stable based on its type
        Different state types have different stability criteria
        """
        if not self.prev_game_state:
            return False
            
        if state_type == "dialog":
            # Dialog is stable when text has stopped rendering
            prev_dialog = self.prev_game_state.get("text", {}).get("dialog", [])
            curr_dialog = self.game_state.get("text", {}).get("dialog", [])
            
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
            curr_menu = self.game_state.get("text", {}).get("menu_state", {})
            
            prev_cursor = prev_menu.get("cursor_pos")
            curr_cursor = curr_menu.get("cursor_pos")
            
            prev_text = prev_menu.get("cursor_text")
            curr_text = curr_menu.get("cursor_text")
            
            return prev_cursor == curr_cursor and prev_text == curr_text and curr_cursor is not None
            
        elif state_type == "default":
            # Default state is stable when no movement or animation is occurring
            # For simplicity, we'll consider it stable if position hasn't changed in a few frames
            prev_pos = self.prev_game_state.get("player", {}).get("position")
            curr_pos = self.game_state.get("player", {}).get("position")
            return prev_pos == curr_pos
            
        elif state_type == "scripted":
            # Scripted state is considered unstable by default
            # It will transition to another state when the script completes
            return False
            
        return False
    
    def record_from_state(self, state):
        """Record relevant data from the current game state"""
        # Record player position if available
        if "player" in state and "position" in state["player"]:
            position = state["player"]["position"]
            map_name = state.get("map", {}).get("name", "Unknown")
            self.record_movement(position, map_name)
            
        # Record dialog if available
        if "text" in state and "dialog" in state["text"] and state["text"]["dialog"]:
            self.record_dialog(state["text"]["dialog"])
            
        # Record menu state if available
        if "text" in state and "menu_state" in state["text"] and state["text"]["menu_state"].get("cursor_pos"):
            self.record_menu(state["text"]["menu_state"])
    
    def record_movement(self, position, map_name):
        """Record player movement and update the world graph"""
        # Check if position has actually changed before recording
        if self.movement_history and self.movement_history[-1]["position"] == position:
            return
            
        current_frame = self.game_state.get("frame", 0)
        x, y, facing = position
        node_id = (map_name, x, y)
        
        # Create journal entry
        entry = {
            "frame": current_frame,
            "position": position,
            "map": map_name
        }
        self.movement_history.append(entry)
        self.journal.append({
            "type": "movement",
            "frame": current_frame,
            "data": entry
        })
        
        # Update graph - add or update node for current position
        if not self.world_graph.has_node(node_id):
            self.world_graph.add_node(node_id, 
                                      map=map_name,
                                      visited=True)
        else:
            # Mark as visited
            self.world_graph.nodes[node_id]['visited'] = True
        
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
                    self.world_graph.add_edge(prev_node, node_id)
            else:
                # Different maps - create edge regardless of position
                # This represents doors, cave entrances, etc.
                self.world_graph.add_edge(prev_node, node_id)
        
        # Update surrounding tiles based on viewport data
        if 'viewport' in self.game_state and 'tiles' in self.game_state['viewport']:
            tiles = self.game_state['viewport']['tiles']
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
                                                     visited=(map_x==x and map_y==y))
                        else:
                            # Existing node - update tile code
                            self.world_graph.nodes[tile_node]['tile_code'] = tile_code
                            
                            # Only update visited status if we're standing on it and it wasn't visited before
                            if map_x==x and map_y==y and not self.world_graph.nodes[tile_node].get('visited', False):
                                self.world_graph.nodes[tile_node]['visited'] = True
        
        logger.debug(f"Recorded movement: {position}")
        
    def record_dialog(self, dialog_text):
        """
        Record dialog text with intelligent handling of continuations.
        Only records in stable states and combines related dialog entries.
        """
        if not dialog_text or not self.stable_state:
            return
            
        current_frame = self.game_state.get("frame", 0)
        
        # Skip exact duplicates
        if self.dialog_history and self.dialog_history[-1]["text"] == dialog_text:
            return
        
        # Check for continuations if we have previous dialog
        if self.dialog_history:
            last_entry = self.dialog_history[-1]
            prev_dialog = last_entry["text"]
            
            # Two main continuation cases:
            # 1. Scrolling text - some overlap between prev and current
            # 2. Sentence continuation - prev doesn't end with punctuation
            
            # Check for overlap
            prev_lines_set = set(prev_dialog)
            current_lines_set = set(dialog_text)
            
            is_continuation = False
            
            # Case 1: Direct overlap in lines
            if prev_lines_set.intersection(current_lines_set):
                is_continuation = True
            
            # Case 2: Previous dialog doesn't end with sentence-ending punctuation
            elif prev_dialog and prev_dialog[-1] and not prev_dialog[-1].endswith((".", "!", "?")):
                is_continuation = True
                
            if is_continuation:
                # Combine entries by taking all lines from both
                # but avoiding duplicates
                combined_lines = prev_dialog.copy()
                
                # Add new lines that aren't in the previous dialog
                for line in dialog_text:
                    if line not in prev_lines_set:
                        combined_lines.append(line)
                
                # Update the previous entry with combined content
                last_entry["text"] = combined_lines
                last_entry["frame"] = current_frame
                
                # Update journal entry
                for i in range(len(self.journal) - 1, -1, -1):
                    if (self.journal[i]["type"] == "dialog" and 
                        self.journal[i]["data"] == prev_dialog):
                        self.journal[i]["data"] = combined_lines
                        self.journal[i]["frame"] = current_frame
                        break
                
                # Update location dialog
                self._update_location_dialog(prev_dialog, combined_lines, current_frame)
                
                return
        
        # If we get here, this is a completely new dialog
        entry = {
            "frame": current_frame,
            "text": dialog_text
        }
        self.dialog_history.append(entry)
        self.journal.append({
            "type": "dialog",
            "frame": current_frame,
            "data": dialog_text
        })
        
        # Associate with location
        if self.movement_history:
            latest_position = self.movement_history[-1]
            map_name = latest_position["map"]
            x, y, _ = latest_position["position"]
            node_id = (map_name, x, y)
            
            if self.world_graph.has_node(node_id):
                if 'dialogs' not in self.world_graph.nodes[node_id]:
                    self.world_graph.nodes[node_id]['dialogs'] = []
                
                self.world_graph.nodes[node_id]['dialogs'].append({
                    'frame': current_frame,
                    'text': dialog_text
                })

    def _update_location_dialog(self, old_text, new_text, current_frame):
        """Helper to update dialog at current location in the graph"""
        if not self.movement_history:
            return
            
        latest_position = self.movement_history[-1]
        map_name = latest_position["map"]
        x, y, _ = latest_position["position"]
        node_id = (map_name, x, y)
        
        if (self.world_graph.has_node(node_id) and 
            'dialogs' in self.world_graph.nodes[node_id]):
            
            for dialog in self.world_graph.nodes[node_id]['dialogs']:
                if dialog['text'] == old_text:
                    dialog['text'] = new_text
                    dialog['frame'] = current_frame
                    return
    def record_menu(self, menu_state):
        """Record menu interaction"""
        current_frame = self.game_state.get("frame", 0)
        
        # Skip if menu state hasn't changed
        if self.menu_history and self.menu_history[-1]["menu_state"] == menu_state:
            return
            
        entry = {
            "frame": current_frame,
            "menu_state": menu_state
        }
        self.menu_history.append(entry)
        self.journal.append({
            "type": "menu",
            "frame": current_frame,
            "data": menu_state
        })
        logger.debug(f"Recorded menu state: {menu_state}")
    
    def record_action(self, action):
        """Record action taken"""
        current_frame = self.game_state.get("frame", 0)
        
        entry = {
            "frame": current_frame,
            "action": action,
            "state": self.current_state_type
        }
        self.action_history.append(entry)
        self.journal.append({
            "type": "action",
            "frame": current_frame,
            "data": {
                "button": action,
                "state": self.current_state_type
            }
        })
        logger.debug(f"Recorded action: {action}")
    
    def get_recent_journal(self, entries=10):
        """Get the N most recent journal entries"""
        return self.journal[-entries:] if self.journal else []
    
    def is_input_ready(self):
        """Check if we're ready to accept new input"""
        if not self.stable_state:
            return False
            
        # Check if we're still in cooldown from previous button press
        current_frame = self.game_state.get("frame", 0)
        frames_since_input = current_frame - self.last_button_frame
        
        # Default cooldown is 24 frames
        return frames_since_input >= 24


# Decision Maker class for determining actions
class DecisionMaker:
    """Responsible for deciding which action to take based on game state"""
    
    def __init__(self, blackboard, interactive=False):
        self.blackboard = blackboard
        self.interactive = interactive
        self.interface = InteractiveMode() if interactive else None
    
    async def decide_action(self):
        """Decide what button to press based on the current state"""
        state_type = self.blackboard.current_state_type
        
        # Determine if we should use interactive mode
        if self.interactive:
            # Use interactive mode
            if state_type == "menu":
                return await self.interface.get_menu_action(self.blackboard)
            elif state_type == "default":
                return await self.interface.get_default_action(self.blackboard)
            elif state_type == "dialog":
                # For dialog, we always auto-advance
                return "a"
            elif state_type == "scripted":
                # Scripted state should just observe
                return None
        else:
            # Use automatic mode
            if state_type == "dialog":
                # For dialog, always press A to advance
                return "a"
            elif state_type == "menu":
                # For menu, always press A to select
                return "a"
            elif state_type == "default":
                # For default state, choose a random direction or A
                return random.choice(["up", "down", "left", "right", "a"])
            elif state_type == "scripted":
                # Scripted state should just observe
                return None
        
        return None

# Main client class
class PokemonAIClient:
    """Client that connects to the plugin-server and focuses on stable state points"""
    
    def __init__(self, host='localhost', port=8765, interactive=False):
        self.host = host
        self.port = port
        self.ws = None
        self.blackboard = None
        self.decision_maker = None
        self.interactive = interactive
        
    async def connect(self):
        """Connect to the WebSocket server"""
        uri = f"ws://{self.host}:{self.port}"
        logger.info(f"Connecting to {uri}")
        
        try:
            self.ws = await websockets.connect(uri)
            self.blackboard = Blackboard(self.ws)
            self.decision_maker = DecisionMaker(self.blackboard, self.interactive)
            
            logger.info("Connected to server")
            return True
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            return False

    async def run(self):
        """Main client loop focusing on stable state points"""
        if not self.ws:
            if not await self.connect():
                return
                
        try:
            # Main loop
            while True:
                # 1. Wait for and find a stable state
                await self.wait_for_stable_state()
                
                # 2. Once stable, make a decision
                button = await self.decision_maker.decide_action()
                
                if button:
                    # 3. Execute the decision
                    await self.blackboard.send_input(button)
                    
                    # 4. After sending input, reset stability tracking (handled in send_input)
                    # 5. Wait a moment to ensure action starts processing
                    await asyncio.sleep(0.1)
                else:
                    # If no decision was made, wait a bit before checking again
                    await asyncio.sleep(0.5)
                
        except websockets.exceptions.ConnectionClosed:
            logger.warning("Connection closed by server")
        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
        finally:
            if self.ws:
                await self.ws.close()
                # Print summary information
                logger.info(f"Total actions: {len(self.blackboard.action_history)}")
                logger.info(f"Total dialog entries: {len(self.blackboard.dialog_history)}")
                logger.info(f"Total movement entries: {len(self.blackboard.movement_history)}")
                logger.info(f"Total menu interactions: {len(self.blackboard.menu_history)}")
                logger.info("Connection closed")
    
    async def wait_for_stable_state(self):
        """Wait until the game state is stable before proceeding"""
        # Reset stability if it was previously stable
        if self.blackboard.stable_state:
            self.blackboard.stability_counter = 0
            self.blackboard.stable_state = False
            
        # Keep receiving states until we find stability
        while not self.blackboard.stable_state:
            try:
                # Set a timeout to avoid hanging indefinitely
                message = await asyncio.wait_for(self.ws.recv(), timeout=5.0)
                data = json.loads(message)
                
                if "type" in data and data["type"] == "state_update":
                    # Update the blackboard with the new state
                    self.blackboard.update_game_state(data["state"])
                    
                # Small yield to prevent CPU hogging
                await asyncio.sleep(0.01)
                
            except asyncio.TimeoutError:
                logger.warning("Timeout while waiting for stable state")
                # If we timeout, assume we can proceed anyway
                break
            except Exception as e:
                logger.error(f"Error while waiting for stable state: {e}")
                # If there's an error, wait a bit before retrying
                await asyncio.sleep(1.0)



# Main entry point
async def main():
    parser = argparse.ArgumentParser(description="Pokémon AI Client")
    parser.add_argument("--host", type=str, default="localhost", help="WebSocket server host")
    parser.add_argument("--port", type=int, default=8765, help="WebSocket server port")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--interactive", action="store_true", help="Enable interactive mode")

    args = parser.parse_args()
    
    if args.debug:
        logger.setLevel(logging.DEBUG)
    
    client = PokemonAIClient(args.host, args.port, args.interactive)
    await client.run()

if __name__ == "__main__":
    asyncio.run(main())