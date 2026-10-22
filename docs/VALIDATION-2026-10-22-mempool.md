# Mempool long-profile validation — 2026-10-22

All four originally failing mempool performance commands completed with exit
status zero using eight enabled lcores and 6 GiB ordinary memory. This is a
test-profile correction. The mempool test source is byte-identical to the
official DPDK 25.11.3 release; no workload, assertion, pool size or inner timing
was reduced.

| Command | Completed combinations | Selected CPUs |
|---|---:|---|
| `mempool_perf_autotest` | 3,420 | 0–7 |
| `mempool_perf_autotest_1core` | 1,140 | 8–15 |
| `mempool_perf_autotest_2cores` | 1,140 | 8–15 |
| `mempool_perf_autotest_allcores` | 1,140 | 16–23 |

The aggregate command exercises one-core, two-core and eight-core configurations.
Each standalone command exercises one of those configurations, with all eight
lcores still enabled during EAL initialization. All commands cover the original
uncached, built-in-cache and user-owned-cache modes. The ring mempool handlers
in this build give 380 combinations per cache mode and core count.

## Why the original profile failed

Pool sizing uses the enabled EAL lcore count, including for the commands that
only measure one or two cores. Eight lcores give 270,335 objects in each of four
pools. Their 2,048-byte payloads alone exceed 2 GiB before object metadata,
alignment, rings and other allocations. The successful run's pool dumps show
2,112-byte objects including headers, occupying one object per 4 KiB page in
this ordinary-memory configuration. Each pool's memory chunk is 1,107,292,288
bytes; the four chunks consume approximately 4.125 GiB before other allocations.
The default mempool allocator accounts for page boundaries when sizing and
populating these objects. This explains the 6 GiB profile and why allocation
already fails at the second pool with 2 GiB.

A new 2 GiB negative control with the
same preserved binary and eight enabled lcores reproduced allocation failure
(exit 255) for all four commands.

The original short timeout is also inappropriate after allocation succeeds.
Each standalone command has 1,140 combinations with an inner duration of at
least one second. An iteration processes a fixed batch before checking time,
so contended combinations can run much longer. The new outer ceiling is three
hours per command; it does not change the benchmark's inner timer.

## Preserved incomplete attempt

The first independent eight-core run on CPUs 8–15 was stopped after 169 of
1,140 combinations and 1,520.995 seconds. It had made progress without an
assertion failure, but several workers accumulated large runqueue waits.
This deliberately terminated attempt returned nonzero and is **not a pass**.

The entire eight-core command was then restarted on CPUs 16–23, retaining eight
lcores, 6 GiB, the original workload and every combination. Its successful
result is the one listed above. The record retains both attempts and the
thread scheduling snapshots that motivated changing affinity. These observations
do not identify all causes of the timing difference or establish a controlled
performance improvement. Other workloads shared this host throughout.

## Reproduction and evidence

```sh
python3 scripts/test-dpdk-mempool.py /path/to/dpdk/build \
  --cpus 16,17,18,19,20,21,22,23
```

The runner selects eight allowed CPUs by default, allocates 6 GiB, and executes
all four commands sequentially. Use repeated `--test` options to select commands
and `--output` for a fresh evidence directory. It preserves exit codes, elapsed
times, CPU IDs, commands, binary hashes and line-buffered logs. Budget several
hours for the complete profile; it is intentionally outside short CI jobs.

The [machine-readable record](results/2026-10-22-mempool.json) contains the four
passes, log hashes, exact combination counts, all four 2 GiB negative controls,
and the incomplete attempt. The preserved thirteen-patch binary was not rebuilt
during these long runs. Patches 0014 and 0015 affect the IPsec performance fixture
and testpmd forwarding respectively; neither changes mempool code. The current
test source and official-release source have the same SHA-256 recorded there.
The aggregate command was launched before the maintained runner, so its elapsed
duration is not claimed. Raw logs remain under
`/tmp/cvm-dpdk-followup-20261022`.
