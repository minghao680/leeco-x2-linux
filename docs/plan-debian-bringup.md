# 计划：把 x2 从「能跑」推到「能用」

基线：主线 6.19 + Debian 13 已在真机运行，USB NCM + SSH 可用（4.64 MB/s）。
下面是把它变成一个日常可用的系统的路线，按"解除阻塞的先后"排，不按"看起来爽"排。

## 现状基线

| 能力 | 状态 |
|---|---|
| 内核 | `6.19.5-msm8996+`，VA39，4 核 / 5.7 GB |
| 用户空间 | Debian 13.7，`apt`/`bash` 可用，187 包 |
| 远程 | SSH over NCM 已验证；USB ACM 串口（COM12）可用 |
| 根 | **userdata 目录根** `/data/debian/root`（53G ext4；`rw`、journal recovery、实际写测均已验收） |
| UFS | **0019 regulator DRMS 修复已验收，0015/0016 已经 A/B 删除**；screen52 最小补丁版通过两次真冷启动和 1 GiB 持续写，正常 PM 稳定，见 `docs/ufs-static-analysis.md` |
| 屏幕 | **1440×2560 全屏 console 已点亮**（`screen23`，MDP5 双接口正统方案） |
| 电量 | `qcom-battery` 可读 `capacity`（当前 16%） |
| WiFi / BT | **WiFi 已连通**：QCA6174 5GHz/WPA2、DHCP、外网、阿里云 apt；蓝牙待做 |
| GPU | disabled，无硬件合成 |
| 交互 | 触摸对（`atmel_mxt_ts`），按键未映射 |

## 阶段 A：持久化根（P0，先做）

**为什么先做**：现在每次改点用户空间的东西都要重来一遍，所有后续工作的效率都被
这一步卡着。

**决策（2026-11-17）**：配额 32 GiB；但因 mkfs 被安全策略硬拦截，最终**不用镜像文件**，
改成 **userdata 上的目录式根** `/data/debian/root`（ext4 直接承载，无 loop、无格式化）。

**状态：已完成并验收（2026-11-17）**。启动日志 `[init] /dev/sda9 mounted rw,noload on /data` →
`[init] disk root OK: 13.7` → `root source: userdata (/data/debian/root)`；`df /` 显示 53G/48G 可用；
硬断电后 `/root/x2-marker` 内容原样保留。

**实际走通的流程**：

1. **解包在 Android 侧做**：把 initramfs 里的静态 `busybox`（`out/busybox-x2`，2,237,080 B，
   v1.37.0）push 到 `/data/local/tmp/busybox-x2`，然后在 Android root shell 里：
   `busybox xz -dc <tar.xz> | busybox tar -xf - -C /data/debian/root`
   归档 sha256 与官方 `.sha256` 一致；解包后 452.8 MB，`usr/bin/bash` 1,412,096 B，
   `etc/debian_version` = 13.7。
2. **旧稳定基线**：`mount -o rw,noload /dev/sda9 /data`。旧内核在 journal replay 时进入 D 状态，
   当时用 `noload` 绕过；后续 PM A/B 已证明持续写/writeback 故障来自 UFS 电源路径，
   因而 `noload` 不再被视为永久硬要求。
3. **当前稳定基线**：initramfs（`initramfs/init-debian-disk`）使用 `mount -o rw`，允许 ext4
   journal replay。screen52 在正常 PM 下已通过两次真冷启动和 1 GiB 持续写；
   并已完成 Debian/Android/TWRP 三种前态热重启及各自 256 MiB 写测。journal recovery、userdata `rw` 挂载均通过。
4. **Android → Debian 的过渡**：Android 的“关机”可能不 unmount `/data`，superblock 会保留
   RECOVER 位；现由主线正常完成 journal replay，不再要求每次先去 TWRP 跑 `e2fsck`。
   若文件系统本身另有损坏，再按普通 ext4 维护流程处理。
5. 旧基线验收：`screen26` 启动即磁盘根；重启一次后 marker/rootfs 均在；Android 数据无损
   （`e2fsck -fn` 报 37,152 files / 1,601,831 blocks，无错误）。

**风险 / 注意**：旧 `noload` 基线会跳过 journal，已不再是当前流程。screen52 的 `rw`
流程已通过两次真冷启动、Debian/Android/TWRP 三种前态热重启、journal replay 和写后 `sync`。不再需要把 TWRP `e2fsck`
当作常规切换步骤。主线上没有 SELinux，写进去的文件没有 label，Android 只是看到一个
不认识的目录。

## 阶段 B：一次内核构建，解决屏幕与电量（P1）

这三件事都要改 DTS/config，**合并成一次 CI 构建、一次 `fastboot boot`**，因为每次
重启都要人工进 fastboot，不能一项一次。

1. `panel-leeco-x2.c`：video mode 面板驱动，参数已从厂商 dtsi 取全（720×2560/链路、
   hfp154/hbp100/hpw10、vfp8/vbp7/vpw1、60 Hz、24 bpp、10 条 on-command、
   reset `<1 10>,<0 10>,<1 10>`，双链路 `dual-dsi-mode`+`master-dsi`+`sync-dual-dsi`）。
2. DTS：`wled@d800` 改 `okay`，把背光接进 panel 的 `backlight` 引用。
3. DTS：`charger@1000`、`fuel-gauge@4000` 改 `okay`，让 `upower`/`/sys/class/power_supply`
   能看到电量。
4. 验收：屏幕出图（先只要能显示 fbcon 文字），`cat /sys/class/power_supply/*/capacity`
   有百分比。

## 阶段 C：让 Debian 能上网（P1）

没有外网，`apt` 就是个摆设，后面装固件、装工具全被卡。

1. 主机侧跑一个极简 HTTP CONNECT 代理，绑 `192.168.42.10:3128`（不需要管理员权限，
   比 ICS 现实）。
2. 设备侧写 `apt.conf.d/01proxy`，`apt update` 验证。
3. 顺手把 `openssh-server` 用 apt 正式装一遍，替掉手搓的那套，`systemd` 起
   `ssh.service`（配合持久化根才能真正开机自启）。

**为什么不做 ICS**：Windows 的 Internet 连接共享要管理员，这个会话拿不到。
代理这条路只需要普通权限。

## 阶段 D：USB OTG 与按键（P2）

1. `dr_mode = "otg"` + role switch。注意**和 NCM 互斥**：转 host 就没有网络和 SSH，
   所以要做成"插 OTG 才切 host"的形态，并保留串口兜底。
2. `gpio-keys` 补齐 vol-down 等；对照厂商 dtsi 逐个核。
3. 验收：插 U 盘能挂载；按键 `evtest` 有事件。

## 阶段 E：WiFi / 蓝牙（P2）

**WiFi 状态：已完成（2026-11-18）**。详细记录见 `docs/wireless-bringup.md`。

1. `pcie0@600000` + PHY 已启用，QCA6174 `0000:01:00.0` 枚举正常。
2. board data **不是**通用 `board-2.bin`：本机 PCI subsystem 为 `0000:0000`，通用
   `board-2.bin` 匹配不到；必须用 Android `modem.img` 里的 `image/bdwlan30.bin`
   （8124 B，SHA256 `d8b3137b...`）作为 `board.bin` 和
   `board-pci-0000:01:00.0.bin`。通用 board 会导致 TX 不出去、认证超时。
3. 内核用 `firmware-4.bin`（API 4）稳定；`firmware-6.bin`（API 6）在启动
   wpa_supplicant 尝试关联后机器重启回 Android，未留下 fw6 崩溃日志，当前重命名为
   `firmware-6.bin.disabled`。
4. `firmware_class` path 必须在加载前指向 rootfs firmware，且 `timeout=1`；
   `timeout=0` 会无限等待 `firmware_fallback_sysfs`。`regulatory.db` 的绝对
   alternatives 符号链接在 initramfs 下失效，需换成真实文件。
5. 验收结果：`wlan0` 关联 `？？？5G`（5180 MHz，VHT80 2×2，-27 dBm），DHCP
   `192.168.1.173/24`，`ping 223.5.5.5` 15–24 ms，阿里云三个 apt 源全部 `Hit`。
6. 下一步：BT `hci_qca` + `btqca`（BT_EN 为 PM8994 GPIO19）；WiFi 自动连接、
   `iperf3` 吞吐和 24 h 稳定性测试。

## 阶段 F：GPU 与媒体（P3）

1. `gpu@b00000` + `iommu@d00000/d40000/da0000` 打开，freedreno（Adreno 530）。
2. 有了 GPU 才谈得上"接近安卓的流畅度"；之前所有界面合成都是软件光栅。
3. 再往后是 venus 视频解码、camss 相机、modem 通话——工程量最大，最后碰。

## 阶段 G：传感器（P2，2026-11-17 追加）

**已查明的关键事实（2026-11-17，Android 实测）**：完整清单与 45 个 sensor 的逐条
记录见 `docs/x2-sensors.md`，整机其它硬件（面板、UFS、相机、音频、无线、指纹等）
见 `docs/x2-hardware.md`，这里只列传感器结论。

| 功能 | 型号 | 厂商 | 总线（来自 vendor `sensor_def_qcomdev.conf`） |
|---|---|---|---|
| 加速度计 / 陀螺仪 | **BMI160** | BOSCH | SSC 配置为 SPI：CS 0 / CS 1，中断 GPIO 117 / 119 |
| 磁力计 | **AK09915**（不是 AK09918） | AKM | 同一条 SPI 总线，CS 1 |
| 环境光 / 接近 | **PA22A** | TXC | I2C bus 3，地址 `0x23`；另有一路同总线 `0x1E` |
| 霍尔（保护套） | BU52053NVX | ROHM | GPIO 124，无总线 |

厂商内核 `mokee_x2_defconfig` 里所有 `CONFIG_SENSORS_*`（BMI160/AKM/MPU 等）全是
`# ... is not set`，设备树里也没有 sensor 节点；Android 侧 `hals.conf` → `sensors.ssc.so`，
即 **Qualcomm Sensor Core（SSC / SLPI，跑在 ADSP 上）**。传感器由 ADSP 枚举，内核完全
不知情。所以主线要自己当总线主控去读芯片。

**步骤**：

1. 在 Debian 里开 `i2c-dev`（SPI 也要 `spidev`），`i2cdetect -y 3` 应能看到 `0x23` / `0x1E`；
   SPI 侧扫 CS0/CS1 读 chip-id（BMI160 的 `0x00` 寄存器返回 `0xD1`，
   AK09915 的 WIA2 `0x01` 返回 `0x31`），确认控制器编号（BLSP SPI 几号要实测）。
2. **内核**：`CONFIG_BMI160`（I2C/SPI 两种前端都编）、`CONFIG_AK09915`（主线是
   `ak09915` IIO 驱动，走 I2C 时地址 0x0C）、`CONFIG_TSL2772` 不适用——PA22A 没有主线
   驱动，先写一个最小 IIO 驱动（读 ALS/prox 两个寄存器组），或先只做 bring-up 验证。
   霍尔直接用 `gpio-keys` 接 GPIO 124。
3. DTS 节点按实测总线写（`compatible` 用主线字符串，中断接 TLMM GPIO）。
4. **用户空间**：读 `/sys/bus/iio/devices/iio:device*/` 下的 `in_accel_*_raw`、
   `in_magn_*_raw`、`in_illuminance_input`、`in_proximity_*`。
5. 验收：`iio:device` 出现、三个轴数值随手翻转而变、`als` 数值随遮光变化、
   `prox` 靠近时跳变、霍尔合盖有按键事件。

## 验收指标

| 维度 | 怎么测 | 目标 |
|---|---|---|
| CPU | `sysbench cpu`、7z 基准 | 与 Android 同频跑分差距 < 10% |
| 存储 | `dd` 顺序 + 4K 随机 | 顺序 ≥ 300 MB/s（UFS 2.0 量级） |
| 网络 | `iperf3` over NCM / WiFi | NCM 已 4.64 MB/s；WiFi 看能不能上 100 Mb/s |
| 图形 | `glmark2` | 需阶段 F 完成后才有意义 |
| 稳定性 | 24 h 连续跑 + 温度 | 不热降频死机，温度 < 45 °C |

## 边界（不做的事）

- 不写 boot / userdata / system 分区，全部走 `fastboot boot` 内存启动
- 不格式化任何分区
- 不碰另一台设备（`38d4fdf`）
- 相机、指纹、通话：沿用之前的取舍，短期不做

## 不等手机就能先干的

阶段 B 的面板驱动和 DTS 改动是纯离线工作，可以现在就写、现在推 CI 编译；
阶段 C 的主机侧代理也可以先实现并用本地回环测通。手机充好电再验证。

## 已拍板的一点

阶段 A 的最终形态是在 Android `/data` 里新增目录 `/data/debian/root`（不建镜像、不格式化、
不动分区表），双系统共存保持不变。Debian 与 Android 不能同时挂载 `/data`；旧基线用
`noload` 规避 UFS 写故障，当前 screen52 的 `rw` + journal replay 已验收。如果你想 `/data`
保持一字节不动，只能退回“纯 RAM + 每次重来”，或等阶段 D 完成后走 OTG U 盘。
