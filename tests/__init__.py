"""Tests for OVMS integration."""
import pytest
from unittest.mock import patch, MagicMock
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from custom_components.ovms.const import DOMAIN
from tests.const import (
    UnitOfTemperature, 
    UnitOfLength, 
    UnitOfSpeed,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfPressure
)
