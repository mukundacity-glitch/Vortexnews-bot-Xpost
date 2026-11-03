from __future__ import annotations

from src import twikit_runtime
import asyncio
from types import SimpleNamespace
import pytest
from bs4 import BeautifulSoup


def test_twikit_transaction_patch_is_applied_and_idempotent():
    transaction = __import__(
        "twikit.x_client_transaction.transaction",
        fromlist=["ClientTransaction"],
    )

    twikit_runtime._APPLIED = False
    assert twikit_runtime.apply_twikit_transaction_patch() is True
    patched = transaction.ClientTransaction.get_indices
    assert patched.__module__ == "src.twikit_runtime"

    # Reapplying must not wrap/replace the method a second time.
    assert twikit_runtime.apply_twikit_transaction_patch() is True
    assert transaction.ClientTransaction.get_indices is patched


@pytest.mark.parametrize('page', [
    '{123:"ondemand.s"},{123:"abcdef1234567890"}',
    '{"ondemand.s":"abcdef1234567890"}',
])
def test_old_and_split_manifest(page):
    assert twikit_runtime.ondemand_url(page).endswith('ondemand.s.abcdef1234567890a.js')


def test_missing_manifest_does_not_invent_a_transaction():
    with pytest.raises(RuntimeError, match='authenticated X session'):
        twikit_runtime.ondemand_url('<script src="entry-client-logged-out.js"></script>')


def test_logged_out_shell_retries_authenticated_home_and_parses_long_indices():
    from twikit.x_client_transaction.transaction import ClientTransaction
    twikit_runtime.apply_twikit_transaction_patch()
    class Session:
        def __init__(self):
            self.calls = []
        async def request(self, **kw):
            self.calls.append(kw['url'])
            text = '{123:"ondemand.s"},{123:"abcdef"}' if kw['url'].endswith('/home') else '(longName[12],16),(other[42], 16)'
            return SimpleNamespace(text=text, raise_for_status=lambda: None)
    session = Session()
    ct = ClientTransaction()
    ct.home_page_response = BeautifulSoup('<html>logged out</html>', 'html.parser')
    result = asyncio.run(ct.get_indices(ct.home_page_response, session, {}))
    assert result == (12, [42])
    assert session.calls[0] == 'https://x.com/home'


def test_failed_initialization_clears_poisoned_state(monkeypatch):
    import twikit.x_client_transaction.transaction as transaction
    async def failed(self, session, headers):
        self.home_page_response = object()
        self.key = 'partial'
        raise RuntimeError('failed initialization')
    monkeypatch.setattr(transaction.ClientTransaction, 'init', failed)
    monkeypatch.setattr(twikit_runtime, '_APPLIED', False)
    twikit_runtime.apply_twikit_transaction_patch()
    ct = transaction.ClientTransaction()
    with pytest.raises(RuntimeError):
        asyncio.run(ct.init(None, {}))
    assert ct.home_page_response is None
    assert not hasattr(ct, 'key')
