import http.server
import os
import socketserver
import sys
import time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
CHUNK = 1024 * 1024
# 16 GiB is enough for a 3-minute run at >700 Mbit/s.
GET_SIZE = 16 * 1024 * 1024 * 1024
BASE = os.path.dirname(os.path.abspath(__file__))
BASE_REAL = os.path.realpath(BASE)


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        path = self.path.split("?")[0]
        if path != "/test.bin":
            name = path.lstrip("/")
            full = os.path.realpath(os.path.join(BASE, name))
            if name and full.startswith(BASE_REAL + os.sep) and os.path.isfile(full):
                data = open(full, "rb").read()
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                return
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(GET_SIZE))
        self.end_headers()
        chunk = b"\0" * CHUNK
        sent = 0
        try:
            while sent < GET_SIZE:
                self.wfile.write(chunk)
                sent += CHUNK
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(GET_SIZE))
        self.end_headers()

    def do_PUT(self):
        self._receive_body()

    def do_POST(self):
        self._receive_body()

    def _receive_body(self):
        total = 0
        length = self.headers.get("Content-Length")
        if length:
            left = int(length)
            while left > 0:
                data = self.rfile.read(min(CHUNK, left))
                if not data:
                    break
                total += len(data)
                left -= len(data)
        else:
            while True:
                data = self.rfile.read(CHUNK)
                if not data:
                    break
                total += len(data)
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(str(total))))
        self.end_headers()
        self.wfile.write(str(total).encode())


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


with Server(("0.0.0.0", PORT), Handler) as srv:
    srv.serve_forever()
