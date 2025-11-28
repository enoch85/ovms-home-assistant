# OVMS Home Assistant Integration - AI Coding Agent Instructions

Home Assistant custom integration providing MQTT-based vehicle monitoring via OVMS (Open Vehicle Monitoring System). **Production code affecting real vehicle data and commands.**

## Core Principles

1. **Read entire files before editing** - Never edit based on grep/partial reads
2. **Configuration-driven, never hardcode** - All values from `const.py`, never hardcode numbers, strings, timeouts, or dynamic values
3. **No regressions** - Preserve existing behavior unless explicitly improving with clear justification
4. **No breaking changes without reason** - Respect existing structure, only refactor when materially beneficial
5. **Test after every change** - Run `python3 scripts/tests/test_code_quality.py` after every code iteration to verify quality
6. **No verbose summaries** - User sees changes in editor, only respond if asked
7. **Keep it simple** - Clean code over complexity, cleanup as you go
8. **Ask before acting** - When uncertain, clarify first
9. **Format with black** - Run `black` on all Python code before committing (line length 88)

## Project Overview

This is a **Home Assistant custom integration** that connects electric vehicles via OVMS (Open Vehicle Monitoring System) modules through MQTT. The integration automatically discovers vehicle metrics, creates appropriate entities (sensors, binary sensors, device trackers, switches), and provides bidirectional command capability.

**Key Architectural Principle**: Discovery-based entity creation with pattern matching - the integration dynamically creates entities from MQTT topics rather than requiring manual configuration.

## Core Architecture

### Component Boundaries

```
MQTT Broker (external)
    ↓
MQTTConnectionManager (mqtt/connection.py)
    ↓
OVMSMQTTClient (mqtt/__init__.py) - orchestrates all components
    ├── TopicParser (mqtt/topic_parser.py) - identifies entity types from topics
    ├── StateParser (mqtt/state_parser.py) - converts MQTT payloads to HA states
    ├── EntityFactory (mqtt/entity_factory.py) - creates entities
    ├── UpdateDispatcher (mqtt/update_dispatcher.py) - pushes state updates
    ├── EntityRegistry (mqtt/entity_registry.py) - tracks created entities
    └── CommandHandler (mqtt/command_handler.py) - sends commands to vehicles
```

### Critical Data Flows

1. **Topic Discovery Flow**: During setup, the integration subscribes to `{prefix}/{mqtt_username}/{vehicle_id}/#` wildcard, collects all topics for ~5 seconds, then parses them to determine entity types.

2. **Entity Creation Pattern**: Topic → TopicParser (matches patterns in `metrics/patterns.py`) → EntityFactory → Platform-specific entity class → Home Assistant entity registry.

3. **State Updates**: MQTT message → StateParser (handles type conversion, array processing) → UpdateDispatcher → Entity state update via signal dispatch.

4. **Command Flow**: Service call → CommandHandler.async_send_command() → MQTT publish to `{prefix}/{username}/{vehicle_id}/client/rr/command/{command_id}` → Response on `{prefix}/{username}/{vehicle_id}/client/rr/response/{command_id}`.

### Configuration Management

- **Config Version**: Track in `const.py::CONFIG_VERSION` (currently 3)
- **Migration Pattern**: `__init__.py::async_migrate_entry()` handles version upgrades
- **Config Merge**: Always use `get_merged_config(entry)` - options override data
- **Stable Client IDs**: Generated as `ha_ovms_{sha256_hash[:12]}` from host+username+vehicle_id to prevent MQTT connection issues

## Critical Rules

### Always Read Full Files

Before editing, use `read_file` for entire file. Understand context, identify all change locations. Never edit based on grep results or partial file reads.

### Use Configuration Constants

**ALL numeric values, thresholds, and tuning parameters MUST be constants from `const.py`.**

```python
# ✅ Do this
from .const import DEFAULT_SCAN_INTERVAL, MAX_STATE_LENGTH, DEFAULT_COMMAND_TIMEOUT
timeout = DEFAULT_SCAN_INTERVAL
max_length = MAX_STATE_LENGTH
command_timeout = DEFAULT_COMMAND_TIMEOUT

# ❌ Never this
timeout = 60  # NEVER hardcode
max_len = 255  # NEVER hardcode
limit = 5  # NEVER hardcode
```

**Constant Reuse Across Files:**
- Production code imports from `const.py`
- Test code imports SAME constants
- NO duplicate definitions - single source of truth
- If constant exists, use it everywhere applicable

**When to Add New Constants:**
1. Any numeric threshold or tuning parameter
2. Any value used in multiple places
3. Any value that might need tuning
4. Add to `const.py` with descriptive comment
5. Update imports in ALL files that need it

### No Regressions or Unnecessary Breaking Changes

- Preserve existing behavior unless explicitly improving functionality
- Respect established patterns and structure
- Breaking changes require clear justification and benefit
- Consider migration path for existing users
- Test thoroughly to ensure no functionality lost

## Key Patterns & Conventions

### Metric Definition System

Metrics are defined in `metrics/` with a three-tier hierarchy:

1. **patterns.py**: Generic patterns (e.g., "temp", "voltage", "soc")
2. **common/*.py**: Category-specific metrics (battery.py, climate.py, etc.)
3. **vehicles/*.py**: Vehicle-specific overrides (vw_eup.py, smart_fortwo.py)

**Lookup Priority**: Vehicle-specific → Category-specific → Generic pattern → Fallback sensor

Example metric definition:
```python
"v.b.soc": {
    "name": "Battery State of Charge",
    "device_class": SensorDeviceClass.BATTERY,
    "state_class": SensorStateClass.MEASUREMENT,
    "unit": PERCENTAGE,
    "category": "battery",
    "icon": "mdi:battery",
}
```

### Entity Categorization

Use `EntityCategory` from `homeassistant.const`:
- `EntityCategory.DIAGNOSTIC` for system/debug metrics (network, logs)
- `None` (no category) for primary vehicle data
- Category is auto-determined in `AttributeManager.determine_entity_category()`

### State Value Handling

**Critical Rule**: Sensors with `SensorDeviceClass` or `SensorStateClass` MUST have numeric states. Use `StateParser.parse_value()` for all incoming data:

```python
# StateParser handles:
# - "yes"/"no" → 1/0 for numeric contexts
# - Array data → statistical processing (min/max/avg/median as attributes)
# - String numbers → float conversion
# - Invalid values → None (triggers unavailable state)
```

### Topic Blacklisting

System blacklist patterns in `const.py::SYSTEM_TOPIC_BLACKLIST` prevent high-frequency log topics from creating entities:
- Patterns are substring matches: "log" blocks all `.log` topics
- User patterns can extend but not remove system patterns
- Migration in `__init__.py::_migrate_blacklist_patterns()` handles upgrades

### Attribute Enrichment

`AttributeManager` adds contextual data:
- Battery levels: "low"/"medium"/"high" based on SoC
- Temperature comfort: "freezing"/"cold"/"comfortable"/"hot"
- GPS accuracy: calculated from signal quality metrics
- Cell statistics: min/max/avg/median for array data stored as attributes

## Development Workflows

### Adding Vehicle Support

1. Create `metrics/vehicles/{vehicle_name}.py`
2. Define `VEHICLE_METRICS` dict with vehicle-specific overrides
3. Import in `metrics/__init__.py` and add to `VEHICLE_SPECIFIC_METRICS`
4. Update README.md with vehicle name

### Adding New Entity Types

1. Add pattern to `metrics/patterns.py::TOPIC_PATTERNS`
2. If category-specific, add to appropriate `metrics/common/{category}.py`
3. Update `TopicParser._determine_entity_type()` if new logic needed
4. Create entity class in `sensor/entities.py` or `binary_sensor.py`

### Release Process

```bash
# Automated release (creates PR, tags, GitHub release)
bash scripts/release/release.sh v1.4.7

# Beta releases (marked as pre-release)
bash scripts/release/release.sh v1.4.7-beta
```

Release script:
- Updates version in `manifest.json` and `hacs.json`
- Creates release branch
- Generates changelog from commits
- Creates GitHub release with artifacts

## Integration Points

### MQTT Protocol

- **Client ID**: 20 chars max for MQTT 3.1/3.1.1 compatibility
- **QoS**: Default 1 (at least once delivery)
- **TLS**: Supported via `CONF_VERIFY_SSL`, uses port 8883
- **LWT**: Published to `{structure_prefix}/status` with "online"/"offline"

### Home Assistant Signals

Use dispatcher signals for component communication:
- `SIGNAL_ADD_ENTITIES`: Trigger platform entity addition
- `SIGNAL_UPDATE_ENTITY`: Push state updates to existing entities
- `SIGNAL_PLATFORMS_LOADED`: Notify MQTT client platforms are ready

**Pattern**: Always use `@callback` decorator for signal handlers to ensure execution in event loop.

### Services

Defined in `services.yaml` and implemented in `services.py`:
- `ovms.send_command`: Raw command interface with rate limiting (5/min)
- `ovms.control_climate`: Climate control wrapper
- `ovms.control_charging`: Charging control wrapper
- `ovms.homelink`: Vehicle-specific button triggers

**Rate Limiting**: Implemented in `rate_limiter.py` with token bucket algorithm.

## Common Pitfalls

### Entity Stability Issues

**Problem**: Entities recreated on every message, causing unique_id conflicts.
**Solution**: Check `unique_id` in `EntityFactory.created_entities` set before creating. Use deterministic unique_id generation from topic path.

### MQTT Client ID Collisions

**Problem**: Dynamic client IDs cause broker authentication failures.
**Solution**: Always use stable client_id from config migration. Never generate random IDs.

### Config Entry Migration

**Problem**: Missing fields after upgrade cause crashes.
**Solution**: Check `entry.version` in `async_setup_entry()`, call `async_migrate_entry()` BEFORE config merge. Always update `CONFIG_VERSION` when adding required fields.

### Numeric State Requirements

**Problem**: String values like "yes" cause errors for sensors with device_class.
**Solution**: Always use `StateParser.parse_value()` with device_class parameter. Parser handles string→number conversion.

### Topic Discovery Timing

**Problem**: Entities not created because discovery completed before vehicle published data.
**Solution**: Discovery runs for `CONF_SCAN_INTERVAL` (default 60s). For testing, trigger `server v3 update all` command on vehicle to force metric publishing.

## File Organization Logic

- `custom_components/ovms/`: Integration root
  - `__init__.py`: Entry point, config migration, platform setup
  - `const.py`: All constants, no logic
  - `config_flow/`: User setup flow (MQTT connection, topic discovery)
  - `mqtt/`: MQTT communication layer (connection, parsing, entity creation)
  - `metrics/`: Metric definitions (patterns, categories, vehicles)
  - `sensor/`: Sensor platform implementation
  - `binary_sensor.py`, `switch.py`, `device_tracker.py`: Other platforms
  - `services.py`: Service handlers
  - `translations/`: Localization files

**Naming Convention**: `async_` prefix for all async functions, `_` prefix for private methods.

## Code Standards

**Format with Black:** All Python code must be formatted with `black` (line length 88) before committing. Run `black .` at project root or use pre-commit hooks.

**Imports:** Group as stdlib, third-party, local. Relative imports within `custom_components/ovms/`.

**Error Handling:** Specific exceptions, log with context, graceful fallback.
```python
try:
    result = mqtt_client.async_send_command(command)
except MQTTError as e:
    _LOGGER.error("MQTT command failed: %s", e)
    return cached_state
```

**Type Hints:** Required on all functions. Use `Optional`, `Union`, `Dict[str, Any]`.

**Async:** Almost everything is async. Use `await`, sessions via `async_get_clientsession(hass)`.

**Docstrings:** Every public function/class. Include:
- What it does
- Parameters with types
- Returns
- OVMS-specific behavior notes if applicable
- Integration implications

```python
def parse_metric_topic(
    self,
    topic: str,
    vehicle_id: str,
) -> Optional[Dict[str, Any]]:
    """Parse OVMS MQTT topic to extract metric information.
    
    Handles various topic structures including custom formats.
    
    Args:
        topic: Full MQTT topic path (e.g., "ovms/user/vehicleid/v/b/soc")
        vehicle_id: Vehicle identifier for validation
        
    Returns:
        Dictionary with metric parts and metadata, or None if invalid
        
    Notes:
        Topic structure must match configured pattern in config entry.
        Blacklisted topics are filtered before this method is called.
    """
```

**Comments:** Explain WHY, not WHAT. Reference documentation for OVMS-specific decisions.

```python
# ✅ Good - explains reasoning
# MQTT client ID limited to 20 chars for MQTT 3.1/3.1.1 compatibility
# Longer IDs cause authentication failures with some brokers
client_id = f"ha_ovms_{hash[:12]}"

# ❌ Bad - obvious what
# Set client ID to 20 characters
client_id = f"ha_ovms_{hash[:12]}"
```

## Dependencies

- `paho-mqtt>=1.6.1`: MQTT client (do NOT use aiomqtt or asyncio-mqtt)
- Home Assistant 2025.2.5+
- Python 3.12+

**Important**: Use synchronous paho-mqtt with manual event loop integration via `hass.loop.run_in_executor()` for blocking calls.

## Testing & Quality Gates

CI/CD checks (must pass for merge):
- Pylint: Zero errors
- Code quality script: All tests pass
- HACS validation: Manifest compliant
- Hassfest: Home Assistant standards

**CRITICAL: Run after every code iteration:**
```bash
python3 scripts/tests/test_code_quality.py
```

This single command validates:
- Python syntax
- Code compilation
- Import statements
- Async/await patterns
- Black formatting (line length 88)
- File structure

### Additional Testing

```bash
# Code quality validation (primary command above)

# Run pylint (must pass for CI)
pylint $(git ls-files '*.py')

# Find hardcoded numeric values (CRITICAL CHECK!)
grep -rE "if .* [<>] -?[0-9]+\.?[0-9]*" custom_components/ovms/ | grep -v "const.py"
grep -rE "= -?[0-9]+\.?[0-9]* *#" custom_components/ovms/ | grep -v "const.py"
grep -rE "\* -?[0-9]+\.?[0-9]*" custom_components/ovms/ | grep -v "const.py"

# Verify constants are imported where used
grep -r "DEFAULT_SCAN_INTERVAL" custom_components/ovms/

# Test imports
python3 -c "from custom_components.ovms.mqtt import OVMSMQTTClient"

# Format with black
black custom_components/ scripts/ --check
```

## Common Mistakes

❌ **Editing without full context** - Read entire file, not grep results
❌ **Incomplete refactoring** - Search ALL occurrences, update ALL (including tests, docs)
❌ **Introducing regressions** - Test existing functionality, preserve working behavior
❌ **Breaking changes without justification** - Respect existing structure unless clear improvement
❌ **Forgetting base classes** - Update base classes first, they affect everything
❌ **Outdated documentation** - Update docstrings, comments, type hints with code

## Code Quality

**Remove dead code immediately:**
```python
# ❌ Don't leave
UNUSED_VAR = True  # Never used

# ✅ Delete it
```

**Fix duplicates:**
```python
# ❌ Same file
MAX_RETRIES = 10  # Line 18
MAX_RETRIES = 5   # Line 26 (overwrites!)

# ✅ One definition
MAX_RETRIES = 10  # Single value in const.py
```

**Document calculations:****
```python
# ✅ Show math when defining constants in const.py
# 5 commands per minute = 300 seconds / 60 = 5 commands
DEFAULT_COMMAND_RATE_LIMIT = 5
DEFAULT_COMMAND_RATE_PERIOD = 60.0  # seconds
```

**Reference source documentation:**
```python
# ✅ Good - traceable to MQTT specification
# MQTT 3.1/3.1.1 client ID max length: 23 characters
# Using 20 to leave buffer for broker-specific limitations
# Source: MQTT v3.1.1 specification, section 3.1.3.1
CLIENT_ID_MAX_LENGTH = 20

# ❌ Bad - no justification
CLIENT_ID_MAX_LENGTH = 20  # Don't exceed this
```

## Key Files

- Entry: `custom_components/ovms/__init__.py`
- Config version & migration: `__init__.py::async_migrate_entry()`
- Constants: `const.py` (all configuration values, no logic)
- MQTT orchestrator: `mqtt/__init__.py::OVMSMQTTClient`
- Topic patterns: `metrics/patterns.py::TOPIC_PATTERNS`
- Entity creation: `mqtt/entity_factory.py`
- State parsing: `mqtt/state_parser.py`
- Services: `services.py` + `services.yaml`

## Documentation Requirements

When adding features:
1. Update README.md with user-facing details
2. Add to `services.yaml` if creating services
3. Update translations in `translations/*.json`
4. Add examples to README for complex features

## Project Context

**Branch:** `main` - Stable production branch

**Integration:** Home Assistant custom component, config flow setup, HACS compatible

Quality and correctness over speed. When uncertain, ask before implementing.
