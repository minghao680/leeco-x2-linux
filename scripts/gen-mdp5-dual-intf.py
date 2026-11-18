#!/usr/bin/env python3
"""Generate 0005-mdp5-dual-intf.patch from the pristine kernel tree.

The build script does `git checkout -- drivers` before applying patches, so
every MDP5 change has to survive as a patch.  This script pulls the pristine
files out of git, applies the split-display edits below, and writes the diff.

Architecture: the panel is bonded across two DSI links, so there is exactly
one DSI encoder/connector (dsi.c skips the slave).  MDP5 is taught to drive
INTF0 and INTF1 from that single CRTC, each with its own CTL, and to program
both INTFs with the half-width timing (720 + 154/100/10, i.e. 984).
"""
import os
import subprocess
import sys
import tempfile

SRC = os.path.expanduser("~/linux-msm8996")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUBDIR = "drivers/gpu/drm/msm/disp/mdp5"
FILES = ["mdp5_kms.h", "mdp5_kms.c", "mdp5_encoder.c", "mdp5_crtc.c",
         "mdp5_ctl.c", "mdp5_ctl.h", "mdp5_plane.c"]
OUT = os.path.join(REPO, "kernel/patches/0005-mdp5-dual-intf.patch")


def pristine(name):
    return subprocess.check_output(
        ["git", "-C", SRC, "show", "HEAD:%s/%s" % (SUBDIR, name)],
        text=True)


def sub1(text, old, new, what):
    if text.count(old) != 1:
        sys.exit("anchor not unique (%d) for %s" % (text.count(old), what))
    return text.replace(old, new)


def edit_kms_h(t):
    t = sub1(t, """struct mdp5_pipeline {
\tstruct mdp5_interface *intf;
\tstruct mdp5_hw_mixer *mixer;
\tstruct mdp5_hw_mixer *r_mixer;\t/* right mixer */
};""", """struct mdp5_pipeline {
\tstruct mdp5_interface *intf;
\tstruct mdp5_hw_mixer *mixer;
\tstruct mdp5_hw_mixer *r_mixer;\t/* right mixer */
\tbool dual_intf;\t\t/* feed each mixer to its own INTF */
};""", "pipeline struct")

    t = sub1(t, """\tstruct mdp5_ctl *ctl;
\tstruct mdp5_pipeline pipeline;

\t/* these are derivatives of intf/mixer state in mdp5_pipeline */""",
"""\tstruct mdp5_ctl *ctl;
\tstruct mdp5_pipeline pipeline;

\t/*
\t * Second CTL/INTF pair used when the panel is split across two DSI
\t * links: the left mixer feeds INTF0 through @ctl, the right mixer
\t * feeds INTF1 through @ctl_r.
\t */
\tstruct mdp5_ctl *ctl_r;
\tstruct mdp5_pipeline pipeline_r;

\t/* these are derivatives of intf/mixer state in mdp5_pipeline */""",
                "crtc_state struct")

    t = sub1(t, """struct mdp5_interface {
\tint idx;
\tint num; /* display interface number */
\tenum mdp5_intf_type type;
\tenum mdp5_intf_mode mode;
};""", """struct mdp5_interface {
\tint idx;
\tint num; /* display interface number */
\tenum mdp5_intf_type type;
\tenum mdp5_intf_mode mode;
\tstruct mdp5_ctl *ctl; /* CTL bound to this interface, if any */
};""", "interface struct")

    t = sub1(t, "\tstruct mdp5_ctl_manager *ctlm;",
             "\tstruct mdp5_ctl_manager *ctlm;\n\n"
             "\t/* one CRTC drives INTF0+INTF1 for a two-link panel */\n"
             "\tbool dual_dsi_split;", "kms struct")

    t = sub1(t, "struct mdp5_pipeline *mdp5_crtc_get_pipeline(struct drm_crtc *crtc);",
             "struct mdp5_pipeline *mdp5_crtc_get_pipeline(struct drm_crtc *crtc);\n"
             "struct mdp5_pipeline *mdp5_crtc_get_pipeline_for(struct drm_crtc *crtc,\n"
             "\t\t\t\t\t\t  struct mdp5_interface *intf);",
             "get_pipeline prototype")
    return t


def edit_kms_c(t):
    t = sub1(t, """\t\tctl = mdp5_ctlm_request(ctlm, intf->num);
\t\tif (!ctl) {
\t\t\tret = -EINVAL;
\t\t\tbreak;
\t\t}

\t\tencoder = construct_encoder(mdp5_kms, intf, ctl);
\t\tif (IS_ERR(encoder)) {
\t\t\tret = PTR_ERR(encoder);
\t\t\tbreak;
\t\t}

\t\tret = msm_dsi_modeset_init(priv->kms->dsi[dsi_id], dev, encoder);""",
"""\t\tctl = mdp5_ctlm_request(ctlm, intf->num);
\t\tif (!ctl) {
\t\t\tret = -EINVAL;
\t\t\tbreak;
\t\t}

\t\t/* keep the CTL around: split display needs one per INTF */
\t\tintf->ctl = ctl;

\t\tencoder = construct_encoder(mdp5_kms, intf, ctl);
\t\tif (IS_ERR(encoder)) {
\t\t\tret = PTR_ERR(encoder);
\t\t\tbreak;
\t\t}

\t\tret = msm_dsi_modeset_init(priv->kms->dsi[dsi_id], dev, encoder);""",
             "dsi ctl retention")

    t = sub1(t, """\tmdp5_kms->pdev = pdev;

\tspin_lock_init(&mdp5_kms->resource_lock);""",
"""\tmdp5_kms->pdev = pdev;

\t/*
\t * Boards whose panel is split across two DSI links need this CRTC to
\t * drive INTF0 and INTF1 at once.  Opt-in from DT so other msm8996
\t * boards keep the existing single-interface behaviour.  The property
\t * lives on the parent mdss node: this platform device is
\t * display-controller@..., not mdss itself.
\t */
\tmdp5_kms->dual_dsi_split =
\t\tof_property_read_bool(pdev->dev.of_node, "qcom,dual-dsi-split");
\tif (!mdp5_kms->dual_dsi_split && pdev->dev.of_node->parent)
\t\tmdp5_kms->dual_dsi_split = of_property_read_bool(
\t\t\t\tpdev->dev.of_node->parent, "qcom,dual-dsi-split");
\tif (mdp5_kms->dual_dsi_split)
\t\tdev_info(&pdev->dev, "split display enabled (INTF0+INTF1)\\n");

\tspin_lock_init(&mdp5_kms->resource_lock);""", "dt opt-in")
    return t


def edit_encoder(t):
    # helper: find the "other" DSI interface
    t = sub1(t, """static struct mdp5_kms *get_kms(struct drm_encoder *encoder)
{
\tstruct msm_drm_private *priv = encoder->dev->dev_private;
\treturn to_mdp5_kms(to_mdp_kms(priv->kms));
}""", """static struct mdp5_kms *get_kms(struct drm_encoder *encoder)
{
\tstruct msm_drm_private *priv = encoder->dev->dev_private;
\treturn to_mdp5_kms(to_mdp_kms(priv->kms));
}

/* the second DSI interface that a split display pair drives */
static struct mdp5_interface *mdp5_split_intf(struct mdp5_kms *mdp5_kms,
\t\t\t\t\t      struct mdp5_interface *intf)
{
\tint i;

\tif (!mdp5_kms->dual_dsi_split)
\t\treturn NULL;

\tfor (i = 0; i < mdp5_kms->num_intfs; i++) {
\t\tstruct mdp5_interface *cur = mdp5_kms->intfs[i];

\t\tif (cur == intf || cur->type != INTF_DSI)
\t\t\tcontinue;
\t\treturn cur;
\t}

\treturn NULL;
}

/* crtc state of the encoder's CRTC, or NULL during teardown */
static struct mdp5_crtc_state *mdp5_cstate_of(struct drm_encoder *encoder)
{
\tif (!encoder->crtc || !encoder->crtc->state)
\t\treturn NULL;

\treturn to_mdp5_crtc_state(encoder->crtc->state);
}""", "split intf helper")

    # replace the inline register programming with a reusable helper
    old_block = t[t.index("\thsync_start_x = (mode->htotal - mode->hsync_start);"):
                  t.index("\tmdp5_crtc_set_pipeline(encoder->crtc);")]
    new_block = """\t/*
\t * Split display: the panel is bonded across two links, so *both*
\t * INTFs carry a half of the panel.  dsi_host halves h_total itself,
\t * which means the INTF timing here has to be the per-link timing
\t * (720 + 154/100/10 = 984) - feeding INTF0 the full 1968 period
\t * makes the DSI FIFO overflow immediately.
\t */
\tif (mdp5_cstate && mdp5_cstate->pipeline.dual_intf &&
\t    mdp5_cstate->pipeline_r.intf) {
\t\tstruct drm_display_mode half = *mode;

\t\thalf.hdisplay = mode->hdisplay / 2;
\t\thalf.htotal = mode->htotal / 2;
\t\thalf.hsync_start = half.htotal -
\t\t\t(mode->htotal - mode->hsync_start) / 2;
\t\thalf.hsync_end = half.hsync_start +
\t\t\t(mode->hsync_end - mode->hsync_start) / 2;
\t\thalf.clock = mode->clock / 2;

\t\tmdp5_vid_intf_mode_set(mdp5_encoder, intf, &half, format,
\t\t\t\t       ctrl_pol);
\t\tmdp5_vid_intf_mode_set(mdp5_encoder,
\t\t\t\t       mdp5_cstate->pipeline_r.intf, &half,
\t\t\t\t       format, ctrl_pol);
\t} else {
\t\tmdp5_vid_intf_mode_set(mdp5_encoder, intf, mode, format, ctrl_pol);
\t}

"""
    t = t.replace(old_block, new_block)

    # the helper itself
    t = sub1(t, "static void mdp5_vid_encoder_mode_set(struct drm_encoder *encoder,",
             """static void mdp5_vid_intf_mode_set(struct mdp5_encoder *mdp5_encoder,
\t\t\t\t   struct mdp5_interface *intf,
\t\t\t\t   const struct drm_display_mode *mode,
\t\t\t\t   uint32_t format, uint32_t ctrl_pol)
{
\tstruct mdp5_kms *mdp5_kms = get_kms(&mdp5_encoder->base);
\tuint32_t dtv_hsync_skew = 0;
\tuint32_t vsync_period, vsync_len;
\tuint32_t display_v_start, display_v_end;
\tuint32_t hsync_start_x, hsync_end_x;
\tint intf_num = intf->num;
\tunsigned long flags;

\thsync_start_x = (mode->htotal - mode->hsync_start);
\thsync_end_x = mode->htotal - (mode->hsync_start - mode->hdisplay) - 1;

\tvsync_period = mode->vtotal * mode->htotal;
\tvsync_len = (mode->vsync_end - mode->vsync_start) * mode->htotal;
\tdisplay_v_start = (mode->vtotal - mode->vsync_start) * mode->htotal +
\t\t\t  dtv_hsync_skew;
\tdisplay_v_end = vsync_period -
\t\t\t((mode->vsync_start - mode->vdisplay) * mode->htotal) +
\t\t\tdtv_hsync_skew - 1;

\tif (intf->type == INTF_eDP) {
\t\tdisplay_v_start += mode->htotal - mode->hsync_start;
\t\tdisplay_v_end -= mode->hsync_start - mode->hdisplay;
\t}

\tspin_lock_irqsave(&mdp5_encoder->intf_lock, flags);

\tmdp5_write(mdp5_kms, REG_MDP5_INTF_HSYNC_CTL(intf_num),
\t\t   MDP5_INTF_HSYNC_CTL_PULSEW(mode->hsync_end - mode->hsync_start) |
\t\t   MDP5_INTF_HSYNC_CTL_PERIOD(mode->htotal));
\tmdp5_write(mdp5_kms, REG_MDP5_INTF_VSYNC_PERIOD_F0(intf_num), vsync_period);
\tmdp5_write(mdp5_kms, REG_MDP5_INTF_VSYNC_LEN_F0(intf_num), vsync_len);
\tmdp5_write(mdp5_kms, REG_MDP5_INTF_DISPLAY_HCTL(intf_num),
\t\t   MDP5_INTF_DISPLAY_HCTL_START(hsync_start_x) |
\t\t   MDP5_INTF_DISPLAY_HCTL_END(hsync_end_x));
\tmdp5_write(mdp5_kms, REG_MDP5_INTF_DISPLAY_VSTART_F0(intf_num),
\t\t   display_v_start);
\tmdp5_write(mdp5_kms, REG_MDP5_INTF_DISPLAY_VEND_F0(intf_num),
\t\t   display_v_end);
\tmdp5_write(mdp5_kms, REG_MDP5_INTF_BORDER_COLOR(intf_num), 0);
\tmdp5_write(mdp5_kms, REG_MDP5_INTF_UNDERFLOW_COLOR(intf_num), 0xff);
\tmdp5_write(mdp5_kms, REG_MDP5_INTF_HSYNC_SKEW(intf_num), dtv_hsync_skew);
\tmdp5_write(mdp5_kms, REG_MDP5_INTF_POLARITY_CTL(intf_num), ctrl_pol);
\tmdp5_write(mdp5_kms, REG_MDP5_INTF_ACTIVE_HCTL(intf_num),
\t\t   MDP5_INTF_ACTIVE_HCTL_START(0) |
\t\t   MDP5_INTF_ACTIVE_HCTL_END(0));
\tmdp5_write(mdp5_kms, REG_MDP5_INTF_ACTIVE_VSTART_F0(intf_num), 0);
\tmdp5_write(mdp5_kms, REG_MDP5_INTF_ACTIVE_VEND_F0(intf_num), 0);
\tmdp5_write(mdp5_kms, REG_MDP5_INTF_PANEL_FORMAT(intf_num), format);
\t/* frame+line count */
\tmdp5_write(mdp5_kms, REG_MDP5_INTF_FRAME_LINE_COUNT_EN(intf_num), 0x3);

\tspin_unlock_irqrestore(&mdp5_encoder->intf_lock, flags);
}

static void mdp5_vid_encoder_mode_set(struct drm_encoder *encoder,""",
             "intf mode helper")

    # mode_set preamble: drop now-unused locals, add cstate
    t = sub1(t, """\tstruct mdp5_encoder *mdp5_encoder = to_mdp5_encoder(encoder);
\tstruct mdp5_kms *mdp5_kms = get_kms(encoder);
\tstruct drm_device *dev = encoder->dev;
\tstruct drm_connector *connector;
\tint intf = mdp5_encoder->intf->num;
\tuint32_t dtv_hsync_skew, vsync_period, vsync_len, ctrl_pol;
\tuint32_t display_v_start, display_v_end;
\tuint32_t hsync_start_x, hsync_end_x;
\tuint32_t format = 0x2100;
\tunsigned long flags;""",
"""\tstruct mdp5_encoder *mdp5_encoder = to_mdp5_encoder(encoder);
\tstruct drm_device *dev = encoder->dev;
\tstruct drm_connector *connector;
\tstruct mdp5_interface *intf = mdp5_encoder->intf;
\tstruct mdp5_crtc_state *mdp5_cstate =
\t\tencoder->crtc ? to_mdp5_crtc_state(encoder->crtc->state) : NULL;
\tuint32_t ctrl_pol;
\tuint32_t format = 0x2100;""", "mode_set locals")

    # the per-INTF skew now lives in the helper
    t = sub1(t, "\tdtv_hsync_skew = 0;  /* get this from panel? */\n\n", "",
             "drop skew local")

    # atomic_check: register the second pipeline
    t = sub1(t, """\tstruct mdp5_encoder *mdp5_encoder = to_mdp5_encoder(encoder);
\tstruct mdp5_crtc_state *mdp5_cstate = to_mdp5_crtc_state(crtc_state);
\tstruct mdp5_interface *intf = mdp5_encoder->intf;
\tstruct mdp5_ctl *ctl = mdp5_encoder->ctl;

\tmdp5_cstate->ctl = ctl;
\tmdp5_cstate->pipeline.intf = intf;""",
"""\tstruct mdp5_encoder *mdp5_encoder = to_mdp5_encoder(encoder);
\tstruct mdp5_crtc_state *mdp5_cstate = to_mdp5_crtc_state(crtc_state);
\tstruct mdp5_interface *intf = mdp5_encoder->intf;
\tstruct mdp5_ctl *ctl = mdp5_encoder->ctl;
\tstruct mdp5_interface *intf_r = mdp5_split_intf(get_kms(encoder), intf);

\tmdp5_cstate->ctl = ctl;
\tmdp5_cstate->pipeline.intf = intf;

\t/* split display: master encoder also owns the second INTF/CTL */
\tif (intf_r && intf_r->ctl) {
\t\tmdp5_cstate->ctl_r = intf_r->ctl;
\t\tmdp5_cstate->pipeline_r.intf = intf_r;
\t\tmdp5_cstate->pipeline.dual_intf = true;
\t}""", "atomic_check dual")

    # enable: kick the second INTF as well
    t = sub1(t, """\tmdp5_ctl_set_encoder_state(ctl, pipeline, true);

\tmdp5_encoder->enabled = true;""",
"""\tmdp5_ctl_set_encoder_state(ctl, pipeline, true);

\tif (mdp5_cstate_of(encoder) && mdp5_cstate_of(encoder)->pipeline.dual_intf &&
\t    mdp5_cstate_of(encoder)->ctl_r) {
\t\tstruct mdp5_crtc_state *cstate = mdp5_cstate_of(encoder);
\t\tstruct mdp5_pipeline *pipeline_r = &cstate->pipeline_r;
\t\tint intf_r_num = pipeline_r->intf->num;

\t\tspin_lock_irqsave(&mdp5_encoder->intf_lock, flags);
\t\tmdp5_write(mdp5_kms, REG_MDP5_INTF_TIMING_ENGINE_EN(intf_r_num), 1);
\t\tspin_unlock_irqrestore(&mdp5_encoder->intf_lock, flags);

\t\tmdp5_ctl_commit(cstate->ctl_r, pipeline_r,
\t\t\t\tmdp_ctl_flush_mask_encoder(pipeline_r->intf), true);
\t\tmdp5_ctl_set_encoder_state(cstate->ctl_r, pipeline_r, true);
\t}

\tmdp5_encoder->enabled = true;""", "enable second intf")

    # disable: shut the second INTF down first
    t = sub1(t, """\tif (WARN_ON(!mdp5_encoder->enabled))
\t\treturn;

\tmdp5_ctl_set_encoder_state(ctl, pipeline, false);""",
"""\tif (WARN_ON(!mdp5_encoder->enabled))
\t\treturn;

\tif (mdp5_cstate_of(encoder) && mdp5_cstate_of(encoder)->pipeline.dual_intf &&
\t    mdp5_cstate_of(encoder)->ctl_r) {
\t\tstruct mdp5_crtc_state *cstate = mdp5_cstate_of(encoder);
\t\tstruct mdp5_pipeline *pipeline_r = &cstate->pipeline_r;
\t\tint intf_r_num = pipeline_r->intf->num;

\t\tmdp5_ctl_set_encoder_state(cstate->ctl_r, pipeline_r, false);
\t\tspin_lock_irqsave(&mdp5_encoder->intf_lock, flags);
\t\tmdp5_write(mdp5_kms, REG_MDP5_INTF_TIMING_ENGINE_EN(intf_r_num), 0);
\t\tspin_unlock_irqrestore(&mdp5_encoder->intf_lock, flags);
\t\tmdp5_ctl_commit(cstate->ctl_r, pipeline_r,
\t\t\t\tmdp_ctl_flush_mask_encoder(pipeline_r->intf), true);
\t}

\tmdp5_ctl_set_encoder_state(ctl, pipeline, false);""",
             "disable second intf")
    return t


def edit_crtc(t):
    t = sub1(t, """struct mdp5_pipeline *mdp5_crtc_get_pipeline(struct drm_crtc *crtc)
{
\tstruct mdp5_crtc_state *mdp5_cstate;

\tif (WARN_ON(!crtc))
\t\treturn ERR_PTR(-EINVAL);

\tmdp5_cstate = to_mdp5_crtc_state(crtc->state);

\treturn &mdp5_cstate->pipeline;
}""", """struct mdp5_pipeline *mdp5_crtc_get_pipeline(struct drm_crtc *crtc)
{
\tstruct mdp5_crtc_state *mdp5_cstate;

\tif (WARN_ON(!crtc))
\t\treturn ERR_PTR(-EINVAL);

\tmdp5_cstate = to_mdp5_crtc_state(crtc->state);

\treturn &mdp5_cstate->pipeline;
}

/* the pipeline an encoder feeds: left by default, right for split display */
struct mdp5_pipeline *mdp5_crtc_get_pipeline_for(struct drm_crtc *crtc,
\t\t\t\t\t\t  struct mdp5_interface *intf)
{
\tstruct mdp5_crtc_state *mdp5_cstate;

\tif (WARN_ON(!crtc))
\t\treturn ERR_PTR(-EINVAL);

\tmdp5_cstate = to_mdp5_crtc_state(crtc->state);

\tif (mdp5_cstate->pipeline.dual_intf &&
\t    mdp5_cstate->pipeline_r.intf == intf)
\t\treturn &mdp5_cstate->pipeline_r;

\treturn &mdp5_cstate->pipeline;
}""", "get_pipeline_for")

    # refresh the right pipeline in setup_pipeline
    t = sub1(t, """\tif (new_mixer) {
\t\tstruct mdp5_hw_mixer *old_mixer = pipeline->mixer;
\t\tstruct mdp5_hw_mixer *old_r_mixer = pipeline->r_mixer;""",
"""\tif (new_mixer) {
\t\tstruct mdp5_hw_mixer *old_mixer = pipeline->mixer;
\t\tstruct mdp5_hw_mixer *old_r_mixer = pipeline->r_mixer;""",
             "setup anchor")  # no-op, keeps anchor readable

    # after the mixer assignment, sync the right pipeline
    t = sub1(t, """\t/*\n\t * these should have been already set up in the encoder's atomic\n\t * check (called by drm_atomic_helper_check_modeset)\n\t */\n\tintf = pipeline->intf;""",
"""\t/*
\t * Split display: the right mixer is fed to INTF1 through the second
\t * CTL, not merged into INTF0 with PACK_3D.
\t */
\tif (mdp5_cstate->ctl_r && pipeline->r_mixer) {
\t\tpipeline->dual_intf = true;
\t\tmdp5_cstate->pipeline_r.mixer = pipeline->r_mixer;
\t\tmdp5_cstate->pipeline_r.r_mixer = NULL;
\t}

\t/*
\t * these should have been already set up in the encoder's atomic
\t * check (called by drm_atomic_helper_check_modeset)
\t */
\tintf = pipeline->intf;""", "setup sync right pipeline")

    # blend: write each LM's layer registers through its own CTL
    t = sub1(t, """\tmdp5_ctl_blend(ctl, pipeline, stage, r_stage, plane_cnt,
\t\t       ctl_blend_flags);""",
"""\tif (pipeline->dual_intf && mdp5_cstate->ctl_r &&
\t    mdp5_cstate->pipeline_r.mixer) {
\t\tstruct mdp5_pipeline left = *pipeline;

\t\t{
\t\t\tstatic bool once;

\t\t\tif (!once) {
\t\t\t\tonce = true;
\t\t\t\tdev_info(mdp5_kms->dev->dev,
\t\t\t\t\t "blend dual: planes=%d rpipe=%d lm=%d/%d\\n",
\t\t\t\t\t plane_cnt,
\t\t\t\t\t (int)r_stage[STAGE_BASE][PIPE_RIGHT],
\t\t\t\t\t (int)left.mixer->lm,
\t\t\t\t\t (int)mdp5_cstate->pipeline_r.mixer->lm);
\t\t\t}
\t\t}

\t\tleft.r_mixer = NULL;
\t\tmdp5_ctl_blend(ctl, &left, stage, NULL, plane_cnt,
\t\t\t       ctl_blend_flags);
\t\tmdp5_ctl_blend(mdp5_cstate->ctl_r, &mdp5_cstate->pipeline_r,
\t\t\t       r_stage, NULL, plane_cnt, ctl_blend_flags);
\t} else {
\t\tmdp5_ctl_blend(ctl, pipeline, stage, r_stage, plane_cnt,
\t\t\t       ctl_blend_flags);
\t}""", "blend dual")

    # flush: left CTL accumulates, right CTL triggers the paired flush
    t = sub1(t, """\tbool start = !mdp5_cstate->defer_start;

\tmdp5_cstate->defer_start = false;

\tDBG("%s: flush=%08x", crtc->name, flush_mask);

\treturn mdp5_ctl_commit(ctl, pipeline, flush_mask, start);""",
"""\tbool start = !mdp5_cstate->defer_start;

\tmdp5_cstate->defer_start = false;

\tDBG("%s: flush=%08x", crtc->name, flush_mask);

\tif (mdp5_cstate->pipeline.dual_intf && mdp5_cstate->ctl_r) {
\t\t/*
\t\t * Each CTL owns its own LM/INTF pair, so flush them separately:
\t\t * the paired single-flush path only writes one CTL register and
\t\t * leaves LM1's layer configuration unlatched.
\t\t */
\t\tmdp5_ctl_commit(ctl, pipeline, flush_mask, start);
\t\tmdp5_ctl_commit(mdp5_cstate->ctl_r,
\t\t\t\t&mdp5_cstate->pipeline_r, flush_mask, start);
\t\treturn flush_mask;
\t}

\treturn mdp5_ctl_commit(ctl, pipeline, flush_mask, start);""",
             "flush dual")

    # program both pipelines, pair the CTLs and join the two pipes
    t = sub1(t, """\tmdp_irq_update(&mdp5_kms->base);

\tmdp5_ctl_set_pipeline(mdp5_cstate->ctl, &mdp5_cstate->pipeline);
}""", """\tmdp_irq_update(&mdp5_kms->base);

\tmdp5_ctl_set_pipeline(mdp5_cstate->ctl, &mdp5_cstate->pipeline);

\tif (mdp5_cstate->pipeline.dual_intf && mdp5_cstate->ctl_r) {
\t\tstatic bool once;

\t\tmdp5_ctl_set_pipeline(mdp5_cstate->ctl_r,
\t\t\t\t      &mdp5_cstate->pipeline_r);

\t\t/*
\t\t * Join the two pipes into one split display.  Vendor values for
\t\t * video mode with main INTF0 / slave INTF1: upper pipe ctrl takes
\t\t * the main interface's SW trigger mux, lower pipe ctrl the slave
\t\t * interface's TG sync.  Without this the second LM never reaches
\t\t * INTF1 and the panel sees only one of its two links.
\t\t */
\t\tmdp5_write(mdp5_kms, REG_MDP5_SPLIT_DPL_UPPER,
\t\t\t   MDP5_SPLIT_DPL_UPPER_INTF1_SW_TRG_MUX);
\t\tmdp5_write(mdp5_kms, REG_MDP5_SPLIT_DPL_LOWER,
\t\t\t   MDP5_SPLIT_DPL_LOWER_INTF2_TG_SYNC);
\t\tmdp5_write(mdp5_kms, REG_MDP5_SPLIT_DPL_EN, 1);

\t\tif (!once) {
\t\t\tonce = true;
\t\t\tdev_info(mdp5_kms->dev->dev,
\t\t\t\t "split display: intf%d + intf%d\\n",
\t\t\t\t mdp5_cstate->pipeline.intf->num,
\t\t\t\t mdp5_cstate->pipeline_r.intf->num);
\t\t}
\t}
}""", "set_pipeline dual + pair + split dpl")

    # tear the split display down with the CRTC
    t = sub1(t, "\tmdp5_crtc->enabled = false;\n}",
"""\tif (mdp5_cstate->pipeline.dual_intf && mdp5_cstate->ctl_r) {
\t\tmdp5_write(mdp5_kms, REG_MDP5_SPLIT_DPL_EN, 0);
\t\tmdp5_write(mdp5_kms, REG_MDP5_SPLIT_DPL_UPPER, 0);
\t\tmdp5_write(mdp5_kms, REG_MDP5_SPLIT_DPL_LOWER, 0);
\t}

\tmdp5_crtc->enabled = false;
}""", "split dpl teardown")
    return t


def edit_ctl(t):
    t = sub1(t, """\tif (pipeline->r_mixer)
\t\tctl_op |= MDP5_CTL_OP_PACK_3D_ENABLE |
\t\t\t  MDP5_CTL_OP_PACK_3D(1);""",
"""\t/*
\t * Source-split into one wide INTF uses 3D packing; a split display
\t * feeds each mixer to its own INTF, so PACK_3D must stay off.
\t */
\tif (pipeline->r_mixer && !pipeline->dual_intf)
\t\tctl_op |= MDP5_CTL_OP_PACK_3D_ENABLE |
\t\t\t  MDP5_CTL_OP_PACK_3D(1);""", "set_ctl_op")

    t = sub1(t, "int mdp5_ctl_pair(struct mdp5_ctl *ctlx, struct mdp5_ctl *ctly, bool enable)",
             """bool mdp5_ctl_is_paired(struct mdp5_ctl *ctl, struct mdp5_ctl *pair)
{
\treturn ctl->pair == pair;
}

int mdp5_ctl_pair(struct mdp5_ctl *ctlx, struct mdp5_ctl *ctly, bool enable)""",
             "is_paired helper")
    return t


def edit_ctl_h(t):
    return sub1(t, "int mdp5_ctl_pair(struct mdp5_ctl *ctlx, struct mdp5_ctl *ctly, bool enable);",
               "bool mdp5_ctl_is_paired(struct mdp5_ctl *ctl, struct mdp5_ctl *pair);\n"
               "int mdp5_ctl_pair(struct mdp5_ctl *ctlx, struct mdp5_ctl *ctly, bool enable);",
               "ctl.h prototype")


def edit_plane(t):
    """Force the primary plane to split into two hwpipes in dual mode."""
    t = sub1(t, """\tmax_width = config->hw->lm.max_width << 16;
\tmax_height = config->hw->lm.max_height << 16;""",
"""\tmax_width = config->hw->lm.max_width << 16;
\tmax_height = config->hw->lm.max_height << 16;

\t/*
\t * Dual-INTF split display scans each LM at half the screen
\t * width, so the plane must be split into two hwpipes even when
\t * a single LM could hold the whole width on its own.
\t */
\tif (crtc_state && to_mdp5_crtc_state(crtc_state)->pipeline.dual_intf) {
\t\tuint32_t half = (crtc_state->mode.hdisplay << 16) / 2;

\t\tif (!half)
\t\t\thalf = max_width / 2;
\t\tif (state->src_w > half)
\t\t\tmax_width = half;
\t}""", "plane force split")
    return t


def main():
    edited = {
        "mdp5_kms.h": edit_kms_h(pristine("mdp5_kms.h")),
        "mdp5_kms.c": edit_kms_c(pristine("mdp5_kms.c")),
        "mdp5_encoder.c": edit_encoder(pristine("mdp5_encoder.c")),
        "mdp5_crtc.c": edit_crtc(pristine("mdp5_crtc.c")),
        "mdp5_ctl.c": edit_ctl(pristine("mdp5_ctl.c")),
        "mdp5_ctl.h": edit_ctl_h(pristine("mdp5_ctl.h")),
        "mdp5_plane.c": edit_plane(pristine("mdp5_plane.c")),
    }

    tmp = tempfile.mkdtemp(prefix="mdp5p5")
    a = os.path.join(tmp, "a", SUBDIR)
    b = os.path.join(tmp, "b", SUBDIR)
    os.makedirs(a)
    os.makedirs(b)
    for name, text in edited.items():
        with open(os.path.join(a, name), "w") as f:
            f.write(pristine(name))
        with open(os.path.join(b, name), "w") as f:
            f.write(text)

    diff = subprocess.run(
        ["git", "diff", "--no-index", "--src-prefix=a/", "--dst-prefix=b/",
         "a", "b"], cwd=tmp, text=True, capture_output=True).stdout
    # drop the leading a/b path component added by the temp dir layout
    diff = diff.replace("a/a/", "a/").replace("b/b/", "b/")

    with open(OUT, "w", newline="\n") as f:
        f.write(diff)
    print("wrote %s (%d bytes)" % (OUT, os.path.getsize(OUT)))


if __name__ == "__main__":
    main()
