"""Server-side passport background removal and white-background compositing."""

import hashlib
import os
import tempfile
import urllib.request
from io import BytesIO
from pathlib import Path
from threading import Lock

from django.core.exceptions import ValidationError
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, UnidentifiedImageError


_MODEL_NAME = "u2net"
_session = None
_session_lock = Lock()

MAX_OUTPUT_BYTES = 5 * 1024 * 1024
MIN_DIMENSION = 100
MAX_DIMENSION = 4000


def _model_path() -> Path:
    """Find a verified U2NET model or download it into the runtime temp directory."""
    expected_md5 = "60024c5c889badc19c04ad937298a77b"
    model_url = (
        "https://github.com/danielgatis/rembg/releases/download/"
        "v0.0.0/u2net.onnx"
    )

    configured_path = os.environ.get("U2NET_MODEL_PATH")
    candidates = [
        Path(configured_path).expanduser() if configured_path else None,
        Path.home() / ".rembg/models/u2net/u2net.onnx",
        Path.home() / ".u2net/u2net.onnx",
        Path(tempfile.gettempdir()) / "u2net.onnx",
    ]

    def is_valid(candidate: Path) -> bool:
        if not candidate.is_file():
            return False

        digest = hashlib.md5()
        with candidate.open("rb") as model_file:
            for chunk in iter(lambda: model_file.read(1024 * 1024), b""):
                digest.update(chunk)

        return digest.hexdigest() == expected_md5

    for candidate in candidates:
        if candidate is not None and is_valid(candidate):
            return candidate

    destination = Path(tempfile.gettempdir()) / "u2net.onnx"
    temporary_path = None

    try:
        digest = hashlib.md5()

        with urllib.request.urlopen(model_url, timeout=120) as response:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=destination.parent,
                prefix="u2net-",
                suffix=".download",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)

                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    temporary_file.write(chunk)

        if digest.hexdigest() != expected_md5:
            raise RuntimeError("The downloaded U2NET model failed checksum verification.")

        os.replace(temporary_path, destination)
        return destination

    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _get_session():
    """Load the U2NET ONNX session once per application process."""
    global _session

    if _session is None:
        with _session_lock:
            if _session is None:
                try:
                    import onnxruntime as ort

                    _session = ort.InferenceSession(
                        str(_model_path()),
                        providers=["CPUExecutionProvider"],
                    )
                except Exception as exc:
                    raise ValidationError(
                        "Passport photo processing is temporarily unavailable. "
                        "Please try again later."
                    ) from exc

    return _session


def _predict_foreground_mask(image: Image.Image) -> Image.Image:
    """Run U2NET inference using the same preprocessing as rembg's U2NET session."""
    import numpy as np

    session = _get_session()

    normalized_image = image.convert("RGB").resize(
        (320, 320),
        Image.Resampling.LANCZOS,
    )
    image_array = np.array(normalized_image)
    image_array = image_array / max(np.max(image_array), 1e-6)

    mean = (0.485, 0.456, 0.406)
    std = (0.229, 0.224, 0.225)

    normalized = np.zeros(
        (image_array.shape[0], image_array.shape[1], 3)
    )
    for channel in range(3):
        normalized[:, :, channel] = (
            image_array[:, :, channel] - mean[channel]
        ) / std[channel]

    model_input = {
        session.get_inputs()[0].name:
            np.expand_dims(normalized.transpose((2, 0, 1)), 0).astype(
                np.float32
            )
    }

    prediction = session.run(None, model_input)[0][:, 0, :, :]
    maximum = np.max(prediction)
    minimum = np.min(prediction)

    if maximum <= minimum:
        raise ValueError("U2NET returned an invalid foreground mask.")

    prediction = (prediction - minimum) / (maximum - minimum)
    prediction = np.squeeze(prediction)

    mask = Image.fromarray(
        (prediction.clip(0, 1) * 255).astype("uint8"),
        mode="L",
    )
    return mask.resize(image.size, Image.Resampling.LANCZOS)

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

        mask = _predict_foreground_mask(image)
        foreground = image.convert("RGBA")
        foreground.putalpha(mask)

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
