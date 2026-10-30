from intelligent_scada.linking.image_text_linker import link_images_to_chunks


def test_page_overlap_links_only_kept_images() -> None:
    images = [
        {
            "filename": "diagram.png",
            "page": 4,
            "img_index": 1,
            "xref": 1,
            "width": 800,
            "height": 600,
            "source_ext": "png",
            "file_size_bytes": 1000,
            "md5": "a",
            "decision": "keep",
        },
        {
            "filename": "noise.png",
            "page": 4,
            "img_index": 2,
            "xref": 2,
            "width": 20,
            "height": 20,
            "source_ext": "png",
            "file_size_bytes": 20,
            "md5": "b",
            "decision": "discard",
        },
    ]
    chunk = {
        "chunk_id": "chunk_000000",
        "chunk_index": 0,
        "text": "Section: Configure\n\nText",
        "char_count": 24,
        "word_count": 3,
        "page_start": 4,
        "page_end": 5,
        "source_pages": [4, 5],
        "toc_level": 1,
        "section_title": "Configure",
        "section_path": ["Configure"],
        "section_start_page": 4,
        "section_end_page": 5,
        "part_index": 1,
        "part_count": 1,
    }

    links = link_images_to_chunks(images, [chunk])

    assert links[0]["image_count"] == 1
    assert links[0]["images"][0]["filename"] == "diagram.png"
