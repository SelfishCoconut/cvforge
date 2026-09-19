# CVForge

A local-first personal professional knowledge system. It records everything you
know and have done professionally, with the evidence behind each fact, and uses
that knowledge to analyze job openings, generate tailored CVs, find gaps in your
skills, plan how to close them, and prepare you for interviews.

## The five invariants

1. The database is the source of truth, not the LLM.
2. `src/cvforge/kb/apply.py` is the only module that writes entity, edge or
   assertion rows. Agents have no write tools.
3. No entity and no edge exists without at least one assertion bound to an
   evidence span in a source.
4. Nothing reaches the database without review: agents propose, you accept, edit
   or reject each operation, and the commit is atomic.
5. Automatic-mode CV generation never emits a claim without a stored assertion.

## Where to look

- [Requirements](requirements/srs.md) — what the system must do.
- [Architecture overview](architecture/overview.md) — how it is put together.
- [Knowledge model](architecture/knowledge-model.md) — entities, relationships and provenance.
- [Decisions](adr/README.md) — why it is built this way.
