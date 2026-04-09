# smartart2md

Convert OOXML SmartArt diagrams to Markdown lists. Supports `.pptx`, `.xlsx`, and `.docx` files with no external dependencies.

## Installation

```bash
pip install smartart2md
```

## Quick Start

```python
from smartart2md import convert_smartart, load_smartart_parts

for root, ctx in load_smartart_parts("presentation.pptx"):
    md, images = convert_smartart(root, ctx)
    print(md)
```

Output:

```markdown
- Root item
  - Child item
  - Child item
- Root item
  - Child item
```

## CLI

```bash
smartart2md input.pptx                  # print all SmartArt to stdout
smartart2md input.pptx -o output.md     # save to file
smartart2md diagram.xml                 # parse a dataModel XML directly
```

## API

### `load_smartart_parts(path)`

Scans an OOXML file and returns a list of `(root, ctx)` pairs, one per
SmartArt diagram. `root` is an `ET.Element` (the `dgm:dataModel` XML root)
and `ctx` is a `ZipContext` that the converter uses to access embedded images.

For `.pptx` files, slide order is preserved. For `.xlsx` and `.docx`, diagrams
are returned in filename sort order.

```python
from smartart2md import load_smartart_parts, convert_smartart

for root, ctx in load_smartart_parts("presentation.pptx"):
    md, images = convert_smartart(root, ctx)
    print(md)
```

### `convert_smartart(root, ctx)`

Converts a SmartArt `dgm:dataModel` XML root element to a Markdown list.

| Parameter | Type | Description |
|-----------|------|-------------|
| `root` | `ET.Element` | `dgm:dataModel` root returned by `load_smartart_parts` or resolved from a slide |
| `ctx` | `ZipContext \| None` | Context object for the archive. Pass `None` to skip image extraction |

Returns a `(markdown_str, images)` tuple:

- `markdown_str` — indented bullet list reflecting the diagram hierarchy
- `images` — list of `(bytes, ext)` tuples for images embedded in diagram nodes. Their positions in the Markdown string are marked with `@@IMG:0@@`, `@@IMG:1@@`, etc.

### `ZipContext`

OOXML files (`.pptx`, `.xlsx`, `.docx`) are ZIP archives that contain many
XML files inside. `ZipContext` pairs an open `zipfile.ZipFile` with the path
of a specific XML file within the archive, so the converter can extract
images embedded in SmartArt nodes.

When you use `load_smartart_parts()`, `ZipContext` objects are created and
returned automatically. You only need to construct one manually when building
a custom pipeline (see below).

```python
import zipfile
from smartart2md import ZipContext

zf = zipfile.ZipFile("presentation.pptx")
ctx = ZipContext(zf, "ppt/diagrams/data1.xml")
```

## Advanced: Full Pipeline Integration

`load_smartart_parts()` is convenient but returns diagrams without slide
context. When you need to convert an entire PPTX in slide order, iterate
the slides manually:

```python
import posixpath
import zipfile
import xml.etree.ElementTree as ET
from smartart2md import convert_smartart, ZipContext

PML_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
DML_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _read_rels(zf, xml_path):
    """Read the .rels file for a given XML part and return {rId: resolved_path}."""
    directory = posixpath.dirname(xml_path)
    filename = posixpath.basename(xml_path)
    rels_path = posixpath.join(directory, "_rels", filename + ".rels")
    result = {}
    try:
        for rel in ET.fromstring(zf.read(rels_path)):
            tag = rel.tag.split("}")[-1] if "}" in rel.tag else rel.tag
            if tag != "Relationship":
                continue
            rid = rel.get("Id", "")
            target = rel.get("Target", "")
            if rel.get("TargetMode") == "External" or not rid:
                continue
            if target.startswith("/"):
                resolved = target.lstrip("/")
            else:
                resolved = posixpath.normpath(
                    posixpath.join(directory, target)
                ).lstrip("/")
            result[rid] = resolved
    except KeyError:
        pass
    return result


with zipfile.ZipFile("presentation.pptx") as zf:
    # 1. Read slide order from presentation.xml
    prs = ET.fromstring(zf.read("ppt/presentation.xml"))
    prs_rels = _read_rels(zf, "ppt/presentation.xml")

    for sld_id_el in prs.findall(f".//{{{PML_NS}}}sldIdLst/{{{PML_NS}}}sldId"):
        rid = sld_id_el.get(f"{{{REL_NS}}}id")
        slide_path = prs_rels.get(rid or "")
        if not slide_path:
            continue

        slide = ET.fromstring(zf.read(slide_path))
        slide_rels = _read_rels(zf, slide_path)

        # 2. Find graphicFrame shapes that contain SmartArt
        for gf in slide.iter():
            if gf.tag.split("}")[-1] != "graphicFrame":
                continue

            graphic = gf.find(f".//{{{DML_NS}}}graphic")
            if graphic is None:
                continue
            graphic_data = graphic.find(f"{{{DML_NS}}}graphicData")
            if graphic_data is None:
                continue

            # 3. SmartArt is identified by "diagram" or "smartArt" in the uri
            uri = graphic_data.get("uri", "")
            if "diagram" not in uri and "smartArt" not in uri.lower():
                continue

            # 4. Find dgm:relIds element and extract the r:dm attribute
            #    r:dm points to the dataModel file that contains the diagram content
            dm_rid = None
            for child in graphic_data.iter():
                if child.tag.split("}")[-1] == "relIds":
                    for attr, val in child.attrib.items():
                        if attr.endswith("}dm"):
                            dm_rid = val
                            break
                    if dm_rid:
                        break
            if not dm_rid:
                continue

            # 5. Resolve the dataModel file path and convert
            data_path = slide_rels.get(dm_rid)
            if not data_path:
                continue

            data_root = ET.fromstring(zf.read(data_path))
            ctx = ZipContext(zf, data_path)
            md, images = convert_smartart(data_root, ctx)
            print(md)
```

## Supported Input Formats

- **`.pptx`, `.xlsx`, `.docx`** — automatically scans for SmartArt data XML inside the archive
- **`.xml`** — parsed directly as a `dgm:dataModel` root

## License

Apache 2.0 — Copyright 2026 INSEONG LEE
