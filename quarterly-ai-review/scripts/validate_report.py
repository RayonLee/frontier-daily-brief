#!/usr/bin/env python3
"""校验季度报告的连续引用、公开链接、PDF 字体与文本完整性。"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

CITATION = re.compile(r"\[\^(\d+)\^\]")
REFERENCE_HEADING = re.compile(r"^#{1,6}\s+参考资料\s*$", re.M)
REFERENCE_ENTRY = re.compile(r"^\s*\[(\d+)\]\s+", re.M)
CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
REQUIRED_FONT_FRAGMENTS = [
    "SimHei",
    "KaiTi",
    "KaiTi-Bold",
    "SimSun",
    "SimSun-Bold",
    "TimesNewRomanPSMT",
    "TimesNewRomanPS-BoldMT",
]


def unique_in_order(values: list[int]) -> list[int]:
    return list(dict.fromkeys(values))


def expected_numbers(count: int) -> list[int]:
    return list(range(1, count + 1))


def split_references(text: str) -> tuple[str, str | None]:
    match = REFERENCE_HEADING.search(text)
    if not match:
        return text, None
    return text[:match.start()], text[match.end():]


def entry_chunks(reference_text: str) -> list[tuple[int, str]]:
    matches = list(REFERENCE_ENTRY.finditer(reference_text))
    chunks = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(reference_text)
        chunks.append((int(match.group(1)), reference_text[match.end():end]))
    return chunks


def validate_markdown(path: Path, min_cjk: int, max_cjk: int, checks: list[dict]) -> dict:
    text = re.sub(r"<!--.*?-->", "", path.read_text(encoding="utf-8-sig"), flags=re.S)
    cjk_count = len(CJK.findall(text))
    checks.append({
        "name": "Markdown 汉字数",
        "passed": min_cjk <= cjk_count <= max_cjk,
        "detail": f"{cjk_count} 汉字，目标区间 {min_cjk}—{max_cjk}",
    })
    checks.append({
        "name": "无尾部附录",
        "passed": not re.search(r"^#{1,6}\s+附录(?:\s|$)", text, re.M),
        "detail": "默认不以附录替代参考资料",
    })

    body, references = split_references(text)
    citation_ids = [int(value) for value in CITATION.findall(body)]
    unique_citations = unique_in_order(citation_ids)
    expected = expected_numbers(len(unique_citations))
    checks.append({
        "name": "正文首次引用连续编号",
        "passed": unique_citations == expected,
        "detail": f"{len(citation_ids)} 处引用，{len(unique_citations)} 个独立来源",
    })
    checks.append({
        "name": "存在参考资料",
        "passed": references is not None,
        "detail": "应有“参考资料”章节",
    })
    if references is None:
        return {"citation_occurrences": len(citation_ids), "unique_sources": len(unique_citations)}

    chunks = entry_chunks(references)
    reference_ids = [number for number, _ in chunks]
    checks.append({
        "name": "参考资料只含实际引用且连续",
        "passed": reference_ids == expected,
        "detail": f"{len(reference_ids)} 条，应与 {len(unique_citations)} 个独立来源一致",
    })
    chunks_without_https = [number for number, chunk in chunks if not re.search(r"https://[^\s<]+", chunk)]
    checks.append({
        "name": "每条参考资料均有 HTTPS 链接",
        "passed": not chunks_without_https,
        "detail": "缺失编号：" + (", ".join(map(str, chunks_without_https)) or "无"),
    })
    forbidden = re.findall(r"file://|本地存档|编列说明|[A-Za-z]:[\\/]Users[\\/]", references)
    checks.append({
        "name": "参考资料无本地路径与编列说明",
        "passed": not forbidden,
        "detail": "不得出现 file://、本地存档、编列说明或本机用户路径",
    })
    return {
        "citation_occurrences": len(citation_ids),
        "unique_sources": len(unique_citations),
        "reference_entries": len(reference_ids),
        "cjk_count": cjk_count,
    }


def validate_pdf(path: Path, checks: list[dict]) -> dict:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("校验 PDF 需要安装 pypdf") from exc

    reader = PdfReader(str(path))
    texts = [page.extract_text() or "" for page in reader.pages]
    checks.append({
        "name": "PDF 无空白文本页",
        "passed": bool(texts) and all(text.strip() for text in texts),
        "detail": f"{len(texts)} 页",
    })
    reference_pages = [index for index, text in enumerate(texts) if re.search(r"^参考资料\s*$", text, re.M)]
    checks.append({
        "name": "PDF 存在参考资料",
        "passed": bool(reference_pages),
        "detail": "未找到独立的参考资料标题" if not reference_pages else "已找到",
    })
    if not reference_pages:
        return {"pages": len(texts)}

    start = max(reference_pages)
    body_text = "\n".join(texts[:start])
    reference_text = "\n".join(texts[start:])
    citation_ids = [int(value) for value in re.findall(r"\[(\d+)\]", body_text)]
    unique_citations = unique_in_order(citation_ids)
    reference_ids = [number for number, _ in entry_chunks(reference_text)]
    count = len(reference_ids)
    expected = expected_numbers(count)
    checks.append({
        "name": "PDF 正文首次引用连续",
        "passed": unique_citations == expected,
        "detail": f"{len(citation_ids)} 处引用，{len(unique_citations)} 个独立来源",
    })
    checks.append({
        "name": "PDF 参考资料连续编号",
        "passed": reference_ids == expected and count == len(unique_citations),
        "detail": f"{count} 条参考资料",
    })
    checks.append({
        "name": "PDF 无本地存档与编列说明",
        "passed": "本地存档" not in reference_text and "编列说明" not in reference_text and "file://" not in reference_text,
        "detail": "最终参考资料仅使用公开链接",
    })

    uris = []
    fonts = set()
    for page in reader.pages:
        resources = page.get("/Resources", {})
        for font in (resources.get("/Font", {}) or {}).values():
            fonts.add(str(font.get_object().get("/BaseFont")))
        for annotation_ref in page.get("/Annots") or []:
            annotation = annotation_ref.get_object()
            action = annotation.get("/A") or {}
            if action.get("/URI"):
                uris.append(str(action["/URI"]))
    unique_uris = set(uris)
    checks.append({
        "name": "PDF 公开来源链接完整",
        "passed": len(unique_uris) == count and all(url.startswith("https://") for url in unique_uris),
        "detail": f"{len(unique_uris)} 个不同来源链接，{len(uris)} 个链接标注（含跨行）",
    })
    missing_fonts = [fragment for fragment in REQUIRED_FONT_FRAGMENTS if not any(fragment in font for font in fonts)]
    checks.append({
        "name": "PDF 指定字体及粗体嵌入",
        "passed": not missing_fonts,
        "detail": "缺失：" + (", ".join(missing_fonts) or "无"),
    })
    return {
        "pages": len(texts),
        "citation_occurrences": len(citation_ids),
        "unique_sources": len(unique_citations),
        "reference_entries": count,
        "unique_urls": len(unique_uris),
        "fonts": sorted(fonts),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--markdown", type=Path, help="重编后的 Markdown 成品")
    parser.add_argument("--pdf", type=Path, help="PDF 成品")
    parser.add_argument("--json-out", type=Path, help="校验结果 JSON")
    parser.add_argument("--min-cjk", type=int, default=45000)
    parser.add_argument("--max-cjk", type=int, default=55000)
    args = parser.parse_args()
    if not args.markdown and not args.pdf:
        parser.error("至少提供 --markdown 或 --pdf")

    checks: list[dict] = []
    metrics = {}
    if args.markdown:
        metrics["markdown"] = validate_markdown(args.markdown, args.min_cjk, args.max_cjk, checks)
    if args.pdf:
        metrics["pdf"] = validate_pdf(args.pdf, checks)

    failed = [check for check in checks if not check["passed"]]
    result = {
        "status": "PASSED" if not failed else "FAILED",
        "checks": checks,
        "metrics": metrics,
    }
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    print(payload)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(payload + "\n", encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
