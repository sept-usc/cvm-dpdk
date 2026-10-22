#!/usr/bin/env python3
"""Exercise testpmd forwarding pools and upstream ethdev queue-state checks."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile
import time


def wait_for(process, ready, description):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"testpmd exited {process.returncode} before {description}")
        if ready():
            return
        time.sleep(0.05)
    raise RuntimeError(f"Timed out waiting for {description}")


def stop(process):
    if process.poll() is None:
        try:
            process.communicate("quit\n", timeout=15)
        except (subprocess.TimeoutExpired, BrokenPipeError):
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path)
    parser.add_argument("--only", choices=("forwarding", "ethdev"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    build = args.build.resolve()
    output = args.output or build / "cvm-dpdk-cli-tests"
    output.mkdir(parents=True, exist_ok=False)
    groups = {}
    for cpu in sorted(os.sched_getaffinity(0)):
        nodes = list(Path(f"/sys/devices/system/cpu/cpu{cpu}").glob("node[0-9]*"))
        node = int(nodes[0].name[4:]) if nodes else 0
        groups.setdefault(node, []).append(cpu)
    cpus = next((group[:4] for group in groups.values() if len(group) >= 4), None)
    if cpus is None:
        parser.error("Four available CPUs on one NUMA node are required")
    environment = os.environ.copy()
    for name in ("DPDK_TEST", "DPDK_TEST_PARAMS", "DPDK_TEST_SKIP"):
        environment.pop(name, None)
    testpmd = build / "app/dpdk-testpmd"
    record = {"testpmd_sha256": hashlib.sha256(testpmd.read_bytes()).hexdigest(),
              "cpu_ids": cpus, "results": []}

    def eal(selected):
        return ["-l", ",".join(map(str, selected)), "--no-huge", "-m", "512",
                "--no-pci", "--no-shconf", "--no-telemetry"]

    def run_testpmd(name, device, options, exercise):
        command = ["stdbuf", "-oL", str(testpmd), *eal(cpus[:2]), "--vdev=" + device, "--", "-i",
                   "--total-num-mbufs=4096", "--disable-link-check", *options]
        log_path = output / (name + ".log")
        result = {"name": name, "command": command}
        with log_path.open("w") as log:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=log,
                                       stderr=subprocess.STDOUT, env=environment, text=True,
                                       start_new_session=True)
            try:
                wait_for(process, lambda: "testpmd>" in log_path.read_text(), "CLI prompt")
                exercise(process, log_path, result)
            finally:
                stop(process)
                result["exit_status"] = process.returncode
                record["results"].append(result)
        if process.returncode != 0:
            raise RuntimeError(f"{name}: testpmd exited {process.returncode}")

    def forwarding(process, log_path, result):
        process.stdin.write("start\n")
        process.stdin.flush()
        wait_for(process, lambda: "Packet forwarding started" in log_path.read_text()
                 or "txonly packet forwarding" in log_path.read_text(), "forwarding start")
        # Poll real port counters rather than treating a prompt as a forwarding pass.
        def transmitted():
            process.stdin.write("show port stats all\n")
            process.stdin.flush()
            counts = re.findall(r"TX-packets:\s*(\d+)", log_path.read_text())
            return bool(counts and max(map(int, counts)) > 0)
        wait_for(process, transmitted, "nonzero transmitted packet count")
        process.stdin.write("stop\n")
        process.stdin.flush()
        result["tx_packets"] = max(map(int, re.findall(
            r"TX-packets:\s*(\d+)", log_path.read_text())))

    try:
        if args.only != "ethdev":
            for name, options in (("numa-forwarding", []),
                                  ("no-numa-forwarding", ["--no-numa"])):
                run_testpmd(name, "net_ring0", ["--forward-mode=txonly", *options], forwarding)
        if args.only != "forwarding":
            with tempfile.TemporaryDirectory(prefix="cvm-ethdev-", dir="/tmp") as runtime:
                socket = str(Path(runtime) / "vhost.sock")

                def ethdev(process, log_path, result):
                    binary = build / "app/dpdk-test"
                    command = [str(binary), *eal(cpus[2:]),
                               f"--vdev=net_virtio_user0,path={socket},queues=2,queue_size=512"]
                    env = dict(environment, DPDK_TEST="ethdev_api")
                    with (output / "ethdev_api.log").open("w") as log:
                        completed = subprocess.run(command, env=env, stdout=log,
                                                   stderr=subprocess.STDOUT, timeout=120)
                    result["frontend_command"] = command
                    result["frontend_sha256"] = hashlib.sha256(binary.read_bytes()).hexdigest()
                    result["frontend_exit_status"] = completed.returncode
                    if completed.returncode != 0:
                        raise RuntimeError(f"ethdev_api exited {completed.returncode}")
                    text = (output / "ethdev_api.log").read_text()
                    if "ethdev_api_queue_status succeeded" not in text or "Test OK" not in text:
                        raise RuntimeError("ethdev_api did not execute its queue-state case")

                run_testpmd("ethdev-vhost-backend", f"net_vhost0,iface={socket},queues=2",
                            ["--no-numa", "--rxq=2", "--txq=2"], ethdev)
    except (RuntimeError, subprocess.TimeoutExpired, BrokenPipeError) as error:
        record["error"] = str(error)
        print(error, flush=True)
        return 1
    finally:
        (output / "results.json").write_text(json.dumps(record, indent=2) + "\n")
    print("PASS: " + ", ".join(r["name"] for r in record["results"]), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
