"""Validate and normalize passport photos without a bundled AI model."""

import logging
import warnings
from io import BytesIO

from django.core.exceptions import ValidationError
from PIL import Image, ImageOps, UnidentifiedImageError


MAX_OUTPUT_BYTES = 5 * 1024 * 1024
MIN_DIMENSION = 100
MAX_DIMENSION = 4000
logger = logging.getLogger(__name__)


def _validate_dimensions(width: int, height: int) -> None:
    if (
        width < MIN_DIMENSION
        or height < MIN_DIMENSION
        or width > MAX_DIMENSION
        or height > MAX_DIMENSION
    ):
        raise ValidationError(
            "The photograph dimensions are invalid. Please retake it."
        )


def _normalize_to_rgb(image: Image.Image) -> Image.Image:
    """Normalize color mode without changing the subject's appearance."""
    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
        foreground = image.convert("RGBA")
        white_background = Image.new(
            "RGBA", foreground.size, (255, 255, 255, 255)
        )
        white_background.alpha_composite(foreground)
        return white_background.convert("RGB")
    return image.convert("RGB")


def process_passport_photo(raw: bytes) -> bytes:
    """Validate and normalize an image already processed in the browser.

    The server preserves the supplied background. It performs no segmentation
    or flood fill. PNG transparency is composited onto white, and dimensions are
    preserved after applying EXIF orientation.
    """
    if not raw:
        raise ValidationError("The passport photograph is empty.")

    try:
        # Promote Pillow's decompression warning to an exception. Check the
        # image's declared dimensions before decoding any pixel data as well.
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(raw)) as source:
                if source.format not in {"JPEG", "PNG"}:
                    raise ValidationError(
                        "Use a JPEG or PNG passport photograph."
                    )
                _validate_dimensions(*source.size)
                source.load()
                oriented = ImageOps.exif_transpose(source)
                _validate_dimensions(*oriented.size)
                image = _normalize_to_rgb(oriented)
    except ValidationError:
        raise
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        # Malformed or unsafe uploads are expected user errors, not application
        # failures. Do not log their payload or emit an exception traceback.
        raise ValidationError(
            "The passport photograph could not be read. Please retake it."
        ) from None

    try:
        processed = _encode_jpeg_within_limit(image)
        _verify_output(processed, image.size)
        return processed
    except ValidationError:
        raise
    except Exception:
        # Errors during conversion or verification indicate an application or
        # runtime problem. Log diagnostics server-side, but keep details private.
        logger.exception("Passport photograph conversion or verification failed.")
        raise ValidationError(
            "The passport photograph could not be prepared. Please retry."
        ) from None


def _encode_jpeg_within_limit(image: Image.Image) -> bytes:
    for quality in (92, 85, 78, 70, 62):
        output = BytesIO()
        image.save(output, format="JPEG", quality=quality, optimize=True)
        processed = output.getvalue()
        if processed and len(processed) <= MAX_OUTPUT_BYTES:
            return processed

    raise ValidationError(
        "The photograph exceeds the 5 MB processed size limit. Please retake it."
    )


def _verify_output(processed: bytes, expected_size: tuple[int, int]) -> None:
    if not processed or len(processed) > MAX_OUTPUT_BYTES:
        raise ValidationError(
            "The photograph exceeds the 5 MB processed size limit. Please retake it."
        )

    with Image.open(BytesIO(processed)) as output:
        if (
            output.format != "JPEG"
            or output.mode != "RGB"
            or output.size != expected_size
        ):
            raise ValidationError(
                "The processed photograph could not be verified. Please retry."
            )
        output.verify()
