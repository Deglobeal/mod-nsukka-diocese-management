import base64
import builtins
import os
import tempfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from PIL import Image, ImageDraw

import apps.members.passport_photo_processing as passport_processing
from apps.members.passport_photo_processing import process_passport_photo


class PassportPhotoProcessingTests(SimpleTestCase):
    def make_input_jpeg(self):
        buffer = BytesIO()
        image = Image.new("RGB", (120, 120), (80, 100, 120))
        draw = ImageDraw.Draw(image)
        draw.rectangle((35, 20, 85, 100), fill=(180, 40, 40))
        image.save(buffer, format="JPEG")
        return buffer.getvalue()

    def test_background_is_composited_to_white(self):
        foreground = Image.new("RGBA", (120, 120), (0, 0, 0, 0))
        draw = ImageDraw.Draw(foreground)
        draw.rectangle((35, 20, 85, 100), fill=(180, 40, 40, 255))

        with patch(
            "apps.members.passport_photo_processing._predict_foreground_mask",
            return_value=foreground.getchannel("A"),
        ):
            result = process_passport_photo(self.make_input_jpeg())

        with Image.open(BytesIO(result)) as processed:
            self.assertEqual(processed.format, "JPEG")
            self.assertEqual(processed.size, (120, 120))
            self.assertEqual(processed.getpixel((5, 5)), (255, 255, 255))

            red, green, blue = processed.getpixel((60, 60))
            self.assertGreater(red, 130)
            self.assertLess(green, 90)
            self.assertLess(blue, 90)

    def test_transparent_rembg_cutout_is_composited_to_opaque_white_jpeg(self):
        foreground = Image.new("RGBA", (120, 120), (0, 0, 0, 0))
        ImageDraw.Draw(foreground).rectangle(
            (35, 20, 85, 100), fill=(180, 40, 40, 255)
        )

        with (
            patch(
                "apps.members.passport_photo_processing._predict_foreground_mask",
                return_value=foreground.getchannel("A"),
            ),
            patch("rembg.bg.decontaminate_cutout", return_value=foreground),
        ):
            result = process_passport_photo(self.make_input_jpeg())

        with Image.open(BytesIO(result)) as processed:
            self.assertEqual(processed.format, "JPEG")
            self.assertEqual(processed.mode, "RGB")
            self.assertEqual(processed.getpixel((5, 5)), (255, 255, 255))

    def test_unsupported_image_format_is_rejected_before_model_inference(self):
        buffer = BytesIO()
        Image.new("RGB", (120, 120), "blue").save(buffer, format="GIF")

        with patch(
            "apps.members.passport_photo_processing._predict_foreground_mask"
        ) as infer:
            with self.assertRaisesRegex(ValidationError, "JPEG or PNG"):
                process_passport_photo(buffer.getvalue())
        infer.assert_not_called()

    def test_empty_input_is_rejected(self):
        with self.assertRaises(ValidationError):
            process_passport_photo(b"")

    def test_invalid_image_is_rejected(self):
        with self.assertRaises(ValidationError):
            process_passport_photo(b"not an image")

    def test_missing_model_returns_retryable_error_and_logs_diagnostics(self):
        with (
            patch.object(passport_processing, "_session", None),
            patch.object(
                passport_processing,
                "_model_path",
                side_effect=FileNotFoundError("model unavailable"),
            ),
            self.assertLogs(passport_processing.logger, level="ERROR"),
        ):
            with self.assertRaisesRegex(
                ValidationError, "temporarily unavailable.*retry"
            ):
                passport_processing._get_session()

    def test_model_initialization_failure_returns_retryable_error(self):
        with (
            patch.object(passport_processing, "_session", None),
            patch.object(passport_processing, "_model_path", return_value=Path("model.onnx")),
            patch("onnxruntime.InferenceSession", side_effect=RuntimeError("bad model")),
            self.assertLogs(passport_processing.logger, level="ERROR"),
        ):
            with self.assertRaisesRegex(
                ValidationError, "temporarily unavailable.*retry"
            ):
                passport_processing._get_session()

    def test_missing_rembg_dependency_is_not_treated_as_success(self):
        original_import = builtins.__import__

        def import_without_rembg(name, *args, **kwargs):
            if name == "rembg.bg":
                raise ModuleNotFoundError("No module named 'rembg'")
            return original_import(name, *args, **kwargs)

        mask = Image.new("L", (120, 120), 255)
        with (
            patch(
                "apps.members.passport_photo_processing._predict_foreground_mask",
                return_value=mask,
            ),
            patch("builtins.__import__", side_effect=import_without_rembg),
            self.assertLogs(passport_processing.logger, level="ERROR"),
        ):
            with self.assertRaisesRegex(
                ValidationError, "temporarily unavailable.*retry"
            ):
                process_passport_photo(self.make_input_jpeg())

    def test_inference_exception_never_returns_original_photo(self):
        with (
            patch(
                "apps.members.passport_photo_processing._predict_foreground_mask",
                side_effect=RuntimeError("inference failed"),
            ),
            self.assertLogs(passport_processing.logger, level="ERROR"),
        ):
            with self.assertRaisesRegex(ValidationError, "original photograph was not accepted"):
                process_passport_photo(self.make_input_jpeg())

    def test_invalid_model_download_cleans_up_partial_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            temp_root = Path(directory)
            with (
                patch.dict(os.environ, {"U2NET_MODEL_PATH": str(temp_root / "configured.onnx")}),
                patch.object(Path, "home", return_value=temp_root / "home"),
                patch("apps.members.passport_photo_processing.tempfile.gettempdir", return_value=directory),
                patch(
                    "apps.members.passport_photo_processing.urllib.request.urlopen",
                    return_value=BytesIO(b"invalid model bytes"),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "checksum"):
                    passport_processing._model_path()

            self.assertEqual(list(temp_root.glob("u2net-*.download")), [])
