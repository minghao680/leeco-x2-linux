# x2 固件与文件缺口审计（2026-11-19）

本文只讨论“驱动真正会向内核请求的文件”，以及换到纯 Debian 后不能丢的本机持久资料。
厂商 blob 不进入 Git 仓库，统一生成在 `out/x2-firmware/`（`out/` 已被 `.gitignore` 忽略）。

## 1. 结论

真正在主线启动日志里造成 `Direct firmware load ... failed with error -2` 的只有：

| 请求 | 原因 | 处理 |
|---|---|---|
| `qcom/a530_pm4.fw`、`a530_pfp.fw`、`a530v3_gpmu.fw2`（兼容旧名 `a530_gpmu.fw2`） | Adreno 在 init 之前 probe，而全局 `firmware_class.path` 到挂 root 之后才设置；rootfs 里的文件当时不可见。实际驱动请求的是 `a530v3_gpmu.fw2` | 嵌入 initramfs，同时部署到 rootfs |
| `qcom/msm8996/leeco-x2/a530_zap.*` | system9 的 initramfs 错放成 `qcom/a530_zap.*`，DTS 实际请求板级路径 | 按 DTS 路径补齐 mdt/b00/b01/b02 |
| `adsp.mdt`（及 `adsp.bNN`） | `adsp_pil` 没覆盖 `firmware-name`，驱动请求 plain `adsp.mdt`；同时 firmware path 只在 `wifi_up()` 临时设置，udev 自动加载时已错过时机 | init 在 root 挂好后立即全局设置 `firmware_class.path`；ADSP 同时嵌入 boot 和 rootfs |
| `maxtouch.cfg` | 内核的可选触摸配置请求；vendor/system 中都没有有效文件 | 不伪造、不阻塞。当前 `atmel_mxt_ts` 无该文件也能工作 |

`qca/rampatch_00440302.bin`、`qca/nvm_00440302.bin` 和 QCA6174 BDF 在现有 rootfs
中已经可用，不属于缺口。**不要**用 vendor 的 `btfw32.tlv` / `btnv32.bin` 直接覆盖
当前可工作的 `qca/` 文件，它们不是同一套加载路径。

## 2. 两层固件包

`scripts/extract-x2-firmware.ps1` 从本地分区备份生成：

```text
out/x2-firmware/
├── stage/lib/firmware/          # 当前主线实际消费，可原样铺到 /
├── x2-firmware-rootfs.tar.gz    # stage 的部署包
├── manifest.tsv                 # 37 个文件的 SHA-256 / 字节数 / 路径
└── reference/                   # 其余厂商资料，只归档，不铺进 /lib/firmware
```

`stage/` 内容：

| 路径 | 来源 | 消费方 | 说明 |
|---|---|---|---|
| `qcom/a530_pm4.fw`、`a530_pfp.fw`、`a530_gpmu.fw2` | vendor `/firmware` | `msm`/Adreno | GPU 命令流与 GPMU |
| `qcom/msm8996/leeco-x2/a530_zap.mdt` + `b00/b01/b02` | vendor `/firmware` | `qcom_q6v5_pas` + zap shader | x2 DTS 的板级路径 |
| `adsp.mdt` + `adsp.b00…b09`（无 b07） | modem FAT `image/` | `qcom_q6v5_pas` ADSP | 音频/传感器协处理器的固件底座 |
| `slpi.mdt` + `slpi.b00…b16` | modem FAT `image/` | SLPI remoteproc（未启用） | **传感器侧唯一真实固件**；只有走 SSC/QRTR 才需要 |
| `ath10k/QCA6174/hw3.0/board.bin`、`board-pci-0000:01:00.0.bin` | Android `bdwlan30.bin` | ath10k | 两文件名内容相同；后者是 PCI 路径专用名 |
| `tfa98xx.cnt` | vendor `/firmware` | TFA9890 驱动（尚未移植） | SmartPA 校准/参数，先备好 |

`reference/` 内容：

| 目录 | 关键文件 | 为什么保留 |
|---|---|---|
| `vendor/firmware/` | `a530v1_*`、`a530v3_*`、`max_plus/a530_zap*`、`cppf.*` + `cpp_firmware_v1_10_0.fw`、`cyccg.cybin` + `cyccg_table.cybin`、`sii6400_wihd_mhl.fw`、`tfa98xx.cnt`、`wlan/qca_cld/*` | GPU 旧变体、相机后处理、CCG2、MHL、音频和 WLAN 配置；多数无主线驱动 |
| `modem/image/` | `modem.mdt/bNN`、`mba.mbn`、`venus.mdt/bNN`、`fingerpr.*`、`cmnlib*`、`widevine.*`、`qpay.*`、`alipayta.*`、`fidotap.*`、`mdtp.*`、`securemm.*`、`cppf.*`、`cpe_9335.*`、`*wlan30*`、`modem_pr/mcfg/*` | modem/Venus/安全应用/运营商配置的原始集合；不是当前内核可直接加载的 Linux 固件 |
| `bluetooth/image/` | `btfw32.tlv`、`btnv32.bin`、`btnv32.b15` | Android 的 QCA BT rampatch/NVM 包装；当前主线使用 linux-firmware 的 `qca/` 文件 |
| `persist/` | `sensors/sns.reg`、`sensors/sensors_settings`、`sensors/pressure_sensor`、`bluetooth/.bt_nv.bin`、`wlan_mac.bin` | 本机校准与出厂地址，换系统后不可再生 |
| `dsp/` | `fastrpc_shell_0`、音频 codec `.so` 等 | Android ADSP 用户态库参考，不是内核固件 |

`persist/` 含设备唯一 MAC/蓝牙地址，**只保留在 `out/`，不要提交 GitHub**。
`persist/data/fingerprint` 是私人指纹模板，未复制、未打包、未分析。

## 3. 其他硬件的固件情况

| 硬件 | 型号 | 是否存在独立固件 | 当前结论 |
|---|---|---|---|
| 屏幕 | Sharp QHD 双 DSI | 无 | 初始化序列应写进 panel 驱动；vendor 没有单独面板固件 |
| 触摸 | Atmel maXTouch T100 | 无（仅可选 `maxtouch.cfg`） | 该 cfg 在 vendor/system 均不存在；触摸已可用，不伪造 |
| 存储 | Samsung KLUCG4J1CB-B0B1 UFS 2.0 | 无用户可加载文件 | 由 `ufshcd-qcom` 管控制器，固件不可分发 |
| 后置相机 | Sony IMX230（LG 模组） | 无内核固件 | `chromatix.xml` 是 Android 用户空间调参，不是 firmware；主线需 camss + sensor 驱动 |
| 前置相机 | OmniVision OV8865（OFILM） | 无内核固件 | 同上 |
| 相机后处理 | CPPF | `cppf.mdt/bNN`、`cpp_firmware_v1_10_0.fw` | 已归档；camss/CPPF 未启用，不部署 |
| 扬声器功放 | NXP TFA9890 | `tfa98xx.cnt` | 已进 stage；还缺主线驱动 |
| 音频编解码器 | WCD9335 | 无独立文件，依赖 ADSP | ADSP 固件已补齐；WCD9335 主线驱动存在 |
| 麦克风/听筒 | WCD9335 直连 | 无 | 无独立固件，待音频链路整体调试 |
| WiFi/蓝牙 | QCA6174 | BDF + BT rampatch/NVM | BDF 已 stage；BT 当前使用可工作的 `qca/` 文件 |
| 指纹 | Qualcomm QBT1000 | TrustZone 应用 `fingerpr.mdt/bNN` | 已归档；没有 QSEE/QBT1000/SSC 主线链路，不能当普通 firmware 加载 |
| 传感器 | BMI160 / AK09915 / PA22A / BU52061NVX | 芯片无固件；SLPI 是协处理器固件 | 直接 IIO 方案不依赖 SLPI；SLPI 仍已归档，供未来 SSC 路线 |
| 充电 CC 逻辑 | Cypress CCG2 | `cyccg.cybin`、`cyccg_table.cybin` | 已归档；无主线驱动，USB 仍以 peripheral 为主 |
| 充电 IC | SMB1351 | 无 | 配置在驱动/DTS，不走 firmware |
| 电量计/PMIC | PMI8994 | 无 | `qcom-battery` 已可用 |
| 震动 | TI DRV2604L | 无 | 波形由驱动生成，无厂商固件 |
| GNSS | MSM8996 集成 | 无独立文件 | 依赖 modem/ADSP 栈，暂未启用 |
| MHL | SiI6400 | `sii6400_wihd_mhl.fw` | 已归档；不是当前 USB 功能路径 |
| 红外/LED/按键 | SoC/PMIC/GPIO | 无 | 纯 DTS/驱动 |

## 4. 启动脚本修复

`initramfs/init-debian-systemd` 原先把 `firmware_class.path` 只放在 `wifi_up()` 里。
这会让 WiFi 之前和之后由 udev 自动加载的模块都继续从 initramfs 找固件。

现在在 root 选定之后、任何手动 `modprobe` 和 systemd/udev 启动之前设置 rootfs 路径：

```sh
printf '%s' "$ROOT/lib/firmware" > /sys/module/firmware_class/parameters/path
```

但系统用的是 `chroot`，内核固件加载器在 systemd 阶段可能仍按 initramfs 的根解析
绝对路径。因此在 exec systemd 前再做一次交接：

```sh
mount --bind "$ROOT/lib/firmware" /lib/firmware
printf '/lib/firmware' > /sys/module/firmware_class/parameters/path
```

这样 `/lib/firmware` 在 chroot 前（initramfs 根上的绑定）和 chroot 后（Debian 根）
指向同一批文件。GPU 是 built-in 且在 init 之前 probe，仍然必须把
zap/pm4/pfp/gpmu 嵌入 initramfs；其余模块可以在 rootfs 挂载后从 `/lib/firmware` 加载。

## 5. 产物与验证

| 产物 | 大小 / SHA-256 |
|---|---|
| `out/x2-firmware/x2-firmware-rootfs.tar.gz` | 6,647,223 B，`fce9a0d008269f29b8f4bc54ed9f913b5c515c14aaa4ed7edab0cd81e59de06c` |
| `out/x2-initramfs-debian-systemd12.gz` | 44,700,952 B，`8ce3fd13cac021d9a43f3005a4b845320dd49d76907f63fc3440efc23fb49cd5` |
| `out/boot-x2-debian-systemd12-firmware-normtfs.img` | 56,479,744 B，`63f308e8fdedcdc9d8167a808292e4ab98e8914441eff52a11e4b8cacaa6f63c` |
| `out/x2-initramfs-debian-systemd13-gpmu.gz` | 44,706,672 B，`2bc781621ddd8a1f4d73d595d6d59297e6f4bca69203afb73e637c1e2f2fcbff` |
| `out/boot-x2-debian-systemd13-gpmu.img` | 56,483,840 B，`167e3b0047eb9e8c0f3a46ef6f6636fb18eefbf030d06a4d3755d420a0bae55d` |

重建与部署：

```powershell
pwsh -File scripts/extract-x2-firmware.ps1
```

```sh
sudo ./scripts/install-x2-firmware.sh /path/to/x2-firmware
```

通过 WiFi SSH 部署时，整个 bundle 只有约 6.4 MB：

```powershell
scp -r "G:\LeEco-Max2\leeco-x2-linux\out\x2-firmware" root@192.168.1.173:/tmp/
```

```sh
ssh root@192.168.1.173 "sh /tmp/x2-firmware/install.sh /tmp/x2-firmware"
```

临时启动验证：

```powershell
& "C:\Program Files\UotanToolbox\Bin\platform-tools\fastboot.exe" boot "G:\LeEco-Max2\leeco-x2-linux\out\boot-x2-debian-systemd12-firmware-normtfs.img"
```

验收时重点看：

```sh
dmesg | grep -E 'Direct firmware load|qcom_q6v5_pas|a530|adsp|slpi|tfa98xx'
ls -l /lib/firmware/adsp.mdt /lib/firmware/slpi.mdt /lib/firmware/qcom/a530v3_gpmu.fw2
sha256sum -c <(awk -F '\t' 'NR>1 {print $1"  /"$3}' manifest.tsv)
```

**部署路径说明**：Debian 13 是 usr-merged，`/lib` 是 `usr/lib` 的符号链接。
固件包现在按 `usr/lib/firmware/...` 打包，安装器不会再用 `./lib` 目录项覆盖 `/lib`。
如果旧脚本仍然把 `/lib` 变成普通目录，会导致 `/lib/ld-linux-aarch64.so.1`
消失；修复方式是恢复 `lib -> usr/lib` 符号链接并把固件合并到 `usr/lib/firmware`。

## 6. system12 实机结果（2026-11-19）

- 启动：systemd 为 PID1，root 为 `/data/debian/root`；`systemctl --failed` 初次为 0，运行到 1278 s 未见 CPU2 hard LOCKUP、RCU stall 或 SMMU deadlock；`rmtfs_mem` 已按 cmdline 黑名单。
- ADSP：部署前 `adsp.mdt` 报 `-2`；把 bundle 安装到 rootfs 后执行 `echo start > /sys/class/remoteproc/remoteproc0/state`，日志出现 `Booting fw image adsp.mdt` 和 `remote processor adsp is now up`，状态为 `running`。
- GPU：`qcom/a530_pm4.fw` / `a530_pfp.fw` 已加载；但驱动请求的 `qcom/a530v3_gpmu.fw2` 缺失，报 `-2`。已补入 rootfs 和 system13 initramfs。system13 实机已确认 `a530v3_gpmu.fw2` 加载成功；随后卡在 `a5xx_me_init()` 的 ringbuffer drain 超时（`rptr/wptr = 0/C`，`gpu hw init failed: -22`），改用 `kernel/patches/0024-a5xx-reset-on-pm-resume.patch` 在 resume 时软复位 GPU，待 `systemd14-reset` 镜像验证。
- 显示：`mdp5_irq_error 0x14000000` 和 `msm: dual display attempt 3..6: -11` 仍存在；`fb0: sys_imageblit: framebuffer is not in virtual address space` 说明 fbcon 仍未正常绘制，屏幕实际状态待确认。
- WiFi：QCA6174 在 5 GHz、VHT80、2×2 下协商到 866.7 Mbit/s；systemd/udev 在 26.96 s 把 `wlan0` 重命名为 `wlp1s0`，但 wpa_supplicant/dhcpcd 仍持有 IP `192.168.1.173/24`。NCM 的 `192.168.42.1:22` 可用；从当前 Windows 主机访问 `192.168.1.173:22` 失败，需区分主机防火墙/路由与 sshd 监听问题。
- 电池：测试期间从 52% 降到 48%，状态 `Charging`；本次测试结束时仍接着电脑。
