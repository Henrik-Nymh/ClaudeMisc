"""Tiny HTTP helper (stdlib only) with an honest, configurable User-Agent."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

DEFAULT_USER_AGENT = "poe1-build-helper/0.1"


def user_agent() -> str:
    # GGG asks tools to identify themselves; set POE1_USER_AGENT to add contact info.
    return os.environ.get("POE1_USER_AGENT", DEFAULT_USER_AGENT)


class HttpError(RuntimeError):
    def __init__(self, url: str, status: int, body: str, headers: dict[str, str]):
        super().__init__(f"HTTP {status} for {url}: {body[:200]}")
        self.url, self.status, self.body, self.headers = url, status, body, headers


def request(
    url: str,
    *,
    data: Any = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30,
) -> tuple[bytes, dict[str, str]]:
    """GET (or POST JSON when `data` is given). Returns (body, headers)."""
    hdrs = {"User-Agent": user_agent(), "Accept": "application/json, text/plain, */*"}
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    hdrs.update(headers or {})
    req = urllib.request.Request(url, data=body, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(), {k.lower(): v for k, v in resp.headers.items()}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        raise HttpError(url, e.code, raw, {k.lower(): v for k, v in e.headers.items()}) from None


def get_text(url: str, **kw) -> str:
    return request(url, **kw)[0].decode("utf-8")
