#!/usr/bin/env python3
"""
ReactAgent for Pokemon Red/Blue that leverages local LLMs through Ollama.

This agent makes decisions based on game context and returns commands
while maintaining memory of goals and notes.
"""

import os
import re
import logging
import asyncio
import json
from datetime import datetime

# Configure logging
logger = logging.getLogger("PokemonAI")

class ReactAgent:
    """
    A ReactAgent that uses Ollama's local LLMs to play Pokemon.
    
    This agent processes game context from the interface, maintains memory
    of goals and notes, and returns structured commands with reasoning.
    """
    
    def __init__(self, model_name="deepseek-r1"):
        """
        Initialize the ReactAgent with Ollama integration.
        
        Args:
            model_name (str, optional): Ollama model to use. Defaults to "deepseek-r1".
        """
        # Set up Ollama configuration
        self.model_name = model_name
        
        # Load system prompt
        self.system_prompt = self._get_system_prompt()
        logger.info(f"Loaded system prompt ({len(self.system_prompt)} characters)")
        
        # Initialize conversation history
        self.messages = [
            {
                'role': 'system',
                'content': self.system_prompt
            }
        ]
        
        # Initialize memory structures
        self.goals = []
        self.notes = []
        self.command_history = []
        
        # Log agent initialization
        logger.info(f"ReactAgent initialized with Ollama model: {model_name}")
        logger.info("Agent is ready to make decisions")
    
    def _get_system_prompt(self):
        """
        Load the system prompt from a file or use default.
        
        Returns:
            str: The system prompt for the agent.
        """
        try:
            # Get the path to the system prompt file
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
                Analyze the game context and decide on the best action.

                When responding:
                1. Reason through the situation in detail
                2. Consider your goals and current game state
                3. End your response with a clear command using this format:

                GOALS:
                - Goal 1
                - Goal 2

                NOTES:
                - Important observation 1
                - Important observation 2

                COMMAND: [button]

                Available commands:
                - Movement: up, down, left, right
                - Action: a, b, start, select
                - Sequences are allowed with commas (e.g., "up,up,right,a")
            """
    
    def _add_memory_to_context(self, context):
        """
        Add the agent's memory (goals and notes) to the provided context.
        
        Args:
            context (str): The game context from the interface
            
        Returns:
            str: Enhanced context with memory information
        """
        memory_section = "\n\n=== YOUR MEMORY ===\n"
        
        # Add goals to context
        memory_section += "CURRENT GOALS:\n"
        if self.goals:
            for goal in self.goals:
                status = goal.get('status', 'active')
                memory_section += f"- {goal.get('description', 'Unknown goal')} [{status}]\n"
        else:
            memory_section += "- No active goals set. Consider exploring or advancing the story.\n"
        
        # Add notes to context
        memory_section += "\nYOUR NOTES:\n"
        if self.notes:
            for note in self.notes[-5:]:  # Only show last 5 notes to avoid context overload
                memory_section += f"- {note.get('text', 'Unknown note')}\n"
        else:
            memory_section += "- No notes recorded yet.\n"
        
        # Add recent commands
        memory_section += "\nRECENT COMMANDS:\n"
        if self.command_history:
            for cmd in self.command_history[-5:]:  # Only show last 5 commands
                memory_section += f"- {cmd}\n"
        else:
            memory_section += "- No commands issued yet.\n"
        
        return context + memory_section
    
    def _parse_response(self, response_text):
        """
        Extract command and other information from the LLM's response.
        
        Args:
            response_text (str): The full text response from the LLM
            
        Returns:
            dict: Parsed information including command, goals, and notes
        """
        # Remove any <think> sections that might be present
        reasoning = re.sub(r'<think>.*?</think>', '', response_text, flags=re.DOTALL).strip()
        
        # Look for explicitly stated command with a clear delimiter
        command_match = re.search(r'COMMAND:\s*([a-zA-Z0-9,]+)', response_text, re.IGNORECASE)
        
        if command_match:
            command = command_match.group(1).strip()
        else:
            # Fallback extraction methods
            # Look for button mentions
            valid_buttons = ["up", "down", "left", "right", "a", "b", "start", "select"]
            
            for button in valid_buttons:
                # Various ways the command might be expressed
                patterns = [
                    rf'press ["\']?{button}["\']?',
                    rf'command: ["\']?{button}["\']?', 
                    rf'button: ["\']?{button}["\']?',
                    rf'move ["\']?{button}["\']?',
                    rf' {button} button',
                    rf' {button}$',
                ]
                
                for pattern in patterns:
                    if re.search(pattern, response_text, re.IGNORECASE):
                        return {"command": button, "reasoning": reasoning}
            
            # Default to 'a' as a safe action if nothing is found
            command = "a"
        
        # Extract any goals/notes if present (optional, not required format)
        goals = []
        notes = []
        
        # Simple regex to find goals and notes if available
        goals_match = re.search(r'GOALS?:(.+?)(?:NOTES?:|COMMAND:|$)', response_text, re.DOTALL | re.IGNORECASE)
        if goals_match:
            goals_text = goals_match.group(1).strip()
            goals = [{"description": goal.strip(), "status": "active", "id": i+1} 
                    for i, goal in enumerate(re.findall(r'[-•*]\s*(.+)', goals_text))]
        
        notes_match = re.search(r'NOTES?:(.+?)(?:GOALS?:|COMMAND:|$)', response_text, re.DOTALL | re.IGNORECASE)
        if notes_match:
            notes_text = notes_match.group(1).strip()
            notes = [{"text": note.strip()} 
                    for note in re.findall(r'[-•*]\s*(.+)', notes_text)]
        
        return {
            "command": command,
            "reasoning": reasoning,
            "goals": goals,
            "notes": notes
        }
    
    def _update_memory(self, parsed_response):
        """
        Update the agent's memory based on the response.
        
        Args:
            parsed_response (dict): The parsed response
        """
        # Update goals if provided
        if 'goals' in parsed_response and parsed_response['goals']:
            # Replace goals completely if provided
            self.goals = parsed_response['goals']
        
        # Add new notes if provided
        if 'notes' in parsed_response and parsed_response['notes']:
            for note in parsed_response['notes']:
                # Add timestamp if not already present
                if 'timestamp' not in note:
                    note['timestamp'] = datetime.now().isoformat()
                self.notes.append(note)
    
    def _record_command(self, command):
        """
        Record the command in the history.
        
        Args:
            command (str): The command being executed
        """
        self.command_history.append(command)
        # Keep history at a reasonable size
        if len(self.command_history) > 50:
            self.command_history = self.command_history[-50:]
    
    async def chat_with_ollama(self, prompt):
        """
        Send a prompt to Ollama and get the response.
        
        Args:
            prompt (str): The prompt to send
            
        Returns:
            str: The model's response
        """
        try:
            # Add user message to history
            self.messages.append({
                'role': 'user',
                'content': prompt
            })
            
            # Log the prompt
            logger.info(f"Asking LLM for next command...")
            logger.info(f"Sending request to Ollama:\n {prompt}")
            
            # Import ollama here to avoid circular imports
            import ollama
            
            # Use the chat method from ollama library
            response = await asyncio.to_thread(
                ollama.chat,
                model=self.model_name,
                messages=self.messages
            )
            
            # Extract content from response
            content = ""
            if hasattr(response, 'message') and hasattr(response.message, 'content'):
                content = response.message.content
            else:
                # Fallback for other response formats
                logger.warning(f"Unexpected response type from Ollama: {type(response)}")
                content = str(response)
            
            # Log the response
            logger.info(f"Response text: \n {content}")
            
            # Add assistant response to history
            self.messages.append({
                'role': 'assistant',
                'content': content
            })
            
            # Keep history manageable - retain last 5 exchanges plus system prompt
            if len(self.messages) > 11:  # system prompt + 5 exchanges
                self.messages = [self.messages[0]] + self.messages[-10:]
            
            return content
            
        except Exception as e:
            logger.error(f"Error using Ollama: {e}")
            return "Error: Failed to get response from Ollama. Using default action 'a'."
        
    async def get_command(self, context):
        """
        Process game context and decide on the next command.
        
        This is the main method called by the interface.
        
        Args:
            context (str): Game context from the interface
            
        Returns:
            str: Command to execute
        """
        try:
            # Add memory to context
            enhanced_context = self._add_memory_to_context(context)
            
            # Send to LLM
            response_text = await self.chat_with_ollama(enhanced_context)
            
            # Parse the response
            parsed_response = self._parse_response(response_text)
            
            # Update memory
            self._update_memory(parsed_response)
            
            # Log reasoning
            logger.info(f"=== AGENT REASONING ===")
            logger.info(parsed_response.get('reasoning', ''))
            logger.info("=======================")
            
            # Get command
            command = parsed_response.get('command', 'a')
            
            # Record command in history
            self._record_command(command)
            
            # Log the command
            if ',' in command:
                logger.info(f"Returning button sequence: {command}")
            else:
                logger.info(f"Returning command: {command}")
            
            return command
            
        except Exception as e:
            logger.error(f"Error in get_command: {e}")
            # Return a safe default command
            return "a"