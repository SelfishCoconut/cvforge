"""NFR-05: the CV generated for a synthetic profile is pinned claim by claim.

Each claim is shown with the entity name and the assertion field behind it, so a change that
starts rendering something no assertion states shows as a snapshot diff.
"""

from collections.abc import Callable
from typing import Any

import pytest
import sqlalchemy as sa
from tests.support.profile import build_profile, matched_posting

from cvforge.cv.generate import generate_cv
from cvforge.kb import queries

pytestmark = pytest.mark.golden


@pytest.mark.parametrize(
    ("name", "skills"),
    [
        ("rust_posting", ("Rust",)),
        ("mixed_posting", ("Rust", "Python", "Haskell", "Fortran")),
        ("unbacked_posting", ("Fortran",)),
    ],
)
def test_generated_cv_matches_snapshot(
    name: str,
    skills: tuple[str, ...],
    kb: sa.Engine,
    propose: Any,
    golden: Callable[[str, object], None],
) -> None:
    build_profile(kb, propose)
    claims = generate_cv(kb, matched_posting(kb, *skills))
    rows = []
    with kb.connect() as conn:
        for c in claims:
            entity = queries.get_entity(conn, c.entity_id)
            assertion = queries.get_assertion(conn, c.assertion_id)
            assert entity is not None and assertion is not None
            rows.append(
                {
                    "section": c.section,
                    "item": c.item_index,
                    "slot": c.slot.value,
                    "text": c.text,
                    "entity": entity.name,
                    "states": assertion.field or "existence",
                }
            )
    golden(f"cv/{name}", rows)
