"""Reference documents bundled with the package (printed by `ugs-matchsim docs <topic>`)."""

from __future__ import annotations

from importlib import resources

TOPICS = {
    "flow": "flow file reference: every field, the 7 expectation kinds, example, common mistakes",
    "output": "exit codes, --json schema, how to read failures and ticket reasons",
    "rules": "which parts of the rules JSON are supported (the spec inventory)",
    "interpretations": "simulator choices where the public docs are silent (N-items) and Limits",
}


def _read(name: str) -> str:
    return resources.files(__package__).joinpath(name).read_text(encoding="utf-8")


def _section(text: str, start: str, stop: str | None) -> str:
    a = text.index(start)
    b = text.index(stop, a) if stop else len(text)
    return text[a:b].rstrip() + "\n"


def topic_text(topic: str) -> str:
    if topic in ("flow", "output"):
        return _read(f"{topic}.md")
    inv = _read("spec-inventory.md")  # single source of truth for `rules` and `interpretations`
    if topic == "rules":
        return inv
    if topic == "interpretations":
        return ("# Interpretations and limits\n\nExtracted from the spec inventory (`ugs-matchsim docs rules`). "
                "N-items are simulator choices where the public docs are silent; results mention the ones that "
                "applied under `interpretations`.\n\n"
                + _section(inv, "## Not specified by the docs", "## Limits") + "\n"
                + _section(inv, "## Limits", "## Minimal examples"))
    raise KeyError(topic)
