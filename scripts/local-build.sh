#!/bin/sh
# Local (WSL2) kernel build for LeEco Le Max 2 / msm8996.
#
# The source tree is expected at $SRC (default ~/linux-msm8996). On the first
# run it is turned into a git repo containing the pristine v6.19.5-msm8996
# tree, so every later run can undo the previous DTS/patch mutations while
# keeping the object files and therefore build incrementally.
set -e

SRC=${SRC:-$HOME/linux-msm8996}
REPO=${REPO:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}
OUT=${OUT:-$REPO/out/local-build}
JOBS=${JOBS:-8}

export ARCH=arm64
export CROSS_COMPILE=aarch64-linux-gnu-

cd "$SRC"
if [ ! -d .git ]; then
	git init -q
	git add -A
	git -c user.email=x2@local -c user.name=x2 commit -qm pristine
fi
git checkout -q -- arch/arm64/boot/dts/qcom drivers
rm -f drivers/gpu/drm/panel/panel-sharp-leeco-x2.c

cp "$REPO/kernel/patches/panel-sharp-leeco-x2.c" \
   drivers/gpu/drm/panel/panel-sharp-leeco-x2.c
cat "$REPO/kernel/patches/panel-Kconfig.fragment" >> drivers/gpu/drm/panel/Kconfig
echo 'obj-$(CONFIG_DRM_PANEL_SHARP_LEECO_X2) += panel-sharp-leeco-x2.o' \
	>> drivers/gpu/drm/panel/Makefile

cp "$REPO/kernel/patches/0001-arm64-dts-qcom-add-LeEco-Le-Max-2.dts" \
   arch/arm64/boot/dts/qcom/msm8996-leeco-x2.dts

MF=arch/arm64/boot/dts/qcom/Makefile
if ! grep -q msm8996-leeco-x2 "$MF"; then
	printf 'dtb-$(CONFIG_ARCH_QCOM)\t+= msm8996-leeco-x2.dtb\n' >> "$MF"
fi

for p in "$REPO"/kernel/patches/*.patch; do
	[ -e "$p" ] || continue
	base=$(basename "$p")
	case " $SKIP_PATCHES " in
	*" $base "*) echo "== skip $base"; continue ;;
	esac
	echo "== $p"
	git apply -v --ignore-whitespace "$p"
done

cp "$REPO/kernel/config-x2-msm8996-va39.aarch64" .config
sed -i 's/^CONFIG_DEBUG_INFO_BTF=y/# CONFIG_DEBUG_INFO_BTF is not set/' .config
make olddefconfig >/dev/null

# Same forced options as .github/workflows/kernel.yml: the seed config ships
# DRM_MSM and USB_CONFIGFS as modules, which can never load without a rootfs.
for opt in ARCH_QCOM DRM_MSM SCSI_UFS_QCOM PHY_QCOM_QMP_UFS \
           TOUCHSCREEN_ATMEL_MXT PINCTRL_MSM8996 QCOM_TSENS ATH10K_PCI \
           ARM_PSCI_CPUIDLE ARM_PSCI_CPUIDLE_DOMAIN; do
	scripts/config --file .config -e "$opt"
done
scripts/config --file .config \
	-e PSTORE -e PSTORE_RAM -e PSTORE_CONSOLE -e PSTORE_PMSG \
	-e PSTORE_DEFLATE_COMPRESS -e PSTORE_DEFLATE_COMPRESS_DEFAULT \
	-e DETECT_HUNG_TASK -e SOFTLOCKUP_DETECTOR -e LOCKUP_DETECTOR \
	-e HARDLOCKUP_DETECTOR -e PERF_EVENTS
scripts/config --file .config \
	-e USB -e USB_DWC3 -e USB_DWC3_DUAL_ROLE -e USB_GADGET \
	-e USB_CONFIGFS -e USB_CONFIGFS_SERIAL -e USB_CONFIGFS_ACM \
	-e TYPEC -e PHY_QCOM_QMP_USB -e PHY_QCOM_QUSB2
scripts/config --file .config -e DRM_PANEL_SHARP_LEECO_X2
scripts/config --file .config -e DRM -e DRM_SIMPLEDRM -e FRAMEBUFFER_CONSOLE
make olddefconfig >/dev/null

mkdir -p "$OUT"
make -j"$JOBS" Image.gz qcom/msm8996-leeco-x2.dtb

cp arch/arm64/boot/Image.gz "$OUT"/Image.gz
cp arch/arm64/boot/dts/qcom/msm8996-leeco-x2.dtb "$OUT"/msm8996-leeco-x2.dtb

if [ "${BUILD_MODULES:-0}" = 1 ]; then
	make -j"$JOBS" modules
	rm -rf "$OUT/modules-root"
	make INSTALL_MOD_PATH="$OUT/modules-root" INSTALL_MOD_STRIP=1 modules_install >/dev/null
	tar -C "$OUT/modules-root" -cJf "$OUT/modules.tar.xz" lib/modules
	echo "modules: $OUT/modules.tar.xz"
fi

ls -l "$OUT"
