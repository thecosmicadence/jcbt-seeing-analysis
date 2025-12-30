import astropy.io.fits as pyfits
import matplotlib as mpl
import astropy.units as u
from astropy.table import Table, Column 
from matplotlib.gridspec import GridSpec as GR
from photutils.aperture import CircularAperture
import sep
from scipy.ndimage import maximum_filter
import sys
from io import StringIO
from pyraf import iraf
import pyds9
import pandas as pd
import glob
import os
import time
import re
import numpy as np
from astropy.wcs import WCS
import shutil

# --- CONFIGURATION ---
SOURCE_DIR = "/mnt/telescope_remote" 
LOCAL_DIR = "/home/luciferat022/29Dec2025_JCBT" 
LIVE_DATA_CSV = os.path.join(LOCAL_DIR, "live_fwhm_data.csv") 
TEMP_COO_FILE = os.path.join(LOCAL_DIR, "temp_sources.coo")

SLEEP_INTERVAL = 3
pixel_scale = 0.257

def save_brightest_as_coo(source_table, filename):
    """Save source table as IRAF coordinate file"""
    x_coords = source_table['x']
    y_coords = source_table['y']
    
    with open(filename, 'w') as f:
        for i, (x, y) in enumerate(zip(x_coords, y_coords), 1):
            f.write(f"{x:.2f} {y:.2f}\n")
    return filename

def extract_iraf_fwhm_average(output_text):
    """Extract average FWHM from IRAF psfmeasure terminal output"""
    avg_pattern = r'Average full width at half maximum \(FWHM\) of ([\d.]+)'
    match = re.search(avg_pattern, output_text)
    
    if match:
        avg_fwhm = float(match.group(1))
        fwhm_pattern = r'\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)'
        fwhm_matches = re.findall(fwhm_pattern, output_text)
        
        individual_fwhms = []
        for match in fwhm_matches:
            try:
                fwhm_val = float(match[4])
                if 1.0 <= fwhm_val <= 10.0:
                    individual_fwhms.append(fwhm_val)
            except:
                continue
        
        return {
            'average_fwhm_pixels': avg_fwhm,
            'individual_fwhms': np.array(individual_fwhms),
            'n_stars': len(individual_fwhms),
            'average_fwhm_arcsec': avg_fwhm * pixel_scale
        }
    return None

def capture_iraf_output(func, *args, **kwargs):
    """Capture IRAF stdout -> parse average"""
    old_stdout = sys.stdout
    sys.stdout = captured_output = StringIO()
    
    try:
        func(*args, **kwargs)
    finally:
        sys.stdout = old_stdout
        output = captured_output.getvalue()
    
    return extract_iraf_fwhm_average(output)

def main():
    if not os.path.exists(LOCAL_DIR):
        os.makedirs(LOCAL_DIR)

    if not os.path.exists(SOURCE_DIR):
        print(f"Error: Source directory {SOURCE_DIR} not found.")
        return
    
    os.chdir(LOCAL_DIR)
    
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
    
    print(f"Watching {SOURCE_DIR}...")

    try:
        while True:
            source_files = {f for f in os.listdir(SOURCE_DIR) if f.lower().endswith('.fits')}
            local_files = {f for f in os.listdir(LOCAL_DIR) if f.lower().endswith('.fits')}
            new_files = sorted(list(source_files - local_files))

            if new_files:
                print(f"\nFound {len(new_files)} new file(s) {new_files} to process. Proceed? (y/n):")
                user_input = input().strip().lower()
                if user_input != 'y':
                    print("Skipping processing.")
                    continue

                for f in new_files:
                    source_path = os.path.join(SOURCE_DIR, f)
                    local_path = os.path.join(LOCAL_DIR, f)

                    try:
                        print(f"Processing: {f}")
                        time.sleep(0.5) 
                        shutil.copy2(source_path, local_path)
                        print(f" -> Copied to local drive")
                    except Exception as e:
                        print(f"Error copying file: {e}")
                        continue 

                    try:
                        d.set(f'file "{local_path}"')
                        d.set('scale', 'zscale')
                        time.sleep(1) 

                        with pyfits.open(local_path) as hdul:
                            header = hdul[0].header
                            # --- FIX: Extracts only HH:MM:SS from DATE-OBS ---
                            raw_ut = header.get('DATE-OBS')
                            # Convert to string, replace T with space (for ISO format), and grab the last part (Time)
                            ut = str(raw_ut).replace('T', ' ').split()[-1]

                            img_data = hdul[0].data
                            if len(img_data.shape) == 3:
                                img_2d = img_data[0].astype(np.float32)
                            else:
                                img_2d = img_data.astype(np.float32)

                            bkg = sep.Background(img_2d)
                            thresh = bkg.globalback + 3.0 * bkg.globalrms
                            img_clean = img_2d - bkg

                            neighborhood_size = 11
                            local_maxima = maximum_filter(img_clean, size=neighborhood_size) == img_clean
                            peaks = np.argwhere(local_maxima & (img_clean > thresh))
                            sources_xy = peaks[:, [1, 0]]
                            fluxes = img_clean[peaks[:, 0], peaks[:, 1]]

                            print(f" -> Sources detected: {len(sources_xy)}")

                            if len(sources_xy) == 0:
                                print(" -> No stars found. Skipping IRAF.")
                                continue

                            source_table = Table()
                            source_table['x'] = sources_xy[:, 0] + 1
                            source_table['y'] = sources_xy[:, 1] + 1
                            source_table['flux'] = fluxes

                            source_table1 = source_table[source_table['flux'] < 100000]
                            brightest_15 = source_table1[np.argsort(source_table1['flux'])[::-1][:15]]

                            save_brightest_as_coo(brightest_15, filename=TEMP_COO_FILE)
                        
                        results = capture_iraf_output(
                            iraf.psfmeasure, 
                            f, 
                            display="no",           
                            scale=1, 
                            radius=10,             
                            coords="markall",       
                            imagecur=TEMP_COO_FILE, 
                            graphcur="dev$null",   # <--- The fix for the hanging window
                            wcs="logical"
                        )
                        
                        if results:
                            print(f" -> Measured FWHM: {results['average_fwhm_pixels']:.2f} px")
                            
                            new_row = {
                                'FILENAME': f,
                                'UT': ut,
                                'FWHM_PIX': results['average_fwhm_pixels'],
                                'FWHM_ARCSEC': results['average_fwhm_arcsec'],
                                'N_STARS': results['n_stars']
                            }
                            
                            if not os.path.exists(LIVE_DATA_CSV):
                                pd.DataFrame([new_row]).to_csv(LIVE_DATA_CSV, index=False)
                            else:
                                pd.DataFrame([new_row]).to_csv(LIVE_DATA_CSV, mode='a', header=False, index=False)
                        else:
                            print(" -> No valid FWHM returned from IRAF.")

                        iraf.imexam()
                        print("Proceed with next file?(y/n):")
                        user_input = input().strip().lower()
                        if user_input != 'y':
                            print("Exiting processing loop.")
                            return

                    except Exception as e:
                        print(f"Skipping {f} - Error processing: {e}")
                        try: iraf.unlearn('psfmeasure') ; iraf.unlearn('imexam')
                        except: pass
                    
            time.sleep(SLEEP_INTERVAL)

    except KeyboardInterrupt:
        print("\nExiting script.")

if __name__ == "__main__":
    main()