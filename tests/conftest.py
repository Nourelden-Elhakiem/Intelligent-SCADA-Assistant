from __future__ import annotations

from pathlib import Path

import pytest

from intelligent_scada.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(project_root=tmp_path, data_dir=tmp_path / "data")
