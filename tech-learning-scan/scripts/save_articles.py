#!/usr/bin/env python3
"""
Save matched articles' raw text for tech-learning-scan.
Reads scans/deep_check_report_<date>.json, saves every matched article to
raw-reports/<date>/<title>_<date>.txt, prints a summary for CSV registration.
Usage: python save_articles.py YYYY-MM-DD
"""
import asyncio
import json
import os
import re
import sys
from playwright.async_api import async_playwright

BODY_JS = """() => {
  const meta = (sel) => { const e = document.querySelector(sel); return e ? e.getAttribute('content') : null; };
  const author = meta('meta[name="author"]') || meta('meta[property="article:author"]') || '';
  const titleMeta = meta('meta[property="og:title"]') || document.title || '';
  let text = '';
  document.querySelectorAll('p, h1, h2, h3, li').forEach(p => { if (p.innerText.trim().length > 10) text += p.innerText.trim() + '\\n'; });
  return {author: author, title: titleMeta, text: text};
}"""

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


def sanitize(t):
    t = re.sub(r'[/?<>\:*|"\']', '', t)
    return re.sub(r'\s+', '_', t.strip())[:90]


async def main():
    scan_date = sys.argv[1]
    report = json.load(open(f"scans/deep_check_report_{scan_date}.json", encoding="utf-8"))
    matched = [r for r in report if r["matches_scan_date"]]
    print(f"=== Save articles {scan_date}: {len(matched)} matched ===", flush=True)
    outdir = f"raw-reports/{scan_date}"
    os.makedirs(outdir, exist_ok=True)

    saved = []
    async with async_playwright() as p:
        _proxy = os.environ.get("https_proxy") or os.environ.get("http_proxy")
        browser = await p.chromium.launch(headless=True, proxy={"server": _proxy} if _proxy else None)
        ctx = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
        for r in matched:
            page = await ctx.new_page()
            try:
                await page.goto(r["url"], wait_until="domcontentloaded", timeout=25000)
                await asyncio.sleep(1.5)
                d = await page.evaluate(BODY_JS)
                wc = len(d["text"].split())
                if wc < 100:
                    print(f"  SKIP thin page ({wc}w) {r['url'][-50:]}", flush=True)
                    continue
                # Strip site/company suffix from page title; keep only the part before the first separator.
                title = re.split(r'\s*[|–-]\s*', d["title"], 1)[0].strip() or r["title"][:90]
                topic = tag_topic(d["text"])
                fname = f"{outdir}/{sanitize(title)}_{scan_date}.txt"
                with open(fname, "w", encoding="utf-8") as f:
                    f.write(f"Title: {title}\nCompany: {r['company']}\nTrack: {r['track']}\nURL: {r['url']}\nPub date: {scan_date}\nAuthor: {d['author']}\nTopic: {topic}\n\n")
                    f.write(d["text"])
                saved.append({"company": r["company"], "track": r["track"], "title": title,
                              "url": r["url"], "words": wc, "topic": topic,
                              "author": d["author"], "pdf_url": r.get("pdf_url"), "file": fname})
                print(f"  saved {wc}w [{topic}] {title[:60]}", flush=True)
            except Exception as e:
                print(f"  ERR {r['url'][-50:]}: {str(e)[:60]}", flush=True)
            finally:
                await page.close()
        await browser.close()

    with open(f"scans/_saved_{scan_date}.json", "w", encoding="utf-8") as f:
        json.dump(saved, f, ensure_ascii=False, indent=2)
    print(f"\nSaved {len(saved)} -> scans/_saved_{scan_date}.json", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
