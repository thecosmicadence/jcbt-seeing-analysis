import matplotlib.pyplot as plt
import matplotlib.animation as animation
import pandas as pd
from matplotlib.dates import DateFormatter

# --- IMPORT SHARED SETTINGS ---
from . import settings 
# We don't need 'import core' anymore unless you use functions from it

def animate(i):
    # Use the shared path!
    if not settings.CSV_FILE.exists():
        plt.gca().clear()
        plt.gca().text(0.5, 0.5, f"Waiting for {settings.CSV_FILE}...", ha='center', color='yellow')
        return

    try:
        df = pd.read_csv(settings.CSV_FILE)
        if df.empty: return

        df['datetime'] = pd.to_datetime(df['UT'], format='%H:%M:%S')
        
        # ... (Your plotting logic remains same) ...
        
        # Save to shared path
        plt.gcf().savefig(settings.PLOT_IMAGE_FILE)

    except Exception as e:
        print(f"Error plotting: {e}")

def main():
    plt.style.use('dark_background')
    fig, ax = plt.subplots(figsize=(10, 5))
    
    ani = animation.FuncAnimation(fig, animate, interval=1000)
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    main()