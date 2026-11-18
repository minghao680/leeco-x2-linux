# QCA6174 board data for LeEco x2

`bdwlan30.bin` is the board data blob shipped in this device's Android
`modem.img` at `image/bdwlan30.bin`.

- size: 8124 bytes
- sha256: `d8b3137be053d73d249e08a0d47c1345bb570e48f534762866855ec3fc0bbbf7`
- source image: `backup/x2-partitions-20261112/pmos-backup/modem.img`
- extracted with 7-Zip from the FAT image, path `image/bdwlan30.bin`

The generic `linux-firmware` `board.bin` for QCA6174 hw3.0 is **not** the right
board data for this machine. It loads, but the card transmits with the wrong
board/MAC calibration and authentication frames never reach the AP (the
driver logs `authentication ... timed out`).

Deploy on the Debian rootfs as both of these names:

```sh
cd /data/debian/root/lib/firmware/ath10k/QCA6174/hw3.0
cp bdwlan30.bin board.bin
cp bdwlan30.bin board-pci-0000:01:00.0.bin
```

`ath10k` first tries `board-2.bin`; the PCI subsystem IDs on this unit are
`0000:0000`, so the generic `board-2.bin` has no matching entry. The
`board-pci-<pci-name>.bin` path above then loads directly and avoids the
firmware-loader fallback wait.

The `bdwlan30.b00` ... `bdwlan30.b1c` files in the modem image are alternate
board variants. `bdwlan30.bin` is the default used here.
