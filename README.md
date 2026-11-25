# Kiri vs. Podman on Linux: A Python Benchmarking Tool for Different Distributions

A lightweight, reproducible Python tool for comparing **Kiri** and **Podman** command latency on your own Linux system. Tested on **Fedora 45**, **CachyOS**, and **Lubuntu 26.04 LTS**; other distributions may work with an appropriate container-engine installation.

**Author:** Anatoly S. Krivitsky, Ph.D. · November 2026  
**Benchmark version:** 1.1.0 · **JSON schema:** 2 · **Last updated:** November 25, 2026

**Purpose:** Provide a tool, **not a verdict** about which container engine is better.

**Test it for yourself.** With this tool, you can benchmark Kiri and Podman on your own Linux system, compare their command latency under your own conditions, and draw your own conclusions from the measurements. You can also save results and compare them after an engine upgrade. Generate your own data rather than relying on someone else’s benchmark results.

**Related article on Medium:** [Kiri vs. Podman on Linux: A Python Benchmarking Tool for Different Distributions](https://medium.com/@anatolykrivitsky/kiri-vs-podman-on-linux-a-python-benchmarking-tool-for-different-distributions-75878ba68418)

## What's new in version 1.1.0

- Tested with **Kiri 0.2.2** on all three distributions, alongside their respective Podman versions.
- Automatically detects Kiri's bundled Docker-compatible CLI on the tested distributions and explicitly connects to Kiri's Unix socket.
- Verifies the Kiri server identity and records the actual Kiri product version separately from the Docker compatibility version.
- Records engine, client, API, system, image identity, and rootless-mode metadata when available, along with UTC timestamps and the exact benchmark commands.
- Generates versioned JSON filenames automatically and protects existing results against accidental overwrite.
- Compares median latencies and warns about differences or missing metadata that may affect comparability. Accepts schema 1 and schema 2 results with the expected benchmark fields.
- Retains the original workloads and timing method. No external Python packages are required.

## What it measures

The script [`compare_kiri_podman_vms.py`](compare_kiri_podman_vms.py) times two complete CLI operations:

- **Container listing:** `ps` (Kiri's Docker-compatible CLI or `podman ps`).
- **Short-lived container execution:** `run --rm --network none docker.io/library/alpine:3.22 /bin/true`.

Each measured execution includes CLI and container-management overhead. The second operation includes container creation, startup, execution, and automatic removal. `/bin/true` exits immediately. The Alpine image is pulled and inspected **before** timing begins.

The script uses `time.perf_counter_ns()`, performs warm-ups, and records the **minimum, maximum, mean, median, sample standard deviation, and individual samples** in JSON. `--compare` reads two JSON files and compares median latencies.

**Requirements:** Linux, Python **3.10+**, working Kiri and/or Podman installations, and internet access for the image pull. **No `pip` dependencies.**

## Install the container engines (if needed)

The following examples use Kiri 0.2.2, the release used for the November 25 tests. Obtain the appropriate package for your architecture from the [official Kiri releases](https://github.com/libracoder/kiri/releases/tag/v0.2.2). The local package examples below are for x86-64 (amd64).

Before installing, verify the package against the published SHA-256 checksum and verify the package signature or signed checksum manifest where available. Obtain and authenticate the signing key using the project's official information; a matching checksum or clean antivirus scan alone does not establish publisher identity. See the [Kiri Linux documentation](https://docs.runkiri.com/linux/).

### Fedora 45

```bash
sudo dnf install podman

# After downloading the official RPM and verifying its checksum
# and signature against the authenticated Kiri signing key:
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

CachyOS installs Kiri via the community-maintained **Arch User Repository (AUR)** package `kiri-bin`. The package version may change; the tested version was `0.2.2-1`.

### Lubuntu 26.04 LTS

```bash
sudo apt update
sudo apt install podman curl ca-certificates

# After downloading the official DEB and verifying it against
# the authenticated, signed checksum manifest:
apt -s install ./kiri_0.2.2_amd64.deb
sudo apt install ./kiri_0.2.2_amd64.deb
sudo kiri host-access "$USER"
```

Review the APT simulation before installing, especially if `podman-docker` is already installed. The tested upgrade preserved the existing Podman packages.

If Kiri access is not effective immediately, log out and back in. Run the benchmark as your normal user after configuring access.

**Security:** Membership in the `kiri` group grants root-equivalent container-management privileges. Grant access only to trusted users.

## Run the benchmark

Place `compare_kiri_podman_vms.py` in your working directory.

```bash
python3 compare_kiri_podman_vms.py --version
```

Expected output:

```text
1.1.0
```

The examples below use **three warm-ups and 30 measured iterations per operation**. The script defaults to 15 measured iterations and three warm-ups if these options are omitted.

Run both engines sequentially on the same system, with the same workload and comparable system conditions. If both engines are installed, specify `--engine` explicitly.

### Fedora 45

```bash
python3 compare_kiri_podman_vms.py --engine kiri --runs 30 --warmups 3 --output kiri_0.2.2_fedora45.json
python3 compare_kiri_podman_vms.py --engine podman --runs 30 --warmups 3 --output podman_6.2.0_fedora45.json

python3 compare_kiri_podman_vms.py --compare kiri_0.2.2_fedora45.json podman_6.2.0_fedora45.json
```

### CachyOS

```bash
python3 compare_kiri_podman_vms.py --engine kiri --runs 30 --warmups 3 --output kiri_0.2.2_cachyos.json
python3 compare_kiri_podman_vms.py --engine podman --runs 30 --warmups 3 --output podman_6.2.1_cachyos.json

python3 compare_kiri_podman_vms.py --compare kiri_0.2.2_cachyos.json podman_6.2.1_cachyos.json
```

### Lubuntu 26.04 LTS

```bash
python3 compare_kiri_podman_vms.py --engine kiri --runs 30 --warmups 3 --output kiri_0.2.2_lubuntu2604.json
python3 compare_kiri_podman_vms.py --engine podman --runs 30 --warmups 3 --output podman_5.7.0_lubuntu2604.json

python3 compare_kiri_podman_vms.py --compare kiri_0.2.2_lubuntu2604.json podman_5.7.0_lubuntu2604.json
```

The filenames above reflect the engine versions used in the November 25 tests. If using different versions, change the filenames accordingly or omit `--output` to generate names automatically.

### Verify that Kiri really is Kiri

Some Linux setups provide a `docker` command that invokes Podman. This was observed on Lubuntu with `podman-docker` installed, where even the `kiri` wrapper invoked Podman.

To avoid benchmarking Podman twice, version 1.1.0 automatically searches for Kiri's bundled Docker-compatible client at:

| Distribution | Bundled client path |
| --- | --- |
| Fedora 45 | `/usr/libexec/kiri/docker` |
| CachyOS | `/usr/lib/kiri/docker` |
| Lubuntu 26.04 | `/usr/libexec/kiri/docker` |

The script explicitly selects Kiri's socket (`/run/kiri/docker.sock` by default) and verifies that the server identifies itself as `Server: Kiri`. It extracts the product version from the `Kiri:` section rather than the Docker compatibility `Engine:` section. It stops if server identification or product-version detection fails.

To verify manually on Fedora or Lubuntu:

```bash
/usr/libexec/kiri/docker -H unix:///run/kiri/docker.sock version
```

On CachyOS:

```bash
/usr/lib/kiri/docker -H unix:///run/kiri/docker.sock version
```

Use `--kiri-cli /path/to/docker` or `--kiri-socket /absolute/path/to/docker.sock` for a nonstandard installation. There is no need to remove `podman-docker` or change the default Docker CLI merely to run this benchmark.

## JSON results and comparison

Each successful benchmark writes a JSON file containing the engine and system information, image metadata, exact commands, iteration counts, and timing statistics with raw samples.

If `--output` is omitted, the script generates a filename of the form:

```text
<engine>_<engine-version>_<distribution-id><distribution-version>.json
```

The distribution ID and version come from the system's OS-release metadata, with non-alphanumeric characters removed. For example, Lubuntu may report Ubuntu and generate a name containing `ubuntu2604` instead of `lubuntu2604`. Explicit output filenames are useful when distinguishing Linux flavors.

Existing JSON files are not overwritten unless `--overwrite` is explicitly supplied. Use a different filename to preserve each independent trial.

```bash
python3 compare_kiri_podman_vms.py --compare FIRST_JSON SECOND_JSON
```

The comparison reports median latency, percentage difference relative to the second file, and the speedup ratio. Negative differences indicate lower latency for the first result.

Comparison checks include the image reference and available image digests, image ID and platform, system configuration, iteration counts, benchmark version, and rootless/rootful status. Different image references cause the comparison to stop; other detected discrepancies or missing image-digest/rootless information generate warnings. A warning is not a failed benchmark, but it must be considered when interpreting the results.

Older schema 1 results can also be read if they contain the expected fields. Historical comparisons may produce warnings about missing metadata or changed benchmark conditions; compatibility with every earlier result file has not been established.

## Tested platforms

Version 1.1.0 was successfully tested with Kiri 0.2.2 and Podman on Fedora 45, CachyOS, and Lubuntu 26.04 LTS, without distribution-specific changes to the Python source code.

The benchmark results are deliberately not presented here. The purpose of this repository is to give you a practical, reusable tool for independent testing, rather than promote one container engine over another. Run the benchmark on your own hardware or virtual machine, compare your own JSON results, and make an informed decision based on your environment.

## Customize and interpret

```bash
python3 compare_kiri_podman_vms.py --help
```

| Option | Purpose |
| --- | --- |
| `--version` | Print the benchmark version |
| `--engine {kiri,podman}` | Select the engine |
| `--runs N` | Measured iterations per operation (default: 15) |
| `--warmups N` | Warm-up iterations per operation (default: 3) |
| `--kiri-cli PATH` | Override the bundled Kiri client path |
| `--kiri-socket PATH` | Override the Kiri Unix socket path |
| `--output FILE` | Set the JSON output filename |
| `--overwrite` | Explicitly allow replacing an existing result |
| `--compare FIRST_JSON SECOND_JSON` | Compare two saved results without running containers |

Review individual timings and outliers in the JSON files. **Median latency** is typically more robust to occasional scheduling delays than the mean.

For a more controlled comparison:

- Use the same VM or physical machine, CPU and memory configuration, and comparable background load for both engines.
- Confirm image identity from the recorded image metadata; a matching tag alone is not proof of identical content.
- Check whether both engines operate in equivalent rootless or rootful modes. If either engine does not report its rootless status, equivalence remains unverified.
- Repeat the experiment with reversed engine order and save each trial separately.
- Record the actual engine versions and any changes to the system when comparing historical results.

When comparing results across distributions or releases, account for differences in engine versions, VM configurations, image identity, and test order.

**Scope:** These tests measure end-to-end container-management CLI latency, **not** isolated engine timings, application throughput, builds, networking, memory efficiency, security, or production reliability. Different systems and workloads may produce different results. **Decide for yourself.**

## License and Use

Copyright (c) 2026 Anatoly S. Krivitsky, Ph.D.  
All rights reserved.

Permission is granted, free of charge, to use, copy, distribute, and publish this code, provided that the copyright notice and permission notice are preserved.

This code is provided "as is", without warranty of any kind. The user assumes all responsibility and risk for its use. Under no circumstances shall the author be liable for damages, lost profits, data loss, business interruption, or other losses arising from the use of, inability to use, or reliance on this code.

See `LICENSE` for complete usage terms.

## Contact

[akrivitsky.dev@proton.me](mailto:akrivitsky.dev@proton.me)
