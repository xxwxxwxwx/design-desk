#!/usr/bin/env python3
"""Local-only key entry page for the authorized eight-poster B2 batch."""
from __future__ import annotations

import html
import json
import os
import secrets
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import server  # noqa: E402

TOKEN = secrets.token_urlsafe(18)
PREPARED = ROOT / "data/experiments/20261104-resize-b2-cross-engine-8-new-posters"
SOURCES = sorted(PREPARED.glob("*/source.png"))
STATE = {"status": "waiting", "message": "等待在本机输入 KIE Key", "output": None}


def page() -> bytes:
    disabled = "disabled" if STATE["status"] == "running" else ""
    body = f"""<!doctype html><meta charset='utf-8'><title>Resize B2 八张对照测试</title>
<style>body{{font:16px -apple-system;margin:40px auto;max-width:720px;color:#18181b}}.card{{padding:28px;border:1px solid #ddd;border-radius:18px}}input{{width:100%;box-sizing:border-box;padding:13px;margin:8px 0 18px}}button{{padding:12px 18px;background:#111;color:#fff;border:0;border-radius:10px}}.msg{{padding:12px;background:#f4f4f5;border-radius:10px}}</style>
<div class='card'><h1>Resize B2 · 8 张 KIE 组</h1>
<p>已授权最多 8 次，预计最多 48 credits。只运行第一阶段 8:9，不扩图、不贴品牌、不修改生产 A、不自动重试。</p>
<p class='msg'>{html.escape(str(STATE['message']))}</p>
<form method='post' action='/{TOKEN}'><label>KIE API Key（仅在本次进程内存中使用）</label>
<input type='password' name='key' autocomplete='off' required {disabled}><button {disabled}>开始 8 张测试</button></form>
<p>输出目录：{html.escape(str(STATE.get('output') or '尚未生成'))}</p></div>"""
    return body.encode("utf-8")


def run(key: str) -> None:
    try:
        balance = server.validate_api_key(key)
        existing = ROOT / "data/experiments/20261104-134207-resize-b2-cross-engine-8"
        failed_count = 0
        if (existing / "manifest.json").is_file():
            failed_count = int(json.loads((existing / "manifest.json").read_text()).get("failed_calls", 0))
        required = failed_count * 6 if failed_count else 48
        if balance < required:
            raise RuntimeError(f"余额不足：{balance:g} credits，本次需要上限 {required} credits")
        output = existing if failed_count else ROOT / "data/experiments" / time.strftime("%Y%m%d-%H%M%S-resize-b2-cross-engine-8")
        action = f"只重试 {failed_count} 张失败图" if failed_count else "生成 8 张"
        STATE.update(message=f"Key 已验证，当前余额 {balance:g} credits；{action}中…", output=str(output))
        env = os.environ.copy()
        env["KIE_API_KEY"] = key
        command = (["/usr/bin/python3", str(ROOT / "scripts/retry_resize_b2_failed.py"), str(output)]
                   if failed_count else [
                       "/usr/bin/python3", str(ROOT / "scripts/run_resize_b2_cross_engine_batch.py"),
                       "--output", str(output), "--execute", *map(str, SOURCES),
                   ])
        completed = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True)
        if completed.returncode:
            raise RuntimeError((completed.stderr or completed.stdout).strip()[-1500:])
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        STATE.update(status=manifest["status"], message=(
            f"完成 {manifest.get('completed_calls', 0)}/8 次，"
            f"实际消耗 {manifest.get('credits_consumed', '待确认')} credits"
        ))
    except Exception as exc:
        STATE.update(status="failed", message=str(exc))


class Handler(BaseHTTPRequestHandler):
    def respond(self) -> None:
        payload = page()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if self.path != f"/{TOKEN}":
            self.send_error(404)
            return
        self.respond()

    def do_POST(self) -> None:
        if self.path != f"/{TOKEN}" or STATE["status"] == "running":
            self.send_error(409)
            return
        fields = parse_qs(self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode())
        key = fields.get("key", [""])[0].strip()
        if not key:
            STATE.update(message="请输入 KIE Key")
        else:
            STATE.update(status="running", message="正在验证 Key…")
            threading.Thread(target=run, args=(key,), daemon=True).start()
        self.respond()

    def log_message(self, *_: object) -> None:
        return


if __name__ == "__main__":
    if len(SOURCES) != 8:
        raise SystemExit(f"EXPECTED_8_PREPARED_SOURCES:{len(SOURCES)}")
    httpd = ThreadingHTTPServer(("127.0.0.1", 8878), Handler)
    print(f"http://127.0.0.1:8878/{TOKEN}", flush=True)
    httpd.serve_forever()
