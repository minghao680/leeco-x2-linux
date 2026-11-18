#!/bin/sh
# HTTP throughput test against the host speed server (port 8000).
# Usage: sh x2-speed-test.sh dl|up
set -u

HOST=${HOST:-192.168.1.179}
URL=http://$HOST:8000/test.bin
UPURL=http://$HOST:8000/upload
N=${N:-4}
SECS=${SECS:-30}

case "${1:-dl}" in
dl)
	rm -f /tmp/dl*.log
	i=1
	while [ "$i" -le "$N" ]; do
		curl -m "$SECS" -sS -o /dev/null \
			-w "%{speed_download} %{size_download} %{time_total}\n" \
			"$URL" > "/tmp/dl$i.log" 2>&1 &
		i=$((i + 1))
	done
	wait
	echo "=== downlink streams ==="
	cat /tmp/dl*.log
	;;
up)
	rm -f /tmp/up*.log
	i=1
	while [ "$i" -le "$N" ]; do
		curl -m "$SECS" -sS -H 'Expect:' -T /tmp/up.bin \
			-w "%{speed_upload} %{size_upload} %{time_total}\n" \
			"$UPURL" > "/tmp/up$i.log" 2>&1 &
		i=$((i + 1))
	done
	wait
	echo "=== uplink streams ==="
	cat /tmp/up*.log
	;;
*)
	echo "usage: $0 dl|up" >&2
	exit 2
	;;
esac
