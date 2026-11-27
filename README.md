# Kiri vs. Podman on Linux: A Python Benchmarking Tool for Different Distributions

A lightweight, reproducible Python tool for comparing **Kiri** and **Podman** command latency on your own Linux system. Tested on **Fedora 45**, **CachyOS**, and **Lubuntu 26.04 LTS**; other distributions may work with an appropriate container-engine installation.

**Author:** Anatoly S. Krivitsky, Ph.D. · November 2026

**Benchmark version:** 1.2.0 (November 26, 2026); JSON schema 2.

**Purpose:** Provide a tool, **not a verdict** about which container engine is better. Run it on your system and evaluate the results yourself.

**Related article on Medium:** [Kiri vs. Podman on Linux: A Python Benchmarking Tool for Different Distributions](https://medium.com/@anatolykrivitsky/kiri-vs-podman-on-linux-a-python-benchmarking-tool-for-different-distributions-75878ba68418)

## What it measures

The script [`compare_kiri_podman_vms.py`](compare_kiri_podman_vms.py) times two complete CLI operations:

- **Container listing:** `ps` (Kiri's Docker-compatible CLI or `podman ps`).
- **Short-lived container execution:** `run --rm --network none docker.io/library/alpine:3.22 /bin/true`.

Each execution includes CLI and container-management overhead. `/bin/true` exits immediately, and the Alpine image is pulled **before** timing begins. The script uses `time.perf_counter_ns()`, runs warm-ups, and records the **minimum, maximum, mean, median, standard deviation, and individual samples** in JSON. `--compare` reads two JSON results and compares median latencies.

**Requirements:** Linux, Python **3.10+**, working Kiri and/or Podman installations, and internet access for the initial image pull. **No `pip` dependencies.**

## Install the container engines (if needed)

Obtain packages from the [official Kiri releases](https://github.com/libracoder/kiri/releases) and verify their published checksums and signatures against authenticated publisher information before installation. The examples below use Kiri 0.2.2, a security release. Check for system and application updates daily using your preferred graphical software updater or the distribution's normal terminal commands. Monitor manually installed packages and AUR packages separately as needed.

### Fedora 45

```bash
sudo dnf install podman
# After verifying the official x86-64 RPM and publisher key:
sudo dnf --setopt=localpkg_gpgcheck=1 install ./kiri-0.2.2-1.x86_64.rpm
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
sudo apt install podman curl ca-certificates
# After verifying the official amd64 DEB against its signed checksum manifest:
apt -s install ./kiri_0.2.2_amd64.deb
sudo apt install ./kiri_0.2.2_amd64.deb
sudo kiri host-access "$USER"
```

If Kiri access is not effective immediately, log out and back in. **Security:** Membership in the `kiri` group grants root-equivalent container-management privileges.

## Run the benchmark

Place `compare_kiri_podman_vms.py` in your working directory. Verify `python3 compare_kiri_podman_vms.py --version` reports `1.2.0` and run the preflight checks described below before timing either engine. The commands below run **three warm-ups** (default) and **30 measured iterations per operation**. Use the same conditions for both engines.

### Fedora 45

```bash
python3 compare_kiri_podman_vms.py --engine kiri --runs 30 --output kiri_fedora45_v120_30.json
python3 compare_kiri_podman_vms.py --engine podman --runs 30 --output podman_fedora45_v120_30.json
python3 compare_kiri_podman_vms.py --compare kiri_fedora45_v120_30.json podman_fedora45_v120_30.json
```

### CachyOS

```bash
python3 compare_kiri_podman_vms.py --engine kiri --kiri-cli /usr/lib/kiri/docker --runs 30 --output kiri_cachyos_v120_30.json
python3 compare_kiri_podman_vms.py --engine podman --runs 30 --output podman_cachyos_v120_30.json
python3 compare_kiri_podman_vms.py --compare kiri_cachyos_v120_30.json podman_cachyos_v120_30.json
```

### Lubuntu 26.04 LTS

```bash
python3 compare_kiri_podman_vms.py --engine kiri --runs 30 --output kiri_lubuntu2604_v120_30.json
python3 compare_kiri_podman_vms.py --engine podman --runs 30 --output podman_lubuntu2604_v120_30.json
python3 compare_kiri_podman_vms.py --compare kiri_lubuntu2604_v120_30.json podman_lubuntu2604_v120_30.json
```

### Verify engine routing before benchmarking

Some installations provide a `docker` command that invokes Podman. The Kiri 0.2.2 diagnostic session on Lubuntu confirmed that bare `kiri ps` could follow that wrapper, even when Kiri's own socket was healthy. The previous benchmark already used an explicit Kiri client and socket; version 1.2.0 further isolates child-process routing and adds a standalone preflight.

```bash
python3 compare_kiri_podman_vms.py --engine kiri --verify-only
python3 compare_kiri_podman_vms.py --engine podman --verify-only
```

Expected identity messages:

```text
Verified: Docker-compatible server is Kiri.
Verified: Podman CLI in native local mode.
```

Kiri uses `/usr/libexec/kiri/docker` or `/usr/lib/kiri/docker` with `-H unix:///run/kiri/docker.sock`. Use `--kiri-cli /path/to/docker` if needed. Podman is invoked directly with `--remote=false`. The same sanitized child environment is used for preflight, image preparation, warm-ups and measured commands. Docker host/context/API/TLS overrides and Podman connection overrides are removed from child environments only; no global shell settings or installed packages are modified.

Verification stops the run if Kiri does not identify itself as Kiri, the Podman emulation warning is present, Podman does not identify itself correctly, a separate Podman server is reported, or container listing fails. `--verify-only` performs no pull, container execution, timed samples or JSON output.

JSON schema 2 is retained, with an additive `engine_routing` object recording the routing mode, verification result and names (not values) of cleared environment variables. Older JSON results remain readable and generate a warning if the new routing evidence is missing. This warning does not by itself invalidate earlier results.

The original Alpine image, two operations, timing method and default counts are unchanged (15 measured runs by default; the commands in this README request 30). For the cleanest comparisons, rerun both engines with the same benchmark version. Version 1.2.0 completed live preflight, both benchmark operations, and comparison on all three distributions. On Lubuntu, both sessions recorded that `DOCKER_HOST` was excluded from subprocess environments.

On CachyOS, add `--kiri-cli /usr/lib/kiri/docker` to the Kiri preflight if necessary. See the related article for optional interactive shell configuration; the benchmark does not require that adjustment.

## Automated regression tests

[`test_engine_routing.py`](test_engine_routing.py) uses Python's built-in `unittest` framework and simulated container-engine executables to verify engine identity checks, routing isolation, rejection of incorrect or remote engines, JSON output, and comparison functionality. It requires no installed container engines, image downloads, or additional Python packages.

Run from the repository directory:

```bash
python3 -m unittest -v test_engine_routing.py
```

All six tests passed on each of Fedora 45, CachyOS, and Lubuntu 26.04 LTS on November 26, 2026 (18/18 test executions passed).

## Validation and your own results

Version 1.2.0 was functionally validated on Fedora 45, CachyOS and Lubuntu 26.04 LTS. This repository distributes the tool and its regression tests, not the author's benchmark measurements. Generate, retain and compare your own local JSON results using the commands above.

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
