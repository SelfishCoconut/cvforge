"""Check that a reworded line adds nothing its entity's stored facts do not already say (FR-31).

A rewording keeps the claim's entity and assertion, but the words are no longer copied, so
this is the backstop that stops a rewrite from smuggling in a fact. It is a heuristic, on
purpose conservative about what it recognises as new content:

- a number or any token with a digit (`50`, `3x`, `2019`);
- a capitalised term that is not the first word (a technology, employer, product, person);
- a strong-claim verb (`led`, `managed`, `architected`, `founded`...), which changes what the
  person did even though it is lowercase.

Each must already occur in the facts stored about the entity (its name, summary, attributes) or
about an entity it is directly related to. Everything else (articles, plain verbs, adjectives)
is free wording. What the heuristic cannot see, a human sees: a collaborative edit is a draft
that is validated, shown and only then made final.
"""

import re
from collections.abc import Iterable
from typing import Final

_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9+#.\-]*")
STRONG_VERBS: Final = frozenset(
    {
        "led",
        "lead",
        "leading",
        "managed",
        "manage",
        "directed",
        "architected",
        "founded",
        "owned",
        "headed",
        "supervised",
        "mentored",
        "spearheaded",
        "pioneered",
        "launched",
        "oversaw",
    }
)


def _tokens(text: str) -> list[str]:
    return [t.rstrip(".-") for t in _TOKEN.findall(text)]


def _needs_support(token: str, first: bool) -> bool:
    return (
        any(ch.isdigit() for ch in token)
        or (not first and token[:1].isupper())
        or token.lower() in STRONG_VERBS
    )


def ungrounded_terms(facts: Iterable[str], text: str) -> list[str]:
    """The terms in `text` that make a claim and appear in none of `facts`.

    Args:
        facts: The stored texts the line may draw on.
        text: The reworded line.

    Returns:
        Distinct terms, in order of appearance; empty means the rewording adds nothing.
    """
    known = {t.lower() for fact in facts for t in _tokens(fact)}
    tokens = _tokens(text)
    found: list[str] = []
    for index, token in enumerate(tokens):
        if _needs_support(token, index == 0) and token.lower() not in known:
            found.append(token)
    return list(dict.fromkeys(found))
