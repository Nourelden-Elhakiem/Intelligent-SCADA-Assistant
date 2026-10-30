import httpx
import pytest

from intelligent_scada.rag.llm_client import LLMProviderError, OpenAICompatibleClient


def client_with_response(monkeypatch, handler):
    original = httpx.Client
    monkeypatch.setattr(httpx, 'Client', lambda **kwargs: original(
        transport=httpx.MockTransport(handler), **kwargs))
    return OpenAICompatibleClient(base_url='https://provider.invalid/v1',
                                  api_key='synthetic-private-key', model='synthetic')


@pytest.mark.parametrize('content', [None, [], {}, '', '   '])
def test_invalid_provider_content_never_becomes_an_answer(monkeypatch, content):
    client = client_with_response(monkeypatch, lambda req: httpx.Response(
        200, json={'choices': [{'message': {'content': content}}]}))
    with pytest.raises(LLMProviderError, match='invalid answer'):
        client.chat([{'role': 'user', 'content': 'question'}])


@pytest.mark.parametrize(('status', 'expected'), [(429, 503), (401, 502), (500, 502)])
def test_provider_http_errors_are_safe(monkeypatch, status, expected):
    client = client_with_response(monkeypatch, lambda req: httpx.Response(
        status, text='private provider body with synthetic-private-key'))
    with pytest.raises(LLMProviderError) as caught:
        client.chat([])
    assert caught.value.status_code == expected
    assert 'synthetic-private-key' not in str(caught.value)
    assert 'provider.invalid' not in str(caught.value)


def test_provider_timeout_and_valid_response(monkeypatch):
    def timeout(req):
        raise httpx.ReadTimeout('private details', request=req)

    client = client_with_response(monkeypatch, timeout)
    with pytest.raises(LLMProviderError) as caught:
        client.chat([])
    assert caught.value.status_code == 504
