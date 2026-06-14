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

A Python-based pipeline for real-time seeing analysis and FWHM measurement at the Vainu Bappu Observatory (VBO). This tool automates data retrieval from a remote Windows server to a local Linux client, handles file conversion (SPE to FITS), and generates live plots.

## Prerequisites

* **Server (Data Source):** Windows PC with the source folder containing `.fits` or `.spe` files.
* **Client (Analysis):** Linux PC (e.g., Fedora/Ubuntu).
* **Software:**
    * cifs-utils (must be installed and running on the Linux PC).
    * `uv` (Python package manager) installed on the Linux client.

---

## 1. Network & File Sharing Setup

Before running the scripts, the data folder on the Windows machine must be mounted on the Linux client.

### Step 1: Configure Windows Sharing
1.  On the **Windows PC**, right-click the folder you wish to share.
2.  Navigate to **Properties** -> **Sharing** -> **Advanced Sharing**.
3.  Check the **Share this folder** option.
4.  Click **Apply** -> **OK**.
5.  *Note:* To find the IP address of the Windows machine, open Command Prompt (`cmd`) and run `ipconfig`.

### Step 2: Mount Folder on Linux
On your **Linux PC**, create the mount point (if it does not already exist):

```bash
sudo mkdir -p /mnt/telescope_remote
```
Mount the shared Windows folder using the `cifs` protocol:
```bash
sudo mount -t cifs //(Windows_IP)/(Shared_Folder_Name) /mnt/telescope_remote -o username=WIN_USER,password=WIN_PASS
```
- Replace `(Windows_IP)` and `(Shared_Folder_Name)` with your specific details.
- Replace `WIN_USER` and `WIN_PASS` with the Windows account credentials.

**To unmount the folder later:**
```bash
sudo umount /mnt/telescope_remote
```
---
## 2. Installation & Environment
This project uses `uv` for high-performance dependency management.

### Step 1: Verify uv Installation
Ensure `uv` is installed on your Linux machine:

```bash
uv --version
```

### Step 2: Initialize Project

If setting up the project for the first time:

```bash
# Create and enter the project directory
mkdir jcbt-seeing-analysis
cd jcbt-seeing-analysis

# Initialize uv and pin Python version
uv init
uv python pin 3.11  # Uses Python 3.11

# Create virtual environment
uv venv
```
### Step 3: Install Dependencies

Add required modules (e.g., `astropy`, `matplotlib`, `numpy`) using:

```bash
uv add module_name1 module_name2
```
### Step 4: Activate Environment

Before running any scripts, activate the virtual environment:

```bash
source .venv/bin/activate
```

## 3. Usage

This repository contains two versions of the analysis pipeline depending on the input file format available on the server.

**Select the Correct Version**
| Version | Input Format | Description |
| :--- | :--- | :--- |
| **Version 1 (v1)** | `.fits` | Use this when the server directory already contains pre-processed FITS files. |
| **Version 2 (v2)** | `.spe` | Use this when the server contains raw `.spe` files. This script handles SPE-to-FITS conversion automatically. |

**Running the Analysis**

Run the appropriate Python script for your data type:
```bash
python3 <script_name>.py
```
**Live Plotting**

To visualize the Full Width at Half Maximum (FWHM) in real-time, open a separate terminal, activate the environment, and run:

```bash
python3 plot_fwhm_v1.py
```

# Credits

**Developed by the Research Trainees of Vainu Bappu Observatory.**
