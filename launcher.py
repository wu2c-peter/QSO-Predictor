# QSO Predictor
# Copyright (C) 2025 Peter Hirst (WU2C)

import logging
import sys
import subprocess
import importlib.util
import os
import traceback

# Simple logging for launcher (runs before main app)
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# --- ADDED: paho (for MQTT) ---
REQUIRED_PACKAGES = [
    ("PyQt6", "PyQt6"),
    ("requests", "requests"),
    ("numpy", "numpy"),
    ("paho-mqtt", "paho") 
]

def check_and_install():
    logger.info("--- QSO Predictor Launcher ---")
    logger.info("Checking system dependencies...")
    
    for package, import_name in REQUIRED_PACKAGES:
        # Check if installed
        try:
            spec = importlib.util.find_spec(import_name)
        except (ImportError, ModuleNotFoundError):
            spec = None
            
        if spec is None:
            logger.info(f" [ MISSING ] {package} not found. Installing...")
            try:
                # Install via pip
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
                logger.info(f" [ INSTALLED ] {package} installed successfully.")
            except subprocess.CalledProcessError as e:
                logger.error(f" [ ERROR ] Failed to install {package}.")
                logger.error(f" Error details: {e}")
                return False
            except Exception as e:
                logger.error(f" [ ERROR ] Unexpected error installing {package}: {e}")
                return False
        else:
            logger.info(f" [ OK ] {package} is ready.")
    
    logger.info("Dependencies OK.\n")
    return True

def launch_app():
    logger.info("Launching main.py...")
    if not os.path.exists("main.py"):
        logger.error(" [ ERROR ] main.py not found in this folder!")
        return

    try:
        # Run main.py
        result = subprocess.run([sys.executable, "main.py"])
        if result.returncode != 0:
            logger.warning(f"Application exited with error code: {result.returncode}")
    except Exception as e:
        logger.error(f"Failed to launch main.py: {e}")

if __name__ == "__main__":
    try:
        if check_and_install():
            launch_app()
    except Exception:
        logger.critical("\nCRITICAL LAUNCHER CRASH:")
        traceback.print_exc()
    
    print("\n------------------------------------------------")
    input("Press Enter to close this window...")