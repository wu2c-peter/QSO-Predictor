# Licenses in Use

This document lists every license that applies to any code, model, or data that ships with QSO Predictor. For detailed attribution of individual third-party components, see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

---

## QSO Predictor (primary)

**License:** GNU General Public License v3.0 (GPL-3.0)

**Full text:** [LICENSE.txt](LICENSE.txt) in the root of this repository.

**Canonical source:** https://www.gnu.org/licenses/gpl-3.0.txt

**Copyright:** © 2025-2026 Peter Hirst (WU2C)

QSO Predictor, including all source code in this repository except where otherwise noted (see below), is distributed under the terms of the GPL-3.0.

---

## Bundled Models

### IONIS Propagation Model (IonisGate V22-gamma)

**License:** GPL-3.0

**Files:** `ionis/data/ionis_v22_gamma.safetensors`, `ionis/data/config_v22.json`

**Author:** Greg Beam (KI7MT)

**Original source:** https://github.com/IONIS-AI

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md#ionis-propagation-model) for full attribution.

---

## Runtime Dependencies (not bundled; installed separately)

QSO Predictor depends on these packages at runtime. They are installed via `pip install -r requirements.txt` and are not included in this repository. Each is used under its own license, listed below.

| License | Packages | Compatibility with GPL-3.0 |
|---------|----------|---------------------------|
| GPL-3.0 | PyQt6 (under its GPL license option) | Matching license |
| BSD-3-Clause | numpy, scipy, pandas, scikit-learn, joblib | Permissive, compatible |
| Apache License 2.0 | requests, safetensors | Compatible with GPL-3.0 |
| Eclipse Public License 2.0 | paho-mqtt | Compatible with GPL-3.0 (via EPL-2.0 secondary license terms) |

All dependency licenses are compatible with the combined distribution of this software under the GPL-3.0.

---

## External Services (not bundled, no license embedded)

QSO Predictor communicates with these external services at runtime. No code, data, or license terms from these services are redistributed as part of QSO Predictor:

- **PSK Reporter** — https://pskreporter.info (community amateur radio data)
- **NOAA Space Weather Prediction Center** — US government public-domain data
- **WSJT-X / JTDX** — interoperation via documented UDP protocol; not bundled

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md#external-services-and-data-sources) for details.

---

## License Reference Links

Canonical copies of each license used anywhere in QSO Predictor's code, models, or dependencies:

| License | Canonical Source |
|---------|-----------------|
| GPL-3.0 | https://www.gnu.org/licenses/gpl-3.0.txt |
| BSD-3-Clause | https://opensource.org/licenses/BSD-3-Clause |
| Apache License 2.0 | https://www.apache.org/licenses/LICENSE-2.0 |
| Eclipse Public License 2.0 | https://www.eclipse.org/legal/epl-2.0/ |
| PSF License | https://docs.python.org/3/license.html |

---

## What This Document Is Not

This document is a license index, not a legal opinion. If you are distributing a derivative work of QSO Predictor, incorporating QSO Predictor into another project, or relying on QSO Predictor's license terms for any specific legal purpose, you should consult qualified legal counsel.

---

73 de WU2C
