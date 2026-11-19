# x2 软重启挂起：分析与修复

## 现象

在 Debian 下执行直接 `reboot(2)`（`/tmp/x2-reboot-nosync` 或带 `sync()` 的
`/tmp/x2-reboot`）后，USB NCM / WiFi 掉线，串口不再输出，设备必须长按电源键。
`/sbin/reboot` 在这套 initramfs 里只是 `/bin/systemctl` 的软链，PID1 不是 systemd，
不能作为内核 reboot 测试入口。

## 静态差异

- Android 3.18 的 `msm8996.dtsi` 有 `wdog: qcom,wdt@9830000`，由 qcom watchdog
  驱动注册 restart handler。
- 主线 `msm8996.dtsi` **没有 watchdog 节点**，启动后 `/sys/class/watchdog` 和
  `/dev/watchdog*` 都不存在；dmesg 里只有 PSCI，没有 wdt。
- 主线 PSCI restart handler 优先级为 **129**。如果 `SYSTEM_RESET` 没有真正复位，
  `machine_restart()` 会打印 `Reboot failed -- System halted` 并死循环，watchdog
  默认优先级 0，根本没有机会兜底。

## 修复

1. `0001-arm64-dts-qcom-add-LeEco-Le-Max-2.dts` 增加：

   ```dts
   &soc {
       watchdog@9830000 {
           compatible = "qcom,kpss-wdt";
           reg = <0x9830000 0x1000>;
           interrupts = <0 28 0>, <0 29 0>;
           clocks = <&sleep_clk>;
           timeout-sec = <30>;
       };
   };
   ```

2. `0007-qcom-wdt-restart-priority.patch`：
   - 如果 bootloader 留下的 WDT 还在跑，probe 时先 `qcom_wdt_stop()`，避免 Debian
     没有 watchdog daemon 被 30 秒复位；
   - 对 `match_data_kpss` 设置 `watchdog_set_restart_priority(..., 130)`，高于 PSCI
     的 129。

3. `0002-ufs-skip-shutdown-on-restart.patch` 保留为重启路径的诊断/规避：在
   `SYSTEM_RESTART` 时跳过 UFS wlun shutdown，避免 shutdown 阶段再次卡住。

## 实机验证

- 候选镜像：`out/boot-x2-debian-wdt.img`（49,836,032 bytes）
- 运行内核：`6.19.5-msm8996+ #53`
- `/proc/device-tree/soc@0/watchdog@9830000` 存在
- `/dev/watchdog0` 已注册；`/sys/class/watchdog/watchdog0` 存在
- `CONFIG_QCOM_WDT=y`；`CONFIG_WATCHDOG_SYSFS` 未开，因此没有 `identity` 等属性，
  这不是 probe 失败

触发 `/tmp/x2-reboot-nosync` 后，设备正常回到 Android。持久 `kmsg.log` 在复位点
直接结束：

```text
[   10.208482] fb0: sys_fillrect: framebuffer is not in virtual address space.
[    0.000000] Booting Linux on physical CPU 0x0000000000 ...
[    0.000000] Linux version 6.19.5-msm8996+ ... #53 ...
```

中间没有 `Restarting system`、`Reboot failed -- System halted` 或 `System halted`。
这说明复位链没有走 PSCI 的正常关机路径，而是在 watchdog 计时到点后直接复位；
因为 printk 未落盘，严格说这是强推断，但软重启确实不再挂死。

## 遗留

- DTS 里 `interrupts` 原为 `<0 28 0>, <0 29 0>`，mainline GIC 会打印
  `WARNING: ... irq-gic-v3.c:1629 at gic_irq_domain_translate`。已改为
  `<0 28 1>, <0 29 1>`（`IRQ_TYPE_EDGE_RISING`），新镜像
  `out/boot-x2-debian-wdt.img` 待启动验证；qcom-wdt 当前没有使用 pretimeout，
  这项修改不影响 restart。
- `fastboot boot` 仍然是临时启动；重启后会回到正常 boot 分区（Android）。
- 下一次要复测 Debian，需要重新 `fastboot boot out/boot-x2-debian-wdt.img`。
