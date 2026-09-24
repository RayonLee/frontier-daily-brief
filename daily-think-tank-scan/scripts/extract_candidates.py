#!/usr/bin/env python3
"""Extract article candidate links from a think-tank list page.
Usage: candidates = await extract_candidates(url, scan_date)
Returns list of {"title": str, "href": str, "list_date": str|None}.
"""
import re
from playwright.async_api import async_playwright

SKIP_HREF_RE = re.compile(
    r"newsletter|/people/|/authors?/|/about|/contact|/jobs?(/|$)|careers?|/events?(/|$)|#main-content|mailto:|/tags?/|/topics?/"
    r"|/solutions?/|/products?(/|$)|/platform|/company|/customers?/|/partners?/|/pricing|/docs(/|$)|/research/?$", re.I)
SKIP_TEXT_RE = re.compile(
    r"^(subscribe|skip to|read more|learn more|comments|share|sign up|log in|follow|watch|listen|view all.*|all news.*)$", re.I)

DATE_NEAR = re.compile(
    r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|January|February|March|April|June|July|August|September|October|November|December)\.?\s+\d{1,2},?\s+202\d'
    r'|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|January|February|March|April|June|July|August|September|October|November|December)\.?\s+202\d'
    r'|202\d-\d{2}-\d{2})', re.I)

MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], 1)}
MONTHS.update({"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
               "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12})


def parse_pub_date(raw):
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


def context_has_scan_date(ctx):
    m = DATE_NEAR.search(ctx)
    if not m:
        return None
    return parse_pub_date(m.group(1))


async def extract_candidates(url, scan_date):
    """Open list page and return article candidates."""
    cands = []
    seen = set()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=20000)
            await page.wait_for_timeout(1500)
            items = await page.evaluate(LIST_JS)
            host_match = re.match(r'https?://([^/]+)', url)
            host = host_match.group(1) if host_match else ""
            for it in items:
                href = it["href"].split("#")[0]
                if href in seen:
                    continue
                if SKIP_HREF_RE.search(href) or SKIP_TEXT_RE.search(it["title"]):
                    continue
                if host and host not in href:
                    continue
                path = href.replace("https://", "").replace("http://", "")
                if path.count("/") < 2:
                    continue
                list_date = context_has_scan_date(it["ctx"])
                cands.append({"title": it["title"], "href": href, "list_date": list_date})
                seen.add(href)
        finally:
            await page.close()
            await browser.close()
    return cands
