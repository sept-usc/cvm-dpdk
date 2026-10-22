#!/usr/bin/env python3
"""Run the unmodified, long-running upstream mempool benchmarks."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


TESTS = (
    "mempool_perf_autotest",
    "mempool_perf_autotest_1core",
    "mempool_perf_autotest_2cores",
    "mempool_perf_autotest_allcores",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path)
    parser.add_argument("--cpus", help="Eight allowed CPU IDs, comma-separated")
    parser.add_argument("--test", choices=TESTS, action="append",
                        help="Select commands; default: all four, sequentially")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    allowed = os.sched_getaffinity(0)
    try:
        cpus = ([int(cpu) for cpu in args.cpus.split(",")] if args.cpus
                else sorted(allowed)[:8])
    except ValueError:
        parser.error("--cpus must contain comma-separated integer CPU IDs")
    if len(cpus) != 8 or len(set(cpus)) != 8 or not set(cpus) <= allowed:
        parser.error("Eight distinct CPUs from the allowed affinity are required")

    binary = args.build.resolve() / "app/dpdk-test"
    if not binary.is_file():
        parser.error(f"Missing executable: {binary}")
    output = args.output or args.build.resolve() / "cvm-dpdk-mempool-tests"
    # Refuse to overwrite an earlier benchmark's evidence.
    output.mkdir(parents=True, exist_ok=False)
    environment = os.environ.copy()
    for name in ("DPDK_TEST_PARAMS", "DPDK_TEST_SKIP"):
        environment.pop(name, None)
    record = {
        "binary": str(binary),
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "cpu_ids": cpus,
        "memory_mib": 6144,
        "timeout_seconds_per_command": 10800,
        "results": [],
    }
    failed = False
    for test in args.test or TESTS:
        command = ["timeout", "--kill-after=10s", "10800", "stdbuf", "-oL",
                   str(binary), "-l", ",".join(map(str, cpus)), "--no-huge",
                   "-m", "6144", "--no-pci", "--no-shconf", "--no-telemetry"]
        environment["DPDK_TEST"] = test
        print(f"Running {test}; log: {output / (test + '.log')}", flush=True)
        start = time.monotonic()
        with (output / (test + ".log")).open("w") as log:
            completed = subprocess.run(command, env=environment, stdout=log,
                                       stderr=subprocess.STDOUT, check=False)
        result = {
            "name": test, "command": command,
            "exit_status": completed.returncode,
            "duration_seconds": round(time.monotonic() - start, 3),
        }
        record["results"].append(result)
        (output / "results.json").write_text(json.dumps(record, indent=2) + "\n")
        print(json.dumps(result), flush=True)
        failed |= completed.returncode != 0
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
