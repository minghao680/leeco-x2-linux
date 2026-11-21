#!/usr/bin/env python3
"""Write a deterministic SHA-256 manifest for a firmware staging tree."""

from __future__ import annotations

import hashlib
import os
import sys


def sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} STAGE_DIR MANIFEST", file=sys.stderr)
        return 2
    stage, manifest = sys.argv[1:]
    rows = []
    for root, _dirs, files in os.walk(stage):
        for name in sorted(files):
            path = os.path.join(root, name)
            rel = os.path.relpath(path, stage).replace(os.sep, "/")
            rows.append(f"{sha256(path)}\t{os.path.getsize(path)}\t{rel}")
    rows.sort(key=lambda line: line.split("\t")[-1])
    with open(manifest, "w", encoding="utf-8", newline="\n") as stream:
        stream.write("sha256\tbytes\tpath\n")
        stream.write("\n".join(rows))
        stream.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
