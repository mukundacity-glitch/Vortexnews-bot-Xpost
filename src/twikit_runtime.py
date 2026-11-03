"""Shared Twikit runtime compatibility patch for X media/tweet delivery.

X periodically changes the client transaction JavaScript that Twikit parses.
The main news bot already carried this workaround inline; keeping it here gives
all publishers one implementation and avoids tactical/news drift.
"""
from __future__ import annotations

import re


def ondemand_url(page: str) -> str:
    """Support both original and split webpack manifests; no fabricated hash."""
    direct = re.search(r"https://abs\.twimg\.com/responsive-web/client-web/ondemand\.s\.[a-zA-Z0-9]+\.js", page)
    if direct:
        return direct.group(0)
    index = re.search(r'''[,{]\s*(\d+)\s*:\s*["']ondemand\.s["']''', page)
    if index:
        match = re.search(r'''[,{]\s*''' + re.escape(index.group(1)) + r'''\s*:\s*["']([0-9a-f]+)["']''', page)
    else:
        match = re.search(r'''["']ondemand\.s["']\s*:\s*["']([0-9a-f]+)["']''', page)
    if not match:
        raise RuntimeError("X transaction bundle missing; verify authenticated X session")
    return f"https://abs.twimg.com/responsive-web/client-web/ondemand.s.{match.group(1)}a.js"

_APPLIED = False


def apply_twikit_transaction_patch() -> bool:
    """Apply the repository's proven Twikit transaction parser workaround once."""
    global _APPLIED
    if _APPLIED:
        return True

    try:
        transaction = __import__(
            "twikit.x_client_transaction.transaction",
            fromlist=["ClientTransaction"],
        )
    except Exception as exc:
        print(f"[PATCH] twikit transaction module not found, skipping patch: {exc}")
        return False

    transaction.ON_DEMAND_FILE_REGEX = re.compile(
        r',(\d+):["\']ondemand\.s["\']',
        flags=(re.VERBOSE | re.MULTILINE),
    )
    transaction.ON_DEMAND_HASH_PATTERN = r',{}:"([0-9a-f]+)"'
    transaction.INDICES_REGEX = re.compile(
        r'(\(\w{1,2}\[(\d{1,2})\],\s*16\))+',
        flags=(re.VERBOSE | re.MULTILINE),
    )

    async def _patched_get_indices(self, home_page_response, session, headers):
        response = self.validate_response(home_page_response) or self.home_page_response
        try:
            url = ondemand_url(str(response))
        except RuntimeError:
            # X now serves a Vite logged-out shell at /. Use the SAME
            # authenticated session at /home, never a separate anonymous client.
            from bs4 import BeautifulSoup
            home = await session.request(method="GET", url="https://x.com/home", headers=headers)
            home.raise_for_status()
            response = BeautifulSoup(home.text, "lxml")
            url = ondemand_url(str(response))
            self.home_page_response = response
        js_response = await session.request(method="GET", url=url, headers=headers)
        js_response.raise_for_status()
        # Minifier variable names and byte indices are no longer 1-2 chars.
        parsed = [int(value) for value in re.findall(r"\[\s*(\d+)\s*\]\s*,\s*16\b", js_response.text)]
        if len(parsed) < 2:
            raise RuntimeError("X transaction byte indices unavailable in current bundle")
        return parsed[0], parsed[1:]

    transaction.ClientTransaction.get_indices = _patched_get_indices
    original_init = transaction.ClientTransaction.init

    async def _atomic_init(self, session, headers):
        try:
            await original_init(self, session, headers)
        except Exception:
            # Twikit tests only home_page_response on the next request. A
            # failed init used to leave it set but key absent, poisoning retries.
            self.home_page_response = None
            for field in ("key", "key_bytes", "animation_key"):
                self.__dict__.pop(field, None)
            raise

    if not getattr(original_init, "_vortex_atomic", False):
        _atomic_init._vortex_atomic = True
        transaction.ClientTransaction.init = _atomic_init
    _APPLIED = True
    print("[PATCH] twikit ClientTransaction.get_indices patched (shared runtime).")
    return True
