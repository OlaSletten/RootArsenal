@echo off
rem ==============================================================================
rem  RootArsenal v2.5 - Windows ADB Companion & Launcher
rem  Compatible with Windows 10/11 (CMD, PowerShell, Windows Terminal)
rem  Universal Android Superuser Suite (Magisk / KernelSU / APatch / SUSFS)
rem ==============================================================================

chcp 65001 >nul
title RootArsenal v2.5 - Windows ADB Launcher
color 0B
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "ADB_BIN=adb"

echo.
echo  ==============================================================================
echo   ⚡ ROOT ARSENAL v2.5 - WINDOWS ADB RUNNER
echo   On-Device Root Crawler, Module Flasher, Hardware Tuner ^& Shizuku Hub
echo  ==============================================================================
echo.

rem ------------------------------------------------------------------------------
rem  Step 1: Locate ADB Binary
rem ------------------------------------------------------------------------------
where adb >nul 2>nul
if %errorlevel% equ 0 (
    set "ADB_BIN=adb"
    goto :ADB_FOUND
)

if exist "%SCRIPT_DIR%adb.exe" (
    set "ADB_BIN=%SCRIPT_DIR%adb.exe"
    goto :ADB_FOUND
)
if exist "%SCRIPT_DIR%platform-tools\adb.exe" (
    set "ADB_BIN=%SCRIPT_DIR%platform-tools\adb.exe"
    goto :ADB_FOUND
)
if exist "%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe" (
    set "ADB_BIN=%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"
    goto :ADB_FOUND
)
if exist "C:\platform-tools\adb.exe" (
    set "ADB_BIN=C:\platform-tools\adb.exe"
    goto :ADB_FOUND
)

echo [!] 'adb.exe' was not found in PATH or standard Android SDK directories.
echo [*] Would you like to automatically download Google Android Platform-Tools now?
set /p "DL_ADB=[Y/N] (Default Y): "
if /i "%DL_ADB%"=="N" (
    echo [!] Please install ADB or place adb.exe in this folder and run again.
    pause
    exit /b 1
)

echo [*] Downloading official Google platform-tools for Windows...
powershell -Command "Invoke-WebRequest -Uri 'https://dl.google.com/android/repository/platform-tools-latest-windows.zip' -OutFile '%SCRIPT_DIR%platform-tools.zip'"
if not exist "%SCRIPT_DIR%platform-tools.zip" (
    echo [!] Download failed. Please download ADB manually from developer.android.com.
    pause
    exit /b 1
)
echo [*] Extracting platform-tools...
powershell -Command "Expand-Archive -Path '%SCRIPT_DIR%platform-tools.zip' -DestinationPath '%SCRIPT_DIR%' -Force"
del /f /q "%SCRIPT_DIR%platform-tools.zip" >nul 2>nul
if exist "%SCRIPT_DIR%platform-tools\adb.exe" (
    set "ADB_BIN=%SCRIPT_DIR%platform-tools\adb.exe"
    echo [+] Successfully extracted ADB!
) else (
    echo [!] Extraction failed.
    pause
    exit /b 1
)

:ADB_FOUND
echo [+] Using ADB binary: %ADB_BIN%

rem ------------------------------------------------------------------------------
rem  Step 2: Check Connected Device
rem ------------------------------------------------------------------------------
echo [*] Checking connected Android devices over USB/Wi-Fi ADB...
"%ADB_BIN%" start-server >nul 2>nul

for /f "tokens=1,2" %%A in ('"%ADB_BIN%" devices ^| findstr /v "List of devices"') do (
    if "%%B"=="device" (
        set "DEVICE_ID=%%A"
        goto :DEV_CONNECTED
    ) else if "%%B"=="unauthorized" (
        echo [!] Device %%A is UNAUTHORIZED!
        echo [!] Please unlock your phone screen and tap "Always Allow from this computer".
        pause
        goto :ADB_FOUND
    )
)

echo.
echo [!] No authorized Android device found!
echo [i] Please ensure:
echo     1. USB debugging is enabled in Developer Options on your phone.
echo     2. Your phone is connected via USB cable (or wireless ADB).
echo     3. You accepted the "Allow USB Debugging" prompt on your phone screen.
echo.
pause
exit /b 1

:DEV_CONNECTED
echo [+] Target Device Connected: %DEVICE_ID%

rem ------------------------------------------------------------------------------
rem  Step 3: Check Superuser / Root Access
rem ------------------------------------------------------------------------------
echo [*] Verifying superuser (root) privileges on device...
"%ADB_BIN%" -s %DEVICE_ID% shell "su -c id" 2>nul | findstr "uid=0" >nul
if %errorlevel% neq 0 (
    echo [!] Superuser check failed or permission prompt was not granted.
    echo [!] Please check your phone screen to grant Root access to ADB Shell in Magisk/KernelSU.
    pause
) else (
    echo [+] Superuser (UID=0 root) confirmed!
)

rem ------------------------------------------------------------------------------
rem  Step 4: Launch Menu
rem ------------------------------------------------------------------------------
:MAIN_MENU
cls
echo  ==============================================================================
echo   ⚡ ROOT ARSENAL v2.5 - WINDOWS ADB DASHBOARD
echo   Device: %DEVICE_ID%
echo  ==============================================================================
echo.
echo   [01]  🚀 Launch Full Interactive RootArsenal TUI (Live via Device Termux)
echo   [02]  🐍 Run Native Windows Python RootArsenal (--adb mode)
echo   [03]  📊 Live Root & Hardware Telemetry (Snapdragon 865, Battery, Magisk, SELinux)
echo   [04]  📦 Install APK from PC via Root PM (Silent pm install)
echo   [05]  ⚡ Flash Magisk / KernelSU Module ZIP from PC (Direct magisk install)
echo   [06]  🛡️ Start Shizuku Service via Root (No Wireless ADB Pairing Needed)
echo   [07]  🔄 Soft-Restart Zygote (Reload Zygisk/LSPosed in ~5s without Reboot)
echo   [08]  💾 Backup All Device Modules ^& magisk.db to PC
echo   [09]  💻 Open Direct Root Shell (su)
echo   [10]  ❌ Exit
echo.
echo  ==============================================================================
set /p "CHOICE=Select an option [01-10] + Enter (Default 01): "
if "%CHOICE%"=="" set "CHOICE=01"

if "%CHOICE%"=="01" goto :RUN_TERMUX_REMOTE
if "%CHOICE%"=="1"  goto :RUN_TERMUX_REMOTE
if "%CHOICE%"=="02" goto :RUN_WINDOWS_PYTHON
if "%CHOICE%"=="2"  goto :RUN_WINDOWS_PYTHON
if "%CHOICE%"=="03" goto :SHOW_TELEMETRY
if "%CHOICE%"=="3"  goto :SHOW_TELEMETRY
if "%CHOICE%"=="04" goto :INSTALL_APK_PC
if "%CHOICE%"=="4"  goto :INSTALL_APK_PC
if "%CHOICE%"=="05" goto :FLASH_MODULE_PC
if "%CHOICE%"=="5"  goto :FLASH_MODULE_PC
if "%CHOICE%"=="06" goto :START_SHIZUKU
if "%CHOICE%"=="6"  goto :START_SHIZUKU
if "%CHOICE%"=="07" goto :RESTART_ZYGOTE
if "%CHOICE%"=="7"  goto :RESTART_ZYGOTE
if "%CHOICE%"=="08" goto :BACKUP_TO_PC
if "%CHOICE%"=="8"  goto :BACKUP_TO_PC
if "%CHOICE%"=="09" goto :OPEN_ROOT_SHELL
if "%CHOICE%"=="9"  goto :OPEN_ROOT_SHELL
if "%CHOICE%"=="10" exit /b 0

echo [!] Invalid choice.
timeout /t 2 >nul
goto :MAIN_MENU

:RUN_TERMUX_REMOTE
cls
echo [*] Launching RootArsenal interactive session via ADB...
echo [*] Keyboard shortcuts: Arrow keys, Enter, 2-digit numbers + Enter, [q] to exit.
echo.
"%ADB_BIN%" -s %DEVICE_ID% shell -t "su -c 'PATH=/data/data/com.termux/files/usr/bin:/system/bin:/system/xbin:$PATH LD_LIBRARY_PATH=/data/data/com.termux/files/usr/lib root-arsenal'"
goto :MAIN_MENU

:RUN_WINDOWS_PYTHON
cls
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [!] Python is not installed or not in PATH on Windows.
    echo [!] Recommended: Use Option 01 to run directly via ADB with 0 dependencies!
    pause
    goto :MAIN_MENU
)
echo [*] Starting RootArsenal in Native Windows Python mode with ADB backend...
python "%SCRIPT_DIR%root_arsenal.py" --adb --device %DEVICE_ID%
pause
goto :MAIN_MENU

:SHOW_TELEMETRY
cls
echo [*] Querying device telemetry from %DEVICE_ID%...
echo.
"%ADB_BIN%" -s %DEVICE_ID% shell -t "su -c 'PATH=/data/data/com.termux/files/usr/bin:/system/bin:$PATH root-arsenal --telemetry'"
echo.
pause
goto :MAIN_MENU

:INSTALL_APK_PC
cls
echo ==============================================================================
echo  Install APK from PC via ADB ^& Root PM
echo ==============================================================================
echo.
echo Drag and drop an .apk file into this window, or type its path:
set /p "APK_FILE=APK Path: "
set "APK_FILE=%APK_FILE:"=%"
if not exist "%APK_FILE%" (
    echo [!] File not found: %APK_FILE%
    pause
    goto :MAIN_MENU
)
echo [*] Sideloading and installing %APK_FILE% via ADB root PM...
"%ADB_BIN%" -s %DEVICE_ID% install -r -d "%APK_FILE%"
echo.
pause
goto :MAIN_MENU

:FLASH_MODULE_PC
cls
echo ==============================================================================
echo  Flash Magisk / KernelSU / APatch Module ZIP from PC
echo ==============================================================================
echo.
echo Drag and drop a module .zip file into this window, or type its path:
set /p "MOD_ZIP=Module ZIP Path: "
set "MOD_ZIP=%MOD_ZIP:"=%"
if not exist "%MOD_ZIP%" (
    echo [!] File not found: %MOD_ZIP%
    pause
    goto :MAIN_MENU
)
echo [*] Pushing module to /data/local/tmp/arsenal_pc_mod.zip...
"%ADB_BIN%" -s %DEVICE_ID% push "%MOD_ZIP%" /data/local/tmp/arsenal_pc_mod.zip
echo [*] Flashing module systemlessly via Magisk...
"%ADB_BIN%" -s %DEVICE_ID% shell "su -c 'magisk --install-module /data/local/tmp/arsenal_pc_mod.zip || /debug_ramdisk/magisk --install-module /data/local/tmp/arsenal_pc_mod.zip || ksud module install /data/local/tmp/arsenal_pc_mod.zip; rm -f /data/local/tmp/arsenal_pc_mod.zip'"
echo.
pause
goto :MAIN_MENU

:START_SHIZUKU
cls
echo [*] Starting Shizuku service via device root...
"%ADB_BIN%" -s %DEVICE_ID% shell "su -c 'PATH=/data/data/com.termux/files/usr/bin:/system/bin:$PATH root-dexopt 2>/dev/null; APK=\$(pm path moe.shizuku.privileged.api | head -n1 | cut -d: -f2); if [ -n \"\$APK\" ]; then /system/bin/app_process -Djava.class.path=\"\$APK\" /system/bin --nice-name=shizuku_server moe.shizuku.starter.ServiceStarter ^& echo \"[+] Dispatched Shizuku starter with root privileges!\"; else echo \"[!] Shizuku app is not installed\"; fi'"
echo.
pause
goto :MAIN_MENU

:RESTART_ZYGOTE
cls
echo [*] Triggering Zygote soft-restart (Reloads Zygisk, LSPosed, and overlays in ~5s)...
"%ADB_BIN%" -s %DEVICE_ID% shell "su -c 'setprop ctl.restart zygote && echo [+] Zygote soft-restart signal sent!'"
echo.
pause
goto :MAIN_MENU

:BACKUP_TO_PC
cls
set "PC_BACKUP_DIR=%SCRIPT_DIR%backups"
if not exist "%PC_BACKUP_DIR%" mkdir "%PC_BACKUP_DIR%"
echo [*] Creating full backup of /data/adb/modules and magisk.db on device...
"%ADB_BIN%" -s %DEVICE_ID% shell "su -c 'tar -czf /data/local/tmp/root_backup.tar.gz /data/adb/modules /data/adb/service.d /data/adb/post-fs-data.d /data/adb/magisk.db 2>/dev/null && chmod 644 /data/local/tmp/root_backup.tar.gz'"
for /f "tokens=1-4 delims=/:. " %%A in ("%date% %time%") do set "TS=%%A%%B%%C_%%D"
set "DEST_PC=%PC_BACKUP_DIR%\root_backup_%TS%.tar.gz"
echo [*] Pulling backup to PC: %DEST_PC%...
"%ADB_BIN%" -s %DEVICE_ID% pull /data/local/tmp/root_backup.tar.gz "%DEST_PC%"
"%ADB_BIN%" -s %DEVICE_ID% shell "su -c 'rm -f /data/local/tmp/root_backup.tar.gz'"
echo [+] Backup saved to PC at: %DEST_PC%
echo.
pause
goto :MAIN_MENU

:OPEN_ROOT_SHELL
cls
echo [*] Spawning direct Android superuser shell (su -mm)...
echo [*] Type 'exit' to return.
echo.
"%ADB_BIN%" -s %DEVICE_ID% shell -t "su -mm"
goto :MAIN_MENU
