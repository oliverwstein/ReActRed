import os
import re
import logging
import asyncio
import google.generativeai as genai
from datetime import datetime

logger = logging.getLogger("PokemonAI")

class ReactAgent:
    """
    A minimalist agent that uses Google's Gemini AI to play Pokemon.
    
    This agent reads the game log file for context and uses Gemini to decide
    what commands to send to the game.
    """
    
    def __init__(self, api_key=None, model_name="gemini-1.5-pro"):
        """
        Initialize the ReactAgent with Gemini API.
        
        Args:
            api_key (str, optional): Google API key. If not provided, tries to use GEMINI_API_KEY env var.
            model_name (str, optional): Which Gemini model to use. Defaults to "gemini-1.5-pro".
        """
        # Set up API key
        if api_key is None:
            api_key = os.environ.get('GEMINI_API_KEY')
            if api_key is None:
                raise ValueError("No API key provided. Please provide an API key or set GEMINI_API_KEY env var.")
        
        # Configure Gemini API
        genai.configure(api_key=api_key)
        
        # Set up model with appropriate parameters
        generation_config = {
            "temperature": 0.7,
            "top_p": 0.95,
            "top_k": 64,
            "max_output_tokens": 2048,
        }
        
        safety_settings = [
            {
                "category": "HARM_CATEGORY_HARASSMENT",
                "threshold": "BLOCK_ONLY_HIGH"
            },
            {
                "category": "HARM_CATEGORY_HATE_SPEECH",
                "threshold": "BLOCK_ONLY_HIGH"
            },
            {
                "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "threshold": "BLOCK_ONLY_HIGH"
            },
            {
                "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                "threshold": "BLOCK_ONLY_HIGH"
            },
        ]
        
        system_prompt = self._get_system_prompt()
        logger.info(f"Loaded system prompt ({len(system_prompt)} characters)")

        # Create the model with system_instruction
        self.model = genai.GenerativeModel(
            model_name=model_name,
            generation_config=generation_config,
            safety_settings=safety_settings,
            system_instruction=system_prompt
        )
        
        # Start chat without including system prompt in history
        self.chat = self.model.start_chat(history=[])
        
        self.log_file = 'logs/pokemon_ai.log'
        self.last_log_position = 0
        
        # Log agent initialization
        logger.info(f"ReactAgent initialized with model: {model_name}")
        logger.info("Agent is ready to make decisions")
    
    def _get_system_prompt(self):
        """
        Load the system prompt from a file.
        
        Returns:
            str: The system prompt for the agent.
        """
        try:
            # Get the path to the system prompt file
            # This assumes the file is in the same directory as the agent.py file
            script_dir = os.path.dirname(os.path.abspath(__file__))
            prompt_path = os.path.join(script_dir, 'system_prompt.txt')
            
            # Load the system prompt from the file
            with open(prompt_path, 'r') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error loading system prompt: {e}")
            # Fallback to a basic prompt if the file can't be loaded
            return """
            You are an intelligent agent playing Pokemon Red/Blue. 
            Make decisions to progress in the game.
            Provide reasoning then a single command on the last line.
            Valid commands: up, down, left, right, a, b, start, select, help
            """
    
    def get_new_log_content(self):
        """
        Get new content from the log file since the last check.
        
        Returns:
            str: New log content
        """
        try:
            with open(self.log_file, 'r') as f:
                f.seek(self.last_log_position)
                new_content = f.read()
                self.last_log_position = f.tell()
                return new_content
        except Exception as e:
            logger.error(f"Error reading log file: {e}")
            return f"[Error reading log file: {e}]"
    
    def read_log_file(self):
        """
        Read the entire log file.
        
        Returns:
            str: Log file content
        """
        try:
            with open(self.log_file, 'r') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error reading log file: {e}")
            return f"[Error reading log file: {e}]"
    
    def extract_updates_since_last_prompt(self, log_content):
        """
        Extract the updates since the last prompt section from log content.
        
        Args:
            log_content (str): Log content to parse
            
        Returns:
            str: The extracted updates section or the whole log if not found
        """
        # Find the last occurrence of "=== UPDATES SINCE LAST PROMPT ==="
        updates_pattern = r"===\s+UPDATES\s+SINCE\s+LAST\s+PROMPT\s+==="
        matches = list(re.finditer(updates_pattern, log_content))
        
        if matches:
            # Get the position of the last match
            last_match = matches[-1]
            start_pos = last_match.start()
            
            # Extract everything from that point onwards
            return log_content[start_pos:]
        
        # If no updates section found, return the whole log
        return log_content
    
    def format_prompt(self, log_updates):
        """
        Format the prompt to send to Gemini.
        
        Args:
            log_updates (str): Recent log updates to include
            
        Returns:
            str: Formatted prompt
        """
        # Build the prompt
        prompt = f"""
        Recent game updates:
        {log_updates}
        Before deciding on your next action:"""

        lines = log_updates.strip().split('\n')
        last_line = lines[-1] if lines else ""
        
        if 'MAP' in last_line:
            # Extract the current position and map name
            prompt = prompt + f"""
                1. ANALYZE YOUR SURROUNDINGS: 
                - Look at the information above about your current position and surrounding tiles
                - The ◄ symbol marks the direction you're currently facing
                - Note any entities (NPCs, items, boulders) or warps nearby that you can interact with
                - Review the paths to nearby warps and entities to plan efficient navigation

                2. INTERPRET TILE CODES:
                - '1' tiles are walkable
                - '0' tiles are objects you can't walk through
                - '#' tiles are map boundaries
                - '?' tiles near warps might be passages (try walking into them)
                - 'G' tiles are grass (may trigger wild Pokémon encounters)
                - 'W' tiles are water (need to Surf to cross)
                - 'T' tiles are trees (need to Cut to cross)
                - '>' tiles are right-facing ledges (can jump right only)
                - '<' tiles are left-facing ledges (can jump left only)
                - 'v' tiles are down-facing ledges (can jump down only)

                3. ORIENT YOURSELF:
                - How well aware are you of the map you are on, between 0 and 100%? 
                - Use command 'map' or 'state' if you are below 80% confidence.

                4. CHOOSE YOUR ACTION:
                - MOVEMENT: 'up', 'down', 'left', or 'right' to navigate
                    * explore [options]: Automatically explore the current map
                        - Available options: see-only, interact-entities, interact-tiles
                        - Example: "explore interact-entities" to talk to all NPCs
                    * map will give you paths to entities and warps you've seen, as well as showing you the map.
                    * explore will explore the map for you. Manual map exploration should only be for when you know exactly where you are and where you want to go.
                    * If you want to go somewhere and map has no path to it, use explore.
                    * When you enter a new map, start by exploring it!
                - INTERACTION: 'a' to interact with what's in front of you, 'b' to cancel
                - MENU: 'start' to access the main menu, 'select' for secondary function
                
                - INFORMATION COMMANDS:
                    * map: Shows the complete map view (use frequently to understand your surroundings better)
                    * state: Shows detailed game state (positions, status, etc.)
                    
                    * inventory: Displays your items
                    * team: Shows your Pokémon team status
                    * atlas: Displays all discovered maps and connections
                    * dialog: Shows recent conversation history
                    * notes: Displays your current notes and objectives
                    
                - NOTE-TAKING COMMANDS:
                    * note [text]: Adds a note to your journal
                    * goal [text]: Sets a new goal
                    * complete [goal]: Marks a goal as completed

                OUTPUT FORMAT: 
                1. SURROUNDINGS: Describe what you observe around you (entities, warps, obstacles)
                2. DESTINATION: State where you want to go next and why
                3. CONFIDENCE: Rate your map knowledge from 0-100%
                * If below 80%, use either 'map' or 'explore'
                4. NAVIGATION PLAN:
                * For exploration: Use 'explore' command with appropriate options
                * For known destinations: Use 'map' to find the optimal path
                * For simple interactions with visible objects: Use directional commands followed by 'a'
                * ONLY use manual movement when following a specific, short path to a visible destination

                COMMAND: [your single command here]
                """
        elif 'MENU' in last_line:
            # Extract the currently selected option
            selected_option = None
            cursor_text_match = re.search(r"Selected Text: '([^']+)'", log_updates)
            if cursor_text_match:
                selected_option = cursor_text_match.group(1)
            
            # Extract menu position information
            menu_position = None
            menu_info_match = re.search(r"INTERACTIVE: Menu selecting '[^']*' \(item (\d+)/(\d+)\)", log_updates)
            if menu_info_match:
                current_item = menu_info_match.group(1)
                total_items = menu_info_match.group(2)
                menu_position = f"{current_item}/{total_items}"
            
            prompt = prompt + f"""
            1. MENU CONTEXT: 
            - Currently selected option: {selected_option or "Unknown"}
            - Menu position: {menu_position or "Unknown"}

            - INFORMATION COMMANDS:
                * map: Shows the current map view
                * state: Shows detailed game state (positions, status, etc.)
                * inventory: Displays your items
                * team: Shows your Pokémon team status
                * atlas: Displays all discovered maps and connections
                * dialog: Shows recent conversation history
                * notes: Displays your current notes and objectives
                * help: See ALL possible commands, with context.
                
            - NOTE-TAKING COMMANDS:
                * note [text]: Adds a note to your journal
                * goal [text]: Sets a new goal
                * complete [goal]: Marks a goal as completed

            3. CONSIDER THE CONSEQUENCES:
            - What will happen if you select this option?
            - Is this choice aligned with your current goals?

            OUTPUT:
            2. OPTIONS ASSESSMENT:
            * Current selection: Is this the option you want? Why/why not?
            * Other visible options: List any other visible options that might be better

            3. GOAL ALIGNMENT:
            * How does this menu choice relate to your current game objectives?
            * Rate the importance of this decision (Low/Medium/High)

            4. DECISION PLAN:
            * If you need more information: Use 'state' or another information command first
            * If current selection is correct: Use 'a' to select it
            * If you need a different option: Use directional commands to navigate. One button at a time!
            * If you entered this menu by mistake: Use 'b' to exit

            COMMAND: [your single command here]
            """
        else:
            prompt = prompt + """
            1. DETERMINE YOUR CURRENT STATE: Based on the log, are you in a map,
            menu, battle, or dialog?
            
            2. IF UNCERTAIN: Use an information command to clarify your situation.
            - state: Get detailed game state
            - map: See the current map view
            - help: See all available commands
            
            3. CHOOSE AN APPROPRIATE ACTION: Based on your current state and goals.

            Start with your reasoning, then just the command.
            """
        prompt = prompt + """\nThink carefully and reason fully. Your thoughts will guide you.
        If you are stuck, take a step back and reflect. Information commands will help you."""
        return prompt

    async def get_command(self):
        """
        Get the next command based.
        
        This is the main method called by the Interface to get the agent's decision.
            
        Returns:
            str: The command to execute
        """
        # Read the log file
        log_content = self.read_log_file()
        
        # Extract the updates since last prompt
        updates = self.extract_updates_since_last_prompt(log_content)
        
        # Format the prompt with just the log updates
        prompt = self.format_prompt(updates)
        
        try:
            # Send the prompt to Gemini
            logger.info("Asking Gemini for next command...")
            response = await asyncio.to_thread(
                lambda: self.chat.send_message(prompt)
            )
            
            # Extract the command (should be the last line)
            response_text = response.text
            lines = response_text.strip().split('\n')
            
            # Log the full response for transparency
            logger.info(f"Gemini's reasoning:\n{response_text.strip()}")
            
            # The command should be on the last non-empty line
            command = None
            for line in reversed(lines):
                if line.strip():
                    command = line.strip()
                    break
            
            if not command:
                logger.warning("No command found in Gemini's response, defaulting to 'a'")
                command = "a"
            
            return command
            
        except Exception as e:
            logger.error(f"Error getting command from Gemini: {e}")
            # Return a safe default command
            return "a"