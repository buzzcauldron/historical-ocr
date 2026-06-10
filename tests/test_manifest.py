from historical_ocr.models.manifest import JobManifest, PageRecord


def test_manifest_roundtrip():
    m = JobManifest(
        job_id="demo",
        pages=[PageRecord(page_id="p1", image_path="pages/p1.jpg", status="ok")],
    )
    raw = m.model_dump_json()
    again = JobManifest.model_validate_json(raw)
    assert again.job_id == "demo"
    assert again.pages[0].page_id == "p1"
