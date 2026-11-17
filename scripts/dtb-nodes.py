"""List node paths from a flattened device tree blob.

Answers "what does the mainline DTS actually describe" without needing dtc on
this machine: walk the FDT structure block and print every node path, so we can
tell which peripherals are wired up and which are simply absent.

Usage: dtb-nodes.py <file.dtb> [filter]
"""

import struct
import sys

path = sys.argv[1]
needle = sys.argv[2].lower() if len(sys.argv) > 2 else None

data = open(path, "rb").read()
magic, totalsize, off_struct, off_strings = struct.unpack(">IIII", data[:16])
if magic != 0xD00DFEED:
    raise SystemExit(f"not a dtb (magic={magic:#x})")

pos = off_struct
stack = []
paths = []
while pos < totalsize:
    token, = struct.unpack(">I", data[pos:pos + 4])
    pos += 4
    if token == 1:  # FDT_BEGIN_NODE
        end = data.index(b"\x00", pos)
        name = data[pos:end].decode("ascii", "replace")
        pos = end + 1
        stack.append(name)
        p = "/".join(x for x in stack if x)
        paths.append(p)
    elif token == 2:  # FDT_END_NODE
        if stack:
            stack.pop()
    elif token == 3:  # FDT_PROP
        ln, nameoff = struct.unpack(">II", data[pos:pos + 8])
        pos += 8 + ln
    elif token == 4:  # FDT_NOP
        continue
    elif token == 9:  # FDT_END
        break
    else:
        raise SystemExit(f"bad token {token} at {pos - 4}")

for p in paths:
    if needle is None or needle in p.lower():
        print(p)
print(f"# total nodes: {len(paths)}", file=sys.stderr)
