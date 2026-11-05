#!/data/data/com.termux/files/usr/bin/env python3
"""
Multi-Source Smart Crawler Engine for RootArsenal.
Crawls and indexes root apps, Magisk/KernelSU/APatch modules, Zygisk/LSPosed modules,
Shizuku implementations & addons, device-editing tools, and on-device root scripts.
"""

import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote_plus
import requests

from catalog_builtin import BUILTIN_SCRIPTS, SEED_TOOLS

CACHE_DIR = os.path.expanduser("~/.cache/root-arsenal")
CACHE_FILE = os.path.join(CACHE_DIR, "catalog.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android) RootArsenal/2.5",
    "Accept": "application/json, text/plain, */*"
}

CATEGORIES = [
    "🛠️ On-Device Root Scripts & System Tweaks",
    "👑 Root Handling, Zygisk & Hiding",
    "⚡ Shizuku & Addons (450+ Tools)",
    "📦 Magisk / KernelSU / APatch Modules",
    "⚙️ Root Device-Editing & System Tools",
    "🔥 Performance, Kernel & Battery",
    "🧩 LSPosed / Xposed & App Mods",
    "🧹 Debloating, Backup & File Managers",
    "🛡️ Privacy, Security & Ad-Blocking",
    "🌐 Network, Audio & Display/UI",
    "💻 Terminal, ADB & Linux Chroot",
    "🎮 Gaming & Hardware Spoofing",
]

AAR_CATEGORY_MAP = {
    "root-management": "👑 Root Handling, Zygisk & Hiding",
    "system": "⚙️ Root Device-Editing & System Tools",
    "performance": "🔥 Performance, Kernel & Battery",
    "privacy": "🛡️ Privacy, Security & Ad-Blocking",
    "security": "🛡️ Privacy, Security & Ad-Blocking",
    "ad-blocking": "🛡️ Privacy, Security & Ad-Blocking",
    "app-modifications": "🧩 LSPosed / Xposed & App Mods",
    "debloating": "🧹 Debloating, Backup & File Managers",
    "file-management": "🧹 Debloating, Backup & File Managers",
    "backup": "🧹 Debloating, Backup & File Managers",
    "customization": "🌐 Network, Audio & Display/UI",
    "audio": "🌐 Network, Audio & Display/UI",
    "networking": "🌐 Network, Audio & Display/UI",
    "gaming": "🎮 Gaming & Hardware Spoofing",
    "development": "💻 Terminal, ADB & Linux Chroot",
    "utilities": "⚙️ Root Device-Editing & System Tools",
}


def normalize_url_key(url: str) -> str:
    if not url:
        return ""
    u = url.strip().rstrip("/")
    u = re.sub(r"^https?://(www\.)?", "", u.lower())
    u = re.sub(r"/blob/[^/]+/readme.*$", "", u)
    u = re.sub(r"\.git$", "", u)
    return u


def clean_markdown_text(text: str) -> str:
    # Remove markdown links inside description but keep label
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Remove backtick badges like `FOSS` `[M]`
    text = re.sub(r"`[^`]+`", "", text)
    text = re.sub(r"\s+", " ", text).strip(" -–—·")
    return text.strip()


def extract_badges(raw_line: str) -> list:
    badges = []
    for b in re.findall(r"`([^`]+)`", raw_line):
        b_clean = b.strip("[] ")
        if b_clean == "M":
            badges.append("MAGISK")
        elif b_clean == "K":
            badges.append("KSU")
        elif b_clean == "A":
            badges.append("APATCH")
        elif b_clean == "LSP":
            badges.append("LSPOSED")
        elif len(b_clean) <= 14:
            badges.append(b_clean.upper())
    if "⭐" in raw_line:
        badges.insert(0, "★TOP")
    return list(dict.fromkeys(badges))[:5]


def infer_kind_from_item(url: str, badges: list, category: str, desc: str) -> str:
    if url.startswith("builtin://"):
        return "root_script"
    if url.endswith(".zip"):
        return "module_zip"
    if url.endswith(".apk"):
        return "apk_direct"
    b_set = set(badges)
    if b_set & {"MAGISK", "KSU", "APATCH"} and "LSPOSED" not in b_set:
        return "module_repo"
    if "📦 Magisk" in category:
        return "module_repo"
    if "f-droid.org" in url or "izzysoft.de" in url:
        return "fdroid_app"
    return "github_repo"


def fetch_awesome_android_root_cat(cat_slug: str) -> list:
    url = f"https://raw.githubusercontent.com/awesome-android-root/awesome-android-root/main/docs/apps-and-modules/{cat_slug}.md"
    items = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return items
        subcat = cat_slug.replace("-", " ").title()
        target_cat = AAR_CATEGORY_MAP.get(cat_slug, "⚙️ Root Device-Editing & System Tools")
        for line in r.text.splitlines():
            line_s = line.strip()
            if line_s.startswith("## ") or line_s.startswith("### "):
                subcat = line_s.lstrip("#").strip()
                continue
            m = re.match(r"^-\s+\*\*\[([^\]]+)\]\(([^)]+)\)\*\*\s*-\s*(.+)$", line_s)
            if m:
                raw_name, item_url, raw_desc = m.group(1), m.group(2).strip(), m.group(3)
                if item_url.startswith("/") or item_url.startswith("."):
                    continue
                name = raw_name.replace("⭐", "").strip()
                badges = extract_badges(raw_name + " " + raw_desc)
                if "ROOT" not in badges and not (set(badges) & {"MAGISK", "KSU", "APATCH", "LSPOSED"}):
                    badges.append("ROOT")
                desc = clean_markdown_text(raw_desc)
                # Extract GitHub source link if main link isn't GitHub
                gh_match = re.search(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", line_s)
                repo_url = gh_match.group(0) if gh_match else item_url
                items.append({
                    "id": f"aar_{cat_slug}_{ re.sub(r'[^a-zA-Z0-9]', '_', name.lower()) }",
                    "name": name,
                    "category": target_cat,
                    "subcategory": subcat,
                    "kind": infer_kind_from_item(repo_url, badges, target_cat, desc),
                    "source": "Awesome-Android-Root",
                    "author": repo_url.split("github.com/")[1].split("/")[0] if "github.com/" in repo_url else "Community",
                    "stars": 500 if "★TOP" in badges else 100,
                    "badges": badges,
                    "description": desc,
                    "url": repo_url,
                    "alt_url": item_url if item_url != repo_url else ""
                })
    except Exception:
        pass
    return items


def fetch_awesome_shizuku() -> list:
    url = "https://raw.githubusercontent.com/timschneeb/awesome-shizuku/master/README.md"
    items = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return items
        subcat = "Shizuku Apps"
        for line in r.text.splitlines():
            line_s = line.strip()
            if line_s.startswith("### ") or line_s.startswith("## "):
                h = line_s.lstrip("#").strip()
                if h.lower() in ("table of contents", "languages", "annotations", "license"):
                    continue
                subcat = h
                continue
            m = re.match(r"^\*\s+\[([^\]]+)\]\(([^)]+)\)\s*(?:✨\s*)?-\s*(.+)$", line_s)
            if m:
                name, item_url, raw_desc = m.group(1).strip(), m.group(2).strip(), m.group(3)
                gh_match = re.search(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", line_s)
                repo_url = gh_match.group(0) if gh_match else item_url
                badges = ["SHIZUKU"] + extract_badges(raw_desc)
                if "✨" in line_s:
                    badges.insert(0, "★TOP")
                desc = clean_markdown_text(raw_desc)
                items.append({
                    "id": f"shizuku_{re.sub(r'[^a-zA-Z0-9]', '_', name.lower())}",
                    "name": name,
                    "category": "⚡ Shizuku & Addons (450+ Tools)",
                    "subcategory": subcat,
                    "kind": infer_kind_from_item(repo_url, badges, "⚡ Shizuku & Addons (450+ Tools)", desc),
                    "source": "Awesome-Shizuku",
                    "author": repo_url.split("github.com/")[1].split("/")[0] if "github.com/" in repo_url else "ShizukuDev",
                    "stars": 400 if "★TOP" in badges else 120,
                    "badges": badges[:5],
                    "description": f"[{subcat}] {desc}",
                    "url": repo_url,
                    "alt_url": item_url if item_url != repo_url else ""
                })
    except Exception:
        pass
    return items


def fetch_mmrl_v2_repo(repo_label: str, json_url: str) -> list:
    items = []
    try:
        r = requests.get(json_url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return items
        data = r.json()
        modules = data.get("modules", [])
        for mod in modules:
            mod_id = mod.get("id", "unknown")
            name = mod.get("name") or mod_id
            desc = mod.get("description") or "Systemless Magisk/KernelSU Module"
            author = mod.get("author") or "ModuleDev"
            stars = mod.get("stars", 80)
            versions = mod.get("versions") or []
            zip_url = versions[-1].get("zipUrl", "") if versions else mod.get("zip_url", "")
            ver_str = versions[-1].get("version", mod.get("version", "")) if versions else mod.get("version", "")
            source_url = (mod.get("track") or {}).get("source") or mod.get("support") or zip_url
            if source_url and source_url.endswith(".git"):
                source_url = source_url[:-4]
            badges = ["MODULE", "MAGISK", "KSU"]
            feats = mod.get("features") or {}
            if feats.get("zygisk"):
                badges.append("ZYGISK")
            if feats.get("resetprop") or feats.get("system_prop"):
                badges.append("PROP")
            if feats.get("webui") or feats.get("action"):
                badges.append("WEBUI")
            min_api = mod.get("minApi")
            max_api = mod.get("maxApi")
            if min_api and int(min_api) > 34:
                badges.append(f"API>={min_api}")
            items.append({
                "id": f"mmrl_{mod_id}",
                "name": f"{name} ({ver_str})" if ver_str and ver_str not in name else name,
                "category": "📦 Magisk / KernelSU / APatch Modules",
                "subcategory": f"{repo_label} Modules",
                "kind": "module_zip" if zip_url else "module_repo",
                "source": repo_label,
                "author": author,
                "stars": stars,
                "badges": badges[:5],
                "description": desc,
                "url": source_url or zip_url,
                "zip_url": zip_url,
                "version": ver_str,
                "module_id": mod_id
            })
    except Exception:
        pass
    return items


def fetch_awesome_kernelsu() -> list:
    items = []
    urls = [
        ("Awesome-KernelSU", "👑 Root Handling, Zygisk & Hiding", "KSU", "https://raw.githubusercontent.com/fynks/awesome-kernelsu/main/README.md"),
        ("Awesome-Temp-Root", "👑 Root Handling, Zygisk & Hiding", "TEMP-ROOT", "https://raw.githubusercontent.com/fynks/awesome-temporary-root/main/README.md"),
        ("Best-Shizuku-Apps", "⚡ Shizuku & Addons (450+ Tools)", "SHIZUKU", "https://raw.githubusercontent.com/krishna3163/best_shizuku_apps_for_android_no_root/main/README.md"),
    ]
    for src_name, cat, bdg, url in urls:
        try:
            r = requests.get(url, headers=HEADERS, timeout=8)
            if r.status_code != 200:
                continue
            for line in r.text.splitlines():
                m = re.search(r"[-*]\s+(?:\*\*)?\[([^\]]+)\]\((https?://[^)]+)\)(?:\*\*)?\s*[-–—:]\s*(.+)$", line.strip())
                if m:
                    name, repo_url, desc = m.group(1).strip(), m.group(2).strip(), clean_markdown_text(m.group(3))
                    items.append({
                        "id": f"ext_{re.sub(r'[^a-zA-Z0-9]', '_', name.lower())}",
                        "name": name,
                        "category": cat,
                        "subcategory": src_name,
                        "kind": "github_repo" if "github.com" in repo_url else "fdroid_app",
                        "source": src_name,
                        "author": repo_url.split("github.com/")[1].split("/")[0] if "github.com/" in repo_url else src_name,
                        "stars": 180,
                        "badges": [bdg, "ROOT", "FOSS"],
                        "description": desc,
                        "url": repo_url
                    })
        except Exception:
            pass
    return items


def fetch_github_topic(query: str, target_cat: str, badge: str, per_page: int = 30) -> list:
    url = f"https://api.github.com/search/repositories?q={quote_plus(query)}&sort=stars&order=desc&per_page={per_page}"
    items = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return items
        for repo in r.json().get("items", []):
            name = repo.get("name", "")
            full_name = repo.get("full_name", "")
            desc = repo.get("description") or "GitHub Android Root / System Project"
            stars = repo.get("stargazers_count", 0)
            html_url = repo.get("html_url", "")
            owner = (repo.get("owner") or {}).get("login", "GitHub")
            badges = [badge, f"★{stars}"]
            if repo.get("license"):
                badges.append("FOSS")
            items.append({
                "id": f"gh_{full_name.replace('/', '_')}",
                "name": name,
                "category": target_cat,
                "subcategory": f"GitHub Top ({badge})",
                "kind": "module_repo" if badge in ("MAGISK", "KSU") else "github_repo",
                "source": "GitHub Live",
                "author": owner,
                "stars": stars,
                "badges": badges,
                "description": desc,
                "url": html_url
            })
    except Exception:
        pass
    return items


def fetch_fdroid_query(query: str, target_cat: str, badge: str) -> list:
    url = f"https://search.f-droid.org/api/search_apps?q={quote_plus(query)}"
    items = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        if r.status_code != 200:
            return items
        for app in r.json().get("apps", []):
            name = app.get("name", "")
            summary = app.get("summary", "")
            pkg_url = app.get("url", "")
            pkg_id = pkg_url.rstrip("/").split("/")[-1] if pkg_url else name
            items.append({
                "id": f"fdroid_{pkg_id}",
                "name": name,
                "category": target_cat,
                "subcategory": f"F-Droid ({query.title()})",
                "kind": "fdroid_app",
                "source": "F-Droid Search",
                "author": pkg_id.split(".")[1] if "." in pkg_id else "F-Droid",
                "stars": 150,
                "badges": ["F-DROID", badge, "FOSS"],
                "description": f"{summary} ({pkg_id})",
                "url": pkg_url,
                "package_id": pkg_id
            })
    except Exception:
        pass
    return items


def crawl_all(progress_cb=None) -> list:
    """
    Executes a parallel multi-source crawl across all 8 sources, merges and deduplicates
    entries, and saves them to the local cache.
    """
    tasks = []
    with ThreadPoolExecutor(max_workers=12) as ex:
        # 1. All 16 Awesome-Android-Root categories
        for slug in AAR_CATEGORY_MAP:
            tasks.append((f"Awesome-Android-Root ({slug})", ex.submit(fetch_awesome_android_root_cat, slug)))

        # 2. Awesome-Shizuku (430+ items)
        tasks.append(("Awesome-Shizuku", ex.submit(fetch_awesome_shizuku)))

        # 3. MMRL & Magisk-Modules-Alt-Repo v2 JSONs
        tasks.append(("Magisk-Alt-Repo v2", ex.submit(
            fetch_mmrl_v2_repo,
            "Magisk-Alt-Repo",
            "https://raw.githubusercontent.com/Magisk-Modules-Alt-Repo/json-v2/main/json/modules.json"
        )))
        tasks.append(("MMRL ZG-R Gems", ex.submit(
            fetch_mmrl_v2_repo,
            "ZG-R Gems",
            "https://raw.githubusercontent.com/ZGUATION-PROJECTS/ZG-R/master/json/modules.json"
        )))
        tasks.append(("MMRL Community Repo", ex.submit(
            fetch_mmrl_v2_repo,
            "MMRL-Community",
            "https://raw.githubusercontent.com/uonou/mmrl-repo/main/json/modules.json"
        )))

        # 4. Awesome-KernelSU
        tasks.append(("Awesome-KernelSU", ex.submit(fetch_awesome_kernelsu)))

        # 5. GitHub Live Topic Crawlers
        tasks.append(("GitHub topic:magisk-module", ex.submit(
            fetch_github_topic, "topic:magisk-module", "📦 Magisk / KernelSU / APatch Modules", "MAGISK", 35
        )))
        tasks.append(("GitHub topic:kernelsu-module", ex.submit(
            fetch_github_topic, "topic:kernelsu-module", "📦 Magisk / KernelSU / APatch Modules", "KSU", 25
        )))
        tasks.append(("GitHub topic:shizuku", ex.submit(
            fetch_github_topic, "topic:shizuku", "⚡ Shizuku & Addons (450+ Tools)", "SHIZUKU", 35
        )))
        tasks.append(("GitHub topic:lsposed-module", ex.submit(
            fetch_github_topic, "topic:lsposed-module", "🧩 LSPosed / Xposed & App Mods", "LSPOSED", 25
        )))

        # 6. F-Droid Live Search Crawlers
        tasks.append(("F-Droid: shizuku", ex.submit(
            fetch_fdroid_query, "shizuku", "⚡ Shizuku & Addons (450+ Tools)", "SHIZUKU"
        )))
        tasks.append(("F-Droid: root", ex.submit(
            fetch_fdroid_query, "root", "⚙️ Root Device-Editing & System Tools", "ROOT"
        )))
        tasks.append(("F-Droid: kernel", ex.submit(
            fetch_fdroid_query, "kernel", "🔥 Performance, Kernel & Battery", "KERNEL"
        )))
        tasks.append(("F-Droid: debloat", ex.submit(
            fetch_fdroid_query, "debloat", "🧹 Debloating, Backup & File Managers", "DEBLOAT"
        )))

        raw_items = list(BUILTIN_SCRIPTS) + list(SEED_TOOLS)
        total_tasks = len(tasks)
        completed = 0
        for label, fut in tasks:
            try:
                res = fut.result(timeout=14)
                raw_items.extend(res)
            except Exception:
                pass
            completed += 1
            if progress_cb:
                progress_cb(completed, total_tasks, label, len(raw_items))

    # Deduplicate by normalized URL or ID, preserving direct zip_url and merging badges
    merged = {}
    for item in raw_items:
        key = normalize_url_key(item.get("url", "")) or item["id"]
        if key not in merged:
            merged[key] = dict(item)
        else:
            existing = merged[key]
            # Merge badges
            combined_badges = list(dict.fromkeys(existing.get("badges", []) + item.get("badges", [])))
            existing["badges"] = combined_badges[:6]
            # Keep direct zip_url if present
            if item.get("zip_url") and not existing.get("zip_url"):
                existing["zip_url"] = item["zip_url"]
                existing["kind"] = "module_zip"
            if item.get("stars", 0) > existing.get("stars", 0):
                existing["stars"] = item["stars"]
            if item.get("source") and item["source"] not in existing.get("source", ""):
                existing["source"] = f"{existing['source']} + {item['source']}"

    final_list = list(merged.values())
    # Sort: Builtin scripts first, then by stars descending, then alphabetical
    final_list.sort(key=lambda x: (
        0 if x.get("kind") == "root_script" else 1,
        -int(x.get("stars", 0)),
        x.get("name", "").lower()
    ))

    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": int(time.time()),
            "count": len(final_list),
            "items": final_list
        }, f, ensure_ascii=False, indent=2)

    return final_list


def load_or_crawl(force_refresh: bool = False, progress_cb=None) -> list:
    if not force_refresh and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            items = data.get("items", [])
            if len(items) > 100:
                return items
        except Exception:
            pass
    return crawl_all(progress_cb=progress_cb)


def live_query_crawl(query: str) -> list:
    """
    Crawls GitHub and F-Droid live for a custom user search query and returns matching tools.
    """
    results = []
    with ThreadPoolExecutor(max_workers=3) as ex:
        f1 = ex.submit(fetch_github_topic, f"{query} android", "⚙️ Root Device-Editing & System Tools", "GITHUB", 20)
        f2 = ex.submit(fetch_github_topic, f"{query} magisk OR shizuku OR root", "👑 Root Handling, Zygisk & Hiding", "ROOT", 20)
        f3 = ex.submit(fetch_fdroid_query, query, "⚙️ Root Device-Editing & System Tools", "F-DROID")
        for fut in (f1, f2, f3):
            try:
                results.extend(fut.result(timeout=10))
            except Exception:
                pass
    dedup = {}
    for it in results:
        k = normalize_url_key(it.get("url", "")) or it["id"]
        if k not in dedup:
            dedup[k] = it
    return list(dedup.values())


if __name__ == "__main__":
    def _cb(done, total, label, count):
        print(f"[{done}/{total}] Crawled {label} -> {count} raw items")
    items = crawl_all(progress_cb=_cb)
    print(f"Done! Total unique tools indexed: {len(items)}")
