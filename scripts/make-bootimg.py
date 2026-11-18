#!/usr/bin/env python3
"""Build a minimal Android boot image (header v0) for the Le Max 2.

The stock bootloader requires an ANDROID! header; a bare Image.gz + DTB
concatenation is not loadable. The offset values below were read back from the
device's own boot partition:

    kernel_addr  = 0x80008000
    ramdisk_addr = 0x84000000
    tags_addr    = 0x80000100
    page_size    = 4096

Usage:
    make-bootimg.py [--ramdisk <initramfs>] [--cmdline "<extra params>"] \
        <kernel> <dtb> <out.img>

Examples:
    make-bootimg.py out/Image.gz out/msm8996-leeco-x2.dtb out/boot.img
    make-bootimg.py out/Image.gz out/msm8996-leeco-x2.dtb out/boot-debian.img \
        --ramdisk out/initramfs-debian-disk.gz --cmdline "console=tty0"
"""

import struct
import sys

PAGE = 4096
KERNEL_ADDR = 0x80008000
# The 6.19 arm64 Image decompresses to about 40 MB and is staged at
# kernel_addr, so it extends to roughly 0x826A0000. The vendor value
# 0x81000000 sits inside that range and would clobber the kernel. Keep the
# ramdisk after the kernel and tags instead.
RAMDISK_ADDR = 0x84000000
TAGS_ADDR = 0x80000100
BOARD = b""

# earlycon uses the DTB stdout path; panic=15 auto-reboots a crashed kernel.
# Extra params such as console=tty0 are appended by --cmdline.
CMDLINE = b"earlycon panic=15"


def pad(data: bytes) -> bytes:
    rem = len(data) % PAGE
    return data + b"\0" * (PAGE - rem if rem else 0)


def main(kernel_path: str, dtb_path: str, out_path: str,
         kernel_addr: int = KERNEL_ADDR, ramdisk_path: str | None = None,
         extra_cmdline: bytes = b"") -> int:
    with open(kernel_path, "rb") as f:
        kernel = f.read()
    with open(dtb_path, "rb") as f:
        dtb = f.read()

    cmdline = CMDLINE + (b" " + extra_cmdline if extra_cmdline else b"")

    # The stock bootloader ignores header dt_size and rejects images with
    # "dtb not found" unless the DTB is appended inside the kernel segment.
    # Mirror the stock boot.img layout: dt_size=0 and DTB concatenated after
    # the gzipped kernel.
    kernel_blob = kernel + dtb

    ramdisk = b"" if ramdisk_path is None else open(ramdisk_path, "rb").read()

    header = struct.pack(
        "<8s10I16s512s32s1024s",
        b"ANDROID!",
        len(kernel_blob),       # kernel_size covers kernel + appended dtb
        kernel_addr,
        len(ramdisk),
        RAMDISK_ADDR,
        0,                      # no second stage
        0,
        TAGS_ADDR,
        PAGE,
        0,                      # dt_size = 0; DTB lives inside kernel blob
        0,                      # unused
        BOARD,
        cmdline,
        b"",                    # id
        b"",                    # extra cmdline
    )

    with open(out_path, "wb") as f:
        f.write(pad(header))
        f.write(pad(kernel_blob))
        if ramdisk:
            f.write(pad(ramdisk))

    print(f"kernel      : {len(kernel)} bytes")
    print(f"dtb         : {len(dtb)} bytes")
    print(f"kernel blob : {len(kernel_blob)} bytes")
    print(f"ramdisk     : {len(ramdisk)} bytes")
    print(f"kernel addr : {kernel_addr:#x}")
    print(f"image       : {out_path}")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    kernel_addr = KERNEL_ADDR
    ramdisk_path = None
    extra_cmdline = b""
    if "--ramdisk" in args:
        i = args.index("--ramdisk")
        ramdisk_path = args[i + 1]
        del args[i:i + 2]
    if "--cmdline" in args:
        i = args.index("--cmdline")
        extra_cmdline = args[i + 1].encode()
        del args[i:i + 2]
    if "--addr" in args:
        i = args.index("--addr")
        kernel_addr = int(args[i + 1], 0)
        del args[i:i + 2]
    if len(args) == 3:
        sys.exit(main(args[0], args[1], args[2], kernel_addr, ramdisk_path,
                      extra_cmdline))
    print(__doc__)
    sys.exit(2)
