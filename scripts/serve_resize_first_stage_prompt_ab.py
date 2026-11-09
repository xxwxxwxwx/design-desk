#!/usr/bin/env python3
"""Local one-time browser UI for the isolated Resize first-stage A/B run."""
from __future__ import annotations

import html
import json
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
import run_resize_first_stage_prompt_ab as runner  # noqa: E402
import server  # noqa: E402

TOKEN = secrets.token_urlsafe(18)
STATE = {"status": "waiting", "message": "等待输入 Key", "output": None}


def page(message: str = "") -> bytes:
    notice = f"<p class='msg'>{html.escape(message)}</p>" if message else ""
    disabled = "disabled" if STATE["status"] == "running" else ""
    body = f"""<!doctype html><meta charset='utf-8'><title>Resize A/B 安全发起</title>
<style>body{{font:16px -apple-system;margin:40px auto;max-width:680px;color:#18181b}}.card{{padding:28px;border:1px solid #ddd;border-radius:18px}}input[type=password]{{width:100%;box-sizing:border-box;padding:13px;margin:8px 0 18px}}button{{padding:12px 18px;background:#111;color:#fff;border:0;border-radius:10px}}.muted{{color:#666}}.msg{{padding:12px;background:#f4f4f5;border-radius:10px}}</style>
<div class='card'><h1>Resize Prompt A/B</h1><p>只运行第一次 8:9 Layout Adaptation。</p>
<ul><li>福州捞化：A / B 各 1 次</li><li>渔香缘：A / B 各 1 次</li><li>gpt-image-2-5-sunburst-image-to-image，1K，8:9</li><li>预计 6 credits/次，总计 24 credits</li><li>不自动重试，不扩图，不贴品牌</li></ul>{notice}
<form method='post' action='/{TOKEN}'><label>KIE API Key（只保存在本次内存，不写入文件）</label><input type='password' name='key' autocomplete='off' required {disabled}>
<label><input type='checkbox' name='confirm' value='yes' required {disabled}> 我确认最多消耗 24 credits</label><p><button {disabled}>验证并发起 4 次对照</button></p></form>
<p class='muted'>请勿关闭此页面。发起后可刷新查看状态。</p></div>"""
    return body.encode("utf-8")


def run(key: str) -> None:
    try:
        balance = server.validate_api_key(key)
        if balance < 24:
            raise RuntimeError(f"余额不足：{balance:g} credits")
        output, requests = runner.prepare_experiment(ROOT / "data/experiments")
        STATE.update(status="running", message=f"Key 已验证，发起中。当前余额 {balance:g} credits", output=str(output))
        runner.execute(output, requests, key)
        manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        STATE.update(status=manifest["status"], message=f"完成 {manifest.get('completed_calls', 0)}/4 次调用")
    except Exception as exc:
        STATE.update(status="failed", message=str(exc))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != f"/{TOKEN}":
            self.send_error(404)
            return
        payload = page(STATE["message"])
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers(); self.wfile.write(payload)

    def do_POST(self) -> None:
        if self.path != f"/{TOKEN}" or STATE["status"] == "running":
            self.send_error(409)
            return
        length = int(self.headers.get("Content-Length", "0"))
        fields = parse_qs(self.rfile.read(length).decode("utf-8"))
        key = fields.get("key", [""])[0].strip()
        if not key or fields.get("confirm", [""])[0] != "yes":
            payload = page("请输入 Key 并确认 24 credits。")
        else:
            STATE.update(status="running", message="正在验证 Key…")
            threading.Thread(target=run, args=(key,), daemon=True).start()
            payload = page(STATE["message"])
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers(); self.wfile.write(payload)

    def log_message(self, *_: object) -> None:
        return


if __name__ == "__main__":
    httpd = ThreadingHTTPServer(("127.0.0.1", 8877), Handler)
    print(f"http://127.0.0.1:8877/{TOKEN}", flush=True)
    httpd.serve_forever()
