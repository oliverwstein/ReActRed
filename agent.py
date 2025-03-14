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
    
    def __init__(self, model_name="gemma3:4b"):
        """
        Initialize the ReactAgent with Ollama integration.
        
        Args:
            model_name (str, optional): Ollama model to use.
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
            prompt_path = os.path.join(script_dir, 'simple_system_prompt.txt')
            
            # Load the system prompt from the file
            with open(prompt_path, 'r') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error loading system prompt: {e}")
            # Fallback to a basic prompt if the file can't be loaded
            return """
                You are an intelligent agent named RED designed to play Pokemon Red through a text-adventure style interface.
                You will be given a prompt with the current state (either a menu state or an Exploration state) and the recent dialog and recent movements (if any),
                and must respond with one of the commands listed in the prompt.
                Your objective is to progress through the game by exploring the world, building a strong team, defeating gym leaders, and ultimately becoming the Pokemon Champion.
                Be whimsical, and have fun when you can. Name your pokemon, and give them personalities.

                When responding:
                1. Reason through the situation in detail
                2. Consider your goals, current game state, and recent actions.
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
            return "Error: Failed to get response from Ollama."
    
    def _parse_response(self, text):
        reasoning = text.split("COMMAND:")[0][:-9]
        logger.info(f"Reasoning:\n{reasoning}")
        command = text.split("COMMAND:")[1].replace(" ", "")
        return reasoning, command

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
            # Send to LLM
            response_text = await self.chat_with_ollama(context)
            # Parse the response
            reasoning, command = self._parse_response(response_text)
            
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
            return ""