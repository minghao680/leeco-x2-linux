"""Command runner for the x2 USB ACM console (Debian bash on ttyGS0).

Real-hardware quirks, all three of them painful:
  * a line pushed in one burst is dropped, so type it character by character;
  * the gadget does not flush its IN endpoint until the host sends more data,
    so after the command we send a bare CR to "nudge" the pending reply out;
  * every prompt is wrapped in ESC[?2004 bracketed-paste markers.

Usage: serial-run.py <COMx> "<command>" [idle_s]
"""

import re
import sys
import time

import serial

port = sys.argv[1]
cmd = sys.argv[2]
idle = float(sys.argv[3]) if len(sys.argv) > 3 else 3.0
char_delay = 0.04

p = serial.Serial(port, 115200, timeout=0.2)
p.dtr = True
p.rts = True
time.sleep(0.4)
p.reset_input_buffer()

for ch in cmd:
    p.write(ch.encode())
    time.sleep(char_delay)
p.write(b"\r")
time.sleep(0.8)

buf = bytearray()
# Nudge until the reply shows up: each bare CR flushes the pending IN data.
t0 = time.time()
nudges = 0
while time.time() - t0 < 60:
    d = p.read(4096)
    if d:
        buf += d
    else:
        if nudges < 6:
            p.write(b"\r")
            nudges += 1
            time.sleep(0.7)
            continue
        break
    # Stop once we see the prompt come back after some output.
    plain = re.sub(rb"\x1b\[[0-9;?]*[a-zA-Z]", b"", bytes(buf))
    if buf.count(b"\n") >= 2 and plain.rstrip().endswith(b"/#"):
        break

text = bytes(buf).decode("utf-8", "replace")
text = re.sub(r"\x1b\[[0-9;?]*[a-zA-Z]", "", text)
lines = text.replace("\r", "").split("\n")
lines = [ln for ln in lines if ln.strip()]
if lines and cmd.strip() in lines[0]:
    lines = lines[1:]
while lines and re.search(r"/#\s*$", lines[-1]):
    lines.pop()
print("\n".join(lines).strip())
p.close()
