import matplotlib.pyplot as plt
import matplotlib.animation as animation
import pandas as pd
import os
import numpy as np

# --- CONFIGURATION ---
DATA_DIR = "/home/luciferat022/test_final_30dec2025"
CSV_FILE = os.path.join(DATA_DIR, "live_fwhm_data.csv")
SAVE_IMAGE_FILE = os.path.join(DATA_DIR, "fwhm_monitor.png") 

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
        
        if 'FOCUS' in df.columns:
            x_col = 'FOCUS'

        # Clear previous plot
        ax.clear()

        # === FOCUS V-CURVE LOGIC ===
        df['focus_val'] = pd.to_numeric(df[x_col], errors='coerce')
        df = df.dropna(subset=['focus_val'])

        if df.empty:
            return
        
        # 2. Sort by focus value (Required to draw a clean line)
        df_sorted = df.sort_values(by='focus_val')
        
        # 3. Plot
        ax.plot(df_sorted['focus_val'], df_sorted['FWHM_ARCSEC'], 'o-', color='#ff00ff', linewidth=2, markersize=6, label='FWHM vs Focus')
        
        # 4. Formatting
        ax.set_title(f"Focus V-Curve Monitor (N={len(df)})", fontsize=14, color='white')
        ax.set_xlabel("Focus Value", fontsize=12)
        ax.set_ylabel("FWHM (arcsec)", fontsize=12)
        ax.grid(True, linestyle='--', alpha=0.3)
        ax.legend(loc='lower right')
        
        # 5. Highlight the Best Focus (Minimum FWHM)
        min_idx = df_sorted['FWHM_ARCSEC'].idxmin()
        best_focus = df_sorted.loc[min_idx, 'focus_val']
        best_fwhm = df_sorted.loc[min_idx, 'FWHM_ARCSEC']
        
        # Draw a vertical line at the best focus
        ax.axvline(best_focus, color='cyan', linestyle='--', alpha=0.5)
        
        # Annotate the best value
        ax.text(best_focus, best_fwhm + 0.5, f"Best Focus: {best_focus}\nFWHM: {best_fwhm:.2f}\"", 
                color='cyan', fontweight='bold', ha='center', 
                bbox=dict(facecolor='black', alpha=0.7, edgecolor='cyan'))

        # --- SAVE THE PLOT ---
        fig.savefig(SAVE_IMAGE_FILE)

    except Exception as e:
        print(f"Error plotting: {e}")

# Update every 3 seconds
ani = animation.FuncAnimation(fig, animate, interval=3000)

plt.tight_layout()
plt.show()