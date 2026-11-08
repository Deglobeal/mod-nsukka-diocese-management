import base64
from io import BytesIO
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from PIL import Image, ImageDraw

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

    def test_empty_input_is_rejected(self):
        with self.assertRaises(ValidationError):
            process_passport_photo(b"")

    def test_invalid_image_is_rejected(self):
        with self.assertRaises(ValidationError):
            process_passport_photo(b"not an image")
