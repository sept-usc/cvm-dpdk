# ARMv8 crypto under user emulation — 2026-10-22

`cryptodev_sw_armv8_autotest` now has a functional pass under ARM64 instruction
emulation on the x86 host. The original command returns zero: 19 subcases pass,
906 unsupported subcases are skipped, and none fail. This is a separate
environment from the native x86 profiles, not ARM hardware or performance
qualification.

The passing subcases include AES-128-CBC with HMAC-SHA1/HMAC-SHA256 encryption
and decryption, short buffers, sessionless SHA1 operation, ESN handling,
rejection of corrupted data/tags, and device/queue configuration and statistics.
The unsupported algorithms in the generic crypto suite remain visible as skips.
No DPDK test assertion, algorithm implementation or expected result was changed.

## Build and run

The local run used GCC 15.2.0 for AArch64, QEMU user mode 10.1.0 with `-cpu max`,
and Arm's AArch64cryptolib commit
`9267aa1d46ae5ca68ff252d96733adb03b78794e` (pkg-config version 23.03), built with
`OPT=big`. DPDK was cross-compiled from the current fifteen-patch tree with
`max_numa_nodes=1`. Only bus drivers, the ring mempool and ARMv8 crypto PMD were
enabled. The executable uses two selected host CPUs, 2 GiB ordinary memory,
no PCI probing and an explicit ARM64 runtime sysroot.

On a Debian/Ubuntu system with `gcc-aarch64-linux-gnu`,
`binutils-aarch64-linux-gnu`, `libc6-dev-arm64-cross`, `qemu-user`, Meson,
Ninja, pkg-config, make and pyelftools available, use a fresh crypto checkout:

```sh
git clone https://github.com/ARM-software/AArch64cryptolib.git /tmp/arm-crypto
git -C /tmp/arm-crypto checkout 9267aa1d46ae5ca68ff252d96733adb03b78794e
make -C /tmp/arm-crypto -j 2 CROSS=aarch64-linux-gnu- OPT=big \
  libAArch64crypto.a libAArch64crypto.pc
export PKG_CONFIG_LIBDIR=/tmp/arm-crypto/pkgconfig
meson setup /path/to/arm-build /path/to/patched-dpdk \
  --cross-file tests/dpdk/arm64-cross.ini \
  -Dtests=true -Ddefault_library=static -Dplatform=generic -Dmax_numa_nodes=1 \
  '-Denable_drivers=bus/*,mempool/ring,crypto/armv8' -Denable_apps=test
ninja -C /path/to/arm-build
python3 scripts/test-dpdk-arm64.py /path/to/arm-build
```

The runner accepts `--qemu`, `--sysroot`, `--cpus` and `--output` for an isolated
toolchain or selected host CPUs. It requires at least one executed pass and no
failed subcases in addition to exit status zero; a top-level skip, crash or
timeout fails. Output must use a fresh directory to preserve earlier evidence.
The separate `DPDK ARM64 emulation` workflow pins the same crypto dependency,
verifies the DPDK release archive and applies the complete patch series.

The local compiler, runtime and emulator packages were unpacked under `/tmp`;
no system packages or binfmt handlers were installed. Both the initial direct
invocation and the maintained runner returned zero with the same 19/906/0
pass/skip/fail counts. The [machine-readable record](results/2026-10-22-arm64-emulation.json)
contains the maintained command, tool and binary hashes, source revision,
subcase names and build configuration. Raw logs and build products remain in
`/tmp/cvm-dpdk-followup-20261022`.
