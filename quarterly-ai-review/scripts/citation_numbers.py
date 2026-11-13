#!/usr/bin/env python3
"""按首次出现顺序重编 [^id^] 引用；重复来源沿用首次编号。"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

MARKER = re.compile(r"\[\^(\d+)\^\]")


def build_mapping(text: str) -> tuple[list[int], dict[int, int]]:
    source_ids = [int(value) for value in MARKER.findall(text)]
    order = list(dict.fromkeys(source_ids))
    return source_ids, {source_id: index for index, source_id in enumerate(order, 1)}


def remap(text: str, number_map: dict[int, int]) -> str:
    return MARKER.sub(lambda match: f"[^{number_map[int(match.group(1))]}^]", text)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("markdown", type=Path, help="包含 [^id^] 标记的 Markdown 文件")
    parser.add_argument("--map-out", type=Path, help="输出引用号与原始档案编号映射 JSON")
    parser.add_argument("--remapped-out", type=Path, help="输出重编后的 Markdown，不覆盖原文件")
    args = parser.parse_args()

    text = args.markdown.read_text(encoding="utf-8-sig")
    source_ids, number_map = build_mapping(text)
    if not number_map:
        parser.error("未发现 [^id^] 引用标记")

    records = [
        {"citation_number": number, "source_id": source_id}
        for source_id, number in sorted(number_map.items(), key=lambda item: item[1])
    ]
    if args.map_out:
        write_json(args.map_out, records)
    if args.remapped_out:
        args.remapped_out.parent.mkdir(parents=True, exist_ok=True)
        args.remapped_out.write_text(remap(text, number_map), encoding="utf-8")

    result = {
        "status": "PASSED",
        "citation_occurrences": len(source_ids),
        "unique_sources": len(number_map),
        "first_citation_source_id": records[0]["source_id"],
        "last_citation_number": records[-1]["citation_number"],
        "map_out": str(args.map_out) if args.map_out else None,
        "remapped_out": str(args.remapped_out) if args.remapped_out else None,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
