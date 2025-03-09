# Pokemon Red/Blue Game Server

A WebSocket server for exploring, monitoring, and controlling Pokemon Red/Blue gameplay through a Python-based emulation system. This project allows programmatic interaction with Pokemon games through a well-structured API.

## Overview

This project provides a WebSocket interface to monitor and control Pokemon Red/Blue game state. It uses the PyBoy emulator as a foundation and adds enhanced wrappers that extract rich game data directly from memory. The server broadcasts game state and accepts button press commands, enabling remote play and automation.

Key features:
- Real-time game state extraction (player position, party data, map information, etc.)
- WebSocket API for controlling the game (button presses)
- Detailed memory mapping for accessing game data

## Project Structure

- `plugin-server.py`: Main server script that connects the game emulator to the WebSocket interface
- `wrapper.py`: Enhanced wrapper for extracting game data from memory
- `memory_map.json`: Memory address definitions
- `value_maps.json`: Mappings between memory values and game concepts (Pokemon species, moves, etc.)

## Requirements

- Python 3.7+
- PyBoy Emulator
- websockets
- numpy
- opencv-python
- A valid Pokemon Red/Blue ROM file (not included)

## Installation

1. Clone the repository
2. Install the required packages:
```bash
pip install pyboy websockets numpy opencv-python
```

## Usage

Start the server by running the plugin-server.py script with the path to your ROM file:

```bash
python plugin-server.py --rom path/to/pokemon_red.gb --memory-addresses memory_map.json --values-path value_maps.json
```

Command-line options:
- `--rom`: Path to Pokemon Red/Blue ROM file (required)
- `--memory-addresses`: Path to memory addresses JSON file (default: memory_map.json)
- `--values-path`: Path to value maps JSON file (default: value_maps.json)
- `--host`: Host address to bind (default: 0.0.0.0)
- `--port`: WebSocket server port (default: 8765)

## WebSocket API

### Connection

Connect to the WebSocket server at: `ws://[host]:[port]`

### Receiving Game State

The server continuously broadcasts game state as JSON with the following structure:

```json
{
  "type": "state_update",
  "state": {
    "frame": 12345,
    "state": "overworld",
    "is_in_battle": false,
    "map": {
      "name": "PalletTown",
      "tileset": {...},
      "dimensions": [20, 18],
      "warps": {...}
    },
    "player": {
      "position": [10, 12, "Down"],
      "money": 3000,
      "badges": ["Boulder Badge", "Cascade Badge"],
      "pokedex": {"owned": 25, "seen": 40},
      "bag": [...],
      "team": {...}
    },
    "viewport": {
      "tiles": [...],
      "entities": [...]
    },
    "text": {...},
    "screen": "base64-encoded-jpeg-image"
  }
}
```

### Sending Commands

Send commands as JSON objects:

```json
{"button": "a"}
```

Supported buttons: "up", "down", "left", "right", "a", "b", "start", "select"

## Enhanced Game State Tracking

The server provides rich information about the game state:

- **Map data**: Current map name, dimensions, tile types, warps to other maps
- **Player data**: Position, orientation, money, badges, Pokedex progress, items
- **Pokemon team**: Species, nicknames, levels, stats, moves, HP, status conditions
- **Battle state**: Opponent details, move information, turn counter
- **NPCs**: Entity positions, movements, and state
- **Text data**: Dialog, menu state, and text context


## Memory Mapping System

The project uses a comprehensive memory mapping system:

- `memory_map.json`: Maps memory addresses to their game functions
- `value_maps.json`: Translates memory values into meaningful game concepts

## Example Client

Here's a simple client example using Python:

```python
import asyncio
import websockets
import json

async def connect_to_game():
    uri = "ws://localhost:8765"
    async with websockets.connect(uri) as websocket:
        # Press the A button
        await websocket.send(json.dumps({"button": "a"}))
        
        # Receive game state update
        response = await websocket.recv()
        data = json.loads(response)
        print(f"Current map: {data['state']['map']['name']}")
        print(f"Player position: {data['state']['player']['position']}")

asyncio.get_event_loop().run_until_complete(connect_to_game())
```

## Extending the Project

The modular design allows for easy extension:

1. **Add new memory addresses**: Update memory_map.json with new addresses
2. **Extract more game data**: Extend the EnhancedPokemonWrapper class in wrapper.py
3. **Implement automation**: Build on top of the WebSocket API to create bots or automation tools

## License

This project is for educational purposes only. Pokemon is a registered trademark of Nintendo, Creatures Inc., and GAME FREAK inc.

## Acknowledgments

- The PyBoy project for providing the Game Boy emulation
- Pokemon disassembly projects for memory mapping information