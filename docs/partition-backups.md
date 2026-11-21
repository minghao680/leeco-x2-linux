# LeEco x2 分区备份清单

## 最新备份位置

主备份：

```text
G:\LeEco-Max2\backup\x2-partitions-20261112\pmos-backup
```

旧备份：

```text
G:\LeEco-Max2\backup\x2-partitions-20261102\pmos-backup
```

备份脚本：

```text
G:\LeEco-Max2\backup\dump-partitions.ps1
```

## 关键镜像与校验

### vendor.img

```text
路径: G:\LeEco-Max2\backup\x2-partitions-20261112\pmos-backup\vendor.img
大小: 619.4 MiB
类型: ext4
LABEL: vendor
UUID: 4064ea63-a2f6-5452-b75b-10834a0e8f22
当前分区: /dev/sde34
验证: 备份 UUID 与当前 vendor 分区一致
```

`vendor` 分区内包含 Adreno、Venus、DSP、蓝牙等固件源。恢复时可直接写回原分区；如果不再保留 Android，也可以先备份 `vendor/firmware` 到 Debian rootfs 后再格式化。

### system.img

```text
路径: G:\LeEco-Max2\backup\x2-partitions-20261112\pmos-backup\system.img
大小: 4.0 GiB
类型: ext4
LABEL: /
UUID: 42708d19-d243-52f5-af2c-e54c7e5dbcba
当前分区: /dev/sde19
验证: 备份 UUID 与当前 system 分区一致
```

### boot.img / recovery.img

```text
boot.img     64 MiB   Android boot image
recovery.img 64 MiB   Android recovery image
```

这两个是 Android 原厂启动备份，不是当前 Debian boot。当前 Debian boot 镜像为：

```text
G:\LeEco-Max2\leeco-x2-linux\out\boot-x2-debian-systemd3-gpu.img
```

### 其他已备份分区

`pmos-backup` 目录还包含：

```text
persist.img       32 MiB
modem.img        110 MiB
modemst1.img       2 MiB
modemst2.img       2 MiB
dsp.img           16 MiB
bluetooth.img      1 MiB
tz.img / tzbak.img
xbl.img / xblbak.img
aboot.img / abootbak.img
spash.img        100 MiB
```

注意：`persist`、`modemst1/2`、`xbl`、`aboot`、`tz`、`devcfg` 不要格式化，它们是校准、基带和引导相关分区。

### 数据备份

```text
G:\LeEco-Max2\backup\x2-partitions-20261112\data-all.7z  ~1.2 GiB
G:\LeEco-Max2\backup\x2-partitions-20261112\data-snap\  tar 快照
```

这是 Android `/data` 的归档/快照，不是 raw `userdata.img`，也不包含当前 Debian rootfs。当前 Debian rootfs 位于：

```text
/dev/sda9[/debian/root]
```

已用约 8.0 GiB / 53 GiB。格式化 `userdata` 前必须单独备份 Debian rootfs。

## 当前安全顺序

1. `boot`：不要格式化，直接用 `fastboot flash boot` 写入 Linux boot 镜像。
2. `system`：已有完整 `system.img` 备份，可格式化或保留。
3. `vendor`：已有完整 `vendor.img` 备份，可格式化；建议先把 `vendor/firmware` 复制到 rootfs。
4. `userdata`：最后处理。当前 Debian rootfs 就在上面，必须先备份 rootfs，再格式化、重建 ext4、还原。

## 还原命令参考

```bash
fastboot flash vendor G:\LeEco-Max2\backup\x2-partitions-20261112\pmos-backup\vendor.img
fastboot flash system G:\LeEco-Max2\backup\x2-partitions-20261112\pmos-backup\system.img
fastboot flash boot G:\LeEco-Max2\backup\x2-partitions-20261112\pmos-backup\boot.img
```

## Debian 13 rootfs 归档

一开始下载的官方最小 rootfs 还在：

```text
G:\LeEco-Max2\integration\debian13-trixie-arm64-rootfs-20261115.tar.xz
```

校验信息：

```text
发行版: Debian GNU/Linux 13 (trixie)
版本: 13.7
架构: arm64
压缩大小: 86.2 MiB
解包大小: 443.6 MiB
生成方式: distrobuilder
SHA256: ec8631af1817716d8ffa0f6cee115b7f43af1f23e3da2c48ce0415d7d0e35e5d
```

这说明可以重新部署一个干净的 Debian 13.7 rootfs。但它是 **minimal rootfs**，不包含当前系统里的这些内容：

```text
GNOME / x2-gnome.service
WiFi / 蓝牙固件与配置
SSH 账号与密钥
NTP、Asia/Shanghai 时区
阿里云 apt 源
Adreno/GPU 相关 firmware
x2 启动脚本与 systemd 配置
```

所以它可以作为干净基线重新部署，但不能直接覆盖当前 8 GiB 的 GNOME rootfs。当前 rootfs 如果要保留，仍应先单独打包备份。

