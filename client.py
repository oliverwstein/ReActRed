#!/usr/bin/env python3
"""
Simplified Pokemon client that trusts the server for stability detection.
"""

import asyncio
import aiohttp
import argparse
import random
import sys

class PokemonClient:
    """Main client that communicates with the server and manages game state"""
    
    def __init__(self, server_url='http://localhost:8765', decision_maker=None, poll_interval=0.1):
        self.server_url = server_url
        self.poll_interval = poll_interval
        self.decision_maker = decision_maker or DecisionMaker()
        self.game_state = {}
        self.last_frame = 0
        self.session = None
    
    async def run(self):
        """Main client loop"""
        async with aiohttp.ClientSession() as self.session:
            while True:
                # Poll for current state
                await self.update_state()
                
                # Only process inputs if:
                # 1. The server reports the state as stable
                # 2. We're in a menu or default state
                if (self.game_state.get("stable", False) and
                    self.game_state.get("current_state_type") in ["menu", "default"]):
                    
                    # Get decision from decision maker
                    button = await self.decision_maker.decide_action(self)
                    
                    # Only send input if we got a valid button
                    if button:
                        await self.send_input(button)
                
                # Wait before polling again
                await asyncio.sleep(self.poll_interval)

    async def update_state(self):
        """Poll server for current state"""
        try:
            async with self.session.get(f"{self.server_url}/state") as response:
                if response.status == 200:
                    self.game_state = await response.json()
                    self.last_frame = self.game_state.get("frame", 0)
                else:
                    print(f"Error getting state: {response.status}")
        except Exception as e:
            print(f"Error updating state: {e}")

    async def send_input(self, button):
        """Send button input to server"""
        try:
            async with self.session.post(
                f"{self.server_url}/input",
                json={"button": button}
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    print(f"Error sending input: {response.status}")
                    return None
        except Exception as e:
            print(f"Error sending input: {e}")
            return None
    
    # On-demand journal queries
    async def get_recent_entries(self, count=10, entry_type=None):
        """Get recent journal entries"""
        params = {"count": count}
        if entry_type:
            params["type"] = entry_type
        
        try:    
            async with self.session.get(
                f"{self.server_url}/journal", 
                params=params
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("entries", [])
                else:
                    print(f"Error getting journal entries: {response.status}")
                    return []
        except Exception as e:
            print(f"Error getting journal entries: {e}")
            return []
    
    async def get_entries_since_frame(self, frame, entry_type=None):
        """Get journal entries since a specific frame"""
        params = {"since_frame": frame}
        if entry_type:
            params["type"] = entry_type
        
        try:
            async with self.session.get(
                f"{self.server_url}/journal", 
                params=params
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("entries", [])
                else:
                    print(f"Error getting journal entries: {response.status}")
                    return []
        except Exception as e:
            print(f"Error getting journal entries: {e}")
            return []
    
class DecisionMaker:
    """Responsible for deciding which action to take based on game state"""
    
    def __init__(self, interface=None):
        self.interface = interface
    
    async def decide_action(self, client):
        """Decide what button to press based on the current state"""
        state_type = client.game_state.get("current_state_type")
        
        # If we have an interface, use it
        if self.interface is not None:
            try:
                # Use interactive mode based on current state type
                if state_type == "menu":
                    return await self.interface.get_menu_action(client)
                elif state_type == "default":
                    return await self.interface.get_default_action(client)
                elif state_type == "dialog":
                    # For dialog, we always auto-advance
                    return await self.interface.get_dialog_action(client)
                elif state_type == "scripted":
                    # Scripted state should just observe
                    return None
            except Exception as e:
                # If there's an error in the interface, log it and return None
                print(f"Error in interface action: {e}")
                return None
        else:
            # Use simple automatic mode
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

async def main():
    parser = argparse.ArgumentParser(description="Pokemon Client")
    parser.add_argument("--server", type=str, default="http://localhost:8765",
                        help="Server URL")
    parser.add_argument("--interactive", action="store_true",
                        help="Use interactive mode")
    parser.add_argument("--agent", action="store_true",
                        help="Use ReAct agent")
    parser.add_argument("--poll-interval", type=float, default=0.1,
                        help="State polling interval in seconds")
    
    args = parser.parse_args()
    
    # Import interface if needed
    if args.interactive or args.agent:
        try:
            from interface import InteractiveMode
            # Create ReAct agent if requested
            agent = None
            if args.agent:
                try:
                    from agent import ReactAgent
                    agent = ReactAgent()
                    print("Using ReactAgent for AI control")
                except ImportError:
                    print("Warning: Could not import ReactAgent, falling back to manual control")
            
            # Create interface
            interface = InteractiveMode(agent=agent)
            
            # Create decision maker with interface
            decision_maker = DecisionMaker(interface=interface)
        except ImportError:
            print("Warning: Could not import InteractiveMode, falling back to automatic mode")
            decision_maker = DecisionMaker()
    else:
        # Use automatic mode
        decision_maker = DecisionMaker()
    
    # Create and run client
    client = PokemonClient(
        server_url=args.server,
        decision_maker=decision_maker,
        poll_interval=args.poll_interval
    )
    
    try:
        await client.run()
    except KeyboardInterrupt:
        print("\nShutting down client...")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        sys.exit(0)

if __name__ == "__main__":
    asyncio.run(main())