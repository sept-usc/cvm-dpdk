# Production-code regressions

These tests require a built, patched DPDK 25.11.3 tree. They need no NIC,
kernel module, hugepages, root privileges, or SNP guest. They use actual DPDK
mbufs, pools and forwarding functions; they do not model the PMD in a separate
implementation.

These are CVM-DPDK regressions, not the complete original DPDK test suite.
The separate [upstream test audit](../../docs/VALIDATION-2026-10-21-upstream-tests.md)
records the original suite's passes, skips and failures, including comparisons
against the unmodified release and supplemental SNP hugepage runs.

The [upstream failure fixes](../../docs/VALIDATION-2026-10-21-upstream-fixes.md)
add targeted EFD, security and IPsec regressions to CI. Enable `crypto/null`
alongside the build's normal drivers, apply the full patch series, and run:

```sh
bash scripts/test-dpdk-upstream.sh /path/to/dpdk/build
```

This runs four original upstream commands with a 600-second limit per
command, no NIC or hugepages, and 2 GiB of memory. It records logs and exit
statuses under the build's `cvm-dpdk-upstream-tests/` directory and fails on
skips as well as errors. This targeted group does not replace the full audit.

For the CI software-device profile, also enable
`event/sw,event/skeleton,dma/skeleton,net/null,net/ring`
and run:

```sh
bash scripts/test-dpdk-upstream.sh /path/to/dpdk/build --software
python3 scripts/test-dpdk-registration.py /path/to/dpdk/build
```

The software profile uses two available CPUs on the same NUMA node (0 or 1,
as required by the upstream PMD test) and runs twelve commands, including
NULL crypto, eventdev common/self-tests, event crypto/DMA/TX/RX adapters, and
PMD software loopback. It supplies the required NULL crypto, skeleton DMA,
and ring Ethernet device instances. The RX adapter command uses 4 GiB of EAL
memory; the other commands use 2 GiB and run sequentially. Allow additional
RAM for the OS and the test process. The ring PMD result is a software-path
check, not a hardware throughput measurement.
The registration check runs twelve BPF cases through Meson and checks that
a build with `crypto/scheduler` disabled reports that command as skipped
(77), not unknown. This availability check is not a scheduler functional pass.
Logs remain under `meson-logs/` and `cvm-dpdk-upstream-tests/` in the build.

See the [test setup validation](../../docs/VALIDATION-2026-10-21-test-setup.md)
and [RX/PMD follow-up](../../docs/VALIDATION-2026-10-21-software-rx-pmd.md)
for before/after evidence and limits. RX interrupts, hugepage subprocess tests,
long mempool benchmarks and timing-sensitive timer tests are outside this
small CI profile.

For the separate extended software profile, also install the development
packages for Intel IPSec Multi-Buffer, OpenSSL, libelf and libpcap, plus
Clang with BPF support and `xxd`. Enable
`crypto/ipsec_mb,crypto/scheduler,crypto/openssl,event/dsw,event/skeleton,net/vhost`
alongside `bus/*,mempool/ring,net/null,net/ring`, then run:

```sh
bash scripts/test-dpdk-extended.sh /path/to/dpdk/build
```

This requires four available CPUs on one NUMA node, local Unix socket binding,
and up to 4 GiB of EAL memory plus process/OS overhead. It runs fourteen
commands, fails on top-level skips, and retains per-command logs and exit
statuses under `cvm-dpdk-extended-tests/`. The scheduler is enabled here;
the separate registration regression above still needs a scheduler-disabled
build. The [extended validation](../../docs/VALIDATION-2026-10-22-extended-tests.md)
records internal crypto skips and the before/after IPsec crash evidence.
The vhost RX interrupt test covers queue registration and lookup using real
epoll descriptors; it does not send packets or validate NIC interrupt delivery.
IPsec performance measures library prepare/process calls and bypasses actual
encryption, even though its setup now uses valid crypto sessions.

With `net/virtio`, `net/vhost`, `net/ring`, and both `test` and `test-pmd`
enabled, the CLI regression also exercises pool selection and `ethdev_api`:

```sh
python3 scripts/test-dpdk-cli.py /path/to/dpdk/build
```

It requires four CPUs on one NUMA node. Two sequential ring-PMD runs must
actually transmit packets with default NUMA allocation and with `--no-numa`.
A testpmd vhost backend then lets virtio-user execute the original queue-state
checks for two RX/TX queues, including before start and after stop. Each
process uses 512 MiB ordinary memory. This needs local Unix sockets but no
root, NIC or hugepages. `--only forwarding` and `--only ethdev` isolate the
groups. Logs and JSON results go under `cvm-dpdk-cli-tests/`; use `--output`
to select a fresh directory for a rerun. See the
[CLI validation](../../docs/VALIDATION-2026-10-22-cli-pools.md).

The four upstream mempool performance commands need a separate long profile:

```sh
python3 scripts/test-dpdk-mempool.py /path/to/dpdk/build
```

This selects eight allowed CPUs, allocates 6 GiB ordinary EAL memory, and runs
all four commands sequentially with a three-hour ceiling per command. Allow
additional process/OS memory and potentially several hours for the complete
invocation. The original one-second cases and iteration batches are unchanged;
the usual 600-second perf-suite timeout is shorter than even one command's
minimum case duration. Use `--cpus` with eight comma-separated CPU IDs to avoid
contended cores, and repeat `--test` to select particular commands. JSON results
and line-buffered logs go into a fresh `cvm-dpdk-mempool-tests/` directory;
`--output` selects another directory. Existing evidence is never overwritten.
Errors, skips and timeouts fail the runner. This profile is intentionally
outside the short CI jobs; benchmark timing on shared CPUs is not a controlled
performance measurement.

See the [long-profile evidence](../../docs/VALIDATION-2026-10-22-mempool.md)
for completed commands, negative memory controls and retained incomplete runs.

For the ARMv8 crypto command on an x86 host, use the separate
[ARM64 cross-build and QEMU profile](../../docs/VALIDATION-2026-10-22-arm64-emulation.md).
Its functional result is recorded as emulation, not native ARM qualification.

Apply the [complete patch series](../../patches/README.md), then build:

```sh
meson setup /path/to/dpdk/build /path/to/dpdk \
  -Dtests=true -Ddefault_library=static \
  '-Denable_drivers=bus/*,common/mlx5,net/mlx5,net/null,net/ring,mempool/ring' \
  -Denable_apps=test,test-pmd
ninja -C /path/to/dpdk/build
```

Meson, Ninja, a C compiler, binutils, pkg-config, NUMA/RDMA development files,
and OpenSSL development files are required. On Debian/Ubuntu the packages
include `meson ninja-build build-essential pkg-config libnuma-dev
libibverbs-dev libssl-dev python3-pyelftools`. If the optional installed
`libmtcr_ul.a` needs C++ symbols, add `-Dc_link_args=-lstdc++` to Meson.
OpenSSL enables the `cvmchunk` engine and its integration case.

From the CVM-DPDK root:

```sh
make test-dpdk DPDK_BUILD=/path/to/dpdk/build
python3 scripts/test-dpdk-integration.py /path/to/dpdk/build --sanitize
```

The runner reuses the build's compiler/linker commands, selects an allowed CPU,
disables PCI probing, and uses 256 MiB of ordinary memory. Generated executables
stay under the supplied build directory. `--only rx`, `--only tx`, and
`--only bridge` select a suite. The sanitizer mode instruments the included
PMD source, bridge, generators, checksum engine, and chunk protocol paths;
the rest of the DPDK libraries retain the original build's instrumentation.
LeakSanitizer needs permission to inspect threads; a restricted process
sandbox can prevent that check from running.

## Coverage

| Suite | Checks |
|---|---|
| RX PMD | Shared length/LRO/hash/opcode mutation after validation; owner wrap; CRC; capacity bounds; zero/CRC-only lengths; LRO/compressed/reserved formats; wrong/error opcodes; empty CQ; persistent stop and pool accounting |
| TX PMD | Shared counter mutation after validation; owner/consumer wrap; missing request; mismatched counter; wrong/error/compressed opcodes; empty CQ; no premature mbuf release |
| Bridge | Private snapshots, metadata sanitization, TX offloads, segmented packets, unknown/mixed pools, disguised shared payload, RX exhaustion, atomic TX rollback, malformed lengths, GSO indirect segments, partial TX/retry cleanup |
| Forwarding engines | `io`, `mac`, `macswap`, `5tswap`, `rxonly`, `txonly`, `flowgen`, `csum`, `icmpecho`, `noisy`, and OpenSSL-enabled `cvmchunk` |

`txonly` runs with one and two source segments; `flowgen` exercises reference
clones; `csum` runs with and without output splitting. GSO is checked through
the real segmentation library and bridge. `noisy` uses its unbuffered path.
The authenticated case sends a corrupted chunk, a valid retry, and a duplicate,
then authenticates the resulting ACKs. Every bridge case checks pool balances.

`ieee1588`, `recycle_mbufs`, and `shared_rxq` must return an explicit unsupported
result while the CVM bridge is enabled. Ordinary operation without a registered
CVM pool remains unchanged.

## Negative control

To prove the mutation tests detect the old behavior, retain an unmodified tree
through patch 0008 and run each PMD suite against that source with the current
build's compatible headers/libraries:

```sh
python3 scripts/test-dpdk-integration.py /path/to/dpdk/build \
  --only rx --pmd-source /path/to/tree-through-0008
python3 scripts/test-dpdk-integration.py /path/to/dpdk/build \
  --only tx --pmd-source /path/to/tree-through-0008
```

Both commands should fail their first assertion: RX observes the changed
packet length and TX observes the changed completion counter. Alternate-source
executables are kept separate from current-source executables.

## Limits

The external data rooms in these fixtures are ordinary host allocations, not
SNP shared pages. CQ rings and doorbells are in test memory. These tests prove
software behavior and ownership, not NIC DMA ordering or a live host attack.
Virtual forwarding exercises representative configurations, not every offload
or CLI combination. Hardware qualification and throughput measurements remain
separate from these regressions.
