"""Application service coordinating routing, memory, retrieval, and answers."""

from __future__ import annotations

import logging

from intelligent_scada.config import Settings, validate_document_key
from intelligent_scada.contracts import AnswerResponse
from intelligent_scada.embeddings.embedding_service import EmbeddingService
from intelligent_scada.images.image_lookup import ImageLookup
from intelligent_scada.memory.memory_filters import (
    is_context_useful,
    requests_fresh_context,
)
from intelligent_scada.memory.memory_store import MemoryStore
from intelligent_scada.rag.answer_generator import AnswerGenerator
from intelligent_scada.rag.citations import CitationValidationError, used_citations
from intelligent_scada.rag.llm_client import OpenAICompatibleClient
from intelligent_scada.retrieval.retriever import Retriever
from intelligent_scada.router.decision_router import DecisionRouter

LOGGER = logging.getLogger(__name__)


class RAGService:
    def __init__(
        self,
        *,
        retriever: Retriever,
        answer_generator: AnswerGenerator,
        router: DecisionRouter,
        image_lookup: ImageLookup | None = None,
        memory_store: MemoryStore | None = None,
        memory_summary_threshold: int,
        default_document_key: str,
        default_document_name: str,
        min_retrieval_score: float,
    ) -> None:
        self.retriever = retriever
        self.answer_generator = answer_generator
        self.router = router
        self.image_lookup = image_lookup
        self.memory_store = memory_store
        self.memory_summary_threshold = memory_summary_threshold
        self.default_document_key = default_document_key
        self.default_document_name = default_document_name
        self.min_retrieval_score = min_retrieval_score

    @classmethod
    def from_settings(cls, settings: Settings) -> RAGService:
        embedder = EmbeddingService(
            settings.embedding_model_name,
            expected_dimension=settings.embedding_dimension,
            batch_size=settings.embedding_batch_size,
            hf_token=settings.hf_token,
            revision=settings.embedding_model_revision,
        )
        answer_client = OpenAICompatibleClient(
            base_url=settings.answer_base_url,
            api_key=settings.answer_api_key,
            model=settings.answer_model,
        )
        router_client = None
        if settings.router_enabled:
            router_client = OpenAICompatibleClient(
                base_url=settings.router_base_url,
                api_key=settings.router_api_key,
                model=settings.router_model,
            )
        return cls(
            retriever=Retriever(settings.pg_conn_str, embedder, max_top_k=settings.max_top_k),
            answer_generator=AnswerGenerator(answer_client),
            router=DecisionRouter(
                default_top_k=settings.default_top_k,
                max_top_k=settings.max_top_k,
                client=router_client,
            ),
            image_lookup=ImageLookup(settings.pg_conn_str, data_root=settings.data_dir),
            memory_store=MemoryStore(settings.pg_conn_str),
            memory_summary_threshold=settings.memory_summary_threshold,
            default_document_key=settings.default_document_key,
            default_document_name=settings.default_document_name,
            min_retrieval_score=settings.min_retrieval_score,
        )

    def ask(
        self,
        question: str,
        document_key: str | None = None,
        *,
        session_id: str | None = None,
        memory_enabled: bool = True,
        include_images: bool | None = None,
        top_k: int | None = None,
    ) -> AnswerResponse:
        if not question.strip():
            raise ValueError("Question cannot be empty")

        resolved_document_key = (document_key or self.default_document_key).strip()
        validate_document_key(resolved_document_key)

        # Obvious conversational, hostile-only, nonsense, and unrelated requests are
        # answered before touching embeddings, pgvector, memory, or the answer provider.
        decision = self.router.route(question)
        contextual_candidate = (
            decision.intent == "clarification"
            and decision.is_followup
            and bool(session_id)
            and memory_enabled
            and not requests_fresh_context(question)
        )
        if not decision.requires_retrieval and not contextual_candidate:
            return {
                "answer": decision.direct_response or "Please ask a Power SCADA question.",
                "citations": [],
                "sources": [],
                "related_images": [],
                "session_id": session_id,
                "routing": decision.to_dict(),
            }

        summary = ""
        recent_messages: list[dict[str, str]] = []
        resolved_session_id: str | None = None
        use_memory_for_request = memory_enabled and not requests_fresh_context(question)

        if self.memory_store is not None and memory_enabled:
            resolved_session_id = self.memory_store.create_or_load_session(
                resolved_document_key,
                session_id,
                memory_enabled=memory_enabled,
            )
            if use_memory_for_request:
                context = self.memory_store.context(resolved_session_id)
                if context["memory_enabled"]:
                    summary = str(context["summary"])
                    recent_messages = list(context["messages"])

        if (summary or recent_messages) and (
            contextual_candidate or decision.use_memory or decision.is_followup
            or self.router.is_followup(question)
        ):
            decision = self.router.route(
                question, summary=summary, recent_messages=recent_messages,
            )
        if not decision.use_memory:
            summary = ""
            recent_messages = []

        if not decision.requires_retrieval:
            return {
                "answer": decision.direct_response or "Please ask a Power SCADA question.",
                "citations": [],
                "sources": [],
                "related_images": [],
                "session_id": resolved_session_id,
                "routing": decision.to_dict(),
            }

        if resolved_session_id and self.memory_store is not None:
            self.memory_store.add_message(
                resolved_session_id,
                "user",
                question,
                useful=is_context_useful(question),
            )

        raw_results = self.retriever.retrieve(
            decision.retrieval_query,
            resolved_document_key,
            top_k=top_k or decision.top_k,
        )
        results = [
            result for result in raw_results if result["score"] >= self.min_retrieval_score
        ]
        if results:
            answer = self.answer_generator.generate(
                question,
                results,
                summary=summary,
                recent_messages=recent_messages,
            )
        else:
            manual_name = (
                self.default_document_name
                if resolved_document_key == self.default_document_key
                else "the selected indexed manual"
            )
            answer = (
                f"I couldn't find enough information in {manual_name} to answer that reliably. "
                "Try rephrasing the question, naming the subsystem or section, or selecting "
                "another indexed manual."
            )

        valid_answer = bool(results)
        try:
            citations = used_citations(answer, results)
        except CitationValidationError:
            LOGGER.warning("Answer rejected because it used an unknown source marker")
            valid_answer = False
            citations = []
            answer = ("I couldn't validate the answer's source references. "
                      "Please rephrase the question or try again.")
        should_include_images = (
            decision.needs_images if include_images is None else include_images
        )
        related_images = []
        if valid_answer and should_include_images and self.image_lookup is not None:
            related_images = self.image_lookup.for_chunks(
                resolved_document_key, [result["chunk_id"] for result in results]
            )

        if resolved_session_id and self.memory_store is not None:
            useful_count = self.memory_store.add_message(
                resolved_session_id,
                "assistant",
                answer,
                useful=valid_answer,
                citations=citations,
            )
            if (
                valid_answer
                and self.memory_summary_threshold > 0
                and useful_count >= self.memory_summary_threshold
                and useful_count % self.memory_summary_threshold == 0
            ):
                try:
                    context = self.memory_store.context(
                        resolved_session_id, limit=self.memory_summary_threshold
                    )
                    new_summary = self.answer_generator.summarize(
                        str(context["summary"]), list(context["messages"])
                    )
                    self.memory_store.update_summary(resolved_session_id, new_summary)
                except Exception as exc:
                    LOGGER.warning("Secondary memory summary failed (%s); preserving the answer", type(exc).__name__)

        return {
            "answer": answer,
            "citations": citations,
            "sources": results,
            "related_images": related_images,
            "session_id": resolved_session_id,
            "routing": decision.to_dict(),
        }
