"""Page CNN training (optional; not used for routing in print-only mode)."""

from __future__ import annotations

from pathlib import Path

import pytest

from historical_ocr.ml.page_cnn import CLASS_NAMES, torch_available, train_page_cnn
from historical_ocr.pipeline.route import apply_routes
from historical_ocr.models.manifest import JobManifest, PageRecord

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "page_cnn"


@pytest.mark.skipif(not torch_available(), reason="PyTorch not installed")
def test_train_page_cnn_smoke(tmp_path: Path) -> None:
    if not (DATA / "print").is_dir() or not (DATA / "manuscript").is_dir():
        pytest.skip("run scripts/bootstrap_page_cnn_data.py first")

    out = tmp_path / "page_cnn.pt"
    meta = train_page_cnn(DATA, out, epochs=2, batch_size=4, log_fn=None)
    assert out.is_file()
    assert meta.val_accuracy is not None
    assert meta.classes == CLASS_NAMES


def test_route_always_print(tmp_path: Path) -> None:
    manifest = JobManifest(
        job_id="t",
        pages=[PageRecord(page_id="p0", image_path="pages/x.jpg")],
    )
    resolved = apply_routes(manifest, "auto", job_root=tmp_path)
    assert resolved == "print"
    assert manifest.pages[0].route == "print"
