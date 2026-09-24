# frontier-daily-brief

智库 + 科技前沿每日扫描，并生成报纸版式日报图片的自动化流程。

- **两条流水线**：`daily-think-tank-scan/`（智库/研究机构）与 `tech-learning-scan/`（科技公司研究出版物与博客）
- **四步流程**：浅扫列表页 → 深查候选文章（真实发布日期 / 字数 / 涉华提及）→ 保存原文 txt → CSV 登记 + 日报 markdown
- **出图**：`generate_daily_picture.py` 把两份日报整合成报纸版式 HTML，再用 Playwright 截图为 1200px 高清 PNG
- **省 token 设计**：深查只记录元数据，登记逐篇处理，不一次性加载全部原文

## 快速开始

```bash
pip install playwright
playwright install chromium
```

1. 按 `config/list-format.md` 填写 `config/think_tank_list.json` 与 `config/tech_company_list.json`
2. 分别运行两条流水线的四个脚本（详见 [SKILL.md](SKILL.md)）
3. 按 `tech-learning-scan/Daily Picture/draft-template.md` 整合成稿，运行 `generate_daily_picture.py <搜集日期>` 出图

完整目录结构、Track A/B 定义、已知限制与扩展建议见 [SKILL.md](SKILL.md)。
