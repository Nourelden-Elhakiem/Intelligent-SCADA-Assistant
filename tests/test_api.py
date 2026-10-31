from datetime import UTC, datetime

from fastapi.testclient import TestClient

from intelligent_scada.api.app import create_app
from intelligent_scada.config import Settings


class FakeJobManager:
    def __init__(self) -> None:
        self.submissions = []
        self.reservations = set()

    def has_active_document(self, document_key):
        return document_key in self.reservations

    def reserve_document(self, document_key):
        self.reservations.add(document_key)
        return 'reservation'

    def release_document(self, document_key, reservation):
        self.reservations.discard(document_key)

    def submit_ingestion(self, pdf_path, **options):
        options["staged_path"].replace(pdf_path)
        self.submissions.append((pdf_path, options))
        return {
            "job_id": "job-1",
            "document_key": options["document_key"],
            "document_name": options["document_name"],
            "status": "queued",
            "stage": "queued",
            "progress": 0.0,
            "message": "Waiting for an ingestion worker",
            "created_at": datetime.now(UTC),
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": None,
        }

    def get(self, job_id):
        return None

    def list(self, *, limit=50):
        return []

    def shutdown(self):
        return None


class FakeRAGService:
    def __init__(self, expected_document_key="manual") -> None:
        self.expected_document_key = expected_document_key

    def ask(self, question, document_key, **options):
        assert question == "How is the controller configured?"
        assert document_key == self.expected_document_key
        return {
            "answer": "Use the controller settings page [S1].",
            "citations": [
                {
                    "source_id": "S1",
                    "chunk_id": "chunk_000001",
                    "label": "Controller > Configuration — p. 10",
                    "page_start": 10,
                    "page_end": 10,
                    "section_path": ["Controller", "Configuration"],
                }
            ],
            "sources": [
                {
                    "chunk_id": "chunk_000001",
                    "text": "Use the controller settings page.",
                    "page_start": 10,
                    "page_end": 10,
                    "source_pages": [10],
                    "section_title": "Configuration",
                    "section_path": ["Controller", "Configuration"],
                    "score": 0.94,
                }
            ],
            "related_images": [],
            "session_id": "d1f858ad-7dfa-414f-b4c2-86d87a771f4a",
            "routing": {"top_k": 6},
        }


class ReadyRepository:
    def ping(self):
        return True

    def list_documents(self):
        now = datetime.now(UTC)
        return [
            {
                "document_key": "power-scada-operation-2020-system-guide",
                "document_name": "Power SCADA Operation 2020 System Guide",
                "source_filename": "Power SCADA Operation 2020 System Guide.pdf",
                "embedding_model": "sentence-transformers/all-mpnet-base-v2",
                "embedding_dimension": 768,
                "chunk_count": 42,
                "image_count": 3,
                "created_at": now,
                "updated_at": now,
            }
        ]

    def get_document(self, document_key):
        documents = self.list_documents()
        return documents[0] if documents[0]["document_key"] == document_key else None


def test_health_runtime_and_spa_smoke(tmp_path, monkeypatch) -> None:
    settings = Settings(
        project_root=tmp_path,
        data_dir=tmp_path / "data",
        auto_init_db=False,
    )
    frontend = tmp_path / 'frontend-fixture'
    frontend.mkdir()
    (frontend / 'index.html').write_text('<html>Intelligent SCADA Assistant</html>')
    monkeypatch.setattr(Settings, 'frontend_dist_dir', property(lambda self: frontend))
    app = create_app(settings, job_manager=FakeJobManager())
    with TestClient(app) as client:
        health = client.get("/api/v1/health")
        runtime = client.get("/api/v1/runtime")
        root = client.get("/")

    assert health.status_code == 200
    assert health.json()["database"] == "not_configured"
    assert health.json()["knowledge_base"] == "database_not_configured"
    assert health.json()["default_pdf"] == "missing"
    assert runtime.json()["embedding_dimension"] == 768
    assert runtime.json()["default_document_key"] == ("power-scada-operation-2020-system-guide")
    assert runtime.json()["default_pdf_path"] == (
        "data/pdf/Power SCADA Operation 2020 System Guide.pdf"
    )
    assert root.status_code == 200
    assert root.headers["content-type"].startswith("text/html")
    assert "Intelligent SCADA Assistant" in root.text


def test_health_and_document_list_mark_ready_default_manual(tmp_path) -> None:
    settings = Settings(
        project_root=tmp_path,
        data_dir=tmp_path / "data",
        pg_conn_str="postgresql://test-only",
        auto_init_db=False,
    )
    app = create_app(settings, job_manager=FakeJobManager())
    app.state.repository = ReadyRepository()

    with TestClient(app) as client:
        health = client.get("/api/v1/health")
        documents = client.get("/api/v1/documents")

    assert health.status_code == 200
    assert health.json()["knowledge_base"] == "ready"
    assert health.json()["default_document"] == "indexed"
    assert documents.json()["documents"][0]["is_default"] is True


def test_pdf_upload_is_validated_saved_and_queued(tmp_path) -> None:
    manager = FakeJobManager()
    settings = Settings(
        project_root=tmp_path,
        data_dir=tmp_path / "data",
        auto_init_db=False,
    )
    app = create_app(settings, job_manager=manager)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": ("Controller Guide.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
            data={
                "document_name": "Controller Guide",
                "document_key": "controller-guide",
                "include_images": "true",
            },
        )

    assert response.status_code == 202
    assert response.json()["document_key"] == "controller-guide"
    saved_path, options = manager.submissions[0]
    assert saved_path.read_bytes().startswith(b"%PDF-")
    assert saved_path.parent.parent == settings.documents_dir / "controller-guide"
    assert options["include_images"] is True


def test_chat_endpoint_returns_typed_citations(tmp_path) -> None:
    settings = Settings(
        project_root=tmp_path,
        data_dir=tmp_path / "data",
        auto_init_db=False,
    )
    app = create_app(
        settings,
        job_manager=FakeJobManager(),
        rag_factory=lambda _: FakeRAGService(),
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat/ask",
            json={
                "question": "How is the controller configured?",
                "document_key": "manual",
                "memory_enabled": True,
                "include_images": True,
                "top_k": 6,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"].endswith("[S1].")
    assert payload["sources"][0]["score"] == 0.94


def test_chat_endpoint_accepts_default_document_without_document_key(tmp_path) -> None:
    settings = Settings(
        project_root=tmp_path,
        data_dir=tmp_path / "data",
        auto_init_db=False,
    )
    service = FakeRAGService(expected_document_key=None)
    app = create_app(
        settings,
        job_manager=FakeJobManager(),
        rag_factory=lambda _: service,
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat/ask",
            json={
                "question": "How is the controller configured?",
                "memory_enabled": False,
            },
        )

    assert response.status_code == 200
    assert response.json()["citations"][0]["source_id"] == "S1"


def test_missing_build_has_honest_backend_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(Settings, 'frontend_dist_dir', property(lambda self: tmp_path / 'missing'))
    app = create_app(Settings(project_root=tmp_path, data_dir=tmp_path / 'data',
                              auto_init_db=False), job_manager=FakeJobManager())
    with TestClient(app) as client:
        assert client.get('/').json()['api_docs'] == '/api/docs'
        assert client.get('/chat').status_code == 404


def test_invalid_ids_rejected_before_service_or_database(tmp_path):
    app = create_app(Settings(project_root=tmp_path, data_dir=tmp_path / 'data',
                              auto_init_db=False), job_manager=FakeJobManager())
    with TestClient(app) as client:
        for value in ['../private', 'a--b', '-bad']:
            response = client.post('/api/v1/chat/ask', json={'question': 'alarm',
                                                          'document_key': value})
            assert response.status_code == 422
        assert client.post('/api/v1/chat/ask', json={'question': 'alarm',
                                                   'session_id': 'invalid'}).status_code == 422
        assert client.get('/api/v1/sessions/invalid/messages').status_code == 422


def test_invalid_upload_releases_reservation_and_removes_temporary_file(tmp_path):
    manager = FakeJobManager()
    settings = Settings(project_root=tmp_path, data_dir=tmp_path / 'data', auto_init_db=False)
    app = create_app(settings, job_manager=manager)
    with TestClient(app) as client:
        response = client.post('/api/v1/documents/upload',
                               files={'file': ('bad.pdf', b'not pdf', 'application/pdf')})
    assert response.status_code == 415
    assert manager.reservations == set()
    assert not list(settings.data_dir.rglob('.upload-*'))
    assert not manager.submissions


def test_ingress_limit_rejects_before_upload_parsing(tmp_path):
    settings = Settings(project_root=tmp_path, data_dir=tmp_path / 'data',
                        max_upload_mb=1, auto_init_db=False)
    app = create_app(settings, job_manager=FakeJobManager())
    with TestClient(app) as client:
        response = client.post('/api/v1/documents/upload', content=b'x' * (2 * 1024 * 1024))
    assert response.status_code == 413


def test_public_errors_do_not_echo_exception_details(tmp_path):
    class FailingService:
        def ask(self, *args, **kwargs):
            raise ValueError('/private/user/token=synthetic-secret')

    settings = Settings(project_root=tmp_path, data_dir=tmp_path / 'data', auto_init_db=False)
    app = create_app(settings, job_manager=FakeJobManager(), rag_factory=lambda _: FailingService())
    with TestClient(app) as client:
        response = client.post('/api/v1/chat/ask', json={'question': 'alarm'})
    assert response.status_code == 422
    assert 'synthetic-secret' not in response.text
    assert '/private' not in response.text


def test_chunked_upload_body_limit_returns_413(tmp_path):
    settings = Settings(project_root=tmp_path, data_dir=tmp_path / 'data',
                        max_upload_mb=1, auto_init_db=False)
    manager = FakeJobManager()
    app = create_app(settings, job_manager=manager)
    def body():
        yield b'--fixture\r\nContent-Disposition: form-data; name="file"; filename="large.pdf"\r\nContent-Type: application/pdf\r\n\r\n%PDF-1.4\n'
        yield b'x' * (2 * 1024 * 1024)
        yield b'\r\n--fixture--\r\n'
    with TestClient(app) as client:
        response = client.post('/api/v1/documents/upload', content=body(),
            headers={'Content-Type': 'multipart/form-data; boundary=fixture'})
    assert response.status_code == 413
    assert not manager.submissions
    assert not manager.reservations
