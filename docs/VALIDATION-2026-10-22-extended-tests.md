# Extended upstream tests — 2026-10-22

Starting at repository revision `b60752d6f785`, fourteen additional maintained
upstream commands now pass locally. This combines optional dependency/device
setup with one test-fixture correction. It does not replace the historical
246-entry audit or establish a new full-suite pass count.

## IPsec performance: a skipped test concealed a crash

`ipsec_perf_autotest` previously skipped because no crypto device was provided.
With `--vdev=crypto_openssl0`, both pristine DPDK 25.11.3 and our thirteen-patch
build crashed through address zero in `create_traffic()`. GDB reproduced this
with CPUs on NUMA node 0, ruling out the initial node-1 memory warning as a
necessary condition for this failure.

The fixture set `crypto.ses` to NULL. `rte_ipsec_session_prepare()` correctly
rejected that session, but `create_sa()` ignored the return value and reported
success. The benchmark then called the unset packet-function pointer.

Patch 0014 creates real symmetric sessions with synthetic keys before timing,
supplies the required key/AAD/IV parameters, checks preparation errors, and
releases both the crypto sessions and security associations between cases and
on setup failures. A two-object session pool services each inbound/outbound
pair and must be reusable across all four configurations. The signed SA-size
result is checked before allocation.

With OpenSSL, all four original ten-second configurations pass, covering
AES-GCM and AES-CBC/SHA1 with and without the ESN/replay-window configuration.
The first corrected run completed in 41.007 seconds (the collector polls
completion once per second). The maintained runner also passes. A NULL crypto
device, which lacks the required algorithms, now returns a normal test failure
(255) instead of a crash; absence of any crypto device still returns skip (77).

This benchmark deliberately bypasses crypto enqueue/dequeue and encryption.
Its metrics concern IPsec prepare/process calls, not authenticated throughput.
No workload, assertion or per-configuration duration was reduced.

## Optional software coverage

The exact maintained runner is:

```sh
bash scripts/test-dpdk-extended.sh /path/to/dpdk-build
```

| Command | Executed subcases passed | Existing skipped subcases |
|---|---:|---:|
| `cryptodev_scheduler_autotest` | 874 | 184 |
| `cryptodev_aesni_mb_autotest` | 639 | 286 |
| `cryptodev_cpu_aesni_mb_autotest` | 306 | 619 |
| `cryptodev_aesni_gcm_autotest` | 83 | 842 |
| `cryptodev_cpu_aesni_gcm_autotest` | 78 | 847 |
| `cryptodev_chacha_poly_mb_autotest` | 6 | 919 |
| `cryptodev_sw_snow3g_autotest` | 45 | 880 |
| `cryptodev_sw_kasumi_autotest` | 31 | 894 |
| `cryptodev_sw_zuc_autotest` | 31 | 894 |
| `dispatcher_autotest` | 4 | 0 |
| `pcapng_autotest` | 2 | 0 |
| `event_eth_rx_intr_adapter_autotest` | 2 | 0 |

The remaining two commands are `bpf_elf_autotest` (ELF load, TX and RX paths)
and `ipsec_perf_autotest` (the four configurations above). Both return zero.
Top-level success does not mean that every algorithm in the generic crypto
suite is supported. The internal skips remain visible in the logs.

Scheduler needs `crypto/scheduler`, `crypto/ipsec_mb` and two worker lcores;
its upstream fixture creates its devices. Dispatcher needs `event/dsw` and
four lcores. BPF ELF needs libelf, Clang's BPF target and `xxd`. Pcapng needs
libpcap development metadata, including its transitive pkg-config dependencies.
The individual crypto commands receive their corresponding software vdev.
These are setup corrections, not changes to driver implementations.

The scheduler, dispatcher, BPF ELF, pcapng and RX interrupt commands also
pass with the unmodified official release in the expanded software build.
All 6,953 regular archive files in that pristine source directory were
byte-compared with the verified release archive; none differed.

## RX interrupt scope

`net_null` does not supply RX interrupt descriptors. The runner supplies
`net_vhost0,iface=<private-temporary-socket>,queues=4` with 4 GiB ordinary
memory. The vhost PMD creates actual epoll descriptors, letting the original
adapter tests add/remove interrupt queues, switch queues to polling, and
check instance lookup and invalid IDs. Both subcases pass without modification.

There is no connected guest, transmitted packet, NIC DMA or hardware interrupt
in this fixture. It verifies the upstream control-path assertions, not delivery
of a packet-triggered notification. An initial sandboxed attempt could not
bind its Unix socket and failed; that attempt is retained separately. The
successful runs used an IPC-capable environment with PCI probing disabled.

## Reproduction and evidence

Apply all fourteen patches. The [test guide](../tests/dpdk/README.md) lists
dependencies and drivers. The separate `DPDK extended software tests` workflow
builds this profile; the original integration job retains its disabled-scheduler
registration check. Revision `0c94886f6388` passed
[portable checks](https://github.com/sept-usc/cvm-dpdk/actions/runs/39747428864),
[DPDK integration](https://github.com/sept-usc/cvm-dpdk/actions/runs/39747428989),
and the new [extended software tests](https://github.com/sept-usc/cvm-dpdk/actions/runs/39747428901).
The detailed counts above describe the local build; CI's dependency versions
and unsupported crypto subcases may differ.

Local tests used GCC 15.2.0, generic static DPDK, Intel IPSec Multi-Buffer
2.0.1, and four selected lcores for the maintained runner. Other workloads
and the long mempool tests shared the machine; cycle counts are not controlled
performance comparisons. The full build and existing 48 production-code
regressions pass. The full patch series was applied from both recorded
baselines and the resulting tree hashes were checked.

The [machine-readable evidence](results/2026-10-22-extended-tests.json) contains
binary hashes, commands, status codes, subcase counts and controls. Large raw
logs and build products stay under `/tmp/cvm-dpdk-followup-20261022`.
The long mempool runs and timer investigation are separate work; hardware-only
skips remain outside this software profile.
