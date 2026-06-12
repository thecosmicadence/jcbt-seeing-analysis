import numpy as np
import re
import sys
from io import StringIO
from config import PIXEL_SCALE

def read_spe_data(filepath):
    # [Unchanged from previous code]
    with open(filepath, 'rb') as f:
        header_bytes = f.read(4100)
        xdim = int(np.frombuffer(header_bytes, dtype=np.uint16, count=1, offset=42)[0])
        ydim = int(np.frombuffer(header_bytes, dtype=np.uint16, count=1, offset=656)[0])
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
    # [Unchanged from previous code]
    x_coords = source_table['x']
    y_coords = source_table['y']
    with open(filename, 'w') as f:
        for i, (x, y) in enumerate(zip(x_coords, y_coords), 1):
            f.write(f"{x:.2f} {y:.2f}\n")
    return filename

def extract_iraf_fwhm_average(output_text):
    # [Unchanged from previous code]
    avg_pattern = r'(?:Average full|Full) width at half maximum \(FWHM\) of ([\d.]+)'
    match_avg = re.search(avg_pattern, output_text)
    
    if match_avg:
        avg_fwhm_iraf = float(match_avg.group(1))
        data_pattern = r'(\d+\.\d+)\s+(\d+\.\d+)\s+(-?\d+\.\d+)\s+(\d+\.\d+)\s+(\d+\.\d+)\s+(-?\d+)'
        matches = re.findall(data_pattern, output_text)
        
        fwhm_values = []
        ellip_values = []
        for m in matches:
            try:
                fwhm_values.append(float(m[3]))
                ellip_values.append(float(m[4]))
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
            'average_fwhm_arcsec': avg_fwhm_iraf * PIXEL_SCALE
        }
    return None

def capture_iraf_output(func, *args, **kwargs):
    # [Unchanged from previous code]
    old_stdout = sys.stdout
    sys.stdout = captured_output = StringIO()
    try:
        func(*args, **kwargs)
    finally:
        sys.stdout = old_stdout
        output = captured_output.getvalue()
    return extract_iraf_fwhm_average(output)
