"""smartart2md — OOXML SmartArt 다이어그램을 Markdown 리스트로 변환하는 패키지.

일반적인 사용:

    from smartart2md import convert_smartart, load_smartart_parts

    for root, ctx in load_smartart_parts("presentation.pptx"):
        md_text, images = convert_smartart(root, ctx)
        print(md_text)
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from typing import Optional

from .smartart2md import convert_smartart, load_smartart_parts
from .ooxml_context import ZipContext, iter_parts_matching

def main() -> None:
    """CLI 진입점 — smartart2md [options] input."""
    parser = argparse.ArgumentParser(description="Convert OOXML SmartArt to Markdown.")
    parser.add_argument('input', help="Input file (.xml, .pptx, .xlsx, .docx)")
    parser.add_argument('-o', '--output', help="Output file (default: stdout)")
    args = parser.parse_args()

    contexts = load_smartart_parts(args.input)
    if not contexts:
        print("No SmartArt data found.", file=sys.stderr)
        sys.exit(1)

    parts = []
    for root, ctx in contexts:
        md, _imgs = convert_smartart(root, ctx)
        parts.append(md)

    # 공유 ZipFile 닫기
    seen_zf: set[int] = set()
    for _, ctx in contexts:
        if ctx is not None and id(ctx.zf) not in seen_zf:
            seen_zf.add(id(ctx.zf))
            try:
                ctx.zf.close()
            except Exception:
                pass

    output = "\n---\n\n".join(parts)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output)
    else:
        print(output, end='')

__all__ = [
    # CLI 진입점
    "main",
    # 통합 entry point
    "convert_smartart",
    "load_smartart_parts",
    # 기타 유틸리티
    "ZipContext",
    "iter_parts_matching",
]
