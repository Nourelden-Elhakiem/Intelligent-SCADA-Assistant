"""Small, testable router that keeps obvious messages away from RAG."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Literal

from intelligent_scada.router.router_prompt import ROUTER_SYSTEM_PROMPT

if TYPE_CHECKING:
    from intelligent_scada.rag.llm_client import OpenAICompatibleClient

RouteIntent = Literal[
    "conversational",
    "technical_rag",
    "technical_followup",
    "image_request",
    "clarification",
    "abusive_nontechnical",
    "out_of_scope",
]

IMAGE_TERMS = {
    "diagram",
    "image",
    "screen",
    "screenshot",
    "figure",
    "schematic",
    "visual",
    "drawing",
    "مخطط",
    "صورة",
}
SAFETY_TERMS = {
    "safety",
    "shutdown",
    "trip",
    "protection",
    "interlock",
    "energized",
    "high voltage",
    "emergency",
    "سلامة",
    "حماية",
    "طوارئ",
}
DEEP_RETRIEVAL_TERMS = {
    "troubleshoot",
    "configure",
    "configuration",
    "procedure",
    "steps",
    "error",
    "failed",
    "architecture",
    "استكشاف",
    "تهيئة",
    "إعداد",
}
TECHNICAL_TERMS = {
    "power scada",
    "scada",
    "tag", "tags", "voltage", "current", "opc", "opc ua", "dnp3", "setpoint",
    "alarms", "configured", "troubleshooting", "trends", "redundancy",
    "controller",
    "alarm",
    "acknowledg",
    "communication",
    "configure",
    "configuration",
    "architecture",
    "installation",
    "install",
    "troubleshoot",
    "system operation",
    "operation",
    "component",
    "procedure",
    "specification",
    "manual",
    "section",
    "page",
    "diagram",
    "image",
    "figure",
    "screenshot",
    "schematic",
    "modbus",
    "iec 61850",
    "ethernet",
    "protocol",
    "gateway",
    "breaker",
    "meter",
    "historian",
    "device",
    "driver",
    "server",
    "network",
    "priority",
    "سكادا",
    "وحدة تحكم",
    "متحكم",
    "إنذار",
    "انذار",
    "اتصال",
    "اتصالات",
    "تهيئة",
    "إعداد",
    "اعداد",
    "تشغيل",
    "تركيب",
    "معمارية",
    "بنية النظام",
    "استكشاف الأخطاء",
    "مخطط",
    "دليل",
    "قسم",
    "صفحة",
}
GREETING_TERMS = {
    "hello",
    "hi",
    "hey",
    "hallo",
    "hello there",
    "hi there",
    "good morning",
    "good afternoon",
    "good evening",
    "مرحبا",
    "السلام عليكم",
    "صباح الخير",
    "مساء الخير",
}
THANKS_TERMS = {
    "thanks",
    "thank you",
    "thx",
    "danke",
    "many thanks",
    "great thanks",
    "great thank you",
    "great, thanks",
    "great, thank you",
    "okay thanks",
    "ok thanks",
    "شكرا",
    "تمام",
    "ماشي",
    "فهمت",
}
BYE_TERMS = {
    "bye",
    "goodbye",
    "see you",
    "مع السلامة",
    "الى اللقاء",
}
IDENTITY_TERMS = {
    "who are you",
    "what are you",
    "what can you do",
    "what do you do",
    "انت مين",
    "بتعمل ايه",
    "ماذا تستطيع ان تفعل",
}
SMALL_TALK_TERMS = {
    "how are you",
    "how is it going",
    "how's it going",
    "nice to meet you",
    "i am fine",
    "i'm fine",
    "i am good",
    "i'm good",
    "okay",
    "ok",
    "great",
    "cool",
    "amazing",
    "كيف حالك",
    "عامل ايه",
    "انا بخير",
    "كويس",
}
ABUSIVE_TERMS = {
    "idiot",
    "stupid",
    "useless",
    "moron",
    "dumb",
    "asshole",
    "fuck",
    "fucking",
    "shit",
    "غبي",
    "احمق",
    "تافه",
    "زبالة",
}
OUT_OF_SCOPE_TERMS = {
    "capital of france",
    "capital of",
    "write a poem",
    "write me a poem",
    "tell me a joke",
    "weather today",
    "weather in",
    "football score",
    "recipe for",
    "stock price",
    "عاصمة فرنسا",
    "اكتب قصيدة",
    "احكي نكتة",
    "الطقس",
}
FOLLOWUP_PREFIXES = (
    "what about",
    "and what about",
    "why",
    "how so",
    "what happens next",
    "what next",
    "the second option",
    "explain that",
    "explain it",
    "tell me more",
    "show me the diagram",
    "show the diagram",
    "وماذا عن",
    "ماذا عن",
    "ليه",
    "لماذا",
    "اشرح ذلك",
    "اشرح ده",
    "ماذا يحدث بعد ذلك",
    "ارني المخطط",
)
AMBIGUOUS_REASON = "ambiguous request"
KEYBOARD_NOISE = {
    "asdf",
    "asdfgh",
    "asdfghjkl",
    "qwerty",
    "qwertyuiop",
    "zxcv",
    "zxcvbnm",
}


def _normalise(text: str) -> str:
    value = text.lower().strip()
    value = re.sub(r"[\u064b-\u065f\u0670]", "", value)
    value = value.translate(str.maketrans("أإآى", "اااي"))
    value = re.sub(r"[\s\u00a0]+", " ", value)
    return value.strip(" \t\r\n.!?,;:؟،…\"'()[]{}")


def _contains_term(value: str, terms: set[str]) -> bool:
    return _contains_keyword(value, terms)


def _contains_keyword(value: str, terms: set[str]) -> bool:
    return any(
        re.search(rf"(?<!\w){re.escape(_normalise(term))}(?!\w)", value) is not None for term in terms
    )


def _contains_technical(value: str) -> bool:
    return (_contains_keyword(value, TECHNICAL_TERMS)
            or bool(re.search(r"\backnowledg\w*\b", value))) or bool(
        re.search(r"\b(?:plc|hmi|rtu|i/?o)\b", value)
    )


def _is_arabic(value: str) -> bool:
    return bool(re.search(r"[\u0600-\u06ff]", value))


def _context_is_technical(summary: str, recent_messages: Sequence[dict[str, str]]) -> bool:
    context = " ".join(
        [summary, *(str(message.get("content", "")) for message in recent_messages[-6:])]
    )
    return _contains_technical(_normalise(context))


def _is_followup(value: str) -> bool:
    if any(value.startswith(prefix) for prefix in FOLLOWUP_PREFIXES):
        return True
    return value in {"why", "how", "then", "next", "and", "ليه", "لماذا", "وبعدين"}


def _followup_query(question: str, recent_messages: Sequence[dict[str, str]]) -> str:
    for message in reversed(recent_messages):
        content = str(message.get("content", "")).strip()
        if message.get("role") == "user" and _contains_technical(_normalise(content)):
            return f"{content}\nFollow-up: {question.strip()}"
    return question.strip()


def _is_nonsense(value: str) -> bool:
    if not value:
        return True
    if value in KEYBOARD_NOISE:
        return True
    return re.search(r"[a-z0-9\u0600-\u06ff]", value) is None


def _direct_response(kind: str, *, arabic: bool) -> str:
    if arabic:
        responses = {
            "greeting": (
                "مرحباً، أنا مساعد Power SCADA. يمكنني مساعدتك في البحث وشرح المعلومات "
                "الموجودة في Power SCADA Operation 2020 System Guide مع ذكر المصادر والصفحات عند الحاجة."
            ),
            "thanks": "على الرحب والسعة. إذا احتجت شيئاً في Power SCADA فأنا جاهز.",
            "bye": "مع السلامة. أتمنى لك عملاً موفقاً مع Power SCADA.",
            "identity": (
                "أنا مساعد Power SCADA. أشرح محتوى Power SCADA Operation 2020 System Guide "
                "وأستخدم الدليل والمصادر عند الأسئلة الفنية."
            ),
            "small_talk": "أنا بخير، شكراً لك. كيف يمكنني مساعدتك في Power SCADA؟",
            "abusive": "أنا هنا للمساعدة. اكتب سؤالك الفني عن Power SCADA وسأحاول الإجابة بهدوء.",
            "clarification": "اكتب سؤالاً واضحاً عن Power SCADA لكي أستطيع مساعدتك.",
            "out_of_scope": (
                "أفضل ما أساعد فيه هو Power SCADA ودليله الفني. يمكنك سؤالي عن "
                "الإعداد أو الإنذارات أو الاتصالات أو التشغيل."
            ),
        }
    else:
        responses = {
            "greeting": (
                "Hello, I'm the Power SCADA Assistant. I can explain information from "
                "Power SCADA Operation 2020 System Guide and cite the relevant pages when needed."
            ),
            "thanks": "You're welcome. I'm here if you have another Power SCADA question.",
            "bye": "Goodbye. I hope your Power SCADA work goes smoothly.",
            "identity": (
                "I'm the Power SCADA Assistant. I answer technical questions from Power SCADA "
                "Operation 2020 System Guide and cite the manual when retrieval is needed."
            ),
            "small_talk": "I'm doing well, thank you. How can I help with Power SCADA?",
            "abusive": "I'm here to help. Send me a Power SCADA technical question and I'll focus on it.",
            "clarification": "Please provide a clear Power SCADA question so I can help.",
            "out_of_scope": (
                "I'm best suited to Power SCADA and its technical manual. You can ask me "
                "about configuration, alarms, communications, or system operation."
            ),
        }
    return responses[kind]


@dataclass(frozen=True, slots=True)
class RouterDecision:
    intent: RouteIntent
    requires_retrieval: bool
    out_of_scope: bool
    use_memory: bool
    needs_images: bool
    is_followup: bool
    safety_sensitive: bool
    top_k: int
    retrieval_query: str
    reason: str
    direct_response: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class DecisionRouter:
    def __init__(
        self,
        *,
        default_top_k: int = 6,
        max_top_k: int = 12,
        client: OpenAICompatibleClient | None = None,
    ) -> None:
        self.default_top_k = default_top_k
        self.max_top_k = max_top_k
        self.client = client

    @staticmethod
    def is_followup(question: str) -> bool:
        return _is_followup(_normalise(question))

    def _decision(
        self,
        question: str,
        *,
        intent: RouteIntent,
        requires_retrieval: bool,
        reason: str,
        direct_response: str | None = None,
        needs_images: bool = False,
        is_followup: bool = False,
        safety_sensitive: bool = False,
        retrieval_query: str | None = None,
        use_memory: bool | None = None,
    ) -> RouterDecision:
        value = _normalise(question)
        top_k = self.default_top_k
        if _contains_term(value, DEEP_RETRIEVAL_TERMS):
            top_k = min(self.max_top_k, self.default_top_k + 2)
        return RouterDecision(
            intent=intent,
            requires_retrieval=requires_retrieval,
            out_of_scope=intent == "out_of_scope",
            # use_memory answers "does resolving this need prior turns?" — that's
            # exactly what is_followup already captures, so default to it instead
            # of conflating "needs memory" with "needs retrieval".
            use_memory=is_followup if use_memory is None else use_memory,
            needs_images=needs_images,
            is_followup=is_followup,
            safety_sensitive=safety_sensitive,
            top_k=top_k,
            retrieval_query=retrieval_query or question.strip(),
            reason=reason,
            direct_response=direct_response,
        )

    def _heuristic(
        self,
        question: str,
        *,
        summary: str = "",
        recent_messages: Sequence[dict[str, str]] = (),
    ) -> RouterDecision:
        value = _normalise(question)
        arabic = _is_arabic(question)
        needs_images = _contains_keyword(value, IMAGE_TERMS)
        technical = _contains_technical(value)
        followup = _is_followup(value) and _context_is_technical(summary, recent_messages)

        # Technical intent has priority over hostile wording so a real request is not hidden.
        if technical or followup:
            intent: RouteIntent = (
                "image_request"
                if needs_images
                else "technical_followup"
                if followup
                else "technical_rag"
            )
            return self._decision(
                question,
                intent=intent,
                requires_retrieval=True,
                reason="technical manual request" if not followup else "technical follow-up",
                needs_images=needs_images,
                is_followup=followup,
                safety_sensitive=_contains_term(value, SAFETY_TERMS),
                retrieval_query=(
                    _followup_query(question, recent_messages) if followup else question.strip()
                ),
            )

        if _contains_keyword(value, GREETING_TERMS):
            return self._decision(
                question,
                intent="conversational",
                requires_retrieval=False,
                reason="greeting",
                direct_response=_direct_response("greeting", arabic=arabic),
            )
        if _contains_keyword(value, THANKS_TERMS):
            return self._decision(
                question,
                intent="conversational",
                requires_retrieval=False,
                reason="thanks",
                direct_response=_direct_response("thanks", arabic=arabic),
            )
        if _contains_keyword(value, BYE_TERMS):
            return self._decision(
                question,
                intent="conversational",
                requires_retrieval=False,
                reason="goodbye",
                direct_response=_direct_response("bye", arabic=arabic),
            )
        if _contains_term(value, IDENTITY_TERMS):
            return self._decision(
                question,
                intent="conversational",
                requires_retrieval=False,
                reason="assistant capability question",
                direct_response=_direct_response("identity", arabic=arabic),
            )
        if _contains_term(value, SMALL_TALK_TERMS):
            return self._decision(
                question,
                intent="conversational",
                requires_retrieval=False,
                reason="social pleasantry",
                direct_response=_direct_response("small_talk", arabic=arabic),
            )
        if _contains_term(value, ABUSIVE_TERMS):
            return self._decision(
                question,
                intent="abusive_nontechnical",
                requires_retrieval=False,
                reason="hostile message without technical request",
                direct_response=_direct_response("abusive", arabic=arabic),
            )
        followup_without_context = _is_followup(value) and not recent_messages
        if _is_nonsense(value) or followup_without_context:
            return self._decision(
                question,
                intent="clarification",
                requires_retrieval=False,
                reason="empty or unclear request",
                direct_response=_direct_response("clarification", arabic=arabic),
                is_followup=followup_without_context,
            )
        if _contains_term(value, OUT_OF_SCOPE_TERMS):
            return self._decision(
                question,
                intent="out_of_scope",
                requires_retrieval=False,
                reason="clearly unrelated request",
                direct_response=_direct_response("out_of_scope", arabic=arabic),
            )
        return self._decision(
            question,
            intent="clarification",
            requires_retrieval=False,
            reason=AMBIGUOUS_REASON,
            direct_response=_direct_response("clarification", arabic=arabic),
        )

    @staticmethod
    def _extract_json(text: str) -> dict[str, object]:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError("Router did not return a JSON object")
        value = json.loads(match.group(0))
        if not isinstance(value, dict):
            raise ValueError("Router JSON must be an object")
        return value

    def route(
        self,
        question: str,
        *,
        summary: str = "",
        recent_messages: Sequence[dict[str, str]] = (),
    ) -> RouterDecision:
        fallback = self._heuristic(question, summary=summary, recent_messages=recent_messages)
        # Obvious greetings, technical terms, abuse, noise, and known unrelated requests
        # are resolved without spending a model call. Only the ambiguous fallback may use it.
        if self.client is None or fallback.reason != AMBIGUOUS_REASON:
            return fallback

        history = "\n".join(
            f"{message['role']}: {message['content']}" for message in recent_messages
        )
        try:
            response = self.client.chat(
                [
                    {"role": "system", "content": ROUTER_SYSTEM_PROMPT.replace("{max_top_k}", str(self.max_top_k))},
                    {
                        "role": "user",
                        "content": (
                            f"Summary:\n{summary or '(none)'}\n\n"
                            f"Recent messages:\n{history or '(none)'}\n\n"
                            f"Question:\n{question}"
                        ),
                    },
                ],
                temperature=0.0,
                max_tokens=300,
                response_format={"type": "json_object"},
            )
            data = self._extract_json(response)
            boolean_fields = ("out_of_scope", "use_memory", "needs_images", "safety_sensitive")
            if any(type(data.get(key)) is not bool for key in boolean_fields):
                raise ValueError("Router flags must be JSON booleans")
            raw_top_k = data.get("top_k")
            query = data.get("retrieval_query")
            reason = data.get("reason")
            if type(raw_top_k) is not int or not 1 <= raw_top_k <= self.max_top_k:
                raise ValueError("Router top_k is outside the configured integer range")
            if not isinstance(query, str) or len(query) > 4000:
                raise ValueError("Router query must be a bounded string")
            if not isinstance(reason, str) or not reason.strip() or len(reason) > 300:
                raise ValueError("Router reason must be a bounded string")
            if data["out_of_scope"] is True:
                return self._decision(question, intent="out_of_scope", requires_retrieval=False,
                                      reason=reason, direct_response=_direct_response(
                                          "out_of_scope", arabic=_is_arabic(question)))
            if not query.strip():
                raise ValueError("A technical router query cannot be empty")
            needs_images = data["needs_images"] is True or fallback.needs_images
            return RouterDecision(
                intent="image_request" if needs_images else "technical_rag",
                requires_retrieval=True,
                out_of_scope=False,
                use_memory=data["use_memory"] is True,
                needs_images=needs_images,
                is_followup=False,
                safety_sensitive=data["safety_sensitive"] is True,
                top_k=max(1, min(raw_top_k, self.max_top_k)),
                retrieval_query=query.strip(),
                reason=reason.strip(),
                direct_response=None,
            )
        except Exception:
            return fallback
