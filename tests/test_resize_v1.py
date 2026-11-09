#!/usr/bin/env python3
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipeline"))

import resize_v1
import server
import v52


def png_bytes(size=(640, 360), color=(24, 88, 120)):
    payload = io.BytesIO()
    Image.new("RGB", size, color).save(payload, "PNG")
    return payload.getvalue()


class ResizeV1Tests(unittest.TestCase):
    def test_two_stage_prompt_requires_real_8x9_adaptation_and_fidelity(self):
        prompt = resize_v1.build_layout_adaptation_prompt(692, 1362)
        self.assertIn("FAITHFUL 8:9 POSTER LAYOUT ADAPTATION", prompt)
        self.assertIn("PRE-GENERATION INTERNAL CONTENT INVENTORY", prompt)
        self.assertIn("punctuation and microtext", prompt)
        self.assertIn("Treat every inventoried item as locked source content", prompt)
        self.assertIn("Do not output the inventory", prompt)
        self.assertIn("genuine layout adaptation", prompt)
        self.assertIn("Use the wider 8:9 canvas deliberately", prompt)
        self.assertIn("Preserve every original title", prompt)
        self.assertIn("merchant logo", prompt)
        self.assertIn("outer 30 px at both top and bottom", prompt)
        self.assertIn("Do not add a new Fantuan logo", prompt)
        self.assertNotIn("background-only extension", prompt.split("REAL 8:9 LAYOUT ADAPTATION", 1)[1])

    def test_single_call_experiment_prompt_targets_full_3_4_and_real_overlay_zones(self):
        prompt = resize_v1.build_single_call_prompt(692, 1362)
        self.assertIn("ONE-CALL FAITHFUL POSTER LAYOUT ADAPTATION", prompt)
        self.assertIn("full 3:4 canvas", prompt)
        self.assertIn("Use the available width deliberately", prompt)
        self.assertIn("visibly cover y=0-159", prompt)
        self.assertIn("y=1315-1439", prompt)
        self.assertIn("ONLY semantic-content box is x=0-1079, y=208-1250", prompt)
        self.assertIn("top exclusion band y=0-207", prompt)
        self.assertIn("bottom exclusion band y=1251-1439", prompt)
        self.assertIn("Preserve every original title", prompt)
        self.assertIn("Preserve every product", prompt)
        self.assertIn("indivisible visual source asset", prompt)
        self.assertIn("source is much narrower than 3:4", prompt)
        self.assertIn("Do not turn a colored or dark design into white", prompt)
        self.assertNotIn("output inside the rectangle will be discarded", prompt)

    def test_single_call_prompt_uses_conservative_near_3_4_strategy(self):
        prompt = resize_v1.build_single_call_prompt(1138, 1300)
        self.assertIn("source is already close to 3:4", prompt)
        self.assertIn("uniform down-scaling and vertical re-spacing", prompt)
        self.assertIn("No shadow, outline, bowl, plate, food edge or logo stroke", prompt)

    def test_single_call_normalization_keeps_generated_artwork_without_source_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = png_bytes((750, 1000))
            result = resize_v1.normalize_single_call_output(payload, root / "raw.png", root / "normalized.png")
            self.assertEqual(result["provider_output_size"], [750, 1000])
            with Image.open(root / "normalized.png") as image:
                self.assertEqual(image.size, (1080, 1440))
                self.assertEqual(image.getpixel((540, 720)), (24, 88, 120))

    def test_single_call_metrics_make_visual_review_boundary_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "result.png"
            Image.new("RGB", (1080, 1440), (24, 88, 120)).save(target)
            report = resize_v1.single_call_mechanical_metrics(target)
            self.assertEqual(report["output_size"], [1080, 1440])
            self.assertIn("all_original_copy_and_prices", report["visual_review_required"])
            self.assertIn("seams_or_stitching", report["visual_review_required"])

    def test_brand_overlay_scope_rejects_any_central_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / "base.png"
            final = root / "final.png"
            Image.new("RGB", (1080, 1440), (10, 20, 30)).save(base)
            Image.new("RGB", (1080, 1440), (10, 20, 30)).save(final)
            report = resize_v1.validate_brand_overlay_scope(base, final)
            self.assertTrue(report["central_pixel_exact"])
            with Image.open(final) as image:
                changed = image.copy()
            changed.putpixel((540, 720), (255, 255, 255))
            changed.save(final)
            with self.assertRaisesRegex(RuntimeError, "RESIZE_BRAND_OVERLAY_TOUCHED_CENTER"):
                resize_v1.validate_brand_overlay_scope(base, final)

    def test_prompt_restricts_ai_to_background_and_declares_local_restore(self):
        prompt = resize_v1.build_outpaint_prompt({"x": 10, "y": 160, "width": 1060, "height": 900})
        self.assertIn("BACKGROUND-ONLY OUTPAINT", prompt)
        self.assertIn("x=10-1069, y=160-1059", prompt)
        self.assertIn("Every visible pixel inside that rectangle is locked", prompt)
        self.assertIn("restore the authoritative source pixels locally", prompt)
        self.assertIn("output inside the rectangle will be discarded", prompt)
        self.assertIn("Generate content only in the transparent area", prompt)
        self.assertIn("Do not replace a colored or dark source background with white", prompt)

    def test_authoritative_canvas_contains_without_crop_and_preserves_ratio(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            Image.new("RGB", (1920, 1080), (12, 34, 56)).save(source)
            placement = resize_v1.prepare_authoritative_canvas(source, root / "canvas.png", root / "authority.png")
            self.assertEqual((placement["width"], placement["height"]), (1080, 608))
            self.assertEqual(placement["x"], 0)
            self.assertGreaterEqual(placement["y"], 160)
            self.assertLessEqual(placement["y"] + placement["height"], 1315)
            self.assertAlmostEqual(placement["source_aspect_ratio"], placement["placed_aspect_ratio"], places=2)
            with Image.open(root / "canvas.png") as canvas:
                self.assertEqual(canvas.size, (1080, 1440))

    def test_local_restore_is_pixel_exact_and_reports_resampling_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            Image.new("RGB", (640, 360), (20, 80, 120)).save(source)
            placement = resize_v1.prepare_authoritative_canvas(source, root / "canvas.png", root / "authority.png")
            Image.new("RGB", (1080, 1440), (21, 81, 121)).save(root / "generated.png")
            resize_v1.restore_authoritative_region(root / "generated.png", root / "authority.png", placement, root / "restored.png")
            report = resize_v1.validate_restored_output(root / "restored.png", root / "authority.png", placement)
            self.assertTrue(report["source_region_pixel_exact"])
            self.assertTrue(report["source_resampled"])
            self.assertEqual(report["pixel_identity_scope"], "resampled_authority")
            self.assertFalse(report["abnormal_white_background"])

    def test_abnormal_white_background_is_rejected_without_white_source_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            Image.new("RGB", (640, 360), (10, 30, 50)).save(source)
            placement = resize_v1.prepare_authoritative_canvas(source, root / "canvas.png", root / "authority.png")
            Image.new("RGB", (1080, 1440), "white").save(root / "generated.png")
            resize_v1.restore_authoritative_region(root / "generated.png", root / "authority.png", placement, root / "restored.png")
            with self.assertRaisesRegex(RuntimeError, "RESIZE_ABNORMAL_WHITE_BACKGROUND"):
                resize_v1.validate_restored_output(root / "restored.png", root / "authority.png", placement)

    def test_resize_requires_exactly_one_source_before_brand_preflight(self):
        fields = {"cost_confirmation": "on", "merchant_name": "茶话弄", "overlay_mode": "fantuan_only"}
        with patch.object(server, "active_api_key", return_value="test-key"), patch.object(server, "preflight_brand_overlay") as preflight:
            with self.assertRaisesRegex(RuntimeError, "SOURCE_POSTER_REQUIRED"):
                server.Handler.handle_resize(None, fields, [])
        preflight.assert_not_called()

    def test_resize_rejects_undecodable_source_without_paid_call(self):
        fields = {"cost_confirmation": "on", "merchant_name": "茶话弄", "overlay_mode": "fantuan_only"}
        files = [("source_poster", "poster.png", b"not-an-image", "image/png")]
        with patch.object(server, "active_api_key", return_value="test-key"), patch.object(server, "preflight_brand_overlay") as preflight:
            with self.assertRaisesRegex(RuntimeError, "SOURCE_POSTER_INVALID"):
                server.Handler.handle_resize(None, fields, files)
        preflight.assert_not_called()

    @patch.object(server, "active_api_key", return_value="test-key")
    @patch.object(server, "preflight_brand_overlay", side_effect=RuntimeError("REACHED_PREFLIGHT"))
    def test_resize_decodes_source_then_runs_brand_preflight(self, _preflight, _active_api_key):
        fields = {"cost_confirmation": "on", "merchant_name": "茶话弄", "overlay_mode": "fantuan_only"}
        files = [("source_poster", "poster.png", png_bytes(), "image/png")]
        with self.assertRaisesRegex(RuntimeError, "REACHED_PREFLIGHT"):
            server.Handler.handle_resize(None, fields, files)

    def test_frontend_exposes_resize_without_original_comparison(self):
        html = (ROOT / "app" / "static" / "index.html").read_text()
        script = (ROOT / "app" / "static" / "app.js").read_text()
        self.assertIn('data-mode="size_adaptation"', html)
        self.assertNotIn('data-mode="size_adaptation" disabled', html)
        self.assertIn('name="source_poster"', html)
        self.assertIn("'/api/resize'", script)
        self.assertIn("resize_prompt_version", script)
        self.assertNotIn("Resize 策略", html)
        self.assertNotIn("原图强制保真（可回退）", html)
        self.assertIn('name="resize_strategy" type="hidden" value="two_stage_layout"', html)
        self.assertNotIn("原图对比", html)
        self.assertNotIn("原海报中的饭团固定信息条会被替换", html)

    def test_health_declares_resize_v1(self):
        self.assertEqual(server.SIZE_ADAPTATION_VERSION, "1.3.0-beta")
        self.assertEqual(server.RESIZE_PROMPT_VERSION, resize_v1.TWO_STAGE_PROMPT_VERSION)

    def test_mock_default_pipeline_calls_ai_twice_and_reuses_second_output_without_center_overwrite(self):
        class ResponseCapture:
            response = None

            def send_json(self, status, value):
                self.response = (status, value)

        central = png_bytes((800, 900), (248, 248, 248))
        outpaint = png_bytes((750, 1000), (120, 20, 30))
        fields = {
            "cost_confirmation": "on", "merchant_name": "茶话弄",
            "overlay_mode": "fantuan_only", "progress_id": "resize-test-1",
        }
        files = [("source_poster", "poster.png", png_bytes(), "image/png")]
        capture = ResponseCapture()
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(server, "JOBS", Path(directory)), \
             patch.object(server, "active_api_key", return_value="test-key"), \
             patch.object(server, "preflight_brand_overlay"), \
             patch.object(v52, "call", side_effect=[central, outpaint]) as call:
            server.Handler.handle_resize(capture, fields, files)
            job_dirs = list(Path(directory).iterdir())
            self.assertEqual(len(job_dirs), 1)
            status = (job_dirs[0] / "status.json").read_text()
            self.assertIn('"status": "completed"', status)
            self.assertTrue((job_dirs[0] / "final.png").is_file())
            metrics = (job_dirs[0] / "metrics.json").read_text()
            self.assertIn('"postprocess_policy": "reuse_normalized_outpaint_result_without_central_overwrite"', metrics)
            self.assertIn('"central_pixel_exact": true', metrics)
            request = (job_dirs[0] / "request.json").read_text()
            self.assertIn('"calls": 2', request)
            self.assertIn('"layout_adaptation_8x9"', request)
            self.assertIn('"reuse_outpaint_result"', request)
            self.assertTrue((job_dirs[0] / "central.png").is_file())
            self.assertTrue((job_dirs[0] / "outpaint-input.png").is_file())
            with Image.open(job_dirs[0] / "generated-base-1080x1440.png") as base:
                self.assertEqual(base.getpixel((540, 720)), (120, 20, 30))
        self.assertEqual(call.call_count, 2)
        self.assertEqual(call.call_args_list[0].args[3], "8:9")
        self.assertEqual(call.call_args_list[1].args[3], "3:4")
        self.assertEqual(capture.response[0], 200)
        self.assertEqual(capture.response[1]["result"]["workbench_mode"], "size_adaptation")
        self.assertEqual(capture.response[1]["result"]["estimated_credits"], 12)
        self.assertEqual(capture.response[1]["result"]["resize_strategy"], "two_stage_layout")
        self.assertNotIn("source_url", capture.response[1]["result"])

    def test_experimental_reflow_calls_source_directly_and_skips_local_restore(self):
        class ResponseCapture:
            response = None
            def send_json(self, status, value):
                self.response = (status, value)

        fields = {
            "cost_confirmation": "on", "merchant_name": "东街口·福州捞化",
            "overlay_mode": "fantuan_only", "resize_strategy": "single_call_reflow",
        }
        files = [("source_poster", "poster.jpg", png_bytes((692, 1362)), "image/jpeg")]
        capture = ResponseCapture()
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(server, "JOBS", Path(directory)), \
             patch.object(server, "active_api_key", return_value="test-key"), \
             patch.object(server, "preflight_brand_overlay"), \
             patch.object(v52, "call", return_value=png_bytes((750, 1000))) as call, \
             patch.object(resize_v1, "restore_authoritative_region") as restore:
            server.Handler.handle_resize(capture, fields, files)
            job = next(Path(directory).iterdir())
            request = (job / "request.json").read_text()
            self.assertIn('"resize_strategy": "single_call_reflow"', request)
            self.assertIn('"experimental": true', request)
            self.assertTrue((job / "single-call.raw.png").is_file())
            self.assertTrue((job / "generated-base-1080x1440.png").is_file())
            self.assertTrue((job / "final.png").is_file())
        self.assertEqual(call.call_count, 1)
        self.assertEqual(call.call_args.args[1][0][1], "source-poster.jpg")
        restore.assert_not_called()
        self.assertEqual(capture.response[1]["result"]["resize_strategy"], "single_call_reflow")


if __name__ == "__main__":
    unittest.main()
