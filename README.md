# LeEco Le Max 2 (x2 / LEX820) · Linux 6.19 + Debian 13

[![Build kernel + DTB](https://github.com/minghao680/leeco-x2-linux/actions/workflows/kernel.yml/badge.svg)](https://github.com/minghao680/leeco-x2-linux/actions/workflows/kernel.yml)
[![Quick DTB check](https://github.com/minghao680/leeco-x2-linux/actions/workflows/dtb-check.yml/badge.svg)](https://github.com/minghao680/leeco-x2-linux/actions/workflows/dtb-check.yml)
[![Panel driver](https://github.com/minghao680/leeco-x2-linux/actions/workflows/panel-check.yml/badge.svg)](https://github.com/minghao680/leeco-x2-linux/actions/workflows/panel-check.yml)
[![Initramfs](https://github.com/minghao680/leeco-x2-linux/actions/workflows/initramfs.yml/badge.svg)](https://github.com/minghao680/leeco-x2-linux/actions/workflows/initramfs.yml)

把乐视 Le Max 2 跑成一台可用的 Linux 设备。当前使用 `6.19.5-msm8996` 主线内核、
Debian 13 用户空间，保留 Android 10 作为另一套可启动系统；不重分区、不写
boot/system。

## 当前状态

| 能力 | 状态 |
|---|---|
| 内核 | `6.19.5-msm8996+`，39-bit VA，4 核 / 5.7 GB 可用 |
| 用户空间 | Debian 13.7，`apt` / `bash` / SSH 可用 |
| 根文件系统 | userdata 上的目录式根 `/data/debian/root`，可持久化 |
| UFS | 已修复冷启动 `fDeviceInit` 与高负载持续写；两次冷启动、Debian/Android/TWRP 三种热重启均通过 |
| 显示 | MDP5 双接口，1440×2560 全屏 console 已点亮 |
| 输入 | Atmel maXTouch 触摸可用；按键映射待补 |
| WiFi | QCA6174 5GHz/WPA2，开机自动连接、DHCP、外网、阿里云 apt；实测约 300 Mbit/s |
| 远程登录 | `sshd` 开机自动启动，root 密码登录，监听 `0.0.0.0:22` |
| 蓝牙 | QCA6174 驱动/固件；已定位为 UART line 冲突，DTB 修正待启动验证 |
| Android | 与 Debian 共存，userdata 未重分区 |

## 快速入口

当前阶段由 bootloader 的 `fastboot boot` 内存加载内核、DTB 和 initramfs：

```sh
fastboot boot out/boot-x2-debian-wifi-ssh-btline.img
```

启动后：

1. initramfs 挂载 `/dev/sda9`，优先进入 `/data/debian/root`
2. 目录根不可用时回退到 initramfs 内的 RAM rootfs
3. USB NCM 提供 `192.168.42.1`，串口与 telnet 作为备用入口
4. `init-debian-disk` 自动加载 QCA6174、连接已保存的 WPA 网络、DHCP，并关闭
   `power_save`
5. rootfs 中存在 `/usr/sbin/sshd` 时自动启动 SSH；root 密码登录，默认端口 22

WiFi 不可用或没有 WPA 配置时，启动不会阻塞，USB NCM 仍然保留。手动重建
WiFi 仍可使用 `scripts/x2-wifi-up.sh`。

内核和根文件系统均未写入 boot/system 分区；日常免 fastboot 启动仍是后续工作。

## 仓库结构

```text
kernel/                   # 6.19 内核配置、DTS、补丁与面板驱动
  config-x2-msm8996-va39.aarch64
  patches/
initramfs/                # Debian 启动、救援与 NCM 脚本；生产入口只有 init-debian-disk
scripts/                  # 构建、打包、串口、UFS 调试、WiFi 辅助脚本
firmware/qca6174/         # 从本机 Android 提取的 QCA6174 board data
docs/                     # 硬件、bring-up 计划、阶段记录；入口见 docs/README.md
.github/workflows/        # 内核、DTB、面板、initramfs 构建检查
out/                      # 本地产物，已忽略，不提交
```

- 代码和配置：`kernel/`、`initramfs/`、`scripts/`
- 设备资料：`docs/x2-hardware.md`、`docs/x2-sensors.md`
- 当前路线：`docs/plan-debian-bringup.md`
- 无线细节：`docs/wireless-bringup.md`
- 完整文档索引：`docs/README.md`

## 构建

宿主机使用 WSL2 Debian，内核源码树默认在 `~/linux-msm8996`：

```sh
wsl -d Debian -- bash -lc \
  'cd /mnt/g/LeEco-Max2/leeco-x2-linux && sh scripts/local-build.sh'
```

脚本会还原干净源码树、应用 `kernel/patches/*.patch`、生成 `.config`，输出：

```text
out/local-build/Image.gz
out/local-build/msm8996-leeco-x2.dtb
```

需要 WiFi 模块时：

```sh
BUILD_MODULES=1 sh scripts/local-build.sh
# out/local-build/modules.tar.xz
```

再用 `scripts/make-bootimg.py` 把内核、DTB 和 initramfs 打包成 boot 镜像。

## 网络实测

2026-11-18，手机在 Debian initramfs 中通过 QCA6174 连接 5GHz AP，
host 端用 HTTP/TCP 测速（应用层，单/四流，30 s）：

| 方向 | 单流 | 四流合计 |
|---|---:|---:|
| 手机接收（host → phone） | 37.7 MB/s ≈ 301 Mbit/s | 35.7 MB/s ≈ 286 Mbit/s |
| 手机发送（phone → host） | — | 38.9 MB/s ≈ 311 Mbit/s |

链路为 5180 MHz、VHT80 2×2；上面是应用层 HTTP 结果，不是 iperf3 原始
TCP 上限，手机 CPU/存储和服务端 Python 都会占一部分开销。5 分钟连续下行
平均 37.4 MB/s（≈299 Mbit/s），同时 ping 网关 300/300、0% 丢包；dmesg
记录到 2 次 `Reason 7` deauth 并自动重连成功。详见
[docs/wireless-bringup.md](docs/wireless-bringup.md)。

`scripts/x2-wifi-up.sh` 是 WiFi 拉起脚本；`scripts/x2-speed-test.sh` 是上面的
HTTP 测速脚本（需要 host 运行 `scripts/x2-speed-server.py`）。

## 已知问题

- **蓝牙 UART 行冲突（待验证）**：QCA6174 的 `blsp1_uart2` 没有 serial alias，
  和 debug console 的 `blsp2_uart2` 都落到 line 0；`serdev_device_open()` 返回
  `-ENXIO`，`hci_uart_register_device()` 在 `qca_open` 之前失败。DTS 已增加
  `serial1 = &blsp1_uart2` 让两者分行，需下次启动确认。
- **常态启动**：仍依赖 `fastboot boot`，未写入 boot 分区。
- **显示**：console 已点亮；GPU/freedreno 和桌面合成尚未做。
- **外设**：音频、摄像头、传感器、指纹未完成。

## 注意

刷机有风险。修改分区前先备份 `modemst1`、`modemst2`、`fsg`、`persist` 等
不可再生数据。仓库中的 boot 镜像目前以内存加载验证为主，不要直接把未验收
镜像写入 boot 分区。WiFi PSK 只保存在手机 rootfs 的
`/etc/wpa_supplicant/wpa_supplicant-wlan0.conf`，不进入仓库；SSH 的 root 密码也只
保存在手机 rootfs 的 `/etc/shadow`，仓库里不放密钥或口令。
