#!/usr/bin/env python3
import contextlib
import io
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "skill" / "scripts"))

import server
from compose_poster import co_brand_template_variant, crop_logo_artwork, slot_box


class LogoTemplateSelectionTests(unittest.TestCase):
    def test_vertical_asset_is_original_svg_and_has_expected_slots(self):
        svg = ROOT / "skill" / "assets" / "fantuan-info-overlay-vertical-1080x1440.svg"
        png = ROOT / "skill" / "assets" / "fantuan-info-overlay-vertical-1080x1440.png"
        root = ET.parse(svg).getroot()
        self.assertEqual(root.get("viewBox"), "0 0 1080 1440")
        self.assertEqual(slot_box(svg, "merchant-logo-slot"), (572, 18, 719, 141))
        self.assertEqual(slot_box(svg, "merchant-name-slot"), (336, 1359, 567, 1393))
        with Image.open(png).convert("RGBA") as overlay:
            self.assertEqual(overlay.size, (1080, 1440))
            self.assertIsNone(overlay.getchannel("A").crop((0, 160, 1080, 1314)).getbbox())

    def test_threshold_uses_cleaned_transparent_content_ratio(self):
        with tempfile.TemporaryDirectory() as directory:
            wide = Path(directory) / "wide.png"
            tall = Path(directory) / "tall.png"
            wide_image = Image.new("RGBA", (400, 300), (0, 0, 0, 0))
            ImageDraw.Draw(wide_image).rectangle((50, 100, 349, 199), fill=(20, 30, 40, 255))
            wide_image.save(wide)
            tall_image = Image.new("RGBA", (400, 300), (0, 0, 0, 0))
            ImageDraw.Draw(tall_image).rectangle((150, 25, 249, 274), fill=(20, 30, 40, 255))
            tall_image.save(tall)

            self.assertEqual(co_brand_template_variant(wide)[:3], ("horizontal", 3.0, "alpha"))
            self.assertEqual(co_brand_template_variant(tall)[:3], ("vertical", 0.4, "alpha"))

    def test_exact_threshold_is_horizontal(self):
        with tempfile.TemporaryDirectory() as directory:
            logo = Path(directory) / "logo.png"
            Image.new("RGBA", (150, 100), (30, 40, 50, 255)).save(logo)
            self.assertEqual(co_brand_template_variant(logo)[0], "horizontal")

    def test_white_background_is_cropped_only_with_strong_edge_evidence(self):
        cautious = Image.new("RGBA", (200, 100), (255, 255, 255, 255))
        ImageDraw.Draw(cautious).rectangle((50, 25, 149, 74), fill=(20, 30, 40, 255))
        cropped, method = crop_logo_artwork(cautious)
        self.assertEqual(method, "white-background")
        self.assertEqual(cropped.size, (100, 50))

        white_brand = Image.new("RGBA", (200, 100), (255, 255, 255, 255))
        ImageDraw.Draw(white_brand).rectangle((0, 45, 199, 54), fill=(20, 30, 40, 255))
        preserved, method = crop_logo_artwork(white_brand)
        self.assertEqual(method, "canvas")
        self.assertEqual(preserved.size, (200, 100))

    def test_compose_logs_selected_variant_and_uses_vertical_template(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / "base.png"
            logo = Path(directory) / "logo.png"
            output = Path(directory) / "output.png"
            Image.new("RGB", (1080, 1440), (237, 242, 240)).save(base)
            Image.new("RGBA", (80, 160), (190, 20, 30, 255)).save(logo)
            log = io.StringIO()
            with contextlib.redirect_stdout(log):
                server.compose_final(base, logo, "茶话弄", "co_brand", output)
            self.assertIn("template_selected=vertical", log.getvalue())
            self.assertIn("threshold=1.5", log.getvalue())
            self.assertTrue(output.is_file())

    def test_fantuan_only_does_not_inspect_or_log_merchant_logo(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / "base.png"
            invalid_logo = Path(directory) / "not-an-image.png"
            output = Path(directory) / "output.png"
            Image.new("RGB", (1080, 1440), (237, 242, 240)).save(base)
            invalid_logo.write_bytes(b"not an image")
            log = io.StringIO()
            with contextlib.redirect_stdout(log):
                server.compose_final(base, invalid_logo, "茶话弄", "fantuan_only", output)
            self.assertNotIn("template_selected", log.getvalue())
            self.assertTrue(output.is_file())


if __name__ == "__main__":
    unittest.main()
