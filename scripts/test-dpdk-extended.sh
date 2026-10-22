#!/usr/bin/env bash
# Optional software PMDs and their original upstream tests; no physical NIC.
set -euo pipefail

if [[ $# != 1 ]]; then
    echo "Usage: $0 /path/to/dpdk-build" >&2
    exit 2
fi
build=$(realpath -- "$1")
binary="$build/app/dpdk-test"
logs="$build/cvm-dpdk-extended-tests"
mkdir -p -- "$logs"
cpus=$(python3 - <<'PY'
import os
from pathlib import Path

groups = {}
for cpu in sorted(os.sched_getaffinity(0)):
    nodes = list(Path(f"/sys/devices/system/cpu/cpu{cpu}").glob("node[0-9]*"))
    node = int(nodes[0].name[4:]) if nodes else 0
    groups.setdefault(node, []).append(cpu)
cpus = next((group[:4] for group in groups.values() if len(group) >= 4), None)
if cpus is None:
    raise SystemExit("Extended tests require four available CPUs on one NUMA node")
print(','.join(map(str, cpus)))
PY
)
# Keep the Unix socket below sockaddr_un's path length limit.
runtime=$(mktemp -d /tmp/cvm-dpdk-extended.XXXXXXXX)
trap 'rm -rf -- "$runtime"' EXIT
tests=(cryptodev_scheduler_autotest dispatcher_autotest bpf_elf_autotest
    pcapng_autotest cryptodev_aesni_mb_autotest cryptodev_cpu_aesni_mb_autotest
    cryptodev_aesni_gcm_autotest cryptodev_cpu_aesni_gcm_autotest
    cryptodev_chacha_poly_mb_autotest cryptodev_sw_snow3g_autotest
    cryptodev_sw_kasumi_autotest cryptodev_sw_zuc_autotest
    ipsec_perf_autotest event_eth_rx_intr_adapter_autotest)
status=0
printf 'test\texit_status\n' > "$logs/results.tsv"
sha256sum -- "$binary" > "$logs/binary.sha256"
for test in "${tests[@]}"; do
    memory=2048
    devices=()
    case "$test" in
        cryptodev_aesni_mb_autotest|cryptodev_cpu_aesni_mb_autotest)
            devices+=(--vdev=crypto_aesni_mb0) ;;
        cryptodev_aesni_gcm_autotest|cryptodev_cpu_aesni_gcm_autotest)
            devices+=(--vdev=crypto_aesni_gcm0) ;;
        cryptodev_chacha_poly_mb_autotest) devices+=(--vdev=crypto_chacha20_poly13050) ;;
        cryptodev_sw_snow3g_autotest) devices+=(--vdev=crypto_snow3g0) ;;
        cryptodev_sw_kasumi_autotest) devices+=(--vdev=crypto_kasumi0) ;;
        cryptodev_sw_zuc_autotest) devices+=(--vdev=crypto_zuc0) ;;
        ipsec_perf_autotest) devices+=(--vdev=crypto_openssl0) ;;
        event_eth_rx_intr_adapter_autotest)
            memory=4096
            devices+=("--vdev=net_vhost0,iface=$runtime/rx.sock,queues=4") ;;
    esac
    args=(-l "$cpus" --no-huge -m "$memory" --no-pci --no-shconf --no-telemetry)
    printf 'DPDK_TEST=%q ' "$test" > "$logs/$test.log"
    printf '%q ' "$binary" "${args[@]}" "${devices[@]}" >> "$logs/$test.log"
    printf '\n' >> "$logs/$test.log"
    if timeout --kill-after=10s 600 env -u DPDK_TEST_PARAMS -u DPDK_TEST_SKIP \
        DPDK_TEST="$test" "$binary" "${args[@]}" "${devices[@]}" >> "$logs/$test.log" 2>&1; then
        code=0
    else
        code=$?
        status=1
        tail -40 -- "$logs/$test.log"
    fi
    printf '%s\t%s\n' "$test" "$code" | tee -a "$logs/results.tsv"
done
# Top-level skips are failures; unsupported crypto subcases remain in the logs.
exit "$status"
