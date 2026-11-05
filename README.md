# ⚡ RootArsenal v2.5

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Android%20%7C%20Termux%20%7C%20Windows%20ADB-orange.svg)](https://github.com)
[![Root Compatibility](https://img.shields.io/badge/Root-Magisk%20%7C%20KernelSU%20%7C%20APatch%20%7C%20SUSFS-brightgreen.svg)](https://github.com)
[![Tools Indexed](https://img.shields.io/badge/Tools-1%2C380%2B%20Indexed-purple.svg)](https://github.com)

**Universal Android Superuser & Root Intelligence Engine, Multi-Source Toolchain Crawler, Volume-Key Installer & Windows ADB Suite.**

RootArsenal crawls, verifies, indexes, downloads, and flashes tools for on-device superuser administration, device-editing, kernel tuning, Shizuku bridges, and systemless Magisk / KernelSU / APatch / SUSFS modules directly on Android (Termux) or from any Windows PC via ADB.

---

## 🌟 Key Capabilities

### 🔍 1. Massive Multi-Source Parallel Crawler (1,380+ Tools)
Indexes 29 live repository feeds across 8 major sources with deduplication, architecture scoring, and license badges:
- **Awesome Android Root**: All 16 primary categories (Root Managers, System Tweaks, Performance & Kernel, Privacy, Security, Ad-Blocking, App Mods, Debloating, File Management, Backup, Customization, Audio, Networking, Gaming, Development, Utilities).
- **Awesome Shizuku & Best Shizuku Apps**: 440+ Shizuku-powered root & wireless ADB applications, `rish` terminal tools, and companion frameworks.
- **Magisk-Modules-Alt-Repo (v2)**: Direct flashable module archives with online metadata and API compatibility requirements.
- **MMRL Repositories**: Community repositories (`ZG-R Hidden Gems` and `uonou/mmrl-repo`).
- **KernelSU & Temporary Root**: Curated tools for kernel-level superuser, SUSFS stealth patches, and locked-bootloader ephemeral root exploits.
- **GitHub Live API Topics**: `topic:magisk-module`, `topic:kernelsu-module`, `topic:shizuku`, `topic:lsposed-module`.
- **F-Droid Search & GitLab Metadata**: Live package discovery via F-Droid search API and GitLab `fdroiddata` source resolution.
- **On-Device Builtin Root Scripts**: 10 standalone systemless scripts for hardware tuning, stealth properties, and watchdog safety.

### 🎮 2. Dual-Mode Input Engine (Volume Keys & Multi-Digit Keyboard)
- **Hardware Volume Key Navigation** (reads Linux kernel `/dev/input/event*` with tactile haptic clicks):
  - `🔊 VOL+ (Short Tap)`: Navigate Up
  - `🔉 VOL- (Short Tap)`: Navigate Down
  - `🔊 VOL+ (Hold 0.45s)`: Open / Select / Install Now
  - `🔉 VOL- (Hold 0.45s)`: Cancel / Go Back
  - Press `m` anytime to switch to classic Magisk 2-button cycle mode (`VOL+` = Next, `VOL-` = Select).
- **Multi-Digit & Range Selection**:
  - Type 2+ digits (e.g. `12` or `145`) and press `[Enter]` to jump to and open any tool or action immediately.
  - Type ranges or comma lists (e.g. `1,4,12` or `5-10`) + `[Enter]` to batch-select multiple tools for one-click installation or download.
  - Press `g` with a typed number to jump the cursor without opening.
  - Press `/` in any category for instant live keyword filtering.

### 🛡️ 3. Safety Protocols & Dynamic Device Detection
- **Universal Architecture Scoring**: Dynamically queries device ABI (`arm64-v8a`, `armeabi-v7a`, `x86_64`) and selects matching releases.
- **Systemless Safety**: Strictly operates via `/data/adb/modules/` or OverlayFS; never remounts `/system` as read-write on system-as-root / EROFS.
- **Bootloop Guard Watchdog**: Automatic timeout watchdog disables modules if System Server hangs during boot.
- **Smart Post-Installation Shortcuts**:
  - APKs: Instant 1-tap options to Launch App, auto-grant runtime permissions (`pm grant`), or view App Info.
  - Modules: Instant 1-tap option to Soft-Restart Zygote (`setprop ctl.restart zygote`) in ~5s without full kernel reboot.

### 🪟 4. Windows ADB Companion (`root-arsenal.exe` & `root-arsenal.bat`)
- Run RootArsenal from your Windows 10/11 PC over USB or Wi-Fi ADB.
- `root-arsenal.exe`: Native 64-bit console executable with Windows Terminal ANSI support.
- `root-arsenal.bat`: Full Windows batch dashboard for APK sideloading, Magisk ZIP flashing, device backups, and live telemetry.

---

## 🚀 Quick Start (Android / Termux)

### Prerequisites
Rooted Android device with **Magisk**, **Kitsune Mask**, **KernelSU**, **APatch**, or **SukiSU**.

```bash
# Clone the repository
git clone https://github.com/OlaSletten/RootArsenal.git ~/root-arsenal
cd ~/root-arsenal

# Make scripts executable and link global shortcuts
chmod +x *.py
ln -sf ~/root-arsenal/root_arsenal.py /data/data/com.termux/files/usr/bin/root-arsenal
ln -sf ~/root-arsenal/root_arsenal.py /data/data/com.termux/files/usr/bin/rarsenal

# Launch interactive UI
root-arsenal
```

### Command-Line Arguments
```bash
root-arsenal --telemetry       # View live CPU, battery, Magisk, and SELinux status
root-arsenal --categories      # List all 12 categories & tool counts
root-arsenal --search <query>  # Search local catalog and crawl GitHub/F-Droid live
root-arsenal --crawl           # Force full refresh of all 29 feeds
root-arsenal --backup          # Create full backup of modules & magisk.db (.tar.gz)
```

---

## 🪟 Quick Start (Windows via ADB)

1. Connect your phone to your PC via USB with **USB Debugging** enabled in Developer Options.
2. Ensure ADB has superuser permissions granted on your phone.
3. Open the `RootArsenal` folder on your PC.
4. Run either:
   - **`root-arsenal.exe`** (double-click for instant remote interactive session)
   - **`root-arsenal.bat`** (Windows batch dashboard menu)

---

## 🎛️ Live Control Center Actions

1. **`[01]`**: Start / Restart Shizuku Server via Root (no PC or wireless ADB needed)
2. **`[02]`**: Toggle SELinux Enforcement Mode (`Enforcing` ↔ `Permissive`)
3. **`[03]`**: Switch Hardware CPU Governor (`schedutil` / `performance` / `powersave`)
4. **`[04]`**: Configure Display Refresh Rate (`120Hz Forced` / `Adaptive`)
5. **`[05]`**: Apply `resetprop` Bootloader & VerifiedBoot Stealth Hardening
6. **`[06]`**: Audit Magisk / KernelSU SQLite Policies & Superuser Grants
7. **`[07]`**: Backup All Installed Modules & Root Scripts (`.tar.gz`)
8. **`[08]`**: Run ART `speed-profile` DEX Compilation on Core System Apps
9. **`[09]`**: Soft-Restart Zygote (`setprop ctl.restart zygote`)
10. **`[10]`**: Soft-Restart Android SystemUI
11. **`[12]`**: Flush RAM & Drop Linux Pagecaches (`sync && echo 3 > /proc/sys/vm/drop_caches`)
12. **`[12]`**: Emergency Safe-Mode (disables all Magisk/KernelSU modules)

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
Open-source, free to inspect, fork, and distribute.
