"""Alembic environment, driven programmatically by `cvforge.kb.migrate`.

There is no `alembic.ini`: the caller hands over an open connection through
`config.attributes["connection"]`, so migrations run on exactly the engine the
application uses, with its foreign-key pragma. `render_as_batch=True` is what
lets future migrations alter SQLite tables at all (SQLite has almost no ALTER).
"""

from alembic import context

from cvforge.kb.schema import metadata

connection = context.config.attributes["connection"]
context.configure(connection=connection, target_metadata=metadata, render_as_batch=True)
with context.begin_transaction():
    context.run_migrations()
