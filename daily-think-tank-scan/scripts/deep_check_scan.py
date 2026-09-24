#!/usr/bin/env python3
"""
Deep check candidate articles for a scan date.
- Loads scan_results_<date>.json, extracts candidates from 'found' list pages
- Visits each candidate article page: true pub date (meta/JSON-LD/visible),
  word count, China mentions, PDF link
- Writes scans/deep_check_report_<date>.json
Usage: python deep_check_scan.py YYYY-MM-DD
"""
import asyncio
import json
import os
import re
import sys
from playwright.async_api import async_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_candidates import extract_candidates

CONCURRENCY = 6
PAGE_TIMEOUT = 20000
SKIP_URL_RE = re.compile(r'/events?/|/podcasts?/', re.I)

EXTRACT_JS = r"""() => {
  const text = document.body.innerText;
  const metaPub = document.querySelector('meta[property="article:published_time"], meta[name="pubdate"], meta[name="publish-date"], meta[name="date"]');
  let pubDate = metaPub ? metaPub.getAttribute('content') : null;
  if (!pubDate) {
    const lds = document.querySelectorAll('script[type="application/ld+json"]');
    for (const ld of lds) {
      try {
        const data = JSON.parse(ld.textContent);
        const arr = Array.isArray(data) ? data : [data];
        for (const d of arr) {
          const dp = d.datePublished || (d['@graph'] && d['@graph'][0] && d['@graph'][0].datePublished);
          if (dp) { pubDate = dp; break; }
        }
      } catch(e) {}
      if (pubDate) break;
    }
  }
  if (!pubDate) {
    const m = text.match(/(?:Published\s+(?:on\s+)?|Posted\s+(?:on\s+)?)((?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+\d{1,2},?\s+202\d|\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+202\d)/i);
    pubDate = m ? m[1] : null;
  }
  if (!pubDate) {
    const m = text.match(/((?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+\d{1,2},?\s+202\d|\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+202\d)/i);
    pubDate = m ? m[1] : null;
  }
  const pdfLink = document.querySelector('a[href*=".pdf"]');
  let paraText = '';
  document.querySelectorAll('p').forEach(p => { if (p.innerText.trim().length > 20) paraText += p.innerText + ' '; });
  return {
    pubDate: pubDate,
    bodyWordCount: paraText.split(/\s+/).filter(w => w.length > 0).length,
    chinaCount: (text.match(/China|Chinese|PRC|Beijing|Xi\s+Jinping/gi) || []).length,
    hasPdf: !!pdfLink,
    pdfUrl: pdfLink ? pdfLink.href : null,
    title: document.title || ''
  };
}"""

MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], 1)}
MONTHS.update({"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
               "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12})


def parse_pub_date(raw):
    """Normalize any pub date string to YYYY-MM-DD, or None."""
    if not raw:
        return None
    s = str(raw).strip()
    m = re.search(r'(202\d)-(\d{2})-(\d{2})', s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r'([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(202\d)', s)
    if m and m.group(1).lower() in MONTHS:
        return f"{m.group(3)}-{MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"
    m = re.search(r'(\d{1,2})\s+([A-Za-z]+)\.?\s+(202\d)', s)
    if m and m.group(2).lower() in MONTHS:
        return f"{m.group(3)}-{MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    return None


async def check_article(context, sem, inst, scan_date, cand):
    url = cand["href"]
    rec = {
        "institution": inst, "scan_date": scan_date, "title": cand["title"][:200],
        "url": url, "pub_date": None, "matches_scan_date": False,
        "word_count": 0, "china_mentions": 0, "pdf_url": None, "error": None,
    }
    if SKIP_URL_RE.search(url):
        rec["error"] = "skipped (event/podcast)"
        return rec
    async with sem:
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
            await asyncio.sleep(1)
            data = await page.evaluate(EXTRACT_JS)
            rec["pub_date"] = parse_pub_date(data["pubDate"])
            rec["matches_scan_date"] = (rec["pub_date"] == scan_date)
            rec["word_count"] = data["bodyWordCount"]
            rec["china_mentions"] = data["chinaCount"]
            rec["pdf_url"] = data["pdfUrl"]
            if data["title"]:
                rec["page_title"] = data["title"][:200]
        except Exception as e:
            rec["error"] = str(e)[:100]
        finally:
            await page.close()
        print(f"  {'MATCH' if rec['matches_scan_date'] else '----'} {inst} | {rec['pub_date']} | w={rec['word_count']} china={rec['china_mentions']} | {rec['title'][:70]}",
              flush=True)
    return rec


async def main():
    scan_date = sys.argv[1]
    results = json.load(open(f"scan_results_{scan_date}.json", encoding="utf-8"))
    found = [r for r in results if r["status"] == "found"]
    print(f"=== Deep check {scan_date}: {len(found)} list pages ===", flush=True)

    # 1) extract candidates from each found list page
    all_cands = []  # (institution, candidate)
    seen_urls = set()
    for r in found:
        cands = await extract_candidates(r["url"], scan_date)
        for c in cands:
            if c["href"] not in seen_urls:
                seen_urls.add(c["href"])
                all_cands.append((r["name"], c))
    print(f"Candidates: {len(all_cands)}", flush=True)

    # 2) deep check each candidate article page
    async with async_playwright() as p:
        _proxy = os.environ.get("https_proxy") or os.environ.get("http_proxy")
        browser = await p.chromium.launch(headless=True, proxy={"server": _proxy} if _proxy else None)
        context = await browser.new_context()
        await context.route(
            re.compile(r'\.(png|jpe?g|gif|svg|webp|ico|woff2?|ttf|otf|eot|mp4|webm)(\?|$)', re.I),
            lambda route: route.abort())
        sem = asyncio.Semaphore(CONCURRENCY)
        records = await asyncio.gather(*(
            check_article(context, sem, inst, scan_date, c) for inst, c in all_cands))
        await browser.close()

    out = f"scans/deep_check_report_{scan_date}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    matched = [r for r in records if r["matches_scan_date"]]
    china = [r for r in matched if r["china_mentions"] > 0]
    print(f"\nMatched {scan_date}: {len(matched)} | China-related: {len(china)} -> {out}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
