"""Parse Lua table literals (as found in Path of Building's data files) into Python.

This is a *data* parser, not an interpreter: it understands only literals
(tables, strings, numbers, booleans, nil) after an optional leading `return`.
Nothing in the input is ever executed.
"""

from __future__ import annotations

import re
from typing import Any

_TOKEN = re.compile(
    r"""
    (?P<skip>\s+|--\[(?P<ceq>=*)\[.*?\](?P=ceq)\]|--[^\n]*)
  | (?P<str>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')
  | (?P<long>\[(?P<leq>=*)\[.*?\](?P=leq)\])
  | (?P<num>-?(?:0[xX][0-9a-fA-F]+|(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?))
  | (?P<name>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op>[{}\[\]=,;])
    """,
    re.S | re.X,
)

_SIMPLE_ESCAPES = {
    "n": b"\n", "t": b"\t", "r": b"\r", "a": b"\a", "b": b"\b",
    "f": b"\f", "v": b"\v", "\\": b"\\", '"': b'"', "'": b"'", "\n": b"\n",
}


class LuaDataError(ValueError):
    pass


def _unescape(body: str) -> str:
    if "\\" not in body:
        return body
    out = bytearray()
    i, n = 0, len(body)
    while i < n:
        c = body[i]
        if c != "\\":
            out += c.encode("utf-8")
            i += 1
            continue
        e = body[i + 1]
        if e in _SIMPLE_ESCAPES:
            out += _SIMPLE_ESCAPES[e]
            i += 2
        elif e.isdigit():
            j = i + 1
            while j < n and j < i + 4 and body[j].isdigit():
                j += 1
            out.append(int(body[i + 1 : j]) & 0xFF)
            i = j
        else:  # unknown escape: keep the character
            out += e.encode("utf-8")
            i += 2
    return out.decode("utf-8", errors="replace")


def _tokens(text: str):
    pos, n = 0, len(text)
    while pos < n:
        m = _TOKEN.match(text, pos)
        if not m:
            snippet = text[pos : pos + 40].replace("\n", "\\n")
            raise LuaDataError(f"unexpected input at offset {pos}: {snippet!r}")
        pos = m.end()
        if m.group("skip") is not None:
            continue
        if m.group("str") is not None:
            yield ("val", _unescape(m.group("str")[1:-1]))
        elif m.group("long") is not None:
            s = m.group("long")
            eq = len(m.group("leq"))
            body = s[2 + eq : -(2 + eq)]
            yield ("val", body[1:] if body.startswith("\n") else body)
        elif m.group("num") is not None:
            t = m.group("num")
            if t.lstrip("-").lower().startswith("0x"):
                yield ("val", int(t, 16))
            elif re.fullmatch(r"-?\d+", t):
                yield ("val", int(t))
            else:
                yield ("val", float(t))
        elif m.group("name") is not None:
            yield ("name", m.group("name"))
        elif m.group("op") is not None:
            yield ("op", m.group("op"))
    yield ("eof", None)


class _Parser:
    def __init__(self, text: str):
        self._it = _tokens(text)
        self._advance()

    def _advance(self):
        self.kind, self.value = next(self._it)

    def _expect_op(self, op: str):
        if self.kind != "op" or self.value != op:
            raise LuaDataError(f"expected {op!r}, got {self.kind} {self.value!r}")
        self._advance()

    def parse_value(self) -> Any:
        if self.kind == "val":
            v = self.value
            self._advance()
            return v
        if self.kind == "name":
            v = self.value
            if v in ("true", "false", "nil"):
                self._advance()
                return {"true": True, "false": False, "nil": None}[v]
            raise LuaDataError(f"identifiers are not data: {v!r}")
        if self.kind == "op" and self.value == "{":
            return self.parse_table()
        raise LuaDataError(f"unexpected token {self.kind} {self.value!r}")

    def parse_table(self) -> Any:
        self._expect_op("{")
        array: list[Any] = []
        mapping: dict[Any, Any] = {}
        while not (self.kind == "op" and self.value == "}"):
            if self.kind == "op" and self.value == "[":
                self._advance()
                key = self.parse_value()
                self._expect_op("]")
                self._expect_op("=")
                mapping[key] = self.parse_value()
            elif self.kind == "name" and self.value not in ("true", "false", "nil"):
                key = self.value
                self._advance()
                self._expect_op("=")
                mapping[key] = self.parse_value()
            else:
                array.append(self.parse_value())
            if self.kind == "op" and self.value in (",", ";"):
                self._advance()
        self._advance()  # consume "}"
        if not mapping:
            return array
        for i, v in enumerate(array, start=1):
            mapping[i] = v
        return mapping


def loads(text: str) -> Any:
    """Parse a Lua data file (`return { ... }`) or a bare table literal."""
    p = _Parser(text)
    if p.kind == "name" and p.value == "return":
        p._advance()
    value = p.parse_value()
    if p.kind != "eof":
        raise LuaDataError(f"trailing input after value: {p.kind} {p.value!r}")
    return value
