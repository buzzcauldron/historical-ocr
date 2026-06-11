"""Newspaper ground-truth scraper helpers."""

from __future__ import annotations

from pathlib import Path

from historical_ocr.ml.newspaper_gt import (
    assign_split,
    chronam_record_from_row,
    fetch_newspaper_gt,
    iiif_full_from_thumbnail,
    normalize_row,
    record_id_from_row,
)


def test_iiif_full_from_thumbnail() -> None:
    thumb = (
        "https://tile.loc.gov/image-services/iiif/service:ndnp:deu:batch_deu_kedavra_ver01:"
        "data:sn82014385:00271740232:1809070801:0074/full/pct:6.25/0/default.jpg#h=318&w=202"
    )
    full = iiif_full_from_thumbnail(thumb)
    assert full is not None
    assert full.endswith("/full/full/0/default.jpg")
    assert "#" not in full


def test_record_id_and_split_stable() -> None:
    row = {
        "lccn": "sn82014385",
        "issue_date": "1809-07-08",
        "Page": "1",
        "edition_order": 1,
        "ocr_text": "THE DELAWARE GAZETTE.",
        "thumbnail_url": "https://example.com/iiif/foo/full/pct:6.25/0/default.jpg",
    }
    rid = record_id_from_row(row)
    assert rid == "sn82014385_1809-07-08_p1_e1"
    assert assign_split(rid, seed=42, val_ratio=0.1) == assign_split(rid, seed=42, val_ratio=0.1)


def test_normalize_row_maps_mixed_case() -> None:
    norm = normalize_row(
        {
            "Web_URL": "https://example.com",
            "Page": "2",
            "source_record_creation_date": "2017-05-24",
        },
    )
    assert norm["web_url"] == "https://example.com"
    assert norm["page"] == "2"


def test_chronam_record_requires_text_and_image() -> None:
    assert chronam_record_from_row({"ocr_text": ""}) is None
    assert chronam_record_from_row({"ocr_text": "hello"}) is None
    rec = chronam_record_from_row(
        {
            "lccn": "sn1",
            "issue_date": "1776-07-04",
            "Page": "1",
            "edition_order": "1",
            "ocr_text": "In CONGRESS",
            "thumbnail_url": "https://example.com/iiif/x/full/pct:6.25/0/default.jpg",
        },
    )
    assert rec is not None
    assert rec.ocr_text == "In CONGRESS"


def test_fetch_text_only_writes_split_layout(tmp_path: Path) -> None:
    shard = tmp_path / "sample.parquet"
    _write_sample_parquet(shard)

    stats = fetch_newspaper_gt(
        tmp_path / "out",
        limit=3,
        val_ratio=0.34,
        seed=7,
        skip_images=True,
        shards=[str(shard)],
        log_fn=None,
    )
    assert stats["saved"] == 3
    root = tmp_path / "out"
    assert (root / "manifest.json").is_file()
    for split in ("train", "val"):
        assert (root / split / "text").is_dir()
        assert (root / split / "meta").is_dir()
    assert len(list((root / "train" / "text").glob("*.txt"))) + len(
        list((root / "val" / "text").glob("*.txt")),
    ) == 3


def _write_sample_parquet(path: Path) -> None:
    import pyarrow as pa
    import pyarrow.parquet as pq

    rows = [
        {
            "lccn": "sn82014385",
            "newspaper_title": "The Delaware gazette",
            "place_of_publication": "Wilmington [Del.]",
            "issue_date": "1809-07-08",
            "edition_order": "1",
            "Page": "1",
            "Web_URL": "https://www.loc.gov/item/sn82014385/1809-07-08/ed-1/",
            "ocr_text": "THE DELAWARE GAZETTE.",
            "ocr_url": "https://example.com/0074.xml",
            "thumbnail_url": (
                "https://tile.loc.gov/image-services/iiif/service:ndnp:deu:"
                "batch_deu_kedavra_ver01:data:sn82014385:00271740232:1809070801:"
                "0074/full/pct:6.25/0/default.jpg"
            ),
            "jpeg2000_url": "https://example.com/0074.jp2",
            "pdf_url": "https://example.com/0074.pdf",
            "source_record_creation_date": "2017-05-24",
        },
        {
            "lccn": "sn83045110",
            "newspaper_title": "Pennsylvania Packet",
            "place_of_publication": "Philadelphia",
            "issue_date": "1777-05-14",
            "edition_order": "1",
            "Page": "2",
            "Web_URL": "https://www.loc.gov/item/sn83045110/1777-05-14/ed-1/",
            "ocr_text": "Philadelphia news.",
            "ocr_url": "https://example.com/0002.xml",
            "thumbnail_url": "https://example.com/iiif/0002/full/pct:6.25/0/default.jpg",
            "jpeg2000_url": "https://example.com/0002.jp2",
            "pdf_url": "https://example.com/0002.pdf",
            "source_record_creation_date": "2017-05-24",
        },
        {
            "lccn": "sn83045110",
            "newspaper_title": "Pennsylvania Packet",
            "place_of_publication": "Philadelphia",
            "issue_date": "1777-05-15",
            "edition_order": "1",
            "Page": "1",
            "Web_URL": "https://www.loc.gov/item/sn83045110/1777-05-15/ed-1/",
            "ocr_text": "Another day.",
            "ocr_url": "https://example.com/0001.xml",
            "thumbnail_url": "https://example.com/iiif/0001/full/pct:6.25/0/default.jpg",
            "jpeg2000_url": "https://example.com/0001.jp2",
            "pdf_url": "https://example.com/0001.pdf",
            "source_record_creation_date": "2017-05-24",
        },
    ]
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, path)
