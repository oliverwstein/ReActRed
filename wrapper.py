import base64

import cv2

class EnhancedPokemonWrapper:
    """
    Enhanced wrapper for Pokemon Red/Blue games that extracts additional data
    directly from memory addresses.
    """
    
    def __init__(self, pyboy, memory_addresses=None, value_maps=None):
        self.pyboy = pyboy
        self.game_wrapper = pyboy.game_wrapper
        
        # Load memory addresses from provided dict or default to empty dict
        self.memory_addresses = memory_addresses or {}
        self.value_maps = value_maps or {}
        self.data = {
            'state': "start",
            "is_in_battle": False,
            'map': {},
            'player': {},
            }
        self._current_button_pressed = None
          
    def __str__(self):
        """Return a string representation of the current game state."""
        # Capture the output of print_game_state in a string
        import io
        from contextlib import redirect_stdout
        
        f = io.StringIO()
        with redirect_stdout(f):
            
            print(f"\n{'-' * 20} Frame: {self.data['frame']} {'-' * 20}")
            print(f"State: {self.data['state']} | In Battle: {self.data['is_in_battle']}")
            
            # Map information
            print(f"\n=== MAP INFO ===")
            print(f"Current Map: {self.data['map']['name']}")
            print(f"Tileset: {self.data['map']['tileset']['name']}")
            print(f"Dimensions: {self.data['map']['dimensions']}")
            
            # Player information
            print(f"\n=== PLAYER INFO ===")
            player_x, player_y, facing = self.data['player']['position']
            print(f"Position: ({player_x}, {player_y}) Facing: {facing}")
            print(f"Money: {self.data['player']['money']} ₽")
            print(f"Badges: {', '.join(self.data['player']['badges']) if self.data['player']['badges'] else 'None'}")
            print(f"Pokédex: {self.data['player']['pokedex']['owned']} owned, {self.data['player']['pokedex']['seen']} seen")
            
            # Bag items
            print(f"\n=== BAG ITEMS ===")
            if self.data['player']['bag']:
                for item_name, quantity in self.data['player']['bag']:
                    print(f"  • {item_name} x{quantity}")
            else:
                print("  • Empty bag")
            
            # Team information
            print(f"\n=== TEAM POKÉMON ===")
            if self.data['player']['team'] and self.data['player']['team'].get('pokemon'):
                for pokemon in self.data['player']['team']['pokemon']:
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
            if self.data['viewport']['entities']:
                for entity in self.data['viewport']['entities']:
                    print(f"  • {entity.get('name', 'Unknown')} @ ({entity['position']['x']}, {entity['position']['y']}) - {entity.get('state', 'Unknown')}")
            else:
                print("  • No visible entities")
            
            # Map warps
            if self.data['map']['warps']:
                print(f"\n=== MAP WARPS ===")
                for coords, destination in self.data['map']['warps'].items():
                    print(f"  • Warp @ {coords} → {destination}")
            
            # Battle information
            if self.data['is_in_battle']:
                print(f"\n{'=' * 20} BATTLE {'=' * 20}")
                battle = self.data['battle']
                
                # Battle type
                battle_type = "Trainer Battle" if battle.get("is_trainer_battle", False) else "Wild Encounter"
                print(f"Type: {battle_type}")
                
                # Player's active Pokémon
                if self.data['player']['team'] and len(self.data['player']['team']['pokemon']) > 0:
                    active_pokemon = self.data['player']['team']['pokemon'][0]
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
            menu_state = self.data['text'].get('menu_state', {})
            if menu_state.get('cursor_pos') is not None:
                print(f"\n=== VISIBLE TEXT ===")
                for line in self.data['text'].get("lines"):
                    print(f"  {line}")
                print(f"\n=== MENU INFO ===")
                cursor_pos = menu_state.get('cursor_pos', ('?', '?'))
                print(f"  Cursor Position: {cursor_pos}")
                if menu_state.get('cursor_text'):
                    print(f"  Selected Text: '{menu_state['cursor_text']}'")
            
            # Text and dialog information
            if self.data['text']['dialog'] and self.data['state'] != 'menu':
                print(f"\n=== DIALOG ===")
                for line in self.data['text']['dialog']:
                    print(f"  {line}")

            # Tilemap visualization
            if self.data['state'] == 'overworld' and not self.data['is_in_battle'] and self.data['viewport'].get('tiles'):
                print(f"\n=== MAP VIEW ===")
                for row in self.data['viewport']['tiles']:
                    print('  ' + ' '.join(row))
            
        return f.getvalue()
    
    def update(self, frame):
        """
        Update self.data with comprehensive error handling to catch and report issues.
        """
        try:
            self.data['frame'] = frame
            if self._current_button_pressed:
                self.data['last_button'] = self._current_button_pressed
            try:
                # Screenshot handling
                screen_ndarray_bgr = cv2.cvtColor(self.pyboy.screen.ndarray, cv2.COLOR_RGB2BGR)
                _, buffer = cv2.imencode('.jpg', screen_ndarray_bgr)
                self.data['screen'] = base64.b64encode(buffer).decode('utf-8')
            except Exception as e:
                print(f"ERROR capturing screenshot: {e}")
                self.data['screen'] = None
            
            try:
                # Battle state
                self.data['battle'] = self.get_battle_state()
                self.data['is_in_battle'] = self.data['battle'] != None
            except Exception as e:
                print(f"ERROR getting battle state: {e}")
                self.data['battle'] = None
                self.data['is_in_battle'] = False
            
            try:
                # Text data
                self.data['text'] = self.get_text_data()
            except Exception as e:
                print(f"ERROR getting text data: {e}")
                self.data['text'] = {'lines': [], 'menu_state': {}, 'dialog': []}
            
            # Determine game state
            try:
                # Check if a menu is active
                menu_active = (self.data['text'].get("menu_state", {}).get("cursor_pos", None) != None)
                
                # Also check if joypad input is ignored
                joy_ignore = self.pyboy.memory[0xCD6B]  # wJoyIgnore
                scripted_sequence = joy_ignore != 0
                
                # Determine the primary state based on priorities
                self.data['state'] = 'overworld'  # Default state
                
                if scripted_sequence:
                    self.data['state'] = 'scripted'
                elif menu_active:
                    self.data['state'] = 'menu'
                elif self.data['text'].get("dialog", False):
                    self.data['state'] = 'dialog'
                
            except Exception as e:
                print(f"ERROR determining game state: {e}")
                self.data['state'] = 'unknown'
            
            try:
                # Map data
                map_data = {
                    'name': self.get_current_map(),
                    'tileset': self.get_current_tileset(),
                    'dimensions': self.get_map_dimensions(),
                    'warps': self.get_warps(),
                }
                self.data['map'] = map_data
            except Exception as e:
                print(f"ERROR getting map data: {e}")
                self.data['map'] = {'name': 'Unknown', 'dimensions': (0, 0), 'warps': {}}
            
            try:
                # Viewport data
                viewport_data = {
                    'tiles': self.get_enhanced_walkable_matrix(),
                    'entities': self.get_entities_info()
                }
                self.data['viewport'] = viewport_data
            except Exception as e:
                print(f"ERROR getting viewport data: {e}")
                self.data['viewport'] = {'tiles': None, 'entities': []}
            
            try:
                # Player data
                player_data = {
                    'position': self.get_player_position(),
                    'money': self.get_player_money(),
                    'badges': self.get_badges(),
                    'pokedex': self.get_pokedex_stats(),
                    'bag': self.get_bag_items(),
                    'team': self.get_team_stats(),
                }
                self.data['player'] = player_data
            except Exception as e:
                print(f"ERROR getting player data: {e}")
                self.data['player'] = {
                    'position': (0, 0, 'Unknown'),
                    'money': 0,
                    'badges': [],
                    'pokedex': {'owned': 0, 'seen': 0},
                    'bag': [],
                    'team': {'count': 0, 'pokemon': []}
                }

        except Exception as e:
            print(f"CRITICAL ERROR in update method: {e}")
            import traceback
            traceback.print_exc()

    def get_player_position(self):
        """
        Get the player's current position on the map.
        
        Returns:
            tuple: (x_coord, y_coord) representing the player's position
        """
        x_coord = self.pyboy.memory[self.memory_addresses["ADDR_X_COORD"]]
        y_coord = self.pyboy.memory[self.memory_addresses["ADDR_Y_COORD"]]
        facing = self.pyboy.memory[self.memory_addresses["ADDR_FACING"]]
        facedict = {8: "Up", 2: "Left", 1: "Right", 4: "Down", 0: "Null"}
        return (x_coord, y_coord, facedict[facing])
    
    def get_current_map(self):
        """
        Get the name of the current map the player is on.
        
        Returns:
            str: Current map name
        """
        return self.value_maps["maps"][self.pyboy.memory[self.memory_addresses["ADDR_CUR_MAP"]]]
    
    def get_map_dimensions(self):
        """
        Get the dimensions of the current map.
        
        Returns:
            tuple: (width, height) of the current map
        """
        width = self.pyboy.memory[self.memory_addresses["ADDR_CUR_MAP_WIDTH"]]*2
        height = self.pyboy.memory[self.memory_addresses["ADDR_CUR_MAP_HEIGHT"]]*2
        return (width, height)
    
    def get_player_money(self):
        """
        Get the player's current money (Poké Dollars).
        Stored as a 3-byte BCD (Binary Coded Decimal) value.
        
        Returns:
            int: Player's money amount
        """
        # Read the 3 bytes of money (BCD format)
        addr = self.memory_addresses["ADDR_PLAYER_MONEY"]
        money_bytes = [
            self.pyboy.memory[addr],
            self.pyboy.memory[addr + 1],
            self.pyboy.memory[addr + 2]
        ]
        
        # Convert from BCD to decimal
        money = 0
        for i, byte in enumerate(money_bytes):
            high_digit = (byte >> 4) & 0xF
            low_digit = byte & 0xF
            money += (high_digit * 10 + low_digit) * (10**(2-i)*2)
            
        return money
    
    def get_badges(self):
        """
        Get a list of obtained gym badges.
        
        Returns:
            list: List of obtained badge names
        """
        badge_bitfield = self.pyboy.memory[self.memory_addresses["ADDR_OBTAINED_BADGES"]]
        
        badge_names = [
            "Boulder Badge",  # Pewter City - Brock
            "Cascade Badge",  # Cerulean City - Misty
            "Thunder Badge",  # Vermilion City - Lt. Surge
            "Rainbow Badge",  # Celadon City - Erika
            "Soul Badge",     # Fuchsia City - Koga
            "Marsh Badge",    # Saffron City - Sabrina
            "Volcano Badge",  # Cinnabar Island - Blaine
            "Earth Badge"     # Viridian City - Giovanni
        ]
        
        owned_badges = []
        for i in range(8):
            if badge_bitfield & (1 << i):
                owned_badges.append(badge_names[i])
                
        return owned_badges
    
    def get_team_stats(self):
        """
        Get detailed information about the player's Pokémon team.
        Uses structured memory layout with offsets from base addresses.
        
        Returns:
            dict: Dictionary containing team information including:
                - count: Number of Pokémon in party
                - pokemon: List of detailed Pokémon information
        """
        # Base addresses
        party_count_addr = self.memory_addresses["ADDR_PARTY_DATA"]
        party_mon1_addr = self.memory_addresses["ADDR_PARTY_MON1"]
        party_nicknames_addr = self.memory_addresses["ADDR_PARTY_NICKNAMES"]
        POKEMON_DATA_SIZE = 44  # Size of each Pokémon's data block
        NICKNAME_SIZE = 11      # Size of each nickname
        
        # Offsets within each Pokémon's data structure
        OFFSET_SPECIES = 0
        OFFSET_HP = 1       # 2 bytes
        OFFSET_LEVEL = 33
        OFFSET_STATUS = 4
        OFFSET_TYPE1 = 5
        OFFSET_TYPE2 = 6
        OFFSET_MOVES = 8    # 4 bytes
        OFFSET_MAXHP = 34   # 2 bytes
        OFFSET_ATTACK = 36  # 2 bytes
        OFFSET_DEFENSE = 38 # 2 bytes
        OFFSET_SPEED = 40   # 2 bytes
        OFFSET_SPECIAL = 42 # 2 bytes

        # Get party count
        party_count = self.pyboy.memory[party_count_addr]
        
        # Validate party count
        if party_count > 6 or party_count <= 0:
            return {"count": 0, "pokemon": []}
    
        
        # Initialize team data
        team_data = {
            "count": party_count,
            "pokemon": []
        }
        
        # Pokemon status conditions lookup
        status_conditions = {
            0: "Healthy",
            1: "Asleep",
            2: "Poisoned",
            4: "Burned",
            8: "Frozen",
            16: "Paralyzed",
            32: "Badly Poisoned"
        }
        
        # Get detailed info for each Pokémon
        for i in range(party_count):
            # Calculate base address for this Pokémon's data
            mon_addr = party_mon1_addr + (i * POKEMON_DATA_SIZE)
            nickname_addr = party_nicknames_addr + (i * NICKNAME_SIZE)
            
            # Read species (double-check against the party species list)
            species_id = self.value_maps["species"][self.pyboy.memory[mon_addr + OFFSET_SPECIES] - 1]
            
            current_hp = self.pyboy.memory[mon_addr + OFFSET_HP] + \
                        (self.pyboy.memory[mon_addr + OFFSET_HP + 1])
            
            # Read level
            level = self.pyboy.memory[mon_addr + OFFSET_LEVEL]
            if level == 0:
                continue
            # Read status
            status_byte = self.pyboy.memory[mon_addr + OFFSET_STATUS]
            status = status_conditions.get(status_byte, "Unknown")
            
            # Read types
            type1 = self.value_maps['types'].get(str(self.pyboy.memory[mon_addr + OFFSET_TYPE1] - 1), "")
            type2 = self.value_maps['types'].get(str(self.pyboy.memory[mon_addr + OFFSET_TYPE2] - 1), "")
            
            # Read moves (up to 4)
            moves = []
            for j in range(4):
                move_id = self.pyboy.memory[mon_addr + OFFSET_MOVES + j]
                if move_id != 0:  # 0 means empty move slot
                    moves.append(self.value_maps.get('moves', {}).get(move_id, "Move Not Found"))
            
            # Read stats
            max_hp = self.pyboy.memory[mon_addr + OFFSET_MAXHP] + \
                        (self.pyboy.memory[mon_addr + OFFSET_MAXHP + 1])
            attack = self.pyboy.memory[mon_addr + OFFSET_ATTACK] + \
                        (self.pyboy.memory[mon_addr + OFFSET_ATTACK + 1])
            defense = self.pyboy.memory[mon_addr + OFFSET_DEFENSE] + \
                        (self.pyboy.memory[mon_addr + OFFSET_DEFENSE + 1])
            speed = self.pyboy.memory[mon_addr + OFFSET_SPEED] + \
                        (self.pyboy.memory[mon_addr + OFFSET_SPEED + 1])
            special = self.pyboy.memory[mon_addr + OFFSET_SPECIAL] + \
                        (self.pyboy.memory[mon_addr + OFFSET_SPECIAL + 1])
            
            # Read nickname (11 bytes)
            nickname_bytes = []
            for j in range(NICKNAME_SIZE):
                char_byte = self.pyboy.memory[nickname_addr + j]
                if char_byte == 0x50:  # End of name marker
                    break
                nickname_bytes.append(char_byte)
            
            # Simple character mapping for Gen 1 Pokémon games (very basic)
            def map_char(char):
                if char >= 0x80 and char <= 0x99:  # A-Z
                    return chr(char - 0x80 + ord('A'))
                elif char >= 0xA0 and char <= 0xB9:  # a-z
                    return chr(char - 0xA0 + ord('a'))
                elif char >= 0xF6 and char <= 0xFF:  # 0-9
                    return chr(char - 0xF6 + ord('0'))
                else:
                    return '?'
            
            nickname = ''.join(map_char(b) for b in nickname_bytes)
            
            # Create Pokémon data structure
            pokemon_data = {
                "species_id": species_id,
                "nickname": nickname,
                "level": level,
                "current_hp": current_hp,
                "max_hp": max_hp,
                "status": status,
                "types": [type1, type2],
                "moves": moves,
                "stats": {
                    "HP": max_hp,
                    "ATTACK": attack,
                    "DEFENSE": defense,
                    "SPEED": speed,
                    "SPECIAL": special
                }
            }
            
            team_data["pokemon"].append(pokemon_data)
        return team_data
    
    def get_pokedex_stats(self):
        """
        Get Pokedex statistics.
        
        Returns:
            dict: Dictionary with 'seen' and 'owned' counts
        """
        # Count owned Pokemon (first 151 bits represent ownership status)
        owned_addr = self.memory_addresses["ADDR_POKEDEX_OWNED"]
        owned_bytes = [self.pyboy.memory[owned_addr + i] for i in range(19)]
        owned_count = 0
        for byte in owned_bytes:
            for bit in range(8):
                if byte & (1 << bit):
                    owned_count += 1
        
        # Count seen Pokemon
        seen_addr = self.memory_addresses["ADDR_POKEDEX_SEEN"]
        seen_bytes = [self.pyboy.memory[seen_addr + i] for i in range(19)]
        seen_count = 0
        for byte in seen_bytes:
            for bit in range(8):
                if byte & (1 << bit):
                    seen_count += 1
        
        return {
            "owned": owned_count,
            "seen": seen_count
        }
    
    def get_bag_items(self):
        """
        Get the items in the player's bag.
        
        Returns:
            list: List of (item_id, quantity) tuples
        """
        num_items = self.pyboy.memory[self.memory_addresses["ADDR_NUM_BAG_ITEMS"]]
        if num_items > 20 or num_items <= 0:  # Sanity check, max 20 items in bag
            return []
            
        items = []
        bag_addr = self.memory_addresses["ADDR_BAG_ITEMS"]
        for i in range(num_items):
            item_addr = bag_addr + (i * 2)
            item_id = self.pyboy.memory[item_addr]
            quantity = self.pyboy.memory[item_addr + 1]
            items.append((self.value_maps['items'][item_id-1], quantity))
            
        return items
    
    def get_entities_info(self):
        """
        Get detailed information about all entities on the map.
        
        Returns:
            list: List of dictionaries containing entity information
        """
        entities = []

        
        # Process all sprite slots except the player (1-15 = NPCs)
        for sprite_idx in range(1, 16):
            # Get sprite state data
            sprite_data1_base = 0xC100 + (sprite_idx * 16)
            sprite_data2_base = 0xC200 + (sprite_idx * 16)
            

            # Check if sprite is active
            movement_status = self.pyboy.memory[sprite_data1_base + 1]
            if movement_status == 0 and sprite_idx != 0:  # Always include player
                continue  # Inactive sprite
            
            # Check if sprite is hidden (0xFF in sprite image index)
            sprite_image_idx = self.pyboy.memory[sprite_data1_base + 2]
            if sprite_image_idx == 0xFF:
                continue  # Hidden sprite
            # Get basic sprite information
            picture_id = self.pyboy.memory[sprite_data1_base]
            facing_direction = self.pyboy.memory[sprite_data1_base + 9]
            
            # Get map position (in 2x2 grid, adjust from offset 4)
            grid_y = self.pyboy.memory[sprite_data2_base + 4]
            grid_x = self.pyboy.memory[sprite_data2_base + 5]
            
            # Convert to map coordinates
            map_y = (grid_y - 4)
            map_x = (grid_x - 4)
            
            # Get movement pattern
            movement_pattern = self.pyboy.memory[sprite_data2_base + 6]
            movement_delay = self.pyboy.memory[sprite_data2_base + 8]
            
            # Determine direction name
            direction_names = {0: "down", 4: "up", 8: "left", 12: "right"}
            direction = direction_names.get(facing_direction, f"unknown ({facing_direction})")
            
            # Determine movement type
            if movement_pattern == 0xFF:
                movement_type = "stationary"
            elif movement_pattern == 0xFE:
                movement_type = "random"
            elif movement_pattern == 0xFD:
                movement_type = "vertical"
            elif movement_pattern == 0xFC:
                movement_type = "horizontal"
            else:
                movement_type = f"scripted ({movement_pattern})"
            
            # Build entity information
            entity = {
                "sprite_index": sprite_idx,
                "name": self.value_maps["sprites"][int(picture_id)-1][0],
                "position": {
                    "x": map_x,
                    "y": map_y,
                },
                "movement": {
                    "status": movement_status,
                    "type": movement_type,
                    "delay": movement_delay,
                    "direction": direction
                },
                "state": movement_type
            }
            
            entities.append(entity)
        
        return entities

    def get_current_tileset(self):
        """
        Get the current tileset being used on the map.
        
        Returns:
            dict: Current tileset entry in value_maps.json
        """
        tileset = self.value_maps['tilesets'][self.pyboy.memory[self.memory_addresses["ADDR_CUR_MAP_TILESET"]]]
        if "WATER" in tileset.get("animation").split("_"):
            tileset['WATER'] = True
        else:
            tileset['WATER'] = False
        return tileset

    def get_warps(self):
        """
        Get all warp points on the current map.
        
        Each warp entry in Pokemon Red/Blue contains:
        - Y-coordinate (1 byte)
        - X-coordinate (1 byte)
        - Destination map ID (1 byte) [Not sure what this actually encodes, so I ignore it]
        - Destination warp ID (1 byte)
        
        Returns:
            Dict: Dictionary containing warp information keyed by:
                - position: (x, y) tuple of coordinates on the current map
                With values:
                - destination_warp_name: String name of the exact destination map (ex. ViridianPokemart)
        """
        # Get number of warps on the current map
        warp_count = self.pyboy.memory[self.memory_addresses["WARPCOUNT"]]
        
        # Validate warp count (sanity check)
        if warp_count > 32 or warp_count < 0:  # 32 is a reasonable upper limit
            print(f"Warning: Invalid warp count: {warp_count}")
            return []
        
        # Starting address of warp entries
        warps_addr = self.memory_addresses["WARPS"]
        
        # Size of each warp entry (4 bytes: y, x, dest_map, dest_warp_id)
        WARP_ENTRY_SIZE = 4

        # Initialize warps list
        warps = {}
        
        # Read all warp entries
        for i in range(warp_count):
            # Calculate address for this warp entry
            entry_addr = warps_addr + (i * WARP_ENTRY_SIZE)
            
            # Read warp data
            y_coord = self.pyboy.memory[entry_addr]
            x_coord = self.pyboy.memory[entry_addr + 1]
            dest_warp_id = self.pyboy.memory[entry_addr + 3]
            
            # Get destination map name
            dest_warp_name = self.value_maps["maps"][dest_warp_id] if dest_warp_id < len(self.value_maps["maps"]) else f"Overworld"
            # Create warp entry dictionary
            warps[(x_coord, y_coord)] = dest_warp_name
        return warps

    def get_logical_tilemap(self):
        """
        Get the logical tilemap directly from WRAM (wTileMap at 0xC3A0).
        
        Returns:
            list: 2D array of metatile indices used by the game logic
        """
        # Base address of wTileMap in WRAM
        wram_tilemap_addr = 0xC3A0
        
        # The actual map stored in memory is 20x18 tiles
        map_width = 20
        map_height = 18
        
        # Create a 2D array to store the tilemap
        logical_tilemap = []
        
        # Read the map directly without scroll calculations
        for y in range(map_height):
            row = []
            for x in range(map_width):
                # Calculate the offset in memory
                offset = y * map_width + x
                
                # Read the metatile ID from WRAM
                if wram_tilemap_addr + offset <= 0xC508:  # Stay within bounds
                    tile_id = self.pyboy.memory[wram_tilemap_addr + offset]
                    row.append(tile_id)
                else:
                    row.append(0)  # Default value if out of bounds
            logical_tilemap.append(row)
        return logical_tilemap
    
    def get_enhanced_walkable_matrix(self):
        """
        Create an enhanced walkable matrix that includes special tiles like:
        - W: Water tiles
        - T: Tree tiles
        - G: Grass tiles
        - V: Down ledges
        - <: Left ledges
        - >: Right ledges
        - #: Off-map areas (distinguished from walls which are '0')
        
        Returns:
            list: 2D array (9x10) with enhanced tile information
        """
        if self.get_map_dimensions() == (0,0):
            return None
        # Get the basic walkable matrix (9x10)
        basic_walkable = self._get_screen_walkable_matrix().tolist()
        
        # Get the logical tilemap (18x20)
        logical_tilemap = self.get_logical_tilemap()
        
        # Get current tileset information
        tileset = self.get_current_tileset()
        
        # Get warps for the current map
        warps = self.get_warps()
        warp_positions = set(warps.keys())
        
        # Get player position to determine top-left corner of visible screen
        player_x, player_y, _ = self.get_player_position()
        screen_left = max(0, player_x - 4)
        screen_top = max(0, player_y - 4)
        
        # Get grass tile ID
        grass_tile = tileset.get('grass_tile', -1)
        codes = self.value_maps.get('tile_codes', {})
        codes[str(grass_tile)] = 'G'
        
        # Start with the basic walkable matrix
        enhanced_matrix = []
        for row in basic_walkable:
            enhanced_row = [str(cell) for cell in row]
            enhanced_matrix.append(enhanced_row)
        
        # Define valid standing tiles for ledges (based on LedgeTiles data)
        valid_standing_tiles = [0x2C, 0x39]  # Tiles player can stand on before a ledge
        
        # Now scan through the logical tilemap to find special tiles
        for tile_y in range(len(logical_tilemap)):
            for tile_x in range(len(logical_tilemap[0])):
                # Get the tile
                tile = logical_tilemap[tile_y][tile_x]
                tile_str = str(tile)
                
                # Convert to walkable matrix coordinates
                walkable_y = tile_y // 2
                walkable_x = tile_x // 2
                
                # Skip if outside the walkable matrix
                if (walkable_y >= len(enhanced_matrix) or
                    walkable_x >= len(enhanced_matrix[0])):
                    continue
                    
                # Check for off-map tiles
                if tile == 0x10:  # This is the typical ID for blank/off-map tiles
                    enhanced_matrix[walkable_y][walkable_x] = '#'
                    continue
                    
                # Determine special tile type
                special_type = None
                
                # Check for ledges or other special tiles
                if tile_str in codes:
                    code = self.value_maps['tile_codes'][tile_str]
                    
                    # For ledges, we need to check if a valid standing tile is adjacent
                    if code in ['v', '<', '>']:
                        # For downward ledges, check the tile above
                        if code == 'v' and tile_y > 0:
                            above_tile = logical_tilemap[tile_y-1][tile_x]
                            if above_tile in valid_standing_tiles:
                                special_type = code
                        
                        # For leftward ledges, check the tile to the right
                        elif code == '<' and tile_x < len(logical_tilemap[0])-1:
                            right_tile = logical_tilemap[tile_y][tile_x+1]
                            if right_tile in valid_standing_tiles:
                                special_type = code
                        
                        # For rightward ledges, check the tile to the left
                        elif code == '>' and tile_x > 0:
                            left_tile = logical_tilemap[tile_y][tile_x-1]
                            if left_tile in valid_standing_tiles:
                                special_type = code
                    
                    # For non-ledge special tiles
                    else:
                        # Don't mark water if the tileset doesn't have water animation
                        if code == "W" and not tileset.get('WATER', False):
                            pass
                        elif (code == "T" or code == "G") and grass_tile == -1:
                            pass
                        else:
                            special_type = code
                
                # If we found a special type, update the matrix
                if special_type:
                    enhanced_matrix[walkable_y][walkable_x] = special_type
        
        return enhanced_matrix

    def _get_screen_walkable_matrix(self):
        """Get the walkable matrix from the original game wrapper"""
        return self.game_wrapper._get_screen_walkable_matrix()

    def get_text_data(self):
        """
        Extract text data from the tilemap with improved structured handling of dialog and menus.
        Uses dialog content changes to track progression without relying on continue markers.
        
        Returns:
            dict: Dictionary containing structured text data
        """
        # Get all visible text from the screen using only tile IDs
        screen_text = self.extract_text_from_tilemap()
        
        # Initialize result structure
        result = {
            "lines": [],
            "menu_state": {},
            "dialog": []
        }
        
        # Process all visible text lines (whole screen)
        for line in screen_text:
            if line.strip():  # Skip empty lines
                result["lines"].append(line)
        
        # Get menu state
        menu_state = {
            "current_item": self.pyboy.memory[self.memory_addresses['CURRENT_MENU_ITEM']],
            "max_item": self.pyboy.memory[0xCC28],      # wMaxMenuItem
            "cursor_pos": None,
            "cursor_text": None
        }
        
        # Find the cursor position if a menu is active
        menu_active = False
        if menu_state["current_item"] != 0xFF:
            for y, line in enumerate(screen_text):
                if "▶" in line:
                    menu_active = True
                    x = line.index("▶")
                    menu_state["cursor_pos"] = (x, y)
                    
                    # Extract the text after the cursor (usually selected item)
                    after_cursor = line[x+1:].strip()
                    if after_cursor:
                        # Get the first word (typical menu item)
                        menu_state["cursor_text"] = after_cursor.split()[0]
                    break
        
        result["menu_state"] = menu_state
        
        # Initialize dialog tracking state if it doesn't exist
        if not hasattr(self, '_dialog_tracker'):
            self._dialog_tracker = {
                'current_dialog': [],     # Current dialog text
                'dialog_history': [],     # Complete dialog history for current conversation
                'stable_frames': 0,       # Counter for frames without dialog changes
                'last_dialog_change': 0,  # Frame count of last dialog change
                'in_conversation': False  # Whether we're currently in a conversation
            }
        
        # Check if we're in a dialog state - dialog area is typically the bottom portion
        dialog_area = screen_text[12:18]  # Rows where dialog typically appears
        
        # Extract dialog text
        current_dialog_text = []
        for line in dialog_area:
            clean_line = line.strip()
            if clean_line and "▶" not in clean_line and clean_line != "▼":
                current_dialog_text.append(clean_line)
        
        # Check if text input is being ignored (common during dialog)
        joy_ignore = self.pyboy.memory[0xCD6B]  # wJoyIgnore
        scripted_input = joy_ignore != 0
        
        # Determine if we're in dialog mode based on multiple factors
        in_dialog_mode = len(current_dialog_text) > 0 or scripted_input
        
        # Track dialog changes
        if current_dialog_text != self._dialog_tracker['current_dialog']:
            # Dialog text has changed
            self._dialog_tracker['stable_frames'] = 0
            self._dialog_tracker['last_dialog_change'] = self.data.get('frame', 0)
            
            # Check if this is a continuation of existing dialog or new dialog
            if not self._dialog_tracker['in_conversation'] or not self._dialog_tracker['current_dialog']:
                # New conversation starting
                self._dialog_tracker['in_conversation'] = True
                self._dialog_tracker['dialog_history'] = current_dialog_text
            else:
                # Could be a continuation - check for partial overlap
                old_dialog = self._dialog_tracker['current_dialog']
                
                # Check for scrolling text (first line of new text matches last line of old text)
                if (len(old_dialog) > 0 and len(current_dialog_text) > 0 and 
                    old_dialog[-1] == current_dialog_text[0]):
                    # Dialog scrolled - append only new lines
                    self._dialog_tracker['dialog_history'] += current_dialog_text[1:]
                else:
                    # Different content - likely a new dialog box
                    # Add a separator to history for clarity
                    if self._dialog_tracker['dialog_history']:
                        self._dialog_tracker['dialog_history'].append("---")
                    self._dialog_tracker['dialog_history'] += current_dialog_text
            
            # Update current dialog
            self._dialog_tracker['current_dialog'] = current_dialog_text
        else:
            # No change in dialog text
            self._dialog_tracker['stable_frames'] += 1
            
            # If we've had no dialog for a significant time, reset conversation state
            if (not in_dialog_mode and 
                self._dialog_tracker['stable_frames'] > 30 and  # About 1 second
                self._dialog_tracker['in_conversation']):
                self._dialog_tracker['in_conversation'] = False
                self._dialog_tracker['dialog_history'] = []
        
        # Set dialog in result
        result["dialog"] = self._dialog_tracker['current_dialog']
        result["dialog_history"] = self._dialog_tracker['dialog_history']
        
        # Add dialog state information
        result["dialog_state"] = {
            "active": in_dialog_mode,
            "in_conversation": self._dialog_tracker['in_conversation'],
            "stable_frames": self._dialog_tracker['stable_frames'],
            "last_change": self._dialog_tracker['last_dialog_change']
        }
        
        # Determine the overall text context
        if menu_active:
            result["text_context"] = "menu"
        elif in_dialog_mode:
            result["text_context"] = "dialog"
        else:
            result["text_context"] = "none"
        
        return result

    def extract_text_from_tilemap(self):
        """
        Extract text from the tilemap based solely on tile IDs.
        Much more efficient than pixel analysis.
        
        Returns:
            list: List of text lines from the screen
        """
        # Get the tilemap
        tilemap_base = 0xC3A0  # wTileMap address
        
        # Process the screen row by row
        text_lines = []
        
        for y in range(18):  # 18 rows of tiles
            line = ""
            
            for x in range(20):  # 20 columns of tiles
                # Calculate offset and get the tile ID
                offset = y * 20 + x
                if tilemap_base + offset >= 0xC508:  # Stay within tilemap bounds
                    continue
                    
                tile_id = self.pyboy.memory[tilemap_base + offset]
                
                # Check if this tile is a text tile based on ID ranges
                # Text tiles are usually in these ranges
                is_text_tile = ((0x80 <= tile_id <= 0xFF) or  # Standard text (A-Z, a-z, 0-9)
                            (tile_id == 0x7F) or          # Space
                            (tile_id in [0xED, 0xEE]) or  # ▶ and ▼ (cursor, prompt)
                            (0x4A <= tile_id <= 0x5F))    # Control characters and special symbols
                
                if is_text_tile:
                    char = self.map_pokemon_char(tile_id)
                    line += char
                else:
                    line += " "  # Non-text tile
            
            line_trimmed = line.rstrip()
            text_lines.append(line_trimmed)
                
                    
        
        return text_lines

    def map_pokemon_char(self, char_byte):
        """
        Decode a character byte using the provided character mapping.
        
        Args:
            char_byte (int): The byte value from memory
            
        Returns:
            str: The decoded character
        """
        # Convert byte to two-character hex string key
        char_key = f"{char_byte:02x}"
        
        # Check if we have this character in our map
        if 'characters' in self.value_maps and char_key in self.value_maps['characters']:
            char = self.value_maps['characters'][char_key]
            
            # Handle special control characters
            if char.startswith('<') and char.endswith('>'):
                if char == "<LINE>":
                    return "\n"
                elif char == "<PK>":
                    return "POKé"
                elif char == "<MN>":
                    return "MON"
                else:
                    return " "  # Replace other control chars with space
            elif char == "@":  # Text terminator
                return ""
            else:
                return char
        
        # Handle some specific, commonly used tiles that might not be in the map
        if char_byte == 0x7F:  # Space
            return " "
        elif char_byte == 0xED:  # ▶ (menu cursor)
            return "▶"
        elif char_byte == 0xEE:  # ▼ (text continue)
            return "▼"
        
        # If character isn't in the map, return a space
        return " "

    def extract_memory_text(self, address, max_length=50):
        """
        Extract text from a memory address until terminator or max length.
        
        Args:
            address (int): Memory address to start reading from
            max_length (int): Maximum length to read
            
        Returns:
            str: Decoded text
        """
        text = ""
        for i in range(max_length):
            if address + i >= 0x10000:  # Memory boundary check
                break
                
            byte = self.pyboy.memory[address + i]
            if byte == 0x50:  # @ terminator
                break
                
            # Skip control characters that should be ignored
            if byte == 0x00:  # NULL character
                continue
                
            char = self.map_pokemon_char(byte)
            text += char
        return text

    def get_player_name(self):
        """Get the player's name from memory"""
        name_addr = self.memory_addresses.get("ADDR_PLAYER_NAME", 0xD158)
        return self.extract_memory_text(name_addr, 11)
        
    def get_rival_name(self):
        """Get the rival's name from memory"""
        name_addr = self.memory_addresses.get("ADDR_RIVAL_NAME", 0xD34A)
        return self.extract_memory_text(name_addr, 11)
    
    def get_battle_state(self):
        """
        Get detailed information about the current battle state.
        This includes information about both the player's and the enemy's Pokemon,
        their moves, stats, and other battle-related data.
        
        Returns:
            dict: Dictionary containing battle state information, or None if not in battle
        """
        # Check if we're in a battle
        is_in_battle = self.is_in_battle()
        if not is_in_battle:
            return None
        
        # Initialize battle state dictionary
        battle_state = {
            "is_trainer_battle": is_in_battle == 2,  # 2 = trainer battle, 1 = wild battle
        }
        
        # Get player Pokemon data
        battle_state["player_pokemon"] = self._extract_battle_mon_data(0xD014)  # wBattleMon
        
        # Get enemy Pokemon data
        enemy = self._extract_battle_mon_data(0xCFE5)  # wEnemyMon
        if enemy['species_name'] != "MISSINGNO":
            battle_state["enemy_pokemon"] = enemy

        # Calculate which turn it is in the battle
        battle_state["turn_counter"] = (self.pyboy.memory[0xCCF1] | self.pyboy.memory[0xCCF2]) > 0
        
        return battle_state

    def _extract_battle_mon_data(self, base_addr):
        """
        Extract battle Pokemon data from a specific memory address.
        
        Args:
            base_addr (int): Base memory address for the Pokemon data
            
        Returns:
            dict: Dictionary containing Pokemon data
        """
        # Pokemon status conditions lookup
        status_conditions = {
            0: "Healthy",
            1: "Asleep",
            2: "Poisoned",
            4: "Burned",
            8: "Frozen",
            16: "Paralyzed",
            32: "Badly Poisoned"
        }
        
        # Species ID is at the base address
        species_id = self.pyboy.memory[base_addr]
        species_name = "MISSINGNO"
        
        # Safely get species name from value maps
        if 0 < species_id <= len(self.value_maps["species"]):
            species_name = self.value_maps["species"][species_id - 1]
        
        # Current and max HP (2 bytes each)
        current_hp = self.pyboy.memory[base_addr + 1] + (self.pyboy.memory[base_addr + 2])
        max_hp = self.pyboy.memory[base_addr + 15] + (self.pyboy.memory[base_addr + 16])
        
        # Status condition
        status_byte = self.pyboy.memory[base_addr + 4]
        status = status_conditions.get(status_byte, "Unknown")
        
        # Type information
        type1_id = self.pyboy.memory[base_addr + 5]
        type2_id = self.pyboy.memory[base_addr + 6]
        
        # Safely map type IDs to names
        type1_name = self.value_maps['types'].get(str(type1_id), f"Type_{type1_id}")
        type2_name = self.value_maps['types'].get(str(type2_id), f"Type_{type2_id}")
        
        # Level
        level = self.pyboy.memory[base_addr + 14]
        
        # Extract nickname if possible
        nickname = ""
        if base_addr == 0xD014:  # Player's Pokemon
            nickname_addr = 0xD009
        elif base_addr == 0xCFE5:  # Enemy Pokemon
            nickname_addr = 0xCFDA
        else:
            nickname_addr = None
            
        if nickname_addr:
            nickname_bytes = []
            for i in range(11):  # Pokemon nicknames are 11 bytes
                char_byte = self.pyboy.memory[nickname_addr + i]
                if char_byte == 0x50:  # End of name marker
                    break
                nickname_bytes.append(char_byte)
            
            # Simple character mapping for Gen 1 Pokémon games
            def map_char(char):
                if char >= 0x80 and char <= 0x99:  # A-Z
                    return chr(char - 0x80 + ord('A'))
                elif char >= 0xA0 and char <= 0xB9:  # a-z
                    return chr(char - 0xA0 + ord('a'))
                elif char >= 0xF6 and char <= 0xFF:  # 0-9
                    return chr(char - 0xF6 + ord('0'))
                else:
                    return '?'
            
            nickname = ''.join(map_char(b) for b in nickname_bytes)

        return {
            "species_id": species_id,
            "species_name": species_name,
            "nickname": nickname,
            "level": level,
            "hp_percent": round(current_hp / max_hp * 100) if max_hp > 0 else 0,
            "status": status,
            "types": [type1_name, type2_name],
        }

    def _extract_move_data(self, base_addr):
        """
        Extract move data from memory.
        
        Args:
            base_addr (int): Base memory address for the move data
            
        Returns:
            dict: Dictionary containing move information
        """
        move_id = self.pyboy.memory[base_addr]
        if move_id <= 0:
            return {
                "id": 0,
                "name": "None",
                "power": 0,
                "type": "Unknown",
                "accuracy": 0,
                "max_pp": 0,
                "effect": 0
            }
        
        move_name = self.value_maps.get('moves', {}).get(str(move_id - 1), f"Move_{move_id}")
        move_effect = self.pyboy.memory[base_addr + 1]
        move_power = self.pyboy.memory[base_addr + 2]
        
        # Get move type ID and map to name
        move_type_id = self.pyboy.memory[base_addr + 3]
        move_type_name = self.value_maps['types'].get(str(move_type_id - 1), f"Type_{move_type_id}")
        
        move_accuracy = self.pyboy.memory[base_addr + 4]
        move_max_pp = self.pyboy.memory[base_addr + 5]
        
        return {
            "id": move_id,
            "name": move_name,
            "power": move_power,
            "type": move_type_name,
            "type_id": move_type_id,
            "accuracy": move_accuracy,
            "max_pp": move_max_pp,
            "effect": move_effect
        }

    def _get_type_effectiveness(self, effectiveness_value):
        """
        Convert type effectiveness value to a human-readable description.
        
        Args:
            effectiveness_value (int): Type effectiveness value from memory
            
        Returns:
            str: Description of the effectiveness
        """
        if effectiveness_value == 0:
            return "No effect"
        elif effectiveness_value == 5:
            return "Not very effective"
        elif effectiveness_value == 10:
            return "Normal effectiveness"
        elif effectiveness_value == 20:
            return "Super effective"
        elif effectiveness_value == 45:
            return "Status Move"
        else:
            return f"Unknown effectiveness ({effectiveness_value})"

    def is_in_battle(self):
        """
        Check if the game is currently in a battle.
        
        Returns:
            bool: True if in battle, False otherwise
        """
        battle_flag = self.pyboy.memory[self.memory_addresses["IS_IN_BATTLE"]]
        return battle_flag != 0
    