import asyncio
from types import SimpleNamespace
import pytest
from tools.x_session_preflight import verify


def test_read_only_preflight_uses_posting_pair_and_closes_session(monkeypatch, capsys):
    monkeypatch.setenv('X_POST_AUTH_TOKEN', 'post-token')
    monkeypatch.setenv('X_POST_CT0_TOKEN', 'post-csrf')
    calls = []
    class Fake:
        _user_agent = 'test-agent'
        def __init__(self, language):
            async def close(): calls.append('closed')
            async def init(session, headers):
                assert headers['User-Agent'] == 'test-agent'
                self.client_transaction.key = 'verified'
            self.http = SimpleNamespace(aclose=close)
            self.client_transaction = SimpleNamespace(init=init)
        def set_cookies(self, cookies):
            assert cookies == {'auth_token': 'post-token', 'ct0': 'post-csrf'}
    asyncio.run(verify(Fake))
    assert calls == ['closed']
    assert 'X_SESSION_READY' in capsys.readouterr().out


def test_missing_cookie_pair_stops_before_network(monkeypatch):
    for name in ('X_AUTH_TOKEN', 'X_CT0_TOKEN', 'X_POST_AUTH_TOKEN', 'X_POST_CT0_TOKEN'):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError, match='cookie pair is missing'):
        asyncio.run(verify(lambda _: pytest.fail('must not connect')))
