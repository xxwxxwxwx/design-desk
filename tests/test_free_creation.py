#!/usr/bin/env python3
import sys
import unittest
import inspect
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipeline"))
import server
import v52


class FreeCreationTests(unittest.TestCase):
    def test_release_and_three_module_versions_are_explicit(self):
        self.assertEqual(server.APP_VERSION, "1.3.0")
        self.assertEqual(server.STANDARD_RECRUITMENT_VERSION, "5.2.0")
        self.assertEqual(server.FREE_CREATION_VERSION, "1.0.0")
        self.assertEqual(server.SIZE_ADAPTATION_VERSION, "0.0.0-unreleased")
        readme = (ROOT / "README.md").read_text()
        for version in ("1.3.0", "5.2.0", "1.0.0", "0.0.0-unreleased"):
            self.assertIn(version, readme)

    def test_prompt_preserves_copy_and_rejects_invented_marketing_facts(self):
        prompt = v52.build_free_creation_prompt({
            "merchant_name": "澜记", "headline": "今晚就吃这一口",
            "subtitle": "热气腾腾，刚刚好", "creation_method": "ai_free",
        }, [])
        self.assertIn("今晚就吃这一口", prompt)
        self.assertIn("热气腾腾，刚刚好", prompt)
        self.assertIn("Render the supplied headline verbatim", prompt)
        self.assertIn("Never invent prices, discounts, dates, locations", prompt)
        self.assertIn("Do not force an activity-information panel", prompt)

    def test_merchant_name_is_reference_only_unless_user_explicitly_requests_it(self):
        prompt = v52.build_free_creation_prompt({
            "merchant_name": "澜记", "headline": "今晚就吃这一口",
            "subtitle": "热气腾腾，刚刚好", "additional_notes": "突出新品",
            "creation_method": "ai_free",
        }, [])
        locked_copy = prompt.split("LOCKED USER COPY", 1)[1].split("REFERENCE-ONLY MERCHANT IDENTITY", 1)[0]
        self.assertNotIn("澜记", locked_copy)
        self.assertIn("Use the merchant name only to understand brand identity", prompt)
        self.assertIn("Do not add or repeat the merchant name in the creative area", prompt)
        self.assertIn("only when the user explicitly included it", prompt)
        self.assertIn("Never invent, rename, rewrite, abbreviate, translate", prompt)

    def test_ai_freestyle_has_commercial_art_direction_without_fixed_style(self):
        prompt = v52.build_free_creation_prompt({
            "merchant_name": "澜记", "headline": "今晚就吃这一口",
            "creation_method": "ai_free",
        }, ["product"])
        self.assertIn("CREATIVE ART DIRECTION — AI FREESTYLE", prompt)
        self.assertIn("experienced commercial advertising art director", prompt)
        self.assertIn("one coherent creative concept", prompt)
        self.assertIn("intentional color palette", prompt)
        self.assertIn("designed background environment", prompt)
        self.assertIn("commercial photography, editorial design, illustration", prompt)
        self.assertIn("Minimalism and clean backgrounds are allowed", prompt)
        self.assertIn("Avoid generic catalog-style compositions", prompt)
        self.assertIn("independently choose a suitable creative direction", prompt)
        self.assertIn("When no PRODUCT image is supplied", prompt)
        self.assertIn("treat their real appearance as authoritative", prompt)

    def test_product_image_is_truth_first_and_visual_inspiration_second(self):
        for source_description in ("白底产品图", "带场景的产品图"):
            with self.subTest(source=source_description):
                prompt = v52.build_free_creation_prompt({
                    "merchant_name": "澜记", "headline": "新品上线",
                    "additional_notes": source_description, "creation_method": "ai_free",
                }, ["product"])
                self.assertIn("PRODUCT IMAGE — CONTENT AND VISUAL CONTEXT", prompt)
                self.assertIn("primarily as an authoritative reference for the product itself", prompt)
                self.assertIn("secondary inspiration for palette, lighting, materials and atmosphere", prompt)
                self.assertIn("Do not automatically reproduce the original background", prompt)
                self.assertIn("white or transparent product background must not cause", prompt)
                self.assertIn("Do not transfer unrelated text, logos, prices", prompt)

    def test_style_reference_has_priority_for_style_while_product_controls_truth(self):
        prompt = v52.build_free_creation_prompt({
            "merchant_name": "澜记", "headline": "新品上线",
            "creation_method": "style_reference",
        }, ["product", "style_reference"])
        self.assertIn("PRODUCT controls product truth", prompt)
        self.assertIn("STYLE_REFERENCE controls overall visual language", prompt)
        self.assertIn("Transfer the style, not the source content", prompt)

    def test_no_image_prompt_allows_inference_without_claiming_exact_match(self):
        prompt = v52.build_free_creation_prompt({
            "merchant_name": "Monta Tea", "headline": "Monta Tea 新品上线",
            "subtitle": "邀请新品品鉴官",
            "additional_notes": "产品为糯香贝贝南瓜和话梅小番茄",
            "creation_method": "ai_free",
        }, [])
        self.assertIn("create a reasonable product visual", prompt)
        self.assertIn("without inventing packaging, certifications, product effects", prompt)
        self.assertIn("do not claim that the inferred product exactly matches a real product", prompt)

    def test_style_reference_mode_does_not_receive_ai_freestyle_direction(self):
        prompt = v52.build_free_creation_prompt({
            "merchant_name": "澜记", "headline": "今晚就吃这一口",
            "creation_method": "style_reference",
        }, ["style_reference"])
        self.assertNotIn("CREATIVE ART DIRECTION — AI FREESTYLE", prompt)
        self.assertNotIn("Avoid generic catalog-style compositions", prompt)
        self.assertIn("Infer and transfer the supplied STYLE REFERENCE visual language", prompt)

    def test_style_reference_method_requires_reference_role(self):
        fields = {"workbench_mode": "free_creation", "creation_method": "style_reference",
                  "cost_confirmation": "on", "merchant_name": "澜记", "headline": "主标题",
                  "overlay_mode": "fantuan_only", "image_roles": '["product"]'}
        files = [("images", "product.png", b"payload", "image/png")]
        with patch.object(server, "active_api_key", return_value="test-key"):
            with self.assertRaisesRegex(RuntimeError, "STYLE_REFERENCE_REQUIRED"):
                server.Handler.handle_generation(None, fields, files)

    @patch.object(server, "active_api_key", return_value="test-key")
    @patch.object(server, "preflight_brand_overlay", side_effect=RuntimeError("REACHED_PREFLIGHT"))
    def test_ai_free_allows_product_images_and_maps_them_as_product(self, _preflight, _active_api_key):
        fields = {"workbench_mode": "free_creation", "creation_method": "ai_free",
                  "cost_confirmation": "on", "merchant_name": "澜记", "headline": "主标题",
                  "overlay_mode": "fantuan_only", "image_roles": '["product"]'}
        files = [("images", "product.png", b"payload", "image/png")]
        with self.assertRaisesRegex(RuntimeError, "REACHED_PREFLIGHT"):
            server.Handler.handle_generation(None, fields, files)

    @patch.object(server, "active_api_key", return_value="test-key")
    @patch.object(server, "preflight_brand_overlay", side_effect=RuntimeError("REACHED_PREFLIGHT"))
    def test_style_reference_allows_reference_only(self, _preflight, _active_api_key):
        fields = {"workbench_mode": "free_creation", "creation_method": "style_reference",
                  "cost_confirmation": "on", "merchant_name": "澜记", "headline": "主标题",
                  "overlay_mode": "fantuan_only", "image_roles": '["style_reference"]'}
        files = [("images", "reference.png", b"payload", "image/png")]
        with self.assertRaisesRegex(RuntimeError, "REACHED_PREFLIGHT"):
            server.Handler.handle_generation(None, fields, files)

    @patch.object(server, "active_api_key", return_value="test-key")
    @patch.object(server, "preflight_brand_overlay", side_effect=RuntimeError("REACHED_PREFLIGHT"))
    def test_style_reference_allows_product_and_reference_mix(self, _preflight, _active_api_key):
        fields = {"workbench_mode": "free_creation", "creation_method": "style_reference",
                  "cost_confirmation": "on", "merchant_name": "澜记", "headline": "主标题",
                  "overlay_mode": "fantuan_only", "image_roles": '["product", "style_reference"]'}
        files = [("images", "product.png", b"product", "image/png"),
                 ("images", "reference.png", b"reference", "image/png")]
        with self.assertRaisesRegex(RuntimeError, "REACHED_PREFLIGHT"):
            server.Handler.handle_generation(None, fields, files)

    def test_ai_free_rejects_style_reference_role_at_backend(self):
        fields = {"workbench_mode": "free_creation", "creation_method": "ai_free",
                  "cost_confirmation": "on", "merchant_name": "澜记", "headline": "主标题",
                  "overlay_mode": "fantuan_only", "image_roles": '["style_reference"]'}
        files = [("images", "reference.png", b"payload", "image/png")]
        with patch.object(server, "active_api_key", return_value="test-key"):
            with self.assertRaisesRegex(RuntimeError, "AI_FREE_ROLES_INVALID"):
                server.Handler.handle_generation(None, fields, files)

    @patch.object(server, "active_api_key", return_value="test-key")
    @patch.object(server, "preflight_brand_overlay", side_effect=RuntimeError("REACHED_PREFLIGHT"))
    def test_ai_free_allows_no_product_image(self, _preflight, _active_api_key):
        fields = {"workbench_mode": "free_creation", "creation_method": "ai_free",
                  "cost_confirmation": "on", "merchant_name": "澜记", "headline": "主标题",
                  "overlay_mode": "fantuan_only", "image_roles": '[]'}
        with self.assertRaisesRegex(RuntimeError, "REACHED_PREFLIGHT"):
            server.Handler.handle_generation(None, fields, [])

    def test_frontend_free_section_has_no_structured_activity_fields(self):
        html = (ROOT / "app" / "static" / "index.html").read_text()
        free_section = html.split('id="freeFields"', 1)[1].split("</section>", 1)[0]
        for field in ("event_date", "address", "recruitment_count", "offer", "requirements"):
            self.assertNotIn(field, free_section)
        self.assertIn('name="free_headline"', free_section)
        self.assertIn('name="free_subtitle"', free_section)

    def test_frontend_blocks_free_creation_against_stale_backend(self):
        script = (ROOT / "app" / "static" / "app.js").read_text()
        self.assertIn("free_creation_prompt_version", script)
        self.assertIn("if (free && !freeCreationBackendReady)", script)
        self.assertIn("本次未发起图片 API 调用", script)

    def test_frontend_locks_ai_free_uploads_to_product_and_keeps_reference_selectors(self):
        html = (ROOT / "app" / "static" / "index.html").read_text()
        script = (ROOT / "app" / "static" / "app.js").read_text()
        self.assertIn('id="dropzoneTitle"', html)
        self.assertIn("dropzoneTitle.textContent = aiFreestyle ? '上传产品图'", script)
        self.assertIn("if (aiFreestyle) asset.role = 'product'", script)
        self.assertIn("assets.map(() => 'product')", script)
        self.assertIn("<select aria-label=", script)
        self.assertIn("creationMethod === 'style_reference'", script)
        self.assertIn('id="additionalNotes"', html)
        self.assertIn("可填写产品名称、希望展示的信息或视觉要求", script)

    def test_standard_prompt_does_not_receive_free_product_context_rules(self):
        prompt = v52.build_central_prompt({"merchant_name": "澜记"}, ["product"])
        self.assertNotIn("PRODUCT IMAGE — CONTENT AND VISUAL CONTEXT", prompt)
        self.assertNotIn("PRODUCT controls product truth", prompt)

    def test_free_prompt_does_not_request_standard_information_panel(self):
        prompt = v52.build_free_creation_prompt({
            "merchant_name": "去青山", "headline": "Monta Tea 新品上线",
            "subtitle": "邀请新品品鉴官", "creation_method": "style_reference",
        }, ["style_reference"])
        self.assertNotIn("exactly three vertically stacked information rows", prompt)
        self.assertNotIn("activity date, full activity address", prompt)
        self.assertNotIn("merchant recruitment creative", prompt)

    def test_both_generation_stages_use_ten_minute_timeout_for_all_modes(self):
        source = inspect.getsource(server.Handler.handle_generation)
        self.assertIn("generation_timeout = 600", source)
        self.assertEqual(source.count("timeout_seconds=generation_timeout"), 2)
        self.assertNotIn("if workbench_mode == \"free_creation\" else 360", source)


if __name__ == "__main__":
    unittest.main()
