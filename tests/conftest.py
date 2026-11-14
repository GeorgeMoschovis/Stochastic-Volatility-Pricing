"""Shared test inputs."""

import pytest


@pytest.fixture
def hull() -> dict:
    """Hull's textbook example: c = 4.76, p = 0.81."""
    return dict(S=42.0, K=40.0, T=0.5, r=0.10, sigma=0.20, q=0.0)
