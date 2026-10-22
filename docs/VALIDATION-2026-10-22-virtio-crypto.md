# Virtio crypto guests and error handling — 2026-10-22

Both original virtio-crypto commands pass in disposable x86 guests using DPDK's
OpenSSL vhost-crypto backend. The symmetric command passes 25 subcases with 900
unsupported subcases skipped; the asymmetric command passes all three subcases.
Guest execution uses QEMU TCG, not KVM or physical crypto hardware. Two additional
regressions verify failure handling in the actual virtio driver and control queue.

## Failed PCI probes must remove the cryptodev

The first guest still had its device bound to the kernel's `virtio-pci` driver.
Adding a UIO PCI ID did not transfer ownership from that driver. DPDK could not
map the device, but `crypto_virtio_create()` left its allocated cryptodev attached.
PCI probe cleanup cleared `device->driver`; both original crypto commands then
crashed when `rte_cryptodev_devices_get()` dereferenced `device->driver->name`.

This also reproduced with a newly built, unmodified official DPDK 25.11.3 source
tree. Both commands returned 139 in the guest. Patch 0016 destroys the allocated
cryptodev and releases PCI mappings when initialization fails. With the device
deliberately left under the kernel driver, both commands now return skip (77)
without a crash. This expected-skip regression is **not a functional pass**.

The functional fixture explicitly unbinds the emulated device from `virtio-pci`,
binds it to `uio_pci_generic`, and checks that the UIO device exists. All binding
operations occur inside the disposable guest; the host backend disables PCI
probing.

## Backend rejection must reach the application

QEMU's built-in crypto backend rejects the cipher/HMAC chaining request used by
several tests. The driver received the rejection, logged it, and jumped to its
error return, but `ret` still held zero from the successful transport exchange.
The public session-create API therefore returned a session that the backend had
never accepted.

Patch 0017 returns `-EIO` on a rejected symmetric session response. The dedicated
[regression](../tests/dpdk/test_virtio_session_error.c) fails against the
through-0016 binary because it receives a non-NULL session. With the fix, two
consecutive rejected requests return NULL with `rte_errno == EIO`, both session
pool objects remain available, and a supported AES-CBC-only session still
succeeds through the same queue and pool. No backend response is mocked.

## Functional backend selection

The QEMU built-in backend is useful for that rejection control, but it is not
the functional profile used here. Before these error-handling fixes, correctly bound control runs of its original
suites failed: 13/25 executed symmetric subcases pass and 12 fail; one of three
asymmetric subcases passes and two fail. Logs report unsupported chaining and
the requested RSA no-hash mode. These failed runs remain in the evidence record.

For full functional tests, the runner uses `dpdk-vhost_crypto` with
`--vdev=crypto_openssl0`. A symmetric backend serves the original symmetric
command; a separate `--asymmetric-crypto` backend serves the original RSA
command. Each run boots a fresh guest and uses a private Unix socket and shared
memfd RAM. The original workload, assertions, crypto transforms and vectors are
unchanged. Generic virtio-crypto does not make every backend support every mode.

## Reproduction and scope

Build the complete patch series with `-Dtests=true -Ddefault_library=static
-Dplatform=generic`, drivers `bus/*,mempool/ring,crypto/virtio,crypto/openssl`,
`-Denable_apps=test`, and `-Dexamples=vhost_crypto`. Then run:

```sh
python3 scripts/test-dpdk-virtio.py /path/to/dpdk-build \
  --kernel /path/to/readable/vmlinuz \
  --modules /path/to/matching/kernel/drivers/uio
```

Provide an x86 guest kernel with built-in `virtio-pci`, devtmpfs and hugepage
support, its matching UIO modules, QEMU, BusyBox and zstd. The runner needs four
allowed host CPUs and room for a 3 GiB guest plus a 1 GiB host backend and process
overhead. Each guest uses two vCPUs, 1 GiB EAL memory and 1,024 reserved 2 MiB
hugepages. No disk image, guest networking, host hugepage reservation or host
device binding is needed. `--backend-build` can select a separate backend build;
`--cpus` and `--output` select host affinity and a fresh evidence directory.

The maintained runner passed all four checks locally. It compiles the session
regression using the supplied build's compiler/linker commands, records guest
and backend logs and hashes, and checks actual guest command statuses rather
than treating QEMU shutdown as a test pass. The separate `DPDK virtio crypto
guests` workflow builds and runs the same profile with an unpacked guest kernel.

The [machine-readable evidence](results/2026-10-22-virtio-crypto.json) retains
the maintained run, pristine/patched probe controls, session rejection before
and after the fix, and the incompatible built-in-backend runs. The earlier
[initial probe record](results/2026-10-22-virtio-probe.json) remains unchanged.
Local runs used QEMU 10.1.0 and guest kernel 6.17.0-41-generic. These are functional
emulation results, not SNP, DMA isolation or throughput measurements. Raw data
remains under `/tmp/cvm-dpdk-followup-20261022`.
