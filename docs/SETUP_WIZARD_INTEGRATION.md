# Setup Wizard Integration Guide
## QSO Predictor v2.2.0 — Auto-Discovery & Configuration

**Date:** February 7, 2026  
**Module:** `setup_wizard.py` (new file, 1073 lines)  
**Dependencies:** None new — uses only stdlib + PyQt6 (already in requirements.txt)

---

## What It Does

Three-phase auto-detection:

1. **Phase 1 — Config File Reader**: Scans for WSJT-X and JTDX `.ini` files on disk, extracts callsign, grid, UDP IP/port
2. **Phase 2 — Port Scanner**: Detects which UDP ports (2230-2260) are in use and by what process
3. **Phase 3 — Running App Detector**: Identifies running ham radio apps (JTAlert, GridTracker, N3FJP, HRD, etc.)

Then the **SetupAnalyzer** combines all three into a single `SetupRecommendation` with warnings and notes.

### Config File Locations (from research + WSJT-X source code)

| Platform | WSJT-X | JTDX |
|----------|--------|------|
| Windows | `%LOCALAPPDATA%\WSJT-X\WSJT-X.ini` | `%LOCALAPPDATA%\JTDX\JTDX.ini` |
| macOS | `~/Library/Preferences/WSJT-X/WSJT-X.ini` | `~/Library/Preferences/JTDX/JTDX.ini` |
| Linux | `~/.config/WSJT-X/WSJT-X.ini` | `~/.config/JTDX/JTDX.ini` |

Multi-instance WSJT-X: `%LOCALAPPDATA%\WSJT-X - <RIGNAME>\WSJT-X - <RIGNAME>.ini`

**Fallback search**: If standard paths find nothing, the module searches config parent directories
(AppData, ~/Library, ~/.config etc.) up to 3 levels deep for any `.ini` file with "WSJT" or "JTDX"
in the filename or parent directory name. These are distinctive enough names that collision risk is
essentially zero, so the broader search is safe and fast.

### QSettings Keys (from Configuration.cpp source)

- `MyCall` — Callsign
- `MyGrid` — Grid locator
- `UDPServerPort` — UDP port (default 2237)
- `UDPServerAddress` — UDP IP
- `AcceptUDPRequests` — Whether UDP is enabled

---

## Integration Points (3 changes to existing code)

### 1. First-Run Hook in `main_v2.py`

**Replace** the existing `_check_first_run_config()` method (around line 746) with:

```python
def _check_first_run_config(self):
    """Check if this is a first run and offer auto-configuration."""
    from setup_wizard import is_first_run, show_setup_wizard
    
    if not is_first_run(self.config):
        return
    
    # Show the setup wizard
    result = show_setup_wizard(parent=self, first_run=True)
    
    if result:
        # Apply detected configuration
        if result['callsign']:
            self.config.set('ANALYSIS', 'my_callsign', result['callsign'])
        if result['grid']:
            self.config.set('ANALYSIS', 'my_grid', result['grid'])
        if result['udp_ip']:
            self.config.set('NETWORK', 'udp_ip', result['udp_ip'])
        if result['udp_port']:
            self.config.set('NETWORK', 'udp_port', str(result['udp_port']))
        
        self.config.save()
        logger.info(f"Setup wizard applied: call={result['callsign']}, "
                   f"grid={result['grid']}, udp={result['udp_ip']}:{result['udp_port']}")
    else:
        # User chose manual — show existing settings dialog or show a brief message
        QMessageBox.information(
            self, "Manual Setup",
            "You can configure QSO Predictor at any time via File → Settings.\n\n"
            "At minimum, set your callsign and grid, and ensure the UDP port "
            "matches your WSJT-X/JTDX configuration."
        )
```

### 2. Auto-Detect Button in `settings_dialog.py`

**Add** to the Network tab (or Station tab):

```python
# In the Network tab setup, add after the existing UDP widgets:
btn_auto_detect = QPushButton("🔍 Auto-Detect")
btn_auto_detect.setToolTip("Scan for WSJT-X/JTDX and detect optimal settings")
btn_auto_detect.clicked.connect(self._on_auto_detect)
network_layout.addWidget(btn_auto_detect)

# ...

def _on_auto_detect(self):
    """Run auto-detection and offer to apply results."""
    from setup_wizard import show_setup_wizard
    
    result = show_setup_wizard(parent=self, first_run=False)
    if result:
        # Update the settings dialog fields with detected values
        if result['callsign'] and hasattr(self, 'callsign_input'):
            self.callsign_input.setText(result['callsign'])
        if result['grid'] and hasattr(self, 'grid_input'):
            self.grid_input.setText(result['grid'])
        if result['udp_ip'] and hasattr(self, 'udp_ip_input'):
            self.udp_ip_input.setText(result['udp_ip'])
        if result['udp_port'] and hasattr(self, 'udp_port_input'):
            self.udp_port_input.setValue(result['udp_port'])
```

### 3. Menu Item (optional but nice)

**Add** to the Tools menu in `main_v2.py`:

```python
# In the menu setup section:
auto_detect_action = tools_menu.addAction("Auto-Detect Configuration...")
auto_detect_action.triggered.connect(self._on_auto_detect_config)

def _on_auto_detect_config(self):
    """Run auto-detect from the Tools menu."""
    from setup_wizard import show_setup_wizard
    
    result = show_setup_wizard(parent=self, first_run=False)
    if result:
        if result['callsign']:
            self.config.set('ANALYSIS', 'my_callsign', result['callsign'])
        if result['grid']:
            self.config.set('ANALYSIS', 'my_grid', result['grid'])
        if result['udp_ip']:
            self.config.set('NETWORK', 'udp_ip', result['udp_ip'])
        if result['udp_port']:
            self.config.set('NETWORK', 'udp_port', str(result['udp_port']))
        self.config.save()
        
        QMessageBox.information(self, "Configuration Applied",
            f"Settings updated:\n"
            f"  Callsign: {result['callsign']}\n"
            f"  Grid: {result['grid']}\n"
            f"  UDP: {result['udp_ip']}:{result['udp_port']}\n\n"
            "Restart QSO Predictor for network changes to take effect."
        )
```

---

## Architecture Notes

### No New Dependencies
The module avoids `psutil` (which was originally discussed) in favor of:
- `netstat` / `lsof` / `ss` for port scanning (platform-native)
- `tasklist` / `ps` for process detection (platform-native)
- `socket.bind()` as fallback for port-in-use checks

This means **no changes to requirements.txt** and no new PyInstaller concerns.

### Thread Safety
The scanning runs in a `QThread` (ScanWorker) so the wizard dialog stays responsive.
Config file reads are fast (<100ms typically), but `netstat`/`tasklist` can take a few seconds.

### Read-Only
The module **never writes to** WSJT-X/JTDX config files. It only reads them.

### Graceful Degradation
- If no config files found → wizard still shows with empty fields for manual entry
- If port scan fails → skips that section, no crash
- If process detection fails → skips running app detection
- Every detection step is wrapped in try/except

---

## Testing Checklist

Before release:

- [ ] Test on Windows with WSJT-X installed (standard path)
- [ ] Test on Windows with JTDX installed
- [ ] Test on Windows with both installed
- [ ] Test on Windows with no ham apps installed (should degrade gracefully)
- [ ] Test fallback search: rename WSJT-X dir to non-standard name, verify fallback finds it
- [ ] Test with JTAlert running (should detect and warn about multicast)
- [ ] Test on macOS (config path detection)
- [ ] Test multi-instance WSJT-X detection
- [ ] Test first-run flow (rename/delete config, relaunch)
- [ ] Test Auto-Detect button from Settings dialog
- [ ] Test with port 2237 already in use (should recommend alternate)
- [ ] Verify no writes to WSJT-X/JTDX config files

---

## Version Assignment

This feature is a natural fit for **v2.2.0** since it's a significant new user-facing feature
(not a bug fix or incremental improvement on existing features).

Alternatively, if you want to batch it with other pending work, it could wait.
Your call on timing, Peter!
