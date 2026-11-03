"""Read-only check of the existing X posting session; never publishes a tweet."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.twikit_runtime import apply_twikit_transaction_patch


async def verify(client_factory=None) -> None:
    token = os.getenv("X_POST_AUTH_TOKEN") or os.getenv("X_AUTH_TOKEN")
    csrf = os.getenv("X_POST_CT0_TOKEN") or os.getenv("X_CT0_TOKEN")
    if not token or not csrf:
        raise RuntimeError("X_SESSION: posting cookie pair is missing")
    apply_twikit_transaction_patch()
    if client_factory is None:
        from twikit import Client
        client_factory = Client
    client = client_factory("en-US")
    try:
        client.set_cookies({"auth_token": token, "ct0": csrf})
        headers = {"Accept-Language": "en-US,en;q=0.9",
                   "Referer": "https://x.com", "User-Agent": client._user_agent}
        await client.client_transaction.init(client.http, headers)
        if not getattr(client.client_transaction, "key", None):
            raise RuntimeError("X_SESSION: transaction initialization incomplete")
        print("X_SESSION_READY: authenticated transaction initialization passed; no tweet sent")
    finally:
        await client.http.aclose()


def main() -> int:
    try:
        asyncio.run(verify())
    except Exception as exc:
        # Exception text from HTTP libraries may contain credentials or URLs.
        # Expose only our fixed diagnostics plus a safe exception category.
        text = str(exc)
        if text.startswith("X_SESSION:") or text.startswith("X transaction "):
            print(text)
        else:
            print(f"X_SESSION_FAILED: {type(exc).__name__}; verify current X posting cookies and connectivity")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
