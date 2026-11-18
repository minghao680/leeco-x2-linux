#!/usr/bin/env python3
"""Generate the msm8996 cold-boot redundant PHY power-cycle removal diff."""
from pathlib import Path
import difflib

path = Path("/home/claude/linux-msm8996/drivers/ufs/host/ufs-qcom.c")
before = path.read_text()
text = before
replacements = [
    (
        "\tstruct phy *phy = host->generic_phy;\n"
        "\tenum phy_mode mode;\n"
        "\tint ret;",
        "\tstruct phy *phy = host->generic_phy;\n"
        "\tenum phy_mode mode;\n"
        "\tbool skip_phy_cycle;\n"
        "\tint ret;",
    ),
    (
        "\tmode = host_params->hs_rate == PA_HS_MODE_B ? PHY_MODE_UFS_HS_B : PHY_MODE_UFS_HS_A;\n",
        "\tmode = host_params->hs_rate == PA_HS_MODE_B ? PHY_MODE_UFS_HS_B : PHY_MODE_UFS_HS_A;\n"
        "\tskip_phy_cycle = of_device_is_compatible(hba->dev->of_node,\n"
        "\t\t\t\t\t\t   \"qcom,msm8996-ufshc\") &&\n"
        "\t\t\t\t phy->power_count;\n",
    ),
    (
        "\tif (phy->power_count)\n"
        "\t\tphy_power_off(phy);",
        "\tif (phy->power_count && !skip_phy_cycle)\n"
        "\t\tphy_power_off(phy);",
    ),
    (
        "\t/* power on phy - start serdes and phy's power and clocks */\n"
        "\tret = phy_power_on(phy);",
        "\t/* power on phy - start serdes and phy's power and clocks */\n"
        "\tif (!skip_phy_cycle)\n"
        "\t\tret = phy_power_on(phy);\n"
        "\telse\n"
        "\t\tret = 0;",
    ),
]
for old, new in replacements:
    if text.count(old) != 1:
        raise SystemExit(f"expected one match, got {text.count(old)}: {old[:80]!r}")
    text = text.replace(old, new, 1)
path.write_text(text)
print("".join(difflib.unified_diff(
    before.splitlines(keepends=True), text.splitlines(keepends=True),
    fromfile="a/drivers/ufs/host/ufs-qcom.c",
    tofile="b/drivers/ufs/host/ufs-qcom.c",
)), end="")
