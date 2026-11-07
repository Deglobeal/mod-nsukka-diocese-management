"""Server-side passport background removal and white-background compositing."""

from io import BytesIO
from threading import Lock

from django.core.exceptions import ValidationError
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, UnidentifiedImageError


_MODEL_NAME = "u2net"
_session = None
_session_lock = Lock()

MAX_OUTPUT_BYTES = 5 * 1024 * 1024
MIN_DIMENSION = 100
MAX_DIMENSION = 4000


def _get_session():
    """Load the background-removal model once per application process."""
    global _session

    if _session is None:
        with _session_lock:
            if _session is None:
                try:
                    from rembg import new_session

                    _session = new_session(_MODEL_NAME)
                except Exception as exc:
                    raise ValidationError(
                        "Passport photo processing is temporarily unavailable. "
                        "Please try again later."
                    ) from exc

    return _session


def _enhance_passport_photo(image: Image.Image) -> Image.Image:
    """Apply restrained luminance correction and sharpening without retouching."""
    image = image.convert("RGB")

    # Correct luminance only, leaving the original colour channels intact.
    lab = image.convert("LAB")
    luminance, channel_a, channel_b = lab.split()

    histogram = luminance.histogram()
    total = sum(histogram)

    if total:
        low_target = total * 0.01
        high_target = total * 0.99
        cumulative = 0
        low = 0
        high = 255

        for value, count in enumerate(histogram):
            cumulative += count
            if cumulative >= low_target:
                low = value
                break

        cumulative = 0
        for value, count in enumerate(histogram):
            cumulative += count
            if cumulative >= high_target:
                high = value
                break

        # Skip correction when the image already has limited tonal range.
        if high - low >= 80:
            corrected = ImageOps.autocontrast(luminance, cutoff=1)
            luminance = Image.blend(luminance, corrected, 0.20)

    enhanced = Image.merge("LAB", (luminance, channel_a, channel_b)).convert("RGB")

    # Mild sharpening; no smoothing, face reshaping, or cosmetic retouching.
    return ImageEnhance.Sharpness(enhanced).enhance(1.15)

def process_passport_photo(raw: bytes) -> bytes:
    """
    Remove the captured photo's background and composite the subject onto white.

    Never return the original image as a fallback.
    """
    if not raw:
        raise ValidationError("The passport photograph is empty.")

    try:
        with Image.open(BytesIO(raw)) as source:
            source.load()
            image = ImageOps.exif_transpose(source).convert("RGB")

        width, height = image.size
        if (
            width < MIN_DIMENSION
            or height < MIN_DIMENSION
            or width > MAX_DIMENSION
            or height > MAX_DIMENSION
        ):
            raise ValidationError(
                "The processed photograph dimensions are invalid. "
                "Please retake the photograph."
            )

        from rembg import remove

        result = remove(image, session=_get_session())

        if isinstance(result, bytes):
            with Image.open(BytesIO(result)) as result_image:
                foreground = result_image.convert("RGBA")
        elif isinstance(result, Image.Image):
            foreground = result.convert("RGBA")
        else:
            raise ValidationError(
                "The background could not be removed. Please retake the photo."
            )

        if foreground.size != image.size:
            raise ValidationError(
                "The processed photograph has invalid dimensions. "
                "Please retake the photograph."
            )

        # Refine the transparency boundary to reduce rough edges and halos.
        # Keep the subject's RGB colours and existing image dimensions unchanged.
        alpha = foreground.getchannel("A")
        alpha = alpha.point(lambda value: 0 if value < 8 else value)
        alpha = alpha.filter(ImageFilter.GaussianBlur(radius=0.6))
        foreground.putalpha(alpha)

        # Composite onto pure white after refining the edge.
        white_background = Image.new(
            "RGBA", foreground.size, (255, 255, 255, 255)
        )
        white_background.alpha_composite(foreground)

        enhanced = _enhance_passport_photo(
            white_background.convert("RGB")
        )

        output = BytesIO()
        enhanced.save(
            output,
            format="JPEG",
            quality=92,
            optimize=True,
        )
        processed = output.getvalue()

        if not processed or len(processed) > MAX_OUTPUT_BYTES:
            raise ValidationError(
                "The processed photograph exceeds the allowed size. "
                "Please retake the photograph."
            )

        # Verify that the generated output is a readable JPEG.
        with Image.open(BytesIO(processed)) as check:
            if check.format != "JPEG" or check.size != image.size:
                raise ValidationError(
                    "The processed photograph could not be verified."
                )
            check.verify()

        return processed

    except ValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValidationError(
            "The passport photograph could not be processed. Please retake it."
        ) from exc
    except Exception as exc:
        raise ValidationError(
            "Background removal failed. Your unprocessed photograph was not accepted."
        ) from exc
