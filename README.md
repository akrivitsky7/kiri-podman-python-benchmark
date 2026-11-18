# Kiri vs. Podman on Linux: A Python Benchmarking Tool for Different Distributions

A lightweight, reproducible Python tool for comparing **Kiri** and **Podman** command latency on your own Linux system. Tested on **Fedora 45**, **CachyOS**, and **Lubuntu 26.04 LTS**; other distributions may work with an appropriate container-engine installation.

**Author:** Anatoly S. Krivitsky, Ph.D. · November 2026

**Purpose:** Provide a tool, **not a verdict** about which container engine is better. Run it on your system and evaluate the results yourself.

## What it measures

The script [`compare_kiri_podman_vms.py`](compare_kiri_podman_vms.py) times two complete CLI operations:

- **Container listing:** `ps` (Kiri's Docker-compatible CLI or `podman ps`).
- **Short-lived container execution:** `run --rm --network none docker.io/library/alpine:3.22 /bin/true`.

Each execution includes CLI and container-management overhead. `/bin/true` exits immediately, and the Alpine image is pulled **before** timing begins. The script uses `time.perf_counter_ns()`, runs warm-ups, and records the **minimum, maximum, mean, median, standard deviation, and individual samples** in JSON. `--compare` reads two JSON results and compares median latencies.

**Requirements:** Linux, Python **3.10+**, working Kiri and/or Podman installations, and internet access for the initial image pull. **No `pip` dependencies.**

## Install the container engines (if needed)

### Fedora 45

```bash
sudo dnf install podman
# Download Kiri's RPM from its official release site, then:
sudo dnf install ./kiri-0.2.1-1.x86_64.rpm
sudo kiri host-access "$USER"
```

### CachyOS

```bash
sudo pacman -Syu
sudo pacman -S --needed podman
# Requires the paru AUR helper; review the PKGBUILD before installing:
paru -S kiri-bin
sudo kiri host-access "$USER"
```

CachyOS installs Kiri via the community-maintained **Arch User Repository (AUR)** package `kiri-bin`. In the tested installation, its Docker-compatible client resides at `/usr/lib/kiri/docker`, rather than `/usr/libexec/kiri/docker` on Fedora and Lubuntu.

### Lubuntu 26.04 LTS

```bash
sudo apt update
sudo apt install -y podman curl ca-certificates
# Review the remote installation script before running it:
curl -fsSL https://runkiri.com/install.sh | bash
sudo kiri host-access "$USER"
```

If Kiri access is not effective immediately, log out and back in. **Security:** Membership in the `kiri` group grants root-equivalent container-management privileges.

## Run the benchmark

Place `compare_kiri_podman_vms.py` in your working directory. The commands below run **three warm-ups** (default) and **30 measured iterations per operation**. Use the same conditions for both engines.

### Fedora 45

```bash
python3 compare_kiri_podman_vms.py --engine kiri --runs 30 --output kiri_fedora45_30.json
python3 compare_kiri_podman_vms.py --engine podman --runs 30 --output podman_fedora45_30.json
python3 compare_kiri_podman_vms.py --compare kiri_fedora45_30.json podman_fedora45_30.json
```

### CachyOS

```bash
python3 compare_kiri_podman_vms.py --engine kiri --kiri-cli /usr/lib/kiri/docker --runs 30 --output kiri_cachyos_30.json
python3 compare_kiri_podman_vms.py --engine podman --runs 30 --output podman_cachyos_30.json
python3 compare_kiri_podman_vms.py --compare kiri_cachyos_30.json podman_cachyos_30.json
```

### Lubuntu 26.04 LTS

```bash
python3 compare_kiri_podman_vms.py --engine kiri --runs 30 --output kiri_lubuntu2604_30.json
python3 compare_kiri_podman_vms.py --engine podman --runs 30 --output podman_lubuntu2604_30.json
python3 compare_kiri_podman_vms.py --compare kiri_lubuntu2604_30.json podman_lubuntu2604_30.json
```

### Verify that Kiri really is Kiri

Some Linux setups provide a `docker` command that invokes Podman. To avoid benchmarking Podman twice, the script **forces Kiri's Unix socket** (`/run/kiri/docker.sock`) and checks the server identity before timing. Successful verification prints:

```text
Verified: Docker-compatible server is Kiri.
```

The Kiri test stops if this check fails. Use `--kiri-cli /path/to/docker` when the bundled client is installed at a different path.

## Customize and interpret

```bash
python3 compare_kiri_podman_vms.py --help
```

Adjust `--runs` and `--warmups` as needed. Review the JSON files for individual timings and outliers; **median latency** is typically more robust to occasional scheduling delays than the mean.

**Scope:** These tests measure complete container-management command latency, **not** application throughput, builds, networking, memory efficiency, security, or production reliability. Different systems and workloads may produce different results. **Decide for yourself.**

## License and Use

Copyright (c) 2026 Anatoly S. Krivitsky, Ph.D.  
All rights reserved.

Permission is granted, free of charge, to use, copy, distribute, and publish this code, provided that the copyright notice and permission notice are preserved.

This code is provided "as is", without warranty of any kind. The user assumes all responsibility and risk for its use. Under no circumstances shall the author be liable for damages, lost profits, data loss, business interruption, or other losses arising from the use of, inability to use, or reliance on this code.

See `LICENSE` for complete usage terms.


## Contact

[akrivitsky.dev@proton.me](mailto:akrivitsky.dev@proton.me)
