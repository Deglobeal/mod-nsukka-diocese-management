from io import BytesIO
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from PIL import Image, ImageDraw

import apps.members.passport_photo_processing as passport_processing
from apps.members.passport_photo_processing import process_passport_photo


class PassportPhotoProcessingTests(SimpleTestCase):
    def make_image(self, *, format="JPEG", size=(120, 120), mode="RGB", exif=None):
        buffer = BytesIO()
        color = (80, 100, 120, 255) if mode == "RGBA" else (80, 100, 120)
        image = Image.new(mode, size, color)
        draw_color = (180, 40, 40, 255) if mode == "RGBA" else (180, 40, 40)
        ImageDraw.Draw(image).rectangle(
            (size[0] // 4, size[1] // 6, size[0] * 3 // 4, size[1] * 5 // 6),
            fill=draw_color,
        )
        save_options = {"exif": exif} if exif else {}
        image.save(buffer, format=format, **save_options)
        return buffer.getvalue()

    def assert_valid_jpeg(self, result, expected_size):
        with Image.open(BytesIO(result)) as output:
            self.assertEqual(output.format, "JPEG")
            self.assertEqual(output.mode, "RGB")
            self.assertEqual(output.size, expected_size)
            output.verify()
        self.assertLessEqual(len(result), 5 * 1024 * 1024)

    def test_empty_upload_is_rejected_without_error_logging(self):
        with self.assertNoLogs(passport_processing.logger, level="ERROR"):
            with self.assertRaisesRegex(ValidationError, "empty"):
                process_passport_photo(b"")

    def test_corrupted_image_bytes_are_rejected_without_traceback_logging(self):
        with self.assertNoLogs(passport_processing.logger, level="ERROR"):
            with self.assertRaisesRegex(ValidationError, "could not be read"):
                process_passport_photo(b"not an image")

    def test_truncated_jpeg_is_rejected_safely(self):
        truncated = self.make_image()[:30]
        with self.assertNoLogs(passport_processing.logger, level="ERROR"):
            with self.assertRaises(ValidationError):
                process_passport_photo(truncated)

    def test_unsupported_image_format_is_rejected(self):
        with self.assertRaisesRegex(ValidationError, "JPEG or PNG"):
            process_passport_photo(self.make_image(format="GIF"))

    def test_server_normalizes_jpeg_without_changing_its_background(self):
        result = process_passport_photo(self.make_image(size=(240, 320)))
        self.assert_valid_jpeg(result, (240, 320))
        with Image.open(BytesIO(result)) as output:
            background_pixel = output.getpixel((5, 5))
            subject_pixel = output.getpixel((120, 160))
            self.assertNotEqual(background_pixel, (255, 255, 255))
            self.assertGreater(subject_pixel[0], subject_pixel[1] * 2)
            self.assertGreater(subject_pixel[0], subject_pixel[2] * 2)

    def test_valid_png_becomes_readable_jpeg_with_same_dimensions(self):
        result = process_passport_photo(self.make_image(format="PNG", size=(180, 140)))
        self.assert_valid_jpeg(result, (180, 140))

    def test_transparent_png_is_composited_onto_white(self):
        buffer = BytesIO()
        image = Image.new("RGBA", (120, 120), (0, 0, 0, 0))
        ImageDraw.Draw(image).rectangle((30, 20, 90, 100), fill=(180, 40, 40, 255))
        image.save(buffer, format="PNG")

        result = process_passport_photo(buffer.getvalue())
        self.assert_valid_jpeg(result, (120, 120))
        with Image.open(BytesIO(result)) as output:
            self.assertEqual(output.getpixel((5, 5)), (255, 255, 255))

    def test_exif_orientation_is_applied_and_dimensions_follow_orientation(self):
        exif = Image.Exif()
        exif[274] = 6
        result = process_passport_photo(
            self.make_image(size=(160, 120), exif=exif.tobytes())
        )
        self.assert_valid_jpeg(result, (120, 160))

    def test_minimum_dimensions_are_enforced(self):
        with self.assertRaisesRegex(ValidationError, "dimensions"):
            process_passport_photo(self.make_image(size=(99, 100)))

    def test_maximum_dimensions_are_enforced_before_pixel_decode(self):
        with self.assertRaisesRegex(ValidationError, "dimensions"):
            process_passport_photo(self.make_image(size=(4001, 100)))

    def test_dimension_limits_are_inclusive(self):
        result = process_passport_photo(self.make_image(size=(100, 4000)))
        self.assert_valid_jpeg(result, (100, 4000))

    def test_decompression_bomb_warning_is_a_user_validation_error(self):
        image_data = self.make_image(size=(120, 120))
        with patch.object(Image, "MAX_IMAGE_PIXELS", 100):
            with self.assertNoLogs(passport_processing.logger, level="ERROR"):
                with self.assertRaisesRegex(ValidationError, "could not be read"):
                    process_passport_photo(image_data)

    def test_output_over_limit_is_rejected_without_resizing(self):
        image_data = self.make_image(size=(120, 120))
        with patch.object(passport_processing, "MAX_OUTPUT_BYTES", 1):
            with self.assertRaisesRegex(ValidationError, "5 MB"):
                process_passport_photo(image_data)

    def test_invalid_generated_output_is_logged_but_details_are_hidden(self):
        with (
            patch.object(
                passport_processing,
                "_encode_jpeg_within_limit",
                return_value=b"not a jpeg",
            ),
            self.assertLogs(passport_processing.logger, level="ERROR"),
        ):
            with self.assertRaisesRegex(ValidationError, "could not be prepared"):
                process_passport_photo(self.make_image())
