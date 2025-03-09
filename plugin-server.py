import asyncio
import json
import argparse
import platform
import threading
import base64
import websockets
from pyboy import PyBoy
import signal
import os
import sys
import time
import queue
from wrapper import EnhancedPokemonWrapper

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

class WebSocketServer:
    """Handles WebSocket connections and communication"""
    def __init__(self, enhanced_wrapper, host='0.0.0.0', port=8765):
        self.wrapper = enhanced_wrapper
        self.host = host
        self.port = port
        self.clients = set()
        self.server = None
        self.loop = None
        self.stop_event = asyncio.Event()
        self.server_thread = None
        self.command_queue = queue.Queue()
        
    def start(self):
        """Start WebSocket server in a separate thread"""
        self.server_thread = threading.Thread(target=self._run_server)
        self.server_thread.daemon = True
        self.server_thread.start()
        
    def _run_server(self):
        """Run the server in its own thread and event loop"""
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        
        server_task = self.loop.create_task(self._start_server())
        broadcast_task = self.loop.create_task(self._broadcast_state())
        stop_task = self.loop.create_task(self._wait_for_stop())
        
        try:
            self.loop.run_until_complete(asyncio.gather(
                server_task, broadcast_task, stop_task
            ))
        finally:
            self.loop.close()
            print("WebSocket server stopped")
            
    async def _start_server(self):
        """Start the WebSocket server"""
        self.server = await websockets.serve(
            self._handle_client, self.host, self.port
        )
        print(f"WebSocket server started at ws://{self.host}:{self.port}")
        
    async def _wait_for_stop(self):
        """Wait for the stop event to be set"""
        await self.stop_event.wait()
        if self.server:
            self.server.close()
            
    async def _handle_client(self, websocket):
        """Handle a client connection"""
        self.clients.add(websocket)
        client_id = id(websocket)
        print(f"Client {client_id} connected. Total clients: {len(self.clients)}")
        
        try:
            # Send initial state
            await self._send_state(websocket)
            
            # Handle incoming messages
            async for message in websocket:
                try:
                    data = json.loads(message)
                    
                    # Handle button presses
                    if "button" in data:
                        button = data["button"]
                        if button in ["up", "down", "left", "right", "a", "b", "start", "select"]:
                            # Add command to queue for main thread to process
                            # We'll use pyboy.button() with a duration, so just need button name
                            self.command_queue.put(("button", button))
                            
                except json.JSONDecodeError:
                    print(f"Invalid JSON received: {message}")
                    
        except websockets.exceptions.ConnectionClosed:
            print(f"Client {client_id} disconnected")
        finally:
            # Unregister client
            self.clients.remove(websocket)
            
    async def _broadcast_state(self):
        """Periodically broadcast game state to all clients"""
        while not self.stop_event.is_set():
            if self.clients:
                await asyncio.gather(*[
                    self._send_state(client) for client in self.clients
                ])
            await asyncio.sleep(0.1)  # Update rate
    
    def find_non_json_serializable_keys(self, dictionary):
        """
        Traverses a dictionary (including nested dictionaries) to find keys that are not JSON serializable.
        
        JSON serializable key types include: str, int, float, bool, None
        
        Args:
            dictionary (dict): The dictionary to check
            
        Returns:
            list: A list of non-JSON serializable keys found
        """
        non_serializable_keys = []
        
        def is_json_serializable_key(key):
            """Check if a key is JSON serializable"""
            return isinstance(key, (str, int, float, bool)) or key is None
        
        def traverse_dict(d, path=""):
            """Recursively traverse the dictionary"""
            for key in d:
                if not is_json_serializable_key(key):
                    non_serializable_keys.append((path, key))
                
                # If the value is a dictionary, traverse it
                if isinstance(d[key], dict):
                    new_path = f"{path}.{key}" if path else str(key)
                    traverse_dict(d[key], new_path)
        
        traverse_dict(dictionary)
        return non_serializable_keys
    

    async def _send_state(self, websocket):
        """Send current game state to a client"""
        try:
            # Create message with relevant game state from wrapper
            # The wrapper.data should already contain the state that
            # was previously in the GameState class
            message = {
                "type": "state_update",
                "state": self.wrapper.data
            }
            await websocket.send(json.dumps(message))
        except Exception as e:
            print(f"Error sending state to client: {e}")
            
    def stop(self):
        """Signal the server to stop"""
        if self.loop:
            # Create a proper coroutine to set the stop event
            async def set_stop_event():
                self.stop_event.set()
            
            try:
                # Run the coroutine in the server's event loop
                asyncio.run_coroutine_threadsafe(set_stop_event(), self.loop)
            except (TypeError, RuntimeError):
                # Fall back if loop is closed or not running
                print("Could not stop WebSocket server gracefully")
        
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(timeout=1.0)
            
    def get_command_queue(self):
        """Return the command queue to be processed by the main thread"""
        return self.command_queue

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

def run_game(rom_path, memory_addresses_path, memory_values_path, stop_event):
    """Run the game in the main thread"""
    # Load memory addresses
    memory_addresses = load_memory_addresses(memory_addresses_path)
    value_maps = load_memory_values(memory_values_path)
    if not memory_addresses:
        print("Critical error: Could not load memory addresses!")
        return
    if not value_maps:
        print("Critical error: Could not load value maps!")
        return
        
    # Initialize PyBoy with headless mode
    print(f"Initializing PyBoy with ROM: {rom_path}")
    pyboy = PyBoy(rom_path, sound_emulated=False)
    
    try:
        # Check if we have a Pokemon game
        if not (pyboy.cartridge_title == "POKEMON RED" or pyboy.cartridge_title == "POKEMON BLUE"):
            print("Error: This server only works with Pokemon Red/Blue ROMs")
            pyboy.stop()
            return
            
        # Create our enhanced wrapper with loaded memory addresses
        enhanced_wrapper = EnhancedPokemonWrapper(pyboy, memory_addresses, value_maps)
        print(f"Pokemon wrapper successfully loaded! ({pyboy.game_wrapper.__class__.__name__} - Enhanced)")
        
        # Create and start WebSocket server
        ws_server = WebSocketServer(enhanced_wrapper, args.host, args.port)
        ws_server.start()
        command_queue = ws_server.get_command_queue()
        
        # Run initial frames to get past intro screens
        print("Running initial frames...")
        for _ in range(180):
            pyboy.tick()
            
        # Main game loop
        print("Entering main game loop...")
        frame_count = 0
        
        while not stop_event.is_set() and not should_exit:
                            # Process any pending commands
            while not command_queue.empty():
                cmd_type, cmd_data = command_queue.get_nowait()
                if cmd_type == "button":
                    # Use pyboy.button with 24 frames duration for consistent button presses
                    pyboy.button(cmd_data, 24)
                    enhanced_wrapper.record_button_input(cmd_data)

            # Process a frame
            pyboy.tick()
            frame_count += 1
            
            enhanced_wrapper.update(frame_count)
            # Update game state (every 24 frames)
            if frame_count % 24 == 0:
                keep_screen(False)
                print(enhanced_wrapper)
            
    finally:
        # Clean up PyBoy instance
        if pyboy:
            pyboy.stop()
            print("PyBoy stopped")

        
        # Stop WebSocket server
        ws_server.stop()

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
    parser = argparse.ArgumentParser(description="Enhanced Pokemon Gen1 WebSocket Server")
    parser.add_argument("--rom", type=str, required=True, help="Path to Pokemon Red/Blue ROM file")
    parser.add_argument("--memory-addresses", type=str, default="memory_map.json", 
                        help="Path to memory addresses JSON file")
    parser.add_argument("--values-path", type=str, default="value_maps.json", 
                        help="Path to value maps JSON file")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host address to bind")
    parser.add_argument("--port", type=int, default=8765, help="WebSocket server port")
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
        run_game(args.rom, args.memory_addresses, args.values_path, stop_event)
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