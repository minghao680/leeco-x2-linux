# Debian 主线内核：外设缺口清单

来源：`out/kernel-x2-29/msm8996-leeco-x2.dtb` 用 `dtc -I dtb -O dts` 反编译成
`out/x2.dts`（614 个节点，38 个 `status = "disabled"`），以及
`out/kernel-x2-29/Image.gz.config.txt`。

结论先说：**黑屏不是 mdss 没驱动，是三件独立的事同时不成立**。

## 屏幕

| 证据 | 状态 |
|---|---|
| `display-subsystem@900000`（mdss）、`dsi@994000`、`dsi@996000`、`phy@994400` | 都 `okay`，双 DSI 链路齐全 |
| `panel@0` 的 `compatible = "sharp,leeco-x2-panel"` | 这个字符串没有任何驱动匹配 |
| `CONFIG_DRM_PANEL_SIMPLE` | **not set** |
| `CONFIG_DRM_PANEL_SONY_SYNAPTICS_JDI` | **not set** |
| `soc@0/spmi@400f000/pmic@3/wled@d800`（背光） | **disabled** |
| `CONFIG_BACKLIGHT_QCOM_WLED` | =y，驱动在，节点关着 |

### 面板真身（Android 侧 cmdline 确证）

```
mdss_mdp.panel=1:dsi:0:qcom,mdss_dsi_sharp_qhd_dualdsi_cmd_le_x2:\
               1:qcom,mdss_dsi_sharp_qhd_dualdsi_cmd_le_x2:cfg:split_dsi
```

对应厂商源码 `arch/arm/boot/dts/qcom/leeco/dsi-panel-sharp-dualmipi-cmd-le_x2_na-dvt1.dtsi`，
参数完整拿到：

| 项 | 值 |
|---|---|
| 分辨率 | **720 x 2560 每条 DSI**（双链路合成 1440 x 2560） |
| panel-type | `dsi_video_mode`（文件名虽叫 cmd，实际是 **video 模式**） |
| 帧率 / bpp | 60 / 24 |
| hfp / hbp / hpw | 154 / 100 / 10 |
| vfp / vbp / vpw | 8 / 7 / 1 |
| lanes | 4（lane-0..3 全开） |
| split | `pingpong-split` |
| reset | `<1 10>, <0 10>, <1 10>` |
| on-command | `FF 10`, `FB 01`, `BA 03`, `E5 01`, `35 00`, `BB 03`, `B0 03`, `3B 03 08 08 64 9A`, `11`(delay 0x20), `29`(delay 0x78) |
| off-command | `28 00`, `10 00` |

这一点很关键：**是 video mode，主线 msm DSI 原生支持**，不必啃 cmd-mode 那条路。
缺的只是一个绑定 `sharp,leeco-x2-panel` 的驱动，把上表喂进去。工程量从"未知"变成
"写一个 200 行的 panel driver"。

### 运行时复核（Android 侧实测，不是看文件）

节点名里的 "cmd" 是历史命名遗留，实际跑的是 video：

| 检查 | 结果 |
|---|---|
| `/proc/device-tree/soc/qcom,mdss_mdp@900000/qcom,mdss_dsi_sharp_qhd_dualdsi_cmd_le_x2/qcom,mdss-dsi-panel-type` | `dsi_video_mode` |
| 驱动判定逻辑 `mdss_dsi_panel.c:2763` | 默认 `DSI_VIDEO_MODE`，**只有**字符串等于 `dsi_cmd_mode` 才切 CMD |
| `/sys/kernel/debug/mdss_panel_fb0/intf0/{xres,yres}` | `720` / `2560` |
| `intf1/{xres,yres}` | `720` / `2560`（双链路同时在线） |
| `clk_rate` | 912,522,240（4 lane × 912.5 Mbps/链路，正好压下 720×2560@60@24bpp 加消隐） |
| `te_tear_check_en` / `te_refx100` | `1` / `6000`（60.00 Hz） |

`te_tear_check_en = 1` 一度看着像 cmd mode，但 tear-check 只是 TE 同步/防撕列的
可选配置，不参与 MIPI mode 选择；mode 只由 `qcom,mdss-dsi-panel-type` 决定。

背光：`wled@d800` 关着意味着 Linux 无法控制亮度，但 fastboot boot 时 LK 会把背光
点亮并留在那个状态，所以"屏幕是黑的但看着有背光"——不是面板没供电，是没有图像数据。

## GPU

`soc@0/gpu@b00000` **disabled**，`iommu@d00000/d40000/da0000` 也 disabled。
Adreno 530 的 freedreno 完全没接上，所以没有硬件合成、没有 GL。CPU 侧跑分可以
接近安卓，但凡涉及界面合成、视频、浏览器的场景都会明显慢。

## 电池与充电

| 节点 | 状态 |
|---|---|
| `pmic@2/charger@1000` | **disabled** |
| `pmic@2/fuel-gauge@4000` | **disabled** |

没有电量计就没有百分比、没有充电状态。设备现在只会突然没电——这次"没电了"正是
这个缺口的直接体现。优先级应该排在屏幕之前：它决定还能不能方便地继续折腾。

## USB OTG

`usb@6af8800`（USB1，带 SS PHY）是 `okay`，但其中 `dr_mode = "peripheral"`
写死。所以这个口只能当设备（gadget），插 U 盘、键鼠都不行。
`usb@76f8800`（USB0，只有 HS）整个 disabled。

要主机模式得改 `dr_mode = "otg"` 并配 role switch / extcon；但注意同一个口
一旦转 host，NCM + ACM 这条命脉就断了，所以 OTG 和远程控制是互斥的，做实验时
必须留串口或让用户手动进 fastboot 兜底。

## 按键

`gpio-keys` 存在，含 `vol-up`；`pwrkey` 走 `qcom,pm8941-pwrkey`。
基本键位有，缺的（vol-down 等）需要逐个核对厂商 dtsi。

## WiFi / 蓝牙

- 蓝牙：`bluetooth { compatible = "qcom,qca6174-bt"; }` 节点已在，缺固件与
  `hci_qca` 链路。
- WiFi：QCA6174 走 **PCIe**，而 `pcie@608000` 与 `pcie@610000` 都是
  **disabled**。必须先把 PCIe 控制器和 PHY 打开，再上 ath10k + 板级 BDF 固件。
  这也解释了 `/sys/class/net` 里只有 `dummy0` 和 `lo`。

## 相机 / 视频 / 通话

`camss@a34000`、`video-codec@c00000`（venus）、
`remoteproc@1c00000`（modem）、`remoteproc@2080000` 全部 disabled。
这三块是最大的工程量，短期不碰。

## rootfs 放哪（已实测确定）

Android 侧实测（`adb shell`）：

```
/dev/block/sda9 on /data type ext4 (rw,seclabel,nosuid,nodev,noatime,
                                    noauto_da_alloc,data=ordered)
getprop ro.crypto.state = unencrypted
df -h /data -> 53G 总量，4.5G 已用，48G 可用
```

**userdata 是 ext4 且完全没有加密。** 所以 TWRP 解密那套根本不需要。

同时 `sde19` 查出来是 `system -> /dev/block/sde19`，**不是闲置分区**，
原先"拿 sde19 当根"的想法作废（幸好先查了没盲写）。

结论：把根文件系统做成 `/data` 里的一个镜像文件，loop 挂载：

```
/data/debian/debian.img   稀疏 ext4，建议 8-16 GiB
```

- 不碰任何分区表，不格式化，Android 数据一行不动，只是多一个文件
- 需要的内核能力全都已具备：`CONFIG_EXT4_FS=y`、`CONFIG_BLK_DEV_LOOP=y`
- 首次启动时在 initramfs 里 `mkfs.ext4` 并解包一次，之后每次直接挂载复用
- 因为 Debian 独占运行时 Android 不在跑，独占挂载 `/data` 没有并发风险

这比 sde19 方案好：容量大（48 G 可用）、无需授权清数据、回滚只需删一个文件。

## 建议的顺序

| 优先级 | 事项 | 成本 |
|---|---|---|
| P0 | `/data/debian/debian.img` → 持久化根（loop + ext4） | 低，解除"每次重新 boot"的枷锁 |
| P1 | 电量计 + 充电状态 | 低 |
| P1 | `panel-leeco-x2` 驱动（video mode，参数已齐）+ `wled` enable | 中 |
| P1 | `dr_mode = "otg"` | 低，但会和 NCM 互斥 |
| P2 | PCIe + ath10k + QCA6174 固件（WiFi） | 中 |
| P2 | 蓝牙 `hci_qca` | 中 |
| P3 | GPU / freedreno | 高 |
| P3 | venus 视频解码、camss 相机、modem 通话 | 很高 |

P0 做完之后，后续每一轮改 DTS 都不用再让手机进 fastboot。

一次内核构建可以批量验证多项（面板 + 背光 + 电量计 + `dr_mode` + `F2FS`/loop），
不必一项一次重启，因为每次重启都要人工进 fastboot。
