import sys

path = sys.argv[1]
data = open(path, "rb").read().replace(b"\r\n", b"\n")
open(path, "wb").write(data)
print("lf-only, bytes", len(data), "crlf-left", data.count(b"\r"))
