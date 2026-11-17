# 主线内核 + Debian 13 首次在真机进入用户空间

日期：2026-11-17
设备：LeEco Le Max 2（x2 / LEX820，MSM8996 v3 + PMI8996）
内核：`6.19.5-msm8996+`（`va39-build` 分支，`kernel-x2-29` artifact，VA 39 / PA 48）
状态：**成功。已拿到 Debian 13 的 bash 提示符 `root@(none):/#`。**

## 结论先行

主线内核 + Debian 13 的启动链**已经在真机上跑通**，全程 `fastboot boot` 内存启动，
**没有写入任何分区**，Android 的 boot / userdata / system 全部保持原样。

```
fastboot boot out/boot-va39-debian-slim.img
        ↓
内核 6.19.5-msm8996+ 启动 → initramfs (busybox) 作为 PID1
        ↓
建 USB CDC-ACM gadget (0525:a4a7) → Windows 出现 COM12
        ↓
把内嵌的 Debian rootfs tar.xz 解到 tmpfs (1.6 GB)
        ↓
chroot → Debian GNU/Linux 13 (trixie) 13.7
```

## 真机实测数据

| 项目 | 结果 |
|---|---|
| Debian 版本 | `13.7`，`PRETTY_NAME="Debian GNU/Linux 13 (trixie)"` |
| 内核 | `6.19.5-msm8996+` |
| CPU | 4 核，`nproc` = 4 |
| 内存 | 5699 MB total，5398 MB free（tmpfs 根占 196 MB） |
| 根文件系统 | `tmpfs 1.6G，已用 196M，可用 1.4G` |
| 温度 | 32.4 °C（`thermal_zone0`） |
| 用户空间 | 381 个 `/usr/bin` 条目，`dpkg -l` 187 个包 |
| 触屏 | `atmel_mxt_ts 2-004a` 已 probe，`X1439Y2559`，注册为 `input3` |
| systemd | `/usr/lib/systemd/systemd`、`/usr/sbin/init` 均在 |
| apt / bash | 均可用 |

## 三个卡住很久的坑（都已在代码里解决）

### 1. `fastboot boot` 拒绝大于 64 MiB 的镜像

103 MB 的镜像（90 MB 原始 rootfs）返回：

```
Booting FAILED (Status read failed (Too many links))
```

`boot` 分区只有 65,536 KB（64 MiB）。原厂 LK 即使做内存启动，也按这个分区大小
校验 boot.img。所以 **initramfs + 内核的总大小必须压在 64 MiB 以内**。

对策：把 rootfs 从 90 MB 裁到 36.8 MB（`out/slim-rootfs.py`），最终镜像 49.9 MB。

### 2. 裁剪策略（`out/slim-rootfs.py`）

保留 bash、coreutils、systemd、apt/dpkg、共享库、网络与终端相关组件，砍掉串口
控制台上毫无用处的体积大户：

| 目录 | 原大小 | 说明 |
|---|---|---|
| `var/lib/apt/lists` | ~91 MB | 包索引，`apt update` 可重建 |
| `usr/share/locale` | ~55 MB | 翻译 |
| `usr/share/vim` | ~38 MB | 编辑器运行时 |
| `usr/lib/udev/hwdb.d` | ~20 MB | 设备 hwdb，udev 二进制保留 |
| `usr/share/i18n` | ~15 MB | locale 源数据 |
| `usr/share/doc` | ~14 MB | 文档 |
| `usr/share/man` | ~6 MB | man |
| `usr/share/mime` | ~5 MB | MIME 库 |
| `usr/share/bash-completion` | ~1 MB | 补全脚本 |

结果：15,690 条目 / 417 MB → 5,671 条目 / 184 MB，xz 后 36.8 MB。
条目按原样写回（mode / uid / gid / 符号链接目标全部不动）。

### 3. USB ACM 控制台的三个硬件怪癖

这三个都是在这台机器上一层层试出来的，写进 `out/serial-run.py`：

1. **整行一次性写入会被丢弃** —— 必须逐字符发，间隔约 40 ms；
2. **gadget 不主动 flush IN 端点** —— 命令执行完了，输出还挂在端点里，主机必须
   再发一个裸 `\r` 才会把它推出来；
3. **每个提示符都被 `ESC[?2004` 括号粘贴标记包裹** —— 原始读取看起来像"没输出"，
   其实 shell 活得好好的。

第 2 条是最阴的：早期判断"shell 挂了"，其实只是输出没被推出来。

## 产物

| 文件 | 大小 | 说明 |
|---|---|---|
| `out/boot-va39-debian-slim.img` | 49,950,720 B | **可用镜像**，内核 + DTB + 含 Debian rootfs 的 initramfs |
| `out/boot-va39-debian.img` | 103,522,304 B | 全量版，超过 64 MiB 上限，`fastboot boot` 会被拒 |
| `integration/debian13-slim.tar.xz` | 36,860,252 B | 裁剪后 rootfs |
| `integration/debian13-trixie-arm64-rootfs-20261115.tar.xz` | 90,414,192 B | 原始 rootfs（保留） |
| `initramfs/init-debian` | — | 解压 + chroot 的 init 脚本 |
| `out/build-initramfs.py` | — | 能**新增**条目的 newc cpio 重打包器 |
| `out/slim-rootfs.py` | — | rootfs 裁剪器 |
| `out/serial-run.py` | — | 已适配上述三个怪癖的串口执行器 |

## 尚未完成

- 现在是 **tmpfs 内存根**，断电即失。要持久化必须落到 UFS，而这需要动分区。
- systemd 还没作为 PID1 跑起来，现在是 initramfs 里 chroot 出一个 bash。
- 没有网络：`/sys/class/net` 只有 `dummy0` 和 `lo`；RNDIS 在 Windows 11 上
  Problem 28（无驱动）。`sshd` 也没装。
- `apt update` 需要网络，目前不可用。

## 复现步骤

```powershell
# 设备进 fastboot 后
fastboot boot out/boot-va39-debian-slim.img

# 等约 60 秒（解压 417 MB 到 tmpfs）
# Windows 会出现新的 COM 口
python out/serial-run.py COM12 "cat /etc/debian_version"
# -> 13.7
```
