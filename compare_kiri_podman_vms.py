#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Kiri vs. Podman: Container Lifecycle Performance Benchmark

Author: Anatoly S. Krivitsky, Ph.D.

Source code for the Medium article:
"Kiri vs. Podman on Linux: Benchmarking Container Lifecycle Performance with Python"

Benchmark Kiri and Podman on Linux. In the published experiments, both
engines were tested on the SAME VM for each distribution. The identical
Python script was run without code changes on Fedora 45 and CachyOS.

This updated version also supports Lubuntu 26.04. It explicitly uses Kiri's
bundled Docker CLI with Kiri's own Unix socket, not the `docker` command in
PATH (which can be a Podman compatibility wrapper on Lubuntu). It verifies
that the remote server identifies itself as Kiri BEFORE any measurement.
The benchmark still tests the same operations and image.

Fedora 45:
    python3 compare_kiri_podman_vms.py --engine kiri \
        --runs 30 --output kiri_fedora45.json
    python3 compare_kiri_podman_vms.py --engine podman \
        --runs 30 --output podman_fedora45.json
    python3 compare_kiri_podman_vms.py --compare \
        kiri_fedora45.json podman_fedora45.json

CachyOS:
    python3 compare_kiri_podman_vms.py --engine kiri \
        --runs 30 --output kiri_cachyos.json
    python3 compare_kiri_podman_vms.py --engine podman \
        --runs 30 --output podman_cachyos.json
    python3 compare_kiri_podman_vms.py --compare \
        kiri_cachyos.json podman_cachyos.json

Lubuntu 26.04:
    python3 compare_kiri_podman_vms.py --engine kiri \
        --runs 30 --output kiri_lubuntu2604.json
    python3 compare_kiri_podman_vms.py --engine podman \
        --runs 30 --output podman_lubuntu2604.json
    python3 compare_kiri_podman_vms.py --compare \
        kiri_lubuntu2604.json podman_lubuntu2604.json

Requirements:
    Python 3.10+
    Kiri or Podman installed and operational
    Internet access for the initial image pull
    No third-party Python packages required.

Copyright (c) 2026 Anatoly S. Krivitsky, Ph.D.
All rights reserved.

Permission is granted, free of charge, to use, copy, distribute, and publish
this code, provided that this copyright notice and permission notice are
preserved.

This code is provided "as is", without warranty of any kind. The user assumes
all responsibility and risk for its use. Under no circumstances shall the
author be liable for any direct, indirect, incidental, special, consequential,
exemplary, or punitive damages, lost profits, data loss, or other losses
arising from the use of, inability to use, or reliance on this code.

Questions and comments:
    akrivitsky.dev@proton.me

See LICENSE for complete usage terms.
"""

import argparse
import json
import platform
import shutil
import statistics
import subprocess
import sys
import time

from datetime import datetime, timezone
from pathlib import Path


IMAGE = "docker.io/library/alpine:3.22"

DEFAULT_RUNS = 15
DEFAULT_WARMUPS = 3
COMMAND_TIMEOUT = 120

# Kiri's bundled Docker CLI and Linux engine socket (Kiri 0.2.1 full package).
# Do not use a Docker/Podman compatibility wrapper from PATH for Kiri runs.
DEFAULT_KIRI_CLI = "/usr/libexec/kiri/docker"
KIRI_SOCKET = "/run/kiri/docker.sock"


# ------------------------------------------------------------
# Command execution
# ------------------------------------------------------------

def execute(command, timeout=COMMAND_TIMEOUT):
    """
    Execute a command and capture its output.

    Returns:
        CompletedProcess instance.

    Raises:
        RuntimeError on command failure.
    """

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {' '.join(command)}\n"
            f"Exit code: {result.returncode}\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )

    return result


def timed_execute(command):
    """
    Execute a command and measure elapsed wall-clock time.

    Returns elapsed time in milliseconds.
    """

    start = time.perf_counter_ns()

    execute(command)

    end = time.perf_counter_ns()

    return (end - start) / 1_000_000


# ------------------------------------------------------------
# Engine detection
# ------------------------------------------------------------

def detect_engine():
    """
    Detect the installed container engine.

    Works on Fedora 45, CachyOS, and other Linux distributions.
    Specify --engine when both Kiri and Podman are installed.
    """

    has_kiri = shutil.which("kiri") is not None
    has_podman = shutil.which("podman") is not None

    if has_kiri and not has_podman:
        return "kiri"

    if has_podman and not has_kiri:
        return "podman"

    if has_kiri and has_podman:
        raise RuntimeError(
            "Both Kiri and Podman were detected. "
            "Specify --engine kiri or --engine podman."
        )

    raise RuntimeError(
        "Neither Kiri nor Podman was found in PATH."
    )


def resolve_engine_command(engine, kiri_cli=None):
    """
    Return an unambiguous command prefix for the selected engine.

    Kiri 0.2.1 on Linux ships a Docker client in /usr/libexec/kiri.
    Explicitly targeting Kiri's socket avoids the Podman `docker` shim
    found on systems such as Lubuntu 26.04. The user may override the
    bundled-client path for custom installations with --kiri-cli.
    """

    if engine == "podman":
        executable = shutil.which("podman")
        if executable is None:
            raise RuntimeError("Podman executable not found in PATH.")
        return [executable]

    if engine == "kiri":
        if shutil.which("kiri") is None:
            raise RuntimeError("Kiri executable not found in PATH.")

        client = Path(kiri_cli or DEFAULT_KIRI_CLI)
        if not client.is_file():
            raise RuntimeError(
                f"Kiri's bundled Docker client was not found: {client}. "
                "Use --kiri-cli /path/to/a/real/docker-client if your "
                "Kiri package installs it elsewhere. Do not use Podman's "
                "docker compatibility wrapper."
            )

        import os
        if not os.access(client, os.X_OK):
            raise RuntimeError(f"Kiri Docker client is not executable: {client}")

        return [str(client.resolve()), "-H", f"unix://{KIRI_SOCKET}"]

    raise ValueError(f"Unknown engine: {engine}")


def verify_kiri_server(command_prefix):
    """Fail closed if the Docker-compatible endpoint is not Kiri."""

    result = execute(command_prefix + ["version"], timeout=30)
    if not any(
        line.strip().casefold().startswith("server: kiri")
        for line in result.stdout.splitlines()
    ):
        raise RuntimeError(
            "The target endpoint did not identify itself as 'Server: Kiri'. "
            "Aborting to avoid accidentally benchmarking Podman or Docker. "
            f"Command: {' '.join(command_prefix)} version\n"
            f"Output:\n{result.stdout}\n{result.stderr}"
        )


def default_output_filename(engine):
    """Generate a distribution-specific filename when --output is omitted."""

    try:
        distro = platform.freedesktop_os_release()
    except OSError:
        distro = {}

    distro_id = "".join(
        ch for ch in distro.get("ID", "linux").lower()
        if ch.isalnum()
    ) or "linux"
    version = "".join(
        ch for ch in distro.get("VERSION_ID", "")
        if ch.isalnum()
    )
    return f"{engine}_{distro_id}{version}.json"


# ------------------------------------------------------------
# Benchmark utilities
# ------------------------------------------------------------

def calculate_statistics(times):
    """
    Calculate timing statistics in milliseconds.
    """

    return {
        "count": len(times),
        "minimum_ms": min(times),
        "maximum_ms": max(times),
        "mean_ms": statistics.mean(times),
        "median_ms": statistics.median(times),
        "stdev_ms": (
            statistics.stdev(times)
            if len(times) > 1
            else 0.0
        ),
        "samples_ms": times
    }


def benchmark(name, command, warmups, runs):
    """
    Benchmark one command.

    Warm-up executions are excluded from results.
    """

    print(f"\n{'=' * 65}")
    print(f"Benchmark: {name}")
    print(f"Command: {' '.join(command)}")
    print(f"{'=' * 65}")

    print(f"\nPerforming {warmups} warm-up executions...")

    for i in range(warmups):
        timed_execute(command)
        print(f"  Warm-up {i + 1}/{warmups}: OK")

    print(f"\nPerforming {runs} measured executions...")

    samples = []

    for i in range(runs):
        elapsed = timed_execute(command)

        samples.append(elapsed)

        print(
            f"  Run {i + 1:2d}/{runs}: "
            f"{elapsed:10.3f} ms"
        )

    stats = calculate_statistics(samples)

    print("\nResults:")
    print(f"  Minimum: {stats['minimum_ms']:.3f} ms")
    print(f"  Maximum: {stats['maximum_ms']:.3f} ms")
    print(f"  Mean:    {stats['mean_ms']:.3f} ms")
    print(f"  Median:  {stats['median_ms']:.3f} ms")
    print(f"  Std dev: {stats['stdev_ms']:.3f} ms")

    return stats


# ------------------------------------------------------------
# System information
# ------------------------------------------------------------

def get_system_information():
    """
    Collect information about the current VM.
    """

    information = {
        "hostname": platform.node(),
        "kernel": platform.release(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "cpu_count": None,
        "memory_total_kib": None
    }

    try:
        import os

        information["cpu_count"] = os.cpu_count()

        with open(
            "/proc/meminfo",
            "r",
            encoding="utf-8"
        ) as file:

            for line in file:
                if line.startswith("MemTotal:"):
                    information["memory_total_kib"] = int(
                        line.split()[1]
                    )
                    break

    except (OSError, ValueError):
        pass

    return information


# ------------------------------------------------------------
# Run benchmark suite
# ------------------------------------------------------------

def run_suite(engine, runs, warmups, output, kiri_cli=None):
    """
    Run the complete benchmark suite on the current VM.
    """

    command_prefix = resolve_engine_command(engine, kiri_cli=kiri_cli)
    executable = command_prefix[0]

    print("\n" + "=" * 65)
    print("KIRI vs PODMAN CONTAINER LIFECYCLE BENCHMARK")
    print("=" * 65)

    print(f"Engine:      {engine}")
    print(f"Executable:  {executable}")
    print(f"CLI prefix:  {' '.join(command_prefix)}")
    print(f"Hostname:    {platform.node()}")
    print(f"Kernel:      {platform.release()}")
    print(f"Image:       {IMAGE}")
    print(f"Runs:        {runs}")
    print(f"Warm-ups:    {warmups}")

    # --------------------------------------------------------
    # Check engine availability
    # --------------------------------------------------------

    print("\nChecking container engine...")

    if engine == "kiri":
        verify_kiri_server(command_prefix)
        print("Verified: Docker-compatible server is Kiri.")

    execute(command_prefix + ["ps"], timeout=30)

    print("Container engine is responding.")

    # --------------------------------------------------------
    # Pull the same image before timing begins
    # --------------------------------------------------------

    print(f"\nPreparing container image: {IMAGE}")
    print("This download is NOT included in benchmark timings.")

    execute(
        command_prefix + ["pull", IMAGE],
        timeout=600
    )

    print("Container image is ready.")

    # --------------------------------------------------------
    # Benchmark 1: CLI container listing
    # --------------------------------------------------------

    ps_results = benchmark(
        name="Container listing",
        command=command_prefix + ["ps"],
        warmups=warmups,
        runs=runs
    )

    # --------------------------------------------------------
    # Benchmark 2: Container creation and execution
    # --------------------------------------------------------

    # Each execution creates a container, runs /bin/true,
    # waits for termination, and removes the container.
    #
    # --network none ensures the container workload does not
    # depend on network initialization.

    run_command = command_prefix + [
        "run",
        "--rm",
        "--network",
        "none",
        IMAGE,
        "/bin/true"
    ]

    startup_results = benchmark(
        name="Container startup and execution",
        command=run_command,
        warmups=warmups,
        runs=runs
    )

    # --------------------------------------------------------
    # Build result document
    # --------------------------------------------------------

    results = {
        "schema_version": 1,
        "timestamp_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "engine": engine,
        "engine_executable": executable,
        "engine_command_prefix": command_prefix,
        "kiri_socket": KIRI_SOCKET if engine == "kiri" else None,
        "image": IMAGE,
        "runs": runs,
        "warmups": warmups,
        "system": get_system_information(),
        "benchmarks": {
            "ps": ps_results,
            "run": startup_results
        }
    }

    # --------------------------------------------------------
    # Save results
    # --------------------------------------------------------

    output_path = Path(output)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    output_path.write_text(
        json.dumps(
            results,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    print("\n" + "=" * 65)
    print("BENCHMARK COMPLETED SUCCESSFULLY")
    print("=" * 65)

    print(f"\nResults saved to: {output_path.resolve()}")

    print("\nSummary:")

    print(
        f"  Container listing median: "
        f"{ps_results['median_ms']:.3f} ms"
    )

    print(
        f"  Container execution median: "
        f"{startup_results['median_ms']:.3f} ms"
    )


# ------------------------------------------------------------
# Compare results from two benchmark runs (ideally on the same VM)
# ------------------------------------------------------------

def compare_results(first_file, second_file):
    """
    Compare benchmark JSON results from two runs.

    For a controlled engine comparison, run both engines on the same VM.
    """

    first_path = Path(first_file)
    second_path = Path(second_file)

    for path in (first_path, second_path):
        if not path.is_file():
            raise FileNotFoundError(
                f"Benchmark file not found: {path.resolve()}\n"
                "Run the benchmark on that VM first, then "
                "copy its JSON file to this directory."
            )

    first = json.loads(
        first_path.read_text(encoding="utf-8")
    )

    second = json.loads(
        second_path.read_text(encoding="utf-8")
    )

    if first["image"] != second["image"]:
        raise RuntimeError(
            "The benchmarks used different container images."
        )

    print("\n" + "=" * 78)
    print("KIRI vs PODMAN BENCHMARK COMPARISON")
    print("=" * 78)

    print(
        f"\nSystem 1: {first['engine']} / "
        f"{first['system']['hostname']}"
    )

    print(
        f"  Kernel: {first['system']['kernel']}"
    )

    print(
        f"\nSystem 2: {second['engine']} / "
        f"{second['system']['hostname']}"
    )

    print(
        f"  Kernel: {second['system']['kernel']}"
    )

    print("\nMedian execution times (milliseconds):\n")

    print(
        f"{'Operation':<28}"
        f"{first['engine']:>15}"
        f"{second['engine']:>15}"
        f"{'Difference':>17}"
    )

    print("-" * 78)

    labels = {
        "ps": "Container listing",
        "run": "Container execution"
    }

    for key, label in labels.items():

        first_time = first[
            "benchmarks"
        ][key]["median_ms"]

        second_time = second[
            "benchmarks"
        ][key]["median_ms"]

        difference = (
            (first_time - second_time)
            / second_time
            * 100
        )

        print(
            f"{label:<28}"
            f"{first_time:>15.3f}"
            f"{second_time:>15.3f}"
            f"{difference:>+16.1f}%"
        )

        if first_time < second_time:
            winner = first["engine"]
            factor = second_time / first_time
        elif second_time < first_time:
            winner = second["engine"]
            factor = first_time / second_time
        else:
            winner = "Tie"
            factor = 1.0

        print(
            f"  Faster: {winner} "
            f"({factor:.2f}x)"
        )

    print("\n" + "=" * 78)

    print(
        "\nNOTE: These measurements compare complete VM "
        "configurations, not isolated container engines."
    )


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Benchmark Kiri and Podman on the same Linux VM, "
            "including Fedora 45, CachyOS, and Lubuntu 26.04."
        )
    )

    parser.add_argument(
        "--engine",
        choices=["kiri", "podman"],
        help="Container engine to benchmark."
    )

    parser.add_argument(
        "--kiri-cli",
        help=(
            "Path to Kiri's genuine Docker CLI "
            f"(default: {DEFAULT_KIRI_CLI}). "
            "Do not point this to Podman's docker compatibility shim."
        )
    )

    parser.add_argument(
        "--runs",
        type=int,
        default=DEFAULT_RUNS,
        help="Number of measured runs (default: 15)."
    )

    parser.add_argument(
        "--warmups",
        type=int,
        default=DEFAULT_WARMUPS,
        help="Number of warm-up runs (default: 3)."
    )

    parser.add_argument(
        "--output",
        help="Output JSON filename."
    )

    parser.add_argument(
        "--compare",
        nargs=2,
        metavar=("KIRI_JSON", "PODMAN_JSON"),
        help="Compare two previously generated JSON files."
    )

    args = parser.parse_args()

    try:

        if args.compare:

            compare_results(
                args.compare[0],
                args.compare[1]
            )

        else:

            if args.runs < 1:
                parser.error("--runs must be at least 1")

            if args.warmups < 0:
                parser.error("--warmups cannot be negative")

            engine = (
                args.engine
                if args.engine
                else detect_engine()
            )

            output = args.output

            if not output:
                output = default_output_filename(engine)

            run_suite(
                engine=engine,
                runs=args.runs,
                warmups=args.warmups,
                output=output,
                kiri_cli=args.kiri_cli
            )

    except (
        RuntimeError,
        FileNotFoundError,
        subprocess.TimeoutExpired,
        OSError,
        KeyError,
        ValueError
    ) as error:

        print(
            f"\nERROR: {error}",
            file=sys.stderr
        )

        sys.exit(1)


if __name__ == "__main__":
    main()