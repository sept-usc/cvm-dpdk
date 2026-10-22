#!/usr/bin/env python3
"""Run the original ARMv8 crypto command under explicit QEMU user emulation."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path)
    parser.add_argument("--qemu", default="qemu-aarch64")
    parser.add_argument("--sysroot", type=Path, default=Path("/usr/aarch64-linux-gnu"))
    parser.add_argument("--cpus", help="Two allowed CPU IDs, comma-separated")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    allowed = os.sched_getaffinity(0)
    try:
        cpus = ([int(cpu) for cpu in args.cpus.split(",")] if args.cpus
                else sorted(allowed)[:2])
    except ValueError:
        parser.error("--cpus must contain comma-separated integer CPU IDs")
    if len(cpus) != 2 or len(set(cpus)) != 2 or not set(cpus) <= allowed:
        parser.error("Two distinct allowed CPUs are required")
    binary = args.build.resolve() / "app/dpdk-test"
    qemu = shutil.which(args.qemu)
    if qemu is None or not binary.is_file() or not args.sysroot.is_dir():
        parser.error("An ARM64 dpdk-test, qemu-aarch64 and ARM64 runtime sysroot are required")
    output = args.output or args.build.resolve() / "cvm-dpdk-arm64-tests"
    output.mkdir(parents=True, exist_ok=False)
    environment = os.environ.copy()
    for name in ("DPDK_TEST_PARAMS", "DPDK_TEST_SKIP"):
        environment.pop(name, None)
    name = "cryptodev_sw_armv8_autotest"
    environment["DPDK_TEST"] = name
    command = [qemu, "-cpu", "max", "-L", str(args.sysroot.resolve()), str(binary),
               "-l", ",".join(map(str, cpus)), "--no-huge", "-m", "2048",
               "--no-pci", "--no-shconf", "--no-telemetry", "--vdev=crypto_armv8"]
    start = time.monotonic()
    log_path = output / (name + ".log")
    timed_out = False
    with log_path.open("w") as log:
        try:
            completed = subprocess.run(command, env=environment, stdout=log,
                                       stderr=subprocess.STDOUT, timeout=600, check=False)
            code = completed.returncode
        except subprocess.TimeoutExpired:
            code, timed_out = 124, True
    duration = round(time.monotonic() - start, 3)
    log_text = log_path.read_text()
    counts = {key.lower(): int(value) for key, value in
              re.findall(r"\+ Tests (Total|Skipped|Executed|Unsupported|Passed|Failed)\s*:\s*(\d+)", log_text)}
    result = {"name": name, "command": command, "exit_status": code,
              "duration_seconds": duration, "timed_out": timed_out, "subcases": counts}
    record = {
        "scope": "ARM64 instruction emulation on the host; not native ARM hardware or performance qualification",
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "qemu_sha256": hashlib.sha256(Path(qemu).read_bytes()).hexdigest(),
        "qemu_version": subprocess.check_output([qemu, "--version"], text=True).splitlines()[0],
        "cpu_ids": cpus, "memory_mib": 2048, "timeout_seconds": 600,
        "log_sha256": hashlib.sha256(log_path.read_bytes()).hexdigest(),
        "results": [result],
    }
    (output / "results.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(result), flush=True)
    if code != 0 or counts.get("failed") != 0 or counts.get("passed", 0) == 0:
        print(log_text[-4000:])
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
