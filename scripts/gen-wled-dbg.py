"""Generate kernel/patches/0003-wled-debug.patch from a pristine qcom-wled.c."""
import difflib
import sys

SRC = sys.argv[1]
OUT = sys.argv[2]

orig = open(SRC, encoding="utf-8").read()

HELPER = """static void wled_dbg_dump(struct wled *wled, const char *tag)
{
\tunsigned int v;
\tint i;

\tregmap_read(wled->regmap, wled->ctrl_addr + WLED3_CTRL_REG_MOD_EN, &v);
\tdev_info(wled->dev, "wled-dbg %s: mod_en=%#x\\n", tag, v);
\tregmap_read(wled->regmap, wled->ctrl_addr + WLED3_CTRL_REG_FAULT_STATUS, &v);
\tdev_info(wled->dev, "wled-dbg %s: fault=%#x\\n", tag, v);
\tregmap_read(wled->regmap, wled->ctrl_addr + WLED3_CTRL_REG_INT_RT_STS, &v);
\tdev_info(wled->dev, "wled-dbg %s: rt_sts=%#x\\n", tag, v);
\tregmap_read(wled->regmap, wled->ctrl_addr + WLED3_CTRL_REG_OVP, &v);
\tdev_info(wled->dev, "wled-dbg %s: ovp=%#x\\n", tag, v);
\tregmap_read(wled->regmap, wled->ctrl_addr + WLED3_CTRL_REG_ILIMIT, &v);
\tdev_info(wled->dev, "wled-dbg %s: ilimit=%#x\\n", tag, v);
\tregmap_read(wled->regmap, wled->ctrl_addr + WLED3_CTRL_REG_FREQ, &v);
\tdev_info(wled->dev, "wled-dbg %s: freq=%#x\\n", tag, v);
\tregmap_read(wled->regmap, wled->ctrl_addr + WLED3_CTRL_REG_FEEDBACK_CONTROL, &v);
\tdev_info(wled->dev, "wled-dbg %s: fb=%#x\\n", tag, v);
\tregmap_read(wled->regmap, wled->ctrl_addr + 0x49, &v);
\tdev_info(wled->dev, "wled-dbg %s: vref=%#x\\n", tag, v);
\tregmap_read(wled->regmap, wled->ctrl_addr + 0x4a, &v);
\tdev_info(wled->dev, "wled-dbg %s: mod=%#x\\n", tag, v);
\tregmap_read(wled->regmap, wled->ctrl_addr + 0x4b, &v);
\tdev_info(wled->dev, "wled-dbg %s: hyb=%#x\\n", tag, v);
\tregmap_read(wled->regmap, wled->ctrl_addr + 0x5e, &v);
\tdev_info(wled->dev, "wled-dbg %s: sc_pro=%#x\\n", tag, v);
\tregmap_read(wled->regmap, wled->ctrl_addr + 0xe5, &v);
\tdev_info(wled->dev, "wled-dbg %s: test4=%#x\\n", tag, v);
\tregmap_read(wled->regmap, wled->ctrl_addr + 0xf2, &v);
\tdev_info(wled->dev, "wled-dbg %s: trim7p7=%#x\\n", tag, v);
\tregmap_read(wled->regmap, wled->ctrl_addr + WLED4_CTRL_REG_TEST1, &v);
\tdev_info(wled->dev, "wled-dbg %s: test1=%#x\\n", tag, v);
\tregmap_read(wled->regmap, wled->sink_addr + WLED4_SINK_REG_CURR_SINK, &v);
\tdev_info(wled->dev, "wled-dbg %s: curr_sink=%#x\\n", tag, v);
\tfor (i = 0; i < wled->cfg.num_strings; i++) {
\t\tregmap_read(wled->regmap,
\t\t\t    wled->sink_addr +
\t\t\t    WLED4_SINK_REG_BRIGHT(wled->cfg.enabled_strings[i]), &v);
\t\tdev_info(wled->dev, "wled-dbg %s: str%d bright=%#x\\n", tag,
\t\t\t wled->cfg.enabled_strings[i], v);
\t}
}

"""

anchor_setup = "static int wled4_setup(struct wled *wled)\n"
assert orig.count(anchor_setup) == 1
new = orig.replace(anchor_setup, HELPER + anchor_setup)

setup_head = (
    "static int wled4_setup(struct wled *wled)\n"
    "{\n"
    "\tint rc, temp, i, j;\n"
)
assert new.count(setup_head) == 1, "setup head anchor"
new = new.replace(setup_head, setup_head + "\n\twled_dbg_dump(wled, \"pre\");\n")

proto = "static void wled_dbg_dump(struct wled *wled, const char *tag);\n\n"
anchor_mod = "static int wled_module_enable(struct wled *wled, int val)\n"
assert new.count(anchor_mod) == 1
new = new.replace(anchor_mod, proto + anchor_mod)

mod_anchor = (
    "\trc = regmap_update_bits(wled->regmap, wled->ctrl_addr +\n"
    "\t\t\t\tWLED3_CTRL_REG_MOD_EN,\n"
    "\t\t\t\tWLED3_CTRL_REG_MOD_EN_MASK,\n"
    "\t\t\t\tval << WLED3_CTRL_REG_MOD_EN_SHIFT);\n"
    "\tif (rc < 0)\n"
    "\t\treturn rc;\n"
)
assert new.count(mod_anchor) == 1, "mod_en anchor"
new = new.replace(
    mod_anchor, mod_anchor + "\twled_dbg_dump(wled, \"module_enable\");\n")

tail_anchor = (
    "\trc = wled_auto_detection_at_init(wled);\n"
    "\n"
    "\treturn rc;\n"
    "}\n"
)
assert new.count(tail_anchor) == 1, "setup tail anchor"
new = new.replace(
    tail_anchor,
    "\trc = wled_auto_detection_at_init(wled);\n"
    "\twled_dbg_dump(wled, \"setup\");\n"
    "\n"
    "\treturn rc;\n"
    "}\n",
)

diff = "".join(
    difflib.unified_diff(
        orig.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile="a/drivers/video/backlight/qcom-wled.c",
        tofile="b/drivers/video/backlight/qcom-wled.c",
        n=3,
    )
)

with open(OUT, "w", encoding="utf-8", newline="") as fh:
    fh.write(diff)

print("wrote", OUT, len(diff), "bytes")
