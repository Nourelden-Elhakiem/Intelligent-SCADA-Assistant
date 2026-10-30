from intelligent_scada.chunking.toc_chunker import create_chunks, split_section_text


def test_legacy_chunk_metadata_and_ids() -> None:
    structure = {
        "total_pages": 2,
        "toc_entries": 1,
        "toc": [{"level": 1, "title": "Configure", "page": 1}],
        "empty_pages": [],
        "page_stats": [],
        "heading_candidates_count": 0,
    }
    pages = [
        {
            "page": 1,
            "raw_text": "First page",
            "clean_text": "First page",
            "raw_char_count": 10,
            "clean_char_count": 10,
            "raw_word_count": 2,
            "clean_word_count": 2,
            "removed_lines": [],
            "has_text": True,
        },
        {
            "page": 2,
            "raw_text": "Second page",
            "clean_text": "Second page",
            "raw_char_count": 11,
            "clean_char_count": 11,
            "raw_word_count": 2,
            "clean_word_count": 2,
            "removed_lines": [],
            "has_text": True,
        },
    ]

    chunks = create_chunks(structure, pages)

    assert chunks[0]["chunk_id"] == "chunk_000000"
    assert chunks[0]["source_pages"] == [1, 2]
    assert chunks[0]["section_path"] == ["Configure"]
    assert chunks[0]["text"] == "Section: Configure\n\nFirst page\n\nSecond page"
    assert chunks[0]["part_index"] == 1
    assert chunks[0]["part_count"] == 1


def test_targeted_strategy_enforces_maximum() -> None:
    text = "A" * 900 + "\n\n" + "B" * 900
    chunks = split_section_text(text, target=600, maximum=800, overlap=100, strategy="targeted")
    assert len(chunks) >= 2
    assert all(len(chunk) <= 800 for chunk in chunks)


def test_each_part_cites_only_pages_present_in_its_text():
    structure = {'total_pages': 3, 'toc': [{'level': 1, 'title': 'Alarm', 'page': 1}]}
    pages = [{'page': p, 'clean_text': text} for p, text in enumerate(
        ['A' * 180, 'B' * 180, 'C' * 180], 1)]
    chunks = create_chunks(structure, pages, target=190, maximum=220, overlap=0,
                           strategy='targeted')
    assert [chunk['source_pages'] for chunk in chunks] == [[1], [2], [3]]
    assert [(c['page_start'], c['page_end']) for c in chunks] == [(1, 1), (2, 2), (3, 3)]
    assert all(c['section_start_page'] == 1 and c['section_end_page'] == 3 for c in chunks)


def test_overlap_and_duplicate_page_text_keep_actual_page_spans():
    structure = {'total_pages': 2, 'toc': [{'level': 1, 'title': 'Alarm', 'page': 1}]}
    pages = [{'page': p, 'clean_text': 'A' * 180} for p in (1, 2)]
    chunks = create_chunks(structure, pages, target=190, maximum=220, overlap=20,
                           strategy='targeted')
    assert chunks[0]['source_pages'] == [1]
    assert chunks[1]['source_pages'] == [1, 2]


def test_missing_toc_and_empty_text_rejected():
    import pytest
    with pytest.raises(ValueError, match="TOC"):
        create_chunks({'total_pages': 1, 'toc': []}, [{'page': 1, 'clean_text': 'text'}])
    with pytest.raises(ValueError, match="extractable"):
        create_chunks({'total_pages': 1, 'toc': [{'level': 1, 'title': 'Alarm', 'page': 1}]},
                      [{'page': 1, 'clean_text': ''}])


def test_legacy_preserves_oversized_paragraph():
    text = 'A' * 2000
    assert split_section_text(text, target=600, maximum=800, overlap=0, strategy='legacy') == [text]
    assert all(len(part) <= 800 for part in split_section_text(
        text, target=600, maximum=800, overlap=0, strategy='targeted'))
