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
SOURCE_DIR = "/mnt/telescope_remote"   # Replace with your remote directory path
LOCAL_DIR = "/home/luciferat022/test_final_30dec2025"  # Replace with your local directory path
LIVE_DATA_CSV = os.path.join(LOCAL_DIR, "live_fwhm_data.csv") 
TEMP_COO_FILE = os.path.join(LOCAL_DIR, "temp_sources.coo")

SLEEP_INTERVAL = 3
pixel_scale = 0.257

def read_spe_data(filepath):
    """
    Basic reader for Princeton Instruments SPE files (v2.x/3.0).
    Reads binary header to find dimensions and data type.
    """
    with open(filepath, 'rb') as f:
        header_bytes = f.read(4100)
        
        # Offset 42: xdim, Offset 656: ydim
        xdim = int(np.frombuffer(header_bytes, dtype=np.uint16, count=1, offset=42)[0])
        ydim = int(np.frombuffer(header_bytes, dtype=np.uint16, count=1, offset=656)[0])
        
        # Offset 108: datatype
        dtype_code = np.frombuffer(header_bytes, dtype=np.int16, count=1, offset=108)[0]
        
        if dtype_code == 0: dt = np.float32
        elif dtype_code == 1: dt = np.int32
        elif dtype_code == 2: dt = np.int16
        elif dtype_code == 3: dt = np.uint16
        else: raise ValueError(f"Unknown SPE data type code: {dtype_code}")
        
        count = xdim * ydim
        data = np.fromfile(f, dtype=dt, count=count)
        
        if data.size != count:
            print(f"Warning: Expected {count} pixels, got {data.size}")
            
        return data.reshape((ydim, xdim))

def save_brightest_as_coo(source_table, filename):
    """Save source table as IRAF coordinate file"""
    x_coords = source_table['x']
    y_coords = source_table['y']
    
    with open(filename, 'w') as f:
        for i, (x, y) in enumerate(zip(x_coords, y_coords), 1):
            f.write(f"{x:.2f} {y:.2f}\n")
    return filename

def extract_iraf_fwhm_average(output_text):
    """
    Parses IRAF psfmeasure output to get FWHM and Ellipticity.
    Handles both single-star ('Full width...') and multi-star ('Average full width...') outputs.
    """
    avg_pattern = r'(?:Average full|Full) width at half maximum \(FWHM\) of ([\d.]+)'
    match_avg = re.search(avg_pattern, output_text)
    
    if match_avg:
        avg_fwhm_iraf = float(match_avg.group(1))
        
        # Extract Individual Star Data (Col, Line, Mag, FWHM, Ellip, PA)
        data_pattern = r'(\d+\.\d+)\s+(\d+\.\d+)\s+(-?\d+\.\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)\s+(-?\d+)'
        matches = re.findall(data_pattern, output_text)
        
        fwhm_values = []
        ellip_values = []
        
        for m in matches:
            try:
                f = float(m[3])
                e = float(m[4])
                fwhm_values.append(f)
                ellip_values.append(e)
            except:
                continue
        
        n_stars = len(fwhm_values)
        avg_ellip = np.mean(ellip_values) if ellip_values else 0.0
        
        if not fwhm_values:
            fwhm_values = [avg_fwhm_iraf]
            n_stars = 1

        return {
            'average_fwhm_pixels': avg_fwhm_iraf,
            'average_ellipticity': avg_ellip,
            'individual_fwhms': np.array(fwhm_values),
            'n_stars': n_stars,
            'average_fwhm_arcsec': avg_fwhm_iraf * pixel_scale
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
    iraf.imred()
    iraf.ccdred()
    iraf.noao()
    iraf.digiphot() 
    iraf.obsutil()
    
    print(f"Watching {SOURCE_DIR} for files...")

    try:
        while True:
            # 1. Scan Remote Directory
            remote_files = os.listdir(SOURCE_DIR)
            
            # 2. Group remote files by base name
            # Structure: {'filename_base': {'has_spe': True/False, 'has_fits': True/False, 'spe_name': '...', 'fits_name': '...'}}
            file_groups = {}
            for f in remote_files:
                base, ext = os.path.splitext(f)
                ext = ext.lower()
                
                if base not in file_groups:
                    file_groups[base] = {'has_spe': False, 'has_fits': False, 'spe_name': None, 'fits_name': None}
                
                if ext == '.spe':
                    file_groups[base]['has_spe'] = True
                    file_groups[base]['spe_name'] = f
                elif ext == '.fits':
                    file_groups[base]['has_fits'] = True
                    file_groups[base]['fits_name'] = f

            # 3. Identify New Work
            processed_files = {f for f in os.listdir(LOCAL_DIR) if f.lower().endswith('.fits')}
            new_tasks = []

            for base, info in file_groups.items():
                expected_local = base + '.fits'
                
                # If the final FITS exists locally, skip it
                if expected_local in processed_files:
                    continue
                
                # PRIORITY LOGIC:
                if info['has_fits']:
                    # Condition 1: Remote FITS exists (Copy it, ignore SPE)
                    new_tasks.append({
                        'source': info['fits_name'],
                        'local': expected_local,
                        'action': 'copy'
                    })
                elif info['has_spe']:
                    # Condition 2: Only SPE exists (Convert it)
                    new_tasks.append({
                        'source': info['spe_name'],
                        'local': expected_local,
                        'action': 'convert'
                    })

            # Sort tasks alphabetically
            new_tasks.sort(key=lambda x: x['source'])

            if new_tasks:
                print(f"\nFound {len(new_tasks)} new file(s) to process. Proceed? (y/n):")
                user_input = input().strip().lower()
                if user_input != 'y':
                    print("Skipping processing.")
                    continue

                for task in new_tasks:
                    source_fname = task['source']
                    local_fname = task['local']
                    action = task['action']
                    
                    source_path = os.path.join(SOURCE_DIR, source_fname)
                    local_path = os.path.join(LOCAL_DIR, local_fname)
                    
                    focus = 0 # Default

                    try:
                        print(f"Processing: {source_fname} ({action})")
                        time.sleep(0.5) 
                        
                        if action == 'convert':
                            # --- SPE CONVERSION MODE ---
                            print(" -> SPE Detected (No matching remote FITS). Converting...")
                            try:
                                data = read_spe_data(source_path)
                                hdu = pyfits.PrimaryHDU(data)
                                hdu.writeto(local_path, overwrite=True)
                                print(" -> Converted and saved.")
                                
                                # Ask for Focus only on manual conversions
                                focus_val = input(f" >> Enter FOCUS value for {source_fname}: ").strip()
                                iraf.ccdhedit(images=local_path, parameter='FOCUS', value=focus_val, type='string')
                                print(f" -> Header updated: FOCUS = {focus_val}")
                                focus = focus_val
                                
                            except Exception as e:
                                print(f"Error converting SPE {source_fname}: {e}")
                                continue
                        else:
                            # --- STANDARD FITS COPY MODE ---
                            shutil.copy2(source_path, local_path)
                            print(f" -> Remote FITS found. Copied to local drive.")

                        # --- DISPLAY & ANALYZE ---
                        d.set(f'file "{local_path}"')
                        d.set('scale', 'zscale')
                        time.sleep(1) 

                        with pyfits.open(local_path) as hdul:
                            header = hdul[0].header
                            img_data = hdul[0].data
                            # Handle 3D cubes vs 2D images
                            if img_data.ndim == 3:
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
                                print(" -> No stars found.")
                                print("Proceed with next file?(y/n):")
                                user_input = input().strip().lower()

                            source_table = Table()
                            source_table['x'] = sources_xy[:, 0] + 1
                            source_table['y'] = sources_xy[:, 1] + 1
                            source_table['flux'] = fluxes

                            source_table1 = source_table[source_table['flux'] < 100000]
                            brightest_15 = source_table1[np.argsort(source_table1['flux'])[::-1][:15]]

                            save_brightest_as_coo(brightest_15, filename=TEMP_COO_FILE)
                        
                        # Fixed the missing comma syntax error here
                        results = capture_iraf_output(
                            iraf.psfmeasure, 
                            local_fname,    
                            display="yes", 
                            wcs='physical',          
                            scale=1, 
                            radius=10,             
                            coords="markall",       
                            imagecur=TEMP_COO_FILE, 
                            #graphcur="dev$null", 
                        )
                        d.set('scale', 'zscale')

                        if results:
                            print(f" -> Measured FWHM: {results['average_fwhm_pixels']:.2f} px")
                            
                            new_row = {
                                'FILENAME': local_fname,
                                'FOCUS': focus if action == 'convert' else 'N/A', # Focus only relevant for SPE
                                'ELLIPTICITY': results['average_ellipticity'],
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
                        
                        print(" -> Launching imexam for manual inspection...")
                        iraf.imexam()
                        print("Proceed with next file?(y/n):")
                        user_input = input().strip().lower()
                        if user_input != 'y':
                            print("Exiting processing loop.")
                            d.set('exit')
                            return

                    except Exception as e:
                        print(f"Skipping {local_fname} - Error processing: {e}")
                        try: iraf.unlearn('psfmeasure') ; iraf.unlearn('imexam')
                        except: pass
                    
            time.sleep(SLEEP_INTERVAL)

    except KeyboardInterrupt:
        print("\nExiting script.")

if __name__ == "__main__":
    main()