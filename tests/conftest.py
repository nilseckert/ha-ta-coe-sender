"""Fixtures für die Home-Assistant-Tests."""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Custom Integrations im Test-HA zulassen."""
    yield
