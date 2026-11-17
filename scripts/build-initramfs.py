#!/usr/bin/env python3
"""Rebuild a newc cpio initramfs: replace `init` and add extra files.

patch-initramfs.py can only overwrite the existing `init` entry, so it cannot
carry the Debian rootfs.  This one parses the whole archive, swaps `init`, appends
new regular files (e.g. rootfs.tar.xz) just before the TRAILER, and re-gzips.

Usage:
    build-initramfs.py <base.cpio> <init> <out.cpio> <out.gz> [name=path ...]
"""

import gzip
import os
import sys


def parse_cpio(data):
    pos = 0
    entries = []
    while pos + 110 <= len(data):
        if data[pos:pos + 6] != b"070701":
            break
        f = [int(data[pos + 6 + i * 8:pos + 14 + i * 8], 16) for i in range(13)]
        filesize, namesize = f[6], f[11]
        name = data[pos + 110:pos + 110 + namesize - 1].decode("utf-8", "replace")
        dstart = (pos + 110 + namesize + 3) & ~3
        payload = data[dstart:dstart + filesize]
        entries.append(dict(ino=f[0], mode=f[1], uid=f[2], gid=f[3], nlink=f[4],
                            mtime=f[5], devmajor=f[7], devminor=f[8],
                            rdevmajor=f[9], rdevminor=f[10],
                            name=name, data=payload))
        pos = (dstart + filesize + 3) & ~3
        if name == "TRAILER!!!":
            break
    return entries


def write_cpio(entries, path):
    out = bytearray()
    for e in entries:
        namebytes = e["name"].encode() + b"\0"
        hdr = b"070701" + b"".join(f"{v:08x}".encode() for v in (
            e["ino"], e["mode"], e["uid"], e["gid"], e["nlink"], e["mtime"],
            len(e["data"]), e["devmajor"], e["devminor"], e["rdevmajor"],
            e["rdevminor"], len(namebytes), 0))
        out += hdr + namebytes
        out += b"\0" * ((4 - (110 + len(namebytes)) % 4) % 4)
        out += e["data"]
        out += b"\0" * ((4 - len(e["data"]) % 4) % 4)
    with open(path, "wb") as f:
        f.write(out)
    return len(out)


def main():
    args = sys.argv[1:]
    if len(args) < 4:
        print(__doc__)
        return 2
    base, init_path, out_cpio, out_gz = args[:4]
    extras = [a.split("=", 1) for a in args[4:]]

    entries = parse_cpio(open(base, "rb").read())

    new_init = open(init_path, "rb").read()
    for e in entries:
        if e["name"] == "init":
            e["data"] = new_init
            e["mtime"] = 0
            break
    else:
        raise SystemExit("init entry not found")

    # Drop the TRAILER, append the extras, then re-add a fresh TRAILER.
    if entries and entries[-1]["name"] == "TRAILER!!!":
        trailer = entries.pop()
    else:
        trailer = dict(ino=0, mode=0, uid=0, gid=0, nlink=1, mtime=0,
                       devmajor=0, devminor=0, rdevmajor=0, rdevminor=0,
                       name="TRAILER!!!", data=b"")

    for idx, (name, path) in enumerate(extras):
        blob = open(path, "rb").read()
        entries.append(dict(ino=0x1000 + idx, mode=0o100644, uid=0, gid=0, nlink=1, mtime=0,
                            devmajor=0, devminor=0, rdevmajor=0, rdevminor=0,
                            name=name, data=blob))
        print(f"  + {name} = {len(blob)} bytes")

    entries.append(trailer)

    cpio_len = write_cpio(entries, out_cpio)
    with gzip.GzipFile(filename="", mode="wb", fileobj=open(out_gz, "wb"), mtime=0) as gz:
        gz.write(open(out_cpio, "rb").read())
    print(f"entries={len(entries)} cpio={cpio_len} gz={os.path.getsize(out_gz)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
