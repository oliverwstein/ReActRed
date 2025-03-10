import json
import logging
import os
import glob
import re
import subprocess
import shlex
import threading

class ToolManager:
    """Manages a collection of tools and provides access to them"""
    
    def __init__(self):
        self.tools = {}
        
    def register_tool(self, tool):
        """Register a tool with the manager
        
        Args:
            tool: An instance of a BaseTool subclass
        """
        self.tools[tool.name] = tool
        
    def get_tool(self, name):
        """Get a tool by name
        
        Args:
            name (str): Name of the tool
            
        Returns:
            BaseTool: The requested tool or None if not found
        """
        return self.tools.get(name)
    
    def list_tools(self):
        """List all available tools
        
        Returns:
            list: Information about all available tools
        """
        return [
            {
                "name": tool.name,
                "description": tool.description
            }
            for tool in self.tools.values()
        ]
    
    def execute_tool(self, name, *args, **kwargs):
        """Execute a tool by name
        
        Args:
            name (str): Name of the tool to execute
            *args: Positional arguments to pass to the tool
            **kwargs: Keyword arguments to pass to the tool
            
        Returns:
            The result of the tool execution or an error
        """
        tool = self.get_tool(name)
        if tool is None:
            return {
                "success": False,
                "error": f"Tool '{name}' not found"
            }
        
        try:
            return tool.execute(*args, **kwargs)
        except Exception as e:
            return {
                "success": False,
                "error": f"Error executing tool '{name}': {str(e)}"
            }
        
class BaseTool:
    """Base class for all tools"""
    def __init__(self, name, description):
        self.name = name
        self.description = description

    def execute(self, *args, **kwargs):
        """Execute the tool with the given arguments"""
        raise NotImplementedError("Subclasses must implement execute method")

class BashTool(BaseTool):
    """Tool for executing shell commands"""
    def __init__(self):
        super().__init__("bash", "Executes shell commands in your environment")
        
    def execute(self, command, capture_output=True):
        """Execute a shell command
        
        Args:
            command (str): The command to execute
            capture_output (bool): Whether to capture and return output
            
        Returns:
            dict: Command result with stdout, stderr, and return code
        """
        try:
            args = shlex.split(command)
            process = subprocess.run(
                args, 
                capture_output=capture_output, 
                text=True,
                check=False
            )
            
            return {
                "success": process.returncode == 0,
                "stdout": process.stdout if capture_output else None,
                "stderr": process.stderr if capture_output else None,
                "returncode": process.returncode
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "stdout": None,
                "stderr": None,
                "returncode": -1
            }

class GlobTool(BaseTool):
    """Tool for finding files based on pattern matching"""
    def __init__(self):
        super().__init__("glob", "Finds files based on pattern matching")
        
    def execute(self, pattern):
        """Find files matching a pattern
        
        Args:
            pattern (str): Glob pattern to match files
            
        Returns:
            list: List of matching file paths
        """
        try:
            matches = glob.glob(pattern, recursive=True)
            return {
                "success": True,
                "matches": matches,
                "count": len(matches)
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "matches": [],
                "count": 0
            }

class GrepTool(BaseTool):
    """Tool for searching for patterns in file contents"""
    def __init__(self):
        super().__init__("grep", "Searches for patterns in file contents")
        
    def execute(self, pattern, file_path=None, directory=None, recursive=False):
        """Search for a pattern in file(s)
        
        Args:
            pattern (str): Regex pattern to search for
            file_path (str, optional): Specific file to search
            directory (str, optional): Directory to search
            recursive (bool): Search subdirectories
            
        Returns:
            dict: Search results with matching lines
        """
        try:
            compiled_pattern = re.compile(pattern)
            results = {}
            
            if file_path:
                # Search in a single file
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    for i, line in enumerate(f, 1):
                        if compiled_pattern.search(line):
                            if file_path not in results:
                                results[file_path] = []
                            results[file_path].append({
                                "line_number": i,
                                "content": line.rstrip()
                            })
            
            elif directory:
                # Search in a directory
                for root, _, files in os.walk(directory):
                    if not recursive and root != directory:
                        continue
                        
                    for file in files:
                        file_path = os.path.join(root, file)
                        try:
                            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                                for i, line in enumerate(f, 1):
                                    if compiled_pattern.search(line):
                                        if file_path not in results:
                                            results[file_path] = []
                                        results[file_path].append({
                                            "line_number": i,
                                            "content": line.rstrip()
                                        })
                        except (UnicodeDecodeError, IOError):
                            # Skip binary or inaccessible files
                            pass
            
            return {
                "success": True,
                "results": results,
                "match_count": sum(len(matches) for matches in results.values())
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "results": {},
                "match_count": 0
            }

class LSTool(BaseTool):
    """Tool for listing files and directories"""
    def __init__(self):
        super().__init__("ls", "Lists files and directories")
        
    def execute(self, path=".", details=False):
        """List files and directories
        
        Args:
            path (str): Directory path to list
            details (bool): Whether to include file details
            
        Returns:
            dict: Directory listing
        """
        try:
            items = os.listdir(path)
            
            if not details:
                return {
                    "success": True,
                    "items": items,
                    "count": len(items)
                }
            
            # Include detailed information
            detailed_items = []
            for item in items:
                full_path = os.path.join(path, item)
                stats = os.stat(full_path)
                
                detailed_items.append({
                    "name": item,
                    "path": full_path,
                    "is_dir": os.path.isdir(full_path),
                    "size": stats.st_size,
                    "modified": stats.st_mtime,
                    "created": stats.st_ctime
                })
                
            return {
                "success": True,
                "items": detailed_items,
                "count": len(detailed_items)
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "items": [],
                "count": 0
            }

class FileReadTool(BaseTool):
    """Tool for reading the contents of files"""
    def __init__(self):
        super().__init__("read", "Reads the contents of files")
        
    def execute(self, file_path, binary=False):
        """Read a file
        
        Args:
            file_path (str): Path to the file
            binary (bool): Whether to read in binary mode
            
        Returns:
            dict: File contents or binary data
        """
        try:
            mode = 'rb' if binary else 'r'
            encoding = None if binary else 'utf-8'
            errors = None if binary else 'replace'
            
            with open(file_path, mode, encoding=encoding, errors=errors) as f:
                content = f.read()
                
            return {
                "success": True,
                "content": content,
                "size": len(content)
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "content": None,
                "size": 0
            }

class FileEditTool(BaseTool):
    """Tool for making targeted edits to specific files"""
    def __init__(self):
        super().__init__("edit", "Makes targeted edits to specific files")
        
    def execute(self, file_path, find_text, replace_text, match_case=True, regex=False):
        """Edit a file by replacing text
        
        Args:
            file_path (str): Path to the file
            find_text (str): Text to find
            replace_text (str): Text to replace with
            match_case (bool): Whether to match case
            regex (bool): Whether to use regex pattern matching
            
        Returns:
            dict: Result of the edit operation
        """
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            
            # Perform the replacement
            if regex:
                flags = 0 if match_case else re.IGNORECASE
                pattern = re.compile(find_text, flags)
                new_content, replacements = re.subn(pattern, replace_text, content)
            else:
                if not match_case:
                    # For case-insensitive literal replacement, we need to do it manually
                    def replace_case_insensitive(c):
                        return c.replace(find_text.lower(), replace_text)
                    
                    new_content = ""
                    remaining = content
                    replacements = 0
                    
                    while True:
                        i = remaining.lower().find(find_text.lower())
                        if i == -1:
                            new_content += remaining
                            break
                        
                        new_content += remaining[:i] + replace_text
                        remaining = remaining[i + len(find_text):]
                        replacements += 1
                else:
                    # Case-sensitive literal replacement
                    new_content = content.replace(find_text, replace_text)
                    replacements = content.count(find_text)
            
            # Write the modified content back to the file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
                
            return {
                "success": True,
                "replacements": replacements,
                "original_size": len(content),
                "new_size": len(new_content)
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "replacements": 0
            }

class FileWriteTool(BaseTool):
    """Tool for creating or overwriting files"""
    def __init__(self):
        super().__init__("write", "Creates or overwrites files")
        
    def execute(self, file_path, content, append=False, binary=False):
        """Write content to a file
        
        Args:
            file_path (str): Path to the file
            content (str or bytes): Content to write
            append (bool): Whether to append to existing content
            binary (bool): Whether to write in binary mode
            
        Returns:
            dict: Result of the write operation
        """
        try:
            mode = 'ab' if append and binary else 'wb' if binary else 'a' if append else 'w'
            encoding = None if binary else 'utf-8'
            
            with open(file_path, mode, encoding=encoding) as f:
                f.write(content)
                
            return {
                "success": True,
                "size": len(content),
                "path": file_path
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "path": file_path
            }

def main():
    # Create a ToolManager instance
    tool_manager = ToolManager()

    # Register various tools
    tool_manager.register_tool(BashTool())
    tool_manager.register_tool(GlobTool())
    tool_manager.register_tool(GrepTool())
    tool_manager.register_tool(LSTool())
    tool_manager.register_tool(FileReadTool())
    tool_manager.register_tool(FileWriteTool())
    tool_manager.register_tool(FileEditTool())
    
    # Example usage of different tools

    # 1. List available tools
    print("Available Tools:")
    for tool_info in tool_manager.list_tools():
        print(f"- {tool_info['name']}: {tool_info['description']}")

    # 2. List files in current directory
    ls_result = tool_manager.execute_tool('ls', details=True)
    print("\nDirectory Contents:")
    for item in ls_result['items']:
        print(f"{item['name']} ({'dir' if item['is_dir'] else 'file'})")

    # 3. Find Python files
    glob_result = tool_manager.execute_tool('glob', '*.py')
    print("\nPython Files:")
    for match in glob_result['matches']:
        print(match)

    # 4. Read a file
    read_result = tool_manager.execute_tool('read', 'tool.py')
    print("\nFile Read Result:")
    print(f"File size: {read_result.get("size")} bytes")

    # 5. Search for a pattern in a file
    grep_result = tool_manager.execute_tool('grep', pattern='class', file_path='tool.py')
    print("\nGrep Results:")
    for file, matches in grep_result['results'].items():
        print(f"Matches in {file}:")
        for match in matches:
            print(f"  Line {match['line_number']}: {match['content']}")

    # 6. Edit a file (be careful with this!)
    # edit_result = tool_manager.execute_tool('edit', 
    #     file_path='example.txt', 
    #     find_text='old text', 
    #     replace_text='new text'
    # )

    # 7. Write to a file
    write_result = tool_manager.execute_tool('write', 
        file_path='example_output.txt', 
        content='This is a sample file created by the tool manager.'
    )
    print("\nWrite Result:")
    print(f"File created: {write_result['path']}, Size: {write_result['size']} bytes")

    # 8. Run a shell command 
    bash_result = tool_manager.execute_tool('bash', 'echo "Hello from bash tool!"')
    print("\nBash Command Result:")
    print(bash_result['stdout'])

if __name__ == '__main__':
    main()