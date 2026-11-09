#!/usr/bin/env python3
"""Run a fixed-prompt Resize B2 first-stage batch against explicit source posters."""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import shutil
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "pipeline"), str(ROOT / "scripts")]
import run_resize_first_stage_prompt_b2 as b2  # noqa: E402
import server  # noqa: E402
import v52  # noqa: E402


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as opened:
        return ImageOps.exif_transpose(opened).size


def safe_request(request: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in request.items() if key not in {"api_key", "input_urls"}}


def create_task(api_key: str, source: Path, prompt: str, request_id: str) -> tuple[str, dict[str, Any]]:
    content_type = mimetypes.guess_type(source.name)[0] or "image/png"
    uploaded = server.upload_to_kie(api_key, source.name, source.read_bytes(), content_type, request_id)
    payload = {
        "model": v52.MODEL,
        "input": {
            "prompt": prompt,
            "input_urls": [uploaded],
            "aspect_ratio": "8:9",
            "resolution": v52.RESOLUTION,
            "background": "opaque",
        },
    }
    created = server.kie_json_request(
        f"{server.KIE_API_ROOT}/api/v1/jobs/createTask", api_key, method="POST", payload=payload
    )
    task_id = str(created.get("data", {}).get("taskId", ""))
    if not task_id:
        raise RuntimeError("KIE_INVALID_RESPONSE:no taskId")
    return task_id, payload


def wait_for_result(api_key: str, task_id: str, timeout_seconds: int = 600) -> tuple[bytes, dict[str, Any]]:
    deadline, delay = time.monotonic() + timeout_seconds, 2.0
    while time.monotonic() < deadline:
        time.sleep(delay)
        response = server.kie_json_request(
            f"{server.KIE_API_ROOT}/api/v1/jobs/recordInfo?taskId={task_id}", api_key
        )
        data = response.get("data", {})
        if data.get("state") == "fail":
            raise RuntimeError(f"KIE_GENERATION_FAILED:{data.get('failMsg') or data.get('failCode') or 'unknown'}")
        if data.get("state") == "success":
            result = json.loads(data.get("resultJson") or "{}")
            with urllib.request.urlopen(result["resultUrls"][0], timeout=120) as downloaded:
                return downloaded.read(), data
        delay = min(delay * 1.35, 8.0)
    raise RuntimeError("KIE_TIMEOUT:10 minutes")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--internal-inventory",
        action="store_true",
        help="Experimental A variant: require an internal content inventory before B2 generation.",
    )
    parser.add_argument("sources", nargs="+", type=Path)
    args = parser.parse_args()
    if len(args.sources) > 8:
        raise SystemExit("MAXIMUM_8_SOURCES")
    args.output.mkdir(parents=True, exist_ok=False)
    requests = []
    for index, source in enumerate(args.sources, 1):
        if not source.is_file():
            raise SystemExit(f"SOURCE_NOT_FOUND:{source}")
        case_dir = args.output / f"{index:02d}-{source.stem}"
        case_dir.mkdir()
        source_copy = case_dir / f"source{source.suffix.lower()}"
        shutil.copy2(source, source_copy)
        width, height = image_size(source_copy)
        if args.internal_inventory:
            baseline, prompt = b2.build_prompt_a(width, height)
            prompt_version = "2026-11-04-resize-b2-internal-inventory-a-v1"
            prompt_filename = "prompt-a-internal-inventory.txt"
        else:
            baseline, prompt = b2.build_prompt_b2(width, height)
            prompt_version = b2.EXPERIMENT_VERSION
            prompt_filename = "prompt-b2.txt"
        (case_dir / "prompt-a-baseline.txt").write_text(baseline, encoding="utf-8")
        (case_dir / prompt_filename).write_text(prompt, encoding="utf-8")
        request = {
            "sequence": index,
            "original_filename": source.name,
            "source_file": source_copy.name,
            "source_size": [width, height],
            "source_sha256": hashlib.sha256(source_copy.read_bytes()).hexdigest(),
            "prompt_version": prompt_version,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "model": v52.MODEL,
            "aspect_ratio": "8:9",
            "resolution": v52.RESOLUTION,
            "background": "opaque",
            "estimated_credits": b2.ESTIMATED_CREDITS_PER_CALL,
            "status": "prepared",
        }
        write_json(case_dir / "request.json", request)
        requests.append((case_dir, source_copy, prompt, request))
    manifest = {
        "experiment": "resize_b2_cross_engine_batch",
        "prompt_version": requests[0][3]["prompt_version"],
        "internal_inventory": args.internal_inventory,
        "production_flow_changed": False,
        "scope": "first 8:9 Layout Adaptation only",
        "excluded": ["second 3:4 outpaint", "local brand overlay", "automatic retry"],
        "planned_calls": len(requests),
        "estimated_credits_total": len(requests) * b2.ESTIMATED_CREDITS_PER_CALL,
        "status": "prepared",
    }
    write_json(args.output / "manifest.json", manifest)
    if not args.execute:
        print(args.output)
        return 0
    api_key = server.active_api_key()
    if not api_key:
        raise SystemExit("KIE_API_KEY_MISSING")
    balance_before = server.validate_api_key(api_key)
    if balance_before < manifest["estimated_credits_total"]:
        raise SystemExit(f"INSUFFICIENT_CREDITS:{balance_before:g}")
    completed = 0
    for case_dir, source, prompt, request in requests:
        request_id = f"resize-b2-cross-{request['sequence']:02d}-{int(time.time())}"
        request.update(status="uploading", request_id=request_id)
        write_json(case_dir / "request.json", request)
        try:
            task_id, payload = create_task(api_key, source, prompt, request_id)
            request.update(status="running", taskId=task_id, actual_request=safe_request(payload))
            write_json(case_dir / "request.json", request)
            image_bytes, record = wait_for_result(api_key, task_id)
            (case_dir / "output.raw.png").write_bytes(image_bytes)
            v52.normalize(image_bytes, case_dir / "output-1080x1215.png", v52.CENTRAL_API_SIZE, 8 / 9)
            request.update(status="completed", provider_record={
                key: record.get(key) for key in ("taskId", "state", "costTime", "createTime", "completeTime")
                if record.get(key) is not None
            })
            completed += 1
        except Exception as exc:
            request.update(status="failed", error=str(exc))
        write_json(case_dir / "request.json", request)
    balance_after = server.validate_api_key(api_key)
    manifest.update(
        status="completed" if completed == len(requests) else "partial_failure",
        completed_calls=completed,
        failed_calls=len(requests) - completed,
        credits_before=balance_before,
        credits_after=balance_after,
        credits_consumed=balance_before - balance_after,
    )
    write_json(args.output / "manifest.json", manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
