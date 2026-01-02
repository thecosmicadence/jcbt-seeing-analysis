import os
from pathlib import Path

# --- GLOBAL CONFIGURATION ---
# Define the base directory relative to the user's home folder (Works on any Linux machine)
BASE_DIR = Path.home() / "jcbt_observing_data"

# Ensure the directory exists
BASE_DIR.mkdir(parents=True, exist_ok=True)

# Shared Paths
CSV_FILE = BASE_DIR / "live_fwhm_data.csv"
TEMP_COO_FILE = BASE_DIR / "temp_sources.coo"
PLOT_IMAGE_FILE = BASE_DIR / "fwhm_monitor.png"

# Telescope Source (You can change this or make it an argument)
SOURCE_DIR = "/mnt/telescope_remote" 

# Settings
SLEEP_INTERVAL = 3
PIXEL_SCALE = 0.257