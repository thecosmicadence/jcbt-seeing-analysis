import matplotlib.pyplot as plt
import matplotlib.animation as animation
import pandas as pd
import os
from matplotlib.dates import DateFormatter

# --- CONFIGURATION ---
DATA_DIR = "/home/luciferat022/telescope_data"
CSV_FILE = os.path.join(DATA_DIR, "live_fwhm_data.csv")
SAVE_IMAGE_FILE = os.path.join(DATA_DIR, "fwhm_monitor.png") # Image will be saved here

# Setup the plot style
plt.style.use('dark_background')
fig, ax = plt.subplots(figsize=(10, 5))

def animate(i):
    if not os.path.exists(CSV_FILE):
        ax.clear()
        ax.text(0.5, 0.5, "Waiting for data...", ha='center', color='yellow')
        return

    try:
        # Read the CSV
        df = pd.read_csv(CSV_FILE)

        if df.empty:
            return

        # Convert UT to datetime objects
        df['datetime'] = pd.to_datetime(df['UT'], format='%H:%M:%S')

        # Clear and redraw
        ax.clear()

        # Plot FWHM (Arcsec)
        ax.plot(df['datetime'], df['FWHM_ARCSEC'], 'o-', color='#00ff00', linewidth=2, markersize=5, label='FWHM (arcsec)')

        # Formatting
        ax.set_title(f"Real-Time Seeing Monitor (N={len(df)})", fontsize=14, color='white')
        ax.set_xlabel("UT Time", fontsize=12)
        ax.set_ylabel("FWHM (arcsec)", fontsize=12)
        ax.grid(True, linestyle='--', alpha=0.3)
        ax.legend(loc='upper right')

        # Format X-axis to show HH:MM:SS
        ax.xaxis.set_major_formatter(DateFormatter('%H:%M:%S'))
        fig.autofmt_xdate()

        # Add current value text
        last_val = df['FWHM_ARCSEC'].iloc[-1]
        ax.text(df['datetime'].iloc[-1], last_val + 0.2, f"{last_val:.2f}\"", color='cyan', fontweight='bold')

        # --- SAVE THE PLOT TO DISK ---
        # This overwrites the file every 3 seconds so you always have the latest view
        fig.savefig(SAVE_IMAGE_FILE)

    except Exception as e:
        print(f"Error plotting: {e}")

# Update every 3000ms (3 seconds)
ani = animation.FuncAnimation(fig, animate, interval=3000)

plt.tight_layout()
plt.show()
