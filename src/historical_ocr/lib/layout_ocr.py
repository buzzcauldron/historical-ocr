"""Print OCR with per-line layout from Tesseract."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image


@dataclass(frozen=True)
class OcrLine:
    line_num: int
    text: str
    left: int
    top: int
    width: int
    height: int
    conf: float


@dataclass(frozen=True)
class LayoutOcrResult:
    lines: list[OcrLine]
    page_width: int
    page_height: int
    full_text: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "page_width": self.page_width,
                "page_height": self.page_height,
                "full_text": self.full_text,
                "lines": [asdict(line) for line in self.lines],
            },
            ensure_ascii=False,
            indent=2,
        )

    @classmethod
    def from_json(cls, raw: str) -> LayoutOcrResult:
        data = json.loads(raw)
        lines = [
            OcrLine(
                line_num=int(item["line_num"]),
                text=str(item["text"]),
                left=int(item["left"]),
                top=int(item["top"]),
                width=int(item["width"]),
                height=int(item["height"]),
                conf=float(item.get("conf", 0.0)),
            )
            for item in data.get("lines", [])
        ]
        return cls(
            lines=lines,
            page_width=int(data["page_width"]),
            page_height=int(data["page_height"]),
            full_text=str(data.get("full_text", "")),
        )


def _group_tesseract_lines(data: dict) -> list[OcrLine]:
    buckets: dict[tuple[int, int, int], list[tuple[str, int, int, int, int, float]]] = {}
    n = len(data["text"])
    for i in range(n):
        text = (data["text"][i] or "").strip()
        if not text:
            continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1.0
        if conf < 0:
            continue
        key = (
            int(data["block_num"][i]),
            int(data["par_num"][i]),
            int(data["line_num"][i]),
        )
        buckets.setdefault(key, []).append(
            (
                text,
                int(data["left"][i]),
                int(data["top"][i]),
                int(data["width"][i]),
                int(data["height"][i]),
                conf,
            ),
        )

    lines: list[OcrLine] = []
    for line_num, (_key, words) in enumerate(sorted(buckets.items()), start=1):
        words.sort(key=lambda w: w[1])
        text = " ".join(w[0] for w in words)
        left = min(w[1] for w in words)
        top = min(w[2] for w in words)
        right = max(w[1] + w[3] for w in words)
        bottom = max(w[2] + w[4] for w in words)
        conf = sum(w[5] for w in words) / len(words)
        lines.append(
            OcrLine(
                line_num=line_num,
                text=text,
                left=left,
                top=top,
                width=right - left,
                height=bottom - top,
                conf=conf,
            ),
        )
    return lines


def ocr_image_with_layout(
    image: Path,
    *,
    lang: str = "lat+frk+eng",
    psm: int = 6,
    settings=None,
) -> LayoutOcrResult:
    from historical_ocr.backends import tesseract as tess_backend
    from pytesseract import Output

    if settings is not None:
        tess_backend.configure_from_settings(settings)
    tess_backend.ensure_ready(lang)

    import pytesseract

    config = f"--psm {psm}"
    with Image.open(image) as im:
        page_width, page_height = im.size
        data = pytesseract.image_to_data(
            im,
            lang=lang,
            config=config,
            output_type=Output.DICT,
        )

    lines = _group_tesseract_lines(data)
    full_text = "\n".join(line.text for line in lines if line.text.strip())
    return LayoutOcrResult(
        lines=lines,
        page_width=page_width,
        page_height=page_height,
        full_text=full_text,
    )


def write_layout_json(result: LayoutOcrResult, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(result.to_json() + "\n", encoding="utf-8")


def read_layout_json(path: Path) -> LayoutOcrResult | None:
    if not path.is_file():
        return None
    return LayoutOcrResult.from_json(path.read_text(encoding="utf-8"))
