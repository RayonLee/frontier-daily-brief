#!/usr/bin/env python3
"""
Streamlined daily-report builder for tech-learning-scan.
Read one saved txt -> register one CSV row -> append one daily-report entry.

Usage:
    python scripts/streamline_save_and_report.py YYYY-MM-DD

Outputs:
    - assets/paper-registry.csv  (Track A)
    - assets/learning-log.csv    (Track B)
    - scans/daily-learn-<date>.md
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
PAPER_CSV = BASE / "assets" / "paper-registry.csv"
LEARNING_CSV = BASE / "assets" / "learning-log.csv"
DAILY_MD = BASE / "scans" / f"daily-learn-{SCAN_DATE}.md"
SAVED_JSON = BASE / "scans" / f"_saved_{SCAN_DATE}.json"

TOPIC_RULES = [
    ("大模型与AI研究", re.compile(r'\b(llm|large language|foundation model|transformer|diffusion|alignment|reasoning model|multimodal|agent|benchmark|pre-?train|fine-?tun|distill|RLHF|inference)\b', re.I)),
    ("芯片与硬件", re.compile(r'\b(gpu|chip|semiconductor|cuda|tensor|tpu|nvlink|hbm|wafer|asic|robotics|embodied)\b', re.I)),
    ("工程与开发者", re.compile(r'\b(sdk|api|framework|library|developer|engineering|kernel|compiler|infrastructure|deployment|open source|github)\b', re.I)),
    ("产业与应用", re.compile(r'\b(enterprise|industry|customer|productivity|workflow|health|finance|retail|manufactur|supply chain|revenue|market)\b', re.I)),
    ("政策与治理", re.compile(r'\b(policy|regulat|governance|safety|compliance|export control|antitrust|privacy|copyright)\b', re.I)),
]

def tag_topic(text):
    best, best_n = "产业与应用", 0
    for name, rx in TOPIC_RULES:
        n = len(rx.findall(text[:8000]))
        if n > best_n:
            best, best_n = name, n
    return best

def clean_body(text):
    parts = text.split("\n\n", 1)
    body = parts[-1] if len(parts) > 1 else text
    lines = [ln.strip() for ln in body.splitlines() if len(ln.strip()) > 25]
    return "\n".join(lines)

def first_sentence(text, max_len=240):
    text = text.replace("\n", " ").strip()
    m = re.search(r"^(.{40,%d}[.!?])" % max_len, text)
    if m:
        return m.group(1).strip()
    return text[:max_len].strip() + "..." if len(text) > max_len else text.strip()

def priority_for(track, company, wc):
    if track == "A":
        return "High"
    if wc >= 1500:
        return "Medium"
    return "Low"

def init_files():
    if DAILY_MD.exists():
        DAILY_MD.unlink()
    with open(DAILY_MD, "w", encoding="utf-8") as f:
        f.write(f"# Tech Learning Scan - {SCAN_DATE}\n\n")
        f.write("## Scan Overview\n")
        f.write(f"- **Scan Date:** {SCAN_DATE}\n")
        f.write("- **Method:** Streamlined one-by-one processing\n\n")
        f.write("## Track A - Official Papers / Reports\n\n")
        f.write("| # | Title | Company | Pub Date | Topic | Words | PDF | Status |\n")
        f.write("|---|-------|---------|----------|-------|-------|-----|--------|\n")
        f.write("<!-- TRACK_A_ROWS -->\n\n")
        f.write("## Track B - Blog / News\n\n")

def main():
    if not SAVED_JSON.exists():
        print(f"Saved JSON not found: {SAVED_JSON}")
        return

    saved = json.load(open(SAVED_JSON, encoding="utf-8"))
    print(f"Streamlined processing: {len(saved)} saved articles")
    init_files()

    track_a_count = 0
    track_b_count = 0
    track_a_rows = []

    for idx, x in enumerate(saved, 1):
        title = x["title"]
        company = x["company"]
        track = x.get("track", "B")
        url = x["url"]
        wc = x.get("words", 0)
        topic = x.get("topic") or tag_topic(open(x["file"], encoding="utf-8").read())
        author = x.get("author", "")
        pdf_url = x.get("pdf_url", "")
        priority = priority_for(track, company, wc)

        raw_text = open(x["file"], encoding="utf-8").read()
        body = clean_body(raw_text)
        key_points = first_sentence(body)

        if track == "A":
            with open(PAPER_CSV, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([
                    title, company, SCAN_DATE, topic, SCAN_DATE, url, pdf_url, "Pending", "paper_report", ""
                ])
            track_a_rows.append(
                f"| {track_a_count+1} | [{title}]({url}) | {company} | {SCAN_DATE} | {topic} | {wc} | {pdf_url or 'N/A'} | Pending |"
            )
            track_a_count += 1
        else:
            with open(LEARNING_CSV, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([
                    title, company, SCAN_DATE, topic, SCAN_DATE, url, author, wc, key_points, priority
                ])
            with open(DAILY_MD, "a", encoding="utf-8") as f:
                f.write(f"### {track_b_count+1}. [{title}]({url})（{company}，{topic}，{priority}）\n")
                f.write(f"- **Words**: {wc}\n")
                f.write(f"- **Key points**: {key_points}\n")
                f.write(f"- **Link**: {url}\n\n")
            track_b_count += 1

        print(f"[{idx}/{len(saved)}] {track} | {company} | {priority} | {title[:50]}")

    if track_a_rows:
        md_text = DAILY_MD.read_text(encoding="utf-8")
        md_text = md_text.replace("<!-- TRACK_A_ROWS -->\n", "\n".join(track_a_rows) + "\n")
        DAILY_MD.write_text(md_text, encoding="utf-8")

    with open(DAILY_MD, "a", encoding="utf-8") as f:
        f.write("\n## Notes & Gap-Filling\n")
        f.write(f"- Processed {len(saved)} saved articles: Track A {track_a_count}, Track B {track_b_count}.\n")
        f.write("- One-sentence summaries extracted from first substantive paragraph.\n")
        f.write("\n## Self-Optimization Log\n")
        f.write("- Used streamlined one-by-one mode to avoid loading all articles into context at once.\n")

    print(f"\nDone: Track A {track_a_count}, Track B {track_b_count}")
    print(f"Daily report: {DAILY_MD}")

if __name__ == "__main__":
    main()
