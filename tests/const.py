"""Constants and compatibility classes for testing."""
from homeassistant.const import (
    # Legacy constants
    TEMP_CELSIUS, TEMP_FAHRENHEIT,
    LENGTH_KILOMETERS, LENGTH_MILES,
)

# For newer Home Assistant versions
try:
    from homeassistant.const import (
        UnitOfTemperature,
        UnitOfLength,
        UnitOfSpeed,
        UnitOfElectricCurrent,
        UnitOfElectricPotential,
        UnitOfEnergy,
        UnitOfPower,
        UnitOfPressure,
    )
except ImportError:
    # Create compatibility classes for testing
    class UnitOfTemperature:
        CELSIUS = TEMP_CELSIUS
        FAHRENHEIT = TEMP_FAHRENHEIT
    
    class UnitOfLength:
        KILOMETERS = LENGTH_KILOMETERS
        MILES = LENGTH_MILES
    
    class UnitOfSpeed:
        KILOMETERS_PER_HOUR = "km/h"
        MILES_PER_HOUR = "mph"
    
    class UnitOfElectricCurrent:
        AMPERE = "A"
    
    class UnitOfElectricPotential:
        VOLT = "V"
    
    class UnitOfEnergy:
        KILO_WATT_HOUR = "kWh"
        WATT_HOUR = "Wh"
    
    class UnitOfPower:
        WATT = "W"
        KILO_WATT = "kW"
    
    class UnitOfPressure:
        KPA = "kPa"
