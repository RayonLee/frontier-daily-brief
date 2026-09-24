#!/usr/bin/env python3
"""
Streamlined daily-report builder for daily-think-tank-scan.
Read one saved txt -> register one CSV row -> append one daily-report entry.
This avoids loading all articles into LLM context at once.

Usage:
    python scripts/streamline_save_and_report.py YYYY-MM-DD

Outputs:
    - assets/report-registry.csv  (Track A, >=8000 words)
    - assets/commentary-log.csv   (Track B, <8000 words, china>=1)
    - scans/daily-scan-<date>.md

Note: This script uses rule-based one-sentence extraction. For higher-quality
summaries, pass the extracted sentence to the LLM for polishing one article at a time.
"""
import csv
import json
import os
import re
import sys
from pathlib import Path

SCAN_DATE = sys.argv[1] if len(sys.argv) > 1 else "2026-09-16"
BASE = Path(__file__).parent.parent
RAWDIR = BASE / "raw-reports" / SCAN_DATE
REPORT_CSV = BASE / "assets" / "report-registry.csv"
COMMENTARY_CSV = BASE / "assets" / "commentary-log.csv"
DAILY_MD = BASE / "scans" / f"daily-scan-{SCAN_DATE}.md"
REPORT_JSON = BASE / "scans" / f"deep_check_report_{SCAN_DATE}.json"

# Domain-specific content selectors are applied in the save script (Playwright).
# Here we just clean the already-saved txt: drop header and very short lines.

def clean_body(text):
    # Split on the '---' header separator
    parts = text.split("---\n", 1)
    body = parts[-1] if len(parts) > 1 else text
    # Drop lines that look like page chrome / menus / cookie notices
    lines = []
    for ln in body.splitlines():
        s = ln.strip()
        if len(s) < 30:
            continue
        if any(k in s.lower() for k in [
            "accessibility tools", "choose a language", "translate the page",
            "sign up for", "newsletter", "i consent", "cookie", "privacy policy",
            "footer", "media inquiries", "all rights reserved"
        ]):
            continue
        lines.append(s)
    return "\n".join(lines)

def first_sentence(text, max_len=240):
    text = text.replace("\n", " ").strip()
    m = re.search(r"^(.{40,%d}[.!?])" % max_len, text)
    if m:
        return m.group(1).strip()
    return text[:max_len].strip() + "..." if len(text) > max_len else text.strip()

def priority_for(x):
    wc = x.get("word_count", 0)
    cc = x.get("china_mentions", 0)
    if wc >= 8000:
        return "High"
    if cc >= 20 or wc >= 4000:
        return "High"
    if cc >= 5 or wc >= 1500:
        return "Medium"
    return "Low"

def classify(x):
    wc = x.get("word_count", 0)
    return "A" if wc >= 8000 else "B"

def find_raw_file(title):
    safe = re.sub(r"[/?<>\\:*\"|]", "", title)
    safe = re.sub(r"\s+", "_", safe.strip())[:90]
    candidates = list(RAWDIR.glob(f"{safe}*.txt"))
    return candidates[0] if candidates else None

def init_files():
    if DAILY_MD.exists():
        DAILY_MD.unlink()
    with open(DAILY_MD, "w", encoding="utf-8") as f:
        f.write(f"# Daily Think-Tank Scan - {SCAN_DATE}\n\n")
        f.write("## Scan Overview\n")
        f.write(f"- **Scan Date:** {SCAN_DATE}\n")
        f.write(f"- **Scan Window:** {SCAN_DATE} (publication date)\n")
        f.write("- **Method:** Streamlined one-by-one processing\n\n")
        f.write("## Track A - Research Reports (>= 8,000 words)\n\n")
        f.write("| # | Title | Institution | Pub Date | Topic | Words | PDF | Status |\n")
        f.write("|---|-------|-------------|----------|-------|-------|-----|--------|\n")
        f.write("<!-- TRACK_A_ROWS -->\n\n")
        f.write("## Track B - Expert Commentary (< 4,000 words)\n\n")

def main():
    if not REPORT_JSON.exists():
        print(f"Report not found: {REPORT_JSON}")
        return

    report = json.load(open(REPORT_JSON, encoding="utf-8"))
    matched = [x for x in report if x.get("matches_scan_date")]
    # Keep items that mention China or are explicitly marked as policy-relevant.
    matched = [x for x in matched if (
        (x.get("china_mentions") or 0) >= 1 or
        (x.get("policy_mentions") or 0) >= 1
    )]

    print(f"Streamlined processing: {len(matched)} candidates")
    init_files()

    track_a_count = 0
    track_b_count = 0
    track_a_rows = []

    for idx, x in enumerate(matched, 1):
        title = x["title"]
        inst = x["institution"]
        url = x["url"]
        wc = x.get("word_count", 0)
        cc = x.get("china_mentions", 0)
        pdf_url = x.get("pdf_url", "")
        track = classify(x)
        priority = priority_for(x)
        topic = "China/Strategy"

        raw_file = find_raw_file(title)
        if not raw_file:
            print(f"[{idx}] raw file missing: {title[:50]}")
            continue

        body = clean_body(raw_file.read_text(encoding="utf-8"))
        key_points = first_sentence(body)

        if track == "A":
            with open(REPORT_CSV, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([
                    title, inst, SCAN_DATE, topic, SCAN_DATE, url, pdf_url, "Pending", "research_report", ""
                ])
            track_a_rows.append(
                f"| {track_a_count+1} | [{title}]({url}) | {inst} | {SCAN_DATE} | {topic} | {wc} | {pdf_url or 'N/A'} | Pending |"
            )
            track_a_count += 1
        else:
            with open(COMMENTARY_CSV, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([
                    title, inst, SCAN_DATE, topic, SCAN_DATE, url, "", wc, key_points, priority
                ])
            with open(DAILY_MD, "a", encoding="utf-8") as f:
                f.write(f"### {track_b_count+1}. [{title}]({url})（{inst}，{priority}）\n")
                f.write(f"- **Words**: {wc} | **China mentions**: {cc}\n")
                f.write(f"- **Key points**: {key_points}\n")
                f.write(f"- **Link**: {url}\n\n")
            track_b_count += 1

        print(f"[{idx}/{len(matched)}] {track} | {inst} | {priority} | {title[:50]}")

    # Insert Track A rows into the placeholder position
    if track_a_rows:
        md_text = DAILY_MD.read_text(encoding="utf-8")
        md_text = md_text.replace("<!-- TRACK_A_ROWS -->\n", "\n".join(track_a_rows) + "\n")
        DAILY_MD.write_text(md_text, encoding="utf-8")

    # Append closing sections
    with open(DAILY_MD, "a", encoding="utf-8") as f:
        f.write("\n## Notes & Gap-Filling\n")
        f.write(f"- Processed {len(matched)} candidates: Track A {track_a_count}, Track B {track_b_count}.\n")
        f.write("- One-sentence summaries extracted from first substantive paragraph.\n")
        f.write("- Official/government pages may still contain site chrome; consider domain-specific body selectors for cleaner summaries.\n")
        f.write("\n## Self-Optimization Log\n")
        f.write("- Used streamlined one-by-one mode to avoid loading all articles into context at once.\n")

    print(f"\nDone: Track A {track_a_count}, Track B {track_b_count}")
    print(f"Daily report: {DAILY_MD}")

if __name__ == "__main__":
    main()
