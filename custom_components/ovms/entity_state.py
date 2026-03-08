"""State parsing helpers for OVMS entities."""

import json
from collections.abc import Iterable
from typing import TypeAlias

from .const import truncate_state_value

StateValues: TypeAlias = Iterable[str]
StatePair: TypeAlias = tuple[StateValues, StateValues]

BOOLEAN_TRUE_STATES = frozenset(("true", "on", "yes", "1"))
BOOLEAN_FALSE_STATES = frozenset(("false", "off", "no", "0"))

BINARY_SENSOR_TRUE_STATES = BOOLEAN_TRUE_STATES | frozenset(("open", "locked"))
BINARY_SENSOR_FALSE_STATES = BOOLEAN_FALSE_STATES | frozenset(("closed", "unlocked"))

LOCK_TRUE_STATES = BOOLEAN_TRUE_STATES | frozenset(("locked",))
LOCK_FALSE_STATES = BOOLEAN_FALSE_STATES | frozenset(("unlocked",))
SWITCH_TRUE_STATES = BOOLEAN_TRUE_STATES | frozenset(("enabled", "active"))
SWITCH_FALSE_STATES = BOOLEAN_FALSE_STATES | frozenset(("disabled", "inactive"))


def normalize_state_value(value: object) -> object:
    """Normalize a payload value for boolean parsing."""
    if isinstance(value, str):
        truncated_value = truncate_state_value(value)
        value = truncated_value if truncated_value is not None else value

        try:
            data = json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return value

        if isinstance(data, dict):
            for key in ("state", "value", "status"):
                if key in data:
                    return data[key]

        return data

    return value


def is_boolean_state(value: object, states: StatePair) -> bool:
    """Return True when a payload can be interpreted as a boolean-like state."""
    true_states, false_states = states
    normalized_value = normalize_state_value(value)

    if isinstance(normalized_value, (bool, int, float)):
        return True

    if isinstance(normalized_value, str):
        truncated_value = truncate_state_value(normalized_value)
        state = truncated_value if truncated_value is not None else normalized_value
        state_lower = state.lower()

        if state_lower in true_states or state_lower in false_states:
            return True

        try:
            float(state)
        except (TypeError, ValueError):
            return False

        return True

    try:
        float(normalized_value)
    except (TypeError, ValueError):
        return False

    return True


def parse_boolean_state(value: object, states: StatePair, flip: bool = False) -> bool:
    """Parse an OVMS payload value into a boolean state."""
    true_states, false_states = states
    normalized_value = normalize_state_value(value)

    if isinstance(normalized_value, bool):
        result = normalized_value
    elif isinstance(normalized_value, (int, float)):
        result = normalized_value > 0
    elif isinstance(normalized_value, str):
        truncated_value = truncate_state_value(normalized_value)
        state = truncated_value if truncated_value is not None else normalized_value
        state_lower = state.lower()

        if state_lower in true_states:
            result = True
        elif state_lower in false_states:
            result = False
        else:
            try:
                result = float(state) > 0
            except (TypeError, ValueError):
                result = False
    else:
        try:
            result = float(normalized_value) > 0
        except (TypeError, ValueError):
            result = False

    return not result if flip else result


def update_attributes_from_json(payload: object, attributes: dict[str, object]) -> None:
    """Update attributes with additional keys from a JSON payload."""
    if not isinstance(payload, str):
        return

    truncated_payload = truncate_state_value(payload)
    payload = truncated_payload if truncated_payload is not None else payload

    try:
        json_data = json.loads(payload)
    except (TypeError, ValueError, json.JSONDecodeError):
        return

    if not isinstance(json_data, dict):
        return

    for key, value in json_data.items():
        if key not in {"value", "state", "status"} and key not in attributes:
            attributes[key] = value

    if "timestamp" in json_data:
        attributes["device_timestamp"] = json_data["timestamp"]
