# OVMS Firmware Improvements Implementation Plan

> **Created**: December 6, 2025  
> **Status**: Planning  
> **Related Issue**: [#180](https://github.com/enoch85/ovms-home-assistant/issues/180)  
> **OVMS Firmware Reference**: [changes.txt](https://raw.githubusercontent.com/openvehicles/Open-Vehicle-Monitoring-System-3/refs/heads/master/vehicle/OVMS.V3/changes.txt)

## Overview

The OVMS firmware (especially edge/3.3.005+) has significantly improved MQTT support. This plan outlines how to leverage these improvements to simplify the integration, improve reliability, and reduce maintenance burden.

**Key Contributor**: @zorgms (author of the MQTT firmware improvements)

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
# On-demand metric request topic (OVMS 3.3.005+)
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

## Phase 2: Add Missing Standard Metrics (MEDIUM PRIORITY)

### Firmware Feature
Recent OVMS versions added standardized metrics that should be in our definitions.

### Implementation Tasks

#### 2.1 Update Battery Metrics (`metrics/common/battery.py`)
- [ ] Add `v.b.capacity` - Main battery usable capacity [kWh]
- [ ] Add `v.b.range.speed` - Momentary ideal range gain/loss speed [kph]

#### 2.2 Update Charging Metrics (`metrics/common/charging.py`)
- [ ] Add `v.c.timestamp` - Date & time of last charge end
- [ ] Add `v.c.kwh.grid` - Energy drawn from grid during session
- [ ] Add `v.c.kwh.grid.total` - Energy drawn from grid total (lifetime)

#### 2.3 Update Location Metrics (`metrics/common/location.py`)
- [ ] Add `v.p.gpssq` - GPS signal quality [%] (0-100, <30 unusable, >50 good, >80 excellent)
- [ ] Add `v.p.gpstime` - Time (UTC) of GPS coordinates [Seconds]
- [ ] Add `v.p.location` - Name of current location if defined

#### 2.4 Add Generator Metrics (NEW: `metrics/common/generator.py`)
For V2G (Vehicle-to-Grid) support:
- [ ] Add `v.g.generating` - True = currently delivering power
- [ ] Add `v.g.power` - Momentary generator output power
- [ ] Add `v.g.kwh` - Energy sum generated in the running session
- [ ] Add `v.g.kwh.grid` - Energy sent to grid during running session
- [ ] Add `v.g.kwh.grid.total` - Energy sent to grid total
- [ ] Add `v.g.timestamp` - Date & time of last generation end

#### 2.5 Update TPMS Metrics (`metrics/common/tire.py`)
- [ ] Add `v.t.alert` - TPMS tyre alert levels [0=normal, 1=warning, 2=alert]
- [ ] Add `v.t.health` - TPMS tyre health states
- [ ] Update `v.t.pressure` - Now a vector (fl,fr,rl,rr)
- [ ] Update `v.t.temp` - Now a vector

---

## Phase 3: Simplify GPS Accuracy Handling (MEDIUM PRIORITY)

### Problem
Current code in `mqtt/__init__.py` has custom GPS accuracy calculations based on signal quality and HDOP.

### Firmware Feature
`v.p.gpssq` provides normalized GPS signal quality (0-100%) directly.

### Implementation Tasks

#### 3.1 Update GPS Quality Tracking (`mqtt/__init__.py`)
- [ ] Prefer `v.p.gpssq` when available (standardized 0-100%)
- [ ] Keep HDOP-based calculation as fallback
- [ ] Simplify `get_gps_accuracy()` method

#### 3.2 Update Device Tracker (`device_tracker.py`)
- [ ] Use `v.p.gpssq` for GPS accuracy attribute when available
- [ ] Document the accuracy mapping in comments

---

## Phase 4: Documentation Updates (MEDIUM PRIORITY)

### Implementation Tasks

#### 4.1 Update README.md
- [ ] Add section on OVMS firmware requirements
- [ ] Document recommended firmware version (3.3.005+)
- [ ] Explain OVMS-side metric filtering options:
  ```
  [server.v3] metrics.include   -- Reduce MQTT traffic at source
  [server.v3] metrics.exclude   -- Exclude unwanted metrics
  ```

#### 4.2 Add Firmware Compatibility Notes
- [ ] Create `docs/FIRMWARE_COMPATIBILITY.md`
- [ ] Document which features require which firmware version
- [ ] Explain fallback behavior for older firmware

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
