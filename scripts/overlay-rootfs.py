"""Overlay extra files onto the slim Debian rootfs tarball.

The rootfs shipped inside the boot image is a pruned Debian 13 tarball. Rather
than un-tarring 184 MB on the host and re-tarring it, this stream-copies every
unchanged member and swaps in the overlay's versions, so only the touched
entries are rewritten.

Overlay files are written with deterministic ownership (root/root) and modes
derived from their path, since Windows cannot carry POSIX modes.

Usage: overlay-rootfs.py <base.tar.xz> <overlay-dir> <out.tar.xz>
"""

import os
import stat
import sys
import tarfile
import time

base_path, ov_dir, out_path = sys.argv[1], sys.argv[2], sys.argv[3]

# Directories/files that must not be world-writable or world-readable.
TIGHT_600 = ("root/.ssh/authorized_keys",)
TIGHT_700 = ("root/.ssh",)


def want_mode(rel):
    if rel in TIGHT_600:
        return 0o600
    if rel in TIGHT_700:
        return 0o700
    p = os.path.join(ov_dir, rel)
    if os.path.isdir(p):
        return 0o755
    if rel.startswith("usr/sbin/") or rel.startswith("usr/bin/") or \
            rel.startswith("usr/lib/openssh/") or rel.startswith("etc/init.d/"):
        return 0o755
    # Debian marks some shared objects executable; keep them 0644 unless ELF exec
    return 0o644


overlay = {}
for root, dirs, files in os.walk(ov_dir):
    for d in dirs:
        full = os.path.join(root, d)
        rel = os.path.relpath(full, ov_dir).replace("\\", "/")
        overlay[rel] = ("dir", full)
    for f in files:
        full = os.path.join(root, f)
        rel = os.path.relpath(full, ov_dir).replace("\\", "/")
        overlay[rel] = ("file", full)

print(f"overlay entries: {len(overlay)}", flush=True)

t0 = time.time()
added = 0
kept = 0
skipped = 0

src = tarfile.open(base_path, "r:xz")
dst = tarfile.open(out_path, "w:xz", preset=6)

for m in src:
    name = m.name.lstrip("./")
    if name in overlay:
        skipped += 1
        continue
    dst.addfile(m, src.extractfile(m) if m.isfile() else None)
    kept += 1
    if kept % 1000 == 0:
        print(f"  kept {kept} skipped {skipped}", flush=True)

base_names = set()
src.close()

for rel, (kind, full) in sorted(overlay.items()):
    ti = tarfile.TarInfo(rel)
    ti.uid = 0
    ti.gid = 0
    ti.uname = "root"
    ti.gname = "root"
    ti.mtime = int(time.time())
    if kind == "dir":
        ti.type = tarfile.DIRTYPE
        ti.mode = want_mode(rel)
        dst.addfile(ti)
    else:
        st = os.stat(full)
        ti.type = tarfile.REGTYPE
        ti.size = st.st_size
        ti.mode = want_mode(rel)
        with open(full, "rb") as fh:
            dst.addfile(ti, fh)
    added += 1

dst.close()
print(f"done: kept={kept} replaced={skipped} added={added} "
      f"out={out_path} size={os.path.getsize(out_path)} "
      f"elapsed={time.time() - t0:.1f}s", flush=True)
