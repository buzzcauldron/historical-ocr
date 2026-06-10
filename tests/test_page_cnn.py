"""Page CNN training and routing (optional PyTorch)."""

from __future__ import annotations

from pathlib import Path

import pytest

from historical_ocr.ml.page_cnn import CLASS_NAMES, predict_image_path, torch_available, train_page_cnn
from historical_ocr.pipeline.route import apply_routes
from historical_ocr.models.manifest import JobManifest, PageRecord
from historical_ocr.config import Settings

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


@pytest.mark.skipif(not torch_available(), reason="PyTorch not installed")
def test_auto_route_uses_cnn(tmp_path: Path) -> None:
    print_imgs = sorted((DATA / "print").glob("*"))
    if not print_imgs:
        pytest.skip("no print training images")

    model = tmp_path / "m.pt"
    train_page_cnn(DATA, model, epochs=10, batch_size=4, log_fn=None)

    print_img = next(
        (p for p in print_imgs if predict_image_path(model, p)[0] == "print"),
        None,
    )
    if print_img is None:
        pytest.skip("no print image classified as print after training")

    manifest = JobManifest(
        job_id="t",
        pages=[PageRecord(page_id="p0", image_path="pages/x.jpg")],
    )
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    dest = pages_dir / "x.jpg"
    dest.write_bytes(print_img.read_bytes())

    settings = Settings(page_cnn_model=model)
    resolved = apply_routes(
        manifest,
        "auto",
        job_root=tmp_path,
        settings=settings,
    )
    assert resolved == "print"
    assert manifest.pages[0].route == "print"
    assert manifest.pages[0].fingerprint_score is not None
