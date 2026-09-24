# 列表配置格式

把你要监控的网页填入对应 JSON，然后运行扫描脚本。

## think_tank_list.json

```json
{
  "institutions": [
    {
      "name": "示例智库",
      "urls": [
        "https://example.org/research"
      ],
      "tier": 1,
      "priority": "★★★"
    }
  ]
}
```

- `name`：机构名，会进入日报与登记 CSV。
- `urls`：该机构需要每日扫描的列表页地址。
- `tier`/`priority`：仅用于展示，不影响流程。

## tech_company_list.json

```json
{
  "companies": [
    {
      "name": "示例公司",
      "urls": [
        "https://example.com/blog/"
      ],
      "track_hint": {
        "example.com/research": "A",
        "example.com/blog": "B"
      }
    }
  ],
  "always_check_urls": []
}
```

- `track_hint`：URL 片段到 Track A/B 的映射，用于区分论文/博客。
- `always_check_urls`：无日期但需无条件深查前 N 条的列表页。
