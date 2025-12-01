# QSO Predictor
# Copyright (C) 2025 [Peter Hirst/WU2C]
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.


import sys
import subprocess
import importlib.util
import os
import traceback # <--- Added to catch crashes

REQUIRED_PACKAGES = [
    ("PyQt6", "PyQt6"),
    ("requests", "requests"),
    ("numpy", "numpy")
]

def check_and_install():
    print("--- QSO Predictor Launcher ---")
    print("Checking system dependencies...")
    
    for package, import_name in REQUIRED_PACKAGES:
        # Check if installed
        spec = importlib.util.find_spec(import_name)
        
        if spec is None:
            print(f" [ MISSING ] {package} not found. Installing...")
            try:
                # Install via pip
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
                print(f" [ INSTALLED ] {package} installed successfully.")
            except subprocess.CalledProcessError as e:
                print(f" [ ERROR ] Failed to install {package}.")
                print(f" Error details: {e}")
                return False
            except Exception as e:
                print(f" [ ERROR ] Unexpected error installing {package}: {e}")
                return False
        else:
            print(f" [ OK ] {package} is ready.")
    
    print("Dependencies OK.\n")
    return True

def launch_app():
    print("Launching main.py...")
    if not os.path.exists("main.py"):
        print(" [ ERROR ] main.py not found in this folder!")
        return

    try:
        # Run main.py
        result = subprocess.run([sys.executable, "main.py"])
        if result.returncode != 0:
            print(f"Application exited with error code: {result.returncode}")
    except Exception as e:
        print(f"Failed to launch main.py: {e}")

if __name__ == "__main__":
    try:
        if check_and_install():
            launch_app()
    except Exception:
        # Catch ANY crash and print it
        print("\nCRITICAL LAUNCHER CRASH:")
        traceback.print_exc()
    
    # Keep window open no matter what
    print("\n------------------------------------------------")
    input("Press Enter to close this window...")


