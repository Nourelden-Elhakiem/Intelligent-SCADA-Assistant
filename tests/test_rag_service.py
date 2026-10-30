import pytest

from intelligent_scada.config import DEFAULT_DOCUMENT_KEY, DEFAULT_DOCUMENT_NAME
from intelligent_scada.rag.service import RAGService
from intelligent_scada.router.decision_router import DecisionRouter


def retrieval_result(*, score: float = 0.91):
    return {
        "chunk_id": "chunk_000001",
        "text": "Controller and alarm architecture text",
        "page_start": 10,
        "page_end": 10,
        "source_pages": [10],
        "section_title": "Architecture",
        "section_path": ["Plan", "Architecture"],
        "score": score,
    }


class SpyRetriever:
    def __init__(self, results=None) -> None:
        self.results = results if results is not None else [retrieval_result()]
        self.calls = []

    def retrieve(self, query, document_key, *, top_k):
        self.calls.append((query, document_key, top_k))
        return self.results


class SpyAnswerGenerator:
    def __init__(self) -> None:
        self.generate_calls = 0
        self.summary_calls = 0

    def generate(self, question, results, *, summary="", recent_messages=()):
        self.generate_calls += 1
        return "The controller architecture is described in the manual [S1]."

    def summarize(self, previous_summary, messages):
        self.summary_calls += 1
        return "summary"


class FakeImageLookup:
    def for_chunks(self, document_key, chunk_ids):
        assert chunk_ids == ["chunk_000001"]
        return [
            {
                "filename": "diagram.png",
                "page": 10,
                "width": 800,
                "height": 600,
                "file_size_bytes": 2000,
            }
        ]


class FakeMemoryStore:
    def __init__(self) -> None:
        self.added = []
        self.context_messages = [
            {"role": "user", "content": "How do I configure alarm priorities?"},
            {
                "role": "assistant",
                "content": "Alarm priorities are configured in the alarm settings.",
            },
        ]

    def create_or_load_session(self, document_key, session_id, *, memory_enabled=True):
        assert document_key == "manual"
        return session_id or "session-1"

    def context(self, session_id, *, limit=8):
        return {
            "summary": "",
            "memory_enabled": True,
            "useful_message_count": 2,
            "messages": self.context_messages,
        }

    def add_message(self, session_id, role, content, *, useful, citations=None):
        self.added.append((role, content))
        return len(self.added) + 2

    def update_summary(self, session_id, summary):
        return None


class FailingRouterClient:
    def chat(self, *args, **kwargs):
        raise AssertionError("The router model must not be called for deterministic greetings")


def build_service(*, results=None, images=False, memory_store=None):
    retriever = SpyRetriever(results)
    generator = SpyAnswerGenerator()
    service = RAGService(
        retriever=retriever,
        answer_generator=generator,
        router=DecisionRouter(default_top_k=6),
        image_lookup=FakeImageLookup() if images else None,
        memory_store=memory_store,
        memory_summary_threshold=100,
        default_document_key=DEFAULT_DOCUMENT_KEY,
        default_document_name=DEFAULT_DOCUMENT_NAME,
        min_retrieval_score=0.25,
    )
    return service, retriever, generator


def test_rag_service_returns_sources_citations_and_optional_images() -> None:
    service, retriever, generator = build_service(images=True)

    response = service.ask(
        "show the controller diagram",
        "manual",
        memory_enabled=False,
    )

    assert retriever.calls == [("show the controller diagram", "manual", 6)]
    assert generator.generate_calls == 1
    assert response["answer"].endswith("[S1].")
    assert response["citations"][0]["label"] == "Plan > Architecture — p. 10"
    assert response["related_images"][0]["filename"] == "diagram.png"
    assert response["routing"]["intent"] == "image_request"
    assert response["routing"]["needs_images"] is True


@pytest.mark.parametrize(
    ("question", "expected_intent"),
    [
        ("Hello", "conversational"),
        ("مرحبا", "conversational"),
        ("Thanks", "conversational"),
        ("Hallo", "conversational"),
        ("Hello, how are you?", "conversational"),
        ("How are you?", "conversational"),
        ("Great, thank you", "conversational"),
        ("You are a useless idiot.", "abusive_nontechnical"),
        ("...", "clarification"),
        ("What is the capital of France?", "out_of_scope"),
    ],
)
def test_non_rag_messages_never_call_retrieval(question, expected_intent) -> None:
    service, retriever, generator = build_service()

    response = service.ask(question, memory_enabled=False)

    assert retriever.calls == []
    assert generator.generate_calls == 0
    assert response["routing"]["intent"] == expected_intent
    assert response["routing"]["requires_retrieval"] is False
    assert response["citations"] == []
    assert response["sources"] == []


def test_greeting_never_calls_optional_router_model() -> None:
    decision = DecisionRouter(client=FailingRouterClient()).route("Hello")

    assert decision.intent == "conversational"
    assert decision.requires_retrieval is False


@pytest.mark.parametrize(
    "question",
    [
        "How do I configure the controller?",
        "How are alarms configured?",
        "You are useless, how does alarm acknowledgement work?",
    ],
)
def test_scada_questions_use_retrieval(question) -> None:
    service, retriever, generator = build_service()

    response = service.ask(question, "manual", memory_enabled=False)

    assert len(retriever.calls) == 1
    assert retriever.calls[0][1] == "manual"
    assert generator.generate_calls == 1
    assert response["routing"]["requires_retrieval"] is True


def test_default_document_is_used_when_document_key_is_omitted() -> None:
    service, retriever, _ = build_service()

    service.ask("How do I configure the controller?", memory_enabled=False)

    assert retriever.calls[0][1] == DEFAULT_DOCUMENT_KEY


def test_architecture_diagram_uses_retrieval_and_image_intent() -> None:
    service, retriever, _ = build_service(images=True)

    response = service.ask("Show the architecture diagram", "manual", memory_enabled=False)

    assert len(retriever.calls) == 1
    assert response["routing"]["intent"] == "image_request"
    assert response["routing"]["needs_images"] is True


def test_configure_word_does_not_trigger_figure_image_intent() -> None:
    decision = DecisionRouter().route("How do I configure the controller?")

    assert decision.requires_retrieval is True
    assert decision.needs_images is False


def test_technical_followup_uses_session_context_for_retrieval() -> None:
    memory = FakeMemoryStore()
    service, retriever, _ = build_service(memory_store=memory)

    response = service.ask(
        "What about acknowledgement?",
        "manual",
        session_id="session-1",
        memory_enabled=True,
    )

    query, document_key, _ = retriever.calls[0]
    assert document_key == "manual"
    assert "alarm priorities" in query.lower()
    assert "acknowledgement" in query.lower()
    assert response["routing"]["is_followup"] is True
    assert response["routing"]["intent"] == "technical_followup"


def test_short_followup_without_scada_keyword_uses_session_context() -> None:
    memory = FakeMemoryStore()
    service, retriever, _ = build_service(memory_store=memory)

    response = service.ask(
        "Why?",
        "manual",
        session_id="session-1",
        memory_enabled=True,
    )

    assert len(retriever.calls) == 1
    assert "alarm priorities" in retriever.calls[0][0].lower()
    assert response["routing"]["intent"] == "technical_followup"


def test_weak_retrieval_does_not_generate_or_cite_an_answer() -> None:
    service, retriever, generator = build_service(results=[retrieval_result(score=0.1)])

    response = service.ask("How do I configure the controller?", "manual", memory_enabled=False)

    assert len(retriever.calls) == 1
    assert generator.generate_calls == 0
    assert response["sources"] == []
    assert response["citations"] == []
    assert "couldn't find enough information" in response["answer"]


def test_router_applies_safety_and_deeper_retrieval_flags() -> None:
    decision = DecisionRouter(default_top_k=5, max_top_k=10).route(
        "What troubleshooting steps apply before emergency shutdown?"
    )
    assert decision.requires_retrieval is True
    assert decision.safety_sensitive is True
    assert decision.top_k == 7


def test_memory_off_never_touches_existing_session():
    class ForbiddenMemory:
        def __getattr__(self, name):
            raise AssertionError(f'Memory off accessed {name}')

    service, _, generator = build_service(memory_store=ForbiddenMemory())
    response = service.ask('Explain the alarm', 'manual', session_id='old', memory_enabled=False)
    assert generator.generate_calls == 1
    assert response['session_id'] is None


def test_no_evidence_never_calls_summary_provider():
    memory = FakeMemoryStore()
    service, _, generator = build_service(results=[], memory_store=memory)
    service.memory_summary_threshold = 1
    service.ask('Explain the alarm', 'manual', session_id='old')
    assert generator.generate_calls == generator.summary_calls == 0


def test_summary_failure_does_not_discard_answer(monkeypatch):
    service, _, generator = build_service(memory_store=FakeMemoryStore())
    service.memory_summary_threshold = 1

    def fail(*args):
        raise RuntimeError('synthetic summary outage')

    monkeypatch.setattr(generator, 'summarize', fail)
    response = service.ask('Explain the alarm', 'manual')
    assert '[S1]' in response['answer']


def test_unknown_source_marker_returns_safe_failure(monkeypatch):
    service, _, generator = build_service()
    monkeypatch.setattr(generator, 'generate', lambda *a, **kw: 'Wrong source [S99].')
    response = service.ask('Explain the alarm', 'manual', memory_enabled=False)
    assert response['citations'] == []
    assert response['sources']
    assert "couldn't validate" in response['answer']


def test_ambiguous_request_uses_one_router_call_without_new_context():
    import json

    from test_router import Client, valid_decision

    service, _, _ = build_service()
    client = Client(json.dumps(valid_decision()))
    service.router = DecisionRouter(client=client)
    service.ask('Explain remote sensing', 'manual', memory_enabled=False)
    assert client.calls == 1
