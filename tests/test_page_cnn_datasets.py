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
    assert "newspaper_gt" in reg
    assert reg["newspaper_gt"]["chronicling-america"]["label"] == "print"
    assert "remote_gt" in reg


def test_list_sources_includes_hf_and_ocrdatasets() -> None:
    ids = {s.source_id for s in list_sources()}
    assert "ocr-quality" in ids
    assert "chronicling-america" in ids
    assert "iam-histdb" in ids
    assert "akdeniz-kraken-vatlib" in ids


def test_harvest_newspaper_gt_copies_images(tmp_path: Path) -> None:
    from historical_ocr.ml.page_cnn_datasets import harvest_newspaper_gt

    corpus = tmp_path / "newspaper_gt"
    for sub in ("images", "text", "meta"):
        (corpus / "train" / sub).mkdir(parents=True)
    from PIL import Image

    Image.new("RGB", (48, 48), (180, 180, 180)).save(corpus / "train" / "images" / "p1.jpg")
    (corpus / "train" / "text" / "p1.txt").write_text("hello\n", encoding="utf-8")
    import json

    manifest = {
        "version": 1,
        "records": {
            "p1": {
                "split": "train",
                "stem": "p1",
                "text": "train/text/p1.txt",
                "meta": "train/meta/p1.json",
                "image": "train/images/p1.jpg",
            },
        },
    }
    (corpus / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    out = tmp_path / "page_cnn"
    n = harvest_newspaper_gt("chronicling-america", out, corpus, limit=10)
    assert n == 1
    assert list((out / "print").glob("chronicling-america_*"))


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
