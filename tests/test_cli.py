import pytest

from intelligent_scada.cli import main


def test_cli_help_smoke() -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--help"])
    assert exit_info.value.code == 0


def test_serve_rejects_effective_worker_override(tmp_path, monkeypatch):
    monkeypatch.setenv('SCADA_PROJECT_ROOT', str(tmp_path))
    assert main(['serve', '--workers', '2']) == 1


def test_cli_data_dir_precedes_command_and_is_dispatched(tmp_path, monkeypatch):
    from intelligent_scada.cli import Pipeline
    monkeypatch.setenv('SCADA_PROJECT_ROOT', str(tmp_path))
    seen = []
    monkeypatch.setattr(Pipeline, 'analyze_pdf', lambda self, pdf, **kwargs:
                        seen.append((self.settings.data_dir, pdf)) or {'total_pages': 1, 'toc_entries': 1})
    assert main(['--data-dir', 'isolated', 'analyze-pdf', str(tmp_path / 'fixture.pdf')]) == 0
    assert seen == [(tmp_path / 'isolated', tmp_path / 'fixture.pdf')]
