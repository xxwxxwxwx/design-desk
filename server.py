#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import mimetypes
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from email.parser import BytesParser
from email.policy import default
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "app" / "static"
SKILL = ROOT / "skill"
JOBS = ROOT / "data" / "jobs"
MAX_REQUEST_BYTES = 120 * 1024 * 1024
MAX_IMAGE_BYTES = 20 * 1024 * 1024
ALLOWED_TYPES = {"image/png", "image/jpeg", "image/webp"}
MODEL = os.environ.get("KIE_IMAGE_MODEL", "gpt-image-2-5-sunburst-image-to-image")
KIE_API_ROOT = "https://api.kie.ai"
KIE_UPLOAD_URL = "https://kieai.redpandaai.co/api/file-stream-upload"
SESSION_API_KEY = ""


def active_api_key() -> str:
    return SESSION_API_KEY or os.environ.get("KIE_API_KEY", "").strip()


def kie_error_message(status: int, detail: str) -> str:
    try:
        payload = json.loads(detail)
        api_message = str(payload.get("error", {}).get("message", "")).strip()
    except (json.JSONDecodeError, AttributeError, TypeError):
        api_message = ""
    if status == 401:
        return "KIE API Key 无效或已失效，请检查后重新填写。"
    if status == 403:
        return "这个 KIE API Key 没有访问图片模型的权限。"
    if status == 429:
        return "KIE 积分或速率限制不足，请检查 KIE 账户。"
    return api_message or f"KIE API 返回错误（HTTP {status}）。"


def validate_api_key(api_key: str) -> float:
    request = urllib.request.Request(
        f"{KIE_API_ROOT}/api/v1/chat/credit",
        headers={"Authorization": f"Bearer {api_key}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:2000]
        raise RuntimeError(f"KIE_KEY_ERROR:{kie_error_message(exc.code, detail)}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"KIE_KEY_ERROR:无法连接 KIE API：{exc.reason}") from exc
    if int(payload.get("code", 0)) != 200:
        raise RuntimeError(f"KIE_KEY_ERROR:{payload.get('msg') or 'KIE API Key 验证失败。'}")
    return float(payload.get("data", 0))


def json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def safe_suffix(content_type: str) -> str:
    return {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}[content_type]


def multipart_body(fields: dict[str, str], images: list[tuple[str, str, bytes, str]]) -> tuple[bytes, str]:
    boundary = f"----FantuanPoster{secrets.token_hex(16)}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            value.encode("utf-8"),
            b"\r\n",
        ])
    for field_name, filename, payload, content_type in images:
        cleaned = Path(filename).name.replace('"', "") or f"image{safe_suffix(content_type)}"
        chunks.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{field_name}"; filename="{cleaned}"\r\n'.encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            payload,
            b"\r\n",
        ])
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), boundary


def prompt_for(form: dict[str, str], roles: list[str]) -> str:
    image_lines = "\n".join(
        f"- Image {index + 1}: {role}. Preserve any real product identity, container, packaging, quantity and aspect ratio."
        for index, role in enumerate(roles)
    )
    facts = [
        ("商家名称", form.get("merchant_name")),
        ("招募类型", form.get("recruitment_type")),
        ("主标题", form.get("headline") or "根据招募类型自动生成，不得添加未提供事实"),
        ("招募人数", form.get("recruitment_count")),
        ("活动时间", form.get("event_date")),
        ("活动地址", form.get("address")),
        ("体验内容或福利", form.get("offer")),
        ("报名条件", form.get("requirements")),
        ("报名方式", form.get("registration")),
        ("通知说明", form.get("notice")),
        ("风格方向", form.get("style")),
        ("重点突出", form.get("emphasis")),
        ("其他要求", form.get("additional_notes")),
    ]
    facts_text = "\n".join(f"- {label}：{value}" for label, value in facts if value)
    return f"""
Create one polished Chinese Xiaohongshu merchant recruitment poster. This is a production poster, not a mockup.

CANVAS AND RESERVED AREAS
- Portrait 1088x1440. The server will crop 4 pixels from each side to 1080x1440.
- Keep the top 160 pixels and bottom 126 pixels as natural, continuous background only.
- No text, products, logos, frames, panels, badges, borders, or placeholders may enter those reserved areas.
- Keep important content at least 60 pixels from the left and right edges.

LOCKED FACTS
{facts_text}

INPUT IMAGE ROLES
{image_lines}

DESIGN REQUIREMENTS
- Reading order: recruitment headline, key offer, real products, activity details.
- Use the uploaded product images as the only authority for actual products.
- Keep products proportional. Never widen, flatten, replace, merge, invent or remove products.
- Style references provide mood and layout only. Never copy their old prices, products, logos or event copy.
- Render all supplied Chinese, numbers, dates, address and punctuation exactly. Do not invent missing facts.
- Do not generate Fantuan branding, merchant logos, co-brand panels, a search bar, safe-area guides, or logo placeholders. The server will add authentic fixed branding later.
- Deliver a cohesive commercial raster poster with integrated products and lighting, not a collage of rectangular screenshots.
""".strip()


def kie_json_request(url: str, api_key: str, method: str = "GET", payload: dict[str, Any] | None = None, timeout: int = 60) -> dict[str, Any]:
    body = json_bytes(payload) if payload is not None else None
    headers = {"Authorization": f"Bearer {api_key}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:2000]
        raise RuntimeError(f"KIE_API_ERROR:{exc.code}:{kie_error_message(exc.code, detail)}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"KIE_NETWORK_ERROR:{exc.reason}") from exc
    code = int(result.get("code", 200 if result.get("success") else 0))
    if code != 200:
        raise RuntimeError(f"KIE_API_ERROR:{code}:{result.get('msg') or 'KIE 请求失败。'}")
    return result


def upload_to_kie(api_key: str, filename: str, payload: bytes, content_type: str, upload_token: str) -> str:
    fields = {"uploadPath": f"images/fantuan-poster/{upload_token}", "fileName": Path(filename).name}
    body, boundary = multipart_body(fields, [("file", filename, payload, content_type)])
    request = urllib.request.Request(
        KIE_UPLOAD_URL,
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:2000]
        raise RuntimeError(f"KIE_UPLOAD_ERROR:{exc.code}:{kie_error_message(exc.code, detail)}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"KIE_UPLOAD_ERROR:无法上传素材：{exc.reason}") from exc
    if int(result.get("code", 0)) != 200 or not result.get("data", {}).get("downloadUrl"):
        raise RuntimeError(f"KIE_UPLOAD_ERROR:{result.get('msg') or '素材上传失败。'}")
    return str(result["data"]["downloadUrl"])


def call_kie(prompt: str, images: list[tuple[str, str, bytes, str]], task_token: str) -> bytes:
    api_key = active_api_key()
    if not api_key:
        raise RuntimeError("KIE_API_KEY_MISSING")
    input_urls = [upload_to_kie(api_key, filename, payload, content_type, task_token) for _, filename, payload, content_type in images]
    created = kie_json_request(
        f"{KIE_API_ROOT}/api/v1/jobs/createTask",
        api_key,
        method="POST",
        payload={
            "model": MODEL,
            "input": {
                "prompt": prompt,
                "input_urls": input_urls,
                "aspect_ratio": "3:4",
                "resolution": "1K",
                "background": "opaque",
            },
        },
    )
    task_id = str(created.get("data", {}).get("taskId", ""))
    if not task_id:
        raise RuntimeError("KIE_INVALID_RESPONSE:没有返回 taskId。")
    delay = 2.0
    deadline = time.monotonic() + 360
    while time.monotonic() < deadline:
        time.sleep(delay)
        status = kie_json_request(f"{KIE_API_ROOT}/api/v1/jobs/recordInfo?taskId={task_id}", api_key)
        data = status.get("data", {})
        state = data.get("state")
        if state == "fail":
            raise RuntimeError(f"KIE_GENERATION_FAILED:{data.get('failMsg') or data.get('failCode') or '生成失败。'}")
        if state == "success":
            try:
                result_json = json.loads(data.get("resultJson") or "{}")
                result_url = result_json["resultUrls"][0]
                with urllib.request.urlopen(result_url, timeout=120) as response:
                    return response.read()
            except (json.JSONDecodeError, KeyError, IndexError, TypeError, urllib.error.URLError) as exc:
                raise RuntimeError("KIE_INVALID_RESPONSE:任务成功但无法下载结果。") from exc
        delay = min(delay * 1.35, 8.0)
    raise RuntimeError("KIE_TIMEOUT:生成超过 6 分钟，请稍后重试。")


def normalize_generated(source: Path, target: Path) -> None:
    with Image.open(source) as image:
        image = image.convert("RGB")
        if image.size == (1088, 1440):
            image = image.crop((4, 0, 1084, 1440))
        elif image.size != (1080, 1440):
            ratio = image.width / image.height
            if not 0.73 <= ratio <= 0.78:
                raise RuntimeError(f"GENERATED_RATIO_INVALID:{image.width}x{image.height}")
            image = ImageOps.fit(image, (1080, 1440), method=Image.Resampling.LANCZOS)
        image.save(target, "PNG", optimize=True)


def compose_final(base_path: Path, logo_path: Path | None, merchant_name: str, overlay_mode: str, output_path: Path) -> None:
    sys.path.insert(0, str(SKILL / "scripts"))
    from compose_poster import BUNDLED_FONT, compose  # type: ignore

    template_svg = SKILL / "assets" / "fantuan-info-overlay-1080x1440.svg"
    template = SKILL / "assets" / (
        "fantuan-info-overlay-1080x1440.png" if overlay_mode == "co_brand"
        else "fixed-overlay-fantuan-only-1080x1440.png"
    )
    compose(
        base_path=base_path,
        logo_path=logo_path,
        merchant_name=merchant_name,
        template_path=template,
        template_svg_path=template_svg,
        output_path=output_path,
        font_path=BUNDLED_FONT,
        font_index=0,
        font_variation="SemiBold",
    )
    completed = subprocess.run(
        [
            sys.executable,
            str(SKILL / "scripts" / "validate_output.py"),
            "--output", str(output_path),
            "--template", str(template),
            "--template-svg", str(template_svg),
            "--base", str(base_path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"OVERLAY_VALIDATION_FAILED:{completed.stderr or completed.stdout}")


class Handler(SimpleHTTPRequestHandler):
    server_version = "FantuanPosterWorkbench/0.1"

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")

    def send_json(self, status: int, value: Any) -> None:
        payload = json_bytes(value)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if self.path == "/api/health":
            required = [
                SKILL / "assets" / "fixed-overlay-blank-1080x1440.png",
                SKILL / "assets" / "fixed-overlay-fantuan-only-1080x1440.png",
                SKILL / "assets" / "fantuan-info-overlay-1080x1440.svg",
                SKILL / "assets" / "fantuan-info-overlay-1080x1440.png",
                SKILL / "assets" / "fonts" / "AlimamaFangYuanTiVF-Thin-2.ttf",
            ]
            self.send_json(200, {
                "status": "ok" if all(path.is_file() for path in required) else "degraded",
                "api_configured": bool(active_api_key()),
                "api_key_source": "session" if SESSION_API_KEY else ("environment" if os.environ.get("KIE_API_KEY", "").strip() else None),
                "model": MODEL,
                "skill_assets_ready": all(path.is_file() for path in required),
            })
            return
        if self.path.startswith("/api/jobs/"):
            parts = self.path.split("?")[0].strip("/").split("/")
            if len(parts) == 4 and parts[:2] == ["api", "jobs"] and parts[3] in {"image", "download"}:
                job_id = parts[2]
                if not job_id.replace("-", "").isalnum():
                    self.send_error(404)
                    return
                output = JOBS / job_id / "final.png"
                if not output.is_file():
                    self.send_error(404)
                    return
                payload = output.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(payload)))
                if parts[3] == "download":
                    self.send_header("Content-Disposition", f'attachment; filename="fantuan-poster-{job_id}.png"')
                self.end_headers()
                self.wfile.write(payload)
                return
        path = self.path.split("?", 1)[0]
        if path == "/":
            path = "/index.html"
        target = (STATIC / path.lstrip("/")).resolve()
        if STATIC.resolve() not in target.parents or not target.is_file():
            self.send_error(404)
            return
        payload = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:
        if self.path == "/api/settings/api-key":
            self.handle_api_key_setting()
            return
        if self.path != "/api/generate":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0 or length > MAX_REQUEST_BYTES:
            self.send_json(413, {"error": "REQUEST_TOO_LARGE", "message": "请求为空或超过 120 MB。"})
            return
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            self.send_json(415, {"error": "INVALID_CONTENT_TYPE", "message": "请使用表单和图片提交。"})
            return
        message = BytesParser(policy=default).parsebytes(
            b"Content-Type: " + content_type.encode() + b"\r\nMIME-Version: 1.0\r\n\r\n" + self.rfile.read(length)
        )
        fields: dict[str, str] = {}
        files: list[tuple[str, str, bytes, str]] = []
        for part in message.iter_parts():
            name = part.get_param("name", header="content-disposition")
            filename = part.get_filename()
            if not name:
                continue
            payload = part.get_payload(decode=True) or b""
            if filename:
                files.append((name, filename, payload, part.get_content_type()))
            else:
                fields[name] = payload.decode(part.get_content_charset() or "utf-8", "replace")
        try:
            self.handle_generation(fields, files)
        except RuntimeError as exc:
            code = str(exc)
            print(f"Generation failed: {code[:1800]}")
            if code == "KIE_API_KEY_MISSING":
                self.send_json(503, {"error": code, "message": "服务端还没有配置 KIE_API_KEY。"})
            elif code.startswith("KIE_"):
                self.send_json(502, {"error": code.split(":", 1)[0], "message": "图片 API 调用失败。", "detail": code[:1800]})
            else:
                self.send_json(422, {"error": code.split(":", 1)[0], "message": "海报处理未通过。", "detail": code[:1800]})
        except Exception as exc:
            self.send_json(500, {"error": "INTERNAL_ERROR", "message": "服务器处理失败。", "detail": str(exc)[:1000]})

    def handle_api_key_setting(self) -> None:
        global SESSION_API_KEY
        try:
            if not ipaddress.ip_address(self.client_address[0]).is_loopback:
                self.send_json(403, {"error": "LOCAL_ONLY", "message": "API Key 只能在本机配置。"})
                return
        except ValueError:
            self.send_json(403, {"error": "LOCAL_ONLY", "message": "API Key 只能在本机配置。"})
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0 or length > 16 * 1024 or self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
            self.send_json(400, {"error": "INVALID_REQUEST", "message": "无法读取 API Key。"})
            return
        try:
            payload = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_json(400, {"error": "INVALID_JSON", "message": "无法读取 API Key。"})
            return
        key = str(payload.get("api_key", "")).strip()
        if key and (len(key) < 20 or any(char.isspace() for char in key)):
            self.send_json(422, {"error": "INVALID_API_KEY_FORMAT", "message": "API Key 格式不正确。"})
            return
        if key:
            try:
                validate_api_key(key)
            except RuntimeError as exc:
                self.send_json(422, {"error": "KIE_KEY_ERROR", "message": str(exc).split(":", 1)[-1]})
                return
        SESSION_API_KEY = key
        self.send_json(200, {"status": "configured" if key else "cleared", "api_configured": bool(key), "provider": "KIE"})

    def handle_generation(self, fields: dict[str, str], files: list[tuple[str, str, bytes, str]]) -> None:
        if not active_api_key():
            raise RuntimeError("KIE_API_KEY_MISSING")
        if fields.get("cost_confirmation") != "on":
            raise RuntimeError("COST_CONFIRMATION_REQUIRED:请先确认本次会调用付费图片 API。")
        references = [item for item in files if item[0] == "images"]
        logos = [item for item in files if item[0] == "merchant_logo"]
        if not 1 <= len(references) <= 9:
            raise RuntimeError("IMAGE_COUNT_INVALID:请上传 1–9 张生成素材。")
        for _, _, payload, content_type in references + logos:
            if content_type not in ALLOWED_TYPES:
                raise RuntimeError(f"IMAGE_TYPE_INVALID:{content_type}")
            if not payload or len(payload) > MAX_IMAGE_BYTES:
                raise RuntimeError("IMAGE_SIZE_INVALID:单张图片必须小于 20 MB。")
        merchant_name = fields.get("merchant_name", "").strip()
        if not merchant_name:
            raise RuntimeError("MERCHANT_NAME_REQUIRED")
        overlay_mode = fields.get("overlay_mode", "co_brand")
        if overlay_mode not in {"co_brand", "fantuan_only"}:
            raise RuntimeError("OVERLAY_MODE_INVALID")
        if overlay_mode == "co_brand" and len(logos) != 1:
            raise RuntimeError("MERCHANT_LOGO_REQUIRED:联名模式需要一张真实商家 Logo。")
        try:
            roles = json.loads(fields.get("image_roles", "[]"))
        except json.JSONDecodeError as exc:
            raise RuntimeError("IMAGE_ROLES_INVALID") from exc
        if not isinstance(roles, list) or len(roles) != len(references):
            raise RuntimeError("IMAGE_ROLES_INVALID")

        job_id = time.strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(4)
        job_dir = JOBS / job_id
        job_dir.mkdir(parents=True, exist_ok=False)
        stored_images: list[tuple[str, str, bytes, str]] = []
        for index, (_, filename, payload, content_type) in enumerate(references, start=1):
            target = job_dir / f"input-{index:02d}{safe_suffix(content_type)}"
            target.write_bytes(payload)
            stored_images.append(("images", filename, payload, content_type))
        logo_path: Path | None = None
        if logos:
            _, _, payload, content_type = logos[0]
            logo_path = job_dir / f"merchant-logo{safe_suffix(content_type)}"
            logo_path.write_bytes(payload)

        prompt = prompt_for(fields, [str(role) for role in roles])
        request_record = {"job_id": job_id, "created_at": int(time.time()), "fields": fields, "roles": roles, "model": MODEL}
        (job_dir / "request.json").write_text(json.dumps(request_record, ensure_ascii=False, indent=2), encoding="utf-8")
        generated_bytes = call_kie(prompt, stored_images, job_id)
        raw_path = job_dir / "generated-raw.png"
        raw_path.write_bytes(generated_bytes)
        base_path = job_dir / "generated-base-1080x1440.png"
        normalize_generated(raw_path, base_path)
        final_path = job_dir / "final.png"
        compose_final(base_path, logo_path, merchant_name, overlay_mode, final_path)
        with Image.open(final_path) as final_image:
            width, height = final_image.size
        self.send_json(200, {
            "job_id": job_id,
            "status": "completed",
            "result": {
                "image_url": f"/api/jobs/{job_id}/image",
                "download_url": f"/api/jobs/{job_id}/download",
                "width": width,
                "height": height,
                "format": "png",
                "mechanical_validation": "passed",
                "visual_review": "pending",
            },
        })


def main() -> None:
    JOBS.mkdir(parents=True, exist_ok=True)
    host = os.environ.get("POSTER_HOST", "127.0.0.1")
    port = int(os.environ.get("POSTER_PORT", "8788"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"饭团小红书海报工作台：http://{host}:{port}")
    print(f"图片 API：{'READY' if active_api_key() else 'NOT CONFIGURED'}")
    server.serve_forever()


if __name__ == "__main__":
    main()

