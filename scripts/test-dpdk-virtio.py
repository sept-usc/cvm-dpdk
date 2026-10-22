#!/usr/bin/env python3
"""Validate virtio crypto in disposable, diskless QEMU TCG guests."""

import argparse
import gzip
import hashlib
import json
import lzma
import os
from pathlib import Path
import re
import shlex
import shutil
import stat
import subprocess
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
SYMMETRIC = "cryptodev_virtio_autotest"
ASYMMETRIC = "cryptodev_virtio_asym_autotest"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compile_session_check(build, output):
    database = json.loads((build / "compile_commands.json").read_text())
    entry = next(row for row in database if row["file"].endswith("/app/test/test.c"))
    command, skip = [], False
    for word in shlex.split(entry["command"]):
        if skip:
            skip = False
        elif word in ("-o", "-MF", "-MQ", "-MT"):
            skip = True
        elif word not in ("-c", "-MD", "-MMD", entry["file"]):
            command.append(word)
    obj = output / "session-check.o"
    binary = output / "session-check"
    subprocess.run(command + ["-c", str(ROOT / "tests/dpdk/test_virtio_session_error.c"),
                              "-o", str(obj)], cwd=build, check=True)
    commands = subprocess.check_output(["ninja", "-t", "commands", "app/dpdk-test"],
                                       cwd=build, text=True).splitlines()
    link = next(shlex.split(line) for line in reversed(commands)
                if " -o app/dpdk-test " in line)
    link = [word for word in link if not word.startswith("app/dpdk-test.p/")]
    link[link.index("-o") + 1] = str(binary)
    link.insert(link.index("-o"), str(obj))
    subprocess.run(link, cwd=build, check=True)
    return binary


def module_bytes(directory, name):
    paths = list(directory.glob(name + ".ko*"))
    if len(paths) != 1:
        raise RuntimeError(f"Expected one {name}.ko module in {directory}")
    path = paths[0]
    if path.suffix == ".zst":
        return subprocess.check_output(["zstd", "-dc", str(path)])
    if path.suffix == ".xz":
        return lzma.decompress(path.read_bytes())
    if path.suffix == ".gz":
        return gzip.decompress(path.read_bytes())
    return path.read_bytes()


def make_initramfs(path, program, busybox, modules, tests, bind):
    entries = {}
    for name in ("bin", "dev", "proc", "sys", "tmp", "run", "var", "var/run",
                 "mnt", "mnt/huge", "lib", "lib/x86_64-linux-gnu", "lib64", "modules"):
        entries[name] = (stat.S_IFDIR | 0o755, b"", 0, 0)
    for name, source in (("bin/busybox", busybox), ("test-program", program)):
        entries[name] = (stat.S_IFREG | 0o755, source.read_bytes(), 0, 0)
        result = subprocess.run(["ldd", str(source)], capture_output=True, text=True)
        if result.returncode and not any(s in result.stdout + result.stderr for s in
                                         ("not a dynamic executable", "statically linked")):
            raise RuntimeError(f"Cannot inspect runtime dependencies of {source}")
        if "not found" in result.stdout:
            raise RuntimeError(f"Missing runtime dependency: {result.stdout}")
        for library in re.findall(r"(/\S+) \(", result.stdout):
            source_lib = Path(library)
            directory = "lib64" if source_lib.name.startswith("ld-linux") else "lib/x86_64-linux-gnu"
            entries[directory + "/" + source_lib.name] = (stat.S_IFREG | 0o755, source_lib.read_bytes(), 0, 0)
    for name, data in modules.items():
        entries["modules/" + name + ".ko"] = (stat.S_IFREG | 0o644, data, 0, 0)
    entries["bin/sh"] = (stat.S_IFLNK | 0o777, b"busybox", 0, 0)
    entries["dev/console"] = (stat.S_IFCHR | 0o600, b"", 5, 1)
    entries["dev/null"] = (stat.S_IFCHR | 0o666, b"", 1, 3)
    setup = ": keep the device bound to virtio-pci for the failed-probe regression"
    if bind:
        setup = """echo 0000:00:04.0 > /sys/bus/pci/drivers/virtio-pci/unbind || fail unbind
echo '1af4 1054' > /sys/bus/pci/drivers/uio_pci_generic/new_id || fail bind
[ -e /dev/uio0 ] || fail missing_uio"""
    init = """#!/bin/sh
export PATH=/bin
bb=/bin/busybox
fail() { echo "VIRTIO_SETUP_FAILED $1"; $bb poweroff -f; }
$bb mount -t devtmpfs devtmpfs /dev || fail devtmpfs
$bb mount -t proc proc /proc || fail proc
$bb mount -t sysfs sysfs /sys || fail sysfs
$bb mount -t hugetlbfs hugetlbfs /mnt/huge || fail hugepages
$bb insmod /modules/uio.ko || fail uio
$bb insmod /modules/uio_pci_generic.ko || fail uio_pci_generic
case "$($bb readlink /sys/bus/pci/devices/0000:00:04.0/driver)" in
    */virtio-pci) ;;
    *) fail initial_binding ;;
esac
SETUP
for name in TEST_NAMES; do
    echo "VIRTIO_TEST_START $name"
    DPDK_TEST=$name /test-program -l 0,1 -m 1024 --no-shconf --no-telemetry --huge-dir=/mnt/huge --iova-mode=pa --file-prefix=$name -a 0000:00:04.0
    code=$?
    echo "VIRTIO_TEST_RESULT $name $code"
done
echo VIRTIO_GUEST_FINISHED
$bb poweroff -f
""".replace("SETUP\n", setup + "\n").replace("TEST_NAMES", " ".join(tests))
    entries["init"] = (stat.S_IFREG | 0o755, init.encode(), 0, 0)
    archive = bytearray()
    # Device nodes are encoded into the guest archive; no host mknod is needed.
    for name, (mode, data, major, minor) in list(entries.items()) + [("TRAILER!!!", (0, b"", 0, 0))]:
        encoded = name.encode() + b"\0"
        fields = [1, mode, 0, 0, 1, 0, len(data), 0, 0, major, minor, len(encoded), 0]
        archive.extend(b"070701" + "".join(f"{value:08x}" for value in fields).encode())
        archive.extend(encoded)
        archive.extend(b"\0" * (-len(archive) % 4))
        archive.extend(data)
        archive.extend(b"\0" * (-len(archive) % 4))
    path.write_bytes(gzip.compress(bytes(archive), mtime=0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build", type=Path)
    parser.add_argument("--backend-build", type=Path)
    parser.add_argument("--kernel", type=Path, required=True)
    parser.add_argument("--modules", type=Path, required=True,
                        help="Matching kernel/drivers/uio directory")
    parser.add_argument("--qemu", default="qemu-system-x86_64")
    parser.add_argument("--busybox", default="busybox")
    parser.add_argument("--cpus", help="Four allowed host CPU IDs, comma-separated")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    build = args.build.resolve()
    binary = build / "app/dpdk-test"
    backend = (args.backend_build or args.build).resolve() / "examples/dpdk-vhost_crypto"
    qemu, busybox = shutil.which(args.qemu), shutil.which(args.busybox)
    if not qemu or not busybox or not all(p.is_file() for p in (binary, backend, args.kernel)):
        parser.error("DPDK test/backend executables, QEMU, BusyBox and a readable guest kernel are required")
    allowed = os.sched_getaffinity(0)
    try:
        cpus = [int(value) for value in args.cpus.split(",")] if args.cpus else sorted(allowed)[:4]
    except ValueError:
        parser.error("--cpus must contain comma-separated integer CPU IDs")
    if len(cpus) != 4 or len(set(cpus)) != 4 or not set(cpus) <= allowed:
        parser.error("Four distinct allowed host CPUs are required")
    output = (args.output or build / "cvm-dpdk-virtio-tests").resolve()
    output.mkdir(parents=True, exist_ok=False)
    session_check = compile_session_check(build, output)
    modules = {name: module_bytes(args.modules, name) for name in ("uio", "uio_pci_generic")}
    environment = os.environ.copy()
    for key in ("DPDK_TEST", "DPDK_TEST_PARAMS", "DPDK_TEST_SKIP"):
        environment.pop(key, None)
    record = {
        "scope": "Diskless, networkless x86 guests under QEMU TCG; software crypto backends; no host PCI binding",
        "binary_sha256": digest(binary), "backend_sha256": digest(backend),
        "session_check_sha256": digest(session_check), "kernel_sha256": digest(args.kernel),
        "busybox_sha256": digest(Path(busybox)), "qemu_sha256": digest(Path(qemu)),
        "qemu_version": subprocess.check_output([qemu, "--version"], text=True).splitlines()[0],
        "module_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in modules.items()},
        "host_cpu_ids": cpus, "guest_cpus": 2, "guest_memory_mib": 3072,
        "guest_hugepage_count": 1024, "guest_hugepage_size_mib": 2,
        "guest_eal_memory_mib": 1024, "backend_eal_memory_mib": 1024,
        "timeout_seconds_per_guest": 900, "cases": [],
    }
    cases = [("failed-probe", binary, [SYMMETRIC, ASYMMETRIC], False, None, 77),
             ("session-rejection", session_check, ["virtio_session_error"], True, None, 0),
             ("symmetric", binary, [SYMMETRIC], True, "sym", 0),
             ("asymmetric", binary, [ASYMMETRIC], True, "asym", 0)]
    for name, program, tests, bind, mode, expected in cases:
        print(f"Running {name}; guest log: {output / (name + '.log')}", flush=True)
        initrd = output / (name + ".cpio.gz")
        make_initramfs(initrd, program, Path(busybox), modules, tests, bind)
        result = {"name": name, "expected_exit_status": expected, "initramfs_sha256": digest(initrd)}
        with tempfile.TemporaryDirectory(prefix="cvm-vcrypto-") as runtime:
            socket = Path(runtime) / "crypto.sock"
            process = None
            try:
                if mode:
                    command = [str(backend), "-l", ",".join(map(str, cpus[:2])), "--no-huge", "-m", "1024",
                               "--no-pci", "--no-shconf", "--no-telemetry", "--vdev=crypto_openssl0", "--",
                               "--config", f"({cpus[1]},0,0)", "--socket-file", f"{cpus[1]},{socket}"]
                    if mode == "asym":
                        command.append("--asymmetric-crypto")
                    result["backend_command"] = command
                    with (output / (name + "-backend.log")).open("w") as log:
                        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, env=environment)
                    deadline = time.monotonic() + 30
                    while not socket.exists():
                        if process.poll() is not None or time.monotonic() > deadline:
                            raise RuntimeError("Backend did not create its socket")
                        time.sleep(0.1)
                command = ["taskset", "-c", ",".join(map(str, cpus[2:])), qemu,
                           "-machine", "pc", "-accel", "tcg,thread=multi", "-cpu", "max", "-smp", "2", "-m", "3072",
                           "-nodefaults", "-display", "none", "-serial", "stdio", "-monitor", "none", "-nic", "none",
                           "-no-reboot", "-kernel", str(args.kernel.resolve()), "-initrd", str(initrd), "-append",
                           "console=ttyS0 rdinit=/init hugepagesz=2M hugepages=1024 panic=-1 random.trust_cpu=on"]
                if mode:
                    command += ["-object", "memory-backend-memfd,id=vmram,size=3G,share=on", "-numa", "node,memdev=vmram",
                                "-chardev", "socket,id=charcrypto,path=" + str(socket), "-object",
                                "cryptodev-vhost-user,id=crypto0,chardev=charcrypto"]
                else:
                    command += ["-object", "cryptodev-backend-builtin,id=crypto0,queues=1"]
                command += ["-device", "virtio-crypto-pci,cryptodev=crypto0,addr=0x4"]
                result["qemu_command"] = command
                start = time.monotonic()
                log_path = output / (name + ".log")
                with log_path.open("w") as log:
                    try:
                        result["qemu_exit_status"] = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                                                    timeout=900, env=environment, check=False).returncode
                    except subprocess.TimeoutExpired:
                        result["qemu_exit_status"] = 124
                result["duration_seconds"] = round(time.monotonic() - start, 3)
                text = log_path.read_text(errors="replace")
                result["log_sha256"] = digest(log_path)
                result["guest_finished"] = "VIRTIO_GUEST_FINISHED" in text
                result["results"] = [{"name": test, "exit_status": int(code)} for test, code in
                                     re.findall(r"VIRTIO_TEST_RESULT (\S+) (\d+)", text)]
                result["subcases"] = {key.lower(): int(value) for key, value in
                                      re.findall(r"\+ Tests (Total|Skipped|Executed|Unsupported|Passed|Failed)\s*:\s*(\d+)", text)}
                result["passed"] = (result["qemu_exit_status"] == 0 and result["guest_finished"] and
                                    result["results"] == [{"name": test, "exit_status": expected} for test in tests])
                if mode:
                    result["passed"] &= result["subcases"].get("passed", 0) > 0 and result["subcases"].get("failed") == 0
                if name == "session-rejection":
                    result["passed"] &= "PASS: backend rejection returns EIO, pool recovers, cipher session succeeds" in text
            except (OSError, RuntimeError) as error:
                result.update(passed=False, error=str(error))
            finally:
                if process is not None:
                    if process.poll() is None:
                        process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    result["backend_exit_after_guest"] = process.returncode
                    result["backend_stopped_by_runner"] = True
        record["cases"].append(result)
        (output / "results.json").write_text(json.dumps(record, indent=2) + "\n")
        print(f"{name}: {'PASS' if result['passed'] else 'FAIL'}", flush=True)
    return int(any(not case["passed"] for case in record["cases"]))


if __name__ == "__main__":
    raise SystemExit(main())
