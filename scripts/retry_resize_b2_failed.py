#!/usr/bin/env python3
"""Retry only failed cases in an existing Resize B2 batch."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "pipeline"), str(ROOT / "scripts")]
import run_resize_b2_cross_engine_batch as runner  # noqa: E402
import server  # noqa: E402
import v52  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("batch", type=Path)
    args = parser.parse_args()
    api_key = server.active_api_key()
    if not api_key:
        raise SystemExit("KIE_API_KEY_MISSING")
    failed = []
    for request_path in sorted(args.batch.glob("*/request.json")):
        request = json.loads(request_path.read_text(encoding="utf-8"))
        if request.get("status") == "failed":
            failed.append((request_path.parent, request_path, request))
    if not failed:
        print("NO_FAILED_CASES")
        return 0
    balance_before = server.validate_api_key(api_key)
    for case_dir, request_path, request in failed:
        previous = {key: request.get(key) for key in ("taskId", "status", "error", "provider_record") if request.get(key) is not None}
        attempts = request.setdefault("attempts", [])
        attempts.append(previous)
        request_id = f"resize-b2-retry-{request['sequence']:02d}-{int(time.time())}"
        request.update(status="uploading", request_id=request_id)
        request.pop("error", None)
        runner.write_json(request_path, request)
        try:
            task_id, payload = runner.create_task(
                api_key, case_dir / request["source_file"],
                (case_dir / "prompt-b2.txt").read_text(encoding="utf-8"), request_id,
            )
            request.update(status="running", taskId=task_id, actual_request=runner.safe_request(payload))
            runner.write_json(request_path, request)
            image_bytes, record = runner.wait_for_result(api_key, task_id)
            (case_dir / "output.raw.png").write_bytes(image_bytes)
            v52.normalize(image_bytes, case_dir / "output-1080x1215.png", v52.CENTRAL_API_SIZE, 8 / 9)
            request.update(status="completed", provider_record={
                key: record.get(key) for key in ("taskId", "state", "costTime", "createTime", "completeTime")
                if record.get(key) is not None
            })
        except Exception as exc:
            request.update(status="failed", error=str(exc))
        runner.write_json(request_path, request)
    statuses = [json.loads(path.read_text()).get("status") for path in sorted(args.batch.glob("*/request.json"))]
    balance_after = server.validate_api_key(api_key)
    manifest_path = args.batch / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        status="completed" if statuses.count("completed") == len(statuses) else "partial_failure",
        completed_calls=statuses.count("completed"),
        failed_calls=statuses.count("failed"),
        retry_credits_before=balance_before,
        retry_credits_after=balance_after,
        retry_credits_consumed=balance_before - balance_after,
        credits_consumed_total=manifest.get("credits_consumed", 0) + balance_before - balance_after,
    )
    runner.write_json(manifest_path, manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
