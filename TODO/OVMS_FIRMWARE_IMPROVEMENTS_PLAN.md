# OVMS Firmware Improvements Implementation Plan

> **Created**: December 6, 2025  
> **Status**: Planning  
> **Related Issue**: [#180](https://github.com/enoch85/ovms-home-assistant/issues/180)  
> **OVMS Firmware Reference**: [changes.txt](https://raw.githubusercontent.com/openvehicles/Open-Vehicle-Monitoring-System-3/refs/heads/master/vehicle/OVMS.V3/changes.txt)

## Overview

The OVMS firmware (especially edge/unreleased) has significantly improved MQTT support. This plan outlines how to leverage these improvements to simplify the integration, improve reliability, and reduce maintenance burden.

**Key Contributor**: @zorgms (author of the MQTT firmware improvements)

**Note**: Features marked as "edge firmware" are not yet in stable 3.3.005 release.

---

## Phase 1: On-Demand Metric Request (HIGH PRIORITY)

### Problem
Current discovery relies on passive waiting (60 seconds) for OVMS to publish metrics. This is slow and unreliable if the vehicle hasn't recently published data.

### Firmware Feature
```
<prefix>/client/<clientid>/request/metric   -- payload: metric name(s) with wildcards
Example: "v.b.*" matches all metrics starting with "v.b."
         "*" requests ALL valid metrics
Each matching metric is published immediately on its normal topic.
```

### Implementation Tasks

#### 1.1 Add New Constants (`const.py`)
```python
# On-demand metric request topic (OVMS edge firmware)
# Allows requesting specific metrics or all metrics with wildcard
# Source: OVMS firmware changes.txt - MQTT client on-demand requests
METRIC_REQUEST_TOPIC_TEMPLATE = "{structure_prefix}/client/{client_id}/request/metric"
CONFIG_REQUEST_TOPIC_TEMPLATE = "{structure_prefix}/client/{client_id}/request/config"
CONFIG_RESPONSE_TOPIC_TEMPLATE = "{structure_prefix}/client/{client_id}/config/{param}/{instance}"

# Discovery timing - reduced because active requests are faster
ACTIVE_DISCOVERY_TIMEOUT = 10  # seconds to wait after requesting metrics
LEGACY_DISCOVERY_TIMEOUT = 60  # fallback for older firmware
```

#### 1.2 Update Topic Discovery (`config_flow/topic_discovery.py`)
- [ ] Add function `request_all_metrics()` that publishes `*` to the request topic
- [ ] Implement hybrid discovery:
  1. First, try active request (publish `*` to request topic)
  2. Wait short timeout (10 seconds)
  3. If no response, fall back to passive discovery (legacy behavior)
- [ ] Reduce default discovery time when active request succeeds

#### 1.3 Update MQTT Client (`mqtt/__init__.py`)
- [ ] Add `async_request_metrics()` method for on-demand metric refresh
- [ ] Remove `async_send_discovery_command()` workaround in `_async_platforms_loaded()`
- [ ] Add metric request during initial connection for faster entity creation

#### 1.4 Update Command Handler (`mqtt/command_handler.py`)
- [ ] Remove or deprecate `async_send_discovery_command()` (replaced by metric request)

### Expected Benefits
- Discovery time reduced from 60s to ~10s
- More reliable discovery (doesn't depend on OVMS publishing schedule)
- Simpler code (remove workarounds)

### Backwards Compatibility
- Keep legacy passive discovery as fallback for older firmware
- Detect firmware capability by checking for response to metric request

---

## Phase 2: Add Missing Standard Metrics (COMPLETED ✓)

### Status
**ALREADY IMPLEMENTED**: All metrics from this phase were found to already exist in the codebase:
- `v.b.capacity` ✓ in `battery.py`
- `v.b.range.speed` ✓ in `battery.py`
- `v.c.timestamp` ✓ in `charging.py`
- `v.c.kwh.grid` ✓ in `charging.py`
- `v.c.kwh.grid.total` ✓ in `charging.py`
- `v.p.gpssq` ✓ in `location.py`
- `v.p.gpstime` ✓ in `location.py`
- `v.p.location` ✓ in `location.py`
- `v.g.*` generator metrics ✓ in `power.py`
- `v.t.alert` ✓ in `tire.py`
- `v.t.health` ✓ in `tire.py`

No changes required - skipping to Phase 3.

---

## Phase 3: Simplify GPS Accuracy Handling (COMPLETED ✓)

### Status
**IMPLEMENTED**: GPS accuracy handling simplified to use only v.p.gpssq (edge firmware).

### Changes Made
1. Fixed `v.p.gpssq` metric in `location.py`:
   - Changed unit from `dBm` to `PERCENTAGE` (correct per OVMS firmware)
   - Updated description with quality thresholds (<30 unusable, >50 good, >80 excellent)
   - Removed incorrect `SensorDeviceClass.SIGNAL_STRENGTH`

2. Added GPS accuracy constants to `const.py`:
   - `GPS_ACCURACY_MIN_METERS = 5` - Minimum accuracy floor
   - `GPS_ACCURACY_MAX_METERS = 100` - Maximum accuracy (poorest quality)

3. Updated `mqtt/__init__.py::get_gps_accuracy()`:
   - Uses constants instead of hardcoded values
   - Improved docstring with firmware notes
   - Uses only v.p.gpssq (OVMS edge firmware)

4. Updated `attribute_manager.py::get_gps_attributes()`:
   - Uses constants instead of hardcoded values
   - Simplified to only handle v.p.gpssq (removed HDOP fallback)

---

## Phase 4: Documentation Updates (COMPLETED ✓)

### Status
**IMPLEMENTED**: Added firmware requirements and compatibility documentation.

### Changes Made
1. Updated `README.md`:
   - Added firmware version table (3.3.001, 3.3.004, 3.3.005, edge features)
   - Added OVMS-side metric filtering examples (metrics.include/exclude)
   - Updated to show edge firmware for new features

2. Created `docs/FIRMWARE_COMPATIBILITY.md`:
   - Detailed feature-to-version mapping
   - Fallback behavior documentation
   - Configuration recommendations
   - Link to OVMS changelog

---

## Phase 5: Climate Scheduling Service (LOWER PRIORITY)

### Firmware Feature
```
climatecontrol schedule set <day> <times>   -- Set schedule (format: HH:MM[/duration][,HH:MM...])
climatecontrol schedule list                -- List all configured schedules
climatecontrol schedule clear <day|all>     -- Clear schedule
climatecontrol schedule enable/disable      -- Global switch
climatecontrol schedule copy <src> <target> -- Copy schedules between days
```

### Implementation Tasks

#### 5.1 Add Climate Schedule Service (`services.py`)
- [ ] Add `ovms.set_climate_schedule` service
- [ ] Add `ovms.get_climate_schedule` service
- [ ] Add `ovms.clear_climate_schedule` service

#### 5.2 Update Service Definitions (`services.yaml`)
- [ ] Add schema for climate schedule services
- [ ] Add translations

---

## Phase 6: Config Request Capability (FUTURE)

### Firmware Feature
```
<prefix>/client/<clientid>/request/config   -- payload: param/instance
Response topic: <prefix>/client/<clientid>/config/<param>/<instance>
```

### Implementation Tasks (Deferred)
- [ ] Add service to request OVMS configuration values
- [ ] Consider creating diagnostic sensors for key OVMS settings
- [ ] Evaluate security implications of exposing configuration

---

## Testing Checklist

### Per-Phase Testing
- [ ] **Phase 1**: Test discovery with 3.3.005+ firmware AND older firmware
- [ ] **Phase 2**: Verify new metrics appear correctly with proper units/icons
- [ ] **Phase 3**: Confirm GPS accuracy displays correctly in device tracker
- [ ] **Phase 4**: Review documentation for accuracy
- [ ] **Phase 5**: Test climate scheduling with various vehicle types

### Regression Testing
- [ ] All existing sensors still work
- [ ] Commands still execute correctly
- [ ] Entity staleness management unaffected
- [ ] No increase in MQTT traffic
- [ ] Config migration works for existing users

### Code Quality
```bash
# Run after each phase
python3 scripts/tests/test_code_quality.py
black custom_components/ --check
pylint $(git ls-files '*.py')
```

---

## Implementation Order

| Phase | Priority | Estimated Effort | Dependencies |
|-------|----------|------------------|--------------|
| 1     | HIGH     | 2-3 hours        | None         |
| 2     | MEDIUM   | 1-2 hours        | None         |
| 3     | MEDIUM   | 1 hour           | Phase 2      |
| 4     | MEDIUM   | 1 hour           | Phase 1-3    |
| 5     | LOWER    | 2-3 hours        | None         |
| 6     | FUTURE   | TBD              | Phase 1      |

---

## Files to Modify

### Phase 1
- `custom_components/ovms/const.py`
- `custom_components/ovms/config_flow/topic_discovery.py`
- `custom_components/ovms/mqtt/__init__.py`
- `custom_components/ovms/mqtt/command_handler.py`
- `custom_components/ovms/mqtt/connection.py` (possibly)

### Phase 2
- `custom_components/ovms/metrics/common/battery.py`
- `custom_components/ovms/metrics/common/charging.py`
- `custom_components/ovms/metrics/common/location.py`
- `custom_components/ovms/metrics/common/tire.py`
- `custom_components/ovms/metrics/common/generator.py` (NEW)
- `custom_components/ovms/metrics/common/__init__.py`
- `custom_components/ovms/metrics/__init__.py`

### Phase 3
- `custom_components/ovms/mqtt/__init__.py`
- `custom_components/ovms/device_tracker.py`

### Phase 4
- `README.md`
- `docs/FIRMWARE_COMPATIBILITY.md` (NEW)

### Phase 5
- `custom_components/ovms/services.py`
- `custom_components/ovms/services.yaml`
- `custom_components/ovms/translations/*.json`

---

## Notes

### Firmware Detection Strategy
Since we can't directly query firmware version, we detect capabilities:
1. Publish metric request with `*` payload
2. If metrics arrive within short timeout → new firmware detected
3. If no response → fall back to legacy passive discovery

### Backwards Compatibility is Critical
Many users may have older OVMS firmware. All new features must gracefully degrade:
- New features should be additive
- Fallback to existing behavior when firmware doesn't support new features
- Log warnings (not errors) when falling back

### Rate Limiting Considerations
The firmware has basic rate-limiting on metric requests:
> "authenticated per client, with basic rate-limiting to prevent abuse"

Our implementation should:
- Only request metrics during setup/reconnection
- Not spam metric requests during normal operation
- Respect existing `CommandRateLimiter` patterns
