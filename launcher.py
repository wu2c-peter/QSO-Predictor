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

# (pip distribution, import name). The install step itself uses
# requirements.txt so this list can't drift behind it again — it went
# four dependencies stale (safetensors, psutil, scipy, pandas), which
# silently disabled IONIS for launcher users.
REQUIRED_PACKAGES = [
    ("PyQt6", "PyQt6"),
    ("requests", "requests"),
    ("numpy", "numpy"),
    ("paho-mqtt", "paho"),
    ("safetensors", "safetensors"),
    ("psutil", "psutil"),
]

def check_and_install():
    logger.info("--- QSO Predictor Launcher ---")
    logger.info("Checking system dependencies...")

    missing = [p for p, name in REQUIRED_PACKAGES
               if importlib.util.find_spec(name) is None]
    if missing and os.path.exists("requirements.txt"):
        logger.info(f" [ MISSING ] {', '.join(missing)} — installing requirements.txt...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install",
                                   "-r", "requirements.txt"])
        except subprocess.CalledProcessError as e:
            logger.error(f" [ ERROR ] pip install -r requirements.txt failed: {e}")
            return False

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
    logger.info("Launching main_v2.py...")
    if not os.path.exists("main_v2.py"):
        logger.error(" [ ERROR ] main_v2.py not found in this folder!")
        return

    try:
        # Run main_v2.py
        result = subprocess.run([sys.executable, "main_v2.py"])
        if result.returncode != 0:
            logger.warning(f"Application exited with error code: {result.returncode}")
    except Exception as e:
        logger.error(f"Failed to launch main_v2.py: {e}")

if __name__ == "__main__":
    try:
        if check_and_install():
            launch_app()
    except Exception:
        logger.critical("\nCRITICAL LAUNCHER CRASH:")
        traceback.print_exc()
    
    print("\n------------------------------------------------")
    input("Press Enter to close this window...")