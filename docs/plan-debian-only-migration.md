# 计划：放弃 Android，把 boot/system/userdata 交给 Debian

状态：**仅规划，未执行**（2026-11-19）。当前仍是 Android + Debian 双系统，
Debian 根在 `/data/debian/root`，所有分区保持原样。

## 1. 结论

最终方向确定为 **原生 Debian 单系统**，但迁移必须等外设和稳定性验收完成后再做。
过渡期继续保留 Android，原因不是“舍不得”，而是它现在仍承担：

- 救砖/回滚：原厂 `boot`、`system`、`userdata` 备份可恢复；
- 固件来源：`vendor`、`modem`、`persist` 里的 GPU/ADSP/WiFi/BT/传感器校准；
- 对照环境：Android 下可继续核对 GPIO、总线、面板、充电等厂商行为。

**现在迁移会把“驱动没修好”和“分区/启动链改动”混在一起，排障成本远高于收益。**

## 2. 现有分区事实

尺寸来自本机备份和 `/proc/partitions`，设备名以 Debian 下 `lsblk`/`blkid`
实测为准，不要直接照搬 Android 的 `/dev/block/...` 编号。

| 分区 | 大小 | 当前用途 | 迁移后备注 |
|---|---:|---|---|
| `boot` | 64 MiB | Android boot image 槽 | 继续作为 LK 启动槽，**不是 Debian `/boot` 文件系统** |
| `recovery` | 64 MiB | Android recovery / TWRP | 保留为救援入口 |
| `system` | 4.0 GiB | Android system | 迁移后做 Debian `/var` |
| `userdata` | 约 53 GiB（56,776,396 KB） | Android `/data` + 当前 Debian 根 `/data/debian/root` | 迁移后做 Debian `/` 根分区 |
| `vendor` | 619.4 MiB | Android vendor，含固件 | 保留或先把所需文件迁到 rootfs |
| `persist` | 32 MiB | 传感器/蓝牙/WiFi 校准 | 不要格式化 |
| `modem` | 110 MiB | 基带/ADSP/SLPI/安全应用 | 不要格式化 |
| `cache` | 256 MiB | Android cache | 可不使用，或做临时缓存 |

当前 Debian rootfs 已用约 **8.0 GiB / 53 GiB**；`system` 只有 4 GiB，
**不能把当前 rootfs 原样放进 `system` 当 `/`**。

## 3. 最终分区布局

推荐方案：**boot 作 LK 启动槽，userdata 作根，system 作 `/var`，recovery 保留。**

| 分区 | 最终角色 | 文件系统 / 内容 |
|---|---|---|
| `boot` | LK 启动槽 | Linux kernel + DTB + 极小 initramfs（GPU/zap 固件）；保持 Android boot image 格式，镜像 < 64 MiB |
| `userdata` | Debian `/` | ext4，根直接放在分区根目录；`/home`、`/usr`、`/var/lib` 等都在这里 |
| `system` | Debian `/var` | ext4，挂载到 `/var`；放日志、apt cache、容器/服务数据 |
| `recovery` | 救援 | TWRP 或等价救援镜像，保留 |
| `vendor` / `persist` / `modem` | 保留 | 固件/校准来源；需要的内容先复制到 rootfs，不随迁移格式化 |

不推荐把 `system` 当 `/`：4 GiB 对 GNOME/桌面环境余量太小；也不建议现在把
`system + userdata` 合并或做 LVM，等单系统稳定后再作为独立高风险阶段评估。

## 4. 最终启动链

目标形态尽量接近原生 Debian，不再使用当前的 chroot init：

```text
LK / aboot
  → boot 分区：Android boot image
      kernel + DTB + 极小 initramfs
  → 内核 initcalls（GPU 在挂根前 probe，需要早固件）
  → 挂 userdata 为 /
  → exec /sbin/init
  → systemd（PID1）
```

要点：

1. `boot` 分区仍是 LK 能识别的 Android boot image，不能格式化成 ext4。
   Debian 的 `/boot` 目录可以放在根分区里，但 LK 不会读它。
2. initramfs 可以做到极小：只放 GPU（`a530_pm4/pfp/gpmu`）和板级 zap
   等必须在挂根前加载的固件；ADSP、QCA BDF、TFA 等可以在 systemd/udev
   阶段从 rootfs `/lib/firmware` 加载。
3. initramfs **可以不放 `/init`**：内核先跑 initcalls，再挂 `root=`，
   最后执行 `/sbin/init`。这样就不需要自定义 init 脚本长期驻留。
4. 根分区建议用 `root=PARTUUID=... rootwait rw`，不要依赖 `/dev/sda9`
   这类可能随枚举变化的设备名；`/var` 用 `LABEL=x2-var` 或 PARTUUID 挂载。
5. `system` 格式化为 ext4 后设置固定 label；`userdata` 格式化为 ext4，
   根目录直接放 Debian rootfs，不再套 `debian/root` 子目录。
6. 迁移后 systemd 负责 WiFi/BT/SSH/NTP 等服务；不要再把
   `wpa_supplicant`、`bluetoothd`、`sshd` 写进 initramfs。

## 5. 迁移门槛

以下项目未全部通过前，不执行分区迁移：

- [ ] 显示、GPU、GNOME/Wayland 能稳定进桌面，硬件渲染可用。
- [ ] WiFi、蓝牙开机自连；SSH 由 systemd 自启；NTP/时区正常。
- [ ] USB OTG、NCM/ACM、按键、触摸、传感器、音频、电量/充电都可用。
- [ ] 冷启动、热重启、断电、软重启挂起问题均通过。
- [ ] CPU/GPU/IO/网络性能达到验收指标，24 h 稳定性通过。
- [ ] Debian rootfs 不依赖 Android 的 `/vendor`、`/data/debian` 路径。
- [ ] 官方 Debian 13 rootfs 可重新部署，配置可脚本化/版本化。
- [ ] 回滚路径已验证：`fastboot boot` 救援镜像、TWRP、分区镜像恢复。

## 6. 迁移步骤（未来执行）

1. **全量备份并验证恢复**：`boot`、`recovery`、`system`、`userdata`、
   `vendor`、`persist`、`modem`；确认至少一种恢复方式在真机上可用。
2. **重建干净 rootfs**：用官方 Debian 13 rootfs 重新部署，把当前 WiFi/BT/
   GPU/SSH/NTP 配置写成脚本和 systemd units，不原样搬 8 GiB 旧树。
3. **先做原生启动演练**：在不破坏 Android 的前提下，尽量用临时 root
   （USB OTG / 备用介质 / 可恢复分区）验证 `root=PARTUUID=...` 直接启动
   systemd；确认 fstab、`/var`、`/run`、cgroup2 正常。
4. **格式化 `system` 为 ext4**，label 设为 `x2-var`；先挂到临时目录验证。
5. **备份当前 Debian rootfs**，再格式化 `userdata` 为 ext4，把新 rootfs
   解包到分区根目录。
6. **刷写 `boot`**：kernel + DTB + 只含早固件的极小 initramfs；cmdline 使用
   `root=PARTUUID=... rootwait rw`。
7. **首次启动验收**：串口/kmsg 抓完整启动链；检查 `findmnt /`、
   `findmnt /var`、`systemd-analyze`、`systemctl --failed`。
8. **保留 Android 备份 1–2 周**，确认单系统稳定后再删除旧镜像。

## 7. 回滚

- `boot` 出问题：`fastboot boot` 救援镜像，或恢复原厂 `boot.img`。
- `system`/`userdata` 出问题：TWRP 或 fastboot 写回备份镜像。
- 不删除 `vendor`/`persist`/`modem` 备份；不覆盖 `aboot`/`xbl`/`tz`。
- 不在首次迁移当天删除 Android 备份。

## 8. 待实测确认

- Debian 下 `system` 分区的实际块设备名、可写性和 ext4 格式化结果。
- `userdata` 的 PARTUUID、4K 对齐和 ext4 参数。
- 极小 initramfs 的最终大小；`boot` 镜像必须 < 64 MiB。
- `system` 做 `/var` 后 journald、apt、容器数据的容量策略。
- 迁移后 GPU 固件在 initramfs、ADSP/QCA 固件在 rootfs 的加载顺序。
- 是否需要保留 `cache` 做临时缓存，或完全闲置。

## 9. 非目标

- 现在不改 GPT、不合并 `system + userdata`、不做 LVM。
- 现在不替换 LK/aboot，不引入 GRUB/UEFI。
- 现在不格式化任何分区，不删除 Android。
- 不把 `persist`/`modem` 里的校准和基带数据当普通文件处理。
