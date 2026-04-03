"""smartart2md 사용 예제 — samples/smartArt.pptx를 Markdown으로 변환."""

import pathlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from smartart2md import convert_smartart, load_smartart_parts

SAMPLE = pathlib.Path(__file__).parent / "smartArt.pptx"
OUTPUT = pathlib.Path(__file__).parent / "smartart2md_example_output.md"
ASSETS = pathlib.Path(__file__).parent / "smartart2md_example_assets"


def main():
    parts = load_smartart_parts(str(SAMPLE))
    print(f"SmartArt 파트 수: {len(parts)}")

    sections = []
    for i, (root, ctx) in enumerate(parts, 1):
        md, images = convert_smartart(root, ctx)

        # 이미지 저장
        for j, (img_bytes, ext) in enumerate(images):
            ASSETS.mkdir(exist_ok=True)
            img_path = ASSETS / f"part{i}_img{j}.{ext}"
            img_path.write_bytes(img_bytes)
            md = md.replace(f"@@IMG:{j}@@", f"![image]({img_path.relative_to(OUTPUT.parent)})")
            print(f"  이미지 저장: {img_path}")

        sections.append(f"## Part {i}\n\n{md}")
        print(f"Part {i}:\n{md}\n")

    OUTPUT.write_text("\n\n---\n\n".join(sections), encoding="utf-8")
    print(f"\n출력 파일: {OUTPUT}")


if __name__ == "__main__":
    main()
