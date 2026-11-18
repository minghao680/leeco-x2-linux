#!/usr/bin/env python3
"""Run a command on the x2 Debian/initramfs shell over NCM telnet.

Usage:
    x2-telnet-run.py <host> <command> [wait_seconds]

telnetd is started by initramfs/init-debian-disk on 192.168.42.1:23, so it
works even when the USB ACM serial console is wedged.
"""

import sys
import time
import telnetlib


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    host = sys.argv[1]
    command = sys.argv[2]
    wait = float(sys.argv[3]) if len(sys.argv) > 3 else 5.0

    tn = telnetlib.Telnet(host, 23, timeout=10)
    time.sleep(0.4)
    tn.write(command.encode() + b"\n")
    time.sleep(wait)
    try:
        out = tn.read_very_eager().decode("utf-8", "replace")
    except EOFError:
        out = ""
    tn.close()
    sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
