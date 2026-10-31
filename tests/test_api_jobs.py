import time

from intelligent_scada.api.jobs import JobManager
from intelligent_scada.config import Settings


class FakePipeline:
    def __init__(self, settings, progress_callback=None):
        self.settings = settings
        self.progress_callback = progress_callback

    def ingest(self, pdf_path, **options):
        self.progress_callback("text", 0.4, "Cleaning text")
        self.progress_callback("completed", 1.0, "Complete")
        return {"pdf": str(pdf_path), "chunks": 3}


def test_job_manager_runs_pipeline_and_records_completion(tmp_path) -> None:
    settings = Settings(
        project_root=tmp_path,
        data_dir=tmp_path / "data",
        ingestion_workers=1,
    )
    pdf_path = settings.documents_dir / "manual" / "pdf" / "manual.pdf"
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")
    manager = JobManager(settings, pipeline_factory=FakePipeline)
    job = manager.submit_ingestion(
        pdf_path,
        document_name="Manual",
        document_key="manual",
        include_images=True,
        resume=False,
        force=False,
    )

    deadline = time.monotonic() + 2
    current = manager.get(job["job_id"])
    while current and current["status"] in {"queued", "running"}:
        if time.monotonic() > deadline:
            raise AssertionError("The ingestion job did not complete")
        time.sleep(0.01)
        current = manager.get(job["job_id"])
    manager.shutdown()

    assert current is not None
    assert current["status"] == "succeeded"
    assert current["progress"] == 1.0
    assert current["result"]["chunks"] == 3


def test_atomic_reservation_blocks_duplicate_upload_and_deletion(settings):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    import pytest

    from intelligent_scada.api.jobs import DocumentBusyError

    manager = JobManager(settings)
    barrier = Barrier(2)

    def reserve():
        barrier.wait()
        try:
            return manager.reserve_document('manual')
        except DocumentBusyError:
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        tokens = list(executor.map(lambda _: reserve(), range(2)))
    assert sum(token is not None for token in tokens) == 1
    with pytest.raises(DocumentBusyError), manager.document_operation('manual'):
        pass
    manager.release_document('manual', next(token for token in tokens if token))
    with manager.document_operation('manual'), pytest.raises(DocumentBusyError):
        manager.reserve_document('manual')
    assert not manager.has_active_document('manual')
    manager.shutdown()


def test_queue_is_bounded_and_failed_submission_releases_owner(settings, tmp_path, monkeypatch):
    from dataclasses import replace

    import pytest

    from intelligent_scada.api.jobs import QueueFullError

    manager = JobManager(replace(settings, max_pending_jobs=1))
    manager.reserve_document('one')
    manager.reserve_document('two')
    with pytest.raises(QueueFullError):
        manager.reserve_document('three')
    manager.release_document('two', manager._owners['two'][0])

    def fail(*args):
        raise RuntimeError('executor unavailable')

    monkeypatch.setattr(manager._executor, 'submit', fail)
    with pytest.raises(RuntimeError):
        manager.submit_ingestion(tmp_path / 'fake.pdf', document_name='Three',
                                 document_key='three', include_images=False,
                                 resume=False, force=False)
    assert not manager.has_active_document('three')
    assert manager.list() == []
    manager.shutdown()


def test_job_error_is_safe_and_completed_history_is_bounded(settings, tmp_path):
    from dataclasses import replace

    class FailingPipeline:
        def __init__(self, *args, **kwargs):
            pass

        def ingest(self, *args, **kwargs):
            raise RuntimeError('/private/local/path secret=synthetic-private')

    manager = JobManager(replace(settings, retained_jobs=1), pipeline_factory=FailingPipeline)
    for key in ('one', 'two'):
        job = manager.submit_ingestion(tmp_path / key / 'pdf' / 'manual.pdf',
                                      document_name=key, document_key=key,
                                      include_images=False, resume=False, force=False)
        deadline = time.monotonic() + 2
        while manager.has_active_document(key):
            assert time.monotonic() < deadline
            time.sleep(0.005)
        current = manager.get(job['job_id'])
        assert current['status'] == 'failed'
        assert 'synthetic-private' not in current['error']
        assert '/private' not in current['error']
    assert len(manager.list()) == 1
    manager.shutdown()
