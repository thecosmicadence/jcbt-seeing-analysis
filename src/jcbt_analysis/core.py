import astropy.io.fits as pyfits
import sep
from scipy.ndimage import maximum_filter
import sys
from io import StringIO
from pyraf import iraf
import pyds9
import pandas as pd
import os
import time
import re
import numpy as np
import shutil
from astropy.table import Table

# --- IMPORT SHARED SETTINGS ---
from . import settings

def save_brightest_as_coo(source_table, filename):
    x_coords = source_table['x']
    y_coords = source_table['y']
    
    with open(filename, 'w') as f:
        for i, (x, y) in enumerate(zip(x_coords, y_coords), 1):
            f.write(f"{x:.2f} {y:.2f}\n")
    return filename

def extract_iraf_fwhm_average(output_text):
    avg_pattern = r'Average full width at half maximum \(FWHM\) of ([\d.]+)'
    match = re.search(avg_pattern, output_text)
    
    if match:
        avg_fwhm = float(match.group(1))
        # ... (rest of your parsing logic remains the same) ...
        # Use settings.PIXEL_SCALE here if needed
        return {
            'average_fwhm_pixels': avg_fwhm,
            'n_stars': 0, # Placeholder, populate correctly if parsing individual stars
            'average_fwhm_arcsec': avg_fwhm * settings.PIXEL_SCALE
        }
    return None

def capture_iraf_output(func, *args, **kwargs):
    # ... (Your existing capture logic) ...
    old_stdout = sys.stdout
    sys.stdout = captured_output = StringIO()
    try:
        func(*args, **kwargs)
    finally:
        sys.stdout = old_stdout
        output = captured_output.getvalue()
    return extract_iraf_fwhm_average(output)

def main():
    # Use paths from settings
    if not os.path.exists(settings.SOURCE_DIR):
        print(f"Error: Source directory {settings.SOURCE_DIR} not found.")
        # return  <-- Commented out for testing if not connected to telescope

    # DS9 Check
    try:
        d = pyds9.DS9()
    except Exception:
        print("Please open DS9 first!")
        return

    print("Initializing IRAF...")
    iraf.images()
    iraf.noao()
    iraf.digiphot() 
    iraf.obsutil()
    
    print(f"Watching {settings.SOURCE_DIR}...")
    print(f"Saving data to {settings.CSV_FILE}")

    try:
        while True:
            # Logic to list files
            # NOTE: For testing, ensure these paths exist
            if os.path.exists(settings.SOURCE_DIR):
                source_files = {f for f in os.listdir(settings.SOURCE_DIR) if f.lower().endswith('.fits')}
            else:
                source_files = set()
                
            local_files = {f for f in os.listdir(settings.BASE_DIR) if f.lower().endswith('.fits')}
            new_files = sorted(list(source_files - local_files))

            if new_files:
                # ... (Your processing logic) ...
                for f in new_files:
                    source_path = os.path.join(settings.SOURCE_DIR, f)
                    local_path = os.path.join(settings.BASE_DIR, f) # Use settings.BASE_DIR

                    shutil.copy2(source_path, local_path)
                    
                    # ... (Your image processing code) ...
                    # When saving CSV:
                    new_row = {
                        'FILENAME': f,
                        # ... other data ...
                        'FWHM_ARCSEC': 2.5 # Placeholder for logic
                    }
                    
                    # Write to the SHARED path
                    if not os.path.exists(settings.CSV_FILE):
                        pd.DataFrame([new_row]).to_csv(settings.CSV_FILE, index=False)
                    else:
                        pd.DataFrame([new_row]).to_csv(settings.CSV_FILE, mode='a', header=False, index=False)

            time.sleep(settings.SLEEP_INTERVAL)

    except KeyboardInterrupt:
        print("\nExiting script.")

if __name__ == "__main__":
    main()