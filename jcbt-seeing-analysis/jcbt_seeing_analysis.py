import astropy.io.fits as pyfits
from astropy.table import Table, Column 
import sep
from scipy.ndimage import maximum_filter
import sys
from pyraf import iraf
import pyds9
import pandas as pd
import os
import time
import numpy as np
import re

import config
from smb_utils import setup_smb_connection, get_smb_connection, select_smb_share, select_remote_folder
from analysis_utils import read_spe_data, save_brightest_as_coo, capture_iraf_output

def main():
    # 1. Interactively establish SMB Connection
    conn = setup_smb_connection()

    # 2. Interactively select the Share Name
    chosen_share = select_smb_share(conn)

    # 3. Interactively select the Remote Folder
    remote_source_dir = select_remote_folder(conn, chosen_share)
    conn.close() # Close it so it doesn't timeout while IRAF is initializing
    
    # 4. Dynamically construct local paths based on the chosen folder
    # Normalize backslashes for basename extraction
    normalized_remote = remote_source_dir.replace('\\', '/')
    remote_folder_name = os.path.basename(normalized_remote.rstrip('/'))
    if not remote_folder_name:
        remote_folder_name = "root_data"
        
    # Sanitize the folder name by removing unusual characters like colons
    remote_folder_name = re.sub(r'[\\/*?:"<>|]', '_', remote_folder_name)
    
    LOCAL_DIR = os.path.join(config.LOCAL_BASE_DIR, remote_folder_name)
    LIVE_DATA_CSV = os.path.join(LOCAL_DIR, "live_fwhm_data.csv") 
    TEMP_COO_FILE = os.path.join(LOCAL_DIR, "temp_sources.coo")

    # 5. Create the local directory if it doesn't exist
    if not os.path.exists(LOCAL_DIR):
        os.makedirs(LOCAL_DIR)
        print(f"Created local directory: {LOCAL_DIR}")
    
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
    
    print(f"Watching remote {remote_source_dir} for files...")

    try:
        while True:
            # Reconnect silently to check for new files
            conn = get_smb_connection()
            if not conn:
                time.sleep(config.SLEEP_INTERVAL)
                continue

            try:
                # Get list of files from the selected remote folder
                file_attributes = conn.listPath(chosen_share, remote_source_dir)
                remote_files = [f.filename for f in file_attributes if not f.isDirectory]
            except Exception as e:
                print(f"Error reading remote directory: {e}")
                conn.close()
                time.sleep(config.SLEEP_INTERVAL)
                continue

            # Group remote files by base name
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

            processed_files = {f for f in os.listdir(LOCAL_DIR) if f.lower().endswith('.fits')}
            new_tasks = []

            for base, info in file_groups.items():
                expected_local = base + '.fits'
                if expected_local in processed_files:
                    continue
                
                if info['has_fits']:
                    new_tasks.append({
                        'source': info['fits_name'],
                        'local': expected_local,
                        'action': 'copy'
                    })
                elif info['has_spe']:
                    new_tasks.append({
                        'source': info['spe_name'],
                        'local': expected_local,
                        'action': 'convert'
                    })

            new_tasks.sort(key=lambda x: x['source'])

            if new_tasks:
                print(f"\nFound {len(new_tasks)} new file(s) to process. Proceed? (y/n):")
                user_input = input().strip().lower()
                if user_input != 'y':
                    print("Skipping processing.")
                    conn.close()
                    time.sleep(config.SLEEP_INTERVAL)
                    continue

                for task in new_tasks:
                    source_fname = task['source']
                    local_fname = task['local']
                    action = task['action']
                    
                    remote_filepath = f"{remote_source_dir}/{source_fname}"
                    local_download_path = os.path.join(LOCAL_DIR, source_fname)
                    local_fits_path = os.path.join(LOCAL_DIR, local_fname)
                    
                    focus = 0 

                    try:
                        print(f"Downloading: {source_fname}...")
                        with open(local_download_path, 'wb') as fp:
                            conn.retrieveFile(chosen_share, remote_filepath, fp)
                        
                        # Close the connection now so it doesn't timeout while we analyze in IRAF
                        conn.close()

                        print(f"Processing: {source_fname} ({action})")
                        time.sleep(0.5) 
                        
                        if action == 'convert':
                            print(" -> SPE Detected. Converting...")
                            try:
                                data = read_spe_data(local_download_path)
                                hdu = pyfits.PrimaryHDU(data)
                                hdu.writeto(local_fits_path, overwrite=True)
                                print(" -> Converted and saved.")
                                
                                # Clean up the downloaded SPE file to save local space
                                os.remove(local_download_path)
                                
                                focus_val = input(f" >> Enter FOCUS value for {source_fname}: ").strip()
                                iraf.ccdhedit(images=local_fits_path, parameter='FOCUS', value=focus_val, type='string')
                                print(f" -> Header updated: FOCUS = {focus_val}")
                                focus = focus_val
                                
                            except Exception as e:
                                print(f"Error converting SPE {source_fname}: {e}")
                                # Reconnect for the next file loop
                                conn = get_smb_connection()
                                continue
                        else:
                            print(f" -> Remote FITS downloaded to local drive.")

                        # --- DISPLAY & ANALYZE ---
                        d.set(f'file "{local_fits_path}"')
                        d.set('scale', 'zscale')
                        time.sleep(1) 

                        with pyfits.open(local_fits_path) as hdul:
                            header = hdul[0].header
                            img_data = hdul[0].data
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
                            if input().strip().lower() != 'y': break

                        source_table = Table()
                        source_table['x'] = sources_xy[:, 0] + 1
                        source_table['y'] = sources_xy[:, 1] + 1
                        source_table['flux'] = fluxes

                        source_table1 = source_table[source_table['flux'] < 60000]   # Can be replaced with 2^(BITPIX)-1
                        #brightest_15 = source_table1[np.argsort(source_table1['flux'])[::-1][:15]]
                        all_valid_stars = source_table1[np.argsort(source_table1['flux'])[::-1]]

                        save_brightest_as_coo(all_valid_stars, filename=TEMP_COO_FILE)
                        
                        results = capture_iraf_output(
                            iraf.psfmeasure, 
                            local_fname,    
                            display="yes", 
                            wcs='physical',          
                            scale=1, 
                            radius=10,             
                            coords="markall",       
                            imagecur=TEMP_COO_FILE, 
                        )
                        d.set('scale', 'zscale')

                        if results:
                            print(f" -> Measured FWHM: {results['average_fwhm_pixels']:.2f} px")
                            
                            new_row = {
                                'FILENAME': local_fname,
                                'FOCUS': focus if action == 'convert' else 'N/A', 
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

                        # Reconnect SMB for the next file in the list
                        conn = get_smb_connection()

                    except Exception as e:
                        print(f"Skipping {local_fname} - Error processing: {e}")
                        try: 
                            iraf.unlearn('psfmeasure') 
                            iraf.unlearn('imexam')
                        except: pass
                        conn = get_smb_connection() # Reconnect after error

            # Ensure connection is closed before sleeping
            if conn:
                try: conn.close()
                except: pass
                
            time.sleep(config.SLEEP_INTERVAL)

    except KeyboardInterrupt:
        print("\nExiting script.")

if __name__ == "__main__":
    main()