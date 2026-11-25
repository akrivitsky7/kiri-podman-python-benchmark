#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
Kiri vs. Podman: Container Lifecycle Performance Benchmark
Version 1.1.0 | JSON schema 2 | Python 3.10+
Author: Anatoly S. Krivitsky, Ph.D.

Run both engines on the same Linux VM for a controlled comparison.
The original workloads and timing method are retained. No external Python
packages are required. Internet access is needed for the image pull.

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

Questions and comments: akrivitsky.dev@proton.me
See LICENSE for complete usage terms.
"""
import argparse
import json
import math
import os
import platform
import re
import shlex
import shutil
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

BENCHMARK_VERSION = "1.1.0"
SCHEMA_VERSION = 2
IMAGE = "docker.io/library/alpine:3.22"
DEFAULT_RUNS = 15
DEFAULT_WARMUPS = 3
COMMAND_TIMEOUT = 120
KIRI_SOCKET = "/run/kiri/docker.sock"
KIRI_CLI_PATHS = ("/usr/libexec/kiri/docker", "/usr/lib/kiri/docker")


def warn(message):
    print(f"WARNING: {message}", file=sys.stderr)


def execute(command, timeout=COMMAND_TIMEOUT):
    result = subprocess.run(
        command, capture_output=True, text=True, timeout=timeout, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {shlex.join(command)}\n"
            f"Exit code: {result.returncode}\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    return result


def timed_execute(command):
    start = time.perf_counter_ns()
    execute(command)
    end = time.perf_counter_ns()
    return (end - start) / 1_000_000


def detect_engine():
    engines = [e for e in ("kiri", "podman") if shutil.which(e)]
    if len(engines) != 1:
        raise RuntimeError("Specify --engine kiri or --engine podman; "
                           f"detected: {', '.join(engines) or 'neither'}.")
    return engines[0]


def resolve_engine_command(engine, kiri_cli=None, kiri_socket=KIRI_SOCKET):
    if engine == "podman":
        executable = shutil.which("podman")
        if not executable:
            raise RuntimeError("Podman executable not found in PATH.")
        return [executable]
    if engine != "kiri":
        raise ValueError(f"Unknown engine: {engine}")
    if not shutil.which("kiri"):
        raise RuntimeError("Kiri executable not found in PATH.")
    if not Path(kiri_socket).is_absolute():
        raise ValueError("--kiri-socket requires an absolute filesystem path.")
    for candidate in ((kiri_cli,) if kiri_cli else KIRI_CLI_PATHS):
        path = Path(candidate).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return [str(path.resolve()), "-H", f"unix://{kiri_socket}"]
    raise RuntimeError("Kiri's bundled Docker CLI not found or not executable. "
                       "Use --kiri-cli with the genuine bundled client.")


def parse_kiri_version(output):
    """Parse named sections; never mistake the compatibility version for Kiri."""
    if not any(line.strip().casefold() == "server: kiri"
               for line in output.splitlines()):
        raise RuntimeError("Endpoint did not identify itself as Server: Kiri.\n"
                           + output)
    fields = {"client": {}, "engine": {}, "kiri": {}}
    section = None
    for line in output.splitlines():
        line = line.strip()
        if line.casefold() == "server: kiri":
            section = None
        elif line.casefold() in ("client:", "engine:", "kiri:"):
            section = line[:-1].casefold()
        elif section and ":" in line:
            key, value = line.split(":", 1)
            fields[section][key.strip().casefold()] = value.strip()
    version = fields["kiri"].get("version")
    if not version:
        raise RuntimeError("Kiri product version missing from server response.\n"
                           + output)
    client_api = fields["client"].get("api version", "")
    downgrade = re.search(r"downgraded from\s+([^\s)]+)", client_api)
    return {
        "engine_version": version,
        "client_version": fields["client"].get("version"),
        "compatibility_engine_version": fields["engine"].get("version"),
        "api_version": client_api.split()[0] if client_api else None,
        "client_max_api_version": downgrade.group(1) if downgrade else None,
        "server_api_version": fields["engine"].get("api version"),
        "rootless": None,
        "version_output": output,
    }


def get_engine_metadata(engine, prefix):
    if engine == "kiri":
        raw = execute(prefix + ["version"], timeout=30).stdout
        meta = parse_kiri_version(raw)
        try:
            options = json.loads(execute(
                prefix + ["info", "--format", "{{json .SecurityOptions}}"], 30
            ).stdout)
            if isinstance(options, list) and any(
                "rootless" in str(option).casefold() for option in options
            ):
                meta["rootless"] = True
        except (RuntimeError, ValueError, subprocess.TimeoutExpired, OSError):
            pass  # A Docker-compatible server need not implement all info fields.
        return meta

    raw = execute(prefix + ["version", "--format", "json"], 30).stdout
    data = json.loads(raw)
    client = data.get("Client") or data.get("client") or {}
    server = data.get("Server") or data.get("server") or {}
    client_version = client.get("Version") or client.get("version")
    server_version = server.get("Version") or server.get("version")
    version = server_version or client_version
    if not version:
        raise RuntimeError("Podman version missing from JSON response.\n" + raw)
    meta = {
        "engine_version": version,
        "client_version": client_version,
        "compatibility_engine_version": None,
        "api_version": (server or client).get("APIVersion"),
        "server_api_version": server.get("APIVersion"),
        "rootless": None,
        "version_output": data,
    }
    try:
        info = json.loads(execute(prefix + ["info", "--format", "json"], 30).stdout)
        rootless = info.get("host", {}).get("security", {}).get("rootless")
        if isinstance(rootless, bool):
            meta["rootless"] = rootless
    except (RuntimeError, ValueError, subprocess.TimeoutExpired, OSError):
        pass
    return meta


def get_system_information():
    try:
        distro = platform.freedesktop_os_release()
    except OSError:
        distro = {}
    memory = None
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                memory = int(line.split()[1])
                break
    except (OSError, ValueError):
        pass
    return {
        "hostname": platform.node(), "kernel": platform.release(),
        "architecture": platform.machine(),
        "python_version": platform.python_version(),
        "cpu_count": os.cpu_count(), "memory_total_kib": memory,
        "distribution": distro.get("NAME"),
        "distribution_id": distro.get("ID"),
        "distribution_version": distro.get("VERSION_ID"),
        "distribution_pretty_name": distro.get("PRETTY_NAME"),
        "effective_uid": os.geteuid() if hasattr(os, "geteuid") else None,
    }


def inspect_image(prefix):
    """Collect identity outside the timed workload; unavailable fields stay null."""
    metadata = {"id": None, "repo_digests": [], "digest": None,
                "architecture": None, "os": None}
    try:
        data = json.loads(execute(prefix + ["image", "inspect", IMAGE], 30).stdout)
        item = data[0] if isinstance(data, list) else data
        metadata.update({
            "id": item.get("Id") or item.get("ID"),
            "repo_digests": item.get("RepoDigests") or [],
            "digest": item.get("Digest") or None,
            "architecture": item.get("Architecture"),
            "os": item.get("Os") or item.get("OS"),
        })
    except (RuntimeError, ValueError, OSError, IndexError,
            TypeError, AttributeError, subprocess.TimeoutExpired) as error:
        warn(f"Image inspection unavailable: {error}")
    if not (metadata["repo_digests"] or metadata["digest"]):
        warn("No repository digest reported; exact image equivalence is unverified.")
    return metadata


def default_output_filename(engine, version, system):
    safe = lambda value: re.sub(r"[^a-zA-Z0-9._-]", "_", str(value))
    distro = re.sub(r"[^a-zA-Z0-9]", "", system.get("distribution_id") or "linux")
    release = re.sub(r"[^a-zA-Z0-9]", "", system.get("distribution_version") or "")
    return f"{engine}_{safe(version)}_{distro}{release}.json"


def calculate_statistics(times):
    return {
        "count": len(times), "minimum_ms": min(times), "maximum_ms": max(times),
        "mean_ms": statistics.mean(times), "median_ms": statistics.median(times),
        "stdev_ms": statistics.stdev(times) if len(times) > 1 else 0.0,
        "samples_ms": times,
    }


def benchmark(name, command, warmups, runs):
    print(f"\n{'=' * 65}\nBenchmark: {name}\nCommand: {shlex.join(command)}")
    for i in range(warmups):
        timed_execute(command)
        print(f"  Warm-up {i + 1}/{warmups}: OK")
    samples = []
    for i in range(runs):
        elapsed = timed_execute(command)
        samples.append(elapsed)
        print(f"  Run {i + 1:2d}/{runs}: {elapsed:10.3f} ms")
    stats = calculate_statistics(samples)
    for label, key in (("Minimum", "minimum_ms"), ("Maximum", "maximum_ms"),
                       ("Mean", "mean_ms"), ("Median", "median_ms"),
                       ("Std dev", "stdev_ms")):
        print(f"  {label:8s}: {stats[key]:.3f} ms")
    return stats


def run_suite(engine, runs, warmups, output=None, kiri_cli=None,
              kiri_socket=KIRI_SOCKET, overwrite=False):
    prefix = resolve_engine_command(engine, kiri_cli, kiri_socket)
    meta = get_engine_metadata(engine, prefix)
    system = get_system_information()
    version = meta["engine_version"]
    path = Path(output or default_output_filename(engine, version, system))
    if path.exists() and not overwrite:
        raise FileExistsError(f"Results already exist: {path}. "
                              "Choose --output or explicitly use --overwrite.")
    print(f"\nKIRI vs PODMAN | Benchmark {BENCHMARK_VERSION}")
    print(f"Engine: {engine} {version}\nCLI: {shlex.join(prefix)}")
    print(f"System: {system['distribution_pretty_name']} / {system['kernel']}")
    print(f"Image: {IMAGE}\nRuns: {runs}\nWarm-ups: {warmups}")
    execute(prefix + ["ps"], timeout=30)
    print("\nPreparing image (not timed)...")
    execute(prefix + ["pull", IMAGE], timeout=600)
    image_metadata = inspect_image(prefix)
    if meta["rootless"] is None:
        warn("Engine rootless status unavailable; it will be recorded as null.")
    # Keep both original measured commands and their order unchanged.
    commands = {"ps": prefix + ["ps"],
                "run": prefix + ["run", "--rm", "--network", "none", IMAGE, "/bin/true"]}
    ps_results = benchmark("Container listing", commands["ps"], warmups, runs)
    run_results = benchmark("Container startup and execution", commands["run"], warmups, runs)
    results = {
        "schema_version": SCHEMA_VERSION, "benchmark_version": BENCHMARK_VERSION,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "engine": engine, "engine_version": version, "engine_metadata": meta,
        "engine_executable": prefix[0], "engine_command_prefix": prefix,
        "kiri_socket": kiri_socket if engine == "kiri" else None,
        "image": IMAGE, "image_metadata": image_metadata,
        "runs": runs, "warmups": warmups, "system": system,
        "benchmark_commands": commands,
        "benchmarks": {"ps": ps_results, "run": run_results},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w" if overwrite else "x", encoding="utf-8") as file:
        json.dump(results, file, indent=2, ensure_ascii=False)
        file.write("\n")
    print(f"\nBENCHMARK COMPLETED\nResults: {path.resolve()}")
    print(f"  Listing median:   {ps_results['median_ms']:.3f} ms")
    print(f"  Execution median: {run_results['median_ms']:.3f} ms")


def read_results(filename):
    data = json.loads(Path(filename).read_text(encoding="utf-8"))
    if data.get("schema_version", 1) not in (1, 2):
        raise ValueError(f"Unsupported JSON schema: {filename}")
    return data


def image_digests(result):
    meta = result.get("image_metadata") or {}
    return {value.rsplit("@", 1)[-1].lower()
            for value in (meta.get("repo_digests") or []) + [meta.get("digest")]
            if isinstance(value, str) and re.fullmatch(
                r"sha256:[0-9a-fA-F]{64}", value.rsplit("@", 1)[-1])}


def check_comparability(first, second):
    if first["image"] != second["image"]:
        raise RuntimeError("Benchmarks used different image references.")
    a, b = image_digests(first), image_digests(second)
    if not a or not b:
        warn("One or both image digests are missing; image identity is unverified.")
    elif not a.intersection(b):
        warn("No shared repository digest; image content may differ (index vs manifest also possible).")
    for key in ("id", "architecture", "os"):
        x = (first.get("image_metadata") or {}).get(key)
        y = (second.get("image_metadata") or {}).get(key)
        if key == "id" and isinstance(x, str) and isinstance(y, str):
            x, y = x.removeprefix("sha256:"), y.removeprefix("sha256:")
        if x is not None and y is not None and x != y:
            warn(f"Image {key} differs: {x} vs {y}.")
    for key in ("hostname", "kernel", "architecture", "cpu_count", "memory_total_kib",
                "distribution_id", "distribution_version", "python_version"):
        x, y = first["system"].get(key), second["system"].get(key)
        if x is not None and y is not None and x != y:
            warn(f"System {key} differs: {x} vs {y}.")
    for key in ("runs", "warmups", "benchmark_version"):
        if first.get(key) != second.get(key):
            warn(f"{key} differs: {first.get(key)} vs {second.get(key)}.")
    x = (first.get("engine_metadata") or {}).get("rootless")
    y = (second.get("engine_metadata") or {}).get("rootless")
    if x is None or y is None:
        warn("Rootless/rootful equivalence is unverified.")
    elif x != y:
        warn(f"Engine rootless status differs: {x} vs {y}.")


def compare_results(first_file, second_file):
    first, second = read_results(first_file), read_results(second_file)
    check_comparability(first, second)
    labels = [f"{r['engine']} {r.get('engine_version') or 'unknown'}" for r in (first, second)]
    print("\nKIRI vs PODMAN BENCHMARK COMPARISON")
    for i, result in enumerate((first, second)):
        print(f"  {labels[i]} | {result['system']['hostname']} | {result['system']['kernel']}")
    print(f"\n{'Operation':<24}{labels[0]:>20}{labels[1]:>20}{'Difference':>15}")
    for key, label in (("ps", "Container listing"), ("run", "Container execution")):
        a, b = (float(r["benchmarks"][key]["median_ms"]) for r in (first, second))
        if not all(math.isfinite(v) and v > 0 for v in (a, b)):
            raise ValueError(f"Invalid median for {key}.")
        difference = (a - b) / b * 100
        print(f"{label:<24}{a:>20.3f}{b:>20.3f}{difference:>+14.1f}%")
        winner = labels[0] if a < b else labels[1] if b < a else "Tie"
        print(f"  Faster: {winner} ({max(a, b) / min(a, b):.2f}x)")
    print("\nTimes are milliseconds; difference is relative to the second result.")
    print("These are end-to-end CLI measurements, not isolated engine timings.")


def main():
    parser = argparse.ArgumentParser(description="Kiri vs. Podman lifecycle benchmark")
    parser.add_argument("--version", action="version", version=BENCHMARK_VERSION)
    parser.add_argument("--engine", choices=("kiri", "podman"))
    parser.add_argument("--kiri-cli", help="Override bundled Kiri Docker CLI path")
    parser.add_argument("--kiri-socket", default=KIRI_SOCKET)
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    parser.add_argument("--warmups", type=int, default=DEFAULT_WARMUPS)
    parser.add_argument("--output", help="Output JSON filename")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing existing results")
    parser.add_argument("--compare", nargs=2, metavar=("FIRST_JSON", "SECOND_JSON"))
    args = parser.parse_args()
    try:
        if args.compare:
            compare_results(*args.compare)
        else:
            if args.runs < 1 or args.warmups < 0:
                parser.error("--runs must be positive and --warmups nonnegative")
            run_suite(args.engine or detect_engine(), args.runs, args.warmups,
                      args.output, args.kiri_cli, args.kiri_socket, args.overwrite)
    except (RuntimeError, OSError, ValueError, KeyError, TypeError,
            AttributeError, subprocess.TimeoutExpired) as error:
        print(f"\nERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
