# Upstream test status — 2026-10-22

Of the 246 commands in the original audit, 210 now have a recorded pass in at
least one tested configuration. This includes all 25 originally reported host
failures. Another 36 commands still have no recorded pass; all 36 were originally
skipped. One timer test also retains an unexplained intermittent failure.

These numbers reconcile evidence across dates, native software builds, ARM64 emulation and
the SNP guest's hugepage profile. They are **not a new full-suite run**, do not mean
every configuration passes, and do not erase internal unsupported subcase skips.
The [status JSON](results/2026-10-22-upstream-status.json) maps each resolved
original failure to a passing record and lists every remaining command.

## Changes in this follow-up

| Work | Result and evidence |
|---|---|
| IPsec performance fixture | Patch 0014 creates valid crypto sessions and propagates preparation errors; the original four benchmark configurations pass. Previously, enabling OpenSSL exposed an address-zero crash in pristine and patched DPDK. [Report](VALIDATION-2026-10-22-extended-tests.md) |
| Non-NUMA forwarding pool | Patch 0015 selects the `SOCKET_ID_ANY` pool used by `testpmd --no-numa` and retains private-pool resolution. Both NUMA modes transmit packets; the old patched binary failed startup and pristine txonly crashed. [Report](VALIDATION-2026-10-22-cli-pools.md) |
| Optional software tests | Fourteen commands now pass with the necessary drivers, dependencies and memory, including scheduler, software crypto, BPF ELF, dispatcher, pcapng and the vhost RX interrupt control-path fixture. [Report](VALIDATION-2026-10-22-extended-tests.md) |
| Ethdev API | A local vhost/virtio-user pair exercises the original two-queue state assertions. [Report](VALIDATION-2026-10-22-cli-pools.md) |
| Mempool performance | All four original commands complete with eight enabled lcores, 6 GiB and a three-hour per-command outer ceiling. Source and workload are unchanged; 2 GiB negative controls still fail. [Report](VALIDATION-2026-10-22-mempool.md) |
| ARMv8 crypto | The original command passes 19 supported subcases under explicit ARM64 user emulation, retaining 906 skips. [Report](VALIDATION-2026-10-22-arm64-emulation.md) |
| Timer repeatability | Six further runs pass 31/31 subcases. No timer code or deadline was changed; the earlier timing failure remains unexplained. [Report](VALIDATION-2026-10-22-timer-followup.md) |

The maintained CI profiles now execute 39 native upstream commands and one
ARM64 command under emulation, alongside 48 production-code regressions and two
testpmd forwarding checks. The long mempool profile and hardware qualification
are separate. The latest code checkpoint, `ab0775d`, passed
[portable checks](https://github.com/sept-usc/cvm-dpdk/actions/runs/39757329605),
[DPDK integration](https://github.com/sept-usc/cvm-dpdk/actions/runs/39757325411),
[extended software tests](https://github.com/sept-usc/cvm-dpdk/actions/runs/39757325360),
and [ARM64 emulation](https://github.com/sept-usc/cvm-dpdk/actions/runs/39757325293).
The fifteen-patch series was also reapplied to both recorded source baselines;
native and ASan/UBSan production regressions each passed all 48 checks.

## Remaining work and required environments

The [hardware prerequisite record](results/2026-10-22-hardware-prerequisites.json)
contains the local capability probe and availability checks. The 36 remaining
commands comprise 26 crypto commands, six hardware event-device self-tests,
and four inline-security commands.

| Remaining group | What is needed next |
|---|---|
| `cryptodev_mlx5_autotest` | A crypto-capable device/configuration. An explicit crypto-only probe of the available ConnectX-7 still returned 77: the PMD reported insufficient capabilities and skipped all 925 subcases. The message does not establish whether firmware, configuration or another prerequisite is responsible. |
| `cryptodev_ccp_autotest` | A supported CCP device or separately validated driver support. The host exposes AMD `1022:14ca`; this release's CCP PMD lists `1456`, `1468` and `15df`, not `14ca`. Kernel binding was not changed. |
| MVSAM and UADK crypto | A compatible Marvell EIP197 platform with MUSDK/modules, or supported UADK accelerator access. This x86 host has no UACCE class. The `sw` naming on MVSAM does not make it a generic software backend. |
| Four virtio/virtio-user crypto commands | A compatible virtio-crypto device/backend. This release's virtio-user crypto driver selects vhost-vDPA, and this host has no exposed vDPA bus or vhost-vDPA node. The passing network virtio fixture is insufficient. |
| Other crypto commands | QAT, DPAA/DPAA2, CAAM JR, OCTEON/CN9K/CN10K, NITROX, BCMFS and ZSDA devices/platforms with their corresponding PMDs and test profiles, including raw API/asymmetric variants. |
| Six `eventdev_selftest_*` commands | OCTEONTX, DPAA2, DLB2, CN9K, CN10K or CN20K event hardware and the matching PMD. |
| Four inline-security commands | Qualified inline MACsec/IPsec offload ports and the test-specific configuration, including scatter/gather and event variants. |

A new isolated QEMU guest probe has now reached the virtio-crypto PCI path.
With the initial UIO configuration, device probing fails and both original
virtio crypto commands crash during device enumeration. This new failure is
under investigation; those two commands still have no passing record. The
[initial probe record](results/2026-10-22-virtio-probe.json) retains both failures.

The next actionable step for the other commands is to provision the matching test
environment and retain the first failing log, rather than weaken capability
checks. For the timer issue, capture a failure-time scheduler/event trace before
changing deadlines or the timer implementation. Current evidence does not
support a further code fix for either category.
