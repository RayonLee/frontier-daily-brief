#!/usr/bin/env python3
"""
Deep check candidates for tech-learning-scan.
- Loads scan_results_<date>.json, extracts candidate article links from 'found' pages
- Verifies each article's true pub date (meta/JSON-LD/visible), word count, PDF link
- Writes scans/deep_check_report_<date>.json
Usage: python deep_check_scan.py YYYY-MM-DD
"""
import asyncio
import json
import os
import re
import sys
from datetime import date
from playwright.async_api import async_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# === 日期/正文提取（复制自 daily-think-tank-scan/scripts/deep_check_scan.py，自包含避免命名冲突） ===
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

_MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], 1)}
_MONTHS.update({"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
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
    if m and m.group(1).lower() in _MONTHS:
        return f"{m.group(3)}-{_MONTHS[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"
    m = re.search(r'(\d{1,2})\s+([A-Za-z]+)\.?\s+(202\d)', s)
    if m and m.group(2).lower() in _MONTHS:
        return f"{m.group(3)}-{_MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    return None

CONCURRENCY = 6
PAGE_TIMEOUT = 20000
SETTLE = 2

SKIP_HREF_RE = re.compile(
    r"newsletter|/people/|/authors?/|/about|/contact|/jobs?(/|$)|careers?|/events?(/|$)|#main-content|mailto:|/tags?/|/topics?/"
    r"|/solutions?/|/products?(/|$)|/platform|/company|/customers?/|/partners?/|/pricing|/docs(/|$)|/research/?$", re.I)
SKIP_TEXT_RE = re.compile(
    r"^(subscribe|skip to|read more|learn more|comments|share|sign up|log in|follow|watch|listen|view all.*|all news.*)$", re.I)

LIST_JS = r"""() => {
  const out = [];
  const seen = new Set();
  document.querySelectorAll('a[href]').forEach(a => {
    const href = a.href;
    if (!/^https?:/.test(href)) return;
    const title = (a.innerText || a.textContent || '').trim();
    if (title.length < 15 || title.length > 300) return;
    if (seen.has(href)) return;
    seen.add(href);
    let ctx = '';
    let node = a;
    for (let i = 0; i < 4 && node; i++) { ctx += ' ' + (node.innerText || ''); node = node.parentElement; }
    out.push({title: title.slice(0, 200), href: href, ctx: ctx.slice(0, 500)});
  });
  return out.slice(0, 30);
}"""

DATE_NEAR = re.compile(
    r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|January|February|March|April|June|July|August|September|October|November|December)\.?\s+\d{1,2},?\s+202\d'
    r'|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|January|February|March|April|June|July|August|September|October|November|December)\.?\s+202\d'
    r'|202\d-\d{2}-\d{2})', re.I)

SCAN_YEAR_RE = re.compile(r'202\d')


def context_has_scan_date(ctx, scan_date):
    """Check if the anchor's surrounding text mentions the scan date (or another 2026 date)."""
    m = DATE_NEAR.search(ctx)
    if not m:
        return None
    return parse_pub_date(m.group(1))


async def extract_candidates(page, url, scan_date):
    """Extract article links from a list page."""
    items = await page.evaluate(LIST_JS)
    cands = []
    seen = set()
    host = re.match(r'https?://([^/]+)', url).group(1)
    for it in items:
        href = it["href"].split("#")[0]
        if href in seen:
            continue
        if SKIP_HREF_RE.search(href) or SKIP_TEXT_RE.search(it["title"]):
            continue
        if host not in href:
            continue
        # keep links that look like articles (have a slug path deeper than 1 level)
        path = href.replace("https://", "").replace("http://", "")
        if path.count("/") < 2:
            continue
        # Note: add domain-specific filters here if a particular site produces many false positives.
        dm = context_has_scan_date(it["ctx"], scan_date)
        cands.append({"title": it["title"], "href": href, "list_date": dm})
        seen.add(href)
    return cands


async def check_article(context, sem, inst, track, scan_date, cand):
    url = cand["href"]
    rec = {
        "company": inst, "track": track, "scan_date": scan_date,
        "title": cand["title"][:200], "url": url,
        "pub_date": None, "matches_scan_date": False,
        "word_count": 0, "pdf_url": None, "error": None,
    }
    async with sem:
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
            await asyncio.sleep(SETTLE)
            data = await page.evaluate(EXTRACT_JS)
            rec["pub_date"] = parse_pub_date(data["pubDate"])
            # HF papers 等页面无 meta 日期时，回退到列表页分组日期（已验证为扫描日）
            if not rec["pub_date"] and cand.get("list_date"):
                rec["pub_date"] = cand["list_date"]
                rec["pub_date_source"] = "list_context"
            rec["matches_scan_date"] = (rec["pub_date"] == scan_date)
            rec["word_count"] = data["bodyWordCount"]
            rec["pdf_url"] = data["pdfUrl"]
            if data["title"]:
                rec["page_title"] = re.sub(r'\s+', ' ', data["title"])[:200]
        except Exception as e:
            rec["error"] = str(e)[:100]
        finally:
            await page.close()
        mark = "MATCH" if rec["matches_scan_date"] else "----"
        print(f"  {mark} {inst} | {rec['pub_date']} | w={rec['word_count']} | {rec['title'][:65]}", flush=True)
    return rec


async def main():
    scan_date = sys.argv[1]
    results = json.load(open(f"scan_results_{scan_date}.json", encoding="utf-8"))
    found = [r for r in results if r["status"] == "found"]
    # 无日期但需 first-N 检查的路径一并纳入
    from daily_scan_parallel import ALWAYS_CHECK_URLS, COMPANIES
    seen_urls = {r["url"] for r in found}
    for name, info in COMPANIES.items():
        for u in info["urls"]:
            if u in ALWAYS_CHECK_URLS and u not in seen_urls:
                tr = "B"
                for frag, t in info["track_hint"].items():
                    if frag in u:
                        tr = t
                        break
                found.append({"name": name, "url": u, "track": tr, "status": "always_check",
                              "dates_found": [], "has_scan_date": False, "error": None})
    print(f"=== Deep check {scan_date}: {len(found)} list pages ===", flush=True)

    async with async_playwright() as p:
        _proxy = os.environ.get("https_proxy") or os.environ.get("http_proxy")
        browser = await p.chromium.launch(headless=True, proxy={"server": _proxy} if _proxy else None)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
        await context.route(
            re.compile(r'\.(png|jpe?g|gif|svg|webp|ico|woff2?|ttf|otf|eot|mp4|webm)(\?|$)', re.I),
            lambda route: route.abort())

        all_cands = []
        seen_urls = set()
        for r in found:
            page = await context.new_page()
            try:
                await page.goto(r["url"], wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
                await asyncio.sleep(SETTLE + 1)
                cands = await extract_candidates(page, r["url"], scan_date)
                # 优先取列表上下文日期等于扫描日的候选；上下文无日期的也保留（页面上核验）
                kept = [c for c in cands if c["list_date"] == scan_date] or cands[:8]
                for c in kept:
                    if c["href"] not in seen_urls:
                        seen_urls.add(c["href"])
                        all_cands.append((r["name"], r["track"], c))
                print(f"{r['name']}: {len(kept)} candidates (from {len(cands)} links)", flush=True)
            except Exception as e:
                print(f"{r['name']}: extract ERR {str(e)[:60]}", flush=True)
            finally:
                await page.close()

        print(f"Total candidates: {len(all_cands)}", flush=True)
        sem = asyncio.Semaphore(CONCURRENCY)
        records = await asyncio.gather(*(
            check_article(context, sem, inst, track, scan_date, c) for inst, track, c in all_cands))
        await browser.close()

    os.makedirs("scans", exist_ok=True)
    out = f"scans/deep_check_report_{scan_date}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    matched = [r for r in records if r["matches_scan_date"]]
    print(f"\nMatched {scan_date}: {len(matched)} -> {out}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
