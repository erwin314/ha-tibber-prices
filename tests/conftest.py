"""Global fixtures for the tibber_prices integration."""
import pytest

# Loads the Home Assistant test fixtures provided by the plugin
pytest_plugins = "pytest_homeassistant_custom_component"

# This fixture automatically enables custom integrations for all tests
@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom components."""
    yield
