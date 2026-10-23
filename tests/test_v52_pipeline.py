#!/usr/bin/env python3
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
import v52


class V52PipelineTests(unittest.TestCase):
    def test_central_geometry_matches_authoritative_svg_regions(self):
        self.assertEqual(v52.CENTRAL_API_SIZE, (1080, 1215))
        self.assertEqual(v52.CENTRAL_CROP_Y, (30, 1185))
        self.assertEqual(v52.CENTRAL_SIZE, (1080, 1155))
        self.assertEqual(v52.CENTRAL_Y, (160, 1315))
        self.assertAlmostEqual(1155 / 1440, 0.8020833)
        self.assertAlmostEqual(1080 / 1215, 8 / 9)

    def test_outpaint_input_preserves_center_and_uses_transparent_extensions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            central_path, canvas_path = root / "central.png", root / "canvas.png"
            Image.new("RGB", v52.CENTRAL_SIZE, (12, 34, 56)).save(central_path)
            v52.prepare_outpaint_input(central_path, canvas_path)
            with Image.open(canvas_path) as canvas:
                self.assertEqual(canvas.size, v52.FINAL_SIZE)
                self.assertEqual(canvas.getpixel((0, 0))[3], 0)
                self.assertEqual(canvas.getpixel((10, 159))[3], 0)
                self.assertEqual(canvas.getpixel((10, 160)), (12, 34, 56, 255))
                self.assertEqual(canvas.getpixel((10, 1314)), (12, 34, 56, 255))
                self.assertEqual(canvas.getpixel((10, 1315))[3], 0)

    def test_api_central_crop_removes_only_background_buffers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root / "source.png", root / "target.png"
            Image.new("RGB", v52.CENTRAL_API_SIZE, (12, 34, 56)).save(source)
            v52.crop_central_api_image(source, target)
            with Image.open(target) as cropped:
                self.assertEqual(cropped.size, v52.CENTRAL_SIZE)
                self.assertEqual(cropped.getpixel((10, 0)), (12, 34, 56))

    def test_central_prompt_restores_single_three_row_information_panel(self):
        fields = {
            "merchant_name": "澜记",
            "event_date": "10月24日-10月26日",
            "address": "40-33 Main St unit 3",
            "requirements": "评论报名并填写参加时间",
        }
        prompt = v52.build_central_prompt(fields, ["product"])
        self.assertIn("ONE cohesive information box", prompt)
        self.assertIn("exactly three vertically stacked information rows", prompt)
        self.assertIn("activity date, full activity address, complete application rules", prompt)
        self.assertIn("compact audience-facing label on the left", prompt)
        self.assertIn("program must not re-typeset, split, shorten or rearrange", prompt)

    def test_central_prompt_treats_product_background_as_non_authoritative(self):
        prompt = v52.build_central_prompt({"merchant_name": "澜记"}, ["product"])
        self.assertIn("only as a reference for the product subject itself", prompt)
        self.assertIn("Ignore and replace any white, solid-color, photographed or designed background", prompt)
        self.assertIn("must never overwrite, flatten, whiten, frame or otherwise control", prompt)

    def test_outpaint_prompt_rejects_white_from_transparency(self):
        prompt = v52.build_outpaint_prompt()
        self.assertIn("not a request for a white, blank or transparent background", prompt)
        self.assertIn("continue its actual colors and illumination", prompt)


if __name__ == "__main__":
    unittest.main()
