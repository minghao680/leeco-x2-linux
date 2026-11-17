# MDP5 双接口输出（正统双链路面板方案）实施方案

> **修订（2026-11-17，读代码后推翻原第 3/6 步）**
>
> `drivers/gpu/drm/msm/dsi/dsi.c: msm_dsi_modeset_init()` 在 bonded 模式下
> **只给 master DSI 创建 encoder/connector，slave DSI 直接 return 0**：
> ```c
> if (msm_dsi_is_bonded_dsi(msm_dsi) && !msm_dsi_is_master_dsi(msm_dsi))
>         return 0;   /* 不给 slave 建 encoder */
> ```
> 所以「一个 CRTC + 两个 DSI encoder」在 bonded 下从根上不成立（只有一个 encoder）。
> 结论：双接口必须**在 MDP5 内部实现**，由一个 encoder 内部驱动 INTF0 + INTF1
> 两套 CTL，而不是靠两个 DRM encoder。
>
> 上游现状：2026-01 只合入了 **DPU** 的 quad-pipe dual-interface
> （`drm/msm/dpu: Support quad pipe with dual-interface` v17），**MDP5 无此能力**，
> 全树没有第二个 INTF 的自动配置路径。
>
> 但下游 3.18 内核里有完整参考实现，可直接照抄语义：
> `G:\LeEco-Max2\mokee-kernel-mkq\drivers\video\msm\mdss\mdss_mdp_ctl.c`
> - `mdss_mdp_ctl_split_display_setup()`（L3774）
> - `mdss_mdp_ctl_split_display_enable()`（L3835，含
>   `MDP_CTL_SPLIT_DPL_SINGLE_FLUSH_EN` / `split_top_bottom_en` 的写法）
> - 调用点 L4042 / L4158 / L4232 / L5509
>
> 修正后的正确架构（**V2**）：
> 1. DSI 侧走 bonded：一个 connector / 一个 encoder，mode = 1440×2560 +
>    **双倍水平 porch**（308/200/20，htotal 1968，clock≈304 MHz），
>    `dsi_host.c` 自己拆半 → 每条链路 720 + 154/100/10 = 984；
> 2. MDP5 侧由这个唯一的 encoder 内部再驱动 INTF1：
>    - `mdp5_crtc_state` 增加 `ctl_r` / `pipeline_r`；
>    - 第二个 CTL 不复用 encoder 的 `mdp5_encoder->ctl`，由 mdp5_crtc 在
>      atomic_check 里按 `mdp5_ctl_get()` 取/配对；
>    - `mdp5_ctl_pair(ctl, ctl_r, true)` 让两次 flush 合并成一次；
>    - `blend_setup()` 的 `mdp5_ctl_blend()` 对左右 LM 分别用各自的 CTL 写；
>    - `mdp5_vid_encoder_mode_set()` 里两套 INTF 都按半幅（720/984）编程。
>
> 这个模型对上层完全透明：Wayland/X 看到的就是一个 1440×2560 的普通输出。

> **结果（2026-11-17，已点亮全屏）**
>
> `out/boot-va39-debian-screen23.img` 实测 **1440×2560 全屏正常**：
> console 跨左右两半连续、无错位，`blend dual: planes=1 rpipe=0 lm=2/5`，
> `dsi_err_worker` 计数 0，`mdp5_irq_error_handler` 只在首次提交时出现
> 一次 `14000000`（INTF1+INTF2 瞬时欠载），uptime 200 s 内不再复现。
>
> **决定性根因**：`mdp5_cfg.c` 里 msm8x96 的 `lm.max_width = 2560`，
> 而屏宽 1440 < 2560，所以上游 `mdp5_plane_atomic_check()` 永远不会把主
> plane 拆成两个 hwpipe（`MDP_CAP_SRC_SPLIT` 只在 `src_w > max_width` 时才走），
> 于是 `r_mixer` 恒为空、`blend_setup()` 从不为右 LM 写 layer 寄存器，
> INTF2 扫到的就是 underflow color（我们写的 `0xff` → 蓝）。
> 之前的 INTF/CTL/SPLIT_DPL 方向都是对的，只是数据源这一层缺了拆分管路。
>
> 最终实现与上面 V2 的差异：
> - `mdp5_plane.c` 新增：CRTC 状态为 `dual_intf` 时把 `max_width` 降到
>   半屏宽度，强制主 plane 拆两个 hwpipe（右 pipe 自动 `src_x = 720`、
>   `crtc_x = 720`）；
> - 不启用 `mdp5_ctl_pair()` 的单次 flush（配对后只写一个 FLUSH 寄存器，
>   LM1 的 layer 配置不 latch），两个 CTL 各自 `mdp5_ctl_commit(..., start)`；
> - LM1 用 `r_stage`（两个 pipe 镜像）而不是只挂右 pipe，
>   `MDP5_LM_BLEND_COLOR_OUT_SPLIT_LEFT_RIGHT` 保留 —— 与 vendor
>   split display 语义一致；
> - `qcom,dual-dsi-split` 必须放在 `&mdss` 父节点（`mdp5` 自身 of_node 是
>   `display-controller@901000`，读不到时回退读 `->parent`）。
>
> 寄存器偏移注意：8996 实际 `intf.base = {0x6a000,0x6a800,0x6b000,...}`、
> `ctl.base = {0x1000,0x1200,...}`、`lm.base = {0x44000,...}`（`mdp5_cfg.c`
> msm8x96_config），此前按 apq8084 表算出的 `0x913400/0x913c14/0x914000`
> 是错的，不要再用。


目标：一个 CRTC / 一个 DRM connector，驱动 1440×2560，左 LM→INTF0→DSI0，
右 LM→INTF1→DSI1，单次 flush。上层（Wayland/X/GL）看到的就是一块普通屏幕。

## 现状与差距（已核对上游代码）

1. `mdp5_ctl.c: set_ctl_op()` 只写一个 `MDP5_CTL_OP_INTF_NUM`，一个 CTL 只能对一个 INTF；
   `mdp5_ctl_pair()`（两个 CTL 配对、`MDP5_SPARE_0_SPLIT_DPL_SINGLE_FLUSH_EN` 单次 flush）
   在上游**没有任何调用者**，是半成品脚手架。
2. `mdp5_crtc_state` 只有一套 `ctl` + `pipeline`；`get_encoder_from_crtc()` 只取第一个 encoder，
   `mdp5_encoder_atomic_check()` 无条件覆盖 `cstate->ctl / pipeline.intf`。
3. 现在的宽屏路径是「两个 LM 用 PACK_3D 合成**一个**接口」（`set_ctl_op` 里
   `if (pipeline->r_mixer) PACK_3D(1)`），这不是双接口，仅适用于单链路宽面板。
4. `blend_setup()` 用同一个 CTL 写两个 LM 的 `REG_MDP5_CTL_LAYER_REG(ctl->id, lm)`；
   真正的双 CTL 下，右 LM 的 layer 寄存器在 **右 CTL** 里，必须分两次写。
5. DSI 侧 `dsi_host.c: dsi_timing_setup()` 对 bonded 的拆半是
   `h_total/=2, hs_end/=2, ha_start/=2, ha_end/=2, hdisplay/=2`，**horizon porches 不额外补偿**；
   `dsi_get_pclk_rate()` 对 bonded 把 pclk 减半。
   因此 DRM mode 必须是「整屏像素 + **双倍**的水平 porch」：1440 + (308/200/20)，
   htotal=1968，clock≈304 MHz → 拆半后正好落回面板 dtsi 的 720 + 154/100/10（984 线）。
   用现在的 1704 时序去 bonded，每链路只有 852，和面板要的 984 不符——这正是之前
   `dsi_err_worker status=4`（FIFO）刷屏的直接原因。
6. 面板真身（`dsi-panel-*-dualmipi-*-le_x2-pvt.dtsi`）：每链路 720×2560，
   hfp/hbp/hpw = 154/100/10，v 方向 8/7/1。

## 需要改的文件与顺序（每个都能单独编译验证）

### 第 1 步：面板 mode 用「双倍水平 porch」
`kernel/patches/panel-sharp-leeco-x2.c`
- 1440×2560@60，hfp=308、hbp=200、hpw=20，clock 按 1968×2576×60 算。
- 再加一个 720×2560 的「单链路」备用 mode（不置 PREFERRED），便于回退调试。

### 第 2 步：`struct mdp5_pipeline` 增加 `bool dual_intf`
`mdp5_kms.h`：
```c
struct mdp5_pipeline {
	struct mdp5_interface *intf;
	struct mdp5_hw_mixer *mixer;
	struct mdp5_hw_mixer *r_mixer;
	bool dual_intf;         /* 两个 mixer 各自喂自己的 INTF */
};
```
`struct mdp5_crtc_state` 增加：
```c
	struct mdp5_ctl *ctl_r;
	struct mdp5_pipeline pipeline_r;
```

### 第 3 步：encoder 侧登记第二套 pipeline
`mdp5_encoder.c: mdp5_encoder_atomic_check()`：
```c
if (!mdp5_cstate->pipeline.intf) {
	mdp5_cstate->ctl = ctl;
	mdp5_cstate->pipeline.intf = intf;
} else if (mdp5_cstate->pipeline.intf != intf) {
	mdp5_cstate->ctl_r = ctl;
	mdp5_cstate->pipeline_r.intf = intf;
}
```
`enable/disable/mode_set` 用新的
`mdp5_crtc_get_pipeline_for(crtc, intf)`（按 intf 返回左/右 pipeline），
`mixer` 同理取 `pipeline->mixer`（右 pipeline 的 mixer = `pipeline.r_mixer`）。

### 第 4 步：双 CTL 的 pipeline / flush / blend
- `mdp5_crtc_set_pipeline()`：两套都 `mdp5_ctl_set_pipeline()`，然后
  `mdp5_ctl_pair(ctl, ctl_r, true)`。
- `mdp5_ctl.c: set_ctl_op()`：`PACK_3D` 只在 `pipeline->r_mixer && !pipeline->dual_intf` 时设。
- `crtc_flush()`：双 CTL 时先 `mdp5_ctl_commit(ctl, &pipeline, mask, false)`，
  再 `mdp5_ctl_commit(ctl_r, &pipeline_r, mask, start)`，由配对逻辑合并成一次 flush。
- `blend_setup()`：拆成「按 LM 写」——左 LM 用 `ctl`，右 LM 用 `ctl_r`。
  这步是真正的工作量所在（函数 ~150 行，需要把 mixer/ctl 绑定参数化）。

### 第 5 步：INTF 时序按半幅编程
`mdp5_vid_encoder_mode_set()`：`dual_intf` 时构造半幅 mode：
```
half.hdisplay = mode->hdisplay / 2;
half.htotal   = mode->htotal / 2;
half.hsync_start = half.htotal - (mode->htotal - mode->hsync_start) / 2;
half.hsync_end   = half.hsync_start + (mode->hsync_end - mode->hsync_start) / 2;
half.clock       = mode->clock / 2;
```
（DSI host 侧 already 自己拆半，两边结果一致：720 + 984。）

### 第 6 步：DT 打开 bonded
`msm8996-leeco-x2.dts` 的 `&mdss_dsi0/&mdss_dsi1`：
```dts
qcom,dual-dsi-mode;     /* dsi0：主 */
qcom,master-dsi;
qcom,sync-dual-dsi;
```
面板驱动里两个 `mipi_dsi_device` 已就绪（`ctx->dsi[0]/[1]`），无需改。

## 验证要点

- `dmesg` 不应再出现 `dsi_err_worker: status=4`。
- `/sys/kernel/debug/dri/0/state`：只有一个 connector 被 fbdev 使用，
  CRTC 两个 mixer 都非空，plane 的 `right-hwpipe` 不为空（双 hwpipe 分割）。
- 左右两半应显示连续的同一幅 1440 宽画面（不是重复、不是裁剪）。
- 每轮验证都需要用户强制重启（设备侧 `reboot` 被安全策略拦截）。

## 回退

保留 `boot-va39-debian-screen14.img`（左半屏 console 可用）与
`screen17`（fbdev 双 CRTC 偏移实验版）。第 1 步的 mode 改动必须和第 6 步的
bonded 开关一起启用，否则单链路会拿到双倍 clock（黑屏但不损坏）。
