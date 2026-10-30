from contextlib import contextmanager

from intelligent_scada.images.image_lookup import ImageLookup


def lookup_with_path(monkeypatch, root, stored):
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, *args):
            pass

        def fetchone(self):
            return (stored,)

    class Connection:
        def cursor(self):
            return Cursor()

    @contextmanager
    def transaction(_):
        yield Connection()

    monkeypatch.setattr('intelligent_scada.images.image_lookup.transaction', transaction)
    return ImageLookup(None, data_root=root)


def test_injected_data_root_serves_owned_images_and_rejects_escape(tmp_path, monkeypatch):
    root = tmp_path / 'custom'
    root.mkdir()
    image = root / 'diagram.png'
    image.write_bytes(b'synthetic image')
    lookup = lookup_with_path(monkeypatch, root, str(image))
    assert lookup.resolve_path('manual', 'diagram.png') == image
    outside = tmp_path / 'private.png'
    outside.write_bytes(b'private')
    lookup = lookup_with_path(monkeypatch, root, str(outside))
    assert lookup.resolve_path('manual', 'private.png') is None
    lookup = lookup_with_path(monkeypatch, root, 'C:\\old\\data\\diagram.png')
    assert lookup.resolve_path('manual', 'diagram.png') == image
    lookup = lookup_with_path(monkeypatch, root, 'C:/old/data/../private.png')
    assert lookup.resolve_path('manual', 'private.png') is None
