#!/usr/bin/env python3
"""Generate the msm8996 14nm UFS PHY common-reset power-cycle diff."""
from pathlib import Path
import difflib

path = Path("/home/claude/linux-msm8996/drivers/phy/qualcomm/phy-qcom-qmp-ufs.c")
before = path.read_text()
text = before
replacements = [
    (
        "\t/* true, if PCS block has no separate SW_RESET register */\n"
        "\tbool no_pcs_sw_reset;\n"
        "};",
        "\t/* true, if PCS block has no separate SW_RESET register */\n"
        "\tbool no_pcs_sw_reset;\n"
        "\t/* true, if analog power collapse requires a common reset pulse */\n"
        "\tbool power_collapse_reset;\n"
        "};",
    ),
    (
        "\t.regs\t\t\t= ufsphy_v2_regs_layout,\n\n"
        "\t.no_pcs_sw_reset\t= true,\n"
        "};\n\n"
        "static const struct qmp_phy_cfg sa8775p_ufsphy_cfg = {",
        "\t.regs\t\t\t= ufsphy_v2_regs_layout,\n\n"
        "\t.no_pcs_sw_reset\t= true,\n"
        "\t.power_collapse_reset\t= true,\n"
        "};\n\n"
        "static const struct qmp_phy_cfg sa8775p_ufsphy_cfg = {",
    ),
    (
        "\tqphy_setbits(pcs, cfg->regs[QPHY_PCS_POWER_DOWN_CONTROL], SW_PWRDN);\n"
        "\treturn 0;",
        "\tqphy_setbits(pcs, cfg->regs[QPHY_PCS_POWER_DOWN_CONTROL], SW_PWRDN);\n"
        "\tif (cfg->power_collapse_reset)\n"
        "\t\tqphy_clrbits(qmp->serdes, QSERDES_COM_SW_RESET, SW_RESET);\n"
        "\treturn 0;",
    ),
    (
        "\t/* Put PHY into POWER DOWN state: active low */\n"
        "\tqphy_clrbits(qmp->pcs, cfg->regs[QPHY_PCS_POWER_DOWN_CONTROL],",
        "\tif (cfg->power_collapse_reset)\n"
        "\t\tqphy_setbits(qmp->serdes, QSERDES_COM_SW_RESET, SW_RESET);\n\n"
        "\t/* Put PHY into POWER DOWN state: active low */\n"
        "\tqphy_clrbits(qmp->pcs, cfg->regs[QPHY_PCS_POWER_DOWN_CONTROL],",
    ),
]
for old, new in replacements:
    if text.count(old) != 1:
        raise SystemExit(f"expected one match, got {text.count(old)}: {old[:80]!r}")
    text = text.replace(old, new, 1)
path.write_text(text)
print("".join(difflib.unified_diff(
    before.splitlines(keepends=True), text.splitlines(keepends=True),
    fromfile="a/drivers/phy/qualcomm/phy-qcom-qmp-ufs.c",
    tofile="b/drivers/phy/qualcomm/phy-qcom-qmp-ufs.c",
)), end="")
