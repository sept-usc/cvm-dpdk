# Forwarding pool selection and ethdev API — 2026-10-22

While providing a software device for the skipped `ethdev_api` command,
testpmd failed to start with `--no-numa`, including ordinary native memory.
This exposed an upstream pool-selection defect whose startup behavior had
changed with CVM-DPDK's forwarding-pool validation.

## Failure and correction

With NUMA disabled, `init_config()` creates its pool with `SOCKET_ID_ANY`.
RX queue setup correctly looks up that pool. Forwarding-lcore setup instead
looked up the lcore's socket, then socket 0; neither name matched.

In pristine DPDK, the forwarding pool stayed NULL. The CLI could start, but
`txonly` subsequently crashed with SIGSEGV. With patch 0010's private-pool
selection and fail-closed check, the same configuration exited immediately
with `No application mbuf pool for lcore 0`. Thus the earlier check prevented
the null dereference but also rejected a configuration that should work.

Patch 0015 selects `SOCKET_ID_ANY` for non-NUMA forwarding, matching creation
and RX queue selection. NUMA-enabled selection retains its existing behavior.
The selected pool still passes through `cvm_mbuf_bridge_cpu_pool()`; registered
CVM pools still resolve to their private peers, and unknown pools are still
rejected while the bridge is active.

## Validation

The maintained regression uses two lcores and a ring Ethernet device to run
actual `txonly` forwarding, then requires a positive TX packet counter:

| Binary / mode | Result |
|---|---|
| Pristine release, NUMA enabled | Pass |
| Pristine release, `--no-numa` | SIGSEGV after forwarding starts |
| CVM-DPDK through 0014, NUMA enabled | Pass |
| CVM-DPDK through 0014, `--no-numa` | Exit 1 before CLI prompt |
| CVM-DPDK through 0015, NUMA enabled | Pass; 1,023 packets transmitted |
| CVM-DPDK through 0015, `--no-numa` | Pass; 1,023 packets transmitted |

The ring fills during TX-only forwarding; these counters are evidence of
working packet allocation and TX, not a zero-loss or throughput benchmark.
The original failing binary is retained and the same regression rejects it.

The second group starts a non-NUMA testpmd vhost backend and connects a
virtio-user frontend running the unchanged `ethdev_api` command. Virtio
implements RX/TX queue-info callbacks, so the command actually checks the
two queues' initial, started and stopped states. Its single subcase passes
with no skip. Both processes exit cleanly. This avoids claiming queue-state
coverage from a PMD that returns `-ENOTSUP` for those callbacks.

```sh
python3 scripts/test-dpdk-cli.py /path/to/dpdk-build
```

The full runner passed with four allowed CPUs on NUMA node 0, PCI probing
disabled and 512 MiB ordinary memory per process. It uses a temporary Unix
socket and no physical device. An initial runner attempt buffered stdout and
timed out waiting for a diagnostic; line-buffered testpmd output corrected
that harness issue before interpreting the forwarding results.

The build, 48 production-code regressions, and their ASan/UBSan variants pass.
The fifteen-patch series was reapplied from both recorded clean baselines
and its resulting trees match the manifests. The extended CI workflow now
builds testpmd and virtio and runs the same CLI regression.

This is software validation. It adds no hardware DMA, SNP shared-allocation,
private-bridge traffic or physical interrupt measurement. The existing bridge
tests separately exercise private-pool resolution and forwarding ownership.

The [machine-readable record](results/2026-10-22-cli-pools.json) retains commands,
hashes, counters and negative controls. Raw logs remain under
`/tmp/cvm-dpdk-followup-20261022`.
