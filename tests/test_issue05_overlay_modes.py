#!/usr/bin/env python3
import hashlib
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import server


class Issue05OverlayModeTests(unittest.TestCase):
    def test_single_logo_asset_is_the_supplied_svg_and_has_required_structure(self):
        svg = ROOT / "skill" / "assets" / "fantuan-only-info-overlay-1080x1440.svg"
        png = ROOT / "skill" / "assets" / "fantuan-only-info-overlay-1080x1440.png"
        self.assertEqual(
            hashlib.sha256(svg.read_bytes()).hexdigest(),
            "8416f1b348513d615e13a6389ba352e8dc128c55e8dbb4328346799e77883088",
        )
        root = ET.parse(svg).getroot()
        self.assertEqual(root.get("viewBox"), "0 0 1080 1440")
        self.assertEqual((root.get("width"), root.get("height")), ("1080", "1440"))
        ids = {element.get("id") for element in root.iter()}
        self.assertIn("fantuan-logo", ids)
        self.assertIn("merchant-name-slot", ids)
        self.assertNotIn("merchant-logo-slot", ids)
        with Image.open(png).convert("RGBA") as overlay:
            self.assertEqual(overlay.size, (1080, 1440))
            self.assertIsNone(overlay.getchannel("A").crop((0, 160, 1080, 1314)).getbbox())

    def test_each_mode_uses_its_own_template_and_single_mode_ignores_logo(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / "base.png"
            fake_logo = Path(directory) / "merchant.png"
            single = Path(directory) / "single.png"
            dual = Path(directory) / "dual.png"
            Image.new("RGB", (1080, 1440), (237, 242, 240)).save(base)
            Image.new("RGBA", (80, 40), (200, 30, 30, 255)).save(fake_logo)
            server.compose_final(base, fake_logo, "茶话弄", "fantuan_only", single)
            server.compose_final(base, fake_logo, "茶话弄", "co_brand", dual)
            with Image.open(single) as single_image, Image.open(dual) as dual_image:
                self.assertEqual(single_image.size, (1080, 1440))
                self.assertEqual(dual_image.size, (1080, 1440))
                self.assertNotEqual(single_image.tobytes(), dual_image.tobytes())

    @patch.object(server, "active_api_key", return_value="test-key")
    @patch.object(server, "preflight_brand_overlay", side_effect=RuntimeError("REACHED_PREFLIGHT"))
    def test_single_mode_without_merchant_logo_is_not_rejected(self, _preflight, _active_api_key):
        fields = {
            "cost_confirmation": "on",
            "merchant_name": "茶话弄",
            "overlay_mode": "fantuan_only",
            "image_roles": '["product"]',
        }
        files = [("images", "product.png", b"payload", "image/png")]
        with self.assertRaisesRegex(RuntimeError, "REACHED_PREFLIGHT"):
            server.Handler.handle_generation(None, fields, files)

    @patch.object(server, "active_api_key", return_value="test-key")
    @patch.object(server, "preflight_brand_overlay")
    def test_dual_mode_still_requires_one_merchant_logo(self, preflight, _active_api_key):
        fields = {
            "cost_confirmation": "on",
            "merchant_name": "茶话弄",
            "overlay_mode": "co_brand",
            "image_roles": '["product"]',
        }
        files = [("images", "product.png", b"payload", "image/png")]
        with self.assertRaisesRegex(RuntimeError, "MERCHANT_LOGO_REQUIRED"):
            server.Handler.handle_generation(None, fields, files)
        preflight.assert_not_called()

    def test_frontend_copy_and_conditional_required_state(self):
        html = (ROOT / "app" / "static" / "index.html").read_text()
        js = (ROOT / "app" / "static" / "app.js").read_text()
        self.assertIn("仅饭团 Logo", html)
        self.assertIn("饭团 + 商家 Logo", html)
        self.assertIn("merchantLogo.required = required", js)
        self.assertIn("logoField.hidden = !required", js)
        self.assertIn("if (overlayMode.value === 'co_brand' && !merchantLogo.files[0])", js)


if __name__ == "__main__":
    unittest.main()
