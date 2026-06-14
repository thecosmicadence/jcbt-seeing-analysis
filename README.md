# JCBT Seeing Analysis — Docker Setup

## Prerequisites

- **Docker / Podman** installed and running
- **X11** display server:
    - **Linux** — X11 is standard on most desktop installs (GNOME, KDE, XFCE, etc.)
    - **macOS** — Install [XQuartz](https://www.xquartz.org/) (see macOS section below)
- **SAOImage DS9** must be running on your **host** machine before launching the container, since the container connects to it via X11 forwarding.

## Quick Start

### 1. Build the image

```bash
cd /path/to/jcbt-seeing-analysis
docker build -t jcbt-seeing .
```

> **Note:** The first build takes ~10-15 minutes (downloads Ubuntu packages, IRAF, Python 3.11, and pip dependencies). Subsequent builds use Docker layer cache and are fast.

### 2. Run the container

#### Fedora / Podman (recommended for your setup)

```bash
# Allow your user to share X11 display with the container
xhost +SI:localuser:$USER

# Create the local directory for downloaded data (Podman won't auto-create it)
mkdir -p ~/seeing_data

# Run the pipeline interactively
podman run --rm -it \
  -e DISPLAY=$DISPLAY \
  --security-opt label=disable \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  -v ~/seeing_data:/data \
  --network host \
  jcbt-seeing
```

#### Ubuntu / Debian (Docker)

```bash
# Allow Docker containers to access the X11 display
xhost +local:docker

mkdir -p ~/seeing_data

docker run --rm -it \
  -e DISPLAY=$DISPLAY \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  -v ~/seeing_data:/data \
  --network host \
  jcbt-seeing
```

> **Note (Wayland users):** If you are running GNOME on Wayland (default on Ubuntu 22.04+), you may need to run under an Xwayland session or set `DISPLAY=:0` explicitly. Check with `echo $XDG_SESSION_TYPE`.

#### Other Linux distros (Docker)

The Ubuntu/Debian command above works on most distros. Adjust `xhost` and SELinux/AppArmor policies if needed.

#### macOS (Docker Desktop)

macOS does not ship with an X11 server. You need **XQuartz**.

**Step 1: Install XQuartz**

Download and install from [xquartz.org](https://www.xquartz.org/), or via Homebrew:
```bash
brew install --cask xquartz
```
> **Important:** After installing XQuartz, **log out and log back in** (or reboot) for the `DISPLAY` variable to be set correctly.

**Step 2: Allow network connections**

1. Open **XQuartz** → **Preferences** → **Security** tab.
2. Check **"Allow connections from network clients"**.
3. Restart XQuartz.

**Step 3: Run the container**

```bash
# Permit connections from localhost
xhost +localhost

mkdir -p ~/seeing_data

# Get your host IP on the Docker bridge
export HOST_IP=$(ifconfig en0 | grep inet | awk '$1=="inet" {print $2}')

docker run --rm -it \
  -e DISPLAY=$HOST_IP:0 \
  -v ~/seeing_data:/data \
  jcbt-seeing
```

> **⚠️ macOS note:** Docker Desktop for Mac does not support `--network host`. The container connects to your host's XQuartz via TCP (port 6000) instead of a Unix socket. The `HOST_IP` approach above handles this.
>
> If DS9 still cannot connect, try using `host.docker.internal` instead:
> ```bash
> docker run --rm -it \
>   -e DISPLAY=host.docker.internal:0 \
>   -v ~/seeing_data:/data \
>   jcbt-seeing
> ```

The `-v ~/seeing_data:/data` mount maps a directory on your host to `/data` inside the container. Downloaded FITS/SPE files and `live_fwhm_data.csv` will appear in `~/seeing_data/` on your host and persist after the container exits.

> **⚠️ Important:** Podman does **not** auto-create host directories. You must `mkdir` before running. The volume mount must have both host and container paths separated by `:` — writing `-v /path/to/data` alone won't work.

### 3. After you're done

```bash
# Revoke X11 access (optional, for security)
xhost -SI:localuser:$USER   # Podman / Fedora
xhost -local:docker          # Docker / Linux
xhost -localhost             # macOS / XQuartz
```

## Volume Mounts

| Host Path | Container Path | Purpose |
|-----------|---------------|---------|
| `~/seeing_data` | `/data` | Local storage for downloaded FITS/SPE files and results CSV |
| `/tmp/.X11-unix` | `/tmp/.X11-unix` | X11 socket for DS9 GUI forwarding |

## Configuration

`config.py` inside the container has `LOCAL_BASE_DIR = "/data"`, which maps to whatever host directory you mount with `-v`. No changes needed for the default setup.

If you want to use a custom config (e.g. different `PIXEL_SCALE` or `SLEEP_INTERVAL`), mount it at runtime:
```bash
podman run --rm -it \
  -e DISPLAY=$DISPLAY \
  --security-opt label=disable \
  -v /tmp/.X11-unix:/tmp/.X11-unix \
  -v ~/seeing_data:/data \
  -v /path/to/custom/config.py:/app/config.py \
  --network host \
  jcbt-seeing
```

## Troubleshooting

### DS9 won't open / "Please open DS9 first!"
DS9 must be running on your **host** machine. The container connects to the host's DS9 via XPA over the shared X11 socket. Start DS9 on the host before running the container.

### "could not open XWindow display" (Podman/Fedora)
This is usually caused by SELinux blocking X11 socket access. Make sure you:
1. Ran `xhost +SI:localuser:$USER` before starting the container
2. Used `--security-opt label=disable` in the run command
3. Have `$DISPLAY` set correctly (check with `echo $DISPLAY`, usually `:0` or `:1`)

### "Undefined environment variable `USER'" (PyRAF)
This is fixed in the current Dockerfile (`ENV USER=observer`). If you still see it, rebuild the image.

### IRAF tasks fail with "No such file" errors
This usually means the IRAF binary symlinks are missing. The Dockerfile handles this, but if you see issues, verify inside the container:
```bash
ls -la /usr/lib/iraf/bin.linux64
ls -la /usr/lib/iraf/noao/bin.linux64
```

### Network connection to SMB/SSH server fails
The container uses `--network host` (Linux), so it shares your host's network stack. If the remote server is reachable from your host, it should be reachable from the container too.

> On **macOS**, `--network host` is not supported. The container uses Docker's default bridge network, which can reach external hosts but not `localhost` services. Use `host.docker.internal` to reach the host from inside the container.

### macOS: DS9 window doesn't appear / X11 errors
1. Make sure **XQuartz** is installed, running, and you have **logged out/in** after the first install.
2. In XQuartz → Preferences → Security, **"Allow connections from network clients"** must be checked.
3. Run `xhost +localhost` before starting the container.
4. Verify `DISPLAY` is set: `echo $DISPLAY` should print something like `/private/tmp/com.apple.launchd.xxxx/org.xquartz:0`.
5. If using an Apple Silicon Mac, the Docker image (Ubuntu x86_64) runs under Rosetta emulation — this is normal but may be slightly slower.

---

# JCBT Seeing Analysis Pipeline

A Python-based pipeline for real-time seeing analysis and FWHM measurement at the Vainu Bappu Observatory (VBO). This tool automates data retrieval from a remote server, handles file conversion (SPE → FITS), and logs FWHM results to a CSV for live monitoring.

## Prerequisites

* **Server (Data Source):** A machine (Windows or Linux) with the source folder containing `.fits` or `.spe` files.
    * **Windows** — Enable folder sharing (SMB). The pipeline connects via SMB (port 445/139).
    * **Linux** — Enable SSH access (port 22). The pipeline connects via SFTP.
* **Client (Analysis):** Linux PC (e.g., Fedora/Ubuntu) or Docker (see above).
* **Software (native setup, without Docker):**
    * Python 3.11
    * IRAF v2.17 + PyRAF
    * SAOImage DS9 (must be running before launching the pipeline)
    * XPA tools (`xpa-tools` package)

> **Tip:** The Docker setup (documented above) bundles all of these automatically. Use native setup only if you have IRAF already installed on your system.

---

## 1. Server Setup

The pipeline connects to your data server **over the network using Python** (`pysmb` for Windows, `paramiko` for Linux). No manual CIFS mount or `cifs-utils` is required.

### Windows Server
1. Right-click the data folder → **Properties** → **Sharing** → **Advanced Sharing**.
2. Check **Share this folder** → **Apply** → **OK**.
3. Note the server's IP address (run `ipconfig` in Command Prompt).

### Linux Server
1. Ensure the SSH server is running: `sudo systemctl status sshd`
2. Note the server's IP address (run `ip a` or `hostname -I`).

> The pipeline auto-detects whether the server is Windows (SMB) or Linux (SSH) by probing ports 445 and 22.

---

## 2. Installation (Native)

### Step 1: Clone the repository

```bash
git clone https://github.com/thecosmicadence/jcbt-seeing-analysis.git
cd jcbt-seeing-analysis
```

### Step 2: Create a virtual environment

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

### Step 3: Install dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Configure

Edit `config.py` to match your setup:

```python
LOCAL_BASE_DIR = "/path/to/local/data"   # Where downloaded files are saved
SLEEP_INTERVAL = 3                        # Seconds between remote folder checks
PIXEL_SCALE = 0.257                       # Arcsec/pixel for your instrument
```

---

## 3. Usage

### Running the Pipeline

1. **Start DS9** on your machine.
2. Activate the virtual environment and run:

```bash
source .venv/bin/activate
python3 jcbt_seeing_analysis.py
```

3. The script will interactively prompt you for:
    - **Server IP** address
    - **Credentials** (Windows username/password or Linux SSH credentials)
    - **Network share** selection (Windows only)
    - **Remote folder** to monitor (interactive browser)

4. The pipeline then enters a **watch loop** — it polls the remote folder for new files, downloads them, and for each file:
    - Converts `.spe` → `.fits` if needed (prompts for a FOCUS value)
    - Copies `.fits` files directly
    - Displays the image in DS9
    - Detects sources and measures FWHM using IRAF `psfmeasure`
    - Launches `imexam` for manual inspection
    - Appends results to `live_fwhm_data.csv`

### Output

Results are saved to `live_fwhm_data.csv` inside the local data directory with the following columns:

| Column | Description |
| :--- | :--- |
| `FILENAME` | Name of the processed FITS file |
| `FOCUS` | Focus value (for SPE conversions, otherwise `N/A`) |
| `ELLIPTICITY` | Average source ellipticity |
| `FWHM_PIX` | Average FWHM in pixels |
| `FWHM_ARCSEC` | Average FWHM in arcseconds (`FWHM_PIX × PIXEL_SCALE`) |
| `N_STARS` | Number of stars used in the measurement |

---

## Project Structure

```
jcbt-seeing-analysis/
├── jcbt_seeing_analysis.py   # Main pipeline script
├── smb_utils.py              # SMB/SSH connection, share browsing, folder navigation
├── analysis_utils.py         # SPE reader, source detection helpers, IRAF output parser
├── config.py                 # User-editable configuration (paths, pixel scale, timing)
├── requirements.txt          # Python dependencies (pip)
├── Dockerfile                # Containerized setup with IRAF + PyRAF + DS9
├── .dockerignore             # Files excluded from Docker build context
└── README.md
```

---

# Credits

**Developed by the Research Trainees of Vainu Bappu Observatory.**
