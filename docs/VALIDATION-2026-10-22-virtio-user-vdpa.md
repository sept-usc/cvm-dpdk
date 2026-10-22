# Virtio-user crypto over vDPA — 2026-10-22

The original virtio-user symmetric and asymmetric commands run in disposable
QEMU guests through Linux `vp_vdpa` and `vhost_vdpa`. This extends the PCI virtio
profile with a real kernel vDPA transport; no physical crypto accelerator or
host device binding is required. Results and controls are retained in the
[machine-readable record](results/2026-10-22-virtio-user-vdpa.json).

The original symmetric command passes 25 subcases with 900 unsupported skips;
the original RSA command passes all three subcases. Seven maintained cases
passed in the full local invocation. The RSA guard initially selected an
unsupported exponent key format; after correcting the fixture to the advertised
CRT format, that case passed separately. The record retains both outcomes.

## Failures and fixes

The first guest successfully exposed `/dev/vhost-vdpa-0`, but its default 8 MiB
memlock limit prevented mapping the test's 1 GiB EAL allocation. The driver
logged the mapping failure, then incorrectly returned success from
`rte_cryptodev_start()`. A subsequent control request waited indefinitely.
Patch 0018 checks that the device actually entered `DRIVER_OK` without a failed
or reset-required status. The dedicated public-API regression lowers memlock
to zero: unmodified DPDK returns success and fails the regression; the fixed
build returns `-EIO`. Restoring the limit permits a retry and a real AES-CBC
session through the same device. The functional guest explicitly raises its
memlock limit; the test workload is unchanged.

Two further transport bugs prevented execution after memory mapping succeeded:

- Patch 0019 expresses the split used ring address as an IOVA plus its offset
  within the ring allocation. Previously it passed a process virtual address,
  producing an emulated IOMMU translation fault with IOVA=PA.
- Patch 0020 includes the control queue in notification setup and teardown.
  Previously its eventfds remained `-1`, so session requests could not notify
  the backend. Queue setup now includes that queue exactly once.

The guest device also needs three MSI-X vectors: one for the data queue, one
for the control queue, and one for configuration. The two-vector control
produced a kernel IRQ allocation failure and is retained as a fixture failure.

Patch 0022 permits reset when a vDPA backend returns `EOPNOTSUPP` for live queue
indices. This path discards queue state and resets the device; it does not
implement migration or resume from a saved queue index. The original suite's
repeated stop/configure/start cycle exercises it.

Patch 0023 stages RSA data for split rings in the existing DMA-visible cookie.
The original RSA fixture supplies ordinary process/stack buffers; directly
translating those addresses did not map them into vDPA and caused an IOMMU
fault. The split path now copies both verification inputs, checks lengths and
NULL buffers before acquiring a cookie, and copies outputs back only on
successful completion. Its buffers cover the advertised 1,024-byte RSA
modulus limit. The RSA guard test rejects 256 invalid submissions, then signs
and verifies through the same queue while checking surrounding canaries.
The original RSA vectors and assertions remain unchanged.

## IOMMU-aware backend and QEMU companion

Patch 0021 preserves explicitly enabled IOMMU support when starting the crypto
vhost driver. The example exposes `--iommu-support` in copy mode, initializes
the normal vhost IOTLB machinery, and rejects the incompatible zero-copy
combination. The library also rejects zero-copy enablement on an IOMMU socket;
its zero-copy path assumes guest physical addresses.

QEMU 10.1.0's crypto vhost code left `acked_features` zero. Even with the DPDK
backend configured for IOMMU, the backend negotiated only `0x40000000` and the
first data request stalled. A separate [QEMU companion patch](../tests/qemu/README.md)
forwards the intersection of guest-negotiated and backend-supported features.
The successful backend profile negotiates `0x340000000`, including
`VIRTIO_F_IOMMU_PLATFORM`. The runner checks this bit in every recorded
negotiation as well as checking guest exit statuses and actual subcase passes.
A same-build negative control, with only that QEMU change reverted, again
negotiated `0x40000000` and did not complete its first data request before the
60-second negative-control ceiling. Restoring the patch reproduced the exact
previous patched QEMU binary hash. This QEMU change is explicitly separate
from the 23-patch DPDK series.

## Reproduction and scope

Build DPDK as described in the [PCI virtio report](VALIDATION-2026-10-22-virtio-crypto.md),
using the complete current patch series. Build the pinned QEMU archive with its
companion patch using the commands in `.github/workflows/dpdk-virtio.yml`. Then:

```sh
python3 scripts/test-dpdk-virtio.py /path/to/dpdk-build \
  --kernel /path/to/matching/vmlinuz \
  --modules /path/to/kernel/drivers/uio \
  --vdpa-modules /path/to/kernel/module/tree \
  --qemu /path/to/patched/qemu-system-x86_64
```

The module tree must contain matching `vdpa`, `vp_vdpa`, `vhost`, `vhost_iotlb`,
`vhost_vdpa` and `irqbypass` modules. `vdpa` from iproute2 is copied with its
runtime libraries into the guest. The vDPA guests use Q35, an emulated Intel
IOMMU, two vCPUs, 3 GiB RAM, 1,024 reserved 2 MiB hugepages, and IOVA=PA.
They bind only the emulated guest PCI device to `vp-vdpa`; the host backend
runs with PCI disabled. Both original PCI commands, both original virtio-user
commands, and four actual driver error-path checks are covered by one runner.

The runner stops an experiment if its backend exits or either diagnostic log
exceeds 64 MiB, and never counts that interruption as a pass. Earlier
failed/interrupted configuration attempts remain in the evidence
record and are not counted as passes. QEMU still emits `wrong value for
queue_enable 0` during queue teardown; the successful command outcomes do not
imply a warning-free emulator log. These are functional emulation results,
not hardware qualification, SNP validation, DMA isolation or throughput
measurements. Raw logs remain under `/tmp/cvm-dpdk-followup-20261022`.
