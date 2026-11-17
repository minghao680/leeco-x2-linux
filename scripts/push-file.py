"""One-shot TCP file server for pushing files into the x2 over its USB NCM link.

The Debian rootfs on the phone is deliberately minimal: no nc, no wget, no curl.
But it does have bash, and bash can act as a TCP client via /dev/tcp, so the
device pulls the file itself:

    cat < /dev/tcp/192.168.42.10/9000 > /tmp/x.deb

This side just waits for one connection, streams the file once, and exits.

Usage: push-file.py <file> <port> [timeout_s]
"""

import socket
import sys
import time

path = sys.argv[1]
port = int(sys.argv[2])
timeout = float(sys.argv[3]) if len(sys.argv) > 3 else 120.0
size = __import__("os").path.getsize(path)
print(f"file={path} size={size} port={port}", flush=True)

srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("0.0.0.0", port))
srv.listen(1)
srv.settimeout(timeout)

try:
    conn, addr = srv.accept()
except socket.timeout:
    print("TIMEOUT: nobody connected", flush=True)
    srv.close()
    sys.exit(1)

print(f"connected from {addr}", flush=True)
start = time.time()
sent = 0
with open(path, "rb") as f:
    while True:
        chunk = f.read(65536)
        if not chunk:
            break
        conn.sendall(chunk)
        sent += len(chunk)
        if sent % (65536 * 8) == 0:
            print(f"  sent {sent // 1024} KiB", flush=True)
conn.shutdown(socket.SHUT_WR)
time.sleep(0.3)
conn.close()
srv.close()
el = time.time() - start
print(f"DONE sent={sent} bytes in {el:.1f}s ({sent / max(el, 1e-9) / 1024:.0f} KiB/s)", flush=True)
