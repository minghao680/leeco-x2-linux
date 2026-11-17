# x2 传感器清单（Android 实测，2026-11-17）

采集方式：Android 10（MoKee，`le_x2` / `msm8996`）运行状态下执行

```
adb shell dumpsys sensorservice
adb shell cat /vendor/etc/sensors/sensor_def_qcomdev.conf
```

原始输出保存在仓库 `out/dumpsys-sensorservice.txt`、`out/x2-sensor_def_qcomdev.conf`。

## 1. 真实硬件

| 功能 | 型号 | 厂商 | 实例数 | 总线 / 中断（vendor registry） |
|---|---|---|---|---|
| 加速度计 | **BMI160** | BOSCH | 1 | SSC 配置为 SPI，CS 0，中断 GPIO 117 |
| 陀螺仪 | **BMI160**（同一颗） | BOSCH | 1 | 同上，CS 1，中断 GPIO 119 |
| 磁力计 | **AK09915** | AKM | 1 | 同一条 SPI 总线，CS 1 |
| 环境光 | **PA22A** | TXC | 1 | I2C bus 3，地址 `0x23`（光感/接近共用一颗） |
| 接近 | **PA22A** | TXC | 1 | 同上；registry 里另有一条 I2C bus 3 `0x1E` 的 prox/light 条目，待实测归属 |
| 霍尔（保护套） | **BU52061NVX** | ROHM | 1 | 纯 GPIO，registry 写 GPIO 124（`BU52053NVX` 是 registry 注释里的旧型号，Android 报的是 52061） |

registry 原文（`sensor_def_qcomdev.conf`）：

```
# SSI SMGR Cfg 0: BMI160 Accel DRI/FIFO
2009 0x1001 ... #SPI_bus        2010 0 ... #CS for SPI        2006 117 ... #gpio1
# SSI SMGR Cfg 1 BMI160 gyro DRI/FIFO
2109 0x1001 ... #SPI_bus        2110 0 ... #CS for SPI        2106 117 ... #gpio1
# SSI SMGR Cfg 2: AKM09915 FIFO
2209 0x1001 ... #SPI_bus        2210 0x1 ... #CS_for_SPI      2206 119 ... #gpio1
# DEVINFO PROX_LIGHT
2309 3 ... #i2c_bus             2310 0x23 ... #i2c_address
2320 3 ... #i2c_bus             2321 0x1E ... #i2c_address
# DEVINFO Hall_Effect
4706 124 ... #gpio1             4710 0x20 ... #i2c_address, dummy
```

**注意**：`0x1001` 这种写法是 SSC 的总线编码（`0x1000 | n` 表示 I2C n，纯 SPI 用
独立编号），到底对应 msm8996 的哪一路 BLSP SPI，需要主线启动后用 `spidev`/逻辑分析
实测确认，不能直接当 Linux 的 spi bus 号用。

## 2. Android 侧 45 个 "h/w sensor" 的构成

`dumpsys` 说 "Total 45 h/w sensors, 45 running"，但其中绝大多数不是独立芯片：

| 类别 | 数量 | 说明 |
|---|---|---|
| 真实芯片的 primary 实例 | 6 | BMI160 Accel / Gyro、AK09915 Mag、PA22A Prox / Light、BU52061NVX Hall |
| 同一芯片的次级实例（"-Wakeup Secondary"、Uncalibrated） | 9 | SSC 为 wakeup/non-wakeup 组合复制的逻辑 sensor，不是新硬件 |
| QTI 合成 sensor | 20 | Gravity / Linear Accel / Rotation Vector / Game RV / GeoMag RV / Orientation / Step Detector / Step Counter / Significant Motion / Tilt / AMD / RMD / Basic Gestures / Facing / Pedometer / Motion Accel / Coarse Motion Classifier 等，全部由 SSC 用 accel+gyro+mag 计算 |
| OEM 软件 sensor | 2 | `Pocket Detect`、`Pickup`（HAL 里挂的 OnePlus 风格逻辑） |
| STMicroelectronics ToF | 1 | `Time of Flight Proximity Sensor`，type 是 `android.sensor.motion_detect`，one-shot、无 batching。x2 硬件上没有 ToF，判断是 registry/HAL 残留，待实测 |
| AOSP 框架合成 | 8 | Corrected Gyro / Game RV / Gyro Bias / GeoMag RV / Gravity / Linear Accel / RV / Orientation（`0x5f...` 句柄，sensorservice 自己算的） |

完整列表（handle 顺序照抄 dumpsys）：

| handle | 名称 | vendor | 备注 |
|---|---|---|---|
| 0x01 | BMI160 Accelerometer | BOSCH | 物理 |
| 0x02 | BMI160 Accelerometer Uncalibrated -Wakeup | BOSCH | 物理（未校准副本） |
| 0x03 | AK09915 Magnetometer | AKM | 物理 |
| 0x04 | AK09915 Magnetometer Uncalibrated | AKM | 物理（未校准副本） |
| 0x05 | BMI160 Gyroscope | BOSCH | 物理 |
| 0x06 | BMI160 Gyroscope Uncalibrated | BOSCH | 物理（未校准副本） |
| 0x07 | PA22A Proximity | TXC | 物理 |
| 0x08 | PA22A Light | TXC | 物理 |
| 0x09–0x10 | BMI160 / AK09915 / PA22A "-Wakeup Secondary" 系列 | BOSCH/AKM/TXC | 物理芯片的逻辑副本 |
| 0x11–0x22 | Gravity / Linear Accel / Rotation Vector / Step Detector / Step Counter / Significant Motion / Game RV / GeoMag RV / Orientation / Tilt + Wakeup 副本 | QTI | 合成 |
| 0x23 | AMD | QTI | 合成（Ambient Mode Detection） |
| 0x24 | RMD | QTI | 合成（Relative Motion Detection） |
| 0x25 | Basic Gestures | QTI | 合成 |
| 0x26 | Facing | QTI | 合成 |
| 0x27 | Pedometer | QTI | 合成 |
| 0x28 | Motion Accel | QTI | 合成 |
| 0x29 | Coarse Motion Classifier | QTI | 合成 |
| 0x2a | BU52061NVX ROHM_Hall_Effect | ROHM_SEMICONDUCTOR | 物理（GPIO） |
| 0x2b | Pocket Detect | OEM | 软件 |
| 0x2c | Pickup | OEM | 软件 |
| 0x2d | Time of Flight Proximity Sensor | STMicroelectronics | 存疑，见上 |

## 3. 对阶段 G（主线驱动）的直接结论

1. **不需要照抄 vendor 内核的 sensor 驱动**：`mokee_x2_defconfig` 里
   `CONFIG_SENSORS_*` 全部未启用，厂商是把这些芯片挂在 ADSP/SSC 上；
   主线必须自己当总线主控。
2. BMI160 + AK09915 是 **SPI 上的两颗芯片**（CS0 / CS1），主线对应
   `drivers/iio/imu/bmi160`（SPI 前端）与 `drivers/iio/magnetometer/ak09915`。
   要把 msm8996 的 BLSP SPI 控制器打开、pinctrl 配好，再核对实际 CS/IRQ 引脚。
3. 光感/接近 PA22A 在 **I2C bus 3 的 `0x23`**，没有主线驱动，需要写最小 IIO 驱动
   （或者先只验证寄存器读写）。
4. 霍尔 BU52061NVX 直接接 **GPIO 124**，用 `gpio-keys` 做保护套开合事件。
5. 计步、手势、Pocket/Pickup 全是 SSC/HAL 软件合成，主线不需要驱动；
   真要做，只能在用户空间拿 accel 数据自己算。

## 4. 复现命令

```
adb shell dumpsys sensorservice | head -120
adb shell cat /vendor/etc/sensors/sensor_def_qcomdev.conf
adb shell ls /vendor/etc/sensors/
adb shell getprop ro.board.platform     # msm8996
adb shell getprop ro.product.device     # le_x2
```
