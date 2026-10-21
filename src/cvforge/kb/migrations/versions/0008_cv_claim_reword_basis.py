"""Allow the `reword` basis on cv_claim for collaborative edits (FR-31).

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-21 14:40:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply this revision."""
    # `compare_metadata` does not compare CHECK constraints, so this is hand-written and held by
    # test_the_migrated_check_constraints_match_the_declared_ones.
    with op.batch_alter_table("cv_claim", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_cv_claim_basis"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_cv_claim_basis"), "basis IN ('name', 'summary', 'period', 'reword')"
        )


def downgrade() -> None:
    """Revert this revision."""
    with op.batch_alter_table("cv_claim", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_cv_claim_basis"), type_="check")
        batch_op.create_check_constraint(
            op.f("ck_cv_claim_basis"), "basis IN ('name', 'summary', 'period')"
        )
