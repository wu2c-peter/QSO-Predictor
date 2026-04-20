# Third-Party Notices

QSO Predictor is distributed under the GNU General Public License v3.0 (see [LICENSE.txt](LICENSE.txt)). This document provides attribution for third-party software, models, and data sources that QSO Predictor relies on or includes.

For a summary of licenses in use across QSO Predictor and its dependencies, see [DEPENDENCY_LICENSES.md](DEPENDENCY_LICENSES.md).

---

## Python Dependencies

QSO Predictor depends on the following Python packages, listed in `requirements.txt`. Each is distributed under its own license terms, reproduced or referenced below.

### Core Dependencies

| Package | Minimum Version | License | Project URL |
|---------|----------------|---------|-------------|
| **PyQt6** | 6.4.0 | GPL-3.0 (or commercial) | https://www.riverbankcomputing.com/software/pyqt/ |
| **paho-mqtt** | 2.0.0 | Eclipse Public License 2.0 | https://www.eclipse.org/paho/ |
| **numpy** | 1.24.0 | BSD-3-Clause | https://numpy.org/ |
| **requests** | 2.28.0 | Apache License 2.0 | https://requests.readthedocs.io/ |

### Local Intelligence Engine

| Package | Minimum Version | License | Project URL |
|---------|----------------|---------|-------------|
| **scipy** | 1.10.0 | BSD-3-Clause | https://scipy.org/ |
| **pandas** | 2.0.0 | BSD-3-Clause | https://pandas.pydata.org/ |

### Optional ML Training

| Package | Minimum Version | License | Project URL |
|---------|----------------|---------|-------------|
| **scikit-learn** | 1.3.0 | BSD-3-Clause | https://scikit-learn.org/ |
| **joblib** | 1.3.0 | BSD-3-Clause | https://joblib.readthedocs.io/ |

### IONIS Propagation Engine

| Package | Minimum Version | License | Project URL |
|---------|----------------|---------|-------------|
| **safetensors** | 0.4.0 | Apache License 2.0 | https://github.com/huggingface/safetensors |

---

## Embedded Models and Weights

### IONIS Propagation Model

QSO Predictor bundles the IonisGate V22-gamma propagation model weights (`ionis/data/ionis_v22_gamma.safetensors`) and configuration (`ionis/data/config_v22.json`).

- **Model author:** Greg Beam (KI7MT)
- **Original project:** [github.com/IONIS-AI](https://github.com/IONIS-AI)
- **License:** GPL-3.0
- **Parameters:** ~205,000
- **Training data:** ~20 million public WSPR (Weak Signal Propagation Reporter) observations, a community amateur radio propagation dataset

QSO Predictor's IONIS integration (`ionis/engine.py`, `ionis/features.py`, `ionis/physics_override.py`) performs pure-numpy inference against the model; it does not include any proprietary dependencies on PyTorch or the original IONIS-AI project infrastructure at runtime.

Use of this model is governed by the GPL-3.0, the same license as QSO Predictor itself.

---

## External Services and Data Sources

QSO Predictor connects to or consumes data from the following third-party services. None of these services are redistributed with QSO Predictor; connections are made at runtime.

### PSK Reporter

- **Service:** [pskreporter.info](https://pskreporter.info)
- **Role:** Provides real-time MQTT-streamed spot data from the global amateur radio reporting network
- **Data model:** Public community-contributed amateur radio propagation reports
- **Attribution:** Use of PSK Reporter data is at the service operator's discretion; QSO Predictor uses the publicly documented MQTT interface

### NOAA Space Weather

- **Service:** NOAA Space Weather Prediction Center public API
- **Role:** Provides real-time solar flux (SFI), Kp/Ap indices, and related geomagnetic conditions used by the IONIS propagation model and displayed in the QSO Predictor status bar
- **Data status:** United States government public-domain data

### Amateur Radio Logging Software (WSJT-X, JTDX)

QSO Predictor interoperates with but does not redistribute WSJT-X or JTDX. Communication is via the documented UDP reporting protocol.

- **WSJT-X:** Developed by Joseph Taylor (K1JT) and contributors. https://wsjt.sourceforge.io/wsjtx.html
- **JTDX:** Fork of WSJT-X maintained by the JTDX team. https://sourceforge.net/projects/jtdx/

---

## Frameworks and Tooling (not redistributed)

QSO Predictor is built and distributed using standard tooling that is not itself bundled with QSO Predictor releases:

- **Python interpreter** — PSF License, https://www.python.org/
- **PyInstaller** (for binary distribution) — GPL-2.0-or-later with exception, https://pyinstaller.org/
- **GitHub Actions** (for CI/CD) — service, not redistributed
- **git** — GPL-2.0, https://git-scm.com/

---

## License Compatibility Notes

QSO Predictor is licensed under **GPL-3.0** (see `LICENSE.txt`). All bundled or runtime-required dependencies are distributed under licenses that are compatible with GPL-3.0 for the purposes of combining and distributing this software:

- **BSD-3-Clause** (numpy, scipy, pandas, scikit-learn, joblib) — permissive, compatible
- **Apache License 2.0** (requests, safetensors) — compatible with GPL-3.0 (note: Apache 2.0 is not forward-compatible with GPL-2.0, but is compatible with GPL-3.0)
- **Eclipse Public License 2.0** (paho-mqtt) — compatible with GPL-3.0 when the EPL-2.0's Secondary License terms apply; paho-mqtt's published license grants these terms
- **GPL-3.0** (PyQt6 under its GPL option, IONIS model) — matching license, fully compatible

No dependency is distributed under a license that conflicts with QSO Predictor's GPL-3.0 terms.

---

## Full License Texts

Full text of licenses referenced above is available at the following canonical sources:

- **GPL-3.0:** See `LICENSE.txt` in this repository, or https://www.gnu.org/licenses/gpl-3.0.txt
- **BSD-3-Clause:** https://opensource.org/licenses/BSD-3-Clause
- **Apache License 2.0:** https://www.apache.org/licenses/LICENSE-2.0
- **Eclipse Public License 2.0:** https://www.eclipse.org/legal/epl-2.0/
- **PSF License:** https://docs.python.org/3/license.html

---

## Acknowledgments

QSO Predictor would not exist without:

- **Greg Beam (KI7MT)** for the IONIS propagation model
- **Joseph Taylor (K1JT)** and the WSJT-X development team for FT8/FT4 and the UDP reporting protocol that makes QSO Predictor possible
- **The JTDX maintainers** for their continued work on the JTDX fork
- **The PSK Reporter community** for building and maintaining the worldwide spot network
- **The amateur radio community** — testers, critics, and operators whose feedback has shaped every release

73 de WU2C
