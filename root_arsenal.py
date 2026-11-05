#!/data/data/com.termux/files/usr/bin/env python3
"""
RootArsenal v2.5 (root-arsenal / rarsenal)
Smart Multi-Source Crawler, Category Browser, Multi-Digit Selector & Volume-Key Installer.
Tailored for OnePlus 8T (KB2003 / Snapdragon 865 / arm64-v8a / Android 14 / Magisk).
"""

import argparse
import json
import os
import queue
import re
import select
import shutil
import signal
import subprocess
import sys
import termios
import threading
import time

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from crawler import CACHE_DIR, CATEGORIES, crawl_all, live_query_crawl, load_or_crawl
from installer import (
    ADB_DEVICE,
    SDCARD_DL_DIR,
    USE_ADB,
    backup_all_modules_and_scripts,
    fetch_tool_readme_and_audit,
    get_installed_state_snapshot,
    get_live_device_telemetry,
    grant_all_permissions_root,
    install_apk_root,
    inspect_and_install_zip,
    is_item_installed,
    launch_app,
    list_installed_device_modules,
    list_local_downloads,
    perform_action_on_candidate,
    resolve_download_candidates,
    run_root_cmd,
    send_device_alert,
    set_adb_mode,
    soft_restart_zygote,
    toggle_installed_module,
    vibrate_tick,
)

FAV_FILE = os.path.join(CACHE_DIR, "favorites.json")

# ANSI Styling
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
CYAN = "\033[38;5;51m"
GREEN = "\033[38;5;48m"
YELLOW = "\033[38;5;220m"
MAGENTA = "\033[38;5;207m"
RED = "\033[38;5;196m"
BLUE = "\033[38;5;39m"
WHITE = "\033[97m"
GRAY = "\033[38;5;245m"
BG_SEL = "\033[48;5;24m"
BG_HEADER = "\033[48;5;17m"
BG_BADGE = "\033[48;5;236m"
BG_NUM = "\033[48;5;54m"


def parse_number_or_range(buf: str, max_len: int) -> list:
    """
    Parses multi-digit input strings like '12', '08', '1,4,15', or '5-10'
    into a 0-based list of valid indices [0 .. max_len-1].
    """
    indices = []
    for part in buf.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            bounds = part.split("-", 1)
            if bounds[0].isdigit() and bounds[1].isdigit():
                start_n, end_n = int(bounds[0]), int(bounds[1])
                if start_n > end_n:
                    start_n, end_n = end_n, start_n
                for n in range(start_n, end_n + 1):
                    if 1 <= n <= max_len and (n - 1) not in indices:
                        indices.append(n - 1)
        elif part.isdigit():
            n = int(part)
            if 1 <= n <= max_len and (n - 1) not in indices:
                indices.append(n - 1)
    return indices


class HybridInputReader:
    """
    Simultaneously listens to:
    1. Linux Kernel Hardware Volume Keys (/dev/input/event* via 'su -c getevent -ql')
       - Distinguishes Short Press (<0.45s) vs Long Hold (>=0.45s) with haptic feedback.
       - Deduplicates multi-device kernel events (gpio-keys + qpnp_pon).
    2. Standard Terminal Stdin (with ECHO disabled so multi-digit typing is clean).
    3. Terminal Resize (SIGWINCH) events for instant responsive layout redraws.
    """

    def __init__(self, hold_threshold: float = 0.45):
        self.events = queue.Queue()
        self.hold_threshold = hold_threshold
        self.running = False
        self.getevent_proc = None
        self.magisk_cycle_mode = False
        self._old_term = None

    def start(self):
        self.running = True
        try:
            signal.signal(signal.SIGWINCH, self._on_sigwinch)
        except Exception:
            pass
        t_hw = threading.Thread(target=self._hardware_volume_worker, daemon=True)
        t_hw.start()
        t_kb = threading.Thread(target=self._stdin_worker, daemon=True)
        t_kb.start()

    def _on_sigwinch(self, signum, frame):
        self.events.put("RESIZE")

    def stop(self):
        self.running = False
        if self.getevent_proc and self.getevent_proc.poll() is None:
            try:
                self.getevent_proc.terminate()
            except Exception:
                pass
        self._restore_term()

    def _restore_term(self):
        if os.name != "nt" and self._old_term is not None:
            try:
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self._old_term)
            except Exception:
                pass

    def _hardware_volume_worker(self):
        try:
            from installer import ADB_DEVICE, USE_ADB
            if USE_ADB:
                base = ["adb"]
                if ADB_DEVICE:
                    base.extend(["-s", ADB_DEVICE])
                base.extend(["shell", "su", "-c", "getevent -ql"])
                cmd = base
            else:
                cmd = ["su", "-c", "getevent -ql"]
            self.getevent_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1
            )
        except Exception:
            return

        active_key = None
        hold_fired = False
        last_down_ts = {"KEY_VOLUMEUP": 0.0, "KEY_VOLUMEDOWN": 0.0}
        last_up_ts = {"KEY_VOLUMEUP": 0.0, "KEY_VOLUMEDOWN": 0.0}
        hold_timer = None

        def on_hold_timeout(k):
            nonlocal hold_fired
            if active_key == k and not hold_fired:
                hold_fired = True
                vibrate_tick(38)
                if k == "KEY_VOLUMEUP":
                    self.events.put("VOL_UP_HOLD")
                elif k == "KEY_VOLUMEDOWN":
                    self.events.put("VOL_DOWN_HOLD")

        for line in self.getevent_proc.stdout:
            if not self.running:
                break
            if "EV_KEY" not in line:
                continue
            parts = line.split()
            if len(parts) < 4:
                continue
            key_name, state = parts[2], parts[3]
            if key_name not in ("KEY_VOLUMEUP", "KEY_VOLUMEDOWN"):
                continue

            now = time.monotonic()
            if state == "DOWN":
                if now - last_down_ts[key_name] < 0.04:
                    continue
                last_down_ts[key_name] = now
                active_key = key_name
                hold_fired = False
                vibrate_tick(12)
                if hold_timer:
                    hold_timer.cancel()
                hold_timer = threading.Timer(self.hold_threshold, on_hold_timeout, args=[key_name])
                hold_timer.daemon = True
                hold_timer.start()

            elif state == "UP":
                if now - last_up_ts[key_name] < 0.04:
                    continue
                last_up_ts[key_name] = now
                if hold_timer:
                    hold_timer.cancel()
                if active_key == key_name:
                    if not hold_fired:
                        if key_name == "KEY_VOLUMEUP":
                            self.events.put("VOL_UP_SHORT")
                        elif key_name == "KEY_VOLUMEDOWN":
                            self.events.put("VOL_DOWN_SHORT")
                    active_key = None

    def _stdin_worker(self):
        if os.name == "nt":
            import msvcrt
            while self.running:
                if not msvcrt.kbhit():
                    time.sleep(0.04)
                    continue
                ch = msvcrt.getwch()
                if ch in ("\x00", "\xe0"):
                    ch2 = msvcrt.getwch()
                    if ch2 == "H": self.events.put("KEY_UP")
                    elif ch2 == "P": self.events.put("KEY_DOWN")
                    elif ch2 == "K": self.events.put("KEY_LEFT")
                    elif ch2 == "M": self.events.put("KEY_RIGHT")
                    elif ch2 == "I": self.events.put("KEY_PGUP")
                    elif ch2 == "Q": self.events.put("KEY_PGDN")
                elif ch in ("\r", "\n"):
                    self.events.put("KEY_ENTER")
                elif ch == "\x08":
                    self.events.put("KEY_BACKSPACE")
                elif ch == "\x1b":
                    self.events.put("KEY_ESC")
                else:
                    self.events.put(ch)
            return

        fd = sys.stdin.fileno()
        if not os.isatty(fd):
            return
        try:
            self._old_term = termios.tcgetattr(fd)
            new_term = termios.tcgetattr(fd)
            # Disable ICANON and ECHO so typed multi-digit numbers do not corrupt the screen
            new_term[3] = new_term[3] & ~(termios.ICANON | termios.ECHO)
            new_term[6][termios.VMIN] = 1
            new_term[6][termios.VTIME] = 0
            termios.tcsetattr(fd, termios.TCSANOW, new_term)

            while self.running:
                rlist, _, _ = select.select([fd], [], [], 0.1)
                if not rlist:
                    continue
                ch = os.read(fd, 1).decode("utf-8", errors="ignore")
                if not ch:
                    continue
                if ch == "\x1b":
                    r2, _, _ = select.select([fd], [], [], 0.03)
                    if r2:
                        seq = os.read(fd, 2).decode("utf-8", errors="ignore")
                        if seq == "[A":
                            self.events.put("KEY_UP")
                        elif seq == "[B":
                            self.events.put("KEY_DOWN")
                        elif seq == "[C":
                            self.events.put("KEY_RIGHT")
                        elif seq == "[D":
                            self.events.put("KEY_LEFT")
                        elif seq == "[5":
                            os.read(fd, 1)
                            self.events.put("KEY_PGUP")
                        elif seq == "[6":
                            os.read(fd, 1)
                            self.events.put("KEY_PGDN")
                    else:
                        self.events.put("KEY_ESC")
                elif ch in ("\r", "\n"):
                    self.events.put("KEY_ENTER")
                elif ch in ("\x7f", "\x08"):
                    self.events.put("KEY_BACKSPACE")
                else:
                    self.events.put(ch)
        except Exception:
            pass
        finally:
            self._restore_term()

    def get_event(self, timeout: float = None):
        try:
            return self.events.get(timeout=timeout)
        except queue.Empty:
            return None

    def flush(self):
        while not self.events.empty():
            try:
                self.events.get_nowait()
            except queue.Empty:
                break


def clear_screen():
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def get_term_size():
    sz = shutil.get_terminal_size((80, 28))
    return max(44, sz.columns), max(18, sz.lines)


def truncate_str(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    return s[: max(1, max_len - 1)] + "…"


class RootArsenalTUI:
    def __init__(self, items: list):
        self.items = items
        self.input_reader = HybridInputReader()
        self.status_msg = "Type 1/2/3+ digit numbers (e.g. 12 or 1,4,12) + Enter, or use Volume Keys!"
        self.favorites = self._load_favorites()
        self.batch_queue = {}  # item_id -> item dict
        self.installed_snapshot = {"packages": set(), "modules": set(), "files": set()}
        threading.Thread(target=self._refresh_installed_bg, daemon=True).start()

    def _refresh_installed_bg(self):
        self.installed_snapshot = get_installed_state_snapshot()

    def _load_favorites(self) -> set:
        if os.path.exists(FAV_FILE):
            try:
                with open(FAV_FILE, "r", encoding="utf-8") as f:
                    return set(json.load(f))
            except Exception:
                pass
        return set()

    def _save_favorites(self):
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(FAV_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(self.favorites), f)

    def build_category_menu(self) -> list:
        counts = {}
        for it in self.items:
            c = it.get("category", "Other")
            counts[c] = counts.get(c, 0) + 1

        menu = [
            {
                "title": "🎛️ Live Root & Hardware Control Center",
                "cat_key": "__CONTROL_CENTER__",
                "count": 12,
                "desc": "Live CPU/Battery/SELinux/Shizuku dashboard & 12 instant 2-digit root actions"
            },
            {
                "title": "🌟 All Crawled & Built-In Tools",
                "cat_key": "__ALL__",
                "count": len(self.items),
                "desc": "Browse all 1,386+ Root, Magisk/KSU, Shizuku, LSPosed & System tools"
            },
        ]
        for c in CATEGORIES:
            menu.append({
                "title": c,
                "cat_key": c,
                "count": counts.get(c, 0),
                "desc": f"{counts.get(c, 0)} tools available in this category"
            })
        menu.extend([
            {
                "title": "⭐ Bookmarked Favorites",
                "cat_key": "__FAVORITES__",
                "count": len(self.favorites),
                "desc": "Your starred tools across all categories (press 'f' on any tool to star)"
            },
            {
                "title": "📥 Batch Queue (Multi-Select Installer/Downloader)",
                "cat_key": "__BATCH__",
                "count": len(self.batch_queue),
                "desc": "Install or Download multiple queued tools at once (mark with 't' or '1,4,12'+Enter)"
            },
            {
                "title": "🔍 Live Deep Search & Custom Crawler",
                "cat_key": "__SEARCH__",
                "count": 0,
                "desc": "Search local database + crawl GitHub & F-Droid live for any keyword"
            },
            {
                "title": "📦 Installed Magisk/KSU Modules Manager",
                "cat_key": "__INSTALLED__",
                "count": len(self.installed_snapshot.get("modules", [])),
                "desc": "Inspect, Enable, Disable, or Remove modules in /data/adb/modules/"
            },
            {
                "title": "📂 Local Downloads & Package Installer",
                "cat_key": "__DOWNLOADS__",
                "count": len(list_local_downloads()),
                "desc": "Manage & flash downloaded .apk, .zip, and .sh files in storage"
            },
            {
                "title": "🔄 Re-Crawl All 8 Live Sources Now",
                "cat_key": "__RECRAWL__",
                "count": 29,
                "desc": "Refresh catalog from Awesome-Root, Awesome-Shizuku, MMRL, GitHub & F-Droid"
            }
        ])
        return menu

    def render_header(self, subtitle: str):
        cols, _ = get_term_size()
        batch_badge = f" | 📥 Batch: {len(self.batch_queue)}" if self.batch_queue else ""
        model = getattr(self, "_cached_model", None)
        if not model:
            tele = get_live_device_telemetry()
            self._cached_model = tele.get("MODEL") or "Android Device"
            self._cached_ver = tele.get("ANDROID") or "Universal"
            model = self._cached_model
        ver = getattr(self, "_cached_ver", "Universal")
        title = f" ⚡ ROOT ARSENAL v2.5 • {model} ({ver}){batch_badge} "
        print(f"{BG_HEADER}{BOLD}{CYAN}{title.ljust(cols)[:cols]}{RESET}")
        sub = f" {subtitle} | Indexed: {len(self.items)} Tools"
        print(f"{BLUE}{BOLD}{sub[:cols]}{RESET}")
        print(f"{GRAY}{'─' * cols}{RESET}")

    def render_footer_list(self, num_buf: str = "", allow_ranges: bool = False):
        cols, _ = get_term_size()
        print(f"{GRAY}{'─' * cols}{RESET}")
        if num_buf:
            range_hint = " (or 1,4,12 / 5-9 for Batch)" if allow_ranges else ""
            prompt = f" 🔢 NUMBER INPUT: [ {num_buf}█ ]  👉 Press [ENTER] to Confirm{range_hint} | [g] Jump Only | [Bksp] Edit | [Esc] Clear "
            print(f"{BG_NUM}{BOLD}{YELLOW}{prompt.ljust(cols)[:cols]}{RESET}")
        else:
            if not self.input_reader.magisk_cycle_mode:
                print(f"{BOLD}{YELLOW}🔊 VOL+ Tap{RESET}: Up  {BOLD}{YELLOW}🔉 VOL- Tap{RESET}: Down  {BOLD}{GREEN}🔊 VOL+ Hold{RESET}: Open  {BOLD}{RED}🔉 VOL- Hold{RESET}: Back")
            else:
                print(f"{BOLD}{YELLOW}[Magisk Mode] 🔊 VOL+{RESET}: Next Item  {BOLD}{GREEN}🔉 VOL-{RESET}: Select/Open")
            print(f"{DIM}🔢 Type 2+ digits (e.g. 04, 12, 145) + [Enter] | [t] BatchTag | [f] Fav | [/] Search | [q] Quit{RESET}")
        if self.status_msg:
            print(f"{CYAN}» {truncate_str(self.status_msg, cols - 4)}{RESET}")

    def run(self):
        self.input_reader.start()
        try:
            self.category_loop()
        finally:
            self.input_reader.stop()

    def category_loop(self):
        cursor = 0
        num_buf = ""
        while True:
            menu = self.build_category_menu()
            if cursor >= len(menu):
                cursor = len(menu) - 1
            cols, lines = get_term_size()
            page_size = max(6, lines - 10)
            start_idx = max(0, min(cursor - page_size // 2, len(menu) - page_size))
            end_idx = min(len(menu), start_idx + page_size)

            clear_screen()
            self.render_header("Main Categories (Use Volume Keys or Type #01-#20 + Enter)")

            for idx in range(start_idx, end_idx):
                entry = menu[idx]
                is_sel = (idx == cursor)
                num_str = f"[{idx + 1:02d}]"
                prefix = "▶ " if is_sel else "  "
                badge = f"({entry['count']})" if entry["count"] else ""
                line_txt = f"{prefix}{num_str} {entry['title']} {badge}"
                if is_sel:
                    print(f"{BG_SEL}{BOLD}{WHITE}{line_txt.ljust(cols)[:cols]}{RESET}")
                    desc_line = f"         ↳ {entry['desc']}"
                    print(f"{CYAN}{truncate_str(desc_line, cols)}{RESET}")
                else:
                    print(f"{YELLOW}{prefix}{num_str}{RESET} {WHITE}{truncate_str(entry['title'] + ' ' + badge, cols - 8)}{RESET}")

            self.render_footer_list(num_buf=num_buf, allow_ranges=False)
            ev = self.input_reader.get_event()
            if not ev or ev == "RESIZE":
                continue

            # Handle Multi-Digit Numeric Input first
            if ev.isdigit():
                num_buf += ev
                idxs = parse_number_or_range(num_buf, len(menu))
                if idxs:
                    cursor = idxs[-1]
                continue
            elif ev == "KEY_BACKSPACE" and num_buf:
                num_buf = num_buf[:-1]
                continue
            elif ev == "KEY_ESC" and num_buf:
                num_buf = ""
                continue
            elif ev == "g" and num_buf:
                idxs = parse_number_or_range(num_buf, len(menu))
                if idxs:
                    cursor = idxs[0]
                    self.status_msg = f"Jumped cursor to Category #{cursor + 1:02d}"
                num_buf = ""
                continue
            elif ev in ("KEY_ENTER", "VOL_UP_HOLD") and num_buf:
                idxs = parse_number_or_range(num_buf, len(menu))
                num_buf = ""
                if idxs:
                    cursor = idxs[0]
                    self.open_category(menu[cursor])
                else:
                    self.status_msg = f"[!] Invalid category number (enter 01 - {len(menu):02d})"
                continue

            # Standard Navigation
            if ev in ("VOL_UP_SHORT", "KEY_UP", "k", "w"):
                if self.input_reader.magisk_cycle_mode and ev == "VOL_UP_SHORT":
                    cursor = (cursor + 1) % len(menu)
                else:
                    cursor = (cursor - 1) % len(menu)
            elif ev in ("VOL_DOWN_SHORT", "KEY_DOWN", "j", "s"):
                if self.input_reader.magisk_cycle_mode and ev == "VOL_DOWN_SHORT":
                    self.open_category(menu[cursor])
                else:
                    cursor = (cursor + 1) % len(menu)
            elif ev in ("VOL_UP_HOLD", "KEY_ENTER", "KEY_RIGHT", " "):
                self.open_category(menu[cursor])
            elif ev == "m":
                self.input_reader.magisk_cycle_mode = not self.input_reader.magisk_cycle_mode
                mode_lbl = "Magisk Cycle (VOL+=Next, VOL-=Select)" if self.input_reader.magisk_cycle_mode else "Standard (VOL+=Up, VOL-=Down, Hold VOL+=Select)"
                self.status_msg = f"Switched Volume Key Mode to: {mode_lbl}"
            elif ev == "/":
                self.prompt_and_search()
            elif ev == "c":
                self.trigger_recrawl()
            elif ev == "i":
                self.installed_modules_loop()
            elif ev in ("q", "Q", "VOL_DOWN_HOLD", "KEY_ESC"):
                clear_screen()
                print(f"{GREEN}{BOLD}[+] Exiting RootArsenal. Happy hacking!{RESET}")
                break

    def open_category(self, cat_entry: dict):
        key = cat_entry["cat_key"]
        if key == "__CONTROL_CENTER__":
            self.live_control_center_loop()
        elif key == "__SEARCH__":
            self.prompt_and_search()
        elif key == "__INSTALLED__":
            self.installed_modules_loop()
        elif key == "__DOWNLOADS__":
            self.local_downloads_loop()
        elif key == "__FAVORITES__":
            fav_items = [it for it in self.items if it["id"] in self.favorites]
            if not fav_items:
                self.status_msg = "No favorites yet! Press 'f' on any tool in any category to bookmark it."
                return
            self.tools_list_loop("⭐ Bookmarked Favorites", fav_items)
        elif key == "__BATCH__":
            self.batch_queue_modal()
        elif key == "__RECRAWL__":
            self.trigger_recrawl()
        elif key == "__ALL__":
            self.tools_list_loop("🌟 All Tools", self.items)
        else:
            filtered = [it for it in self.items if it.get("category") == key]
            self.tools_list_loop(key, filtered)

    def tools_list_loop(self, title: str, tool_list: list):
        if not tool_list:
            self.status_msg = f"No tools found in {title}."
            return
        cursor = 0
        num_buf = ""
        filter_str = ""

        while True:
            if filter_str:
                fl = filter_str.lower()
                active_list = [
                    it for it in tool_list
                    if fl in it.get("name", "").lower()
                    or fl in it.get("description", "").lower()
                    or fl in it.get("subcategory", "").lower()
                    or any(fl in b.lower() for b in it.get("badges", []))
                ]
                if not active_list:
                    filter_str = ""
                    active_list = list(tool_list)
                    self.status_msg = "No tools matched filter. Showing all."
            else:
                active_list = list(tool_list)

            num_width = max(2, len(str(len(active_list))))
            if cursor >= len(active_list):
                cursor = max(0, len(active_list) - 1)

            cols, lines = get_term_size()
            page_size = max(5, (lines - 11) // 2)
            start_idx = max(0, min(cursor - page_size // 2, len(active_list) - page_size))
            end_idx = min(len(active_list), start_idx + page_size)

            clear_screen()
            filter_tag = f" [Filter: '{filter_str}']" if filter_str else ""
            self.render_header(f"{title}{filter_tag} ({cursor + 1}/{len(active_list)})")

            for idx in range(start_idx, end_idx):
                item = active_list[idx]
                is_sel = (idx == cursor)
                num_tag = f"[{idx + 1:0{num_width}d}]"
                is_queued = item["id"] in self.batch_queue
                is_fav = item["id"] in self.favorites
                is_inst = is_item_installed(item, self.installed_snapshot)

                q_mark = "[✓] " if is_queued else ""
                fav_mark = "★ " if is_fav else ""
                inst_badge = "[✔INSTALLED] " if is_inst else ""
                badges_str = inst_badge + " ".join(f"[{b}]" for b in item.get("badges", [])[:3])

                prefix = "▶ " if is_sel else "  "
                head_line = f"{prefix}{num_tag} {q_mark}{fav_mark}{item['name']}  {badges_str}"
                desc_line = f"       {item.get('description', '')}"

                if is_sel:
                    print(f"{BG_SEL}{BOLD}{WHITE}{truncate_str(head_line, cols).ljust(cols)}{RESET}")
                    print(f"{CYAN}{truncate_str(desc_line, cols)}{RESET}")
                else:
                    c_num = GREEN if is_queued else YELLOW
                    item_display = f"{q_mark}{fav_mark}{item['name']}  {badges_str}"
                    print(f"{c_num}{prefix}{num_tag}{RESET} {WHITE}{truncate_str(item_display, cols - (num_width + 5))}{RESET}")
                    print(f"{GRAY}{truncate_str(desc_line, cols)}{RESET}")

            self.render_footer_list(num_buf=num_buf, allow_ranges=True)
            ev = self.input_reader.get_event()
            if not ev or ev == "RESIZE":
                continue

            # Multi-Digit & Range Input (e.g. '04', '12', '145', '1,4,12', '10-15')
            if ev.isdigit() or (num_buf and ev in (",", "-")):
                num_buf += ev
                idxs = parse_number_or_range(num_buf, len(active_list))
                if idxs:
                    cursor = idxs[-1]
                continue
            elif ev == "KEY_BACKSPACE":
                if num_buf:
                    num_buf = num_buf[:-1]
                    idxs = parse_number_or_range(num_buf, len(active_list))
                    if idxs:
                        cursor = idxs[-1]
                else:
                    break
                continue
            elif ev == "KEY_ESC":
                if num_buf:
                    num_buf = ""
                elif filter_str:
                    filter_str = ""
                    self.status_msg = "Cleared in-category filter."
                else:
                    break
                continue
            elif ev == "g" and num_buf:
                idxs = parse_number_or_range(num_buf, len(active_list))
                if idxs:
                    cursor = idxs[0]
                    self.status_msg = f"Jumped cursor to #{cursor + 1:0{num_width}d} ({active_list[cursor]['name']})"
                num_buf = ""
                continue
            elif ev in ("KEY_ENTER", "VOL_UP_HOLD") and num_buf:
                idxs = parse_number_or_range(num_buf, len(active_list))
                raw_entered = num_buf
                num_buf = ""
                if not idxs:
                    self.status_msg = f"[!] Invalid number/range '{raw_entered}' (valid: 1..{len(active_list)})"
                    continue
                if len(idxs) == 1 and "," not in raw_entered and "-" not in raw_entered:
                    cursor = idxs[0]
                    self.tool_action_modal(active_list[cursor])
                else:
                    for i in idxs:
                        it = active_list[i]
                        self.batch_queue[it["id"]] = it
                    self.status_msg = f"Added {len(idxs)} tools to Batch Queue! Press 'B' to review/run."
                    self.batch_queue_modal()
                continue

            # In-list Quick Search Filter
            if ev == "/":
                self.input_reader.stop()
                clear_screen()
                self.render_header(f"Filter within: {title}")
                print(f"\n{WHITE}Enter text to filter this list (or press Enter to clear):{RESET}")
                try:
                    f_in = input(f"{YELLOW}Filter > {RESET}").strip()
                except EOFError:
                    f_in = ""
                self.input_reader.start()
                filter_str = f_in
                cursor = 0
                self.input_reader.flush()
                continue

            # Standard Navigation & Shortcuts
            if ev in ("VOL_UP_SHORT", "KEY_UP", "k", "w"):
                if self.input_reader.magisk_cycle_mode and ev == "VOL_UP_SHORT":
                    cursor = (cursor + 1) % len(active_list)
                else:
                    cursor = (cursor - 1) % len(active_list)
            elif ev in ("VOL_DOWN_SHORT", "KEY_DOWN", "j", "s"):
                if self.input_reader.magisk_cycle_mode and ev == "VOL_DOWN_SHORT":
                    self.tool_action_modal(active_list[cursor])
                else:
                    cursor = (cursor + 1) % len(active_list)
            elif ev == "KEY_PGUP":
                cursor = max(0, cursor - page_size)
            elif ev == "KEY_PGDN":
                cursor = min(len(active_list) - 1, cursor + page_size)
            elif ev in ("VOL_UP_HOLD", "KEY_ENTER", "KEY_RIGHT"):
                self.tool_action_modal(active_list[cursor])
            elif ev in ("t", " "):
                cur_it = active_list[cursor]
                if cur_it["id"] in self.batch_queue:
                    del self.batch_queue[cur_it["id"]]
                    self.status_msg = f"Removed '{cur_it['name']}' from Batch Queue."
                else:
                    self.batch_queue[cur_it["id"]] = cur_it
                    self.status_msg = f"Added '{cur_it['name']}' to Batch Queue ({len(self.batch_queue)} total). Press 'B' to run batch!"
            elif ev == "B":
                self.batch_queue_modal()
            elif ev in ("f", "F"):
                cur_it = active_list[cursor]
                if cur_it["id"] in self.favorites:
                    self.favorites.remove(cur_it["id"])
                    self.status_msg = f"Removed '{cur_it['name']}' from Favorites."
                else:
                    self.favorites.add(cur_it["id"])
                    self.status_msg = f"★ Bookmarked '{cur_it['name']}' to Favorites!"
                self._save_favorites()
            elif ev in ("VOL_DOWN_HOLD", "KEY_LEFT", "b", "q"):
                break

    def tool_action_modal(self, item: dict):
        """
        Displays detailed metadata for a selected tool, resolves downloadable/installable
        assets in real time, and supports Volume Keys OR 1/2-digit number + Enter!
        """
        cols, _ = get_term_size()
        clear_screen()
        self.render_header(f"Tool Inspector: {item['name']}")
        print(f"{BOLD}{WHITE}Name       :{RESET} {CYAN}{BOLD}{item['name']}{RESET}")
        print(f"{BOLD}{WHITE}Category   :{RESET} {item.get('category', '')} › {item.get('subcategory', '')}")
        print(f"{BOLD}{WHITE}Author/Src :{RESET} {item.get('author', 'Unknown')} ({item.get('source', '')})")
        print(f"{BOLD}{WHITE}Badges     :{RESET} {YELLOW}{' '.join('[' + b + ']' for b in item.get('badges', []))}{RESET}")
        print(f"{BOLD}{WHITE}URL        :{RESET} {BLUE}{item.get('url', '')}{RESET}")
        print(f"{GRAY}{'─' * cols}{RESET}")
        print(f"{WHITE}{item.get('description', '')}{RESET}")
        print(f"{GRAY}{'─' * cols}{RESET}")
        print(f"{YELLOW}[*] Resolving best installable packages/assets for OnePlus 8T (arm64-v8a)...{RESET}")

        candidates = resolve_download_candidates(item)
        self.input_reader.flush()

        if not candidates:
            print(f"{RED}[!] Could not resolve direct downloadable assets for this URL.{RESET}")
            print(f"{DIM}Press any key or Volume button to go back...{RESET}")
            self.input_reader.get_event()
            return

        selected_cand_idx = 0
        num_buf = ""
        while True:
            cand = candidates[selected_cand_idx]
            is_fav = item["id"] in self.favorites
            clear_screen()
            self.render_header(f"Action Selector: {item['name']}")
            print(f"{BOLD}{CYAN}{item['name']}{RESET} {'★ ' if is_fav else ''}{YELLOW}({' '.join(item.get('badges', [])[:4])}){RESET}")
            print(f"{WHITE}{item.get('description', '')}{RESET}")
            print(f"{GRAY}{'─' * cols}{RESET}")
            print(f"{BOLD}{GREEN}Selected Package [{selected_cand_idx + 1}/{len(candidates)}]:{RESET}")
            print(f"  📦 {BOLD}{WHITE}{cand['label']}{RESET}")
            print(f"  🔗 {DIM}{truncate_str(cand['url'], cols - 6)}{RESET}")
            print(f"{GRAY}{'─' * cols}{RESET}")

            print(f"{BOLD}{WHITE}CHOOSE ACTION (VOLUME KEYS OR TYPE 01-06 + ENTER):{RESET}\n")
            print(f"  {BG_SEL}{BOLD}{GREEN} [01] / 🔊 VOL+ Tap   👉  INSTALL NOW (Root Auto-Installer)      {RESET}")
            if cand["type"] == "builtin_script":
                print(f"       {DIM}↳ Installs script to {item.get('install_target')} & executes via su{RESET}")
            elif cand["type"] == "apk":
                print(f"       {DIM}↳ Downloads APK & installs silently via 'su -c pm install -r -d'{RESET}")
            elif cand["type"] == "zip":
                print(f"       {DIM}↳ Downloads ZIP & flashes systemlessly via 'magisk --install-module'{RESET}")
            else:
                print(f"       {DIM}↳ Clones repo & auto-builds/installs Magisk module or scripts{RESET}")

            print(f"  {BG_BADGE}{BOLD}{YELLOW} [02] / 🔉 VOL- Tap   👉  DOWNLOAD ONLY (Save to Storage)       {RESET}")
            print(f"       {DIM}↳ Saves to ~/root-arsenal/downloads/ & {SDCARD_DL_DIR}/{RESET}")

            if len(candidates) > 1:
                print(f"  {BOLD}{CYAN} [03] / 🔊 VOL+ Hold  👉  CYCLE ASSET / VERSION ({selected_cand_idx + 1}/{len(candidates)}){RESET}")
            elif cand["type"] == "builtin_script":
                print(f"  {BOLD}{CYAN} [03] / 🔊 VOL+ Hold  👉  RUN SCRIPT ONCE (Without Installing)  {RESET}")
            else:
                print(f"  {BOLD}{CYAN} [03] / 🔊 VOL+ Hold  👉  RE-RESOLVE / CHECK RELEASES           {RESET}")

            is_queued = item["id"] in self.batch_queue
            print(f"  {BOLD}{MAGENTA} [04] / [v]           👉  VIEW LIVE README, CHANGELOG & AUDIT   {RESET}")
            print(f"  {BOLD}{BLUE} [05] / [f]           👉  {'REMOVE FROM' if is_fav else 'ADD TO'} BOOKMARKED FAVORITES (★)   {RESET}")
            print(f"  {BOLD}{CYAN} [06] / [t]           👉  {'REMOVE FROM' if is_queued else 'ADD TO'} BATCH QUEUE (📥)         {RESET}")
            print(f"  {BOLD}{RED} [07] / 🔉 VOL- Hold  👉  CANCEL / GO BACK                      {RESET}")
            print(f"{GRAY}{'─' * cols}{RESET}")

            if num_buf:
                print(f"{BG_NUM}{BOLD}{YELLOW} 🔢 Action Number: [ {num_buf}█ ]  (Press ENTER to Confirm, Backspace to clear) {RESET}")

            ev = self.input_reader.get_event()
            if not ev or ev == "RESIZE":
                continue

            if ev.isdigit():
                num_buf += ev
                continue
            elif ev == "KEY_BACKSPACE" and num_buf:
                num_buf = num_buf[:-1]
                continue
            elif ev == "KEY_ESC" and num_buf:
                num_buf = ""
                continue

            choice = None
            if ev == "KEY_ENTER" and num_buf:
                choice = int(num_buf)
                num_buf = ""
            elif ev in ("VOL_UP_SHORT", "i", "I") or (ev == "KEY_ENTER" and not num_buf):
                choice = 1
            elif ev in ("VOL_DOWN_SHORT", "d", "D"):
                choice = 2
            elif ev in ("VOL_UP_HOLD", "n"):
                choice = 3
            elif ev in ("v", "V"):
                choice = 4
            elif ev in ("f", "F"):
                choice = 5
            elif ev in ("t", "T"):
                choice = 6
            elif ev in ("VOL_DOWN_HOLD", "b", "B", "q", "KEY_ESC", "KEY_LEFT", "KEY_BACKSPACE"):
                choice = 7

            if choice == 1:
                self.execute_candidate_flow(item, cand, action="install")
                self._refresh_installed_bg()
                break
            elif choice == 2:
                self.execute_candidate_flow(item, cand, action="download")
                break
            elif choice == 3:
                if len(candidates) > 1:
                    selected_cand_idx = (selected_cand_idx + 1) % len(candidates)
                elif cand["type"] == "builtin_script":
                    self.execute_candidate_flow(item, cand, action="run_once")
                    break
            elif choice == 4:
                self.view_readme_modal(item)
            elif choice == 5:
                if item["id"] in self.favorites:
                    self.favorites.remove(item["id"])
                else:
                    self.favorites.add(item["id"])
                self._save_favorites()
            elif choice == 6:
                if item["id"] in self.batch_queue:
                    del self.batch_queue[item["id"]]
                    self.status_msg = f"Removed '{item['name']}' from Batch Queue."
                else:
                    self.batch_queue[item["id"]] = item
                    self.status_msg = f"Added '{item['name']}' to Batch Queue ({len(self.batch_queue)} total)."
            elif choice == 7:
                break

    def view_readme_modal(self, item: dict):
        clear_screen()
        self.render_header(f"Fetching Live Documentation: {item['name']}...")
        print(f"\n{YELLOW}[*] Downloading README.md, Release Changelog & Safety Audit...{RESET}")
        text = fetch_tool_readme_and_audit(item)
        doc_lines = text.splitlines()
        self.input_reader.flush()

        scroll = 0
        while True:
            cols, lines = get_term_size()
            view_h = max(8, lines - 7)
            max_scroll = max(0, len(doc_lines) - view_h)
            scroll = max(0, min(scroll, max_scroll))

            clear_screen()
            self.render_header(f"README & Audit: {item['name']} (Line {scroll + 1}/{len(doc_lines)})")
            for ln in doc_lines[scroll: scroll + view_h]:
                print(truncate_str(ln, cols))
            print(f"{GRAY}{'─' * cols}{RESET}")
            print(f"{BOLD}{YELLOW}🔊 VOL+ Tap{RESET}: Scroll Up  {BOLD}{YELLOW}🔉 VOL- Tap{RESET}: Scroll Down  {BOLD}{RED}🔉 VOL- Hold / [b] / [Enter]{RESET}: Back")

            ev = self.input_reader.get_event()
            if not ev or ev == "RESIZE":
                continue
            if ev in ("VOL_UP_SHORT", "KEY_UP", "k"):
                scroll -= 4
            elif ev in ("VOL_DOWN_SHORT", "KEY_DOWN", "j", " "):
                scroll += 4
            elif ev == "KEY_PGUP":
                scroll -= view_h
            elif ev == "KEY_PGDN":
                scroll += view_h
            elif ev in ("VOL_DOWN_HOLD", "VOL_UP_HOLD", "KEY_ENTER", "KEY_ESC", "b", "q", "KEY_LEFT", "KEY_BACKSPACE"):
                break

    def batch_queue_modal(self):
        num_buf = ""
        while True:
            cols, _ = get_term_size()
            queued_list = list(self.batch_queue.values())
            clear_screen()
            self.render_header(f"Batch Queue Manager ({len(queued_list)} Tools Queued)")
            if not queued_list:
                print(f"\n  {YELLOW}Your Batch Queue is currently empty.{RESET}")
                print(f"  {WHITE}How to add multiple tools:{RESET}")
                print(f"    • In any Tool List, type a comma list or range like {CYAN}1,4,12{WHITE} or {CYAN}5-10{WHITE} + {GREEN}Enter{RESET}")
                print(f"    • Or press {CYAN}[t]{WHITE} or {CYAN}[Space]{WHITE} on any tool to toggle its {GREEN}[✓]{WHITE} checkmark!{RESET}\n")
                print(f"{GRAY}{'─' * cols}{RESET}")
                print(f"{DIM}Press any Volume Key or [b] to go back...{RESET}")
                self.input_reader.flush()
                self.input_reader.get_event()
                return

            for i, it in enumerate(queued_list[:12], 1):
                print(f"  {GREEN}[{i:02d}]{RESET} {BOLD}{WHITE}{it['name']}{RESET} {DIM}({it.get('category')}){RESET}")
            if len(queued_list) > 12:
                print(f"  {DIM}... and {len(queued_list) - 12} more queued tools{RESET}")

            print(f"{GRAY}{'─' * cols}{RESET}")
            print(f"  {BG_SEL}{BOLD}{GREEN} [01] / 🔊 VOL+ Tap   👉  BATCH INSTALL ALL ({len(queued_list)} TOOLS)   {RESET}")
            print(f"  {BG_BADGE}{BOLD}{YELLOW} [02] / 🔉 VOL- Tap   👉  BATCH DOWNLOAD ALL ({len(queued_list)} TOOLS)  {RESET}")
            print(f"  {BOLD}{RED} [03] / [c]           👉  CLEAR BATCH QUEUE                     {RESET}")
            print(f"  {BOLD}{WHITE} [04] / 🔉 VOL- Hold  👉  GO BACK                               {RESET}")
            print(f"{GRAY}{'─' * cols}{RESET}")
            if num_buf:
                print(f"{BG_NUM}{BOLD}{YELLOW} 🔢 Action #: [ {num_buf}█ ] (Press ENTER to Confirm) {RESET}")

            ev = self.input_reader.get_event()
            if not ev or ev == "RESIZE":
                continue
            if ev.isdigit():
                num_buf += ev
                continue
            elif ev == "KEY_BACKSPACE" and num_buf:
                num_buf = num_buf[:-1]
                continue

            choice = None
            if ev == "KEY_ENTER" and num_buf:
                choice = int(num_buf)
                num_buf = ""
            elif ev in ("VOL_UP_SHORT", "i") or (ev == "KEY_ENTER" and not num_buf):
                choice = 1
            elif ev in ("VOL_DOWN_SHORT", "d"):
                choice = 2
            elif ev in ("c", "C"):
                choice = 3
            elif ev in ("VOL_DOWN_HOLD", "b", "q", "KEY_ESC", "KEY_LEFT"):
                choice = 4

            if choice in (1, 2):
                act = "install" if choice == 1 else "download"
                clear_screen()
                self.render_header(f"Running Batch {act.upper()} ({len(queued_list)} Tools)...")
                for idx, it in enumerate(queued_list, 1):
                    print(f"\n{BOLD}{CYAN}[{idx}/{len(queued_list)}] Processing: {it['name']}...{RESET}")
                    cands = resolve_download_candidates(it)
                    if not cands:
                        print(f"  {RED}✖ No downloadable assets resolved.{RESET}")
                        continue
                    ok, msg = perform_action_on_candidate(it, cands[0], action=act)
                    status_icon = f"{GREEN}✔" if ok else f"{RED}✖"
                    print(f"  {status_icon} {msg.splitlines()[0] if msg else ''}{RESET}")
                self._refresh_installed_bg()
                print(f"\n{GREEN}{BOLD}=== Batch Operation Finished! Press any Volume Key or Enter ==={RESET}")
                self.input_reader.flush()
                self.input_reader.get_event()
                break
            elif choice == 3:
                self.batch_queue.clear()
                self.status_msg = "Cleared Batch Queue."
                break
            elif choice == 4:
                break

    def live_control_center_loop(self):
        """
        Interactive On-Device Root & Hardware Control Center.
        Supports 2-digit action codes (01-12 + Enter) OR Volume Keys!
        """
        cursor = 0
        num_buf = ""
        actions = [
            ("Start / Restart Shizuku Server via Root (No ADB Needed)", "shizuku_start"),
            ("Toggle SELinux Mode (Enforcing ↔ Permissive)", "selinux_toggle"),
            ("Switch CPU Governor (schedutil / performance / powersave)", "cpu_gov"),
            ("Configure Display Refresh Rate (120Hz Forced / Adaptive)", "hz_toggle"),
            ("Apply resetprop Bootloader & VerifiedBoot Stealth Hardening", "resetprop_stealth"),
            ("Audit Magisk SQLite Policies & Superuser Grants", "magisk_audit"),
            ("Backup All Installed Modules & Root Scripts (.tar.gz)", "backup_all"),
            ("Run ART 'speed-profile' DEX Optimization on Core System Apps", "dexopt"),
            ("Soft-Restart Zygote (Reload Zygisk/LSPosed without full reboot)", "restart_zygote"),
            ("Soft-Restart Android SystemUI (Reload Status Bar / Overlays)", "restart_sysui"),
            ("Flush RAM & Drop Linux Pagecaches (sync + drop_caches)", "drop_caches"),
            ("Emergency Safe-Mode: Disable All Installed Magisk Modules", "disable_all_mods"),
        ]

        while True:
            cols, _ = get_term_size()
            tele = get_live_device_telemetry()
            clear_screen()
            self.render_header("🎛️ Live Root & Hardware Control Center")

            # Telemetry Panel
            model = tele.get('MODEL', 'Android')
            abi = tele.get('ABI', 'arm64-v8a')
            print(
                f" {BOLD}{WHITE}Device :{RESET} {CYAN}{model}{RESET} • Android {tele.get('ANDROID', '14')} ({abi})  |  "
                f"{BOLD}{WHITE}Root :{RESET} {GREEN}Magisk {tele.get('MAGISK', 'Active')}{RESET}"
            )
            cpu_min = tele.get('CPU_MIN_MHZ', '?')
            cpu_max = tele.get('CPU_MAX_MHZ', '?')
            print(
                f" {BOLD}{WHITE}CPU    :{RESET} {YELLOW}{tele.get('GOV', 'schedutil')}{RESET} (Min: {cpu_min} MHz, Max: {cpu_max} MHz)  |  "
                f"{BOLD}{WHITE}SELinux :{RESET} {MAGENTA}{tele.get('SELINUX', 'Enforcing')}{RESET}"
            )
            shiz_col = GREEN if tele.get("SHIZUKU") == "RUNNING" else RED
            print(
                f" {BOLD}{WHITE}Battery:{RESET} {GREEN}{tele.get('BAT_CAP', '?')}{RESET} ({tele.get('BAT_TEMP', '?')}, Cycles: {tele.get('BAT_CYCLES', '?')})  |  "
                f"{BOLD}{WHITE}Shizuku :{RESET} {shiz_col}{tele.get('SHIZUKU', 'STOPPED')}{RESET}  |  {BOLD}{WHITE}Peak Hz:{RESET} {CYAN}{tele.get('HZ', '120')}{RESET}"
            )
            print(f"{GRAY}{'─' * cols}{RESET}")
            print(f"{BOLD}{WHITE}SELECT INSTANT ROOT ACTION (TYPE 01-12 + ENTER OR USE VOLUME KEYS):{RESET}")

            for idx, (label, _) in enumerate(actions):
                is_sel = (idx == cursor)
                prefix = "▶ " if is_sel else "  "
                line = f"{prefix}[{idx + 1:02d}] {label}"
                if is_sel:
                    print(f"{BG_SEL}{BOLD}{WHITE}{truncate_str(line, cols).ljust(cols)}{RESET}")
                else:
                    print(f"{YELLOW}{prefix}[{idx + 1:02d}]{RESET} {WHITE}{truncate_str(label, cols - 9)}{RESET}")

            self.render_footer_list(num_buf=num_buf, allow_ranges=False)
            ev = self.input_reader.get_event()
            if not ev or ev == "RESIZE":
                continue

            if ev.isdigit():
                num_buf += ev
                idxs = parse_number_or_range(num_buf, len(actions))
                if idxs:
                    cursor = idxs[-1]
                continue
            elif ev == "KEY_BACKSPACE":
                if num_buf:
                    num_buf = num_buf[:-1]
                else:
                    break
                continue
            elif ev == "KEY_ESC":
                if num_buf:
                    num_buf = ""
                else:
                    break
                continue
            elif ev in ("KEY_ENTER", "VOL_UP_HOLD") and num_buf:
                idxs = parse_number_or_range(num_buf, len(actions))
                num_buf = ""
                if idxs:
                    cursor = idxs[0]
                    self._exec_control_center_action(actions[cursor][0], actions[cursor][1], tele)
                continue

            if ev in ("VOL_UP_SHORT", "KEY_UP", "k"):
                cursor = (cursor - 1) % len(actions)
            elif ev in ("VOL_DOWN_SHORT", "KEY_DOWN", "j"):
                cursor = (cursor + 1) % len(actions)
            elif ev in ("VOL_UP_HOLD", "KEY_ENTER", " "):
                self._exec_control_center_action(actions[cursor][0], actions[cursor][1], tele)
            elif ev in ("VOL_DOWN_HOLD", "b", "q", "KEY_LEFT"):
                break

    def _exec_control_center_action(self, label: str, code_id: str, tele: dict):
        clear_screen()
        self.render_header(f"Executing: {label}")
        print(f"\n{YELLOW}[*] Running root action '{code_id}'...{RESET}\n")
        out_msg = ""
        if code_id == "shizuku_start":
            from catalog_builtin import BUILTIN_SCRIPTS
            from installer import execute_or_install_builtin_script
            shiz_item = BUILTIN_SCRIPTS[0]
            _, out_msg = execute_or_install_builtin_script(shiz_item, mode="run")
        elif code_id == "selinux_toggle":
            cur = tele.get("SELINUX", "Enforcing")
            target = "0" if "Enforcing" in cur else "1"
            _, out_msg = run_root_cmd(f"setenforce {target} && echo 'New SELinux status:' $(getenforce)")
        elif code_id == "cpu_gov":
            cur = tele.get("GOV", "schedutil")
            nxt = "performance" if cur == "schedutil" else ("powersave" if cur == "performance" else "schedutil")
            _, out_msg = run_root_cmd(
                f"for p in /sys/devices/system/cpu/cpufreq/policy*; do echo {nxt} > \"$p/scaling_governor\" 2>/dev/null; done; "
                f"echo 'Set all CPU clusters to governor:' $(cat /sys/devices/system/cpu/cpufreq/policy0/scaling_governor)"
            )
        elif code_id == "hz_toggle":
            cur = tele.get("HZ", "120.0")
            nxt = "60.0" if "120" in str(cur) else "120.0"
            _, out_msg = run_root_cmd(f"settings put system peak_refresh_rate {nxt}; settings put system min_refresh_rate {nxt}; echo 'Display Refresh Rate set to {nxt} Hz'")
        elif code_id == "resetprop_stealth":
            from catalog_builtin import BUILTIN_SCRIPTS
            from installer import execute_or_install_builtin_script
            _, out_msg = execute_or_install_builtin_script(BUILTIN_SCRIPTS[3], mode="run")
        elif code_id == "magisk_audit":
            from catalog_builtin import BUILTIN_SCRIPTS
            from installer import execute_or_install_builtin_script
            _, out_msg = execute_or_install_builtin_script(BUILTIN_SCRIPTS[8], mode="run")
        elif code_id == "backup_all":
            _, out_msg = backup_all_modules_and_scripts()
        elif code_id == "dexopt":
            from catalog_builtin import BUILTIN_SCRIPTS
            from installer import execute_or_install_builtin_script
            _, out_msg = execute_or_install_builtin_script(BUILTIN_SCRIPTS[4], mode="run")
        elif code_id == "restart_zygote":
            _, out_msg = soft_restart_zygote()
        elif code_id == "restart_sysui":
            _, out_msg = run_root_cmd("killall com.android.systemui && echo '[+] SystemUI restarted cleanly.'")
        elif code_id == "drop_caches":
            _, out_msg = run_root_cmd("sync && echo 3 > /proc/sys/vm/drop_caches && echo '[+] Flushed pagecaches and dentries/inodes.'")
        elif code_id == "disable_all_mods":
            _, out_msg = run_root_cmd("for d in /data/adb/modules/*; do [ -d \"$d\" ] && touch \"$d/disable\"; done; echo '[+] All modules disabled (Safe Mode).'")

        vibrate_tick(40)
        print(f"{WHITE}{out_msg}{RESET}")
        print(f"\n{BOLD}{GREEN}Press any Volume Key or Enter to return to Control Center...{RESET}")
        self.input_reader.flush()
        self.input_reader.get_event()

    def local_downloads_loop(self):
        cursor = 0
        num_buf = ""
        while True:
            files = list_local_downloads()
            cols, _ = get_term_size()
            clear_screen()
            self.render_header(f"📂 Local Downloads & Package Installer ({len(files)} files)")
            if not files:
                print(f"\n  {YELLOW}No downloaded .apk, .zip, or .sh files found yet.{RESET}\n")
                print(f"{DIM}Press any Volume Key or [b] to go back...{RESET}")
                self.input_reader.flush()
                self.input_reader.get_event()
                return

            if cursor >= len(files):
                cursor = len(files) - 1
            for idx, f in enumerate(files):
                is_sel = (idx == cursor)
                line = f"{'▶ ' if is_sel else '  '}[{idx + 1:02d}] {f['name']} ({f['size_mb']}) [{f['type'].upper()}]"
                if is_sel:
                    print(f"{BG_SEL}{BOLD}{WHITE}{truncate_str(line, cols).ljust(cols)}{RESET}")
                    print(f"       {CYAN}{truncate_str(f['path'], cols - 7)}{RESET}")
                else:
                    print(f"{WHITE}{truncate_str(line, cols)}{RESET}")

            print(f"{GRAY}{'─' * cols}{RESET}")
            print(f"{BOLD}{GREEN}🔊 VOL+ Hold / Enter / #+{RESET}: Install/Run File  {BOLD}{RED}[x]{RESET}: Delete File  {BOLD}{RED}🔉 VOL- Hold / [b]{RESET}: Back")
            if num_buf:
                print(f"{BG_NUM}{BOLD}{YELLOW} 🔢 File #: [ {num_buf}█ ] (Press ENTER to Install/Run) {RESET}")

            ev = self.input_reader.get_event()
            if not ev or ev == "RESIZE":
                continue
            if ev.isdigit():
                num_buf += ev
                idxs = parse_number_or_range(num_buf, len(files))
                if idxs:
                    cursor = idxs[-1]
                continue
            elif ev == "KEY_BACKSPACE" and num_buf:
                num_buf = num_buf[:-1]
                continue
            elif ev in ("KEY_ENTER", "VOL_UP_HOLD") and num_buf:
                idxs = parse_number_or_range(num_buf, len(files))
                num_buf = ""
                if idxs:
                    cursor = idxs[0]
                    self._install_local_file(files[cursor])
                continue

            if ev in ("VOL_UP_SHORT", "KEY_UP", "k"):
                cursor = (cursor - 1) % len(files)
            elif ev in ("VOL_DOWN_SHORT", "KEY_DOWN", "j"):
                cursor = (cursor + 1) % len(files)
            elif ev in ("VOL_UP_HOLD", "KEY_ENTER", " "):
                self._install_local_file(files[cursor])
            elif ev in ("x", "X"):
                try:
                    os.remove(files[cursor]["path"])
                    self.status_msg = f"Deleted {files[cursor]['name']}"
                except Exception as e:
                    self.status_msg = f"Delete error: {e}"
            elif ev in ("VOL_DOWN_HOLD", "b", "q", "KEY_ESC", "KEY_LEFT"):
                break

    def _install_local_file(self, fentry: dict):
        clear_screen()
        self.render_header(f"Installing Local Package: {fentry['name']}")
        p = fentry["path"]
        if fentry["type"] == "apk":
            ok, msg = install_apk_root(p)
        elif fentry["type"] == "zip":
            ok, msg = inspect_and_install_zip(p)
        else:
            _, msg = run_root_cmd(f"sh '{p}'")
            ok = True
        print(f"\n{WHITE}{msg}{RESET}\n")
        print(f"{YELLOW}Press any Volume Key or Enter to continue...{RESET}")
        self.input_reader.flush()
        self.input_reader.get_event()

    def trigger_recrawl(self):
        clear_screen()
        self.render_header("Crawling All 8 Live Sources in Parallel...")
        print(f"\n{YELLOW}{BOLD}[*] Launching multi-threaded crawler across 29 feeds...{RESET}\n")

        def prog(done, total, label, count):
            print(f"  {GREEN}[{done:02d}/{total:02d}]{RESET} {label:<36} -> {CYAN}{count} raw items{RESET}")

        self.items = crawl_all(progress_cb=prog)
        self._refresh_installed_bg()
        self.status_msg = f"Crawl complete! {len(self.items)} unique tools indexed."
        self.input_reader.flush()
        time.sleep(0.8)

    def prompt_and_search(self):
        self.input_reader.stop()
        clear_screen()
        self.render_header("Live Deep Search & Custom Keyword Crawler")
        print(f"\n{WHITE}Enter a keyword (e.g. {CYAN}viper4android{WHITE}, {CYAN}lsposed{WHITE}, {CYAN}shizuku{WHITE}, {CYAN}battery{WHITE}, {CYAN}kona{WHITE}):{RESET}")
        try:
            q = input(f"{YELLOW}Search Query > {RESET}").strip()
        except EOFError:
            q = ""
        self.input_reader.start()
        if not q:
            return
        ql = q.lower()
        local_matches = [
            it for it in self.items
            if ql in it.get("name", "").lower()
            or ql in it.get("description", "").lower()
            or ql in it.get("subcategory", "").lower()
            or any(ql in b.lower() for b in it.get("badges", []))
        ]
        print(f"\n{CYAN}[*] Found {len(local_matches)} local matches. Also crawling GitHub & F-Droid live for '{q}'...{RESET}")
        live_matches = live_query_crawl(q)
        seen_urls = {it.get("url") for it in local_matches if it.get("url")}
        for lm in live_matches:
            if lm.get("url") not in seen_urls:
                local_matches.append(lm)
                seen_urls.add(lm.get("url"))
        self.input_reader.flush()
        self.tools_list_loop(f"🔍 Search: '{q}' ({len(local_matches)} results)", local_matches)

    def execute_candidate_flow(self, item: dict, cand: dict, action: str):
        cols, _ = get_term_size()
        clear_screen()
        act_title = "INSTALLING" if action == "install" else ("RUNNING" if action == "run_once" else "DOWNLOADING")
        self.render_header(f"{act_title}: {item['name']}")
        print(f"\n{YELLOW}{BOLD}[*] Target: {cand['label']}{RESET}")
        print(f"{DIM}URL: {cand['url']}{RESET}\n")

        def dl_prog(done, total):
            if total > 0:
                pct = int(done * 100 / total)
                bar_w = 26
                filled = int(bar_w * pct / 100)
                bar = "█" * filled + "░" * (bar_w - filled)
                mb_done = done / (1024 * 1024)
                mb_tot = total / (1024 * 1024)
                sys.stdout.write(f"\r  {CYAN}[{bar}] {pct:3d}% ({mb_done:.1f}/{mb_tot:.1f} MB){RESET}")
                sys.stdout.flush()

        extra = {}
        if action == "run_once" and cand["type"] == "builtin_script":
            from installer import execute_or_install_builtin_script
            ok, msg = execute_or_install_builtin_script(item, mode="run")
            extra = {"type": "builtin_script"}
        else:
            ok, msg, extra = perform_action_on_candidate(item, cand, action=action, progress_cb=dl_prog)
        print("\n")
        print(f"{GRAY}{'─' * cols}{RESET}")
        if ok:
            vibrate_tick(45)
            print(f"{GREEN}{BOLD}✔ OPERATION SUCCEEDED!{RESET}\n")
        else:
            vibrate_tick(80)
            print(f"{RED}{BOLD}✖ OPERATION REPORT:{RESET}\n")
        print(f"{WHITE}{msg}{RESET}")
        print(f"{GRAY}{'─' * cols}{RESET}")

        if ok and action == "install":
            self._post_install_actions_menu(item, extra)
        else:
            print(f"\n{BOLD}{YELLOW}Press any Volume Key or Enter to continue...{RESET}")
            self.input_reader.flush()
            self.input_reader.get_event()

    def _post_install_actions_menu(self, item: dict, extra: dict):
        """Displays instant smart root post-install actions for APKs and Magisk modules."""
        cols, _ = get_term_size()
        t = (extra or {}).get("type", "")
        pkg = (extra or {}).get("pkg_name") or item.get("package_id") or ""
        num_buf = ""

        if t == "apk":
            while True:
                print(f"\n{BOLD}{GREEN}📦 SMART POST-INSTALL SHORTCUTS ({pkg or item['name']}):{RESET}")
                print(f"  {BG_SEL}{BOLD}{CYAN} [01] / 🔊 VOL+ Tap  👉  LAUNCH APP NOW (Root Launcher)          {RESET}")
                print(f"  {BOLD}{YELLOW} [02]                👉  AUTO-GRANT ALL RUNTIME PERMISSIONS (pm grant) {RESET}")
                print(f"  {BOLD}{MAGENTA} [03]                👉  OPEN APP INFO IN ANDROID SETTINGS             {RESET}")
                print(f"  {BOLD}{WHITE} [04] / Enter / Back 👉  RETURN TO TOOL CATALOG                        {RESET}")
                if num_buf:
                    print(f"{BG_NUM}{BOLD}{YELLOW} 🔢 Action #: [ {num_buf}█ ] (Press ENTER to Confirm) {RESET}")

                ev = self.input_reader.get_event()
                if not ev or ev == "RESIZE":
                    continue
                if ev.isdigit():
                    num_buf += ev
                    continue
                elif ev == "KEY_BACKSPACE" and num_buf:
                    num_buf = num_buf[:-1]
                    continue

                choice = None
                if ev == "KEY_ENTER" and num_buf:
                    choice = int(num_buf)
                    num_buf = ""
                elif ev in ("VOL_UP_SHORT", "1"):
                    choice = 1
                elif ev in ("2",):
                    choice = 2
                elif ev in ("3",):
                    choice = 3
                elif ev in ("VOL_DOWN_HOLD", "b", "q", "KEY_ESC", "KEY_LEFT", "4") or (ev == "KEY_ENTER" and not num_buf):
                    choice = 4

                if choice == 1:
                    _, msg_l = launch_app(pkg)
                    print(f"\n{GREEN}{msg_l}{RESET}")
                    time.sleep(1.0)
                    break
                elif choice == 2:
                    _, msg_p = grant_all_permissions_root(pkg)
                    print(f"\n{GREEN}{msg_p}{RESET}")
                    time.sleep(1.2)
                    break
                elif choice == 3:
                    run_root_cmd(f"am start -a android.settings.APPLICATION_DETAILS_SETTINGS package:{pkg}")
                    break
                elif choice == 4:
                    break

        elif t == "module":
            while True:
                print(f"\n{BOLD}{GREEN}⚡ SYSTEMLESS MAGISK MODULE INSTALLED:{RESET}")
                print(f"  {BG_SEL}{BOLD}{CYAN} [01] / 🔊 VOL+ Tap  👉  SOFT-RESTART ZYGOTE (Reload Zygisk in ~5s) {RESET}")
                print(f"  {BOLD}{YELLOW} [02]                👉  FULL DEVICE REBOOT                            {RESET}")
                print(f"  {BOLD}{WHITE} [03] / Enter / Back 👉  RETURN TO TOOL CATALOG (Reboot Later)         {RESET}")
                if num_buf:
                    print(f"{BG_NUM}{BOLD}{YELLOW} 🔢 Action #: [ {num_buf}█ ] (Press ENTER to Confirm) {RESET}")

                ev = self.input_reader.get_event()
                if not ev or ev == "RESIZE":
                    continue
                if ev.isdigit():
                    num_buf += ev
                    continue
                elif ev == "KEY_BACKSPACE" and num_buf:
                    num_buf = num_buf[:-1]
                    continue

                choice = None
                if ev == "KEY_ENTER" and num_buf:
                    choice = int(num_buf)
                    num_buf = ""
                elif ev in ("VOL_UP_SHORT", "1"):
                    choice = 1
                elif ev in ("2",):
                    choice = 2
                elif ev in ("VOL_DOWN_HOLD", "b", "q", "KEY_ESC", "KEY_LEFT", "3") or (ev == "KEY_ENTER" and not num_buf):
                    choice = 3

                if choice == 1:
                    soft_restart_zygote()
                    print(f"\n{GREEN}[+] Zygote soft restart dispatched! UI reloading in background...{RESET}")
                    time.sleep(2.0)
                    break
                elif choice == 2:
                    run_root_cmd("reboot")
                    break
                elif choice == 3:
                    break
        else:
            print(f"\n{BOLD}{YELLOW}Press any Volume Key or Enter to continue...{RESET}")
            self.input_reader.flush()
            self.input_reader.get_event()

    def installed_modules_loop(self):
        cursor = 0
        num_buf = ""
        while True:
            mods = list_installed_device_modules()
            cols, _ = get_term_size()
            clear_screen()
            self.render_header(f"Installed Systemless Modules (/data/adb/modules: {len(mods)})")
            if not mods:
                print(f"\n  {YELLOW}No Magisk/KernelSU modules are currently installed in /data/adb/modules/.{RESET}")
                print(f"  {WHITE}Tip: Browse the '📦 Magisk / KernelSU / APatch Modules' category to install modules!{RESET}\n")
                print(f"{GRAY}{'─' * cols}{RESET}")
                print(f"{DIM}Press any Volume Key or [b] to go back...{RESET}")
                self.input_reader.flush()
                self.input_reader.get_event()
                return

            if cursor >= len(mods):
                cursor = len(mods) - 1

            for idx, m in enumerate(mods):
                is_sel = (idx == cursor)
                line = f"{'▶ ' if is_sel else '  '}[{idx + 1:02d}] {m['name']} ({m['version']}) [{m['state']}]"
                if is_sel:
                    print(f"{BG_SEL}{BOLD}{WHITE}{truncate_str(line, cols).ljust(cols)}{RESET}")
                    print(f"       {CYAN}{truncate_str(m['description'], cols - 7)}{RESET}")
                else:
                    print(f"{WHITE}{truncate_str(line, cols)}{RESET}")

            print(f"{GRAY}{'─' * cols}{RESET}")
            print(f"{BOLD}{YELLOW}🔊 VOL+ Tap{RESET}: Up  {BOLD}{YELLOW}🔉 VOL- Tap{RESET}: Down  {BOLD}{GREEN}🔊 VOL+ Hold / Enter / #+{RESET}: Toggle  {BOLD}{RED}[r]{RESET}: Remove  {BOLD}{RED}🔉 VOL- Hold / [b]{RESET}: Back")
            if num_buf:
                print(f"{BG_NUM}{BOLD}{YELLOW} 🔢 Module #: [ {num_buf}█ ] (Press ENTER to Toggle Enable/Disable) {RESET}")

            ev = self.input_reader.get_event()
            if not ev or ev == "RESIZE":
                continue
            if ev.isdigit():
                num_buf += ev
                idxs = parse_number_or_range(num_buf, len(mods))
                if idxs:
                    cursor = idxs[-1]
                continue
            elif ev == "KEY_BACKSPACE" and num_buf:
                num_buf = num_buf[:-1]
                continue
            elif ev in ("KEY_ENTER", "VOL_UP_HOLD") and num_buf:
                idxs = parse_number_or_range(num_buf, len(mods))
                num_buf = ""
                if idxs:
                    cursor = idxs[0]
                    target = mods[cursor]
                    new_act = "disable" if target["state"] == "ENABLED" else "enable"
                    _, msg = toggle_installed_module(target["id"], new_act)
                    self.status_msg = msg
                continue

            if ev in ("VOL_UP_SHORT", "KEY_UP", "k"):
                cursor = (cursor - 1) % len(mods)
            elif ev in ("VOL_DOWN_SHORT", "KEY_DOWN", "j"):
                cursor = (cursor + 1) % len(mods)
            elif ev in ("VOL_UP_HOLD", "KEY_ENTER", " "):
                target = mods[cursor]
                new_act = "disable" if target["state"] == "ENABLED" else "enable"
                _, msg = toggle_installed_module(target["id"], new_act)
                self.status_msg = msg
            elif ev in ("r", "R"):
                target = mods[cursor]
                _, msg = toggle_installed_module(target["id"], "remove")
                self.status_msg = msg
            elif ev in ("VOL_DOWN_HOLD", "b", "q", "KEY_ESC", "KEY_LEFT"):
                break


def main():
    parser = argparse.ArgumentParser(
        description="RootArsenal v2.5: Smart Multi-Source Root/Shizuku/Module Crawler, Multi-Digit & Volume-Key Installer"
    )
    parser.add_argument("--crawl", action="store_true", help="Force re-crawl all 8 live sources and update cache")
    parser.add_argument("--categories", action="store_true", help="List all categories and tool counts")
    parser.add_argument("--telemetry", action="store_true", help="Display live OnePlus 8T root & hardware telemetry")
    parser.add_argument("--backup", action="store_true", help="Create a full backup of /data/adb/modules and magisk.db")
    parser.add_argument("--adb", action="store_true", help="Run in ADB mode for Windows / PC USB connection")
    parser.add_argument("--device", type=str, default=None, help="Specific ADB device serial (optional)")
    parser.add_argument("--search", type=str, help="Search local catalog + live crawl for a keyword")
    parser.add_argument("--install", type=str, help="Find best matching tool by ID, number, or name and install via root")
    parser.add_argument("--download", type=str, help="Find best matching tool by ID, number, or name and download only")
    args = parser.parse_args()

    if args.adb:
        set_adb_mode(True, args.device)

    if args.crawl:
        print(f"{CYAN}[*] Crawling all 8 sources in parallel...{RESET}")
        items = crawl_all(progress_cb=lambda d, t, lbl, c: print(f"  [{d:02d}/{t:02d}] {lbl} -> {c} items"))
        print(f"{GREEN}[+] Successfully indexed {len(items)} unique tools!{RESET}")
        return

    if args.telemetry:
        t = get_live_device_telemetry()
        model = t.get("MODEL", "Android Device")
        print(f"{BOLD}{CYAN}=== Live Root & Hardware Telemetry ({model}) ==={RESET}")
        for k, v in t.items():
            print(f"  {BOLD}{k:<12}:{RESET} {v}")
        return

    if args.backup:
        ok, msg = backup_all_modules_and_scripts()
        print(msg)
        sys.exit(0 if ok else 1)

    items = load_or_crawl(force_refresh=False)

    if args.categories:
        print(f"{BOLD}{CYAN}=== RootArsenal Categories ({len(items)} Total Tools) ==={RESET}")
        for idx, c in enumerate(CATEGORIES, 1):
            cnt = sum(1 for it in items if it.get("category") == c)
            print(f"  [{idx:02d}] {c:<46} ({cnt} tools)")
        return

    if args.search:
        q = args.search.lower()
        matches = [
            it for it in items
            if q in it.get("name", "").lower() or q in it.get("description", "").lower()
        ]
        live = live_query_crawl(args.search)
        seen = {it.get("url") for it in matches}
        for lm in live:
            if lm.get("url") not in seen:
                matches.append(lm)
        print(f"{BOLD}{CYAN}=== Search Results for '{args.search}' ({len(matches)} found) ==={RESET}")
        for idx, it in enumerate(matches[:25], 1):
            b_str = " ".join(f"[{b}]" for b in it.get("badges", [])[:3])
            print(f"[{idx:02d}] {BOLD}{WHITE}{it['name']}{RESET} {YELLOW}{b_str}{RESET} ({it.get('category')})")
            print(f"     {GRAY}{it.get('description')}{RESET}")
            print(f"     {BLUE}{it.get('url')}{RESET}")
        return

    if args.install or args.download:
        target_q = (args.install or args.download).strip()
        act = "install" if args.install else "download"
        match = None
        if target_q.isdigit():
            n = int(target_q)
            if 1 <= n <= len(items):
                match = items[n - 1]
        if not match:
            ql = target_q.lower()
            match = next(
                (it for it in items if it["id"].lower() == ql or it["name"].lower() == ql),
                None
            ) or next(
                (it for it in items if ql in it["name"].lower() or ql in it["id"].lower()),
                None
            )
        if not match:
            print(f"{RED}[!] No tool matching '{target_q}' found.{RESET}")
            sys.exit(1)
        print(f"{CYAN}[*] Selected: {match['name']} ({match['url']}){RESET}")
        cands = resolve_download_candidates(match)
        if not cands:
            print(f"{RED}[!] Could not resolve downloadable assets for {match['name']}.{RESET}")
            sys.exit(1)
        print(f"{YELLOW}[*] Best asset: {cands[0]['label']}{RESET}")
        ok, msg = perform_action_on_candidate(match, cands[0], action=act)
        print(msg)
        sys.exit(0 if ok else 1)

    # Launch Interactive Volume-Key & Multi-Digit TUI
    tui = RootArsenalTUI(items)
    tui.run()


if __name__ == "__main__":
    main()
