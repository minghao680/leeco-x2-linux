#!/bin/sh
# Bring up QCA6174 WiFi from the x2 initramfs rescue shell.
#
# Run after /data/debian/root is mounted, for example:
#   ROOT=/data/debian/root sh /data/debian/root/usr/local/sbin/x2-wifi-up.sh
#
# The rootfs must already contain:
#   lib/firmware/ath10k/QCA6174/hw3.0/firmware-4.bin
#   lib/firmware/ath10k/QCA6174/hw3.0/board.bin          (Android bdwlan30.bin)
#   lib/firmware/ath10k/QCA6174/hw3.0/board-pci-0000:01:00.0.bin
#   lib/firmware/regulatory.db{,.p7s}                    (real files, not absolute symlinks)
#   etc/wpa_supplicant/wpa_supplicant-wlan0.conf
#
# It intentionally does not contain an SSID or PSK.

set -eu

ROOT=${ROOT:-/data/debian/root}
WPA_CONF=${WPA_CONF:-/etc/wpa_supplicant/wpa_supplicant-wlan0.conf}
WIFI_DNS=${WIFI_DNS:-}

[ -d "$ROOT" ] || { echo "missing rootfs: $ROOT" >&2; exit 1; }
[ -x "$ROOT/usr/sbin/wpa_supplicant" ] || { echo "wpa_supplicant missing" >&2; exit 1; }
[ -f "$ROOT$WPA_CONF" ] || { echo "missing $ROOT$WPA_CONF" >&2; exit 1; }

echo "[wifi] firmware path: $ROOT/lib/firmware"
printf '%s' "$ROOT/lib/firmware" > /sys/module/firmware_class/parameters/path

# 0 means "wait forever" in the firmware loader.  Missing optional cal files
# must fail fast; otherwise probe sits in firmware_fallback_sysfs.
echo 1 > /sys/class/firmware/timeout

echo "[wifi] loading cfg80211 + ath10k_pci"
chroot "$ROOT" /usr/sbin/modprobe cfg80211 || true
chroot "$ROOT" /usr/sbin/modprobe ath10k_pci

i=0
while [ ! -d /sys/class/net/wlan0 ] && [ $i -lt 15 ]; do
	busybox sleep 1
	i=$((i + 1))
done
[ -d /sys/class/net/wlan0 ] || {
	echo "[wifi] wlan0 did not appear; last ath10k log:" >&2
	dmesg | grep -i ath10k | tail -n 20 >&2 || true
	exit 1
}

chroot "$ROOT" /usr/sbin/rfkill unblock all 2>/dev/null || true
chroot "$ROOT" /usr/sbin/iw reg set CN 2>/dev/null || true
chroot "$ROOT" /usr/sbin/ip link set wlan0 up

busybox killall wpa_supplicant 2>/dev/null || true
busybox sleep 1

echo "[wifi] starting wpa_supplicant"
chroot "$ROOT" /usr/sbin/wpa_supplicant -B -D nl80211 -i wlan0 \
	-c "$WPA_CONF" -P /run/wpa_supplicant-wlan0.pid

busybox sleep 8
chroot "$ROOT" /usr/sbin/iw dev wlan0 link || true

echo "[wifi] requesting DHCP"
chroot "$ROOT" /usr/sbin/dhcpcd -4 -t 15 wlan0 || true

if [ -n "$WIFI_DNS" ]; then
	printf 'nameserver %s\n' "$WIFI_DNS" > "$ROOT/etc/resolv.conf"
fi

chroot "$ROOT" /usr/sbin/ip -4 addr show wlan0 || true
chroot "$ROOT" /usr/sbin/ip route || true
