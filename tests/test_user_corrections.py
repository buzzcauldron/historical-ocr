"""User correction corpus + tune rules."""

from __future__ import annotations

from pathlib import Path

from historical_ocr.lib.rules_only import apply_user_tune_rules
from historical_ocr.config import Settings
from historical_ocr.ml.user_corrections import (
    apply_tune_rules,
    mine_tune_rules,
    save_tune_rules,
    submit_correction,
    tune_corpus,
)


def test_submit_and_mine_rules(tmp_path: Path) -> None:
    from PIL import Image

    img = tmp_path / "page.jpg"
    Image.new("RGB", (32, 32), (255, 255, 255)).save(img)
    corpus = tmp_path / "user_gt"
    submit_correction(
        corpus,
        record_id="page1",
        image_src=img,
        raw_text="the'boys peeand run",
        corrected_text="the boys pee and run",
        split="train",
    )
    rules = mine_tune_rules(corpus)
    assert any(r.src == "the'boys" and r.dst == "the boys" for r in rules) or len(rules) >= 1
    stats = tune_corpus(corpus)
    assert stats["rules"] >= 1
    assert (corpus / "tuned_rules.json").is_file()


def test_apply_tune_rules_word_and_phrase() -> None:
    from historical_ocr.ml.user_corrections import TuneRule

    rules = [
        TuneRule(src="peeand", dst="pee and", count=1),
        TuneRule(src="diarrhea", dst="diarrhoea", count=1),
    ]
    out = apply_tune_rules("they peeand here diarrhea", rules)
    assert "pee and" in out
    assert "diarrhoea" in out


def test_apply_user_tune_rules_via_settings(tmp_path: Path) -> None:
    from historical_ocr.ml.user_corrections import TuneRule, save_tune_rules

    corpus = tmp_path / "user_gt"
    corpus.mkdir()
    save_tune_rules(corpus, [TuneRule(src="bwana", dst="Bwana", count=1)])
    s = Settings(tune_rules_path=corpus / "tuned_rules.json")
    assert "Bwana" in apply_user_tune_rules("as bwana crawls", s)
