// SPDX-License-Identifier: GPL-2.0-only
/*
 * Sharp QHD dual-DSI video-mode panel for the LeEco Le Max 2 (x2).
 *
 * The panel is driven over two bonded DSI links: DSI0 carries the left half
 * (720x2560) and DSI1 the right half, giving a combined 1440x2560 @60Hz
 * display in pingpong-split video mode (non-burst, sync-event).
 *
 * All parameters come from the vendor kernel devicetree of a retail PVT
 * unit (msm8996-v3-pmi8994-le_x2_na-pvt.dts):
 *   arch/arm/boot/dts/qcom/leeco/dsi-panel-sharp-dualmipi-cmd-le_x2-dvt1_1.dtsi
 *     h-front-porch = 154, h-back-porch = 100, h-pulse-width = 10
 *     v-back-porch  = 7,   v-front-porch = 8,  v-pulse-width = 1
 *     panel 720x2560 @60, bpp 24, 68mm x 121mm
 *     reset sequence <1 10>, <0 10>, <1 10> (raw gpio, ends out of reset)
 *     traffic mode non_burst_sync_event -> MIPI_DSI_MODE_VIDEO only
 *     (no SYNC_PULSE / BURST; msm dsi host maps that to
 *     NON_BURST_SYNCH_EVENTS), te-check-enable via SET_TEAR_ON
 *
 * The panel has no dedicated supply rails in the vendor DTS (the PVT dtsi
 * even /delete-property/ the DSI controller vddio-supply), so none are
 * requested here.
 *
 * Structure is modelled on panel-sharp-lq079l1sx01.c, which is also a
 * two-link Sharp panel, and on panel-novatek-nt36523.c for the dual-link
 * command helper usage.
 *
 * NOTE: untested on hardware. The on/off sequences are byte-for-byte the
 * vendor qcom,mdss-dsi-on/off-command payloads; the vendor attribute
 * qcom,dcs-cmd-by-left is approximated by writing to both links, as other
 * mainline dual-DSI panels do.
 */

#include <linux/backlight.h>
#include <linux/delay.h>
#include <linux/gpio/consumer.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_graph.h>

#include <drm/drm_connector.h>
#include <drm/drm_mipi_dsi.h>
#include <drm/drm_modes.h>
#include <drm/drm_panel.h>
#include <drm/drm_print.h>
#include <drm/drm_probe_helper.h>

#include <video/mipi_display.h>

struct leeco_x2_panel {
	struct drm_panel panel;
	struct mipi_dsi_device *dsi[2];

	struct gpio_desc *reset_gpio;
};

static inline struct leeco_x2_panel *to_leeco_x2_panel(struct drm_panel *panel)
{
	return container_of(panel, struct leeco_x2_panel, panel);
}

static void leeco_x2_panel_reset(struct leeco_x2_panel *ctx)
{
	/*
	 * reset-gpios is GPIO_ACTIVE_LOW: gpiod 1 = panel held in reset
	 * (raw line low). The vendor sequence pulses the raw line low for
	 * 10ms and ends with the panel OUT of reset, so do the same: the
	 * panel is held in reset since probe (GPIOD_OUT_HIGH).
	 */
	gpiod_set_value_cansleep(ctx->reset_gpio, 1);
	usleep_range(10000, 11000);
	gpiod_set_value_cansleep(ctx->reset_gpio, 0);
	usleep_range(10000, 11000);
}

static int leeco_x2_panel_prepare(struct drm_panel *panel)
{
	struct leeco_x2_panel *ctx = to_leeco_x2_panel(panel);
	struct mipi_dsi_device *dsi0 = ctx->dsi[0];
	struct mipi_dsi_device *dsi1 = ctx->dsi[1];
	struct mipi_dsi_multi_context dsi_ctx = { .dsi = NULL };

	leeco_x2_panel_reset(ctx);

	/*
	 * Vendor qcom,mdss-dsi-on-command, byte-for-byte. The 0x15 setup
	 * writes carry no wait times in the vendor dtsi; the only waits are
	 * 120ms after sleep-out and 32ms after display-on.
	 */
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, dsi0, dsi1, 0xff, 0x10);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, dsi0, dsi1, 0xfb, 0x01);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, dsi0, dsi1, 0xba, 0x03);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, dsi0, dsi1, 0xe5, 0x01);
	/* set tear on */
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, dsi0, dsi1,
					  MIPI_DCS_SET_TEAR_ON, 0x00);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, dsi0, dsi1, 0xbb, 0x03);
	/* MCAP page 3 */
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, dsi0, dsi1, 0xb0, 0x03);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, dsi0, dsi1, 0x3b, 0x03,
					  0x08, 0x08, 0x64, 0x9a);
	/* sleep out, vendor waits 120ms */
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, dsi0, dsi1,
					  MIPI_DCS_EXIT_SLEEP_MODE);
	mipi_dsi_msleep(&dsi_ctx, 120);
	/* display on, vendor waits 32ms */
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, dsi0, dsi1,
					  MIPI_DCS_SET_DISPLAY_ON);
	mipi_dsi_msleep(&dsi_ctx, 32);

	return dsi_ctx.accum_err;
}

static int leeco_x2_panel_unprepare(struct drm_panel *panel)
{
	struct leeco_x2_panel *ctx = to_leeco_x2_panel(panel);
	struct mipi_dsi_device *dsi0 = ctx->dsi[0];
	struct mipi_dsi_device *dsi1 = ctx->dsi[1];
	struct mipi_dsi_multi_context dsi_ctx = { .dsi = NULL };

	/*
	 * Vendor qcom,mdss-dsi-off-command: FF 10, FB 01, display off
	 * (50ms), sleep in (120ms), 4f 01 (120ms).
	 */
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, dsi0, dsi1, 0xff, 0x10);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, dsi0, dsi1, 0xfb, 0x01);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, dsi0, dsi1,
					  MIPI_DCS_SET_DISPLAY_OFF);
	mipi_dsi_msleep(&dsi_ctx, 50);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, dsi0, dsi1,
					  MIPI_DCS_ENTER_SLEEP_MODE);
	mipi_dsi_msleep(&dsi_ctx, 120);
	mipi_dsi_dual_dcs_write_seq_multi(&dsi_ctx, dsi0, dsi1, 0x4f, 0x01);
	mipi_dsi_msleep(&dsi_ctx, 120);

	if (dsi_ctx.accum_err)
		return dsi_ctx.accum_err;

	/* hold the panel in reset while powered down */
	gpiod_set_value_cansleep(ctx->reset_gpio, 1);

	return 0;
}

/*
 * Per-link timing, straight from the vendor PVT dtsi
 * (dsi-panel-sharp-dualmipi-cmd-le_x2-dvt1_1): each DSI link drives
 * 720 columns with hfp 154 / hbp 100 / hpw 10.
 */
#define LEECO_X2_HFP	154
#define LEECO_X2_HBP	100
#define LEECO_X2_HPW	10
#define LEECO_X2_VFP	8
#define LEECO_X2_VBP	7
#define LEECO_X2_VPW	1

/*
 * Bonded dual-DSI mode: dsi_host halves h_total, hsync_end, ha_start,
 * ha_end and hdisplay for each link, so the DRM mode has to carry *twice*
 * the per-link horizontal porches. 720 + 154/100/10 per link therefore
 * becomes 1440 + 308/200/20 = 1968 here, and 1968/2 = 984 on the wire.
 */
#define LEECO_X2_FULL_HFP	(LEECO_X2_HFP * 2)
#define LEECO_X2_FULL_HBP	(LEECO_X2_HBP * 2)
#define LEECO_X2_FULL_HPW	(LEECO_X2_HPW * 2)

/* DRM mode clock is the combined pixel clock in kHz. */
#define LEECO_X2_FULL_PCLK(hz) \
	((1440 + LEECO_X2_FULL_HFP + LEECO_X2_FULL_HBP + LEECO_X2_FULL_HPW) * \
	 (2560 + LEECO_X2_VFP + LEECO_X2_VBP + LEECO_X2_VPW) * (hz) / 1000)
#define LEECO_X2_HALF_PCLK(hz) \
	((720 + LEECO_X2_HFP + LEECO_X2_HBP + LEECO_X2_HPW) * \
	 (2560 + LEECO_X2_VFP + LEECO_X2_VBP + LEECO_X2_VPW) * (hz) / 1000)

static const struct drm_display_mode leeco_x2_default_mode = {
	.clock = LEECO_X2_FULL_PCLK(60),
	.hdisplay = 1440,
	.hsync_start = 1440 + LEECO_X2_FULL_HFP,
	.hsync_end = 1440 + LEECO_X2_FULL_HFP + LEECO_X2_FULL_HPW,
	.htotal = 1440 + LEECO_X2_FULL_HFP + LEECO_X2_FULL_HPW +
		  LEECO_X2_FULL_HBP,
	.vdisplay = 2560,
	.vsync_start = 2560 + LEECO_X2_VFP,
	.vsync_end = 2560 + LEECO_X2_VFP + LEECO_X2_VPW,
	.vtotal = 2560 + LEECO_X2_VFP + LEECO_X2_VPW + LEECO_X2_VBP,
	.width_mm = 68,
	.height_mm = 121,
	.type = DRM_MODE_TYPE_DRIVER | DRM_MODE_TYPE_PREFERRED,
};

/*
 * Single-link fallback mode (720x2560, per-link timing). Only advertised
 * for the secondary connector if the board is ever run un-bonded; the
 * supported configuration is the bonded 1440x2560 mode above.
 */
static const struct drm_display_mode leeco_x2_half_mode = {
	.clock = LEECO_X2_HALF_PCLK(60),
	.hdisplay = 720,
	.hsync_start = 720 + LEECO_X2_HFP,
	.hsync_end = 720 + LEECO_X2_HFP + LEECO_X2_HPW,
	.htotal = 720 + LEECO_X2_HFP + LEECO_X2_HPW + LEECO_X2_HBP,
	.vdisplay = 2560,
	.vsync_start = 2560 + LEECO_X2_VFP,
	.vsync_end = 2560 + LEECO_X2_VFP + LEECO_X2_VPW,
	.vtotal = 2560 + LEECO_X2_VFP + LEECO_X2_VPW + LEECO_X2_VBP,
	.width_mm = 34,
	.height_mm = 121,
	.type = DRM_MODE_TYPE_DRIVER,
};

static int leeco_x2_add_mode(struct drm_connector *connector,
			     const struct drm_display_mode *src,
			     unsigned int clock, bool preferred)
{
	struct drm_display_mode *mode;

	mode = drm_mode_duplicate(connector->dev, src);
	if (!mode)
		return 0;

	mode->clock = clock;
	if (preferred)
		mode->type |= DRM_MODE_TYPE_PREFERRED;
	else
		mode->type &= ~DRM_MODE_TYPE_PREFERRED;
	drm_mode_set_name(mode);
	drm_mode_probed_add(connector, mode);

	if (mode->width_mm)
		connector->display_info.width_mm = mode->width_mm;
	if (mode->height_mm)
		connector->display_info.height_mm = mode->height_mm;

	return 1;
}

static int leeco_x2_panel_get_modes(struct drm_panel *panel,
				    struct drm_connector *connector)
{
	int count = 0;

	/* DSI-1 carries the 1440-wide combined mode fbcon uses; DSI-2 only
	 * advertises the 720-wide right-half mode. */
	if (strstr(connector->name, "-2"))
		return leeco_x2_add_mode(connector, &leeco_x2_half_mode,
					 LEECO_X2_HALF_PCLK(60), true);

	/* Keep 60 Hz preferred; 65 Hz is the opt-in overclock profile. */
	count += leeco_x2_add_mode(connector, &leeco_x2_default_mode,
				   LEECO_X2_FULL_PCLK(60), true);
	count += leeco_x2_add_mode(connector, &leeco_x2_default_mode,
				   LEECO_X2_FULL_PCLK(65), false);
	return count;
}

static const struct drm_panel_funcs leeco_x2_panel_funcs = {
	.prepare = leeco_x2_panel_prepare,
	.unprepare = leeco_x2_panel_unprepare,
	.get_modes = leeco_x2_panel_get_modes,
};

static int leeco_x2_panel_probe(struct mipi_dsi_device *dsi)
{
	struct leeco_x2_panel *ctx;
	struct mipi_dsi_host *dsi_r_host;
	struct device *dev = &dsi->dev;
	struct device_node *dsi_r;
	struct mipi_dsi_device_info info = {
		.type = "leeco-x2-panel",
		.channel = 0,
		.node = NULL,
	};
	int ret;

	ctx = devm_kzalloc(dev, sizeof(*ctx), GFP_KERNEL);
	if (!ctx)
		return -ENOMEM;

	drm_panel_init(&ctx->panel, dev, &leeco_x2_panel_funcs,
		       DRM_MODE_CONNECTOR_DSI);

	/* hold the panel in reset until prepare() (gpiod 1 = raw line low) */
	ctx->reset_gpio = devm_gpiod_get_optional(dev, "reset", GPIOD_OUT_HIGH);
	if (IS_ERR(ctx->reset_gpio))
		return dev_err_probe(dev, PTR_ERR(ctx->reset_gpio),
				     "failed to get reset GPIO\n");

	/*
	 * The panel always sits on two DSI hosts: port 0 is DSI0, port 1 is
	 * DSI1. Look the second link up through the of-graph.
	 */
	dsi_r = of_graph_get_remote_node(dev->of_node, 1, -1);
	if (!dsi_r)
		return dev_err_probe(dev, -ENODEV,
				     "failed to find second DSI host node\n");

	dsi_r_host = of_find_mipi_dsi_host_by_node(dsi_r);
	of_node_put(dsi_r);
	if (!dsi_r_host)
		return dev_err_probe(dev, -EPROBE_DEFER,
				     "cannot get secondary DSI host\n");

	ctx->dsi[1] = devm_mipi_dsi_device_register_full(dev, dsi_r_host, &info);
	if (IS_ERR(ctx->dsi[1]))
		return dev_err_probe(dev, PTR_ERR(ctx->dsi[1]),
				     "second link registration failed\n");

	ctx->dsi[0] = dsi;
	mipi_dsi_set_drvdata(dsi, ctx);

	ret = drm_panel_of_backlight(&ctx->panel);
	if (ret)
		return dev_err_probe(dev, ret, "failed to get backlight\n");

	drm_panel_add(&ctx->panel);

	for (int i = 0; i < ARRAY_SIZE(ctx->dsi); i++) {
		if (!ctx->dsi[i])
			continue;

		ctx->dsi[i]->lanes = 4;
		ctx->dsi[i]->format = MIPI_DSI_FMT_RGB888;
		/*
		 * vendor traffic mode non_burst_sync_event: plain video
		 * mode - the msm dsi host maps VIDEO without SYNC_PULSE or
		 * BURST to NON_BURST_SYNCH_EVENTS. LPM for LP DCS writes.
		 */
		ctx->dsi[i]->mode_flags = MIPI_DSI_MODE_VIDEO |
					  MIPI_DSI_MODE_LPM;

		ret = devm_mipi_dsi_attach(dev, ctx->dsi[i]);
		if (ret < 0) {
			drm_panel_remove(&ctx->panel);
			return dev_err_probe(dev, ret,
					     "failed to attach to DSI%d\n", i);
		}
	}

	return 0;
}

static void leeco_x2_panel_remove(struct mipi_dsi_device *dsi)
{
	struct leeco_x2_panel *ctx = mipi_dsi_get_drvdata(dsi);

	drm_panel_remove(&ctx->panel);
}

static const struct of_device_id leeco_x2_of_match[] = {
	{ .compatible = "sharp,leeco-x2-panel" },
	{ }
};
MODULE_DEVICE_TABLE(of, leeco_x2_of_match);

static struct mipi_dsi_driver leeco_x2_panel_driver = {
	.driver = {
		.name = "panel-sharp-leeco-x2",
		.of_match_table = leeco_x2_of_match,
	},
	.probe = leeco_x2_panel_probe,
	.remove = leeco_x2_panel_remove,
};
module_mipi_dsi_driver(leeco_x2_panel_driver);

MODULE_AUTHOR("minghao680");
MODULE_DESCRIPTION("LeEco Le Max 2 (x2) Sharp QHD dual-DSI panel");
MODULE_LICENSE("GPL");
