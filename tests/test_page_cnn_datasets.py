"""Page CNN dataset registry and harvest helpers."""

from __future__ import annotations

from pathlib import Path

from historical_ocr.ml.page_cnn_datasets import (
    harvest_local_dir,
    list_sources,
    load_registry,
)


def test_registry_loads() -> None:
    reg = load_registry()
    assert "huggingface" in reg
    assert "ocr-quality" in reg["huggingface"]
    assert reg["huggingface"]["ocr-quality"]["label"] == "print"
    assert "ocr-pdf-degraded" in reg["huggingface"]
    assert "ocrdatasets" in reg
    assert "remote_gt" in reg


def test_list_sources_includes_hf_and_ocrdatasets() -> None:
    ids = {s.source_id for s in list_sources()}
    assert "ocr-quality" in ids
    assert "iam-histdb" in ids
    assert "akdeniz-kraken-vatlib" in ids


def test_harvest_local_dir(tmp_path: Path) -> None:
    src = tmp_path / "incoming"
    src.mkdir()
    from PIL import Image

    Image.new("RGB", (64, 64), (200, 200, 200)).save(src / "a.jpg")
    out = tmp_path / "dataset"
    n = harvest_local_dir(src, out, label="print", prefix="test")
    assert n == 1
    assert (out / "print").is_dir()
    assert len(list((out / "print").glob("local_test_*"))) == 1


def test_harvest_akdeniz_skips_missing(tmp_path: Path) -> None:
    from historical_ocr.ml.page_cnn_datasets import harvest_akdeniz_gt

    out = tmp_path / "dataset"
    n = harvest_akdeniz_gt(
        "akdeniz-kraken-vatlib",
        out,
        akdeniz_home=tmp_path / "empty_home",
        limit=10,
    )
    assert n == 0


def test_harvest_akdeniz_copies_images(tmp_path: Path) -> None:
    from historical_ocr.ml.page_cnn_datasets import harvest_akdeniz_gt

    home = tmp_path / "home"
    gt = home / "kraken-vatlib-gt" / "pages"
    gt.mkdir(parents=True)
    from PIL import Image

    Image.new("RGB", (32, 32), (100, 100, 100)).save(gt / "p1.png")
    out = tmp_path / "dataset"
    n = harvest_akdeniz_gt("akdeniz-kraken-vatlib", out, akdeniz_home=home, limit=5)
    assert n == 1
    assert list((out / "manuscript").glob("akdeniz-kraken-vatlib_*"))
