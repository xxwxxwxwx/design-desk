#!/usr/bin/env python3
"""Validate output size and pixel preservation of every fixed template element."""

from __future__ import annotations

import argparse
from pathlib import Path
import xml.etree.ElementTree as ET

try:
    from PIL import Image
except ImportError as exc:  # pragma: no cover - environment guidance
    raise SystemExit("缺少 Pillow；请先安装 Pillow，再运行验收脚本。") from exc


SIZE = (1080, 1440)
VARIABLE_BOXES: tuple[tuple[int, int, int, int], ...] = ()


def read_variable_boxes(svg_path: Path) -> tuple[tuple[int, int, int, int], ...]:
    root = ET.parse(svg_path).getroot()
    boxes = [(0, 0, 1080, 160)]
    for slot_id in ("merchant-name-slot",):
        target = next((element for element in root.iter() if element.get("id") == slot_id), None)
        rect = None if target is None else next((child for child in target.iter() if child.tag.endswith("rect")), None)
        if rect is None:
            raise SystemExit(f"失败：SVG 缺少 {slot_id} 矩形。")
        x, y = round(float(rect.get("x", "0"))), round(float(rect.get("y", "0")))
        width, height = round(float(rect.attrib["width"])), round(float(rect.attrib["height"]))
        boxes.append((x, y, x + width, y + height))
    return tuple(boxes)


def is_variable(x: int, y: int) -> bool:
    return any(left <= x < right and top <= y < bottom for left, top, right, bottom in VARIABLE_BOXES)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--template-svg", type=Path, required=True)
    args = parser.parse_args()

    global VARIABLE_BOXES
    VARIABLE_BOXES = read_variable_boxes(args.template_svg)

    output = Image.open(args.output).convert("RGBA")
    template = Image.open(args.template).convert("RGBA")
    base = Image.open(args.base).convert("RGBA")
    if output.size != SIZE:
        raise SystemExit(f"失败：输出不是 1080×1440，而是 {output.size[0]}×{output.size[1]}")
    if template.size != SIZE:
        raise SystemExit("失败：固定模板不是 1080×1440")
    if base.size != SIZE:
        raise SystemExit("失败：底图不是 1080×1440")

    output_pixels = output.load()
    template_pixels = template.load()
    base_pixels = base.load()
    changed = 0
    for y in list(range(0, 160)) + list(range(1314, 1440)):
        for x in range(1080):
            if is_variable(x, y):
                continue
            expected = template_pixels[x, y]
            alpha = expected[3]
            if alpha:
                background = base_pixels[x, y]
                composited = tuple(
                    (expected[channel] * alpha + background[channel] * (255 - alpha) + 127) // 255
                    for channel in range(3)
                )
                actual = output_pixels[x, y][:3]
                if any(abs(actual[channel] - composited[channel]) > 1 for channel in range(3)):
                    changed += 1
    if changed:
        raise SystemExit(f"失败：有 {changed} 个固定模板像素被改变。")
    print("通过：尺寸正确，且变量区之外的固定模板像素均未改变。")


if __name__ == "__main__":
    main()
