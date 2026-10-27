"""Optional local AI detection of signature-like marks.

This detects a signature-like object; it does not verify authorship or
prove that a signature is genuine. Model loading is lazy and local-only.
"""
from functools import lru_cache
from pathlib import Path

from django.conf import settings


MODEL_RELATIVE_PATH = (
    Path("models") / "signature" / "yolos-tiny-signature-detection"
)
DEFAULT_CONFIDENCE_THRESHOLD = 0.50


@lru_cache(maxsize=1)
def _load_detector():
    import torch
    from transformers import AutoImageProcessor, AutoModelForObjectDetection

    model_path = Path(settings.BASE_DIR) / MODEL_RELATIVE_PATH

    if not (model_path / "model.safetensors").is_file():
        raise FileNotFoundError("Local signature model weights were not found.")

    processor = AutoImageProcessor.from_pretrained(
        str(model_path),
        local_files_only=True,
    )
    model = AutoModelForObjectDetection.from_pretrained(
        str(model_path),
        local_files_only=True,
    )
    model.to("cpu")
    model.eval()
    return processor, model, torch


def detect_signature(image_file, threshold=DEFAULT_CONFIDENCE_THRESHOLD):
    """Return non-blocking detection diagnostics for an uploaded image.

    Result fields:
      available: whether inference completed
      detected: whether a signature object exceeded the threshold
      confidence: best detected confidence, or None
      box: best bounding box [x1, y1, x2, y2], or None
      error: safe error category when inference is unavailable
    """
    try:
        from PIL import Image

        processor, model, torch = _load_detector()

        image_file.seek(0)
        with Image.open(image_file) as opened:
            image = opened.convert("RGB")

        inputs = processor(images=image, return_tensors="pt")

        with torch.inference_mode():
            outputs = model(**inputs)

        results = processor.post_process_object_detection(
            outputs,
            threshold=threshold,
            target_sizes=[(image.height, image.width)],
        )[0]

        scores = results["scores"].detach().cpu().tolist()
        boxes = results["boxes"].detach().cpu().tolist()
        labels = results["labels"].detach().cpu().tolist()

        # The downloaded model's only class is ID 0: "signature".
        candidates = [
            (float(score), [float(value) for value in box])
            for score, box, label in zip(scores, boxes, labels)
            if int(label) == 0
        ]

        if not candidates:
            return {
                "available": True,
                "detected": False,
                "confidence": None,
                "box": None,
                "error": None,
            }

        confidence, box = max(candidates, key=lambda item: item[0])
        return {
            "available": True,
            "detected": True,
            "confidence": confidence,
            "box": box,
            "error": None,
        }

    except Exception as exc:
        # Return only the error type; do not include image data or contents.
        return {
            "available": False,
            "detected": False,
            "confidence": None,
            "box": None,
            "error": type(exc).__name__,
        }
    finally:
        try:
            image_file.seek(0)
        except Exception:
            pass
