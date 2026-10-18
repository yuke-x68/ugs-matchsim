"""Shared helpers: errors, diagnostics, lenient JSON, value formatting."""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field
from typing import Any


class InputError(Exception):
    """Invalid input (CLI exit code 2). The message may hold several lines, one error each."""


@dataclass
class Diagnostics:
    warnings: list[str] = field(default_factory=list)
    # each: {"element": str, "effect": str}
    unsupported: list[dict[str, str]] = field(default_factory=list)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def unsupp(self, element: str, effect: str) -> None:
        self.unsupported.append({"element": element, "effect": effect})


def _line_col(text: str, pos: int) -> tuple[int, int]:
    line = text.count("\n", 0, pos) + 1
    return line, pos - (text.rfind("\n", 0, pos) + 1) + 1


def strip_jsonc(text: str) -> str:
    """Blank out line/block comments and trailing commas (string-aware).

    Every removed character becomes a space (newlines are kept), so line and column
    numbers of the stripped text equal those of the original file.
    """
    out = list(text)
    i, n, in_str = 0, len(text), False
    last_comma = -1  # index of a comma not yet followed by a value or a closer
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                in_str = False
        elif c == '"':
            in_str = True
            last_comma = -1
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                out[i] = " "
                i += 1
            continue
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end < 0:
                line, col = _line_col(text, i)
                raise InputError(f"line {line}, column {col}: unterminated block comment")
            for j in range(i, end + 2):
                if text[j] != "\n":
                    out[j] = " "
            i = end + 2
            continue
        elif c == ",":
            last_comma = i
        elif c in "}]":
            if last_comma >= 0:
                out[last_comma] = " "
            last_comma = -1
        elif c not in " \t\r\n":
            last_comma = -1
        i += 1
    return "".join(out)


def loads_lenient(text: str, what: str) -> Any:
    """Parse JSON with comments / trailing commas. `what` is the file name used in messages."""
    try:
        return json.loads(strip_jsonc(text))
    except InputError as e:
        raise InputError(f"{what}: {e}") from None
    except json.JSONDecodeError as e:
        raise InputError(f"{what}: line {e.lineno}, column {e.colno}: {e.msg}") from None


def did_you_mean(key: str, valid: list[str], aliases: dict[str, str] | None = None) -> str | None:
    low = key.lower()
    if aliases and low in aliases:
        return aliases[low]
    hit = difflib.get_close_matches(low, [v.lower() for v in valid], n=1, cutoff=0.6)
    return next(v for v in valid if v.lower() == hit[0]) if hit else None


def ci_keys(obj: Any, known: set[str], ctx: str, diag: Diagnostics) -> dict[str, Any]:
    """Case-insensitive key view. Returns lower-case key -> value; unknown keys warn."""
    if not isinstance(obj, dict):
        raise InputError(f"{ctx}: expected an object")
    out: dict[str, Any] = {}
    for k, v in obj.items():
        lk = k.lower()
        if lk in known:
            if lk in out:
                raise InputError(f"{ctx}: duplicate key '{k}' (keys are case-insensitive)")
            out[lk] = v
        else:
            diag.warn(f"{ctx}: unknown key '{k}' was ignored")
    return out


def is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def num(x: float) -> Any:
    """Stable JSON/text number: whole values as int, others rounded."""
    x = round(float(x), 6)
    return int(x) if x == int(x) else x


def fmt(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if is_num(v):
        return str(num(v))
    if isinstance(v, str):
        return v
    return json.dumps(v, ensure_ascii=False, sort_keys=True)
