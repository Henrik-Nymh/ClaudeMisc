"""Decode/encode Path of Building export codes and fetch them from share sites."""

from __future__ import annotations

import base64
import re
import sys
import zlib
from pathlib import Path

from . import net

_SHARE_SITES = [
    # (pattern, raw url template)
    (re.compile(r"^https?://(?:www\.)?pobb\.in/(?:u/[^/]+/)?([A-Za-z0-9_-]+)/?$"), "https://pobb.in/{}/raw"),
    (re.compile(r"^https?://(?:www\.)?pastebin\.com/(?:raw/)?([A-Za-z0-9]+)/?$"), "https://pastebin.com/raw/{}"),
]


class PobCodeError(ValueError):
    pass


def decode(code: str) -> str:
    """PoB export code (base64url of zlib-deflated XML) -> XML text."""
    code = re.sub(r"\s+", "", code)
    code += "=" * (-len(code) % 4)
    try:
        raw = base64.urlsafe_b64decode(code)
        xml = zlib.decompress(raw).decode("utf-8")
    except Exception as e:  # noqa: BLE001 - surface a friendly error
        raise PobCodeError(f"not a valid Path of Building code: {e}") from None
    if "<PathOfBuilding" not in xml[:500]:
        raise PobCodeError("decoded data is not a Path of Building build")
    return xml


def encode(xml: str) -> str:
    """XML text -> PoB export code."""
    return base64.urlsafe_b64encode(zlib.compress(xml.encode("utf-8"), 9)).decode("ascii")


def share_raw_url(url: str) -> str | None:
    for pattern, template in _SHARE_SITES:
        m = pattern.match(url.strip())
        if m:
            return template.format(m.group(1))
    return None


def load(source: str) -> str:
    """Load build XML from a PoB code, share link, file path, or '-' (stdin)."""
    source = source.strip()
    if source == "-":
        return _from_text(sys.stdin.read())
    if re.match(r"^https?://", source):
        raw = share_raw_url(source) or source
        return _from_text(net.get_text(raw))
    try:
        path = Path(source)
        if path.is_file():
            return _from_text(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):  # e.g. a long code: "file name too long"
        pass
    return _from_text(source)


def _from_text(text: str) -> str:
    text = text.strip()
    if text.startswith("<"):
        if "<PathOfBuilding" not in text[:500]:
            raise PobCodeError("XML is not a Path of Building build")
        return text
    return decode(text)
