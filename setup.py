#!/usr/bin/env python3
"""
Setup script for Pokemon Red/Blue Game Server

This script helps set up the Python environment for running the Pokemon Red/Blue
Game Server. It installs all required dependencies, verifies the presence of
necessary files, and provides guidance on obtaining a valid ROM file.

Usage:
    python setup.py [--rom PATH] [--create-venv]

Options:
    --rom PATH         Path to Pokemon Red/Blue ROM file
    --create-venv      Create a virtual environment for the project
"""

import os
import sys
import json
import shutil
import argparse
import platform
import subprocess
from pathlib import Path


REQUIRED_PACKAGES = [
    "pyboy",
    "websockets",
    "numpy",
    "opencv-python"
]

REQUIRED_FILES = [
    "plugin-server.py",
    "wrapper.py",
    "memory_map.json",
    "value_maps.json"
]


def create_virtual_environment(venv_path=".venv"):
    """Create a virtual environment for the project"""
    print(f"Creating virtual environment at {venv_path}...")
    
    try:
        import venv
        venv.create(venv_path, with_pip=True)
        
        # Determine the path to the Python executable in the venv
        if platform.system() == "Windows":
            python_path = os.path.join(venv_path, "Scripts", "python.exe")
        else:
            python_path = os.path.join(venv_path, "bin", "python")
        
        # Upgrade pip in the virtual environment
        subprocess.check_call([python_path, "-m", "pip", "install", "--upgrade", "pip"])
        print("Virtual environment created successfully.")
        return python_path
    
    except Exception as e:
        print(f"Error creating virtual environment: {e}")
        return sys.executable


def install_dependencies(python_path):
    """Install required packages"""
    print("Installing required packages...")
    try:
        subprocess.check_call([python_path, "-m", "pip", "install"] + REQUIRED_PACKAGES)
        print("Dependencies installed successfully.")
        return True
    except Exception as e:
        print(f"Error installing dependencies: {e}")
        return False


def verify_files():
    """Verify that all required files are present"""
    print("Verifying required files...")
    missing_files = []
    
    for file in REQUIRED_FILES:
        if not os.path.exists(file):
            missing_files.append(file)
    
    if missing_files:
        print("The following required files are missing:")
        for file in missing_files:
            print(f"  - {file}")
        return False
    
    print("All required files are present.")
    return True


def verify_rom(rom_path):
    """Verify that the ROM file exists and has a valid extension"""
    if not rom_path:
        print("No ROM path provided. You will need to specify one when running the server.")
        return False
    
    if not os.path.exists(rom_path):
        print(f"ROM file not found: {rom_path}")
        return False
    
    if not rom_path.lower().endswith((".gb", ".gbc")):
        print(f"Warning: ROM file '{rom_path}' does not have a Game Boy extension (.gb or .gbc)")
        return False
    
    print(f"ROM file verified: {rom_path}")
    return True


def verify_value_maps():
    """Verify that value_maps.json has the expected structure"""
    try:
        with open("value_maps.json", "r") as f:
            value_maps = json.load(f)
        
        required_keys = ["moves", "species", "maps", "items", "sprites", "tilesets", "tile_codes"]
        missing_keys = [key for key in required_keys if key not in value_maps]
        
        if missing_keys:
            print(f"Warning: value_maps.json is missing the following keys: {', '.join(missing_keys)}")
            return False
        
        print("value_maps.json structure verified.")
        return True
    
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error verifying value_maps.json: {e}")
        return False


def verify_memory_map():
    """Verify that memory_map.json has the expected structure"""
    try:
        with open("memory_map.json", "r") as f:
            memory_map = json.load(f)
        
        # Check if we have at least some essential addresses
        essential_addresses = ["ADDR_PARTY_DATA", "ADDR_CUR_MAP", "ADDR_X_COORD", "ADDR_Y_COORD", "ADDR_FACING"]
        missing_addresses = [addr for addr in essential_addresses if addr not in memory_map]
        
        if missing_addresses:
            print(f"Warning: memory_map.json is missing the following essential addresses: {', '.join(missing_addresses)}")
            return False
        
        print("memory_map.json structure verified.")
        return True
    
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error verifying memory_map.json: {e}")
        return False


def create_run_script(python_path, rom_path):
    """Create a run script for the server"""
    if platform.system() == "Windows":
        script_name = "run_server.bat"
        script_content = f"""@echo off
echo Starting Pokemon Red/Blue Game Server...
"{python_path}" plugin-server.py --rom "{rom_path}" --memory-addresses memory_map.json --values-path value_maps.json
pause
"""
    else:
        script_name = "run_server.sh"
        script_content = f"""#!/bin/bash
echo "Starting Pokemon Red/Blue Game Server..."
"{python_path}" plugin-server.py --rom "{rom_path}" --memory-addresses memory_map.json --values-path value_maps.json
"""
    
    with open(script_name, "w") as f:
        f.write(script_content)
    
    # Make the script executable on Unix-like systems
    if platform.system() != "Windows":
        os.chmod(script_name, 0o755)
    
    print(f"Created run script: {script_name}")


def main():
    parser = argparse.ArgumentParser(description="Setup script for Pokemon Red/Blue Game Server")
    parser.add_argument("--rom", type=str, help="Path to Pokemon Red/Blue ROM file")
    parser.add_argument("--create-venv", action="store_true", help="Create a virtual environment for the project")
    args = parser.parse_args()
    
    print("=" * 60)
    print("Pokemon Red/Blue Game Server Setup")
    print("=" * 60)
    
    # Verify required files are present
    if not verify_files():
        print("Setup failed: Missing required files.")
        return
    
    # Verify JSON structure
    verify_value_maps()
    verify_memory_map()
    
    # Create virtual environment if requested
    python_path = sys.executable
    if args.create_venv:
        python_path = create_virtual_environment()
    
    # Install dependencies
    if not install_dependencies(python_path):
        print("Setup failed: Unable to install dependencies.")
        return
    
    # Verify ROM file
    rom_verified = verify_rom(args.rom)
    
    # Create run script if ROM is verified
    if rom_verified:
        create_run_script(python_path, args.rom)
    
    print("\nSetup completed!")
    
    if not rom_verified:
        print("\nNote: You need to provide a valid Pokemon Red/Blue ROM file to run the server.")
        print("You can use the --rom option when running this setup script or specify it when starting the server.")
    
    print("\nTo run the server:")
    if platform.system() == "Windows" and rom_verified:
        print("  1. Double-click run_server.bat")
    elif rom_verified:
        print(f"  1. Run: ./run_server.sh")
    else:
        print(f"  1. Run: {python_path} plugin-server.py --rom path/to/pokemon_red.gb")
    
    print("\nOnce the server is running, you can connect to it using WebSockets at:")
    print("  ws://localhost:8765")
    print("\nEnjoy using the Pokemon Red/Blue Game Server!")


if __name__ == "__main__":
    main()