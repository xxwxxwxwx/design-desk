#!/usr/bin/env python3
"""Run an isolated paid one-call Resize A/B experiment without changing production flow."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "pipeline")]
import resize_v1  # noqa: E402
import server  # noqa: E402
import v52  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--merchant-name", required=True)
    parser.add_argument("--overlay-mode", choices=("fantuan_only", "co_brand"), default="fantuan_only")
    parser.add_argument("--merchant-logo", type=Path)
    parser.add_argument("--baseline-job", type=Path)
    parser.add_argument("--output-root", type=Path, default=ROOT / "data" / "experiments")
    parser.add_argument("--execute", action="store_true", help="Make exactly one paid KIE call (estimated 6 credits).")
    args = parser.parse_args()

    if not args.source.is_file():
        raise SystemExit("SOURCE_NOT_FOUND")
    if args.overlay_mode == "co_brand" and not (args.merchant_logo and args.merchant_logo.is_file()):
        raise SystemExit("MERCHANT_LOGO_REQUIRED")
    if args.execute and not server.active_api_key():
        raise SystemExit("KIE_API_KEY_MISSING")

    with Image.open(args.source) as opened:
        source = ImageOps.exif_transpose(opened)
        width, height = source.size
    prompt = resize_v1.build_single_call_prompt(width, height)
    experiment_id = time.strftime("%Y%m%d-%H%M%S-resize-single-call-ab")
    output = args.output_root / experiment_id
    output.mkdir(parents=True, exist_ok=False)
    shutil.copy2(args.source, output / f"source{args.source.suffix.lower()}")
    (output / "prompt.txt").write_text(prompt, encoding="utf-8")

    manifest = {
        "experiment": "resize_single_call_ab", "experimental": True,
        "production_flow_changed": False, "prompt_version": resize_v1.SINGLE_CALL_PROMPT_VERSION,
        "model": v52.MODEL, "aspect_ratio": "3:4", "resolution": v52.RESOLUTION,
        "background": "auto", "paid_calls": 1 if args.execute else 0,
        "estimated_credits_if_executed": 6, "source": str(args.source),
        "baseline_job": str(args.baseline_job) if args.baseline_job else None,
        "status": "running" if args.execute else "dry_run",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    actual_request = {
        "model": v52.MODEL,
        "input_file": str(args.source),
        "aspect_ratio": "3:4",
        "resolution": v52.RESOLUTION,
        "background": "auto",
        "prompt_version": resize_v1.SINGLE_CALL_PROMPT_VERSION,
        "prompt": prompt,
        "paid_call_authorized": bool(args.execute),
    }
    (output / "actual-request.json").write_text(
        json.dumps(actual_request, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    review = {
        "status": "pending",
        "ratings": {
            "composition_utilization": None,
            "merchant_logo_fidelity": None,
            "copy_and_price_fidelity": None,
            "product_completeness": None,
            "top_occlusion_after_overlay": None,
            "bottom_occlusion_after_overlay": None,
            "background_quality": None,
        },
        "notes": [],
        "rating_scale": "0=failed, 1=partly passed, 2=passed",
    }
    (output / "visual-review.json").write_text(json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8")
    if not args.execute:
        print(output)
        return 0

    response = v52.call(prompt, [v52.image_tuple(args.source)], experiment_id, "3:4", background="auto", timeout_seconds=600)
    normalization = resize_v1.normalize_single_call_output(response, output / "single-call.raw.png", output / "single-call.1080x1440.png")
    server.compose_final(output / "single-call.1080x1440.png", args.merchant_logo, args.merchant_name, args.overlay_mode, output / "single-call.final.png")
    metrics = resize_v1.single_call_mechanical_metrics(output / "single-call.1080x1440.png")
    metrics["normalization"] = normalization
    (output / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.baseline_job:
        for name in ("source-poster.jpg", "generated-base-1080x1440.png", "final.png", "metrics.json", "request.json"):
            candidate = args.baseline_job / name
            if candidate.is_file():
                shutil.copy2(candidate, output / f"baseline-double-call.{name}")
    manifest["status"] = "completed"
    manifest["visual_review"] = "pending"
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
