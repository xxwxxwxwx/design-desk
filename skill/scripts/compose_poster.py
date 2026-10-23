#!/usr/bin/env python3
"""Compose a merchant poster without redrawing any fixed Fantuan element."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional
import xml.etree.ElementTree as ET

try:
    from PIL import Image, ImageDraw, ImageFont, ImageOps
except ImportError as exc:  # pragma: no cover - environment guidance
    raise SystemExit("缺少 Pillow；请先安装 Pillow，再运行合成脚本。") from exc


SIZE = (1080, 1440)
NAME_BACKGROUND = (20, 193, 193, 255)
HEADER_CLEAR_HEIGHT = 160
HEADER_PANEL_HEIGHT = 148
HEADER_RADIUS = 36
HEADER_PADDING_X = 42
HEADER_CONTENT_GAP = 20
MERCHANT_LOGO_MAX_WIDTH = 260
MERCHANT_LOGO_MAX_HEIGHT = 64
FANTUAN_LOCKUP = Path(__file__).resolve().parents[1] / "assets" / "fantuan-lockup-transparent.png"
PREVIEW_FONT = Path("/System/Library/Fonts/PingFang.ttc")
PREVIEW_FONT_INDEX = 8
NAME_FONT_SIZE = 32
NAME_MIN_FONT_SIZE = 24
BUNDLED_FONT = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "AlimamaFangYuanTiVF-Thin-2.ttf"


def fitted_name_font(
    name: str,
    draw: ImageDraw.ImageDraw,
    text_box: tuple[int, int, int, int],
    font_path: Path,
    font_index: int,
    font_variation: Optional[str],
) -> ImageFont.FreeTypeFont:
    max_width = text_box[2] - text_box[0]
    max_height = text_box[3] - text_box[1]
    for size in range(NAME_FONT_SIZE, NAME_MIN_FONT_SIZE - 1, -1):
        font = ImageFont.truetype(str(font_path), size, index=font_index)
        if font_variation:
            try:
                font.set_variation_by_name(font_variation)
            except (AttributeError, OSError, ValueError) as exc:
                raise ValueError(f"字体不支持已确认字重 {font_variation!r}：{font_path}") from exc
        left, top, right, bottom = draw.textbbox((0, 0), name, font=font)
        if right - left <= max_width and bottom - top <= max_height:
            return font
    raise ValueError(
        "商家名称即使缩小至 24 px 仍无法在底部品牌信息条中单行完整显示，请缩短商家名称。"
    )


def validate_merchant_name_layout(
    name: str,
    template_svg_path: Path,
    font_path: Path,
    font_index: int = 0,
    font_variation: Optional[str] = None,
) -> int:
    """使用正式字体和 SVG 槽位预检商家名称，返回最大可用字号。"""
    normalized = name.strip()
    if not normalized:
        raise ValueError("商家名称不能为空。")
    if len(normalized) > 10:
        raise ValueError("商家名称最多填写 10 个 Unicode 字符。")
    draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    text_box = slot_box(template_svg_path, "merchant-name-slot")
    return fitted_name_font(
        normalized, draw, text_box, font_path, font_index, font_variation
    ).size


def slot_box(svg_path: Path, slot_id: str) -> tuple[int, int, int, int]:
    root = ET.parse(svg_path).getroot()
    target = next((element for element in root.iter() if element.get("id") == slot_id), None)
    if target is None:
        raise ValueError(f"SVG 缺少动态区域 {slot_id!r}。")
    rect = target if target.tag.endswith("rect") else next((child for child in target.iter() if child.tag.endswith("rect")), None)
    if rect is None:
        raise ValueError(f"SVG 动态区域 {slot_id!r} 内没有 rect。")
    try:
        x = round(float(rect.get("x", "0")))
        y = round(float(rect.get("y", "0")))
        width = round(float(rect.attrib["width"]))
        height = round(float(rect.attrib["height"]))
    except (KeyError, ValueError) as exc:
        raise ValueError(f"SVG 动态区域 {slot_id!r} 坐标无效。") from exc
    return (x, y, x + width, y + height)


def validate_template(overlay: Image.Image) -> None:
    if overlay.size != SIZE:
        raise ValueError(f"固定模板必须是 1080×1440，实际为 {overlay.size[0]}×{overlay.size[1]}")
    if overlay.getchannel("A").crop((0, 160, 1080, 1314)).getbbox() is not None:
        raise ValueError("固定模板的中区不是全透明，不能安全叠加。")


def crop_logo_artwork(logo: Image.Image) -> Image.Image:
    """裁掉透明边和纯白画布边，不改变 Logo 内部的白色。"""
    alpha_bounds = logo.getchannel("A").getbbox()
    if alpha_bounds is None:
        raise ValueError("商家 Logo 全透明。")
    logo = logo.crop(alpha_bounds)

    # 很多商家上传的是带大块白边的 JPG/PNG。白色与面板同色，
    # 只裁四周近白区域；彩色底、深色底和 Logo 内部留白保持原样。
    rgba = logo.load()
    corners = [
        rgba[0, 0],
        rgba[logo.width - 1, 0],
        rgba[0, logo.height - 1],
        rgba[logo.width - 1, logo.height - 1],
    ]
    near_white_corners = sum(1 for r, g, b, a in corners if a >= 250 and min(r, g, b) >= 245)
    if near_white_corners >= 3:
        mask = Image.new("L", logo.size, 0)
        mask_pixels = mask.load()
        for y in range(logo.height):
            for x in range(logo.width):
                r, g, b, a = rgba[x, y]
                if a > 8 and min(r, g, b) < 242:
                    mask_pixels[x, y] = 255
        content_bounds = mask.getbbox()
        if content_bounds is not None:
            logo = logo.crop(content_bounds)
    return logo


def merchant_logo_box(logo: Image.Image) -> tuple[int, int]:
    """按宽高比约束视觉份量：窄 Logo 不与饭团主标等高，超宽 Logo 不无限拉长面板。"""
    aspect = logo.width / logo.height
    if aspect < 0.85:
        return (58, MERCHANT_LOGO_MAX_HEIGHT)
    if aspect < 1.4:
        return (72, MERCHANT_LOGO_MAX_HEIGHT)
    if aspect > 4.0:
        return (MERCHANT_LOGO_MAX_WIDTH, 52)
    return (MERCHANT_LOGO_MAX_WIDTH, 60)


def compose(
    base_path: Path,
    logo_path: Optional[Path],
    merchant_name: str,
    template_path: Path,
    template_svg_path: Path,
    output_path: Path,
    font_path: Path,
    font_index: int,
    font_variation: Optional[str],
) -> None:
    if not merchant_name.strip():
        raise ValueError("商家名称不能为空。")
    resolved_inputs = {base_path.resolve(), template_path.resolve(), template_svg_path.resolve(), font_path.resolve()}
    if logo_path is not None:
        resolved_inputs.add(logo_path.resolve())
    if output_path.resolve() in resolved_inputs:
        raise ValueError("输出文件不得覆盖任何输入文件。")

    base = Image.open(base_path).convert("RGBA")
    if base.size != SIZE:
        raise ValueError(f"商家原图必须是 1080×1440，实际为 {base.size[0]}×{base.size[1]}")

    overlay = Image.open(template_path).convert("RGBA")
    validate_template(overlay)
    name_text_box = slot_box(template_svg_path, "merchant-name-slot")
    draw = ImageDraw.Draw(overlay)
    if logo_path is not None:
        if not FANTUAN_LOCKUP.is_file():
            raise ValueError(f"缺少饭团顶部矢量派生资源：{FANTUAN_LOCKUP}")
        draw.rectangle((0, 0, SIZE[0], HEADER_CLEAR_HEIGHT), fill=(0, 0, 0, 0))
    # SVG rect 的右、下边界为排他终点；Pillow rectangle 的终点则会被绘制。
    # 减 1 保证动态底色不会多覆盖固定模板边界像素。
    draw.rectangle(
        (name_text_box[0], name_text_box[1], name_text_box[2] - 1, name_text_box[3] - 1),
        fill=NAME_BACKGROUND,
    )

    if logo_path is not None:
        logo = crop_logo_artwork(Image.open(logo_path).convert("RGBA"))
        logo = ImageOps.contain(
            logo,
            merchant_logo_box(logo),
            Image.Resampling.LANCZOS,
        )
        lockup = Image.open(FANTUAN_LOCKUP).convert("RGBA")
        panel_width = HEADER_PADDING_X * 2 + lockup.width + HEADER_CONTENT_GAP + logo.width
        panel_left = (SIZE[0] - panel_width) // 2
        panel_right = panel_left + panel_width
        draw.rounded_rectangle(
            (panel_left, -HEADER_RADIUS, panel_right, HEADER_PANEL_HEIGHT),
            radius=HEADER_RADIUS,
            fill=(255, 255, 255, 255),
        )
        lockup_x = panel_left + HEADER_PADDING_X
        lockup_y = (HEADER_PANEL_HEIGHT - lockup.height) // 2
        overlay.alpha_composite(lockup, (lockup_x, lockup_y))
        logo_x = lockup_x + lockup.width + HEADER_CONTENT_GAP
        logo_y = (HEADER_PANEL_HEIGHT - logo.height) // 2
        overlay.alpha_composite(logo, (logo_x, logo_y))

    name = merchant_name.strip()
    font = fitted_name_font(name, draw, name_text_box, font_path, font_index, font_variation)
    left, top, right, bottom = draw.textbbox((0, 0), name, font=font)
    text_width, text_height = right - left, bottom - top
    x = name_text_box[0] + (name_text_box[2] - name_text_box[0] - text_width) / 2 - left
    y = name_text_box[1] + (name_text_box[3] - name_text_box[1] - text_height) / 2 - top
    draw.text((round(x), round(y)), name, font=font, fill=(255, 255, 255, 255))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.alpha_composite(base, overlay).convert("RGB").save(output_path, format="PNG", optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--logo", type=Path)
    parser.add_argument("--name", required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--template-svg", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--font-file", type=Path)
    parser.add_argument("--font-index", type=int, default=0)
    parser.add_argument("--font-variation")
    parser.add_argument("--preview-use-system-pingfang", action="store_true")
    args = parser.parse_args()

    if args.font_file is None:
        if BUNDLED_FONT.is_file() and not args.preview_use_system_pingfang:
            args.font_file = BUNDLED_FONT
            args.font_index = 0
            args.font_variation = args.font_variation or "SemiBold"
        elif not args.preview_use_system_pingfang:
            raise SystemExit(
                "缺少随 Skill 提供的已确认字体。为避免改变字体，正式合成必须提供 --font-file；"
                "只有预览可使用 --preview-use-system-pingfang。"
            )
        else:
            args.font_file = PREVIEW_FONT
            args.font_index = PREVIEW_FONT_INDEX
            args.font_variation = None

    compose(
        base_path=args.base,
        logo_path=args.logo,
        merchant_name=args.name,
        template_path=args.template,
        template_svg_path=args.template_svg,
        output_path=args.output,
        font_path=args.font_file,
        font_index=args.font_index,
        font_variation=args.font_variation,
    )
    suffix = "（仅预览，字体尚未获确认）" if args.preview_use_system_pingfang else ""
    print(f"已生成 1080×1440 PNG：{args.output}{suffix}")


if __name__ == "__main__":
    main()
