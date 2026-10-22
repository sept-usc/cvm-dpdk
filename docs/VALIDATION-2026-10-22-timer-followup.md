# Timer repeatability — 2026-10-22

The initially failing `event_timer_adapter_test` was run six more times on
the shared host. All six runs passed all 31 subcases. This is additional
repeatability evidence, not a fix or an explanation of the original failure.

The preserved thirteen-patch software build was used with CPUs 16–23,
2 GiB ordinary memory, `--no-pci --no-shconf --no-telemetry`, and a 600-second
outer limit. Each process used `DPDK_TEST=event_timer_adapter_test`; inherited
`DPDK_TEST_PARAMS` and `DPDK_TEST_SKIP` were removed. Each observed duration
was approximately 225 seconds, including the collector's one-second polling
granularity. No timer deadline, assertion or implementation was changed.

The first three runs were launched through `stdbuf`. Inspection showed that
this host's wrapper kept a separate parent process, so the attempted
`/proc/<pid>/task/*/schedstat` collection sampled the wrapper rather than DPDK.
Those samples are not useful scheduler evidence; their test results remain
valid and are retained separately.

The next three runs launched `dpdk-test` directly. The collector sampled the
main, interrupt and worker threads approximately once per second, recording
CPU runtime, runqueue wait time and scheduler slice counts. The result file
contains per-thread summaries and actual sample intervals. These snapshots
cannot reconstruct event-queue state or precisely attribute an individual
timer deadline; a failure-time scheduler/event trace is still needed.

The mempool benchmarks and other host workloads ran concurrently on other
selected CPU ranges. CPUs were not reserved exclusively. These successful
runs do not establish that scheduling caused the historical failure, nor
do they establish immunity to timing failures under other workloads.

The [machine-readable record](results/2026-10-22-timer-followup.json) retains
all six commands, binary hashes, statuses, durations and the useful scheduling
summaries. Raw logs and samples remain under
`/tmp/cvm-dpdk-followup-20261022/timer` and `timer-direct`.
