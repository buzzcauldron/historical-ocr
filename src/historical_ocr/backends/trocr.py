"""Microsoft TrOCR (transformers) — line-level printed-text OCR."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image

DEFAULT_MODEL = "microsoft/trocr-base-printed"
# Synthetic confidence assigned when TrOCR replaces a weak Tesseract line.
DEFAULT_REPAIR_CONF = 78.0


def available() -> bool:
    try:
        import torch  # noqa: F401
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel  # noqa: F401
    except ImportError:
        return False
    return True


def describe(*, model: str | None = None) -> str:
    name = model or DEFAULT_MODEL
    if not available():
        return "TrOCR unavailable (pip install -e .)"
    try:
        import torch

        device = "cuda" if torch.cuda.is_available() else "cpu"
        return f"TrOCR {name} ({device})"
    except ImportError:
        return f"TrOCR {name} (torch missing)"


@lru_cache(maxsize=2)
def _load(model_name: str):
    import torch
    from transformers import TrOCRProcessor, VisionEncoderDecoderModel

    processor = TrOCRProcessor.from_pretrained(model_name)
    model = VisionEncoderDecoderModel.from_pretrained(model_name)
    model.eval()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)
    return processor, model, device


def transcribe_pil(image: Image.Image, *, model: str | None = None) -> str:
    """Transcribe a single line or short text crop."""
    import torch

    if not available():
        raise RuntimeError("TrOCR requires transformers (pip install -e .)")

    model_name = model or DEFAULT_MODEL
    processor, trocr_model, device = _load(model_name)

    if image.mode != "RGB":
        image = image.convert("RGB")

    pixel_values = processor(images=image, return_tensors="pt").pixel_values.to(device)
    with torch.no_grad():
        ids = trocr_model.generate(pixel_values, max_new_tokens=128)
    text = processor.batch_decode(ids, skip_special_tokens=True)[0]
    return text.strip()


def transcribe_path(path, *, model: str | None = None) -> str:
    from PIL import Image

    with Image.open(path) as im:
        return transcribe_pil(im.convert("RGB"), model=model)
