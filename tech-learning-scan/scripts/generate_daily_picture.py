#!/usr/bin/env python3
"""
学习日报 + 智库日报 → 报纸版式 HTML → 高清 PNG
Usage: python generate_daily_picture.py YYYY-MM-DD [智库日报路径]

流程：
1. 读取 tech-learning-scan/scans/daily-learn-<date>.md（科技 3W 学习笔记）
2. 读取 daily-think-tank-scan/scans/daily-scan-<date>.md（智库日报，可选；
   缺省时自动按同日查找，找不到则智库观察版块显示"本日智库无收录"）
3. 解析两份内容：智库观察 ← 智库日报 Track A 头条 + Track B 前 2 条；
   头条/次头条/科技要闻/社区短讯/词典 ← 学习日报
4. 生成报纸版式 HTML（模板固定，只换内容）
5. 用 Playwright 截图生成 PNG（仅 1200px 标准版；高清版已按用户要求取消）
6. 保存到 tech-learning-scan/Daily Picture/
"""

import asyncio
import json
import os
import re
import sys
from datetime import datetime, timedelta
from playwright.async_api import async_playwright

# 工作目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # tech-learning-scan/
DAILY_DIR = os.path.join(BASE_DIR, "scans")
OUTPUT_DIR = os.path.join(BASE_DIR, "Daily Picture")

# 报纸模板（CSS 固定，内容动态填充）
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<title><你的实验室>前沿科技咨询 · {date_cn}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  html, body {{ background: #e8e2d4; }}
  body {{
    font-family: "Noto Serif CJK SC", "Noto Serif SC", "Songti SC", "SimSun", serif;
    color: #1a1a1a;
  }}
  .paper {{
    width: 1200px;
    margin: 0 auto;
    background: #f5f0e6;
    padding: 26px 46px 15px 46px;
    background-image: radial-gradient(rgba(120,100,60,0.045) 1px, transparent 1px);
    background-size: 5px 5px;
  }}

  /* ===== 报头 ===== */
  .masthead-top {{
    display: flex; justify-content: space-between; align-items: flex-end;
    border-bottom: 1px solid #1a1a1a; padding-bottom: 5px;
    font-size: 13px; letter-spacing: 1px;
  }}
  .masthead {{ text-align: center; padding: 10px 0 8px 0; }}
  .masthead h1 {{
    font-size: 46px; font-weight: 900;
    letter-spacing: 5px; text-indent: 5px; line-height: 1.05;
  }}
  .masthead .en {{
    font-size: 14.5px; letter-spacing: 5px; text-indent: 5px;
    margin-top: 7px; color: #3a3a3a;
  }}
  .masthead-info {{
    display: flex; justify-content: space-between; align-items: center;
    border-top: 3px double #1a1a1a;
    border-bottom: 4px solid #1a1a1a;
    padding: 6px 2px 7px 2px;
    font-size: 14px;
  }}
  .masthead-info .slogan {{ font-weight: 700; letter-spacing: 2px; }}

  /* ===== 导读条 ===== */
  .lead-bar {{
    border-bottom: 1px solid #1a1a1a;
    padding: 9px 4px;
    font-size: 15px; line-height: 1.72; text-align: justify;
  }}
  .lead-bar .tag {{
    display: inline-block; background: #1a1a1a; color: #f5f0e6;
    font-size: 13px; padding: 1px 9px; margin-right: 10px;
    letter-spacing: 3px; vertical-align: 2px;
  }}

  /* ===== 版块眉题 ===== */
  .kicker {{
    text-align: center; font-size: 14px; letter-spacing: 2px;
    color: #333; margin: 10px 0 6px 0;
    white-space: nowrap;
  }}

  /* ===== 智库观察 ===== */
  .thinktank-zone {{
    border-bottom: 3px double #1a1a1a;
    padding-bottom: 12px;
  }}
  .thinktank-zone h2 {{
    text-align: center;
    font-size: 31px; font-weight: 900; line-height: 1.3;
    letter-spacing: 2px;
    margin-bottom: 8px;
  }}
  .thinktank-zone .subhead {{
    text-align: center; font-size: 15px; line-height: 1.65;
    margin: 0 auto 10px auto; max-width: 1020px; color: #2a2a2a;
  }}
  .thinktank-cols {{
    column-count: 3; column-gap: 24px;
    column-rule: 1px solid #8a8272;
    font-size: 14px; line-height: 1.72; text-align: justify;
  }}
  .thinktank-cols p {{ margin-bottom: 7px; text-indent: 2em; }}

  /* ===== 头条 ===== */
  .headline-zone {{ border-bottom: 1px solid #1a1a1a; padding: 8px 0 12px 0; }}
  .headline-zone h2 {{
    text-align: center;
    font-size: 33px; font-weight: 900; line-height: 1.28;
    letter-spacing: 2px;
  }}
  .headline-zone .subhead {{
    text-align: center; font-size: 15.5px; line-height: 1.65;
    margin: 8px auto 11px auto; max-width: 1020px; color: #2a2a2a;
  }}
  .headline-cols {{
    column-count: 3; column-gap: 24px;
    column-rule: 1px solid #8a8272;
    font-size: 14.2px; line-height: 1.74; text-align: justify;
  }}
  .headline-cols p {{ margin-bottom: 7px; text-indent: 2em; }}
  .dateline {{ font-weight: 700; }}

  /* ===== 中部：科技要闻（通栏两栏） ===== */
  .mid-zone {{
    border-bottom: 3px double #1a1a1a;
    padding: 0 0 13px 0;
  }}
  .news-list {{
    column-count: 2; column-gap: 28px;
    column-rule: 1px solid #b3ab97;
  }}
  .news-item {{
    break-inside: avoid;
    border-bottom: 1px solid #b3ab97;
    padding: 7px 0 8px 0;
  }}
  .news-item:nth-child(odd) {{ margin-right: 8px; }}
  .news-item h5 {{
    font-size: 17.5px; font-weight: 900; line-height: 1.42; margin-bottom: 5px;
  }}
  .news-item h5 .cat {{
    display: inline-block; background: #1a1a1a; color: #f5f0e6;
    font-size: 11.5px; font-weight: 400; letter-spacing: 2px;
    padding: 1px 7px; margin-right: 8px; vertical-align: 2px;
  }}
  .news-item p {{
    font-size: 13.5px; line-height: 1.68; text-align: justify; text-indent: 2em;
  }}

  /* ===== 社区短讯 ===== */
  .community {{ padding-top: 3px; border-bottom: 1px solid #1a1a1a; padding-bottom: 8px; }}
  .community-grid {{
    column-count: 2; column-gap: 24px; column-rule: 1px solid #b3ab97;
  }}
  .brief {{ margin-bottom: 7px; font-size: 13.4px; line-height: 1.64; text-align: justify; break-inside: avoid; }}
  .brief .bt {{ font-weight: 900; }}
  .brief .src {{ color: #555; font-size: 11.5px; }}

  /* ===== 页脚 ===== */
  .footer {{
    margin-top: 9px;
    border-top: 4px solid #1a1a1a;
    padding-top: 6px;
    display: flex; justify-content: space-between;
    font-size: 12px; color: #3a3a3a; letter-spacing: 1px;
  }}
</style>
</head>
<body>
<div class="paper">

  <!-- 报头 -->
  <div class="masthead-top">
    <span>{lunar_date}</span>
    <span>{weekday} · 正刊</span>
  </div>
  <div class="masthead">
    <h1><你的实验室>前沿科技咨询</h1>
    <div class="en">YOUR&nbsp;LAB&nbsp;·&nbsp;TECH&nbsp;FRONTIER&nbsp;BRIEFING</div>
  </div>
  <div class="masthead-info">
    <span>{date_full}　第 {issue} 期</span>
    <span class="slogan">{slogan}</span>
    <span><你的实验室> · 前沿观察室</span>
  </div>

  <!-- 导读条 -->
  <div class="lead-bar">
    <span class="tag">今日导读</span>{lead}
  </div>

  <!-- 智库观察 -->
  <div class="kicker">智　库　观　察</div>
  <div class="thinktank-zone">
    <h2>{thinktank_title}</h2>
    <div class="subhead">{thinktank_sub}</div>
    <div class="thinktank-cols">
      {thinktank_cols}
    </div>
  </div>

  <!-- 头条 -->
  <div class="kicker">要　闻</div>
  <div class="headline-zone">
    <h2>{headline_title}</h2>
    <div class="subhead">{headline_sub}</div>
    <div class="headline-cols">
      {headline_cols}
    </div>
  </div>

  <!-- 中部：科技要闻（通栏两栏） -->
  <div class="kicker">科 技 要 闻</div>
  <div class="mid-zone">
    <div class="news-list">
      {news_list}
    </div>
  </div>

  <!-- 社区短讯 -->
  <div class="kicker">社 区 短 讯</div>
  <div class="community">
    <div class="community-grid">
      {briefs}
    </div>
  </div>

  <!-- 页脚 -->
  <div class="footer">
    <span>整理来源：学习日报「科技公司前沿动态 · 分层级 3W 版」（内容归属 {date_str}）；智库观察来自 daily-think-tank-scan {tt_source} 扫描</span>
    <span><你的实验室> 编印</span>
  </div>

</div>
</body>
</html>
"""

def _md_bold_to_html(text):
    """把 markdown **加粗** 转成 <b> 标签"""
    text = re.sub(r'\*\*', '<b>', text, count=1)
    text = re.sub(r'\*\*', '</b>', text, count=1)
    text = re.sub(r'\*\*', '<b>', text)
    text = re.sub(r'\*\*', '</b>', text)
    return text


def parse_thinktank_md(tt_path, date_str):
    """解析智库日报 daily-scan-<date>.md，提取智库观察版块内容。

    固定抽取规则（内容换、规则不换）：
    - 版块标题：Track A 首条报告标题；无 Track A 时取 Track B 首个 High 优先级条目
    - 副题：来源机构 + 日期
    - 正文三栏：Track A 要点 1 栏 + Track B 前 2 条（High 优先）各 1 栏
    返回 dict 或 None（文件不存在/解析失败）。
    """
    if not os.path.exists(tt_path):
        return None
    with open(tt_path, "r", encoding="utf-8") as f:
        text = f.read()

    # --- Track A：表格首行 | 1 | [title](url) | Inst | date | topic | words | pdf | status |
    track_a = None
    m = re.search(r'## Track A[^\n]*\n(?:.*\n)*?\|[\s]*1[\s]*\|\s*\[([^\]]+)\]\(([^)]+)\)\s*\|\s*([^|]+)\|', text)
    if m:
        track_a = {"title": m.group(1).strip(), "url": m.group(2).strip(),
                   "inst": m.group(3).strip()}

    # --- Track B：按条目拆分，避免跨条目匹配导致标题与正文错配
    track_b = []
    for part in re.split(r'\n(?=### \d+\.\s+)', text):
        m = re.match(r'### \d+\.\s+\[([^\]]+)\]\(([^)]+)\)（([^，）]+)[，)]([^）]*?)）', part)
        if not m:
            continue
        title, url, inst, prio = [g.strip() for g in m.groups()]
        # 取该条目内最有信息量的摘要：导语 > Key points > 事实
        kp = ""
        for pat in [r'- \*\*导语\*\*[：:]\s*(.+?)(?=\n- \*\*|\n## |\n---|$)',
                    r'- \*\*Key points\*\*[：:]\s*(.+?)(?=\n|$)',
                    r'- \*\*事实\*\*[：:]\s*(.+?)(?=\n- \*\*|\n## |\n---|$)']:
            mm = re.search(pat, part, re.S)
            if mm:
                kp = mm.group(1).strip()
                break
        if len(kp) < 30:          # 太短的摘要（等于标题或空洞）跳过
            continue
        track_b.append({"title": title, "url": url, "inst": inst,
                        "prio": prio, "kp": kp})

    if not track_a and not track_b:
        return None

    # High 优先排序；同优先级保持原文顺序
    track_b.sort(key=lambda x: 0 if x["prio"] == "High" else 1)

    # --- 版块标题与副题
    if track_a:
        zone_title = track_a["title"]
        zone_sub = f'{track_a["inst"]} 研究报告 · {date_str}'
        b_items = track_b[:2]          # 有 Track A 时补 2 条 Track B
    else:
        zone_title = track_b[0]["title"]
        zone_sub = f'{track_b[0]["inst"]} 评论 · {date_str}'
        b_items = track_b[:3]          # 无 Track A 时取 3 条 Track B

    # --- 正文三栏
    col_texts = []
    if track_a:
        p = f'{track_a["title"]}（{track_a["inst"]}）'
        col_texts.append(f'<p><span class="dateline">【智库报告】</span>{p}，详见智库日报。</p>')
    for item in b_items:
        kp = item["kp"]
        if len(kp) > 220:
            kp = kp[:217] + "..."
        kp = _md_bold_to_html(kp)
        col_texts.append(
            f'<p><span class="dateline">【{item["inst"]}】</span>'
            f'<b>{item["title"]}</b>。{kp}</p>')
    while len(col_texts) < 3:
        col_texts.append('<p><span class="dateline">【智库观察】</span>详见智库日报。</p>')

    return {"thinktank_title": zone_title, "thinktank_sub": zone_sub,
            "thinktank_cols": "\n".join(col_texts)}


def parse_draft(draft_path, base_data):
    """解析日报成稿 daily-news-<date>.draft.md（编辑重写后的报纸成稿）。

    成稿为固定结构（见 draft-template.md），本函数只做机械分栏，不做改写。
    允许在正文中直接使用 <b> 等 HTML 标签；每栏第一个 <p> 自动加【本报讯】/【智库观察】。
    """
    with open(draft_path, "r", encoding="utf-8") as f:
        text = f.read()

    data = dict(base_data)

    def section(name):
        m = re.search(rf'## {name}\s*\n(.+?)(?=\n## |\Z)', text, re.S)
        return m.group(1).strip() if m else ""

    def field(body, key, default=""):
        m = re.search(rf'^{key}[：:](.+?)(?=\n[^ \t]|\Z)', body, re.S | re.M)
        return m.group(1).strip() if m else default

    def items(body):
        return [m.strip() for m in re.findall(r'^- (.+?)(?=\n- |\Z)', body, re.S | re.M)]

    # 导读
    lead = field(text, "导读") if text.startswith("导读") else ""
    if not lead:
        m = re.search(r'## 导读\s*\n\s*\n?(.+?)(?=\n## |\Z)', text, re.S)
        lead = m.group(1).strip() if m else ""
    if lead:
        data["lead"] = re.sub(r'\n+', '', lead)

    # 智库观察
    tt = section("智库观察")
    if tt:
        data["thinktank_title"] = field(tt, "标题", data.get("thinktank_title", ""))
        data["thinktank_sub"] = field(tt, "副题", data.get("thinktank_sub", ""))
        cols = items(tt)
        if cols:
            paras = "".join(f'<p>{c}</p>' for c in cols)
            paras = paras.replace("<p>", '<p><span class="dateline">【智库观察】</span>', 1)
            data["thinktank_cols"] = paras

    # 要闻
    hl = section("要闻")
    if hl:
        data["headline_title"] = field(hl, "标题", data.get("headline_title", ""))
        data["headline_sub"] = field(hl, "副题", data.get("headline_sub", ""))
        cols = items(hl)
        if cols:
            paras = "".join(f'<p>{c}</p>' for c in cols)
            paras = paras.replace("<p>", '<p><span class="dateline">【本报讯】</span>', 1)
            data["headline_cols"] = paras

    # 科技要闻：### <分类> <标题>\n<摘要>
    mid = section("科技要闻")
    news_items = []
    for m in re.finditer(r'###\s+(\S+)\s+(.+?)\n\s*\n?(.+?)(?=\n### |\Z)', mid, re.S):
        cat, title, para = m.group(1), m.group(2).strip(), m.group(3).strip()
        para = re.sub(r'\n+', ' ', para)
        news_items.append(
            f'<div class="news-item"><h5><span class="cat">{cat}</span>{title}</h5>'
            f'<p>{para}</p></div>')
    if news_items:
        data["news_list"] = "\n".join(news_items)

    # 社区短讯
    comm = section("社区短讯")
    briefs = items(comm)
    if briefs:
        data["briefs"] = "\n".join(
            f'<div class="brief">{b}</div>' for b in briefs)

    # 口号（报头眉题）：兼容「口号：xxx」与「## 口号\nxxx」两种写法
    slogan = field(text, "口号")
    if not slogan:
        m = re.search(r'## 口号\s*\n\s*\n?(.+?)(?=\n## |\Z)', text, re.S)
        slogan = m.group(1).strip() if m else ""
    if slogan:
        data["slogan"] = re.sub(r'\n+', '', slogan)

    return data


def parse_daily_md(md_path):
    """解析 daily-learn-*.md，提取结构化内容"""
    with open(md_path, "r", encoding="utf-8") as f:
        text = f.read()

    # 提取日期（学习笔记文件日期 = 搜集日期；报纸出版日期 = 搜集日期 + 1 天，以覆盖跨洋滞后）
    m = re.search(r'# 学习笔记 · (\d{4}-\d{2}-\d{2})', text)
    date_str = m.group(1) if m else ""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    publish_dt = dt + timedelta(days=1)
    date_cn = f"{publish_dt.year}年{publish_dt.month}月{publish_dt.day}日"
    weekday = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"][publish_dt.weekday()]
    date_full = f"{date_cn}　{weekday}"
    issue = (publish_dt - datetime(2026, 7, 28)).days + 1  # 假设从7月28日起算第一期

    # 提取主题导览（导读）
    lead_match = re.search(r'## 今日主题导览\s*\n\s*\n(.+?)(?=\n\n# |\n---|$)', text, re.S)
    lead = lead_match.group(1).strip() if lead_match else ""
    # 清理 lead 中的 markdown 格式
    lead = re.sub(r'\*\*', '<b>', lead, count=1)
    lead = re.sub(r'\*\*', '</b>', lead, count=1)
    lead = re.sub(r'\*\*', '<b>', lead)
    lead = re.sub(r'\*\*', '</b>', lead)
    lead = re.sub(r'\n+', '', lead)
    # 限制长度
    if len(lead) > 400:
        lead = lead[:397] + "..."

    # 提取 slogan（最后一句话）
    slogan = ""
    m = re.search(r'一句话[：:]\s*(.+?)(?:\n|$)', text)
    if m:
        slogan = m.group(1).strip().strip("*").strip()
    if not slogan:
        slogan = "跟踪前沿，洞察趋势。"

    # 提取智库观察
    thinktank_title = ""
    thinktank_sub = ""
    thinktank_cols = ""
    tt_match = re.search(r'## 智库观察\s*\n\n(.+?)(?=\n## |\n---|$)', text, re.S)
    if tt_match:
        tt_body = tt_match.group(1).strip()
        tt_title_match = re.search(r'\*\*(.+?)\*\*', tt_body)
        thinktank_title = tt_title_match.group(1).strip() if tt_title_match else ""
        tt_paras = [p.strip() for p in tt_body.split('\n\n') if p.strip()]
        if len(tt_paras) >= 2 and len(tt_paras[1]) < 220:
            thinktank_sub = tt_paras[1]
            tt_paras = tt_paras[2:]
        else:
            tt_paras = tt_paras[1:]
        col_texts = []
        for p in tt_paras[:3]:
            p = re.sub(r'\*\*', '<b>', p, count=1)
            p = re.sub(r'\*\*', '</b>', p, count=1)
            p = re.sub(r'\*\*', '<b>', p)
            p = re.sub(r'\*\*', '</b>', p)
            p = re.sub(r'\n+', '</p><p>', p.strip())
            col_texts.append(f'<p><span class="dateline">【智库观察】</span>{p}</p>')
        while len(col_texts) < 3:
            col_texts.append('<p><span class="dateline">【智库观察】</span>详见智库日报。</p>')
        thinktank_cols = "\n".join(col_texts)

    # 提取头条（Tier 1 或 2.1）
    sections = re.findall(r'## ([\d.]+)\s+(.+?)\n\n(.+?)(?=\n## [\d.]+|\n---|$)', text, re.S)

    headline_title = ""
    headline_sub = ""
    headline_cols = ""
    second_title = ""
    second_cols = ""
    side_title = ""
    side_content = ""
    news_list = ""
    dict_items = ""
    briefs = ""

    for idx, (num, title, body) in enumerate(sections):
        # 清理 body
        body = body.strip()
        # 提取链接
        link_match = re.search(r'\- 链接[：:]\s*\[(.+?)\]\((.+?)\)', body)
        link = f'<a href="{link_match.group(2)}">{link_match.group(1)}</a>' if link_match else ""

        # 提取 What/Why/How 段落
        paras = re.findall(r'\*\*[WWH].*?\*\*\s*（.+?）\s*\n(.+?)(?=\n\*\*[WWH]|\n\- 链接|## |\n---|$)', body, re.S)

        if idx == 0:  # 头条
            headline_title = title.strip()
            headline_sub_match = re.search(r'\*\*What.*?\n(.+?)(?=\n\*\*Why|$)', body, re.S)
            headline_sub = headline_sub_match.group(1).strip() if headline_sub_match else ""
            headline_sub = re.sub(r'\*\*', '', headline_sub)
            headline_sub = re.sub(r'\n+', ' ', headline_sub)
            if len(headline_sub) > 200:
                headline_sub = headline_sub[:197] + "..."

            # 构造三栏正文
            col_texts = []
            for p in paras[:3]:
                p = re.sub(r'\*\*', '<b>', p, count=1)
                p = re.sub(r'\*\*', '</b>', p, count=1)
                p = re.sub(r'\*\*', '<b>', p)
                p = re.sub(r'\*\*', '</b>', p)
                p = re.sub(r'\n+', '</p><p>', p.strip())
                col_texts.append(f'<p><span class="dateline">【本报讯】</span>{p}</p>')
            # 如果段落不够，用通用内容填充
            while len(col_texts) < 3:
                col_texts.append(f'<p><span class="dateline">【本报讯】</span>详见原始学习日报：{link}</p>')
            headline_cols = "\n".join(col_texts)

        elif idx == 1:  # 次头条
            second_title = title.strip()
            col_texts = []
            for p in paras[:3]:
                p = re.sub(r'\*\*', '<b>', p, count=1)
                p = re.sub(r'\*\*', '</b>', p, count=1)
                p = re.sub(r'\*\*', '<b>', p)
                p = re.sub(r'\*\*', '</b>', p)
                p = re.sub(r'\n+', '</p><p>', p.strip())
                col_texts.append(f'<p>{p}</p>')
            while len(col_texts) < 3:
                col_texts.append(f'<p>详见原始学习日报：{link}</p>')
            second_cols = "\n".join(col_texts)

            # 旁注内容：取自当日「今日主题导览」（学习日报的综合判断），不再硬编码
            side_title = "今日主题导览"
            lead_html = lead if lead else "详见原始学习日报。"
            side_content = f'<p>{lead_html}</p>'

    # 提取社区精选（3.1-3.x）
    community_sections = re.findall(r'## 3\.(\d+)\s+(.+?)\n\n(.+?)(?=\n## 3\.|\n## |\n---|$)', text, re.S)
    news_items = []
    for num, title, body in community_sections[:4]:
        cat = "精选"
        if "电商" in title or "Agent" in title:
            cat = "电商"
        elif "视频" in title or "编辑" in title:
            cat = "视频"
        elif "落地" in title or "部署" in title:
            cat = "落地"
        elif "模型" in title or "LLM" in title:
            cat = "模型"

        # 提取正文第一段（跳过"链接："行——那是原始 markdown 链接，直接上版会露馅）
        para_match = re.search(r'\n\- ((?!链接[：:]).+?)(?=\n\n|\n\- |$)', body, re.S)
        para = para_match.group(1).strip() if para_match else body[:300]
        para = re.sub(r'\*\*', '<b>', para, count=1)
        para = re.sub(r'\*\*', '</b>', para, count=1)
        para = re.sub(r'\*\*', '<b>', para)
        para = re.sub(r'\*\*', '</b>', para)
        para = re.sub(r'\n+', ' ', para)
        if len(para) > 350:
            para = para[:347] + "..."

        news_items.append(f'<div class="news-item"><h5><span class="cat">{cat}</span>{title.strip()}</h5><p>{para}</p></div>')
    news_list = "\n".join(news_items)

    # 提取概念小词典
    dict_match = re.search(r'## 概念小词典.*?\n\n\| 术语 \| 一句话解释 \|.*?\n\|[-\s|]+\n(.+?)(?=\n## |\n---|$)', text, re.S)
    if dict_match:
        dict_rows = re.findall(r'\|\s*(.+?)\s*\|\s*(.+?)\s*\|', dict_match.group(1))
        dict_items_list = []
        for term, defin in dict_rows[:6]:
            term = term.strip().strip('**').strip()
            defin = defin.strip()
            dict_items_list.append(f'<div class="dict-item"><div class="term">{term}</div><div class="def">{defin}</div></div>')
        dict_items = "\n".join(dict_items_list)
    else:
        dict_items = '<div class="dict-item"><div class="term">MCP</div><div class="def">Model Context Protocol，AI 的 USB-C 接口</div></div>'

    # 提取社区短讯
    brief_match = re.search(r'## 3\.3\s+其余精选\n\n(.+?)(?=\n## |\n---|$)', text, re.S)
    if brief_match:
        brief_text = brief_match.group(1)
        brief_lines = re.findall(r'\- \[(.+?)\]\((.+?)\)（(.+?)）—\s*(.+?)(?=\n|$)', brief_text)
        brief_list = []
        for title_b, url_b, src_b, desc_b in brief_lines[:6]:
            brief_list.append(f'<div class="brief"><span class="bt">▲ {title_b}。</span>{desc_b}<span class="src">（{src_b}）</span></div>')
        briefs = "\n".join(brief_list)
    else:
        briefs = '<div class="brief"><span class="bt">▲ 暂无短讯。</span>详见原始学习日报。</div>'

    # 农历日期（简化，使用固定映射或忽略）
    lunar_date = "农历丙午年"

    return {
        "lunar_date": lunar_date,
        "weekday": weekday,
        "date_full": date_full,
        "issue": issue,
        "slogan": slogan,
        "lead": lead,
        "thinktank_title": thinktank_title,
        "thinktank_sub": thinktank_sub,
        "thinktank_cols": thinktank_cols,
        "headline_title": headline_title,
        "headline_sub": headline_sub,
        "headline_cols": headline_cols,
        "second_title": second_title,
        "second_cols": second_cols,
        "side_title": side_title,
        "side_content": side_content,
        "news_list": news_list,
        "briefs": briefs,
        "date_str": date_str,
        "date_cn": date_cn,
    }


def fill_template(data):
    """填充 HTML 模板"""
    html = HTML_TEMPLATE
    for key, val in data.items():
        html = html.replace("{" + key + "}", str(val))
    # CSS uses double braces as literal escapes; convert them after variable substitution
    html = html.replace("{{", "{").replace("}}", "}")
    return html


async def screenshot_html(html_path, png_path):
    """用 Playwright 截图生成 PNG（仅标准版 1200px；高清版已取消，2026-09-17 用户决定）"""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(f"file:///{os.path.abspath(html_path)}", wait_until="networkidle")
        # 等待字体加载
        await asyncio.sleep(1)

        # 获取页面完整高度
        height = await page.evaluate("() => document.body.scrollHeight")

        # 标准分辨率截图 (1200px 宽)
        await page.set_viewport_size({"width": 1200, "height": height + 20})
        await page.screenshot(path=png_path, full_page=True)
        print(f"  Saved PNG: {png_path} ({1200}x{height})")

        await browser.close()


async def main():
    auto_fallback = "--auto" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    date_str = args[0] if args else datetime.now().strftime("%Y-%m-%d")
    # 跨洋信息滞后：日报报头/成稿/输出文件均使用发布日期（搜集日期 +1 天）
    pub_dt = datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)
    pub_date_str = pub_dt.strftime("%Y-%m-%d")

    md_path = os.path.join(DAILY_DIR, f"daily-learn-{date_str}.md")

    if not os.path.exists(md_path):
        print(f"ERROR: Markdown not found: {md_path}")
        sys.exit(1)

    # 智库日报输入：第二个非 flag 命令行参数可显式指定；否则按同日自动查找
    tt_path = args[1] if len(args) > 1 else os.path.join(
        BASE_DIR, os.pardir, "daily-think-tank-scan", "scans",
        f"daily-scan-{date_str}.md")

    # 日报成稿优先；无成稿时默认阻断，避免自动解析产出低质量图片
    # 成稿文件名使用发布日期，与图片报头保持一致
    draft_path = os.path.join(OUTPUT_DIR, f"daily-news-{pub_date_str}.draft.md")
    if not os.path.exists(draft_path) and not auto_fallback:
        print(f"ERROR: 日报成稿不存在：{draft_path}")
        print("请按 Daily Picture/draft-template.md 整合两份日报后重新运行；")
        print("或加 --auto 强制使用自动解析兜底（质量不保证，仅用于调试）。")
        sys.exit(1)

    print(f"=== Daily Picture Generator ===")
    print(f"Collection date: {date_str}")
    print(f"Publish date:    {pub_date_str}")
    print(f"Input (tech): {md_path}")
    print(f"Input (think-tank): {tt_path}")

    # 解析 markdown
    print("Parsing markdown...")
    data = parse_daily_md(md_path)

    # 智库观察版块：优先取智库日报；缺失时降级
    tt_file = os.path.basename(tt_path)
    tt_date = re.sub(r'^daily-scan-|\.md$', '', tt_file)  # 智库内容以其文件日期为准
    tt_data = parse_thinktank_md(tt_path, tt_date)
    if tt_data:
        data.update(tt_data)
        data["tt_source"] = tt_date
        print("  Think-tank section: from daily-scan md")
    else:
        data["thinktank_title"] = data.get("thinktank_title") or "本日智库无收录"
        data["thinktank_sub"] = data.get("thinktank_sub") or "详见 daily-think-tank-scan/scans/"
        data["tt_source"] = "（无当日扫描）"
        print("  Think-tank section: fallback (no daily-scan md found)")

    # 成稿优先：若存在编辑重写的 draft，用成稿内容覆盖自动解析结果
    if os.path.exists(draft_path):
        data = parse_draft(draft_path, data)
        print(f"  Draft override: {draft_path}")
    else:
        print("  Draft override: none (auto-parsed)")

    # 生成 HTML
    print("Generating HTML...")
    html = fill_template(data)
    html_path = os.path.join(OUTPUT_DIR, f"daily-news-{pub_date_str}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Saved HTML: {html_path}")

    # 截图（仅标准版；高清版已取消）
    print("Capturing screenshot...")
    png_path = os.path.join(OUTPUT_DIR, f"daily-news-{pub_date_str}.png")
    await screenshot_html(html_path, png_path)

    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
