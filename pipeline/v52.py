#!/usr/bin/env python3
"""Production v5.2 central-creative and vertical-outpaint pipeline."""
from __future__ import annotations

import json
import math
import mimetypes
import sys
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageOps, ImageStat


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import server  # noqa: E402


FINAL_SIZE = (1080, 1440)
CENTRAL_RATIO = (8, 9)
CENTRAL_API_SIZE = (1080, 1215)
CENTRAL_CROP_Y = (30, 1185)
CENTRAL_SIZE = (1080, 1155)
CENTRAL_Y = (160, 1315)
MODEL = "gpt-image-2-5-sunburst-image-to-image"
RESOLUTION = "1K"


def image_tuple(path: Path) -> tuple[str, str, bytes, str]:
    content_type = mimetypes.guess_type(path.name)[0] or "image/png"
    if content_type not in server.ALLOWED_TYPES:
        content_type = "image/png"
    return ("images", path.name, path.read_bytes(), content_type)


def build_central_prompt(fields: dict[str, str], roles: list[str]) -> str:
    fact_keys = (
        ("merchant", "merchant_name"), ("recruitment", "recruitment_type"),
        ("headline", "headline"), ("participants", "recruitment_count"),
        ("date", "event_date"), ("address", "address"),
        ("offer", "offer"), ("application_rules", "requirements"),
    )
    facts = {label: fields.get(key, "").strip() for label, key in fact_keys if fields.get(key, "").strip()}
    image_lines = "\n".join(f"- Image {i + 1}: {role.upper()}" for i, role in enumerate(roles))
    role_rules = "\n".join(server.ROLE_RULES[role] for role in dict.fromkeys(roles))
    notes = fields.get("additional_notes", "").strip()
    return f"""Create one finished Chinese Xiaohongshu merchant recruitment creative in an 8:9 portrait canvas.

This is the complete semantic creative plate for the middle of a later 3:4 poster. AI must design every creative element here: headline, real products, activity facts, information panel, typography, decoration, lighting and environmental scene. Do not add Fantuan or merchant logos; authoritative brand SVGs are added locally afterward.

CANVAS
- Output aspect ratio: exactly 8:9, opaque, full bleed.
- Compose directly for this 8:9 canvas. Do not shrink or frame another poster inside it.
- The outer 30 px at both the top and bottom are crop buffers and may contain continuous background only. Keep every semantic element outside those buffers.
- After removing those two background-only buffers, the 1080×1155 creative will be placed pixel-for-pixel at x=0–1079, y=160–1314 of a 1080×1440 final canvas. This is the exact unobstructed region between the authoritative SVG overlays.

LOCKED CAMPAIGN FACTS
{json.dumps(facts, ensure_ascii=False, indent=2)}
Preserve every supplied value and unique fact exactly. Omit absent facts and invent nothing. Do not print metadata keys, filenames, extensions or production instructions.

INPUT IMAGES
{image_lines}
{role_rules}

CREATIVE DIRECTION
- Infer one coherent visual world from the style reference and apply it to background, typography, graphics, lighting and product integration.
- Treat each PRODUCT image only as a reference for the product subject itself: its physical form, packaging, label and product-logo details. Ignore and replace any white, solid-color, photographed or designed background surrounding the product. That source-image background is not part of the product and must never overwrite, flatten, whiten, frame or otherwise control the poster's creative background.
- Preserve both real products, their packaging, labels, proportions and distinguishing details.
- Put date, full address and complete application rules together inside ONE cohesive information box at the bottom of the central creative region. It must be one unified outer panel, not separate badges, cards or floating labels.
- Inside that one panel, use exactly three vertically stacked information rows in this order: activity date, full activity address, complete application rules.
- Each row must use a compact audience-facing label on the left and its complete supplied content on the right. Keep the three left labels consistently aligned; left-align all right-side content; allow natural wrapping at semantic boundaries.
- Keep the complete outer panel, including border, glow and shadow, above the lower crop buffer and leave visible background breathing room below it. Adapt its styling to the supplied reference, but do not change this one-panel / three-row information structure.
- The image model owns the panel's visual design and typography. The program must not re-typeset, split, shorten or rearrange the activity text.
- Make the recruitment theme, headline and products legible at mobile thumbnail size.
- Leave the scene visually extendable above and below without bands, borders, inner frames or abrupt horizontal boundaries.

PRODUCTION NOTES
{json.dumps(notes, ensure_ascii=False)}

OUTPUT
One opaque 8:9 raster creative plate. No logos, mockup frame, crop marks or guides.""".strip()


def build_outpaint_prompt() -> str:
    return """Extend the supplied transparent 3:4 canvas into one finished opaque 3:4 poster background.

The existing non-transparent middle rectangle is locked artwork. Preserve every visible pixel, Chinese glyph, product, package, fact, panel, position, scale, color, lighting and sharpness in that middle rectangle. Do not redesign, translate, correct, move, resize, crop or re-render it.

Generate content only in the transparent top and bottom regions. Continue the same environmental background, materials, texture, perspective, lighting, depth, atmosphere and non-semantic decoration naturally into those regions. The extensions must be visually continuous at both horizontal joins with no seam, band, brightness step, blur strip, repeated or mirrored texture, copied edge, frame or padding appearance.

Transparency is only a placement cue for regions that need environmental continuation. It is not a request for a white, blank or transparent background. Sample the visible scene immediately beside each join and continue its actual colors and illumination. Do not render either extension as white unless the locked scene itself is genuinely white at that join.

Do not add any new title, word, number, product, package, fruit, person, badge, information card, logo, slogan or recognizable campaign element in the extended regions. Return one opaque 3:4 raster image.""".strip()


def normalize(image_bytes: bytes, target: Path, size: tuple[int, int], expected_ratio: float) -> None:
    raw = target.with_suffix(".raw.png")
    raw.write_bytes(image_bytes)
    with Image.open(raw) as image:
        image = image.convert("RGB")
        ratio = image.width / image.height
        if not math.isclose(ratio, expected_ratio, rel_tol=0.035):
            raise RuntimeError(f"GENERATED_RATIO_INVALID:{image.width}x{image.height}")
        ImageOps.fit(image, size, method=Image.Resampling.LANCZOS).save(target, "PNG", optimize=True)


def prepare_outpaint_input(central_path: Path, target: Path) -> None:
    with Image.open(central_path) as image:
        central = image.convert("RGBA")
        if central.size != CENTRAL_SIZE:
            raise RuntimeError(f"CENTRAL_SIZE_INVALID:{central.size}")
        canvas = Image.new("RGBA", FINAL_SIZE, (0, 0, 0, 0))
        canvas.alpha_composite(central, (0, CENTRAL_Y[0]))
        canvas.save(target, "PNG", optimize=True)


def crop_central_api_image(source: Path, target: Path) -> None:
    with Image.open(source) as image:
        image = image.convert("RGB")
        if image.size != CENTRAL_API_SIZE:
            raise RuntimeError(f"CENTRAL_API_SIZE_INVALID:{image.size}")
        image.crop((0, CENTRAL_CROP_Y[0], CENTRAL_API_SIZE[0], CENTRAL_CROP_Y[1])).save(
            target, "PNG", optimize=True
        )


def call(
    prompt: str,
    images: list[tuple[str, str, bytes, str]],
    token: str,
    aspect_ratio: str,
    background: str = "opaque",
) -> bytes:
    api_key = server.active_api_key()
    if not api_key:
        raise RuntimeError("KIE_API_KEY_MISSING")
    urls = [server.upload_to_kie(api_key, name, payload, content_type, token) for _, name, payload, content_type in images]
    created = server.kie_json_request(
        f"{server.KIE_API_ROOT}/api/v1/jobs/createTask", api_key, method="POST",
        payload={"model": MODEL, "input": {"prompt": prompt, "input_urls": urls,
                                              "aspect_ratio": aspect_ratio, "resolution": RESOLUTION,
                                              "background": background}},
    )
    task_id = str(created.get("data", {}).get("taskId", ""))
    if not task_id:
        raise RuntimeError("KIE_INVALID_RESPONSE:没有返回 taskId。")
    deadline, delay = time.monotonic() + 360, 2.0
    while time.monotonic() < deadline:
        time.sleep(delay)
        status = server.kie_json_request(f"{server.KIE_API_ROOT}/api/v1/jobs/recordInfo?taskId={task_id}", api_key)
        data = status.get("data", {})
        if data.get("state") == "fail":
            raise RuntimeError(f"KIE_GENERATION_FAILED:{data.get('failMsg') or data.get('failCode') or '生成失败。'}")
        if data.get("state") == "success":
            result = json.loads(data.get("resultJson") or "{}")
            url = result["resultUrls"][0]
            import urllib.request
            with urllib.request.urlopen(url, timeout=120) as response:
                return response.read()
        delay = min(delay * 1.35, 8.0)
    raise RuntimeError("KIE_TIMEOUT:生成超过 6 分钟。")


def mean_abs_difference(left: Image.Image, right: Image.Image) -> float:
    diff = ImageChops.difference(left.convert("RGB"), right.convert("RGB"))
    return sum(ImageStat.Stat(diff).mean) / (3 * 255)


def seam_score(image: Image.Image, y: int) -> float:
    rgb = image.convert("RGB")
    row_a = rgb.crop((0, y - 1, rgb.width, y))
    row_b = rgb.crop((0, y, rgb.width, y + 1))
    return mean_abs_difference(row_a, row_b)


def metrics(central_path: Path, b_base: Path) -> dict[str, Any]:
    with Image.open(central_path) as central, Image.open(b_base) as b_image:
        middle = b_image.crop((0, CENTRAL_Y[0], FINAL_SIZE[0], CENTRAL_Y[1]))
        return {
            "central_pixel_change_ratio": round(mean_abs_difference(central, middle), 6),
            "top_join_row_difference": round(seam_score(b_image, CENTRAL_Y[0]), 6),
            "bottom_join_row_difference": round(seam_score(b_image, CENTRAL_Y[1]), 6),
            "interpretation": "Mechanical proxy only; visual continuity and Chinese copy still require human review.",
        }


