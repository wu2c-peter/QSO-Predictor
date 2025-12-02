# QSO Predictor
# Copyright (C) 2025 [Peter Hirst/WU2C]

import sys
import subprocess
import importlib.util
import os
import traceback

# --- ADDED: paho (for MQTT) ---
REQUIRED_PACKAGES = [
    ("PyQt6", "PyQt6"),
    ("requests", "requests"),
    ("numpy", "numpy"),
    ("paho-mqtt", "paho") 
]

def check_and_install():
    print("--- QSO Predictor Launcher ---")
    print("Checking system dependencies...")
    
    for package, import_name in REQUIRED_PACKAGES:
        # Check if installed
        try:
            spec = importlib.util.find_spec(import_name)
        except (ImportError, ModuleNotFoundError):
            spec = None
            
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
        print("\nCRITICAL LAUNCHER CRASH:")
        traceback.print_exc()
    
    print("\n------------------------------------------------")
    input("Press Enter to close this window...")