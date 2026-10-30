from intelligent_scada.rag.answer_generator import AnswerGenerator


class RecordingClient:
    def __init__(self) -> None:
        self.calls = []

    def chat(self, messages, *, temperature, max_tokens, response_format=None):
        self.calls.append((messages, temperature, max_tokens))
        return "Grounded response [S1]."


def test_answer_generation_runs_through_langchain_prompt_pipeline() -> None:
    client = RecordingClient()
    generator = AnswerGenerator(client)
    result = generator.generate(
        "How is the controller configured?",
        [
            {
                "chunk_id": "chunk_000001",
                "text": "Configure the controller from the settings page.",
                "page_start": 10,
                "page_end": 10,
                "source_pages": [10],
                "section_title": "Configuration",
                "section_path": ["Controller", "Configuration"],
                "score": 0.95,
            }
        ],
    )

    assert result == "Grounded response [S1]."
    messages, temperature, max_tokens = client.calls[0]
    assert messages[0]["role"] == "system"
    system_prompt = " ".join(messages[0]["content"].split())
    assert "SCADA domain specialist" in system_prompt
    assert "social pleasantries politely" in system_prompt
    assert "readable Markdown" in system_prompt
    assert messages[1]["role"] == "user"
    assert "[S1] Controller > Configuration" in messages[1]["content"]
    assert temperature == 0.1
    assert max_tokens == 1400
