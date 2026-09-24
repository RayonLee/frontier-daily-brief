#!/usr/bin/env python3
"""
Daily Think-Tank Scan - Full Coverage Playwright Batch Scanner
Usage: python daily_scan.py YYYY-MM-DD

Loads the institution list from config/think_tank_list.json (one level above
the project root by default). Fill that JSON with the list pages you want to
monitor.
"""

import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

BASE = Path(__file__).parent.parent
CONFIG_PATH = BASE.parent / "config" / "think_tank_list.json"


def load_institutions():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    institutions = data.get("institutions", [])
    if not institutions:
        print("WARNING: config/think_tank_list.json is empty; nothing to scan.")
    return {item["name"]: item for item in institutions}


def normalize_date(text):
    if not text:
        return []
    m1 = re.findall(
        r'((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+2026)',
        str(text)
    )
    m2 = re.findall(
        r'(\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+2026)',
        str(text)
    )
    return list(dict.fromkeys(m1 + m2))[:10]


def standardize_date(date_str):
    date_str = date_str.strip()
    for fmt in ("%B %d, %Y", "%B %d %Y", "%d %B %Y", "%d %B, %Y"):
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%B %d").replace(" 0", " ")
        except ValueError:
            continue
    return date_str


def check_scan_date(dates, scan_date):
    scan_dt = datetime.strptime(scan_date, "%Y-%m-%d")
    scan_std = scan_dt.strftime("%B %d").replace(" 0", " ")
    standardized = {standardize_date(d) for d in dates}
    return scan_std in standardized


async def scan_url(browser, name, url, info, scan_date):
    result = {
        "name": name,
        "url": url,
        "tier": info.get("tier", 1),
        "priority": info.get("priority", "★★★"),
        "status": "pending",
        "dates_found": [],
        "has_scan_date": False,
        "error": None
    }

    page = await browser.new_page()
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=12000)
        await asyncio.sleep(1)
        text = await page.evaluate("() => document.body.innerText")
        dates = normalize_date(text)
        result["dates_found"] = dates
        result["has_scan_date"] = check_scan_date(dates, scan_date)
        result["status"] = "found" if result["has_scan_date"] else "no_match"
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)[:80]
    finally:
        await page.close()

    return result


async def scan_institution(browser, name, info, scan_date):
    results = []
    for url in info["urls"]:
        r = await scan_url(browser, name, url, info, scan_date)
        results.append(r)
        await asyncio.sleep(0.5)
    return results


async def main():
    if len(sys.argv) < 2:
        scan_date = datetime.now().strftime("%Y-%m-%d")
    else:
        scan_date = sys.argv[1]

    INSTITUTIONS = load_institutions()
    total_urls = sum(len(info["urls"]) for info in INSTITUTIONS.values())

    print(f"=== Daily Think-Tank Scan - {scan_date} ===")
    print(f"Institutions: {len(INSTITUTIONS)}")
    print(f"URLs to scan: {total_urls}")
    print(f"Method: Playwright primary (batch scanning)")
    print()

    all_results = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        for name, info in INSTITUTIONS.items():
            results = await scan_institution(browser, name, info, scan_date)
            all_results.extend(results)

            any_found = any(r["status"] == "found" for r in results)
            all_no_match = all(r["status"] == "no_match" for r in results)

            if any_found:
                status_icon = "✓"
                status_text = "found"
            elif all_no_match:
                status_icon = "✗"
                status_text = "no_match"
            else:
                status_icon = "⚠"
                status_text = "partial_error"

            dates_sample = []
            for r in results:
                dates_sample.extend(r["dates_found"][:3])
            dates_sample = list(dict.fromkeys(dates_sample))[:3]

            print(f"  {status_icon} {name}: {status_text} | Dates: {dates_sample}")

        await browser.close()

    print("\n=== SUMMARY ===")
    found = [r for r in all_results if r["status"] == "found"]
    no_match = [r for r in all_results if r["status"] == "no_match"]
    errors = [r for r in all_results if r["status"] == "error"]

    print(f"Found articles on {scan_date}: {len(found)} URL(s)")
    print(f"No match: {len(no_match)}")
    print(f"Errors: {len(errors)}")

    if errors:
        print("\nAccess failures:")
        for r in errors:
            print(f"  {r['name']} ({r['url']}): {r['error']}")

    output_file = f"scan_results_{scan_date}.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to {output_file}")


if __name__ == "__main__":
    asyncio.run(main())
