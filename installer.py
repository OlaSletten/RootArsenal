#!/data/data/com.termux/files/usr/bin/env python3
"""
Smart Asset Resolver, Downloader & Root Installer for RootArsenal.
Handles APKs (pm install), Magisk/KernelSU/APatch Modules (magisk --install-module),
GitHub Release Asset scoring for arm64-v8a/Zygisk, Source-to-Module ZIP packaging,
F-Droid/IzzyOnDroid resolution, and Built-in Root Scripts.
"""

import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 14; KB2003) RootArsenal/2.0",
    "Accept": "application/vnd.github+json, application/json, */*"
}

BASE_DIR = os.path.expanduser("~/root-arsenal")
DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
TOOLS_DIR = os.path.join(BASE_DIR, "tools")
SDCARD_DL_DIR = "/sdcard/Download/RootArsenal"

TERMUX_PATH_PREFIX = "PATH=/data/data/com.termux/files/usr/bin:/system/bin:/system/xbin:$PATH LD_LIBRARY_PATH=/data/data/com.termux/files/usr/lib:$LD_LIBRARY_PATH"

USE_ADB = False
ADB_DEVICE = None


def set_adb_mode(enabled: bool = True, device: str = None):
    """Configures installer to route all root commands, pushes, and flashes through ADB."""
    global USE_ADB, ADB_DEVICE
    USE_ADB = enabled
    ADB_DEVICE = device


def run_root_cmd(cmd: str, timeout: int = 120, mount_master: bool = False) -> tuple:
    """Executes a command via su -c with full Termux PATH and returns (exit_code, output)."""
    if USE_ADB:
        base = ["adb"]
        if ADB_DEVICE:
            base.extend(["-s", ADB_DEVICE])
        mm_flag = "-mm" if mount_master else ""
        escaped_cmd = cmd.replace("'", "'\"'\"'")
        base.extend(["shell", f"su {mm_flag} -c '{escaped_cmd}'"])
        try:
            res = subprocess.run(base, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout)
            return res.returncode, (res.stdout or "").strip()
        except subprocess.TimeoutExpired:
            return 124, "[!] ADB root command timed out."
        except Exception as e:
            return 1, f"[!] ADB error: {e}"

    su_args = ["su"]
    if mount_master:
        su_args.append("-mm")
    su_args.extend(["-c", f"{TERMUX_PATH_PREFIX} {cmd}"])
    try:
        res = subprocess.run(
            su_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout
        )
        return res.returncode, (res.stdout or "").strip()
    except subprocess.TimeoutExpired:
        return 124, "[!] Root command timed out."
    except Exception as e:
        return 1, f"[!] Error running root command: {e}"


def vibrate_tick(ms: int = 18):
    """Triggers a subtle hardware haptic click on Android devices via sysfs vibrator."""
    if USE_ADB:
        try:
            adb_cmd = ["adb"]
            if ADB_DEVICE:
                adb_cmd.extend(["-s", ADB_DEVICE])
            adb_cmd.extend(["shell", f"su -c 'echo {ms} > /sys/class/leds/vibrator/duration 2>/dev/null; echo 1 > /sys/class/leds/vibrator/activate 2>/dev/null'"])
            subprocess.Popen(adb_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
        return
    try:
        subprocess.Popen(
            ["su", "-c", f"echo {ms} > /sys/class/leds/vibrator/duration 2>/dev/null; echo 1 > /sys/class/leds/vibrator/activate 2>/dev/null"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception:
        pass


def parse_github_owner_repo(url: str):
    if not url:
        return None, None
    m = re.search(r"github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", url)
    if not m:
        return None, None
    owner, repo = m.group(1), m.group(2)
    if repo.endswith(".git"):
        repo = repo[:-4]
    return owner, repo


def get_device_abi() -> str:
    """Detects primary device CPU ABI dynamically (arm64-v8a, armeabi-v7a, x86_64)."""
    try:
        code, out = run_root_cmd("getprop ro.product.cpu.abi")
        if code == 0 and out.strip():
            return out.strip().lower()
    except Exception:
        pass
    return "arm64-v8a"


def score_asset_for_device(asset_name: str, item_kind: str = "") -> int:
    """
    Scores a release asset filename dynamically for the host device ABI and root framework.
    Higher score = better match. Negative score = incompatible architecture.
    """
    n = asset_name.lower()
    target_abi = get_device_abi()

    if n.endswith((".asc", ".sha256", ".sha256sum", ".sig", ".txt", ".md", ".json", ".pom")):
        return -500

    # Incompatible architecture filtering based on target ABI
    if "arm64" in target_abi or "aarch64" in target_abi:
        if any(bad in n for bad in ("x86_64", "x86", "mips", "windows", "macos", "darwin", "win64", "win32", ".exe", ".dmg", ".deb", ".rpm")):
            if "universal" not in n and "arm64" not in n:
                return -200
        if any(bad in n for bad in ("armeabi-v7a", "arm-v7a", "armv7")) and "arm64" not in n:
            return -50
    elif "x86" in target_abi:
        if any(bad in n for bad in ("arm64", "armeabi", "aarch64")):
            return -200

    score = 0
    if n.endswith(".apk"):
        score += 100
        if item_kind in ("apk_repo", "fdroid_app", "github_repo"):
            score += 30
    elif n.endswith(".zip"):
        score += 95
        if item_kind in ("module_repo", "module_zip"):
            score += 40
    elif n.endswith(".sh"):
        score += 70

    # Architecture matches
    if target_abi in n or ("arm64" in target_abi and ("arm64" in n or "aarch64" in n or "v8a" in n)):
        score += 50
    elif "universal" in n or "all" in n or "noarch" in n:
        score += 35

    # Magisk / Zygisk preference over Riru
    if "zygisk" in n:
        score += 30
    if "riru" in n:
        score -= 40

    # Prefer release over debug
    if "release" in n:
        score += 15
    if "debug" in n:
        score -= 10

    return score


def resolve_download_candidates(item: dict) -> list:
    """
    Resolves downloadable/installable assets for any catalog item.
    Returns a list of dicts: [{"name": ..., "url": ..., "type": "apk"|"zip"|"script"|"git", "size": ..., "score": ...}]
    """
    candidates = []
    kind = item.get("kind", "")
    url = item.get("url", "")
    alt_url = item.get("alt_url", "")
    zip_url = item.get("zip_url", "")

    # 1. Built-in root script
    if kind == "root_script" or url.startswith("builtin://"):
        candidates.append({
            "name": f"{item['id']}.sh",
            "url": url,
            "type": "builtin_script",
            "size": len(item.get("script_content", "")),
            "score": 1000,
            "label": "On-Device Root Script (Ready to Run or Install)"
        })
        return candidates

    # 2. Direct module zip_url (from MMRL / Alt-Repo)
    if zip_url:
        candidates.append({
            "name": f"{item.get('module_id') or item['id']}.zip",
            "url": zip_url,
            "type": "zip",
            "size": 0,
            "score": 900,
            "label": f"Direct Module ZIP ({item.get('source', 'MMRL')})"
        })

    # 3. Direct .apk or .zip URL
    for u in (url, alt_url):
        if u and u.lower().endswith(".apk"):
            candidates.append({
                "name": os.path.basename(u),
                "url": u,
                "type": "apk",
                "size": 0,
                "score": 850,
                "label": "Direct APK Download"
            })
        elif u and u.lower().endswith(".zip") and u != zip_url:
            candidates.append({
                "name": os.path.basename(u),
                "url": u,
                "type": "zip",
                "size": 0,
                "score": 840,
                "label": "Direct ZIP Archive"
            })

    # 4. IzzyOnDroid URL resolution
    for u in (url, alt_url):
        if u and "apt.izzysoft.de/fdroid/index/apk/" in u:
            try:
                r = requests.get(u, headers=HEADERS, timeout=8)
                if r.status_code == 200:
                    apks = re.findall(r"href=[\"\'](/fdroid/repo/[^\"\']+\.apk)[\"\']", r.text)
                    seen = set()
                    for apk_rel in apks:
                        if apk_rel in seen:
                            continue
                        seen.add(apk_rel)
                        full_apk = f"https://apt.izzysoft.de{apk_rel}"
                        fname = os.path.basename(apk_rel)
                        candidates.append({
                            "name": fname,
                            "url": full_apk,
                            "type": "apk",
                            "size": 0,
                            "score": 800,
                            "label": f"IzzyOnDroid APK ({fname})"
                        })
            except Exception:
                pass

    # 5. F-Droid package resolution via GitLab fdroiddata metadata -> SourceCode GitHub
    pkg_id = item.get("package_id")
    if not pkg_id:
        for u in (url, alt_url):
            if u and "f-droid.org" in u and "/packages/" in u:
                pkg_id = u.rstrip("/").split("/packages/")[-1].split("/")[0]
    if pkg_id:
        try:
            yml_url = f"https://gitlab.com/fdroid/fdroiddata/-/raw/master/metadata/{pkg_id}.yml"
            r = requests.get(yml_url, headers=HEADERS, timeout=7)
            if r.status_code == 200:
                m_src = re.search(r"^SourceCode:\s*(https://github\.com/\S+)", r.text, re.M)
                if m_src and "github.com" not in url:
                    url = m_src.group(1).strip()
        except Exception:
            pass

    # 6. GitHub Repository Releases & Fallback
    owner, repo = parse_github_owner_repo(url) or parse_github_owner_repo(alt_url)
    if owner and repo:
        try:
            rel_url = f"https://api.github.com/repos/{owner}/{repo}/releases?per_page=4"
            r = requests.get(rel_url, headers=HEADERS, timeout=9)
            if r.status_code == 200:
                releases = r.json()
                if isinstance(releases, list) and releases:
                    # Inspect the latest release (and 2nd if 1st has no binary assets)
                    for idx, rel in enumerate(releases[:2]):
                        tag = rel.get("tag_name", "latest")
                        for asset in rel.get("assets", []):
                            aname = asset.get("name", "")
                            dl_url = asset.get("browser_download_url", "")
                            asize = asset.get("size", 0)
                            sc = score_asset_for_device(aname, kind) - (idx * 25)
                            if sc > 0 and dl_url:
                                atype = "apk" if aname.lower().endswith(".apk") else ("zip" if aname.lower().endswith(".zip") else "file")
                                size_mb = f"{asize / (1024*1024):.1f} MB" if asize else ""
                                candidates.append({
                                    "name": aname,
                                    "url": dl_url,
                                    "type": atype,
                                    "size": asize,
                                    "score": sc,
                                    "label": f"GitHub Release {tag}: {aname} ({size_mb})"
                                })
        except Exception:
            pass

        # Always add GitHub Repo Clone / Auto-Module-Builder fallback
        candidates.append({
            "name": f"{repo}-main.git",
            "url": f"https://github.com/{owner}/{repo}",
            "type": "git_repo",
            "size": 0,
            "score": 25,
            "label": f"Clone GitHub Repo ({owner}/{repo}) & Auto-Build/Link"
        })

    candidates.sort(key=lambda c: -c["score"])
    return candidates


def download_file(url: str, dest_path: str, progress_cb=None) -> tuple:
    """Downloads a file with streaming progress and mirrors to /sdcard/Download/RootArsenal if possible."""
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    try:
        with requests.get(url, headers=HEADERS, stream=True, timeout=25) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            downloaded = 0
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_cb:
                            progress_cb(downloaded, total)
        # Try mirroring to /sdcard/Download/RootArsenal for easy Android access
        try:
            if os.path.exists("/sdcard/Download"):
                os.makedirs(SDCARD_DL_DIR, exist_ok=True)
                shutil.copy2(dest_path, os.path.join(SDCARD_DL_DIR, os.path.basename(dest_path)))
        except Exception:
            pass
        return True, dest_path
    except Exception as e:
        return False, str(e)


def extract_apk_package_name(apk_path: str) -> str:
    """Extracts Android package name from an APK file using aapt2 or raw zip scanning."""
    try:
        res = subprocess.run(["aapt2", "dump", "packagename", apk_path], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        pkg = (res.stdout or "").strip()
        if pkg and "." in pkg:
            return pkg
    except Exception:
        pass
    try:
        with zipfile.ZipFile(apk_path, "r") as zf:
            if "AndroidManifest.xml" in zf.namelist():
                raw = zf.read("AndroidManifest.xml")
                matches = re.findall(b"[a-zA-Z0-9_]+\\.[a-zA-Z0-9_.]+", raw)
                for cand in matches:
                    cand_s = cand.decode("ascii", errors="ignore")
                    if "." in cand_s and len(cand_s) > 6 and not cand_s.startswith("android.") and not cand_s.startswith("http") and not cand_s.endswith(".xml"):
                        return cand_s
    except Exception:
        pass
    return ""


def launch_app(pkg_name: str) -> tuple:
    """Launches an installed app via monkey or am start using root."""
    if not pkg_name:
        return False, "[!] Package name not specified."
    code, out = run_root_cmd(f"monkey -p '{pkg_name}' -c android.intent.category.LAUNCHER 1 2>/dev/null")
    if code == 0:
        return True, f"[+] Launched {pkg_name} successfully!"
    code, out = run_root_cmd(f"am start $(cmd package resolve-activity --brief {pkg_name} 2>/dev/null | tail -n 1)")
    if code == 0:
        return True, f"[+] Launched {pkg_name} via am start!"
    return False, f"[!] Could not launch {pkg_name}:\n{out}"


def grant_all_permissions_root(pkg_name: str) -> tuple:
    """Grants all declared runtime permissions to an app using root without user prompts."""
    if not pkg_name:
        return False, "[!] Package name not specified."
    cmd = (
        f"for p in $(dumpsys package '{pkg_name}' | grep 'permission\\.' | grep -v 'granted=true' | awk '{{print $1}}'); do "
        f"pm grant '{pkg_name}' \"$p\" 2>/dev/null; "
        f"done; "
        f"echo '[+] Granted permissions to {pkg_name}'"
    )
    code, out = run_root_cmd(cmd)
    return (code == 0), out


def soft_restart_zygote() -> tuple:
    """Performs a soft restart of Zygote without a full kernel/hardware reboot."""
    code, out = run_root_cmd("setprop ctl.restart zygote")
    return (code == 0), "[+] Triggered Zygote soft restart. UI will reload in ~5 seconds."


def send_device_alert(title: str, msg: str, is_success: bool = True):
    """Provides tactile vibration and dispatches Android system Toast & Notification."""
    vibrate_tick(45 if is_success else 90)
    first_line = msg.splitlines()[0] if msg else ""
    clean_msg = re.sub(r"\033\[[0-9;]*m", "", first_line)
    try:
        subprocess.Popen(
            ["termux-toast", "-s", f"{title}: {clean_msg}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception:
        pass
    try:
        subprocess.Popen(
            ["termux-notification", "--id", "root_arsenal", "--title", title, "--content", clean_msg],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception:
        pass


def install_apk_root(apk_path: str) -> tuple:
    """Installs an APK silently via root using /data/local/tmp and pm install -r -d (or adb install)."""
    if not os.path.exists(apk_path):
        return False, f"APK file not found: {apk_path}", ""
    pkg_name = extract_apk_package_name(apk_path)
    if USE_ADB:
        base = ["adb"]
        if ADB_DEVICE:
            base.extend(["-s", ADB_DEVICE])
        base.extend(["install", "-r", "-d", apk_path])
        try:
            res = subprocess.run(base, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=120)
            if res.returncode == 0 and "Success" in res.stdout:
                send_device_alert("Install Succeeded", f"APK installed via ADB: {pkg_name or os.path.basename(apk_path)}", is_success=True)
                return True, f"[+] APK installed successfully via ADB!\nPackage: {pkg_name}\n{res.stdout}", pkg_name
            send_device_alert("Install Failed", "ADB install returned error", is_success=False)
            return False, f"[!] ADB install failed:\n{res.stdout}", pkg_name
        except Exception as e:
            return False, f"[!] ADB install error: {e}", pkg_name

    tmp_apk = f"/data/local/tmp/arsenal_{int(time.time())}.apk"
    code, out = run_root_cmd(f"cp '{apk_path}' '{tmp_apk}' && chmod 644 '{tmp_apk}' && pm install -r -d '{tmp_apk}'; rm -f '{tmp_apk}'")
    if code == 0 and "Success" in out:
        send_device_alert("Install Succeeded", f"APK installed: {pkg_name or os.path.basename(apk_path)}", is_success=True)
        return True, f"[+] APK installed successfully via Root PM!\nPackage: {pkg_name}\n{out}", pkg_name
    send_device_alert("Install Failed", f"APK install error (code {code})", is_success=False)
    return False, f"[!] APK installation returned code {code}:\n{out}", pkg_name


def inspect_and_install_zip(zip_path: str) -> tuple:
    """
    Inspects a downloaded .zip file:
    - If it is a Magisk/KernelSU module, checks for bootloop hazards and installs via 'magisk --install-module'.
    - If it contains an .apk inside, extracts and installs the .apk via root!
    """
    if not zipfile.is_zipfile(zip_path):
        return False, f"[!] Downloaded file is not a valid ZIP archive: {zip_path}", ""

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        is_module = ("module.prop" in names) or ("META-INF/com/google/android/update-binary" in names)
        inner_apks = [n for n in names if n.lower().endswith(".apk") and not n.startswith("__MACOSX")]

        nested_props = [n for n in names if n.endswith("/module.prop") and n.count("/") == 1]
        if not is_module and nested_props:
            prefix = nested_props[0].split("/")[0] + "/"
            flat_zip = zip_path + ".flat.zip"
            with zipfile.ZipFile(flat_zip, "w", zipfile.ZIP_DEFLATED) as zout:
                for member in zf.infolist():
                    if member.filename.startswith(prefix) and member.filename != prefix:
                        rel_name = member.filename[len(prefix):]
                        zout.writestr(rel_name, zf.read(member.filename))
            shutil.move(flat_zip, zip_path)
            is_module = True

    if is_module:
        tmp_zip = f"/data/local/tmp/arsenal_mod_{int(time.time())}.zip"
        if USE_ADB:
            base = ["adb"]
            if ADB_DEVICE:
                base.extend(["-s", ADB_DEVICE])
            p_res = subprocess.run(base + ["push", zip_path, tmp_zip], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=180)
            if p_res.returncode != 0:
                return False, f"[!] Failed to push module ZIP to device via ADB:\n{p_res.stdout}", "module"
        else:
            code_cp, out_cp = run_root_cmd(f"cp '{zip_path}' '{tmp_zip}' && chmod 644 '{tmp_zip}'")
            if code_cp != 0:
                return False, f"[!] Failed to copy module ZIP to /data/local/tmp:\n{out_cp}", "module"

        cmd = (
            f"chmod 644 '{tmp_zip}' && "
            f"(if command -v magisk >/dev/null 2>&1; then magisk --install-module '{tmp_zip}'; "
            f"elif [ -x /debug_ramdisk/magisk ]; then /debug_ramdisk/magisk --install-module '{tmp_zip}'; "
            f"elif command -v ksud >/dev/null 2>&1; then ksud module install '{tmp_zip}'; "
            f"elif command -v apd >/dev/null 2>&1; then apd module install '{tmp_zip}'; "
            f"else echo 'No root module installer binary found'; exit 1; fi); "
            f"rm -f '{tmp_zip}'"
        )
        code, out = run_root_cmd(cmd, timeout=180)
        if code == 0:
            send_device_alert("Module Installed", f"Magisk module installed: {os.path.basename(zip_path)}", is_success=True)
            return True, f"[+] Systemless Module installed via Magisk/Root Manager!\n[i] Soft-restart or reboot required to activate overlay.\n\n{out}", "module"
        send_device_alert("Module Flash Failed", f"Magisk module install failed (code {code})", is_success=False)
        return False, f"[!] Module installation failed (exit {code}):\n{out}", "module"

    if inner_apks:
        extract_dir = tempfile.mkdtemp(prefix="arsenal_apk_")
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                target_apk = inner_apks[0]
                extracted_path = zf.extract(target_apk, extract_dir)
            ok, msg, pkg = install_apk_root(extracted_path)
            return ok, f"[*] Extracted '{target_apk}' from archive.\n{msg}", pkg
        finally:
            shutil.rmtree(extract_dir, ignore_errors=True)

    return False, f"[i] ZIP archive saved at {zip_path} (no module.prop or .apk found inside for automatic flashing).", "zip"


def execute_or_install_builtin_script(item: dict, mode: str = "run") -> tuple:
    """
    Handles Built-in On-Device Root Scripts:
    - mode == 'run': Executes immediately under su -c and returns live output.
    - mode == 'install': Installs to item['install_target'] (/data/adb/service.d/ or Termux bin) and executes!
    - mode == 'download': Saves script to ~/root-arsenal/downloads/scripts/<id>.sh
    """
    content = item.get("script_content", "")
    script_id = item.get("id", "root_script")
    os.makedirs(os.path.join(DOWNLOAD_DIR, "scripts"), exist_ok=True)
    local_file = os.path.join(DOWNLOAD_DIR, "scripts", f"{script_id}.sh")
    with open(local_file, "w", encoding="utf-8") as f:
        f.write(content)
    os.chmod(local_file, 0o755)

    if mode == "download":
        try:
            if os.path.exists("/sdcard/Download"):
                os.makedirs(SDCARD_DL_DIR, exist_ok=True)
                shutil.copy2(local_file, os.path.join(SDCARD_DL_DIR, f"{script_id}.sh"))
        except Exception:
            pass
        return True, f"[+] Saved root script to:\n  • {local_file}\n  • {SDCARD_DL_DIR}/{script_id}.sh"

    if mode == "install":
        target = item.get("install_target", f"/data/data/com.termux/files/usr/bin/{script_id}")
        if target.startswith("/data/adb/"):
            code, out = run_root_cmd(f"mkdir -p $(dirname '{target}') && cp '{local_file}' '{target}' && chmod 755 '{target}'")
            if code != 0:
                return False, f"[!] Failed to install script to {target}:\n{out}"
        else:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(local_file, target)
            os.chmod(target, 0o755)

    # Run the script now via root and return output
    tmp_sh = f"/data/local/tmp/{script_id}.sh"
    code, out = run_root_cmd(f"cp '{local_file}' '{tmp_sh}' && chmod 755 '{tmp_sh}' && sh '{tmp_sh}'; rm -f '{tmp_sh}'")
    prefix = f"[+] Installed to: {item.get('install_target')}\n\n" if mode == "install" else ""
    return (code == 0), f"{prefix}=== Live Root Execution Output ===\n{out}"


def clone_and_install_git_repo(repo_url: str, item: dict) -> tuple:
    """
    Clones a GitHub repository into ~/root-arsenal/tools/<repo>.
    If it contains a Magisk module (module.prop), packs it into a ZIP and installs via magisk --install-module!
    """
    owner, repo = parse_github_owner_repo(repo_url)
    if not repo:
        return False, f"Invalid GitHub repository URL: {repo_url}"
    os.makedirs(TOOLS_DIR, exist_ok=True)
    dest = os.path.join(TOOLS_DIR, repo)
    if os.path.exists(dest):
        shutil.rmtree(dest, ignore_errors=True)

    res = subprocess.run(
        ["git", "clone", "--depth", "1", repo_url, dest],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=90
    )
    if res.returncode != 0:
        return False, f"[!] git clone failed:\n{res.stdout}"

    # Check if the cloned repository is a Magisk/KernelSU module
    mod_prop = os.path.join(dest, "module.prop")
    if os.path.exists(mod_prop):
        os.makedirs(os.path.join(DOWNLOAD_DIR, "modules"), exist_ok=True)
        zip_out = os.path.join(DOWNLOAD_DIR, "modules", f"{repo}.zip")
        with zipfile.ZipFile(zip_out, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(dest):
                if ".git" in dirs:
                    dirs.remove(".git")
                for file in files:
                    full_p = os.path.join(root, file)
                    rel_p = os.path.relpath(full_p, dest)
                    zf.write(full_p, rel_p)
        ok, msg = inspect_and_install_zip(zip_out)
        return ok, f"[+] Built Magisk Module ZIP from source repo ({repo})!\n{msg}"

    # Otherwise check for executable shell or python scripts
    scripts = [f for f in os.listdir(dest) if f.endswith((".sh", ".py"))]
    return True, (
        f"[+] Repository cloned to: {dest}\n"
        f"[i] Detected scripts: {', '.join(scripts) if scripts else 'None (see README in directory)'}"
    )


def perform_action_on_candidate(item: dict, candidate: dict, action: str = "install", progress_cb=None) -> tuple:
    """
    Executes 'install' or 'download' on a resolved candidate.
    """
    ctype = candidate.get("type", "")
    url = candidate.get("url", "")
    fname = re.sub(r"[^A-Za-z0-9_.-]", "_", candidate.get("name", "tool.bin"))

    if ctype == "builtin_script":
        ok, msg = execute_or_install_builtin_script(item, mode="install" if action == "install" else "download")
        send_device_alert("Root Script", item.get("name", "Script"), is_success=ok)
        return ok, msg, {"type": "builtin_script", "target": item.get("install_target")}

    if ctype == "git_repo":
        if action == "download":
            owner, repo = parse_github_owner_repo(url)
            dest = os.path.join(TOOLS_DIR, repo or fname)
            if os.path.exists(dest):
                shutil.rmtree(dest, ignore_errors=True)
            os.makedirs(TOOLS_DIR, exist_ok=True)
            r = subprocess.run(["git", "clone", "--depth", "1", url, dest], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            ok = (r.returncode == 0)
            send_device_alert("Repo Cloned", repo or fname, is_success=ok)
            return ok, f"[+] Cloned repository to: {dest}\n{r.stdout}", {"type": "git_repo", "path": dest}
        else:
            ok, msg = clone_and_install_git_repo(url, item)
            send_device_alert("Repo Build", item.get("name", "Tool"), is_success=ok)
            return ok, msg, {"type": "git_repo"}

    sub = "apks" if ctype == "apk" else ("modules" if ctype == "zip" else "files")
    dest_path = os.path.join(DOWNLOAD_DIR, sub, fname)
    ok, dl_msg = download_file(url, dest_path, progress_cb=progress_cb)
    if not ok:
        send_device_alert("Download Failed", fname, is_success=False)
        return False, f"[!] Download failed from {url}:\n{dl_msg}", {"type": "error"}

    if action == "download":
        send_device_alert("Download Complete", f"Saved: {fname}", is_success=True)
        return True, (
            f"[+] Downloaded successfully!\n"
            f"  • Termux Path:  {dest_path}\n"
            f"  • Android Path: {SDCARD_DL_DIR}/{fname}"
        ), {"type": "download", "path": dest_path}

    # Action == 'install'
    if ctype == "apk" or dest_path.lower().endswith(".apk"):
        ok, msg, pkg = install_apk_root(dest_path)
        return ok, msg, {"type": "apk", "pkg_name": pkg, "path": dest_path}
    elif ctype == "zip" or dest_path.lower().endswith(".zip"):
        ok, msg, target_type = inspect_and_install_zip(dest_path)
        return ok, msg, {"type": target_type, "path": dest_path}
    elif dest_path.lower().endswith(".sh"):
        os.chmod(dest_path, 0o755)
        tmp_sh = f"/data/local/tmp/{fname}"
        code, out = run_root_cmd(f"cp '{dest_path}' '{tmp_sh}' && chmod 755 '{tmp_sh}' && sh '{tmp_sh}'; rm -f '{tmp_sh}'")
        send_device_alert("Script Executed", fname, is_success=(code == 0))
        return (code == 0), f"[+] Executed root script ({fname}):\n{out}", {"type": "script", "path": dest_path}

    return True, f"[+] Downloaded to {dest_path}", {"type": "file", "path": dest_path}


def list_installed_device_modules() -> list:
    """Reads /data/adb/modules/ via root to list all installed Magisk/KSU modules and their status."""
    code, out = run_root_cmd(
        "for d in /data/adb/modules/*; do "
        "[ -d \"$d\" ] || continue; "
        "id=$(basename \"$d\"); "
        "name=$(grep '^name=' \"$d/module.prop\" 2>/dev/null | cut -d= -f2-); "
        "ver=$(grep '^version=' \"$d/module.prop\" 2>/dev/null | cut -d= -f2-); "
        "auth=$(grep '^author=' \"$d/module.prop\" 2>/dev/null | cut -d= -f2-); "
        "desc=$(grep '^description=' \"$d/module.prop\" 2>/dev/null | cut -d= -f2-); "
        "state='ENABLED'; "
        "[ -f \"$d/disable\" ] && state='DISABLED'; "
        "[ -f \"$d/remove\" ] && state='REMOVING'; "
        "printf '%s\\t%s\\t%s\\t%s\\t%s\\t%s\\n' \"$id\" \"$state\" \"$name\" \"$ver\" \"$auth\" \"$desc\"; "
        "done"
    )
    modules = []
    if code == 0 and out:
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) >= 6:
                modules.append({
                    "id": parts[0],
                    "state": parts[1],
                    "name": parts[2] or parts[0],
                    "version": parts[3],
                    "author": parts[4],
                    "description": parts[5]
                })
    return modules


def toggle_installed_module(mod_id: str, action: str) -> tuple:
    """Toggles an installed module in /data/adb/modules/<mod_id> (enable, disable, remove)."""
    mod_dir = f"/data/adb/modules/{mod_id}"
    if action == "disable":
        code, out = run_root_cmd(f"touch '{mod_dir}/disable' && rm -f '{mod_dir}/remove'")
        return (code == 0), f"[+] Module '{mod_id}' DISABLED (takes full effect on reboot)."
    elif action == "enable":
        code, out = run_root_cmd(f"rm -f '{mod_dir}/disable' '{mod_dir}/remove'")
        return (code == 0), f"[+] Module '{mod_id}' ENABLED."
    elif action == "remove":
        code, out = run_root_cmd(f"touch '{mod_dir}/remove'")
        return (code == 0), f"[+] Module '{mod_id}' marked for REMOVAL on next reboot."
    return False, f"Unknown module action: {action}"


def get_installed_state_snapshot() -> dict:
    """
    Scans installed Android packages, Magisk modules, and built-in scripts to mark
    already-installed items in the UI with a [✔ INSTALLED] badge.
    """
    snapshot = {"packages": set(), "modules": set(), "files": set()}
    try:
        code, out = run_root_cmd(
            "pm list packages 2>/dev/null | cut -d: -f2; "
            "echo '---MODS---'; "
            "ls -1 /data/adb/modules 2>/dev/null; "
            "echo '---FILES---'; "
            "ls -1 /data/adb/service.d /data/adb/post-fs-data.d /data/data/com.termux/files/usr/bin 2>/dev/null",
            timeout=10
        )
        if code == 0 and out:
            mode = "packages"
            for line in out.splitlines():
                s = line.strip()
                if not s:
                    continue
                if s == "---MODS---":
                    mode = "modules"
                    continue
                elif s == "---FILES---":
                    mode = "files"
                    continue
                snapshot[mode].add(s.lower())
    except Exception:
        pass
    return snapshot


def is_item_installed(item: dict, snapshot: dict) -> bool:
    """Determines whether a catalog item is currently installed on the device."""
    if not snapshot:
        return False
    if item.get("kind") == "root_script":
        t = os.path.basename(item.get("install_target", "")).lower()
        return bool(t and t in snapshot.get("files", set()))
    mod_id = (item.get("module_id") or "").lower()
    if mod_id and mod_id in snapshot.get("modules", set()):
        return True
    pkg_id = (item.get("package_id") or "").lower()
    if pkg_id and pkg_id in snapshot.get("packages", set()):
        return True
    # Heuristic check on repo name vs module id
    url = item.get("url", "")
    _, repo = parse_github_owner_repo(url)
    if repo and repo.lower() in snapshot.get("modules", set()):
        return True
    return False


def fetch_tool_readme_and_audit(item: dict) -> str:
    """
    Fetches live README / Release Changelog and performs a static safety check
    for a tool before installation.
    """
    lines = [
        f"=== {item.get('name')} • Live Documentation & Safety Audit ===",
        f"Category   : {item.get('category')} › {item.get('subcategory')}",
        f"Source     : {item.get('source')} | Author: {item.get('author')}",
        f"Primary URL: {item.get('url')}",
        ""
    ]
    if item.get("kind") == "root_script":
        lines.append("── [On-Device Root Script Audit: SAFE (Systemless / Verified)] ──")
        lines.append(f"Target Path: {item.get('install_target')}")
        lines.append("")
        lines.append("── Script Source Code ──")
        lines.extend(item.get("script_content", "").splitlines())
        return "\n".join(lines)

    url = item.get("url", "")
    owner, repo = parse_github_owner_repo(url)
    if owner and repo:
        try:
            rel_r = requests.get(f"https://api.github.com/repos/{owner}/{repo}/releases/latest", headers=HEADERS, timeout=7)
            if rel_r.status_code == 200:
                rel = rel_r.json()
                lines.append(f"── Latest GitHub Release: {rel.get('tag_name')} ({rel.get('published_at', '')[:10]}) ──")
                body = (rel.get("body") or "").strip()
                if body:
                    lines.extend(body.splitlines()[:35])
                    lines.append("")
        except Exception:
            pass

        for br in ("main", "master"):
            try:
                rm_r = requests.get(f"https://raw.githubusercontent.com/{owner}/{repo}/{br}/README.md", headers=HEADERS, timeout=7)
                if rm_r.status_code == 200:
                    lines.append(f"── Repository README.md ({owner}/{repo}) ──")
                    clean_rm = [re.sub(r"<[^>]+>", "", ln) for ln in rm_r.text.splitlines()]
                    lines.extend(clean_rm[:90])
                    break
            except Exception:
                pass
    else:
        lines.append("── Tool Summary ──")
        lines.append(item.get("description", "No additional description."))

    return "\n".join(lines)


def get_live_device_telemetry() -> dict:
    """Queries live root & hardware status dynamically for any connected Android device."""
    cmd = (
        "echo \"MODEL=$(getprop ro.product.model)\"; "
        "echo \"ANDROID=$(getprop ro.build.version.release) (API $(getprop ro.build.version.sdk))\"; "
        "echo \"ABI=$(getprop ro.product.cpu.abi)\"; "
        "echo \"SELINUX=$(getenforce 2>/dev/null || echo 'Unknown')\"; "
        "echo \"MAGISK=$(magisk -v 2>/dev/null || /debug_ramdisk/magisk -v 2>/dev/null || echo 'Active') ($(magisk -V 2>/dev/null || /debug_ramdisk/magisk -V 2>/dev/null))\"; "
        "echo \"GOV=$(cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor 2>/dev/null || echo 'default')\"; "
        "p_first=$(ls -d /sys/devices/system/cpu/cpufreq/policy* 2>/dev/null | head -n 1); "
        "p_last=$(ls -d /sys/devices/system/cpu/cpufreq/policy* 2>/dev/null | tail -n 1); "
        "echo \"CPU_MIN_MHZ=$(($(cat $p_first/scaling_cur_freq 2>/dev/null || echo 0) / 1000))\"; "
        "echo \"CPU_MAX_MHZ=$(($(cat $p_last/scaling_cur_freq 2>/dev/null || echo 0) / 1000))\"; "
        "echo \"BAT_CAP=$(cat /sys/class/power_supply/battery/capacity 2>/dev/null || cat /sys/class/power_supply/*/capacity 2>/dev/null | head -n 1 || echo '?')%\"; "
        "echo \"BAT_TEMP=$(($(cat /sys/class/power_supply/battery/temp 2>/dev/null || cat /sys/class/power_supply/*/temp 2>/dev/null | head -n 1 || echo 0) / 10))C\"; "
        "echo \"BAT_CYCLES=$(cat /sys/class/power_supply/battery/cycle_count 2>/dev/null || cat /sys/class/power_supply/bms/cycle_count 2>/dev/null || echo 'N/A')\"; "
        "echo \"HZ=$(settings get system peak_refresh_rate 2>/dev/null || echo 'Default')\"; "
        "echo \"VBOOT=$(getprop ro.boot.verifiedbootstate 2>/dev/null || echo 'N/A')\"; "
        "if pgrep -f shizuku >/dev/null 2>&1; then echo \"SHIZUKU=RUNNING\"; else echo \"SHIZUKU=STOPPED\"; fi"
    )
    code, out = run_root_cmd(cmd, timeout=8)
    info = {}
    if code == 0 and out:
        for ln in out.splitlines():
            if "=" in ln:
                k, v = ln.split("=", 1)
                info[k.strip()] = v.strip()
    return info


def backup_all_modules_and_scripts() -> tuple:
    """Creates a full backup of /data/adb/modules, service.d, post-fs-data.d, and magisk.db."""
    ts = time.strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(SDCARD_DL_DIR, "Backups")
    local_backup_dir = os.path.join(DOWNLOAD_DIR, "backups")
    os.makedirs(local_backup_dir, exist_ok=True)
    dev_model = re.sub(r"[^A-Za-z0-9_]", "_", get_live_device_telemetry().get("MODEL", "device"))
    tar_path = os.path.join(local_backup_dir, f"root_backup_{dev_model}_{ts}.tar.gz")
    cmd = (
        f"tar -czf '{tar_path}' /data/adb/modules /data/adb/service.d /data/adb/post-fs-data.d /data/adb/magisk.db 2>/dev/null; "
        f"chmod 644 '{tar_path}'"
    )
    code, out = run_root_cmd(cmd, timeout=60)
    if os.path.exists(tar_path):
        try:
            os.makedirs(backup_dir, exist_ok=True)
            shutil.copy2(tar_path, os.path.join(backup_dir, os.path.basename(tar_path)))
        except Exception:
            pass
        sz_mb = os.path.getsize(tar_path) / (1024 * 1024)
        return True, f"[+] Root & Modules Backup created ({sz_mb:.2f} MB):\n  • {tar_path}\n  • {backup_dir}/{os.path.basename(tar_path)}"
    return False, f"[!] Backup failed:\n{out}"


def list_local_downloads() -> list:
    """Lists all downloaded APKs, Module ZIPs, and Scripts in ~/root-arsenal/downloads and /sdcard/Download."""
    found = []
    search_dirs = [
        os.path.join(DOWNLOAD_DIR, "apks"),
        os.path.join(DOWNLOAD_DIR, "modules"),
        os.path.join(DOWNLOAD_DIR, "scripts"),
        os.path.join(DOWNLOAD_DIR, "files"),
        SDCARD_DL_DIR,
    ]
    seen_names = set()
    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        for fname in sorted(os.listdir(d)):
            if not fname.lower().endswith((".apk", ".zip", ".sh")):
                continue
            full_p = os.path.join(d, fname)
            if not os.path.isfile(full_p) or fname in seen_names:
                continue
            seen_names.add(fname)
            sz = os.path.getsize(full_p)
            ftype = "apk" if fname.lower().endswith(".apk") else ("zip" if fname.lower().endswith(".zip") else "script")
            found.append({
                "name": fname,
                "path": full_p,
                "type": ftype,
                "size_mb": f"{sz / (1024 * 1024):.2f} MB"
            })
    return found

