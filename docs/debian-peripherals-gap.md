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
| `CONFIG_DRM_PANEL_SONY_SYNAPTICS_JDI` | **not set**（但早前有提交专门修它的 include，说明本来打算用它） |
| `soc@0/spmi@400f000/pmic@3/wled@d800`（背光） | **disabled** |
| `CONFIG_BACKLIGHT_QCOM_WLED` | =y，驱动在，节点关着 |

所以即使 panel 绑上了，背光也永远不会亮。三个门槛要一起过：panel 驱动 +
`wled` 节点 enable + 时序参数。

面板真身大概率是 Sony Synaptics JDI 系（msm8996 一代常见方案），需要从厂商
dtsi 或 Android 侧 `/sys/class/graphics/fb0` 的 panel 名确认，再决定是
`DRM_PANEL_SIMPLE` + 手写时序，还是直接启用 `SONY_SYNAPTICS_JDI` 改 compatible。

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

## rootfs 放哪

boot 分区只有 64 MiB，且 `fastboot boot` 是纯内存启动，断电即失。要持久化只有
三条路：

1. **`sde19`（4,194,304 KB = 4 GiB，用途未确认）** —— 如果它确实是闲置分区，
   格式化成 ext4 当根最干净，完全不碰 Android 的 boot/userdata/system。
2. **userdata** —— Android FBE 加密，主线内核没有 keymaster，读不了；要动就得
   清数据，用户从未授权。
3. **OTG U 盘** —— 需要先解决上面的 host 模式，且和 gadget 抢同一个口。

所以下一步最该做的是**只读侦察 `sde19`**：看它的分区名、内容、是否被 Android
挂载。确认闲置后再决定。

## 建议的顺序

| 优先级 | 事项 | 成本 |
|---|---|---|
| P0 | `sde19` 侦察 → 持久化根 | 低，但解除"每次都要重新 boot"的枷锁 |
| P1 | 电量计 + 充电状态 | 低 |
| P1 | 背光 `wled` + 面板驱动 | 中，一次内核构建能试 |
| P1 | `dr_mode = "otg"` | 低，但会和 NCM 互斥 |
| P2 | PCIe + ath10k + QCA6174 固件（WiFi） | 中 |
| P2 | 蓝牙 `hci_qca` | 中 |
| P3 | GPU / freedreno | 高 |
| P3 | venus 视频解码、camss 相机、modem 通话 | 很高 |

P0 做完之后，后续每一轮改 DTS 都不用再让手机进 fastboot，只要替换根文件系统里
的内核模块或直接重启——这是把整条路走通的前提。

一次内核构建可以批量验证多项（面板 + 背光 + 电量计 + `dr_mode`），不必一项一次
重启，因为每次重启都要人工进 fastboot。
