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

## 吞吐与稳定性（2026-11-18）

手机在 Debian initramfs 中连接已保存的 5GHz AP（5180 MHz、VHT80、2×2），
host 用 HTTP/TCP 测速（`scripts/x2-speed-server.py`，端口 8000），手机用
`curl` 拉 16 GiB 动态零流或 PUT 1 GiB 文件。选 HTTP 是因为本机 Windows
iperf3 客户端报 `unable to create a new stream: Permission denied`，WSL 到
手机又 `No route to host`；这是测试环境问题，不是内核网络栈问题。

| 场景 | 结果 |
|---|---:|
| 单流下行 5 s | 188,276,064 B / 4.999 s = 37.7 MB/s ≈ 301 Mbit/s |
| 四流下行 30 s | 6.08 + 8.64 + 11.82 + 9.20 = 35.75 MB/s ≈ 286 Mbit/s |
| 四流上行 30 s | 10.22 + 8.84 + 9.89 + 9.90 = 38.85 MB/s ≈ 311 Mbit/s |
| 5 min 连续下行 + 1 Hz ping | 11.23 GB / 300 s = 37.4 MB/s ≈ 299 Mbit/s；ping 300/300，0% 丢包，RTT avg 25.2 ms / max 44.3 ms |

四流下行没有比单流更快，说明瓶颈在 WiFi 链路/AP 侧或 host 无线网卡，
不是手机单条 TCP 流；四流上行略高。5 分钟窗口内 `dmesg` 记录到 2 次
`Reason: 7=CLASS3_FRAME_FROM_NONASSOC_STA` deauth，均在约 0.1 s 内重新
authenticate/associate 成功，ping 没有丢包。当前 `iw dev wlan0 get power_save`
为 `on`；这两个重连可能是 AP 侧状态或省电时序，留作后续 A/B（关省电、
换 `firmware-6`/`board-2`）。

复现：

```sh
# host
python3 scripts/x2-speed-server.py 8000
# phone（rootfs 内）
sh /tmp/x2-speed-test.sh dl     # N=4 SECS=30
sh /tmp/x2-speed-test.sh up     # 需先准备 /tmp/up.bin
```

## 蓝牙现场（2026-11-18）

`hci_uart.ko`、`btqca.ko`、`bluetooth.ko` 都已加载，serdev 设备也已经生成：

```text
/sys/bus/serial/devices/serial0-0
modalias: of:NbluetoothT(null)Cqcom,qca6174-bt
/sys/bus/serial/drivers/hci_uart_qca
```

在 `hci_serdev.c` 的 `serdev_device_open()` 失败分支临时补上 errno 后，抓到：

```text
hci_uart_qca serial0-0: serdev_device_open failed: -6
Bluetooth: serdev registration failed: -6
```

`-6` 是 `-ENXIO`。继续追到 `ttyport_open()` → `uart_open()` →
`uart_port_activate()`：`msm_serial` 把 **debug console `blsp2_uart2`（75b0000）**
和 **BT `blsp1_uart2`（7570000）** 都分配到了 line 0。DTS 的 alias 只有：

```dts
aliases { serial0 = &blsp2_uart2; };
```

蓝牙节点没有 alias，`msm_serial_probe()` 用递增 id 也拿到 0；日志里两个 UART
都打印 `detected port #0`，第二个 probe 以 `-22` 失败。蓝牙 serdev 最终打开
的 tty port 因此不是可用的 BT line。

当前修正：

```dts
aliases {
	serial0 = &blsp2_uart2; /* debug console */
	serial1 = &blsp1_uart2; /* QCA6174 HCI */
};
```

这样 console 保持 `ttyMSM0`，蓝牙走 line 1。真机启动后已确认：

```text
7570000.serial: ttyMSM1   # BT, line 1
75b0000.serial: ttyMSM0   # console, line 0
/sys/bus/serial/devices/serial0-0
```

`hci_uart` + `btqca` 加载后 `hci0` 出现，QCA 固件 setup 完成：

```text
QCA Product ID   :0x00000008
QCA SOC Version  :0x00000044
QCA ROM Version  :0x00000302
QCA Patch Version:0x00000111
QCA controller version 0x00440302
QCA setup on UART is completed
```

下载 `rampatch_00440302.bin` 后会打印一条 `Frame reassembly failed (-84)`，但
后续 NVM 下载、`hci0` 创建、`hciconfig up` 和 BlueZ 扫描都成功，当前按
非致命告警记录，暂不做 H4 重传层改动。

但控制器返回的 BD_ADDR 是全 0，`btqca` 会置 `HCI_QUIRK_USE_BDADDR_PROPERTY`，
Linux 随后把设备标成 `HCI_UNCONFIGURED`，表现为 `DOWN RAW` 和
`hciconfig hci0 up` 返回 `Operation not supported (95)`。修复是给蓝牙节点补一个
本地管理地址（对称字节避免 endian 歧义）：

```dts
bluetooth {
	compatible = "qcom,qca6174-bt";
	enable-gpios = <&pm8994_gpios 19 GPIO_ACTIVE_HIGH>;
	clocks = <&divclk4>;
	local-bd-address = [ 02 00 00 00 00 02 ];
};
```

真机验证：

```text
hci0: BD Address: 02:00:00:00:00:02  ACL MTU: 1024:7  SCO MTU: 60:8
      UP RUNNING
bluetoothctl list:
Controller 02:00:00:00:00:02 BlueZ 5.82 [default]
```

`BlueZ 5.82` 扫描已能发现附近设备（美的空调、米家体重秤等），说明 HCI、
L2CAP、SCO、LE 广播路径都已打通。生产 init 现在会自动加载 `bluetooth`/`btqca`/`hci_uart`、启动 `dbus-daemon --system` 和 `bluetoothd`，再 `hciconfig hci0 up`；当前验证镜像为 `out/boot-x2-debian-btlog.img`。

## 还没做

- 24 h 长稳/iperf3 原始 TCP 对比；当前只有 5 min HTTP 持续下行 + ping。
- 蓝牙真实出厂 BD_ADDR：当前用 `02:00:00:00:00:02` 本地管理地址；后续可从
  Android 的 NVM/persist 数据提取原始地址替换。
- A2DP/HFP、BLE GATT 外设、配对/绑定持久化等上层功能还没逐项验收。
- `firmware-6` + 正确的 `board-2` 是否能把速率/稳定性做得更好，留作 A/B。
- `Reason 7` deauth 的 AP/省电时序 A/B（关 `power_save`、换 AP 信道）。
- RTC 持久化/NTP，避免每次开机都回到 1970。
