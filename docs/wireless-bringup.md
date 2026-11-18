# QCA6174 WiFi bring-up（2026-11-18）

目标：在 x2 的 Debian 13 侧把 QCA6174 从「PCIe 能枚举」推进到「`wlan0` 可用、
WPA2 关联、DHCP、外网、apt 可用」。

## 结论

已完成。当前连接结果：

| 项目 | 结果 |
|---|---|
| 网卡 | `wlan0`，MAC `00:03:7f:c2:00:43` |
| AP | `？？？5G`，BSSID `52:33:f0:9c:8d:66` |
| 频段/速率 | 5180 MHz，VHT80 2×2，协商速率 526.6 Mbit/s |
| 信号 | -27 dBm |
| 加密 | WPA2-PSK / CCMP |
| DHCP | `192.168.1.173/24`，网关 `192.168.1.1` |
| 外网 | `ping 223.5.5.5`，15.1–24.1 ms |
| apt | 阿里云 `trixie`、`trixie-updates`、`trixie-security` 全部 `Hit` |

## 关键发现（按重要性）

### 1. 必须使用本机 Android 的 `bdwlan30.bin` 作为 board data

`linux-firmware` 自带的通用 `board.bin` 能加载，但**发射路径不对**：

- 通用 `board.bin`：`board_file api 1 ... crc32 ed5f849a`，网卡 MAC 为
  `00:03:7f:50:00:01`；`iw scan` 能看到 AP，但 `wpa_supplicant` 一直停在
  `Trying to authenticate`，`tx_packets` 为 0，最后
  `authentication ... timed out`。
- Android `modem.img` 里的 `bdwlan30.bin`：`board_file api 1 ... crc32 03928380`，
  网卡 MAC 变为 `00:03:7f:c2:00:43`；认证、关联、四次握手一次通过，TX 正常。

`bdwlan30.bin` 已放在 `firmware/qca6174/bdwlan30.bin`，SHA256：

```text
d8b3137be053d73d249e08a0d47c1345bb570e48f534762866855ec3fc0bbbf7
```

来源和部署方法见 `firmware/qca6174/README.md`。在 rootfs 中必须同时放成：

```text
/lib/firmware/ath10k/QCA6174/hw3.0/board.bin
/lib/firmware/ath10k/QCA6174/hw3.0/board-pci-0000:01:00.0.bin
```

本机 PCI subsystem 是 `0000:0000`，通用 `board-2.bin` 匹配不到任何条目；
`board-pci-0000:01:00.0.bin` 可以直接命中，避免 sysfs fallback。

### 2. 用 `firmware-4.bin`，暂时禁用 `firmware-6.bin`

- `firmware-4.bin`：API 4，`WLAN.RM.2.0-00180-QCARMSWPZ-1`，稳定。
- `firmware-6.bin`：API 6，`WLAN.RM.4.4.1-00309-`，在启动 wpa_supplicant
  尝试关联后机器重启回 Android；该次启动没有留下 fw6 的崩溃日志。当前已重命名为
  `firmware-6.bin.disabled`，驱动回退到 `firmware-4.bin`。

如果以后要再试 API 6，先准备好匹配的 board data，再单独做 A/B，不要直接替换
工作版本。

### 3. `firmware_class` 的 path 和 timeout

当前内核根是 initramfs，Debian 的 `/lib/firmware` 在 rootfs 里，内核看不到。
必须在加载模块**之前**设置：

```sh
printf '%s' /data/debian/root/lib/firmware \
  > /sys/module/firmware_class/parameters/path
echo 1 > /sys/class/firmware/timeout
```

注意：

- 用 `printf`，不要用会补换行的写法；path 里多一个换行会导致直接加载失败。
- `timeout=0` 是「无限等待」，不是「立即失败」。之前 probe 卡在
  `firmware_fallback_sysfs` 就是这个原因。
- `timeout=1` 后，缺失的可选 `pre-cal-pci-...bin` / `cal-pci-...bin` 会在 1 秒后
  失败并继续；本机最终走 `cal otp`（OTP 校准），不需要额外的 cal 文件。

加载顺序：

```sh
chroot /data/debian/root /usr/sbin/modprobe cfg80211
chroot /data/debian/root /usr/sbin/modprobe ath10k_pci
```

`cfg80211` 加载时会读 `regulatory.db`；`ath10k_pci` 加载时读 firmware、board 和
可选的 cal 文件。

### 4. `regulatory.db` 的绝对符号链接在 initramfs 下是坏的

Debian 的 `/lib/firmware/regulatory.db` 是：

```text
regulatory.db -> /etc/alternatives/regulatory.db
```

这个绝对路径是相对**当前内核根**（initramfs）解析的，不是相对 Debian rootfs。
所以会 `Direct firmware load ... failed with error -2`。解决：

```sh
cd /data/debian/root/lib/firmware
rm -f regulatory.db regulatory.db.p7s
cp regulatory.db-upstream regulatory.db
cp regulatory.db.p7s-upstream regulatory.db.p7s
```

然后用 `iw reg set CN`。当前 `iw reg get` 显示 global `country CN`，AP 的
beacon/association 也触发 `CTRL-EVENT-REGDOM-CHANGE ... alpha2=CN`。
`phy#0` 仍可能显示驱动自管的 `US` 域；5180 MHz（channel 36）在 US/CN 都允许，
不影响当前连接。

### 5. wpa_supplicant / DHCP

PSK 从本机 Android 的 `/data/misc/wifi/WifiConfigStore.xml` 读取（该文件里只有
一个 5GHz 网络），**不写进仓库**。设备上的配置：

```text
/data/debian/root/etc/wpa_supplicant/wpa_supplicant-wlan0.conf
```

配置里加 `ctrl_interface=/run/wpa_supplicant`，否则 `wpa_cli` 找不到 socket。
启动：

```sh
chroot /data/debian/root /usr/sbin/ip link set wlan0 up
chroot /data/debian/root /usr/sbin/wpa_supplicant -B -D nl80211 -i wlan0 \
  -c /etc/wpa_supplicant/wpa_supplicant-wlan0.conf \
  -P /run/wpa_supplicant-wlan0.pid
```

DHCP：

```sh
chroot /data/debian/root /usr/sbin/dhcpcd -4 -t 15 wlan0
```

`dhcpcd` 拿到 `192.168.1.173`，添加默认路由，并把 `/etc/resolv.conf` 指向
DHCP 下发的 DNS；如果它没有覆盖，手工写：

```sh
printf 'nameserver 192.168.1.1\nnameserver 223.5.5.5\n' \
  > /data/debian/root/etc/resolv.conf
```

### 6. apt 换源和时钟

apt 源已经是阿里云：

```text
http://mirrors.aliyun.com/debian/ trixie main contrib non-free-firmware
http://mirrors.aliyun.com/debian/ trixie-updates ...
http://mirrors.aliyun.com/debian-security/ trixie-security ...
```

原先给 NCM 宿主代理用的 `/etc/apt/apt.conf.d/01x2-proxy` 已改名为
`01x2-proxy.disabled`；WiFi 直连时不要保留 `192.168.42.10:3128` 代理。

手机 RTC 每次启动会回到 1970，`sqv` 会报
`Not live until ...` 导致签名校验失败。联网后先校时：

```sh
/bin/busybox date -u -s "2026-11-18 14:30:10"
```

再 `apt-get update`，三个源全部通过。

## 当前可复现流程

在 initramfs 的 telnet/串口 shell 中，rootfs 已挂到 `/data/debian/root`：

```sh
ROOT=/data/debian/root

printf '%s' "$ROOT/lib/firmware" \
  > /sys/module/firmware_class/parameters/path
echo 1 > /sys/class/firmware/timeout

chroot "$ROOT" /usr/sbin/modprobe cfg80211
chroot "$ROOT" /usr/sbin/modprobe ath10k_pci

# 等 wlan0
i=0
while [ ! -d /sys/class/net/wlan0 ] && [ $i -lt 10 ]; do
  sleep 1; i=$((i+1))
done

chroot "$ROOT" /usr/sbin/iw reg set CN || true
chroot "$ROOT" /usr/sbin/ip link set wlan0 up
chroot "$ROOT" /usr/sbin/rfkill unblock all || true

chroot "$ROOT" /usr/sbin/wpa_supplicant -B -D nl80211 -i wlan0 \
  -c /etc/wpa_supplicant/wpa_supplicant-wlan0.conf \
  -P /run/wpa_supplicant-wlan0.pid
sleep 8

chroot "$ROOT" /usr/sbin/dhcpcd -4 -t 15 wlan0
```

仓库里的 `scripts/x2-wifi-up.sh` 就是这段流程的可执行版本，默认
`ROOT=/data/debian/root`，可用 `WPA_CONF` / `WIFI_DNS` 覆盖。

## 验证记录

```text
wlan0: authenticate with 52:33:f0:9c:8d:66 (local address=00:03:7f:c2:00:43)
wlan0: send auth to ... (try 1/3)
wlan0: authenticated
wlan0: associate with ... (try 1/3)
wlan0: RX AssocResp ... status=0 aid=7
wlan0: associated
wlan0: WPA: Key negotiation completed ... [PTK=CCMP GTK=CCMP]
wlan0: CTRL-EVENT-CONNECTED
```

```text
5: wlan0: inet 192.168.1.173/24 ... state UP
default via 192.168.1.1 dev wlan0 proto dhcp src 192.168.1.173 metric 3005

PING 223.5.5.5: 2 packets transmitted, 2 received, 0% packet loss
rtt min/avg/max/mdev = 15.121/19.610/24.100/4.489 ms
```

## 蓝牙现场（2026-11-18）

`hci_uart.ko`、`btqca.ko`、`bluetooth.ko` 都已加载，serdev 设备也已经生成：

```text
/sys/bus/serial/devices/serial0-0
modalias: of:NbluetoothT(null)Cqcom,qca6174-bt
/sys/bus/serial/drivers/hci_uart_qca
```

但绑定 `serial0-0` 时返回失败，dmesg 只有：

```text
Bluetooth: serdev registration failed
```

打开 `hci_qca` 的 dynamic debug 后能看到 probe 走到
`UART will pick default operating speed`，但没有 `qca_open` 的 `BT_DBG`，说明失败发生在
`hci_uart_register_device()` 内部、`qca_open` 之前，最可能是
`serdev_device_open()` / `ttyport_open()`。`msm_serial 7570000.serial` 已经注册
`ttyMSM0`，所以下一步是给 `hci_qca.c` 的失败分支补 `err` 值，或直接检查
`serdev-ttyport.c:ttyport_open()` 的 `tty->ops->open()` 返回码。

## 还没做

- 开机自动加载 `ath10k`、自动连 WiFi、自动 DHCP（当前是手动跑脚本）。
- WiFi 吞吐/长时间稳定性（`iperf3`、24 h）。
- 蓝牙：`hci_uart` + `btqca`，BT_EN 为 PM8994 GPIO19，固件文件已在 rootfs。
- `firmware-6` + 正确的 `board-2` 是否能把速率/稳定性做得更好，留作 A/B。
- RTC 持久化/NTP，避免每次开机都回到 1970。
