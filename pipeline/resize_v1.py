#!/usr/bin/env python3
"""Resize V1: deterministic source placement plus background-only outpainting."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageOps

PROMPT_VERSION = "2026-10-30-resize-pixel-authority-v1"
SINGLE_CALL_PROMPT_VERSION = "2026-10-30-resize-single-call-safe-buffer-v2"
TWO_STAGE_PROMPT_VERSION = "2026-11-04-resize-layout-adaptation-8x9-internal-inventory-v1"
FINAL_SIZE = (1080, 1440)
SAFE_BOX = (0, 160, 1080, 1315)
# Read from the authoritative 1080x1440 SVG templates. The buffer is deliberately
# stricter than the visible overlay bounds because generated objects and glyphs
# often extend beyond the coordinates requested in prose.
TOP_OVERLAY_END = 160
BOTTOM_OVERLAY_START = 1315
TOP_SEMANTIC_BUFFER = 48
BOTTOM_SEMANTIC_BUFFER = 64
SEMANTIC_SAFE_BOX = (
    0,
    TOP_OVERLAY_END + TOP_SEMANTIC_BUFFER,
    1080,
    BOTTOM_OVERLAY_START - BOTTOM_SEMANTIC_BUFFER,
)
NEAR_WHITE = 248
WHITE_ANOMALY_THRESHOLD = 0.85
SOURCE_WHITE_EVIDENCE_THRESHOLD = 0.15


def build_layout_adaptation_prompt(source_width: int, source_height: int) -> str:
    """Build the Resize-only first-stage prompt for a real 8:9 layout adaptation."""
    source_ratio = source_width / source_height
    ratio_note = (
        "The source is substantially narrower than 8:9. Use the added width to redistribute existing groups "
        "and improve spacing while preserving their hierarchy."
        if source_ratio < 0.72
        else
        "The source is already relatively close to 8:9. Make only the spacing and position changes required "
        "for a balanced 8:9 composition."
    )
    return f"""TASK: FAITHFUL 8:9 POSTER LAYOUT ADAPTATION

Adapt the supplied finished {source_width} x {source_height} poster into one finished 8:9 central creative plate. This is a genuine layout adaptation of the same design, not a redesign, background-only extension, letterbox, or flat resize.

PRE-GENERATION INTERNAL CONTENT INVENTORY
Before composing the output, inspect the supplied poster in full and internally inventory every visible:
- text string, including Chinese characters, English words, numbers, prices, punctuation and microtext;
- merchant logo, brand mark and printed product label;
- product, package, dish, person, mascot and other distinctive visual object;
- defining color, material, texture, lighting treatment and decorative element.

Complete this inventory before generating. Treat every inventoried item as locked source content. Use the inventory to verify the composition internally before returning the image: every item must still be present, semantically unchanged and recognizably faithful to the source. Do not output the inventory and do not turn it into new poster copy. If exact detail is uncertain, preserve the source appearance rather than guessing, correcting, paraphrasing or substituting it.

SOURCE AUTHORITY
- The uploaded poster is the only authority for content, merchant identity and visual style.
- Preserve every original title, subtitle, body line, number, price, date, discount, offer, rule and other audience-facing statement verbatim. Never invent, delete, correct, translate, paraphrase, merge or replace text.
- Preserve every original product, dish, package, person, merchant logo and brand identifier. Keep recognizable shapes, labels, proportions, colors and distinguishing details.
- Preserve the original palette, typography character, hierarchy, lettering effects, photography or illustration treatment, lighting, materials, textures, decorations and overall design language.
- Do not modernize, simplify, beautify into a different style, add campaign facts, or substitute look-alike glyphs or logos.

REAL 8:9 LAYOUT ADAPTATION
- Compose directly for the full 8:9 canvas. Do not paste, stretch, frame or letterbox the old poster as one flat rectangle.
- Use the wider 8:9 canvas deliberately: move and proportionally scale existing groups, rebalance gaps, and reflow existing elements only as much as the aspect-ratio change requires.
- Preserve the original reading order, hierarchy, focal relationships and relative visual weight. Do not crop, cover, omit, duplicate or replace semantic content.
- Treat each existing text block, price and merchant logo as an intact visual source asset to be repositioned or uniformly scaled, not retyped or redrawn.
- {ratio_note}
- If content does not fit, reduce and re-space existing groups until it does. Never solve fit by clipping or regenerating text, logos, prices or products.

8:9 CROP BUFFER FOR THE NEXT STAGE
- Output exactly 8:9, opaque and full bleed.
- At 1080 x 1215 normalization, the outer 30 px at both top and bottom will be removed locally before vertical outpainting.
- Keep the complete bounding box of every word, number, price, product, dish, package, person, merchant logo and brand identifier outside those two 30 px crop buffers.
- Fill both crop buffers only with natural continuous non-semantic background from the source design. No text, logo, product, dish, package, person, badge or information card may enter them.
- Leave the background at both crop joins visually extendable, without a horizontal band, inner border, abrupt lighting boundary or framed-poster edge.

LOCAL BRAND COMPOSITION
- Preserve the source merchant logo because it belongs to the original design.
- Do not add a new Fantuan logo, Fantuan header, Fantuan information bar, crop mark or guide. The application adds authoritative Fantuan SVG assets locally after both AI stages.

OUTPUT
Return one opaque, full-bleed 8:9 raster central creative plate containing the same design and facts, intelligently reflowed for the wider canvas.""".strip()


def build_single_call_prompt(source_width: int, source_height: int) -> str:
    """Build the isolated one-call A/B prompt; production Resize does not use it."""
    source_ratio = source_width / source_height
    if source_ratio < 0.62:
        adaptation_note = (
            "The source is much narrower than 3:4. Reflow its existing groups across the wider canvas, "
            "but keep each original text block and merchant mark as an intact visual asset."
        )
    else:
        adaptation_note = (
            "The source is already close to 3:4. Prefer uniform down-scaling and vertical re-spacing over "
            "reconstruction; do not enlarge the layout toward either overlay."
        )
    semantic_top = SEMANTIC_SAFE_BOX[1]
    semantic_bottom = SEMANTIC_SAFE_BOX[3] - 1
    return f"""TASK: ONE-CALL FAITHFUL POSTER LAYOUT ADAPTATION (EXPERIMENT)

Adapt the supplied finished {source_width} x {source_height} poster directly into one finished 3:4 poster. This is layout adaptation of the same artwork, not a redesign and not a background-only outpaint.

SOURCE AUTHORITY
- The uploaded poster is the only authority for content and visual identity.
- Preserve every original title, subtitle, body line, number, price, date, discount, offer, rule and other audience-facing statement verbatim. Never invent, delete, correct, translate, paraphrase, merge or replace text.
- Preserve every product, package, person, original merchant logo and brand identifier. Preserve recognizable shapes, labels, proportions, colors and distinguishing details.
- Preserve the original palette, background, typography character, hierarchy, lettering effects, photography or illustration treatment, lighting, materials, textures, decoration and overall design language.
- Treat every existing text block and merchant logo as an indivisible visual source asset to be moved or uniformly scaled, not as content to interpret, retype, redraw or improve. Do not synthesize substitute glyphs or a look-alike logo.

INTELLIGENT 3:4 REFLOW
- Compose directly for the full 3:4 canvas. Do not place, stretch or letterbox the old poster as one flat rectangle.
- Use the available width deliberately. Enlarge and redistribute existing elements when appropriate instead of leaving narrow content with large side margins.
- Reflow existing elements only as much as the aspect-ratio change requires. You may move, proportionally scale, re-space, re-wrap or change an existing left-right arrangement into a top-bottom arrangement.
- Preserve the original hierarchy and focal relationships. Do not crop away, duplicate or replace semantic content.
- {adaptation_note}
- If the full source content does not initially fit, uniformly reduce and re-space existing groups until it does. Never solve fit by clipping, covering, omitting or regenerating text, logos, prices or products.

AUTHORITATIVE LOCAL BRAND OVERLAYS
- The application will add the Fantuan SVG header and information bar locally after this image is returned.
- Final canvas coordinates are 1080 x 1440. The SVGs visibly cover y=0-159 at the top and y=1315-1439 at the bottom.
- Apply a mandatory safety buffer beyond those overlays. The ONLY semantic-content box is x=0-1079, y={semantic_top}-{semantic_bottom}. Its height is {SEMANTIC_SAFE_BOX[3] - SEMANTIC_SAFE_BOX[1]} px.
- Keep the complete bounding box of every word, number, price, product, package, person, dish, merchant logo and brand identifier inside y={semantic_top}-{semantic_bottom}. No shadow, outline, bowl, plate, food edge or logo stroke may cross those two lines.
- In the entire top exclusion band y=0-{semantic_top - 1} and bottom exclusion band y={SEMANTIC_SAFE_BOX[3]}-1439, render only natural continuous non-semantic background matching the source. These bands must contain no text, logo, product, dish, package, person, badge or other meaningful object.
- Before returning the image, check the topmost and bottommost meaningful pixels. If either falls outside y={semantic_top}-{semantic_bottom}, scale down and reposition the full layout until both pass.
- Do not generate a new Fantuan logo, Fantuan header, Fantuan information bar, crop mark or guide.

BACKGROUND CONTINUITY
- Extend or reconstruct the original background across the entire 3:4 canvas. Do not turn a colored or dark design into white, gray, a generic studio, padding, a frame or a new environment.
- Avoid horizontal seams, bands, brightness steps, blur strips, mirrored texture, copied edges and inner-poster borders.

OUTPUT
Return exactly one opaque, full-bleed 3:4 raster poster. Preserve the source merchant logo exactly; keep both exclusion bands background-only for deterministic local SVG composition.""".strip()


def normalize_single_call_output(image_bytes: bytes, raw_path: Path, normalized_path: Path) -> dict[str, Any]:
    raw_path.write_bytes(image_bytes)
    with Image.open(raw_path) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
        source_size = image.size
        ratio = image.width / image.height
        if not math.isclose(ratio, 3 / 4, rel_tol=0.035):
            raise RuntimeError(f"RESIZE_SINGLE_CALL_RATIO_INVALID:{image.width}x{image.height}")
        ImageOps.fit(image, FINAL_SIZE, method=Image.Resampling.LANCZOS).save(normalized_path, "PNG", optimize=True)
    return {"provider_output_size": list(source_size), "normalized_size": list(FINAL_SIZE)}


def validate_brand_overlay_scope(base_path: Path, final_path: Path) -> dict[str, Any]:
    """Prove that deterministic branding did not alter the central creative region."""
    with Image.open(base_path) as opened:
        base = opened.convert("RGB")
    with Image.open(final_path) as opened:
        final = opened.convert("RGB")
    if base.size != FINAL_SIZE or final.size != FINAL_SIZE:
        raise RuntimeError("RESIZE_BRAND_SCOPE_SIZE_INVALID")
    central_box = (0, SAFE_BOX[1], FINAL_SIZE[0], SAFE_BOX[3])
    central_unchanged = ImageChops.difference(base.crop(central_box), final.crop(central_box)).getbbox() is None
    if not central_unchanged:
        raise RuntimeError("RESIZE_BRAND_OVERLAY_TOUCHED_CENTER")
    return {
        "central_box": list(central_box),
        "central_pixel_exact": True,
        "changed_regions_expected": [[0, 0, 1080, SAFE_BOX[1]], [0, SAFE_BOX[3], 1080, 1440]],
    }


def single_call_mechanical_metrics(image_path: Path) -> dict[str, Any]:
    """Mechanical proxies only; content, typography and density require visual review."""
    with Image.open(image_path) as opened:
        image = opened.convert("RGB")
        top = image.crop((0, 0, image.width, SAFE_BOX[1]))
        bottom = image.crop((0, SAFE_BOX[3], image.width, image.height))
        center = image.crop(SAFE_BOX)

    def near_white_ratio(region: Image.Image) -> float:
        pixels = list(region.getdata())
        return sum(1 for value in pixels if min(value) >= NEAR_WHITE) / len(pixels) if pixels else 0.0

    return {
        "output_size": list(image.size),
        "output_aspect_ratio": image.width / image.height,
        "top_overlay_zone_near_white_ratio": round(near_white_ratio(top), 6),
        "center_near_white_ratio": round(near_white_ratio(center), 6),
        "bottom_overlay_zone_near_white_ratio": round(near_white_ratio(bottom), 6),
        "visual_review_required": [
            "all_original_copy_and_prices", "product_and_merchant_logo_fidelity",
            "horizontal_space_usage_and_visual_density", "brand_overlay_occlusion",
            "background_whitening", "seams_or_stitching",
        ],
        "interpretation": "Mechanical proxies only; no OCR or semantic correctness claim.",
    }


def build_outpaint_prompt(placement: dict[str, Any]) -> str:
    x, y, width, height = (placement[key] for key in ("x", "y", "width", "height"))
    return f"""TASK: BACKGROUND-ONLY OUTPAINT FOR A FINISHED POSTER

The supplied transparent 3:4 canvas contains one authoritative finished poster rectangle at x={x}-{x + width - 1}, y={y}-{y + height - 1}. Every visible pixel inside that rectangle is locked source artwork.

PIXEL AUTHORITY
- Do not redraw, restyle, correct, move, resize, crop, sharpen, blur or regenerate anything inside the locked rectangle.
- Do not alter any glyph, word, number, logo, product, person, package, color, texture or original background pixel inside it.
- The application will restore the authoritative source pixels locally after generation. Your output inside the rectangle will be discarded.

BACKGROUND EXTENSION ONLY
- Generate content only in the transparent area outside the locked rectangle.
- Continue the source artwork's actual background colors, texture, lighting, materials, depth, perspective, atmosphere and non-semantic decoration naturally to all four canvas edges.
- Sample the source background immediately beside each boundary. Do not replace a colored or dark source background with white, gray, a generic studio, padding, a frame or a new scene.
- Make every join continuous: no seam, band, brightness step, blur strip, repeated or mirrored texture, copied edge, border or letterbox appearance.
- Do not add any new title, word, number, product, package, person, badge, information card, logo, slogan or recognizable campaign element outside the locked rectangle.

OUTPUT
Return one opaque, full-bleed 3:4 raster image. The locked rectangle is placement context only; all semantic artwork remains authoritative in the uploaded source.""".strip()


def _sha256_pixels(image: Image.Image) -> str:
    return hashlib.sha256(image.convert("RGBA").tobytes()).hexdigest()


def prepare_authoritative_canvas(source_path: Path, canvas_path: Path, authority_path: Path) -> dict[str, Any]:
    """Contain the decoded source in the safe box without cropping and create an outpaint canvas."""
    with Image.open(source_path) as opened:
        source = ImageOps.exif_transpose(opened).convert("RGBA")
    source_width, source_height = source.size
    safe_width = SAFE_BOX[2] - SAFE_BOX[0]
    safe_height = SAFE_BOX[3] - SAFE_BOX[1]
    scale = min(safe_width / source_width, safe_height / source_height)
    target_width = max(1, min(safe_width, round(source_width * scale)))
    target_height = max(1, min(safe_height, round(source_height * scale)))
    if (target_width, target_height) == source.size:
        authority = source.copy()
        resampled = False
    else:
        authority = source.resize((target_width, target_height), Image.Resampling.LANCZOS)
        resampled = True
    x = SAFE_BOX[0] + (safe_width - target_width) // 2
    y = SAFE_BOX[1] + (safe_height - target_height) // 2
    canvas = Image.new("RGBA", FINAL_SIZE, (0, 0, 0, 0))
    canvas.alpha_composite(authority, (x, y))
    authority.save(authority_path, "PNG", optimize=True)
    canvas.save(canvas_path, "PNG", optimize=True)
    return {
        "x": x, "y": y, "width": target_width, "height": target_height,
        "source_width": source_width, "source_height": source_height,
        "scale": scale, "resampled": resampled,
        "source_aspect_ratio": source_width / source_height,
        "placed_aspect_ratio": target_width / target_height,
        "authority_pixel_sha256": _sha256_pixels(authority),
        "pixel_identity_scope": "resampled_authority" if resampled else "decoded_source",
    }


def restore_authoritative_region(generated_path: Path, authority_path: Path, placement: dict[str, Any], target_path: Path) -> None:
    with Image.open(generated_path) as opened:
        generated = opened.convert("RGBA")
    if generated.size != FINAL_SIZE:
        raise RuntimeError(f"RESIZE_OUTPUT_SIZE_INVALID:{generated.size}")
    with Image.open(authority_path) as opened:
        authority = opened.convert("RGBA")
    expected = (int(placement["width"]), int(placement["height"]))
    if authority.size != expected:
        raise RuntimeError(f"RESIZE_AUTHORITY_SIZE_INVALID:{authority.size}")
    generated.alpha_composite(authority, (int(placement["x"]), int(placement["y"])))
    generated.convert("RGB").save(target_path, "PNG", optimize=True)


def validate_restored_output(output_path: Path, authority_path: Path, placement: dict[str, Any], *, reject_white_anomaly: bool = True) -> dict[str, Any]:
    with Image.open(output_path) as opened:
        output = opened.convert("RGBA")
    if output.size != FINAL_SIZE:
        raise RuntimeError(f"RESIZE_OUTPUT_SIZE_INVALID:{output.size}")
    x, y = int(placement["x"]), int(placement["y"])
    width, height = int(placement["width"]), int(placement["height"])
    with Image.open(authority_path) as opened:
        authority = opened.convert("RGBA")
    restored = output.crop((x, y, x + width, y + height))
    pixel_exact = ImageChops.difference(restored, authority).getbbox() is None

    mask = Image.new("L", FINAL_SIZE, 255)
    mask.paste(0, (x, y, x + width, y + height))
    white_pixels = generated_pixels = 0
    for value, include in zip(output.convert("RGB").getdata(), mask.getdata()):
        if include:
            generated_pixels += 1
            if min(value) >= NEAR_WHITE:
                white_pixels += 1
    generated_white_ratio = white_pixels / generated_pixels if generated_pixels else 0.0

    border = max(1, min(8, width // 2, height // 2))
    border_mask = Image.new("L", authority.size, 255)
    if width > border * 2 and height > border * 2:
        border_mask.paste(0, (border, border, width - border, height - border))
    source_white_pixels = source_border_pixels = 0
    for value, include in zip(authority.convert("RGB").getdata(), border_mask.getdata()):
        if include:
            source_border_pixels += 1
            if min(value) >= NEAR_WHITE:
                source_white_pixels += 1
    source_border_white_ratio = source_white_pixels / source_border_pixels if source_border_pixels else 0.0
    white_anomaly = generated_white_ratio >= WHITE_ANOMALY_THRESHOLD and source_border_white_ratio < SOURCE_WHITE_EVIDENCE_THRESHOLD
    aspect_error = abs(float(placement["source_aspect_ratio"]) - float(placement["placed_aspect_ratio"]))
    report = {
        "output_size": list(output.size), "output_aspect_ratio": output.width / output.height,
        "source_aspect_ratio": placement["source_aspect_ratio"], "placed_aspect_ratio": placement["placed_aspect_ratio"],
        "aspect_ratio_error": aspect_error, "source_region_pixel_exact": pixel_exact,
        "authority_pixel_sha256": _sha256_pixels(restored), "source_resampled": bool(placement["resampled"]),
        "pixel_identity_scope": placement["pixel_identity_scope"], "generated_region_near_white_ratio": generated_white_ratio,
        "source_border_near_white_ratio": source_border_white_ratio, "abnormal_white_background": white_anomaly,
    }
    if not pixel_exact:
        raise RuntimeError("RESIZE_SOURCE_PIXEL_MISMATCH")
    if not math.isclose(output.width / output.height, 3 / 4, abs_tol=1e-12):
        raise RuntimeError("RESIZE_OUTPUT_RATIO_INVALID")
    if not math.isclose(float(placement["source_aspect_ratio"]), float(placement["placed_aspect_ratio"]), rel_tol=0.002):
        raise RuntimeError("RESIZE_SOURCE_RATIO_INVALID")
    if reject_white_anomaly and white_anomaly:
        raise RuntimeError("RESIZE_ABNORMAL_WHITE_BACKGROUND")
    return report
