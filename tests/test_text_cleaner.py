from intelligent_scada.ingestion.text_cleaner import clean_page_text


def test_header_footer_removal_preserves_chapter_label() -> None:
    raw = (
        "Configure\nSystem Guide\nPage 50 of 1314\n7EN02-0440-03\n"
        "Set the parameter.\n\n\nContinue.\n"
    )

    clean, removed = clean_page_text(raw)

    assert clean == "Configure\nSet the parameter.\n\nContinue."
    assert removed == ["System Guide", "Page 50 of 1314", "7EN02-0440-03"]


def test_page_number_pattern_is_not_hardcoded_to_one_manual_length() -> None:
    clean, removed = clean_page_text("Page 2 of 9\nUseful text")
    assert clean == "Useful text"
    assert removed == ["Page 2 of 9"]
