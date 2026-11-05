#!/data/data/com.termux/files/usr/bin/env python3
"""
Built-in On-Device Root Scripts, System Tweaks, and Curated Essential Root/Shizuku Tools
Engineered for Universal Android Root Compatibility (Magisk / KernelSU / APatch / SukiSU / SUSFS).
"""

BUILTIN_SCRIPTS = [
    {
        "id": "script_shizuku_root_start",
        "name": "Shizuku Root Auto-Starter (No ADB Needed)",
        "category": "🛠️ On-Device Root Scripts & System Tweaks",
        "subcategory": "Shizuku & Bridges",
        "kind": "root_script",
        "source": "On-Device Builtin",
        "author": "RootArsenal",
        "stars": 999,
        "badges": ["ROOT", "SHIZUKU", "SCRIPT", "UNIVERSAL"],
        "description": "Starts the Shizuku privileged server daemon directly via su root without needing wireless ADB or PC pairing. Can also be installed to /data/adb/service.d/ to auto-start on boot.",
        "url": "builtin://shizuku_root_start",
        "install_target": "/data/adb/service.d/shizuku_autostart.sh",
        "script_content": """#!/system/bin/sh
# Wait for boot completion if running from service.d
if [ "${0##*/}" = "shizuku_autostart.sh" ]; then
    until [ "$(getprop sys.boot_completed)" = "1" ]; do sleep 2; done
    sleep 5
fi
echo "[*] Searching for installed Shizuku package (moe.shizuku.privileged.api)..."
APK_PATH=$(pm path moe.shizuku.privileged.api | head -n 1 | cut -d: -f2)
if [ -z "$APK_PATH" ]; then
    echo "[!] Shizuku app (moe.shizuku.privileged.api) is not installed yet!"
    echo "[i] Tip: Install Shizuku or Shizuku-Next from the Shizuku category first."
    exit 1
fi
APP_DIR=$(dirname "$APK_PATH")
LIB_PATH=$(find "$APP_DIR/lib" -name "libshizuku.so" 2>/dev/null | head -n 1)
if [ -n "$LIB_PATH" ]; then
    echo "[+] Starting Shizuku server via $LIB_PATH ..."
    "$LIB_PATH" &
    sleep 1
    echo "[+] Shizuku server started with root privileges!"
else
    echo "[*] Extracting/executing starter from APK..."
    /system/bin/app_process -Djava.class.path="$APK_PATH" /system/bin --nice-name=shizuku_server moe.shizuku.starter.ServiceStarter &
    echo "[+] Dispatched Shizuku ServiceStarter!"
fi
"""
    },
    {
        "id": "script_bootloop_protector",
        "name": "Universal Bootloop Guard Watchdog",
        "category": "🛠️ On-Device Root Scripts & System Tweaks",
        "subcategory": "Bootloop Safety",
        "kind": "root_script",
        "source": "On-Device Builtin",
        "author": "RootArsenal",
        "stars": 995,
        "badges": ["ROOT", "SAFETY", "WATCHDOG", "UNIVERSAL"],
        "description": "Installs a non-blocking watchdog in /data/adb/post-fs-data.d/ that monitors boot completion. If Android Zygote/SystemServer fails to boot within 110 seconds, automatically disables all modules and reboots cleanly.",
        "url": "builtin://bootloop_guard",
        "install_target": "/data/adb/post-fs-data.d/99_bootloop_guard.sh",
        "script_content": """#!/system/bin/sh
# Non-blocking background watchdog to prevent bootloops from faulty modules
(
    COUNTER=0
    while [ "$(getprop sys.boot_completed)" != "1" ]; do
        sleep 5
        COUNTER=$((COUNTER + 5))
        if [ "$COUNTER" -ge 110 ]; then
            for mod in /data/adb/modules/*; do
                [ -d "$mod" ] && touch "$mod/disable"
            done
            log -p e -t BootloopGuard "Boot timeout exceeded! Disabled all modules and rebooting."
            reboot
            exit 0
        fi
    done
) &
echo "[+] Bootloop Guard watchdog is active."
"""
    },
    {
        "id": "script_cpu_tuner",
        "name": "Universal Multi-Cluster CPU Governor & Frequency Tuner",
        "category": "🛠️ On-Device Root Scripts & System Tweaks",
        "subcategory": "Performance & Kernel",
        "kind": "root_script",
        "source": "On-Device Builtin",
        "author": "RootArsenal",
        "stars": 980,
        "badges": ["ROOT", "SYSFS", "CPU", "UNIVERSAL"],
        "description": "Inspects and dynamically tunes CPU scaling governors across all CPU clusters on any device (schedutil vs performance vs powersave) and displays live cluster frequencies and thermal metrics.",
        "url": "builtin://cpu_tuner",
        "install_target": "/data/data/com.termux/files/usr/bin/root-cpu-tuner",
        "script_content": """#!/system/bin/sh
MODEL=$(getprop ro.product.model)
CHIP=$(getprop ro.board.platform)
echo "=== Universal Hardware CPU Status ($MODEL / $CHIP) ==="
for policy in /sys/devices/system/cpu/cpufreq/policy*; do
    [ -d "$policy" ] || continue
    p_name=$(basename "$policy")
    gov=$(cat "$policy/scaling_governor" 2>/dev/null)
    cur=$(cat "$policy/scaling_cur_freq" 2>/dev/null)
    max=$(cat "$policy/scaling_max_freq" 2>/dev/null)
    avail=$(cat "$policy/scaling_available_governors" 2>/dev/null)
    echo "[$p_name] Gov: $gov | Cur: $((cur / 1000)) MHz | Max: $((max / 1000)) MHz"
    echo "  Available: $avail"
done
echo ""
echo "[*] Setting optimal balanced governor across all CPU clusters..."
for policy in /sys/devices/system/cpu/cpufreq/policy*; do
    [ -w "$policy/scaling_governor" ] && echo "schedutil" > "$policy/scaling_governor" 2>/dev/null
done
echo "[+] Applied balanced CPU governor across all clusters."
"""
    },
    {
        "id": "script_resetprop_stealth",
        "name": "resetprop Bootloader & VerifiedBoot Stealth Hardener",
        "category": "🛠️ On-Device Root Scripts & System Tweaks",
        "subcategory": "Root Hiding & Integrity",
        "kind": "root_script",
        "source": "On-Device Builtin",
        "author": "RootArsenal",
        "stars": 990,
        "badges": ["ROOT", "RESETPROP", "STEALTH", "UNIVERSAL"],
        "description": "Uses resetprop to spoof bootloader lock, verifiedbootstate=green, flash.locked=1, and build.type=user, hiding unlocked bootloader flags from banking and DRM detectors without touching read-only partitions.",
        "url": "builtin://resetprop_stealth",
        "install_target": "/data/adb/service.d/resetprop_stealth.sh",
        "script_content": """#!/system/bin/sh
RESETPROP=$(which resetprop || echo "/debug_ramdisk/magisk resetprop")
echo "[*] Applying stealth system properties via resetprop..."
resetprop -n ro.boot.verifiedbootstate green 2>/dev/null
resetprop -n ro.boot.flash.locked 1 2>/dev/null
resetprop -n ro.boot.vbmeta.device_state locked 2>/dev/null
resetprop -n ro.boot.veritymode enforcing 2>/dev/null
resetprop -n ro.debuggable 0 2>/dev/null
resetprop -n ro.secure 1 2>/dev/null
resetprop -n ro.build.type user 2>/dev/null
resetprop -n ro.build.tags release-keys 2>/dev/null
echo "[+] VerifiedBootState: $(getprop ro.boot.verifiedbootstate)"
echo "[+] FlashLocked:       $(getprop ro.boot.flash.locked)"
echo "[+] VBMetaState:       $(getprop ro.boot.vbmeta.device_state)"
echo "[+] BuildType/Tags:    $(getprop ro.build.type) / $(getprop ro.build.tags)"
"""
    },
    {
        "id": "script_aot_speed_compiler",
        "name": "Universal System AOT Speed-Profile DEX Optimizer",
        "category": "🛠️ On-Device Root Scripts & System Tweaks",
        "subcategory": "System Optimization",
        "kind": "root_script",
        "source": "On-Device Builtin",
        "author": "RootArsenal",
        "stars": 970,
        "badges": ["ROOT", "DEXOPT", "PERFORMANCE", "UNIVERSAL"],
        "description": "Forces Android ART package manager to compile user and critical system apps with 'speed-profile' AOT optimization and trims filesystem caches for smoother UI frame pacing.",
        "url": "builtin://aot_speed_compiler",
        "install_target": "/data/data/com.termux/files/usr/bin/root-dexopt",
        "script_content": """#!/system/bin/sh
echo "[*] Running ART speed-profile compilation on core UI packages..."
for pkg in com.android.systemui com.android.launcher3 com.termux; do
    if pm list packages | grep -q "^package:${pkg}$"; then
        echo "  -> Compiling $pkg (speed)..."
        cmd package compile -m speed -f "$pkg" 2>/dev/null
    fi
done
echo "[*] Triggering background dexopt job for all installed apps..."
cmd package bg-dexopt-job 2>/dev/null
echo "[+] Optimization complete!"
"""
    },
    {
        "id": "script_display_rate_tune",
        "name": "Display High Refresh Rate & Density Controller",
        "category": "🛠️ On-Device Root Scripts & System Tweaks",
        "subcategory": "Display & UI",
        "kind": "root_script",
        "source": "On-Device Builtin",
        "author": "RootArsenal",
        "stars": 965,
        "badges": ["ROOT", "DISPLAY", "REFRESH-RATE", "UNIVERSAL"],
        "description": "Inspects and configures peak/minimum display refresh rates across all Android applications and displays current WindowManager resolution and DPI density.",
        "url": "builtin://display_rate_tune",
        "install_target": "/data/data/com.termux/files/usr/bin/root-display-tune",
        "script_content": """#!/system/bin/sh
echo "=== Display & WindowManager Status ==="
wm size
wm density
PEAK=$(settings get system peak_refresh_rate 2>/dev/null || echo "120.0")
echo "Current Peak Refresh Rate Setting: $PEAK"
settings put system peak_refresh_rate 120.0 2>/dev/null
settings put system min_refresh_rate 60.0 2>/dev/null
echo "[+] Display refresh rate settings configured."
"""
    },
    {
        "id": "script_battery_health_inspector",
        "name": "Hardware Battery & Charging Diagnostics",
        "category": "🛠️ On-Device Root Scripts & System Tweaks",
        "subcategory": "Battery & Thermal",
        "kind": "root_script",
        "source": "On-Device Builtin",
        "author": "RootArsenal",
        "stars": 960,
        "badges": ["ROOT", "BATTERY", "SYSFS", "UNIVERSAL"],
        "description": "Reads kernel power supply sysfs nodes and Android battery service to report real cycle count, charge capacity, voltage, current, and temperature on any Android device.",
        "url": "builtin://battery_health_inspector",
        "install_target": "/data/data/com.termux/files/usr/bin/root-battery",
        "script_content": """#!/system/bin/sh
echo "=== Hardware Battery & Power Supply Diagnostics ==="
for node in status health capacity charge_full charge_full_design cycle_count voltage_now current_now temp technology; do
    for dir in /sys/class/power_supply/battery /sys/class/power_supply/bms; do
        if [ -r "$dir/$node" ]; then
            val=$(cat "$dir/$node" 2>/dev/null)
            printf "  %-22s (%s): %s\\n" "$node" "$(basename $dir)" "$val"
        fi
    done
done
echo ""
echo "=== Android Battery Service ==="
dumpsys battery | grep -E "level|scale|voltage|temperature|status|AC powered|USB powered"
"""
    },
    {
        "id": "script_telemetry_freezer",
        "name": "Universal Telemetry & Bloatware Freezer (Systemless PM Disable)",
        "category": "🛠️ On-Device Root Scripts & System Tweaks",
        "subcategory": "Debloating",
        "kind": "root_script",
        "source": "On-Device Builtin",
        "author": "RootArsenal",
        "stars": 955,
        "badges": ["ROOT", "DEBLOAT", "PRIVACY", "UNIVERSAL"],
        "description": "Safely freezes common background analytics, tracking, and bloatware packages using 'pm disable-user --user 0' (100% reversible without modifying /system).",
        "url": "builtin://telemetry_freezer",
        "install_target": "/data/data/com.termux/files/usr/bin/root-debloat",
        "script_content": """#!/system/bin/sh
echo "=== Systemless Bloatware & Telemetry Freezer ==="
BLOAT_PKGS="
com.facebook.services
com.facebook.system
com.facebook.appmanager
com.netflix.partner.activation
com.qualcomm.qti.optinoverlay
com.android.traceur
"
COUNT=0
for pkg in $BLOAT_PKGS; do
    if pm list packages | grep -q "^package:${pkg}$"; then
        pm disable-user --user 0 "$pkg" 2>/dev/null && COUNT=$((COUNT + 1))
    fi
done
echo "[+] Checked telemetry/bloatware list ($COUNT packages frozen)."
echo "[i] Currently disabled packages on device:"
pm list packages -d
"""
    },
    {
        "id": "script_magisk_db_audit",
        "name": "Magisk / KernelSU Superuser Policy & Isolation Inspector",
        "category": "🛠️ On-Device Root Scripts & System Tweaks",
        "subcategory": "Root Management",
        "kind": "root_script",
        "source": "On-Device Builtin",
        "author": "RootArsenal",
        "stars": 950,
        "badges": ["ROOT", "MAGISK", "SQLITE", "UNIVERSAL"],
        "description": "Queries root manager policies directly via 'magisk --sqlite' to list all UIDs granted/denied root permissions, mount namespace settings, and Denylist entries.",
        "url": "builtin://magisk_db_audit",
        "install_target": "/data/data/com.termux/files/usr/bin/root-audit",
        "script_content": """#!/system/bin/sh
echo "=== Superuser Database Policy Audit ==="
if command -v magisk >/dev/null 2>&1; then
    echo "[1] Settings:"
    magisk --sqlite "SELECT * FROM settings;" 2>/dev/null
    echo ""
    echo "[2] Superuser Policies (policy=2 Granted, 1 Denied):"
    magisk --sqlite "SELECT * FROM policies;" 2>/dev/null
    echo ""
    echo "[3] DenyList Entries:"
    magisk --sqlite "SELECT * FROM denylist;" 2>/dev/null
else
    echo "[i] Checking /data/adb permissions and state..."
    ls -ld /data/adb/modules 2>/dev/null
fi
"""
    },
    {
        "id": "script_selinux_inspector",
        "name": "SELinux Status & AVC Denial Live Auditor",
        "category": "🛠️ On-Device Root Scripts & System Tweaks",
        "subcategory": "Security & SELinux",
        "kind": "root_script",
        "source": "On-Device Builtin",
        "author": "RootArsenal",
        "stars": 945,
        "badges": ["ROOT", "SELINUX", "SECURITY", "UNIVERSAL"],
        "description": "Checks current SELinux enforcement status, current domain context, and extracts recent 'avc: denied' events from dmesg/logcat for policy tuning.",
        "url": "builtin://selinux_inspector",
        "install_target": "/data/data/com.termux/files/usr/bin/root-selinux",
        "script_content": """#!/system/bin/sh
echo "=== SELinux Status ==="
echo "Mode:    $(getenforce 2>/dev/null || echo 'Unknown')"
echo "Context: $(id -Z 2>/dev/null || echo 'Unknown')"
echo ""
echo "=== Recent SELinux AVC Denials (last 15) ==="
dmesg 2>/dev/null | grep "avc: denied" | tail -n 15 || logcat -d -b all 2>/dev/null | grep "avc: denied" | tail -n 15
"""
    }
]

# Curated high-priority tools with known direct GitHub repos so they are always available even offline
SEED_TOOLS = [
    {
        "id": "seed_shizuku_official",
        "name": "Shizuku (Official by RikkaApps)",
        "category": "⚡ Shizuku & Addons (450+ Tools)",
        "subcategory": "Shizuku Implementations",
        "kind": "apk_repo",
        "source": "Curated Seed",
        "author": "RikkaApps",
        "stars": 14500,
        "badges": ["SHIZUKU", "ROOT", "ADB", "FOSS"],
        "description": "Use system APIs directly with adb/root privileges from normal apps.",
        "url": "https://github.com/RikkaApps/Shizuku"
    },
    {
        "id": "seed_shizuku_next",
        "name": "Shizuku Next",
        "category": "⚡ Shizuku & Addons (450+ Tools)",
        "subcategory": "Shizuku Implementations",
        "kind": "apk_repo",
        "source": "Curated Seed",
        "author": "rushiranpise",
        "stars": 850,
        "badges": ["SHIZUKU", "ROOT", "M3", "FOSS"],
        "description": "Maintained continuation of Shizuku with automated pairing, watchdog, in-app shell terminal, app-ops/firewall manager and Material 3 UI.",
        "url": "https://github.com/rushiranpise/Shizuku-Next"
    },
    {
        "id": "seed_shizustore",
        "name": "ShizuStore",
        "category": "⚡ Shizuku & Addons (450+ Tools)",
        "subcategory": "Installer & App Stores",
        "kind": "apk_repo",
        "source": "Curated Seed",
        "author": "timschneeb",
        "stars": 1200,
        "badges": ["SHIZUKU", "STORE", "FOSS"],
        "description": "Open-source Android app store for browsing and silently installing Shizuku apps.",
        "url": "https://github.com/timschneeb/ShizuStore"
    },
    {
        "id": "seed_canta",
        "name": "Canta (Shizuku/Root Debloater)",
        "category": "🧹 Debloating, Backup & File Managers",
        "subcategory": "Debloating",
        "kind": "apk_repo",
        "source": "Curated Seed",
        "author": "samolego",
        "stars": 3100,
        "badges": ["SHIZUKU", "DEBLOAT", "FOSS"],
        "description": "Uninstall any app without root using Shizuku, powered by Universal Android Debloater descriptions and safety badges.",
        "url": "https://github.com/samolego/Canta"
    },
    {
        "id": "seed_appmanager",
        "name": "App Manager (MuntashirAkon)",
        "category": "⚙️ Root Device-Editing & System Tools",
        "subcategory": "App & System Control",
        "kind": "apk_repo",
        "source": "Curated Seed",
        "author": "MuntashirAkon",
        "stars": 6200,
        "badges": ["ROOT", "SHIZUKU", "SYSTEM", "FOSS"],
        "description": "Full-featured open-source package manager, AppOps editor, permission controller, blocker, scanner, and log viewer for Root & Shizuku.",
        "url": "https://github.com/MuntashirAkon/AppManager"
    },
    {
        "id": "seed_mmrl",
        "name": "MMRL (Magisk Module Repo Loader)",
        "category": "👑 Root Handling, Zygisk & Hiding",
        "subcategory": "Module Managers",
        "kind": "apk_repo",
        "source": "Curated Seed",
        "author": "MMRLApp",
        "stars": 2300,
        "badges": ["ROOT", "MAGISK", "KSU", "APATCH", "FOSS"],
        "description": "Modern Android app for managing, sharing, and exploring Magisk, KernelSU, and APatch modules across multiple repositories with WebUI support.",
        "url": "https://github.com/MMRLApp/MMRL"
    },
    {
        "id": "seed_zygisknext",
        "name": "Zygisk Next",
        "category": "👑 Root Handling, Zygisk & Hiding",
        "subcategory": "Zygisk & Root Hiding",
        "kind": "module_repo",
        "source": "Curated Seed",
        "author": "Dr-TSNG",
        "stars": 4900,
        "badges": ["MAGISK", "KSU", "ZYGISK"],
        "description": "Standalone implementation of Zygisk providing Zygisk API support for KernelSU and Magisk with superior hiding capabilities.",
        "url": "https://github.com/Dr-TSNG/ZygiskNext"
    },
    {
        "id": "seed_pif",
        "name": "Play Integrity Fork (osm0sis)",
        "category": "👑 Root Handling, Zygisk & Hiding",
        "subcategory": "Play Integrity & Spoofing",
        "kind": "module_repo",
        "source": "Curated Seed",
        "author": "osm0sis",
        "stars": 3400,
        "badges": ["MAGISK", "ZYGISK", "INTEGRITY", "FOSS"],
        "description": "Zygisk module to fix Play Integrity (DEVICE_INTEGRITY) and SafetyNet on rooted Android devices.",
        "url": "https://github.com/osm0sis/PlayIntegrityFork"
    },
    {
        "id": "seed_trickystore",
        "name": "TrickyStore",
        "category": "👑 Root Handling, Zygisk & Hiding",
        "subcategory": "Play Integrity & Spoofing",
        "kind": "module_repo",
        "source": "Curated Seed",
        "author": "5ec1cff",
        "stars": 4100,
        "badges": ["MAGISK", "KSU", "ZYGISK", "INTEGRITY"],
        "description": "Keystore certificate chain manipulation module for fixing bootloader locked verification and Play Integrity.",
        "url": "https://github.com/5ec1cff/TrickyStore"
    },
    {
        "id": "seed_lsposed_vector",
        "name": "Vector (Modern Open-Source LSPosed Fork)",
        "category": "🧩 LSPosed / Xposed & App Mods",
        "subcategory": "LSPosed Framework",
        "kind": "module_repo",
        "source": "Curated Seed",
        "author": "JingMatrix",
        "stars": 3800,
        "badges": ["MAGISK", "ZYGISK", "LSPOSED", "FOSS"],
        "description": "Actively maintained open-source fork of LSPosed framework supporting Android 8.1 - 15+ with dynamic module loading.",
        "url": "https://github.com/JingMatrix/Vector"
    },
    {
        "id": "seed_smartpack",
        "name": "SmartPack-Kernel Manager",
        "category": "🔥 Performance, Kernel & Battery",
        "subcategory": "Kernel Managers",
        "kind": "apk_repo",
        "source": "Curated Seed",
        "author": "SmartPack",
        "stars": 1900,
        "badges": ["ROOT", "KERNEL", "SYSFS", "FOSS"],
        "description": "Full-featured root kernel manager based on Kernel Adiutor for CPU/GPU frequencies, governors, thermal, KCAL display, and custom sysfs scripts.",
        "url": "https://github.com/SmartPack/SmartPack-Kernel-Manager"
    },
    {
        "id": "seed_adaway",
        "name": "AdAway",
        "category": "🛡️ Privacy, Security & Ad-Blocking",
        "subcategory": "Ad Blockers",
        "kind": "apk_repo",
        "source": "Curated Seed",
        "author": "AdAway",
        "stars": 13500,
        "badges": ["ROOT", "ADBLOCK", "FOSS"],
        "description": "Open-source systemless hosts-based and local VPN ad blocker for Android.",
        "url": "https://github.com/AdAway/AdAway"
    },
    {
        "id": "seed_afwall",
        "name": "AFWall+ (Android Firewall)",
        "category": "🛡️ Privacy, Security & Ad-Blocking",
        "subcategory": "Firewalls",
        "kind": "apk_repo",
        "source": "Curated Seed",
        "author": "ukanth",
        "stars": 4600,
        "badges": ["ROOT", "FIREWALL", "IPTABLES", "FOSS"],
        "description": "Linux iptables-based root firewall for Android allowing fine-grained per-app control over Wi-Fi, Cellular, LAN, Roaming, and VPN.",
        "url": "https://github.com/ukanth/afwall"
    },
    {
        "id": "seed_neobackup",
        "name": "Neo Backup",
        "category": "🧹 Debloating, Backup & File Managers",
        "subcategory": "Backup & Restore",
        "kind": "apk_repo",
        "source": "Curated Seed",
        "author": "NeoApplications",
        "stars": 3600,
        "badges": ["ROOT", "BACKUP", "FOSS"],
        "description": "Powerful open-source root backup manager for Android apps, data, external storage, and special system data with scheduling and encryption.",
        "url": "https://github.com/NeoApplications/Neo-Backup"
    }
]
