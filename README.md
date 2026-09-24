# frontier-daily-brief

**中文** | [English](#english)

智库 + 科技前沿每日扫描，自动生成报纸版式日报图片的自动化流程。
Daily scanning of think tanks & tech frontier sources, generating newspaper-style daily briefing images.

---

## 中文

一套基于 Playwright 的自动化流程：每日扫描你配置的智库与科技公司页面，筛选当日新发布的内容，登记成 CSV 与日报 markdown，最终整合生成一张报纸版式的高清 PNG 日报图。

### 功能特性

- **两条独立流水线**
  - `daily-think-tank-scan/`：智库 / 研究机构（Track A：≥8000 字研究报告；Track B：涉华评论分析）
  - `tech-learning-scan/`：科技公司研究出版物与博客（Track A：论文/报告；Track B：博客/新闻）
- **四步流程**：浅扫列表页 → 深查候选文章（核实真实发布日期、字数、涉华提及、PDF 链接）→ 保存原文 txt → CSV 登记 + 生成日报 markdown
- **报纸版式出图**：`generate_daily_picture.py` 将两份日报整合为报纸版式 HTML，再用 Playwright 截图为 1200px 高清 PNG（导读 / 智库观察 / 要闻 / 科技要闻 / 社区短讯 五个版块）
- **省 token 设计**：深查只记录元数据，登记逐篇处理，不一次性加载全部原文
- **配置驱动**：监控目标全部来自 `config/*.json`，按需增删，代码零改动

### 快速开始

```bash
pip install playwright
playwright install chromium
```

1. 按 [config/list-format.md](config/list-format.md) 的格式填写 `config/think_tank_list.json` 与 `config/tech_company_list.json`（仓库内为空白模板）
2. 运行智库流水线（`daily-think-tank-scan/`）与科技流水线（`tech-learning-scan/`）各自的四个脚本
3. 按 [draft-template.md](tech-learning-scan/Daily%20Picture/draft-template.md) 整合成稿，运行 `python scripts/generate_daily_picture.py <搜集日期>` 出图

### 目录结构

```
├── config/                     # 监控列表（空白模板）
├── daily-think-tank-scan/      # 智库流水线（scripts + assets/scans/raw-reports 输出目录）
├── tech-learning-scan/         # 科技流水线（scripts + Daily Picture 出图）
├── SKILL.md                    # 完整使用文档
└── README.md
```

Track A/B 详细定义、已知限制与扩展建议见 [SKILL.md](SKILL.md)。

---

## English

A Playwright-based automation pipeline that scans your configured think-tank and tech-company pages every day, filters content published on the target date, registers everything into CSVs and daily markdown reports, and finally composes a newspaper-style high-resolution PNG briefing.

### Features

- **Two independent pipelines**
  - `daily-think-tank-scan/`: think tanks / research institutions (Track A: research reports ≥ 8,000 words; Track B: China-related commentary)
  - `tech-learning-scan/`: tech company research publications & blogs (Track A: papers/reports; Track B: blog/news posts)
- **Four-step flow**: shallow scan of list pages → deep check of candidate articles (true publication date, word count, China mentions, PDF link) → save raw text → CSV registry + daily markdown report
- **Newspaper-style rendering**: `generate_daily_picture.py` merges both reports into a newspaper-layout HTML and screenshots it into a 1200px PNG (lead / think-tank watch / headline / tech news / community briefs)
- **Token-saving design**: deep check records metadata only; registration processes articles one by one instead of loading everything at once
- **Config-driven**: all monitored targets live in `config/*.json` — add or remove sources without touching code

### Quick Start

```bash
pip install playwright
playwright install chromium
```

1. Fill in `config/think_tank_list.json` and `config/tech_company_list.json` following [config/list-format.md](config/list-format.md) (blank templates included)
2. Run the four scripts of each pipeline (`daily-think-tank-scan/` and `tech-learning-scan/`)
3. Compose the draft following [draft-template.md](tech-learning-scan/Daily%20Picture/draft-template.md), then run `python scripts/generate_daily_picture.py <scan-date>` to render the image

### Layout

```
├── config/                     # Watch lists (blank templates)
├── daily-think-tank-scan/      # Think-tank pipeline (scripts + assets/scans/raw-reports output dirs)
├── tech-learning-scan/         # Tech pipeline (scripts + Daily Picture rendering)
├── SKILL.md                    # Full documentation
└── README.md
```

See [SKILL.md](SKILL.md) for Track A/B definitions, known limitations, and extension ideas.

> Note: the generated newspaper is in Chinese; the pipelines themselves work with any English-language source pages.
