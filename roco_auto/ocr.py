from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import Any

import numpy as np
from PIL import Image, ImageFilter, ImageOps


@dataclass(frozen=True)
class TextOcrResult:
    text: str
    confidence: float
    backend: str


def extract_colored_letters(
    image: Image.Image,
    letter: tuple[int, int, int],
    threshold: float,
    scale: int = 3,
) -> Image.Image:
    """Extract text pixels close to a target color, similar to ALAS extract_letters."""
    arr = np.asarray(image.convert("RGB"), dtype=np.float32)
    target = np.array(letter, dtype=np.float32)
    distance = np.sqrt(np.square(arr - target).sum(axis=2))
    mask = distance <= threshold
    out = Image.fromarray((mask.astype(np.uint8) * 255), mode="L")
    out = out.filter(ImageFilter.MaxFilter(3))
    out = ImageOps.invert(out)
    if scale > 1:
        out = out.resize((out.width * scale, out.height * scale), Image.Resampling.NEAREST)
    return out


class OptionalTextOcr:
    def __init__(self, config: Any) -> None:
        self.config = config

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("ocr.enabled", False))

    @cached_property
    def backend_name(self) -> str:
        if not self.enabled:
            return "disabled"
        backend = str(self.config.get("ocr.backend", "auto")).lower()
        if backend in {"auto", "rapidocr", "rapidocr_onnxruntime"} and self._rapidocr_engine is not None:
            return "rapidocr"
        if backend in {"auto", "pytesseract", "tesseract"} and self._pytesseract is not None:
            return "pytesseract"
        return "unavailable"

    @cached_property
    def _rapidocr_engine(self):
        try:
            from rapidocr_onnxruntime import RapidOCR  # type: ignore
        except Exception:
            try:
                from rapidocr import RapidOCR  # type: ignore
            except Exception:
                return None
        try:
            return RapidOCR()
        except Exception:
            return None

    @cached_property
    def _pytesseract(self):
        try:
            import pytesseract  # type: ignore
        except Exception:
            return None
        return pytesseract

    def _preprocess(self, image: Image.Image) -> Image.Image:
        color = self.config.get("ocr.letter_color", [92, 205, 30])
        threshold = float(self.config.get("ocr.color_threshold", 90))
        scale = int(self.config.get("ocr.scale", 3))
        return extract_colored_letters(
            image,
            (int(color[0]), int(color[1]), int(color[2])),
            threshold,
            scale=max(1, scale),
        )

    @staticmethod
    def _normalize_rapidocr_result(raw: Any) -> TextOcrResult:
        if hasattr(raw, "txts"):
            texts = [str(item) for item in getattr(raw, "txts") or []]
            scores = [float(item) for item in getattr(raw, "scores") or []]
            return TextOcrResult("".join(texts), min(scores) if scores else 0.0, "rapidocr")

        result = raw[0] if isinstance(raw, tuple) else raw
        if not result:
            return TextOcrResult("", 0.0, "rapidocr")

        texts: list[str] = []
        scores: list[float] = []
        for item in result:
            if len(item) >= 3:
                texts.append(str(item[1]))
                try:
                    scores.append(float(item[2]))
                except (TypeError, ValueError):
                    pass
        return TextOcrResult("".join(texts), min(scores) if scores else 0.0, "rapidocr")

    def recognize(self, image: Image.Image) -> TextOcrResult:
        backend = self.backend_name
        if backend in {"disabled", "unavailable"}:
            return TextOcrResult("", 0.0, backend)

        prepared = self._preprocess(image)
        if backend == "rapidocr":
            raw = self._rapidocr_engine(np.asarray(prepared.convert("RGB")))
            return self._normalize_rapidocr_result(raw)

        if backend == "pytesseract":
            language = str(self.config.get("ocr.language", "chi_sim"))
            psm = int(self.config.get("ocr.psm", 7))
            text = self._pytesseract.image_to_string(prepared, lang=language, config=f"--psm {psm}")
            return TextOcrResult(text.strip(), 0.0, "pytesseract")

        return TextOcrResult("", 0.0, "unavailable")
