"""smartart2md — OOXML SmartArt 다이어그램을 Markdown 리스트로 변환하는 패키지.

일반적인 사용:

    from smartart2md import convert_smartart, load_smartart_parts

    for root, ctx in load_smartart_parts("presentation.pptx"):
        md_text, images = convert_smartart(root, ctx)
        print(md_text)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

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

    parts_md: list[str] = []
    global_images: list[tuple[bytes, str]] = []

    for root, ctx in contexts:
        md, images = convert_smartart(root, ctx)
        for local_idx, img in enumerate(images):
            global_idx = len(global_images)
            global_images.append(img)
            md = md.replace(f"@@IMG:{local_idx}@@", f"@@GIMG:{global_idx}@@")
        parts_md.append(md)

    # 공유 ZipFile 닫기
    seen_zf: set[int] = set()
    for _, ctx in contexts:
        if ctx is not None and id(ctx.zf) not in seen_zf:
            seen_zf.add(id(ctx.zf))
            try:
                ctx.zf.close()
            except Exception:
                pass

    if args.output and global_images:
        out_path = Path(args.output)
        assets_dir = out_path.parent / (out_path.stem + "_assets")
        assets_dir.mkdir(exist_ok=True)
        for i, (data, ext) in enumerate(global_images):
            (assets_dir / f"img{i}.{ext}").write_bytes(data)
        parts_md = [
            re.sub(
                r"@@GIMG:(\d+)@@",
                lambda m: f"![image]({assets_dir.name}/img{m.group(1)}.{global_images[int(m.group(1))][1]})",
                md,
            )
            for md in parts_md
        ]
    else:
        parts_md = [re.sub(r"@@GIMG:\d+@@", "", md) for md in parts_md]

    output = "\n---\n\n".join(parts_md)
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
    else:
        print(output, end="")

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
