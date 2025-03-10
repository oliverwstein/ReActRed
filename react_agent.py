import google.generativeai as genai
import asyncio
import re
import networkx as nx
from typing import Optional, Dict, List, Any, Tuple

class GeminiAgent:
    """Provides reasoning capabilities via Gemini API with memory and ReAct-style information retrieval"""
    
    def __init__(self, api_key: str, blackboard):
        self.api_key = api_key
        self.blackboard = blackboard  # Store reference to blackboard for journal and graph access
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-1.5-pro')
        
        # Initialize with a system prompt that establishes the agent's role and tools
        initial_prompt = """
        You are an AI assistant playing Pokémon Red/Blue. Your goal is to progress through the game 
        by making intelligent decisions based on the game state.
        
        You have access to the following tools:
        
        1. search_journal(query): Search the game's journal for information matching your query
           - Example: search_journal("Oak's Lab") will return entries related to Oak's Lab
           - Example: search_journal("last 5 dialogs") will return the last 5 dialog entries
        
        2. get_visited_locations(map_name=None): List visited locations in a specific map or all maps
           - Example: get_visited_locations("Viridian City") will return all visited positions in Viridian City
           - Example: get_visited_locations() will return all visited map names
        
        3. get_shortest_path(destination_map, dest_x, dest_y): Find the shortest path to a destination
           - Example: get_shortest_path("Pewter City", 10, 15) will return the path to that position
           - Returns: A sequence of steps to reach the destination
        
        When you want to use a tool, use the following format:
        <thinking>
        I need to know X, so I'll use tool Y
        </thinking>
        <tool>tool_name("parameters")</tool>
        
        After receiving tool output, continue your reasoning and conclude with your action decision.
        """
        
        self.chat = self.model.start_chat(history=[
            {"role": "user", "parts": [initial_prompt]},
            {"role": "model", "parts": ["I understand my role. I'll help play Pokémon Red/Blue by analyzing the game state and using the available tools to gather information before making decisions."]}
        ])
    
    async def reason(self, game_state: Dict[str, Any], recent_events: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Generate reasoning with ReAct-style tool use capability"""
        # Format the current state update
        context = self._format_updates(game_state, recent_events)
        
        # Ask Gemini to reason about the current state with tool access
        prompt = f"""
        Here's an update on the current game state:
        
        {context}
        
        Based on this update and our previous interactions, what action should I take next?
        Feel free to use the available tools if you need additional information.
        
        Remember to conclude with:
        Reasoning: [your final reasoning]
        Action: [recommended action: up, down, left, right, a, b, start, select]
        """
        
        # Begin the ReAct process
        final_reasoning = ""
        final_action = ""
        max_iterations = 5  # Prevent infinite loops
        
        for i in range(max_iterations):
            # Get response from Gemini
            response = await self._async_send_message(prompt)
            
            # Check if the response contains a tool call
            tool_match = re.search(r'<tool>(.*?)\((.*?)\)</tool>', response)
            if tool_match:
                tool_name = tool_match.group(1)
                tool_params = tool_match.group(2)
                
                # Parse parameters - handle quoted strings properly
                params = []
                if tool_params:
                    # Match either quoted strings or numbers
                    param_pattern = r'"([^"]*)"|\d+'
                    param_matches = re.finditer(param_pattern, tool_params)
                    for match in param_matches:
                        # If group 1 exists, it's a quoted string, otherwise use group 0 (number)
                        params.append(match.group(1) if match.group(1) is not None else match.group(0))
                
                # Execute the appropriate tool
                tool_result = "Tool execution failed. Please try again."
                
                if tool_name == "search_journal":
                    if params:
                        tool_result = self._search_journal(params[0])
                
                elif tool_name == "get_visited_locations":
                    map_name = params[0] if params else None
                    tool_result = self._get_visited_locations(map_name)
                
                elif tool_name == "get_shortest_path":
                    if len(params) >= 3:
                        tool_result = self._get_shortest_path(params[0], int(params[1]), int(params[2]))
                
                # Send the results back to continue the reasoning
                prompt = f"Tool result for {tool_name}({', '.join(params)}):\n\n{tool_result}\n\nContinue your reasoning and decide what action to take."
            else:
                # Extract final reasoning and action
                parts = self._parse_response(response)
                final_reasoning = parts["reasoning"]
                final_action = parts["action"]
                break
        
        return {"reasoning": final_reasoning, "action": final_action}
    
    def _search_journal(self, query: str) -> str:
        """Search the journal for relevant information"""
        journal = self.blackboard.journal
        results = []
        
        # Handle special queries
        if "last" in query.lower() and "dialog" in query.lower():
            # Extract number from query (default to 5 if not found)
            num_entries = 5
            num_match = re.search(r'last (\d+)', query.lower())
            if num_match:
                num_entries = int(num_match.group(1))
            
            # Get last N dialog entries
            dialog_entries = [entry for entry in journal if entry["type"] == "dialog"]
            selected_entries = dialog_entries[-num_entries:] if dialog_entries else []
            
            for entry in selected_entries:
                results.append(f"Frame {entry['frame']} - Dialog: {' '.join(entry['data'])}")
        
        # Map-related queries
        elif "map" in query.lower():
            map_entries = []
            current_map = None
            
            # Find relevant map entries
            for entry in journal:
                if entry["type"] == "movement" and "map" in entry["data"]:
                    map_name = entry["data"]["map"]
                    if current_map != map_name:
                        current_map = map_name
                        map_entries.append(f"Frame {entry['frame']} - Entered map: {map_name}")
            
            # Select entries based on specific map mention
            if any(map_name.lower() in query.lower() for map_name in set(entry["data"]["map"] for entry in journal if entry["type"] == "movement" and "map" in entry["data"])):
                for map_name in set(entry["data"]["map"] for entry in journal if entry["type"] == "movement" and "map" in entry["data"]):
                    if map_name.lower() in query.lower():
                        map_specific_entries = [entry for entry in journal 
                                               if entry["type"] in ["movement", "dialog", "menu"] 
                                               and (entry["type"] == "movement" and entry["data"].get("map") == map_name)]
                        for entry in map_specific_entries[-10:]:  # Last 10 entries for this map
                            if entry["type"] == "movement":
                                results.append(f"Frame {entry['frame']} - Position in {map_name}: {entry['data']['position']}")
                            elif entry["type"] == "dialog":
                                results.append(f"Frame {entry['frame']} - Dialog in {map_name}: {' '.join(entry['data'])}")
            else:
                # Return general map history
                results.extend(map_entries[-10:])  # Last 10 map changes
        
        # General keyword search
        else:
            for entry in journal:
                entry_text = str(entry["data"])
                if query.lower() in entry_text.lower():
                    results.append(f"Frame {entry['frame']} - {entry['type']}: {entry_text}")
        
        # Limit results and return
        if not results:
            return f"No results found for query: {query}"
        
        return "\n".join(results[-15:])  # Return last 15 matching entries
    
    def _get_visited_locations(self, map_name=None) -> str:
        """Get visited locations from the world graph"""
        graph = self.blackboard.world_graph
        
        if not graph or len(graph.nodes()) == 0:
            return "No location data available yet."
        
        results = []
        
        if map_name:
            # Get all visited nodes in a specific map
            map_nodes = [(node_id, data) for node_id, data in graph.nodes(data=True) 
                         if data.get('map') == map_name and data.get('visited', False)]
            
            if not map_nodes:
                return f"No visited locations found in {map_name}."
            
            results.append(f"Visited locations in {map_name}:")
            for node_id, data in map_nodes:
                map_name, x, y = node_id
                results.append(f"- Position ({x}, {y})")
                
                # Add any dialog that happened at this location
                if 'dialogs' in data:
                    for dialog in data['dialogs'][-1:]:  # Just the most recent dialog
                        dialog_text = ' '.join(dialog['text'])
                        results.append(f"  Dialog: \"{dialog_text}\"")
        else:
            # Get all visited maps
            visited_maps = set(data['map'] for _, data in graph.nodes(data=True) 
                              if data.get('visited', False))
            
            if not visited_maps:
                return "No maps have been visited yet."
            
            results.append("Visited maps:")
            for map_name in sorted(visited_maps):
                # Count visited positions in this map
                positions = [(node_id, data) for node_id, data in graph.nodes(data=True) 
                             if data.get('map') == map_name and data.get('visited', False)]
                results.append(f"- {map_name}: {len(positions)} positions visited")
        
        return "\n".join(results)
    
    def _get_shortest_path(self, dest_map: str, dest_x: int, dest_y: int) -> str:
        """Find the shortest path to a destination"""
        graph = self.blackboard.world_graph
        
        if not graph or len(graph.nodes()) == 0:
            return "No map data available yet."
        
        # Get current position
        current_pos = self.blackboard.game_state.get('player', {}).get('position', (0, 0, 'Unknown'))
        current_map = self.blackboard.game_state.get('map', {}).get('name', 'Unknown')
        current_x, current_y, _ = current_pos
        
        # Create node IDs
        current_node = (current_map, current_x, current_y)
        dest_node = (dest_map, dest_x, dest_y)
        
        # Check if nodes exist
        if not graph.has_node(current_node):
            return f"Current position ({current_map}, {current_x}, {current_y}) is not in the map graph."
        
        if not graph.has_node(dest_node):
            return f"Destination ({dest_map}, {dest_x}, {dest_y}) is not in the map graph."
        
        try:
            # Find shortest path using NetworkX
            path = nx.shortest_path(graph, current_node, dest_node)
            
            if not path:
                return f"No path found from current position to {dest_map} ({dest_x}, {dest_y})."
            
            # Format the path as directions
            results = [f"Path from {current_map} ({current_x}, {current_y}) to {dest_map} ({dest_x}, {dest_y}):"]
            
            for i in range(1, len(path)):
                prev_map, prev_x, prev_y = path[i-1]
                curr_map, curr_x, curr_y = path[i]
                
                if prev_map != curr_map:
                    results.append(f"{i}. Take warp from {prev_map} ({prev_x}, {prev_y}) to {curr_map} ({curr_x}, {curr_y})")
                else:
                    # Determine direction
                    dx = curr_x - prev_x
                    dy = curr_y - prev_y
                    
                    direction = ""
                    if dx > 0:
                        direction = "right"
                    elif dx < 0:
                        direction = "left"
                    elif dy > 0:
                        direction = "down"
                    elif dy < 0:
                        direction = "up"
                    
                    results.append(f"{i}. Move {direction} from ({prev_x}, {prev_y}) to ({curr_x}, {curr_y})")
            
            return "\n".join(results)
            
        except nx.NetworkXNoPath:
            return f"No path exists from current position to {dest_map} ({dest_x}, {dest_y})."
        except Exception as e:
            return f"Error finding path: {str(e)}"
    
    async def _async_send_message(self, message: str) -> str:
        """Asynchronous wrapper for sending messages to Gemini"""
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, lambda: self.chat.send_message(message).text
        )
        return response
    
    def _format_updates(self, game_state: Dict[str, Any], recent_events: List[Dict[str, Any]]) -> str:
        """Format recent state updates as a string for the prompt"""
        # Current state summary
        state_str = f"Current State: {game_state.get('state', 'unknown')}\n"
        
        # Add player position if available
        if 'player' in game_state and 'position' in game_state['player']:
            pos = game_state['player']['position']
            state_str += f"Position: ({pos[0]}, {pos[1]}, facing {pos[2]})\n"
        
        # Add map info if available
        if 'map' in game_state and 'name' in game_state['map']:
            state_str += f"Current Map: {game_state['map']['name']}\n"
        
        # Add visible entities (NPCs, items)
        if 'viewport' in game_state and 'entities' in game_state['viewport'] and game_state['viewport']['entities']:
            state_str += "Visible Entities:\n"
            for entity in game_state['viewport']['entities'][:5]:  # Limit to 5 entities
                state_str += f"- {entity.get('name', 'Unknown')} at ({entity['position']['x']}, {entity['position']['y']})\n"
        
        # Add tilemap information if available
        if 'viewport' in game_state and 'tiles' in game_state['viewport'] and game_state['viewport']['tiles']:
            state_str += "Surrounding Tiles:\n"
            tiles_repr = ""
            for row in game_state['viewport']['tiles'][:5]:  # First 5 rows
                tiles_repr += "  " + " ".join(row[:10]) + "\n"  # First 10 columns
            state_str += tiles_repr
        
        # Add recent events
        events_str = "Recent Events:\n"
        for item in recent_events[-5:]:  # Last 5 events
            if item['type'] == 'action':
                events_str += f"- Action: {item['data']['button']} in {item['data']['state']} state\n"
            elif item['type'] == 'dialog':
                dialog_text = ' '.join(item['data'])
                events_str += f"- Dialog: \"{dialog_text}\"\n"
            elif item['type'] == 'menu':
                if 'cursor_text' in item['data']:
                    events_str += f"- Menu: Selected \"{item['data']['cursor_text']}\"\n"
        
        return state_str + "\n" + events_str
    
    def _parse_response(self, response: str) -> Dict[str, str]:
        """Extract reasoning and action from Gemini's response"""
        reasoning = ""
        action = ""
        
        # Remove thinking and tool sections for final parsing
        cleaned_response = re.sub(r'<thinking>.*?</thinking>', '', response, flags=re.DOTALL)
        cleaned_response = re.sub(r'<tool>.*?</tool>', '', cleaned_response, flags=re.DOTALL)
        
        # Extract reasoning and action
        reasoning_match = re.search(r'Reasoning:\s*(.*?)(?=Action:|$)', cleaned_response, re.DOTALL)
        action_match = re.search(r'Action:\s*(\w+)', cleaned_response)
        
        if reasoning_match:
            reasoning = reasoning_match.group(1).strip()
        
        if action_match:
            action = action_match.group(1).strip().lower()
            
        # Fallback if action not found or invalid
        valid_actions = ["up", "down", "left", "right", "a", "b", "start", "select"]
        if not action or action not in valid_actions:
            action = "a"  # Default to pressing A
            
        return {
            "reasoning": reasoning,
            "action": action
        }