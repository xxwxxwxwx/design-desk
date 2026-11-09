#!/usr/bin/env python3
"""Run an isolated four-call Resize first-stage Prompt A/B experiment."""
from __future__ import annotations

import argparse
import getpass
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "pipeline")]
import resize_v1  # noqa: E402
import server  # noqa: E402
import v52  # noqa: E402

EXPERIMENT_VERSION = "2026-10-30-resize-first-stage-prompt-ab-v1"
ESTIMATED_CREDITS_PER_CALL = 6

CASES = (
    {
        "id": "fuzhou-laohua",
        "label": "福州捞化",
        "source": ROOT / "data/jobs/20261030-150535-853e239c/source-poster.jpg",
    },
    {
        "id": "yuxiangyuan",
        "label": "渔香缘",
        "source": ROOT / "data/jobs/20261030-150225-b6c89fcf/source-poster.jpg",
    },
)


def build_prompt_b(width: int, height: int) -> str:
    """Concise visual-target prompt; factual constraints stay explicit."""
    return f"""Adapt this finished {width} x {height} poster into one full-bleed 8:9 central creative plate.

TARGET VISUAL
Create a visually full, lively and balanced commercial-food poster like the previously accepted Fuzhou Laohua adaptation: confident use of the wider canvas, clear hierarchy, generous product scale, compact purposeful spacing and strong appetizing impact. Keep the source poster's own palette, typography character, graphic treatment and overall design language; this is layout adaptation, not redesign.

MUST PRESERVE
- Keep every original Chinese word, number and price verbatim and readable. Do not invent, omit, correct, translate, paraphrase or replace any copy.
- Keep the merchant logo and all brand identifiers recognizable and accurate.
- Keep every original product or dish complete, recognizable and uncropped; do not add, remove, merge or substitute products.
- Reflow, reposition and proportionally scale existing groups only as needed to make the 8:9 composition feel full and balanced. Preserve the original hierarchy and reading order.

OUTPUT
Return exactly one opaque, full-bleed 8:9 raster image. Do not add Fantuan branding, guides, frames or unrelated content.""".strip()


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as opened:
        image = ImageOps.exif_transpose(opened)
        return image.size


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def prepare_experiment(output_root: Path) -> tuple[Path, list[dict[str, Any]]]:
    experiment_id = time.strftime("%Y%m%d-%H%M%S-resize-first-stage-prompt-ab")
    output = output_root / experiment_id
    output.mkdir(parents=True, exist_ok=False)
    requests: list[dict[str, Any]] = []
    for case in CASES:
        source = Path(case["source"])
        if not source.is_file():
            raise SystemExit(f"SOURCE_NOT_FOUND:{source}")
        width, height = image_size(source)
        for variant in ("A", "B"):
            prompt = (
                resize_v1.build_layout_adaptation_prompt(width, height)
                if variant == "A"
                else build_prompt_b(width, height)
            )
            request_id = f"{case['id']}-{variant.lower()}"
            case_dir = output / request_id
            case_dir.mkdir()
            shutil.copy2(source, case_dir / "source.jpg")
            (case_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
            request = {
                "request_id": request_id,
                "case": case["label"],
                "variant": variant,
                "prompt_role": "current_strict_fidelity" if variant == "A" else "concise_target_visual",
                "prompt": prompt,
                "model": v52.MODEL,
                "aspect_ratio": "8:9",
                "resolution": v52.RESOLUTION,
                "background": "opaque",
                "source": str(source.relative_to(ROOT)),
                "source_size": [width, height],
                "estimated_credits": ESTIMATED_CREDITS_PER_CALL,
                "status": "prepared",
            }
            write_json(case_dir / "request.json", request)
            requests.append({**request, "case_dir": str(case_dir)})
    manifest = {
        "experiment": "resize_first_stage_prompt_ab",
        "experiment_version": EXPERIMENT_VERSION,
        "experimental": True,
        "production_flow_changed": False,
        "scope": "first 8:9 image-to-image layout adaptation only",
        "excluded": ["second outpaint call", "brand overlay", "production prompt mutation", "automatic retry"],
        "model": v52.MODEL,
        "aspect_ratio": "8:9",
        "resolution": v52.RESOLUTION,
        "background": "opaque",
        "planned_calls": len(requests),
        "estimated_credits_per_call": ESTIMATED_CREDITS_PER_CALL,
        "estimated_credits_total": len(requests) * ESTIMATED_CREDITS_PER_CALL,
        "status": "prepared",
        "requests": [{k: v for k, v in item.items() if k not in {"prompt", "case_dir"}} for item in requests],
    }
    write_json(output / "manifest.json", manifest)
    return output, requests


def execute(output: Path, requests: list[dict[str, Any]], api_key: str) -> None:
    server.SESSION_API_KEY = api_key
    completed = 0
    for item in requests:
        case_dir = Path(item["case_dir"])
        request_path = case_dir / "request.json"
        request = json.loads(request_path.read_text(encoding="utf-8"))
        request["status"] = "running"
        write_json(request_path, request)
        try:
            payload = v52.call(
                item["prompt"],
                [v52.image_tuple(case_dir / "source.jpg")],
                item["request_id"],
                "8:9",
                background="opaque",
                timeout_seconds=600,
            )
            v52.normalize(payload, case_dir / "output-1080x1215.png", v52.CENTRAL_API_SIZE, 8 / 9)
            request["status"] = "completed"
            completed += 1
        except Exception as exc:
            request["status"] = "failed"
            request["error"] = str(exc)
        write_json(request_path, request)

    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["completed_calls"] = completed
    manifest["failed_calls"] = len(requests) - completed
    manifest["actual_credits_estimate"] = completed * ESTIMATED_CREDITS_PER_CALL
    manifest["status"] = "completed" if completed == len(requests) else "partial_failure"
    manifest["visual_review"] = "pending"
    write_json(manifest_path, manifest)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, default=ROOT / "data/experiments")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    output, requests = prepare_experiment(args.output_root)
    print(f"Prepared: {output}")
    print("Plan: 4 calls x 6 credits = 24 estimated credits; no retries.")
    if not args.execute:
        return 0
    api_key = getpass.getpass("KIE API Key (hidden, not saved): ").strip()
    if not api_key:
        raise SystemExit("KIE_API_KEY_MISSING")
    balance = server.validate_api_key(api_key)
    print(f"Key validated. Current balance: {balance:g} credits.")
    if balance < len(requests) * ESTIMATED_CREDITS_PER_CALL:
        raise SystemExit("KIE_CREDITS_INSUFFICIENT")
    confirmation = input("Type RUN 24 to start exactly four paid calls: ").strip()
    if confirmation != "RUN 24":
        raise SystemExit("CANCELLED")
    execute(output, requests, api_key)
    print(f"Finished: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
