# LeEco Le Max 2 (x2 / LEX820) · Linux 6.19 + Debian 13

把乐视 Le Max 2 跑成一台可用的 Linux 设备。当前项目使用 `6.19.5-msm8996` 内核、
Debian 13 用户空间，并保留 Android 10 作为另一套可启动系统。

## 当前状态

| 能力 | 状态 |
|---|---|
| 内核 | `6.19.5-msm8996+`，39-bit VA，4 核 / 5.7 GB 可用 |
| 用户空间 | Debian 13.7，`apt` / `bash` / SSH 可用 |
| 根文件系统 | userdata 上的目录式根 `/data/debian/root`，可持久化 |
| UFS | 已修复冷启动 `fDeviceInit` 与高负载持续写问题；两次冷启动、Debian/Android/TWRP 三种热重启均通过 |
| 显示 | MDP5 双接口，1440×2560 全屏 console 已点亮 |
| 输入 | Atmel maXTouch 触摸可用；按键映射待补 |
| 网络 | USB NCM + SSH；USB ACM 串口可作为救援通道 |
| Android | 与 Debian 共存，userdata 未重分区 |

## 启动方式

当前阶段由 bootloader 的 `fastboot boot` 内存加载内核、DTB 和 initramfs：

1. `fastboot boot out/boot-va39-debian-screen51-normal-pm.img`
2. initramfs 挂载 `/dev/sda9`，优先进入 `/data/debian/root`
3. 目录根不可用时回退到 initramfs 内的 RAM rootfs
4. USB NCM 提供 `192.168.42.1`，串口与 telnet 作为备用入口

内核与根文件系统均未写入 boot/system 分区。日常免 fastboot 启动仍是后续工作。

## 仓库结构

```text
kernel/                   # 6.19 内核配置、DTS 与补丁
  config-x2-msm8996-va39.aarch64
  patches/                # 显示、UFS、DTS 等补丁
initramfs/                # Debian 启动与救援脚本
scripts/                  # 构建、打包、串口、UFS 调试工具
docs/                     # 硬件清单、bring-up 计划与阶段记录
.github/workflows/        # 当前内核、DTB、面板与 initramfs 的构建检查
```

## 本地构建

宿主机使用 WSL2 Debian，内核源码树放在 `~/linux-msm8996`：

```sh
wsl -d Debian -- bash -lc \
  'cd /mnt/g/LeEco-Max2/leeco-x2-linux && sh scripts/local-build.sh'
```

脚本会还原干净源码树、应用 `kernel/patches/*.patch`、生成 `.config`，并输出：

```text
out/local-build/Image.gz
out/local-build/msm8996-leeco-x2.dtb
```

再使用 `scripts/make-bootimg.py` 把内核、DTB 和 initramfs 打包为 boot 镜像。

## 主要文档

- `docs/plan-debian-bringup.md` — 当前路线与阶段状态
- `docs/ufs-static-analysis.md` — UFS 冷启动和持续写问题的根因与验收矩阵
- `docs/display-bringup-notes.md` — 双 DSI 面板与 MDP5 双接口点亮过程
- `docs/mdp5-dual-intf-plan.md` — 全屏显示的正统实现方案
- `docs/x2-hardware.md` / `docs/x2-sensors.md` — 整机与传感器硬件清单
- `docs/debian-mainline-milestone.md` — Debian 首次进入用户空间的里程碑记录
- `docs/debian-peripherals-gap.md` — 尚缺的外设与驱动
- `docs/fingerprint-qbt1000-analysis.md` — QBT1000 指纹方案分析

## 待完成

- 不依赖 fastboot / TWRP 的常态启动
- WiFi / 蓝牙（QCA6174）
- USB OTG 与按键映射
- GPU / freedreno、音频、摄像头
- 传感器（BMI160、AK09915、PA22A、霍尔）
- 指纹（QBT1000，受 TrustZone/SSC 限制）

## 注意

刷机有风险。修改分区前先备份 `modemst1`、`modemst2`、`fsg`、`persist` 等不可再生数据。
仓库中的 boot 镜像目前仍以内存加载验证为主，不要直接把未验收镜像写入 boot 分区。
