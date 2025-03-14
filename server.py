#!/usr/bin/env python3
"""
Enhanced Pokémon Server with GameStateManager

An HTTP server that manages the Pokémon game state, detects stable states,
and provides a REST API for clients to query state and provide input.
"""

import asyncio
import json
import argparse
import platform
import threading
import time
import signal
import os
import sys
import queue
import networkx as nx
from aiohttp import web
from pyboy import PyBoy
from wrapper import EnhancedPokemonWrapper
from game_state_manager import GameStateManager

def keep_screen(no_clear):
    """Clear the terminal screen in a cross-platform way"""
    if no_clear:
        print("\n" + "=" * 80 + "\n")
        return
    else:
        # Windows
        if platform.system() == "Windows":
            os.system('cls')
        # macOS and Linux (UNIX-like)
        else:
            os.system('clear')

class HttpGameServer:
    """HTTP server for game state and input handling with REST API"""
    
    def __init__(self, enhanced_wrapper, game_state_manager, host='0.0.0.0', port=8765):
        self.wrapper = enhanced_wrapper
        self.state_manager = game_state_manager
        self.host = host
        self.port = port
        self.http_server = None
        self.server_thread = None
        self.stop_event = threading.Event()
        
        # Input handling
        self.input_buttons = queue.Queue()
        
        # State tracking for client information
        self.current_state_info = {
            "stable": False,
            "state_type": "unknown"
        }
    
    def start(self):
        """Start HTTP server in a separate thread"""
        self.server_thread = threading.Thread(target=self._run_server)
        self.server_thread.daemon = True
        self.server_thread.start()
    
    def _run_server(self):
        """Run the HTTP server in its own thread and event loop"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        app = web.Application()
        app.router.add_get('/state', self._handle_state)
        app.router.add_post('/input', self._handle_input)
        app.router.add_get('/journal', self._handle_journal)
        
        runner = web.AppRunner(app)
        loop.run_until_complete(runner.setup())
        site = web.TCPSite(runner, self.host, self.port)
        loop.run_until_complete(site.start())
        
        print(f"HTTP game server started at http://{self.host}:{self.port}")
        
        try:
            loop.run_until_complete(self._wait_for_stop())
        finally:
            loop.run_until_complete(runner.cleanup())
            loop.close()
            print("HTTP server stopped")
    
    async def _wait_for_stop(self):
        """Wait for the stop event to be set"""
        while not self.stop_event.is_set():
            await asyncio.sleep(0.1)
    
    async def _handle_state(self, request):
        """Handle request for current game state"""
        return web.json_response({
            "state": self.wrapper.data,
            "stable": self.current_state_info["stable"],
            "current_state_type": self.current_state_info["state_type"],
            "frame": self.wrapper.data.get("frame", 0)
        })
    
    async def _handle_input(self, request):
        """Handle input submission"""
        try:
            data = await request.json()
            button = data.get("button")
            
            if button in ["up", "down", "left", "right", "a", "b", "start", "select"]:
                self.input_buttons.put(button)
                return web.json_response({
                    "status": "success", 
                    "button": button
                })
            else:
                return web.json_response({"status": "error", "message": "Invalid button"}, status=400)
        except Exception as e:
            return web.json_response({"status": "error", "message": str(e)}, status=400)
    
    async def _handle_journal(self, request):
        """Handle request for journal entries"""
        since_frame = int(request.query.get("since_frame", 0))
        count = int(request.query.get("count", 50))
        entry_type = request.query.get("type")
        
        # Get journal entries
        if since_frame > 0:
            entries = self.state_manager.get_entries_since_frame(since_frame, entry_type)
        elif entry_type:
            entries = self.state_manager.get_entries_by_type(entry_type, count)
        else:
            entries = self.state_manager.journal[-count:]
        
        return web.json_response({
            "entries": entries
        })
    
    async def _handle_world_atlas(self):
        """Handle request for world atlas data (map information)"""
        try:
            # Get visited maps from state manager
            visited_maps = self.state_manager.get_visited_maps()
            
            # Get current position
            current_map = None
            current_position = None
            recent_movements = self.state_manager.get_entries_by_type("movement", 1)
            
            if recent_movements:
                current_map = recent_movements[0]["data"]["map"]
                current_position = recent_movements[0]["data"]["position"]
            
            # Get distances to all maps
            map_distances = {}
            if current_map and current_position:
                x, y, _ = current_position
                map_distances = self.state_manager.world_graph.get_map_distances((current_map, x, y))
            
            return web.json_response({
                "visited_maps": visited_maps,
                "current_map": current_map,
                "current_position": current_position,
                "map_distances": map_distances
            })
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)

    async def _handle_path_finding(self, request):
        """Handle request for path finding"""
        try:
            # Get destination map
            dest_map = request.query.get("map")
            if not dest_map:
                return web.json_response({"error": "Destination map is required"}, status=400)
            
            # Get optional coordinates
            dest_x = request.query.get("x")
            dest_y = request.query.get("y")
            has_coords = dest_x is not None and dest_y is not None
            
            # Get current position
            recent_movements = self.state_manager.get_entries_by_type("movement", 1)
            if not recent_movements:
                return web.json_response({"error": "Cannot determine current position"}, status=400)
            
            current_map = recent_movements[0]["data"]["map"]
            current_pos = recent_movements[0]["data"]["position"]
            current_x, current_y, _ = current_pos
            
            # Find path
            if has_coords:
                # Path to specific coordinates
                try:
                    dest_x = int(dest_x)
                    dest_y = int(dest_y)
                except ValueError:
                    return web.json_response({"error": "Invalid coordinates"}, status=400)
                    
                path = self.state_manager.world_graph.find_path(
                    (current_map, current_x, current_y),
                    (dest_map, dest_x, dest_y)
                )
            else:
                # Path to any point in the destination map
                path = self.state_manager.world_graph.find_path_to_map(
                    (current_map, current_x, current_y),
                    dest_map
                )
            
            if not path:
                return web.json_response({
                    "error": f"No path found to {dest_map}" + 
                            (f" ({dest_x}, {dest_y})" if has_coords else "")
                }, status=404)
            
            # Convert path to a list of positions and directions
            positions = []
            directions = []
            
            for i in range(len(path)):
                map_name, x, y = path[i]
                positions.append({"map": map_name, "x": x, "y": y})
                
                # Calculate direction for each step except the last
                if i < len(path) - 1:
                    from_pos = path[i]
                    to_pos = path[i + 1]
                    from_map, from_x, from_y = from_pos
                    to_map, to_x, to_y = to_pos
                    
                    if from_map != to_map:
                        # This is a map transition
                        directions.append("transition")
                    else:
                        # Regular movement
                        dx, dy = to_x - from_x, to_y - from_y
                        if dx == 1 and dy == 0:
                            directions.append("right")
                        elif dx == -1 and dy == 0:
                            directions.append("left")
                        elif dx == 0 and dy == 1:
                            directions.append("down")
                        elif dx == 0 and dy == -1:
                            directions.append("up")
                        else:
                            directions.append("unknown")
            
            return web.json_response({
                "path": positions,
                "directions": directions,
                "length": len(path) - 1
            })
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)
    
    def update_state_info(self, stable, state_type):
        """Update the current state information for clients"""
        self.current_state_info = {
            "stable": stable,
            "state_type": state_type
        }
    
    def get_next_button(self):
        """Get next button from input queue if available"""
        try:
            return self.input_buttons.get_nowait()
        except queue.Empty:
            return None
    
    def stop(self):
        """Signal the server to stop"""
        self.stop_event.set()
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=1.0)

def load_memory_addresses(file_path):
    """Load memory addresses from a JSON file and convert hex strings to integers"""
    try:
        with open(file_path, 'r') as f:
            memory_addresses = json.load(f)
            
            # Convert hex strings to integers
            for key, value in memory_addresses.items():
                if isinstance(value, str) and value.startswith("0x"):
                    memory_addresses[key] = int(value, 16)
            
            return memory_addresses
    
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error loading memory addresses: {e}")
        print("Using default memory addresses")
        # Return empty dict to signal failure
        return {}

def load_memory_values(file_path):
    """Load memory values from a JSON file"""
    try:
        with open(file_path, 'r') as f:
            maps = json.load(f)

            moves = {}
            # Convert hex strings to integers
            for key, value in maps.get('moves', {}).items():
                moves[int(key)] = value
            maps["moves"] = moves
            return maps
    
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error loading memory values: {e}")
        print("Using default memory values")
        # Return empty dict to signal failure
        return {}

def run_game(rom_path, memory_addresses_path, memory_values_path, stop_event, args):
    """Run the game continuously while tracking state and responding to inputs"""
    # Load memory addresses and value maps
    memory_addresses = load_memory_addresses(memory_addresses_path)
    value_maps = load_memory_values(memory_values_path)
    if not memory_addresses:
        print("Critical error: Could not load memory addresses!")
        return
    if not value_maps:
        print("Critical error: Could not load value maps!")
        return
    
    # Initialize PyBoy
    print(f"Initializing PyBoy with ROM: {rom_path}")
    pyboy = PyBoy(rom_path, sound_emulated=False)
    
    try:
        # Check if we have a Pokemon game
        if not (pyboy.cartridge_title == "POKEMON RED" or pyboy.cartridge_title == "POKEMON BLUE"):
            print("Error: This server only works with Pokemon Red/Blue ROMs")
            pyboy.stop()
            return
        
        # Create enhanced wrapper with loaded memory addresses
        enhanced_wrapper = EnhancedPokemonWrapper(pyboy, memory_addresses, value_maps)
        print(f"Pokemon wrapper successfully loaded! ({pyboy.game_wrapper.__class__.__name__} - Enhanced)")
        
        # Create GameStateManager (just for tracking, not for pausing)
        game_state_manager = GameStateManager(pyboy, enhanced_wrapper)
        
        # Create and start HTTP server
        http_server = HttpGameServer(enhanced_wrapper, game_state_manager, args.host, args.port)
        http_server.start()
        
        # Run initial frames to get past intro screens
        print("Running initial frames...")
        for _ in range(180):
            pyboy.tick()
        
        # Main game loop with continuous execution
        print("Entering main game loop...")
        frame_count = 0
        last_dialog_frame = 0
        
        while not stop_event.is_set() and not should_exit:
            # Process a frame
            pyboy.tick()
            frame_count += 1
            
            # Update wrapper with new game state
            enhanced_wrapper.update(frame_count)
            
            # Update GameStateManager (for tracking only)
            game_state_manager.update(frame_count)
            
            # Auto-handle dialog if in a stable dialog state
            # Add some spacing between auto-dialog presses
            if (game_state_manager.stable_state and 
                game_state_manager.current_state_type == "dialog" and
                frame_count - last_dialog_frame > 30):
                
                # Auto-advance dialog
                print(f"Auto-pressing A for dialog at frame {frame_count}")
                pyboy.button("a", 10)
                enhanced_wrapper.record_button_input("a")
                game_state_manager.process_button("a", frame_count)
                last_dialog_frame = frame_count
            
            # Check for input from clients (process immediately)
            button = http_server.get_next_button()
            if button:
                print(f"Processing button input: {button} at frame {frame_count}")
                pyboy.button(button, 14)  # 14-frame button press
                enhanced_wrapper.record_button_input(button)
                game_state_manager.process_button(button, frame_count)
            
            # Display game state periodically
            if frame_count % 24 == 0:
                keep_screen(args.no_clear)
                print(enhanced_wrapper)
                
                # Update HTTP server with current state info
                stable = game_state_manager.stable_state
                state_type = game_state_manager.current_state_type
                http_server.update_state_info(stable, state_type)

    
    finally:
        # Clean up resources
        if pyboy:
            pyboy.stop()
            print("PyBoy stopped")
        
        # Stop HTTP server
        http_server.stop()

def signal_handler(sig, frame):
    """Handle Ctrl+C signal"""
    print("\nReceived signal to terminate. Shutting down...")
    global should_exit
    should_exit = True
    
    # Try to exit gracefully after a short delay
    def force_exit():
        print("Forcing exit...")
        os._exit(0)
    
    # Schedule a forced exit after 3 seconds if graceful shutdown fails
    threading.Timer(3.0, force_exit).start()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enhanced Pokemon Gen1 Server with GameStateManager")
    parser.add_argument("--rom", type=str, required=True, help="Path to Pokemon Red/Blue ROM file")
    parser.add_argument("--memory-addresses", type=str, default="memory_map.json", 
                        help="Path to memory addresses JSON file")
    parser.add_argument("--values-path", type=str, default="value_maps.json", 
                        help="Path to value maps JSON file")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host address to bind")
    parser.add_argument("--port", type=int, default=8765, help="HTTP server port")
    parser.add_argument("--no-clear", action="store_true", help="Don't clear the terminal screen")
    
    args = parser.parse_args()
    
    # Check if ROM file exists
    if not os.path.isfile(args.rom):
        print(f"Error: ROM file '{args.rom}' was not found!")
        sys.exit(1)
    
    # Check if memory addresses file exists
    if not os.path.isfile(args.memory_addresses):
        print(f"Error: Memory addresses file '{args.memory_addresses}' was not found!")
        sys.exit(1)
    
    # Set up signal handler for clean termination
    should_exit = False
    signal.signal(signal.SIGINT, signal_handler)
    
    # Create a stop event for clean shutdown
    stop_event = threading.Event()
    
    try:
        run_game(args.rom, args.memory_addresses, args.values_path, stop_event, args)
    except KeyboardInterrupt:
        print("KeyboardInterrupt received in main thread")
    except Exception as e:
        print(f"Error in game loop: {e}")
    finally:
        # Signal threads to stop
        print("Shutting down...")
        stop_event.set()
        print("Server shut down completed")
        
        # Force exit if we're still running
        os._exit(0)