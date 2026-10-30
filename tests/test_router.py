import json

import pytest

from intelligent_scada.router.decision_router import DecisionRouter


def valid_decision():
    return dict(out_of_scope=False, use_memory=False, needs_images=False,
                safety_sensitive=False, top_k=4, retrieval_query='remote sensing',
                reason='Technical question')


class Client:
    def __init__(self, value):
        self.value = value
        self.calls = 0

    def chat(self, *args, **kwargs):
        self.calls += 1
        return self.value


@pytest.mark.parametrize(('field', 'value'), [
    ('out_of_scope', 'false'), ('use_memory', 1), ('needs_images', None),
    ('safety_sensitive', 'no'), ('top_k', True), ('top_k', 2.5),
    ('top_k', 0), ('top_k', 13), ('retrieval_query', []), ('retrieval_query', ''),
    ('reason', {}), ('reason', 'a' * 301),
])
def test_malformed_router_fields_use_deterministic_fallback(field, value):
    data = valid_decision()
    data[field] = value
    router = DecisionRouter(client=Client(json.dumps(data)))
    decision = router.route('Explain remote sensing')
    assert decision.intent == 'clarification'
    assert decision.requires_retrieval is False


def test_router_accepts_only_valid_json_and_configured_limit():
    router = DecisionRouter(max_top_k=4, client=Client(json.dumps(valid_decision())))
    assert router.route('Explain remote sensing').top_k == 4
    router.client = Client('not JSON')
    assert router.route('Explain remote sensing').intent == 'clarification'


@pytest.mark.parametrize('question', ['How do I set a tag?', 'What is the voltage?',
                                      'How does OPC UA work?', 'Alarm acknowledgement?',
                                      'How are alarms configured?'])
def test_scada_vocabulary_reaches_retrieval(question):
    assert DecisionRouter().route(question).requires_retrieval


def test_word_boundaries_avoid_false_social_and_technical_matches():
    assert DecisionRouter().route('Tell me a joke').intent == 'out_of_scope'
    assert DecisionRouter().route('A bookmark collection').intent == 'clarification'
    assert DecisionRouter().route('okay').intent == 'conversational'
