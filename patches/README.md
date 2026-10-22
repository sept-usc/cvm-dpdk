# DPDK patch series

`dpdk-25.11.3/series` is the authoritative application order. Apply the whole
series to the exact baseline; the early patches alone do not include the
validated completion guards or resource-lifetime fixes.

## Baseline and installation

Two exact baselines are supported. The recommended one is the official
[DPDK 25.11.3 release archive](https://fast.dpdk.org/rel/dpdk-25.11.3.tar.xz).
`RELEASE_SHA256` identifies the archive; `RELEASE_BASE_TREE` and
`RELEASE_RESULT_TREE` identify the complete imported and patched trees.

The original CVM checkout imported the source as local root commit
`9d1130944dfc9ad9dc75b7b4bf37fdbd68c48c2c`, **not an upstream DPDK commit ID**.
`BASE`, `BASE_TREE`, and `RESULT_TREE` retain that historical provenance.
Unlike the official release, that import replaced `.gitignore` and included
one generated `buildtools/__pycache__/coff.cpython-314.pyc` file. All other
tracked files match the fully imported release. The historical bytecode is
not distributed by CVM-DPDK and is not needed for new builds.

Verify the downloaded archive against `RELEASE_SHA256`. In a freshly extracted
release directory, initialize and commit the entire tree **before building**:

```sh
cd /path/to/dpdk-stable-25.11.3
git init
git add -f .
git commit -m 'Import unmodified DPDK 25.11.3'
```

The force-add is intentional only for this fresh release: upstream ignore
patterns also match shipped source/configuration files. Ordinary `git add .`
omits them and produces a different tree. Do not force-add a directory that
already contains build outputs or local files.

From this repository, run:

```sh
bash scripts/apply-dpdk-patches.sh /path/to/dpdk-stable-25.11.3
```

The script checks that the checkout is clean and its tree matches one of the
two exact baselines, applies the series with `git am`, and checks the
corresponding result tree.
It aborts and rolls back the series if patch application fails. A source tree
that differs from the recorded release is rejected before any changes.

## Contents and provenance

| Patch | Change | Original CVM source |
|---|---|---|
| 0001 | mlx5 glue support for DevX dma-buf UMEM registration | `7345b49` |
| 0002 | dma-buf-backed memory registration and DevX mkey | `7362db7` |
| 0003 | DMA allocation and HWS resources in shared memory | `79cab7b` |
| 0004 | HWS DevX CQ, testpmd external buffers, initial PMD guards | `acaa959` |
| 0005 | Explicit diagnostics for unsupported configurations | `fc1a57c` |
| 0006 | Consolidated conservative mode, RX/TX tests, fail-stop handling, fd ownership, fail-closed allocation, UMEM alignment | Exact delta `fc1a57c..8a3a43b` |
| 0007 | Synchronous private-mbuf bridge | `466d145` |
| 0008 | Authenticated chunk receiver | `470dcb6` |
| 0009 | Private CQE snapshots, guarded error/opcode handling, nonempty RX completions | CVM-DPDK correctness fix, 2026-10-20 |
| 0010 | Private forwarding/GSO pools, strict buffer ownership, explicit unsupported-mode checks | CVM-DPDK coverage extension, 2026-10-20 |
| 0011 | Select EFD AVX2 lookup only when its implementation was compiled | Upstream audit follow-up, 2026-10-21 |
| 0012 | Reject missing security session-size callbacks; repair IPsec test fixture and add a rejection regression | Upstream audit follow-up, 2026-10-21 |
| 0013 | Correct BPF no-huge/ASan metadata and report a disabled crypto scheduler explicitly | Upstream test setup fixes, 2026-10-21 |
| 0014 | Create valid IPsec benchmark sessions, check preparation failures and release session/SA resources | Extended upstream tests, 2026-10-22 |
| 0015 | Select the non-NUMA forwarding pool before resolving its private peer | Testpmd CLI regression, 2026-10-22 |

Patch 0006 folds intermediate experiments and reversions into the tested final
state. It was recovered on 2026-10-20 by reading the powered-off CVM disk and
exporting its original Git objects. The VM and disk were not modified.

The private-mbuf bridge and authenticated receiver were previously stored as
`dpdk-patches/0006-…` and `dpdk-patches/0007-…`. They are renumbered 0007 and
0008 here because the missing conservative-baseline delta is now explicit.
Their implementation is unchanged.

| Checkpoint | Git tree hash |
|---|---|
| Official release, fully imported | `893022eb662f7517dc58f3f8bd0e4b7c417138cd` |
| Official release, through 0010 | `488ff6198a811383b3d8bb71b23b09dcbe8e1d36` |
| Official release, through 0011 | `874701773735b7b90214eab6841896eedc312947` |
| Official release, through 0012 | `138e9168feac7091f8ea8f90da95554b7480113c` |
| Official release, through 0013 | `54139e1ff627b06e438ea14ca0a8750168314735` |
| Official release, through 0014 | `b2860235e5abd41775032e82876ec21c477b9c7c` |
| Official release, through 0015 | `7f67782d633d0cfae4b5416078b84b7e483a9b92` |
| Archived CVM import | `d09d6d6f46cef3d6234ba7f11ee7e187e0ca4e02` |
| Conservative baseline, through 0006 | `6dc438c1e5f09ee298ef7d84f1f490e19f96b352` |
| Private bridge, through 0007 | `2b6019b4092fc728203063b0a05fa3ae899d0838` |
| Authenticated receiver, through 0008 | `0284ee73f1416fe6b1ce9c9d24070eb82b776bfd` |
| CQE snapshots and private forwarding, through 0010 | `bc671f0bfef8c50f2934d3002b76afe68397ccf4` |
| EFD generic-build dispatch fix, through 0011 | `1dbb76f412f4cf159acc86951a970515daf2bc16` |
| Security session-size validation, through 0012 | `a99e55096ffddbfce7687e6c7a2355e4f990770a` |
| Test registration metadata, through 0013 | `92d30365612504a53394ac6d3de15c854c7b8d09` |
| IPsec performance sessions, through 0014 | `02c3374df711bf75e3eb456a613b41afbd11d764` |
| Non-NUMA forwarding pool, through 0015 | `b0f716046d79ea645de74af7f966c52b4170dd75` |

The tree through 0008 corresponds to the archived receiver implementation.
Patches 0009 and 0010 extend that implementation; the earlier patches remain
unchanged. Subsequent
sender changes (one-second RTO and streaming source hash) live in
`scratch/cvm-chunk-proto/cvm_chunk_send.c`; they do not change the DPDK tree.

The new regressions compile the actual PMD RX/TX source with deterministic
mutation at the validation boundary, and link the actual testpmd engines to
ring-backed Ethernet ports. Run them against a built tree with
`python3 scripts/test-dpdk-integration.py /path/to/dpdk/build` from the CVM-DPDK
root. See [the test guide](../tests/dpdk/README.md) for coverage and limitations.

Historical generators and early source snapshots are retained in
[`../dpdk-patches/archive/`](../dpdk-patches/archive/README.md). Do not run them
over a patched tree.
