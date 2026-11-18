# x2 整机硬件清单（Android 实测 + 厂商 dtsi 对照，2026-11-17）

采集环境：Android 10（MoKee，`le_x2` / `msm8996` / hardware version `pvt`），

adb 在线状态下读取 `/sys`、`/proc`、`dumpsys`，再与

`mokee-kernel-mkq/arch/arm64/boot/dts/qcom/leeco/*.dtsi` 对照。

原始输出在 `out/hw-survey/*.txt`。

## 1. SoC / 存储



| 项     | 型号                                        | 证据                                                                                              |
| ----- | ----------------------------------------- | ----------------------------------------------------------------------------------------------- |
| SoC   | Qualcomm **MSM8996**（Snapdragon 820）      | `ro.board.platform=msm8996`、`/sys/devices/soc0/machine=MSM8996`                                 |
| 存储    | Samsung **KLUCG4J1CB-B0B1**，64 GB UFS 2.0 | `/sys/class/scsi_device/0:0:0:*/device/{vendor,model,rev}` = `SAMSUNG / KLUCG4J1CB-B0B1 / 0700` |
| 存储控制器 | `624000.ufshc`                            | `androidboot.bootdevice=624000.ufshc`                                                           |

分区（`/proc/partitions`，单位 KB）：`sda` 57,073,664（整盘），`sda1..sda9`，

其中 `sda9` = 56,776,396（userdata）；另有 `sdb/sdc` 4 MB、`sdd` 128 MB、

`sde` 5 GiB（16 个分区，firmware/modem 等）。

## 2. 显示 / 触摸



| 项      | 型号                                                    | 证据                                                                                                                                                                    |
| ------ | ----------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 面板     | **Sharp QHD dual-DSI**，5.7" 1440×2560 @60 Hz，双 DSI 拼接 | `panel_name=le_x2_mdss_dsi_sharp_qhd_dualdsi_cmd`；`modes=U:1440x2560p-60`；`is_pingpong_split=1`；dtsi `qcom,mdss-pan-physical-height-dimension = <121>`、`720×2560` 每链路 |
| 背光     | PMI8994 **WLED**                                      | `/sys/class/leds/wled`、`lcd-backlight`                                                                                                                                |
| 触摸     | **Atmel maXTouch T100**（`atmel_mxt_ts`）               | `i2c-12` 地址 `0x4a`；input 名 `atmel_mxt_T100_touchscreen`；TP 固件 `160513`                                                                                                |
| 触摸（备选） | **Synaptics DSX**（`dsx-i2c`）                          | 同一 `i2c-12` 地址 `0x4b`，为不同面板批次备选，本机未绑定                                                                                                                                 |

## 3. 相机



| 位置  | 型号                                            | 模组                       | 证据                                                                                                            |
| --- | --------------------------------------------- | ------------------------ | ------------------------------------------------------------------------------------------------------------- |
| 后置  | Sony **IMX230**（2100 万像素，PDAF，带 OIS/actuator） | LG 模组（`imx230_lg`）       | `/vendor/etc/camera/imx230_lg_chromatix.xml`；v4l subdev 名 `imx230_lg`；dtsi `eeprom-name = "sony_imx230_plus"` |
| 前置  | OmniVision **OV8865**（800 万像素）                | OFILM 模组（`ov8865_ofilm`） | `/vendor/etc/camera/ov8865_ofilm_chromatix.xml`；v4l subdev 名 `ov8865_ofilm`                                   |
| 闪光灯 | **LM3643** 双路 LED                             | —                        | dtsi `label = "leds-lm3643"`；`/sys/class/leds/led:flash_0/1`、`led:torch_0/1`                                  |
| 第三路 | 未装配 / 未识别                                     | —                        | dtsi 有 `camera@1`（CSID1，无 eeprom、无 chromatix），运行时无对应 v4l sensor                                               |

## 4. 音频



| 项       | 型号                                               | 证据                                                                                    |
| ------- | ------------------------------------------------ | ------------------------------------------------------------------------------------- |
| 音频编解码器  | Qualcomm **WCD9335**（Tasha）                      | `soc:sound-9335`、`/proc/asound/cards` = `msm8996-tasha-mtp-snd-card`                  |
| 扬声器功放   | NXP **TFA9890** SmartPA（单声道）                     | `i2c-8` 地址 `0x34`，`/sys/bus/i2c/devices/8-0034/name=tfa9890`；`init.svc.vendor.tfa-sh` |
| 听筒 / 耳机 | WCD9335 直接驱动                                     | 无独立器件                                                                                 |
| 麦克风     | WCD9335 采集（`persist.audio.ssr.3mic=false`，三麦不启用） | 具体麦克风数量待拆机 / 实测确认                                                                     |
| 耳机检测    | WCD9335 MBHC（Headset Jack input）                 | input 设备 `Headset Jack`、`Button Jack`                                                 |

## 5. 无线



| 项         | 型号                                               | 证据                                                                          |
| --------- | ------------------------------------------------ | --------------------------------------------------------------------------- |
| WiFi + 蓝牙 | Qualcomm **QCA6174**（Rome，802.11ac 2×2 + BT 4.1） | PCI `168c:003e`（`0000:01:00.0`）；`vendor.qcom.bluetooth.soc=rome`            |
| GNSS      | MSM8996 集成（GPS/GLONASS/ 北斗）                      | `init.svc.gnss_service`                                                     |
| NFC       | **未装配**                                          | `dumpsys nfc` = "Can't find service"，`/dev` 无 `nq*`，i2c-8 只有 TFA9890+EEPROM |
| FM        | **未装配**                                          | vendor dts 有 `silabs4705@11`（i2c\_7），但运行时 `i2c-7` 只有 `0x1d` SMB1351         |

## 6. 传感器

见 `docs/x2-sensors.md`。硬件为 **BMI160**（加速度 + 陀螺，SPI CS0/1）、

**AK09915**（磁力计，SPI CS1）、**PA22A**（光感 + 接近，I2C3 `0x23`）、

**BU52061NVX**（霍尔，GPIO124）。

## 7. 指纹



| 项  | 型号                   | 证据                                                                                |
| -- | -------------------- | --------------------------------------------------------------------------------- |
| 指纹 | Qualcomm **QBT1000** | `/dev/qbt1000`、`soc:qcom,qbt1000`、`soc:qbt1000`；厂商驱动 `drivers/soc/qcom/qbt1000.c` |

厂商实现：QBT1000 通过 **SPI 或 SSC\_SPI** 连接，驱动把 `fpv2` 应用加载进 SSC，

再经 QSEE/TrustZone 做匹配。主线上没有对应驱动，且依赖高通安全环境，

**短期基本不可做**（只能记录，不作为阶段 G 目标）。

## 8. 电源 / 充电 / 震动 / LED



| 项           | 型号                                | 证据                                                             |
| ----------- | --------------------------------- | -------------------------------------------------------------- |
| PMIC        | Qualcomm **PM8994** + **PMI8994** | dtsi supplies；PMI8996GUI 电量计配置                                 |
| 并联充电 IC     | Qualcomm **SMB1351**              | `i2c-7` 地址 `0x1d`，`name=smb1351-charger`                       |
| 电池          | **3200 mAh**，4.4 V 上限             | `batterydata-le_x2-3200mah.dtsi`（`letv_x2_3200mah`）            |
| 电量计         | PMI8994 fuel gauge                | `/sys/class/power_supply/bms`、`battery`；主线上 `qcom-battery` 已可用 |
| 震动马达驱动      | TI **DRV2604L**                   | `i2c-9` 地址 `0x5a`，`/sys/class/drv260x/drv2604l`                |
| USB-C CC 逻辑 | Cypress **CCG2**                  | `i2c-6` 地址 `0x08`，`name=cyccg`                                 |
| EEPROM      | Atmel **24C32** ×2                | `i2c-6 0x51`、`i2c-8 0x51`                                      |
| 通知 / 按键 LED | RGB LED + button-backlight        | `/sys/class/leds/{red,green,blue,rgb,button-backlight}`        |

## 9. 按键 / IR / 其它



| 项        | 型号                                | 证据                                          |
| -------- | --------------------------------- | ------------------------------------------- |
| 电源 / 音量键 | PMIC `qpnp_pon` + `gpio-keys`     | input `qpnp_pon`、`gpio-keys`                |
| 红外       | `soc:ir-remote`（Consumer IR）      | `/sys/bus/platform/devices/soc:ir-remote`   |
| 霍尔       | BU52061NVX（GPIO124）               | 见传感器清单                                      |
| USB      | MSM8996 DWC3，Type-C（CCG2 做 CC 检测） | `androidboot.bootdevice`、`/sys/class/typec` |

## 10. 主线适配优先级（据此排阶段 G 之后的硬件工作）



| 子系统                            | 主线现状                                              | 难度 |
| ------------------------------ | ------------------------------------------------- | -- |
| 显示 / 触摸 / 电量                   | 已可用（screen23 + `atmel_mxt_ts` + `qcom-battery`）   | 完成 |
| 存储 UFS                         | 已可用（`ufshcd-qcom`，screen52 正常 PM 已通过冷启动与持续写验收）                   | 完成 |
| 音频（WCD9335 + TFA9890）          | 未做；编解码器主线有 `wcd9335` 驱动，TFA9890 无主线驱动（只有 TFA9879） | 中  |
| WiFi/BT（QCA6174）               | 未做；ath10k + hci\_qca + BDF / 固件                   | 中  |
| 相机（IMX230 / OV8865）            | 未做；camss + 两个 sensor 驱动 + VFE/CSID                | 高  |
| 传感器（BMI160/AK09915/PA22A / 霍尔） | 未做；见 `x2-sensors.md`                              | 中  |
| 指纹（QBT1000）                    | 不可做（QSEE/SSC 依赖）                                  | 极高 |
| 红外 / 震动 / LED                  | 未做，但都很简单（gpio/pwm/leds）                           | 低  |

## 11. 复现命令



```
adb shell getprop
adb shell cat /proc/cmdline
adb shell cat /proc/partitions
adb shell 'for x in /sys/class/scsi_device/0:0:0:0/device; do cat $x/vendor $x/model $x/rev; done'
adb shell 'grep -H . /sys/bus/i2c/devices/*/name'
adb shell 'for d in /sys/bus/pci/devices/*; do echo $d; cat $d/vendor $d/device $d/class; done'
adb shell cat /sys/class/graphics/fb0/msm_fb_panel_info
adb shell cat /proc/bus/input/devices
adb shell ls /sys/class/video4linux; adb shell cat /sys/class/video4linux/*/name
adb shell cat /proc/asound/cards
dumpsys sensorservice / dumpsys fingerprint / dumpsys nfc
```