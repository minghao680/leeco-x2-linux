#!/usr/bin/env python3
"""Slim the LXC Debian 13 arm64 rootfs down to fit an x2 boot.img.

The stock Le Max 2 bootloader validates the boot image against the 64 MiB `boot`
partition even for `fastboot boot`, and rejects anything larger with the very
unhelpful "Too many links".  With an 11.8 MB kernel that leaves roughly 50 MB
for the whole initramfs, i.e. the embedded rootfs tarball must shrink from
90 MB to under ~48 MB.

We keep bash, coreutils, systemd, apt/dpkg, the shared libraries and the
network/terminal bits, and drop the space hogs that are useless on a serial
console:
    var/lib/apt/lists   ~91 MB   package indexes, regenerable with apt update
    usr/share/locale    ~55 MB   translations
    usr/share/vim       ~38 MB   editor runtime files
    usr/share/i18n      ~15 MB   locale source data
    usr/share/doc       ~14 MB   documentation
    usr/share/man        ~6 MB   man pages
    usr/share/mime       ~5 MB   MIME database
    usr/lib/udev/hwdb   ~20 MB   device hwdb (keep the udev binaries)

Entries are written back verbatim (mode/uid/gid/symlink targets untouched) so
the result stays a valid rootfs.

Usage: slim-rootfs.py <in.tar.xz> <out.tar.xz>
"""

import tarfile
import sys

DROP_PREFIXES = [
    "./var/lib/apt/lists",
    "./usr/share/locale",
    "./usr/share/vim",
    "./usr/share/i18n",
    "./usr/share/doc",
    "./usr/share/man",
    "./usr/share/mime",
    "./usr/lib/udev/hwdb.d",
    "./usr/share/bash-completion",
]


def dropped(name):
    # Normalise "./usr/share/locale/fr" -> "usr/share/locale/fr"
    norm = name[2:] if name.startswith("./") else name.lstrip("/")
    for p in DROP_PREFIXES:
        pn = p[2:]
        if norm == pn or norm.startswith(pn + "/"):
            return True
    return False


def main(src, dst):
    kept = 0
    kept_bytes = 0
    dropped_n = 0
    with tarfile.open(src, "r:xz") as tin, tarfile.open(dst, "w:xz", preset=6) as tout:
        for m in tin:
            if dropped(m.name):
                dropped_n += 1
                continue
            data = tin.extractfile(m) if m.isreg() else None
            tout.addfile(m, data)
            kept += 1
            if m.isreg():
                kept_bytes += m.size
    print(f"kept {kept} entries ({kept_bytes / 1048576:.1f} MB), dropped {dropped_n}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
