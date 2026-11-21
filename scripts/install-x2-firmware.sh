#!/bin/sh
# Install the x2 firmware bundle into a booted Debian rootfs.
#
# Usage (inside the x2 Debian system):
#   sudo ./scripts/install-x2-firmware.sh /path/to/x2-firmware
#
# The bundle directory must contain manifest.tsv and
# x2-firmware-rootfs.tar.gz. Existing files are copied to
# /var/backups/x2-firmware/<timestamp>/ before they are replaced.

set -eu

BUNDLE=${1:?usage: install-x2-firmware.sh BUNDLE_DIR}
MANIFEST="$BUNDLE/manifest.tsv"
TARBALL="$BUNDLE/x2-firmware-rootfs.tar.gz"

[ "$(id -u)" -eq 0 ] || { echo "must run as root" >&2; exit 1; }
[ -r "$MANIFEST" ] || { echo "missing $MANIFEST" >&2; exit 1; }
[ -r "$TARBALL" ] || { echo "missing $TARBALL" >&2; exit 1; }

verify_manifest() {
	while IFS='	' read -r hash bytes path; do
		[ "$hash" = "sha256" ] && continue
		[ -n "$path" ] || continue
		if [ ! -f "/$path" ]; then
			echo "missing: /$path" >&2
			return 1
		fi
		actual=$(sha256sum "/$path" | cut -d' ' -f1)
		if [ "$actual" != "$hash" ]; then
			echo "checksum mismatch: /$path" >&2
			return 1
		fi
	done < "$MANIFEST"
}

echo "[1/4] verifying staged bundle"
tmp=$(mktemp -d)
trap ':' EXIT
tar -xzf "$TARBALL" -C "$tmp"
( cd "$tmp" && awk -F '\t' 'NR>1 {print $1"  "$3}' "$MANIFEST" | sha256sum -c - >/dev/null )

backup="/var/backups/x2-firmware/$(date +%Y%m%d-%H%M%S)"
echo "[2/4] saving overwritten files under $backup"
mkdir -p "$backup"
tar -tzf "$TARBALL" | while IFS= read -r path; do
	case "$path" in
		*/|.) continue ;;
	esac
	if [ -f "/$path" ]; then
		mkdir -p "$backup/$(dirname "$path")"
		cp -a "/$path" "$backup/$path"
	fi
done

echo "[3/4] installing firmware into /usr/lib/firmware"
# The bundle is staged as usr/lib/firmware/... because Debian is usr-merged.
# Extracting it must never replace /lib (a symlink to usr/lib) with a directory.
tar -xzf "$TARBALL" --no-same-owner -C /
while IFS='	' read -r hash bytes path; do
	[ "$hash" = "sha256" ] && continue
	[ -n "$path" ] || continue
	chmod 0644 "/$path"
done < "$MANIFEST"

echo "[4/4] verifying installed files"
( cd / && awk -F '\t' 'NR>1 {print $1"  "$3}' "$MANIFEST" | sha256sum -c - >/dev/null )

echo "installed. Reboot (or reload the relevant module) so udev re-probes with the new firmware."
echo "Note: the matching boot image must set firmware_class path to the Debian rootfs;"
echo "the GPU zap shader and pm4/pfp/gpmu still have to be embedded in the initramfs because they probe before init."
