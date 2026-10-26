import os
from dataclasses import replace
from pathlib import Path

import pytest

from intelligent_scada.config import (
    DEFAULT_DOCUMENT_KEY,
    DEFAULT_DOCUMENT_NAME,
    DEFAULT_PDF_FILENAME,
    Settings,
)


def test_primary_manual_defaults_are_centralized(tmp_path: Path) -> None:
    settings = Settings(project_root=tmp_path, data_dir=tmp_path / "data")

    assert settings.default_document_key == DEFAULT_DOCUMENT_KEY
    assert settings.default_document_name == DEFAULT_DOCUMENT_NAME
    assert settings.default_pdf_path == tmp_path / "data" / "pdf" / DEFAULT_PDF_FILENAME
    assert settings.default_pdf_display_path == (
        "data/pdf/Power SCADA Operation 2020 System Guide.pdf"
    )


def test_missing_primary_manual_error_explains_expected_location(tmp_path: Path) -> None:
    settings = Settings(project_root=tmp_path, data_dir=tmp_path / "data")

    with pytest.raises(FileNotFoundError, match="data/pdf/Power SCADA Operation 2020"):
        settings.require_default_pdf()


def test_for_default_document_restores_primary_identity(tmp_path: Path) -> None:
    settings = Settings(
        project_root=tmp_path,
        data_dir=tmp_path / "data",
        document_name="Other Manual",
        document_key="other-manual",
    )

    primary = settings.for_default_document()

    assert primary.document_name == DEFAULT_DOCUMENT_NAME
    assert primary.document_key == DEFAULT_DOCUMENT_KEY


def test_for_document_creates_an_isolated_settings_view(tmp_path: Path) -> None:
    settings = Settings(project_root=tmp_path, data_dir=tmp_path / "data")
    document_data = tmp_path / "data" / "documents" / "controller-guide"

    scoped = settings.for_document(
        document_name="Controller Guide",
        document_key="controller-guide",
        data_dir=document_data,
        pdf_filename="Controller Guide.pdf",
    )

    assert scoped.document_name == "Controller Guide"
    assert scoped.document_key == "controller-guide"
    assert scoped.data_dir == document_data
    assert scoped.pdf_path == document_data / "pdf" / "Controller Guide.pdf"
    assert settings.document_key == DEFAULT_DOCUMENT_KEY


def test_database_schema_path_prefers_the_repository_schema(tmp_path: Path) -> None:
    schema = tmp_path / "database" / "schema.sql"
    schema.parent.mkdir()
    schema.write_text("SELECT 1;", encoding="utf-8")
    settings = Settings(project_root=tmp_path, data_dir=tmp_path / "data")

    assert settings.database_schema_path == schema


def test_notebook_env_reload_can_override_stale_process_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("SCADA_CHUNK_TARGET_SIZE=2800\n", encoding="utf-8")
    monkeypatch.setenv("SCADA_CHUNK_TARGET_SIZE", "2500")

    process_first = Settings.from_env(project_root=tmp_path, env_override=False)
    notebook_reload = Settings.from_env(project_root=tmp_path, env_override=True)

    assert process_first.chunk_target_size == 2500
    assert notebook_reload.chunk_target_size == 2800


def test_worker_environment_uses_resolved_settings_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SCADA_PROJECT_ROOT", raising=False)
    monkeypatch.delenv("SCADA_DATA_DIR", raising=False)
    settings = Settings(project_root=tmp_path, data_dir=tmp_path / "artifacts")

    settings.configure_worker_environment()

    assert os.environ["SCADA_PROJECT_ROOT"] == str(tmp_path)
    assert os.environ["SCADA_DATA_DIR"] == str(tmp_path / "artifacts")


def test_relative_data_dir_is_owned_by_explicit_root(tmp_path, monkeypatch):
    monkeypatch.setenv("SCADA_DATA_DIR", "relative-artifacts")
    settings = Settings.from_env(project_root=tmp_path)
    assert settings.data_dir == tmp_path / "relative-artifacts"


def test_dotenv_root_is_resolved_once_relative_to_the_dotenv_file(tmp_path, monkeypatch):
    monkeypatch.delenv("SCADA_PROJECT_ROOT", raising=False)
    monkeypatch.delenv("SCADA_DATA_DIR", raising=False)
    env = tmp_path / ".env"
    env.write_text("SCADA_PROJECT_ROOT=project\nSCADA_DATA_DIR=local-data\n")
    settings = Settings.from_env(env_file=env)
    assert settings.project_root == tmp_path / "project"
    assert settings.data_dir == tmp_path / "project/local-data"
    explicit = Settings.from_env(project_root=tmp_path / "explicit", env_file=env)
    assert explicit.project_root == tmp_path / "explicit"


def test_process_root_precedes_dotenv_unless_override_is_requested(tmp_path, monkeypatch):
    monkeypatch.setenv("SCADA_PROJECT_ROOT", str(tmp_path / "process"))
    env = tmp_path / ".env"
    env.write_text("SCADA_PROJECT_ROOT=from-file\n")
    assert Settings.from_env(env_file=env).project_root == tmp_path / "process"
    assert Settings.from_env(env_file=env, env_override=True).project_root == tmp_path / "from-file"


def test_external_primary_pdf_is_used_without_exposing_its_directory(tmp_path):
    external = tmp_path / "private" / "manual.pdf"
    external.parent.mkdir()
    external.write_bytes(b"synthetic")
    settings = Settings(project_root=tmp_path / "project", data_dir=tmp_path / "data",
                        default_pdf_path_override=external)
    assert settings.for_default_document().require_default_pdf() == external
    assert settings.default_pdf_display_path == "manual.pdf"


@pytest.mark.parametrize("changes", [
    {"embedding_dimension": 384}, {"embedding_batch_size": 0},
    {"default_top_k": 13}, {"max_top_k": 0}, {"api_workers": 2},
    {"ingestion_workers": 2}, {"max_pending_jobs": 0}, {"retained_jobs": 0},
    {"document_key": "../escape"}, {"default_document_key": "invalid-"},
])
def test_incompatible_settings_fail_early(tmp_path, changes):
    settings = replace(Settings(project_root=tmp_path, data_dir=tmp_path / "data"), **changes)
    with pytest.raises(ValueError):
        settings.validate()
