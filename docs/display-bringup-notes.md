# 阶段 B：屏幕点亮记录（Le Max 2 / x2，主线 6.19.5-msm8996）

状态：**背光已解决，左半屏（720×2560）正常显示 console，右半屏无内容**。
全屏（1440×2560）需要主线 MDP5 支持“双接口输出”，目前上游没有实现，见文末。

## 1. 背光（WLED / PMI8994）

现象演进：完全不亮 → 亮一瞬即灭（OVP）→ 只有把灯串数改成 2 串才真正亮。

关键寄存器快照（`kernel/patches/0003-wled-debug.patch` 打在 `wled4_setup()` /
`wled_module_enable()` 里，打印 pre / setup / module_enable 三组）：

| 项 | bootloader(LK) 留下的可用配置 | 我们最初的配置 |
|---|---|---|
| `curr_sink` | `0x30`（只 0、1 两串） | `0xf0`（四串） |
| `test1` | `0x0`（内部 PFET） | `0x9`（外部 PFET DTEST2） |
| `sc_pro` | `0x2`（无 EN_SC） | `0x82`（EN_SC + 防抖） |
| `ilimit` | `0x3` | `0x4` |
| `ovp` | `0x1`（29.5 V） | 29.5 V / 31 V 都试过 |
| 每串 bright | `0x1a,0x1a,0xff,0xff` | 写 0xff |

结论：
- **四串全开 → 硬件保护直接关断**；只有 `qcom,enabled-strings = <0 1>`（两串）
  才能稳定点亮。四串配置下 `rt_sts=0x2`（OVP 实时跳闸）、`fault=0xa`。
- **必须用内部 PFET**：把 msm8996.dtsi 继承来的 `qcom,external-pfet`
  `/delete-property/` 掉（`test1` 保持 0），否则灯串电流路径不通。
- OVP 提到 31 V 对“不亮”无效，问题不是阈值而是通路；最终回到 29.5 V。
- `qcom,switching-freq` 在 pmi8994 的 match data 上会被判 `-EINVAL`
  （整个 wled probe 失败），默认值就是 11（800 kHz），**不要写**。
- `qcom,num-strings` 与 `qcom,enabled-strings` 同写只会告警，二者留一个即可。

最终 DT（`&pmi8994_wled`）：

```dts
&pmi8994_wled {
	status = "okay";
	qcom,enabled-strings = <0 1>;
	qcom,current-limit-microamp = <25000>;
	qcom,ovp-millivolt = <29500>;
	/delete-property/ qcom,external-pfet;
};
```

## 2. 显示链路（DSI / MDP5）

已验证：
- `panel-sharp-leeco-x2.c` 的面板驱动、reset 序列、vendor on/off 命令都正确。
- 非绑定（不写 `qcom,dual-dsi-mode`）时，DSI0 正常出画：左半屏 console 正确，
  背光稳定。
- `dmesg` 会出现一次性 `[drm:mdp5_irq_error_handler] errors: 04000000`，不致命。

尝试过但失败：
- 在 **DSI0/DSI1 控制器节点**上加 `qcom,dual-dsi-mode` +
  `qcom,master-dsi` + `qcom,sync-dual-dsi`（这是 `dsi_mgr_parse_of()` 真正读取的位置，
  写在面板节点上无效）→ 两路被绑定成 bonded 模式：
  - 画面完全消失（连左半屏都没有）
  - `dsi_err_worker: status=4`（`DSI_ERR_STATE_FIFO`）持续刷屏
  - 原因是 msm 的 bonded 实现是给 8998/845 那种“MDP 出一个 1440 流、DSI 内部劈半”
    准备的，而 8996 + MDP5 这条路上游没有相应支持：
    `mdp5_ctl_pair()`（配对两个 CTL 做 split-display 单次 flush）在上游是**死代码**，
    `mdp5_crtc` 只按单个 encoder/单个 INTF 出图。
- 上游 `msm8996-zte-axon7.dtsi` 虽然写了 dual-dsi，但它的面板
  `samsung,s6e3ha3` 在本树里**没有驱动**，说明这条路径上游基本无人验证。

## 3. 偶发黑屏（重要，别再误判成“显示链路坏了”）

同配置（DTB 内容逐字节等价，仅 phandle 编号不同）多次启动，会出现两种结果：

- 正常：左半屏 console + 企鹅，`/sys/class/graphics/fb0/virtual_size = 1440,2560`，
  CRTC `enable=1`、`hwmixer=LM2`。
- 黑屏但背光亮：dmesg 出现
  `fbcon_init: detected unhandled fb_set_par error, error code -16 (EBUSY)` +
  `fb0: sys_imageblit: framebuffer is not in virtual address space`，
  CRTC 实际没被 fbdev 成功 set_par，面板收不到有效帧。

判别方法：黑屏时直接 `head -c 3686400 /dev/urandom > /dev/fb0`，
如果左半屏出现彩色雪花，就说明 DSI/MDP5 出图正常，只是 fbcon 没接管；
问题在 fbdev/fbcon 初始化竞态，不在显示硬件。**不要因此改 WLED/DSI 配置。**

## 4. 全屏（1440×2560）已实现（screen23）

MDP5 的 `MDP_CAP_SRC_SPLIT` 上游只用于“两个 LM 拼成一个接口”，
双 INTF 输出是我们在 `kernel/patches/0005-mdp5-dual-intf.patch` 里补的：
一个 CRTC、一个 encoder，内部同时驱动 INTF1(DSI0) + INTF2(DSI1)，
每接口一套 CTL，靠 `SPLIT_DPL_EN/UPPER/LOWER` 绑定。

要点（详见 `docs/mdp5-dual-intf-plan.md`）：

1. `dsi_host.c` 的 bonded 路径自己把时序拆半，所以 DRM mode 必须用
   **双倍水平 porch**（1440+308/200/20，htotal 1968，clock≈304 MHz），
   拆半后正好是面板 dtsi 的 720+154/100/10 = 984；
2. **必须强制主 plane 拆两个 hwpipe**：8996 的 `lm.max_width = 2560`，
   1440 宽不会触发拆分，`r_mixer` 为空 → 右 LM 无 layer → INTF2 underflow
   蓝屏。补丁在 `mdp5_plane.c` 里对 `dual_intf` 把 `max_width` 压到半屏宽；
3. 两个 CTL 各自 flush（`mdp5_ctl_pair()` 的单次 flush 只写一个 FLUSH
   寄存器，LM1 的 layer 配置不会 latch）；
4. `qcom,dual-dsi-split` 必须写在 `&mdss` 父节点（`mdp5` 的 of_node 是
   `display-controller@901000`）。

实测：左右两半内容连续、无错位，`dsi_err_worker` 0 次，
`mdp5_irq_error_handler` 仅首次提交时一次 `14000000`（INTF1+INTF2 瞬时欠载）。

## 5. 复现与镜像

- 构建：`sh scripts/local-build.sh`（WSL，产物 `out/local-build`）
- 打包：`python scripts/make-bootimg.py <Image.gz> <dtb> out/boot-*.img
  --ramdisk out/initramfs-edit/initramfs-debian-net.gz --cmdline "console=tty0"`
- 当前最佳镜像：`out/boot-va39-debian-screen23.img`
  （**1440×2560 全屏 console**；背光正常；SMMU 双 workaround 在）
- 兜底基线：`out/boot-va39-debian-screen14.img`（背光 + 左半屏 console）
- 打点补丁：`kernel/patches/0003-wled-debug.patch`（由
  `scripts/gen-wled-dbg.py` 从 pristine `qcom-wled.c` 生成，勿手改）

## 6. 踩坑清单

- `qcom,switching-freq` 写入 → wled probe `-EINVAL`，panel 因 supplier 未就绪 defer。
- 四串 enabled → OVP 保护关断，表现为“背光时有时无”。
- 外部 PFET → 完全不亮。
- 面板节点的 `qcom,dual-dsi-mode` 不会被 `dsi_mgr_parse_of()` 读取。
- `unbind` wled 驱动会触发内核空指针 oops（`wled_remove` 路径），别在线试。
