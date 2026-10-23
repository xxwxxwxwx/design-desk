#!/usr/bin/env python3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "skill" / "scripts"))

import server
from compose_poster import (
    BUNDLED_FONT,
    compose,
    fitted_name_font,
    slot_box,
    validate_merchant_name_layout,
)


class MerchantNameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template_svg = ROOT / "skill" / "assets" / "fantuan-info-overlay-1080x1440.svg"
        cls.text_box = slot_box(cls.template_svg, "merchant-name-slot")
        cls.draw = ImageDraw.Draw(Image.new("RGBA", (1080, 1440)))

    def test_prefers_32_px_when_name_fits(self):
        font = fitted_name_font(
            "澜记", self.draw, self.text_box, BUNDLED_FONT, 0, "SemiBold"
        )
        self.assertEqual(font.size, 32)

    def test_shrinks_only_as_needed_and_never_below_24_px(self):
        font = fitted_name_font(
            "WWWWWWWWWW", self.draw, self.text_box, BUNDLED_FONT, 0, "SemiBold"
        )
        self.assertEqual(font.size, 26)

        with self.assertRaisesRegex(ValueError, "24 px"):
            validate_merchant_name_layout(
                "一二三四五六七八九十", self.template_svg, BUNDLED_FONT, 0, "SemiBold"
            )

    def test_unicode_code_points_are_counted_instead_of_utf16_units(self):
        size = validate_merchant_name_layout(
            "😀" * 10, self.template_svg, BUNDLED_FONT, 0, "SemiBold"
        )
        self.assertEqual(size, 32)
        with self.assertRaisesRegex(ValueError, "10 个 Unicode 字符"):
            validate_merchant_name_layout(
                "😀" * 11, self.template_svg, BUNDLED_FONT, 0, "SemiBold"
            )

    def test_dynamic_name_background_does_not_touch_exclusive_svg_boundary(self):
        template = ROOT / "skill" / "assets" / "fixed-overlay-fantuan-only-1080x1440.png"
        with tempfile.TemporaryDirectory() as directory:
            base_path = Path(directory) / "base.png"
            output_path = Path(directory) / "output.png"
            Image.new("RGB", (1080, 1440), (254, 242, 225)).save(base_path)
            compose(
                base_path, None, "茶话弄", template, self.template_svg, output_path,
                BUNDLED_FONT, 0, "SemiBold",
            )
            with Image.open(template).convert("RGBA") as overlay, Image.open(output_path) as output:
                self.assertEqual(output.getpixel((336, 1393)), overlay.getpixel((336, 1393))[:3])

    def test_brand_overlay_preflight_runs_complete_local_composition(self):
        server.preflight_brand_overlay("茶话弄", "fantuan_only", None)

    @patch.object(server, "active_api_key", return_value="test-key")
    @patch.object(server, "preflight_brand_overlay", side_effect=RuntimeError("BRAND_PREFLIGHT_FAILED:test"))
    def test_preflight_failure_stops_before_image_api_call(self, _preflight, _active_api_key):
        fields = {
            "cost_confirmation": "on",
            "merchant_name": "茶话弄",
            "overlay_mode": "fantuan_only",
            "image_roles": '["product"]',
        }
        files = [("images", "product.png", b"not-decoded-before-preflight", "image/png")]
        with patch.object(server, "kie_json_request") as api_call:
            with self.assertRaisesRegex(RuntimeError, "BRAND_PREFLIGHT_FAILED"):
                server.Handler.handle_generation(None, fields, files)
            api_call.assert_not_called()

    @patch.object(server, "active_api_key", return_value="test-key")
    def test_server_rejects_invalid_name_before_image_api_call(self, _active_api_key):
        fields = {
            "cost_confirmation": "on",
            "merchant_name": "一二三四五六七八九十",
            "overlay_mode": "fantuan_only",
            "image_roles": '["product"]',
        }
        files = [("images", "product.png", b"not-decoded-before-preflight", "image/png")]
        with patch.object(server, "kie_json_request") as api_call:
            with self.assertRaisesRegex(RuntimeError, "MERCHANT_NAME_INVALID"):
                server.Handler.handle_generation(None, fields, files)
            api_call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
