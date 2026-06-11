"""Internet Archive resolver for Institutional Books."""

from __future__ import annotations

import json

from historical_ocr.ml.archive_org import (
    build_archive_search_queries,
    normalize_htid,
    page_image_urls_from_manifest,
)


def test_normalize_htid() -> None:
    assert normalize_htid("32044036307312") == "hvd.32044036307312"
    assert normalize_htid("hvd.32044036307312") == "hvd.32044036307312"


def test_build_search_queries_uses_oclc_and_title() -> None:
    queries = build_archive_search_queries(
        {
            "barcode_src": "32044036307312",
            "title_src": "Subject-index of the London Library",
            "author_src": "C. T. Hagberg Wright",
            "publication_year_parsed": 1913,
            "identifiers_src": {"ocolc": ["12345678"], "lccn": ["abc123"]},
        },
    )
    assert any("oclc:12345678" in q for q in queries)
    assert any("lccn:abc123" in q for q in queries)
    assert any("London Library" in q for q in queries)


def test_page_urls_from_iiif_v3_manifest() -> None:
    manifest = {
        "items": [
            {
                "type": "Canvas",
                "items": [
                    {
                        "items": [
                            {
                                "body": {
                                    "id": (
                                        "https://iiif.archive.org/image/iiif/3/"
                                        "b29000427_0001%2fb29000427_0001_jp2.zip%2f"
                                        "b29000427_0001_jp2%2fb29000427_0001_0003.jp2"
                                    ),
                                },
                            },
                        ],
                    },
                ],
            },
        ],
    }
    urls = page_image_urls_from_manifest(manifest)
    assert len(urls) == 1
    assert urls[0].endswith("/full/max/0/default.jpg")


def test_resolve_london_library_index_live() -> None:
    """Integration: known IA item for a well-known catalog title."""
    import httpx

    from historical_ocr.ml.archive_org import resolve_archive_identifier

    record = {
        "barcode_src": "b29000427_0001",
        "title_src": "Subject-index of the London Library",
        "publication_year_parsed": 1913,
    }
    with httpx.Client(timeout=90.0, follow_redirects=True) as client:
        ia_id = resolve_archive_identifier(record, client=client)
    assert ia_id == "b29000427_0001"
