#!/usr/bin/env python3
"""Inject the Le Max 2 bits into a fresh pmaports checkout.

Used by nura-image.yml inside the build container before
`pmbootstrap install` runs:

  1. device package   -> device/testing/device-leeco-x2
  2. firmware package -> device/testing/firmware-leeco-x2
  3. kernel patches   -> device/community/linux-postmarketos-qcom-msm8996
     the patch files are appended to the APKBUILD source= list and their
     sha512 sums are added to sha512sums, so abuild's default_prepare()
     applies them to the msm8996-mainline kernel tarball.

Usage: pmaports-inject.py <pmaports-dir> <kernel-patches-dir> <device-dir> <firmware-dir>
"""

import hashlib
import pathlib
import shutil
import sys


def main() -> int:
    pmaports = pathlib.Path(sys.argv[1])
    patch_dir = pathlib.Path(sys.argv[2])
    device_dir = pathlib.Path(sys.argv[3])
    fw_dir = pathlib.Path(sys.argv[4])

    # 1. + 2. device and firmware packages
    shutil.copytree(device_dir, pmaports / "device/testing/device-leeco-x2",
                    dirs_exist_ok=True)
    shutil.copytree(fw_dir, pmaports / "device/testing/firmware-leeco-x2",
                    dirs_exist_ok=True)
    print("injected: device/testing/device-leeco-x2")
    print("injected: device/testing/firmware-leeco-x2")

    # 3. kernel package patches
    kp = pmaports / "device/community/linux-postmarketos-qcom-msm8996"
    patches = sorted(patch_dir.glob("*.patch"))
    if not patches:
        print("ERROR: no kernel patches found in", patch_dir)
        return 1
    for p in patches:
        shutil.copy2(p, kp / p.name)

    ap_path = kp / "APKBUILD"
    ap = ap_path.read_text()
    if "0001-arm64-dts" not in ap:
        src_old = '\tconfig-$_flavor.$arch\n"'
        if src_old not in ap:
            print("ERROR: APKBUILD source anchor not found "
                  "(pmaports layout changed?)")
            return 1
        src_new = ('\tconfig-$_flavor.$arch\n'
                   + "".join("\t%s\n" % p.name for p in patches) + '"')
        ap = ap.replace(src_old, src_new)

        sums = "".join(
            "%s  %s\n" % (hashlib.sha512((kp / p.name).read_bytes()).hexdigest(),
                          p.name)
            for p in patches)
        # append to the sha512sums block (it is the last quoted block);
        # sums without a trailing newline so no blank line precedes the
        # closing quote (abuild counts lines in the checksum variable)
        idx = ap.rfind('\n"')
        ap = ap[:idx] + "\n" + sums.rstrip("\n") + ap[idx:]
        ap_path.write_text(ap)
        print("patched APKBUILD: +source, +sha512sums")
    else:
        print("APKBUILD already patched, skipping")

    for line in ap_path.read_text().splitlines():
        if "patch" in line or line.startswith("sha512") or line.startswith('"'):
            print("  |", line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
