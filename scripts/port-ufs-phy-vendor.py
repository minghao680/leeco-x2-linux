from pathlib import Path
import subprocess

src = Path('/home/claude/linux-msm8996/drivers/phy/qualcomm/phy-qcom-qmp-ufs.c')
s = src.read_text()

start = s.index('static const struct qmp_phy_init_tbl msm8996_ufsphy_serdes[] = {')
end = s.index('static const struct qmp_phy_init_tbl sc7280_ufsphy_tx[] = {', start)
new_tables = '''static const struct qmp_phy_init_tbl msm8996_ufsphy_serdes[] = {
	QMP_PHY_INIT_CFG(QSERDES_COM_CMN_CONFIG, 0x0e),
	QMP_PHY_INIT_CFG(QSERDES_COM_SYSCLK_EN_SEL, 0x17),
	QMP_PHY_INIT_CFG(QSERDES_COM_CLK_SELECT, 0x30),
	QMP_PHY_INIT_CFG(QSERDES_COM_SYS_CLK_CTRL, 0x02),
	QMP_PHY_INIT_CFG(QSERDES_COM_BIAS_EN_CLKBUFLR_EN, 0x08),
	QMP_PHY_INIT_CFG(QSERDES_COM_BG_TIMER, 0x0a),
	QMP_PHY_INIT_CFG(QSERDES_COM_HSCLK_SEL, 0x05),
	QMP_PHY_INIT_CFG(QSERDES_COM_CORECLK_DIV, 0x0a),
	QMP_PHY_INIT_CFG(QSERDES_COM_CORECLK_DIV_MODE1, 0x0a),
	QMP_PHY_INIT_CFG(QSERDES_COM_LOCK_CMP_EN, 0x01),
	QMP_PHY_INIT_CFG(QSERDES_COM_VCO_TUNE_CTRL, 0x1c),
	QMP_PHY_INIT_CFG(QSERDES_COM_RESETSM_CNTRL, 0x20),
	QMP_PHY_INIT_CFG(QSERDES_COM_CORE_CLK_EN, 0x00),
	QMP_PHY_INIT_CFG(QSERDES_COM_LOCK_CMP_CFG, 0x00),
	QMP_PHY_INIT_CFG(QSERDES_COM_VCO_TUNE_TIMER1, 0xff),
	QMP_PHY_INIT_CFG(QSERDES_COM_VCO_TUNE_TIMER2, 0x3f),
	QMP_PHY_INIT_CFG(QSERDES_COM_VCO_TUNE_MAP, 0x14),
	QMP_PHY_INIT_CFG(QSERDES_COM_SVS_MODE_CLK_SEL, 0x05),
	QMP_PHY_INIT_CFG(QSERDES_COM_DEC_START_MODE0, 0x82),
	QMP_PHY_INIT_CFG(QSERDES_COM_DIV_FRAC_START1_MODE0, 0x00),
	QMP_PHY_INIT_CFG(QSERDES_COM_DIV_FRAC_START2_MODE0, 0x00),
	QMP_PHY_INIT_CFG(QSERDES_COM_DIV_FRAC_START3_MODE0, 0x00),
	QMP_PHY_INIT_CFG(QSERDES_COM_CP_CTRL_MODE0, 0x0b),
	QMP_PHY_INIT_CFG(QSERDES_COM_PLL_RCTRL_MODE0, 0x16),
	QMP_PHY_INIT_CFG(QSERDES_COM_PLL_CCTRL_MODE0, 0x28),
	QMP_PHY_INIT_CFG(QSERDES_COM_INTEGLOOP_GAIN0_MODE0, 0x80),
	QMP_PHY_INIT_CFG(QSERDES_COM_INTEGLOOP_GAIN1_MODE0, 0x00),
	QMP_PHY_INIT_CFG(QSERDES_COM_VCO_TUNE1_MODE0, 0x3f),
	QMP_PHY_INIT_CFG(QSERDES_COM_VCO_TUNE2_MODE0, 0x01),
	QMP_PHY_INIT_CFG(QSERDES_COM_LOCK_CMP1_MODE0, 0xff),
	QMP_PHY_INIT_CFG(QSERDES_COM_LOCK_CMP2_MODE0, 0x0c),
	QMP_PHY_INIT_CFG(QSERDES_COM_LOCK_CMP3_MODE0, 0x00),
	QMP_PHY_INIT_CFG(QSERDES_COM_DEC_START_MODE1, 0x98),
	QMP_PHY_INIT_CFG(QSERDES_COM_DIV_FRAC_START1_MODE1, 0x00),
	QMP_PHY_INIT_CFG(QSERDES_COM_DIV_FRAC_START2_MODE1, 0x00),
	QMP_PHY_INIT_CFG(QSERDES_COM_DIV_FRAC_START3_MODE1, 0x00),
	QMP_PHY_INIT_CFG(QSERDES_COM_CP_CTRL_MODE1, 0x0b),
	QMP_PHY_INIT_CFG(QSERDES_COM_PLL_RCTRL_MODE1, 0x16),
	QMP_PHY_INIT_CFG(QSERDES_COM_PLL_CCTRL_MODE1, 0x28),
	QMP_PHY_INIT_CFG(QSERDES_COM_INTEGLOOP_GAIN0_MODE1, 0x80),
	QMP_PHY_INIT_CFG(QSERDES_COM_INTEGLOOP_GAIN1_MODE1, 0x00),
	QMP_PHY_INIT_CFG(QSERDES_COM_VCO_TUNE1_MODE1, 0xd6),
	QMP_PHY_INIT_CFG(QSERDES_COM_VCO_TUNE2_MODE1, 0x00),
	QMP_PHY_INIT_CFG(QSERDES_COM_LOCK_CMP1_MODE1, 0x32),
	QMP_PHY_INIT_CFG(QSERDES_COM_LOCK_CMP2_MODE1, 0x0f),
	QMP_PHY_INIT_CFG(QSERDES_COM_LOCK_CMP3_MODE1, 0x00),
	QMP_PHY_INIT_CFG(QSERDES_COM_PLL_IVCO, 0x0f),
	QMP_PHY_INIT_CFG(QSERDES_COM_BG_TRIM, 0x0f),
	QMP_PHY_INIT_CFG(QSERDES_COM_RESCODE_DIV_NUM, 0x15),
	QMP_PHY_INIT_CFG(QSERDES_COM_CMN_MISC2, 0x1f),
};

static const struct qmp_phy_init_tbl msm8996_ufsphy_tx[] = {
	QMP_PHY_INIT_CFG(QSERDES_TX_HIGHZ_TRANSCEIVEREN_BIAS_DRVR_EN, 0x45),
	QMP_PHY_INIT_CFG(QSERDES_TX_LANE_MODE, 0x06),
};

static const struct qmp_phy_init_tbl msm8996_ufsphy_rx[] = {
	QMP_PHY_INIT_CFG(QSERDES_RX_SIGDET_LVL, 0x24),
	QMP_PHY_INIT_CFG(QSERDES_RX_SIGDET_CNTRL, 0x0f),
	QMP_PHY_INIT_CFG(QSERDES_RX_RX_INTERFACE_MODE, 0x00),
	QMP_PHY_INIT_CFG(QSERDES_RX_SIGDET_DEGLITCH_CNTRL, 0x1e),
	QMP_PHY_INIT_CFG(QSERDES_RX_UCDR_FASTLOCK_FO_GAIN, 0x0b),
	QMP_PHY_INIT_CFG(QSERDES_RX_RX_TERM_BW, 0x5b),
	QMP_PHY_INIT_CFG(QSERDES_RX_RX_EQ_GAIN1_LSB, 0xff),
	QMP_PHY_INIT_CFG(QSERDES_RX_RX_EQ_GAIN1_MSB, 0x3f),
	QMP_PHY_INIT_CFG(QSERDES_RX_RX_EQ_GAIN2_LSB, 0xff),
	QMP_PHY_INIT_CFG(QSERDES_RX_RX_EQ_GAIN2_MSB, 0x3f),
	QMP_PHY_INIT_CFG(QSERDES_RX_RX_EQU_ADAPTOR_CNTRL2, 0x0d),
	QMP_PHY_INIT_CFG(QSERDES_RX_UCDR_SVS_SO_GAIN_HALF, 0x04),
	QMP_PHY_INIT_CFG(QSERDES_RX_UCDR_SVS_SO_GAIN_QUARTER, 0x04),
	QMP_PHY_INIT_CFG(QSERDES_RX_UCDR_SVS_SO_GAIN, 0x04),
	QMP_PHY_INIT_CFG(QSERDES_RX_UCDR_SO_SATURATION_AND_ENABLE, 0x4b),
};

static const struct qmp_phy_init_tbl msm8996_ufsphy_pcs[] = {
	QMP_PHY_INIT_CFG(QPHY_V2_PCS_UFS_RX_SIGDET_CTRL2, 0x6c),
	QMP_PHY_INIT_CFG(QPHY_V2_PCS_UFS_TX_LARGE_AMP_DRV_LVL, 0x12),
	QMP_PHY_INIT_CFG(QPHY_V2_PCS_UFS_TX_SMALL_AMP_DRV_LVL, 0x06),
	QMP_PHY_INIT_CFG(QPHY_V2_PCS_UFS_RX_MIN_STALL_NOCONFIG_TIME_CAP, 0x28),
	QMP_PHY_INIT_CFG(QPHY_V2_PCS_UFS_RX_SYM_RESYNC_CTRL, 0x03),
	QMP_PHY_INIT_CFG(QPHY_V2_PCS_UFS_RX_PWM_GEAR_BAND, 0x55),
};

'''
s = s[:start] + new_tables + s[end:]

old = '''	/* true, if PCS block has no separate SW_RESET register */
	bool no_pcs_sw_reset;
};'''
new = '''	/* true, if PCS block has no separate SW_RESET register */
	bool no_pcs_sw_reset;

	/* Apply the 14nm PHY SVS configuration after PCS becomes ready */
	bool svs_mode;
};'''
assert s.count(old) == 1
s = s.replace(old, new)

old = '''		.rx		= msm8996_ufsphy_rx,
		.rx_num		= ARRAY_SIZE(msm8996_ufsphy_rx),
	},'''
new = '''		.rx		= msm8996_ufsphy_rx,
		.rx_num		= ARRAY_SIZE(msm8996_ufsphy_rx),
		.pcs		= msm8996_ufsphy_pcs,
		.pcs_num	= ARRAY_SIZE(msm8996_ufsphy_pcs),
	},'''
assert s.count(old) == 1
s = s.replace(old, new)

old = '''	.no_pcs_sw_reset	= true,
};

static const struct qmp_phy_cfg sa8775p_ufsphy_cfg = {'''
new = '''	.no_pcs_sw_reset	= true,
	.svs_mode		= true,
};

static const struct qmp_phy_cfg sa8775p_ufsphy_cfg = {'''
assert s.count(old) == 1
s = s.replace(old, new)

old = '''	if (ret) {
		dev_err(qmp->dev, "phy initialization timed-out\\n");
		return ret;
	}

	return 0;
}'''
new = '''	if (ret) {
		dev_err(qmp->dev, "phy initialization timed-out\\n");
		return ret;
	}

	if (cfg->svs_mode) {
		writel(0x40, qmp->rx + QSERDES_RX_RX_INTERFACE_MODE);
		writel(0x15, pcs + QPHY_V2_PCS_UFS_RX_PWM_GEAR_BAND);
		/* Ensure the SVS configuration is committed before link startup. */
		readl(pcs + QPHY_V2_PCS_UFS_RX_PWM_GEAR_BAND);
	}

	return 0;
}'''
assert s.count(old) == 1
s = s.replace(old, new)
src.write_text(s)

diff = subprocess.run(
    ['git', '-C', '/home/claude/linux-msm8996', 'diff', '--',
     'drivers/phy/qualcomm/phy-qcom-qmp-ufs.c'],
    check=True, capture_output=True, text=True).stdout
out = Path('/mnt/g/LeEco-Max2/leeco-x2-nura/kernel/patches/0012-ufs-phy-vendor-calibration.patch')
out.write_text(diff)
print(f'wrote {out}: {len(diff.splitlines())} lines')
