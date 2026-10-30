"""Grounded answer and memory-summary generation."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda

from intelligent_scada.contracts import RetrievalResult
from intelligent_scada.rag.llm_client import OpenAICompatibleClient
from intelligent_scada.rag.prompts import (
    ANSWER_SYSTEM_PROMPT,
    SUMMARY_SYSTEM_PROMPT,
    build_user_prompt,
)


class AnswerGenerator:
    def __init__(self, client: OpenAICompatibleClient) -> None:
        self.client = client
        self.answer_chain = self._build_chain(
            ANSWER_SYSTEM_PROMPT,
            temperature=0.1,
            max_tokens=1400,
        )
        self.summary_chain = self._build_chain(
            SUMMARY_SYSTEM_PROMPT,
            temperature=0.0,
            max_tokens=500,
        )

    @staticmethod
    def _provider_messages(messages: Sequence[BaseMessage]) -> list[dict[str, str]]:
        role_map = {"human": "user", "ai": "assistant"}
        return [
            {
                "role": role_map.get(message.type, message.type),
                "content": str(message.content),
            }
            for message in messages
        ]

    def _build_chain(
        self,
        system_prompt: str,
        *,
        temperature: float,
        max_tokens: int,
    ) -> Any:
        """Build a LangChain Runnable while retaining the existing model client."""
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("human", "{user_prompt}"),
            ]
        )

        def invoke_model(prompt_value: Any) -> AIMessage:
            content = self.client.chat(
                self._provider_messages(prompt_value.to_messages()),
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return AIMessage(content=content)

        return prompt | RunnableLambda(invoke_model) | StrOutputParser()

    def generate(
        self,
        question: str,
        results: Sequence[RetrievalResult],
        *,
        summary: str = "",
        recent_messages: Sequence[dict[str, str]] = (),
    ) -> str:
        return str(
            self.answer_chain.invoke(
                {
                    "user_prompt": build_user_prompt(
                        question,
                        results,
                        summary=summary,
                        recent_messages=recent_messages,
                    )
                }
            )
        )

    def summarize(self, previous_summary: str, messages: Sequence[dict[str, str]]) -> str:
        transcript = "\n".join(
            f"{message['role']}: {message['content']}" for message in messages
        )
        return str(
            self.summary_chain.invoke(
                {
                    "user_prompt": (
                        f"Previous summary:\n{previous_summary or '(none)'}\n\n"
                        f"Messages:\n{transcript}"
                    )
                }
            )
        )
