#!/usr/bin/env python3
"""
学习搜索 (Tech Learning Scan) - Parallel list-page scanner
Usage: python daily_scan_parallel.py YYYY-MM-DD [YYYY-MM-DD ...] [--timeout=25]

Loads the company list from config/tech_company_list.json (one level above the
project root). Fill that JSON with the research/blog pages you want to monitor.
"""
import asyncio
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

BASE = Path(__file__).parent.parent
CONFIG_PATH = BASE.parent / "config" / "tech_company_list.json"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    companies = data.get("companies", [])
    always = data.get("always_check_urls", [])
    if not companies:
        print("WARNING: config/tech_company_list.json is empty; nothing to scan.")
    return companies, always


# These are populated from config at import time.
_COMPANIES, ALWAYS_CHECK_URLS = load_config()
COMPANIES = {item["name"]: item for item in _COMPANIES}

CONCURRENCY = 6
PAGE_TIMEOUT = 20000
SETTLE_SEC = 3

DATE_RE_1 = re.compile(
    r'((?:January|February|March|April|May|June|July|August|September|October|November|December'
    r'|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+\d{1,2},?\s+2026)', re.I)
DATE_RE_2 = re.compile(
    r'(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December'
    r'|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+2026)', re.I)
DATE_RE_ISO = re.compile(r'(2026-\d{2}-\d{2})')

MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], 1)}
MONTHS.update({"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
               "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12})
FULL_MONTH = {i: m for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], 1)}


def normalize_date(text):
    if not text:
        return []
    found = DATE_RE_1.findall(str(text)) + DATE_RE_2.findall(str(text)) + DATE_RE_ISO.findall(str(text))
    return list(dict.fromkeys(found))[:10]


def standardize_date(date_str):
    s = date_str.strip().replace(",", "")
    m = re.match(r'^(2026)-(\d{2})-(\d{2})$', s)
    if m:
        return f"{FULL_MONTH[int(m.group(2))]} {int(m.group(3))}"
    m = re.match(r'^([A-Za-z]+)\.?\s+(\d{1,2})\s+2026$', s)
    if m and m.group(1).lower() in MONTHS:
        return f"{FULL_MONTH[MONTHS[m.group(1).lower()]]} {int(m.group(2))}"
    m = re.match(r'^(\d{1,2})\s+([A-Za-z]+)\.?\s+2026$', s)
    if m and m.group(2).lower() in MONTHS:
        return f"{FULL_MONTH[MONTHS[m.group(2).lower()]]} {int(m.group(1))}"
    return date_str


def check_scan_date(dates, scan_date):
    scan_dt = datetime.strptime(scan_date, "%Y-%m-%d")
    scan_std = scan_dt.strftime("%B %d").replace(" 0", " ")
    standardized = {standardize_date(d) for d in dates}
    return scan_std in standardized


def track_for(url, info):
    for frag, tr in info.get("track_hint", {}).items():
        if frag in url:
            return tr
    return "A"


async def scan_url(context, sem, name, url, info, counter):
    result = {
        "name": name, "url": url, "track": track_for(url, info),
        "status": "pending", "dates_found": [], "has_scan_date": False, "error": None,
    }
    async with sem:
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
            await asyncio.sleep(SETTLE_SEC)
            for _ in range(3):
                await page.evaluate("() => window.scrollBy(0, 1400)")
                await asyncio.sleep(1.5)
            text = await page.evaluate("() => document.body.innerText")
            html = await page.content()
            result["dates_found"] = list(dict.fromkeys(normalize_date(text) + normalize_date(html)))[:10]
            result["status"] = "ok"
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)[:80]
        finally:
            await page.close()
        counter["done"] += 1
        mark = "ERR" if result["status"] == "error" else "ok"
        print(f"[{counter['done']}/{counter['total']}] {name} ({url}): {mark} | {result['dates_found'][:3]}", flush=True)
    return result


async def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    timeout_override = next((int(a.split("=")[1]) for a in sys.argv[1:] if a.startswith("--timeout=")), None)
    global PAGE_TIMEOUT
    if timeout_override:
        PAGE_TIMEOUT = timeout_override * 1000
    scan_dates = args or [datetime.now().strftime("%Y-%m-%d")]
    for d in scan_dates:
        datetime.strptime(d, "%Y-%m-%d")

    if not COMPANIES:
        print("ERROR: No companies configured.")
        sys.exit(1)

    tasks_spec = [(name, url, info) for name, info in COMPANIES.items() for url in info["urls"]]
    total = len(tasks_spec)
    print("=== Tech Learning Scan ===", flush=True)
    print(f"Scan dates: {', '.join(scan_dates)} | Companies: {len(COMPANIES)} | URLs: {total} | Concurrency: {CONCURRENCY}", flush=True)
    t0 = datetime.now()

    async with async_playwright() as p:
        _proxy = os.environ.get("https_proxy") or os.environ.get("http_proxy")
        browser = await p.chromium.launch(headless=True, proxy={"server": _proxy} if _proxy else None)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
        await context.route(
            re.compile(r'\.(png|jpe?g|gif|svg|webp|ico|woff2?|ttf|otf|eot|mp4|webm|css)(\?|$)', re.I),
            lambda route: route.abort())
        sem = asyncio.Semaphore(CONCURRENCY)
        counter = {"done": 0, "total": total}
        results = await asyncio.gather(*(scan_url(context, sem, name, url, info, counter)
                                         for name, url, info in tasks_spec))
        await browser.close()

    for scan_date in scan_dates:
        per_date = []
        for r in results:
            rec = dict(r)
            if r["status"] == "error":
                rec["status"] = "error"
                rec["has_scan_date"] = False
            else:
                rec["has_scan_date"] = check_scan_date(r["dates_found"], scan_date)
                rec["status"] = "found" if rec["has_scan_date"] else "no_match"
            per_date.append(rec)

        output_file = f"scan_results_{scan_date}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(per_date, f, ensure_ascii=False, indent=2)

        found = [r for r in per_date if r["status"] == "found"]
        errors = [r for r in per_date if r["status"] == "error"]
        print(f"\n--- {scan_date}: found {len(found)}, no_match {len(per_date) - len(found) - len(errors)}, errors {len(errors)} -> {output_file}", flush=True)
        for r in found:
            print(f"  FOUND {r['name']} [{r['track']}] {r['url']} | {r['dates_found'][:4]}", flush=True)
        for r in errors:
            print(f"  ERR   {r['name']}: {r['url']} | {r['error']}", flush=True)

    elapsed = (datetime.now() - t0).total_seconds()
    print(f"\nTotal elapsed: {elapsed:.0f}s for {total} URLs x {len(scan_dates)} date(s)", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
