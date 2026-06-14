# ──────────────────────────────────────────────────────────────────────────────
# Dockerfile — JCBT Seeing Analysis Pipeline
#
# Base: Ubuntu 22.04 LTS (x86_64)
# Python: 3.11 (via deadsnakes PPA)
# IRAF: v2.17 from Ubuntu repos
# DS9: saods9 from Ubuntu repos (required for pyds9)
# GUI: X11 forwarding for DS9 + IRAF imexam
#
# BUILD:
#   docker build -t jcbt-seeing .
#
# RUN (Fedora / Podman):
#   xhost +SI:localuser:$USER
#   podman run --rm -it \
#     -e DISPLAY=$DISPLAY \
#     --security-opt label=disable \
#     -v /tmp/.X11-unix:/tmp/.X11-unix \
#     -v /path/to/your/data:/data \
#     --network host \
#     jcbt-seeing
# ──────────────────────────────────────────────────────────────────────────────

FROM ubuntu:22.04

# Prevent interactive prompts during apt installs
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

# ── 1. Base tools + deadsnakes PPA ────────────────────────────────────────────
#    add-apt-repository fails in containers (no gpg-agent/D-Bus),
#    so we add the deadsnakes PPA manually.
#    We also enable multiverse for iraf-noao.
RUN sed -i 's/ main$/ main multiverse/' /etc/apt/sources.list \
    && sed -i 's/ universe$/ universe multiverse/' /etc/apt/sources.list \
    && apt-get update && apt-get install -y --no-install-recommends \
    gnupg \
    curl \
    wget \
    ca-certificates \
    && mkdir -p /usr/share/keyrings \
    && curl -fsSL "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0xF23C5A6CF475977595C89F51BA6932366A755776" \
       | gpg --batch --yes --dearmor -o /usr/share/keyrings/deadsnakes.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/deadsnakes.gpg] https://ppa.launchpadcontent.net/deadsnakes/ppa/ubuntu jammy main" \
       > /etc/apt/sources.list.d/deadsnakes.list \
    && apt-get update

# ── 2. System packages ───────────────────────────────────────────────────────
RUN apt-get install -y --no-install-recommends \
    # IRAF + NOAO (from multiverse)
    iraf \
    iraf-noao \
    # SAOImage DS9 + XPA tools (required for pyds9)
    saods9 \
    xpa-tools \
    # Python 3.11 from deadsnakes PPA
    python3.11 \
    python3.11-dev \
    python3.11-tk \
    # X11 display libraries (for DS9 GUI over X11 forwarding)
    libx11-6 \
    libx11-dev \
    libxt-dev \
    libxext-dev \
    libxrender1 \
    libxtst6 \
    libxi6 \
    libxext6 \
    libxcb1 \
    libxcb-util1 \
    # Build tools (needed for pip packages compiled from source, e.g. sep)
    gcc \
    g++ \
    make \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── 3. Make python3.11 the default python3 ───────────────────────────────────
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
    && update-alternatives --set python3 /usr/bin/python3.11

# ── 4. Install pip for python3.11 ────────────────────────────────────────────
RUN curl -fsSL https://bootstrap.pypa.io/get-pip.py | python3.11

# ── 5. Set IRAF environment variables ────────────────────────────────────────
#    Ubuntu's iraf package installs to /usr/lib/iraf
ENV iraf=/usr/lib/iraf/
ENV IRAFARCH=linux64
ENV DISPLAY=:0

# ── 5b. Set user environment for PyRAF ───────────────────────────────────────
#    PyRAF reads $USER during IRAF init (login.cl). Containers don't set this.
#    HOME must point to a writable dir for PyRAF cache and uparm.
ENV USER=observer
ENV HOME=/app

# ── 5a. Fix IRAF binary path mismatch ────────────────────────────────────────
#    Ubuntu puts binaries in bin/ (no arch suffix), but PyRAF with
#    IRAFARCH=linux64 looks for bin.linux64/. Symlinks bridge the gap.
RUN ln -s /usr/lib/iraf/bin /usr/lib/iraf/bin.linux64 \
    && ln -s /usr/lib/iraf/noao/bin /usr/lib/iraf/noao/bin.linux64

# ── 6. Working directory ─────────────────────────────────────────────────────
WORKDIR /app

# ── 7. Install Python dependencies ───────────────────────────────────────────
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# ── 8. Copy pipeline source code ─────────────────────────────────────────────
COPY . .

# ── 9. Create writable directories ────────────────────────────────────────────
#    /data  — where the pipeline downloads FITS/SPE files (config.LOCAL_BASE_DIR)
#    /app/pyraf — PyRAF cache (clcache.sqlite3, uparm, etc.)
RUN mkdir -p /data /app/pyraf && chmod 777 /data /app/pyraf

# ── 10. Default entry point ──────────────────────────────────────────────────
CMD ["python3", "jcbt_seeing_analysis.py"]
