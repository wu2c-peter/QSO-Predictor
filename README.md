{\rtf1\ansi\ansicpg1252\cocoartf2867
\cocoatextscaling0\cocoaplatform0{\fonttbl\f0\fnil\fcharset0 HelveticaNeue;}
{\colortbl;\red255\green255\blue255;\red25\green25\blue25;}
{\*\expandedcolortbl;;\cssrgb\c12941\c12941\c12941;}
\margl1440\margr1440\vieww11520\viewh8400\viewkind0
\deftab720
\pard\pardeftab720\partightenfactor0

\f0\fs24 \cf2 \expnd0\expndtw0\kerning0
# QSO Predictor\
\
**QSO Predictor** is a real-time tactical assistant for Amateur Radio digital modes (FT8/FT4). It acts as a "middle-man" between **WSJT-X** and other tools (like GridTracker), using data analytics to predict which stations you can actually contact and recommending the cleanest frequency to transmit on.\
\
---\
\
## \uc0\u55357 \u56960  Key Features\
\
### 1. Smart Probability Score\
Don't waste time calling stations that can't hear you. The app calculates a **Probability Score (0-99%)** based on:\
* **Signal Strength (SNR):** Stronger signals get a higher base score.\
* **PSK Reporter Spots:** Checks if the station is currently hearing other people in your area.\
* **"Freshness" Bonus:** Identifies new, strong signals that haven't been spotted yet (high opportunity).\
* **Pileup Penalty:** Lowers the score if dozens of other stations are already calling them.\
\
### 2. Tactical Band Map (The "Heatmap")\
A visual representation of the band that combines **Local Reality** with **Remote Reality**.\
* **Green/Yellow Bars:** Stations *you* are hearing right now (Height = Signal Strength).\
* **Blue Bars (Foreground):** **Remote QRM**. This shows signals that the *DX Station* is hearing, even if you can't hear them.\
    * *Crucial Feature:* If a Blue Bar covers a clear spot, **do not transmit there**. You will be blocked at the receiving end.\
* **Yellow Dotted Line:** Your current TX frequency.\
* **Green Dashed Line:** The recommended "Best Gap" to transmit in.\
\
### 3. "Widest Gap" Recommendation Engine\
The app scans the entire passband (300Hz\'962700Hz) to find the largest available hole.\
* It avoids your local signals (Green bars).\
* It avoids the DX station's interference (Blue bars).\
* It avoids the target station itself (to prevent stomping).\
* It suggests the center of the widest safe zone.\
\
### 4. High-Performance Table\
* **Live Sorting:** Click headers to sort by SNR, Probability, or Time.\
* **Target Pinning:** Click a station in WSJT-X (or the table) to "Pin" it to the top row.\
* **Visual Status:** See exactly when the app is fetching data from PSK Reporter.\
\
---\
\
## \uc0\u55357 \u57056 \u65039  Installation & Setup\
\
### Prerequisites\
* **Python 3.10+**\
* **WSJT-X** (or JTDX)\
\
### Quick Start\
1.  Run the **`launcher.py`** script:\
    ```bash\
    python launcher.py\
    ```\
    *(This automatically installs required libraries: `PyQt6`, `requests`, `numpy`)*\
\
### Configuration\
1.  **Configure WSJT-X:**\
    * Go to **File** -> **Settings** -> **Reporting**.\
    * UDP Server: `127.0.0.1`\
    * UDP Server Port: `2237`\
    * Check **"Accept UDP Requests"**.\
\
2.  **Configure QSO Predictor:**\
    * Launch the app.\
    * Go to **File** -> **Settings**.\
    * Enter **My Callsign** and **My Grid**.\
    * (Optional) Set **Forwarding Port** to `2238` if you use GridTracker.\
\
---\
\
## \uc0\u55357 \u56522  Reading the Band Map\
\
| Visual Element | Meaning | Action |\
| :--- | :--- | :--- |\
| **Green Bar** | Strong Local Signal (> 0dB) | Avoid. |\
| **Yellow Bar** | Average Local Signal (-10dB) | Avoid. |\
| **Red Bar** | Weak Local Signal (< -20dB) | Avoid if possible. |\
| **Blue Bar** | **Remote QRM** (The DX hears this!) | **CRITICAL: Avoid.** You will be blocked. |\
| **Magenta Line** | Your Target Station | Do not transmit exactly here (Simplex). |\
| **Yellow Line** | Your Current TX Freq | Move this to the Green Line! |\
| **Green Line** | **Recommended TX Freq** | **Click here** in WSJT-X (Shift+Click). |\
\
---\
\
## \uc0\u55357 \u56998  Status & Troubleshooting\
\
* **"Fetching Spots..."**: The app is downloading the latest reception reports from PSK Reporter. This happens automatically when you change bands.\
* **"No Spots"**: The target station hasn't reported hearing anyone recently. (You might still work them if your signal is strong!).\
* **"Rec. DF" is the same for everyone**: This is normal. The "Best Gap" is a global calculation for the band, not specific to one station.\
\
### Common Issues\
* **0Hz Frequency:** Ensure WSJT-X is running and the "Dial Frequency" is visible.\
* **Table Frozen:** The app throttles updates to 50 rows/second to prevent freezing during massive decode bursts. Just wait a second.\
\
---\
\
## License\
**GNU General Public License v3.0**\
Copyright \'a9 2025 [Peter Hirst/WU2C]}