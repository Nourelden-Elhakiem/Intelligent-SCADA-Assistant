from intelligent_scada.rag.citations import build_citations, format_citation


def test_citation_formatting_for_page_range() -> None:
    result = {
        "chunk_id": "chunk_000010",
        "text": "text",
        "page_start": 10,
        "page_end": 12,
        "source_pages": [10, 11, 12],
        "section_title": "Ports",
        "section_path": ["Configure", "Servers", "Ports"],
        "score": 0.9,
    }
    assert format_citation(result) == "Configure > Servers > Ports — pp. 10-12"
    citation = build_citations([result])[0]
    assert citation["source_id"] == "S1"
    assert citation["chunk_id"] == "chunk_000010"


def test_only_markers_used_by_the_answer_are_citations():
    import pytest

    from intelligent_scada.rag.citations import CitationValidationError, used_citations

    source = {'chunk_id': 'chunk_000000', 'text': 'Synthetic evidence', 'page_start': 1,
              'page_end': 1, 'source_pages': [1], 'section_title': 'Alarms',
              'section_path': ['Alarms'], 'score': 0.9}
    sources = [source, source]
    assert [c['source_id'] for c in used_citations('See [S2].', sources)] == ['S2']
    assert used_citations('Insufficient information.', sources) == []
    assert len(used_citations('Grouped [S1, S2].', sources)) == 2
    with pytest.raises(CitationValidationError):
        used_citations('Unsupported [S99].', sources)
