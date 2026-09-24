#!/usr/bin/env python3
"""Save matched think-tank articles' raw text.
Reads scans/deep_check_report_<date>.json, saves every matches_scan_date article to
raw-reports/<date>/<title>_<pub_date>.txt, writes scans/_saved_<date>.json.
Usage: python save_articles.py YYYY-MM-DD
"""
import asyncio
import json
import os
import re
import sys
from playwright.async_api import async_playwright

BODY_JS = r"""() => {
  const meta = (sel) => { const e = document.querySelector(sel); return e ? e.getAttribute('content') : null; };
  const author = meta('meta[name="author"]') || meta('meta[property="article:author"]') || '';
  const titleMeta = meta('meta[property="og:title"]') || document.title || '';
  let text = '';
  document.querySelectorAll('p, h1, h2, h3, li').forEach(p => { if (p.innerText.trim().length > 10) text += p.innerText.trim() + '\n'; });
  return {author: author, title: titleMeta, text: text};
}"""

TOPIC_RULES = [
    ("China/Strategy", re.compile(r'\b(China|Chinese|Beijing|PRC|Xi\s+Jinping|Taiwan|Indo-Pacific|deterrence)\b', re.I)),
    ("Trade/Tech", re.compile(r'\b(trade|tariff|export control|semiconductor|chip|AI|technology|WTO|supply chain)\b', re.I)),
    ("Security/Defense", re.compile(r'\b(defense|military|NATO|Ukraine|Russia|Iran|North Korea|terrorism|nonproliferation)\b', re.I)),
    ("Economy/Energy", re.compile(r'\b(economy|energy|climate|critical minerals|inflation|debt|growth)\b', re.I)),
    ("Governance/Rights", re.compile(r'\b(democracy|human rights|governance|election|disinformation|cyber)\b', re.I)),
]


def tag_topic(text):
    best, best_n = "General", 0
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
        await ctx.route(
            re.compile(r'\.(png|jpe?g|gif|svg|webp|ico|woff2?|ttf|otf|eot|mp4|webm)(\?|$)', re.I),
            lambda route: route.abort())
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
                # Strip site/institution suffix from page title; keep only the part before the first separator.
                title = re.split(r'\s*[|–-]\s*', d["title"], 1)[0].strip() or r["title"][:90]
                pub_date = r.get("pub_date") or scan_date
                topic = tag_topic(d["text"])
                fname = f"{outdir}/{sanitize(title)}_{pub_date}.txt"
                with open(fname, "w", encoding="utf-8") as f:
                    f.write(f"Title: {title}\nInstitution: {r['institution']}\nURL: {r['url']}\nPub date: {pub_date}\nAuthor: {d['author']}\nTopic: {topic}\nWords: {wc}\nChina mentions: {r.get('china_mentions', 0)}\n\n")
                    f.write(d["text"])
                saved.append({"institution": r["institution"], "title": title,
                              "url": r["url"], "words": wc, "topic": topic,
                              "author": d["author"], "pub_date": pub_date,
                              "china_mentions": r.get("china_mentions", 0),
                              "pdf_url": r.get("pdf_url"), "file": fname})
                print(f"  saved {wc}w china={r.get('china_mentions', 0)} [{topic}] {title[:60]}", flush=True)
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
