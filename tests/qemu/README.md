# QEMU companion patch for crypto vDPA testing

The virtio guest workflow builds the official QEMU 10.1.0 archive pinned by
`RELEASE_SHA256` and applies `0001-crypto-vhost-ack-features.patch`. This is a
separate test-environment change, not part of the DPDK patch series.

The crypto backend otherwise leaves `vhost_dev.acked_features` zero. A guest
using an emulated IOMMU then sends IOTLB traffic to a backend that has not
negotiated `VIRTIO_F_IOMMU_PLATFORM`. The patch forwards the intersection of
features negotiated by the guest and supported by the vhost backend before
starting its queues. The vDPA runner requires IOMMU negotiation in the backend
log as well as successful original test results.

The workflow builds only the x86 system emulator and uses TCG. Neither KVM nor
host PCI binding is needed. This fixture does not establish DMA isolation,
confidential-VM security or production throughput.
