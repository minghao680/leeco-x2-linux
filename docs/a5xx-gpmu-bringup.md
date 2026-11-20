# A530 GPMU / RBCCU bring-up

## Why `a5xx_me_init` fails

Mainline `a5xx_me_init()` waits for a full RBBM idle after `CP_ME_INIT`:

- `_a5xx_check_idle()` requires every `RBBM_STATUS` bit except `HI_BUSY` to be clear.
- On this A530, after `CP_ME_INIT` the CP ring drains (`rptr/wptr = 9/9`) but
  `RBBM_STATUS = c0000101` (and later `e0c80101`) keeps HLSQ/VFD/VFDP/PC_DCALL
  busy.
- Vendor KGSL does not perform this full RBBM idle at ME_INIT; it only waits
  for the CP ring read pointer.
- The RBCCU/SP GDSC domains are owned by the GPMU firmware and are still off
  during the first hw_init, so those graphics-pipeline busy bits are expected
  to remain asserted until the GPMU has booted.

## Vendor sequence

Vendor `a5xx_rb_start()`:

1. Program CP ring.
2. Load PM4/PFP microcode.
3. `CP_ME_CNTL = 0`.
4. Send `CP_ME_INIT` and wait for the ring to drain (not full RBBM idle).
5. Switch out of secure mode.
6. `a5xx_lm_init()`.
7. `a5xx_enable_pc()`.
8. `a5xx_gpmu_start()` — load GPMU firmware, release `GPMU_CM3_SYSRESET`,
   wait up to ~100 us for `GPMU_GENERAL_0 == 0xBABEFACE`.
9. `a5xx_lm_enable()`.
10. `a5xx_post_start()`.

The RBCCU/SP GDSC enable sequence belongs after the GPMU is running. Mainline
`a5xx_pm_resume()` postpones it on the first pass (patch 0020), but nothing
re-enabled it after a successful GPMU start.

## Patch 0030

`0030-a5xx-gpmu-before-rbccu.patch`:

- Adds `a5xx_gpu->gpmu_ready`.
- Until the GPMU has answered `0xBABEFACE`, `a5xx_idle()` still waits for the
  CP ring to drain but skips the full RBBM_STATUS check.
- Raises the GPMU startup wait from 25 us to 100 us.
- On GPMU success, enables the RBCCU then SP GDSC domains, with the same
  register values and polling used by `a5xx_pm_resume()`.
- Logs `GPMU_GENERAL_0`, GDSC status and `RBBM_STATUS` around the sequence.

`0029-a5xx-ignore-ahb-busy.patch` is disabled: ignoring only the AHB bits still
left HLSQ/VFD/VFDP/PC_DCALL asserted and produced 2603 log lines without fixing
the init.

## Test image

- `out/boot-x2-debian-systemd20-gpmu.img`
- size: 56,483,840 bytes
- SHA256: `ee5b56e2328b83ee46ad275a7e184d1898cc6f3106874511d356990c33f3c51d`
- kernel: `out/local-build/Image.gz` (11,698,400 bytes, built 2026-11-20 11:29)
- DTB: `out/local-build/msm8996-leeco-x2.dtb`
- initramfs: `out/local-build/x2-initramfs-systemd18.gz`
- cmdline keeps the ADSP blacklist:
  `module_blacklist=rmtfs_mem,qcom_q6v5_pas,qcom_q6v5_adsp`

The image has been written to `/dev/disk/by-partlabel/boot` (`/dev/sde18`) on
the device and the first 56,483,840 bytes were verified to match the SHA256.
It has **not** been runtime-tested yet: the automatic reboot was blocked by the
execution safety layer. A manual reboot is required.

## What to look for after reboot

```sh
dmesg | grep -E 'gpmu_init ret|gpmu domains ret|skipping RBBM idle|me_init ret|gpu hw init'
```

Expected success path:

```text
gpmu_init ret=0 ready=1 GENERAL_0=babeface
gpmu domains ret=0 ...
me_init ret=0
```

If `GENERAL_0` is not `babeface`, the GPMU firmware did not start; the next
step is to inspect `GPMU_CM3_SYSRESET`, GPMU firmware load and the GPMU clock /
reset controls rather than the RBCCU GDSC.

If GPMU starts and GDSC enables but `RBBM_STATUS` still shows HLSQ/VFD busy,
the remaining issue is in the graphics pipeline reset/clock state, not the CP
ring.

## 2026-11-20 runtime result (0030)

`fastboot boot` of `boot-x2-debian-systemd20-gpmu.img` worked as a temporary
boot (no partition write):

- `me_init ret=0`, ring `rptr/wptr=9/9`: the strict RBBM idle check is no
longer blocking ME_INIT.
- `GPMU_GENERAL_0=00000000`, `gpmu_ready=0`: the GPMU firmware still did not
  start.
- CP fault immediately after the GPMU IB:
  `gpu fault ... ib1 0000000001023000/0000`, i.e. the GPMU indirect buffer was
  rejected with size 0.
- Mesa/freedreno still exposed the GPU as `FD530` (OpenGL ES 3.1), so basic
  command submission is partially alive.
- `kmscube -c 60` triggered a GPU hang, the hangcheck recovery re-ran
  `a5xx_hw_init`, hit the same GPMU IB fault, and the device reset to Android.

This points to the secure-mode ordering: vendor KGSL switches the CP out of
secure mode **before** loading the GPMU, while mainline was doing it after
`a5xx_power_init()`.

## Patch 0031

`0031-a5xx-unsecure-before-gpmu.patch`:

- Moves `a5xx_zap_shader_init()` and the `CP_SET_SECURE_MODE` / 
  `RBBM_SECVID_TRUST_CNTL` fallback ahead of `a5xx_power_init()`.
- Logs the zap result and `RBBM_SECVID_TRUST_CNTL`.
- Leaves the GPMU IB, `GPMU_GENERAL_0` wait and RBCCU/SP GDSC enable in the
  same order as 0030.

Test image:

- `out/boot-x2-debian-systemd21-unsecure.img`
- size: 56,483,840 bytes
- SHA256: `27f180fdbb30eff84c086a453a66d4fd00b9d9020f3f3475ff452b42b13eab49`

Test it only with:

```sh
fastboot boot out/boot-x2-debian-systemd21-unsecure.img
```

Do **not** `fastboot flash boot`: the temporary boot keeps the Android boot
partition untouched.

## 0041/0042 runtime suspend/resume result

`0041-a530-allow-runtime-pm-after-gpmu.patch` lets A530 use runtime PM only
after the GPMU answers `0xBABEFACE`. The first `hw_init` on this board can
still time out, so `pm_runtime_forbid` remains active until a later
`hw_init` succeeds. On success, `pm_runtime_allow` is called and
`a5xx_pm_suspend()` clears `gpmu_ready` after the core is off; the next
`pm_resume` therefore returns early and `hw_init` reloads the GPMU.

`0042-a530-runtime-pm-trace.patch` adds stage logs for suspend/resume and
`hw_init`.

Hardware result (trace image, KDE loaded, no `x2-gpu-keepalive`):

- GPMU ready at about 25.9 s after a first timeout.
- Runtime suspend at 63.45 s: `pm_suspend core suspended`.
- Runtime resume at 122.0 s: `pm_resume deferred to hw_init (GPMU lost)`,
  then `hw_init power done gpmu_ready=1`, `hw_init done gpmu_ready=1`.
- Multiple suspend/resume cycles completed without SSH loss or reboot.
- `/sys/bus/platform/devices/b00000.gpu/power/control` is `auto`.

