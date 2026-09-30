#!/bin/ksh
# PCM-Forge activation — https://github.com/dspl1236/PCM-Forge
USBROOT="$1"
[ -z "$USBROOT" ] && USBROOT="/fs/usb0"
# --- status splash: RUNNING (forge_splash draws natively on Porsche; replaces showScreen) ---
TMPD=/tmp; [ -d /fs/tmpfs ] && TMPD=/fs/tmpfs
FS_FLAG="${TMPD}/forge_done"; rm -f "$FS_FLAG"; FS_PID=""
if [ -f "${USBROOT}/bin/forge_splash" ] && [ -f "${USBROOT}/lib/running.bin" ]; then
    cp "${USBROOT}/bin/forge_splash" "${TMPD}/forge_splash" 2>/dev/null && chmod +x "${TMPD}/forge_splash"
    "${TMPD}/forge_splash" "${USBROOT}/lib/running.bin" "${USBROOT}/lib/done.bin" "$FS_FLAG" 600 4 >>"${USBROOT}/splash.log" 2>&1 &
    FS_PID=$!
fi
if [ -f /HBpersistence/PagSWAct.002 ]; then
    cp /HBpersistence/PagSWAct.002 /HBpersistence/PagSWAct.002.bak 2>/dev/null
    TS=$(date +%Y%m%d_%H%M%S 2>/dev/null || echo nodate)
    cp /HBpersistence/PagSWAct.002 "${USBROOT}/PagSWAct_backup_${TS}.002" 2>/dev/null
fi
for obs in /HBpersistence/CustomBootscreen_*.bin; do
    [ -f "$obs" ] && cp "$obs" "${USBROOT}/${obs##*/}.bak" 2>/dev/null
done
if [ -f "${USBROOT}/PagSWAct.002" ]; then
    cp "${USBROOT}/PagSWAct.002" /HBpersistence/PagSWAct.002 2>&1
    touch /HBpersistence/DBGModeActive 2>&1
fi
for bs in "${USBROOT}"/CustomBootscreen_*.bin; do
    [ -f "$bs" ] && cp "$bs" /HBpersistence/ 2>/dev/null
done
echo "PCM-Forge done" > "${USBROOT}/pcm_ran.txt" 2>/dev/null
# --- status splash: DONE ---
touch "$FS_FLAG" 2>/dev/null; [ -n "$FS_PID" ] && wait "$FS_PID" 2>/dev/null
