#!/usr/bin/env python3
from __future__ import annotations

import base64
import ipaddress
import json
import mimetypes
import os
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from email.parser import BytesParser
from email.policy import default
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from PIL import Image


ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "app" / "static"
SKILL = ROOT / "skill"
JOBS = ROOT / "data" / "jobs"
MAX_REQUEST_BYTES = 120 * 1024 * 1024
MAX_IMAGE_BYTES = 20 * 1024 * 1024
ALLOWED_TYPES = {"image/png", "image/jpeg", "image/webp"}
ROLE_RULES = {
    "product": (
        "REAL PRODUCT. Use this image as the authoritative product reference. "
        "Preserve the product identity, container, packaging, quantity, proportions and distinguishing details. "
        "Do not replace, merge, invent or remove the product."
    ),
    "style_reference": (
        "STYLE REFERENCE. First infer a reusable visual style recipe from this image: its cultural and spatial setting, "
        "background environment, materials and textures, color palette and contrast, typography character, graphic motifs, "
        "lighting, photographic or illustrative treatment, composition rhythm, density and overall energy. "
        "Apply that style recipe consistently across the entire new poster, including its background, atmosphere, typography treatment, "
        "decorative graphics and product presentation. Preserve the reference's recognizable creative identity; do not reduce it to color matching alone. "
        "Transfer the style, not the source content. Do not carry over its specific products, food, drinks, packaging, merchant identity, "
        "logos, words, numbers, prices, promotional claims or event facts. Use the supplied REAL PRODUCT images and LOCKED FACTS as the content authority. "
        "Recompose the style to fit the layout contract: exact source positions are not mandatory, but its overall visual world, "
        "background language and art direction must remain clearly recognizable."
    ),
}
MODEL = os.environ.get("KIE_IMAGE_MODEL", "gpt-image-2-5-sunburst-image-to-image")
KIE_API_ROOT = "https://api.kie.ai"
KIE_UPLOAD_URL = "https://kieai.redpandaai.co/api/file-stream-upload"
PROMPT_VERSION = "2026-10-22-svg-exact-central-outpaint-v5.2"
FREE_CREATION_PROMPT_VERSION = "2026-10-28-free-creation-v1"
GENERATION_PIPELINE_VERSION = "2026-10-22-sunburst-central-outpaint-v5.2"
APP_VERSION = "1.3.0"
STANDARD_RECRUITMENT_VERSION = "5.2.0"
FREE_CREATION_VERSION = "1.0.0"
SIZE_ADAPTATION_VERSION = "0.0.0-unreleased"
SESSION_API_KEY = ""
GENERATION_PROGRESS: dict[str, str] = {}


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


def compose_final(base_path: Path, logo_path: Path | None, merchant_name: str, overlay_mode: str, output_path: Path) -> None:
    sys.path.insert(0, str(SKILL / "scripts"))
    from compose_poster import (  # type: ignore
        BUNDLED_FONT,
        LOGO_TEMPLATE_ASPECT_THRESHOLD,
        co_brand_template_variant,
        compose,
    )

    if overlay_mode == "co_brand":
        if logo_path is None:
            raise ValueError("联名模式缺少商家 Logo。")
        variant, aspect, crop_method, content_size = co_brand_template_variant(logo_path)
        suffix = "" if variant == "horizontal" else "-vertical"
        template_svg = SKILL / "assets" / f"fantuan-info-overlay{suffix}-1080x1440.svg"
        template = SKILL / "assets" / f"fantuan-info-overlay{suffix}-1080x1440.png"
        print(
            "[brand-overlay] "
            f"template_selected={variant} content_aspect_ratio={aspect:.4f} "
            f"threshold={LOGO_TEMPLATE_ASPECT_THRESHOLD:.1f} crop_method={crop_method} "
            f"content_size={content_size[0]}x{content_size[1]}"
        )
    else:
        template_svg = SKILL / "assets" / "fantuan-only-info-overlay-1080x1440.svg"
        template = SKILL / "assets" / "fantuan-only-info-overlay-1080x1440.png"
        logo_path = None
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


def validate_merchant_name(merchant_name: str, overlay_mode: str) -> int:
    """在任何图片 API 调用前，用最终合成所用的真实字体和 SVG 槽位做预检。"""
    scripts_path = str(SKILL / "scripts")
    if scripts_path not in sys.path:
        sys.path.insert(0, scripts_path)
    from compose_poster import BUNDLED_FONT, validate_merchant_name_layout  # type: ignore

    try:
        return validate_merchant_name_layout(
            merchant_name,
            SKILL / "assets" / (
                "fantuan-info-overlay-1080x1440.svg"
                if overlay_mode == "co_brand"
                else "fantuan-only-info-overlay-1080x1440.svg"
            ),
            BUNDLED_FONT,
            font_index=0,
            font_variation="SemiBold",
        )
    except ValueError as exc:
        raise RuntimeError(f"MERCHANT_NAME_INVALID:{exc}") from exc


def preflight_brand_overlay(
    merchant_name: str,
    overlay_mode: str,
    logo: tuple[str, str, bytes, str] | None,
) -> None:
    """付费图片 API 前执行一次完整的本地品牌合成和固定像素校验。"""
    try:
        with tempfile.TemporaryDirectory(prefix="fantuan-brand-preflight-") as directory:
            preflight_dir = Path(directory)
            base_path = preflight_dir / "base.png"
            output_path = preflight_dir / "output.png"
            Image.new("RGB", (1080, 1440), (237, 242, 240)).save(base_path)
            logo_path: Path | None = None
            if logo is not None:
                _, _, payload, content_type = logo
                logo_path = preflight_dir / f"merchant-logo{safe_suffix(content_type)}"
                logo_path.write_bytes(payload)
            compose_final(base_path, logo_path, merchant_name, overlay_mode, output_path)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"BRAND_PREFLIGHT_FAILED:{exc}") from exc


class Handler(SimpleHTTPRequestHandler):
    server_version = f"FantuanPosterWorkbench/{APP_VERSION}"

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
        if self.path.startswith("/api/progress/"):
            progress_id = self.path.split("?", 1)[0].removeprefix("/api/progress/")
            if not progress_id.replace("-", "").isalnum() or progress_id not in GENERATION_PROGRESS:
                self.send_error(404)
                return
            self.send_json(200, {"stage": GENERATION_PROGRESS[progress_id]})
            return
        if self.path == "/api/health":
            required = [
                SKILL / "assets" / "fantuan-only-info-overlay-1080x1440.svg",
                SKILL / "assets" / "fantuan-only-info-overlay-1080x1440.png",
                SKILL / "assets" / "fantuan-info-overlay-1080x1440.svg",
                SKILL / "assets" / "fantuan-info-overlay-1080x1440.png",
                SKILL / "assets" / "fantuan-info-overlay-vertical-1080x1440.svg",
                SKILL / "assets" / "fantuan-info-overlay-vertical-1080x1440.png",
                SKILL / "assets" / "fantuan-lockup-transparent.png",
                SKILL / "assets" / "fonts" / "AlimamaFangYuanTiVF-Thin-2.ttf",
            ]
            self.send_json(200, {
                "status": "ok" if all(path.is_file() for path in required) else "degraded",
                "api_configured": bool(active_api_key()),
                "api_key_source": "session" if SESSION_API_KEY else ("environment" if os.environ.get("KIE_API_KEY", "").strip() else None),
                "model": MODEL,
                "app_version": APP_VERSION,
                "prompt_version": PROMPT_VERSION,
                "free_creation_prompt_version": FREE_CREATION_PROMPT_VERSION,
                "generation_pipeline": GENERATION_PIPELINE_VERSION,
                "module_versions": {
                    "standard_recruitment": STANDARD_RECRUITMENT_VERSION,
                    "free_creation": FREE_CREATION_VERSION,
                    "size_adaptation": SIZE_ADAPTATION_VERSION,
                },
                "validation_status": "test_succeeded",
                "default_generation_mode": "v5.2",
                "paid_calls_per_poster": 2,
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
            progress_id = fields.get("progress_id", "")
            if progress_id:
                GENERATION_PROGRESS[progress_id] = "failed"
            code = str(exc)
            print(f"Generation failed: {code[:1800]}")
            if code == "KIE_API_KEY_MISSING":
                self.send_json(503, {"error": code, "message": "服务端还没有配置 KIE_API_KEY。"})
            elif code.startswith("MERCHANT_NAME_INVALID:"):
                self.send_json(422, {"error": "MERCHANT_NAME_INVALID", "message": code.split(":", 1)[1]})
            elif code.startswith("BRAND_PREFLIGHT_FAILED:"):
                self.send_json(422, {
                    "error": "BRAND_PREFLIGHT_FAILED",
                    "message": "品牌信息条本地预检未通过，尚未调用图片 API。",
                    "detail": code.split(":", 1)[1][:1800],
                })
            elif code.startswith("KIE_"):
                self.send_json(502, {"error": code.split(":", 1)[0], "message": "图片 API 调用失败。", "detail": code[:1800]})
            else:
                self.send_json(422, {"error": code.split(":", 1)[0], "message": "海报处理未通过。", "detail": code[:1800]})
        except Exception as exc:
            progress_id = fields.get("progress_id", "")
            if progress_id:
                GENERATION_PROGRESS[progress_id] = "failed"
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
        progress_id = fields.get("progress_id", "").strip()
        if progress_id and not progress_id.replace("-", "").isalnum():
            raise RuntimeError("PROGRESS_ID_INVALID")
        if progress_id:
            GENERATION_PROGRESS[progress_id] = "creative"
        if not active_api_key():
            raise RuntimeError("KIE_API_KEY_MISSING")
        if fields.get("cost_confirmation") != "on":
            raise RuntimeError("COST_CONFIRMATION_REQUIRED:请先确认本次会调用 2 次付费图片 API。")

        workbench_mode = fields.get("workbench_mode", "standard")
        if workbench_mode not in {"standard", "free_creation"}:
            raise RuntimeError("WORKBENCH_MODE_INVALID")
        creation_method = fields.get("creation_method", "ai_free")
        if workbench_mode == "free_creation" and creation_method not in {"ai_free", "style_reference"}:
            raise RuntimeError("CREATION_METHOD_INVALID")
        references = [item for item in files if item[0] == "images"]
        logos = [item for item in files if item[0] == "merchant_logo"]
        minimum_images = 0 if workbench_mode == "free_creation" else 1
        if not minimum_images <= len(references) <= 9:
            raise RuntimeError("IMAGE_COUNT_INVALID:标准招募模式请上传 1–9 张生成素材。")
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
        validate_merchant_name(merchant_name, overlay_mode)
        if overlay_mode == "co_brand" and len(logos) != 1:
            raise RuntimeError("MERCHANT_LOGO_REQUIRED:联名模式需要一张真实商家 Logo。")
        try:
            roles = json.loads(fields.get("image_roles", "[]"))
        except json.JSONDecodeError as exc:
            raise RuntimeError("IMAGE_ROLES_INVALID") from exc
        if (
            not isinstance(roles, list)
            or len(roles) != len(references)
            or any(not isinstance(role, str) or role not in ROLE_RULES for role in roles)
        ):
            raise RuntimeError("IMAGE_ROLES_INVALID")
        if workbench_mode == "free_creation":
            if not fields.get("headline", "").strip():
                raise RuntimeError("HEADLINE_REQUIRED:自由创作模式必须填写主标题。")
            if creation_method == "ai_free" and any(role != "product" for role in roles):
                raise RuntimeError("AI_FREE_ROLES_INVALID:AI 自由创意模式的上传图片只能标记为真实产品。")
            if creation_method == "style_reference" and "style_reference" not in roles:
                raise RuntimeError("STYLE_REFERENCE_REQUIRED:视觉参考创作必须上传并标记至少一张风格参考图。")

        preflight_brand_overlay(
            merchant_name,
            overlay_mode,
            logos[0] if logos else None,
        )

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

        pipeline_path = str(ROOT / "pipeline")
        if pipeline_path not in sys.path:
            sys.path.insert(0, pipeline_path)
        import v52  # type: ignore

        v52.server.SESSION_API_KEY = active_api_key()
        role_values = [str(role) for role in roles]
        central_prompt = (v52.build_free_creation_prompt(fields, role_values)
                          if workbench_mode == "free_creation" else v52.build_central_prompt(fields, role_values))
        outpaint_prompt = v52.build_outpaint_prompt()
        request_record = {
            "job_id": job_id,
            "created_at": int(time.time()),
            "fields": fields,
            "roles": roles,
            "model": MODEL,
            "generation_mode": "v5.2",
            "workbench_mode": workbench_mode,
            "creation_method": creation_method if workbench_mode == "free_creation" else None,
            "prompt_version": FREE_CREATION_PROMPT_VERSION if workbench_mode == "free_creation" else PROMPT_VERSION,
            "production_ready": True,
            "validation_status": "test_succeeded",
            "generation_pipeline": {
                "version": GENERATION_PIPELINE_VERSION,
                "calls": 2,
                "model": MODEL,
                "resolution_each": "1K",
                "estimated_credits": 12,
                "central_api_ratio": "8:9",
                "central_size": list(v52.CENTRAL_SIZE),
                "central_y": list(v52.CENTRAL_Y),
                "stages": ["central_creative", "crop_background_buffers", "vertical_outpaint", "brand_overlay"],
            },
            "prompts": {"central": central_prompt, "outpaint": outpaint_prompt},
        }
        (job_dir / "request.json").write_text(
            json.dumps(request_record, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        generation_timeout = 600
        central_bytes = v52.call(
            central_prompt,
            stored_images,
            job_id + "-central",
            "8:9",
            timeout_seconds=generation_timeout,
        )
        central_api = job_dir / "central-api.png"
        v52.normalize(central_bytes, central_api, v52.CENTRAL_API_SIZE, 8 / 9)
        central_path = job_dir / "central.png"
        v52.crop_central_api_image(central_api, central_path)
        if progress_id:
            GENERATION_PROGRESS[progress_id] = "outpaint"

        outpaint_input = job_dir / "outpaint-input.png"
        v52.prepare_outpaint_input(central_path, outpaint_input)
        base_bytes = v52.call(
            outpaint_prompt,
            [v52.image_tuple(outpaint_input)],
            job_id + "-outpaint",
            "3:4",
            background="auto",
            timeout_seconds=generation_timeout,
        )
        base_path = job_dir / "generated-base-1080x1440.png"
        v52.normalize(base_bytes, base_path, v52.FINAL_SIZE, 3 / 4)
        if progress_id:
            GENERATION_PROGRESS[progress_id] = "compose"

        final_path = job_dir / "final.png"
        compose_final(base_path, logo_path, merchant_name, overlay_mode, final_path)
        mechanical_metrics = v52.metrics(central_path, base_path)
        (job_dir / "metrics.json").write_text(
            json.dumps(mechanical_metrics, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        with Image.open(final_path) as final_image:
            width, height = final_image.size
        if progress_id:
            GENERATION_PROGRESS[progress_id] = "completed"
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
                "generation_mode": "v5.2",
                "production_ready": True,
                "estimated_credits": 12,
                "mechanical_metrics": mechanical_metrics,
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

