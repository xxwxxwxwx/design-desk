#!/usr/bin/env python3
"""Run the isolated two-call Resize first-stage Prompt B2 experiment."""
from __future__ import annotations

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

EXPERIMENT_VERSION = "2026-10-30-resize-first-stage-prompt-b2-v1"
ESTIMATED_CREDITS_PER_CALL = 6
ACTIVE_RECOMPOSITION = (
    "Recompose the existing elements to make full and balanced use of the 8:9 canvas. "
    "Enlarge and redistribute products and promotional elements where appropriate, while preserving "
    "the original design language, color palette, typography treatment and all original content."
)
INTERNAL_INVENTORY = """PRE-GENERATION INTERNAL CONTENT INVENTORY
Before composing the output, inspect the supplied poster in full and internally inventory every visible:
- text string, including Chinese characters, English words, numbers, prices, punctuation and microtext;
- merchant logo, brand mark and printed product label;
- product, package, dish, person, mascot and other distinctive visual object;
- defining color, material, texture, lighting treatment and decorative element.

Complete this inventory before generating. Treat every inventoried item as locked source content. Use the
inventory to verify the composition internally before returning the image: every item must still be present,
semantically unchanged and recognizably faithful to the source. Do not output the inventory and do not turn it
into new poster copy. If exact detail is uncertain, preserve the source appearance rather than guessing,
correcting, paraphrasing or substituting it.
"""

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


def _conservative_ratio_instruction(width: int, height: int) -> str:
    if width / height < 0.72:
        return (
            "The source is substantially narrower than 8:9. Use the added width to redistribute existing groups "
            "and improve spacing while preserving their hierarchy."
        )
    return (
        "The source is already relatively close to 8:9. Make only the spacing and position changes required "
        "for a balanced 8:9 composition."
    )


def build_prompt_b2(width: int, height: int) -> tuple[str, str]:
    """Derive B2 from production A with one exact instruction replacement."""
    baseline = resize_v1.build_layout_adaptation_prompt(width, height)
    old = f"- {_conservative_ratio_instruction(width, height)}"
    new = f"- {ACTIVE_RECOMPOSITION}"
    if baseline.count(old) != 1:
        raise RuntimeError("B2_BASELINE_REPLACEMENT_TARGET_MISMATCH")
    prompt = baseline.replace(old, new, 1)
    return baseline, prompt


def build_prompt_a(width: int, height: int) -> tuple[str, str]:
    """Add an internal source inventory pass to B2 without changing its layout rules."""
    _, prompt_b2 = build_prompt_b2(width, height)
    marker = "SOURCE AUTHORITY\n"
    if prompt_b2.count(marker) != 1:
        raise RuntimeError("A_SOURCE_AUTHORITY_MARKER_MISMATCH")
    prompt_a = prompt_b2.replace(marker, f"{INTERNAL_INVENTORY}\n{marker}", 1)
    return prompt_b2, prompt_a


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as opened:
        return ImageOps.exif_transpose(opened).size


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def prepare_experiment(output_root: Path) -> tuple[Path, list[dict[str, Any]]]:
    experiment_id = time.strftime("%Y%m%d-%H%M%S-resize-first-stage-prompt-b2")
    output = output_root / experiment_id
    output.mkdir(parents=True, exist_ok=False)
    requests: list[dict[str, Any]] = []
    for case in CASES:
        source = Path(case["source"])
        if not source.is_file():
            raise SystemExit(f"SOURCE_NOT_FOUND:{source}")
        width, height = image_size(source)
        prompt_a, prompt_b2 = build_prompt_b2(width, height)
        case_dir = output / case["id"]
        case_dir.mkdir()
        shutil.copy2(source, case_dir / "source.jpg")
        (case_dir / "prompt-a-baseline.txt").write_text(prompt_a, encoding="utf-8")
        (case_dir / "prompt-b2.txt").write_text(prompt_b2, encoding="utf-8")
        request = {
            "request_id": f"{case['id']}-b2",
            "case": case["label"],
            "variant": "B2",
            "prompt_role": "production_a_with_active_recomposition_only",
            "prompt_version": EXPERIMENT_VERSION,
            "prompt": prompt_b2,
            "baseline_prompt_sha256": __import__("hashlib").sha256(prompt_a.encode()).hexdigest(),
            "actual_prompt_sha256": __import__("hashlib").sha256(prompt_b2.encode()).hexdigest(),
            "replacement": {"removed": _conservative_ratio_instruction(width, height), "inserted": ACTIVE_RECOMPOSITION},
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
        "experiment": "resize_first_stage_prompt_b2",
        "experiment_version": EXPERIMENT_VERSION,
        "experimental": True,
        "production_flow_changed": False,
        "scope": "first 8:9 image-to-image layout adaptation only",
        "excluded": ["second outpaint call", "brand overlay", "production prompt mutation", "automatic retry"],
        "model": v52.MODEL,
        "aspect_ratio": "8:9",
        "resolution": v52.RESOLUTION,
        "background": "opaque",
        "planned_calls": 2,
        "estimated_credits_per_call": ESTIMATED_CREDITS_PER_CALL,
        "estimated_credits_total": 12,
        "status": "prepared",
        "comparison_baseline": "data/experiments/20261030-170713-resize-first-stage-prompt-ab",
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
                item["prompt"], [v52.image_tuple(case_dir / "source.jpg")], item["request_id"],
                "8:9", background="opaque", timeout_seconds=600,
            )
            (case_dir / "output.raw.png").write_bytes(payload)
            v52.normalize(payload, case_dir / "output-1080x1215.png", v52.CENTRAL_API_SIZE, 8 / 9)
            request["status"] = "completed"
            completed += 1
        except Exception as exc:
            request["status"] = "failed"
            request["error"] = str(exc)
        write_json(request_path, request)
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        completed_calls=completed,
        failed_calls=len(requests) - completed,
        actual_credits_estimate=completed * ESTIMATED_CREDITS_PER_CALL,
        failed_call_billing_verified=False if completed != len(requests) else None,
        status="completed" if completed == len(requests) else "partial_failure",
        visual_review="pending",
    )
    write_json(manifest_path, manifest)

