# QSO Predictor v2.0 - Integration Guide

This guide shows the minimal changes needed to integrate Local Intelligence into your existing main.py.

## Quick Start

Add these changes to your main.py:

### 1. Add Import (near top of file)

```python
# After existing imports, add:
from local_intel_integration import LocalIntelligence
from local_intel import PathStatus
```

### 2. Initialize in MainWindow.__init__()

```python
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # ... existing initialization code ...
        
        # === ADD THIS SECTION ===
        # Initialize Local Intelligence (after UI setup, before show())
        try:
            self.local_intel = LocalIntelligence(
                my_callsign=self.settings.value("my_callsign", "")
            )
            self.local_intel.setup(self)
            
            # Add menu items (if you have a Tools menu)
            if hasattr(self, 'tools_menu'):
                self.local_intel.add_menu_items(self.tools_menu)
        except Exception as e:
            print(f"Local Intelligence disabled: {e}")
            self.local_intel = None
        # === END ADDITION ===
        
        self.show()
```

### 3. Hook into Target Selection

When the user selects a DX station (e.g., clicks on a CQ in the decode list):

```python
def on_target_selected(self, callsign, grid=None):
    """Called when user selects a DX target."""
    # ... existing target handling ...
    
    # === ADD THIS ===
    if self.local_intel:
        self.local_intel.set_target(callsign, grid)
    # === END ADDITION ===
```

### 4. Hook into UDP Decode Handler

In your UDP decode callback (where you receive decodes from WSJT-X):

```python
def on_decode_received(self, decode_data):
    """Called for each decode from WSJT-X UDP."""
    # ... existing decode handling ...
    
    # === ADD THIS ===
    if self.local_intel:
        self.local_intel.process_decode({
            'callsign': decode_data.get('callsign'),
            'snr': decode_data.get('snr'),
            'frequency': decode_data.get('frequency'),
            'message': decode_data.get('message'),
            'dt': decode_data.get('dt', 0.0),
            'mode': decode_data.get('mode', 'FT8'),
        })
    # === END ADDITION ===
```

### 5. Hook into Path Status Updates

When your path indicator changes:

```python
def update_path_status(self, status_string):
    """Called when path status changes."""
    # ... existing path handling ...
    
    # === ADD THIS ===
    if self.local_intel:
        # Map your status string to PathStatus enum
        status_map = {
            'CONNECTED': PathStatus.CONNECTED,
            'Path Open': PathStatus.PATH_OPEN,
            'No Path': PathStatus.NO_PATH,
        }
        path_status = status_map.get(status_string, PathStatus.UNKNOWN)
        self.local_intel.set_path_status(path_status)
    # === END ADDITION ===
```

### 6. Clean Shutdown

In your close event handler:

```python
def closeEvent(self, event):
    """Handle application close."""
    # === ADD THIS ===
    if self.local_intel:
        self.local_intel.shutdown()
    # === END ADDITION ===
    
    # ... existing cleanup ...
    event.accept()
```

---

## Optional Enhancements

### Access Predictions Programmatically

```python
# Get current prediction
if self.local_intel:
    prediction = self.local_intel.get_prediction()
    if prediction:
        print(f"Success probability: {prediction['probability']:.0%}")
        print(f"Confidence: {prediction['confidence']}")

# Get strategy recommendation
if self.local_intel:
    strategy = self.local_intel.get_strategy()
    if strategy:
        print(f"Recommended action: {strategy['action']}")
        print(f"Reasons: {', '.join(strategy['reasons'])}")
```

### Enable Purist Mode (No Internet)

```python
# Disable PSK Reporter, use only local data
if self.local_intel:
    self.local_intel.purist_mode = True
```

### Show/Hide Panel Programmatically

```python
if self.local_intel:
    self.local_intel.is_enabled = False  # Hide panel
    self.local_intel.is_enabled = True   # Show panel
```

### React to Model Staleness

```python
# Connect to the signal
if self.local_intel:
    self.local_intel.models_stale.connect(self.on_models_stale)

def on_models_stale(self, stale_models):
    """Called when models need retraining."""
    self.statusBar().showMessage(
        f"ML models need retraining: {', '.join(stale_models)}", 
        10000
    )
```

---

## File Structure After Integration

```
qso-predictor/
├── main.py                    # Modified (6 small additions)
├── local_intel_integration.py # NEW - main integration class
├── training_manager.py        # NEW - training subprocess manager
├── insights_panel.py          # NEW - UI panel
├── training_dialog.py         # NEW - training dialog
├── local_intel/               # NEW - core engine
│   ├── __init__.py
│   ├── models.py
│   ├── log_discovery.py
│   ├── log_parser.py
│   ├── session_tracker.py
│   ├── model_manager.py
│   └── predictor.py
├── training/                  # NEW - ML training
│   ├── __init__.py
│   ├── feature_builders.py
│   └── trainer_process.py
└── ... (existing files unchanged)
```

---

## Troubleshooting

### Panel Not Showing
- Check that `self.local_intel.setup(self)` is called after UI initialization
- The panel docks to the right side by default

### Models Not Training
- Ensure WSJT-X or JTDX has created all.txt files
- Check `~/.qso-predictor/models/` for output
- Run training manually to see errors

### Import Errors
- Install dependencies: `python -m pip install -r requirements.txt`
- Ensure all files are in correct locations

### Testing Without Full Integration
```python
# Quick test in Python console
from local_intel import SessionTracker, LogFileDiscovery

# Test log discovery
discovery = LogFileDiscovery()
files = discovery.discover_all_files()
print(f"Found {len(files)} log files")

# Test session tracking
tracker = SessionTracker("W1ABC")
tracker.set_target("JA1XYZ")
print(f"Target set: {tracker.target_session.callsign}")
```
