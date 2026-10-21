"""Assemble a CV for a posting from stored facts only (FR-24, NFR-05).

Automatic mode makes no model call and writes no free text. What goes in is decided by the
posting's stored matches: the entities that back a `satisfied` or `evidenced` verdict, and
the roles, projects and achievements that touch them. A requirement's own words are never
rendered, and an `undocumented` or `gap` requirement contributes nothing (it has no
supporting entity to select). Every string is a `claim_source`, copied from a confirmed
entity together with the assertion that states it.
"""

from collections.abc import Iterable

import sqlalchemy as sa

from cvforge.cv.facts import claim_source
from cvforge.cv.model import ClaimDraft
from cvforge.kb import queries
from cvforge.kb.vocab import ClaimBasis, ClaimSlot, EntityKind, KnowledgeState, MatchVerdict, Rel
from cvforge.match.store import list_matches

_BACKED = frozenset({MatchVerdict.SATISFIED, MatchVerdict.EVIDENCED})
_USES = frozenset({Rel.USED_IN.value, Rel.DEMONSTRATES.value})
_PART = frozenset({Rel.PART_OF.value, Rel.PRODUCED.value, Rel.INVOLVED.value})
_AT_ORG = frozenset({Rel.AT_ORGANIZATION.value})
_CHILD_KINDS = frozenset({EntityKind.PROJECT, EntityKind.ACHIEVEMENT, EntityKind.RESPONSIBILITY})


class _Builder:
    """Collects claims, dropping any whose fact has no assertion."""

    def __init__(self, conn: sa.Connection) -> None:
        self.conn = conn
        self.claims: list[ClaimDraft] = []
        self._items: dict[str, int] = {}

    def new_item(self, section: str) -> int:
        index = self._items.get(section, -1) + 1
        self._items[section] = index
        return index

    def add(
        self,
        section: str,
        item: int,
        slot: ClaimSlot,
        position: int,
        entity_id: int,
        basis: ClaimBasis,
        link: int | None = None,
    ) -> bool:
        source = claim_source(self.conn, entity_id, basis)
        if source is None:
            return False
        text, assertion_id = source
        self.claims.append(
            ClaimDraft(section, item, slot, position, basis, text, entity_id, assertion_id, link)
        )
        return True


class _Graph:
    """The confirmed entities, and the edges between them, a CV may draw on."""

    def __init__(self, conn: sa.Connection) -> None:
        self.conn = conn
        confirmed = queries.list_entities(conn, state=KnowledgeState.CONFIRMED)
        self.kind = {e.id: e.kind for e in confirmed}

    def of_kind(self, kind: EntityKind) -> list[int]:
        return sorted(i for i, k in self.kind.items() if k is kind)

    def linked(self, entity_id: int, rels: frozenset[str]) -> set[int]:
        """Confirmed entities joined to `entity_id` by an edge of one of `rels`, either way."""
        ends: set[int] = set()
        for edge in queries.neighbours(self.conn, entity_id):
            if edge.rel in rels:
                ends.add(edge.dst_id if edge.src_id == entity_id else edge.src_id)
        return {i for i in ends if i in self.kind}


def _start(conn: sa.Connection, entity_id: int) -> str:
    record = queries.get_entity(conn, entity_id)
    return str(record.attributes.get("started_at") or "") if record else ""


def _seeds(engine: sa.Engine, posting_id: int, graph: _Graph) -> set[int]:
    """Entities that back a `satisfied` or `evidenced` requirement and are still confirmed."""
    backed = (
        e for m in list_matches(engine, posting_id) if m.verdict in _BACKED for e in m.support
    )
    return {e for e in backed if e in graph.kind}


def _touches(graph: _Graph, seeds: set[int], entity_id: int) -> bool:
    return entity_id in seeds or bool(graph.linked(entity_id, _USES) & seeds)


def _link(conn: sa.Connection, header: int, other: int) -> int | None:
    """The existence assertion of an edge joining `header` and `other`, if one exists."""
    for edge in queries.neighbours(conn, header):
        if {edge.src_id, edge.dst_id} == {header, other}:
            return queries.edge_existence_assertion_id(conn, edge.id)
    return None


def _add_item(
    out: _Builder, section: str, entity_id: int, bullets: Iterable[int], org: int | None = None
) -> None:
    item = out.new_item(section)
    out.add(section, item, ClaimSlot.HEADER, 0, entity_id, ClaimBasis.NAME)
    if org is not None:
        link = _link(out.conn, entity_id, org)
        if link is not None:
            out.add(section, item, ClaimSlot.SUBHEADER, 0, org, ClaimBasis.NAME, link)
    out.add(section, item, ClaimSlot.PERIOD, 0, entity_id, ClaimBasis.PERIOD)
    position = 0
    if out.add(section, item, ClaimSlot.BULLET, position, entity_id, ClaimBasis.SUMMARY):
        position += 1
    for child in bullets:
        link = _link(out.conn, entity_id, child)
        if link is None:
            continue
        for basis in (ClaimBasis.SUMMARY, ClaimBasis.NAME):
            if out.add(section, item, ClaimSlot.BULLET, position, child, basis, link):
                position += 1
                break


def _skills(out: _Builder, graph: _Graph, seeds: set[int]) -> None:
    skills = [i for i in graph.of_kind(EntityKind.SKILL) if i in seeds]
    if not skills:
        return
    item = out.new_item("Skills")
    for position, skill in enumerate(skills):
        out.add("Skills", item, ClaimSlot.BULLET, position, skill, ClaimBasis.NAME)


def _experience(out: _Builder, graph: _Graph, seeds: set[int]) -> set[int]:
    """Add the roles that touch the seeds; return the projects they already cover."""
    covered: set[int] = set()
    roles = sorted(graph.of_kind(EntityKind.ROLE), key=lambda r: (_start(out.conn, r), r))
    for role in reversed(roles):
        children = sorted(c for c in graph.linked(role, _PART) if graph.kind[c] in _CHILD_KINDS)
        if not (_touches(graph, seeds, role) or any(_touches(graph, seeds, c) for c in children)):
            continue
        orgs = sorted(
            o for o in graph.linked(role, _AT_ORG) if graph.kind[o] is EntityKind.ORGANIZATION
        )
        _add_item(out, "Experience", role, children, orgs[0] if orgs else None)
        covered.update(children)
    return covered


def _projects(out: _Builder, graph: _Graph, seeds: set[int], covered: set[int]) -> None:
    for project in graph.of_kind(EntityKind.PROJECT):
        if project not in covered and _touches(graph, seeds, project):
            _add_item(out, "Projects", project, ())


def _record(out: _Builder, graph: _Graph, kind: EntityKind, section: str) -> None:
    for entity_id in graph.of_kind(kind):
        _add_item(out, section, entity_id, ())


def generate_cv(engine: sa.Engine, posting_id: int) -> list[ClaimDraft]:
    """Generate the claims of an automatic-mode CV for a matched posting.

    Args:
        engine: The knowledge-base engine.
        posting_id: A `job_posting` id whose requirements have been matched.

    Returns:
        The claims, in render order. Every one carries the entity and assertion it was copied
        from; none is ever worded by a model.
    """
    with engine.connect() as conn:
        graph = _Graph(conn)
        seeds = _seeds(engine, posting_id, graph)
        out = _Builder(conn)
        _skills(out, graph, seeds)
        covered = _experience(out, graph, seeds)
        _projects(out, graph, seeds, covered)
        _record(out, graph, EntityKind.EDUCATION, "Education")
        _record(out, graph, EntityKind.CREDENTIAL, "Certifications")
    return out.claims
