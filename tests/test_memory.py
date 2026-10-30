from contextlib import contextmanager
from datetime import datetime

import pytest

from intelligent_scada.memory.memory_filters import is_context_useful
from intelligent_scada.memory.memory_store import MemoryStore


def test_unicode_technical_context_is_useful():
    assert is_context_useful('كيف أضبط الإنذار؟')
    assert not is_context_useful('!!!')
    assert not is_context_useful('Thank you')


def test_transcript_is_chronological_and_parses_stored_citations(monkeypatch):
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, sql, params):
            assert params == ('00000000-0000-0000-0000-000000000001', 100)

        def fetchall(self):
            return [('assistant', 'answer', '[]', datetime(2026, 1, 1)),
                    ('user', 'question', [], datetime(2026, 1, 1))]

    class Connection:
        def cursor(self):
            return Cursor()

    @contextmanager
    def transaction(_):
        yield Connection()

    monkeypatch.setattr('intelligent_scada.memory.memory_store.transaction', transaction)
    messages = MemoryStore(None).messages('00000000-0000-0000-0000-000000000001')
    assert [m['role'] for m in messages] == ['user', 'assistant']
    assert messages[1]['citations'] == []
    with pytest.raises(ValueError):
        MemoryStore(None).messages('00000000-0000-0000-0000-000000000001', limit=0)


def test_invalid_session_id_rejected_before_database():
    store = MemoryStore(None)
    for call in [lambda: store.create_or_load_session('manual', 'invalid'),
                 lambda: store.context('invalid'), lambda: store.messages('invalid'),
                 lambda: store.update_summary('invalid', 'text'),
                 lambda: store.useful_message_count('invalid'),
                 lambda: store.add_message('invalid', 'user', 'text', useful=True)]:
        with pytest.raises(ValueError, match='UUID'):
            call()
