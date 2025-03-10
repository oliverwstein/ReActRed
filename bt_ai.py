#!/usr/bin/env python3
"""
Pokémon AI Client

Usage:
    python pokemon_ai.py [--host HOST] [--port PORT]
"""

import asyncio
import json
import argparse
import logging
import time
import random
import websockets
from enum import Enum
from abc import ABC, abstractmethod
from collections import deque
import networkx as nx
from interface import InteractiveMode

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger("PokemonAI")

# Behavior Tree Status Enum
class Status(Enum):
    SUCCESS = 1
    FAILURE = 2
    RUNNING = 3

class Node(ABC):
    """Base class for behavior tree nodes"""
    
    def __init__(self, name):
        self.name = name
        self.status = Status.FAILURE
        
    @abstractmethod
    async def run(self):
        """Run the node's behavior and return a Status"""
        pass
    
class Composite(Node):
    """Base class for composite nodes that have children"""
    
    def __init__(self, name, children=None):
        super().__init__(name)
        self.children = children or []
        
    def add_child(self, child):
        self.children.append(child)
        return self

class Selector(Composite):
    """Selector (OR) node - succeeds if any child succeeds, runs until first success"""
    
    async def run(self):
        for child in self.children:
            child_status = await child.run()
            if child_status != Status.FAILURE:
                self.status = child_status
                return self.status
        
        self.status = Status.FAILURE
        return self.status

class Sequence(Composite):
    """Sequence (AND) node - succeeds if all children succeed, fails on first failure"""
    
    async def run(self):
        for child in self.children:
            child_status = await child.run()
            if child_status != Status.SUCCESS:
                self.status = child_status
                return self.status
        
        self.status = Status.SUCCESS
        return self.status

# Action Node for button presses
class PressButton(Node):
    """Presses a button on the Game Boy with frame-based delay"""
    
    def __init__(self, name, button, wait_frames=24, blackboard=None):
        super().__init__(name)
        self.button = button
        self.wait_frames = wait_frames
        self.pressed = False
        self.start_frame = None
        self.blackboard = blackboard
        
    async def run(self):
        current_frame = self.blackboard.game_state.get("frame", 0)
        
        # If we haven't pressed the button yet, do so
        if not self.pressed:
            # logger.info(f"Pressing button: {self.button}")
            await self.blackboard.ws.send(json.dumps({"button": self.button}))
            self.pressed = True
            self.start_frame = current_frame
            
            # Record this action in the journal
            self.blackboard.record_action(self.button)
            
            self.status = Status.RUNNING
            return self.status
        
        # Wait for the specified number of frames
        if current_frame - self.start_frame >= self.wait_frames:
            logger.debug(f"Button {self.button} press complete after {current_frame - self.start_frame} frames")
            self.pressed = False
            self.start_frame = None
            self.status = Status.SUCCESS
            return self.status
        
        # Still waiting for frames to pass
        self.status = Status.RUNNING
        return self.status

# Basic State Handlers
class StateHandler(Node):
    """Base class for state-specific handlers"""
    
    def __init__(self, name, required_state, blackboard=None):
        super().__init__(name)
        self.required_state = required_state
        self.entered_state_frame = None
        self.last_state_data = None
        self.stable_state_data = None
        self.stability_counter = 0
        self.input_ready = False
        self.blackboard = blackboard
        
    async def check_state(self):
        """Check if current game state matches the required state for this handler"""
        current_state = self.blackboard.game_state.get("state", "unknown")
        current_frame = self.blackboard.game_state.get("frame", 0)
        
        # Check if this is the current state
        if current_state != self.required_state:
            # Reset state tracking if we've exited the state
            self.entered_state_frame = None
            self.last_state_data = None
            self.stable_state_data = None
            self.stability_counter = 0
            self.input_ready = False
            return False
            
        # If we just entered this state, record the frame
        if self.entered_state_frame is None:
            self.entered_state_frame = current_frame
            logger.info(f"Entered {self.required_state} state at frame {current_frame}")
            
        return True
    
    async def run(self):
        """Main execution method for the state handler"""
        # First check if we're in the correct state
        if not await self.check_state():
            self.status = Status.FAILURE
            return self.status
        
        # Check if we can input (respecting global cooldown)
        current_frame = self.blackboard.game_state.get("frame", 0)
        if not self.blackboard.can_input(current_frame):
            self.status = Status.RUNNING
            return self.status
        
        # Process the current state data and prepare for action
        state_ready = await self.process_state()
        
        # If ready, take action
        if state_ready:
            action_status = await self.act()
            self.status = action_status
            return self.status
        
        # State processing not complete, keep running
        self.status = Status.RUNNING
        return self.status
    
    @abstractmethod
    async def process_state(self):
        """
        Process the current state data to determine if action is possible.
        Returns True if the state is ready for action, False otherwise.
        """
        pass
    
    @abstractmethod
    async def act(self):
        """
        Take action based on the current state.
        Returns a Status value indicating success, failure, or running.
        """
        pass

class DialogStateHandler(StateHandler):
    """
    Handles the dialog game state - intelligently waits for dialog to fully render
    before pressing A to advance
    """
    
    def __init__(self, blackboard=None):
        super().__init__("DialogStateHandler", "dialog", blackboard)
        self.wait_frames = 24
        self.dialog_history = []  # Store recent dialog
        self.previous_dialog_length = 0  # Track the previous dialog length
        self.last_dialog_change_frame = 0  # Track when dialog last changed
        self.consecutive_stable_frames = 0  # Count frames with no dialog changes
        
    async def process_state(self):
        current_frame = self.blackboard.game_state.get("frame", 0)
        dialog_text = self.blackboard.game_state.get("text", {}).get("dialog", [])
        
        # Get the current dialog text and join for easier comparison
        current_dialog = tuple(dialog_text)  # Convert to tuple for comparison
        
        # Check for different conditions that indicate dialog is changing
        dialog_changing = False
        
        # Check if current dialog is different from the last recorded state
        if self.last_state_data != current_dialog:
            # Dialog content has changed
            dialog_changing = True
        # Check if dialog is still being rendered character-by-character
        elif len(dialog_text) > 0:
            # Check for dialog that's still being drawn character-by-character
            # This checks if we have the same number of lines but the content length is growing
            current_total_length = sum(len(line) for line in dialog_text)
            if current_total_length > self.previous_dialog_length:
                dialog_changing = True
                logger.debug(f"Dialog still rendering: {current_total_length} chars (was {self.previous_dialog_length})")
                self.previous_dialog_length = current_total_length
        
        # Update our state based on whether dialog is changing
        if dialog_changing:
            # Dialog is still changing, reset stability counter
            self.consecutive_stable_frames = 0
            self.last_dialog_change_frame = current_frame
            self.last_state_data = current_dialog
            self.input_ready = False
        else:
            # Dialog is stable for this frame, increment counter
            self.consecutive_stable_frames += 1
            
            # If dialog has been stable for enough frames, it's fully rendered
            required_stable_frames = 8  # Wait for 8 frames of stability to ensure complete rendering
            if self.consecutive_stable_frames >= required_stable_frames and not self.input_ready:
                logger.info(f"Dialog fully rendered after {self.consecutive_stable_frames} stable frames")
                self.input_ready = True
                self.stable_state_data = current_dialog
                
                # Make sure we've recorded this dialog
                self.blackboard.record_dialog(dialog_text)
        
        return self.input_ready
    
    async def act(self):
        logger.info(f"Dialog input ready - pressing A to advance")
        
        # Reset the dialog length tracking for the next dialog segment
        self.previous_dialog_length = 0
        
        # Create and run the button press node
        button_node = PressButton("Dialog_A_Press", "a", self.wait_frames, self.blackboard)
        await button_node.run()
        
        # Reset state tracking
        self.input_ready = False
        self.consecutive_stable_frames = 0
        
        return Status.SUCCESS

class MenuStateHandler(StateHandler):
    """Handles the menu game state - waits a short delay before pressing A"""
    
    def __init__(self, blackboard=None):
        super().__init__("MenuStateHandler", "menu", blackboard)
        self.wait_frames = 24
        self.menu_delay_frames = 6  # Short delay for menu processing
        self.button_node = None  # Store button node reference
        
    async def process_state(self):
        # If we have an active button press, check its status
        if self.button_node is not None:
            button_status = await self.button_node.run()
            
            # If button press is still running, report that we're busy
            if button_status == Status.RUNNING:
                return False
            
            # If button press is complete, clear it and reset state
            if button_status == Status.SUCCESS:
                self.button_node = None
                self.input_ready = False
                self.stability_counter = 0
                return False
        
        # Get the current menu state
        menu_state = self.blackboard.game_state.get("text", {}).get("menu_state", {})
        current_menu = (
            menu_state.get("current_item", -1),
            menu_state.get("cursor_text", "")
        )
        
        # Check if menu has changed
        if self.last_state_data != current_menu:
            # Menu has changed, update and reset stability counter
            logger.debug(f"Menu changed: {current_menu}")
            self.last_state_data = current_menu
            self.stability_counter = 0
            self.input_ready = False
            
            # Record the menu state
            self.blackboard.record_menu(menu_state)
        else:
            # Menu has remained the same for at least one frame
            self.stability_counter += 1
            
            # If stable for enough frames, mark input as ready
            if self.stability_counter >= self.menu_delay_frames and not self.input_ready:
                logger.info(f"Menu stabilized after {self.stability_counter} frames")
                self.input_ready = True
                self.stable_state_data = current_menu
        
        return self.input_ready
    
    async def act(self):
        if self.blackboard.interactive_mode:
            # Get action from interactive handler
            button = await self.blackboard.interactive_handler.get_menu_action()
            logger.info(f"Menu input ready - pressing {button}")
            
            # Create and store the button press node
            self.button_node = PressButton(f"Menu_{button}_Press", button, self.wait_frames, self.blackboard)
            # Initial run of the button node
            await self.button_node.run()
            
        else:
            # Default behavior - always press A
            logger.info(f"Menu input ready - pressing A")
            self.button_node = PressButton("Menu_A_Press", "a", self.wait_frames, self.blackboard)
            await self.button_node.run()
        
        # We're now busy with a button press
        self.input_ready = False
        
        # Return RUNNING status to indicate we need more time
        return Status.RUNNING
    
class ScriptedStateHandler(StateHandler):
    """
    Handles the scripted game state - observes and records data but doesn't provide input
    """
    
    def __init__(self, blackboard=None):
        super().__init__("ScriptedStateHandler", "scripted", blackboard)
        self.observation_interval = 30  # Check every 30 frames
        self.last_check_frame = 0
        self.last_position = None
        
    async def process_state(self):
        current_frame = self.blackboard.game_state.get("frame", 0)
        
        # Only check periodically to avoid excessive logging
        if current_frame - self.last_check_frame < self.observation_interval:
            return False
            
        self.last_check_frame = current_frame
        
        # Get current player position
        current_position = self.blackboard.game_state.get("player", {}).get("position", (0, 0, "Unknown"))
        
        # Check if position has changed since last check
        if self.last_position != current_position:
            logger.info(f"Player position changed in scripted state: {current_position}")
            self.blackboard.record_movement(current_position)
            self.last_position = current_position
        
        # Check for dialog in scripted state
        dialog_text = self.blackboard.game_state.get("text", {}).get("dialog", [])
        if dialog_text:
            self.blackboard.record_dialog(dialog_text)
        
        # Ready to act (observe)
        return True
    
    async def act(self):
        # Just observe, don't provide input in scripted state
        current_frame = self.blackboard.game_state.get("frame", 0)
        logger.info(f"In scripted state - observing at frame {current_frame}")
        return Status.SUCCESS

class DefaultStateHandler(StateHandler):
    """
    Handles the default (overworld) game state - waits to ensure it's a stable state,
    then takes action
    """
    
    def __init__(self, blackboard=None):
        super().__init__("DefaultStateHandler", "default", blackboard)
        self.wait_frames = 24
        self.min_default_duration = 180  # Wait to ensure it's truly the overworld
        self.continuous_default_frames = 0  # Track continuous frames in default state
        self.button_node = None  # Store button node reference
        
    async def check_state(self):
        """Override the check_state method to track continuous frames"""
        current_state = self.blackboard.game_state.get("state", "unknown")
        current_frame = self.blackboard.game_state.get("frame", 0)
        
        # Check if this is the current state
        if current_state != self.required_state:
            # Reset state tracking if we've exited the state
            self.entered_state_frame = None
            self.last_state_data = None
            self.stable_state_data = None
            self.stability_counter = 0
            self.input_ready = False
            self.continuous_default_frames = 0  # Reset the counter when we exit default state
            self.button_node = None  # Clear any button node
            return False
            
        # If we just entered this state, record the frame
        if self.entered_state_frame is None:
            self.entered_state_frame = current_frame
            self.continuous_default_frames = 0  # Start counting from zero
            logger.info(f"Entered {self.required_state} state at frame {current_frame}")
        
        # Increment our counter of continuous frames in default state
        self.continuous_default_frames += 1
            
        return True
        
    async def process_state(self):
        # If we have an active button press, check its status
        if self.button_node is not None:
            button_status = await self.button_node.run()
            
            # If button press is still running, report that we're busy
            if button_status == Status.RUNNING:
                return False
            
            # If button press is complete, clear it and reset state
            if button_status == Status.SUCCESS:
                self.button_node = None
                self.input_ready = False
                return False
        
        # Check how long we've been continuously in default state
        # This uses our counter instead of frame difference
        if self.continuous_default_frames < self.min_default_duration:
            logger.debug(f"In default state for {self.continuous_default_frames} frames (waiting for {self.min_default_duration})")
            return False
        
        # Get current position and record it
        current_position = self.blackboard.game_state.get("player", {}).get("position", (0, 0, "Unknown"))
        self.blackboard.record_movement(current_position)
        
        # Record that we're ready for input in the default state
        logger.info(f"Default state stable after {self.continuous_default_frames} frames - ready for input")
        return True
    
    async def act(self):
        if self.blackboard.interactive_mode:
            # Get action from interactive handler
            button = await self.blackboard.interactive_handler.get_default_action()
            logger.info(f"Default state - pressing {button}")
            
            # Create and store the button press node
            self.button_node = PressButton(f"Default_{button}_Press", button, self.wait_frames, self.blackboard)
            # Initial run of the button node
            await self.button_node.run()
            
        else:
            # Choose a random direction or press A
            action = random.choice(["up", "down", "left", "right", "a"])
            logger.info(f"Taking default action - {action}")
            
            # Create and store the button press node
            self.button_node = PressButton(f"Default_{action}", action, self.wait_frames, self.blackboard)
            await self.button_node.run()
        
        # We're now busy with a button press
        self.input_ready = False
        
        # Return RUNNING status to indicate we need more time
        return Status.RUNNING
    
# Main Behavior Tree
class PokemonBehaviorTree(Selector):
    """Main behavior tree that handles different game states"""
    
    def __init__(self, blackboard=None):
        super().__init__("PokemonBehaviorTree")
        self.blackboard = blackboard
        
        # Add handlers for each state, in order of priority
        self.add_child(ScriptedStateHandler(blackboard))
        self.add_child(DialogStateHandler(blackboard))
        self.add_child(MenuStateHandler(blackboard))
        self.add_child(DefaultStateHandler(blackboard))

# Enhanced Blackboard for sharing data
class Blackboard:
    """Stores shared data for behavior tree nodes and records game state history"""
    
    def __init__(self, ws):
        self.ws = ws
        self.game_state = {}
        self.input_cooldown = 0  # Frames to wait before next input
        self.last_input_frame = 0  # Frame when last input was sent
        
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
        
        self.world_graph = nx.Graph()
        self.interactive_mode = False
        self.interactive_handler = None

        
    def can_input(self, current_frame):
        """Check if we can send input based on cooldown"""
        frames_elapsed = current_frame - self.last_input_frame
        return frames_elapsed >= self.input_cooldown
        
    async def send_input(self, button, wait_frames, current_frame):
        """Send input and set cooldown"""
        await self.ws.send(json.dumps({"button": button}))
        self.input_cooldown = wait_frames
        self.last_input_frame = current_frame
        
        # Record the action
        self.record_action(button)
        
        logger.info(f"Sent {button}, waiting {wait_frames} frames")
        return True
    
    def update_state_tracking(self, new_state, frame):
        """Track state transitions"""
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
                logger.info(f"Exited {self.current_state} state after {duration} frames")
            
            # Record new state entry
            self.current_state = new_state
            self.current_state_entered = frame
            logger.info(f"Entered {new_state} state at frame {frame}")
    
    def record_movement(self, position):
        """Record player movement and update the world graph"""
        current_frame = self.game_state.get("frame", 0)
        map_name = self.game_state.get("map", {}).get("name", "Unknown")
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
        """Record dialog text"""
        if not dialog_text:
            return
            
        current_frame = self.game_state.get("frame", 0)
        # Avoid duplicates by checking if the last entry is identical
        if not self.dialog_history:
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
        else:
            if self.dialog_history[-1]["text"][-1] == dialog_text[0]:
                self.dialog_history[-1]["text"].append(dialog_text[1])
            else:
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
                if self.movement_history:
                    latest_movement = self.movement_history[-1]
                    map_name = latest_movement["map"]
                    x, y, _ = latest_movement["position"]
                    node_id = (map_name, x, y)
                    
                    if self.world_graph.has_node(node_id):
                        # Add dialog as node attribute
                        if 'dialogs' not in self.world_graph.nodes[node_id]:
                            self.world_graph.nodes[node_id]['dialogs'] = []
                        
                        self.world_graph.nodes[node_id]['dialogs'].append({
                            'frame': current_frame,
                            'text': dialog_text
                        })
                # logger.info(f"Recorded dialog: {" ".join(self.dialog_history[-1]["text"])}")
        
    def record_menu(self, menu_state):
        """Record menu interaction"""
        current_frame = self.game_state.get("frame", 0)
        
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
            "state": self.current_state
        }
        self.action_history.append(entry)
        self.journal.append({
            "type": "action",
            "frame": current_frame,
            "data": {
                "button": action,
                "state": self.current_state
            }
        })
        logger.debug(f"Recorded action: {action}")
    
    def get_recent_journal(self, entries=10):
        """Get the N most recent journal entries"""
        return self.journal[-entries:] if self.journal else []

# Main client class
class PokemonAIClient:
    """Client that connects to the plugin-server and runs the behavior tree"""
    
    def __init__(self, host='localhost', port=8765, interactive=False):
        self.host = host
        self.port = port
        self.ws = None
        self.blackboard = None
        self.behavior_tree = None
        self.interactive = interactive
        self.interactive_handler = None
        
    async def connect(self):
        """Connect to the WebSocket server"""
        uri = f"ws://{self.host}:{self.port}"
        logger.info(f"Connecting to {uri}")
        
        try:
            self.ws = await websockets.connect(uri)
            self.blackboard = Blackboard(self.ws)
            self.blackboard.interactive_mode = self.interactive
            
            # Create behavior tree and interactive handler with blackboard reference
            self.behavior_tree = PokemonBehaviorTree(self.blackboard)
            if self.interactive:
                self.interactive_handler = InteractiveMode(self.blackboard)
                self.blackboard.interactive_handler = self.interactive_handler
            
            logger.info("Connected to server")
            if self.interactive_handler:
                logger.info("Interaction Handler Initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            return False
            
    async def run(self):
        """Main client loop"""
        if not self.ws:
            if not await self.connect():
                return
                
        try:
            # Main loop
            while True:
                # Receive game state update
                try:
                    message = await self.ws.recv()
                    data = json.loads(message)
                    
                    if "type" in data and data["type"] == "state_update":
                        # Store the new game state
                        self.blackboard.game_state = data["state"]
                        current_frame = self.blackboard.game_state.get('frame', 0)
                        current_state = self.blackboard.game_state.get('state', 'unknown')
                        
                        # Update state tracking
                        self.blackboard.update_state_tracking(current_state, current_frame)
                        
                        # Display cooldown status
                        if self.blackboard.input_cooldown > 0:
                            frames_elapsed = current_frame - self.blackboard.last_input_frame
                            frames_remaining = max(0, self.blackboard.input_cooldown - frames_elapsed)
                            if frames_remaining == 0:
                                logger.debug(f"Frame {current_frame}: State={current_state} - Cooldown complete")
                            else:
                                logger.debug(f"Frame {current_frame}: State={current_state} - Cooldown: {frames_remaining} frames remaining")
                        else:
                            logger.debug(f"Frame {current_frame}: State={current_state} - Ready for input")
                        
                        # Run the behavior tree
                        await self.behavior_tree.run()
                    
                except websockets.exceptions.ConnectionClosed:
                    logger.warning("Connection closed by server")
                    break
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse message: {e}")
                except Exception as e:
                    logger.error(f"Error in main loop: {e}", exc_info=True)
                
                # Sleep briefly to avoid tight loops
                await asyncio.sleep(0.05)
                
        finally:
            if self.ws:
                await self.ws.close()
                for i in range(len(self.blackboard.journal)):
                    if self.blackboard.journal[i]['type'] == 'dialog':
                        logger.info(f"Recorded dialog: {" ".join(self.blackboard.journal[i]['data'])}")
                        # print(f"{self.blackboard.journal[i]['data']}")
                    if self.blackboard.journal[i]['type'] == 'movement':
                        print(f"{self.blackboard.journal[i]['data']}")
                logger.info("Connection closed")

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