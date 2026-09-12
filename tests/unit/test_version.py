"""The package exposes a version string."""

import cvforge


def test_package_exposes_a_semver_version() -> None:
    assert cvforge.__version__.count(".") == 2
    assert all(part.isdigit() for part in cvforge.__version__.split("."))
