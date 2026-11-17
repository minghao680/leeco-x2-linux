# 计划：把 x2 从「能跑」推到「能用」

基线：主线 6.19 + Debian 13 已在真机运行，USB NCM + SSH 可用（4.64 MB/s）。
下面是把它变成一个日常可用的系统的路线，按"解除阻塞的先后"排，不按"看起来爽"排。

## 现状基线

| 能力 | 状态 |
|---|---|
| 内核 | `6.19.5-msm8996+`，VA39，4 核 / 5.7 GB |
| 用户空间 | Debian 13.7，`apt`/`bash` 可用，187 包 |
| 远程 | SSH over NCM 已验证，sshd 已烤进 `boot-va39-debian-sshd.img`（待首启验证） |
| 根 | **tmpfs，断电即失** |
| 屏幕 | mdss/DSI 就绪，只缺 panel 驱动；背光由 LK 点亮 |
| 电量 | 无电量计，看不到百分比 |
| WiFi / BT | PCIe 关着；BT 节点在，缺固件 |
| GPU | disabled，无硬件合成 |
| 交互 | 触摸对（`atmel_mxt_ts`），无显示 |

## 阶段 A：持久化根（P0，先做）

**为什么先做**：现在每次改点用户空间的东西都要重来一遍，所有后续工作的效率都被
这一步卡着。

1. 在 Debian 里挂 `/dev/sda9`（Android 的 `/data`，ext4、未加密、48 G 空闲），
   先只读验证能读，再读写。
2. 建 `/data/debian/debian.img`，稀疏 ext4，建议 8 GiB（够装 systemd + 编译工具链
   + 桌面基础包）。
3. 改 initramfs：启动时挂 sda9 → `losetup` 挂镜像 → 首次则 `mkfs.ext4` + 解包一次，
   之后直接复用 → chroot 到 loop 根。
4. 保留 RAM 模式作兜底：cmdline 加 `x2.root=ram|disk`，出问题能回到现在这套。
5. 验收：连续重启两次，`/data/debian/debian.img` 里的改动都在；Android 数据无损。

**风险**：Debian 独占挂载 Android 的 `/data` 时，Android 不能同时在跑（本来就是）。
主线上没有 SELinux，写进去的文件没有 label，Android 侧只是看不到一个不认识的目录，
不影响它启动。

**红线**：不碰分区表、不格式化任何分区、不写 boot。只在 `/data` 里新增一个文件。

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

1. `pcie@608000`/`pcie@610000` + PHY 打开，确认 QCA6174 枚举到。
2. `ath10k` + 板级 BDF（`board-2.bin` / `bus/pci/...`），从 Android `/vendor/firmware`
   或 `/system/etc/firmware` 取对应文件。
3. `hci_qca` + BT 固件（同源）。
4. 验收：`iw` 能扫到 AP，`iperf3` 跑吞吐，和 NCM 的 4.6 MB/s 对比。

## 阶段 F：GPU 与媒体（P3）

1. `gpu@b00000` + `iommu@d00000/d40000/da0000` 打开，freedreno（Adreno 530）。
2. 有了 GPU 才谈得上"接近安卓的流畅度"；之前所有界面合成都是软件光栅。
3. 再往后是 venus 视频解码、camss 相机、modem 通话——工程量最大，最后碰。

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

## 需要你确认的一点

阶段 A 会在 Android 的 `/data` 里新增 `/data/debian/debian.img` 一个文件（8 GiB 稀疏，
实际占用按写入增长）。不改分区、不清数据，但确实动了 Android 的文件系统。
如果你希望 `/data` 保持一字节不动，那就只能退回"纯 RAM + 每次重来"，或者走 OTG U 盘
（依赖阶段 D 先完成）。
