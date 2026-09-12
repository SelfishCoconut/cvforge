"""Shared fixtures."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from cvforge.app import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A test client over a freshly built application with default settings."""
    with TestClient(create_app()) as test_client:
        yield test_client
