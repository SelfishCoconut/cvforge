"""Walk a CV's lineage (FR-27).

Versions are numbered per posting by `cv.store.save_cv` (1, 2, 3...), and a CV may name the
CV it was derived from. A parent must already exist, so parent links cannot form a cycle;
the walk still guards against one, because a lineage that never terminates would hang a
request.
"""

from sqlalchemy import Engine

from cvforge.cv.store import StoredCv, get_cv

MAX_DEPTH = 1000


class LineageError(Exception):
    """A CV's parent chain is broken or does not terminate."""


def lineage(engine: Engine, cv_id: int) -> list[StoredCv]:
    """The chain of CVs from the root version down to `cv_id`.

    Args:
        engine: The knowledge-base engine.
        cv_id: The CV whose ancestry to read.

    Returns:
        CVs ordered root first, ending with `cv_id`. A CV with no parent returns itself alone.

    Raises:
        LineageError: If the CV or an ancestor is missing, or the chain loops.
    """
    chain: list[StoredCv] = []
    seen: set[int] = set()
    current: int | None = cv_id
    while current is not None:
        if current in seen or len(chain) >= MAX_DEPTH:
            raise LineageError(f"CV {cv_id} has a lineage that never ends")
        seen.add(current)
        cv = get_cv(engine, current)
        if cv is None:
            raise LineageError(f"CV {current} is missing from the lineage of CV {cv_id}")
        chain.append(cv)
        current = cv.parent_cv_id
    return list(reversed(chain))
