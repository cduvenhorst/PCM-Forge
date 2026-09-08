#!/bin/ksh
# PCM-Forge Enhanced Diagnostic + CAN Probe v3
USBROOT="$1"
[ -z "$USBROOT" ] && USBROOT="/fs/usb0"
DTSTAMP=$(date +%Y%m%d_%H%M%S 2>/dev/null || echo nodate)
LOG="${USBROOT}/pcm_debug_${DTSTAMP}.log"
DUMPDIR="${USBROOT}/pcm_dump_${DTSTAMP}"
mkdir -p "$DUMPDIR" 2>/dev/null
# --- status splash: RUNNING (forge_splash draws natively on Porsche; replaces showScreen) ---
TMPD=/tmp; [ -d /fs/tmpfs ] && TMPD=/fs/tmpfs
FS_FLAG="${TMPD}/forge_done"; rm -f "$FS_FLAG"; FS_PID=""
if [ -f "${USBROOT}/bin/forge_splash" ] && [ -f "${USBROOT}/lib/running.bin" ]; then
    cp "${USBROOT}/bin/forge_splash" "${TMPD}/forge_splash" 2>/dev/null && chmod +x "${TMPD}/forge_splash"
    "${TMPD}/forge_splash" "${USBROOT}/lib/running.bin" "${USBROOT}/lib/done.bin" "$FS_FLAG" 600 4 >>"${USBROOT}/splash.log" 2>&1 &
    FS_PID=$!
fi
echo "PCM-Forge diag starting" > "${USBROOT}/pcm_ran.txt"
{
    echo "============================================"
    echo "  PCM-Forge Enhanced Diagnostic + CAN Probe v3"
    echo "============================================"
    echo ""
    echo "=== PCM Version ==="
    cat /mnt/ifs1/HBproject/version.txt 2>&1
    cat /HBproject/version.txt 2>&1
    echo ""
    echo "=== VIN ==="
    cat /HBpersistence/vin 2>&1
    echo ""
    echo "=== Existing Activation Files ==="
    ls -la /HBpersistence/PagSWAct* 2>&1
    ls -la /HBpersistence/DBGModeActive 2>&1
    ls -la /HBpersistence/CustomBootscreen* 2>&1
    echo ""
    echo "=== Backup PagSWAct.002 ==="
    if [ -f /HBpersistence/PagSWAct.002 ]; then
        TS=$(date +%Y%m%d_%H%M%S 2>/dev/null || echo nodate)
        cp /HBpersistence/PagSWAct.002 "${USBROOT}/PagSWAct_backup_${TS}.002" 2>&1
        echo "Backed up to USB"
    else
        echo "not present"
    fi
    echo ""
    echo "=== FeatureLevel / Boot Screen ==="
    ls -la /HBpersistence/CustomBootscreen_*.bin 2>&1
    echo ""
    echo "=== CVALUE Files ==="
    ls -la /HBpersistence/CVALUE*.CVA 2>&1
    for cva in /HBpersistence/CVALUE*.CVA; do
        [ -f "$cva" ] && cp "$cva" "$DUMPDIR/" 2>/dev/null
    done
    echo ""
    echo "=== FSC Files ==="
    ls -la /HBpersistence/FSC/ 2>&1
    ls -la /mnt/efs-persist/FSC/ 2>&1
    echo ""
    echo "=== Mount Points ==="
    mount 2>&1
    echo ""
    echo "=== /HBpersistence ==="
    ls -la /HBpersistence/ 2>&1
    echo ""
    echo "=== Processes ==="
    pidin 2>&1
    echo ""
    echo "=== Network ==="
    ifconfig 2>&1
    echo ""
    echo "============================================"
    echo "  CAN / IOC Probe"
    echo "============================================"
    echo ""
    echo "=== IPC Devices ==="
    ls -laR /dev/ipc/ 2>&1
    echo ""
    echo "=== DSP IPC ==="
    ls -laR /dev/dspipc/ 2>&1
    echo ""
    echo "=== All /dev ==="
    ls /dev/ 2>&1
    echo ""
    echo "=== Device Nodes ==="
    ls /dev/ser* /dev/can* /dev/spi* /dev/i2c* /dev/hd* /dev/fs* 2>&1
    echo ""
    echo "=== Sysregs (FPGA) ==="
    ls -la /dev/sysregs/ 2>&1
    echo ""
    echo "=== MOST ==="
    ls -la /dev/most* 2>&1
    echo ""
    echo "=== hbsystem ==="
    ls -laR /hbsystem/ 2>&1
    echo ""
    echo "=== Service Broker ==="
    ls -la /srv/ 2>&1
    echo ""
    echo "=== /dev/name ==="
    ls -laR /dev/name/ 2>&1
    echo ""
    echo "=== /dev/dsi ==="
    ls -laR /dev/dsi/ 2>&1
    echo ""
    echo "=== Flash Partitions ==="
    ls -la /dev/fs0* 2>&1
    echo ""
    echo "=== HDD Partitions ==="
    ls -la /dev/hd0* 2>&1
    echo ""
    echo "=== IFS/EFS Paths ==="
    ls -d /mnt/ifs1/ /mnt/flash/ /mnt/efs-system/ /mnt/efs-extended/ /mnt/data/ /mnt/share/ /mnt/nav/ 2>&1
    echo ""
    echo "=== Engineering ESD ==="
    ls /mnt/flash/efs1/engdefs/ 2>&1
    ls /HBpersistence/engdefs/ 2>&1
    ls /mnt/ifs1/engdefs/ 2>&1
    echo ""
    echo "=== inetd.conf ==="
    cat /etc/inetd.conf 2>&1
    echo ""
    echo "=== screensaver.conf ==="
    cat /HBpersistence/screensaver.conf 2>&1
    echo ""
    echo "=== hybrid.bin ==="
    ls -la /HBpersistence/hybrid.bin 2>&1
    cp /HBpersistence/hybrid.bin "$DUMPDIR/" 2>/dev/null
    echo ""
    echo "=== test.html ==="
    cat /HBpersistence/test.html 2>&1
    echo ""
    echo "=== test1.html ==="
    cat /HBpersistence/test1.html 2>&1
    echo ""
    echo ""
    echo "=== Display / Layer Manager ==="
    ls -la /dev/layermanager 2>&1
    ls -la /dev/io-display/ 2>&1
    pidin ar | grep -i "layer\|display\|carmine\|PCM3Root" 2>&1
    cat /etc/system/config/img.conf 2>&1
    ls -la /dev/pv/ 2>&1
    echo ""
    echo "=== showScreen test ==="
    if [ -x "$TMPD/showScreen" ]; then
        "$TMPD/showScreen" 2>&1 | head -5
    else
        echo "showScreen not available"
    fi
    echo ""
    echo "============================================"
    echo "  Diagnostic + CAN Probe Complete"
    echo "============================================"
} > "$LOG" 2>&1
cp /HBpersistence/vin "$DUMPDIR/vin" 2>/dev/null
cp /HBpersistence/screensaver.conf "$DUMPDIR/" 2>/dev/null
cp /HBpersistence/test.html "$DUMPDIR/" 2>/dev/null
cp /HBpersistence/test1.html "$DUMPDIR/" 2>/dev/null
echo "PCM-Forge diag done" > "${USBROOT}/pcm_ran.txt"
# --- status splash: DONE ---
touch "$FS_FLAG" 2>/dev/null; [ -n "$FS_PID" ] && wait "$FS_PID" 2>/dev/null
