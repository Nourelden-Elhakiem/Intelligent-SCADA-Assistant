from intelligent_scada.chunking.toc_parser import build_sections


def test_section_hierarchy_and_same_page_boundary() -> None:
    toc = [
        {"level": 1, "title": "Configure", "page": 1},
        {"level": 2, "title": "Servers", "page": 2},
        {"level": 3, "title": "Ports", "page": 2},
        {"level": 2, "title": "Clients", "page": 4},
    ]

    sections = build_sections(toc, total_pages=5)

    assert sections[2]["section_path"] == ["Configure", "Servers", "Ports"]
    assert sections[1]["section_start_page"] == 2
    assert sections[1]["section_end_page"] == 2
    assert sections[-1]["section_path"] == ["Configure", "Clients"]
    assert sections[-1]["section_end_page"] == 5
