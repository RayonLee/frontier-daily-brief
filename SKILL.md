# 智库 + 科技搜索日报 Skill

一套用 Playwright 抓取、筛选、登记并生成报纸版式日报图片的自动化流程。

## 目录结构

```
skill-export/
├── config/                           # 监控列表（导出时已清空）
│   ├── think_tank_list.json
│   ├── tech_company_list.json
│   └── list-format.md
├── daily-think-tank-scan/            # 智库流程
│   ├── scripts/
│   │   ├── daily_scan.py
│   │   ├── deep_check_scan.py
│   │   ├── extract_candidates.py
│   │   ├── save_articles.py
│   │   └── streamline_save_and_report.py
│   ├── assets/                       # CSV 登记目录
│   ├── scans/                        # 深查报告与日报 md
│   └── raw-reports/                  # 原文 txt
├── tech-learning-scan/               # 科技公司流程
│   ├── scripts/
│   │   ├── daily_scan_parallel.py
│   │   ├── deep_check_scan.py
│   │   ├── save_articles.py
│   │   ├── streamline_save_and_report.py
│   │   └── generate_daily_picture.py
│   ├── Daily Picture/                # 日报成稿 + HTML + PNG
│   │   └── draft-template.md
│   ├── assets/
│   ├── scans/
│   └── raw-reports/
└── SKILL.md
```

## 安装依赖

```bash
pip install playwright
playwright install chromium
```

额外依赖（可选）：`python-docx`、`pdfplumber`（仅在你想扩展 PDF 分析时）。

## 第一步：填写监控列表

打开 `config/think_tank_list.json` 和 `config/tech_company_list.json`，按 `config/list-format.md` 的格式填入你要监控的机构与列表页 URL。

> 导出版本里这两个 JSON 是空的，不会暴露任何实际监控目标。

## 第二步：运行智库流程

```bash
cd daily-think-tank-scan

# 1. 浅扫：检测哪些列表页包含目标日期
python scripts/daily_scan.py 2026-09-23

# 2. 深查：进入候选文章页核实发布日期、字数、涉华提及
python scripts/deep_check_scan.py 2026-09-23

# 3. 保存原文
python scripts/save_articles.py 2026-09-23

# 4. 登记 + 生成日报 markdown
python scripts/streamline_save_and_report.py 2026-09-23
```

## 第三步：运行科技流程

```bash
cd tech-learning-scan

# 1. 浅扫
python scripts/daily_scan_parallel.py 2026-09-23

# 2. 深查
python scripts/deep_check_scan.py 2026-09-23

# 3. 保存原文
python scripts/save_articles.py 2026-09-23

# 4. 登记 + 生成日报 markdown
python scripts/streamline_save_and_report.py 2026-09-23
```

## 第四步：生成日报图片

图片发布日期 = 搜集日期 + 1 天。例如 9 月 23 日搜集，输出文件名为 `daily-news-2026-09-24`。

1. 复制 `Daily Picture/draft-template.md` 为 `Daily Picture/daily-news-<发布日期>.draft.md`，按模板整合智库 + 科技两份日报。
2. 确保 `tech-learning-scan/scans/daily-learn-<搜集日期>.md` 的标题为 `# 学习笔记 · YYYY-MM-DD`。
3. 运行：

```bash
cd tech-learning-scan
python scripts/generate_daily_picture.py <搜集日期>
```

输出：
- `Daily Picture/daily-news-<发布日期>.html`
- `Daily Picture/daily-news-<发布日期>.png`

## 主要输出文件

| 流程 | 文件 | 说明 |
|---|---|---|
| 浅扫 | `scan_results_<date>.json` | 各列表页是否发现目标日期 |
| 深查 | `scans/deep_check_report_<date>.json` | 每篇候选文章的日期、字数、PDF、涉华提及 |
| 保存 | `scans/_saved_<date>.json` | 成功保存的原文清单 |
| 智库日报 | `daily-think-tank-scan/scans/daily-scan-<date>.md` | Track A/B 表格与摘要 |
| 科技日报 | `tech-learning-scan/scans/daily-learn-<date>.md` | Track A/B 表格与摘要 |
| 图片 | `tech-learning-scan/Daily Picture/daily-news-<发布日期>.png` | 报纸版式高清图 |

## Track A / Track B 定义

- **智库 Track A**：字数 ≥ 8,000 的研究报告。
- **智库 Track B**：字数 < 8,000 的评论/分析，且涉华提及 ≥ 1（或白宫/官方渠道的政策页面）。
- **科技 Track A**：来自公司研究出版物页面的论文/报告。
- **科技 Track B**：来自公司博客、新闻、开发者博客的文章。

## 省 token 设计要点

- 深查阶段只记录元数据，不读全文。
- 保存阶段逐页下载，但登记日报时只读单篇 txt，不一次性加载所有原文。
- 生成图片前再人工整合为 `draft.md`，避免反复解析大量 markdown。

## 已知限制

- `streamline_save_and_report.py` 靠标题字符串匹配 txt 文件名，标题含换行或页面 chrome 时可能匹配失败。
- `generate_daily_picture.py` 对 `daily-learn-*.md` 的标题格式有硬性要求。
- 正文提取目前较粗（`p/h1/h2/h3/li`），会带入导航、cookie 提示等噪声；可按域名进一步清洗。

## 扩展建议

- 将 `config/*.json` 接入你自己的数据库或 CMS，实现动态增删监控源。
- 把 `draft-template.md` 的填写步骤交给 LLM，进一步减少人工。
- 对高频失败站点增加 domain-specific 正文选择器。
