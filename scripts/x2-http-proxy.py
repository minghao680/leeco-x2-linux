#!/usr/bin/env python3
"""Minimal HTTP proxy (CONNECT + plain GET) for the x2 Debian VM.

Runs on the Windows host, listens on the NCM link (192.168.42.10:3128).
No admin rights needed; the device points apt at it via
/etc/apt/apt.conf.d/01proxy.

    python scripts/x2-http-proxy.py [--listen 0.0.0.0:3128] [--log path]
"""
import argparse
import http.client as http_client
import socket
import sys
import threading
import time
import urllib.parse

LOG_LOCK = threading.Lock()
LOGFILE = None


def log(msg):
    line = "%s %s" % (time.strftime("%H:%M:%S"), msg)
    with LOG_LOCK:
        print(line, flush=True)
        if LOGFILE:
            with open(LOGFILE, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")


def pump(src, dst):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def handle_connect(conn, hostport):
    try:
        host, port = hostport.rsplit(":", 1)
        up = socket.create_connection((host, int(port)), timeout=15)
    except (OSError, ValueError) as exc:
        log("CONNECT %s failed: %s" % (hostport, exc))
        conn.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
        return
    log("CONNECT %s" % hostport)
    conn.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
    conn.settimeout(None)
    up.settimeout(None)
    t = threading.Thread(target=pump, args=(up, conn), daemon=True)
    t.start()
    pump(conn, up)
    t.join(timeout=5)


def handle_http(conn, method, url, version, headers):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "http" or not parsed.hostname:
        conn.sendall(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
        return
    port = parsed.port or 80
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    drop = {"proxy-connection", "proxy-authorization", "connection", "host"}
    out = [(k, v) for k, v in headers.items() if k.lower() not in drop]
    out.append(("Host", parsed.hostname))
    out.append(("Connection", "close"))
    try:
        http_conn = http_client.HTTPConnection(parsed.hostname, port, timeout=30)
        http_conn.request(method, path, headers=dict(out))
        resp = http_conn.getresponse()
    except (OSError, http_client.HTTPException) as exc:
        log("%s %s failed: %s" % (method, url, exc))
        conn.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
        return
    log("%s %s -> %d" % (method, url, resp.status))
    reason = resp.reason or ""
    head = "HTTP/1.1 %d %s\r\n" % (resp.status, reason)
    for k, v in resp.getheaders():
        if k.lower() in ("connection", "transfer-encoding", "content-length"):
            continue
        head += "%s: %s\r\n" % (k, v)
    body = resp.read()
    head += "Content-Length: %d\r\nConnection: close\r\n\r\n" % len(body)
    conn.sendall(head.encode("latin-1") + body)


def handle(conn, addr):
    conn.settimeout(30)
    try:
        f = conn.makefile("rb")
        line = f.readline(65536).decode("latin-1").strip()
        if not line:
            return
        parts = line.split()
        if len(parts) < 3:
            return
        method, target, version = parts[0], parts[1], parts[2]
        headers = {}
        while True:
            h = f.readline(65536).decode("latin-1")
            if not h or h in ("\r\n", "\n"):
                break
            k, _, v = h.partition(":")
            headers[k.strip()] = v.strip()
        if method.upper() == "CONNECT":
            handle_connect(conn, target)
        else:
            handle_http(conn, method, target, version, headers)
    except (OSError, ValueError) as exc:
        log("client error from %s: %s" % (addr, exc))
    finally:
        try:
            conn.close()
        except OSError:
            pass


def main():
    global LOGFILE
    ap = argparse.ArgumentParser()
    ap.add_argument("--listen", default="0.0.0.0:3128")
    ap.add_argument("--log", default="")
    args = ap.parse_args()
    if args.log:
        LOGFILE = args.log
    host, port = args.listen.rsplit(":", 1)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, int(port)))
    srv.listen(64)
    log("listening on %s:%s" % (host, port))
    while True:
        conn, addr = srv.accept()
        threading.Thread(target=handle, args=(conn, addr), daemon=True).start()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
