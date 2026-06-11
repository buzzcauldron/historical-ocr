"""Newspaper OCR training corpus preparation."""

from __future__ import annotations

from pathlib import Path

from historical_ocr.ml.newspaper_train import (
    CorpusSource,
    MIN_TRAIN_LINES,
    _ketos_line,
    prepare_training_corpus,
    train_newspaper_ocr,
)


def test_ketos_line_flattens_whitespace() -> None:
    line = _ketos_line(Path("/tmp/a.jpg"), "line one\nline two")
    assert "\n" not in line
    assert "line one line two" in line


def test_prepare_merges_corpora(tmp_path: Path) -> None:
    from PIL import Image

    ca = tmp_path / "ca"
    user = tmp_path / "user"
    for corpus, rid, split in (
        (ca, "p1", "train"),
        (user, "bn1", "val"),
    ):
        for sub in ("images", "text", "meta"):
            (corpus / split / sub).mkdir(parents=True)
        Image.new("RGB", (16, 16), (200, 200, 200)).save(corpus / split / "images" / f"{rid}.jpg")
        (corpus / split / "text" / f"{rid}.txt").write_text("hello world\n", encoding="utf-8")
        import json

        manifest = {
            "version": 1,
            "records": {
                rid: {
                    "split": split,
                    "stem": rid,
                    "text": f"{split}/text/{rid}.txt",
                    "meta": f"{split}/meta/{rid}.json",
                    "image": f"{split}/images/{rid}.jpg",
                },
            },
        }
        (corpus / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    out = tmp_path / "train_root"
    stats = prepare_training_corpus(
        out,
        sources=[
            CorpusSource("ca", ca, "ca"),
            CorpusSource("user", user, "user"),
        ],
    )
    assert stats["counts"]["train"] == 1
    assert stats["counts"]["val"] == 1
    assert (out / "ketos" / "train.txt").is_file()
    assert (out / "ketos" / "val.txt").is_file()


def test_prepare_skips_empty_flattened_text(tmp_path: Path) -> None:
    from PIL import Image
    import json

    corpus = tmp_path / "ca"
    rid = "empty"
    for sub in ("images", "text", "meta"):
        (corpus / "train" / sub).mkdir(parents=True)
    Image.new("RGB", (8, 8), (128, 128, 128)).save(corpus / "train" / "images" / f"{rid}.jpg")
    (corpus / "train" / "text" / f"{rid}.txt").write_text("   \n\t\n", encoding="utf-8")
    manifest = {
        "version": 1,
        "records": {
            rid: {
                "split": "train",
                "stem": rid,
                "text": f"train/text/{rid}.txt",
                "meta": f"train/meta/{rid}.json",
                "image": f"train/images/{rid}.jpg",
            },
        },
    }
    (corpus / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    out = tmp_path / "train_root"
    stats = prepare_training_corpus(out, sources=[CorpusSource("ca", corpus, "ca")])
    assert stats["counts"]["train"] == 0
    assert (out / "ketos" / "train.txt").read_text(encoding="utf-8").strip() == ""


def test_train_exits_early_when_corpus_too_small(tmp_path: Path) -> None:
    import json

    data_root = tmp_path / "data"
    data_root.mkdir(parents=True)
    (data_root / "manifest.json").write_text(
        json.dumps({"version": 1, "counts": {"train": MIN_TRAIN_LINES - 1, "val": 0}, "records": {}}),
        encoding="utf-8",
    )

    meta = train_newspaper_ocr(data_root, tmp_path / "model.state.json")
    assert meta["skipped"] is True
    assert meta["train_lines"] == MIN_TRAIN_LINES - 1
