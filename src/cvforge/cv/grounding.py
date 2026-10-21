"""Check that a reworded line adds nothing its entity's stored facts do not already say (FR-31).

A rewording keeps the claim's entity and assertion, but the words are no longer copied, so this
is the mechanical backstop against a rewrite smuggling in a fact. It is a heuristic and says so;
a collaborative edit is still a draft that is validated and reviewed before it is final. It
refuses a rewording that:

- is longer than the line it replaces by more than a few words (no new clauses);
- contains a number, or a token with a digit, that the facts do not (digits are NFKC-normalised,
  so fullwidth forms count), or states the facts' numbers in a different order or loses a `%`;
- contains a capitalised term, any token that names another stored entity, or a strong-claim
  or seniority word (stems such as lead/manag/found/senior/expert) that the facts do not;
- introduces a negation (`no`, `not`, `never`, `without`...) the facts do not contain.

Tokenisation is Unicode-aware, so accented and non-Latin words are seen, not dropped.
"""

import re
import unicodedata
from collections.abc import Iterable
from typing import Final

_TOKEN = re.compile(r"\w[\w+#.\-]*%?", re.UNICODE)
GROWTH_WORDS: Final = 3
NEGATIONS: Final = frozenset(
    {"no", "not", "never", "without", "none", "nor", "cannot", "neither", "ningún", "nunca", "sin"}
)
STRONG_STEMS: Final = (
    "lead", "led", "manag", "direct", "architect", "found", "own", "head", "supervis",
    "mentor", "spearhead", "pioneer", "launch", "oversaw", "oversee", "senior", "expert",
    "principal", "chief", "staff", "responsible", "ownership", "lider", "lideré", "dirig",
    "gestion", "fund", "руковод",
)  # fmt: skip


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def _tokens(text: str) -> list[str]:
    return [t.rstrip(".-") for t in _TOKEN.findall(_norm(text))]


def _is_number(token: str) -> bool:
    return any(ch.isdigit() for ch in token)


def _strong(token: str) -> bool:
    low = token.lower()
    return any(low == s or (len(s) > 4 and low.startswith(s)) for s in STRONG_STEMS)


def ungrounded_terms(
    facts: Iterable[str], text: str, *, other_entities: Iterable[str] = ()
) -> list[str]:
    """The terms or properties of `text` that its facts do not support.

    Args:
        facts: The stored texts the line may draw on.
        text: The reworded line.
        other_entities: Names of other stored entities; mentioning one the facts do not is
            flagged even in lowercase.

    Returns:
        Distinct findings, in order; empty means the rewording adds nothing recognisable.
    """
    fact_list = list(facts)
    known = {t.lower() for fact in fact_list for t in _tokens(fact)}
    entity_words = {t.lower() for name in other_entities for t in _tokens(name)} - known
    tokens = _tokens(text)
    found = [
        token
        for index, token in enumerate(tokens)
        if token.lower() not in known and _makes_a_claim(token, index, entity_words)
    ]
    found += _order_problems(fact_list, tokens)
    found += _growth_problem(fact_list, tokens)
    return list(dict.fromkeys(found))


def _makes_a_claim(token: str, index: int, entity_words: set[str]) -> bool:
    """True for a token that is not in the facts and would add a number, name or claim."""
    return (
        _is_number(token)
        or (index > 0 and token[:1].isupper())  # the first word is capitalised anyway
        or token.lower() in entity_words
        or _strong(token)
        or token.lower() in NEGATIONS
    )


def _growth_problem(facts: list[str], tokens: list[str]) -> list[str]:
    """A rewording may not add clauses: it stays within a few words of the longest stored line."""
    original = max((len(_tokens(f)) for f in facts), default=0)
    if original and len(tokens) > original + GROWTH_WORDS:
        return [f"{len(tokens)} words (more than {original} + {GROWTH_WORDS})"]
    return []


def _order_problems(facts: list[str], tokens: list[str]) -> list[str]:
    """Numbers must keep the order they have in some single stored fact."""
    new = [t.lower() for t in tokens if _is_number(t)]
    if len(new) < 2:
        return []
    for fact in facts:
        old = [t.lower() for t in _tokens(fact) if _is_number(t)]
        it = iter(old)
        if all(any(n == o for o in it) for n in new):
            return []
    return ["numbers out of their stored order"]
