"""Report which DT nodes are enabled vs disabled.

dtc's text output is a brace-nested tree, so a small stack walk is enough to
attribute each `status = "disabled"` back to the node it belongs to. Nodes with
no explicit status are enabled by default.

Usage: dt-status.py <x2.dts>
"""

import re
import sys

node_re = re.compile(r"^([A-Za-z0-9_,.@+\-]+)\s*\{$")
status_re = re.compile(r'status\s*=\s*"(\w+)"')

stack = []
rows = []
pending = {}

for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
    raw = line.rstrip("\n")
    if not raw.strip().startswith("/*") and "//" not in raw[:2]:
        pass

    m = node_re.match(raw.strip())
    if m:
        stack.append(m.group(1))
        continue
    if raw.strip() == "};":
        if stack:
            # closing a node: flush any status recorded for it
            path = "/".join(stack)
            rows.append((path, pending.pop(path, "okay")))
            stack.pop()
        continue
    sm = status_re.search(raw)
    if sm and stack:
        pending["/".join(stack)] = sm.group(1)

disabled = [p for p, s in rows if s != "okay"]
print(f"# nodes: {len(rows)}  disabled: {len(disabled)}")
for p in sorted(disabled):
    print("disabled:", p)
